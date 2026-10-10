# Iterative WB-CGEC Evaluation

This repository runs and evaluates iterative T0--T3 Chinese grammatical error
correction (CGEC) experiments with a projection-based word-boundary protocol.
The evaluation scripts reuse saved model outputs and do not call an LLM.

Latest statistical documentation (2026-09-29):
[GPT-5.6 Sol statistics, execution records, and limitations](paper/arr_october_2026/GPT_STATISTICS_ANSWERS_20260929.md).
The full manuscript, Overleaf sources, and delivery archives remain local-only
and are not included in this public repository.

For user-facing results, use the
[Kimi / DeepSeek / GPT-5.6 Sol results and parameters](paper/arr_october_2026/KIMI_DEEPSEEK_GPT56_EVALUATION_RESULTS.md).
It gives each model a separate chapter with recorded calling parameters and
all four metrics under R/D/P/I. Current Word GLEU uses the revised
S1/S1/S2/S3 source policy, not the archived fixed-source values.

**Additional-experiment progress (2026-10-10):**
[MuCGEC dev first additional experiment results](paper/arr_october_2026/mucgec_dev_gold_first/MuCGEC_Dev_First_Additional_Experiment_Results.md)
and [protocol](docs/MUCGEC_GOLD_REFERENCE_EXPERIMENT.md).
DeepSeek/Kimi R/D/P are complete on 1,079 selected single-reference pairs,
separate from the historical three-model test/validation results above.
Output evaluation now uses Target-compatible LTP/base; generation D_input
still uses LTP/small and P_input retains its original supplied-Target
projection. All 1,079 Target boundaries reproduce, and the previous 113
same-text tokenization mismatches across 35 sources are resolved. Generation
inputs/outputs and character scores are unchanged.

These are descriptive results, with no new significance or equivalence test.
The paper retains its negative-result framing; the second R_output-projection
experiment is not planned, and human-annotated Target WB remains future work.
Only code, synthetic tests, and aggregate records are published for this
additional experiment; its MuCGEC CSV and sentence-level artifacts remain
withheld under the [dataset restrictions](data/benchmarks/README.md).

## Final protocol

- T0: raw learner sentence
- T1: direct LTP word-boundary input
- T2: first projected-boundary input
- T3: second projected-boundary input, with converged rows carried forward
- Character and word M2: projection-derived M/R/U/W annotations with linked
  long-distance order changes reported separately as `WO`
- Long-distance one-block order changes: reciprocal linked U--M records, scored
  once and reported as `WO` (the internal logical key remains `W-LD`)
- GLEU: character and word 1--4 grams with sentence-level select-best over all
  references
- Normalization: remove BOM and whitespace only; no OpenCC and no BPE
- Reported thresholds: `L_max_char = 3`, `L_max_word = 3`

Word M2 evaluation first selects the closest gold reference by raw-character
Levenshtein distance (earliest-reference tie break), projects its LTP boundaries
to the learner source once, and shares that fixed source segmentation across
T0--T3.

**Word-GLEU revision, 2026-09-19:** T0/Raw and T1/Direct use saved direct-LTP
`S1`; T2/Projected uses saved `S2`; T3/Iterative uses saved `S3`. Hypotheses and
all complete references still use the same LTP installation. Historical
fixed-source word-GLEU results are preserved, not overwritten or relabelled.
The revised Kimi/DeepSeek results and exact offline reproduction commands are in
[`KIMI_DEEPSEEK_REVISED_WORD_GLEU_20260919.md`](paper/arr_october_2026/KIMI_DEEPSEEK_REVISED_WORD_GLEU_20260919.md).
The [complete four-metric report](paper/arr_october_2026/KIMI_DEEPSEEK_FOUR_METRICS_REVISED_WORD_GLEU_20260919.md)
combines these new scores with unchanged corrected M2 and character GLEU.

## Reproduce the current evaluation

### Dataset availability

All eight prepared source/reference pairs exist in the original local research
workspace: 20,213 sources and 38,000 complete references in 16 files.
**Only the two FCGEC validation files are published here**:
[source plus first reference](data/benchmarks/prepared/fcgec/validation/pipeline.tsv)
and [all references](data/benchmarks/prepared/fcgec/validation/gold.para),
covering 2,000 sources and 2,550 complete references.

