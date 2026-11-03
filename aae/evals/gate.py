"""Decide whether a candidate agent may replace the production one.

Two kinds of rule, both from ``config/gates.yaml``: floors every release must meet, and non-inferiority against
production on the same packages (paired bootstrap). A rule that cannot be evaluated (no defects of a kind in
the split) is reported as such and does not pass silently.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .. import config
from .metrics import Counts, paired, point


@dataclass
class Check:
    rule: str
    metric: str
    status: str  # pass | fail | n/a
    value: float | None
    limit: float
    low: float | None = None
    high: float | None = None
    detail: str = ""


def floors(c: Counts, cfg: dict | None = None) -> list[Check]:
    cfg = cfg or config.load("gates")
    out = []
    for metric, lim in cfg["floors"].items():
        v = point(c, metric)
        if "min" in lim:
            limit, ok = float(lim["min"]), v is not None and v >= lim["min"]
            what = "at least"
        else:
            limit, ok = float(lim["max"]), v is not None and v <= lim["max"]
            what = "at most"
        status = "n/a" if v is None else "pass" if ok else "fail"
        out.append(Check("floor", metric, status, v, limit, detail=f"{what} {limit:.2f}"))
    return out


def non_inferiority(base: Counts, cand: Counts, cfg: dict | None = None) -> list[Check]:
    cfg = cfg or config.load("gates")
    b = cfg["bootstrap"]
    out = []
    for metric, margin in cfg["non_inferiority"].items():
        p = paired(base, cand, metric, b=b["resamples"], seed=b["seed"], level=b["level"])
        if p["low"] is None:
            out.append(Check("non-inferiority", metric, "n/a", p["diff"], -margin, detail="no cases in this split"))
            continue
        ok = p["low"] >= -margin
        out.append(
            Check(
                "non-inferiority",
                metric,
                "pass" if ok else "fail",
                p["diff"],
                -float(margin),
                p["low"],
                p["high"],
                detail=f"production {p['base']:.3f}, candidate {p['candidate']:.3f}",
            )
        )
    return out


def decide(base: Counts | None, cand: Counts, cfg: dict | None = None) -> dict:
    checks = floors(cand, cfg) + (non_inferiority(base, cand, cfg) if base is not None else [])
    failed = [c for c in checks if c.status == "fail"]
    return {
        "ship": not failed and any(c.status == "pass" for c in checks),
        "failed": [f"{c.rule}: {c.metric}" for c in failed],
        "checks": [asdict(c) for c in checks],
    }
