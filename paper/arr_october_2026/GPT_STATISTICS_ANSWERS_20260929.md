# Answers to the GPT statistics and documentation questions

**Model: GPT-5.6 Sol, nonthinking (`gpt-5.6-sol`, `reasoningEffort=none`).**

This is a standalone factual response to the advisor's comments on the supplied
`acl_latex.tex`, which is local-only and not distributed here. It does not
modify the manuscript. All results below come from
the completed, verified analysis of the saved outputs; no new model calls,
metric computations, or bootstrap runs were needed for this response.

## 1. Short answer

**GPT's statistical analysis and execution records are available.** The
statements that its reliability is unassessed, its bootstrap intervals are
unavailable, or its source coverage remains unverified are documentation gaps,
not missing experiments.

The primary analysis uses the same 50,000-replicate paired bootstrap design as
the other models. For GPT, the projection gain on FCGEC is positive under the
95% BCa interval, but its percentile interval includes zero. Further iteration
significantly reduces the FCGEC score under both interval methods. Nine of
GPT's 14 formal refinement comparisons meet the specified half-point
equivalence criterion.

The one genuine unresolved numerical setting is the effective **output cap**:
the provider route does not expose it, and an attempted capability override was
not enforced. We can document that limitation precisely, but cannot substitute
an invented 512-token cap or confuse the verified 8,192-token **input** cap
with an output limit.

## 2. Answers mapped to every comment

Line numbers refer to the supplied manuscript, before any edits.

| Advisor's location/question | Verified answer | Details below |
| --- | --- | --- |
| L79: “statistical reliability of these gains remains unassessed” | Assessed. Of seven formal primary P-D comparisons, one has a positive 95% BCa interval: FCGEC. That result is interval-sensitive; six positive point estimates across eight datasets do not mean six significant improvements. | Sections 3–5 |
| L245: “statistical reliability and practical equivalence remain unassessed” | Both assessed. GPT has four P-D and five I-P equivalence decisions, totaling 9/14 under the specified +/-0.50-point margin. | Sections 4–5 |
| L267: “its statistical reliability remains unassessed” | The conclusion can be supported by the completed inference: one fragile primary projection improvement, one primary iteration deterioration, and no supported primary iteration improvement. | Sections 4–6 |
| L446: access dates and output-processing/retry/fallback records missing | Available. Formal access was September 20–21, 2026, UTC. Cleaning, zero format retries, zero filtering fallbacks, and two recovered transport timeouts are documented. | Sections 7–9 |
| L446 / Table 4 caption: “no numeric output limit was verified” | This is a real interface limitation, not a missing result to guess. The effective output cap is provider-controlled/unexposed. The explicit, verified 8,192-token setting is an input cap. | Section 8 |
| L522: identical source-level coverage remains unverified | Verified: the same 20,213 source sentences and 38,000 complete references; all source IDs/texts, reference counts/order, and retained T0–T3 outputs passed the existing audits. | Section 7 |
| L621: paired bootstrap intervals have not been computed | Already computed for all eight datasets: 21 formal primary contrasts across seven datasets, plus three descriptive CEFE contrasts without intervals. Secondary intervals are also available. | Sections 3–6 |
| Table 5 caption: paired intervals unavailable | The complete GPT primary differences, 95% BCa intervals, and equivalence markers are supplied below. | Section 4 |
| L762: GPT intervention diagnostics unavailable | Available: changed-source/correction counts, proxy-distance directions, correction-span overlap, and changed-subset performance. | Section 10 |
| L790: GPT execution metadata unavailable | Available: 43,495 successful formal calls, stage totals, stopping counts, token totals, and two additional attempts with unknown usage. | Sections 9 and 11 |

## 3. Statistical method and what “significant” means here

| Item | Actual analysis |
| --- | --- |
| Primary outcome | Projection-derived character-level corpus micro-F0.5, on the 0–100 scale |
| Comparisons | D-R, P-D, and I-P, separately within each model and dataset |
| R/D/P/I | Raw / Direct-WB / first Projected-WB / one additional Iterative Projected-WB condition |
| Resampling unit | Source sentence |
| Pairing | Identical resampled source weights across conditions and metrics within each model–dataset block |
| Bootstrap replicates | 50,000 per inferential model–dataset block |
| Base seed | `20260915`; deterministic model–dataset-specific derived seeds |
| Chunk size | 1,000 |
| Edit-score aggregation | Recompute micro-F0.5 from pooled TP/FP/FN in every draw; do not average sentence F-scores |
| Directional inference | Paired 95% bias-corrected and accelerated (BCa) confidence interval |
| Positive/negative evidence | The entire 95% interval must be above/below zero |
| Equivalence | Separate paired 90% BCa interval strictly inside (-0.50, +0.50) points |
| Sensitivity checks | Ordinary percentile intervals and equivalence margins of +/-0.25 and +/-1.00 |
| Formal datasets | NLPCC2018, MuCGEC, YACLC, FlaCGEC, FCGEC, NaCGEC, NaSGEC-Exam |
| CEFE Track 3 | Descriptive only because n=19; no formal intervals or equivalence decisions |
| Multiple comparisons | No correction; intervals are pointwise and secondary/subset analyses are exploratory |

