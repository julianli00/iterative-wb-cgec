# Consolidated Evaluation Report

Generated: 2026-08-06 05:57 UTC

## Scope

This report consolidates the finalized evaluations of the iterative word-boundary-aware Chinese grammatical error correction pipeline. The same saved DeepSeek outputs are evaluated at T0--T3 under three conditions:

1. uniform ChERRANT character-level M2 evaluation;
2. projection-based character-level M2 evaluation; and
3. character-based multi-reference GLEU-select-best.

Pilot runs, the no-`t2s` projection diagnostic, and the preliminary mixed-M2 scoreboard are not treated as formal results. A historical FlaCGEC T0--T10 diagnostic is retained separately at the end.

## Experimental Setup

- Model: `deepseek-v4-pro`.
- Decoding: thinking disabled; temperature `0.000001`.
- Prompting: the paper's Chinese baseline and structured prompts.
- T0: unsegmented learner sentence.
- T1: LTP-segmented learner sentence.
- T2: first word-boundary projection from T1.
- T3: second word-boundary projection from T2.
- Convergence: when the projected segmentation is unchanged, the prior output is carried forward without another LLM call.

## Dataset Coverage

| Dataset | Split | Sentences | References | Multi-ref sentences | >3 refs | Max refs |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| NLPCC2018 | test | 2,000 | 2,183 | 183 | 0 | 2 |
| MuCGEC | test | 6,000 | 13,119 | 4,268 | 557 | 8 |
| YACLC | validation | 1,000 | 8,931 | 1,000 | 1,000 | 11 |
| FlaCGEC | test | 1,325 | 1,325 | 0 | 0 | 1 |
| FCGEC | validation | 2,000 | 2,550 | 351 | 47 | 8 |
| NaCGEC | test | 5,869 | 6,978 | 1,083 | 4 | 5 |
| NaSGEC-Exam | test | 2,000 | 2,895 | 819 | 5 | 4 |
| CEFE Track 3 | validation | 19 | 19 | 0 | 0 | 1 |

Total: **20,213 sentences**, **38,000 references**, and **7,704 multi-reference sentences**; **1,613 sentences** have more than three references.

For both M2 methods, the same complete reference set and the same comparator are used. GLEU independently scores every available reference and selects the highest sentence-level score. No first-three-reference cap is applied.

### Effect of Using All References

The following values are the uniform ChERRANT F0.5 difference between using all generated references and retaining only annotator IDs 0--2. Positive values show the benefit of references beyond the first three.

| Dataset | Split | T0 | T1 | T2 | T3 |
| --- | --- | ---: | ---: | ---: | ---: |
| NLPCC2018 | test | +0.00 | +0.00 | +0.00 | +0.00 |
| MuCGEC | test | +0.40 | +0.58 | +0.57 | +0.56 |
| YACLC | validation | +14.35 | +15.25 | +15.27 | +15.35 |
| FlaCGEC | test | +0.00 | +0.00 | +0.00 | +0.00 |
| FCGEC | validation | +0.00 | +0.01 | +0.01 | +0.01 |
| NaCGEC | test | +0.01 | +0.02 | +0.02 | +0.01 |
| NaSGEC-Exam | test | +0.00 | +0.00 | +0.00 | +0.00 |
| CEFE Track 3 | validation | +0.00 | +0.00 | +0.00 | +0.00 |

Using all references is especially important for YACLC (+14.35 to +15.35 points) and also affects MuCGEC (+0.40 to +0.58). Effects on the other splits are at most 0.02 points because they have fewer references or later references rarely change the selected edit match.

## Pipeline Diagnostics

| Dataset | Split | N | Converged by T3 | WB splits | WB merges |
| --- | --- | ---: | ---: | ---: | ---: |
| NLPCC2018 | test | 2,000 | 1,978 (98.9%) | 92 | 149 |
| MuCGEC | test | 6,000 | 5,901 (98.4%) | 351 | 474 |
| YACLC | validation | 1,000 | 977 (97.7%) | 64 | 80 |
| FlaCGEC | test | 1,325 | 1,302 (98.3%) | 100 | 106 |
| FCGEC | validation | 2,000 | 1,980 (99.0%) | 83 | 96 |
| NaCGEC | test | 5,869 | 5,823 (99.2%) | 249 | 308 |
| NaSGEC-Exam | test | 2,000 | 1,981 (99.1%) | 73 | 81 |
| CEFE Track 3 | validation | 19 | 19 (100.0%) | 4 | 1 |

