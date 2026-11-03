"""Seeded defects: the plausible ways a financial statement package goes wrong, planted where we know.

Each defect changes what one place shows. Its ground truth is the place changed plus every place whose check
it breaks, found by running the reference checks (``aae/checks.py``) before and after: a reviewer who points at
any of those places, with a fitting type, has found the defect.

Decoys are changes that look like errors but are not: a prior-year figure restated and disclosed in the notes.
Rounding differences need no planting; they occur naturally because every line is rounded on its own.
"""

from __future__ import annotations

import copy
import random
from dataclasses import asdict, dataclass, field

from . import ledger as L
from .checks import REQUIRED_DISCLOSURES, Violation, all_violations, rounding_tolerance
from .document import Claim, Document, Heading, Package, Paragraph, Table, fmt, fmt_pct

KINDS = ("casting", "tie", "prior_year", "narrative", "missing_disclosure", "period")


@dataclass
class Defect:
    id: str
    kind: str
    description: str
    target: str  # the location changed
    original: str
    injected: str
    style: str  # transposition, typo, shift, sign, removed, wrong_year, wrong_number
    # every location a correct finding may point at, and the types it may carry
    acceptable_locations: list[str] = field(default_factory=list)
    acceptable_types: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class Decoy:
    id: str
    kind: str  # "restatement"
    description: str
    locations: list[str]


# ------------------------------------------------------------------------------------------- perturbations


def perturb(rng: random.Random, value: int, min_diff: int) -> tuple[int, str]:
    """A wrong number of the kind people actually type: swapped digits, a slipped digit, a shifted amount."""
    s = str(abs(value))
    for _ in range(20):
        style = rng.choice(["transposition", "transposition", "typo", "shift"])
        if style == "transposition" and len(s) >= 2:
            i = rng.randrange(len(s) - 1)
            if s[i] == s[i + 1]:
                continue
            new = int(s[:i] + s[i + 1] + s[i] + s[i + 2 :])
        elif style == "typo":
            i = rng.randrange(len(s))
            d = str((int(s[i]) + rng.choice([1, 2, 8, 9])) % 10)
            if i == 0 and d == "0":
                continue
            new = int(s[:i] + d + s[i + 1 :])
        else:
            new = int(abs(value) * rng.choice([0.9, 0.95, 1.05, 1.1, 1.2]))
        new = new if value >= 0 else -new
        if abs(new - value) > max(min_diff, 1):
            return new, style
    return value + (min_diff + 10) * (1 if rng.random() < 0.5 else -1), "shift"


# ---------------------------------------------------------------------------------------------- injectors


def _statement_cells(doc: Document, tid: str, totals: bool, period: str | None = None) -> list[tuple[Table, str, str]]:
    t = doc.table(tid)
    out = []
    for r in t.rows:
        if r.total != totals:
            continue
        for c in r.cells:
            if period is None or c.col == period:
                out.append((t, r.key, c.col))
    return out


def _set_cell(doc: Document, t: Table, row: str, col: str, rng: random.Random) -> tuple[str, str, str]:
    cell = t.cell(row, col)
    new, style = perturb(rng, cell.value, rounding_tolerance(6))
    old = cell.text
    cell.value = new
    return old, cell.text, style


def inject_casting(pkg: Package, rng: random.Random, did: str) -> Defect | None:
    doc = pkg.documents[0]
    candidates = []
    for tid in ("bs_assets", "bs_liabilities", "guv", "anl", "vbl", "fees"):
        candidates += _statement_cells(doc, tid, totals=True)
    t, row, col = rng.choice(candidates)
    old, new, style = _set_cell(doc, t, row, col, rng)
    return Defect(
        did, "casting", f"{t.title}: '{row}' {col} does not add up", f"{doc.id}:{t.id}:{row}:{col}", old, new, style
    )


