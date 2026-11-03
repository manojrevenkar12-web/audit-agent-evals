# Release decision: hybrid-sonnet@1

Compared with production `baseline@3` on the `test` split. **Do not ship.**

Failed: non-inferiority: precision

| Rule | Metric | Value | Limit | 95% interval | Result |
|---|---|---|---|---|---|
| floor | precision | 0.983 | +0.90 |  | pass |
| floor | clean_false_alarm_rate | 0.057 | +0.10 |  | pass |
| floor | decoy_false_alarm_rate | 0.000 | +0.15 |  | pass |
| floor | recall_digital | 1.000 | +0.85 |  | pass |
| non-inferiority | recall | +0.203 | -0.03 | [0.127, 0.282] | pass |
| non-inferiority | precision | -0.017 | -0.03 | [-0.030, -0.005] | fail |
| non-inferiority | recall:casting | +0.227 | -0.10 | [0.098, 0.372] | pass |
| non-inferiority | recall:tie | +0.171 | -0.10 | [0.047, 0.308] | pass |
| non-inferiority | recall:prior_year | +0.324 | -0.10 | [0.167, 0.487] | pass |
| non-inferiority | recall:narrative | +0.068 | -0.10 | [0.000, 0.157] | pass |
| non-inferiority | recall:missing_disclosure | +0.259 | -0.15 | [0.077, 0.440] | pass |
| non-inferiority | recall:period | +0.208 | -0.15 | [0.040, 0.412] | pass |

Watched, not gating: duplicates_per_finding 0.475, cost_per_package_usd 0.022, p95_latency_s 34.207, recall_scanned 0.917

Evidence runs (pinned in the trace archive): 6f33fb56-8fa5-54c0, a0c3033c-dd93-59cb