This is the same interval-based significance assessment used for DeepSeek and
Kimi. The archived analysis reports confidence intervals and their direction,
not numerical p-values. **No p-values are invented from rounded interval
endpoints.** A 95% interval containing zero is inconclusive; it is not evidence
of equality. Equivalence requires the separate 90% interval and specified
margin, and the margin itself does not prove linguistic or practical
negligibility.

All multi-reference edit scores use sentence-local selection of one complete
reference. Character and word GLEU independently select the best complete
reference per sentence and then macro-average. Word GLEU uses source
**R/D=S1, P=S2, I=S3**, with LTP hypotheses/references. Word M2 retains the
shared fixed gold-informed source segmentation. No BPE or OpenCC is used.

## 4. Complete GPT primary significance results

Each cell contains **difference in character micro-F0.5 points [95% BCa CI]**.
`E` denotes the separate 90% interval passing the half-point equivalence
criterion. `*` marks an interval-sensitive directional result.

| Dataset | D-R | P-D | I-P |
| --- | --- | --- | --- |
| NLPCC2018 | +3.30 [+2.29, +4.33] | +0.11 [-0.29, +0.48] E | -0.07 [-0.27, +0.14] E |
| MuCGEC | +4.40 [+3.84, +4.95] | -0.13 [-0.36, +0.09] E | -0.01 [-0.14, +0.13] E |
| YACLC | +2.91 [+1.42, +4.40] | +0.05 [-0.40, +0.58] E | -0.25 [-0.66, +0.01] |
| FlaCGEC | +0.70 [-0.85, +2.23] | +0.41 [-0.09, +1.03] | -0.19 [-0.47, +0.01] E |
| FCGEC | +3.09 [+2.08, +4.10] | +0.37 [+0.05, +0.95] * | -0.37 [-0.86, -0.15] |
| NaCGEC | +2.21 [+1.55, +2.88] | +0.05 [-0.12, +0.22] E | -0.08 [-0.19, +0.04] E |
| NaSGEC-Exam | +4.16 [+2.92, +5.42] | +0.37 [-0.02, +0.82] | -0.16 [-0.40, +0.02] E |
| CEFE Track 3, descriptive | -4.16 | -0.47 | -0.46 |

These differences use unrounded pooled-count scores. They can differ by 0.01
from subtracting the two-decimal absolute scores printed in a manuscript table.

### Primary conclusions

| GPT contrast | Formal comparisons | Positive 95% BCa | Negative 95% BCa | Inconclusive | Equivalence established |
| --- | ---: | ---: | ---: | ---: | --- |
| D-R | 7 | 6 | 0 | 1 | Not tested for this contrast |
| P-D | 7 | 1 | 0 | 6 | 4/7 |
| I-P | 7 | 0 | 1 | 6 | 5/7 |
| P-D and I-P combined | 14 | 1 | 1 | 12 | 9/14 |

Thus, GPT's six positive P-D point estimates across eight datasets are **not**
six statistically supported improvements. Under the primary criterion, only
FCGEC has a positive interval, and that classification needs the qualification
below. CEFE never contributes to the seven-dataset inferential counts.

### FCGEC: projection improvement is interval-sensitive

| Quantity | GPT P-D on FCGEC |
| --- | --- |
| Difference | +0.370029 points |
| 95% BCa CI | [+0.054955, +0.952431] |
| 95% percentile CI | [-0.003324, +0.823210] |
| 90% BCa CI | [+0.098457, +0.833728] |
| 90% percentile CI | [+0.049501, +0.741799] |
| Interpretation | Positive under the specified 95% BCa criterion, but inconclusive under percentile intervals; half-point equivalence is not established. |

For the subsequent FCGEC I-P comparison, the difference is **-0.372636**,
with 95% BCa **[-0.863919, -0.150098]** and percentile
**[-0.726765, -0.103643]**. Both intervals support deterioration.

