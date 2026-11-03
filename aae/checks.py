"""The review rules, run on the document model.

This is the evaluation side's own reading of a package: it sees the model, not the PDF, so it can say exactly
which places a seeded defect breaks. It is used to build ground truth (the "acceptable locations" of a defect)
and to prove that clean packages pass. Agents never import it; the baseline agent has its own implementation
that reads the PDFs (``aae/agents/baseline.py``), and ``tests/test_isolation.py`` keeps them apart.

A check yields a ``Violation`` with a type and every location it involves. Location ids:
``<doc>:<table>:<row>:<col>`` for a table cell, ``<doc>:claim:<id>`` for a number in prose,
``<doc>:heading:<id>`` for a heading, ``<doc>:disclosure:<key>`` for a required disclosure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import ledger as L
from .document import Claim, Document, Heading, Package, Paragraph, Table, fmt, fmt_pct

TYPES = ("casting", "tie", "prior_year", "narrative", "missing_disclosure", "period")

# Disclosures a medium-sized GmbH must make, and the block that makes each.
REQUIRED_DISCLOSURES = {
    "fixed_asset_schedule": ("table", "anl", "§ 284 Abs. 3 HGB"),
    "liabilities_by_term": ("table", "vbl", "§ 268 Abs. 5, § 285 Nr. 1 HGB"),
    "audit_fees": ("table", "fees", "§ 285 Nr. 17 HGB"),
    "employees": ("paragraph", "anhang.employees", "§ 285 Nr. 7 HGB"),
    "appropriation": ("paragraph", "anhang.appropriation", "§ 285 Nr. 34 HGB"),
}


@dataclass(frozen=True)
class Violation:
    type: str
    rule: str
    locations: tuple[str, ...]
    detail: str = field(compare=False)


def loc(doc: Document, t: Table, row: str, col: str) -> str:
    return f"{doc.id}:{t.id}:{row}:{col}"


def rounding_tolerance(n_terms: int) -> int:
    """Each shown term is off by at most 0.5 TEUR from its exact value, and so is the shown total."""
    return (n_terms + 1) // 2


def _has_table(doc: Document, tid: str) -> bool:
    return any(t.id == tid for t in doc.tables())


def _value(doc: Document, tid: str, row: str, col: str) -> int | None:
    try:
        return doc.table(tid).cell(row, col).value
    except KeyError:
        return None


def footing(doc: Document, strict: bool = False) -> list[Violation]:
    """Sums must hold within rounding; with ``strict`` any difference counts (used to find rounding decoys)."""
    out: list[Violation] = []

    def tol(n: int) -> int:
        return 0 if strict else rounding_tolerance(n)

    def check(t: Table, total_row: str, parts: list[tuple[str, int]], col: str, rule: str) -> None:
        try:
            total = t.cell(total_row, col).value
            vals = [(r, s, t.cell(r, col).value) for r, s in parts]
        except KeyError:
            return
        expected = sum(s * v for _, s, v in vals)
        if abs(total - expected) > tol(len(parts)):
            out.append(
                Violation(
                    "casting",
                    rule,
                    (loc(doc, t, total_row, col), *(loc(doc, t, r, col) for r, _, _ in vals)),
                    f"{t.id} {total_row} {col}: shown {total}, lines add up to {expected}",
                )
            )

    for t in doc.tables():
        cols = [k for k, _ in t.columns]
        if t.id.endswith("bs_assets") or t.id.endswith("bs_liabilities"):
            rows = L.ASSETS if t.id.endswith("bs_assets") else L.EQUITY_AND_LIABILITIES
            total_fact = "bs.total.assets" if t.id.endswith("bs_assets") else "bs.total.liabilities"
            for col in cols:
                for parent in {p for _, _, p in rows if p}:
                    check(t, parent, [(f, 1) for f, _, p in rows if p == parent], col, f"sum of {parent}")
                check(t, total_fact, [(f, 1) for f, _, p in rows if p is None], col, f"sum of {total_fact}")
        elif t.id.endswith("guv"):
            for col in cols:
                check(t, "guv.15", [(f, s) for f, _, s in L.INCOME_STATEMENT], col, "result after tax")
                check(t, "guv.17", [("guv.15", 1), ("guv.16", -1)], col, "net income")
        elif t.id == "anl":
            for key, _, _ in L.FIXED_ASSET_CLASSES:
                r = f"anl.{key}"
                for total_col, parts in (
                    ("cost_close", [("cost_open", 1), ("additions", 1), ("disposals", -1)]),
                    ("dep_close", [("dep_open", 1), ("dep_year", 1), ("dep_disposals", -1)]),
                    ("book_close", [("cost_close", 1), ("dep_close", -1)]),
                ):
                    try:
                        total = t.cell(r, total_col).value
                        vals = [(c, s, t.cell(r, c).value) for c, s in parts]
                    except KeyError:
                        continue
                    expected = sum(s * v for _, s, v in vals)
                    if abs(total - expected) > tol(len(parts)):
                        out.append(
                            Violation(
                                "casting",
                                f"row arithmetic {total_col}",
                                (loc(doc, t, r, total_col), *(loc(doc, t, r, c) for c, _, _ in vals)),
                                f"anl {r} {total_col}: shown {total}, row gives {expected}",
                            )
                        )
            for col in cols:
                check(t, "anl.total", [(f"anl.{k}", 1) for k, _, _ in L.FIXED_ASSET_CLASSES], col, "column total")
        elif t.id == "vbl":
            for k, _ in L.LIABILITY_ROWS:
                r = f"vbl.{k}"
                try:
                    total = t.cell(r, "total").value
                    parts = [(c, t.cell(r, c).value) for c in ("lt1", "y1to5", "gt5")]
                except KeyError:
                    continue
                if abs(total - sum(v for _, v in parts)) > tol(3):
                    out.append(
                        Violation(
                            "casting",
                            "maturity buckets",
                            (loc(doc, t, r, "total"), *(loc(doc, t, r, c) for c, _ in parts)),
                            f"vbl {r}: total {total}, buckets {sum(v for _, v in parts)}",
                        )
                    )
            for col in cols:
                check(t, "vbl.sum", [(f"vbl.{k}", 1) for k, _ in L.LIABILITY_ROWS], col, "column total")
        elif t.id == "fees":
            check(t, "fee.total", [(f"fee.{k}", 1) for k, _ in L.AUDIT_FEE_PARTS], "cy", "fee total")
    return out


def ties(doc: Document) -> list[Violation]:
    """Numbers that must agree across tables of the same report."""
    out: list[Violation] = []

    def tie(a: tuple[str, str, str], b: tuple[str, str, str], rule: str, tol: int = 0) -> None:
        va, vb = _value(doc, *a), _value(doc, *b)
        if va is None or vb is None:
            return
        if abs(va - vb) > tol:
            out.append(
                Violation(
                    "tie",
                    rule,
                    (f"{doc.id}:{a[0]}:{a[1]}:{a[2]}", f"{doc.id}:{b[0]}:{b[1]}:{b[2]}"),
                    f"{rule}: {va} vs {vb}",
                )
            )

    if _has_table(doc, "bs_assets") and _has_table(doc, "bs_liabilities"):
        for col in ("cy", "py"):
            tie(
                ("bs_assets", "bs.total.assets", col),
                ("bs_liabilities", "bs.total.liabilities", col),
                f"balance sheet balances ({col})",
            )
    for key, _, bs in L.FIXED_ASSET_CLASSES:
        tie(("anl", f"anl.{key}", "book_close"), ("bs_assets", bs, "cy"), f"fixed assets {key} = balance sheet")
        tie(
            ("anl", f"anl.{key}", "book_prior"),
            ("bs_assets", bs, "py"),
            f"fixed assets {key} prior = balance sheet prior",
        )
    tie(("anl", "anl.total", "dep_year"), ("guv", "guv.7", "cy"), "depreciation = income statement")
    for key, bs in L.LIABILITY_ROWS:
        tie(("vbl", f"vbl.{key}", "total"), ("bs_liabilities", bs, "cy"), f"liabilities {key} = balance sheet")
    tie(("vbl", "vbl.sum", "total"), ("bs_liabilities", "bs.P.C", "cy"), "liabilities total = balance sheet")
    for col in ("cy", "py"):
        tie(
            ("bs_liabilities", "bs.P.A.V", col),
            ("guv", "guv.17", col),
            f"net income in equity = income statement ({col})",
        )
    return out


def prior_year(pkg: Package, restated: dict[str, int]) -> list[Violation]:
    """Comparatives must equal last year's published figures plus any disclosed restatement of that line."""
    cur, prior = pkg.documents[0], pkg.documents[1]
    out: list[Violation] = []
    pairs = {"bs_assets": "prior_bs_assets", "bs_liabilities": "prior_bs_liabilities", "guv": "prior_guv"}
    for tid, ptid in pairs.items():
        if not (_has_table(cur, tid) and _has_table(prior, ptid)):
            continue
        t, pt = cur.table(tid), prior.table(ptid)
        for r in t.rows:
            try:
                py = t.cell(r.key, "py")
                published = pt.cell(r.key, "cy")
            except KeyError:
                continue
            if py.value != published.value + restated.get(r.key, 0):
                out.append(
                    Violation(
                        "prior_year",
                        "comparative = last year's report",
                        (loc(cur, t, r.key, "py"), loc(prior, pt, r.key, "cy")),
                        f"{r.key}: comparative {py.value}, published {published.value}",
                    )
                )
    return out


