# Consistency audit: manuscript and current three-model results

**Conclusion: the current formal report correctly uses revised Word GLEU, but the newly supplied 15-page PDF has not been synchronized.** Update the manuscript's affected scores, method descriptions, and model scope rather than changing verified evaluation results to match the old draft.

- Audited document: `_ARR_October_2026__prompting_CGEC (2).pdf` (local-only, not distributed in the public repository). Page numbers below refer to physical PDF pages.
- Recorded PDF SHA256: `8f968a0a6a943486f6aaf6c6f7c9420f69f0be7440690111c9deed2dc1a06609`.
- Current formal source: [Separate Kimi, DeepSeek, and GPT-5.6 Sol results and parameters](KIMI_DEEPSEEK_GPT56_EVALUATION_RESULTS.md).
- This report organizes the completed page-by-page audit. It does not reread or modify the PDF, recompute metrics, resample statistics, or change the scorer.

## The current formal report is already correct

The current report has separate **Kimi -> DeepSeek -> GPT-5.6 Sol** chapters, each with its calling-parameter table and its own 32-row evaluation table.

All **96 Word GLEU values** were checked individually against completed condition-source artifacts: R/D use S1, P uses S2, and I uses S3; hypotheses and all complete references continue to use LTP. The other **288 metric values are unchanged**, and the default report does not mix in old fixed-source Word GLEU.

Those 96 values already used the revised policy before the model-by-model layout change, so the presentation update changed no metric values. Preserving historical experiment records does not mean using historical values as current results; the PDF is a separate, unsynchronized document.

## Cell-by-cell numeric comparison

| PDF location | Comparison | Matching content | Content requiring synchronization |
| --- | --- | --- | --- |
| Page 3, Table 1 | Two models, four metrics, 256 cells | All 192 M2 / Character GLEU cells match | All 64 Word GLEU cells still use old fixed-source values |
| Page 14, Table 7 | Two models, Character / Word GLEU, 128 cells | All 64 Character GLEU cells match | The same 64 old Word GLEU values are repeated |
| Page 13, Table 6 | Two models, character / word M2, 128 cells | All 128 cells match | No score changes needed |
| Page 13, Table 5 | Primary differences, intervals, and equivalence markers | All 132 displayed numbers and 20 E markers match | No changes needed to the existing two-model results |
| Page 9, Table 3 | Dataset statistics | All 45 displayed numbers match | No numeric changes needed |

Tables 1 and 7 contain **64 distinct old Word GLEU scores repeated in 128 locations**, not 128 distinct experimental conditions. They all correspond to historical shared-fixed-source values.

The following examples list R / D / P / I in order:

| Model / dataset | Old Word GLEU in the PDF | Current revised Word GLEU |
| --- | --- | --- |
| DeepSeek / NLPCC2018 | 64.35 / 60.87 / 60.87 / 60.85 | 63.86 / 60.07 / 59.93 / 59.89 |
| Kimi / YACLC | 74.35 / 73.29 / 73.06 / 73.04 | 74.15 / 73.06 / 72.73 / 72.57 |

Replace the Word GLEU columns in both tables and recheck bold best-score markers within those metric groups. Do not change the already matching character M2, word M2, or Character GLEU values.

The existing audit also identifies three changes to DeepSeek's best Word GLEU markers:

| Dataset | Previous best condition and score | Revised best condition and score |
| --- | --- | --- |
| YACLC | I: 74.87 | D: 74.54 |
| FCGEC | P: 88.98 | D: 88.57 |
| NaSGEC-Exam | I: 87.34 | D: 86.95 |

## Model scope and calling parameters

**The PDF's downstream CGEC experiments still cover only DeepSeek and Kimi.** GPT-5.6 Sol does appear in Table 2 on page 9, but that is a separate **1,079-sentence intrinsic word-boundary experiment**, not the current **20,213-sentence downstream GEC experiment**. It is therefore incorrect both to say that Sol never appears in the PDF and to say that the paper already includes Sol's downstream results.

The two existing model configurations in Appendix D on pages 8 to 10, especially Table 4 on page 10, agree with the recorded baseline:

| Model | Relationship between the PDF and the recorded configuration |
| --- | --- |
| Kimi | `kimi-k2.6`, thinking disabled; temperature omitted from the request and fixed by the nonthinking endpoint at 0.6; explicit `max_tokens=512` |
| DeepSeek | `deepseek-v4-pro`, explicit `temperature=0.000001`, thinking disabled; `max_tokens` omitted, using the provider default |
| GPT-5.6 Sol | Table 4 omits the downstream configuration; the current run uses `gpt-5.6-sol`, explicit `reasoningEffort=none`, and a verified `maxPromptTokens=8192` input cap; temperature, top_p, and the effective output cap are unexposed provider defaults |

Sol's downstream settings must not automatically be applied to the intrinsic experiment in Table 2. If the paper is to cover the current three-model experiments, add Sol's downstream results, parameters, and corresponding discussion, and update model counts, contrast counts, and combined statistical scope. Each model's current parameter table distinguishes explicit requests, documented defaults, and unexposed settings.

## Method and prose updates

