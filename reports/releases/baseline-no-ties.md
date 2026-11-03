# Release decision: baseline-no-ties@4

Compared with production `baseline@3` on the `test` split. **Do not ship.**

Failed: non-inferiority: recall:tie

| Rule | Metric | Value | Limit | 95% interval | Result |
|---|---|---|---|---|---|
| floor | precision | 1.000 | +0.90 |  | pass |
| floor | clean_false_alarm_rate | 0.000 | +0.10 |  | pass |
| floor | decoy_false_alarm_rate | 0.000 | +0.15 |  | pass |
| floor | recall_digital | 0.988 | +0.85 |  | pass |
| non-inferiority | recall | -0.009 | -0.03 | [-0.024, 0.000] | pass |
| non-inferiority | precision | +0.000 | -0.03 | [0.000, 0.000] | pass |
| non-inferiority | recall:casting | +0.000 | -0.10 | [0.000, 0.000] | pass |
| non-inferiority | recall:tie | -0.049 | -0.10 | [-0.128, 0.000] | fail |
| non-inferiority | recall:prior_year | +0.000 | -0.10 | [0.000, 0.000] | pass |
| non-inferiority | recall:narrative | +0.000 | -0.10 | [0.000, 0.000] | pass |
| non-inferiority | recall:missing_disclosure | +0.000 | -0.15 | [0.000, 0.000] | pass |
| non-inferiority | recall:period | +0.000 | -0.15 | [0.000, 0.000] | pass |

Watched, not gating: duplicates_per_finding 0.412, cost_per_package_usd 0.000, p95_latency_s 1.479, recall_scanned 0.000

Evidence runs (pinned in the trace archive): 6f33fb56-8fa5-54c0, 23b22a05-e6b9-53c8