Overall, **19,961/20,213 (98.8%)** sentences converged by T3. Projection performed **1,016 splits** and **1,295 merges**, confirming that it supports both boundary operations.

## Evaluation 1: Uniform ChERRANT Character M2

Reference and hypothesis M2 files are generated uniformly at character granularity, without BPE, using all textual references. ChERRANT target normalization applies Traditional-to-Simplified conversion. Scores are corpus-level F0.5 multiplied by 100.

| Dataset | Split | N | T0 | T1 | T2 | T3 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| NLPCC2018 | test | 2,000 | 34.74 | 40.40 | 40.27 | 40.23 |
| MuCGEC | test | 6,000 | 42.95 | 49.84 | 49.75 | 49.73 |
| YACLC | validation | 1,000 | 57.40 | 63.37 | 63.47 | 63.42 |
| FlaCGEC | test | 1,325 | 45.74 | 46.83 | 46.95 | 46.94 |
| FCGEC | validation | 2,000 | 21.38 | 24.96 | 25.07 | 24.99 |
| NaCGEC | test | 5,869 | 33.48 | 33.06 | 33.34 | 33.14 |
| NaSGEC-Exam | test | 2,000 | 29.57 | 33.32 | 33.18 | 33.49 |
| CEFE Track 3 | validation | 19 | 42.86 | 44.12 | 44.12 | 44.12 |

The best structured stage exceeds T0 on seven of eight splits; NaCGEC is the exception. Most of the gain occurs at T0 to T1, while T1--T3 changes are small and non-monotonic.

## Evaluation 2: Projection-based Character M2

Gold references and hypotheses are regenerated with the same projection-based character alignment. The source-target pairs, reference sets, normalization, edit comparator, and beta values are otherwise controlled. Scores are corpus-level F0.5 multiplied by 100.

| Dataset | Split | N | T0 | T1 | T2 | T3 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| NLPCC2018 | test | 2,000 | 35.32 | 40.93 | 40.78 | 40.73 |
| MuCGEC | test | 6,000 | 42.63 | 49.54 | 49.50 | 49.46 |
| YACLC | validation | 1,000 | 58.89 | 63.72 | 63.73 | 63.72 |
| FlaCGEC | test | 1,325 | 59.03 | 59.91 | 60.10 | 60.08 |
| FCGEC | validation | 2,000 | 24.17 | 26.80 | 26.99 | 26.86 |
| NaCGEC | test | 5,869 | 35.52 | 34.53 | 34.75 | 34.59 |
| NaSGEC-Exam | test | 2,000 | 31.64 | 35.13 | 34.88 | 35.14 |
| CEFE Track 3 | validation | 19 | 48.52 | 44.97 | 44.97 | 44.97 |

### Alignment Effect: Projection minus ChERRANT

| Dataset | Split | T0 | T1 | T2 | T3 |
| --- | --- | ---: | ---: | ---: | ---: |
| NLPCC2018 | test | +0.58 | +0.53 | +0.51 | +0.50 |
| MuCGEC | test | -0.32 | -0.30 | -0.25 | -0.27 |
| YACLC | validation | +1.49 | +0.35 | +0.26 | +0.30 |
| FlaCGEC | test | +13.29 | +13.08 | +13.15 | +13.14 |
| FCGEC | validation | +2.79 | +1.84 | +1.92 | +1.87 |
| NaCGEC | test | +2.04 | +1.47 | +1.41 | +1.45 |
| NaSGEC-Exam | test | +2.07 | +1.81 | +1.70 | +1.65 |
| CEFE Track 3 | validation | +5.66 | +0.85 | +0.85 | +0.85 |

