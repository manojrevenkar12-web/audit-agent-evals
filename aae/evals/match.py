"""Match an agent's findings to the seeded defects of one package.

A finding names a place the way a reviewer would (document, page, line item, column, or a quoted sentence). The
truth file's location map (``placed``) turns that into location ids; a finding hits a defect when one of those
ids is among the defect's acceptable locations and its type is one the defect can carry. Every finding gets
exactly one verdict, so precision and the reasons for false alarms add up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import config
from ..agents.schema import Finding

PREFIX = re.compile(r"^(?:[IVX]+|[A-Z]|\d{1,2})\.\s+")
YEAR = re.compile(r"\b(19|20)\d{2}\b")

# Verdicts for a finding
HIT, DUPLICATE, MISTYPED, DECOY, ROUNDING, UNLOCATED, FALSE_ALARM = (
    "hit",
    "duplicate",
    "mistyped",
    "decoy",
    "rounding",
    "unlocated",
    "false_alarm",
)
CORRECT = {HIT, DUPLICATE}


def norm(s: str | None) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip().lower().rstrip(":")
    return PREFIX.sub("", s)


def doc_id(name: str) -> str:
    return re.sub(r"\.pdf$", "", name.strip())


@dataclass
class Located:
    ids: set[str]
    how: str  # cell | row | claim | heading | disclosure | value | none


@dataclass
class FindingResult:
    index: int
    finding: Finding
    verdict: str
    location: Located
    defect: str | None = None


@dataclass
class PackageResult:
    package: str
    defects: list[dict]
    found: dict[str, int] = field(default_factory=dict)  # defect id -> index of first finding
    findings: list[FindingResult] = field(default_factory=list)
    scanned: bool = False
    has_decoy: bool = False

    @property
    def clean(self) -> bool:
        return not self.defects


class Locator:
    def __init__(self, truth: dict):
        self.placed = truth["placed"]
        self.current = truth["documents"][0]["id"]
        self.keywords = config.load("matching")["disclosure_keywords"]
        self.fallback = config.load("matching")["column_fallback"]

    def _in_doc(self, did: str, kind: str, page: int | None = None) -> list[dict]:
        return [
            p
            for p in self.placed
            if p["id"].startswith(did + ":") and p["kind"] == kind and (page is None or p["page"] == page)
        ]

    def locate(self, f: Finding) -> Located:
        did = doc_id(f.document)
        if f.type == "missing_disclosure":
            keys: set[str] = set()
            # what the finding names first; its explanation only if that names nothing
            for text in (norm(f"{f.row_label or ''} {f.quote or ''}"), norm(f.explanation)):
                keys = {k for k, words in self.keywords.items() if any(w in text for w in words)}
                if keys:
                    break
            if keys:
                d = did if any(p["id"].startswith(did + ":") for p in self.placed) else self.current
                return Located({f"{d}:disclosure:{k}" for k in keys}, "disclosure")
            return Located(set(), "none")
        if f.row_label:
            loc = self._cell(did, f)
            if loc.ids:
                return loc
        if f.type == "period" or (f.quote and not f.row_label and f.type != "narrative"):
            loc = self._heading(did, f)
            if loc.ids:
                return loc
        if f.quote or f.found_value:
            loc = self._claim(did, f)
            if loc.ids:
                return loc
        if f.found_value and f.page:
            ids = {p["id"] for p in self._in_doc(did, "cell", f.page) if p["text"] == f.found_value.strip()}
            if len(ids) == 1:
                return Located(ids, "value")
        return Located(set(), "none")

    def _cell(self, did: str, f: Finding) -> Located:
        label = norm(f.row_label)
        cells = [p for p in self._in_doc(did, "cell") if norm(p["label"]) == label]
        if not cells:
            cells = [
                p
                for p in self._in_doc(did, "cell")
                if label and (label in norm(p["label"]) or norm(p["label"]) in label)
            ]
        if f.page is not None and any(p["page"] == f.page for p in cells):
            cells = [p for p in cells if p["page"] == f.page]
        if not cells:
            return Located(set(), "none")
        if f.column:
            col = norm(f.column)
            exact = [p for p in cells if norm(p["column"]) == col]
            if exact:
                return Located({p["id"] for p in exact}, "cell")
            years = set(m.group(0) for m in YEAR.finditer(col))
            by_year = [p for p in cells if years and years & set(m.group(0) for m in YEAR.finditer(p["column"]))]
            if by_year:
                return Located({p["id"] for p in by_year}, "cell")
            loose = [p for p in cells if col and (col in norm(p["column"]) or norm(p["column"]) in col)]
            if loose:
                return Located({p["id"] for p in loose}, "cell")
        if f.found_value:
            same = [p for p in cells if p["text"] == f.found_value.strip()]
            if len(same) == 1:
                return Located({same[0]["id"]}, "cell")
        if f.column and self.fallback != "row":
            return Located(set(), "none")
        return Located({p["id"] for p in cells}, "row")

    def _heading(self, did: str, f: Finding) -> Located:
        q = norm(f.quote)
        hs = self._in_doc(did, "heading", f.page) or self._in_doc(did, "heading")
        exact = [h for h in hs if q and norm(h["text"]) == q]
        if exact:
            return Located({h["id"] for h in exact}, "heading")
        near = [h for h in hs if q and (q in norm(h["text"]) or norm(h["text"]) in q)]
        if f.found_value:
            near = [h for h in near if f.found_value in h["text"]] or near
        return Located({h["id"] for h in near}, "heading") if near else Located(set(), "none")

    def _claim(self, did: str, f: Finding) -> Located:
        claims = self._in_doc(did, "claim", f.page) or self._in_doc(did, "claim")
        if f.found_value:
            v = re.sub(r"\s*(%|TEUR|EUR|Mitarbeitende)$", "", f.found_value.strip()).strip()
            with_value = [c for c in claims if re.search(rf"(?<![\d.,]){re.escape(v)}(?![\d,]|\.\d)", c["text"])]
            if len(with_value) == 1:
                return Located({with_value[0]["id"]}, "claim")
            if with_value:
                claims = with_value
        q = set(norm(f.quote).split())
        if not q:
            return Located(set(), "none")
        scored = sorted(
            (
                (len(q & set(norm(c["text"]).split())) / max(1, len(set(norm(c["text"]).split()))), c["id"])
                for c in claims
            ),
            reverse=True,
        )
        if scored and scored[0][0] >= 0.5:
            return Located({scored[0][1]}, "claim")
        return Located(set(), "none")


def match(truth: dict, findings: list[Finding]) -> PackageResult:
    loc = Locator(truth)
    type_strict = config.load("matching")["type_must_match"]
    res = PackageResult(
        truth["package"],
        truth["defects"],
        scanned=any(d["scanned"] for d in truth["documents"]),
        has_decoy=bool(truth["decoys"]),
    )
    decoy_locs = {x for d in truth["decoys"] for x in d["locations"]}
    rounding = set(truth["rounding_differences"])
    for i, f in enumerate(findings):
        located = loc.locate(f)
        verdict, defect = FALSE_ALARM, None
        if not located.ids:
            verdict = UNLOCATED
        else:
            fits = [d for d in truth["defects"] if located.ids & set(d["acceptable_locations"])]
            typed = [d for d in fits if not type_strict or f.type in d["acceptable_types"]]
            if typed:
                fresh = [d for d in typed if d["id"] not in res.found]
                defect = (fresh or typed)[0]["id"]
                verdict = HIT if fresh else DUPLICATE
                if fresh:
                    res.found[defect] = i
            elif fits:
                verdict, defect = MISTYPED, fits[0]["id"]
            elif located.ids & decoy_locs:
                verdict = DECOY
            elif located.ids & rounding:
                verdict = ROUNDING
        res.findings.append(FindingResult(i, f, verdict, located, defect))
    return res