FCGEC retains its upstream Apache 2.0 license and its separate
**noncommercial, academic-research-only data-use conditions**. The other
seven datasets' 14 prepared files are not published: redistribution is
restricted or permission has not been established. See the
[dataset availability, publisher access, and licensing guide](data/benchmarks/README.md).
Public download access alone is not redistribution permission.

### Local prerequisites

The current runner uses condition-specific word GLEU with S1/S1/S2/S3.
Historical fixed-source outputs remain separate; reproducing that policy
requires explicitly selecting `--source-policy fixed-gold` in the word-GLEU
evaluator and `--word-gleu-source-policy fixed-gold` in its audits/reports.
Do not mix the two policies.

These commands require the remaining separately obtained benchmark data, saved model
outputs, cached model assets, and an environment containing LTP, PyTorch,
Transformers, and the local WB alignment dependencies. A fresh public clone
includes the FCGEC validation source/reference pair, but not those other
research artifacts:

```bash
PYTHON_BIN=/path/to/python \
  ./scripts/run_final_projection_evaluations.sh
```

The runner defaults to the local WB repository and shape table configured in
`scripts/projection_character_m2.py`. Set `WB_REPO` and `SHAPE_TABLE` to
override them. Hugging Face and Transformers are put in offline mode so the
cached LTP/BERT assets are used reproducibly.

## Current formal results

- `paper/arr_october_2026/KIMI_DEEPSEEK_GPT56_EVALUATION_RESULTS.md`:
  three independent model chapters, recorded parameters, and revised evaluation tables
- `paper/arr_october_2026/kimi_deepseek_gpt56_evaluation_results.tsv`:
  model-grouped full-precision scores for all four metrics and conditions
- `paper/arr_october_2026/kimi_deepseek_gpt56_call_parameters.tsv`:
  explicit settings, documented defaults, unexposed values, and evidence sources

## Historical reports and audit archives

These files are retained for provenance, not as the default formal result
presentation. In particular, old fixed-source word-GLEU values in the legacy
reports must not replace the revised Word GLEU in the current tables above.

- `paper/arr_october_2026/GPT56_SOL_NONTHINKING_RESULTS.md`:
  archived detailed Sol experiment report
- `paper/arr_october_2026/gpt56_sol_none/`: compact full-precision tables,
  paired statistics, input hashes, and experiment audit artifacts
- `paper/arr_october_2026/KIMI_DEEPSEEK_REVISED_WORD_GLEU_20260919.md`:
  revised condition-source word GLEU, paired intervals, JSONL hashes, and audit
- `paper/arr_october_2026/KIMI_DEEPSEEK_FOUR_METRICS_REVISED_WORD_GLEU_20260919.md`:
  complete two-model results with unchanged corrected M2 and character GLEU
- `paper/arr_october_2026/TABLES_AND_ANALYSIS.md`: historical consolidated
  analysis; its fixed-source word-GLEU columns are explicitly superseded
- `paper/arr_october_2026/PAPER_TABLES.tex` and
  `paper/arr_october_2026/table_3_model_configuration.tsv`: compact historical
  two-model tables, not the current three-model configuration
- `runs/FINAL_PROJECTION_EVALUATIONS.md`: historical human-readable results
- `runs/FINAL_PROJECTION_EVALUATIONS.tsv`: historical machine-readable table
- `runs/PAPER_SECTION_5_3_6_INPUTS.md`: historical manuscript values and wording
- `runs/final_projection_audit/AUDIT.md`: artifact and invariant audit
- `runs/final_alignment_examples/QUALITATIVE_ALIGNMENT_EXAMPLES.md`: five
  manually checked ChERRANT/projection alignment examples
- `runs/sections_6_7_analysis/PAPER_SECTIONS_6_7.md`: validated error analysis,
  operation results, convergence, reference density, and paper-ready wording
