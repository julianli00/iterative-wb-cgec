# Kimi and DeepSeek: revised word GLEU (protocol 2026-09-19)

**Computed offline on 2026-09-20 from the 16 authoritative final JSONL files. These are new condition-source results, not relabelled historical fixed-source scores. No new LLM calls, prediction regeneration, LTP inference, or downloads were made.**

R/Raw/T0 and D/Direct/T1 use saved S1; P/Projected/T2 uses saved S2; I/Iterative/T3 uses saved S3. Hypotheses and every complete reference use the unchanged LTP 4.2.14 cache. Word 1-4-gram GLEU independently selects the highest-scoring complete reference for each sentence, then macro-averages and multiplies by 100. Normalization removes BOM/whitespace only: no BPE, OpenCC, reference merging, reordering, or dropping.

## DeepSeek

| Dataset | R / T0 | D / T1 | P / T2 | I / T3 |
| --- | --- | --- | --- | --- |
| NLPCC2018 | 63.86 | 60.07 | 59.93 | 59.89 |
| MuCGEC | 67.54 | 64.73 | 64.48 | 64.50 |
| YACLC | 73.07 | 74.54 | 74.38 | 74.35 |
| FlaCGEC | 77.30 | 72.78 | 72.48 | 72.51 |
| FCGEC | 87.27 | 88.57 | 88.39 | 88.36 |
| NaCGEC | 84.71 | 83.20 | 83.06 | 83.01 |
| NaSGEC-Exam | 86.40 | 86.95 | 86.81 | 86.81 |
| CEFE Track 3 | 74.31 | 68.67 | 68.59 | 68.59 |

## Kimi

| Dataset | R / T0 | D / T1 | P / T2 | I / T3 |
| --- | --- | --- | --- | --- |
| NLPCC2018 | 63.31 | 59.53 | 59.31 | 59.30 |
| MuCGEC | 66.70 | 62.96 | 62.71 | 62.65 |
| YACLC | 74.15 | 73.06 | 72.73 | 72.57 |
| FlaCGEC | 73.11 | 68.94 | 68.57 | 68.57 |
| FCGEC | 86.12 | 85.83 | 85.66 | 85.63 |
| NaCGEC | 83.70 | 80.58 | 80.44 | 80.43 |
| NaSGEC-Exam | 85.73 | 84.11 | 83.93 | 83.89 |
| CEFE Track 3 | 70.55 | 68.64 | 68.05 | 68.05 |

## Paired word-GLEU contrasts

Entries are later-minus-earlier points with paired 95% BCa intervals. The CSV also contains 90% BCa and ordinary 95%/90% percentile intervals. There are 50,000 paired source-sentence replicates per model/dataset, seed `20260915`, chunk size `1000`, using the unmodified existing statistical helpers and their model/dataset-specific stable seed derivation. CEFE (n=19) is descriptive only.

### DeepSeek

| Dataset | D-R | P-D | I-P |
| --- | --- | --- | --- |
| NLPCC2018 | -3.79 [-4.89, -2.71] | -0.14 [-0.36, +0.05] | -0.03 [-0.15, +0.09] |
| MuCGEC | -2.81 [-3.41, -2.23] | -0.25 [-0.36, -0.14] | +0.02 [-0.05, +0.09] |
| YACLC | +1.46 [+0.02, +2.82] | -0.16 [-0.53, +0.11] | -0.03 [-0.28, +0.31] |
| FlaCGEC | -4.52 [-5.67, -3.45] | -0.30 [-0.50, -0.09] | +0.03 [-0.12, +0.15] |
| FCGEC | +1.30 [+0.78, +1.78] | -0.18 [-0.27, -0.09] | -0.03 [-0.09, +0.02] |
| NaCGEC | -1.51 [-1.83, -1.19] | -0.14 [-0.19, -0.09] | -0.04 [-0.08, -0.01] |
| NaSGEC-Exam | +0.55 [+0.03, +1.06] | -0.14 [-0.25, -0.05] | -0.00 [-0.06, +0.07] |
| CEFE Track 3 | -5.64 (descriptive) | -0.08 (descriptive) | +0.00 (descriptive) |

### Kimi

| Dataset | D-R | P-D | I-P |
| --- | --- | --- | --- |
| NLPCC2018 | -3.78 [-4.78, -2.80] | -0.22 [-0.44, -0.02] | -0.01 [-0.13, +0.11] |
| MuCGEC | -3.74 [-4.26, -3.21] | -0.25 [-0.36, -0.15] | -0.06 [-0.12, -0.01] |
| YACLC | -1.08 [-2.41, +0.23] | -0.33 [-0.79, -0.02] * | -0.16 [-0.34, -0.01] |
| FlaCGEC | -4.17 [-5.25, -3.13] | -0.36 [-0.63, -0.12] | -0.01 [-0.24, +0.15] |
| FCGEC | -0.29 [-0.78, +0.18] | -0.17 [-0.27, -0.06] | -0.03 [-0.09, +0.02] |
| NaCGEC | -3.13 [-3.45, -2.80] | -0.14 [-0.21, -0.07] | -0.01 [-0.05, +0.04] |
| NaSGEC-Exam | -1.62 [-2.16, -1.12] | -0.18 [-0.27, -0.09] | -0.03 [-0.08, +0.01] |
| CEFE Track 3 | -1.90 (descriptive) | -0.59 (descriptive) | +0.00 (descriptive) |