Projection-based M2 raises F0.5 on seven of eight splits relative to ChERRANT-generated M2; MuCGEC decreases slightly. FlaCGEC changes by about 13 points. These score changes demonstrate alignment sensitivity, but higher downstream scores alone do not prove that an alignment is linguistically more accurate.

## Evaluation 3: Character GLEU Select-best

GLEU uses character 1--4 grams. For each sentence and stage, it scores every gold reference, selects the highest reference score, and macro-averages the selected scores. BOM and whitespace are removed; no BPE, word segmentation, or OpenCC conversion is applied. Values are multiplied by 100.

| Dataset | Split | N | References | T0 | T1 | T2 | T3 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NLPCC2018 | test | 2,000 | 2,183 | 73.20 | 70.66 | 70.62 | 70.63 |
| MuCGEC | test | 6,000 | 13,119 | 75.92 | 74.36 | 74.31 | 74.37 |
| YACLC | validation | 1,000 | 8,931 | 79.86 | 81.44 | 81.39 | 81.42 |
| FlaCGEC | test | 1,325 | 1,325 | 84.13 | 80.94 | 80.92 | 81.03 |
| FCGEC | validation | 2,000 | 2,550 | 91.77 | 92.76 | 92.78 | 92.77 |
| NaCGEC | test | 5,869 | 6,978 | 89.67 | 88.91 | 88.93 | 88.92 |
| NaSGEC-Exam | test | 2,000 | 2,895 | 90.95 | 91.27 | 91.24 | 91.27 |
| CEFE Track 3 | validation | 19 | 19 | 82.74 | 81.00 | 81.00 | 81.00 |

YACLC, FCGEC, and NaSGEC-Exam obtain a higher structured-stage GLEU than T0. GLEU often favors conservative outputs that preserve source n-grams, so its ranking need not match edit-based M2 F0.5.

## Cross-metric Best Stage

| Dataset | Split | ChERRANT F0.5 | Projection F0.5 | GLEU |
| --- | --- | ---: | ---: | ---: |
| NLPCC2018 | test | T1 (40.40) | T1 (40.93) | T0 (73.20) |
| MuCGEC | test | T1 (49.84) | T1 (49.54) | T0 (75.92) |
| YACLC | validation | T2 (63.47) | T2 (63.73) | T1 (81.44) |
| FlaCGEC | test | T2 (46.95) | T2 (60.10) | T0 (84.13) |
| FCGEC | validation | T2 (25.07) | T2 (26.99) | T2 (92.78) |
| NaCGEC | test | T0 (33.48) | T0 (35.52) | T0 (89.67) |
| NaSGEC-Exam | test | T3 (33.49) | T3 (35.14) | T3 (91.27) |
| CEFE Track 3 | validation | T1 (44.12) | T0 (48.52) | T0 (82.74) |

## F1 and F2 Summary

F1 and F2 were computed with the same M2 comparator. The table reports the best T0--T3 stage for each beta and alignment method.

| Dataset | Split | ChERRANT F1 | Projection F1 | ChERRANT F2 | Projection F2 |
| --- | --- | ---: | ---: | ---: | ---: |
| NLPCC2018 | test | T0 (36.90) | T0 (37.32) | T0 (39.37) | T0 (39.56) |
| MuCGEC | test | T0 (43.51) | T0 (43.33) | T0 (44.27) | T0 (44.17) |
| YACLC | validation | T1 (59.51) | T1 (59.73) | T0 (62.22) | T0 (63.13) |
| FlaCGEC | test | T0 (45.45) | T0 (57.10) | T0 (45.17) | T0 (55.29) |
| FCGEC | validation | T0 (25.58) | T0 (28.31) | T0 (31.84) | T0 (34.17) |
| NaCGEC | test | T0 (35.76) | T0 (37.35) | T0 (38.37) | T0 (39.39) |
| NaSGEC-Exam | test | T0 (33.29) | T0 (35.08) | T0 (38.13) | T0 (39.38) |
| CEFE Track 3 | validation | T0 (42.86) | T0 (47.92) | T0 (42.86) | T0 (47.33) |

## Main Findings

