#!/usr/bin/env python3
"""Evaluate saved T0--T3 predictions with word GLEU select-best."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import importlib
import json
import math
from pathlib import Path
import sys
from typing import Any

from evaluation_segmentation import (
    LtpSegmentationCache,
    fixed_segmentation_path,
    load_fixed_segmentations,
)
from projection_character_m2 import normalize_text
from run_projection_m2_evaluation import load_target_normalizer
from standardize_m2_evaluation import (
    ROOT,
    ROUNDS,
    load_result_rows,
    load_specs,
    para_rows,
)


GLEU_ROOT = ROOT / "external_tools/multi-reference-GLEU"
DEFAULT_OUTPUT = ROOT / "runs/word_gleu_select_best_final"
DEFAULT_LTP_CACHE = ROOT / "runs/word_evaluation_shared/ltp_segmentation_cache.sqlite3"
DEFAULT_FIXED_SEGMENTATION_ROOT = ROOT / "runs/gold_fixed_source_segmentation"


def load_gleu_module() -> Any:
    if str(GLEU_ROOT) not in sys.path:
        sys.path.insert(0, str(GLEU_ROOT))
    return importlib.import_module("gleu_wrapper")


def calculate_select_best_word(
    gleu: Any,
    source: str,
    hypothesis: str,
    references: list[str],
    *,
    max_n: int,
) -> tuple[float, int]:
    scores = [
        float(
            gleu.calculate_gleu_score(
                source,
                hypothesis,
                reference,
                n=max_n,
                tokenization="word",
            )
        )
        for reference in references
    ]
    selected_index, selected_score = max(
        enumerate(scores), key=lambda item: item[1]
    )
    return selected_score, selected_index


def _write_lines(path: Path, values: list[str]) -> None:
    path.write_text("\n".join(values) + "\n", encoding="utf-8")


def _write_references(path: Path, references: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        for row in references:
            stream.write("\t".join(row) + "\n")


def format_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Word-based GLEU Select-best",
        "",
        "Scores are sentence-level multi-reference word GLEU-select-best, macro-averaged by corpus and multiplied by 100.",
        "",
        "| Dataset | Split | N | References | Multi-ref sentences | T0 | T1 | T2 | T3 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {dataset} | {split} | {sentences:,} | {references:,} | "
            "{multi_reference_sentences:,} | {T0:.2f} | {T1:.2f} | "
            "{T2:.2f} | {T3:.2f} |".format(**row)
        )
    lines.extend(
        [
            "",
            "All T0--T3 stages use the same gold-informed projected learner segmentation. Hypotheses and every gold reference are segmented by the same LTP installation.",
            "",
            "For every sentence and stage, all references are scored and the highest GLEU is selected before corpus macro-averaging. No BPE or LLM calls are used.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    specs = load_specs()
    choices = [spec.dataset for spec in specs]
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", nargs="+", choices=choices, default=choices)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ltp-cache", type=Path, default=DEFAULT_LTP_CACHE)
    parser.add_argument(
        "--fixed-segmentation-root",
        type=Path,
        default=DEFAULT_FIXED_SEGMENTATION_ROOT,
    )
    parser.add_argument("--ltp-batch-size", type=int, default=64)
    parser.add_argument("--max-n", type=int, default=4)
    parser.add_argument("--target-normalization", choices=("t2s", "none"), default="none")
    args = parser.parse_args()

    selected = [spec for spec in specs if spec.dataset in args.datasets]
    args.output.mkdir(parents=True, exist_ok=True)
    normalize_target = load_target_normalizer(args.target_normalization)
    segmenter = LtpSegmentationCache(args.ltp_cache)
    gleu = load_gleu_module()
    compact_rows: list[dict[str, Any]] = []
    long_rows: list[dict[str, Any]] = []
    sentence_path = args.output / "sentence_scores.tsv"
    try:
        with sentence_path.open("w", encoding="utf-8", newline="") as stream:
            sentence_writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "dataset",
                    "split",
                    "id",
                    "stage",
                    "reference_count",
                    "selected_reference",
                    "gleu_select_best",
                ],
                delimiter="\t",
                lineterminator="\n",
            )
            sentence_writer.writeheader()
            for spec in selected:
                gold_rows = para_rows(spec.gold_para)
                result_rows = load_result_rows(spec)
                if len(gold_rows) != spec.rows or len(result_rows) != spec.rows:
                    raise ValueError(f"{spec.dataset}: row-count mismatch")
                fixed_records = load_fixed_segmentations(
                    fixed_segmentation_path(
                        args.fixed_segmentation_root, spec.dataset, spec.split
                    ),
                    expected_sources=[row["source"] for row in result_rows],
                )
                all_targets = [
                    normalize_target(target)
                    for gold_row, result_row in zip(gold_rows, result_rows)
                    for target in [*gold_row[2:], *(result_row[stage] for stage in ROUNDS)]
                ]
                segmentations = segmenter.get_many(
                    all_targets,
                    batch_size=args.ltp_batch_size,
                )
                reference_count = sum(len(row) - 2 for row in gold_rows)
                multi_reference_sentences = sum(len(row) > 3 for row in gold_rows)
                reference_distribution = Counter(len(row) - 2 for row in gold_rows)
                compact: dict[str, Any] = {
                    "dataset": spec.dataset,
                    "split": spec.split,
                    "sentences": spec.rows,
                    "references": reference_count,
                    "multi_reference_sentences": multi_reference_sentences,
                }
                stage_inputs: dict[str, tuple[list[str], list[str], list[list[str]]]] = {}
                for stage in ROUNDS:
                    sources: list[str] = []
                    hypotheses: list[str] = []
                    references: list[list[str]] = []
                    selected_scores: list[float] = []
                    for row_number, (gold_row, result_row, fixed_record) in enumerate(
                        zip(gold_rows, result_rows, fixed_records), start=1
                    ):
                        if normalize_text(gold_row[1]) != normalize_text(result_row["source"]):
                            raise ValueError(f"{spec.dataset}: source mismatch at {row_number}")
                        source = fixed_record.fixed_source_segmentation
                        if normalize_text(source) != normalize_text(result_row["source"]):
                            raise ValueError(
                                f"{spec.dataset}: fixed source segmentation changed text at {row_number}"
                            )
                        hypothesis = segmentations[normalize_target(result_row[stage])]
                        sentence_references = [
                            segmentations[normalize_target(target)] for target in gold_row[2:]
                        ]
                        score, selected_reference = calculate_select_best_word(
                            gleu,
                            source,
                            hypothesis,
                            sentence_references,
                            max_n=args.max_n,
                        )
                        if not math.isfinite(score):
                            raise ValueError(
                                f"{spec.dataset}/{stage}/{row_number}: non-finite GLEU"
                            )
                        selected_scores.append(score)
                        sentence_writer.writerow(
                            {
                                "dataset": spec.dataset,
                                "split": spec.split,
                                "id": gold_row[0],
                                "stage": stage,
                                "reference_count": len(sentence_references),
                                "selected_reference": selected_reference,
                                "gleu_select_best": f"{score:.12f}",
                            }
                        )
                        sources.append(source)
                        hypotheses.append(hypothesis)
                        references.append(sentence_references)
                    corpus_score = math.fsum(selected_scores) / len(selected_scores)
                    compact[stage] = corpus_score * 100.0
                    long_rows.append(
                        {
                            "dataset": spec.dataset,
                            "split": spec.split,
                            "sentences": spec.rows,
                            "references": reference_count,
                            "multi_reference_sentences": multi_reference_sentences,
                            "stage": stage,
                            "gleu_select_best": corpus_score,
                            "gleu_select_best_x100": corpus_score * 100.0,
                        }
                    )
                    stage_inputs[stage] = (sources, hypotheses, references)
                    gleu.clear_caches()
                compact_rows.append(compact)

                input_dir = args.output / spec.dataset / spec.split / "inputs"
                input_dir.mkdir(parents=True, exist_ok=True)
                for stage, (sources, hypotheses, references) in stage_inputs.items():
                    _write_lines(input_dir / f"source.{stage}.txt", sources)
                    _write_lines(input_dir / f"hypothesis.{stage}.txt", hypotheses)
                    _write_references(input_dir / f"references.{stage}.tsv", references)
                (args.output / spec.dataset / spec.split / "stats.json").write_text(
                    json.dumps(
                        {
                            "dataset": spec.dataset,
                            "split": spec.split,
                            "sentences": spec.rows,
                            "references": reference_count,
                            "multi_reference_sentences": multi_reference_sentences,
                            "reference_count_distribution": {
                                str(count): sentences
                                for count, sentences in sorted(reference_distribution.items())
                            },
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                print(
                    f"[{spec.dataset}] "
                    + " ".join(f"{stage}={compact[stage]:.2f}" for stage in ROUNDS),
                    flush=True,
                )
    finally:
        segmenter.close()

    with (args.output / "scores.long.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(long_rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(long_rows)
    with (args.output / "scores.compact.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(compact_rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(compact_rows)
    (args.output / "scores.md").write_text(
        format_markdown(compact_rows), encoding="utf-8"
    )
    (args.output / "run_config.json").write_text(
        json.dumps(
            {
                "completed_utc": datetime.now(timezone.utc).isoformat(),
                "evaluation": "multi-reference GLEU select-best",
                "tokenization": "word",
                "max_n": args.max_n,
                "source_segmentation": "one fixed gold-informed projection shared by T0--T3",
                "reference_selection": "minimum raw character Levenshtein distance; first-reference tie break",
                "fixed_segmentation_root": str(args.fixed_segmentation_root),
                "hypothesis_and_reference_segmentation": "LTP",
                "target_normalization": args.target_normalization,
                "aggregation": "select best reference per sentence, then macro-average",
                "bpe": False,
                "llm_calls": False,
                "datasets": [spec.dataset for spec in selected],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(args.output / "scores.md")


if __name__ == "__main__":
    main()