## 5. The actual 90% equivalence intervals

Decisions use full precision, not the rounded endpoints below.

| Dataset | P-D: 90% BCa CI | P-D equivalent? | I-P: 90% BCa CI | I-P equivalent? |
| --- | --- | --- | --- | --- |
| NLPCC2018 | [-0.23, +0.42] | Yes | [-0.24, +0.10] | Yes |
| MuCGEC | [-0.32, +0.06] | Yes | [-0.12, +0.10] | Yes |
| YACLC | [-0.33, +0.49] | Yes | [-0.58, -0.03] | Not established |
| FlaCGEC | [-0.01, +0.92] | Not established | [-0.42, -0.01] | Yes |
| FCGEC | [+0.10, +0.83] | Not established | [-0.76, -0.18] | Not established |
| NaCGEC | [-0.09, +0.20] | Yes | [-0.18, +0.02] | Yes |
| NaSGEC-Exam | [+0.04, +0.74] | Not established | [-0.35, -0.01] | Yes |

Failure to establish equivalence is not proof of a practically important
effect. GPT has no primary equivalence classification that changes between
BCa and percentile intervals at the specified margin.

If the manuscript reports counts for all three models, the correct combined
figures are:

| Incremental primary contrasts | Comparisons | Improvements | Deteriorations | Inconclusive directions | Equivalence established |
| --- | ---: | ---: | ---: | ---: | ---: |
| P-D, three models | 21 | 3 | 2 | 16 | 12 |
| I-P, three models | 21 | 0 | 2 | 19 | 17 |
| Total | 42 | 3 | 4 | 35 | 29 |

DeepSeek/Kimi contribute the unchanged 20/28 equivalence decisions; GPT adds
9/14, yielding **29/42**. These are counts of separate within-model,
within-dataset comparisons, not a pooled effect or a test of superiority
between models.

The statement that GPT is the only model where projection helps is too broad.
The existing primary analysis also has positive P-D intervals for DeepSeek on
NaCGEC and Kimi on FlaCGEC. GPT's overall pattern and the number of positive
point estimates differ, but it is not the only model with a positive contrast.

## 6. Secondary metrics: distinguish point estimates from inference

### Word-level M2 F0.5

Cells contain **difference [95% BCa CI]**.

| Dataset | P-D | I-P |
| --- | --- | --- |
| NLPCC2018 | +0.16 [-0.28, +0.62] | -0.12 [-0.35, +0.15] |
| MuCGEC | +0.08 [-0.16, +0.32] | -0.05 [-0.20, +0.11] |
| YACLC | -0.16 [-0.82, +0.45] | -0.17 [-0.53, +0.19] |
| FlaCGEC | +0.29 [-0.27, +0.91] | -0.07 [-0.40, +0.16] |
| FCGEC | +0.65 [+0.31, +1.22] | -0.40 [-0.88, -0.17] |
| NaCGEC | +0.28 [+0.07, +0.51] | -0.16 [-0.32, -0.02] |
| NaSGEC-Exam | +0.58 [+0.17, +1.00] | -0.22 [-0.51, +0.05] |
| CEFE Track 3, descriptive | +0.00 | -1.08 |

Projection has positive word-F0.5 intervals on **FCGEC, NaCGEC, and
NaSGEC-Exam**. The other four formal projection intervals include zero.
Iteration has negative intervals on **FCGEC and NaCGEC**; the other five
include zero. These are exploratory secondary results, not replacements for
the primary character-F0.5 analysis.

### All GPT secondary directional counts

Each row covers the seven formal datasets.

| Metric | Contrast | Positive 95% BCa | Negative 95% BCa | Inconclusive |
| --- | --- | ---: | ---: | ---: |
| Word F0.5 | D-R | 6 | 0 | 1 |
| Word F0.5 | P-D | 3 | 0 | 4 |
| Word F0.5 | I-P | 0 | 2 | 5 |
| Character GLEU | D-R | 6 | 0 | 1 |
| Character GLEU | P-D | 1 | 0 | 6 |
| Character GLEU | I-P | 0 | 1 | 6 |
| Word GLEU, revised source policy | D-R | 6 | 0 | 1 |
| Word GLEU, revised source policy | P-D | 0 | 2 | 5 |
| Word GLEU, revised source policy | I-P | 0 | 4 | 3 |

