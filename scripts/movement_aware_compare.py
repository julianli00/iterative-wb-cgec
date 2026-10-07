#!/usr/bin/env python3
"""M2 correction scorer with strict linked-movement matching.

Multi-reference evaluation selects the best reference independently for each
sentence before aggregating TP/FP/FN.  ``corpus`` selection is retained only
to audit results produced by the historical ERRANT greedy procedure.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from movement_m2 import (
        NO_CORRECTION,
        parse_link_comment,
        validate_linked_movements,
    )
except ModuleNotFoundError:
    from scripts.movement_m2 import (
        NO_CORRECTION,
        parse_link_comment,
        validate_linked_movements,
    )


@dataclass(frozen=True)
class ParsedEdit:
    source_start: int
    source_end: int
    edit_type: str
    correction: str | tuple[str, ...]
    comment: str
    annotator_id: int


@dataclass(frozen=True)
class M2Block:
    source_units: tuple[str, ...]
    edits: tuple[ParsedEdit, ...]
    unit: str


def split_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig").replace("\ufeff", "").strip()
    return [] if not text else text.split("\n\n")


def parse_block(block: str, *, unit: str) -> M2Block:
    lines = [line for line in block.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("S "):
        raise ValueError("M2 block does not start with an S line")
    source_tokens = tuple(lines[0][2:].split())
    source_units = tuple("".join(source_tokens)) if unit == "character" else source_tokens
    edits: list[ParsedEdit] = []
    for line in lines[1:]:
        if not line.startswith("A "):
            continue
        fields = line[2:].split("|||")
        if len(fields) != 6:
            raise ValueError(f"M2 annotation must contain six fields: {line}")
        span = fields[0].split()
        if len(span) != 2:
            raise ValueError(f"Invalid M2 span: {line}")
        start, end = (int(value) for value in span)
        edit_type = fields[1]
        correction_text = fields[2]
        correction: str | tuple[str, ...]
        if correction_text == NO_CORRECTION:
            correction = NO_CORRECTION
        elif unit == "character":
            correction = "".join(correction_text.split())
        else:
            correction = tuple(correction_text.split())
        edits.append(
            ParsedEdit(
                source_start=start,
                source_end=end,
                edit_type=edit_type,
                correction=correction,
                comment=fields[4],
                annotator_id=int(fields[5]),
            )
        )
    return M2Block(source_units=source_units, edits=tuple(edits), unit=unit)


def parse_file(path: Path, *, unit: str) -> list[M2Block]:
    return [parse_block(block, unit=unit) for block in split_blocks(path)]


def _normal_correction(edit: ParsedEdit, unit: str) -> str:
    if edit.correction == NO_CORRECTION:
        return NO_CORRECTION
    if isinstance(edit.correction, str):
        return edit.correction
    return "".join(edit.correction) if unit == "character" else "\u241f".join(edit.correction)


def scored_edits(
    block: M2Block, *, unit: str
) -> dict[int, dict[tuple[Any, ...], list[str]]]:
    """Convert physical M2 edits into logical correction edits by annotator."""

    grouped: dict[int, list[ParsedEdit]] = {}
    for edit in block.edits:
        grouped.setdefault(edit.annotator_id, []).append(edit)
    if not grouped:
        grouped[0] = []

    result: dict[int, dict[tuple[Any, ...], list[str]]] = {}
    for annotator_id, edits in grouped.items():
        movements = validate_linked_movements(block.source_units, edits)
        origins = {id(movement.origin_edit) for movement in movements.values()}
        destinations = {
            id(movement.destination_edit): movement
            for movement in movements.values()
        }
        logical: dict[tuple[Any, ...], list[str]] = {}
        if not edits:
            logical[(-1, -1, NO_CORRECTION)] = ["noop"]
        for edit in edits:
            if edit.edit_type == "noop":
                logical.setdefault((-1, -1, NO_CORRECTION), []).append("noop")
                continue
            if id(edit) in origins:
                continue
            movement = destinations.get(id(edit))
            if movement is not None:
                key = (
                    "W-LD",
                    movement.origin_start,
                    movement.origin_end,
                    movement.destination,
                    movement.material,
                    unit,
                )
                logical.setdefault(key, []).append("W-LD")
                continue
            metadata = parse_link_comment(edit.comment)
            if metadata is not None:
                raise ValueError("Validated linked edit was not assigned to a movement")
            key = (
                edit.source_start,
                edit.source_end,
                _normal_correction(edit, unit),
            )
            logical.setdefault(key, []).append(edit.edit_type)
        result[annotator_id] = logical
    return result


def compare_edits(
    hypothesis: dict[tuple[Any, ...], list[str]],
    reference: dict[tuple[Any, ...], list[str]],
) -> tuple[int, int, int, dict[str, list[int]]]:
    tp = fp = fn = 0
    categories: dict[str, list[int]] = {}

    def add(category: str, index: int) -> None:
        # Keep short-span W and linked long-distance word order separate in
        # operation-level reports. The linked pair still contributes exactly
        # one edit to the aggregate score.
        report_category = "WO" if category == "W-LD" else category
        categories.setdefault(report_category, [0, 0, 0])[index] += 1

    for key, hypothesis_categories in hypothesis.items():
        if hypothesis_categories[0] == "noop":
            continue
        if key in reference:
            for category in reference[key]:
                tp += 1
                add(category, 0)
        else:
            for category in hypothesis_categories:
                fp += 1
                add(category, 1)
    for key, reference_categories in reference.items():
        if reference_categories[0] == "noop":
            continue
        if key not in hypothesis:
            for category in reference_categories:
                fn += 1
                add(category, 2)
    return tp, fp, fn, categories


def f_score(tp: int, fp: int, fn: int, beta: float) -> tuple[float, float, float]:
    precision, recall, score = _f_score_unrounded(tp, fp, fn, beta)
    return round(precision, 4), round(recall, 4), round(score, 4)


def _f_score_unrounded(
    tp: int, fp: int, fn: int, beta: float
) -> tuple[float, float, float]:
    precision = float(tp) / (tp + fp) if fp else 1.0
    recall = float(tp) / (tp + fn) if fn else 1.0
    score = (
        (1 + beta**2) * precision * recall / (beta**2 * precision + recall)
        if precision + recall
        else 0.0
    )
    return precision, recall, score


def _merge_categories(
    aggregate: dict[str, list[int]], current: dict[str, list[int]]
) -> None:
    for category, counts in current.items():
        destination = aggregate.setdefault(category, [0, 0, 0])
        for index, value in enumerate(counts):
            destination[index] += value


def evaluate(
    hypothesis_blocks: Sequence[M2Block],
    reference_blocks: Sequence[M2Block],
    *,
    beta: float,
    selection_mode: str = "sentence",
) -> tuple[Counter[str], dict[str, list[int]], list[dict[str, Any]]]:
    if selection_mode not in {"sentence", "corpus"}:
        raise ValueError(f"Unsupported selection mode: {selection_mode}")
    if len(hypothesis_blocks) != len(reference_blocks):
        raise ValueError(
            "Hypothesis/reference block count mismatch: "
            f"{len(hypothesis_blocks)} != {len(reference_blocks)}"
        )
    best = Counter({"tp": 0, "fp": 0, "fn": 0})
    category_totals: dict[str, list[int]] = {}
    selections: list[dict[str, Any]] = []
    for sentence_id, (hypothesis_block, reference_block) in enumerate(
        zip(hypothesis_blocks, reference_blocks)
    ):
        if hypothesis_block.source_units != reference_block.source_units:
            raise ValueError(f"Source mismatch in M2 block {sentence_id + 1}")
        if hypothesis_block.unit != reference_block.unit:
            raise ValueError(f"Evaluation-unit mismatch in M2 block {sentence_id + 1}")
        hypotheses = scored_edits(hypothesis_block, unit=hypothesis_block.unit)
        references = scored_edits(reference_block, unit=reference_block.unit)
        selected: tuple[int, int, int, float, int, int, dict[str, list[int]]] | None = None
        for hypothesis_id, hypothesis in hypotheses.items():
            for reference_id, reference in references.items():
                tp, fp, fn, categories = compare_edits(hypothesis, reference)
                if selection_mode == "sentence":
                    _p, _r, selection_score = _f_score_unrounded(
                        tp, fp, fn, beta
                    )
                else:
                    # Reproduce the historical ERRANT procedure exactly,
                    # including its four-decimal score used for greedy choice.
                    _p, _r, selection_score = f_score(
                        tp + best["tp"],
                        fp + best["fp"],
                        fn + best["fn"],
                        beta,
                    )
                candidate = (
                    tp,
                    fp,
                    fn,
                    selection_score,
                    hypothesis_id,
                    reference_id,
                    categories,
                )
                if selected is None or _is_better(candidate, selected):
                    selected = candidate
        if selected is None:
            raise ValueError(f"No hypothesis/reference combination in block {sentence_id + 1}")
        tp, fp, fn, _global_f, hypothesis_id, reference_id, categories = selected
        best.update({"tp": tp, "fp": fp, "fn": fn})
        _merge_categories(category_totals, categories)
        selections.append(
            {
                "sentence": sentence_id,
                "hypothesis": hypothesis_id,
                "reference": reference_id,
                "TP": tp,
                "FP": fp,
                "FN": fn,
                "selection_score": selected[3],
            }
        )
    return best, category_totals, selections


def _is_better(
    candidate: tuple[int, int, int, float, int, int, dict[str, list[int]]],
    incumbent: tuple[int, int, int, float, int, int, dict[str, list[int]]],
) -> bool:
    tp, fp, fn, score, _hypothesis, _reference, _categories = candidate
    best_tp, best_fp, best_fn, best_score, *_rest = incumbent
    return (
        score > best_score
        or (score == best_score and tp > best_tp)
        or (score == best_score and tp == best_tp and fp < best_fp)
        or (
            score == best_score
            and tp == best_tp
            and fp == best_fp
            and fn < best_fn
        )
    )


def format_results(
    counts: Counter[str], categories: dict[str, list[int]], beta: float
) -> str:
    title = " Span-Based Correction "
    lines = ["", f"{title:=^66}"]
    lines.append("Category      TP       FP       FN       P        R        F" + str(beta))
    for category, values in sorted(categories.items()):
        precision, recall, score = f_score(*values, beta)
        lines.append(
            f"{category:<14}{values[0]:<9}{values[1]:<9}{values[2]:<9}"
            f"{precision:<9}{recall:<9}{score}"
        )
    precision, recall, score = f_score(
        counts["tp"], counts["fp"], counts["fn"], beta
    )
    lines.extend(
        [
            "",
            f"{title:=^46}",
            "\t".join(["TP", "FP", "FN", "Prec", "Rec", "F" + str(beta)]),
            "\t".join(
                map(
                    str,
                    [
                        counts["tp"],
                        counts["fp"],
                        counts["fn"],
                        precision,
                        recall,
                        score,
                    ],
                )
            ),
            f"{'':=^46}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-hyp", "--hypothesis", type=Path, required=True)
    parser.add_argument("-ref", "--reference", type=Path, required=True)
    parser.add_argument("-b", "--beta", type=float, default=0.5)
    parser.add_argument("--unit", choices=("character", "word"), required=True)
    parser.add_argument(
        "--selection-mode",
        choices=("sentence", "corpus"),
        default="sentence",
        help=(
            "Select each reference by sentence-local F-score (paper protocol) "
            "or reproduce the historical order-dependent corpus-greedy mode"
        ),
    )
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    hypothesis_blocks = parse_file(args.hypothesis, unit=args.unit)
    reference_blocks = parse_file(args.reference, unit=args.unit)
    selection = slice(args.start, args.end)
    hypothesis_blocks = hypothesis_blocks[selection]
    reference_blocks = reference_blocks[selection]
    counts, categories, selections = evaluate(
        hypothesis_blocks,
        reference_blocks,
        beta=args.beta,
        selection_mode=args.selection_mode,
    )
    output = format_results(counts, categories, args.beta)
    print(output)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        precision, recall, score = f_score(
            counts["tp"], counts["fp"], counts["fn"], args.beta
        )
        args.json_output.write_text(
            json.dumps(
                {
                    "unit": args.unit,
                    "beta": args.beta,
                    "selection_mode": args.selection_mode,
                    "TP": counts["tp"],
                    "FP": counts["fp"],
                    "FN": counts["fn"],
                    "precision": precision,
                    "recall": recall,
                    "F_beta": score,
                    "categories": categories,
                    "selections": selections,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