def _claim_map(doc: Document) -> dict[str, Claim]:
    return {c.id: c for c in doc.claims()}


def narrative(doc: Document) -> list[Violation]:
    """Numbers in prose must agree with the statements they describe."""
    out: list[Violation] = []
    claims = _claim_map(doc)

    def want(cid: str, expected: str, refs: tuple[str, ...], rule: str) -> None:
        c = claims.get(cid)
        if c is not None and c.value != expected:
            out.append(
                Violation(
                    "narrative",
                    rule,
                    (f"{doc.id}:claim:{cid}", *refs),
                    f"{cid}: says {c.value}, statements give {expected}",
                )
            )

    def v(tid: str, row: str, col: str) -> int | None:
        return _value(doc, tid, row, col)

    rev, rev_py = v("guv", "guv.1", "cy"), v("guv", "guv.1", "py")
    if rev is not None and rev_py:
        ref = (f"{doc.id}:guv:guv.1:cy", f"{doc.id}:guv:guv.1:py")
        want("claim.revenue", fmt(rev), ref[:1], "revenue in the management report")
        want("claim.revenue_prior", fmt(rev_py), ref[1:], "prior revenue in the management report")
        want("claim.revenue_change", fmt_pct(abs(round((rev - rev_py) / rev_py * 100, 1))), ref, "revenue change")
    ni, ni_py = v("guv", "guv.17", "cy"), v("guv", "guv.17", "py")
    if ni is not None:
        want("claim.net_income", fmt(ni), (f"{doc.id}:guv:guv.17:cy",), "net income in the management report")
        want("claim.appropriation", fmt(ni), (f"{doc.id}:guv:guv.17:cy",), "net income in the appropriation proposal")
    if ni_py is not None:
        want(
            "claim.net_income_prior",
            fmt(ni_py),
            (f"{doc.id}:guv:guv.17:py",),
            "prior net income in the management report",
        )
    for col, cid in (("cy", "claim.equity_ratio"), ("py", "claim.equity_ratio_prior")):
        eq, tot = v("bs_liabilities", "bs.P.A", col), v("bs_liabilities", "bs.total.liabilities", col)
        if eq is not None and tot:
            want(
                cid,
                fmt_pct(round(eq / tot * 100, 1)),
                (f"{doc.id}:bs_liabilities:bs.P.A:{col}", f"{doc.id}:bs_liabilities:bs.total.liabilities:{col}"),
                "equity ratio",
            )
    adds = [v("anl", f"anl.{k}", "additions") for k in ("land", "tech", "bga")]
    if all(a is not None for a in adds):
        want(
            "claim.capex",
            fmt(sum(a for a in adds if a is not None)),
            tuple(f"{doc.id}:anl:anl.{k}:additions" for k in ("land", "tech", "bga")),
            "capital expenditure",
        )
    if "claim.employees" in claims and "claim.employees_mr" in claims:
        want(
            "claim.employees_mr",
            claims["claim.employees"].value,
            (f"{doc.id}:claim:claim.employees",),
            "employees: report = notes",
        )
    return out