Full-precision intervals exist for all 72 GPT secondary comparisons, including
the nine descriptive CEFE rows. No GPT secondary directional classification
changes between BCa and percentile intervals. Across all three models, five
of the 189 formal secondary classifications are interval-sensitive: four
character-GLEU comparisons and one revised-word-GLEU comparison, all belonging
to DeepSeek/Kimi.

Word-GLEU changes can result from a changed source segmentation even when the
corrected output is identical. They cannot be attributed solely to improved
or worsened corrections.

## 7. Access dates and identical source coverage

**Formal GPT access dates: September 20–21, 2026, UTC.**

| Record | UTC timestamp |
| --- | --- |
| First formal request started | `2026-09-20T16:09:36.593642+00:00` |
| Last formal request started | `2026-09-21T02:06:12.539804+00:00` |
| Generation completion recorded | `2026-09-21T02:06:17.820532+00:00` |

Request timestamps are not presented as response-completion timestamps.
Pilot and interface-probe timestamps are excluded from these formal-run dates.

| Dataset | Split | Source sentences | Complete references |
| --- | --- | ---: | ---: |
| NLPCC2018 | Test | 2,000 | 2,183 |
| MuCGEC | Test | 6,000 | 13,119 |
| YACLC | Validation | 1,000 | 8,931 |
| FlaCGEC | Test | 1,325 | 1,325 |
| FCGEC | Validation | 2,000 | 2,550 |
| NaCGEC | Test | 5,869 | 6,978 |
| NaSGEC-Exam | Test | 2,000 | 2,895 |
| CEFE Track 3 | Validation | 19 | 19 |
| **Total per model** | | **20,213** | **38,000** |

The completed audits verify source IDs, normalized source strings, reference
counts/order, and all T0–T3 outputs. Saved prediction IDs are zero-based and
prepared gold IDs are one-based; this convention was accounted for during
alignment checks. The eight gold-file hashes match those used for DeepSeek and
Kimi, and the eight GPT JSONL hashes match the saved input manifest.

GPT therefore has **80,852 sentence–condition records**, including
carry-forward outputs, with no post-hoc source exclusions. The common-coverage
claim is verified; it does not remain an open item.

## 8. Actual model settings and the output-limit question

| Setting | Verified record |
| --- | --- |
| Model identifier | `gpt-5.6-sol` |
| Access route | GitHub Copilot SDK, serving the OpenAI model |
| SDK / runtime | SDK `1.0.14`; runtime `1.0.85` |
| Requested reasoning | Explicit `reasoningEffort=none` |
| Returned reasoning | `none` on every successful formal response |
| Recorded reasoning tokens | Zero on every successful formal response |
| Temperature | Not set explicitly; provider default not exposed |
| Top-p | Not set explicitly; provider default not exposed |
| Generation seed | Not configured or exposed; the bootstrap seed is not a generation seed |
| Input cap | Explicit `maxPromptTokens=8192`, verified in returned settings |
| Effective output cap | Provider-controlled and not exposed; no numeric enforced value is known |
| Samples | One retained correction per executed condition; converged conditions reuse the preceding output |
| Evaluated stages | T0–T3; one extra iteration after the first projected condition |
| Prompt variant | The same zero-shot Chinese `paper` prompts as the other runs |
| Session context | Fresh, tool-free session per executed source/condition; neutral system message “You are a helpful assistant.” plus the current prompt |
| Excluded context | Conversation history, repository instructions, tools, and gold answers |

A previously saved, separate synthetic probe requested an output-cap override
of one token but returned **23 output tokens** with finish reason `stop`.
The capability override was therefore not enforced through this route. It
would be incorrect to describe a requested override as the effective formal
output limit.

The maximum successful formal completion observed was **212 output tokens**.
That is an observation, not a configured limit. All successful completions
reported `stop`, and none reported length truncation. The two attempts without
returned usage cannot be assigned a finish reason.

Thus a precise answer is: **“The effective output limit was controlled by the
provider and was not exposed through the interface; the explicitly verified
8,192-token limit applied to input context.”** The actual output cap remains
unknown, rather than being a documentation value we can now fill numerically.

## 9. Output processing, retries, fallbacks, and two timeouts

### Output processing

Before a correction is saved, the generation pipeline strips code fences,
recognized answer prefixes, trailing explanation sections, whitespace, and
surrounding quotation marks. Format checks reject empty responses, explicit
self-analysis, and implausibly long corrections.

Evaluation reuses the saved corrections. At that stage, normalization removes
only BOM and whitespace; it does not rewrite the remaining characters and does
not use OpenCC or BPE. Generation-time wrapper cleaning and evaluation-time
normalization are separate operations.

