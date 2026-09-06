# Sections 6-7 Analysis Package

**Status: complete for the saved DeepSeek outputs.** No LLM/API calls were made.

## 1. Evaluation correctness

All 128 reported Table 5-6 cells were independently reconstructed from final M2 and GLEU inputs. Maximum discrepancies are 0 for character/word F0.5, below 5e-7 points for character GLEU, and 0 for word GLEU. Stage mapping, carry-forward convergence, multi-reference use, fixed word segmentation, and no-BPE normalization also pass. The surprising ranking is therefore present in the saved outputs under the stated protocol, rather than being caused by a table transcription or scorer invocation error.

## 2. Manual comparator validation

The controlled two-sentence fixture gives TP/FP/FN = 2/1/1 and F0.5 = 0.6667, exactly matching the hand calculation. A reciprocal long-distance M+U pair contributes one `WO` item; a mismatched destination contributes one FP and one FN.

## 3. Main result interpretation

Direct-WB improves character F0.5 on 7/8 datasets and word F0.5 on 6/8 datasets. The change is precision-driven and accompanied by lower recall, so visible boundaries make DeepSeek substantially more conservative. Raw outputs have a source-copy rate of only 5.83% and a mean character distance of 3.646, compared with 33.53% and 1.773 for Direct-WB. Raw is therefore more aggressive, not more conservative.

GLEU favors Raw on 5/8 datasets at both character and word levels. This does not contradict the edit scorer mechanically: GLEU rewards reference-supported n-gram overlap and can reward aggressive partially correct rewriting, whereas exact edit F0.5 rewards localized agreement and weights precision more heavily. Projection-affected rows are mixed across datasets, so dilution by converged carry-forward rows is not the sole explanation.

## 4. Projection and convergence

The first projection changes boundaries for 1,666/20,213 sources (8.24%). 18,547 stop after Direct-WB, 1,414 after Projected-WB, and only 252 reach T3. Among changed S2 inputs, 527/1,666 (31.63%) change the correction. Among changed S3 inputs, 212/252 (84.13%) change it. There are 194 S1-S2-S1 two-cycles, handled by Kmax rather than reported as convergence. Projection performs 1,016 splits and 1,295 merges, confirming bidirectional boundary repair.

The dominant empirical effect is Raw to Direct-WB. Projection and further iteration usually alter only a small subset and have small, non-monotonic aggregate effects. This supports a mixed or negative iterative result, not a universal monotonic-improvement claim.

## 5. Operation-level analysis

The final reporting inventory is M, R, U, W, and WO. W is a conventional bounded short-range order edit; WO is one validated long-distance movement represented physically by linked M+U records. Category TP/FP/FN totals reconstruct every aggregate score exactly. See `OPERATION_LEVEL_RESULTS.md` and `operation_scores.long.tsv`.

At character level, Direct-WB minus Raw is +5.25 for M, +7.92 for R, +2.93 for U, -5.90 for W, and -3.48 for WO. At word level, the corresponding deltas are +4.49, +5.54, +1.45, -7.68, and -0.37. Thus the aggregate Direct-WB gain comes from M/R/U rather than order changes; W and WO become worse.

## 6. Qualitative and reference analyses

Five manually inspected real examples compare ChERRANT with projection M2. In the clearest long-distance cases, projection isolates the moved constituent and retains its origin and destination, while ChERRANT places W over a large intervening span. This is qualitative evidence of representational coherence, not an aggregate alignment-accuracy claim.

`PROMPTING_CASES.md` supplies reproducibly selected success, no-effect, failure, and conservative cases. `REFERENCE_DENSITY.md` reports grouped results and a controlled first-1 through first-11 analysis on the same 178 YACLC sentences.

## Manuscript-ready conclusion

> Under the DeepSeek setting, explicit direct word boundaries consistently make correction more precise and conservative, improving edit-based F0.5 on most datasets. Projection repairs the source representation intrinsically, but it changes only 8.24% of source boundary sequences and does not yield consistent downstream gains; additional iteration is similarly small and non-monotonic. GLEU often favors the more aggressive Raw outputs, demonstrating that exact edit agreement and source-aware n-gram overlap capture different aspects of correction behavior. These findings support a mixed-result interpretation: direct boundary display is useful for precision-oriented CGEC, while automatically projected and iterative refinement require error analysis rather than a universal improvement claim.

## Remaining work outside tasks 1-6

- Run the frozen pipeline on GPT, Claude, Kimi, and Qwen to test whether the DeepSeek pattern generalizes.
- Perform the C-based-LTP versus Python-LTP comparison (the separately assigned task 7).
- Insert model identifiers/configurations and cross-model tables once those runs exist.

## Files

- `MANUAL_SCORER_VALIDATION.md`: hand-checkable WO scorer proof.
- `OPERATION_LEVEL_RESULTS.md` and `operation_scores.long.tsv`: five-category results.
- `CONVERGENCE.md` and `convergence.tsv`: dataset-level iterative diagnostics.
- `REFERENCE_DENSITY.md`, `reference_density.long.tsv`, and `yaclc_incremental_references.tsv`: reference analyses.
- `PROMPTING_CASES.md`: projection success/no-effect/failure examples.
- `../final_alignment_examples/QUALITATIVE_ALIGNMENT_EXAMPLES.md`: ChERRANT/projection alignment examples.
- `../tables_5_6_evaluation_audit/AUDIT.md`: independent Tables 5-6 reconstruction.
