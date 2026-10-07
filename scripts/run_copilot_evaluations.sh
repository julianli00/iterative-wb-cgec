#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
RUN_ROOT="${RUN_ROOT:-$ROOT/runs/gpt_6_astra_copilot_default}"
WB_REPO="${WB_REPO:-$ROOT/external_tools/chinese-wb-fixing}"
SHAPE_TABLE="${SHAPE_TABLE:-$ROOT/external_tools/wb-shape-data/triplet_no_dup_threshold.csv}"

export CGEC_RUN_NAMES_FILE="$RUN_ROOT/run_names.json"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
export TOKENIZERS_PARALLELISM=false
export PYTHONDONTWRITEBYTECODE=1

if (( $# )); then
  set -- --datasets "$@"
fi

run() {
  printf '\n+ %q' "$@"
  printf '\n'
  "$@"
}

cd "$ROOT"

run "$PYTHON_BIN" scripts/prepare_gold_source_segmentations.py \
  --target-normalization none --wb-repo "$WB_REPO" \
  --shape-table "$SHAPE_TABLE" "$@"

run "$PYTHON_BIN" scripts/run_projection_m2_evaluation.py \
  --python "$PYTHON_BIN" --target-normalization none \
  --wb-repo "$WB_REPO" --shape-table "$SHAPE_TABLE" \
  --output-root "$RUN_ROOT/projection_character_m2" \
  --baseline-root "$RUN_ROOT/cherrant_baseline" "$@"

run "$PYTHON_BIN" scripts/run_projection_word_m2_evaluation.py \
  --python "$PYTHON_BIN" --target-normalization none \
  --character-cache "$RUN_ROOT/projection_character_m2/alignment_cache.sqlite3" \
  --output-root "$RUN_ROOT/projection_word_m2" "$@"

run "$PYTHON_BIN" scripts/run_character_gleu_evaluation.py \
  --output "$RUN_ROOT/character_gleu" "$@"

run "$PYTHON_BIN" scripts/run_word_gleu_evaluation.py \
  --target-normalization none --source-policy condition \
  --output "$RUN_ROOT/word_gleu_condition" "$@"
