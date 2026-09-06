#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
export TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}"

alignment_args=()
if [[ -n "${WB_REPO:-}" ]]; then
  alignment_args+=(--wb-repo "$WB_REPO")
fi
if [[ -n "${SHAPE_TABLE:-}" ]]; then
  alignment_args+=(--shape-table "$SHAPE_TABLE")
fi

run() {
  printf '\n+ %q' "$@"
  printf '\n'
  "$@"
}

cd "$ROOT"

run "$PYTHON_BIN" -B scripts/prepare_gold_source_segmentations.py \
  --target-normalization none "${alignment_args[@]}"

run "$PYTHON_BIN" -B scripts/run_projection_m2_evaluation.py \
  --python "$PYTHON_BIN" --target-normalization none "${alignment_args[@]}"

run "$PYTHON_BIN" -B scripts/run_projection_word_m2_evaluation.py \
  --python "$PYTHON_BIN" --target-normalization none

run "$PYTHON_BIN" -B scripts/run_character_gleu_evaluation.py
run "$PYTHON_BIN" -B scripts/run_word_gleu_evaluation.py \
  --target-normalization none

for l_max in 2 4; do
  run "$PYTHON_BIN" -B scripts/run_projection_m2_evaluation.py \
    --python "$PYTHON_BIN" --target-normalization none \
    --l-max-char "$l_max" \
    --output-root "runs/threshold_sensitivity/character_lmax${l_max}" \
    "${alignment_args[@]}"
  run "$PYTHON_BIN" -B scripts/run_projection_word_m2_evaluation.py \
    --python "$PYTHON_BIN" --target-normalization none \
    --l-max-word "$l_max" \
    --output-root "runs/threshold_sensitivity/word_lmax${l_max}"
done

run "$PYTHON_BIN" -B -m unittest discover -s tests -v
run "$PYTHON_BIN" -B scripts/audit_final_projection_artifacts.py
run "$PYTHON_BIN" -B scripts/audit_long_distance_word_order.py
run "$PYTHON_BIN" -B scripts/build_final_projection_report.py
