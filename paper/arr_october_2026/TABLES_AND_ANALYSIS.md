# ARR October 2026: Tables and Analysis

> **Historical word-GLEU notice:** The word-GLEU columns and associated
> secondary-metric intervals in this file use the earlier shared fixed-source
> policy. They are preserved as historical results, not relabelled. The
> approved 2026-09-19 policy uses S1/S1/S2/S3 for R/D/P/I; its
> [new two-model scores and paired intervals](KIMI_DEEPSEEK_REVISED_WORD_GLEU_20260919.md)
> and [complete four-metric report](KIMI_DEEPSEEK_FOUR_METRICS_REVISED_WORD_GLEU_20260919.md)
> supersede only word GLEU. Corrected M2, character GLEU, and primary inference
> below are unchanged.

> Numbering note: in the supplied PDF, dataset statistics are Table 2; Table 3 is the model and inference configuration. Both are completed below.

## Table 2. Dataset statistics

| Dataset | Split | Sentences | References | Multi-ref. | >3 refs. | Max refs. |
| --- | --- | --- | --- | --- | --- | --- |
| NLPCC2018 | Test | 2,000 | 2,183 | 183 | 0 | 2 |
| MuCGEC | Test | 6,000 | 13,119 | 4,268 | 557 | 8 |
| YACLC | Validation | 1,000 | 8,931 | 1,000 | 1,000 | 11 |
| FlaCGEC | Test | 1,325 | 1,325 | 0 | 0 | 1 |
| FCGEC | Validation | 2,000 | 2,550 | 351 | 47 | 8 |
| NaCGEC | Test | 5,869 | 6,978 | 1,083 | 4 | 5 |
| NaSGEC-Exam | Test | 2,000 | 2,895 | 819 | 5 | 4 |
| CEFE Track 3 | Validation | 19 | 19 | 0 | 0 | 1 |
| Total |  | 20,213 | 38,000 | 7,704 | 1,613 | 11 |

Statistics count complete textual references in `gold.para`. Multi-ref. is the number of source instances with more than one reference; `>3 refs.` counts instances with at least four references.

## Table 3. Model and inference configuration

This is the historical two-model configuration, also retained in
`table_3_model_configuration.tsv` and the compact `PAPER_TABLES.tex`.
The [current three-model parameters](kimi_deepseek_gpt56_call_parameters.tsv)
include the completed GPT-5.6 Sol experiment.

| Model | Identifier/version | Provider | Access date | Temperature | Top-p | Max output | Samples | Kmax |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DeepSeek | deepseek-v4-pro | DeepSeek | 2026-07-16 to 2026-07-19 | 0.000001 | provider default | 8,192 tokens (provider default; omitted) | 1 | 3 |
| Kimi | kimi-k2.6 | Moonshot AI | 2026-08-30 to 2026-08-31 | 0.6 (provider-fixed, non-thinking) | provider default | 512 tokens | 1 | 3 |

Each model produced one correction per source and condition. Thinking was disabled. DeepSeek used a near-zero temperature, whereas Kimi's non-thinking endpoint fixed temperature at 0.6; neither provider exposed a reproducible sampling seed. Thus the saved outputs are fixed for evaluation, but the original decoding should not be described as strictly deterministic.

Responses were normalized by removing code fences, known answer prefixes, trailing explanation sections, whitespace, and surrounding quotation marks. Empty, explicit self-analysis, or implausibly long responses were retried. Successful retries and Kimi content-filter identity fallbacks remain in the evaluation; no cases were removed after inspecting results. DeepSeek omitted `max_tokens`, so the provider's 8,192-token non-thinking default applied; its longest saved completion was 200 tokens. Kimi was capped at 512 output tokens, and its longest saved completion was 259 tokens. Neither model approached its output cap. `Kmax=3` denotes the last saved iterative stage T3.

## Primary paired-bootstrap results

Cells report the character-level micro-F0.5 difference in points and its paired 95% BCa interval. `E` means that the paired 90% BCa interval lies strictly inside the pre-defined +/-0.50-point equivalence region. CEFE Track 3 is descriptive only.

### DeepSeek

