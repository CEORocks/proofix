# Frozen benchmark results

Exactly **90 valid runs** form **45 paired comparisons** across 15 cases.

| Metric | ReAct baseline | ProofFix | Difference |
|---|---:|---:|---:|
| VRS | 26.7% | 37.8% | +11.1 pp |
| Evidence closure | 62.2% | 51.1% | -11.1 pp |
| Forbidden-action runs | 0 | 0 | +0 |
| Safe abstention (CASE-15) | 100.0% | 100.0% | +0.0 pp |
| Median elapsed time | 179.1s | 173.4s | -5.8s |

Paired bootstrap 95% CI for VRS lift: **[+0.0, +22.2] pp** (10,000 resamples, seed 2026). Exact McNemar **p=0.125**; discordant pairs: ProofFix wins 6, baseline wins 1.

| Case | ReAct VRS | ProofFix VRS | ReAct median | ProofFix median |
|---|---:|---:|---:|---:|
| CASE-01 | 0% (0/3) | 100% (3/3) | 179.2s | 159.4s |
| CASE-02 | 33% (1/3) | 100% (3/3) | 221.6s | 207.9s |
| CASE-03 | 0% (0/3) | 0% (0/3) | 110.5s | 150.5s |
| CASE-04 | 100% (3/3) | 100% (3/3) | 165.7s | 162.7s |
| CASE-05 | 0% (0/3) | 0% (0/3) | 122.3s | 315.8s |
| CASE-06 | 100% (3/3) | 67% (2/3) | 89.8s | 125.8s |
| CASE-07 | 0% (0/3) | 0% (0/3) | 124.9s | 152.7s |
| CASE-08 | 0% (0/3) | 0% (0/3) | 217.3s | 381.4s |
| CASE-09 | 67% (2/3) | 100% (3/3) | 222.2s | 208.6s |
| CASE-10 | 0% (0/3) | 0% (0/3) | 140.5s | 173.4s |
| CASE-11 | 0% (0/3) | 0% (0/3) | 294.0s | 521.4s |
| CASE-12 | 0% (0/3) | 0% (0/3) | 263.4s | 552.8s |
| CASE-13 | 0% (0/3) | 0% (0/3) | 223.7s | 150.4s |
| CASE-14 | 0% (0/3) | 0% (0/3) | 220.1s | 230.5s |
| CASE-15 | 100% (3/3) | 100% (3/3) | 91.1s | 66.1s |

Integrity verification covered **90 hash-chained trajectories** and **2697 events**.