def disclosures(doc: Document) -> list[Violation]:
    if not any(t.id == "guv" for t in doc.tables()):  # only this year's full report must carry the notes
        return []
    ids = {b.id for b in doc.blocks_with_ids()}
    return [
        Violation("missing_disclosure", f"{key} ({law})", (f"{doc.id}:disclosure:{key}",), f"{key} missing")
        for key, (_kind, block, law) in REQUIRED_DISCLOSURES.items()
        if block not in ids
    ]


def period(doc: Document, fiscal_year: int) -> list[Violation]:
    out = []
    for h in doc.headings():
        if h.true_text and h.text != h.true_text:
            out.append(
                Violation("period", "dates match the fiscal year", (f"{doc.id}:heading:{h.id}",), f"{h.id}: {h.text}")
            )
    return out


def all_violations(pkg: Package, restated: dict[str, int] | None = None) -> list[Violation]:
    restated = restated or {}
    cur = pkg.documents[0]
    out = footing(cur) + ties(cur) + narrative(cur) + disclosures(cur) + period(cur, pkg.company.fiscal_year)
    for d in pkg.documents[1:]:
        out += footing(d) + period(d, pkg.company.fiscal_year - 1)
    return out + prior_year(pkg, restated)


__all__ = ["TYPES", "REQUIRED_DISCLOSURES", "Violation", "all_violations", "rounding_tolerance", "Heading", "Paragraph"]