- Structured prompting is beneficial under character M2 F0.5 on most datasets, with the largest change generally occurring at T0 to T1.
- Additional WB-projection iterations produce small, dataset-dependent, and non-monotonic changes; the process usually converges by T3.
- Projection changes both split and merge boundaries and changes extracted M2 edits substantially enough to alter corpus scores.
- ChERRANT and projection M2 use exactly the same multi-reference setup; only character alignment and resulting edits differ.
- GLEU provides a complementary surface-similarity view and is more favorable to conservative outputs on several datasets.
- GLEU selected the fourth-or-later reference for **882 unique sentences**, confirming that all references were available to select-best.
- The large FlaCGEC projection delta and the small negative MuCGEC delta warrant qualitative alignment analysis before claiming that projection is universally more accurate.

## Verification

- 20,213 saved model outputs were reused; no evaluation rerun called the LLM.
- 38,000 gold references were retained.
- 118,852 projection M2 gold/prediction targets were reconstructed exactly from serialized S/A edits.
- 80,852 GLEU sentence-stage scores were audited and re-aggregated exactly.
- The GLEU CLI was cross-checked against the report runner after fixing the upstream character-tokenization scope bug.
- 35 repository tests passed after the GLEU integration.

## Historical FlaCGEC T0--T10 Diagnostic

The earlier direct ChERRANT run extended FlaCGEC to T10. It predates the uniform M2 regeneration, so it is useful only for iteration-depth diagnostics and should not replace the formal T0--T3 table above.

| Stage | Precision | Recall | F0.5 x100 |
| --- | --- | ---: | ---: |
| T0 | 45.85 | 44.98 | 45.67 |
| T1 | 49.59 | 38.06 | 46.76 |
| T2 | 49.75 | 38.06 | 46.87 |
| T3 | 49.64 | 38.27 | 46.86 |
| T4 | 49.70 | 38.14 | 46.86 |
| T5 | 49.67 | 38.27 | 46.88 |
| T6 | 49.75 | 38.23 | 46.92 |
| T7 | 49.67 | 38.23 | 46.87 |
| T8 | 49.78 | 38.23 | 46.94 |
| T9 | 49.67 | 38.23 | 46.87 |
| T10 | 49.78 | 38.23 | 46.94 |

The score plateaus after T2; T8/T10 are only 0.07 points above T2 in this historical evaluation. This supports an empirical iteration limit rather than monotonic improvement through T10.

## Full Stage-level Metrics

All M2 values and GLEU values below are multiplied by 100.

