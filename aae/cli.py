"""aae: build datasets, run agents, score them, decide releases, keep traces.

aae build [split ...]                 seeded-defect packages (PDFs + truth)
aae eval <agent> [--split dev]        run, score, record; prints the metrics with 95% intervals
aae release <candidate>               production vs candidate on the gate split; writes reports/releases/
aae traces load|query|replay|prune    the trace archive and ClickHouse
aae schema                            regenerate infra/bigquery/*.json from the one table definition
aae judge calibrate|estimate          LLM-as-judge against seeded truth; corrected precision without truth
aae queue build|show                  findings that need a person, most useful first
aae serve                             the review API and console
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from . import config


def _metrics_table(report: dict) -> str:
    out = [
        f"{report['agent']} on {report['split']}: {report['packages']} packages, {report['defects']} defects, "
        f"{report['findings']} findings"
    ]
    for k, v in report["metrics"].items():
        if v["value"] is not None:
            out.append(f"  {k:30s} {v['value']:.3f}  [{v['low']:.3f}, {v['high']:.3f}]  ({v['k']}/{v['n']})")
    out.append("  verdicts: " + ", ".join(f"{k} {n}" for k, n in report["verdicts"].items() if n))
    ops = report["operational"]
    out.append(
        f"  cost/package ${ops['cost_per_package_usd']:.4f}, p95 {ops['p95_latency_s']:.1f}s, errors {ops['errors']}"
    )
    if report.get("run_id"):
        out.append(f"  run {report['run_id']} archived at {report['archive']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aae", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("splits", nargs="*", default=["dev", "test", "llm"])
    b.add_argument("--limit", type=int)
    e = sub.add_parser("eval")
    e.add_argument("agent")
    e.add_argument("--split", default="dev")
    e.add_argument("--workers", type=int, default=4)
    r = sub.add_parser("release")
    r.add_argument("candidate")
    r.add_argument("--workers", type=int, default=4)
    t = sub.add_parser("traces")
    t.add_argument("action", choices=["load", "query", "replay", "prune"])
    t.add_argument("arg", nargs="?")
    t.add_argument("--today")
    t.add_argument("--dry-run", action="store_true")
    sub.add_parser("schema")
    j = sub.add_parser("judge")
    j.add_argument("action", choices=["calibrate", "estimate"])
    j.add_argument("--split", default="llm")
    j.add_argument("--agents", nargs="*")
    q = sub.add_parser("queue")
    q.add_argument("action", choices=["build", "show"])
    q.add_argument("--split", default="llm")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8077)
    a = p.parse_args(argv)

    if a.cmd == "build":
        from .dataset import build

        for split in a.splits:
            print(build(split, a.limit))
    elif a.cmd == "eval":
        from .evals.evaluate import evaluate

        report, _ = evaluate(a.agent, a.split, a.workers)
        print(_metrics_table(report))
    elif a.cmd == "release":
        from .evals.evaluate import release

        d = release(a.candidate, a.workers)
        print((config.REPORTS / "releases" / f"{a.candidate}.md").read_text())
        return 0 if d["ship"] else 1
    elif a.cmd == "traces":
        from .traces import store

        if a.action == "load":
            ch = store.ClickHouse()
            print(f"loaded {ch.rebuild(store.archived_runs())} runs")
            ch.close()
        elif a.action == "query":
            ch = store.ClickHouse()
            for row in ch.query(
                a.arg
                or "SELECT agent, split, count() AS packages, sum(found)/sum(defects) AS recall "
                "FROM {db}.runs FINAL GROUP BY agent, split ORDER BY agent"
            ):
                print(json.dumps(row, ensure_ascii=False))
            ch.close()
        elif a.action == "replay":
            out = store.replay(a.arg)
            print(json.dumps(out, indent=1))
            return 1 if out["changed"] else 0
        elif a.action == "prune":
            today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
            print(json.dumps(store.prune(today, dry_run=a.dry_run), indent=1))
    elif a.cmd == "schema":
        from .traces import schema

        for table in schema.TABLES:
            path = config.ROOT / "infra" / "bigquery" / f"{table}.json"
            path.write_text(json.dumps(schema.bigquery_schema(table), indent=1) + "\n")
            print(path.relative_to(config.ROOT))
    elif a.cmd == "judge":
        from .evals import judge

        if a.action == "calibrate":
            print(json.dumps(judge.calibrate(a.split, a.agents), indent=1))
        else:
            print(json.dumps(judge.estimate(a.split, a.agents), indent=1))
    elif a.cmd == "queue":
        from .review import queue

        if a.action == "build":
            print(f"{queue.build(a.split)} items queued")
        else:
            for item in queue.load()[:20]:
                print(f"{item['priority']:.2f} {item['package']} #{item['idx']} {item['type']}: {item['reason']}")
    elif a.cmd == "serve":
        import uvicorn

        uvicorn.run("aae.api:app", host="127.0.0.1", port=a.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
