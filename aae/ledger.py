"""A company's books for two years, generated so that everything ties.

Amounts are exact integers in cents. The statements show thousands of euros (TEUR), each line rounded on its own,
so the sum of shown lines can differ from the shown total by a few TEUR, exactly as in real German financial
statements ("Rundungsdifferenzen"). Those differences are not errors, and an agent that flags them is wrong.

Everything an agent could check is a *fact* with an id (``bs.A.II.2``, ``guv.7``, ``anl.tech.dep_year``, ...).
The renderer places facts on pages; the defect injector changes a fact's shown value; the evaluator knows the
original value of every fact.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------------------------- structure

# Balance sheet (§ 266 HGB, shortened for a medium-sized GmbH). Leaves carry amounts; parents are sums.
ASSETS: list[tuple[str, str, str | None]] = [
    ("bs.A", "A. Anlagevermögen", None),
    ("bs.A.I", "I. Immaterielle Vermögensgegenstände", "bs.A"),
    ("bs.A.II", "II. Sachanlagen", "bs.A"),
    ("bs.A.II.1", "1. Grundstücke und Bauten", "bs.A.II"),
    ("bs.A.II.2", "2. Technische Anlagen und Maschinen", "bs.A.II"),
    ("bs.A.II.3", "3. Andere Anlagen, Betriebs- und Geschäftsausstattung", "bs.A.II"),
    ("bs.A.III", "III. Finanzanlagen", "bs.A"),
    ("bs.B", "B. Umlaufvermögen", None),
    ("bs.B.I", "I. Vorräte", "bs.B"),
    ("bs.B.II", "II. Forderungen und sonstige Vermögensgegenstände", "bs.B"),
    ("bs.B.II.1", "1. Forderungen aus Lieferungen und Leistungen", "bs.B.II"),
    ("bs.B.II.2", "2. Sonstige Vermögensgegenstände", "bs.B.II"),
    ("bs.B.III", "III. Kassenbestand, Guthaben bei Kreditinstituten", "bs.B"),
    ("bs.C", "C. Rechnungsabgrenzungsposten", None),
]
EQUITY_AND_LIABILITIES: list[tuple[str, str, str | None]] = [
    ("bs.P.A", "A. Eigenkapital", None),
    ("bs.P.A.I", "I. Gezeichnetes Kapital", "bs.P.A"),
    ("bs.P.A.II", "II. Kapitalrücklage", "bs.P.A"),
    ("bs.P.A.III", "III. Gewinnrücklagen", "bs.P.A"),
    ("bs.P.A.IV", "IV. Gewinnvortrag", "bs.P.A"),
    ("bs.P.A.V", "V. Jahresüberschuss", "bs.P.A"),
    ("bs.P.B", "B. Rückstellungen", None),
    ("bs.P.B.1", "1. Steuerrückstellungen", "bs.P.B"),
    ("bs.P.B.2", "2. Sonstige Rückstellungen", "bs.P.B"),
    ("bs.P.C", "C. Verbindlichkeiten", None),
    ("bs.P.C.1", "1. Verbindlichkeiten gegenüber Kreditinstituten", "bs.P.C"),
    ("bs.P.C.2", "2. Verbindlichkeiten aus Lieferungen und Leistungen", "bs.P.C"),
    ("bs.P.C.3", "3. Sonstige Verbindlichkeiten", "bs.P.C"),
    ("bs.P.D", "D. Rechnungsabgrenzungsposten", None),
]

# Income statement (§ 275 Abs. 2 HGB, nature of expense method). Sign: +1 income, -1 expense.
INCOME_STATEMENT: list[tuple[str, str, int]] = [
    ("guv.1", "1. Umsatzerlöse", +1),
    ("guv.2", "2. Erhöhung (Verminderung) des Bestands an fertigen und unfertigen Erzeugnissen", +1),
    ("guv.4", "4. Sonstige betriebliche Erträge", +1),
    ("guv.5", "5. Materialaufwand", -1),
    ("guv.6", "6. Personalaufwand", -1),
    ("guv.7", "7. Abschreibungen auf immaterielle Vermögensgegenstände und Sachanlagen", -1),
    ("guv.8", "8. Sonstige betriebliche Aufwendungen", -1),
    ("guv.11", "11. Sonstige Zinsen und ähnliche Erträge", +1),
    ("guv.13", "13. Zinsen und ähnliche Aufwendungen", -1),
    ("guv.14", "14. Steuern vom Einkommen und vom Ertrag", -1),
]
GUV_RESULT_AFTER_TAX = ("guv.15", "15. Ergebnis nach Steuern")
GUV_OTHER_TAXES = ("guv.16", "16. Sonstige Steuern", -1)
GUV_NET = ("guv.17", "17. Jahresüberschuss")

# Fixed-asset schedule (Anlagenspiegel, § 284 Abs. 3 HGB): one row per class.
FIXED_ASSET_CLASSES = [
    ("intangible", "Immaterielle Vermögensgegenstände", "bs.A.I"),
    ("land", "Grundstücke und Bauten", "bs.A.II.1"),
    ("tech", "Technische Anlagen und Maschinen", "bs.A.II.2"),
    ("bga", "Andere Anlagen, Betriebs- und Geschäftsausstattung", "bs.A.II.3"),
    ("fin", "Finanzanlagen", "bs.A.III"),
]
ANL_COLUMNS = [
    ("cost_open", "AK 1.1."),
    ("additions", "Zugänge"),
    ("disposals", "Abgänge"),
    ("cost_close", "AK 31.12."),
    ("dep_open", "Kum. AfA 1.1."),
    ("dep_year", "AfA GJ"),
    ("dep_disposals", "AfA Abgänge"),
    ("dep_close", "Kum. AfA 31.12."),
    ("book_close", "Buchwert 31.12."),
    ("book_prior", "Buchwert Vorjahr"),
]

# Liabilities by remaining term (Verbindlichkeitenspiegel, § 268 Abs. 5 and § 285 Nr. 1 HGB).
LIABILITY_ROWS = [("bank", "bs.P.C.1"), ("trade", "bs.P.C.2"), ("other", "bs.P.C.3")]
LIAB_COLUMNS = [("total", "Gesamt"), ("lt1", "bis 1 Jahr"), ("y1to5", "1 bis 5 Jahre"), ("gt5", "über 5 Jahre")]

AUDIT_FEE_PARTS = [
    ("audit", "Abschlussprüfungsleistungen"),
    ("assurance", "Andere Bestätigungsleistungen"),
    ("tax", "Steuerberatungsleistungen"),
    ("other", "Sonstige Leistungen"),
]

CITIES = ["Darmstadt", "Kassel", "Bielefeld", "Augsburg", "Freiburg", "Regensburg", "Würzburg", "Osnabrück", "Ulm"]
NAME_STEMS = ["Nordlicht", "Weserstahl", "Alpenhaus", "Mainfeld", "Rheintal", "Elbwerk", "Ostkamm", "Lindenholz"]
NAME_SUFFIX = ["Maschinenbau", "Verpackung", "Präzisionsteile", "Logistik", "Elektrotechnik", "Kunststofftechnik"]


def teur(cents: int) -> int:
    """Round an exact amount in cents to whole thousands of euros, half away from zero."""
    sign = -1 if cents < 0 else 1
    return sign * ((abs(cents) + 50_000) // 100_000)


@dataclass
class Year:
    year: int
    exact: dict[str, int] = field(default_factory=dict)  # fact id -> cents (leaf and computed totals)

    def shown(self, fact: str) -> int:
        return teur(self.exact[fact])


@dataclass
class Company:
    name: str
    city: str
    hrb: str
    fiscal_year: int
    current: Year
    prior: Year
    employees: int
    employees_prior: int
    audit_fees: dict[str, int]  # TEUR, as disclosed
    capital_stock_eur: int
    restated: list[str] = field(default_factory=list)  # prior-year facts restated in this year's report

    @property
    def year_end(self) -> str:
        return f"31. Dezember {self.fiscal_year}"


def _pct(rng: random.Random, lo: float, hi: float) -> float:
    return rng.uniform(lo, hi)


def _fixed_assets(rng: random.Random, revenue: int, opening: dict[str, int] | None) -> dict[str, int]:
    """One year of the fixed-asset schedule. ``opening`` carries cost and depreciation from the year before."""
    out: dict[str, int] = {}
    for key, _label, _bs in FIXED_ASSET_CLASSES:
        if opening is None:
            share = {"intangible": 0.03, "land": 0.25, "tech": 0.30, "bga": 0.08, "fin": 0.05}[key]
            cost_open = int(revenue * share * _pct(rng, 0.7, 1.3))
            dep_open = 0 if key == "fin" else int(cost_open * _pct(rng, 0.35, 0.6))
        else:
            cost_open, dep_open = opening[f"anl.{key}.cost_close"], opening[f"anl.{key}.dep_close"]
        additions = int(cost_open * _pct(rng, 0.02, 0.15))
        disposals = int(cost_open * _pct(rng, 0.0, 0.04)) if key != "land" else 0
        cost_close = cost_open + additions - disposals
        if key == "fin":
            dep_year = dep_disp = 0
        else:
            rate = {"intangible": 0.2, "land": 0.03, "tech": 0.1, "bga": 0.15}[key]
            dep_year = int(cost_open * rate * _pct(rng, 0.8, 1.1))
            dep_disp = int(disposals * _pct(rng, 0.6, 0.95))
        dep_close = dep_open + dep_year - dep_disp
        if dep_close > cost_close:  # never depreciate below zero
            dep_year -= dep_close - cost_close
            dep_close = cost_close
        out |= {
            f"anl.{key}.cost_open": cost_open,
            f"anl.{key}.additions": additions,
            f"anl.{key}.disposals": disposals,
            f"anl.{key}.cost_close": cost_close,
            f"anl.{key}.dep_open": dep_open,
            f"anl.{key}.dep_year": dep_year,
            f"anl.{key}.dep_disposals": dep_disp,
            f"anl.{key}.dep_close": dep_close,
            f"anl.{key}.book_close": cost_close - dep_close,
            f"anl.{key}.book_prior": cost_open - dep_open,
        }
    for col, _ in ANL_COLUMNS:
        out[f"anl.total.{col}"] = sum(out[f"anl.{k}.{col}"] for k, _, _ in FIXED_ASSET_CLASSES)
    return out


def _year(rng: random.Random, year: int, revenue: int, prev: Year | None, equity_fixed: dict[str, int]) -> Year:
    y = Year(year)
    e = y.exact
    e |= _fixed_assets(rng, revenue, prev.exact if prev else None)
    for key, _label, bs in FIXED_ASSET_CLASSES:
        e[bs] = e[f"anl.{key}.book_close"]

    # Income statement
    e["guv.1"] = revenue
    e["guv.2"] = int(revenue * _pct(rng, -0.01, 0.015))
    e["guv.4"] = int(revenue * _pct(rng, 0.005, 0.02))
    e["guv.5"] = int(revenue * _pct(rng, 0.40, 0.52))
    e["guv.6"] = int(revenue * _pct(rng, 0.20, 0.28))
    e["guv.7"] = sum(e[f"anl.{k}.dep_year"] for k, _, _ in FIXED_ASSET_CLASSES)
    e["guv.8"] = int(revenue * _pct(rng, 0.07, 0.11))
    e["guv.11"] = int(revenue * _pct(rng, 0.0002, 0.001))
    bank = int(revenue * _pct(rng, 0.10, 0.25))
    e["guv.13"] = int(bank * _pct(rng, 0.03, 0.055))
    ebt = sum(sign * e[f] for f, _, sign in INCOME_STATEMENT if f != "guv.14")
    e["guv.14"] = max(0, int(ebt * _pct(rng, 0.28, 0.31)))
    e["guv.15"] = ebt - e["guv.14"]
    e["guv.16"] = int(revenue * _pct(rng, 0.0005, 0.002))
    e["guv.17"] = e["guv.15"] - e["guv.16"]

    # Balance sheet
    e["bs.B.I"] = int(revenue * _pct(rng, 0.09, 0.15))
    e["bs.B.II.1"] = int(revenue * _pct(rng, 0.09, 0.14))
    e["bs.B.II.2"] = int(revenue * _pct(rng, 0.005, 0.02))
    e["bs.C"] = int(revenue * _pct(rng, 0.001, 0.004))
    e["bs.P.A.I"] = equity_fixed["capital"]
    e["bs.P.A.II"] = equity_fixed["reserve"]
    e["bs.P.A.III"] = equity_fixed["retained"]
    # No distribution: last year's profit is carried forward.
    e["bs.P.A.IV"] = (
        (prev.exact["bs.P.A.IV"] + prev.exact["bs.P.A.V"]) if prev else int(revenue * _pct(rng, 0.02, 0.08))
    )
    e["bs.P.A.V"] = e["guv.17"]
    e["bs.P.B.1"] = int(e["guv.14"] * _pct(rng, 0.2, 0.45))
    e["bs.P.B.2"] = int(revenue * _pct(rng, 0.03, 0.06))
    e["bs.P.C.1"] = bank
    e["bs.P.C.2"] = int(revenue * _pct(rng, 0.05, 0.09))
    e["bs.P.C.3"] = int(revenue * _pct(rng, 0.01, 0.03))
    e["bs.P.D"] = int(revenue * _pct(rng, 0.0, 0.002))

    def total(rows: list[tuple[str, str, str | None]], fact: str) -> int:
        kids = [f for f, _, p in rows if p == fact]
        return sum(total(rows, k) for k in kids) if kids else e[fact]

    # Cash closes the balance sheet; if it would go negative, the bank lends more.
    e["bs.B.III"] = 0
    for _ in range(3):
        assets = sum(total(ASSETS, f) for f, _, p in ASSETS if p is None)
        liabilities = sum(total(EQUITY_AND_LIABILITIES, f) for f, _, p in EQUITY_AND_LIABILITIES if p is None)
        e["bs.B.III"] = liabilities - assets
        if e["bs.B.III"] >= revenue * 0.01:
            break
        e["bs.P.C.1"] += int(revenue * 0.05) - e["bs.B.III"]
        e["bs.B.III"] = 0
    for rows in (ASSETS, EQUITY_AND_LIABILITIES):
        for f, _, _p in rows:
            e[f] = total(rows, f)
    e["bs.total.assets"] = sum(e[f] for f, _, p in ASSETS if p is None)
    e["bs.total.liabilities"] = sum(e[f] for f, _, p in EQUITY_AND_LIABILITIES if p is None)
    assert e["bs.total.assets"] == e["bs.total.liabilities"], "the balance sheet must balance"

    # Liabilities by remaining term
    for key, bs in LIABILITY_ROWS:
        amount = e[bs]
        if key == "bank":
            lt1 = int(amount * _pct(rng, 0.1, 0.3))
            y1to5 = int(amount * _pct(rng, 0.3, 0.5))
        else:
            lt1, y1to5 = int(amount * _pct(rng, 0.85, 1.0)), 0
        gt5 = amount - lt1 - y1to5
        if key != "bank":
            lt1 += gt5
            gt5 = 0
        e |= {f"vbl.{key}.total": amount, f"vbl.{key}.lt1": lt1, f"vbl.{key}.y1to5": y1to5, f"vbl.{key}.gt5": gt5}
    for col, _ in LIAB_COLUMNS:
        e[f"vbl.sum.{col}"] = sum(e[f"vbl.{k}.{col}"] for k, _ in LIABILITY_ROWS)
    return y


def generate_company(seed: int, fiscal_year: int = 2026) -> Company:
    rng = random.Random(seed)
    revenue_prior = rng.randrange(25_000_000_00, 180_000_000_00)
    growth = rng.uniform(-0.12, 0.18)
    capital = rng.choice([25_000_00, 100_000_00, 500_000_00, 1_000_000_00, 2_500_000_00])
    equity_fixed = {
        "capital": capital,
        "reserve": int(revenue_prior * rng.uniform(0.01, 0.05)),
        "retained": int(revenue_prior * rng.uniform(0.02, 0.10)),
    }
    prior = _year(rng, fiscal_year - 1, revenue_prior, None, equity_fixed)
    current = _year(rng, fiscal_year, int(revenue_prior * (1 + growth)), prior, equity_fixed)
    employees_prior = max(40, int(revenue_prior / 100 / rng.uniform(150_000, 260_000)))
    employees = max(40, int(employees_prior * (1 + growth * rng.uniform(0.3, 0.9))))
    audit = rng.randrange(45, 180)
    fees = {
        "audit": audit,
        "assurance": rng.choice([0, 0, rng.randrange(5, 25)]),
        "tax": rng.choice([0, rng.randrange(10, 60)]),
        "other": rng.choice([0, 0, rng.randrange(3, 15)]),
    }
    fees["total"] = sum(fees.values())
    name = f"{rng.choice(NAME_STEMS)} {rng.choice(NAME_SUFFIX)} GmbH"
    return Company(
        name=name,
        city=rng.choice(CITIES),
        hrb=f"HRB {rng.randrange(1000, 99999)}",
        fiscal_year=fiscal_year,
        current=current,
        prior=prior,
        employees=employees,
        employees_prior=employees_prior,
        audit_fees=fees,
        capital_stock_eur=capital // 100,
    )


# --------------------------------------------------------------------------------------- derived figures


def revenue_change_pct(c: Company) -> float:
    """As a management report states it: one decimal, from the shown TEUR figures."""
    cur, pri = c.current.shown("guv.1"), c.prior.shown("guv.1")
    return round((cur - pri) / pri * 100, 1)


def equity_ratio_pct(y: Year) -> float:
    return round(y.shown("bs.P.A") / y.shown("bs.total.assets") * 100, 1)