### Successful formal calls

- **43,495** successful completions, with unique source-stage keys, completion
  identifiers, and sessions.
- **0 format retries** and **0 content-filter identity fallbacks**.
- All successful completions report `stop`, `reasoningEffort=none`, and zero
  reasoning tokens.

### Transport timeouts

There were **43,497 client attempts**, including two additional attempts that
timed out without returning a completion or a provider-usage record.

| Dataset | Zero-based source ID | Stage | Request started, UTC | Client timeout | Outcome |
| --- | ---: | --- | --- | --- | --- |
| MuCGEC | 3,752 | P / T2 | `2026-09-20T17:13:00.707880+00:00` | 180 seconds | Missing request recovered successfully |
| FlaCGEC | 112 | D / T1 | `2026-09-20T19:29:20.980663+00:00` | 300 seconds | Missing request recovered successfully |

These are **transport failures, not format retries**. The resumed run reused
completed requests and retried the missing source-stage requests; no completed
successful output was regenerated. For the two timed-out attempts, server-side
execution, token usage, reasoning usage, and finish reason remain unknown.
They are not silently counted as zero usage.

## 10. GPT boundary diagnostics and affected-subset performance

### Aggregate diagnostics

These descriptive aggregates cover all 20,213 sources, including CEFE.
Percentages use pooled numerators and denominators, not averages of
dataset percentages.

| Contrast | Changed sources | Changed corrections among changed sources | Closer to fixed proxy | Tied | Farther from fixed proxy | Correction-span overlap |
| --- | --- | --- | ---: | ---: | ---: | --- |
| P-D | 2,511 / 20,213 (12.42%) | 1,362 / 2,511 (54.24%) | 1,073 | 48 | 1,390 | 744 / 3,019 positions (24.64%) |
| I-P | 558 / 20,213 (2.76%) | 445 / 558 (79.75%) | 376 | 13 | 169 | 110 / 677 positions (16.25%) |

“Changed correction” means a different output, not necessarily a better one.
The fixed gold-informed segmentation is a proxy, not manually verified gold
word boundaries. Moving closer to it is not proof of linguistic improvement.

### Changed-boundary subsets were also evaluated

Both conditions are compared on exactly the same affected sources for each
dataset/contrast, including sources whose output did not change. The outcome
is pooled-count character micro-F0.5. Cells show **difference [95% BCa CI]**.

| Dataset | P-D subset n | P-D subset result | I-P subset n | I-P subset result |
| --- | ---: | --- | ---: | --- |
| NLPCC2018 | 257 | +0.64 [-1.69, +2.87] | 53 | -1.32 [-5.98, +4.07] |
| MuCGEC | 871 | -0.68 [-1.77, +0.42] | 203 | +0.12 [-2.16, +2.50] |
| YACLC | 125 | +0.39 [-2.65, +3.89] | 32 | -5.59 [-13.20, +0.68] |
| FlaCGEC | 166 | +2.39 [-0.81, +6.01] | 24 | -7.46 [-19.56, +1.15] |
| FCGEC | 201 | +2.49 [+0.26, +6.69] | 47 | -13.53 [-31.98, -4.09] |
| NaCGEC | 672 | +0.27 [-0.94, +1.46] | 142 | -1.18 [-4.58, +2.01] |
| NaSGEC-Exam | 213 | +2.47 [-0.23, +5.63] | 56 | -4.08 [-10.60, +0.99] |
| CEFE Track 3 | 6 | -1.05, descriptive only | 1 | +0.00, descriptive only |

The wider subset intervals establish neither a general affected-input benefit
nor a causal effect of boundary repair. Subset membership is selected by the
intervention, and the changed input also triggers another model call. Without
a matched repeat-call control, boundary effects and generation variability
cannot be isolated.

## 11. Recorded execution totals

These counts refer to the **formal experiment**, excluding pilot and
interface-probe requests. They answer the missing execution-metadata question,
not a monetary billing question.

| Stage | Successful calls | Recorded input tokens | Recorded output tokens | Recorded total tokens |
| --- | ---: | ---: | ---: | ---: |
| Raw / T0 | 20,213 | 2,506,847 | 788,144 | 3,294,991 |
| Direct / T1 | 20,213 | 3,331,345 | 787,053 | 4,118,398 |
| Projected / T2 | 2,511 | 432,662 | 111,078 | 543,740 |
| Iterative / T3 | 558 | 99,094 | 26,713 | 125,807 |
| **Total reported** | **43,495** | **6,369,948** | **1,712,988** | **8,082,936** |

