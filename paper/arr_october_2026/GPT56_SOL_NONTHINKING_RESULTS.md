# GPT-5.6 Sol: nonthinking R/D/P/I results

Archived experiment detail. The default public presentation is the
[Kimi / DeepSeek / GPT-5.6 Sol report](KIMI_DEEPSEEK_GPT56_EVALUATION_RESULTS.md).

**Complete:** 8 benchmark splits, 20,213 sources, 38,000 complete references, and 80,852 evaluated sentence-condition rows. Every recorded formal completion reported `reasoningEffort=none` and zero reasoning tokens.

## Exact generation configuration

| Parameter | Recorded setting |
| --- | --- |
| Model | `gpt-5.6-sol` via GitHub Copilot |
| SDK / runtime | 1.0.14 / 1.0.85 (pinned; unchanged from the earlier GPT experiment) |
| Thinking | Explicit none; per-completion setting and zero reasoning tokens verified |
| Temperature / top-p | Provider defaults; omitted and not claimed to be minimum or deterministic |
| Output limit | Provider default; SDK capability override was empirically ignored, so no 512-token cap is claimed |
| Context | Fresh tool-free session per source/stage, neutral system message, no chat history, repository instructions, or gold answers |
| Prompt limit | 8,192 input tokens; all actual prompts remain below it |
| Prompt / samples / last stage | Existing paper prompts / one sample / T3 |

This is a new GPT-5.6 experiment, not a GPT-6 thinking on/off ablation. The interface cap probe and 64-source pilot are excluded from all benchmark metrics. Historical GPT-6, DeepSeek, and Kimi predictions/results were preserved.

## Primary character M2 micro-F0.5

| Dataset | N | R / T0 | D / T1 | P / T2 | I / T3 |
| --- | --- | --- | --- | --- | --- |
| NLPCC2018 | 2000 | 29.45 | 32.75 | 32.86 | 32.79 |
| MuCGEC | 6000 | 36.33 | 40.73 | 40.59 | 40.58 |
| YACLC | 1000 | 55.02 | 57.93 | 57.99 | 57.73 |
| FlaCGEC | 1325 | 39.23 | 39.94 | 40.35 | 40.16 |
| FCGEC | 2000 | 14.13 | 17.22 | 17.59 | 17.22 |
| NaCGEC | 5869 | 24.62 | 26.83 | 26.88 | 26.80 |
| NaSGEC-Exam | 2000 | 21.93 | 26.09 | 26.46 | 26.30 |
| CEFE Track 3 | 19 | 39.51 | 35.35 | 34.88 | 34.43 |

Among the 7 formal datasets, Direct-minus-Raw has 6 positive and 0 negative pointwise 95% BCa intervals. Among the 14 formal P-D/I-P contrasts, 9 meet the pre-specified +/-0.50-point practical-equivalence criterion. Directional evidence and practical equivalence are not mutually exclusive.

| Dataset | D-R | P-D | I-P |
| --- | --- | --- | --- |
| NLPCC2018 | +3.30 [+2.29, +4.33] | +0.11 [-0.29, +0.48] E | -0.07 [-0.27, +0.14] E |
| MuCGEC | +4.40 [+3.84, +4.95] | -0.13 [-0.36, +0.09] E | -0.01 [-0.14, +0.13] E |
| YACLC | +2.91 [+1.42, +4.40] | +0.05 [-0.40, +0.58] E | -0.25 [-0.66, +0.01] |
| FlaCGEC | +0.70 [-0.85, +2.23] | +0.41 [-0.09, +1.03] | -0.19 [-0.47, +0.01] E |
| FCGEC | +3.09 [+2.08, +4.10] | +0.37 [+0.05, +0.95] * | -0.37 [-0.86, -0.15] |
| NaCGEC | +2.21 [+1.55, +2.88] | +0.05 [-0.12, +0.22] E | -0.08 [-0.19, +0.04] E |
| NaSGEC-Exam | +4.16 [+2.92, +5.42] | +0.37 [-0.02, +0.82] | -0.16 [-0.40, +0.02] E |
| CEFE Track 3 | -4.16 (descriptive) | -0.47 (descriptive) | -0.46 (descriptive) |

