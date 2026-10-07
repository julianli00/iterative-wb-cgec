# Configured-model paired-bootstrap analysis

Models analyzed: GPT-5.6 Sol (none).
This report describes only the configured saved runs, not a comparison against unprovided historical runs. Frozen historical-model invariants are **SKIPPED**, not passed; reference, cache, coverage, and carry-forward checks still apply to every configured run.

## Dataset statistics

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

Counts include every complete textual reference in `gold.para`; no source instances or references are removed after inspecting results. See [the shared dataset table](../table_2_dataset_statistics.tsv) for totals.

## Model and inference configuration

| Model | Identifier/version | Provider | Access date | Temperature | Top-p | Max output | Reasoning/thinking | Samples | Kmax | Cached edit selector | Word GLEU source policy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GPT-5.6 Sol (none) | gpt-5.6-sol | GitHub Copilot (OpenAI) | 2026-09-20 to 2026-09-21 (UTC) | provider default (omitted; not claimed to be minimum) | provider default (omitted) | provider default; capability override empirically ignored in the interface probe | disabled; requested and reported none; reasoning tokens verified zero | 1 | 3 | sentence | condition |

These are the declared generation settings, not settings inferred from score tables. Provider-default settings are not claims of disabled reasoning, deterministic decoding, a known numeric sampling value, or a verified output cap. One saved output is evaluated per source and condition; Kmax=3 denotes the last saved stage T3. Analysis reuses R/T0 (Raw), D/T1 (Direct), P/T2 (Projected), and I/T3 (Iterative) and makes no model/API calls.

## Statistical protocol

Each model-dataset block uses 50,000 paired source-level bootstrap replicates, base seed 20260915, and chunk size 1,000. Stable model/dataset-specific seeds are derived from this base seed. The same sampled source weights are shared across conditions and metrics within a block. The primary outcome is projection-based character micro-F0.5, recomputed from pooled TP/FP/FN in every resample, not an average of sentence F-scores. Estimation uses 95% BCa intervals; P-D and I-P equivalence requires the 90% BCa interval strictly inside +/-0.50 points, with +/-0.25 and +/-1.00 sensitivity analyses. All scores and differences are on the 0--100 scale.

Inferential datasets: NLPCC2018, MuCGEC, YACLC, FlaCGEC, FCGEC, NaCGEC, NaSGEC-Exam.
Descriptive only: CEFE Track 3 (n=19); no bootstrap intervals or equivalence decisions are reported for these datasets, including boundary subsets.

Edit references are selected independently by sentence using the highest unrounded F0.5 (ties: more TP, fewer FP, fewer FN, then first annotator order). The configured cached selector is only a cache-validation policy: both corpus-greedy and sentence-local scores are audited, but all primary and secondary edit estimates use sentence-local counts. Character and word GLEU independently select the highest-scoring complete reference per sentence. This script reads and validates saved GLEU scores; it does not retokenize them.

## Word GLEU source policy

| Model | Word GLEU policy | R/T0 source | D/T1 source | P/T2 source | I/T3 source |
| --- | --- | --- | --- | --- | --- |
| GPT-5.6 Sol (none) | condition | S1 | S1 | S2 | S3 |

Condition-specific word GLEU uses saved direct LTP S1 for both R/T0 and D/T1, saved S2 for P/T2, and saved S3 for I/T3. `fixed-gold` is explicit historical reproduction using one shared gold-informed source segmentation at all stages.

Word-GLEU hypotheses and complete references remain LTP-segmented. Character GLEU and both M2 metrics are unchanged: word M2 still uses shared fixed gold-informed source boundaries, validated independently of the word-GLEU policy. Analysis does not retokenize inputs.

Word GLEU depends on source n-grams: a difference can arise from source segmentation even with an identical hypothesis. Values from condition and fixed-gold policies are not interchangeable. Completion metadata, row policy labels, and exported source boundaries are checked in `word_gleu_source_audit.tsv`; identifiable legacy fixed-gold metadata is accepted only when explicitly selected.

## Primary character micro-F0.5 contrasts

Each cell is a difference in points with its paired 95% BCa interval. `E` denotes the separate 90% BCa practical-equivalence decision at +/-0.50. An interval containing zero is inconclusive, not evidence of no difference. Intervals are per-comparison; no multiple-comparison adjustment is applied.

### GPT-5.6 Sol (none)

| Dataset | N | D-R | P-D | I-P |
| --- | --- | --- | --- | --- |
| NLPCC2018 | 2000 | +3.30 [+2.29, +4.33] | +0.11 [-0.29, +0.48] E | -0.07 [-0.27, +0.14] E |
| MuCGEC | 6000 | +4.40 [+3.84, +4.95] | -0.13 [-0.36, +0.09] E | -0.01 [-0.14, +0.13] E |
| YACLC | 1000 | +2.91 [+1.42, +4.40] | +0.05 [-0.40, +0.58] E | -0.25 [-0.66, +0.01] |
| FlaCGEC | 1325 | +0.70 [-0.85, +2.23] | +0.41 [-0.09, +1.03] | -0.19 [-0.47, +0.01] E |
| FCGEC | 2000 | +3.09 [+2.08, +4.10] | +0.37 [+0.05, +0.95] | -0.37 [-0.86, -0.15] |
| NaCGEC | 5869 | +2.21 [+1.55, +2.88] | +0.05 [-0.12, +0.22] E | -0.08 [-0.19, +0.04] E |
| NaSGEC-Exam | 2000 | +4.16 [+2.92, +5.42] | +0.37 [-0.02, +0.82] | -0.16 [-0.40, +0.02] E |
| CEFE Track 3 | 19 | -4.16 [descriptive] | -0.47 [descriptive] | -0.46 [descriptive] |