| Dataset | Stage | Ch F0.5 | Ch F1 | Ch F2 | Proj F0.5 | Proj F1 | Proj F2 | GLEU |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NLPCC2018 | T0 | 34.74 | 36.90 | 39.37 | 35.32 | 37.32 | 39.56 | 73.20 |
| NLPCC2018 | T1 | 40.40 | 36.80 | 33.79 | 40.93 | 36.95 | 33.67 | 70.66 |
| NLPCC2018 | T2 | 40.27 | 36.68 | 33.68 | 40.78 | 36.82 | 33.57 | 70.62 |
| NLPCC2018 | T3 | 40.23 | 36.71 | 33.76 | 40.73 | 36.85 | 33.64 | 70.63 |
| MuCGEC | T0 | 42.95 | 43.51 | 44.27 | 42.63 | 43.33 | 44.17 | 75.92 |
| MuCGEC | T1 | 49.84 | 42.98 | 37.86 | 49.54 | 42.76 | 37.68 | 74.36 |
| MuCGEC | T2 | 49.75 | 42.87 | 37.73 | 49.50 | 42.68 | 37.54 | 74.31 |
| MuCGEC | T3 | 49.73 | 42.91 | 37.81 | 49.46 | 42.70 | 37.63 | 74.37 |
| YACLC | T0 | 57.40 | 58.45 | 62.22 | 58.89 | 59.67 | 63.13 | 79.86 |
| YACLC | T1 | 63.37 | 59.51 | 58.02 | 63.72 | 59.73 | 58.14 | 81.44 |
| YACLC | T2 | 63.47 | 59.39 | 57.70 | 63.73 | 59.55 | 57.82 | 81.39 |
| YACLC | T3 | 63.42 | 59.42 | 57.82 | 63.72 | 59.60 | 57.91 | 81.42 |
| FlaCGEC | T0 | 45.74 | 45.45 | 45.17 | 59.03 | 57.10 | 55.29 | 84.13 |
| FlaCGEC | T1 | 46.83 | 43.11 | 39.93 | 59.91 | 54.33 | 49.70 | 80.94 |
| FlaCGEC | T2 | 46.95 | 43.17 | 39.95 | 60.10 | 54.43 | 49.74 | 80.92 |
| FlaCGEC | T3 | 46.94 | 43.26 | 40.12 | 60.08 | 54.53 | 49.92 | 81.03 |
| FCGEC | T0 | 21.38 | 25.58 | 31.84 | 24.17 | 28.31 | 34.17 | 91.77 |
| FCGEC | T1 | 24.96 | 24.60 | 24.25 | 26.80 | 25.71 | 24.71 | 92.76 |
| FCGEC | T2 | 25.07 | 24.63 | 24.22 | 26.99 | 25.79 | 24.70 | 92.78 |
| FCGEC | T3 | 24.99 | 24.62 | 24.26 | 26.86 | 25.75 | 24.72 | 92.77 |
| NaCGEC | T0 | 33.48 | 35.76 | 38.37 | 35.52 | 37.35 | 39.39 | 89.67 |
| NaCGEC | T1 | 33.06 | 29.45 | 26.55 | 34.53 | 30.05 | 26.59 | 88.91 |
| NaCGEC | T2 | 33.34 | 29.60 | 26.62 | 34.75 | 30.16 | 26.64 | 88.93 |
| NaCGEC | T3 | 33.14 | 29.50 | 26.58 | 34.59 | 30.10 | 26.63 | 88.92 |
| NaSGEC-Exam | T0 | 29.57 | 33.29 | 38.13 | 31.64 | 35.08 | 39.38 | 90.95 |
| NaSGEC-Exam | T1 | 33.32 | 30.26 | 27.73 | 35.13 | 31.40 | 28.38 | 91.27 |
| NaSGEC-Exam | T2 | 33.18 | 30.02 | 27.42 | 34.88 | 31.05 | 27.99 | 91.24 |
| NaSGEC-Exam | T3 | 33.49 | 30.38 | 27.80 | 35.14 | 31.36 | 28.32 | 91.27 |
| CEFE Track 3 | T0 | 42.86 | 42.86 | 42.86 | 48.52 | 47.92 | 47.33 | 82.74 |
| CEFE Track 3 | T1 | 44.12 | 40.54 | 37.50 | 44.97 | 40.48 | 36.80 | 81.00 |
| CEFE Track 3 | T2 | 44.12 | 40.54 | 37.50 | 44.97 | 40.48 | 36.80 | 81.00 |
| CEFE Track 3 | T3 | 44.12 | 40.54 | 37.50 | 44.97 | 40.48 | 36.80 | 81.00 |

## Source Artifacts

- Uniform ChERRANT M2: [`standardized_m2_eval/`](standardized_m2_eval/)
- All-reference versus first-three audit: [`standardized_m2_eval/scores.all_vs_first3.tsv`](standardized_m2_eval/scores.all_vs_first3.tsv)
- Projection M2 method and scores: [`projection_character_m2_eval/`](projection_character_m2_eval/)
- GLEU method and scores: [`character_gleu_select_best/`](character_gleu_select_best/)
- Pipeline diagnostics: [`scoreboard_t3_summary.tsv`](scoreboard_t3_summary.tsv)
- Projection alignment spot checks: [`projection_character_m2_eval/ALIGNMENT_SPOTCHECK.md`](projection_character_m2_eval/ALIGNMENT_SPOTCHECK.md)

## Superseded or Diagnostic Results

- `scoreboard_t3_summary.md` contains preliminary M2 values produced before uniform reference regeneration; use the formal ChERRANT table in this report instead.
- `projection_character_m2_eval_no_t2s_diagnostic/` intentionally omits target `t2s` normalization and is not a controlled paper result.
- `projection_character_m2_eval_pilot*/` and the 20-sentence Flash runs are smoke tests, not final evaluations.
