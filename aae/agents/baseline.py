"""The rules-based review agent: reads the PDFs' text layer and checks what a reviewer checks first.

It knows how an HGB report is laid out (``config/hgb.yaml``) and nothing about how packages are made. Variants
differ only in settings (``config/agents.yaml``): rounding tolerance, whether the restatement note is read,
which check families run. A page without a text layer is counted as unreadable and skipped.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from .. import config
from .pdfread import ReadDocument, ReadTable, TableRow, normalise, parse_number, read
from .schema import AgentRun, Finding, FindingType, Span


def fmt(v: int) -> str:
    s = f"{abs(v):,}".replace(",", ".")
    return f"-{s}" if v < 0 else s


def fmt_pct(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


def round_half_up(v: float, digits: int = 1) -> float:
    q = 10**digits
    return (int(abs(v) * q + 0.5) / q) * (1 if v >= 0 else -1)


class _Review:
    def __init__(self, hgb: dict, settings: dict, current: ReadDocument, prior: ReadDocument | None, fy: int):
        self.hgb, self.s, self.cur, self.prior, self.fy = hgb, settings, current, prior, fy
        self.findings: list[Finding] = []
        self.titles = hgb["tables"]

    # ------------------------------------------------------------------------------------------- helpers

    def tol(self, n_terms: int) -> int:
        if self.s["rounding"] == "strict":
            return 0
        return int((n_terms + 1) * self.s.get("rounding_per_line", 0.5))  # every shown amount is off by up to 0.5

    def add(
        self,
        type_: FindingType,
        doc: ReadDocument,
        row: TableRow | None,
        column: str | None,
        found: str | None,
        expected: str | None,
        why: str,
        *,
        page: int | None = None,
        quote: str | None = None,
    ) -> None:
        self.findings.append(
            Finding(
                type=type_,
                document=doc.file,
                page=row.page if row else page,
                row_label=row.label if row else None,
                column=column,
                quote=quote,
                found_value=found,
                expected_value=expected,
                explanation=why,
            )
        )

    @staticmethod
    def column_for(t: ReadTable, year: int) -> str | None:
        return next((c for c in t.columns if re.search(rf"\b{year}\b", c)), None)

    # ------------------------------------------------------------------------------------------ casting

    def footing_all(self, docs: list[ReadDocument]) -> None:
        for d in docs:
            self.footing(d)

    def period_all(self, docs: list[ReadDocument], years: dict[str, int | None], fy: int) -> None:
        for d in docs:
            self.period(d, years[d.file] or fy)

    def footing(self, doc: ReadDocument) -> None:
        for key in ("assets", "liabilities"):
            t = doc.table(self.titles[key])
            if t:
                self._hierarchy(doc, t)
        t = doc.table(self.titles["income"])
        if t:
            self._income(doc, t)
        t = doc.table(self.titles["fixed_assets"])
        if t:
            self._fixed_assets(doc, t)
        t = doc.table(self.titles["maturities"])
        if t:
            self._maturities(doc, t)
        t = doc.table(self.titles["audit_fees"])
        if t:
            self._fees(doc, t)

    def _check_sum(
        self, doc: ReadDocument, t: ReadTable, total: TableRow, parts: list[tuple[TableRow, int]], col: str, what: str
    ) -> None:
        if col not in total.values or any(col not in r.values for r, _ in parts):
            return
        expected = sum(s * r.values[col] for r, s in parts)
        shown = total.values[col]
        if abs(shown - expected) > self.tol(len(parts)):
            self.add(
                "casting",
                doc,
                total,
                col,
                fmt(shown),
                fmt(expected),
                f"{t.title}: '{total.label}' shows {fmt(shown)}, {what} add up to {fmt(expected)}",
            )

    def _hierarchy(self, doc: ReadDocument, t: ReadTable) -> None:
        rows = t.rows
        for i, r in enumerate(rows):
            if r.level == 0:
                if r.label.startswith(self.hgb["total_prefix"]):
                    tops = [(x, 1) for x in rows if x.level == 1]
                    for col in t.columns:
                        self._check_sum(doc, t, r, tops, col, "the main headings")
                continue
            below: list[TableRow] = []
            for x in rows[i + 1 :]:
                if x.level == 0 or x.level <= r.level:
                    break
                below.append(x)
            if not below:
                continue
            depth = min(x.level for x in below)
            children = [(x, 1) for x in below if x.level == depth]
            for col in t.columns:
                self._check_sum(doc, t, r, children, col, "the lines below it")

    def _income(self, doc: ReadDocument, t: ReadTable) -> None:
        items = {r.number: r for r in t.rows if r.number is not None}
        signs = {int(k): v for k, v in self.hgb["income_signs"].items()}
        n = self.hgb["income_items"]
        after_tax, other_taxes, net = (
            items.get(n["result_after_tax"]),
            items.get(n["other_taxes"]),
            items.get(n["net_income"]),
        )
        parts = [(r, signs[k]) for k, r in items.items() if k in signs]
        for col in t.columns:
            if after_tax:
                self._check_sum(doc, t, after_tax, parts, col, "the income and expense items")
            if net and after_tax and other_taxes:
                self._check_sum(
                    doc, t, net, [(after_tax, 1), (other_taxes, -1)], col, "result after taxes less other taxes"
                )

    def _roles(self, t: ReadTable, mapping: dict[str, str]) -> dict[str, str]:
        return {role: col for col, role in mapping.items() if col in t.columns}

    def _total_row(self, t: ReadTable) -> TableRow | None:
        return next((r for r in t.rows if r.bold and r.label.startswith(self.hgb["total_prefix"])), None)

    def _fixed_assets(self, doc: ReadDocument, t: ReadTable) -> None:
        c = self._roles(t, self.hgb["fixed_asset_columns"])
        total = self._total_row(t)
        lines = [r for r in t.rows if r is not total]
        formulas = (
            ("cost_close", [("cost_open", 1), ("additions", 1), ("disposals", -1)]),
            ("dep_close", [("dep_open", 1), ("dep_year", 1), ("dep_disposals", -1)]),
            ("book_close", [("cost_close", 1), ("dep_close", -1)]),
        )
        for r in lines:
            for result, terms in formulas:
                if result not in c or any(k not in c for k, _ in terms):
                    continue
                if c[result] not in r.values or any(c[k] not in r.values for k, _ in terms):
                    continue
                expected = sum(s * r.values[c[k]] for k, s in terms)
                shown = r.values[c[result]]
                if abs(shown - expected) > self.tol(len(terms)):
                    self.add(
                        "casting",
                        doc,
                        r,
                        c[result],
                        fmt(shown),
                        fmt(expected),
                        f"{t.title}: '{r.label}' {c[result]} shows {fmt(shown)}, the row gives {fmt(expected)}",
                    )
        if total:
            for col in t.columns:
                self._check_sum(doc, t, total, [(r, 1) for r in lines], col, "the asset classes")

    def _maturities(self, doc: ReadDocument, t: ReadTable) -> None:
        c = self._roles(t, self.hgb["maturity_columns"])
        total = self._total_row(t)
        lines = [r for r in t.rows if r is not total]
        if all(k in c for k in ("total", "lt1", "y1to5", "gt5")):
            for r in lines:
                vals = [r.values.get(c[k]) for k in ("lt1", "y1to5", "gt5")]
                shown = r.values.get(c["total"])
                if shown is None or any(v is None for v in vals):
                    continue
                expected = sum(v for v in vals if v is not None)
                if abs(shown - expected) > self.tol(3):
                    self.add(
                        "casting",
                        doc,
                        r,
                        c["total"],
                        fmt(shown),
                        fmt(expected),
                        f"{t.title}: '{r.label}' total {fmt(shown)}, maturities add up to {fmt(expected)}",
                    )
        if total:
            for col in t.columns:
                self._check_sum(doc, t, total, [(r, 1) for r in lines], col, "the liability lines")

    def _fees(self, doc: ReadDocument, t: ReadTable) -> None:
        total = next((r for r in t.rows if r.name == normalise(self.hgb["fee_total_label"])), None)
        if total:
            for col in t.columns:
                self._check_sum(doc, t, total, [(r, 1) for r in t.rows if r is not total], col, "the fee categories")

    # ---------------------------------------------------------------------------------------------- ties

    def ties(self) -> None:
        d, h = self.cur, self.hgb
        assets, liabs = d.table(self.titles["assets"]), d.table(self.titles["liabilities"])
        income = d.table(self.titles["income"])
        anl, vbl = d.table(self.titles["fixed_assets"]), d.table(self.titles["maturities"])

        def tie(
            row: TableRow | None, col: str | None, other: TableRow | None, other_col: str | None, what: str
        ) -> None:
            if not (row and col and other and other_col) or col not in row.values or other_col not in other.values:
                return
            a, b = row.values[col], other.values[other_col]
            if a != b:
                self.add("tie", d, row, col, fmt(a), fmt(b), f"{what}: {fmt(a)} here, {fmt(b)} in the other statement")

        cy_a = self.column_for(assets, self.fy) if assets else None
        py_a = self.column_for(assets, self.fy - 1) if assets else None
        cy_l = self.column_for(liabs, self.fy) if liabs else None
        py_l = self.column_for(liabs, self.fy - 1) if liabs else None
        if assets and liabs:
            ta, tl = self._total_row(assets), self._total_row(liabs)
            tie(tl, cy_l, ta, cy_a, "total equity and liabilities = total assets")
            tie(tl, py_l, ta, py_a, "total equity and liabilities = total assets (prior year)")
        if anl and assets:
            c = self._roles(anl, h["fixed_asset_columns"])
            for line, m in h["fixed_asset_rows"].items():
                r, bs = anl.row(line), assets.row(m["balance_sheet"])
                tie(r, c.get("book_close"), bs, cy_a, f"book value of {line} = balance sheet")
                tie(r, c.get("book_prior"), bs, py_a, f"prior book value of {line} = balance sheet comparative")
        if anl and income:
            c = self._roles(anl, h["fixed_asset_columns"])
            dep = next((r for r in income.rows if r.number == h["income_items"]["depreciation"]), None)
            tie(
                self._total_row(anl),
                c.get("dep_year"),
                dep,
                self.column_for(income, self.fy),
                "depreciation in the schedule = income statement",
            )
        if vbl and liabs:
            c = self._roles(vbl, h["maturity_columns"])
            for r in vbl.rows:
                if r is self._total_row(vbl):
                    tie(
                        r,
                        c.get("total"),
                        liabs.row(h["liabilities_line"]),
                        cy_l,
                        "liabilities schedule total = balance sheet",
                    )
                else:
                    tie(r, c.get("total"), liabs.row(r.name), cy_l, f"{r.label} = balance sheet")
        if liabs and income:
            ni = liabs.row(h["net_income_line"])
            net = next((r for r in income.rows if r.number == h["income_items"]["net_income"]), None)
            tie(ni, cy_l, net, self.column_for(income, self.fy), "net income in equity = income statement")
            tie(
                ni,
                py_l,
                net,
                self.column_for(income, self.fy - 1),
                "net income in equity = income statement (prior year)",
            )

    # ---------------------------------------------------------------------------------------- prior year

    def prior_year(self) -> None:
        if not self.prior:
            return
        restated: int | None = None
        if self.s["restatements"] == "read":
            m = re.search(self.hgb["restatement"], self.cur.text())
            restated = parse_number(m.group("amount")) if m else None
        for key in ("assets", "liabilities", "income"):
            t, pt = self.cur.table(self.titles[key]), self.prior.table(self.titles[key])
            if not (t and pt):
                continue
            col, pcol = self.column_for(t, self.fy - 1), self.column_for(pt, self.fy - 1)
            if not (col and pcol):
                continue
            for r in t.rows:
                p = pt.row(r.name)
                if not p or col not in r.values or pcol not in p.values:
                    continue
                diff = r.values[col] - p.values[pcol]
                if diff == 0 or (restated is not None and abs(diff) == restated):
                    continue
                self.add(
                    "prior_year",
                    self.cur,
                    r,
                    col,
                    fmt(r.values[col]),
                    fmt(p.values[pcol]),
                    f"comparative differs from last year's published {fmt(p.values[pcol])} with no restatement disclosed",
                )

    # ----------------------------------------------------------------------------------------- narrative

    def narrative(self) -> None:
        d, h = self.cur, self.hgb
        found: dict[str, tuple[str, int, str]] = {}  # claim -> (value, page, quote)
        for page in range(1, d.pages + 1):
            text = d.page_text(page)
            for pattern in h["claims"].values():
                for m in re.finditer(pattern, text):
                    for name, value in m.groupdict().items():
                        if value is not None and name != "verb":
                            found.setdefault(name, (value, page, m.group(0)))
        income, liabs = d.table(self.titles["income"]), d.table(self.titles["liabilities"])
        anl = d.table(self.titles["fixed_assets"])
        expected: dict[str, str] = {}
        if income:
            items = {r.number: r for r in income.rows if r.number is not None}
            cy, py = self.column_for(income, self.fy), self.column_for(income, self.fy - 1)
            rev, net = items.get(h["income_items"]["revenue"]), items.get(h["income_items"]["net_income"])
            if rev and cy in rev.values:
                expected["revenue"] = fmt(rev.values[cy])
            if rev and py in rev.values:
                expected["revenue_prior"] = fmt(rev.values[py])
                if cy in rev.values and rev.values[py]:
                    expected["change"] = fmt_pct(
                        abs(round_half_up((rev.values[cy] - rev.values[py]) / rev.values[py] * 100))
                    )
            if net and cy in net.values:
                expected["net_income"] = expected["appropriation"] = fmt(net.values[cy])
            if net and py in net.values:
                expected["net_income_prior"] = fmt(net.values[py])
        if liabs:
            eq, total = liabs.row(h["equity_line"]), self._total_row(liabs)
            for name, year in (("equity_ratio", self.fy), ("equity_ratio_prior", self.fy - 1)):
                col = self.column_for(liabs, year)
                if eq and total and col in eq.values and total.values.get(col):
                    expected[name] = fmt_pct(round_half_up(eq.values[col] / total.values[col] * 100))
        if anl:
            add = self._roles(anl, h["fixed_asset_columns"]).get("additions")
            tangible = [anl.row(k) for k, m in h["fixed_asset_rows"].items() if m["tangible"]]
            if add and all(r and add in r.values for r in tangible):
                expected["capex"] = fmt(sum(r.values[add] for r in tangible if r))
        if "employees" in found:
            expected["employees_mr"] = found["employees"][0]
        for name, want in expected.items():
            if name in found and found[name][0] != want:
                value, page, quote = found[name]
                self.add(
                    "narrative",
                    d,
                    None,
                    None,
                    value,
                    want,
                    f"the text says {value}, the figures give {want} ({name.replace('_', ' ')})",
                    page=page,
                    quote=quote,
                )

    # ------------------------------------------------------------------------------------- disclosures

    def disclosures(self) -> None:
        text = self.cur.text()
        if not re.search(rf"{self.hgb['notes_heading']} für das Geschäftsjahr", text):
            return
        for key, dsc in self.hgb["disclosures"].items():
            if not re.search(dsc["pattern"], text):
                self.add(
                    "missing_disclosure",
                    self.cur,
                    None,
                    None,
                    None,
                    None,
                    f"required disclosure not found: {dsc['name']} ({dsc['law']})",
                    quote=f"{key}: {dsc['name']}",
                )

    # ------------------------------------------------------------------------------------------- period

    def period(self, doc: ReadDocument, fy: int) -> None:
        for ln in doc.headings():
            for pattern in self.hgb["dated_headings"]:
                m = re.search(pattern, ln.text)
                if m and int(m.group("year")) != fy:
                    self.add(
                        "period",
                        doc,
                        None,
                        None,
                        m.group("year"),
                        str(fy),
                        f"heading names {m.group('year')}, the statements are for {fy}",
                        page=ln.page,
                        quote=ln.text,
                    )


def fiscal_year(doc: ReadDocument, hgb: dict) -> int | None:
    t = doc.table(hgb["tables"]["assets"])
    if t and t.columns:
        m = re.search(r"(\d{4})", t.columns[0])
        if m:
            return int(m.group(1))
    m = re.search(r"(\d{4})", doc.file)
    return int(m.group(1)) if m else None


class BaselineAgent:
    """``review(folder)`` reads every PDF in a package folder and returns findings with a trace."""

    def __init__(self, name: str = "baseline", settings: dict | None = None, version: int | None = None):
        agents = config.load("agents")["agents"]
        spec = agents[name]
        self.name = name
        self.version = version or spec["version"]
        self.settings = {**spec.get("settings", {}), **(settings or {})}
        self.hgb = config.load("hgb")

    @property
    def id(self) -> str:
        return f"{self.name}@{self.version}"

    def review(self, folder: Path) -> AgentRun:
        spans: list[Span] = []
        t0 = time.perf_counter()

        @contextmanager
        def span(name: str, kind: Literal["extract", "check"], **attrs: str | int | float | bool) -> Iterator[None]:
            start = time.perf_counter()
            status = "ok"
            try:
                yield
            except Exception:
                status = "error"
                raise
            finally:
                spans.append(
                    Span(
                        name=name,
                        kind=kind,
                        started_ms=round((start - t0) * 1000, 3),  # type: ignore[arg-type]
                        duration_ms=round((time.perf_counter() - start) * 1000, 3),
                        status=status,  # type: ignore[arg-type]
                        attributes=attrs,
                    )
                )

        docs: list[ReadDocument] = []
        for pdf in sorted(folder.glob("*.pdf")):
            with span(f"read {pdf.name}", "extract", file=pdf.name):
                docs.append(read(pdf, list(self.hgb["tables"].values())))
            spans[-1].attributes["unreadable"] = bool(docs[-1].unreadable_pages)
        years = {d.file: fiscal_year(d, self.hgb) for d in docs}
        known = [y for y in years.values() if y]
        run = AgentRun(
            package=folder.name,
            agent=self.id,
            findings=[],
            spans=spans,
            pages_read=sum(d.pages - len(d.unreadable_pages) for d in docs),
            pages_unreadable=sum(len(d.unreadable_pages) for d in docs),
        )
        if not known:
            run.error = "no readable document"
            return run
        fy = max(known)
        current = next(d for d in docs if years[d.file] == fy)
        prior = next((d for d in docs if years[d.file] == fy - 1), None)
        review = _Review(self.hgb, self.settings, current, prior, fy)
        enabled = set(self.settings["checks"])
        steps: list[tuple[str, Callable[[], None]]] = [
            ("casting", lambda: review.footing_all(docs)),
            ("tie", review.ties),
            ("prior_year", review.prior_year),
            ("narrative", review.narrative),
            ("missing_disclosure", review.disclosures),
            ("period", lambda: review.period_all(docs, years, fy)),
        ]
        for family, step in steps:
            current_readable = len(current.unreadable_pages) < current.pages
            if family in enabled and (current_readable or family in ("casting", "period")):
                before = len(review.findings)
                with span(f"check {family}", "check", family=family):
                    step()
                spans[-1].attributes["findings"] = len(review.findings) - before
        run.findings = review.findings
        return run