## Computed primary findings

| Model | Contrast | Comparisons | 95% improvement | 95% deterioration | 95% inconclusive | Equivalent +/-0.50 | Gain >=0.50 excluded |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GPT-5.6 Sol (none) | D-R | 7 | 6 | 0 | 1 | not tested | not tested |
| GPT-5.6 Sol (none) | P-D | 7 | 1 | 0 | 6 | 4 | 4 |
| GPT-5.6 Sol (none) | I-P | 7 | 0 | 1 | 6 | 5 | 7 |

D-R estimates the effect of presenting word-boundary-aware input. P-D and I-P estimate incremental projection and iteration effects. These counts summarize separate within-dataset comparisons; they are not a pooled effect or a test of between-model differences. Directional evidence and practical equivalence are not mutually exclusive. Excluding a meaningful gain does not establish equivalence if harm remains plausible.

## Absolute sentence-local edit scores

| Model | Dataset | Word source policy | Char R | Char D | Char P | Char I | Word R | Word D | Word P | Word I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GPT-5.6 Sol (none) | NLPCC2018 | fixed-gold | 29.45 | 32.75 | 32.86 | 32.79 | 29.15 | 32.39 | 32.55 | 32.43 |
| GPT-5.6 Sol (none) | MuCGEC | fixed-gold | 36.33 | 40.73 | 40.59 | 40.58 | 36.55 | 40.81 | 40.88 | 40.84 |
| GPT-5.6 Sol (none) | YACLC | fixed-gold | 55.02 | 57.93 | 57.99 | 57.73 | 55.92 | 58.90 | 58.74 | 58.57 |
| GPT-5.6 Sol (none) | FlaCGEC | fixed-gold | 39.23 | 39.94 | 40.35 | 40.16 | 38.20 | 38.45 | 38.75 | 38.68 |
| GPT-5.6 Sol (none) | FCGEC | fixed-gold | 14.13 | 17.22 | 17.59 | 17.22 | 12.54 | 15.19 | 15.84 | 15.43 |
| GPT-5.6 Sol (none) | NaCGEC | fixed-gold | 24.62 | 26.83 | 26.88 | 26.80 | 23.21 | 25.18 | 25.46 | 25.30 |
| GPT-5.6 Sol (none) | NaSGEC-Exam | fixed-gold | 21.93 | 26.09 | 26.46 | 26.30 | 22.09 | 25.12 | 25.70 | 25.48 |
| GPT-5.6 Sol (none) | CEFE Track 3 | fixed-gold | 39.51 | 35.35 | 34.88 | 34.43 | 32.89 | 31.25 | 31.25 | 30.17 |

## Absolute GLEU scores

| Model | Dataset | Word source policy | Char R | Char D | Char P | Char I | Word R | Word D | Word P | Word I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GPT-5.6 Sol (none) | NLPCC2018 | condition | 72.11 | 73.32 | 73.32 | 73.28 | 62.46 | 64.05 | 63.98 | 63.82 |
| GPT-5.6 Sol (none) | MuCGEC | condition | 74.95 | 76.49 | 76.51 | 76.51 | 66.47 | 68.18 | 68.06 | 68.04 |
| GPT-5.6 Sol (none) | YACLC | condition | 78.53 | 80.09 | 80.15 | 80.07 | 71.22 | 72.77 | 72.74 | 72.60 |
| GPT-5.6 Sol (none) | FlaCGEC | condition | 84.53 | 84.35 | 84.34 | 84.34 | 77.81 | 77.52 | 77.14 | 77.11 |
| GPT-5.6 Sol (none) | FCGEC | condition | 88.36 | 90.62 | 90.72 | 90.66 | 82.09 | 85.34 | 85.22 | 85.04 |
| GPT-5.6 Sol (none) | NaCGEC | condition | 87.50 | 88.16 | 88.16 | 88.14 | 81.32 | 82.17 | 81.93 | 81.86 |
| GPT-5.6 Sol (none) | NaSGEC-Exam | condition | 88.54 | 90.13 | 90.18 | 90.16 | 82.92 | 85.07 | 84.98 | 84.88 |
| GPT-5.6 Sol (none) | CEFE Track 3 | condition | 80.58 | 81.64 | 81.23 | 81.32 | 69.78 | 71.54 | 70.98 | 70.65 |

## Exploratory secondary outcomes

