"""Record evaluation runs as traces: an append-only Parquet archive, loaded into ClickHouse for queries.

The archive is the record. ClickHouse holds the recent part (a TTL drops old partitions) and can be rebuilt from
the archive at any time; writes are idempotent (a run's id is derived from its answers, and the tables are
ReplacingMergeTree, read with FINAL), so loading twice changes nothing. A run can be replayed from the archive
alone: its findings are re-scored with the current matcher and every changed verdict is listed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import uuid
from collections.abc import Iterable
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .. import config
from ..agents.schema import AgentRun, Finding
from ..evals.match import PackageResult, match
from . import schema

NAMESPACE = uuid.UUID("6f1c2b0e-9a53-4c1e-8d0e-6b8f3f1d2a77")


def settings() -> dict:
    return config.load("traces")


def archive_root() -> Path:
    return config.ROOT / settings()["archive"]["path"]


def make_run_id(agent_id: str, split: str, runs: dict[str, AgentRun]) -> str:
    """Same agent, split and answers give the same id, so recording a run twice is harmless."""
    h = hashlib.sha256(f"{agent_id}|{split}".encode())
    for pid in sorted(runs):
        h.update(runs[pid].model_dump_json(exclude={"spans"}).encode())
    return str(uuid.uuid5(NAMESPACE, h.hexdigest()))[:18]


def rows(
    run_id: str, split: str, runs: dict[str, AgentRun], results: list[PackageResult], recorded_at: dt.datetime
) -> dict[str, list[dict]]:
    by_pkg = {r.package: r for r in results}
    day = recorded_at.date()
    out: dict[str, list[dict]] = {"runs": [], "spans": [], "findings": []}
    for pid in sorted(runs):
        run, res = runs[pid], by_pkg[pid]
        common = {"run_id": run_id, "day": day, "agent": run.agent, "split": split, "package": pid}
        out["runs"].append(
            {
                **common,
                "recorded_at": recorded_at,
                "error": run.error,
                "findings": len(run.findings),
                "defects": len(res.defects),
                "found": len(res.found),
                "pages_read": run.pages_read,
                "pages_unreadable": run.pages_unreadable,
                "scanned": res.scanned,
                "cost_usd": sum(s.cost_usd for s in run.spans),
                "latency_ms": sum(s.duration_ms for s in run.spans if s.kind != "check")
                or sum(s.duration_ms for s in run.spans),
            }
        )
        for seq, s in enumerate(run.spans):
            out["spans"].append(
                {
                    **common,
                    "seq": seq,
                    "name": s.name,
                    "kind": s.kind,
                    "started_ms": s.started_ms,
                    "duration_ms": s.duration_ms,
                    "input_tokens": s.input_tokens,
                    "output_tokens": s.output_tokens,
                    "cache_read_tokens": s.cache_read_tokens,
                    "cost_usd": s.cost_usd,
                    "model": s.model,
                    "status": s.status,
                    "attributes": json.dumps(s.attributes, sort_keys=True),
                }
            )
        for fr in res.findings:
            f = fr.finding
            out["findings"].append(
                {
                    **common,
                    "idx": fr.index,
                    "type": f.type,
                    "document": f.document,
                    "page": f.page,
                    "row_label": f.row_label,
                    "col": f.column,
                    "quote": f.quote,
                    "found_value": f.found_value,
                    "expected_value": f.expected_value,
                    "explanation": f.explanation,
                    "confidence": f.confidence,
                    "verdict": fr.verdict,
                    "defect": fr.defect,
                    "located": fr.location.how,
                }
            )
    return out


def write_archive(run_id: str, table_rows: dict[str, list[dict]], day: dt.date, root: Path | None = None) -> Path:
    root = root or archive_root()
    folder = root / f"dt={day.isoformat()}" / f"run={run_id}"
    manifest_path = folder / "manifest.json"
    if manifest_path.exists():  # already archived: the archive is append-only
        return folder
    tmp = folder.with_name(folder.name + ".tmp")
    tmp.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"run_id": run_id, "day": day.isoformat(), "tables": {}}
    for table, items in table_rows.items():
        t = pa.Table.from_pylist(items, schema=schema.arrow_schema(table))
        path = tmp / f"{table}.parquet"
        pq.write_table(t, path, compression="zstd")
        manifest["tables"][table] = {"rows": t.num_rows, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1))
    tmp.rename(folder)
    return folder


def verify(folder: Path) -> dict:
    """Check an archived run against its manifest before anyone relies on it."""
    manifest = json.loads((folder / "manifest.json").read_text())
    for table, meta in manifest["tables"].items():
        data = (folder / f"{table}.parquet").read_bytes()
        if hashlib.sha256(data).hexdigest() != meta["sha256"]:
            raise ValueError(f"{folder.name}/{table}.parquet does not match its manifest")
    return manifest


def find_run(run_id: str, root: Path | None = None) -> Path:
    root = root or archive_root()
    hits = list(root.glob(f"dt=*/run={run_id}"))
    if not hits:
        raise KeyError(f"run {run_id} is not in the archive")
    return hits[0]


def archived_runs(root: Path | None = None) -> list[Path]:
    root = root or archive_root()
    return sorted(p for p in root.glob("dt=*/run=*") if (p / "manifest.json").exists())


# ---------------------------------------------------------------------------------------------- ClickHouse


class ClickHouse:
    """Embedded ClickHouse (chdb) over a local data path; the same SQL runs on a ClickHouse server."""

    def __init__(self, path: Path | None = None):
        from chdb import session

        s = settings()["clickhouse"]
        self.db = s["database"]
        self.hot_days = int(s["hot_days"])
        self.path = path or config.ROOT / s["path"]
        self.path.mkdir(parents=True, exist_ok=True)
        self.s = session.Session(str(self.path))
        self.s.query(f"CREATE DATABASE IF NOT EXISTS {self.db}")
        for table in schema.TABLES:
            self.s.query(schema.clickhouse_ddl(table, self.db, self.hot_days))

    def close(self) -> None:
        self.s.close()

    def load(self, folder: Path) -> None:
        verify(folder)
        for table in schema.TABLES:
            cols = ", ".join(f"`{n}`" for n, _, _ in schema.TABLES[table])
            self.s.query(
                f"INSERT INTO {self.db}.{table} ({cols}) SELECT {cols} FROM file('{folder / (table + '.parquet')}', Parquet)"
            )

    def rebuild(self, folders: Iterable[Path]) -> int:
        for table in schema.TABLES:
            self.s.query(f"TRUNCATE TABLE IF EXISTS {self.db}.{table}")
        n = 0
        for f in folders:
            self.load(f)
            n += 1
        return n

    def query(self, sql: str) -> list[dict]:
        out = str(self.s.query(sql.replace("{db}", self.db), "JSONEachRow")).strip()
        return [json.loads(line) for line in out.splitlines() if line]


# ------------------------------------------------------------------------------------------------- replay


def replay(run_id: str, split: str | None = None, root: Path | None = None) -> dict:
    """Re-score an archived run with today's matcher and truth; list every verdict that changed."""
    folder = find_run(run_id, root)
    verify(folder)
    findings = pq.read_table(folder / "findings.parquet").to_pylist()
    runs = pq.read_table(folder / "runs.parquet").to_pylist()
    split = split or runs[0]["split"]
    by_pkg: dict[str, list[dict]] = {r["package"]: [] for r in runs}
    for f in findings:
        by_pkg[f["package"]].append(f)
    changed, total = [], 0
    for pid, items in sorted(by_pkg.items()):
        items.sort(key=lambda r: r["idx"])
        objs = [
            Finding(
                type=r["type"],
                document=r["document"],
                page=r["page"],
                row_label=r["row_label"],
                column=r["col"],
                quote=r["quote"],
                found_value=r["found_value"],
                expected_value=r["expected_value"],
                explanation=r["explanation"],
                confidence=r["confidence"],
            )
            for r in items
        ]
        truth = json.loads((config.DATA / split / "truth" / f"{pid}.json").read_text())
        res = match(truth, objs)
        for r, fr in zip(items, res.findings, strict=True):
            total += 1
            if fr.verdict != r["verdict"] or fr.defect != r["defect"]:
                changed.append(
                    {
                        "package": pid,
                        "idx": r["idx"],
                        "was": r["verdict"],
                        "now": fr.verdict,
                        "defect_was": r["defect"],
                        "defect_now": fr.defect,
                    }
                )
    return {"run_id": run_id, "findings": total, "changed": changed}


# -------------------------------------------------------------------------------------------------- prune


def pinned_runs() -> set[str]:
    folder = config.ROOT / settings()["pins"]
    pins: set[str] = set()
    for p in folder.glob("*.json"):
        pins |= set(json.loads(p.read_text()).get("evidence_runs", []))
    return pins


def prune(today: dt.date, root: Path | None = None, dry_run: bool = False) -> dict:
    keep = int(settings()["archive"]["keep_days"])
    pins = pinned_runs()
    removed, kept_pinned = [], []
    for folder in archived_runs(root):
        day = dt.date.fromisoformat(folder.parent.name.removeprefix("dt="))
        if (today - day).days <= keep:
            continue
        rid = folder.name.removeprefix("run=")
        if rid in pins:
            kept_pinned.append(rid)
            continue
        removed.append(rid)
        if not dry_run:
            shutil.rmtree(folder)
    return {"removed": removed, "kept_pinned": kept_pinned}
