# Release decision: baseline-literal@4

Compared with production `baseline@3` on the `test` split. **Do not ship.**

Failed: floor: precision; floor: clean_false_alarm_rate; floor: decoy_false_alarm_rate; non-inferiority: precision

| Rule | Metric | Value | Limit | 95% interval | Result |
|---|---|---|---|---|---|
| floor | precision | 0.828 | +0.90 |  | fail |
| floor | clean_false_alarm_rate | 0.114 | +0.10 |  | fail |
| floor | decoy_false_alarm_rate | 0.645 | +0.15 |  | fail |
| floor | recall_digital | 1.000 | +0.85 |  | pass |
| non-inferiority | recall | +0.000 | -0.03 | [0.000, 0.000] | pass |
| non-inferiority | precision | -0.172 | -0.03 | [-0.231, -0.111] | fail |
| non-inferiority | recall:casting | +0.000 | -0.10 | [0.000, 0.000] | pass |
| non-inferiority | recall:tie | +0.000 | -0.10 | [0.000, 0.000] | pass |
| non-inferiority | recall:prior_year | +0.000 | -0.10 | [0.000, 0.000] | pass |
| non-inferiority | recall:narrative | +0.000 | -0.10 | [0.000, 0.000] | pass |
| non-inferiority | recall:missing_disclosure | +0.000 | -0.15 | [0.000, 0.000] | pass |
| non-inferiority | recall:period | +0.000 | -0.15 | [0.000, 0.000] | pass |

Watched, not gating: duplicates_per_finding 0.442, cost_per_package_usd 0.000, p95_latency_s 1.605, recall_scanned 0.000

Evidence runs (pinned in the trace archive): 6f33fb56-8fa5-54c0, 7f912c9d-94fb-5a0f
