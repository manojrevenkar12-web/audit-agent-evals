# 1. Measure agents on seeded errors, not on hand-labelled real reports

**Context.** An audit-quality agent is judged by the errors it finds before sign-off. Real reports with
known errors are scarce, confidential and labelled inconsistently; a team that tunes on a few dozen of them
learns the dataset, not the task.

**Decision.** Generate packages whose figures tie in exact cents, then plant errors of six kinds where we know
it, with decoys that look like errors and are not (disclosed restatements, natural rounding differences). Ground
truth for each error is every place whose check it breaks, found by running reference checks before and after.

**Consequences.** Recall and precision are exact and cheap to recompute; packages can be regenerated at any
size; splits are separate seed ranges, so `test` is never seen while building. The price is realism: synthetic
packages are cleaner than real ones, and errors outside the six kinds are invisible to the truth. That gap is
what the judge and the review queue are for (ADR 3).