Intervals use 50,000 paired source-sentence replicates, seed 20260915, chunk size 1000. `E` denotes the paired 90% BCa interval strictly inside +/-0.50 points. 95%/90% percentile checks and sensitivity margins +/-0.25 and +/-1.00 are retained in the CSVs. CEFE (n=19) is descriptive only.

* Interval-sensitive primary result: FCGEC P-D, delta +0.370; BCa 95% [+0.0550, +0.9524], percentile 95% [-0.0033, +0.8232]. The pointwise directional conclusion is fragile and must not be described as robust across interval constructions.

## Revised word GLEU

| Dataset | R / T0 | D / T1 | P / T2 | I / T3 |
| --- | --- | --- | --- | --- |
| NLPCC2018 | 62.46 | 64.05 | 63.98 | 63.82 |
| MuCGEC | 66.47 | 68.18 | 68.06 | 68.04 |
| YACLC | 71.22 | 72.77 | 72.74 | 72.60 |
| FlaCGEC | 77.81 | 77.52 | 77.14 | 77.11 |
| FCGEC | 82.09 | 85.34 | 85.22 | 85.04 |
| NaCGEC | 81.32 | 82.17 | 81.93 | 81.86 |
| NaSGEC-Exam | 82.92 | 85.07 | 84.98 | 84.88 |
| CEFE Track 3 | 69.78 | 71.54 | 70.98 | 70.65 |

Word-GLEU source policy is S1/S1/S2/S3 for R/D/P/I. Hypotheses and every complete reference use LTP 4.2.14. GLEU selects the highest complete-reference score independently per sentence and macro-averages. Source boundaries can change word GLEU even when a correction stays identical. Word M2 independently retains shared fixed gold-informed source boundaries. Both M2 metrics use projection-derived edits, sentence-local select-best, thresholds 3, and linked U-M counted once as WO; no BPE or OpenCC.

## Complete four-metric scores

| Dataset | Condition | Character F0.5 | Word F0.5 | Character GLEU | Word GLEU |
| --- | --- | --- | --- | --- | --- |
| NLPCC2018 | R | 29.45 | 29.15 | 72.11 | 62.46 |
| NLPCC2018 | D | 32.75 | 32.39 | 73.32 | 64.05 |
| NLPCC2018 | P | 32.86 | 32.55 | 73.32 | 63.98 |
| NLPCC2018 | I | 32.79 | 32.43 | 73.28 | 63.82 |
| MuCGEC | R | 36.33 | 36.55 | 74.95 | 66.47 |
| MuCGEC | D | 40.73 | 40.81 | 76.49 | 68.18 |
| MuCGEC | P | 40.59 | 40.88 | 76.51 | 68.06 |
| MuCGEC | I | 40.58 | 40.84 | 76.51 | 68.04 |
| YACLC | R | 55.02 | 55.92 | 78.53 | 71.22 |
| YACLC | D | 57.93 | 58.90 | 80.09 | 72.77 |
| YACLC | P | 57.99 | 58.74 | 80.15 | 72.74 |
| YACLC | I | 57.73 | 58.57 | 80.07 | 72.60 |
| FlaCGEC | R | 39.23 | 38.20 | 84.53 | 77.81 |
| FlaCGEC | D | 39.94 | 38.45 | 84.35 | 77.52 |
| FlaCGEC | P | 40.35 | 38.75 | 84.34 | 77.14 |
| FlaCGEC | I | 40.16 | 38.68 | 84.34 | 77.11 |
| FCGEC | R | 14.13 | 12.54 | 88.36 | 82.09 |
| FCGEC | D | 17.22 | 15.19 | 90.62 | 85.34 |
| FCGEC | P | 17.59 | 15.84 | 90.72 | 85.22 |
| FCGEC | I | 17.22 | 15.43 | 90.66 | 85.04 |
| NaCGEC | R | 24.62 | 23.21 | 87.50 | 81.32 |
| NaCGEC | D | 26.83 | 25.18 | 88.16 | 82.17 |
| NaCGEC | P | 26.88 | 25.46 | 88.16 | 81.93 |
| NaCGEC | I | 26.80 | 25.30 | 88.14 | 81.86 |
| NaSGEC-Exam | R | 21.93 | 22.09 | 88.54 | 82.92 |
| NaSGEC-Exam | D | 26.09 | 25.12 | 90.13 | 85.07 |
| NaSGEC-Exam | P | 26.46 | 25.70 | 90.18 | 84.98 |
| NaSGEC-Exam | I | 26.30 | 25.48 | 90.16 | 84.88 |
| CEFE Track 3 | R | 39.51 | 32.89 | 80.58 | 69.78 |
| CEFE Track 3 | D | 35.35 | 31.25 | 81.64 | 71.54 |
| CEFE Track 3 | P | 34.88 | 31.25 | 81.23 | 70.98 |
| CEFE Track 3 | I | 34.43 | 30.17 | 81.32 | 70.65 |

