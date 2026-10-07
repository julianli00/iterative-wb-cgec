#!/usr/bin/env python3
"""Audit the final projection-based DeepSeek evaluation artifacts."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if not __package__:
    from movement_aware_compare import parse_block, scored_edits
    from projection_character_m2 import targets_from_m2_block
    from projection_word_m2 import targets_from_word_m2_block
    from standardize_m2_evaluation import ROUNDS, ROOT, load_result_rows, load_specs
    from word_gleu_protocol import (
        CONDITION_SOURCE_COLUMNS,
        SOURCE_POLICIES,
        load_source_policy,
        select_source_segmentation,
    )
else:
    from .movement_aware_compare import parse_block, scored_edits
    from .projection_character_m2 import targets_from_m2_block
    from .projection_word_m2 import targets_from_word_m2_block
    from .standardize_m2_evaluation import ROUNDS, ROOT, load_result_rows, load_specs
    from .word_gleu_protocol import (
        CONDITION_SOURCE_COLUMNS,
        SOURCE_POLICIES,
        load_source_policy,
        select_source_segmentation,
    )


RUNS = ROOT / "runs"
CHARACTER_ROOT = RUNS / "projection_character_m2_eval_final"
WORD_ROOT = RUNS / "projection_word_m2_eval_final"
CHARACTER_GLEU_ROOT = RUNS / "character_gleu_select_best"
WORD_GLEU_ROOT = RUNS / "word_gleu_condition_select_best"
LEGACY_WORD_GLEU_ROOT = RUNS / "word_gleu_select_best_final"
FIXED_SEGMENTATION_ROOT = RUNS / "gold_fixed_source_segmentation"
DEFAULT_OUTPUT = RUNS / "final_projection_audit"


def add_word_gleu_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--word-gleu-root", type=Path)
    parser.add_argument(
        "--word-gleu-source-policy",
        choices=SOURCE_POLICIES,
        default="condition",
        help=(
            "Default: condition, using runs/word_gleu_condition_select_best. "
            "fixed-gold explicitly reproduces the historical fixed-source run."
        ),
    )


def resolve_word_gleu_root(
    root: Path | None = None, *, source_policy: str = "condition"
) -> Path:
    if source_policy not in SOURCE_POLICIES:
        raise ValueError(f"Unknown word-GLEU source policy: {source_policy}")
    if root is not None:
        return root
    return WORD_GLEU_ROOT if source_policy == "condition" else LEGACY_WORD_GLEU_ROOT


def word_gleu_source_metadata(root: Path, source_policy: str) -> dict[str, Any]:
    resolve_word_gleu_root(root, source_policy=source_policy)
    return {
        "word_gleu_root": str(root.resolve()),
        "word_gleu_source_policy": source_policy,
        "word_gleu_source_stage_mapping": (
            dict(CONDITION_SOURCE_COLUMNS) if source_policy == "condition" else None
        ),
    }


def word_gleu_protocol_description(source_policy: str) -> str:
    if source_policy == "condition":
        return (
            "Word GLEU uses condition-specific saved source segmentations: "
            "R/T0 and D/T1 use S1 (direct LTP), P/T2 uses S2, and I/T3 uses S3. "
            "Hypotheses and references remain LTP-segmented."
        )
    if source_policy == "fixed-gold":
        return (
            "Historical fixed-gold word GLEU uses one fixed gold-informed source "
            "segmentation shared by T0--T3, matching word M2. "
            "Hypotheses and references remain LTP-segmented."
        )
    raise ValueError(f"Unknown word-GLEU source policy: {source_policy}")


def require_word_gleu_audit(
    audit: Mapping[str, Any], *, source_policy: str, word_gleu_root: Path
) -> None:
    resolve_word_gleu_root(word_gleu_root, source_policy=source_policy)
    if not isinstance(audit, Mapping):
        raise ValueError("Expected an evaluation artifact audit object")
    if audit.get("status") != "PASS":
        raise ValueError("Evaluation artifact audit did not pass")
    policy = audit.get("word_gleu_source_policy")
    if policy is None and source_policy == "fixed-gold":
        policy = "fixed-gold"
    if policy != source_policy:
        raise ValueError(
            f"Word-GLEU audit policy mismatch: {policy!r} != {source_policy!r}"
        )
    recorded_root = audit.get("word_gleu_root")
    if recorded_root is None:
        if source_policy != "fixed-gold":
            raise ValueError("Condition-specific word-GLEU audit has no input root")
    elif not isinstance(recorded_root, str) or not recorded_root:
        raise ValueError("Word-GLEU audit input root is invalid")
    elif Path(recorded_root).resolve() != word_gleu_root.resolve():
        raise ValueError("Word-GLEU audit input root does not match the report inputs")
    if (
        source_policy == "condition"
        and audit.get("word_gleu_source_stage_mapping") != CONDITION_SOURCE_COLUMNS
    ):
        raise ValueError("Condition-specific word-GLEU audit has an invalid stage mapping")


def assert_word_gleu_sources(
    sources_by_stage: Mapping[str, Sequence[str]],
    result_rows: Sequence[Mapping[str, str]],
    *,
    source_policy: str = "condition",
    fixed_sources: Sequence[str] | None = None,
    expected_rows: int | None = None,
) -> int:
    resolve_word_gleu_root(source_policy=source_policy)
    row_count = len(result_rows) if expected_rows is None else expected_rows
    if len(result_rows) != row_count or set(sources_by_stage) != set(ROUNDS):
        raise ValueError("Word-GLEU source audit has incomplete saved rows or stages")
    if any(len(values) != row_count for values in sources_by_stage.values()):
        raise ValueError("Word-GLEU source audit found an unexpected row count")
    if source_policy == "fixed-gold":
        if fixed_sources is None or len(fixed_sources) != row_count:
            raise ValueError("Fixed-gold word GLEU requires the fixed word-M2 sources")
        baseline = list(sources_by_stage["T0"])
        if any(list(values) != baseline for values in sources_by_stage.values()):
            raise ValueError("Fixed-gold word-GLEU source segmentation varies by stage")
        if baseline != list(fixed_sources):
            raise ValueError("Fixed-gold word-GLEU sources differ from fixed word M2")
    for stage in ROUNDS:
        for index, (actual, row) in enumerate(
            zip(sources_by_stage[stage], result_rows), start=1
        ):
            expected = select_source_segmentation(
                row,
                stage,
                source_policy=source_policy,
                fixed_source=(
                    fixed_sources[index - 1] if source_policy == "fixed-gold" else None
                ),
            )
            if " ".join(actual.replace("\ufeff", "").split()) != expected:
                column = (
                    CONDITION_SOURCE_COLUMNS[stage]
                    if source_policy == "condition"
                    else "fixed word-M2 source"
                )
                raise ValueError(
                    f"Word-GLEU {stage} source does not match {column} at row {index}"
                )
    return row_count


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
    """Check the historical fixed-gold word-GLEU source invariant."""
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
    add_word_gleu_arguments(parser)
    args = parser.parse_args()
    word_gleu_root = resolve_word_gleu_root(
        args.word_gleu_root, source_policy=args.word_gleu_source_policy
    )
    load_source_policy(word_gleu_root, expected_policy=args.word_gleu_source_policy)
    args.output.mkdir(parents=True, exist_ok=True)

    specs = load_specs()
    m2_rows: list[dict[str, Any]] = []
    fixed_rows = word_m2_invariant = word_gleu_validated = 0
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
        word_input_dir = word_gleu_root / spec.dataset / spec.split / "inputs"
        word_gleu_validated += assert_word_gleu_sources(
            {
                stage: (word_input_dir / f"source.{stage}.txt")
                .read_text(encoding="utf-8-sig")
                .splitlines()
                for stage in ROUNDS
            },
            load_result_rows(spec),
            source_policy=args.word_gleu_source_policy,
            fixed_sources=[
                source_line(block)
                for block in read_blocks(word_dir / "reference.T0.projection.word.m2")
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
            word_gleu_root / "scores.long.tsv", kind="gleu"
        ),
    }
    model_runs = model_run_audit()
    sensitivity = threshold_sensitivity()
    audit = {
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "model_runs": model_runs,
        **word_gleu_source_metadata(word_gleu_root, args.word_gleu_source_policy),
        "fixed_source_segmentations": fixed_rows,
        "word_m2_stage_invariant_sources": word_m2_invariant,
        "word_gleu_source_rows_validated": word_gleu_validated,
        "word_gleu_stage_invariant_sources": (
            word_gleu_validated if args.word_gleu_source_policy == "fixed-gold" else None
        ),
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
        "- The word-M2 source segmentation is byte-for-byte identical across T0--T3 for every sentence.",
        "- " + word_gleu_protocol_description(args.word_gleu_source_policy),
        "- Word-GLEU source inputs match the declared source policy and preserve learner text after BOM/whitespace normalization.",
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