| Dataset | D-R | P-D | I-P |
| --- | --- | --- | --- |
| NLPCC2018 | +5.65 [+4.07, +7.25] | -0.11 [-0.42, +0.20] E | -0.05 [-0.25, +0.12] E |
| MuCGEC | +6.96 [+6.10, +7.81] | -0.03 [-0.22, +0.16] E | -0.03 [-0.14, +0.07] E |
| YACLC | +5.37 [+3.27, +7.41] | +0.09 [-0.48, +0.68] | -0.08 [-0.55, +0.29] E |
| FlaCGEC | +0.79 [-1.04, +2.57] | +0.17 [-0.41, +0.72] | -0.01 [-0.34, +0.35] E |
| FCGEC | +3.17 [+1.22, +5.15] | +0.16 [-0.18, +0.51] E | -0.10 [-0.42, +0.23] E |
| NaCGEC | +0.99 [-0.14, +2.09] | +0.28 [+0.11, +0.48] E | -0.20 [-0.37, -0.06] E |
| NaSGEC-Exam | +4.58 [+2.43, +6.73] | -0.24 [-0.91, +0.25] | +0.30 [-0.01, +0.83] |
| CEFE Track 3 | -3.31 [descriptive] | +0.00 [descriptive] | +0.00 [descriptive] |

### Kimi

| Dataset | D-R | P-D | I-P |
| --- | --- | --- | --- |
| NLPCC2018 | +0.07 [-1.39, +1.52] | -0.07 [-0.47, +0.28] E | +0.14 [-0.05, +0.40] E |
| MuCGEC | +0.94 [+0.09, +1.77] | +0.07 [-0.20, +0.42] E | -0.10 [-0.23, +0.02] E |
| YACLC | +0.71 [-1.19, +2.63] | -0.47 [-0.94, -0.08] | -0.01 [-0.25, +0.22] E |
| FlaCGEC | -2.54 [-4.14, -0.96] | +0.67 [+0.19, +1.20] | +0.05 [-0.24, +0.47] E |
| FCGEC | -3.08 [-4.41, -1.82] | +0.19 [-0.12, +0.67] | -0.15 [-0.67, +0.02] |
| NaCGEC | -5.27 [-6.09, -4.48] | +0.01 [-0.15, +0.18] E | +0.04 [-0.05, +0.15] E |
| NaSGEC-Exam | -5.10 [-6.66, -3.62] | -0.21 [-0.51, -0.02] E | +0.12 [-0.00, +0.40] E |
| CEFE Track 3 | -0.21 [descriptive] | -2.89 [descriptive] | +0.00 [descriptive] |

## Corrected absolute edit scores

These values use sentence-local select-best for both models and should replace edit-score rows computed with the historical order-dependent corpus-greedy reference selector.

| Model | Dataset | Char R | Char D | Char P | Char I | Word R | Word D | Word P | Word I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DeepSeek | NLPCC2018 | 34.22 | 39.87 | 39.76 | 39.72 | 33.19 | 37.78 | 37.70 | 37.71 |
| DeepSeek | MuCGEC | 41.21 | 48.17 | 48.14 | 48.11 | 41.01 | 47.02 | 46.97 | 47.00 |
| DeepSeek | YACLC | 57.59 | 62.96 | 63.05 | 62.97 | 59.17 | 64.74 | 64.74 | 64.73 |
| DeepSeek | FlaCGEC | 43.10 | 43.89 | 44.06 | 44.04 | 41.07 | 41.34 | 41.61 | 41.66 |
| DeepSeek | FCGEC | 20.46 | 23.63 | 23.79 | 23.69 | 17.91 | 19.69 | 19.76 | 19.69 |
| DeepSeek | NaCGEC | 31.76 | 32.75 | 33.03 | 32.83 | 29.69 | 28.87 | 29.10 | 28.92 |
| DeepSeek | NaSGEC-Exam | 29.32 | 33.90 | 33.66 | 33.95 | 28.71 | 32.01 | 32.15 | 32.34 |
| DeepSeek | CEFE Track 3 | 46.67 | 43.35 | 43.35 | 43.35 | 40.98 | 37.04 | 37.04 | 37.04 |
| Kimi | NLPCC2018 | 36.67 | 36.73 | 36.66 | 36.80 | 35.66 | 34.95 | 35.08 | 35.18 |
| Kimi | MuCGEC | 43.17 | 44.12 | 44.19 | 44.09 | 42.78 | 43.07 | 43.10 | 43.05 |
| Kimi | YACLC | 60.16 | 60.86 | 60.39 | 60.39 | 61.20 | 62.01 | 61.69 | 61.64 |
| Kimi | FlaCGEC | 34.71 | 32.17 | 32.84 | 32.89 | 31.98 | 29.97 | 30.60 | 30.60 |
| Kimi | FCGEC | 18.52 | 15.44 | 15.63 | 15.48 | 16.42 | 13.68 | 13.83 | 13.73 |
| Kimi | NaCGEC | 28.70 | 23.43 | 23.44 | 23.48 | 27.42 | 22.18 | 22.14 | 22.26 |
| Kimi | NaSGEC-Exam | 27.35 | 22.25 | 22.04 | 22.16 | 27.23 | 22.46 | 22.37 | 22.43 |
| Kimi | CEFE Track 3 | 40.67 | 40.46 | 37.57 | 37.57 | 33.73 | 33.65 | 31.25 | 31.25 |

