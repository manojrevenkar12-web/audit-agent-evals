# Release decision: hybrid-haiku@1

Compared with production `baseline@3` on the `test` split. **Do not ship.**

Failed: floor: clean_false_alarm_rate; non-inferiority: precision

| Rule | Metric | Value | Limit | 95% interval | Result |
|---|---|---|---|---|---|
| floor | precision | 0.981 | +0.90 |  | pass |
| floor | clean_false_alarm_rate | 0.114 | +0.10 |  | fail |
| floor | decoy_false_alarm_rate | 0.000 | +0.15 |  | pass |
| floor | recall_digital | 1.000 | +0.85 |  | pass |
| non-inferiority | recall | +0.161 | -0.03 | [0.093, 0.230] | pass |
| non-inferiority | precision | -0.019 | -0.03 | [-0.037, -0.006] | fail |
| non-inferiority | recall:casting | +0.091 | -0.10 | [0.021, 0.188] | pass |
| non-inferiority | recall:tie | +0.122 | -0.10 | [0.021, 0.244] | pass |
| non-inferiority | recall:prior_year | +0.270 | -0.10 | [0.121, 0.419] | pass |
| non-inferiority | recall:narrative | +0.091 | -0.10 | [0.020, 0.186] | pass |
| non-inferiority | recall:missing_disclosure | +0.259 | -0.15 | [0.077, 0.440] | pass |
| non-inferiority | recall:period | +0.208 | -0.15 | [0.040, 0.412] | pass |

Watched, not gating: duplicates_per_finding 0.490, cost_per_package_usd 0.002, p95_latency_s 50.673, recall_scanned 0.729

Evidence runs (pinned in the trace archive): 6f33fb56-8fa5-54c0, ebb04217-2bd0-5944
