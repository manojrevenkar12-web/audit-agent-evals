"""The archive is the record: idempotent, verified, replayable, pruned only outside retention and never for evidence."""

import datetime as dt
import json

import pytest

from aae import config
from aae.agents.baseline import BaselineAgent
from aae.evals.match import match
from aae.traces import schema, store


@pytest.fixture(scope="module")
def recorded(unit_split, unit_truths, tmp_path_factory):
    agent = BaselineAgent("baseline")
    runs = {pid: agent.review(config.DATA / unit_split / "packages" / pid) for pid in list(unit_truths)[:6]}
    results = [match(unit_truths[pid], r.findings) for pid, r in runs.items()]
    rid = store.make_run_id(agent.id, unit_split, runs)
    at = dt.datetime(2026, 11, 2, 9, 30, tzinfo=dt.UTC)
    root = tmp_path_factory.mktemp("archive")
    folder = store.write_archive(rid, store.rows(rid, unit_split, runs, results, at), at.date(), root)
    return rid, runs, results, folder, root


def test_run_id_depends_only_on_answers(recorded, unit_split):
    rid, runs, *_ = recorded
    assert store.make_run_id("baseline@3", unit_split, runs) == rid
    changed = {k: v.model_copy(update={"findings": []}) for k, v in runs.items()}
    assert store.make_run_id("baseline@3", unit_split, changed) != rid


def test_archive_is_append_only_and_verified(recorded):
    rid, _, _, folder, root = recorded
    manifest = store.verify(folder)
    assert manifest["tables"]["runs"]["rows"] == 6
    before = (folder / "findings.parquet").read_bytes()
    store.write_archive(rid, {"runs": [], "spans": [], "findings": []}, dt.date(2026, 11, 2), root)
    assert (folder / "findings.parquet").read_bytes() == before


def test_tampering_is_detected(recorded, tmp_path):
    _, _, _, folder, _ = recorded
    copy = tmp_path / folder.name
    copy.mkdir()
    for p in folder.iterdir():
        (copy / p.name).write_bytes(p.read_bytes())
    data = bytearray((copy / "runs.parquet").read_bytes())
    data[100] ^= 0xFF
    (copy / "runs.parquet").write_bytes(bytes(data))
    with pytest.raises(ValueError):
        store.verify(copy)


def test_clickhouse_load_is_idempotent_and_answers_questions(recorded, tmp_path):
    rid, runs, results, folder, _ = recorded
    ch = store.ClickHouse(tmp_path / "ch")
    try:
        ch.load(folder)
        ch.load(folder)  # twice: ReplacingMergeTree + FINAL
        n = ch.query("SELECT count() AS n FROM {db}.runs FINAL")[0]["n"]
        assert int(n) == 6
        found = ch.query("SELECT sum(found) AS f, sum(defects) AS d FROM {db}.runs FINAL")[0]
        assert int(found["f"]) == sum(len(r.found) for r in results)
        verdicts = ch.query("SELECT verdict, count() AS n FROM {db}.findings FINAL GROUP BY verdict ORDER BY verdict")
        assert sum(int(v["n"]) for v in verdicts) == sum(len(r.findings) for r in results)
    finally:
        ch.close()


def test_replay_from_the_archive_alone_reproduces_every_verdict(recorded, unit_split):
    rid, *_, root = recorded
    out = store.replay(rid, unit_split, root)
    assert out["changed"] == [] and out["findings"] > 0


def test_prune_respects_retention_and_pins(recorded, tmp_path, monkeypatch):
    rid, _, _, folder, root = recorded
    pins = tmp_path / "pins"
    pins.mkdir()
    monkeypatch.setattr(store, "pinned_runs", lambda: {rid})
    late = dt.date(2026, 11, 2) + dt.timedelta(days=1000)
    assert store.prune(dt.date(2026, 12, 1), root, dry_run=True) == {"removed": [], "kept_pinned": []}
    assert store.prune(late, root, dry_run=True) == {"removed": [], "kept_pinned": [rid]}
    monkeypatch.setattr(store, "pinned_runs", lambda: set())
    assert store.prune(late, root, dry_run=True)["removed"] == [rid]


def test_schemas_come_from_one_definition():
    for table in schema.TABLES:
        names = [n for n, _, _ in schema.TABLES[table]]
        assert schema.arrow_schema(table).names == names
        assert [c["name"] for c in schema.bigquery_schema(table)] == names
        ddl = schema.clickhouse_ddl(table, "aae", 90)
        assert all(f"`{n}`" in ddl for n in names) and "TTL day + INTERVAL 90 DAY" in ddl


def test_bigquery_schema_files_are_generated(tmp_path):
    for table in schema.TABLES:
        path = config.ROOT / "infra" / "bigquery" / f"{table}.json"
        assert json.loads(path.read_text()) == schema.bigquery_schema(table), f"regenerate {path} (aae schema)"
