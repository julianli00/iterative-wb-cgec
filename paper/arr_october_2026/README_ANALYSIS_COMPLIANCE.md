# README analysis compliance

> The historical analysis documented here retains fixed-source word GLEU.
> For the approved 2026-09-19 S1/S1/S2/S3 revision, see
> [the revised Kimi/DeepSeek report](KIMI_DEEPSEEK_REVISED_WORD_GLEU_20260919.md)
> and `word_gleu_condition_validation_20260919.json`. The three unchanged
> metrics and their 144 contrast rows were reproduced; historical outputs
> remain intact.

This is a historical compliance record. Bare artifact filenames in the
evidence column refer to local-only exports under `runs/paired_bootstrap_analysis/`,
not bundled files. Current compact public scores, parameters, and statistics
are linked from the [three-model report](KIMI_DEEPSEEK_GPT56_EVALUATION_RESULTS.md).

| Requirement | Status | Evidence |
| --- | --- | --- |
| Freeze seed, replicates, scale, margins, contrasts, and inferential datasets | Complete | `analysis_config.json` |
| Reuse complete saved R/D/P/I outputs without post-hoc exclusions | Complete | `sentence_level_scores.tsv` and `validation.log` |
| Preserve identical complete gold references and annotator order across character/word M2 | Complete | `validation.log` |
| Sentence-local select-best for complete edit references | Complete | `scripts/movement_aware_compare.py` and `scorer_selection_audit.tsv` |
| Independent character/word GLEU select-best | Complete | `sentence_level_scores.tsv` and cached-summary validation |
| Paired source-level resampling with corpus micro-F0.5 | Complete | `bootstrap_primary.csv` and `bootstrap_secondary.csv` |
| 50,000 paired 95%/90% BCa intervals | Complete | bootstrap CSV files |
| Ordinary percentile robustness check | Complete | bootstrap CSV flags and paper report |
| Practical equivalence at +/-0.50 with +/-0.25 and +/-1.00 sensitivity | Complete | `equivalence_sensitivity.csv` |
| CEFE Track 3 treated descriptively | Complete | bootstrap CSV files |
| Boundary coverage, split/merge direction, changed-output, changed-subset performance | Complete | `changed_boundary_diagnostics.csv` |
| Proximity to fixed gold-informed boundaries | Complete | `changed_boundary_diagnostics.csv` |
| Overlap with correction-relevant spans | Complete | `changed_boundary_diagnostics.csv` |
| Convergence, calls, tokens, and efficiency | Complete | `convergence_and_cost.csv` |
| Reproducibility and software versions | Complete | `analysis_config.json` and `validation.log` |

## Recorded limitations

- No reliable document, essay, or learner cluster identifiers are available, so the independent resampling unit is the source sentence.
- Only one saved decode exists per model, source, and condition; the intervals do not quantify repeated-API sampling variability.
- Provider pricing snapshots were not archived, so monetary costs are not compared. Calls and recorded tokens are reported instead.
- DeepSeek omitted `max_tokens`, so the documented 8,192-token non-thinking default applied; its longest saved completion was 200 tokens. Kimi's longest saved completion was 259 of its 512-token cap. Historical finish reasons were not stored, but the observed completion counts remain well below both caps, and the evaluation code performs no post-hoc truncation.
- Five historical calls were triggered by whitespace-only segmentation formatting despite unchanged normalized boundary vectors. Those outputs remain in the faithful analysis, while future pipeline runs now use normalized boundary signatures for convergence.
- The supplied draft's cached M2 scores use the historical corpus-greedy reference selector. They are exactly reproducible, but 10/128 displayed cells change under the README-required sentence-local selector; corrected values are in the paper report.
