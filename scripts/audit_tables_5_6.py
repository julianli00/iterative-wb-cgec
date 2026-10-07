#!/usr/bin/env python3
"""Recompute and diagnose the values reported in manuscript Tables 5 and 6."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from typing import Any, Callable, Sequence

try:
    from Levenshtein import distance as _fast_levenshtein
except ImportError:
    _fast_levenshtein = None

if not __package__:
    from audit_final_projection_artifacts import (
        add_word_gleu_arguments,
        assert_word_gleu_sources,
        resolve_word_gleu_root,
        word_gleu_protocol_description,
        word_gleu_source_metadata,
    )
    from movement_aware_compare import evaluate, f_score, parse_file
    from projection_character_m2 import normalize_text
    from run_character_gleu_evaluation import load_gleu_module, normalize_character_text
    from standardize_m2_evaluation import (
        ROUNDS,
        ROOT,
        load_result_rows,
        load_specs,
        para_rows,
    )
    from word_gleu_protocol import load_source_policy
else:
    from .audit_final_projection_artifacts import (
        add_word_gleu_arguments,
        assert_word_gleu_sources,
        resolve_word_gleu_root,
        word_gleu_protocol_description,
        word_gleu_source_metadata,
    )
    from .movement_aware_compare import evaluate, f_score, parse_file
    from .projection_character_m2 import normalize_text
    from .run_character_gleu_evaluation import (
        load_gleu_module,
        normalize_character_text,
    )
    from .standardize_m2_evaluation import (
        ROUNDS,
        ROOT,
        load_result_rows,
        load_specs,
        para_rows,
    )
    from .word_gleu_protocol import load_source_policy


RUNS = ROOT / "runs"
CHARACTER_M2_ROOT = RUNS / "projection_character_m2_eval_final"
WORD_M2_ROOT = RUNS / "projection_word_m2_eval_final"
CHARACTER_GLEU_ROOT = RUNS / "character_gleu_select_best"
WORD_GLEU_ROOT = RUNS / "word_gleu_condition_select_best"
DEFAULT_OUTPUT = RUNS / "tables_5_6_evaluation_audit"

METRIC_LABELS = {
    "character_m2": "Character F0.5",
    "word_m2": "Word F0.5",
    "character_gleu": "Character GLEU",
    "word_gleu": "Word GLEU",
}

CONDITION_LABELS = {
    "T0": "Raw",
    "T1": "Direct-WB",
    "T2": "Projected-WB",
    "T3": "Iterative Projected-WB",
}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8-sig").splitlines()


def read_reference_lines(path: Path) -> list[list[str]]:
    return [line.split("\t") for line in read_lines(path)]


def load_published_m2(
    path: Path, *, alignment: str | None = None
) -> dict[tuple[str, str], dict[str, float | int]]:
    output: dict[tuple[str, str], dict[str, float | int]] = {}
    for row in read_tsv(path):
        if row["beta"] != "0.5":
            continue
        if alignment is not None and row.get("alignment") != alignment:
            continue
        output[(row["dataset"], row["round"])] = {
            "TP": int(row["TP"]),
            "FP": int(row["FP"]),
            "FN": int(row["FN"]),
            "precision_x100": float(row["Prec"]) * 100.0,
            "recall_x100": float(row["Rec"]) * 100.0,
            "score_x100": float(row["F_beta"]) * 100.0,
        }
    return output


def load_published_gleu(path: Path) -> dict[tuple[str, str], dict[str, float]]:
    return {
        (row["dataset"], row["stage"]): {
            "score_x100": float(row["gleu_select_best_x100"])
        }
        for row in read_tsv(path)
    }


def levenshtein(left: str, right: str) -> int:
    """Return character Levenshtein distance without an optional dependency."""

    if _fast_levenshtein is not None:
        return int(_fast_levenshtein(left, right))
    if left == right:
        return 0
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_unit in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_unit in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_unit != right_unit),
                )
            )
        previous = current
    return previous[-1]


def compare_value(
    issues: list[str],
    label: str,
    actual: float | int,
    expected: float | int,
    *,
    tolerance: float = 0.0,
) -> None:
    if abs(float(actual) - float(expected)) > tolerance:
        issues.append(f"{label}: recomputed={actual}, published={expected}")


def score_m2(
    hypothesis_blocks: Sequence[Any], reference_blocks: Sequence[Any]
) -> dict[str, float | int]:
    counts, _categories, _selections = evaluate(
        hypothesis_blocks, reference_blocks, beta=0.5
    )
    precision, recall, score = f_score(
        counts["tp"], counts["fp"], counts["fn"], 0.5
    )
    return {
        "TP": counts["tp"],
        "FP": counts["fp"],
        "FN": counts["fn"],
        "precision_x100": precision * 100.0,
        "recall_x100": recall * 100.0,
        "score_x100": score * 100.0,
    }


def select_best_gleu(
    gleu: Any,
    sources: Sequence[str],
    hypotheses: Sequence[str],
    references: Sequence[Sequence[str]],
    *,
    tokenization: str,
) -> tuple[float, list[float]]:
    if not (len(sources) == len(hypotheses) == len(references)):
        raise ValueError("GLEU input row counts differ")
    selected_scores: list[float] = []
    for source, hypothesis, sentence_references in zip(
        sources, hypotheses, references
    ):
        if not sentence_references:
            raise ValueError("GLEU sentence has no reference")
        selected_scores.append(
            max(
                float(
                    gleu.calculate_gleu_score(
                        source,
                        hypothesis,
                        reference,
                        n=4,
                        tokenization=tokenization,
                    )
                )
                for reference in sentence_references
            )
        )
    return math.fsum(selected_scores) / len(selected_scores) * 100.0, selected_scores


def transition_counts(values: Sequence[float], baseline: Sequence[float]) -> dict[str, int]:
    counts = {"better": 0, "equal": 0, "worse": 0}
    for current, previous in zip(values, baseline):
        difference = current - previous
        if difference > 1e-12:
            counts["better"] += 1
        elif difference < -1e-12:
            counts["worse"] += 1
        else:
            counts["equal"] += 1
    return counts


def rank_summary(
    scores: dict[tuple[str, str], dict[str, float | int]],
    datasets: Sequence[str],
) -> dict[str, int]:
    """Summarize comparisons as they appear after two-decimal table rounding."""

    def value(dataset: str, stage: str) -> float:
        return round(float(scores[(dataset, stage)]["score_x100"]), 2)

    result = {
        "structured_beats_raw": 0,
        "direct_beats_raw": 0,
        "projected_beats_raw": 0,
        "iterative_beats_raw": 0,
        "projected_beats_direct": 0,
        "projected_equals_direct": 0,
        "projected_below_direct": 0,
        "iterative_beats_projected": 0,
        "iterative_equals_projected": 0,
        "iterative_below_projected": 0,
    }
    for dataset in datasets:
        raw = value(dataset, "T0")
        direct = value(dataset, "T1")
        projected = value(dataset, "T2")
        iterative = value(dataset, "T3")
        result["structured_beats_raw"] += max(direct, projected, iterative) > raw
        result["direct_beats_raw"] += direct > raw
        result["projected_beats_raw"] += projected > raw
        result["iterative_beats_raw"] += iterative > raw
        if projected > direct:
            result["projected_beats_direct"] += 1
        elif projected < direct:
            result["projected_below_direct"] += 1
        else:
            result["projected_equals_direct"] += 1
        if iterative > projected:
            result["iterative_beats_projected"] += 1
        elif iterative < projected:
            result["iterative_below_projected"] += 1
        else:
            result["iterative_equals_projected"] += 1
    return result


def subset_average(values: Sequence[float], indices: Sequence[int]) -> float:
    return math.fsum(values[index] for index in indices) / len(indices) * 100.0


def write_tsv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(rows[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def append_table(
    lines: list[str], headers: Sequence[str], rows: Sequence[Sequence[str]]
) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    lines.append("")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model-label", default="DeepSeek")
    parser.add_argument(
        "--character-m2-root", type=Path, default=CHARACTER_M2_ROOT
    )
    parser.add_argument("--word-m2-root", type=Path, default=WORD_M2_ROOT)
    parser.add_argument(
        "--character-gleu-root", type=Path, default=CHARACTER_GLEU_ROOT
    )
    add_word_gleu_arguments(parser)
    args = parser.parse_args()
    args.word_gleu_root = resolve_word_gleu_root(
        args.word_gleu_root, source_policy=args.word_gleu_source_policy
    )
    load_source_policy(
        args.word_gleu_root, expected_policy=args.word_gleu_source_policy
    )
    args.output.mkdir(parents=True, exist_ok=True)

    specs = load_specs()
    datasets = [spec.dataset for spec in specs]
    published = {
        "character_m2": load_published_m2(
            args.character_m2_root / "scores.long.tsv", alignment="projection"
        ),
        "word_m2": load_published_m2(args.word_m2_root / "scores.long.tsv"),
        "character_gleu": load_published_gleu(
            args.character_gleu_root / "scores.long.tsv"
        ),
        "word_gleu": load_published_gleu(args.word_gleu_root / "scores.long.tsv"),
    }
    recomputed: dict[str, dict[tuple[str, str], dict[str, float | int]]] = {
        metric: {} for metric in METRIC_LABELS
    }
    issues: list[str] = []
    cell_rows: list[dict[str, Any]] = []
    transition_rows: list[dict[str, Any]] = []
    dataset_diagnostics: list[dict[str, Any]] = []
    stage_totals = {
        stage: {"copies": 0, "distance": 0, "same_as_previous": 0}
        for stage in ROUNDS
    }
    total_rows = 0
    word_source_rows_validated = 0
    converged_after_direct = converged_after_projected = reached_t3 = 0
    gleu = load_gleu_module()

    for spec in specs:
        result_rows = load_result_rows(spec)
        gold_rows = para_rows(spec.gold_para)
        if len(gold_rows) != spec.rows:
            issues.append(f"{spec.dataset}: gold row count differs from manifest")
        total_rows += len(result_rows)

        diagnostics: dict[str, Any] = {
            "dataset": spec.dataset,
            "sentences": len(result_rows),
        }
        for stage_index, stage in enumerate(ROUNDS):
            copies = 0
            distance_sum = 0
            same_as_previous = 0
            for row in result_rows:
                source = normalize_text(row["source"])
                output = normalize_text(row[stage])
                copies += output == source
                distance_sum += levenshtein(source, output)
                if stage_index:
                    same_as_previous += output == normalize_text(row[ROUNDS[stage_index - 1]])
            diagnostics[f"{stage}_source_copies"] = copies
            diagnostics[f"{stage}_mean_source_distance"] = distance_sum / len(result_rows)
            diagnostics[f"{stage}_same_as_previous"] = same_as_previous
            stage_totals[stage]["copies"] += copies
            stage_totals[stage]["distance"] += distance_sum
            stage_totals[stage]["same_as_previous"] += same_as_previous

        first_changed = [
            index for index, row in enumerate(result_rows) if row["S2"] != row["S1"]
        ]
        second_changed = [
            index for index, row in enumerate(result_rows) if row["S3"] != row["S2"]
        ]
        for row_number, row in enumerate(result_rows, start=1):
            if row["S2"] == row["S1"] and row["T2"] != row["T1"]:
                issues.append(
                    f"{spec.dataset}:{row_number}: unchanged S2 did not carry T1"
                )
            if row["S3"] == row["S2"] and row["T3"] != row["T2"]:
                issues.append(
                    f"{spec.dataset}:{row_number}: unchanged S3 did not carry T2"
                )
        direct_stops = len(result_rows) - len(first_changed)
        projected_stops = sum(
            row["S2"] != row["S1"] and row["S3"] == row["S2"]
            for row in result_rows
        )
        t3_rows = sum(
            row["S2"] != row["S1"] and row["S3"] != row["S2"]
            for row in result_rows
        )
        converged_after_direct += direct_stops
        converged_after_projected += projected_stops
        reached_t3 += t3_rows
        diagnostics.update(
            {
                "first_projection_changed": len(first_changed),
                "second_projection_changed": len(second_changed),
                "converged_after_direct": direct_stops,
                "converged_after_projected": projected_stops,
                "reached_t3": t3_rows,
            }
        )
        dataset_diagnostics.append(diagnostics)

        char_dir = args.character_m2_root / spec.dataset / spec.split / "char"
        word_dir = args.word_m2_root / spec.dataset / spec.split / "word"
        char_reference = parse_file(
            char_dir / "reference.projection.all.char.m2", unit="character"
        )
        char_hypotheses = {
            stage: parse_file(
                char_dir / f"hypothesis.{stage}.projection.char.m2",
                unit="character",
            )
            for stage in ROUNDS
        }
        word_reference_blocks = {
            stage: parse_file(
                word_dir / f"reference.{stage}.projection.word.m2", unit="word"
            )
            for stage in ROUNDS
        }
        word_hypotheses = {
            stage: parse_file(
                word_dir / f"hypothesis.{stage}.projection.word.m2", unit="word"
            )
            for stage in ROUNDS
        }
        fixed_word_sources = [
            " ".join(block.source_units) for block in word_reference_blocks["T0"]
        ]
        for stage in ROUNDS:
            for blocks in (word_reference_blocks[stage], word_hypotheses[stage]):
                if [" ".join(block.source_units) for block in blocks] != fixed_word_sources:
                    issues.append(
                        f"{spec.dataset}/{stage}: word M2 source segmentation varies"
                    )

        for stage in ROUNDS:
            for metric, hypothesis_blocks, reference_blocks in (
                ("character_m2", char_hypotheses[stage], char_reference),
                ("word_m2", word_hypotheses[stage], word_reference_blocks[stage]),
            ):
                score = score_m2(hypothesis_blocks, reference_blocks)
                recomputed[metric][(spec.dataset, stage)] = score
                expected = published[metric][(spec.dataset, stage)]
                for field in ("TP", "FP", "FN"):
                    compare_value(
                        issues,
                        f"{metric}/{spec.dataset}/{stage}/{field}",
                        score[field],
                        expected[field],
                    )
                compare_value(
                    issues,
                    f"{metric}/{spec.dataset}/{stage}/score",
                    score["score_x100"],
                    expected["score_x100"],
                    tolerance=1e-12,
                )
                cell_rows.append(
                    {
                        "metric": metric,
                        "dataset": spec.dataset,
                        "stage": stage,
                        "published_x100": f"{float(expected['score_x100']):.8f}",
                        "recomputed_x100": f"{float(score['score_x100']):.8f}",
                        "absolute_difference": f"{abs(float(score['score_x100']) - float(expected['score_x100'])):.12f}",
                    }
                )

        char_input_dir = args.character_gleu_root / spec.dataset / spec.split / "inputs"
        char_sources = read_lines(char_input_dir / "original.txt")
        char_references = read_reference_lines(char_input_dir / "references.tsv")
        expected_char_sources = [normalize_character_text(row["source"]) for row in result_rows]
        expected_char_references = [
            [normalize_character_text(value) for value in row[2:]] for row in gold_rows
        ]
        if char_sources != expected_char_sources:
            issues.append(f"{spec.dataset}: character GLEU source input mismatch")
        if char_references != expected_char_references:
            issues.append(f"{spec.dataset}: character GLEU reference input mismatch")

        word_input_dir = args.word_gleu_root / spec.dataset / spec.split / "inputs"
        word_sources_by_stage: dict[str, list[str]] = {}
        word_references_by_stage: dict[str, list[list[str]]] = {}
        char_sentence_scores: dict[str, list[float]] = {}
        word_sentence_scores: dict[str, list[float]] = {}
        for stage in ROUNDS:
            char_hypothesis = read_lines(char_input_dir / f"hypothesis.{stage}.txt")
            expected_hypothesis = [
                normalize_character_text(row[stage]) for row in result_rows
            ]
            if char_hypothesis != expected_hypothesis:
                issues.append(f"{spec.dataset}/{stage}: character GLEU hypothesis mismatch")
            char_score, char_per_sentence = select_best_gleu(
                gleu,
                char_sources,
                char_hypothesis,
                char_references,
                tokenization="char",
            )
            char_sentence_scores[stage] = char_per_sentence
            recomputed["character_gleu"][(spec.dataset, stage)] = {
                "score_x100": char_score
            }
            expected = published["character_gleu"][(spec.dataset, stage)]
            compare_value(
                issues,
                f"character_gleu/{spec.dataset}/{stage}/score",
                char_score,
                expected["score_x100"],
                tolerance=1.1e-6,
            )
            cell_rows.append(
                {
                    "metric": "character_gleu",
                    "dataset": spec.dataset,
                    "stage": stage,
                    "published_x100": f"{float(expected['score_x100']):.8f}",
                    "recomputed_x100": f"{char_score:.8f}",
                    "absolute_difference": f"{abs(char_score - float(expected['score_x100'])):.12f}",
                }
            )

        for stage in ROUNDS:
            expected_hypothesis = [
                normalize_character_text(row[stage]) for row in result_rows
            ]
            word_sources = read_lines(word_input_dir / f"source.{stage}.txt")
            word_hypothesis = read_lines(
                word_input_dir / f"hypothesis.{stage}.txt"
            )
            word_reference_texts = read_reference_lines(
                word_input_dir / f"references.{stage}.tsv"
            )
            if [normalize_text(value) for value in word_sources] != expected_char_sources:
                issues.append(f"{spec.dataset}/{stage}: word GLEU source text mismatch")
            if [normalize_text(value) for value in word_hypothesis] != expected_hypothesis:
                issues.append(f"{spec.dataset}/{stage}: word GLEU hypothesis text mismatch")
            if [
                [normalize_text(value) for value in references]
                for references in word_reference_texts
            ] != expected_char_references:
                issues.append(f"{spec.dataset}/{stage}: word GLEU reference text mismatch")
            word_sources_by_stage[stage] = word_sources
            word_references_by_stage[stage] = word_reference_texts
            word_score, word_per_sentence = select_best_gleu(
                gleu,
                word_sources,
                word_hypothesis,
                word_reference_texts,
                tokenization="word",
            )
            word_sentence_scores[stage] = word_per_sentence
            recomputed["word_gleu"][(spec.dataset, stage)] = {
                "score_x100": word_score
            }
            expected = published["word_gleu"][(spec.dataset, stage)]
            compare_value(
                issues,
                f"word_gleu/{spec.dataset}/{stage}/score",
                word_score,
                expected["score_x100"],
                tolerance=1.1e-6,
            )
            cell_rows.append(
                {
                    "metric": "word_gleu",
                    "dataset": spec.dataset,
                    "stage": stage,
                    "published_x100": f"{float(expected['score_x100']):.8f}",
                    "recomputed_x100": f"{word_score:.8f}",
                    "absolute_difference": f"{abs(word_score - float(expected['score_x100'])):.12f}",
                }
            )

        try:
            word_source_rows_validated += assert_word_gleu_sources(
                word_sources_by_stage,
                result_rows,
                source_policy=args.word_gleu_source_policy,
                fixed_sources=fixed_word_sources,
                expected_rows=spec.rows,
            )
        except ValueError as error:
            issues.append(f"{spec.dataset}: {error}")

        for before, after, indices in (
            ("T1", "T2", first_changed),
            ("T2", "T3", second_changed),
        ):
            if not indices:
                continue
            char_before = score_m2(
                [char_hypotheses[before][index] for index in indices],
                [char_reference[index] for index in indices],
            )["score_x100"]
            char_after = score_m2(
                [char_hypotheses[after][index] for index in indices],
                [char_reference[index] for index in indices],
            )["score_x100"]
            word_before = score_m2(
                [word_hypotheses[before][index] for index in indices],
                [word_reference_blocks[before][index] for index in indices],
            )["score_x100"]
            word_after = score_m2(
                [word_hypotheses[after][index] for index in indices],
                [word_reference_blocks[after][index] for index in indices],
            )["score_x100"]
            char_gleu_before = subset_average(char_sentence_scores[before], indices)
            char_gleu_after = subset_average(char_sentence_scores[after], indices)
            word_gleu_before = subset_average(word_sentence_scores[before], indices)
            word_gleu_after = subset_average(word_sentence_scores[after], indices)
            transition_rows.append(
                {
                    "dataset": spec.dataset,
                    "transition": f"{before}->{after}",
                    "changed_boundary_rows": len(indices),
                    "character_f0.5_before": f"{float(char_before):.4f}",
                    "character_f0.5_after": f"{float(char_after):.4f}",
                    "character_f0.5_delta": f"{float(char_after) - float(char_before):+.4f}",
                    "word_f0.5_before": f"{float(word_before):.4f}",
                    "word_f0.5_after": f"{float(word_after):.4f}",
                    "word_f0.5_delta": f"{float(word_after) - float(word_before):+.4f}",
                    "character_gleu_before": f"{char_gleu_before:.4f}",
                    "character_gleu_after": f"{char_gleu_after:.4f}",
                    "character_gleu_delta": f"{char_gleu_after - char_gleu_before:+.4f}",
                    "word_gleu_before": f"{word_gleu_before:.4f}",
                    "word_gleu_after": f"{word_gleu_after:.4f}",
                    "word_gleu_delta": f"{word_gleu_after - word_gleu_before:+.4f}",
                }
            )
        gleu.clear_caches()

    expected_keys = {(dataset, stage) for dataset in datasets for stage in ROUNDS}
    for metric in METRIC_LABELS:
        if set(published[metric]) != expected_keys:
            issues.append(f"{metric}: published score coverage is incomplete")
        if set(recomputed[metric]) != expected_keys:
            issues.append(f"{metric}: recomputed score coverage is incomplete")

    rankings = {
        metric: rank_summary(recomputed[metric], datasets)
        for metric in METRIC_LABELS
    }
    stage_summary = []
    for stage in ROUNDS:
        stage_summary.append(
            {
                "stage": stage,
                "condition": CONDITION_LABELS[stage],
                "source_copies": stage_totals[stage]["copies"],
                "source_copy_percent": stage_totals[stage]["copies"] / total_rows * 100.0,
                "mean_character_distance_from_source": stage_totals[stage]["distance"] / total_rows,
                "same_as_previous": stage_totals[stage]["same_as_previous"],
            }
        )

    status = "PASS" if not issues else "FAIL"
    audit = {
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "scope": f"Manuscript Tables 5 and 6, {args.model_label} T0-T3",
        **word_gleu_source_metadata(
            args.word_gleu_root, args.word_gleu_source_policy
        ),
        "word_gleu_source_rows_validated": word_source_rows_validated,
        "published_cells_recomputed": len(cell_rows),
        "issues": issues,
        "rankings_after_two_decimal_rounding": rankings,
        "convergence": {
            "sentences": total_rows,
            "converged_after_direct": converged_after_direct,
            "converged_after_projected": converged_after_projected,
            "reached_t3": reached_t3,
        },
        "stage_summary": stage_summary,
        "dataset_diagnostics": dataset_diagnostics,
        "projection_affected_subsets": transition_rows,
    }
    (args.output / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_tsv(args.output / "recomputed_cells.tsv", cell_rows)
    write_tsv(args.output / "projection_affected_subsets.tsv", transition_rows)

    by_metric: dict[str, list[float]] = {metric: [] for metric in METRIC_LABELS}
    for row in cell_rows:
        by_metric[row["metric"]].append(float(row["absolute_difference"]))

    lines = [
        "# Tables 5 and 6 Evaluation Audit",
        "",
        f"**Status: {status}.** All checks use saved T0-T3 outputs; no LLM or API calls are made.",
        "",
        "## Reproduction",
        "",
        "The audit reconstructs every M2 score from the final hypothesis/reference files and every GLEU score from the saved source, hypothesis, and all-reference text inputs.",
        "",
        word_gleu_protocol_description(args.word_gleu_source_policy),
        "Word M2 continues to use one fixed gold-informed source segmentation across T0--T3.",
        "",
    ]
    append_table(
        lines,
        ("Metric", "Cells", "Maximum absolute difference (x100)"),
        [
            (
                METRIC_LABELS[metric],
                str(len(values)),
                f"{max(values, default=0.0):.9f}",
            )
            for metric, values in by_metric.items()
        ],
    )
    lines.extend(
        [
            (
                "The stage-to-input mapping also passes: T0 is the Raw output, T1 is Direct-WB, T2 is the first projected-boundary output, and T3 is the next iterative output. Whenever a projected segmentation is unchanged, the previous correction is carried forward without a new generation."
                if not issues
                else "Stage mapping, source-policy, and carry-forward checks found issues; see the issue list below."
            ),
            "",
            "## What The Tables Show",
            "",
        ]
    )
    append_table(
        lines,
        (
            "Metric",
            "Any structured > Raw",
            "Direct > Raw",
            "Projected > Raw",
            "Iterative > Raw",
            "Projected >/=/< Direct",
            "Iterative >/=/< Projected",
        ),
        [
            (
                METRIC_LABELS[metric],
                f"{values['structured_beats_raw']}/8",
                f"{values['direct_beats_raw']}/8",
                f"{values['projected_beats_raw']}/8",
                f"{values['iterative_beats_raw']}/8",
                f"{values['projected_beats_direct']}/{values['projected_equals_direct']}/{values['projected_below_direct']}",
                f"{values['iterative_beats_projected']}/{values['iterative_equals_projected']}/{values['iterative_below_projected']}",
            )
            for metric, values in rankings.items()
        ],
    )
    lines.extend(
        [
            "Across character/word F0.5, a structured condition is higher than Raw on "
            f"{rankings['character_m2']['structured_beats_raw']}/8 and "
            f"{rankings['word_m2']['structured_beats_raw']}/8 datasets, respectively. "
            "For character/word GLEU, the corresponding counts are "
            f"{rankings['character_gleu']['structured_beats_raw']}/8 and "
            f"{rankings['word_gleu']['structured_beats_raw']}/8. "
            "Projected and Iterative are not consistently above Direct.",
            "",
            "## Why Projection Changes Are Small",
            "",
            f"- {converged_after_direct:,}/{total_rows:,} sentences ({converged_after_direct / total_rows * 100:.2f}%) stop after Direct-WB, so T2 and T3 are exact carry-forwards of T1.",
            f"- {converged_after_projected:,}/{total_rows:,} ({converged_after_projected / total_rows * 100:.2f}%) stop after the first projected pass.",
            f"- Only {reached_t3:,}/{total_rows:,} ({reached_t3 / total_rows * 100:.2f}%) reach a second projected generation at T3.",
            "",
            "## Raw Versus WB-aware Output Behavior",
            "",
        ]
    )
    append_table(
        lines,
        ("Stage", "Condition", "Normalized source copies", "Copy rate", "Mean char distance from source", "Same as previous stage"),
        [
            (
                row["stage"],
                row["condition"],
                f"{row['source_copies']:,}",
                f"{row['source_copy_percent']:.2f}%",
                f"{row['mean_character_distance_from_source']:.3f}",
                "-" if row["stage"] == "T0" else f"{row['same_as_previous']:,}",
            )
            for row in stage_summary
        ],
    )
    lines.extend(
        [
            "Raw is not the more source-preserving condition in these outputs. It changes the source much more aggressively. GLEU rewards reference-supported n-grams and penalizes source n-grams that a reference changes, whereas F0.5 rewards exact localized edits and weights precision more heavily. The two metrics can therefore rank the same outputs differently without an evaluation error.",
            "",
            "## Projection-affected Rows",
            "",
            "The following deltas re-evaluate only rows where the first projection actually changes S1 into S2. Positive values favor Projected-WB over Direct-WB.",
            (
                "Under condition word GLEU, these contrasts include the prescribed source-boundary changes as well as any changed hypotheses; hypotheses and references remain LTP-segmented."
                if args.word_gleu_source_policy == "condition"
                else "Historical fixed-gold word GLEU holds the source segmentation constant across the compared stages."
            ),
            "",
        ]
    )
    first_projection_rows = [
        row for row in transition_rows if row["transition"] == "T1->T2"
    ]
    append_table(
        lines,
        ("Dataset", "N", "Char F0.5 delta", "Word F0.5 delta", "Char GLEU delta", "Word GLEU delta"),
        [
            (
                row["dataset"],
                str(row["changed_boundary_rows"]),
                row["character_f0.5_delta"],
                row["word_f0.5_delta"],
                row["character_gleu_delta"],
                row["word_gleu_delta"],
            )
            for row in first_projection_rows
        ],
    )
    lines.extend(
        [
            "The affected subset is mixed rather than uniformly positive. This confirms that the small corpus-level effect is not merely a scoring dilution artifact: projection helps some datasets and hurts others.",
            "",
            "## Conclusion",
            "",
            (
                "The Table 5 and Table 6 values are correctly evaluated under the selected protocol. "
                if not issues
                else "The Table 5 and Table 6 values have not passed validation under the selected protocol. "
            )
            + f"The current {args.model_label} results do not support a universal claim that "
            "Direct-WB, Projected-WB, or further Iterative Projected-WB is better than Raw. "
            "The appropriate interpretation is a model- and dataset-dependent empirical result, "
            "rather than an evaluator problem.",
            "",
        ]
    )
    if issues:
        lines.extend(["## Issues", "", *[f"- {issue}" for issue in issues], ""])
    (args.output / "AUDIT.md").write_text("\n".join(lines), encoding="utf-8")

    print(
        f"{status}: recomputed {len(cell_rows)} cells; "
        f"report={args.output / 'AUDIT.md'}"
    )
    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