Projection and iteration add **3,069 successful calls**, or **15.18%** relative
to 20,213 Direct calls. Of the source sentences, **17,702 stop after Direct**,
**1,953 stop after Projected**, and **558 reach Iterative**.

GPT convergence uses the normalized source character sequence and
inter-character boundary vector. It records no whitespace-only additional
calls. The older two DeepSeek and three Kimi whitespace-triggered calls remain
in their historical outputs; they are not retroactively removed.

The two unreported-usage timeouts are additional attempts, not additional
evaluated outputs. The token total above is known reported usage, not a claim
that the timed-out attempts consumed nothing.

## 12. Interpretation that answers the main scientific concern

The completed results do not leave GPT as an untested exception. They support
a narrower, evidence-based account:

1. Direct WB improves the primary GPT score on six of seven formal datasets
   under the specified 95% criterion.
2. Single-pass projection has a positive primary interval on FCGEC only, and
   that direction is sensitive to BCa versus percentile construction. The
   word-level secondary metric supports projection gains on three datasets.
3. Further iteration has no positive primary interval and significantly
   decreases FCGEC performance.
4. Nine of the 14 GPT refinement comparisons are equivalent within the chosen
   half-point tolerance; the others cannot be declared equivalent.
5. These results concern saved outputs under the tested prompting and stopping
   policy. Sentence resampling does not capture repeated-decoding variability,
   document/learner clustering, or an isolated causal effect of word boundaries.

Suggested concise response:

> The GPT statistics are available now: the same 50,000-replicate paired
> bootstrap gives a positive primary projection effect only on FCGEC, and
> that result is sensitive to the interval method. Further iteration
> significantly lowers its FCGEC score, while 9 of the 14 refinement
> comparisons meet the specified half-point equivalence criterion. The access
> dates, source coverage, cleaning, retry/fallback records, and diagnostics
> have also been verified. I've put the complete answers and tables in this
> separate document. The one setting we cannot give a numeric value for is
> the provider-controlled output cap; the verified 8,192-token limit is for
> input, not output.

## 13. Evidence and scope

The full-precision results underlying the rounded tables are preserved; no
conclusion is decided from rounded endpoints.

| Evidence | Original project-relative source |
| --- | --- |
| GPT primary intervals and equivalence | `paper/arr_october_2026/gpt56_sol_none/bootstrap_primary.csv` |
| GPT secondary intervals | `paper/arr_october_2026/gpt56_sol_none/bootstrap_secondary.csv` |
| Absolute scores | `paper/arr_october_2026/gpt56_sol_none/scores.tsv` |
| Run-input hashes and completed validation | [Input manifest](gpt56_sol_none/input_manifest.json), [sanitized verification](gpt_statistics_revision_20260928/evidence/sol_verification_summary.sanitized.json), and [sanitized final validation](gpt_statistics_revision_20260928/evidence/sol_final_validation.sanitized.json) |
| Boundary and changed-subset diagnostics | `runs/gpt_5_6_sol_copilot_nothinking/paired_analysis/changed_boundary_diagnostics.csv` |
| Generation settings | `runs/gpt_5_6_sol_copilot_nothinking/generation_config.json` |
| Recorded invocation metadata | Formal `*.requests.jsonl` journals under `runs/gpt_5_6_sol_copilot_nothinking/artifacts/` |
| Previously saved output-cap check | `runs/gpt_5_6_sol_copilot_nothinking/interface_probe.json` |
| Verified, nonfinancial evidence extracts | `paper/arr_october_2026/gpt_statistics_revision_20260928/evidence/` |

Paths under `runs/` identify local-only research artifacts; the raw journals,
predictions, and task-local snapshots are not bundled. The evidence-extraction
manifest named below is also local-only; its recorded hash is retained as
historical provenance, not as a claim that the manifest is published here.

The original local primary CSV SHA256 (before Git line-ending normalization) is
`e455ab89c9c07b9a77c5515fe194be2c9121e49cde1ab072939641a57b9eecca`.
The evidence-extraction manifest SHA256 is
`1d06242608c9c9182da24117e7b6dfb4c04d403afdfd3d42dc71ac035c4bfd8d`.

**Only this Markdown answer is produced for the present request.** No original
manuscript, result values, historical predictions, or evaluation protocol is
changed. This response does not claim that the original manuscript has already
been updated. It supplies the answers and evidence for the authors to use.