Across the 28 formal P-D/I-P word-GLEU contrasts, the pointwise 95% BCa intervals show 0 improvements, 15 deteriorations, and 13 inconclusive differences. These are exploratory secondary-metric comparisons without a multiple-comparison correction, not a replacement for the primary character M2 analysis.

* Interval-sensitive result: Kimi YACLC P-D (-0.329); BCa 95% [-0.788, -0.016], percentile 95% [-0.726, +0.025]. The near-zero endpoint makes the directional claim fragile.

## Interpretation and unchanged metrics

**Changing source boundaries can change word GLEU even when the correction is identical.** This occurs in 918 saved sentence-transition instances (including descriptive CEFE), so P-D/I-P word-GLEU differences must not be attributed solely to changed corrected text or treated as source-invariant accuracy changes.

| Model | Contrast | Unchanged correction, changed word GLEU |
| --- | --- | --- |
| DeepSeek | P-D | 421 |
| DeepSeek | I-P | 20 |
| Kimi | P-D | 435 |
| Kimi | I-P | 42 |

Character M2, word M2, and character GLEU are unchanged. The complete four-metric report reuses the already corrected sentence-local M2 counts, not the legacy corpus-greedy tables. Word M2 still uses one shared fixed gold-informed source segmentation across T0-T3; both movement thresholds remain 3, and a linked U-M movement is scored once as WO. The previous character-primary conclusions and all 144 contrast rows for the three unchanged metrics were reproduced, including their BCa/percentile intervals.

## Integrity and lineage

All 16 JSONL files are readable and contain 40,426 successful records in total (20,213 per model), aligned by ID and learner text with 38,000 complete references per model. S1-S3 preserve every learner character. The DeepSeek FlaCGEC T10-named file contributes only T0-T3; DeepSeek NaSGEC-Exam uses the `_bpe_fixed` JSONL. JSONL supplies every evaluated prediction/boundary; same-named TSVs were checked only for historical artifact lineage and were never evaluation inputs.

All 161,704 word-GLEU sentence-condition scores were independently recomputed against the exact persisted source/hypothesis/complete-reference files; reference counts and order match. The unchanged metrics were traced through 323,408 hypothesis M2 blocks and 202,130 reference M2 blocks containing 380,000 serialized complete references. All 77,249 unique hypothesis/reference texts were already in the read-only LTP cache.

SHA256 hashes of all originals and 1,324 protected files (including historical results, fixed boundaries, the LTP cache, and original evaluator scripts) remain unchanged. Historical whitespace-only extra calls (DeepSeek 2; Kimi 3) and all saved carry-forward outputs were retained verbatim. No convergence decisions were rerun.

Focused checks passed: 11 JSONL/read-only-cache adapter tests and 14 archived protocol/evaluator tests. The full current-checkout suite passed all 73 tests (98 total across the three runs). Original tracked evaluator code and git HEAD were not changed; no commit or push was made.

## Files and reproduction

- [Complete four-metric report](KIMI_DEEPSEEK_FOUR_METRICS_REVISED_WORD_GLEU_20260919.md) and [full-precision four-metric TSV](four_metrics_condition_word_gleu_20260919.tsv).
- [Full-precision revised word-GLEU table](word_gleu_condition_20260919.tsv).
- [Word-GLEU paired bootstrap CSV](word_gleu_condition_paired_bootstrap_20260919.csv) (42 inferential and 6 descriptive contrasts).
- [Exact authoritative inputs and SHA256](word_gleu_condition_input_manifest_20260919.json) and [validation summary](word_gleu_condition_validation_20260919.json).
- Private DeepSeek scores, sentence scores, and exact inputs: `runs/word_gleu_condition_select_best/`.
- Private Kimi scores, sentence scores, and exact inputs: `runs/kimi_k2_6/word_gleu_condition/`.
- Reproducible adapters, unmodified helper snapshot, frozen hashes, logs, revised all-metric sentence export, and bootstrap draws: `runs/word_gleu_revision_20260919/`.

The task-local evaluator is the exact two-file snapshot from git object `3bf47ca`, with only runtime JSONL-loader/read-only-cache adapters. The existing statistical helper is from main at `caa41fd`. GLEU is the locally archived `d550c76dd66228eb2c05b197efc49040a2dafe37` implementation with its documented global tokenization/cache fix. No other worktree was accessed and no branch was merged or checked out.

Run in the original local checkout, which contains the ignored JSONL/cache artifacts:

```bash
PY=/path/to/compatible/python
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
"$PY" runs/word_gleu_revision_20260919/evaluate_revision.py audit
"$PY" runs/word_gleu_revision_20260919/evaluate_revision.py evaluate
"$PY" runs/word_gleu_revision_20260919/evaluate_revision.py verify
"$PY" runs/word_gleu_revision_20260919/analyze_revision.py
"$PY" runs/word_gleu_revision_20260919/publish_revision.py
```

The original fixed-source word-GLEU roots and summaries remain historical and must not be mixed with this revision. The task-local driver and large artifacts are intentionally ignored, so a fresh clone alone is not sufficient to reproduce this package.

## Remaining limitations

CEFE has only 19 public validation examples. YACLC and FCGEC are validation splits, not hidden-test leaderboard submissions. Source-level resampling cannot account for unavailable document/learner clusters, and one saved decode per condition cannot estimate API sampling variability. The source-dependent word-GLEU effect and the interval-sensitive Kimi YACLC P-D result above must be retained in interpretation. No outstanding evaluation or statistical computation remains for these two models.
