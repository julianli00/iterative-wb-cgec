# Word-based GLEU Select-best

Scores are sentence-level multi-reference word GLEU-select-best, macro-averaged by corpus and multiplied by 100.

| Dataset | Split | N | References | Multi-ref sentences | T0 | T1 | T2 | T3 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nlpcc2018 | test | 2,000 | 2,183 | 183 | 63.74 | 60.30 | 60.18 | 60.24 |
| mucgec | test | 6,000 | 13,119 | 4,268 | 67.13 | 63.52 | 63.45 | 63.45 |
| yaclc | validation | 1,000 | 8,931 | 1,000 | 74.35 | 73.29 | 73.06 | 73.04 |
| flacgec | test | 1,325 | 1,325 | 0 | 73.50 | 69.49 | 69.48 | 69.51 |
| fcgec | validation | 2,000 | 2,550 | 351 | 86.34 | 86.14 | 86.21 | 86.20 |
| nacgec | test | 5,869 | 6,978 | 1,083 | 83.99 | 81.11 | 81.13 | 81.15 |
| nasgec_exam | test | 2,000 | 2,895 | 819 | 85.89 | 84.38 | 84.40 | 84.38 |
| cefe_track3 | validation | 19 | 19 | 0 | 72.30 | 70.46 | 70.29 | 70.29 |

All T0--T3 stages use the same gold-informed projected learner segmentation. Hypotheses and every gold reference are segmented by the same LTP installation.

For every sentence and stage, all references are scored and the highest GLEU is selected before corpus macro-averaging. No BPE or LLM calls are used.
