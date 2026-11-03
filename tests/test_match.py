"""The matcher turns a reviewer's pointer into location ids; every finding gets exactly one verdict."""

from aae.agents.schema import Finding
from aae.evals.match import DECOY, DUPLICATE, FALSE_ALARM, HIT, MISTYPED, ROUNDING, UNLOCATED, match


def placed(i, kind, page, text, label="", column=""):
    return {"id": i, "kind": kind, "page": page, "bbox": [0, 0, 1, 1], "text": text, "label": label, "column": column}


TRUTH = {
    "package": "p1",
    "documents": [
        {"id": "ja_2026", "file": "ja_2026.pdf", "scanned": False},
        {"id": "ja_2025", "file": "ja_2025.pdf", "scanned": False},
    ],
    "placed": [
        placed("ja_2026:bs_assets:bs.A:cy", "cell", 2, "65.604", "A. Anlagevermögen", "31.12.2026 TEUR"),
        placed("ja_2026:bs_assets:bs.A:py", "cell", 2, "65.896", "A. Anlagevermögen", "31.12.2025 TEUR"),
        placed("ja_2026:bs_assets:bs.total.assets:cy", "cell", 2, "109.926", "Summe Aktiva", "31.12.2026 TEUR"),
        placed("ja_2026:bs_liabilities:bs.P.B:py", "cell", 3, "6.539", "B. Rückstellungen", "31.12.2025 TEUR"),
        placed("ja_2026:guv:guv.17:cy", "cell", 4, "8.287", "17. Jahresüberschuss", "2026 TEUR"),
        placed("ja_2026:heading:cover.title", "heading", 1, "Jahresabschluss zum 31. Dezember 2025"),
        placed("ja_2026:claim:claim.revenue", "claim", 8, "auf 134.124 TEUR"),
        placed("ja_2026:claim:claim.revenue_prior", "claim", 8, "(Vorjahr: 133.274 TEUR)."),
    ],
    "defects": [
        {
            "id": "p1.d1",
            "kind": "casting",
            "target": "ja_2026:bs_assets:bs.A:cy",
            "acceptable_locations": ["ja_2026:bs_assets:bs.A:cy", "ja_2026:bs_assets:bs.total.assets:cy"],
            "acceptable_types": ["casting"],
        },
        {
            "id": "p1.d2",
            "kind": "period",
            "target": "ja_2026:heading:cover.title",
            "acceptable_locations": ["ja_2026:heading:cover.title"],
            "acceptable_types": ["period"],
        },
        {
            "id": "p1.d3",
            "kind": "narrative",
            "target": "ja_2026:claim:claim.revenue_prior",
            "acceptable_locations": ["ja_2026:claim:claim.revenue_prior"],
            "acceptable_types": ["narrative"],
        },
        {
            "id": "p1.d4",
            "kind": "missing_disclosure",
            "target": "ja_2026:disclosure:audit_fees",
            "acceptable_locations": ["ja_2026:disclosure:audit_fees"],
            "acceptable_types": ["missing_disclosure"],
        },
    ],
    "decoys": [{"id": "p1.decoy1", "kind": "restatement", "locations": ["ja_2026:bs_liabilities:bs.P.B:py"]}],
    "rounding_differences": ["ja_2026:guv:guv.17:cy"],
}


def f(**kw):
    return Finding(document=kw.pop("document", "ja_2026.pdf"), **kw)


def test_cell_by_label_and_column_hits_and_repeats_are_duplicates():
    r = match(
        TRUTH,
        [
            f(type="casting", page=2, row_label="Anlagevermögen", column="31.12.2026 TEUR"),
            f(type="casting", page=2, row_label="Summe Aktiva", column="2026"),
        ],
    )
    assert [x.verdict for x in r.findings] == [HIT, DUPLICATE]
    assert r.found == {"p1.d1": 0}


def test_wrong_type_at_the_right_place_is_mistyped():
    r = match(TRUTH, [f(type="tie", page=2, row_label="A. Anlagevermögen", column="31.12.2026 TEUR")])
    assert r.findings[0].verdict == MISTYPED and not r.found


def test_heading_claim_and_disclosure():
    r = match(
        TRUTH,
        [
            f(type="period", page=1, quote="Jahresabschluss zum 31. Dezember 2025", found_value="2025"),
            f(
                type="narrative",
                page=8,
                quote="Die Umsatzerlöse ... (Vorjahr: 133.274 TEUR)",
                found_value="133.274 TEUR",
            ),
            f(type="missing_disclosure", quote="Honorar des Abschlussprüfers fehlt"),
        ],
    )
    assert [x.verdict for x in r.findings] == [HIT, HIT, HIT]
    assert set(r.found) == {"p1.d2", "p1.d3", "p1.d4"}


def test_decoys_rounding_and_unlocated_are_false_alarms_with_reasons():
    r = match(
        TRUTH,
        [
            f(type="prior_year", page=3, row_label="B. Rückstellungen", column="31.12.2025 TEUR"),
            f(type="casting", page=4, row_label="Jahresüberschuss", column="2026 TEUR"),
            f(type="casting", page=9, row_label="Nicht vorhanden"),
            f(type="casting", page=2, row_label="A. Anlagevermögen", column="31.12.2025 TEUR"),
        ],
    )
    assert [x.verdict for x in r.findings] == [DECOY, ROUNDING, UNLOCATED, FALSE_ALARM]


def test_value_disambiguates_an_unknown_column():
    r = match(
        TRUTH, [f(type="casting", page=2, row_label="A. Anlagevermögen", column="laufendes Jahr", found_value="65.604")]
    )
    assert r.findings[0].verdict == HIT
