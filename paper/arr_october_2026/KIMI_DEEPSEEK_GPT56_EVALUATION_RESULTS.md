# Kimi / DeepSeek / GPT-5.6 Sol: evaluation results and calling parameters

**Current results: Kimi, DeepSeek, and GPT-5.6 Sol (nonthinking), listed separately. Each model covers the same 20,213 sources and 38,000 complete references.**

**The current official tables use revised condition-source Word GLEU only. Earlier shared fixed-source Word GLEU is superseded in this presentation; historical experiment files and audits are retained unchanged.**

**Manuscript consistency:** [Audit of the uploaded paper against these results](MANUSCRIPT_RESULTS_CONSISTENCY_20260921.md).

R/T0 = Raw; D/T1 = Direct LTP boundaries; P/T2 = Projected boundaries; I/T3 = Iterative boundaries. Scores are on the 0-100 scale; higher is better. The primary metric is Character M2 F0.5.

M2 scores are corrected sentence-local select-best corpus micro-F0.5. Both GLEU metrics select the highest-scoring complete reference independently per sentence and then macro-average. Revised Word GLEU uses source S1/S1/S2/S3 for R/D/P/I; hypotheses and all complete references still use the same LTP installation. Word M2 separately keeps shared fixed gold-informed source boundaries. Both movement thresholds remain 3; linked U-M is scored once as WO. No BPE or OpenCC.

All three retain one correction per executed condition. Converged later stages reuse the preceding correction instead of creating another sample. The legacy runs used saved segmentation-string equality; the Sol run used normalized characters and boundary positions. Historical whitespace-only extra steps remain preserved, not retroactively regenerated.

The parameter tables distinguish explicit settings, provider-fixed values, documented defaults, and values that are unexposed or not recorded. Omitted settings are not assumed to be zero or minimum. Generation seeds are not available; statistical resampling seeds are not generation seeds.

Evidence paths under `runs/`, `implementation/`, and `interface_probe.json`
refer to archived local research artifacts, not bundled downloads. Selected
public generation, validation, and execution summaries are available in
[the nonfinancial evidence directory](gpt_statistics_revision_20260928/evidence/).
The calling-parameter TSV preserves those original provenance descriptions.

Results are point estimates, not between-model statistical significance. YACLC, FCGEC, and CEFE use validation splits. CEFE Track 3 (19 examples) is descriptive only. Word-GLEU source-boundary changes can affect the score even when the correction is unchanged.

## Kimi

### Calling parameters

| Parameter | Request / configuration | Verified or documented interpretation |
| --- | --- | --- |
| Model ID | kimi-k2.6 | Explicit model selection. |
| Provider / interface | Moonshot AI; HTTP chat completions | Recorded base URL: https://api.moonshot.ai/v1. |
| temperature | Omitted from the request | Provider-fixed 0.6 in nonthinking mode; not a client-selected value. |
| top_p | Omitted from the request | Provider default; its numeric value is not recorded. |
| Thinking | thinking.type = "disabled" | Explicitly disabled. |
| max_tokens / output limit | max_tokens = 512 | Explicit output limit, not an input/context cap. |
| Input cap | Not configured or recorded | No verified numeric input limit is available. |
| Generation seed | Not sent | No reproducible generation seed is available; this is not the statistical resampling seed. |
| Samples per executed condition | One retained output | n=1 as an experimental design; no explicit n field. Carried-forward conditions reuse the preceding output. |
| Generated max_t | 3 | Saved T0-T3, including carried-forward outputs. |
| Evaluated Kmax | 3 | Only T0-T3 enter these tables. |
| prompt_variant | paper | The same existing Raw and boundary-aware paper prompt templates. |
| Context | Current correction prompt only | A single user message; no previous dialogue or separate system message. |
| Convergence / reuse | Saved S_i equals S_(i-1) | Legacy exact segmentation-string equality; remaining stages carry the preceding correction forward. |

**Parameter evidence:** runs/kimi_k2_6/generation_config.json; paper/arr_october_2026/table_3_model_configuration.tsv; git:c7e2ee7:scripts/run_iterative_gec.py (HTTP payload, paper prompts, convergence).

### Evaluation results

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

## DeepSeek

### Calling parameters

