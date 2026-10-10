# Kimi and DeepSeek: complete four-metric results

**Word GLEU uses the revised 2026-09-19 condition-source policy (S1/S1/S2/S3). All other values are unchanged corrected results. All scores are on the 0-100 scale.**

See [KIMI_DEEPSEEK_REVISED_WORD_GLEU_20260919.md](KIMI_DEEPSEEK_REVISED_WORD_GLEU_20260919.md) for exact inputs, word-GLEU intervals, validation, and limitations. R/D/P/I correspond to T0/T1/T2/T3. CEFE is descriptive only.

Character and word M2 are sentence-local select-best corpus micro-F0.5 with projection-derived edits; linked U-M movement is counted once as WO, thresholds are 3, and word M2 keeps the shared fixed gold-informed source boundaries. Character GLEU is character-by-character. Both GLEU metrics select the highest-scoring complete reference per sentence and macro-average. No BPE or OpenCC is used.

## DeepSeek

| Dataset | Metric | R / T0 | D / T1 | P / T2 | I / T3 |
| --- | --- | --- | --- | --- | --- |
| NLPCC2018 | Character M2 F0.5 | 34.22 | 39.87 | 39.76 | 39.72 |
| NLPCC2018 | Word M2 F0.5 | 33.19 | 37.78 | 37.70 | 37.71 |
| NLPCC2018 | Character GLEU | 73.20 | 70.66 | 70.62 | 70.63 |
| NLPCC2018 | Word GLEU (revised) | 63.86 | 60.07 | 59.93 | 59.89 |
| MuCGEC | Character M2 F0.5 | 41.21 | 48.17 | 48.14 | 48.11 |
| MuCGEC | Word M2 F0.5 | 41.01 | 47.02 | 46.97 | 47.00 |
| MuCGEC | Character GLEU | 75.92 | 74.36 | 74.31 | 74.37 |
| MuCGEC | Word GLEU (revised) | 67.54 | 64.73 | 64.48 | 64.50 |
| YACLC | Character M2 F0.5 | 57.59 | 62.96 | 63.05 | 62.97 |
| YACLC | Word M2 F0.5 | 59.17 | 64.74 | 64.74 | 64.73 |
| YACLC | Character GLEU | 79.86 | 81.44 | 81.39 | 81.42 |
| YACLC | Word GLEU (revised) | 73.07 | 74.54 | 74.38 | 74.35 |
| FlaCGEC | Character M2 F0.5 | 43.10 | 43.89 | 44.06 | 44.04 |
| FlaCGEC | Word M2 F0.5 | 41.07 | 41.34 | 41.61 | 41.66 |
| FlaCGEC | Character GLEU | 84.13 | 80.94 | 80.92 | 81.03 |
| FlaCGEC | Word GLEU (revised) | 77.30 | 72.78 | 72.48 | 72.51 |
| FCGEC | Character M2 F0.5 | 20.46 | 23.63 | 23.79 | 23.69 |
| FCGEC | Word M2 F0.5 | 17.91 | 19.69 | 19.76 | 19.69 |
| FCGEC | Character GLEU | 91.77 | 92.76 | 92.78 | 92.77 |
| FCGEC | Word GLEU (revised) | 87.27 | 88.57 | 88.39 | 88.36 |
| NaCGEC | Character M2 F0.5 | 31.76 | 32.75 | 33.03 | 32.83 |
| NaCGEC | Word M2 F0.5 | 29.69 | 28.87 | 29.10 | 28.92 |
| NaCGEC | Character GLEU | 89.67 | 88.91 | 88.93 | 88.92 |
| NaCGEC | Word GLEU (revised) | 84.71 | 83.20 | 83.06 | 83.01 |
| NaSGEC-Exam | Character M2 F0.5 | 29.32 | 33.90 | 33.66 | 33.95 |
| NaSGEC-Exam | Word M2 F0.5 | 28.71 | 32.01 | 32.15 | 32.34 |
| NaSGEC-Exam | Character GLEU | 90.95 | 91.27 | 91.24 | 91.27 |
| NaSGEC-Exam | Word GLEU (revised) | 86.40 | 86.95 | 86.81 | 86.81 |
| CEFE Track 3 | Character M2 F0.5 | 46.67 | 43.35 | 43.35 | 43.35 |
| CEFE Track 3 | Word M2 F0.5 | 40.98 | 37.04 | 37.04 | 37.04 |
| CEFE Track 3 | Character GLEU | 82.74 | 81.00 | 81.00 | 81.00 |
| CEFE Track 3 | Word GLEU (revised) | 74.31 | 68.67 | 68.59 | 68.59 |

