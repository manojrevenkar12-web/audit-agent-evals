"""LLM-as-judge: is this finding a real error? Calibrated on seeded truth, then used where there is none.

A judge is itself a model with error rates. On seeded packages we know which findings are right, so we measure
the judge's sensitivity (it accepts right findings) and specificity (it rejects wrong ones). On traffic without
truth, the share of findings the judge accepts is biased by those rates; the Rogan-Gladen correction removes the
bias: precision = (accepted + specificity - 1) / (sensitivity + specificity - 1).

The judge sees the finding and the package PDFs, never the truth or the matcher's verdict.
"""

from __future__ import annotations

import hashlib
import json
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np

from .. import config
from ..agents import claude_cli
from ..agents.schema import Finding
from .match import FindingResult, match
from .run import load_runs, load_truth

SCHEMA = {
    "type": "object",
    "properties": {
        "valid": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
    },
    "required": ["valid", "confidence", "reason"],
}


@dataclass
class Judged:
    agent: str
    package: str
    idx: int
    finding: Finding
    verdict: str  # the matcher's, kept away from the judge
    label: str  # valid | invalid | unknown (from the verdict)
    judge_valid: bool | None = None
    judge_confidence: float = 0.0
    judge_reason: str = ""
    cost_usd: float = 0.0
    error: str | None = None

    def to_json(self) -> dict:
        d = self.__dict__.copy()
        d["finding"] = self.finding.model_dump(exclude_none=True)
        return d


def label_of(fr: FindingResult, cfg: dict | None = None) -> str:
    cfg = (cfg or config.load("judge"))["labels"]
    if fr.verdict in cfg["valid"]:
        return "valid"
    if fr.verdict in cfg["invalid"]:
        return "invalid"
    if fr.verdict in cfg["invalid_if_numeric"] and fr.finding.type in cfg["numeric_types"]:
        return "invalid"
    return "unknown"


def judge_one(split: str, package: str, f: Finding, cfg: dict | None = None) -> dict:
    cfg = cfg or config.load("judge")
    system = (config.ROOT / cfg["prompt"]).read_text()
    user = "Issue to check:\n" + json.dumps(f.model_dump(exclude_none=True), ensure_ascii=False, indent=1)
    files = sorted((config.DATA / split / "packages" / package).glob("*.pdf"))
    raw, _key, _replayed = claude_cli.ask(cfg["model"], system, user, SCHEMA, files, float(cfg["budget_usd"]))
    out = raw.get("structured_output") or {}
    return {
        "valid": out.get("valid"),
        "confidence": float(out.get("confidence", 0.0)),
        "reason": out.get("reason", ""),
        "cost_usd": claude_cli.usage(raw)["cost_usd"],
        "error": claude_cli.failed(raw),
    }


def sample(split: str, agents: list[str], per_agent: int, seed: int) -> list[Judged]:
    """A fixed sample per agent, stratified so every verdict an agent produced is represented."""
    out: list[Judged] = []
    for agent in agents:
        items: list[Judged] = []
        for pid, run in sorted(load_runs(split, agent).items()):
            res = match(load_truth(split, pid), run.findings)
            items += [Judged(agent, pid, fr.index, fr.finding, fr.verdict, label_of(fr)) for fr in res.findings]
        rng = random.Random(f"{seed}:{agent}")
        by_verdict: dict[str, list[Judged]] = {}
        for it in items:
            by_verdict.setdefault(it.verdict, []).append(it)
        chosen: list[Judged] = []
        pools = [rng.sample(v, len(v)) for _, v in sorted(by_verdict.items())]
        while len(chosen) < min(per_agent, len(items)):  # round-robin over verdicts
            for pool in pools:
                if pool and len(chosen) < per_agent:
                    chosen.append(pool.pop())
        out += chosen
    return out


def run_judge(split: str, items: list[Judged], workers: int) -> list[Judged]:
    def go(it: Judged) -> Judged:
        try:
            r = judge_one(split, it.package, it.finding)
            it.judge_valid, it.judge_confidence, it.judge_reason = r["valid"], r["confidence"], r["reason"]
            it.cost_usd, it.error = r["cost_usd"], r["error"]
        except Exception as e:  # recorded, excluded from the rates
            it.error = f"{type(e).__name__}: {e}"
        return it

    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(go, items))


# --------------------------------------------------------------------------------------------- statistics


