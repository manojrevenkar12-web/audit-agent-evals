"""Evaluate an agent on a split and decide releases; every result is recorded as a trace and a report.

evaluate(agent, split)        run (or reuse saved answers), score, record, write reports/evals/<split>/<agent>.json
release(candidate)            evaluate production and candidate on the gate split, apply the gates, and
                              write reports/releases/<candidate>.json naming the runs it rests on
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

from .. import config
from ..agents import registry
from ..traces import store
from .gate import decide
from .metrics import Counts, summary
from .run import load_runs, run_agent, score_runs


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def operational(runs: dict) -> dict:
    lat = [sum(s.duration_ms for s in r.spans) / 1000 for r in runs.values()]
    cost = [sum(s.cost_usd for s in r.spans) for r in runs.values()]
    tokens = [sum(s.input_tokens + s.output_tokens + s.cache_read_tokens for s in r.spans) for r in runs.values()]
    return {
        "cost_per_package_usd": float(np.mean(cost)) if cost else 0.0,
        "cost_total_usd": float(sum(cost)),
        "p50_latency_s": float(np.percentile(lat, 50)) if lat else 0.0,
        "p95_latency_s": float(np.percentile(lat, 95)) if lat else 0.0,
        "tokens_per_package": float(np.mean(tokens)) if tokens else 0.0,
        "errors": sum(1 for r in runs.values() if r.error),
        "pages_unreadable": sum(r.pages_unreadable for r in runs.values()),
    }


def evaluate(
    name: str, split: str, workers: int = 4, record: bool = True, now: dt.datetime | None = None
) -> tuple[dict, Counts]:
    agent = registry.get(name)
    run_agent(name, split, workers=workers)
    runs = load_runs(split, agent.id)
    results, c = score_runs(split, runs)
    b = config.load("gates")["bootstrap"]
    report = {
        "agent": agent.id,
        "split": split,
        **summary(c, b=b["resamples"], seed=b["seed"], level=b["level"]),
        "operational": operational(runs),
    }
    v = report["verdicts"]
    report["operational"]["duplicates_per_finding"] = v["duplicate"] / report["findings"] if report["findings"] else 0.0
    if record:
        recorded_at = now or _now()
        rid = store.make_run_id(agent.id, split, runs)
        folder = store.write_archive(rid, store.rows(rid, split, runs, results, recorded_at), recorded_at.date())
        report["run_id"] = rid
        report["archive"] = str(folder.relative_to(config.ROOT))
    out = config.REPORTS / "evals" / split / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    return report, c


def release(candidate: str, workers: int = 4, now: dt.datetime | None = None) -> dict:
    cfg = config.load("gates")
    production = config.load("agents")["production"]
    split = cfg["split"]
    base_report, base = evaluate(production, split, workers, now=now)
    cand_report, cand = evaluate(candidate, split, workers, now=now)
    decision = decide(base if candidate != production else None, cand, cfg)
    ops = {k: cand_report["operational"].get(k) for k in cfg["watch"] if k in cand_report["operational"]}
    ops.update({k: cand_report["metrics"][k]["value"] for k in cfg["watch"] if k in cand_report["metrics"]})
    out = {
        "candidate": cand_report["agent"],
        "production": base_report["agent"],
        "split": split,
        "decided_at": (now or _now()).isoformat(),
        **decision,
        "watch": ops,
        "evidence_runs": [base_report.get("run_id"), cand_report.get("run_id")],
    }
    folder = config.REPORTS / "releases"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{candidate}.json").write_text(json.dumps(out, indent=1))
    (folder / f"{candidate}.md").write_text(render_release(out))
    return out


def _f(v: float | None) -> str:
    return "–" if v is None else f"{v:.3f}"


def render_release(d: dict) -> str:
    lines = [
        f"# Release decision: {d['candidate']}",
        "",
        f"Compared with production `{d['production']}` on the `{d['split']}` split. "
        f"**{'Ship' if d['ship'] else 'Do not ship'}.**",
        "",
    ]
    if d["failed"]:
        lines += ["Failed: " + "; ".join(d["failed"]), ""]
    lines += ["| Rule | Metric | Value | Limit | 95% interval | Result |", "|---|---|---|---|---|---|"]
    for c in d["checks"]:
        ci = "" if c["low"] is None else f"[{_f(c['low'])}, {_f(c['high'])}]"
        val = _f(c["value"]) if c["rule"] == "floor" else (f"{c['value']:+.3f}" if c["value"] is not None else "–")
        lines.append(f"| {c['rule']} | {c['metric']} | {val} | {c['limit']:+.2f} | {ci} | {c['status']} |")
    lines += [
        "",
        "Watched, not gating: "
        + ", ".join(f"{k} {_f(v) if isinstance(v, float) else v}" for k, v in d["watch"].items()),
        "",
        f"Evidence runs (pinned in the trace archive): {', '.join(str(r) for r in d['evidence_runs'])}",
        "",
    ]
    return "\n".join(lines)


def report_path(split: str, name: str) -> Path:
    return config.REPORTS / "evals" / split / f"{name}.json"
