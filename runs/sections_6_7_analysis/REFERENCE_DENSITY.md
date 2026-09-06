# Reference-density Analysis

Scores are grouped by the number of available references (1, 2, 3, or >3). These groups describe oracle opportunity under select-best; they do not imply that dense-reference datasets contain intrinsically better outputs.

The machine-readable dataset-by-stage results are in `reference_density.long.tsv`.

## Pooled descriptive scores by reference-count bucket

| Metric | Unit | Refs | N | T0 | T1 | T2 | T3 | Best |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F0.5 | character | 1 | 12,509 | 29.64 | 34.18 | 34.34 | 34.26 | T2 |
| F0.5 | character | 2 | 4,331 | 42.94 | 48.79 | 48.65 | 48.59 | T1 |
| F0.5 | character | 3 | 1,760 | 46.06 | 50.81 | 50.92 | 50.93 | T3 |
| F0.5 | character | >3 | 1,613 | 54.19 | 59.49 | 59.44 | 59.41 | T1 |
| F0.5 | word | 1 | 12,509 | 27.68 | 30.79 | 30.93 | 30.89 | T2 |
| F0.5 | word | 2 | 4,331 | 43.05 | 47.38 | 47.27 | 47.18 | T1 |
| F0.5 | word | 3 | 1,760 | 46.10 | 50.15 | 50.45 | 50.52 | T3 |
| F0.5 | word | >3 | 1,613 | 55.55 | 60.72 | 60.58 | 60.66 | T1 |
| GLEU | character | 1 | 12,509 | 84.61 | 84.10 | 84.11 | 84.12 | T0 |
| GLEU | character | 2 | 4,331 | 83.42 | 81.50 | 81.40 | 81.45 | T0 |
| GLEU | character | 3 | 1,760 | 78.82 | 76.23 | 76.21 | 76.30 | T0 |
| GLEU | character | >3 | 1,613 | 79.45 | 79.65 | 79.60 | 79.63 | T1 |
| GLEU | word | 1 | 12,509 | 78.59 | 77.84 | 77.87 | 77.86 | T0 |
| GLEU | word | 2 | 4,331 | 77.33 | 74.48 | 74.38 | 74.41 | T0 |
| GLEU | word | 3 | 1,760 | 71.21 | 67.44 | 67.42 | 67.50 | T0 |
| GLEU | word | >3 | 1,613 | 72.57 | 72.14 | 72.11 | 72.18 | T0 |

These pooled groups contain different sentences and datasets, so score levels across rows are descriptive. The best prompting stage is not invariant across reference-count buckets; reference density can affect observed condition rankings.

## Controlled YACLC analysis

YACLC contains 178 sentences with exactly 11 references. Holding those same sentences and hypotheses fixed, the table below compares one reference with all eleven.

| Metric | Unit | Stage | First 1 | All 11 | Delta |
| --- | --- | --- | --- | --- | --- |
| F0.5 | character | T0 | 19.73 | 50.70 | +30.97 |
| F0.5 | character | T1 | 20.11 | 55.56 | +35.45 |
| F0.5 | character | T2 | 20.38 | 56.19 | +35.81 |
| F0.5 | character | T3 | 19.79 | 55.48 | +35.69 |
| F0.5 | word | T0 | 20.60 | 53.36 | +32.76 |
| F0.5 | word | T1 | 22.27 | 56.57 | +34.29 |
| F0.5 | word | T2 | 21.85 | 57.63 | +35.79 |
| F0.5 | word | T3 | 21.49 | 57.38 | +35.89 |
| GLEU | character | T0 | 46.30 | 74.39 | +28.09 |
| GLEU | character | T1 | 42.14 | 76.35 | +34.21 |
| GLEU | character | T2 | 42.66 | 76.91 | +34.25 |
| GLEU | character | T3 | 42.27 | 76.56 | +34.28 |
| GLEU | word | T0 | 34.17 | 65.50 | +31.33 |
| GLEU | word | T1 | 29.31 | 67.44 | +38.13 |
| GLEU | word | T2 | 29.34 | 67.80 | +38.45 |
| GLEU | word | T3 | 29.17 | 67.56 | +38.40 |

All deltas in this controlled table arise only from adding valid references to the same 178 source-hypothesis pairs. The complete first-1 through first-11 trajectories are in `yaclc_incremental_references.tsv`.