def inject_tie(pkg: Package, rng: random.Random, did: str) -> Defect | None:
    doc = pkg.documents[0]
    options = [("anl", f"anl.{k}", c) for k, _, _ in L.FIXED_ASSET_CLASSES for c in ("book_close", "book_prior")]
    options += [("vbl", f"vbl.{k}", "total") for k, _ in L.LIABILITY_ROWS]
    options += [("anl", "anl.total", "dep_year"), ("bs_liabilities", "bs.P.A.V", "cy")]
    tid, row, col = rng.choice(options)
    t = doc.table(tid)
    old, new, style = _set_cell(doc, t, row, col, rng)
    return Defect(
        did,
        "tie",
        f"{t.title}: '{row}' {col} disagrees with the statement it explains",
        f"{doc.id}:{tid}:{row}:{col}",
        old,
        new,
        style,
    )


def inject_prior_year(pkg: Package, rng: random.Random, did: str) -> Defect | None:
    doc = pkg.documents[0]
    tid = rng.choice(["bs_assets", "bs_liabilities", "guv"])
    cells = _statement_cells(doc, tid, totals=False, period="py")
    t, row, col = rng.choice(cells)
    # Keep the comparative column internally consistent, so the only symptom is the difference to last year.
    cell = t.cell(row, col)
    new, style = perturb(rng, cell.value, rounding_tolerance(6))
    d = new - cell.value
    old = cell.text
    _shift_with_parents(t, row, col, d)
    return Defect(
        did,
        "prior_year",
        f"{t.title}: comparative for '{row}' differs from last year's report",
        f"{doc.id}:{tid}:{row}:{col}",
        old,
        fmt(new),
        style,
    )


def _shift_with_parents(t: Table, row: str, col: str, d: int) -> None:
    """Change a line and every sum above it by the same amount (balance-sheet and income-statement tables)."""
    t.cell(row, col).value += d
    if t.id.endswith("guv"):
        sign = next((s for f, _, s in L.INCOME_STATEMENT if f == row), 0)
        if sign:
            t.cell("guv.15", col).value += sign * d
            t.cell("guv.17", col).value += sign * d
        elif row == "guv.16":
            t.cell("guv.17", col).value -= d
        return
    rows = L.ASSETS if t.id.endswith("bs_assets") else L.EQUITY_AND_LIABILITIES
    parent_of = {f: p for f, _, p in rows}
    p = parent_of.get(row)
    while p:
        t.cell(p, col).value += d
        p = parent_of.get(p)
    total = "bs.total.assets" if t.id.endswith("bs_assets") else "bs.total.liabilities"
    t.cell(total, col).value += d


def inject_narrative(pkg: Package, rng: random.Random, did: str) -> Defect | None:
    doc = pkg.documents[0]
    claims = {c.id: c for c in doc.claims()}
    cid = rng.choice(
        [
            "claim.revenue_change",
            "claim.revenue",
            "claim.net_income",
            "claim.equity_ratio",
            "claim.capex",
            "claim.employees_mr",
            "claim.appropriation",
            "claim.revenue_prior",
        ]
    )
    c = claims[cid]
    old = c.value
    if cid in ("claim.revenue_change", "claim.equity_ratio"):
        v = float(old.replace(",", "."))
        new = fmt_pct(max(0.1, v + rng.choice([-3.0, -1.5, -0.8, 0.8, 1.5, 2.4, 3.0])))
        style = "wrong_number"
    elif cid == "claim.employees_mr":
        new, style = str(int(old) + rng.choice([-12, -5, 7, 15])), "wrong_number"
    else:
        num = int(old.replace(".", "").replace("-", ""))
        nv, style = perturb(rng, num, 2)
        new = fmt(-nv if old.startswith("-") else nv)
    c.value = new
    return Defect(
        did,
        "narrative",
        f"management report or notes state {cid} as {new} instead of {old}",
        f"{doc.id}:claim:{cid}",
        old,
        new,
        style,
    )


def inject_missing_disclosure(pkg: Package, rng: random.Random, did: str) -> Defect | None:
    doc = pkg.documents[0]
    key = rng.choice(sorted(REQUIRED_DISCLOSURES))
    _kind, block, law = REQUIRED_DISCLOSURES[key]
    for p in doc.pages:
        for b in list(p.blocks):
            if getattr(b, "id", None) == block:
                p.blocks.remove(b)
                # the heading of a section that held only this block goes too
                return Defect(
                    did,
                    "missing_disclosure",
                    f"required disclosure missing: {key} ({law})",
                    f"{doc.id}:disclosure:{key}",
                    block,
                    "",
                    "removed",
                )
    return None