| Model | Metric | Source policy | Contrast | Comparisons | 95% improvement | 95% deterioration | 95% inconclusive |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GPT-5.6 Sol (none) | word_f05 | fixed-gold | D-R | 7 | 6 | 0 | 1 |
| GPT-5.6 Sol (none) | word_f05 | fixed-gold | P-D | 7 | 3 | 0 | 4 |
| GPT-5.6 Sol (none) | word_f05 | fixed-gold | I-P | 7 | 0 | 2 | 5 |
| GPT-5.6 Sol (none) | character_gleu | character | D-R | 7 | 6 | 0 | 1 |
| GPT-5.6 Sol (none) | character_gleu | character | P-D | 7 | 1 | 0 | 6 |
| GPT-5.6 Sol (none) | character_gleu | character | I-P | 7 | 0 | 1 | 6 |
| GPT-5.6 Sol (none) | word_gleu | condition | D-R | 7 | 6 | 0 | 1 |
| GPT-5.6 Sol (none) | word_gleu | condition | P-D | 7 | 0 | 2 | 5 |
| GPT-5.6 Sol (none) | word_gleu | condition | I-P | 7 | 0 | 4 | 3 |

Full effect estimates and intervals are in `bootstrap_secondary.csv`; these metrics do not replace the pre-specified primary outcome.

## Equivalence sensitivity and interval robustness

| Model | Margin | P-D/I-P comparisons | Equivalent | Meaningful gain excluded |
| --- | --- | --- | --- | --- |
| GPT-5.6 Sol (none) | +/-0.25 | 14 | 4 | 9 |
| GPT-5.6 Sol (none) | +/-0.50 | 14 | 9 | 11 |
| GPT-5.6 Sol (none) | +/-1.00 | 14 | 14 | 14 |

Counts of conclusions that differ between BCa and ordinary percentile intervals:

| Model | Primary direction | Primary equivalence | Secondary direction |
| --- | --- | --- | --- |
| GPT-5.6 Sol (none) | 1 | 0 | 0 |

BCa remains the pre-specified analysis. Flagged comparisons and both interval endpoints are retained in the bootstrap CSV files; sensitivity to interval construction should be considered when interpreting those comparisons.

## Boundary intervention and recorded calls

- GPT-5.6 Sol (none) P-D: normalized boundaries changed for 2,511/20,213 (12.42%) sources; corrections changed for 1,362/2,511 (54.24%) of those sources. 1,073 moved closer to and 1,390 farther from fixed gold-informed boundaries. Correction-relevant spans overlapped 744/3,019 (24.64%) changed boundary positions.
- GPT-5.6 Sol (none) I-P: normalized boundaries changed for 558/20,213 (2.76%) sources; corrections changed for 445/558 (79.75%) of those sources. 376 moved closer to and 169 farther from fixed gold-informed boundaries. Correction-relevant spans overlapped 110/677 (16.25%) changed boundary positions.
- GPT-5.6 Sol (none): 20,213 Direct calls and 3,069 additional Projected/Iterative calls (added/Direct: 3,069/20,213 (15.18%)); 8,082,936 recorded tokens across all conditions; 0 recorded format retries and 0 content-filter identity fallbacks. 0 calls were recorded after unchanged normalized boundary vectors.

## Limitations and reproducibility

Boundary-change subsets are intervention-selected diagnostics, not randomized subgroups. The fixed source segmentations used for word M2 and boundary diagnostics are gold-informed proxies, not manually annotated gold word boundaries. Boundary summaries above include descriptive datasets; CEFE contributes no inferential intervals. Reliable document/learner cluster IDs were unavailable, so source-level intervals do not account for within-document dependence. One saved decode per condition cannot quantify repeated-API sampling variability.

Calls, retries, fallbacks, and tokens are totals from saved API metadata, not independently measured billing records. Missing usage fields contribute zero to the token ledger, which is not evidence of zero token consumption. A declared provider-default output limit does not establish a numeric cap or rule out truncation. Monetary costs are not inferred from token totals because pricing and billing records were not independently verified.

## Public artifacts and local-only inputs

- [Scores](scores.tsv), [primary intervals](bootstrap_primary.csv),
  [secondary intervals](bootstrap_secondary.csv), and
  [equivalence sensitivity](equivalence_sensitivity.csv): compact result tables.
- [Dataset counts](../table_2_dataset_statistics.tsv) and
  [current three-model parameters](../kimi_deepseek_gpt56_call_parameters.tsv).
  The shared LaTeX/model-table baseline is historical and covers two models.
- [Boundary diagnostics](../gpt_statistics_revision_20260928/evidence/sol_changed_boundary_diagnostics.csv),
  [changed-subset estimates](../gpt_statistics_revision_20260928/evidence/sol_changed_subset_character_f05.csv),
  and [convergence/call totals](../gpt_statistics_revision_20260928/evidence/sol_convergence_and_calls.csv).
- [Word-GLEU source audit](word_gleu_source_audit.tsv),
  [analysis configuration](analysis_config.json), and [input hashes](input_manifest.json).
  Their paths refer to local research inputs; only the metadata is public.

Full sentence-level scores, predictions, scorer-selection exports, per-run
table snapshots, and validation logs remain local-only. They are not supplied
by this public clone.