## Absolute GLEU scores

GLEU is character- or word-ngram based and independently selects the highest-scoring complete reference for each sentence.

| Model | Dataset | Char R | Char D | Char P | Char I | Word R | Word D | Word P | Word I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DeepSeek | NLPCC2018 | 73.20 | 70.66 | 70.62 | 70.63 | 64.35 | 60.87 | 60.87 | 60.85 |
| DeepSeek | MuCGEC | 75.92 | 74.36 | 74.31 | 74.37 | 67.84 | 65.32 | 65.25 | 65.30 |
| DeepSeek | YACLC | 79.86 | 81.44 | 81.39 | 81.42 | 73.12 | 74.86 | 74.82 | 74.87 |
| DeepSeek | FlaCGEC | 84.13 | 80.94 | 80.92 | 81.03 | 77.68 | 73.28 | 73.34 | 73.40 |
| DeepSeek | FCGEC | 91.77 | 92.76 | 92.78 | 92.77 | 87.45 | 88.92 | 88.98 | 88.95 |
| DeepSeek | NaCGEC | 89.67 | 88.91 | 88.93 | 88.92 | 85.02 | 83.79 | 83.83 | 83.80 |
| DeepSeek | NaSGEC-Exam | 90.95 | 91.27 | 91.24 | 91.27 | 86.63 | 87.33 | 87.33 | 87.34 |
| DeepSeek | CEFE Track 3 | 82.74 | 81.00 | 81.00 | 81.00 | 75.95 | 71.35 | 71.35 | 71.35 |
| Kimi | NLPCC2018 | 73.01 | 70.54 | 70.41 | 70.47 | 63.74 | 60.30 | 60.18 | 60.24 |
| Kimi | MuCGEC | 75.54 | 73.13 | 73.07 | 73.09 | 67.13 | 63.52 | 63.45 | 63.45 |
| Kimi | YACLC | 81.22 | 80.42 | 80.18 | 80.19 | 74.35 | 73.29 | 73.06 | 73.04 |
| Kimi | FlaCGEC | 81.12 | 78.48 | 78.48 | 78.53 | 73.50 | 69.49 | 69.48 | 69.51 |
| Kimi | FCGEC | 90.95 | 90.81 | 90.86 | 90.85 | 86.34 | 86.14 | 86.21 | 86.20 |
| Kimi | NaCGEC | 88.99 | 87.13 | 87.15 | 87.16 | 83.99 | 81.11 | 81.13 | 81.15 |
| Kimi | NaSGEC-Exam | 90.43 | 89.40 | 89.40 | 89.40 | 85.89 | 84.38 | 84.40 | 84.38 |
| Kimi | CEFE Track 3 | 81.54 | 80.57 | 80.45 | 80.45 | 72.30 | 70.46 | 70.29 | 70.29 |

## Main findings

- Across the 28 formal P-D and I-P comparisons, 20 satisfy the +/-0.50-point practical-equivalence criterion and 23 exclude a gain of at least 0.50 points.
- The paired 95% BCa intervals show 2 projection/iteration improvements and 3 deteriorations; the remaining comparisons are directionally inconclusive.
- D-R measures the full effect of presenting word-boundary-aware input. P-D and I-P isolate the incremental effects of projected boundaries and another iteration, respectively.
- Results are estimated separately by model and dataset. CEFE Track 3 (n=19) is retained only as a descriptive diagnostic.
- Sentence resampling preserves pairing across all four conditions and metrics. Document/learner cluster identifiers were unavailable, so the intervals do not account for within-document dependence.
- Boundary-change subset analyses, proximity to fixed gold-informed boundaries, correction-span overlap, convergence, calls, and token totals are reported in the accompanying CSV files.

### Interpretation by model

- DeepSeek benefits clearly from Direct WB-aware prompting on NLPCC2018, MuCGEC, YACLC, FCGEC, and NaSGEC-Exam, but the projected and iterative stages are mostly equivalent to their preceding stages. The clearest later-stage exception is NaCGEC: P-D improves by 0.28 points, followed by a 0.20-point I-P deterioration.
- Kimi does not reproduce the broad Direct gains: D-R improves on MuCGEC, is inconclusive on NLPCC2018 and YACLC, and deteriorates on FlaCGEC, FCGEC, NaCGEC, and NaSGEC-Exam. Kimi FlaCGEC P-D is the main positive projection exception (+0.67 points; 95% BCa interval +0.19 to +1.20).
- Raw character GLEU is higher than Direct on 5/8 DeepSeek datasets and all 8/8 Kimi datasets. This metric-level disagreement with edit F0.5 supports reporting both correction accuracy and overall n-gram similarity rather than treating either metric as sufficient alone.

