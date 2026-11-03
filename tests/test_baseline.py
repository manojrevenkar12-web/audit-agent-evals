"""The rules agent on the unit split: every defect in a readable package is found, nothing else is flagged."""

import pytest

from aae import config
from aae.agents.baseline import BaselineAgent, round_half_up
from aae.evals.match import CORRECT, match


@pytest.fixture(scope="module")
def answers(unit_split, unit_truths):
    a = BaselineAgent("baseline")
    return {pid: (a.review(config.DATA / unit_split / "packages" / pid), t) for pid, t in unit_truths.items()}


def test_finds_every_defect_in_readable_packages_without_false_alarms(answers):
    for pid, (run, truth) in answers.items():
        r = match(truth, run.findings)
        assert all(f.verdict in CORRECT for f in r.findings), (
            pid,
            [(f.verdict, f.finding) for f in r.findings if f.verdict not in CORRECT],
        )
        if not r.scanned:
            assert len(r.found) == len(r.defects), pid


def test_scanned_reports_are_reported_unreadable(answers):
    scanned = [(run, t) for run, t in answers.values() if t["documents"][0]["scanned"]]
    assert scanned, "the unit split should contain a scanned report"
    for run, _ in scanned:
        assert run.pages_unreadable >= 8 and run.error is None


def test_strict_variant_flags_rounding_differences(unit_split, unit_truths):
    a = BaselineAgent("baseline-strict")
    verdicts = []
    for pid, t in unit_truths.items():
        if t["rounding_differences"] and not t["documents"][0]["scanned"]:
            verdicts += [
                f.verdict for f in match(t, a.review(config.DATA / unit_split / "packages" / pid).findings).findings
            ]
    assert "rounding" in verdicts


def test_spans_trace_every_step(answers):
    run, _ = next(iter(answers.values()))
    kinds = {s.kind for s in run.spans}
    assert {"extract"} <= kinds and all(s.duration_ms >= 0 for s in run.spans)


def test_round_half_up():
    assert round_half_up(2.25) == 2.3 and round_half_up(-2.25) == -2.3 and round_half_up(0.04) == 0.0
