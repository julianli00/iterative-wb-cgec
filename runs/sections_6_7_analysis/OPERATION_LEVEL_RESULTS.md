# Operation-level M/R/U/W/WO Results

`W` denotes a bounded short-range order change. `WO` denotes a linked long-distance movement serialized as reciprocal M+U records but counted once. The five category totals reconstruct every aggregate TP/FP/FN score exactly.

## All-dataset micro totals

### Character evaluation

| Operation | T0 | T1 | T2 | T3 |
| --- | --- | --- | --- | --- |
| M | 33.04 | 38.30 | 38.27 | 38.17 |
| R | 36.71 | 44.62 | 44.67 | 44.68 |
| U | 40.86 | 43.80 | 43.91 | 43.84 |
| W | 60.09 | 54.20 | 54.45 | 54.23 |
| WO | 56.47 | 52.99 | 52.97 | 52.84 |

| Operation | Direct-Raw | Projected-Direct | Iterative-Projected |
| --- | --- | --- | --- |
| M | +5.25 | -0.03 | -0.09 |
| R | +7.92 | +0.05 | +0.01 |
| U | +2.93 | +0.11 | -0.06 |
| W | -5.90 | +0.25 | -0.21 |
| WO | -3.48 | -0.02 | -0.13 |

### Word evaluation

| Operation | T0 | T1 | T2 | T3 |
| --- | --- | --- | --- | --- |
| M | 31.22 | 35.71 | 35.72 | 35.69 |
| R | 36.93 | 42.47 | 42.51 | 42.52 |
| U | 40.26 | 41.70 | 41.68 | 41.67 |
| W | 59.53 | 51.85 | 52.25 | 52.24 |
| WO | 53.51 | 53.14 | 52.65 | 52.65 |

| Operation | Direct-Raw | Projected-Direct | Iterative-Projected |
| --- | --- | --- | --- |
| M | +4.49 | +0.02 | -0.03 |
| R | +5.54 | +0.05 | +0.01 |
| U | +1.45 | -0.03 | -0.01 |
| W | -7.68 | +0.40 | -0.02 |
| WO | -0.37 | -0.49 | +0.00 |

## Main pattern

Direct-WB improves M, R, and U at both evaluation units, but lowers W and WO. The aggregate F0.5 gain is therefore driven by ordinary missing/replacement/unnecessary corrections, not by better word-order correction. Projection and iteration move every operation by less than one point in the all-dataset micro totals and have mixed signs.

## Interpretation guardrails

- Operation scores are based on the same selected hypothesis-reference combinations as the aggregate F0.5 scores.
- `WO` is not a sixth physical M2 label: it is the report-level name for one validated linked M+U pair.
- Character and word spans can yield different edit counts for the same output, so their operation scores are complementary rather than directly interchangeable.
- Full per-dataset counts, precision, recall, and F0.5 are in `operation_scores.long.tsv`.
