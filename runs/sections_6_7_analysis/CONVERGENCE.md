# Iterative Behavior and Convergence

An unchanged projected boundary sequence stops the row and carries the previous correction forward without another LLM call. A changed S3 means the row reached the configured T3 endpoint; it is not labeled converged. S1-S2-S1 cycles are reported separately.

| Dataset | N | S1->S2 changed | Stop T1 | Stop T2 | Reach T3 | 2-cycles | T2 output changed | T3 output changed | Splits | Merges |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NLPCC2018 | 2,000 | 9.20% | 1,816 | 162 | 22 | 16 | 33.15% | 90.91% | 92 | 149 |
| MuCGEC | 6,000 | 10.22% | 5,387 | 514 | 99 | 76 | 38.99% | 85.86% | 351 | 474 |
| YACLC | 1,000 | 10.70% | 893 | 84 | 23 | 21 | 48.60% | 86.96% | 64 | 80 |
| FlaCGEC | 1,325 | 11.25% | 1,176 | 126 | 23 | 15 | 28.86% | 82.61% | 100 | 106 |
| FCGEC | 2,000 | 6.10% | 1,878 | 102 | 20 | 16 | 22.95% | 70.00% | 83 | 96 |
| NaCGEC | 5,869 | 6.61% | 5,481 | 342 | 46 | 37 | 19.59% | 86.96% | 249 | 308 |
| NaSGEC-Exam | 2,000 | 5.10% | 1,898 | 83 | 19 | 13 | 27.45% | 73.68% | 73 | 81 |
| CEFE Track 3 | 19 | 5.26% | 18 | 1 | 0 | 0 | 0.00% | 0.00% | 4 | 1 |

`T2 output changed` is conditional on S1->S2 changing; `T3 output changed` is conditional on S2->S3 changing. Both split and merge operations occur in every sufficiently large dataset, so projection is not a split-only procedure.
