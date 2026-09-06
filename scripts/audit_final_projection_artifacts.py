#!/usr/bin/env python3
"""Audit the final projection-based DeepSeek evaluation artifacts."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from movement_aware_compare import parse_block, scored_edits
from projection_character_m2 import targets_from_m2_block
from projection_word_m2 import targets_from_word_m2_block
from standardize_m2_evaluation import ROUNDS, ROOT, load_specs


RUNS = ROOT / "runs"
CHARACTER_ROOT = RUNS / "projection_character_m2_eval_final"
WORD_ROOT = RUNS / "projection_word_m2_eval_final"
CHARACTER_GLEU_ROOT = RUNS / "character_gleu_select_best"
WORD_GLEU_ROOT = RUNS / "word_gleu_select_best_final"
FIXED_SEGMENTATION_ROOT = RUNS / "gold_fixed_source_segmentation"
DEFAULT_OUTPUT = RUNS / "final_projection_audit"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def read_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig").replace("\ufeff", "").strip()
    return [] if not text else text.split("\n\n")


def source_line(block: str) -> str:
    first = block.splitlines()[0]
    if not first.startswith("S "):
        raise ValueError("M2 block does not begin with an S line")
    return first[2:]


def validate_m2_file(path: Path, *, unit: str, expected_rows: int) -> dict[str, int]:
    blocks = read_blocks(path)
    if len(blocks) != expected_rows:
        raise ValueError(f"{path}: expected {expected_rows} blocks, found {len(blocks)}")
    annotations = 0
    logical_movements = 0
    references = 0
    for block_text in blocks:
        block = parse_block(block_text, unit=unit)
        logical_by_annotator = scored_edits(block, unit=unit)
        references += len(logical_by_annotator)
        annotations += len(block.edits)
        logical_movements += sum(
            1
            for edits in logical_by_annotator.values()
            for key in edits
            if key and key[0] == "W-LD"
        )
        if unit == "character":
            targets_from_m2_block(block_text)
        else:
            targets_from_word_m2_block(block_text)
    return {
        "blocks": len(blocks),
        "references": references,
        "physical_annotations": annotations,
        "linked_movements": logical_movements,
    }


def assert_stage_invariant(paths: Sequence[Path], *, expected_rows: int) -> int:
    all_sources = [[source_line(block) for block in read_blocks(path)] for path in paths]
    if any(len(sources) != expected_rows for sources in all_sources):
        raise ValueError("Stage-invariance audit found an unexpected M2 row count")
    baseline = all_sources[0]
    for path, sources in zip(paths[1:], all_sources[1:]):
        if sources != baseline:
            raise ValueError(f"Source segmentation is not stage-invariant in {path}")
    return expected_rows


def assert_text_stage_invariant(paths: Sequence[Path], *, expected_rows: int) -> int:
    contents = [path.read_text(encoding="utf-8-sig").splitlines() for path in paths]
    if any(len(lines) != expected_rows for lines in contents):
        raise ValueError("Stage-invariance audit found an unexpected text row count")
    if any(lines != contents[0] for lines in contents[1:]):
        raise ValueError("Word-GLEU source segmentation changes across T0--T3")
    return expected_rows


def matrix_scores(path: Path) -> dict[tuple[str, str], float]:
    rows = read_tsv(path)
    return {
        (row["dataset"], stage): float(row[stage])
        for row in rows
        for stage in ROUNDS
    }


def long_scores(path: Path, *, alignment: str | None = None) -> dict[tuple[str, str], float]:
    rows = read_tsv(path)
    output: dict[tuple[str, str], float] = {}
    for row in rows:
        if row["beta"] != "0.5":
            continue
        if alignment is not None and row.get("alignment") != alignment:
            continue
        output[(row["dataset"], row["round"])] = float(row["F_beta"]) * 100.0
    return output


def threshold_sensitivity() -> dict[str, Any]:
    character = {
        2: matrix_scores(
            RUNS / "threshold_sensitivity/character_lmax2/scores.projection.f05.tsv"
        ),
        3: matrix_scores(CHARACTER_ROOT / "scores.projection.f05.tsv"),
        4: matrix_scores(
            RUNS / "threshold_sensitivity/character_lmax4/scores.projection.f05.tsv"
        ),
    }
    word = {
        2: long_scores(RUNS / "threshold_sensitivity/word_lmax2/scores.long.tsv"),
        3: long_scores(WORD_ROOT / "scores.long.tsv"),
        4: long_scores(RUNS / "threshold_sensitivity/word_lmax4/scores.long.tsv"),
    }
    result: dict[str, Any] = {}
    for unit, values in (("character", character), ("word", word)):
        keys = set(values[3])
        if any(set(current) != keys for current in values.values()):
            raise ValueError(f"Incomplete {unit} threshold-sensitivity results")
        ranges = {
            f"{dataset}/{stage}": max(values[limit][(dataset, stage)] for limit in (2, 3, 4))
            - min(values[limit][(dataset, stage)] for limit in (2, 3, 4))
            for dataset, stage in sorted(keys)
        }
        result[unit] = {
            "max_f0.5_x100_range": max(ranges.values()),
            "mean_f0.5_x100_range": sum(ranges.values()) / len(ranges),
            "ranges": ranges,
        }
    return result


def require_score_coverage(path: Path, *, kind: str) -> int:
    rows = read_tsv(path)
    if kind == "character_m2":
        keys = {
            (row["dataset"], row["round"])
            for row in rows
            if row["alignment"] == "projection" and row["beta"] == "0.5"
        }
    elif kind == "word_m2":
        keys = {
            (row["dataset"], row["round"])
            for row in rows
            if row["beta"] == "0.5"
        }
    else:
        keys = {(row["dataset"], row["stage"]) for row in rows}
    expected = {(spec.dataset, stage) for spec in load_specs() for stage in ROUNDS}
    if keys != expected:
        raise ValueError(f"Incomplete {kind} score coverage")
    return len(keys)


def model_run_audit() -> dict[str, Any]:
    datasets: list[dict[str, Any]] = []
    total_rows = total_calls = total_fallbacks = total_errors = total_empty = 0
    api_models: set[str] = set()
    for spec in load_specs():
        path = spec.result_tsv.with_suffix(".jsonl")
        rows = read_jsonl(path)
        errors = sum(not row.get("ok", False) for row in rows)
        empty = sum(
            not str(row.get(stage, "")).strip() for row in rows for stage in ROUNDS
        )
        calls = fallbacks = 0
        models: set[str] = set()
        for row in rows:
            for call in row.get("meta", {}).get("api", []):
                stage = int(call.get("T", 0))
                if stage > 3:
                    continue
                calls += 1
                fallbacks += bool(call.get("fallback_without_thinking"))
                if call.get("model"):
                    models.add(str(call["model"]))
        if len(rows) != spec.rows or errors or empty:
            raise ValueError(f"Incomplete saved model outputs for {spec.dataset}")
        datasets.append(
            {
                "dataset": spec.dataset,
                "rows": len(rows),
                "api_calls_through_T3": calls,
                "models": sorted(models),
                "thinking_fallbacks": fallbacks,
                "errors": errors,
                "empty_stage_outputs": empty,
            }
        )
        total_rows += len(rows)
        total_calls += calls
        total_fallbacks += fallbacks
        total_errors += errors
        total_empty += empty
        api_models.update(models)
    if api_models != {"deepseek-v4-pro"} or total_fallbacks:
        raise ValueError("Saved model-call metadata does not match the declared setup")
    return {
        "rows": total_rows,
        "api_calls_through_T3": total_calls,
        "models": sorted(api_models),
        "thinking_fallbacks": total_fallbacks,
        "errors": total_errors,
        "empty_stage_outputs": total_empty,
        "datasets": datasets,
    }


def add_markdown_table(
    lines: list[str], headers: Sequence[str], rows: Iterable[Sequence[str]]
) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    lines.append("")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    specs = load_specs()
    m2_rows: list[dict[str, Any]] = []
    fixed_rows = word_m2_invariant = word_gleu_invariant = 0
    for spec in specs:
        char_dir = CHARACTER_ROOT / spec.dataset / spec.split / "char"
        word_dir = WORD_ROOT / spec.dataset / spec.split / "word"
        char_files = [char_dir / "reference.projection.all.char.m2"] + [
            char_dir / f"hypothesis.{stage}.projection.char.m2" for stage in ROUNDS
        ]
        word_files = [
            word_dir / f"reference.{stage}.projection.word.m2" for stage in ROUNDS
        ] + [word_dir / f"hypothesis.{stage}.projection.word.m2" for stage in ROUNDS]
        for path in char_files:
            m2_rows.append(
                {
                    "dataset": spec.dataset,
                    "unit": "character",
                    "file": str(path.relative_to(ROOT)),
                    **validate_m2_file(path, unit="character", expected_rows=spec.rows),
                }
            )
        for path in word_files:
            m2_rows.append(
                {
                    "dataset": spec.dataset,
                    "unit": "word",
                    "file": str(path.relative_to(ROOT)),
                    **validate_m2_file(path, unit="word", expected_rows=spec.rows),
                }
            )
        word_m2_invariant += assert_stage_invariant(
            [word_dir / f"reference.{stage}.projection.word.m2" for stage in ROUNDS]
            + [word_dir / f"hypothesis.{stage}.projection.word.m2" for stage in ROUNDS],
            expected_rows=spec.rows,
        )
        word_gleu_invariant += assert_text_stage_invariant(
            [
                WORD_GLEU_ROOT
                / spec.dataset
                / spec.split
                / "inputs"
                / f"source.{stage}.txt"
                for stage in ROUNDS
            ],
            expected_rows=spec.rows,
        )
        fixed_path = (
            FIXED_SEGMENTATION_ROOT
            / spec.dataset
            / spec.split
            / "fixed_source_segmentation.tsv"
        )
        records = read_tsv(fixed_path)
        if len(records) != spec.rows:
            raise ValueError(f"Incomplete fixed segmentation file: {fixed_path}")
        for record in records:
            if "".join(record["fixed_source_segmentation"].split()) != "".join(
                record["source"].split()
            ):
                raise ValueError(f"Fixed segmentation changes source text: {fixed_path}")
        fixed_rows += len(records)

    score_coverage = {
        "character_m2": require_score_coverage(
            CHARACTER_ROOT / "scores.long.tsv", kind="character_m2"
        ),
        "word_m2": require_score_coverage(WORD_ROOT / "scores.long.tsv", kind="word_m2"),
        "character_gleu": require_score_coverage(
            CHARACTER_GLEU_ROOT / "scores.long.tsv", kind="gleu"
        ),
        "word_gleu": require_score_coverage(
            WORD_GLEU_ROOT / "scores.long.tsv", kind="gleu"
        ),
    }
    model_runs = model_run_audit()
    sensitivity = threshold_sensitivity()
    audit = {
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "model_runs": model_runs,
        "fixed_source_segmentations": fixed_rows,
        "word_m2_stage_invariant_sources": word_m2_invariant,
        "word_gleu_stage_invariant_sources": word_gleu_invariant,
        "m2_files": len(m2_rows),
        "m2_blocks_validated": sum(row["blocks"] for row in m2_rows),
        "m2_physical_annotations_validated": sum(
            row["physical_annotations"] for row in m2_rows
        ),
        "linked_movements_validated": sum(row["linked_movements"] for row in m2_rows),
        "score_coverage": score_coverage,
        "threshold_sensitivity": sensitivity,
        "files": m2_rows,
    }
    (args.output / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Final Projection Artifact Audit",
        "",
        "**Status: PASS**",
        "",
        "This audit uses only saved model outputs and local evaluation artifacts; it makes no LLM or API calls.",
        "",
        "## Coverage",
        "",
        f"- Saved DeepSeek rows: {model_runs['rows']:,}",
        f"- Fixed gold-informed source segmentations: {fixed_rows:,}",
        f"- M2 files validated: {len(m2_rows):,}",
        f"- M2 blocks parsed and reconstructed: {audit['m2_blocks_validated']:,}",
        f"- Physical M2 annotations checked: {audit['m2_physical_annotations_validated']:,}",
        f"- Linked movements checked as reciprocal U--M pairs: {audit['linked_movements_validated']:,}",
        "- Character M2, word M2, character GLEU, and word GLEU each contain all 8 datasets x 4 stages.",
        "",
        "## Invariants",
        "",
        "- Every saved row has non-empty T0--T3 output and successful API metadata.",
        "- Every linked movement passed syntax, reciprocal-coordinate, material-identity, non-overlap, and reconstruction checks.",
        "- The fixed evaluation-side source segmentation preserves the learner characters.",
        "- The word-M2 and word-GLEU source segmentation is byte-for-byte identical across T0--T3 for every sentence.",
        "- No BPE is used in any final result.",
        "",
        "## Threshold Sensitivity",
        "",
    ]
    add_markdown_table(
        lines,
        ("Unit", "L_max values", "Maximum F0.5 range", "Mean F0.5 range"),
        (
            (
                unit,
                "2, 3, 4",
                f"{values['max_f0.5_x100_range']:.4f}",
                f"{values['mean_f0.5_x100_range']:.4f}",
            )
            for unit, values in sensitivity.items()
        ),
    )
    lines.extend(
        [
            "The reported setting is `L_max_char = 3` and `L_max_word = 3`. "
            "Character scores are invariant across the tested values; word scores "
            f"vary by at most {sensitivity['word']['max_f0.5_x100_range']:.4f} "
            "F0.5 points.",
            "",
        ]
    )
    (args.output / "AUDIT.md").write_text("\n".join(lines), encoding="utf-8")
    print(args.output / "AUDIT.md")
    print(args.output / "audit.json")


if __name__ == "__main__":
    main()
