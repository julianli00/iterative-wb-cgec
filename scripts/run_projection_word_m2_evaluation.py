#!/usr/bin/env python3
"""Evaluate saved T0--T3 outputs with projection-derived word M2 files."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, Callable, Sequence

from evaluation_segmentation import (
    FixedSourceSegmentation,
    LtpSegmentationCache,
    fixed_segmentation_path,
    load_fixed_segmentations,
)
from movement_m2 import DEFAULT_L_MAX_WORD

from projection_character_m2 import CharacterEdit, apply_edits, normalize_text
from projection_word_m2 import (
    projection_word_edits_from_character_edits,
    render_word_m2_block,
    segmented_tokens,
    targets_from_word_m2_block,
)
from run_projection_m2_evaluation import BETAS, load_target_normalizer, run_compare
from standardize_m2_evaluation import (
    ROOT,
    ROUNDS,
    DatasetSpec,
    load_result_rows,
    load_specs,
    para_rows,
)


DEFAULT_OUTPUT = ROOT / "runs/projection_word_m2_eval_final"
DEFAULT_CHARACTER_CACHE = (
    ROOT / "runs/projection_character_m2_eval_final/alignment_cache.sqlite3"
)
DEFAULT_FIXED_SEGMENTATION_ROOT = ROOT / "runs/gold_fixed_source_segmentation"
DEFAULT_LTP_CACHE = ROOT / "runs/word_evaluation_shared/ltp_segmentation_cache.sqlite3"
DEFAULT_PYTHON = Path(sys.executable)


class StoredCharacterEdits:
    """Read projection character edits without loading BERT again."""

    def __init__(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(path)
        connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
        try:
            self.payloads = {
                (source, target): payload
                for source, target, payload in connection.execute(
                    "SELECT source, target, payload FROM pair_cache"
                )
            }
        finally:
            connection.close()

    def get(self, source: str, target: str) -> list[CharacterEdit]:
        source = normalize_text(source)
        target = normalize_text(target)
        payload_text = self.payloads.get((source, target))
        if payload_text is None:
            raise KeyError(f"Projection character alignment is not cached: {source!r}")
        payload = json.loads(payload_text)
        edits = [CharacterEdit(**record) for record in payload["edits"]]
        if apply_edits(source, edits) != target:
            raise ValueError("Stored projection character edits failed validation")
        return edits


def source_segmentation(record: FixedSourceSegmentation) -> str:
    """Return the one fixed gold-informed source segmentation for all stages."""

    if normalize_text(record.fixed_source_segmentation) != normalize_text(record.source):
        raise ValueError("Fixed source segmentation does not preserve learner text")
    return record.fixed_source_segmentation


def _write_block(handle: Any, block: str, index: int) -> None:
    if index:
        handle.write("\n")
    handle.write(block)
    handle.write("\n")


def _empty_stats() -> dict[str, int]:
    return {
        "pairs": 0,
        "physical_edits": 0,
        "M": 0,
        "R": 0,
        "U": 0,
        "W": 0,
        "W_LD": 0,
    }


def _record(stats: dict[str, int], edits: Sequence[Any]) -> None:
    stats["pairs"] += 1
    stats["physical_edits"] += len(edits)
    for edit in edits:
        stats[edit.edit_type] += 1
    stats["W_LD"] += sum(1 for edit in edits if "FROM=" in edit.comment)


def _validate_word_file(
    path: Path,
    expected: Sequence[tuple[str, Sequence[str]]],
) -> dict[str, int]:
    text = path.read_text(encoding="utf-8-sig").strip()
    blocks = [] if not text else text.split("\n\n")
    if len(blocks) != len(expected):
        raise ValueError(f"Word M2 block count mismatch: {path}")
    references = 0
    for row_number, (block, (source, targets)) in enumerate(
        zip(blocks, expected), start=1
    ):
        actual_source, actual_targets = targets_from_word_m2_block(block)
        if actual_source != segmented_tokens(source):
            raise ValueError(f"Word M2 source mismatch at row {row_number}")
        expected_targets = {
            index: segmented_tokens(target) for index, target in enumerate(targets)
        }
        if actual_targets != expected_targets:
            raise ValueError(f"Word M2 target mismatch at row {row_number}")
        references += len(targets)
    return {"sentences": len(blocks), "references": references}


def generate_dataset_word_m2(
    spec: DatasetSpec,
    output_dir: Path,
    character_store: StoredCharacterEdits,
    segmenter: LtpSegmentationCache,
    fixed_records: Sequence[FixedSourceSegmentation],
    *,
    rounds: Sequence[str],
    limit: int,
    ltp_batch_size: int,
    normalize_target: Callable[[str], str],
    l_max_word: int,
) -> tuple[dict[str, dict[str, Path]], dict[str, Any]]:
    gold_rows = para_rows(spec.gold_para)
    result_rows = load_result_rows(spec)
    row_count = min(len(result_rows), limit) if limit else len(result_rows)
    gold_rows = gold_rows[:row_count]
    result_rows = result_rows[:row_count]
    fixed_records = fixed_records[:row_count]
    if len(gold_rows) != row_count or len(fixed_records) != row_count:
        raise ValueError(f"{spec.dataset}: gold row mismatch")

    targets_to_segment: list[str] = []
    for gold_row, result_row in zip(gold_rows, result_rows):
        if normalize_text(gold_row[1]) != normalize_text(result_row["source"]):
            raise ValueError(f"{spec.dataset}: source mismatch")
        targets_to_segment.extend(normalize_target(target) for target in gold_row[2:])
        targets_to_segment.extend(
            normalize_target(result_row[stage]) for stage in rounds
        )
    segmentations = segmenter.get_many(
        targets_to_segment,
        batch_size=ltp_batch_size,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        stage: {
            "reference": output_dir / f"reference.{stage}.projection.word.m2",
            "hypothesis": output_dir / f"hypothesis.{stage}.projection.word.m2",
        }
        for stage in rounds
    }
    handles = {
        (stage, kind): path.with_suffix(path.suffix + ".tmp").open(
            "w", encoding="utf-8", newline="\n"
        )
        for stage, stage_paths in paths.items()
        for kind, path in stage_paths.items()
    }
    stats = {
        "dataset": spec.dataset,
        "split": spec.split,
        "sentences": row_count,
        "references": {stage: _empty_stats() for stage in rounds},
        "hypotheses": {stage: _empty_stats() for stage in rounds},
    }
    expected: dict[tuple[str, str], list[tuple[str, list[str]]]] = {
        (stage, kind): []
        for stage in rounds
        for kind in ("reference", "hypothesis")
    }
    try:
        for row_index, (gold_row, result_row) in enumerate(
            zip(gold_rows, result_rows)
        ):
            source = result_row["source"]
            fixed_record = fixed_records[row_index]
            source_segmented = source_segmentation(fixed_record)
            normalized_references = [normalize_target(value) for value in gold_row[2:]]
            for stage in rounds:
                converted_references = []
                target_segmented_values: list[str] = []
                for target in normalized_references:
                    target_segmented = segmentations[target]
                    character_edits = character_store.get(source, target)
                    edits = projection_word_edits_from_character_edits(
                        source_segmented,
                        target_segmented,
                        character_edits,
                        l_max=l_max_word,
                    )
                    _record(stats["references"][stage], edits)
                    converted_references.append((target_segmented, edits))
                    target_segmented_values.append(target_segmented)
                reference_block = render_word_m2_block(
                    source_segmented,
                    converted_references,
                )
                _write_block(handles[(stage, "reference")], reference_block, row_index)
                expected[(stage, "reference")].append(
                    (source_segmented, target_segmented_values)
                )

                target = normalize_target(result_row[stage])
                target_segmented = segmentations[target]
                character_edits = character_store.get(source, target)
                edits = projection_word_edits_from_character_edits(
                    source_segmented,
                    target_segmented,
                    character_edits,
                    l_max=l_max_word,
                )
                _record(stats["hypotheses"][stage], edits)
                hypothesis_block = render_word_m2_block(
                    source_segmented,
                    [(target_segmented, edits)],
                )
                _write_block(
                    handles[(stage, "hypothesis")],
                    hypothesis_block,
                    row_index,
                )
                expected[(stage, "hypothesis")].append(
                    (source_segmented, [target_segmented])
                )
    finally:
        for handle in handles.values():
            handle.close()

    serialized_validation = {}
    for stage, stage_paths in paths.items():
        serialized_validation[stage] = {}
        for kind, path in stage_paths.items():
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.replace(path)
            serialized_validation[stage][kind] = _validate_word_file(
                path,
                expected[(stage, kind)],
            )
    stats["serialized_validation"] = serialized_validation
    return paths, stats


def format_markdown(rows: Sequence[dict[str, Any]], rounds: Sequence[str]) -> str:
    indexed = {(row["dataset"], row["round"]): row for row in rows if row["beta"] == 0.5}
    datasets = list(dict.fromkeys(row["dataset"] for row in rows))
    lines = [
        "# Projection-based Word M2 Evaluation",
        "",
        "Scores are corpus-level F0.5 x 100 using projection-derived MRU+W word edits and one fixed gold-informed source segmentation per sentence.",
        "",
        "| Dataset | Split | N | " + " | ".join(rounds) + " |",
        "| --- | --- | ---: | " + " | ".join("---:" for _ in rounds) + " |",
    ]
    for dataset in datasets:
        first = indexed[(dataset, rounds[0])]
        lines.append(
            f"| {dataset} | {first['split']} | {first['sentences']:,} | "
            + " | ".join(
                f"{100 * float(indexed[(dataset, stage)]['F_beta']):.2f}"
                for stage in rounds
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    specs = load_specs()
    choices = [spec.dataset for spec in specs]
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", nargs="+", choices=choices, default=choices)
    parser.add_argument("--rounds", nargs="+", choices=ROUNDS, default=list(ROUNDS))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--character-cache", type=Path, default=DEFAULT_CHARACTER_CACHE)
    parser.add_argument(
        "--fixed-segmentation-root",
        type=Path,
        default=DEFAULT_FIXED_SEGMENTATION_ROOT,
    )
    parser.add_argument("--ltp-cache", type=Path, default=DEFAULT_LTP_CACHE)
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--target-normalization", choices=("t2s", "none"), default="none")
    parser.add_argument("--ltp-batch-size", type=int, default=64)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--l-max-word", type=int, default=DEFAULT_L_MAX_WORD)
    args = parser.parse_args()

    selected = [spec for spec in specs if spec.dataset in args.datasets]
    normalize_target = load_target_normalizer(args.target_normalization)
    if args.l_max_word < 2:
        parser.error("--l-max-word must be at least 2")
    args.output_root.mkdir(parents=True, exist_ok=True)
    character_store = StoredCharacterEdits(args.character_cache)
    segmenter = LtpSegmentationCache(args.ltp_cache)
    all_scores: list[dict[str, Any]] = []
    try:
        for spec in selected:
            output_dir = args.output_root / spec.dataset / spec.split / "word"
            result_rows = load_result_rows(spec)
            fixed_records = load_fixed_segmentations(
                fixed_segmentation_path(
                    args.fixed_segmentation_root, spec.dataset, spec.split
                ),
                expected_sources=[row["source"] for row in result_rows],
            )
            print(f"[{spec.dataset}] generating projection word M2", flush=True)
            paths, stats = generate_dataset_word_m2(
                spec,
                output_dir,
                character_store,
                segmenter,
                fixed_records,
                rounds=args.rounds,
                limit=args.limit,
                ltp_batch_size=args.ltp_batch_size,
                normalize_target=normalize_target,
                l_max_word=args.l_max_word,
            )
            rows = []
            for stage in args.rounds:
                for beta in BETAS:
                    metrics = run_compare(
                        hypothesis=paths[stage]["hypothesis"],
                        reference=paths[stage]["reference"],
                        beta=beta,
                        python=args.python,
                        output_path=output_dir / "comparisons" / f"{stage}.beta{beta:g}.txt",
                        unit="word",
                    )
                    rows.append(
                        {
                            "dataset": spec.dataset,
                            "split": spec.split,
                            "sentences": stats["sentences"],
                            "round": stage,
                            "beta": beta,
                            **metrics,
                        }
                    )
            with (output_dir / "scores.long.tsv").open(
                "w", encoding="utf-8", newline=""
            ) as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t")
                writer.writeheader()
                writer.writerows(rows)
            (output_dir / "generation_stats.json").write_text(
                json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            all_scores.extend(rows)
            print(f"[{spec.dataset}] word evaluation complete", flush=True)
    finally:
        segmenter.close()

    with (args.output_root / "scores.long.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(all_scores[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(all_scores)
    (args.output_root / "scores.f05.md").write_text(
        format_markdown(all_scores, args.rounds), encoding="utf-8"
    )
    (args.output_root / "run_config.json").write_text(
        json.dumps(
            {
                "completed_utc": datetime.now(timezone.utc).isoformat(),
                "datasets": [spec.dataset for spec in selected],
                "rounds": list(args.rounds),
                "limit": args.limit or None,
                "source_segmentation": "one fixed gold-informed projection shared by T0--T3",
                "reference_selection": "minimum raw character Levenshtein distance; first-reference tie break",
                "fixed_segmentation_root": str(args.fixed_segmentation_root),
                "target_segmentation": "LTP",
                "alignment": "WB projection character edits aggregated to words",
                "edit_types": ["M", "R", "U", "W"],
                "long_distance_word_order": {
                    "representation": "linked U--M scored once as W-LD",
                    "l_max_word": args.l_max_word,
                    "matching": "origin + destination + moved material + unit",
                },
                "pos_or_spelling_subtypes": False,
                "all_gold_references": True,
                "target_normalization": args.target_normalization,
                "bpe": False,
                "llm_calls": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    method = """# Projection-based Word M2 Method

- Existing T0--T3 predictions are reused; no LLM calls are made.
- Every T0--T3 stage uses the same source segmentation: LTP boundaries from the closest gold reference are projected onto the learner source.
- The closest gold reference is selected by minimum raw character Levenshtein distance, with first-reference tie breaking.
- Gold references and corrected hypotheses are segmented with the same LTP installation.
- The saved WB projection character edits are aggregated into monotonic word anchors.
- Coarse labels are M, R, U, and W only; long-distance one-block movements use linked U--M records and count once as W-LD.
- Multiple references retain distinct annotator IDs in each stage-specific reference M2 file.
- No BPE is used.
"""
    (args.output_root / "METHOD.md").write_text(method, encoding="utf-8")
    print(args.output_root / "scores.f05.md")


if __name__ == "__main__":
    main()
