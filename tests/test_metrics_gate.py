import numpy as np

from aae.agents.schema import Finding
from aae.evals.gate import decide
from aae.evals.match import FindingResult, Located, PackageResult
from aae.evals.metrics import counts, paired, point, summary

CFG = {
    "split": "x",
    "bootstrap": {"resamples": 500, "seed": 1, "level": 0.95},
    "floors": {"precision": {"min": 0.9}, "clean_false_alarm_rate": {"max": 0.1}},
    "non_inferiority": {"recall": 0.03, "recall:tie": 0.1},
}


def pkg(name, kinds, found, wrong=0, clean_alarm=False):
    defects = [{"id": f"{name}.{i}", "kind": k} for i, k in enumerate(kinds)]
    r = PackageResult(name, defects)
    fi = 0
    for i, d in enumerate(defects):
        if i < found:
            r.found[d["id"]] = fi
            r.findings.append(
                FindingResult(fi, Finding(type=d["kind"], document="a.pdf"), "hit", Located(set(), "cell"), d["id"])
            )
            fi += 1
    for _ in range(wrong + int(clean_alarm)):
        r.findings.append(
            FindingResult(fi, Finding(type="casting", document="a.pdf"), "false_alarm", Located(set(), "none"))
        )
        fi += 1
    return r


def test_ratios_are_sums_over_packages():
    c = counts([pkg("a", ["tie", "casting"], 2), pkg("b", ["tie"], 0, wrong=2), pkg("c", [], 0)])
    assert point(c, "recall") == 2 / 3
    assert point(c, "precision") == 2 / 4
    assert point(c, "recall:tie") == 1 / 2
    assert point(c, "clean_false_alarm_rate") == 0.0


def test_interval_contains_point_and_identical_agents_do_not_differ():
    res = [pkg(f"p{i}", ["tie", "casting"], i % 3) for i in range(30)]
    c = counts(res)
    s = summary(c, b=500, seed=3)
    m = s["metrics"]["recall"]
    assert m["low"] <= m["value"] <= m["high"]
    p = paired(c, counts(res), "recall", b=500)
    assert p["diff"] == 0 and p["low"] == 0 and p["high"] == 0


def test_gate_blocks_a_regression_on_one_kind_and_passes_an_equal_candidate():
    base = [pkg(f"p{i}", ["casting", "tie"], 2) for i in range(40)]
    worse = [pkg(f"p{i}", ["casting", "tie"], 2 if i % 2 else 1) for i in range(40)]  # half the ties lost
    assert decide(counts(base), counts(base), CFG)["ship"]
    d = decide(counts(base), counts(worse), CFG)
    assert not d["ship"] and "non-inferiority: recall:tie" in d["failed"]


def test_floors_block_noisy_candidates():
    noisy = [pkg(f"p{i}", ["tie"], 1, wrong=1) for i in range(20)] + [
        pkg(f"c{i}", [], 0, clean_alarm=True) for i in range(5)
    ]
    d = decide(None, counts(noisy), CFG)
    assert not d["ship"]
    assert {"floor: precision", "floor: clean_false_alarm_rate"} <= set(d["failed"])


def test_paired_needs_the_same_packages():
    a, b = counts([pkg("a", ["tie"], 1)]), counts([pkg("b", ["tie"], 1)])
    try:
        paired(a, b, "recall")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_empty_split_is_not_a_pass():
    c = counts([pkg("a", [], 0)])
    d = decide(None, c, {**CFG, "floors": {"recall_scanned": {"min": 0.5}}})
    assert not d["ship"] and d["checks"][0]["status"] == "n/a"
    assert np.isnan(np.array([np.nan])).all()