## Same-condition comparison: Direct / T1

| Dataset | DeepSeek | Kimi | GPT-6 (medium) | GPT-5.6 Sol (none) |
| --- | --- | --- | --- | --- |
| NLPCC2018 | 39.87 | 36.73 | 36.71 | 32.75 |
| MuCGEC | 48.17 | 44.12 | 43.44 | 40.73 |
| YACLC | 62.96 | 60.86 | 61.17 | 57.93 |
| FlaCGEC | 43.89 | 32.17 | 46.34 | 39.94 |
| FCGEC | 23.63 | 15.44 | 21.29 | 17.22 |
| NaCGEC | 32.75 | 23.43 | 34.24 | 26.83 |
| NaSGEC-Exam | 33.90 | 22.25 | 31.11 | 26.09 |
| CEFE Track 3 | 43.35 | 40.46 | 35.35 | 35.35 |

This historical table compares character F0.5 point estimates, not cross-model
significance. The full four-model comparison remains local-only; the public
default is the three-model report linked above. Model identity, provider
defaults, access dates, and original reasoning settings differ; performance
differences cannot be causally attributed solely to thinking.

Numbers of formal datasets with a higher GPT-5.6 Sol score under the same Direct/T1 condition (point estimates; CEFE excluded):

| Metric | Versus DeepSeek | Versus Kimi | Versus GPT-6 |
| --- | --- | --- | --- |
| character_f05 | 0/7 | 4/7 | 0/7 |
| word_f05 | 0/7 | 4/7 | 0/7 |
| character_gleu | 3/7 | 5/7 | 0/7 |
| word_gleu | 3/7 | 5/7 | 0/7 |

## Verification, artifacts, and limitations

Independent checks reconstructed 161,704 hypothesis M2 blocks and recomputed 161,704 character/word GLEU sentence-condition scores from exact persisted inputs. All complete references, IDs, source boundaries, prediction hashes, and corrected corpus aggregations were checked. Original experiment artifacts remain unchanged.

- `gpt56_sol_none/scores.tsv`: full-precision four-metric scores.
- `gpt56_sol_none/ANALYSIS.md`: full paired analysis and diagnostics.
- `gpt56_sol_none/bootstrap_primary.csv` and `bootstrap_secondary.csv`: all intervals and robustness flags.
- [Input manifest](gpt56_sol_none/input_manifest.json): local input paths and unchanged hashes, not the raw inputs.
- [Sanitized verification summary](gpt_statistics_revision_20260928/evidence/sol_verification_summary.sanitized.json) and [final validation](gpt_statistics_revision_20260928/evidence/sol_final_validation.sanitized.json): compact public validation records.
- Private raw predictions, request journals, model snapshot, tests, caches, and inputs: `runs/gpt_5_6_sol_copilot_nothinking/`.

To reproduce only evaluation and reporting from the completed local outputs (no new LLM calls):

```bash
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
PY=/path/to/compatible/python
"$PY" runs/gpt_5_6_sol_copilot_nothinking/evaluate_sol_experiment.py
"$PY" runs/gpt_5_6_sol_copilot_nothinking/verify_publish_sol.py
```

The local ignored run directory is required; a fresh clone alone lacks the generations, model assets, and reproducible task-local snapshot. Do not launch a new generation to reproduce these tables.

There is one saved decode per model/source/condition and no reliable document/learner clusters. Intervals do not cover API sampling variability or within-document dependence, and they are pointwise without multiplicity adjustment. YACLC/FCGEC/CEFE use public validation splits. Temperature is unexposed; the attempted output-cap override did not work and is not described as enforced. The independent pilot and original model runs are never mixed into formal metrics.
