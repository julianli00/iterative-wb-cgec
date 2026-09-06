# Character-based GLEU Evaluation

This run reuses the existing DeepSeek T0--T3 predictions and makes no LLM or API calls.

## Method

- Evaluator: Park's multi-reference GLEU v1 (https://doi.org/10.5281/zenodo.18206055).
- Upstream commit: `d550c76dd66228eb2c05b197efc49040a2dafe37`.
- Tokenization: Unicode characters, n-grams 1 through 4.
- Multi-reference aggregation: compute GLEU against every reference, select the highest score for each sentence, then macro-average the selected sentence scores.
- Normalization: remove BOM and all whitespace. No BPE, word segmentation, or OpenCC conversion.
- Inputs: the same prepared source/reference pairs and saved T0--T3 hypotheses used by the character M2 experiments.

## Upstream correction

The archived v1 `set_tokenization` function assigns `split_ngram` in local scope, so `--token char` silently retains word tokenization. The vendored copy changes that assignment to the module global and clears tokenization-dependent caches. Regression tests verify that an unspaced Chinese string produces individual character n-grams.

## Outputs

- `scores.compact.tsv`: one row per dataset, GLEU x 100 for T0--T3.
- `scores.long.tsv`: raw 0--1 and x100 scores by dataset and stage.
- `scores.md`: report-ready Markdown table.
- `sentence_scores.tsv`: selected score and selected reference index for every sentence and stage.
- `<dataset>/<split>/inputs/`: exact normalized source, references, and hypotheses used for scoring.
- `<dataset>/<split>/stats.json`: reference-density audit.