| Parameter | Request / configuration | Verified or documented interpretation |
| --- | --- | --- |
| Model ID | deepseek-v4-pro | Explicit model selection, matching saved response metadata. |
| Provider / interface | DeepSeek API; HTTP chat completions | The saved direct HTTP request builder is used. |
| temperature | 0.000001 | Explicitly set; not 0 or an inferred default. |
| top_p | Omitted from the request | Provider default; its numeric value is not recorded. |
| Thinking | thinking.type = "disabled" | Explicitly disabled; the archived audit reports no fallback dropping this field. |
| max_tokens / output limit | Omitted from the request | The then-documented nonthinking default is 8,192; this was not an explicitly sent cap. |
| Input cap | Not configured or recorded | No verified numeric input limit; 8,192 above refers to the documented output default. |
| Generation seed | Not sent | No reproducible generation seed is available; this is not the statistical resampling seed. |
| Samples per executed condition | One retained output | n=1 as an experimental design; no explicit n field. Carried-forward conditions reuse the preceding output. |
| Generated stage coverage | T0-T3; FlaCGEC archive retains T0-T10 | The T10-named FlaCGEC file is preserved, but later stages are not evaluated here. |
| Evaluated Kmax | 3 | Only T0-T3 enter these tables. |
| prompt_variant | paper | The same existing Raw and boundary-aware paper prompt templates. |
| Context | Current correction prompt only | A single user message; no previous dialogue or separate system message. |
| Convergence / reuse | Saved S_i equals S_(i-1) | Legacy exact segmentation-string equality; remaining stages carry the preceding correction forward. |

**Parameter evidence:** runs/PAPER_SECTION_5_3_6_INPUTS.md (Section 6.1.5); paper/arr_october_2026/table_3_model_configuration.tsv; git:c7e2ee7:scripts/run_iterative_gec.py (HTTP payload, paper prompts, convergence).

### Evaluation results

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

## GPT-5.6 Sol

### Calling parameters

| Parameter | Request / configuration | Verified or documented interpretation |
| --- | --- | --- |
| Model ID | gpt-5.6-sol | Explicit model selection, matching saved response metadata. |
| Provider / interface | GitHub Copilot SDK; OpenAI model | Pinned SDK 1.0.14 and runtime 1.0.85. |
| temperature | Omitted / not exposed by this interface | Provider default; no numeric value or minimum temperature is claimed. |
| top_p | Omitted / not exposed by this interface | Provider default; no numeric value is claimed. |
| Thinking / reasoning | reasoningEffort = "none" | Explicit request and matching returned reasoning mode. |
| max_tokens / output limit | Provider default; no verified numeric cap | The attempted capability override was empirically ignored; no 512 cap or probe limit is claimed for the formal run. |
| Input cap | maxPromptTokens = 8192 | Explicit and confirmed in returned settings; this is an input limit, not an output limit. |
| Generation seed | Not explicitly configured or exposed | No reproducible generation seed is available; statistical resampling seeds are unrelated. |
| Samples per executed condition | One retained output | n=1 as an experimental design; no explicit n field. Carried-forward conditions reuse the preceding output. |
| Generated max_t | 3 | Saved T0-T3, including carried-forward outputs. |
| Evaluated Kmax | 3 | Only T0-T3 enter these tables. |
| prompt_variant | paper | The same existing Raw and boundary-aware paper prompt templates. |
| Context | Fresh isolated session per executed condition | Neutral system message "You are a helpful assistant." plus the current prompt; no history, tools, repository instructions, or gold references. |
| Convergence / reuse | Normalized learner characters and boundary positions unchanged | Remaining stages carry the preceding correction forward. |

**Parameter evidence:** runs/gpt_5_6_sol_copilot_nothinking/generation_config.json; saved generation_settings and returned reasoningEffort/maxPromptTokens; interface_probe.json; implementation/scripts/copilot/gec_bridge.mjs.

### Evaluation results

