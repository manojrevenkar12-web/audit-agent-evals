"""Scores from matched packages, with confidence intervals from a package-level bootstrap.

Packages are the unit of resampling: defects in one package share a reader, a layout and a scan, so counting
them as independent would make intervals too narrow. Two agents run on the same packages are compared on the
same resamples (a paired bootstrap), which is what the release gates use.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .match import CORRECT, DECOY, PackageResult

KINDS = ("casting", "tie", "prior_year", "narrative", "missing_disclosure", "period")
VERDICTS = ("hit", "duplicate", "mistyped", "decoy", "rounding", "unlocated", "false_alarm")


@dataclass
class Counts:
    """Per-package counts; every metric is a ratio of sums over these columns."""

    names: list[str]
    data: np.ndarray  # packages x columns
    packages: list[str]

    def col(self, name: str) -> np.ndarray:
        return self.data[:, self.names.index(name)]


def counts(results: list[PackageResult]) -> Counts:
    names = [
        "defects",
        "found",
        "findings",
        "correct",
        "clean",
        "clean_alarm",
        "decoy_pkg",
        "decoy_alarm",
        "scanned_defects",
        "scanned_found",
        "digital_defects",
        "digital_found",
    ]
    names += [f"defects:{k}" for k in KINDS] + [f"found:{k}" for k in KINDS]
    names += [f"findings:{k}" for k in KINDS] + [f"correct:{k}" for k in KINDS]
    names += [f"verdict:{v}" for v in VERDICTS]
    rows = []
    for r in sorted(results, key=lambda r: r.package):
        row = dict.fromkeys(names, 0.0)
        row["defects"] = len(r.defects)
        row["found"] = len(r.found)
        row["findings"] = len(r.findings)
        row["correct"] = sum(f.verdict in CORRECT for f in r.findings)
        row["clean"] = float(r.clean)
        row["clean_alarm"] = float(r.clean and any(f.verdict not in CORRECT for f in r.findings))
        row["decoy_pkg"] = float(r.has_decoy)
        row["decoy_alarm"] = float(any(f.verdict == DECOY for f in r.findings))
        side = "scanned" if r.scanned else "digital"
        row[f"{side}_defects"] = len(r.defects)
        row[f"{side}_found"] = len(r.found)
        for d in r.defects:
            row[f"defects:{d['kind']}"] += 1
            row[f"found:{d['kind']}"] += d["id"] in r.found
        for f in r.findings:
            row[f"findings:{f.finding.type}"] += 1
            row[f"correct:{f.finding.type}"] += f.verdict in CORRECT
            row[f"verdict:{f.verdict}"] += 1
        rows.append([row[n] for n in names])
    return Counts(
        names,
        np.array(rows, dtype=float).reshape(len(rows), len(names)),
        [r.package for r in sorted(results, key=lambda r: r.package)],
    )


# metric name -> (numerator column, denominator column)
METRICS: dict[str, tuple[str, str]] = {
    "recall": ("found", "defects"),
    "precision": ("correct", "findings"),
    "clean_false_alarm_rate": ("clean_alarm", "clean"),
    "decoy_false_alarm_rate": ("decoy_alarm", "decoy_pkg"),
    "recall_digital": ("digital_found", "digital_defects"),
    "recall_scanned": ("scanned_found", "scanned_defects"),
    **{f"recall:{k}": (f"found:{k}", f"defects:{k}") for k in KINDS},
    **{f"precision:{k}": (f"correct:{k}", f"findings:{k}") for k in KINDS},
}


def _ratio(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)


def point(c: Counts, metric: str) -> float | None:
    n, d = METRICS[metric]
    den = c.col(d).sum()
    return None if den == 0 else float(c.col(n).sum() / den)


def resample_index(n_packages: int, b: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, n_packages, size=(b, n_packages))


def bootstrap(c: Counts, metric: str, idx: np.ndarray) -> np.ndarray:
    n, d = METRICS[metric]
    return _ratio(c.col(n)[idx].sum(axis=1), c.col(d)[idx].sum(axis=1))


def interval(samples: np.ndarray, level: float) -> tuple[float | None, float | None]:
    s = samples[~np.isnan(samples)]
    if not len(s):
        return None, None
    a = (1 - level) / 2
    return float(np.quantile(s, a)), float(np.quantile(s, 1 - a))


def summary(c: Counts, b: int = 2000, seed: int = 7, level: float = 0.95) -> dict:
    idx = resample_index(len(c.packages), b, seed)
    out: dict = {
        "packages": len(c.packages),
        "defects": int(c.col("defects").sum()),
        "findings": int(c.col("findings").sum()),
        "verdicts": {v: int(c.col(f"verdict:{v}").sum()) for v in VERDICTS},
        "metrics": {},
    }
    for m in METRICS:
        p = point(c, m)
        lo, hi = interval(bootstrap(c, m, idx), level) if p is not None else (None, None)
        n, d = METRICS[m]
        out["metrics"][m] = {"value": p, "low": lo, "high": hi, "n": int(c.col(d).sum()), "k": int(c.col(n).sum())}
    return out


def paired(base: Counts, cand: Counts, metric: str, b: int = 2000, seed: int = 7, level: float = 0.95) -> dict:
    """Candidate minus baseline on the same packages and the same resamples."""
    if base.packages != cand.packages:
        raise ValueError("paired comparison needs the same packages for both agents")
    idx = resample_index(len(base.packages), b, seed)
    diff = bootstrap(cand, metric, idx) - bootstrap(base, metric, idx)
    pb, pc = point(base, metric), point(cand, metric)
    lo, hi = interval(diff, level)
    return {
        "metric": metric,
        "base": pb,
        "candidate": pc,
        "diff": None if pb is None or pc is None else pc - pb,
        "low": lo,
        "high": hi,
    }
