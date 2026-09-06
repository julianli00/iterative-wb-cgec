# Iterative WB-CGEC Evaluation

This repository runs and evaluates iterative T0--T3 Chinese grammatical error
correction (CGEC) experiments with a projection-based word-boundary protocol.
The evaluation scripts reuse saved model outputs and do not call an LLM.

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

Word evaluation first selects the closest gold reference by raw-character
Levenshtein distance (earliest-reference tie break), projects its LTP boundaries
to the learner source once, and shares that fixed source segmentation across
T0--T3 and both word metrics.

## Reproduce the evaluation

Use the environment that contains LTP, PyTorch, Transformers, and the local WB
alignment dependencies:

```bash
PYTHON_BIN=/path/to/python \
  ./scripts/run_final_projection_evaluations.sh
```

The runner defaults to the local WB repository and shape table configured in
`scripts/projection_character_m2.py`. Set `WB_REPO` and `SHAPE_TABLE` to
override them. Hugging Face and Transformers are put in offline mode so the
cached LTP/BERT assets are used reproducibly.

## Main outputs

- `runs/FINAL_PROJECTION_EVALUATIONS.md`: complete human-readable results
- `runs/FINAL_PROJECTION_EVALUATIONS.tsv`: machine-readable long table
- `runs/PAPER_SECTION_5_3_6_INPUTS.md`: manuscript-ready values and wording
- `runs/final_projection_audit/AUDIT.md`: artifact and invariant audit
- `runs/final_alignment_examples/QUALITATIVE_ALIGNMENT_EXAMPLES.md`: five
  manually checked ChERRANT/projection alignment examples
- `runs/sections_6_7_analysis/PAPER_SECTIONS_6_7.md`: validated error analysis,
  operation results, convergence, reference density, and paper-ready wording
- `runs/kimi_k2_6/RESULTS.md`: Kimi K2.6 evaluation summary
- `runs/kimi_k2_6/KIMI_VS_DEEPSEEK.md`: controlled Kimi/DeepSeek comparison

The final audit covers all 20,213 saved DeepSeek rows, all M2 and GLEU result
cells, fixed source segmentation, linked-movement validity, round-trip target
reconstruction, and threshold sensitivity.

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

The prepared benchmark manifest and per-split metadata are versioned. Raw
corpora, third-party repositories, full per-sentence generations, alignment
caches, and model assets are intentionally excluded because of size, privacy,
and redistribution constraints. The compact final tables and audits listed
above are retained in Git.