| PDF location | Finding | Required revision |
| --- | --- | --- |
| Page 10, E.1 | Word evaluation is described globally as using a shared gold-informed source independent of prompting condition | Separate Word M2 from Word GLEU: the former retains a shared fixed gold-informed source; the latter uses R/D=S1, P=S2, I=S3. Hypotheses and complete references remain LTP-segmented, and Character GLEU remains character-based |
| Page 2, Section 2 | The claim that Projected / Iterative GLEU always differs from Direct by at most 0.25 no longer holds | Revise the generalization or restrict it to metrics that satisfy it; explain that source-boundary changes alone can affect Word GLEU |
| Page 11, E.4 | Equal sentence F0.5 is described as being resolved by precision -> recall -> reference order | Match the existing implementation: highest unrounded sentence F0.5, then more TP, fewer FP, fewer FN, and earliest complete-reference order; do not change the scorer |
| Page 11, Figure 1 / E.5 | Both ordinary short-range W and linked long-distance movement are reported as W | The current report distinguishes W from WO; linked movement uses the internal key W-LD. A linked U-M pair still counts once, so no total-score change is required |
| Page 9, D.3 | Only BOM / whitespace removal is described, suggesting that generation responses receive no other cleaning | Distinguish generation-time cleaning before saving from evaluation-time normalization afterward: the former also strips code fences, known answer labels, explanation tails, and surrounding quotes; the latter still removes only BOM / whitespace |

Two formal-dataset counterexamples to the page 2 generalization, at displayed precision:

| Model / dataset | Revised Word GLEU contrast | Displayed score difference |
| --- | --- | --- |
| DeepSeek / FlaCGEC | Direct 72.78 -> Projected 72.48 | P-D is -0.30 |
| Kimi / YACLC | Direct 73.06 -> Iterative 72.57 | I-D is -0.49 |

The E.4 rule difference is not merely wording: candidate counts `TP/FP/FN=0/1/2` and `0/1/1` have equal F0.5, precision, and recall, but the current implementation selects the latter because it has fewer FN. The PDF's stated rule would select the earlier reference. Correct the prose, not the already verified implementation.

## Page 12, F.4: revise secondary direction-sensitive count from 6 to 5

The scope here remains **DeepSeek / Kimi, seven formal datasets, three secondary metrics, and three condition contrasts: 126 comparisons**, excluding Sol, CEFE, and the primary character F0.5 metric.

Keeping Word F0.5 / Character GLEU statistics unchanged and substituting existing revised Word GLEU statistics yields **5 comparisons** whose directional classifications differ between BCa and percentile intervals: 0 for Word F0.5, 4 for Character GLEU, and 1 for Word GLEU.

| Model | Dataset | Metric | Contrast | Difference | 95% BCa | 95% percentile |
| --- | --- | --- | --- | --- | --- | --- |
| DeepSeek | NaCGEC | Character GLEU | P-D | +0.019249 | [+0.000539, +0.040585] | [-0.000251, +0.039655] |
| DeepSeek | NaSGEC-Exam | Character GLEU | I-P | +0.033965 | [+0.001401, +0.091454] | [-0.004329, +0.079512] |
| Kimi | YACLC | Character GLEU | P-D | -0.240134 | [-0.625065, -0.033337] | [-0.536999, +0.006604] |
| Kimi | FCGEC | Character GLEU | P-D | +0.051607 | [+0.006411, +0.148151] | [-0.003363, +0.121635] |
| Kimi | YACLC | Word GLEU revised | P-D | -0.328893 | [-0.787853, -0.015766] | [-0.725628, +0.024685] |

This result comes from reading existing `percentile_conclusion_differs` flags and checking interval endpoints, not from resampling. Existing primary character-F0.5 robustness conclusions are unchanged. Adding Sol requires updating the downstream model scope and combined counts; do not simply reuse this two-model count of 5.

## Results that can remain and audit limits

Matching M2, Character GLEU, dataset statistics, and the existing two-model primary findings in Table 5 do not need to change for this synchronization. Counts of datasets where Raw has the highest GLEU also remain unchanged: 5/8 for DeepSeek and 8/8 for Kimi, for both character and revised word GLEU.

Comparison uses the PDF's displayed precision. This report does not modify the uploaded PDF, edit or recompile LaTeX, or independently reproduce all intrinsic word-boundary scores or external reference results. The finding is that the manuscript is not synchronized with the current report, not that other verified metrics need to be rerun.

## Cell-level records and structured evidence

- [Cell-by-cell TSV](manuscript_results_consistency_20260921.tsv): preserves the completed parent-session audit's 512 Table 1 / 6 / 7 comparison records; 384 match and 128 contain repeated old Word GLEU values.
- [Structured findings JSON](manuscript_results_consistency_20260921.json): preserves the latest audit findings, PDF identifier, current-report verification, parameter checks, page references, revision recommendations, and limitations.
- [Current separate three-model results and parameters](KIMI_DEEPSEEK_GPT56_EVALUATION_RESULTS.md): the formal result entry point.

This record was assembled from the completed `manuscript_consistency_findings.json`, `paper_v2_score_comparison.tsv`, `paper_v2_primary_and_text_claims.json`, and `paper_v2_dataset_and_ranking_checks.json`; that step only organized and saved the existing audit artifacts.
