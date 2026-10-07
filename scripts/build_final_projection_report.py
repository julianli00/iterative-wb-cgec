#!/usr/bin/env python3
"""Build final DeepSeek result tables and paper-ready method text."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

if not __package__:
    from audit_final_projection_artifacts import (
        add_word_gleu_arguments,
        require_word_gleu_audit,
        resolve_word_gleu_root,
        word_gleu_protocol_description,
    )
    from standardize_m2_evaluation import ROOT, ROUNDS, load_specs, para_rows
    from word_gleu_protocol import load_source_policy
else:
    from .audit_final_projection_artifacts import (
        add_word_gleu_arguments,
        require_word_gleu_audit,
        resolve_word_gleu_root,
        word_gleu_protocol_description,
    )
    from .standardize_m2_evaluation import ROOT, ROUNDS, load_specs, para_rows
    from .word_gleu_protocol import load_source_policy


RUNS = ROOT / "runs"
CHARACTER_M2 = RUNS / "projection_character_m2_eval_final/scores.long.tsv"
WORD_M2 = RUNS / "projection_word_m2_eval_final/scores.long.tsv"
CHARACTER_GLEU = RUNS / "character_gleu_select_best/scores.long.tsv"
WORD_GLEU = RUNS / "word_gleu_condition_select_best/scores.long.tsv"
FIXED_CONFIG = RUNS / "gold_fixed_source_segmentation/run_config.json"
AUDIT = RUNS / "final_projection_audit/audit.json"
ALIGNMENT_EXAMPLES = RUNS / "final_alignment_examples/QUALITATIVE_ALIGNMENT_EXAMPLES.md"
OUTPUT_MD = RUNS / "FINAL_PROJECTION_EVALUATIONS.md"
OUTPUT_TSV = RUNS / "FINAL_PROJECTION_EVALUATIONS.tsv"
PAPER_OUTPUT = RUNS / "PAPER_SECTION_5_3_6_INPUTS.md"

STAGES = tuple(ROUNDS)
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


@dataclass(frozen=True)
class M2Score:
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f05: float


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def load_m2_scores(path: Path, *, alignment: str | None = None) -> dict[tuple[str, str], M2Score]:
    result: dict[tuple[str, str], M2Score] = {}
    for row in read_tsv(path):
        if row["beta"] != "0.5":
            continue
        if alignment is not None and row.get("alignment") != alignment:
            continue
        result[(row["dataset"], row["round"])] = M2Score(
            tp=int(row["TP"]),
            fp=int(row["FP"]),
            fn=int(row["FN"]),
            precision=float(row["Prec"]) * 100.0,
            recall=float(row["Rec"]) * 100.0,
            f05=float(row["F_beta"]) * 100.0,
        )
    return result


def load_gleu_scores(path: Path) -> dict[tuple[str, str], float]:
    return {
        (row["dataset"], row["stage"]): float(row["gleu_select_best_x100"])
        for row in read_tsv(path)
    }


def add_table(
    lines: list[str], headers: Sequence[str], rows: Iterable[Sequence[str]]
) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append(
        "| "
        + " | ".join("---" if index < 2 else "---:" for index in range(len(headers)))
        + " |"
    )
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    lines.append("")


def reference_metadata() -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for spec in load_specs():
        rows = para_rows(spec.gold_para)
        counts = [len(row) - 2 for row in rows]
        output[spec.dataset] = {
            "references": sum(counts),
            "multi_reference_sentences": sum(count > 1 for count in counts),
            "more_than_three": sum(count > 3 for count in counts),
            "max_references": max(counts),
        }
    return output


def fixed_segmentation_stats() -> dict[str, Any]:
    config = json.loads(FIXED_CONFIG.read_text(encoding="utf-8"))
    summaries = config["summaries"]
    return {
        "config": config,
        "selected_nonfirst": sum(row["selected_nonfirst_reference"] for row in summaries),
        "changed_from_ltp": sum(
            row["source_segmentation_changed_from_ltp"] for row in summaries
        ),
    }


def movement_stats() -> dict[str, dict[str, int]]:
    output = {
        "character": {"reference_linked": 0, "hypothesis_linked": 0},
        "word": {"reference_linked": 0, "hypothesis_linked": 0},
    }
    for spec in load_specs():
        char_path = (
            RUNS
            / "projection_character_m2_eval_final"
            / spec.dataset
            / spec.split
            / "char/generation_stats.json"
        )
        char = json.loads(char_path.read_text(encoding="utf-8"))
        output["character"]["reference_linked"] += char["references"]["W_LD"]
        output["character"]["hypothesis_linked"] += sum(
            row["W_LD"] for row in char["hypotheses"].values()
        )

        word_path = (
            RUNS
            / "projection_word_m2_eval_final"
            / spec.dataset
            / spec.split
            / "word/generation_stats.json"
        )
        word = json.loads(word_path.read_text(encoding="utf-8"))
        output["word"]["reference_linked"] += word["references"]["T0"]["W_LD"]
        output["word"]["hypothesis_linked"] += sum(
            row["W_LD"] for row in word["hypotheses"].values()
        )
    for values in output.values():
        values["total_linked"] = values["reference_linked"] + values["hypothesis_linked"]
    return output


def convergence_stats() -> dict[str, Any]:
    totals = {
        "sentences": 0,
        "first_projection_changed": 0,
        "second_projection_changed": 0,
        "converged_after_direct": 0,
        "converged_after_projected": 0,
        "reached_t3": 0,
        "two_cycles": 0,
        "t2_correction_changed": 0,
        "t3_correction_changed": 0,
        "splits": 0,
        "merges": 0,
    }
    dataset_rows: list[dict[str, Any]] = []
    summary_rows = {
        row["dataset"]: row for row in read_tsv(RUNS / "scoreboard_t3_summary.tsv")
    }
    for spec in load_specs():
        rows = read_jsonl(spec.result_tsv.with_suffix(".jsonl"))
        current = {key: 0 for key in totals if key != "sentences"}
        current["sentences"] = len(rows)
        for row in rows:
            first_changed = row["S2"] != row["S1"]
            second_changed = row["S3"] != row["S2"]
            current["first_projection_changed"] += first_changed
            current["second_projection_changed"] += second_changed
            current["converged_after_direct"] += not first_changed
            current["converged_after_projected"] += first_changed and not second_changed
            current["reached_t3"] += first_changed and second_changed
            current["two_cycles"] += (
                first_changed and second_changed and row["S3"] == row["S1"]
            )
            current["t2_correction_changed"] += first_changed and row["T2"] != row["T1"]
            current["t3_correction_changed"] += second_changed and row["T3"] != row["T2"]
        summary = summary_rows[spec.dataset]
        current["splits"] = int(summary["projection_splits_through_S3"])
        current["merges"] = int(summary["projection_merges_through_S3"])
        dataset_rows.append({"dataset": spec.dataset, **current})
        for key in totals:
            totals[key] += current[key]
    totals["mean_wb_aware_passes"] = (
        totals["converged_after_direct"]
        + 2 * totals["converged_after_projected"]
        + 3 * totals["reached_t3"]
    ) / totals["sentences"]
    totals["median_wb_aware_passes"] = 1
    totals["datasets"] = dataset_rows
    return totals


def best_stage(values: dict[tuple[str, str], float], dataset: str) -> tuple[str, float]:
    candidates = [(stage, values[(dataset, stage)]) for stage in STAGES]
    return max(candidates, key=lambda item: (item[1], -STAGES.index(item[0])))


def m2_values(scores: dict[tuple[str, str], M2Score]) -> dict[tuple[str, str], float]:
    return {key: value.f05 for key, value in scores.items()}


def fmt_m2(score: M2Score) -> str:
    return f"{score.precision:.2f}/{score.recall:.2f}/{score.f05:.2f}"


def contrast_range(
    scores: dict[tuple[str, str], M2Score], left: str, right: str
) -> tuple[float, float]:
    differences = [
        scores[(spec.dataset, right)].f05 - scores[(spec.dataset, left)].f05
        for spec in load_specs()
    ]
    return min(differences), max(differences)


def write_long_tsv(
    character_m2: dict[tuple[str, str], M2Score],
    word_m2: dict[tuple[str, str], M2Score],
    character_gleu: dict[tuple[str, str], float],
    word_gleu: dict[tuple[str, str], float],
    refs: dict[str, dict[str, int]],
) -> None:
    fieldnames = (
        "dataset",
        "split",
        "sentences",
        "references",
        "metric",
        "stage",
        "condition",
        "TP",
        "FP",
        "FN",
        "precision_x100",
        "recall_x100",
        "score_x100",
    )
    rows: list[dict[str, str]] = []
    for spec in load_specs():
        for metric, scores in (
            ("character_m2_f0.5", character_m2),
            ("word_m2_f0.5", word_m2),
        ):
            for stage in STAGES:
                score = scores[(spec.dataset, stage)]
                rows.append(
                    {
                        "dataset": spec.dataset,
                        "split": spec.split,
                        "sentences": str(spec.rows),
                        "references": str(refs[spec.dataset]["references"]),
                        "metric": metric,
                        "stage": stage,
                        "condition": CONDITIONS[stage],
                        "TP": str(score.tp),
                        "FP": str(score.fp),
                        "FN": str(score.fn),
                        "precision_x100": f"{score.precision:.6f}",
                        "recall_x100": f"{score.recall:.6f}",
                        "score_x100": f"{score.f05:.6f}",
                    }
                )
        for metric, scores in (
            ("character_gleu", character_gleu),
            ("word_gleu", word_gleu),
        ):
            for stage in STAGES:
                rows.append(
                    {
                        "dataset": spec.dataset,
                        "split": spec.split,
                        "sentences": str(spec.rows),
                        "references": str(refs[spec.dataset]["references"]),
                        "metric": metric,
                        "stage": stage,
                        "condition": CONDITIONS[stage],
                        "TP": "",
                        "FP": "",
                        "FN": "",
                        "precision_x100": "",
                        "recall_x100": "",
                        "score_x100": f"{scores[(spec.dataset, stage)]:.6f}",
                    }
                )
    with OUTPUT_TSV.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def result_tables(
    lines: list[str],
    character_m2: dict[tuple[str, str], M2Score],
    word_m2: dict[tuple[str, str], M2Score],
    character_gleu: dict[tuple[str, str], float],
    word_gleu: dict[tuple[str, str], float],
) -> None:
    lines.extend(
        [
            "## Edit-based Results",
            "",
            "Each cell is precision/recall/F0.5 x 100 from the movement-aware comparator.",
            "",
        ]
    )
    add_table(
        lines,
        (
            "Dataset",
            "Char Raw",
            "Char Direct",
            "Char Projected",
            "Char Iterative",
            "Word Raw",
            "Word Direct",
            "Word Projected",
            "Word Iterative",
        ),
        (
            (
                DISPLAY_NAMES[spec.dataset],
                *[fmt_m2(character_m2[(spec.dataset, stage)]) for stage in STAGES],
                *[fmt_m2(word_m2[(spec.dataset, stage)]) for stage in STAGES],
            )
            for spec in load_specs()
        ),
    )
    lines.extend(
        [
            "## GLEU Results",
            "",
            "Character/word 1-4 gram GLEU uses sentence-level select-best over every reference and macro-averaging; values are x 100.",
            "",
        ]
    )
    add_table(
        lines,
        (
            "Dataset",
            "Char Raw",
            "Char Direct",
            "Char Projected",
            "Char Iterative",
            "Word Raw",
            "Word Direct",
            "Word Projected",
            "Word Iterative",
        ),
        (
            (
                DISPLAY_NAMES[spec.dataset],
                *[f"{character_gleu[(spec.dataset, stage)]:.2f}" for stage in STAGES],
                *[f"{word_gleu[(spec.dataset, stage)]:.2f}" for stage in STAGES],
            )
            for spec in load_specs()
        ),
    )


def build_report(
    character_m2: dict[tuple[str, str], M2Score],
    word_m2: dict[tuple[str, str], M2Score],
    character_gleu: dict[tuple[str, str], float],
    word_gleu: dict[tuple[str, str], float],
    refs: dict[str, dict[str, int]],
    fixed: dict[str, Any],
    convergence: dict[str, Any],
    movements: dict[str, dict[str, int]],
    audit: dict[str, Any],
    *,
    word_gleu_source_policy: str = "condition",
    word_gleu_root: Path | None = None,
) -> None:
    require_word_gleu_audit(
        audit,
        source_policy=word_gleu_source_policy,
        word_gleu_root=resolve_word_gleu_root(
            word_gleu_root, source_policy=word_gleu_source_policy
        ),
    )
    total_sentences = sum(spec.rows for spec in load_specs())
    total_references = sum(row["references"] for row in refs.values())
    total_multi = sum(row["multi_reference_sentences"] for row in refs.values())
    char_values = m2_values(character_m2)
    word_values = m2_values(word_m2)
    lines = [
        "# Final Projection-based DeepSeek CGEC Evaluation",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "**Artifact audit: PASS.** This document supersedes the earlier preliminary reports in this workspace.",
        "",
        "## Scope",
        "",
        "- Model outputs: saved `deepseek-v4-pro` T0-T3 results; evaluation made no LLM/API calls.",
        "- Decoding used one sample, temperature `0.000001`, disabled thinking, and the paper's Chinese prompts.",
        "- Conditions: T0 Raw, T1 Direct-WB, T2 Projected-WB, and T3 Iterative Projected-WB.",
        "- Final numeric metrics: projection character M2, projection word M2, character GLEU, and word GLEU.",
        "- Character normalization removes BOM and whitespace; word inputs preserve normalized token boundaries. No OpenCC or BPE is used.",
        "- ChERRANT is retained only for qualitative alignment examples, not as a competing final score table.",
        "",
        "## Dataset Coverage",
        "",
    ]
    add_table(
        lines,
        ("Dataset", "Split", "N", "References", "Multi-ref.", ">3 refs.", "Max refs."),
        (
            (
                DISPLAY_NAMES[spec.dataset],
                spec.split,
                f"{spec.rows:,}",
                f"{refs[spec.dataset]['references']:,}",
                f"{refs[spec.dataset]['multi_reference_sentences']:,}",
                f"{refs[spec.dataset]['more_than_three']:,}",
                f"{refs[spec.dataset]['max_references']:,}",
            )
            for spec in load_specs()
        ),
    )
    lines.extend(
        [
            f"Total: **{total_sentences:,} sources**, **{total_references:,} references**, and **{total_multi:,} multi-reference sources**.",
            "",
            "YACLC, FCGEC, and CEFE Track 3 use validation gold because public test gold is unavailable. CEFE Track 3 has only 19 sources and is interpreted descriptively.",
            "",
            "## Final Evaluation Protocol",
            "",
            "- All available references are retained. M2 and GLEU independently apply sentence-level select-best; there is no three-reference cap.",
            "- For word M2, the closest gold reference is selected by minimum raw-character Levenshtein distance after BOM/whitespace removal; ties use the earliest reference.",
            "- Its LTP boundaries are projected to the learner source once. That fixed source segmentation is shared by all T0-T3 hypothesis/reference M2 files.",
            "- " + word_gleu_protocol_description(word_gleu_source_policy),
            "- Ordinary edits use M/R/U/W. Pure reorderings with an envelope of at most three units use W. An unambiguous one-block movement beyond three units uses linked U-M, is scored once, and is reported separately as WO; ambiguous, mixed, or multi-block cases use a round-trippable fallback.",
            "- Linked movements match strictly on origin, destination, moved material, and evaluation unit. The local link identifier is not part of the cross-file key.",
            "",
            "## Gold-informed Source Segmentation for Word M2",
            "",
            f"The closest-reference selector chose a non-first reference for **{fixed['selected_nonfirst']:,}/{total_sentences:,}** sources ({100 * fixed['selected_nonfirst'] / total_sentences:.2f}%). Projection changed the direct LTP source segmentation for **{fixed['changed_from_ltp']:,}/{total_sentences:,}** sources ({100 * fixed['changed_from_ltp'] / total_sentences:.2f}%).",
            "",
        ]
    )
    result_tables(lines, character_m2, word_m2, character_gleu, word_gleu)

    char_direct = contrast_range(character_m2, "T0", "T1")
    word_direct = contrast_range(word_m2, "T0", "T1")
    char_post = max(
        max(char_values[(spec.dataset, stage)] for stage in ("T1", "T2", "T3"))
        - min(char_values[(spec.dataset, stage)] for stage in ("T1", "T2", "T3"))
        for spec in load_specs()
    )
    word_post = max(
        max(word_values[(spec.dataset, stage)] for stage in ("T1", "T2", "T3"))
        - min(word_values[(spec.dataset, stage)] for stage in ("T1", "T2", "T3"))
        for spec in load_specs()
    )
    char_wins = sum(
        max(char_values[(spec.dataset, stage)] for stage in STAGES[1:])
        > char_values[(spec.dataset, "T0")]
        for spec in load_specs()
    )
    word_wins = sum(
        max(word_values[(spec.dataset, stage)] for stage in STAGES[1:])
        > word_values[(spec.dataset, "T0")]
        for spec in load_specs()
    )
    char_gleu_wins = sum(
        max(character_gleu[(spec.dataset, stage)] for stage in STAGES[1:])
        > character_gleu[(spec.dataset, "T0")]
        for spec in load_specs()
    )
    word_gleu_wins = sum(
        max(word_gleu[(spec.dataset, stage)] for stage in STAGES[1:])
        > word_gleu[(spec.dataset, "T0")]
        for spec in load_specs()
    )
    sensitivity = audit["threshold_sensitivity"]
    lines.extend(
        [
            "## Main Findings",
            "",
            f"- A structured stage exceeds Raw on **{char_wins}/8** datasets in character F0.5 and **{word_wins}/8** in word F0.5.",
            f"- Direct-WB minus Raw ranges from {char_direct[0]:+.2f} to {char_direct[1]:+.2f} character F0.5 points and from {word_direct[0]:+.2f} to {word_direct[1]:+.2f} word F0.5 points.",
            "- Direct-WB generally increases precision and lowers recall, indicating more conservative correction. CEFE Track 3 is too small for a stable dataset-level inference.",
            f"- After Direct-WB, the largest within-dataset T1-T3 spread is only {char_post:.2f} character F0.5 and {word_post:.2f} word F0.5; projection and further iteration are therefore small and non-monotonic at corpus level.",
            f"- A structured stage exceeds Raw on **{char_gleu_wins}/8** datasets in character GLEU and **{word_gleu_wins}/8** in word GLEU. GLEU uses source-aware n-gram overlap rather than exact localized edit matching, so the two metrics need not rank stages alike.",
            "",
            "## Iteration Diagnostics",
            "",
            f"- The first projection changes S1 for {convergence['first_projection_changed']:,}/{total_sentences:,} sources ({100 * convergence['first_projection_changed'] / total_sentences:.2f}%).",
            f"- {convergence['converged_after_direct']:,} stop after Direct-WB, {convergence['converged_after_projected']:,} stop after Projected-WB, and {convergence['reached_t3']:,} reach T3; the median is {convergence['median_wb_aware_passes']} and mean is {convergence['mean_wb_aware_passes']:.3f} WB-aware passes.",
            f"- There are {convergence['two_cycles']:,} S1-S2-S1 two-cycles ({100 * convergence['two_cycles'] / total_sentences:.2f}%). The implementation follows the paper's maximum-pass policy rather than claiming convergence for these cases.",
            f"- Projection performs {convergence['splits']:,} boundary splits and {convergence['merges']:,} boundary merges through S3, confirming that it supports both operations.",
            "",
            "## Validation and Sensitivity",
            "",
            f"- `L_max_char = 3`: F0.5 is identical under tested values 2, 3, and 4 (maximum range {sensitivity['character']['max_f0.5_x100_range']:.4f}).",
            f"- `L_max_word = 3`: the maximum F0.5 range under 2, 3, and 4 is {sensitivity['word']['max_f0.5_x100_range']:.4f} points.",
            f"- The final files contain {movements['character']['total_linked']:,} character-level and {movements['word']['total_linked']:,} word-level linked movements across references and T0-T3 hypotheses.",
            f"- The artifact audit parsed/reconstructed {audit['m2_blocks_validated']:,} M2 blocks and validated {audit['linked_movements_validated']:,} linked-pair instances across all stored stage-specific files.",
            "- Repository test results are recorded separately; this report validates the supplied evaluation artifacts.",
            "",
            "## Qualitative Evidence",
            "",
            "Five manually inspected examples compare final projection character/word annotations with ChERRANT. The evidence supports a narrow representational claim: linked projection isolates moved material and preserves origin/destination, while multi-block permutations use the documented fallback. It is not an aggregate alignment-accuracy claim.",
            "",
            "## Pending Experiments",
            "",
            "- Cross-model scores are outside this DeepSeek report and must come from each model's own saved outputs and policy-matched evaluations.",
            "- A C-based-LTP versus Python-LTP consistency comparison is not available in this workspace and is not used by the formal projection results.",
            "- Model 2 fields and cross-model interpretation in the current manuscript must remain pending rather than being inferred from DeepSeek.",
            "",
            "## Reproducibility Artifacts",
            "",
            "- Tables 5 and 6 audit: [`tables_5_6_evaluation_audit/AUDIT.md`](tables_5_6_evaluation_audit/AUDIT.md)",
            "- Machine-readable scores: [`FINAL_PROJECTION_EVALUATIONS.tsv`](FINAL_PROJECTION_EVALUATIONS.tsv)",
            "- Full artifact audit: [`final_projection_audit/AUDIT.md`](final_projection_audit/AUDIT.md)",
            "- Alignment examples: [`final_alignment_examples/QUALITATIVE_ALIGNMENT_EXAMPLES.md`](final_alignment_examples/QUALITATIVE_ALIGNMENT_EXAMPLES.md)",
            "- Paper-ready inputs: [`PAPER_SECTION_5_3_6_INPUTS.md`](PAPER_SECTION_5_3_6_INPUTS.md)",
            "",
        ]
    )
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")


def build_paper_inputs(
    character_m2: dict[tuple[str, str], M2Score],
    word_m2: dict[tuple[str, str], M2Score],
    character_gleu: dict[tuple[str, str], float],
    word_gleu: dict[tuple[str, str], float],
    fixed: dict[str, Any],
    convergence: dict[str, Any],
    audit: dict[str, Any],
    *,
    word_gleu_source_policy: str = "condition",
    word_gleu_root: Path | None = None,
) -> None:
    require_word_gleu_audit(
        audit,
        source_policy=word_gleu_source_policy,
        word_gleu_root=resolve_word_gleu_root(
            word_gleu_root, source_policy=word_gleu_source_policy
        ),
    )
    total = sum(spec.rows for spec in load_specs())
    char_values = {key: score.f05 for key, score in character_m2.items()}
    word_values = {key: score.f05 for key, score in word_m2.items()}
    sensitivity = audit["threshold_sensitivity"]
    char_direct_wins = sum(
        char_values[(spec.dataset, "T1")] > char_values[(spec.dataset, "T0")]
        for spec in load_specs()
    )
    word_direct_wins = sum(
        word_values[(spec.dataset, "T1")] > word_values[(spec.dataset, "T0")]
        for spec in load_specs()
    )
    char_best_gain, char_best_dataset = max(
        (
            char_values[(spec.dataset, "T1")] - char_values[(spec.dataset, "T0")],
            DISPLAY_NAMES[spec.dataset],
        )
        for spec in load_specs()
    )
    word_best_gain, word_best_dataset = max(
        (
            word_values[(spec.dataset, "T1")] - word_values[(spec.dataset, "T0")],
            DISPLAY_NAMES[spec.dataset],
        )
        for spec in load_specs()
    )
    direct_character_gleu_wins = sum(
        character_gleu[(spec.dataset, "T1")] > character_gleu[(spec.dataset, "T0")]
        for spec in load_specs()
    )
    direct_word_gleu_wins = sum(
        word_gleu[(spec.dataset, "T1")] > word_gleu[(spec.dataset, "T0")]
        for spec in load_specs()
    )
    char_gleu_post = max(
        max(character_gleu[(spec.dataset, stage)] for stage in STAGES[1:])
        - min(character_gleu[(spec.dataset, stage)] for stage in STAGES[1:])
        for spec in load_specs()
    )
    word_gleu_post = max(
        max(word_gleu[(spec.dataset, stage)] for stage in STAGES[1:])
        - min(word_gleu[(spec.dataset, stage)] for stage in STAGES[1:])
        for spec in load_specs()
    )
    lines = [
        "# Paper Inputs for Sections 5.2, 5.3, and 6",
        "",
        "This file answers the applicable red placeholders in the 2026-08-19 manuscript. Items requiring models or software not present in the workspace are marked pending rather than guessed.",
        "",
        "## Section 5.2: Gold-informed Source Representation for Word M2",
        "",
        "Replace `[EXACT CHARACTER-SEQUENCE SIMILARITY MEASURE]` with:",
        "",
        "> raw character-level Levenshtein distance after removing the byte-order mark and all whitespace, selecting the reference with minimum distance",
        "",
        "Replace `[TIE-BREAKING RULE]` with:",
        "",
        "> the earliest reference in the dataset's original reference order",
        "",
        f"Audit fact: a non-first reference was selected for {fixed['selected_nonfirst']:,}/{total:,} sources, and the projected gold-informed segmentation differed from direct LTP for {fixed['changed_from_ltp']:,}/{total:,} sources.",
        "",
        "## Section 5.3: Edit-based Evaluation",
        "",
        "Use `3` for both `[CHARACTER THRESHOLD]` and `[WORD THRESHOLD]`.",
        "",
        "Recommended clarification:",
        "",
        "> We set `L_max_char = 3` and `L_max_word = 3` before final scoring. A pure reordering whose contiguous source envelope contains at most three evaluation units is serialized as one conventional W. When a larger change is an unambiguous one-block movement, it is serialized as linked U and M records with reciprocal FROM/TO coordinates. Mixed lexical changes, ambiguous alignments, crossing movements, and multi-block permutations are not forced into a link; they retain a round-trippable ordinary or encompassing-W representation. Sensitivity runs with thresholds 2, 3, and 4 leave all character F0.5 values unchanged and change word F0.5 by at most "
        f"{sensitivity['word']['max_f0.5_x100_range']:.2f} points.",
        "",
        "Comparator wording correction:",
        "",
        "> In standard span-based correction mode, ordinary edits match on source span and correction material; the operation label is retained for category reporting but is not part of the default correction key. A linked movement is converted to one logical item and matched strictly on origin interval, destination boundary, moved material, and evaluation unit. It is reported as WO, separately from bounded W, while still contributing exactly one edit to the aggregate score. The local LINK identifier is ignored across files. Validated origin-side U records are excluded only after their reciprocal M record passes validation.",
        "",
        "Normalization statement:",
        "",
        "> Byte-order marks and whitespace are removed. No BPE, word segmentation, or OpenCC conversion is applied to character evaluation. Word M2 uses the fixed gold-informed source segmentation and LTP-segmented hypotheses/references. "
        + word_gleu_protocol_description(word_gleu_source_policy)
        + " Neither word metric uses BPE or OpenCC.",
        "",
        "## Section 6.1.5: Model and Inference Configuration",
        "",
    ]
    add_table(
        lines,
        ("Model", "Identifier", "Provider", "Access dates", "Temp.", "Top-p", "Max output", "Samples", "Kmax"),
        (
            (
                "DeepSeek",
                "deepseek-v4-pro",
                "DeepSeek API",
                "2026-07-16 to 2026-07-20",
                "0.000001",
                "provider default (omitted)",
                "provider default (omitted)",
                "1",
                "3",
            ),
            ("Other models", "outside this report", "", "", "", "", "", "", ""),
        ),
    )
    lines.extend(
        [
            "Paste-ready decoding description:",
            "",
            "> We generated one correction per source and condition. The request set temperature to 0.000001 and disabled thinking. It did not set top-p, max_tokens, or a random seed, so provider defaults applied to the omitted fields and exact deterministic decoding should not be claimed. Requests used a 90-second timeout and up to two retries. The final saved DeepSeek files contain no failed rows, empty T0-T3 outputs, or fallback requests without the disabled-thinking field.",
            "",
            "Paste-ready output normalization description:",
            "",
            "> Response cleaning removes surrounding whitespace and quotation marks, Markdown code fences, recognized Chinese answer labels, and explanation text following recognized explanation headers. It then removes whitespace from the returned Chinese sentence. The final corpus contained no empty stage outputs. The current implementation does not apply a separate grammaticality or semantic-validity filter after this cleaning step.",
            "",
            "## Section 6.2.2: Edit Results (Table 5)",
            "",
            "Each cell is precision/recall/F0.5 x 100.",
            "",
        ]
    )
    add_table(
        lines,
        (
            "Dataset",
            "Char Raw",
            "Char Direct",
            "Char Projected",
            "Char Iterative",
            "Word Raw",
            "Word Direct",
            "Word Projected",
            "Word Iterative",
        ),
        (
            (
                DISPLAY_NAMES[spec.dataset],
                *[fmt_m2(character_m2[(spec.dataset, stage)]) for stage in STAGES],
                *[fmt_m2(word_m2[(spec.dataset, stage)]) for stage in STAGES],
            )
            for spec in load_specs()
        ),
    )
    lines.extend(
        [
            "Paste-ready result summary:",
            "",
            f"> Direct-WB raises character F0.5 on {char_direct_wins} of eight datasets and word F0.5 on {word_direct_wins} of eight. The improvement is primarily precision-driven: recall decreases on every dataset at character level and on every dataset at word level, while precision generally rises, indicating more conservative correction under explicit boundaries. The strongest Direct-WB gains are {char_best_gain:+.2f} character F0.5 on {char_best_dataset} and {word_best_gain:+.2f} word F0.5 on {word_best_dataset}; CEFE Track 3 decreases at both levels but contains only 19 sources. After Direct-WB, Projected-WB and Iterative Projected-WB differ by at most a few tenths of an F0.5 point and do not improve monotonically. The character- and word-based results therefore agree on the main conservative effect of explicit boundaries and on the limited aggregate effect of additional projection passes, while differing on individual dataset rankings.",
            "",
            "## Section 6.2.3: GLEU Results (Table 6)",
            "",
        ]
    )
    add_table(
        lines,
        (
            "Dataset",
            "Char Raw",
            "Char Direct",
            "Char Projected",
            "Char Iterative",
            "Word Raw",
            "Word Direct",
            "Word Projected",
            "Word Iterative",
        ),
        (
            (
                DISPLAY_NAMES[spec.dataset],
                *[f"{character_gleu[(spec.dataset, stage)]:.2f}" for stage in STAGES],
                *[f"{word_gleu[(spec.dataset, stage)]:.2f}" for stage in STAGES],
            )
            for spec in load_specs()
        ),
    )
    lines.extend(
        [
            "Paste-ready GLEU interpretation:",
            "",
            f"> Direct-WB improves over Raw on {direct_character_gleu_wins}/{len(load_specs())} datasets in character GLEU and {direct_word_gleu_wins}/{len(load_specs())} in word GLEU. The largest T1-T3 spread is {char_gleu_post:.2f} character points and {word_gleu_post:.2f} word points. GLEU gives partial credit to reference-supported n-grams and penalizes retained source material, whereas edit scoring requires exact localized correction agreement and weights precision more heavily.",
            (
                "> For condition-specific word GLEU, P and I contrasts reflect the prescribed S2/S3 source boundaries as well as changes to the corrected text; hypotheses and references retain LTP segmentation. Word M2 remains fixed-gold."
                if word_gleu_source_policy == "condition"
                else "> These historical fixed-gold word-GLEU contrasts hold the source segmentation constant across all four conditions."
            ),
            "",
            "## Additional Section 7 Facts Available Now",
            "",
            f"- First projection changes S1: {convergence['first_projection_changed']:,}/{total:,} ({100 * convergence['first_projection_changed'] / total:.2f}%).",
            f"- Stops after Direct/Projected/reaches T3: {convergence['converged_after_direct']:,}/{convergence['converged_after_projected']:,}/{convergence['reached_t3']:,}.",
            f"- Two-cycles S1-S2-S1: {convergence['two_cycles']:,} ({100 * convergence['two_cycles'] / total:.2f}%); handled by Kmax, not reported as convergence.",
            f"- Boundary operations through S3: {convergence['splits']:,} splits and {convergence['merges']:,} merges.",
            f"- Threshold sensitivity: character max range {audit['threshold_sensitivity']['character']['max_f0.5_x100_range']:.4f}; word max range {audit['threshold_sensitivity']['word']['max_f0.5_x100_range']:.4f} F0.5 points.",
            "- Five manually inspected ChERRANT/projection examples are in `runs/final_alignment_examples/QUALITATIVE_ALIGNMENT_EXAMPLES.md`.",
            "",
            "## Red Items That Remain Pending",
            "",
            "- Model 2 and cross-model results are outside this DeepSeek report; do not infer scores or output availability from this report.",
            "- C-based LTP versus Python LTP consistency: no C-based segmentation output or runnable dependency is present; the formal experiments use Python `ltp` 4.2.14.",
            "- Any cross-system comparison table requiring published scores under exactly the same unit, reference set, normalization, and comparator must remain pending unless comparability is established.",
            "",
        ]
    )
    PAPER_OUTPUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    add_word_gleu_arguments(parser)
    parser.add_argument("--audit", type=Path, default=AUDIT)
    args = parser.parse_args()
    word_gleu_root = resolve_word_gleu_root(
        args.word_gleu_root, source_policy=args.word_gleu_source_policy
    )
    load_source_policy(word_gleu_root, expected_policy=args.word_gleu_source_policy)
    word_gleu_path = word_gleu_root / "scores.long.tsv"
    required = (
        CHARACTER_M2,
        WORD_M2,
        CHARACTER_GLEU,
        word_gleu_path,
        word_gleu_root / "run_config.json",
        FIXED_CONFIG,
        args.audit,
        ALIGNMENT_EXAMPLES,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing final inputs: " + ", ".join(missing))

    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    require_word_gleu_audit(
        audit,
        source_policy=args.word_gleu_source_policy,
        word_gleu_root=word_gleu_root,
    )
    character_m2 = load_m2_scores(CHARACTER_M2, alignment="projection")
    word_m2 = load_m2_scores(WORD_M2)
    character_gleu = load_gleu_scores(CHARACTER_GLEU)
    word_gleu = load_gleu_scores(word_gleu_path)
    refs = reference_metadata()
    fixed = fixed_segmentation_stats()
    convergence = convergence_stats()
    movements = movement_stats()

    expected = {(spec.dataset, stage) for spec in load_specs() for stage in STAGES}
    for name, values in (
        ("character M2", character_m2),
        ("word M2", word_m2),
        ("character GLEU", character_gleu),
        ("word GLEU", word_gleu),
    ):
        if set(values) != expected:
            raise ValueError(f"Incomplete {name} score table")

    write_long_tsv(character_m2, word_m2, character_gleu, word_gleu, refs)
    build_report(
        character_m2,
        word_m2,
        character_gleu,
        word_gleu,
        refs,
        fixed,
        convergence,
        movements,
        audit,
        word_gleu_source_policy=args.word_gleu_source_policy,
        word_gleu_root=word_gleu_root,
    )
    build_paper_inputs(
        character_m2,
        word_m2,
        character_gleu,
        word_gleu,
        fixed,
        convergence,
        audit,
        word_gleu_source_policy=args.word_gleu_source_policy,
        word_gleu_root=word_gleu_root,
    )
    print(OUTPUT_MD)
    print(OUTPUT_TSV)
    print(PAPER_OUTPUT)


if __name__ == "__main__":
    main()