def inject_period(pkg: Package, rng: random.Random, did: str) -> Defect | None:
    doc = pkg.documents[0]
    y = pkg.company.fiscal_year
    hs = [h for h in doc.headings() if str(y) in h.text and h.id != "cover.name"]
    h = rng.choice(hs)
    old = h.text
    h.text = old.replace(str(y), str(y - 1))
    return Defect(
        did,
        "period",
        f"heading '{h.id}' names the wrong fiscal year",
        f"{doc.id}:heading:{h.id}",
        old,
        h.text,
        "wrong_year",
    )


INJECTORS = {
    "casting": inject_casting,
    "tie": inject_tie,
    "prior_year": inject_prior_year,
    "narrative": inject_narrative,
    "missing_disclosure": inject_missing_disclosure,
    "period": inject_period,
}


def plant_restatement(pkg: Package, rng: random.Random, did: str) -> tuple[Decoy, dict[str, int]]:
    """Reclassify an amount in last year's comparatives and disclose it: different from last year's report, correct."""
    doc = pkg.documents[0]
    t = doc.table("bs_liabilities")
    other = t.cell("bs.P.C.3", "py").value
    d = max(3, int(other * rng.uniform(0.15, 0.4)))
    _shift_with_parents(t, "bs.P.C.3", "py", -d)
    _shift_with_parents(t, "bs.P.B.2", "py", d)
    para = Paragraph(
        "anhang.restatement",
        [
            f"Im Vorjahr unter den sonstigen Verbindlichkeiten ausgewiesene Verpflichtungen von {fmt(d)} TEUR werden "
            "nunmehr unter den sonstigen Rückstellungen gezeigt. Die Vorjahreszahlen wurden entsprechend angepasst "
            "(§ 265 Abs. 2 Satz 3 HGB)."
        ],
    )
    for p in doc.pages:
        ids = [getattr(b, "id", None) for b in p.blocks]
        if "anhang.methods.text" in ids:
            p.blocks.insert(ids.index("anhang.methods.text") + 1, para)
            break
    rows = {"bs.P.C.3": -d, "bs.P.C": -d, "bs.P.B.2": d, "bs.P.B": d}  # line -> change to the published figure
    return Decoy(
        did,
        "restatement",
        f"comparatives reclassified by {d} TEUR and disclosed",
        [f"{doc.id}:bs_liabilities:{r}:py" for r in sorted(rows)],
    ), rows


def plant(
    pkg: Package, rng: random.Random, kinds: list[str], restate: bool
) -> tuple[list[Defect], list[Decoy], dict[str, int]]:
    """Plant the decoy first, then the defects one by one; each defect's ground truth is what it newly breaks."""
    decoys: list[Decoy] = []
    restated: dict[str, int] = {}
    if restate:
        dec, restated = plant_restatement(pkg, rng, f"{pkg.id}.decoy1")
        decoys.append(dec)
    defects: list[Defect] = []
    for i, kind in enumerate(kinds):
        before = {v for v in all_violations(pkg, restated)}
        for _attempt in range(10):
            trial = copy.deepcopy(pkg)
            try:
                d = INJECTORS[kind](trial, rng, f"{pkg.id}.d{i + 1}")
            except (KeyError, IndexError):  # the target was removed by an earlier defect
                d = None
            if d is None:
                continue
            new = [v for v in all_violations(trial, restated) if v not in before]
            if not new and kind != "missing_disclosure":
                continue
            if any(x.target == d.target for x in defects):
                continue
            _accept(d, new)
            pkg.documents = trial.documents
            defects.append(d)
            break
    return defects, decoys, restated


def _accept(d: Defect, new: list[Violation]) -> None:
    locs = {d.target}
    types = {d.kind}
    for v in new:
        locs.update(v.locations)
        types.add(v.type)
    d.acceptable_locations = sorted(locs)
    d.acceptable_types = sorted(types)


__all__ = ["KINDS", "Defect", "Decoy", "plant", "perturb", "Claim", "Heading", "fmt"]