- `runs/kimi_k2_6/RESULTS.md`: historical Kimi K2.6 evaluation summary
- `runs/kimi_k2_6/KIMI_VS_DEEPSEEK.md`: historical Kimi/DeepSeek comparison

The historical audit covers all 20,213 saved DeepSeek rows, all M2 and GLEU result
cells, fixed source segmentation, linked-movement validity, round-trip target
reconstruction, and threshold sensitivity.

## Generic tokenized M2 tool

The independent [generic M2 pipeline](docs/GENERIC_TOKENIZED_M2.md) extracts
tokenized source/reference pairs and generates generic M/R/U/W annotations
using local Transformer alignment, including linked long-distance movements.
See the [historical v1 conversion report](docs/GENERIC_M2_ENGLISH_RUN_20261006.md)
for output coverage and limitations. Existing Chinese evaluations are unchanged.

The current [punctuation-separated v2 policy and report](docs/GENERIC_M2_PUNCTUATION_REVISION_20261006.md)
separate standalone punctuation/symbol tokens from lexical edit spans.
The documented `relabel` command reuses saved alignments without model inference;
v2 outputs are separate, and the original v1 results and cache remain unchanged.

The [v2.1 recheck](docs/GENERIC_M2_V2_RECHECK_20261006.md) documents tool guard fixes; annotation data are unchanged.

## Unit checks

The unit tests use synthetic inputs and mocked model interfaces; they do not
require raw corpora, pretrained model weights, or correction API calls.
The full suite uses NumPy, SciPy, requests, Node.js 22.12 or newer, and these
separately obtained scorer sources under ignored `external_tools/`:

| Dependency | Pinned source | Required local location |
| --- | --- | --- |
| ChERRANT comparator | [MuCGEC `39221934ee4ccf07801879136a75dd7e11319977`](https://github.com/HillZhang1999/MuCGEC/tree/39221934ee4ccf07801879136a75dd7e11319977) | `external_tools/MuCGEC/scorers/ChERRANT/compare_m2_for_evaluation.py` |
| ERRANT comparator | [ERRANT v3.0.2](https://github.com/chrisjbryant/errant/tree/v3.0.2) | `external_tools/errant/errant/commands/compare_m2.py` |
| Multi-reference GLEU | [`d550c76dd66228eb2c05b197efc49040a2dafe37`](https://github.com/jungyeul/multi-reference-GLEU/tree/d550c76dd66228eb2c05b197efc49040a2dafe37) | `external_tools/multi-reference-GLEU/` |

Retain the upstream licenses. The GLEU wrapper also requires the recorded
tokenization/cache correction: `set_tokenization` updates the module-global
`split_ngram` and clears `make_n_accum`, `ngram_counter`, `split_char_ngram`,
and `split_word_ngram` caches when switching units. Unpatched upstream GLEU
is not the implementation used by the archived evaluations.

```bash
python3 -m unittest discover -s tests -v
node --test scripts/copilot/gec_bridge.test.mjs
```

## Run a model

Create a local `.env` from `.env.example`, then run the provider-neutral
scoreboard driver. For example:

```bash
set -a
source .env
set +a
python3 scripts/run_model_scoreboard_t3.py \
  --model "$LLM_MODEL" \
  --base-url "$LLM_BASE_URL" \
  --thinking "$LLM_THINKING" \
  --temperature "$LLM_TEMPERATURE" \
  --python /path/to/python
```

## Public scope

The prepared benchmark manifest and per-split metadata are versioned, together
with source, tests, compact aggregate scores, calling parameters, and statistical
summaries. The two FCGEC validation source/reference files are the sole
newly published dataset pair and retain their upstream license and data-use
conditions. Historical compact artifacts already in Git are retained
separately from the current three-model presentation.

Other raw corpora and gold text, full per-sentence generations and score exports,
third-party repositories, alignment caches, model weights, request logs,
credentials, financial records, original PDFs, full manuscript sources, and
delivery archives are not added to this public snapshot. Paths under `runs/`
in the new reports usually identify local-only reproducibility inputs, not
files supplied by a fresh clone. Published metadata uses portable paths while
preserving the recorded scores, settings, and input hashes.
