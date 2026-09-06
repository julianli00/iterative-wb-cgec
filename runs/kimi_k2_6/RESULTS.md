# Kimi K2.6 Iterative CGEC Results

## Setup

- Model: `kimi-k2.6`
- Thinking: disabled
- Temperature: omitted from the request; the provider-fixed non-thinking value is 0.6
- Prompting: the paper's Chinese baseline and structured prompts
- Stages: T0 Raw, T1 Direct-WB, T2 Projected-WB, T3 Iterative Projected-WB
- Iteration rule: when the projected segmentation is unchanged, the previous correction is carried forward without another API call
- Data: 8 test/validation splits, 20,213 sentences in total
- Main M2 evaluation: projection-derived `M/R/U/W`, with linked `M+U` pairs scored once as long-distance `WO`; no BPE
- GLEU evaluation: character and LTP-word n-grams, with sentence-level select-best for every available reference
- All scores below are multiplied by 100

## Projection-based Character M2 F0.5

| Dataset | Split | N | T0 | T1 | T2 | T3 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| NLPCC2018 | test | 2,000 | 36.67 | 36.73 | 36.66 | **36.80** |
| MuCGEC | test | 6,000 | 43.18 | 44.12 | **44.19** | 44.09 |
| YACLC | validation | 1,000 | 60.16 | **60.86** | 60.39 | 60.39 |
| FlaCGEC | test | 1,325 | **34.71** | 32.17 | 32.84 | 32.89 |
| FCGEC | validation | 2,000 | **18.52** | 15.44 | 15.63 | 15.48 |
| NaCGEC | test | 5,869 | **28.70** | 23.43 | 23.44 | 23.48 |
| NaSGEC-Exam | test | 2,000 | **27.35** | 22.25 | 22.04 | 22.16 |
| CEFE Track 3 | validation | 19 | **40.67** | 40.46 | 37.57 | 37.57 |

## Projection-based Word M2 F0.5

| Dataset | Split | N | T0 | T1 | T2 | T3 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| NLPCC2018 | test | 2,000 | **35.66** | 34.95 | 35.08 | 35.18 |
| MuCGEC | test | 6,000 | 42.78 | 43.07 | **43.10** | 43.05 |
| YACLC | validation | 1,000 | 61.20 | **62.02** | 61.70 | 61.66 |
| FlaCGEC | test | 1,325 | **31.98** | 29.97 | 30.60 | 30.60 |
| FCGEC | validation | 2,000 | **16.42** | 13.68 | 13.83 | 13.73 |
| NaCGEC | test | 5,869 | **27.42** | 22.18 | 22.14 | 22.26 |
| NaSGEC-Exam | test | 2,000 | **27.23** | 22.46 | 22.37 | 22.43 |
| CEFE Track 3 | validation | 19 | **33.73** | 33.65 | 31.25 | 31.25 |

## Character GLEU Select-best

| Dataset | Split | N | T0 | T1 | T2 | T3 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| NLPCC2018 | test | 2,000 | **73.01** | 70.54 | 70.41 | 70.47 |
| MuCGEC | test | 6,000 | **75.54** | 73.13 | 73.07 | 73.09 |
| YACLC | validation | 1,000 | **81.22** | 80.42 | 80.18 | 80.19 |
| FlaCGEC | test | 1,325 | **81.12** | 78.48 | 78.48 | 78.53 |
| FCGEC | validation | 2,000 | **90.95** | 90.81 | 90.86 | 90.85 |
| NaCGEC | test | 5,869 | **88.99** | 87.13 | 87.15 | 87.16 |
| NaSGEC-Exam | test | 2,000 | **90.43** | 89.40 | 89.40 | 89.40 |
| CEFE Track 3 | validation | 19 | **81.54** | 80.57 | 80.45 | 80.45 |

## Word GLEU Select-best

| Dataset | Split | N | T0 | T1 | T2 | T3 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| NLPCC2018 | test | 2,000 | **63.74** | 60.30 | 60.18 | 60.24 |
| MuCGEC | test | 6,000 | **67.13** | 63.52 | 63.45 | 63.45 |
| YACLC | validation | 1,000 | **74.35** | 73.29 | 73.06 | 73.04 |
| FlaCGEC | test | 1,325 | **73.50** | 69.49 | 69.48 | 69.51 |
| FCGEC | validation | 2,000 | **86.34** | 86.14 | 86.21 | 86.20 |
| NaCGEC | test | 5,869 | **83.99** | 81.11 | 81.13 | 81.15 |
| NaSGEC-Exam | test | 2,000 | **85.89** | 84.38 | 84.40 | 84.38 |
| CEFE Track 3 | validation | 19 | **72.30** | 70.46 | 70.29 | 70.29 |

## Main Findings

1. A structured stage exceeds Raw on 3/8 datasets for character F0.5 and 2/8 for word F0.5. It exceeds Raw on 0/8 datasets for both character and word GLEU.
2. Projection is not uniformly harmful or helpful relative to Direct-WB. T2 exceeds T1 on 4/8 datasets for both character and word F0.5, but the corpus-level differences are generally small.
3. The Kimi experiment therefore confirms that better or iteratively projected word boundaries do not reliably improve GEC quality. Raw remains best on most M2 datasets and all GLEU datasets.
4. The pipeline converges quickly: 18,487/20,213 sentences (91.46%) stop after Direct-WB, 1,432 (7.08%) stop after the first projected pass, and only 294 (1.45%) reach T3 generation.
5. Projection performs both operations through S3: 1,098 boundary splits and 1,289 boundary merges.
6. An independent audit reconstructed all 128 reported metric cells. Maximum discrepancies were 0 for character/word F0.5, 0.0000005 points for character GLEU, and 0 for word GLEU.

## Generation Audit

- All 20,213 rows are present and marked successful; no T0-T3 output is missing.
- The retained rows contain 42,446 API calls and 5,057,526 total tokens reported by the API.
- Output validation retried 28 malformed or runaway responses successfully.
- Kimi content filtering affected 76 sentences (0.38%): 146 stage calls used the documented identity fallback, comprising 76 T0 and 70 T1 calls.
- A 512-token response cap was added as a guard during the resumable run. No accepted output approached it: the longest retained output was 363 characters, and none exceeded 512 characters.
- CEFE Track 3 contains only 19 validation sentences, so its scores are exploratory rather than stable corpus evidence.

## Supporting Artifacts

- `projection_character_m2/scores.projection.f05.md`: primary character M2 table
- `projection_word_m2/scores.f05.md`: primary word M2 table
- `character_gleu/scores.md`: character GLEU table and reference counts
- `word_gleu/scores.md`: word GLEU table and reference counts
- `projection_character_m2/scores.f05_comparison.md`: controlled ChERRANT-versus-projection alignment comparison using the same Kimi outputs
- `evaluation_audit/AUDIT.md`: independent 128-cell evaluation audit
- `GENERATION_AUDIT.tsv`: per-dataset generation, convergence, and boundary-operation diagnostics
