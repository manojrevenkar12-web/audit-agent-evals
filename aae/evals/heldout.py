"""Run a held-out case set against the evaluator once and record what happened.

The first run of a set is written to ``reports/heldout/<set>/first_run.json`` and never rewritten; later runs go
to ``latest_run.json``. A case passes when the evaluator gives the expected verdict and, for hit, duplicate and
mistyped, the expected error.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter

import yaml

from .. import config
from ..agents.schema import Finding
from .match import match
from .run import load_truth

SPLIT = "heldout"


def run(name: str, now: dt.datetime | None = None) -> dict:
    folder = config.ROOT / "heldout" / name
    cases = yaml.safe_load((folder / "cases.yaml").read_text())
    status = (folder / "STATUS").read_text().strip() if (folder / "STATUS").exists() else "blind"
    by_pkg: dict[str, list[tuple[int, dict]]] = {}
    for i, c in enumerate(cases):
        by_pkg.setdefault(c["package"], []).append((i, c))
    results = []
    for pid, items in by_pkg.items():
        findings = [Finding.model_validate(c["finding"]) for _, c in items]
        res = match(load_truth(SPLIT, pid), findings)
        for (i, c), fr in zip(items, res.findings, strict=True):
            want_v = c["expect"]["verdict"]
            want_d = c["expect"].get("defect")
            ok = fr.verdict == want_v and (want_v not in ("hit", "duplicate", "mistyped") or fr.defect == want_d)
            results.append(
                {
                    "case": i,
                    "package": pid,
                    "type": c["finding"]["type"],
                    "expected": want_v,
                    "expected_defect": want_d,
                    "got": fr.verdict,
                    "got_defect": fr.defect,
                    "located": fr.location.how,
                    "pass": ok,
                    "why": c.get("why", ""),
                }
            )
    results.sort(key=lambda r: r["case"])
    passed = sum(r["pass"] for r in results)
    report = {
        "set": name,
        "status": status,
        "ran_at": (now or dt.datetime.now(dt.UTC)).isoformat(timespec="seconds"),
        "cases": len(results),
        "passed": passed,
        "by_expected": {
            v: {"cases": n, "passed": sum(r["pass"] for r in results if r["expected"] == v)}
            for v, n in sorted(Counter(r["expected"] for r in results).items())
        },
        "failures": [r for r in results if not r["pass"]],
    }
    out = config.REPORTS / "heldout" / name
    out.mkdir(parents=True, exist_ok=True)
    first = out / "first_run.json"
    target = out / "latest_run.json" if first.exists() else first
    target.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    report["recorded_as"] = target.name
    return report
