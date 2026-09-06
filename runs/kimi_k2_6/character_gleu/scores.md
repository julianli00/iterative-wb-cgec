# Character-based GLEU Select-best

Scores are sentence-level multi-reference GLEU-select-best, averaged over each corpus and multiplied by 100. Character n-grams up to order 4 are used.

| Dataset | Split | N | References | Multi-ref sentences | T0 | T1 | T2 | T3 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nlpcc2018 | test | 2,000 | 2,183 | 183 | 73.01 | 70.54 | 70.41 | 70.47 |
| mucgec | test | 6,000 | 13,119 | 4,268 | 75.54 | 73.13 | 73.07 | 73.09 |
| yaclc | validation | 1,000 | 8,931 | 1,000 | 81.22 | 80.42 | 80.18 | 80.19 |
| flacgec | test | 1,325 | 1,325 | 0 | 81.12 | 78.48 | 78.48 | 78.53 |
| fcgec | validation | 2,000 | 2,550 | 351 | 90.95 | 90.81 | 90.86 | 90.85 |
| nacgec | test | 5,869 | 6,978 | 1,083 | 88.99 | 87.13 | 87.15 | 87.16 |
| nasgec_exam | test | 2,000 | 2,895 | 819 | 90.43 | 89.40 | 89.40 | 89.40 |
| cefe_track3 | validation | 19 | 19 | 0 | 81.54 | 80.57 | 80.45 | 80.45 |

For each sentence and stage, GLEU is computed against every available gold reference; the highest reference score is selected, and the selected sentence scores are macro-averaged.

Normalization removes BOM characters and whitespace only. No BPE, word segmentation, OpenCC conversion, or LLM calls are used.
