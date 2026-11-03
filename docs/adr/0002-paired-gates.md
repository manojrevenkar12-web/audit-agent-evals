# 2. Release gates: floors plus paired non-inferiority

**Context.** Comparing two agents' point estimates on 160 packages says little: the intervals overlap. A
regression in one rare kind of error disappears in the overall number.

**Decision.** A candidate must meet absolute floors (precision, false alarms on clean packages and on
restatements, recall on text documents) and must not be worse than production by more than a margin, judged on
the lower end of a 95% paired bootstrap interval of the difference, overall and per kind. Packages are the unit
of resampling. A rule with nothing to count is "n/a", never a pass.

**Consequences.** A candidate that loses part of one check family fails even when overall recall barely moves
(`baseline-no-ties`). Margins are policy and live in `config/gates.yaml`. Paired comparison needs both agents on
the same packages; the code refuses anything else.
