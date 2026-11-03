import copy
import random

import pytest

from aae.checks import all_violations, footing
from aae.dataset import make_package
from aae.defects import KINDS, plant
from aae.document import build_package
from aae.ledger import generate_company, teur


@pytest.mark.parametrize("seed", range(40))
def test_clean_packages_pass_every_check(seed):
    pkg = build_package(f"t-{seed}", generate_company(seed))
    assert all_violations(pkg) == []


def test_teur_rounds_half_away_from_zero():
    assert teur(150_000) == 2 and teur(149_999) == 1 and teur(-150_000) == -2


def test_packages_are_reproducible():
    a, ta = make_package(7, "dev")
    b, tb = make_package(7, "dev")
    assert ta == tb


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_can_be_planted_and_is_detectable(kind):
    planted = 0
    for seed in range(12):
        pkg = build_package(f"k-{seed}", generate_company(seed))
        defects, _, restated = plant(pkg, random.Random(seed), [kind], restate=False)
        if not defects:
            continue
        planted += 1
        d = defects[0]
        assert d.kind == kind and d.target in d.acceptable_locations and kind in d.acceptable_types
        assert all_violations(pkg, restated), "a planted defect must break at least one rule"
    assert planted >= 10


def test_restatement_is_not_a_violation():
    for seed in range(10):
        pkg = build_package(f"r-{seed}", generate_company(seed))
        _, decoys, restated = plant(pkg, random.Random(seed), [], restate=True)
        assert decoys and restated
        assert all_violations(pkg, restated) == []
        assert any(v.type == "prior_year" for v in all_violations(pkg, {})), "without the note it would be an error"


def test_rounding_differences_occur_and_are_tolerated():
    strict = sum(len(footing(build_package("x", generate_company(s)).documents[0], strict=True)) for s in range(20))
    real = sum(len(footing(build_package("x", generate_company(s)).documents[0])) for s in range(20))
    assert strict > 20 and real == 0


def test_truth_lists_locations_on_the_page(unit_truths):
    for t in unit_truths.values():
        placed = {p["id"] for p in t["placed"]}
        for d in t["defects"]:
            for loc in d["acceptable_locations"]:
                assert ":disclosure:" in loc or loc in placed or loc.rsplit(":", 1)[0] in placed, loc


def test_deepcopy_of_package_is_independent():
    pkg = build_package("c", generate_company(3))
    other = copy.deepcopy(pkg)
    other.documents[0].table("guv").cell("guv.1", "cy").value += 1
    assert (
        pkg.documents[0].table("guv").cell("guv.1", "cy").value
        != other.documents[0].table("guv").cell("guv.1", "cy").value
    )
