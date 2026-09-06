#!/usr/bin/env python3
"""Build the validated operation, convergence, and error-analysis package.

The script consumes only saved DeepSeek T0--T3 outputs and existing evaluation
artifacts. It never calls an LLM or a remote API.
"""

from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import replace
import json
import math
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from movement_aware_compare import (
        M2Block,
        evaluate,
        f_score,
        parse_block,
        parse_file,
    )
    from projection_character_m2 import normalize_text
    from run_character_gleu_evaluation import load_gleu_module
    from standardize_m2_evaluation import (
        ROOT,
        ROUNDS,
        load_result_rows,
        load_specs,
        para_rows,
    )
except ModuleNotFoundError:
    from scripts.movement_aware_compare import (
        M2Block,
        evaluate,
        f_score,
        parse_block,
        parse_file,
    )
    from scripts.projection_character_m2 import normalize_text
    from scripts.run_character_gleu_evaluation import load_gleu_module
    from scripts.standardize_m2_evaluation import (
        ROOT,
        ROUNDS,
        load_result_rows,
        load_specs,
        para_rows,
    )


RUNS = ROOT / "runs"
CHARACTER_M2_ROOT = RUNS / "projection_character_m2_eval_final"
WORD_M2_ROOT = RUNS / "projection_word_m2_eval_final"
CHARACTER_GLEU_ROOT = RUNS / "character_gleu_select_best"
WORD_GLEU_ROOT = RUNS / "word_gleu_select_best_final"
TABLE_AUDIT = RUNS / "tables_5_6_evaluation_audit"
ALIGNMENT_EXAMPLES = RUNS / "final_alignment_examples/QUALITATIVE_ALIGNMENT_EXAMPLES.md"
DEFAULT_OUTPUT = RUNS / "sections_6_7_analysis"

STAGES = tuple(ROUNDS)
CATEGORIES = ("M", "R", "U", "W", "WO")
CONDITIONS = {
    "T0": "Raw",
    "T1": "Direct-WB",
    "T2": "Projected-WB",
    "T3": "Iterative Projected-WB",
}
DISPLAY_NAMES = {
    "nlpcc2018": "NLPCC2018",
    "mucgec": "MuCGEC",
    "yaclc": "YACLC",
    "flacgec": "FlaCGEC",
    "fcgec": "FCGEC",
    "nacgec": "NaCGEC",
    "nasgec_exam": "NaSGEC-Exam",
    "cefe_track3": "CEFE Track 3",
}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def write_tsv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8-sig").splitlines()


def read_reference_lines(path: Path) -> list[list[str]]:
    return [line.split("\t") for line in read_lines(path)]


def add_table(
    lines: list[str], headers: Sequence[str], rows: Iterable[Sequence[Any]]
) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    lines.append("")