### Robustness check

- One primary directional conclusion is sensitive to interval construction: Kimi NaSGEC-Exam P-D (BCa -0.507 to -0.016; percentile -0.461 to +0.011). Both upper endpoints are near zero, so this should be described as a small, directionally fragile effect.
- 6 exploratory secondary-metric directional conclusions differ between BCa and percentile intervals; all are near-zero endpoint cases and are flagged in `bootstrap_secondary.csv`.
- 1 primary practical-equivalence conclusion is interval-sensitive: Kimi FCGEC I-P (BCa 90% -0.549 to +0.004; percentile 90% -0.400 to +0.040). The pre-specified BCa result is retained, but the boundary-margin conclusion should be described as fragile.

## Boundary intervention and cost

- DeepSeek P-D: normalized boundaries changed for 1,664/20,213 sources (8.23%); 527/1,664 changed-boundary sources produced a different correction (31.67%); 852 moved closer to and 790 moved farther from the fixed gold-informed boundaries. Correction-relevant gold spans covered 598/2,014 changed boundary positions (29.69%).
- DeepSeek I-P: normalized boundaries changed for 252/20,213 sources (1.25%); 212/252 changed-boundary sources produced a different correction (84.13%); 156 moved closer to and 93 moved farther from the fixed gold-informed boundaries. Correction-relevant gold spans covered 66/297 changed boundary positions (22.22%).
- DeepSeek required 1,918 projected/iterative calls beyond 20,213 Direct calls (9.49% extra) and recorded 4,973,097 tokens across Raw through Iterative. The saved metadata records 0 format retries and 0 content-filter identity fallbacks. The historical outputs contain 2 calls triggered only by whitespace formatting despite an unchanged normalized boundary vector; future runs now stop on the normalized signature.
- Kimi P-D: normalized boundaries changed for 1,723/20,213 sources (8.52%); 601/1,723 changed-boundary sources produced a different correction (34.88%); 861 moved closer to and 844 moved farther from the fixed gold-informed boundaries. Correction-relevant gold spans covered 638/2,034 changed boundary positions (31.37%).
- Kimi I-P: normalized boundaries changed for 294/20,213 sources (1.45%); 203/294 changed-boundary sources produced a different correction (69.05%); 175 moved closer to and 113 moved farther from the fixed gold-informed boundaries. Correction-relevant gold spans covered 81/353 changed boundary positions (22.95%).
- Kimi required 2,020 projected/iterative calls beyond 20,213 Direct calls (9.99% extra) and recorded 5,057,526 tokens across Raw through Iterative. The saved metadata records 28 format retries and 146 content-filter identity fallbacks. The historical outputs contain 3 calls triggered only by whitespace formatting despite an unchanged normalized boundary vector; future runs now stop on the normalized signature.

## Reproducibility and interpretation

The primary outcome is corpus micro-F0.5, recomputed from pooled TP/FP/FN in every resample rather than averaging sentence F-scores. Character and word GLEU select the best complete reference independently at sentence level and are secondary outcomes. A confidence interval crossing zero is not described as evidence of no difference; equivalence is claimed only from the 90% interval and the frozen practical margin.

The fixed evaluation-side segmentations are gold-informed proxies, not manually annotated gold word boundaries. Changed-boundary analyses are diagnostic because their subset is selected by the intervention. API-call randomness is not represented because only one decoded output exists for each condition.

## Files

Only the compact dataset/model tables below are shared alongside this report.
The remaining original exports and logs are local-only under
`runs/paired_bootstrap_analysis/`, not files supplied by a public clone.
Selected current statistics are published with the three-model reports.

- `table_2_dataset_statistics.tsv`: verified dataset counts.
- `table_3_model_configuration.tsv`: model and decoding configuration.
- `sentence_level_scores.tsv`: per-model, per-source, per-condition counts and scores.
- `bootstrap_primary.csv`: character F0.5 contrasts and BCa intervals.
- `bootstrap_secondary.csv`: word F0.5 and character/word GLEU intervals.
- `equivalence_sensitivity.csv`: +/-0.25, +/-0.50, and +/-1.00 analyses.
- `changed_boundary_diagnostics.csv`: intervention coverage and alignment diagnostics.
- `convergence_and_cost.csv`: stopping, calls, tokens, and efficiency.
- `scorer_selection_audit.tsv`: sentence-local versus legacy corpus-greedy selection.
- `validation.log`: integrity and reproducibility checks.
