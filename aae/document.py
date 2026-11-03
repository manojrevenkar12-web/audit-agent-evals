"""The financial statement package as a document model: pages of headings, paragraphs and tables.

Every number an agent might check is a ``Cell`` with an address (doc, table, row, column) and the fact it shows;
every number in prose is a ``Claim``. Defects change what a cell or claim shows; the renderer draws the model
to PDF and records where each address landed on the page, so findings can be matched to defects by place.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import ledger as L
from .ledger import Company


def fmt(teur: int) -> str:
    """German number format: 12.345 and -1.234."""
    s = f"{abs(teur):,}".replace(",", ".")
    return f"-{s}" if teur < 0 else s


def fmt_pct(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


@dataclass
class Cell:
    row: str  # row key, e.g. "bs.A.II.2" or "anl.tech"
    col: str  # column key, e.g. "cy", "py", "book_close"
    fact: str  # fact id in the ledger
    period: str  # "cy" or "py"
    value: int  # TEUR as shown
    true_value: int  # TEUR as the books say

    @property
    def text(self) -> str:
        return fmt(self.value)


@dataclass
class Row:
    key: str
    label: str
    cells: list[Cell]
    total: bool = False  # a sum line (drawn bold, ruled)
    level: int = 0


@dataclass
class Table:
    id: str  # "bs_assets", "bs_liabilities", "guv", "anl", "vbl", "fees"
    title: str
    columns: list[tuple[str, str]]  # (key, header)
    rows: list[Row]
    landscape: bool = False

    def cell(self, row: str, col: str) -> Cell:
        for r in self.rows:
            if r.key == row:
                for c in r.cells:
                    if c.col == col:
                        return c
        raise KeyError(f"{self.id}:{row}:{col}")


@dataclass
class Claim:
    """A number stated in prose. ``template`` holds ``{v}`` where the number goes."""

    id: str
    template: str
    value: str  # as shown
    true_value: str


@dataclass
class Paragraph:
    id: str
    parts: list[str | Claim]

    @property
    def text(self) -> str:
        return "".join(p if isinstance(p, str) else p.template.replace("{v}", p.value) for p in self.parts)


@dataclass
class Heading:
    id: str
    text: str
    true_text: str = ""
    level: int = 1


Block = Heading | Paragraph | Table


@dataclass
class Page:
    blocks: list[Block]
    landscape: bool = False
    section: str = ""  # "cover", "bilanz", "guv", "anhang", "lagebericht"


@dataclass
class Document:
    id: str  # file stem, e.g. "jahresabschluss_2026"
    title: str
    pages: list[Page]
    scanned: bool = False  # rendered as page images without a text layer

    def tables(self) -> list[Table]:
        return [b for p in self.pages for b in p.blocks if isinstance(b, Table)]

    def table(self, tid: str) -> Table:
        for t in self.tables():
            if t.id == tid:
                return t
        raise KeyError(tid)

    def claims(self) -> list[Claim]:
        return [
            x for p in self.pages for b in p.blocks if isinstance(b, Paragraph) for x in b.parts if isinstance(x, Claim)
        ]

    def headings(self) -> list[Heading]:
        return [b for p in self.pages for b in p.blocks if isinstance(b, Heading)]

    def blocks_with_ids(self) -> list[Block]:
        return [b for p in self.pages for b in p.blocks]


@dataclass
class Package:
    """What an agent receives for one engagement: this year's report and last year's published statements."""

    id: str
    company: Company
    documents: list[Document] = field(default_factory=list)

    def doc(self, did: str) -> Document:
        for d in self.documents:
            if d.id == did:
                return d
        raise KeyError(did)


# ------------------------------------------------------------------------------------------------ builders


def _cell(row: str, col: str, fact: str, period: str, y: L.Year) -> Cell:
    v = y.shown(fact)
    return Cell(row=row, col=col, fact=fact, period=period, value=v, true_value=v)


def _statement_table(
    tid: str,
    title: str,
    rows: list[tuple[str, str, str | None]],
    c: Company,
    total_fact: str,
    total_label: str,
    with_prior: bool = True,
) -> Table:
    cols = [("cy", f"31.12.{c.fiscal_year} TEUR")] + ([("py", f"31.12.{c.fiscal_year - 1} TEUR")] if with_prior else [])
    out: list[Row] = []
    parents = {p for _, _, p in rows if p}
    parent_of = {f: p for f, _, p in rows}
    for fact, label, parent in rows:
        level = 0 if parent is None else (1 if parent_of.get(parent) is None else 2)
        cells = [_cell(fact, "cy", fact, "cy", c.current)]
        if with_prior:
            cells.append(_cell(fact, "py", fact, "py", c.prior))
        out.append(Row(key=fact, label=label, cells=cells, total=fact in parents, level=level))
    tot = [_cell(total_fact, "cy", total_fact, "cy", c.current)]
    if with_prior:
        tot.append(_cell(total_fact, "py", total_fact, "py", c.prior))
    out.append(Row(key=total_fact, label=total_label, cells=tot, total=True))
    return Table(id=tid, title=title, columns=cols, rows=out)


def _guv_table(c: Company, with_prior: bool = True) -> Table:
    cols = [("cy", f"{c.fiscal_year} TEUR")] + ([("py", f"{c.fiscal_year - 1} TEUR")] if with_prior else [])
    rows: list[Row] = []

    def mk(fact: str, label: str, total: bool = False) -> Row:
        cells = [_cell(fact, "cy", fact, "cy", c.current)]
        if with_prior:
            cells.append(_cell(fact, "py", fact, "py", c.prior))
        return Row(key=fact, label=label, cells=cells, total=total)

    for fact, label, _sign in L.INCOME_STATEMENT:
        rows.append(mk(fact, label))
    rows.append(mk(L.GUV_RESULT_AFTER_TAX[0], L.GUV_RESULT_AFTER_TAX[1], total=True))
    rows.append(mk(L.GUV_OTHER_TAXES[0], L.GUV_OTHER_TAXES[1]))
    rows.append(mk(L.GUV_NET[0], L.GUV_NET[1], total=True))
    return Table(id="guv", title="Gewinn- und Verlustrechnung", columns=cols, rows=rows)


def _anl_table(c: Company) -> Table:
    rows = []
    for key, label, _bs in L.FIXED_ASSET_CLASSES:
        rows.append(
            Row(
                key=f"anl.{key}",
                label=label,
                cells=[_cell(f"anl.{key}", col, f"anl.{key}.{col}", "cy", c.current) for col, _ in L.ANL_COLUMNS],
            )
        )
    rows.append(
        Row(
            key="anl.total",
            label="Summe",
            total=True,
            cells=[_cell("anl.total", col, f"anl.total.{col}", "cy", c.current) for col, _ in L.ANL_COLUMNS],
        )
    )
    return Table(
        id="anl", title="Entwicklung des Anlagevermögens (TEUR)", columns=list(L.ANL_COLUMNS), rows=rows, landscape=True
    )


def _vbl_table(c: Company) -> Table:
    labels = {
        "bank": "Verbindlichkeiten gegenüber Kreditinstituten",
        "trade": "Verbindlichkeiten aus Lieferungen und Leistungen",
        "other": "Sonstige Verbindlichkeiten",
    }
    rows = [
        Row(
            key=f"vbl.{k}",
            label=labels[k],
            cells=[_cell(f"vbl.{k}", col, f"vbl.{k}.{col}", "cy", c.current) for col, _ in L.LIAB_COLUMNS],
        )
        for k, _ in L.LIABILITY_ROWS
    ]
    rows.append(
        Row(
            key="vbl.sum",
            label="Summe",
            total=True,
            cells=[_cell("vbl.sum", col, f"vbl.sum.{col}", "cy", c.current) for col, _ in L.LIAB_COLUMNS],
        )
    )
    return Table(id="vbl", title="Verbindlichkeitenspiegel (TEUR)", columns=list(L.LIAB_COLUMNS), rows=rows)


def _fees_table(c: Company) -> Table:
    rows = []
    for key, label in L.AUDIT_FEE_PARTS:
        v = c.audit_fees[key]
        rows.append(Row(key=f"fee.{key}", label=label, cells=[Cell(f"fee.{key}", "cy", f"fee.{key}", "cy", v, v)]))
    t = c.audit_fees["total"]
    rows.append(
        Row(
            key="fee.total", label="Gesamthonorar", total=True, cells=[Cell("fee.total", "cy", "fee.total", "cy", t, t)]
        )
    )
    return Table(
        id="fees", title="Honorar des Abschlussprüfers (TEUR)", columns=[("cy", f"{c.fiscal_year} TEUR")], rows=rows
    )


def _claim(cid: str, template: str, value: str) -> Claim:
    return Claim(id=cid, template=template, value=value, true_value=value)


def build_current_report(c: Company) -> Document:
    y, cy = c.fiscal_year, c.current
    change = L.revenue_change_pct(c)
    verb = "stiegen" if change >= 0 else "sanken"
    additions_tangible = sum(cy.shown(f"anl.{k}.additions") for k in ("land", "tech", "bga"))
    pages = [
        Page(
            section="cover",
            blocks=[
                Heading("cover.name", c.name, c.name),
                Heading(
                    "cover.title", f"Jahresabschluss zum {c.year_end}", f"Jahresabschluss zum {c.year_end}", level=2
                ),
                Paragraph("cover.seat", [f"Sitz: {c.city}, Amtsgericht {c.city}, {c.hrb}"]),
            ],
        ),
        Page(
            section="bilanz",
            blocks=[
                Heading("bilanz.title", f"Bilanz zum {c.year_end}", f"Bilanz zum {c.year_end}"),
                _statement_table("bs_assets", "Aktiva", L.ASSETS, c, "bs.total.assets", "Summe Aktiva"),
            ],
        ),
        Page(
            section="bilanz",
            blocks=[
                Heading("bilanz.title_p", f"Bilanz zum {c.year_end}", f"Bilanz zum {c.year_end}"),
                _statement_table(
                    "bs_liabilities", "Passiva", L.EQUITY_AND_LIABILITIES, c, "bs.total.liabilities", "Summe Passiva"
                ),
            ],
        ),
        Page(
            section="guv",
            blocks=[
                Heading(
                    "guv.title",
                    f"Gewinn- und Verlustrechnung für die Zeit vom 1. Januar bis {c.year_end}",
                    f"Gewinn- und Verlustrechnung für die Zeit vom 1. Januar bis {c.year_end}",
                ),
                _guv_table(c),
            ],
        ),
        Page(
            section="anhang",
            blocks=[
                Heading("anhang.title", f"Anhang für das Geschäftsjahr {y}", f"Anhang für das Geschäftsjahr {y}"),
                Heading("anhang.general", "1. Allgemeine Angaben", "1. Allgemeine Angaben", level=2),
                Paragraph(
                    "anhang.general.text",
                    [
                        f"Der Jahresabschluss der {c.name} wurde nach den Vorschriften der §§ 242 ff. und §§ 264 ff. HGB sowie den "
                        "ergänzenden Bestimmungen des GmbHG aufgestellt. Die Gewinn- und Verlustrechnung ist nach dem "
                        "Gesamtkostenverfahren gegliedert. Alle Beträge werden in Tausend Euro (TEUR) angegeben; durch die "
                        "Rundung einzelner Posten können sich in Summen geringfügige Rundungsdifferenzen ergeben."
                    ],
                ),
                Heading(
                    "anhang.methods",
                    "2. Bilanzierungs- und Bewertungsmethoden",
                    "2. Bilanzierungs- und Bewertungsmethoden",
                    level=2,
                ),
                Paragraph(
                    "anhang.methods.text",
                    [
                        "Immaterielle Vermögensgegenstände und Sachanlagen sind zu Anschaffungs- oder Herstellungskosten "
                        "vermindert um planmäßige lineare Abschreibungen bewertet. Vorräte werden zu Anschaffungs- oder "
                        "Herstellungskosten unter Beachtung des Niederstwertprinzips angesetzt. Forderungen sind zum Nennwert "
                        "bilanziert; erkennbaren Einzelrisiken wird durch Wertberichtigungen Rechnung getragen. Rückstellungen "
                        "sind in Höhe des nach vernünftiger kaufmännischer Beurteilung notwendigen Erfüllungsbetrags angesetzt."
                    ],
                ),
            ],
        ),
        Page(
            section="anhang",
            landscape=True,
            blocks=[
                Heading("anhang.anl", "3. Anlagevermögen", "3. Anlagevermögen", level=2),
                _anl_table(c),
            ],
        ),
        Page(
            section="anhang",
            blocks=[
                Heading("anhang.vbl", "4. Verbindlichkeiten", "4. Verbindlichkeiten", level=2),
                _vbl_table(c),
                Paragraph(
                    "anhang.receivables",
                    [
                        "Sämtliche Forderungen und sonstigen Vermögensgegenstände haben eine Restlaufzeit von bis zu einem Jahr."
                    ],
                ),
                Heading("anhang.other", "5. Sonstige Angaben", "5. Sonstige Angaben", level=2),
                Paragraph(
                    "anhang.employees",
                    [
                        _claim(
                            "claim.employees",
                            "Im Geschäftsjahr wurden durchschnittlich {v} Arbeitnehmerinnen und Arbeitnehmer beschäftigt",
                            str(c.employees),
                        ),
                        f" (Vorjahr: {c.employees_prior}).",
                    ],
                ),
                _fees_table(c),
                Paragraph(
                    "anhang.appropriation",
                    [
                        _claim(
                            "claim.appropriation",
                            "Die Geschäftsführung schlägt vor, den Jahresüberschuss von {v} TEUR auf neue Rechnung vorzutragen.",
                            fmt(cy.shown("guv.17")),
                        )
                    ],
                ),
                Paragraph("anhang.signature", [f"{c.city}, im März {y + 1}. Die Geschäftsführung"]),
            ],
        ),
        Page(
            section="lagebericht",
            blocks=[
                Heading(
                    "lagebericht.title",
                    f"Lagebericht für das Geschäftsjahr {y}",
                    f"Lagebericht für das Geschäftsjahr {y}",
                ),
                Heading("lagebericht.course", "1. Geschäftsverlauf", "1. Geschäftsverlauf", level=2),
                Paragraph(
                    "lagebericht.revenue",
                    [
                        _claim(
                            "claim.revenue_change",
                            f"Die Umsatzerlöse {verb} im Geschäftsjahr {y} um {{v}} %",
                            fmt_pct(abs(change)),
                        ),
                        _claim("claim.revenue", " auf {v} TEUR", fmt(cy.shown("guv.1"))),
                        _claim("claim.revenue_prior", " (Vorjahr: {v} TEUR).", fmt(c.prior.shown("guv.1"))),
                        " Die Entwicklung ist im Wesentlichen auf die Nachfrage unserer Bestandskunden zurückzuführen.",
                    ],
                ),
                Heading("lagebericht.results", "2. Ertragslage", "2. Ertragslage", level=2),
                Paragraph(
                    "lagebericht.net",
                    [
                        _claim(
                            "claim.net_income",
                            "Das Geschäftsjahr schließt mit einem Jahresüberschuss von {v} TEUR",
                            fmt(cy.shown("guv.17")),
                        ),
                        _claim("claim.net_income_prior", " (Vorjahr: {v} TEUR) ab.", fmt(c.prior.shown("guv.17"))),
                        " Der Materialaufwand und der Personalaufwand entwickelten sich im Verhältnis zur Leistung planmäßig.",
                    ],
                ),
                Heading(
                    "lagebericht.position", "3. Vermögens- und Finanzlage", "3. Vermögens- und Finanzlage", level=2
                ),
                Paragraph(
                    "lagebericht.equity",
                    [
                        _claim(
                            "claim.equity_ratio",
                            "Die Eigenkapitalquote beträgt zum Stichtag {v} %",
                            fmt_pct(L.equity_ratio_pct(cy)),
                        ),
                        _claim("claim.equity_ratio_prior", " (Vorjahr: {v} %).", fmt_pct(L.equity_ratio_pct(c.prior))),
                        _claim(
                            "claim.capex",
                            " Im Geschäftsjahr wurden {v} TEUR in Sachanlagen investiert.",
                            fmt(additions_tangible),
                        ),
                    ],
                ),
                Heading("lagebericht.staff", "4. Mitarbeitende", "4. Mitarbeitende", level=2),
                Paragraph(
                    "lagebericht.staff.text",
                    [
                        _claim(
                            "claim.employees_mr",
                            "Im Jahresdurchschnitt beschäftigte die Gesellschaft {v} Mitarbeitende.",
                            str(c.employees),
                        )
                    ],
                ),
                Heading("lagebericht.outlook", "5. Prognosebericht", "5. Prognosebericht", level=2),
                Paragraph(
                    "lagebericht.outlook.text",
                    [
                        f"Für das Geschäftsjahr {y + 1} erwarten wir eine leicht steigende Umsatzentwicklung bei stabiler Ertragslage."
                    ],
                ),
            ],
        ),
    ]
    return Document(id=f"jahresabschluss_{y}", title=f"Jahresabschluss {y}", pages=pages)


def build_prior_report(c: Company) -> Document:
    """Last year's statements as published (balance sheet and income statement, no comparatives)."""
    py = c.fiscal_year - 1
    prior_view = L.Company(
        name=c.name,
        city=c.city,
        hrb=c.hrb,
        fiscal_year=py,
        current=c.prior,
        prior=c.prior,
        employees=c.employees_prior,
        employees_prior=c.employees_prior,
        audit_fees=c.audit_fees,
        capital_stock_eur=c.capital_stock_eur,
    )
    pages = [
        Page(
            section="cover",
            blocks=[
                Heading("prior.cover.name", c.name, c.name),
                Heading(
                    "prior.cover.title",
                    f"Jahresabschluss zum 31. Dezember {py}",
                    f"Jahresabschluss zum 31. Dezember {py}",
                    level=2,
                ),
            ],
        ),
        Page(
            section="bilanz",
            blocks=[
                Heading("prior.bilanz.title", f"Bilanz zum 31. Dezember {py}", f"Bilanz zum 31. Dezember {py}"),
                _statement_table(
                    "prior_bs_assets",
                    "Aktiva",
                    L.ASSETS,
                    prior_view,
                    "bs.total.assets",
                    "Summe Aktiva",
                    with_prior=False,
                ),
                _statement_table(
                    "prior_bs_liabilities",
                    "Passiva",
                    L.EQUITY_AND_LIABILITIES,
                    prior_view,
                    "bs.total.liabilities",
                    "Summe Passiva",
                    with_prior=False,
                ),
            ],
        ),
        Page(
            section="guv",
            blocks=[
                Heading("prior.guv.title", f"Gewinn- und Verlustrechnung {py}", f"Gewinn- und Verlustrechnung {py}"),
                _guv_table(prior_view, with_prior=False),
            ],
        ),
    ]
    for p in pages:
        for b in p.blocks:
            if isinstance(b, Table) and b.id == "guv":
                b.id = "prior_guv"
    return Document(id=f"jahresabschluss_{py}", title=f"Jahresabschluss {py} (Vorjahr)", pages=pages)


def build_package(pid: str, c: Company) -> Package:
    return Package(id=pid, company=c, documents=[build_current_report(c), build_prior_report(c)])