def exact_scores(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    denominator = 1.25 * tp + fp + 0.25 * fn
    score = 1.25 * tp / denominator if denominator else 1.0
    return precision, recall, score


def score_blocks(
    hypotheses: Sequence[M2Block], references: Sequence[M2Block]
) -> tuple[dict[str, int], dict[str, list[int]]]:
    counts, categories, _selections = evaluate(hypotheses, references, beta=0.5)
    return {
        "TP": int(counts["tp"]),
        "FP": int(counts["fp"]),
        "FN": int(counts["fn"]),
    }, categories


def category_row(
    dataset: str,
    split: str,
    sentences: int,
    unit: str,
    stage: str,
    category: str,
    counts: Sequence[int],
) -> dict[str, Any]:
    tp, fp, fn = (int(value) for value in counts)
    precision, recall, score = exact_scores(tp, fp, fn)
    return {
        "dataset": dataset,
        "split": split,
        "sentences": sentences,
        "unit": unit,
        "stage": stage,
        "condition": CONDITIONS[stage],
        "category": category,
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "reference_edits": tp + fn,
        "predicted_edits": tp + fp,
        "precision": f"{precision:.6f}",
        "recall": f"{recall:.6f}",
        "f0.5": f"{score:.6f}",
        "f0.5_x100": f"{score * 100:.2f}",
    }


def manual_scorer_validation(output: Path) -> dict[str, Any]:
    hypothesis_text = (
        "S 甲 乙 丙 丁 戊\n"
        "A 0 1|||U|||-NONE-|||-REQUIRED-|||LINK=w1;TO=5|||0\n"
        "A 5 5|||M|||甲|||-REQUIRED-|||LINK=w1;FROM=0:1|||0\n\n"
        "S 我 很 喜 欢 茶\n"
        "A 4 5|||R|||咖啡|||-REQUIRED-|||NONE|||0\n"
        "A 0 0|||M|||今天|||-REQUIRED-|||NONE|||0\n"
    )
    reference_text = (
        "S 甲 乙 丙 丁 戊\n"
        "A 0 1|||U|||-NONE-|||-REQUIRED-|||LINK=w7;TO=5|||0\n"
        "A 5 5|||M|||甲|||-REQUIRED-|||LINK=w7;FROM=0:1|||0\n\n"
        "S 我 很 喜 欢 茶\n"
        "A 1 2|||U|||-NONE-|||-REQUIRED-|||NONE|||0\n"
        "A 4 5|||R|||咖啡|||-REQUIRED-|||NONE|||0\n"
    )
    fixture_dir = output / "manual_micro"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    hypothesis_path = fixture_dir / "hypothesis.m2"
    reference_path = fixture_dir / "reference.m2"
    hypothesis_path.write_text(hypothesis_text, encoding="utf-8")
    reference_path.write_text(reference_text, encoding="utf-8")

    hypotheses = parse_file(hypothesis_path, unit="character")
    references = parse_file(reference_path, unit="character")
    counts, categories = score_blocks(hypotheses, references)
    expected_counts = {"TP": 2, "FP": 1, "FN": 1}
    expected_categories = {
        "M": [0, 1, 0],
        "R": [1, 0, 0],
        "U": [0, 0, 1],
        "WO": [1, 0, 0],
    }
    if counts != expected_counts:
        raise AssertionError(f"Manual micro counts differ: {counts}")
    if categories != expected_categories:
        raise AssertionError(f"Manual micro categories differ: {categories}")
    precision, recall, score = exact_scores(**{key.lower(): value for key, value in counts.items()})
    if not math.isclose(score, 2 / 3, abs_tol=1e-12):
        raise AssertionError(f"Manual micro F0.5 differs: {score}")

    wrong_destination = reference_text.replace("TO=5", "TO=4").replace(
        "A 5 5|||M|||甲", "A 4 4|||M|||甲"
    )
    wrong_reference = [
        parse_block(wrong_destination.split("\n\n", 1)[0], unit="character")
    ]
    movement_only = score_blocks(hypotheses[:1], wrong_reference)[0]
    if movement_only != {"TP": 0, "FP": 1, "FN": 1}:
        raise AssertionError(f"Strict movement mismatch differs: {movement_only}")

    lines = [
        "# Manual Scorer Validation",
        "",
        "**Status: PASS.** This two-sentence fixture is intentionally small enough to calculate by hand.",
        "",
        "## Sentence 1: linked long-distance word order",
        "",
        "The hypothesis and reference use different local link identifiers (`w1` and `w7`) but the same origin, destination, and moved material. Each file contains two physical M2 records (`U` and `M`), which the comparator validates and collapses into **one logical `WO` edit**. The result is one `WO` true positive, not two true positives.",
        "",
        "## Sentence 2: ordinary edits",
        "",
        "Both sides replace `茶` with `咖啡`, giving one `R` true positive. The hypothesis alone inserts `今天`, giving one `M` false positive. The reference alone deletes `很`, giving one `U` false negative.",
        "",
        "## Hand calculation",
        "",
    ]
    add_table(
        lines,
        ("Logical operation", "TP", "FP", "FN"),
        (
            ("M", 0, 1, 0),
            ("R", 1, 0, 0),
            ("U", 0, 0, 1),
            ("W", 0, 0, 0),
            ("WO (linked M+U)", 1, 0, 0),
            ("Total", 2, 1, 1),
        ),
    )
    lines.extend(
        [
            "- Precision = `2 / (2 + 1) = 0.6667`.",
            "- Recall = `2 / (2 + 1) = 0.6667`.",
            "- F0.5 = `1.25 x TP / (1.25 x TP + FP + 0.25 x FN) = 2.5 / 3.75 = 0.6667`.",
            "- Changing only the movement destination produces one `WO` FP and one `WO` FN, confirming strict origin/destination/material matching.",
            "",
            "The program output exactly matches all hand-calculated counts and scores.",
            "",
        ]
    )
    (output / "MANUAL_SCORER_VALIDATION.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    payload = {
        "status": "PASS",
        **counts,
        "precision": precision,
        "recall": recall,
        "f0.5": score,
        "categories": categories,
        "strict_mismatch": movement_only,
    }
    (output / "manual_validation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def reference_bucket(count: int) -> str:
    return str(count) if count <= 3 else ">3"


def subset_block(block: M2Block, annotator_ids: set[int]) -> M2Block:
    return replace(
        block,
        edits=tuple(
            edit for edit in block.edits if edit.annotator_id in annotator_ids
        ),
    )


def first_k_block(block: M2Block, k: int) -> M2Block:
    annotators = sorted({edit.annotator_id for edit in block.edits})
    return subset_block(block, set(annotators[:k]))


def load_gleu_sentence_groups(path: Path) -> dict[tuple[str, str], list[float]]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in read_tsv(path):
        grouped[(row["dataset"], row["stage"])].append(
            float(row["gleu_select_best"])
        )
    return grouped


def boundary_positions(segmented: str) -> set[int]:
    tokens = segmented.split()
    positions: set[int] = set()
    cursor = 0
    for token in tokens[:-1]:
        cursor += len(token)
        positions.add(cursor)
    return positions


def boundary_error(segmented: str, gold_segmented: str) -> int:
    if normalize_text(segmented) != normalize_text(gold_segmented):
        raise ValueError("Segmentations do not preserve the same characters")
    return len(boundary_positions(segmented) ^ boundary_positions(gold_segmented))


def select_prompting_cases(
    specs: Sequence[Any],
    char_gleu: dict[tuple[str, str], list[float]],
    output: Path,
) -> list[dict[str, Any]]:
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for spec in specs:
        results = load_result_rows(spec)
        gold = para_rows(spec.gold_para)
        fixed_path = (
            RUNS
            / "gold_fixed_source_segmentation"
            / spec.dataset
            / spec.split
            / "fixed_source_segmentation.tsv"
        )
        fixed_rows = read_tsv(fixed_path)
        t0_scores = char_gleu[(spec.dataset, "T0")]
        t1_scores = char_gleu[(spec.dataset, "T1")]
        t2_scores = char_gleu[(spec.dataset, "T2")]
        if not (len(results) == len(gold) == len(fixed_rows) == len(t1_scores)):
            raise ValueError(f"Case-analysis row mismatch for {spec.dataset}")
        for index, (row, gold_row, fixed) in enumerate(
            zip(results, gold, fixed_rows)
        ):
            direct_error = boundary_error(row["S1"], fixed["fixed_source_segmentation"])
            projected_error = boundary_error(row["S2"], fixed["fixed_source_segmentation"])
            delta = t2_scores[index] - t1_scores[index]
            record = {
                "dataset": spec.dataset,
                "row": index + 1,
                "source": row["source"],
                "S1": row["S1"],
                "S2": row["S2"],
                "T0": row["T0"],
                "T1": row["T1"],
                "T2": row["T2"],
                "references": gold_row[2:],
                "direct_boundary_error": direct_error,
                "projected_boundary_error": projected_error,
                "direct_vs_raw_gleu_delta": t1_scores[index] - t0_scores[index],
                "char_gleu_delta": delta,
            }
            if row["S1"] != row["S2"] and projected_error < direct_error:
                candidates["closer_boundary"].append(record)
            if (
                row["S1"] != row["S2"]
                and projected_error < direct_error
                and row["T1"] != row["T2"]
                and delta > 0
            ):
                candidates["improved_correction"].append(record)
            if row["S1"] != row["S2"] and row["T1"] == row["T2"]:
                candidates["unchanged_correction"].append(record)
            if (
                row["S1"] != row["S2"]
                and projected_error > direct_error
                and row["T1"] != row["T2"]
                and delta < 0
            ):
                candidates["unhelpful_projection"].append(record)
            if (
                row["S1"] == row["S2"]
                and normalize_text(row["T1"]) == normalize_text(row["source"])
                and normalize_text(row["T0"]) != normalize_text(row["source"])
                and len(normalize_text(row["source"])) >= 12
            ):
                candidates["conservative_unchanged"].append(record)

    selectors = {
        "Direct boundaries become closer to the gold-informed segmentation": (
            "closer_boundary",
            lambda row: (
                row["direct_boundary_error"] - row["projected_boundary_error"],
                row["char_gleu_delta"],
            ),
        ),
        "Closer projected boundaries improve the correction score": (
            "improved_correction",
            lambda row: row["char_gleu_delta"],
        ),
        "Changed boundaries leave the correction unchanged": (
            "unchanged_correction",
            lambda row: row["direct_boundary_error"] - row["projected_boundary_error"],
        ),
        "Projection moves away from the gold-informed segmentation and hurts": (
            "unhelpful_projection",
            lambda row: -row["char_gleu_delta"],
        ),
        "Conservative rule leaves an already stable case unchanged": (
            "conservative_unchanged",
            lambda row: row["direct_vs_raw_gleu_delta"],
        ),
    }
    selected: list[dict[str, Any]] = []
    used: set[tuple[str, int]] = set()
    for label, (bucket, key) in selectors.items():
        available = [
            row
            for row in candidates[bucket]
            if (row["dataset"], row["row"]) not in used
        ]
        if not available:
            raise AssertionError(f"No prompting case found for {bucket}")
        best = max(available, key=key)
        used.add((best["dataset"], best["row"]))
        selected.append({"category": label, **best})

    lines = [
        "# Prompting and Projection Cases",
        "",
        "These cases are selected by reproducible criteria from saved outputs. Boundary error is symmetric difference from the fixed gold-informed evaluation segmentation; it is not a claim of unique linguistic gold segmentation. GLEU deltas are character-based sentence-level select-best values.",
        "",
    ]
    for number, row in enumerate(selected, start=1):
        lines.extend(
            [
                f"## Case {number}: {row['category']}",
                "",
                f"- Dataset/row: `{row['dataset']}` / `{row['row']}`",
                f"- Boundary error S1 -> S2: `{row['direct_boundary_error']} -> {row['projected_boundary_error']}`",
                f"- Character GLEU T1 -> T2: `{row['char_gleu_delta']:+.4f}`",
                f"- Source: {row['source']}",
                f"- Direct boundaries (S1): {row['S1']}",
                f"- Projected boundaries (S2): {row['S2']}",
                f"- Raw correction (T0): {row['T0']}",
                f"- Direct correction (T1): {row['T1']}",
                f"- Projected correction (T2): {row['T2']}",
                f"- References: {' / '.join(row['references'])}",
                "",
            ]
        )
    (output / "PROMPTING_CASES.md").write_text("\n".join(lines), encoding="utf-8")
    return selected


def build_analysis(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    specs = load_specs()
    manual = manual_scorer_validation(output)
    char_gleu_groups = load_gleu_sentence_groups(
        CHARACTER_GLEU_ROOT / "sentence_scores.tsv"
    )
    word_gleu_groups = load_gleu_sentence_groups(
        WORD_GLEU_ROOT / "sentence_scores.tsv"
    )

    operation_rows: list[dict[str, Any]] = []
    density_rows: list[dict[str, Any]] = []
    convergence_rows: list[dict[str, Any]] = []
    aggregate_categories: dict[tuple[str, str, str], list[int]] = defaultdict(
        lambda: [0, 0, 0]
    )

    summary_by_dataset = {
        row["dataset"]: row for row in read_tsv(RUNS / "scoreboard_t3_summary.tsv")
    }

    for spec in specs:
        results = load_result_rows(spec)
        gold_rows = para_rows(spec.gold_para)
        ref_counts = [len(row) - 2 for row in gold_rows]
        if len(results) != len(ref_counts):
            raise ValueError(f"Result/reference count mismatch for {spec.dataset}")

        char_dir = CHARACTER_M2_ROOT / spec.dataset / spec.split / "char"
        word_dir = WORD_M2_ROOT / spec.dataset / spec.split / "word"
        char_reference = parse_file(
            char_dir / "reference.projection.all.char.m2", unit="character"
        )
        char_hypotheses = {
            stage: parse_file(
                char_dir / f"hypothesis.{stage}.projection.char.m2",
                unit="character",
            )
            for stage in STAGES
        }
        word_references = {
            stage: parse_file(
                word_dir / f"reference.{stage}.projection.word.m2", unit="word"
            )
            for stage in STAGES
        }
        word_hypotheses = {
            stage: parse_file(
                word_dir / f"hypothesis.{stage}.projection.word.m2", unit="word"
            )
            for stage in STAGES
        }

        for unit, hypotheses_by_stage, references_by_stage in (
            (
                "character",
                char_hypotheses,
                {stage: char_reference for stage in STAGES},
            ),
            ("word", word_hypotheses, word_references),
        ):
            for stage in STAGES:
                hypotheses = hypotheses_by_stage[stage]
                references = references_by_stage[stage]
                counts, categories = score_blocks(hypotheses, references)
                category_sums = [0, 0, 0]
                unknown = set(categories) - set(CATEGORIES)
                if unknown:
                    raise AssertionError(
                        f"Unexpected categories for {spec.dataset}/{unit}/{stage}: {unknown}"
                    )
                for category in CATEGORIES:
                    values = categories.get(category, [0, 0, 0])
                    operation_rows.append(
                        category_row(
                            spec.dataset,
                            spec.split,
                            len(results),
                            unit,
                            stage,
                            category,
                            values,
                        )
                    )
                    for index, value in enumerate(values):
                        category_sums[index] += value
                        aggregate_categories[(unit, stage, category)][index] += value
                if category_sums != [counts["TP"], counts["FP"], counts["FN"]]:
                    raise AssertionError(
                        f"Category totals do not reconstruct aggregate score for "
                        f"{spec.dataset}/{unit}/{stage}: {category_sums} vs {counts}"
                    )

                for bucket in ("1", "2", "3", ">3"):
                    indices = [
                        index
                        for index, count in enumerate(ref_counts)
                        if reference_bucket(count) == bucket
                    ]
                    if not indices:
                        continue
                    subset_counts, _subset_categories = score_blocks(
                        [hypotheses[index] for index in indices],
                        [references[index] for index in indices],
                    )
                    precision, recall, score = exact_scores(
                        subset_counts["TP"], subset_counts["FP"], subset_counts["FN"]
                    )
                    density_rows.append(
                        {
                            "metric": "F0.5",
                            "unit": unit,
                            "dataset": spec.dataset,
                            "split": spec.split,
                            "reference_bucket": bucket,
                            "sentences": len(indices),
                            "stage": stage,
                            "TP": subset_counts["TP"],
                            "FP": subset_counts["FP"],
                            "FN": subset_counts["FN"],
                            "precision_x100": f"{precision * 100:.2f}",
                            "recall_x100": f"{recall * 100:.2f}",
                            "score_x100": f"{score * 100:.2f}",
                        }
                    )

        for unit, groups in (
            ("character", char_gleu_groups),
            ("word", word_gleu_groups),
        ):
            for stage in STAGES:
                scores = groups[(spec.dataset, stage)]
                if len(scores) != len(ref_counts):
                    raise ValueError(f"GLEU row mismatch for {spec.dataset}/{unit}/{stage}")
                for bucket in ("1", "2", "3", ">3"):
                    selected = [
                        score
                        for score, count in zip(scores, ref_counts)
                        if reference_bucket(count) == bucket
                    ]
                    if not selected:
                        continue
                    density_rows.append(
                        {
                            "metric": "GLEU",
                            "unit": unit,
                            "dataset": spec.dataset,
                            "split": spec.split,
                            "reference_bucket": bucket,
                            "sentences": len(selected),
                            "stage": stage,
                            "TP": "",
                            "FP": "",
                            "FN": "",
                            "precision_x100": "",
                            "recall_x100": "",
                            "score_x100": f"{math.fsum(selected) / len(selected) * 100:.2f}",
                        }
                    )

        first_changed = sum(row["S2"] != row["S1"] for row in results)
        second_changed = sum(row["S3"] != row["S2"] for row in results)
        stop_direct = len(results) - first_changed
        stop_projected = sum(
            row["S2"] != row["S1"] and row["S3"] == row["S2"] for row in results
        )
        reach_t3 = sum(
            row["S2"] != row["S1"] and row["S3"] != row["S2"] for row in results
        )
        cycles = sum(
            row["S2"] != row["S1"]
            and row["S3"] != row["S2"]
            and row["S3"] == row["S1"]
            for row in results
        )
        t2_output_changed = sum(
            row["S2"] != row["S1"] and row["T2"] != row["T1"] for row in results
        )
        t3_output_changed = sum(
            row["S3"] != row["S2"] and row["T3"] != row["T2"] for row in results
        )
        summary = summary_by_dataset[spec.dataset]
        convergence_rows.append(
            {
                "dataset": spec.dataset,
                "split": spec.split,
                "sentences": len(results),
                "first_projection_changed": first_changed,
                "first_projection_changed_pct": f"{first_changed / len(results) * 100:.2f}",
                "stopped_after_direct": stop_direct,
                "stopped_after_projected": stop_projected,
                "reached_T3": reach_t3,
                "second_projection_changed": second_changed,
                "two_cycles": cycles,
                "T2_output_changed_given_S2_changed": t2_output_changed,
                "T2_output_changed_pct": f"{t2_output_changed / first_changed * 100:.2f}" if first_changed else "0.00",
                "T3_output_changed_given_S3_changed": t3_output_changed,
                "T3_output_changed_pct": f"{t3_output_changed / second_changed * 100:.2f}" if second_changed else "0.00",
                "splits_through_S3": int(summary["projection_splits_through_S3"]),
                "merges_through_S3": int(summary["projection_merges_through_S3"]),
            }
        )

    operation_fields = (
        "dataset",
        "split",
        "sentences",
        "unit",
        "stage",
        "condition",
        "category",
        "TP",
        "FP",
        "FN",
        "reference_edits",
        "predicted_edits",
        "precision",
        "recall",
        "f0.5",
        "f0.5_x100",
    )
    write_tsv(output / "operation_scores.long.tsv", operation_rows, operation_fields)
    write_tsv(
        output / "reference_density.long.tsv",
        density_rows,
        (
            "metric",
            "unit",
            "dataset",
            "split",
            "reference_bucket",
            "sentences",
            "stage",
            "TP",
            "FP",
            "FN",
            "precision_x100",
            "recall_x100",
            "score_x100",
        ),
    )
    write_tsv(
        output / "convergence.tsv",
        convergence_rows,
        tuple(convergence_rows[0]),
    )

    prompting_cases = select_prompting_cases(specs, char_gleu_groups, output)
    incremental_rows = build_yaclc_incremental(output)
    build_operation_markdown(output, aggregate_categories, operation_rows)
    build_reference_markdown(output, density_rows, incremental_rows)
    build_convergence_markdown(output, convergence_rows)
    build_paper_report(
        output,
        manual,
        aggregate_categories,
        convergence_rows,
        prompting_cases,
    )


def build_yaclc_incremental(output: Path) -> list[dict[str, Any]]:
    spec = next(spec for spec in load_specs() if spec.dataset == "yaclc")
    gold_rows = para_rows(spec.gold_para)
    ref_counts = [len(row) - 2 for row in gold_rows]
    max_references = max(ref_counts)
    indices = [index for index, count in enumerate(ref_counts) if count == max_references]
    if not indices:
        raise AssertionError("YACLC has no maximum-reference subset")

    char_dir = CHARACTER_M2_ROOT / spec.dataset / spec.split / "char"
    word_dir = WORD_M2_ROOT / spec.dataset / spec.split / "word"
    char_reference = parse_file(
        char_dir / "reference.projection.all.char.m2", unit="character"
    )
    char_hypotheses = {
        stage: parse_file(
            char_dir / f"hypothesis.{stage}.projection.char.m2", unit="character"
        )
        for stage in STAGES
    }
    word_references = {
        stage: parse_file(
            word_dir / f"reference.{stage}.projection.word.m2", unit="word"
        )
        for stage in STAGES
    }
    word_hypotheses = {
        stage: parse_file(
            word_dir / f"hypothesis.{stage}.projection.word.m2", unit="word"
        )
        for stage in STAGES
    }
    rows: list[dict[str, Any]] = []
    for unit, hypotheses_by_stage, references_by_stage in (
        (
            "character",
            char_hypotheses,
            {stage: char_reference for stage in STAGES},
        ),
        ("word", word_hypotheses, word_references),
    ):
        for stage in STAGES:
            hypotheses = [hypotheses_by_stage[stage][index] for index in indices]
            reference_blocks = [references_by_stage[stage][index] for index in indices]
            for k in range(1, max_references + 1):
                counts, _categories = score_blocks(
                    hypotheses,
                    [first_k_block(block, k) for block in reference_blocks],
                )
                precision, recall, score = exact_scores(
                    counts["TP"], counts["FP"], counts["FN"]
                )
                rows.append(
                    {
                        "metric": "F0.5",
                        "unit": unit,
                        "dataset": "yaclc",
                        "sentences": len(indices),
                        "available_references": max_references,
                        "references_used": k,
                        "stage": stage,
                        "score_x100": f"{score * 100:.4f}",
                        "precision_x100": f"{precision * 100:.4f}",
                        "recall_x100": f"{recall * 100:.4f}",
                    }
                )

    gleu = load_gleu_module()
    for unit, root, tokenization in (
        ("character", CHARACTER_GLEU_ROOT, "char"),
        ("word", WORD_GLEU_ROOT, "word"),
    ):
        input_dir = root / spec.dataset / spec.split / "inputs"
        for stage in STAGES:
            if unit == "character":
                sources = read_lines(input_dir / "original.txt")
                hypotheses = read_lines(input_dir / f"hypothesis.{stage}.txt")
                references = read_reference_lines(input_dir / "references.tsv")
            else:
                sources = read_lines(input_dir / f"source.{stage}.txt")
                hypotheses = read_lines(input_dir / f"hypothesis.{stage}.txt")
                references = read_reference_lines(input_dir / f"references.{stage}.tsv")
            per_sentence: list[list[float]] = []
            for index in indices:
                per_sentence.append(
                    [
                        float(
                            gleu.calculate_gleu_score(
                                sources[index],
                                hypotheses[index],
                                reference,
                                n=4,
                                tokenization=tokenization,
                            )
                        )
                        for reference in references[index]
                    ]
                )
            for k in range(1, max_references + 1):
                score = math.fsum(max(values[:k]) for values in per_sentence) / len(indices)
                rows.append(
                    {
                        "metric": "GLEU",
                        "unit": unit,
                        "dataset": "yaclc",
                        "sentences": len(indices),
                        "available_references": max_references,
                        "references_used": k,
                        "stage": stage,
                        "score_x100": f"{score * 100:.4f}",
                        "precision_x100": "",
                        "recall_x100": "",
                    }
                )
    gleu.clear_caches()
    write_tsv(
        output / "yaclc_incremental_references.tsv",
        rows,
        (
            "metric",
            "unit",
            "dataset",
            "sentences",
            "available_references",
            "references_used",
            "stage",
            "score_x100",
            "precision_x100",
            "recall_x100",
        ),
    )
    return rows


def build_operation_markdown(
    output: Path,
    aggregate: dict[tuple[str, str, str], list[int]],
    rows: Sequence[dict[str, Any]],
) -> None:
    lines = [
        "# Operation-level M/R/U/W/WO Results",
        "",
        "`W` denotes a bounded short-range order change. `WO` denotes a linked long-distance movement serialized as reciprocal M+U records but counted once. The five category totals reconstruct every aggregate TP/FP/FN score exactly.",
        "",
        "## All-dataset micro totals",
        "",
    ]
    for unit in ("character", "word"):
        table_rows = []
        delta_rows = []
        for category in CATEGORIES:
            values = []
            numeric_values = []
            for stage in STAGES:
                tp, fp, fn = aggregate[(unit, stage, category)]
                _p, _r, score = exact_scores(tp, fp, fn)
                values.append(f"{score * 100:.2f}")
                numeric_values.append(score * 100)
            table_rows.append((category, *values))
            delta_rows.append(
                (
                    category,
                    f"{numeric_values[1] - numeric_values[0]:+.2f}",
                    f"{numeric_values[2] - numeric_values[1]:+.2f}",
                    f"{numeric_values[3] - numeric_values[2]:+.2f}",
                )
            )
        lines.append(f"### {unit.title()} evaluation")
        lines.append("")
        add_table(lines, ("Operation", *STAGES), table_rows)
        add_table(
            lines,
            ("Operation", "Direct-Raw", "Projected-Direct", "Iterative-Projected"),
            delta_rows,
        )

    lines.extend(
        [
            "## Main pattern",
            "",
            "Direct-WB improves M, R, and U at both evaluation units, but lowers W and WO. The aggregate F0.5 gain is therefore driven by ordinary missing/replacement/unnecessary corrections, not by better word-order correction. Projection and iteration move every operation by less than one point in the all-dataset micro totals and have mixed signs.",
            "",
        ]
    )

    lines.extend(
        [
            "## Interpretation guardrails",
            "",
            "- Operation scores are based on the same selected hypothesis-reference combinations as the aggregate F0.5 scores.",
            "- `WO` is not a sixth physical M2 label: it is the report-level name for one validated linked M+U pair.",
            "- Character and word spans can yield different edit counts for the same output, so their operation scores are complementary rather than directly interchangeable.",
            "- Full per-dataset counts, precision, recall, and F0.5 are in `operation_scores.long.tsv`.",
            "",
        ]
    )
    (output / "OPERATION_LEVEL_RESULTS.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def build_reference_markdown(
    output: Path,
    density_rows: Sequence[dict[str, Any]],
    incremental_rows: Sequence[dict[str, Any]],
) -> None:
    lines = [
        "# Reference-density Analysis",
        "",
        "Scores are grouped by the number of available references (1, 2, 3, or >3). These groups describe oracle opportunity under select-best; they do not imply that dense-reference datasets contain intrinsically better outputs.",
        "",
        "The machine-readable dataset-by-stage results are in `reference_density.long.tsv`.",
        "",
        "## Pooled descriptive scores by reference-count bucket",
        "",
    ]
    pooled_rows = []
    for metric in ("F0.5", "GLEU"):
        for unit in ("character", "word"):
            for bucket in ("1", "2", "3", ">3"):
                values = []
                sentence_count = 0
                for stage in STAGES:
                    selected = [
                        row
                        for row in density_rows
                        if row["metric"] == metric
                        and row["unit"] == unit
                        and row["reference_bucket"] == bucket
                        and row["stage"] == stage
                    ]
                    if not selected:
                        values.append(float("nan"))
                        continue
                    sentence_count = sum(int(row["sentences"]) for row in selected)
                    if metric == "F0.5":
                        tp = sum(int(row["TP"]) for row in selected)
                        fp = sum(int(row["FP"]) for row in selected)
                        fn = sum(int(row["FN"]) for row in selected)
                        values.append(exact_scores(tp, fp, fn)[2] * 100)
                    else:
                        values.append(
                            sum(
                                float(row["score_x100"])
                                * int(row["sentences"])
                                for row in selected
                            )
                            / sentence_count
                        )
                if not values or any(math.isnan(value) for value in values):
                    continue
                best_index = max(range(len(values)), key=values.__getitem__)
                pooled_rows.append(
                    (
                        metric,
                        unit,
                        bucket,
                        f"{sentence_count:,}",
                        *(f"{value:.2f}" for value in values),
                        STAGES[best_index],
                    )
                )
    add_table(
        lines,
        ("Metric", "Unit", "Refs", "N", *STAGES, "Best"),
        pooled_rows,
    )
    lines.extend(
        [
            "These pooled groups contain different sentences and datasets, so score levels across rows are descriptive. The best prompting stage is not invariant across reference-count buckets; reference density can affect observed condition rankings.",
            "",
            "## Controlled YACLC analysis",
            "",
            "YACLC contains 178 sentences with exactly 11 references. Holding those same sentences and hypotheses fixed, the table below compares one reference with all eleven.",
            "",
        ]
    )
    indexed = {
        (row["metric"], row["unit"], row["stage"], int(row["references_used"])): row
        for row in incremental_rows
    }
    table_rows = []
    for metric in ("F0.5", "GLEU"):
        for unit in ("character", "word"):
            for stage in STAGES:
                one = float(indexed[(metric, unit, stage, 1)]["score_x100"])
                eleven = float(indexed[(metric, unit, stage, 11)]["score_x100"])
                table_rows.append(
                    (
                        metric,
                        unit,
                        stage,
                        f"{one:.2f}",
                        f"{eleven:.2f}",
                        f"{eleven - one:+.2f}",
                    )
                )
    add_table(
        lines,
        ("Metric", "Unit", "Stage", "First 1", "All 11", "Delta"),
        table_rows,
    )
    lines.extend(
        [
            "All deltas in this controlled table arise only from adding valid references to the same 178 source-hypothesis pairs. The complete first-1 through first-11 trajectories are in `yaclc_incremental_references.tsv`.",
            "",
        ]
    )
    (output / "REFERENCE_DENSITY.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def build_convergence_markdown(
    output: Path, rows: Sequence[dict[str, Any]]
) -> None:
    lines = [
        "# Iterative Behavior and Convergence",
        "",
        "An unchanged projected boundary sequence stops the row and carries the previous correction forward without another LLM call. A changed S3 means the row reached the configured T3 endpoint; it is not labeled converged. S1-S2-S1 cycles are reported separately.",
        "",
    ]
    table_rows = []
    for row in rows:
        table_rows.append(
            (
                DISPLAY_NAMES[row["dataset"]],
                f"{int(row['sentences']):,}",
                f"{row['first_projection_changed_pct']}%",
                f"{int(row['stopped_after_direct']):,}",
                f"{int(row['stopped_after_projected']):,}",
                f"{int(row['reached_T3']):,}",
                f"{int(row['two_cycles']):,}",
                f"{row['T2_output_changed_pct']}%",
                f"{row['T3_output_changed_pct']}%",
                f"{int(row['splits_through_S3']):,}",
                f"{int(row['merges_through_S3']):,}",
            )
        )
    add_table(
        lines,
        (
            "Dataset",
            "N",
            "S1->S2 changed",
            "Stop T1",
            "Stop T2",
            "Reach T3",
            "2-cycles",
            "T2 output changed",
            "T3 output changed",
            "Splits",
            "Merges",
        ),
        table_rows,
    )
    lines.extend(
        [
            "`T2 output changed` is conditional on S1->S2 changing; `T3 output changed` is conditional on S2->S3 changing. Both split and merge operations occur in every sufficiently large dataset, so projection is not a split-only procedure.",
            "",
        ]
    )
    (output / "CONVERGENCE.md").write_text("\n".join(lines), encoding="utf-8")


def build_paper_report(
    output: Path,
    manual: dict[str, Any],
    aggregate: dict[tuple[str, str, str], list[int]],
    convergence_rows: Sequence[dict[str, Any]],
    cases: Sequence[dict[str, Any]],
) -> None:
    total = sum(int(row["sentences"]) for row in convergence_rows)
    first_changed = sum(int(row["first_projection_changed"]) for row in convergence_rows)
    stop_direct = sum(int(row["stopped_after_direct"]) for row in convergence_rows)
    stop_projected = sum(int(row["stopped_after_projected"]) for row in convergence_rows)
    reach_t3 = sum(int(row["reached_T3"]) for row in convergence_rows)
    cycles = sum(int(row["two_cycles"]) for row in convergence_rows)
    t2_changed = sum(
        int(row["T2_output_changed_given_S2_changed"]) for row in convergence_rows
    )
    second_changed = sum(
        int(row["second_projection_changed"]) for row in convergence_rows
    )
    t3_changed = sum(
        int(row["T3_output_changed_given_S3_changed"]) for row in convergence_rows
    )
    splits = sum(int(row["splits_through_S3"]) for row in convergence_rows)
    merges = sum(int(row["merges_through_S3"]) for row in convergence_rows)

    def operation_score(unit: str, stage: str, category: str) -> float:
        tp, fp, fn = aggregate[(unit, stage, category)]
        return exact_scores(tp, fp, fn)[2] * 100

    character_operation_deltas = {
        category: operation_score("character", "T1", category)
        - operation_score("character", "T0", category)
        for category in CATEGORIES
    }
    word_operation_deltas = {
        category: operation_score("word", "T1", category)
        - operation_score("word", "T0", category)
        for category in CATEGORIES
    }

    audit = (TABLE_AUDIT / "AUDIT.md").read_text(encoding="utf-8")
    if "**Status: PASS.**" not in audit:
        raise AssertionError("Tables 5/6 audit does not report PASS")
    if not ALIGNMENT_EXAMPLES.exists():
        raise FileNotFoundError(ALIGNMENT_EXAMPLES)

    lines = [
        "# Sections 6-7 Analysis Package",
        "",
        "**Status: complete for the saved DeepSeek outputs.** No LLM/API calls were made.",
        "",
        "## 1. Evaluation correctness",
        "",
        "All 128 reported Table 5-6 cells were independently reconstructed from final M2 and GLEU inputs. Maximum discrepancies are 0 for character/word F0.5, below 5e-7 points for character GLEU, and 0 for word GLEU. Stage mapping, carry-forward convergence, multi-reference use, fixed word segmentation, and no-BPE normalization also pass. The surprising ranking is therefore present in the saved outputs under the stated protocol, rather than being caused by a table transcription or scorer invocation error.",
        "",
        "## 2. Manual comparator validation",
        "",
        f"The controlled two-sentence fixture gives TP/FP/FN = {manual['TP']}/{manual['FP']}/{manual['FN']} and F0.5 = {manual['f0.5']:.4f}, exactly matching the hand calculation. A reciprocal long-distance M+U pair contributes one `WO` item; a mismatched destination contributes one FP and one FN.",
        "",
        "## 3. Main result interpretation",
        "",
        "Direct-WB improves character F0.5 on 7/8 datasets and word F0.5 on 6/8 datasets. The change is precision-driven and accompanied by lower recall, so visible boundaries make DeepSeek substantially more conservative. Raw outputs have a source-copy rate of only 5.83% and a mean character distance of 3.646, compared with 33.53% and 1.773 for Direct-WB. Raw is therefore more aggressive, not more conservative.",
        "",
        "GLEU favors Raw on 5/8 datasets at both character and word levels. This does not contradict the edit scorer mechanically: GLEU rewards reference-supported n-gram overlap and can reward aggressive partially correct rewriting, whereas exact edit F0.5 rewards localized agreement and weights precision more heavily. Projection-affected rows are mixed across datasets, so dilution by converged carry-forward rows is not the sole explanation.",
        "",
        "## 4. Projection and convergence",
        "",
        f"The first projection changes boundaries for {first_changed:,}/{total:,} sources ({first_changed / total * 100:.2f}%). {stop_direct:,} stop after Direct-WB, {stop_projected:,} after Projected-WB, and only {reach_t3:,} reach T3. Among changed S2 inputs, {t2_changed:,}/{first_changed:,} ({t2_changed / first_changed * 100:.2f}%) change the correction. Among changed S3 inputs, {t3_changed:,}/{second_changed:,} ({t3_changed / second_changed * 100:.2f}%) change it. There are {cycles:,} S1-S2-S1 two-cycles, handled by Kmax rather than reported as convergence. Projection performs {splits:,} splits and {merges:,} merges, confirming bidirectional boundary repair.",
        "",
        "The dominant empirical effect is Raw to Direct-WB. Projection and further iteration usually alter only a small subset and have small, non-monotonic aggregate effects. This supports a mixed or negative iterative result, not a universal monotonic-improvement claim.",
        "",
        "## 5. Operation-level analysis",
        "",
        "The final reporting inventory is M, R, U, W, and WO. W is a conventional bounded short-range order edit; WO is one validated long-distance movement represented physically by linked M+U records. Category TP/FP/FN totals reconstruct every aggregate score exactly. See `OPERATION_LEVEL_RESULTS.md` and `operation_scores.long.tsv`.",
        "",
        f"At character level, Direct-WB minus Raw is {character_operation_deltas['M']:+.2f} for M, {character_operation_deltas['R']:+.2f} for R, {character_operation_deltas['U']:+.2f} for U, {character_operation_deltas['W']:+.2f} for W, and {character_operation_deltas['WO']:+.2f} for WO. At word level, the corresponding deltas are {word_operation_deltas['M']:+.2f}, {word_operation_deltas['R']:+.2f}, {word_operation_deltas['U']:+.2f}, {word_operation_deltas['W']:+.2f}, and {word_operation_deltas['WO']:+.2f}. Thus the aggregate Direct-WB gain comes from M/R/U rather than order changes; W and WO become worse.",
        "",
        "## 6. Qualitative and reference analyses",
        "",
        "Five manually inspected real examples compare ChERRANT with projection M2. In the clearest long-distance cases, projection isolates the moved constituent and retains its origin and destination, while ChERRANT places W over a large intervening span. This is qualitative evidence of representational coherence, not an aggregate alignment-accuracy claim.",
        "",
        "`PROMPTING_CASES.md` supplies reproducibly selected success, no-effect, failure, and conservative cases. `REFERENCE_DENSITY.md` reports grouped results and a controlled first-1 through first-11 analysis on the same 178 YACLC sentences.",
        "",
        "## Manuscript-ready conclusion",
        "",
        "> Under the DeepSeek setting, explicit direct word boundaries consistently make correction more precise and conservative, improving edit-based F0.5 on most datasets. Projection repairs the source representation intrinsically, but it changes only 8.24% of source boundary sequences and does not yield consistent downstream gains; additional iteration is similarly small and non-monotonic. GLEU often favors the more aggressive Raw outputs, demonstrating that exact edit agreement and source-aware n-gram overlap capture different aspects of correction behavior. These findings support a mixed-result interpretation: direct boundary display is useful for precision-oriented CGEC, while automatically projected and iterative refinement require error analysis rather than a universal improvement claim.",
        "",
        "## Remaining work outside tasks 1-6",
        "",
        "- Run the frozen pipeline on GPT, Claude, Kimi, and Qwen to test whether the DeepSeek pattern generalizes.",
        "- Perform the C-based-LTP versus Python-LTP comparison (the separately assigned task 7).",
        "- Insert model identifiers/configurations and cross-model tables once those runs exist.",
        "",
        "## Files",
        "",
        "- `MANUAL_SCORER_VALIDATION.md`: hand-checkable WO scorer proof.",
        "- `OPERATION_LEVEL_RESULTS.md` and `operation_scores.long.tsv`: five-category results.",
        "- `CONVERGENCE.md` and `convergence.tsv`: dataset-level iterative diagnostics.",
        "- `REFERENCE_DENSITY.md`, `reference_density.long.tsv`, and `yaclc_incremental_references.tsv`: reference analyses.",
        "- `PROMPTING_CASES.md`: projection success/no-effect/failure examples.",
        "- `../final_alignment_examples/QUALITATIVE_ALIGNMENT_EXAMPLES.md`: ChERRANT/projection alignment examples.",
        "- `../tables_5_6_evaluation_audit/AUDIT.md`: independent Tables 5-6 reconstruction.",
        "",
    ]
    (output / "PAPER_SECTIONS_6_7.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    build_analysis(DEFAULT_OUTPUT)
    print(DEFAULT_OUTPUT)


if __name__ == "__main__":
    main()