## Kimi

| Dataset | Metric | R / T0 | D / T1 | P / T2 | I / T3 |
| --- | --- | --- | --- | --- | --- |
| NLPCC2018 | Character M2 F0.5 | 36.67 | 36.73 | 36.66 | 36.80 |
| NLPCC2018 | Word M2 F0.5 | 35.66 | 34.95 | 35.08 | 35.18 |
| NLPCC2018 | Character GLEU | 73.01 | 70.54 | 70.41 | 70.47 |
| NLPCC2018 | Word GLEU (revised) | 63.31 | 59.53 | 59.31 | 59.30 |
| MuCGEC | Character M2 F0.5 | 43.17 | 44.12 | 44.19 | 44.09 |
| MuCGEC | Word M2 F0.5 | 42.78 | 43.07 | 43.10 | 43.05 |
| MuCGEC | Character GLEU | 75.54 | 73.13 | 73.07 | 73.09 |
| MuCGEC | Word GLEU (revised) | 66.70 | 62.96 | 62.71 | 62.65 |
| YACLC | Character M2 F0.5 | 60.16 | 60.86 | 60.39 | 60.39 |
| YACLC | Word M2 F0.5 | 61.20 | 62.01 | 61.69 | 61.64 |
| YACLC | Character GLEU | 81.22 | 80.42 | 80.18 | 80.19 |
| YACLC | Word GLEU (revised) | 74.15 | 73.06 | 72.73 | 72.57 |
| FlaCGEC | Character M2 F0.5 | 34.71 | 32.17 | 32.84 | 32.89 |
| FlaCGEC | Word M2 F0.5 | 31.98 | 29.97 | 30.60 | 30.60 |
| FlaCGEC | Character GLEU | 81.12 | 78.48 | 78.48 | 78.53 |
| FlaCGEC | Word GLEU (revised) | 73.11 | 68.94 | 68.57 | 68.57 |
| FCGEC | Character M2 F0.5 | 18.52 | 15.44 | 15.63 | 15.48 |
| FCGEC | Word M2 F0.5 | 16.42 | 13.68 | 13.83 | 13.73 |
| FCGEC | Character GLEU | 90.95 | 90.81 | 90.86 | 90.85 |
| FCGEC | Word GLEU (revised) | 86.12 | 85.83 | 85.66 | 85.63 |
| NaCGEC | Character M2 F0.5 | 28.70 | 23.43 | 23.44 | 23.48 |
| NaCGEC | Word M2 F0.5 | 27.42 | 22.18 | 22.14 | 22.26 |
| NaCGEC | Character GLEU | 88.99 | 87.13 | 87.15 | 87.16 |
| NaCGEC | Word GLEU (revised) | 83.70 | 80.58 | 80.44 | 80.43 |
| NaSGEC-Exam | Character M2 F0.5 | 27.35 | 22.25 | 22.04 | 22.16 |
| NaSGEC-Exam | Word M2 F0.5 | 27.23 | 22.46 | 22.37 | 22.43 |
| NaSGEC-Exam | Character GLEU | 90.43 | 89.40 | 89.40 | 89.40 |
| NaSGEC-Exam | Word GLEU (revised) | 85.73 | 84.11 | 83.93 | 83.89 |
| CEFE Track 3 | Character M2 F0.5 | 40.67 | 40.46 | 37.57 | 37.57 |
| CEFE Track 3 | Word M2 F0.5 | 33.73 | 33.65 | 31.25 | 31.25 |
| CEFE Track 3 | Character GLEU | 81.54 | 80.57 | 80.45 | 80.45 |
| CEFE Track 3 | Word GLEU (revised) | 70.55 | 68.64 | 68.05 | 68.05 |

## Provenance

The 128 M2 cells reuse the corrected per-sentence TP/FP/FN in `runs/paired_bootstrap_analysis/sentence_level_scores.tsv` and reproduce its sentence-local selector audit. They do not come from the legacy corpus-greedy `projection_*_m2/scores.long.tsv` summaries. The 64 character-GLEU cells reuse the same validated character inputs and scores. Only the 64 word-GLEU cells are replaced by the new condition-source evaluation.

Machine-readable, full-precision values: [four_metrics_condition_word_gleu_20260919.tsv](four_metrics_condition_word_gleu_20260919.tsv). All 144 existing contrast rows for the unchanged metrics reproduce with the identical 50,000 paired draws, seed, chunk size, and BCa/percentile interval helpers. The primary character M2 findings are therefore unchanged.

Historical fixed-source word-GLEU tables remain archived separately. **Zero new model calls; original JSONL hashes unchanged.**