| Dataset | Metric | R / T0 | D / T1 | P / T2 | I / T3 |
| --- | --- | --- | --- | --- | --- |
| NLPCC2018 | Character M2 F0.5 | 29.45 | 32.75 | 32.86 | 32.79 |
| NLPCC2018 | Word M2 F0.5 | 29.15 | 32.39 | 32.55 | 32.43 |
| NLPCC2018 | Character GLEU | 72.11 | 73.32 | 73.32 | 73.28 |
| NLPCC2018 | Word GLEU (revised) | 62.46 | 64.05 | 63.98 | 63.82 |
| MuCGEC | Character M2 F0.5 | 36.33 | 40.73 | 40.59 | 40.58 |
| MuCGEC | Word M2 F0.5 | 36.55 | 40.81 | 40.88 | 40.84 |
| MuCGEC | Character GLEU | 74.95 | 76.49 | 76.51 | 76.51 |
| MuCGEC | Word GLEU (revised) | 66.47 | 68.18 | 68.06 | 68.04 |
| YACLC | Character M2 F0.5 | 55.02 | 57.93 | 57.99 | 57.73 |
| YACLC | Word M2 F0.5 | 55.92 | 58.90 | 58.74 | 58.57 |
| YACLC | Character GLEU | 78.53 | 80.09 | 80.15 | 80.07 |
| YACLC | Word GLEU (revised) | 71.22 | 72.77 | 72.74 | 72.60 |
| FlaCGEC | Character M2 F0.5 | 39.23 | 39.94 | 40.35 | 40.16 |
| FlaCGEC | Word M2 F0.5 | 38.20 | 38.45 | 38.75 | 38.68 |
| FlaCGEC | Character GLEU | 84.53 | 84.35 | 84.34 | 84.34 |
| FlaCGEC | Word GLEU (revised) | 77.81 | 77.52 | 77.14 | 77.11 |
| FCGEC | Character M2 F0.5 | 14.13 | 17.22 | 17.59 | 17.22 |
| FCGEC | Word M2 F0.5 | 12.54 | 15.19 | 15.84 | 15.43 |
| FCGEC | Character GLEU | 88.36 | 90.62 | 90.72 | 90.66 |
| FCGEC | Word GLEU (revised) | 82.09 | 85.34 | 85.22 | 85.04 |
| NaCGEC | Character M2 F0.5 | 24.62 | 26.83 | 26.88 | 26.80 |
| NaCGEC | Word M2 F0.5 | 23.21 | 25.18 | 25.46 | 25.30 |
| NaCGEC | Character GLEU | 87.50 | 88.16 | 88.16 | 88.14 |
| NaCGEC | Word GLEU (revised) | 81.32 | 82.17 | 81.93 | 81.86 |
| NaSGEC-Exam | Character M2 F0.5 | 21.93 | 26.09 | 26.46 | 26.30 |
| NaSGEC-Exam | Word M2 F0.5 | 22.09 | 25.12 | 25.70 | 25.48 |
| NaSGEC-Exam | Character GLEU | 88.54 | 90.13 | 90.18 | 90.16 |
| NaSGEC-Exam | Word GLEU (revised) | 82.92 | 85.07 | 84.98 | 84.88 |
| CEFE Track 3 | Character M2 F0.5 | 39.51 | 35.35 | 34.88 | 34.43 |
| CEFE Track 3 | Word M2 F0.5 | 32.89 | 31.25 | 31.25 | 30.17 |
| CEFE Track 3 | Character GLEU | 80.58 | 81.64 | 81.23 | 81.32 |
| CEFE Track 3 | Word GLEU (revised) | 69.78 | 71.54 | 70.98 | 70.65 |

**Machine-readable tables**

[Full-precision evaluation TSV](kimi_deepseek_gpt56_evaluation_results.tsv) preserves the original condition-row schema and is grouped by model: 32 rows per model, 96 rows and 384 metric values in total. Each model's Markdown result table has 32 metric rows (8 datasets x 4 metrics), with two-decimal display.

[Calling-parameter TSV](kimi_deepseek_gpt56_call_parameters.tsv) records the parameter descriptions and their evidence separately; parameter rows are not mixed into the metric TSV.

The 96 revised Word-GLEU values are checked against the completed condition-source outputs in `runs/kimi_k2_6/word_gleu_condition`, `runs/word_gleu_condition_select_best`, and `runs/gpt_5_6_sol_copilot_nothinking/word_gleu_condition`. The other 288 metric values match the previously verified score tables unchanged. Only presentation and parameter documentation are updated.