def rates(items: list[Judged]) -> dict:
    lab = [i for i in items if i.label != "unknown" and i.judge_valid is not None]
    tp = sum(i.label == "valid" and bool(i.judge_valid) for i in lab)
    fn = sum(i.label == "valid" and not i.judge_valid for i in lab)
    tn = sum(i.label == "invalid" and not i.judge_valid for i in lab)
    fp = sum(i.label == "invalid" and bool(i.judge_valid) for i in lab)
    n = tp + fn + tn + fp
    sens = tp / (tp + fn) if tp + fn else None
    spec = tn / (tn + fp) if tn + fp else None
    po = (tp + tn) / n if n else None
    pe = (((tp + fp) * (tp + fn)) + ((fn + tn) * (fp + tn))) / n**2 if n else None
    kappa = (po - pe) / (1 - pe) if po is not None and pe is not None and pe < 1 else None
    return {
        "n": n,
        "tp": tp,
        "fn": fn,
        "tn": tn,
        "fp": fp,
        "sensitivity": sens,
        "specificity": spec,
        "agreement": po,
        "kappa": kappa,
    }


def corrected(accepted_share: float, sens: float, spec: float) -> float | None:
    """Rogan-Gladen: the true share of valid findings, given the judge's error rates."""
    j = sens + spec - 1
    if j <= 0:
        return None  # the judge is no better than chance: its acceptance says nothing
    return float(min(1.0, max(0.0, (accepted_share + spec - 1) / j)))


def _half(package: str) -> int:
    return int(hashlib.sha256(package.encode()).hexdigest(), 16) % 2


def holdout_estimate(items: list[Judged], b: int = 1000, seed: int = 5) -> dict:
    """Calibrate on one half of the packages, estimate each agent's precision on the other half from the judge
    alone, and compare with the precision the truth gives on that half."""
    cal = [i for i in items if _half(i.package) == 0]
    est = [i for i in items if _half(i.package) == 1 and i.judge_valid is not None]
    r = rates(cal)
    out: dict = {"calibration": r, "agents": {}}
    if r["sensitivity"] is None or r["specificity"] is None:
        return out
    rng = np.random.default_rng(seed)
    cal_lab = [i for i in cal if i.label != "unknown" and i.judge_valid is not None]
    for agent in sorted({i.agent for i in est}):
        # Findings whose truth is known, so the estimate can be checked; the judge never sees that truth.
        mine = [i for i in est if i.agent == agent and i.label != "unknown"]
        if not mine:
            continue
        q = float(np.mean([bool(i.judge_valid) for i in mine]))
        actual = float(np.mean([i.label == "valid" for i in mine]))
        boots = []
        for _ in range(b):  # resample both the calibration set and the estimate set
            cs = [cal_lab[k] for k in rng.integers(0, len(cal_lab), len(cal_lab))]
            ms = [mine[k] for k in rng.integers(0, len(mine), len(mine))]
            rr = rates(cs)
            if rr["sensitivity"] is None or rr["specificity"] is None:
                continue
            v = corrected(float(np.mean([bool(i.judge_valid) for i in ms])), rr["sensitivity"], rr["specificity"])
            if v is not None:
                boots.append(v)
        out["agents"][agent] = {
            "findings": len(mine),
            "judge_accepted": q,
            "naive_precision": q,
            "corrected_precision": corrected(q, r["sensitivity"], r["specificity"]),
            "low": float(np.quantile(boots, 0.025)) if boots else None,
            "high": float(np.quantile(boots, 0.975)) if boots else None,
            "truth_precision": actual,
        }
    return out


def results_path(split: str):
    return config.REPORTS / "judge" / f"{split}.json"


def calibrate(split: str | None = None, agents: list[str] | None = None) -> dict:
    cfg = config.load("judge")
    c = cfg["calibration"]
    split = split or c["split"]
    items = sample(split, agents or c["agents"], int(c["per_agent"]), int(c["seed"]))
    items = run_judge(split, items, int(cfg["workers"]))
    report = {
        "split": split,
        "model": cfg["model"],
        "prompt": cfg["prompt"],
        "items": len(items),
        "errors": sum(1 for i in items if i.error),
        "cost_usd": round(sum(i.cost_usd for i in items), 4),
        "overall": rates(items),
        "by_agent": {a: rates([i for i in items if i.agent == a]) for a in sorted({i.agent for i in items})},
        "by_verdict": {
            v: {"n": len(xs), "judge_accepted": sum(bool(i.judge_valid) for i in xs)}
            for v in sorted({i.verdict for i in items})
            for xs in [[i for i in items if i.verdict == v and i.judge_valid is not None]]
        },
        "holdout": holdout_estimate(items),
    }
    path = results_path(split)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    (path.parent / f"{split}_items.jsonl").write_text(
        "\n".join(json.dumps(i.to_json(), ensure_ascii=False) for i in items) + "\n"
    )
    return report


def estimate(split: str | None = None, agents: list[str] | None = None) -> dict:
    """Re-read the last calibration and report the hold-out estimates."""
    data = json.loads(results_path(split or config.load("judge")["calibration"]["split"]).read_text())
    return data["holdout"]
