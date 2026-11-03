"""Build the review queue from judged findings; record labels append-only; measure agreement; export a golden set.

data/review/queue.json      rebuilt from reports/judge/<split>_items.jsonl (derived, safe to delete)
data/review/labels.jsonl    every label anyone gave, append-only; the latest label per reviewer counts
data/golden/<split>.jsonl   findings with a settled label (truth, or people when truth cannot say)
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
from collections import Counter
from pathlib import Path

from .. import config

_lock = threading.Lock()


def _dir() -> Path:
    d = config.DATA / "review"
    d.mkdir(parents=True, exist_ok=True)
    return d


def item_id(split: str, agent: str, package: str, idx: int) -> str:
    return f"{split}:{agent}:{package}:{idx}"


def _needs_second(iid: str, share: float) -> bool:
    return int(hashlib.sha256(iid.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < share


def build(split: str = "llm") -> int:
    cfg = config.load("review")
    pr = cfg["priority"]
    src = config.REPORTS / "judge" / f"{split}_items.jsonl"
    items = []
    for line in src.read_text().splitlines():
        it = json.loads(line)
        reason, priority = None, 0.0
        judge = it["judge_valid"]
        if it.get("error") or judge is None:
            reason, priority = "the judge could not decide", pr["judge_failed"]
        elif it["label"] == "unknown":
            reason = "the seeded truth does not cover this finding"
            priority = pr["unknown_truth"] + 0.4 * float(it["finding"].get("confidence", 1.0))
        elif (it["label"] == "valid") != bool(judge):
            reason = f"the judge says {'valid' if judge else 'invalid'}, the truth says {it['label']}"
            priority = pr["judge_disagrees_with_truth"]
        if reason is None:
            continue
        iid = item_id(split, it["agent"], it["package"], it["idx"])
        items.append(
            {
                "id": iid,
                "split": split,
                "agent": it["agent"],
                "package": it["package"],
                "idx": it["idx"],
                "type": it["finding"]["type"],
                "finding": it["finding"],
                "verdict": it["verdict"],
                "truth_label": it["label"],
                "judge_valid": judge,
                "judge_reason": it.get("judge_reason", ""),
                "judge_confidence": it.get("judge_confidence", 0.0),
                "reason": reason,
                "priority": round(priority, 3),
                "reviews_needed": 2 if _needs_second(iid, cfg["second_review_share"]) else 1,
            }
        )
    items.sort(key=lambda x: (-x["priority"], x["id"]))
    (_dir() / "queue.json").write_text(json.dumps(items, ensure_ascii=False, indent=1))
    return len(items)


def load() -> list[dict]:
    p = _dir() / "queue.json"
    if not p.exists():
        return []
    items = json.loads(p.read_text())
    labels = latest_labels()
    for it in items:
        given = labels.get(it["id"], {})
        it["labels"] = given
        it["status"] = "done" if len(given) >= it["reviews_needed"] else "open"
    return items


def add_label(iid: str, reviewer: str, label: str, note: str = "", now: dt.datetime | None = None) -> dict:
    allowed = config.load("review")["labels"]
    if label not in allowed:
        raise ValueError(f"label must be one of {allowed}")
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("a label needs a reviewer")
    if iid not in {i["id"] for i in load()}:
        raise KeyError(iid)
    rec = {
        "item": iid,
        "reviewer": reviewer,
        "label": label,
        "note": note.strip()[:2000],
        "at": (now or dt.datetime.now(dt.UTC)).isoformat(timespec="seconds"),
    }
    with _lock, open(_dir() / "labels.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def all_labels() -> list[dict]:
    p = _dir() / "labels.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def latest_labels() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for rec in all_labels():  # file order is time order; later labels replace earlier ones by the same reviewer
        out.setdefault(rec["item"], {})[rec["reviewer"]] = rec["label"]
    return out


def agreement() -> dict:
    """Cohen's kappa over items labelled by exactly two or more reviewers (first two by name)."""
    pairs = [(v[a], v[b]) for v in latest_labels().values() if len(v) >= 2 for a, b in [sorted(v)[:2]]]
    n = len(pairs)
    if not n:
        return {"items": 0, "agreement": None, "kappa": None}
    po = sum(x == y for x, y in pairs) / n
    ca, cb = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n**2
    return {"items": n, "agreement": po, "kappa": None if pe == 1 else (po - pe) / (1 - pe)}


def settled(item: dict) -> str | None:
    """A person's label settles an item when every reviewer agrees."""
    given = set(item.get("labels", {}).values())
    return given.pop() if len(given) == 1 and len(item.get("labels", {})) >= item["reviews_needed"] else None


def export_golden(split: str = "llm") -> Path:
    src = config.REPORTS / "judge" / f"{split}_items.jsonl"
    queue = {i["id"]: i for i in load()}
    rows = []
    for line in src.read_text().splitlines():
        it = json.loads(line)
        iid = item_id(split, it["agent"], it["package"], it["idx"])
        label, source = it["label"], "seeded truth"
        if iid in queue and (human := settled(queue[iid])):
            label, source = human, "review"
        if label == "unknown":
            continue
        rows.append({"id": iid, "package": it["package"], "finding": it["finding"], "label": label, "source": source})
    out = config.DATA / "golden" / f"{split}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""))
    return out
