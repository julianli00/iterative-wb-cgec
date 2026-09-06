#!/usr/bin/env python3
"""Build final qualitative examples for projection-based word-order edits."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import csv
from pathlib import Path
from typing import Any, Iterable, Sequence

from movement_aware_compare import parse_block
from movement_m2 import validate_linked_movements
from projection_word_m2 import targets_from_word_m2_block
from standardize_m2_evaluation import ROOT, ROUNDS, load_specs


WORD_ROOT = ROOT / "runs/projection_word_m2_eval_final"
CHAR_ROOT = ROOT / "runs/projection_character_m2_eval_final"
CHERRANT_ROOT = ROOT / "runs/standardized_m2_eval"
DEFAULT_OUTPUT = ROOT / "runs/final_alignment_examples"

CURATED_CASES = (
    (
        "flacgec",
        "test",
        "T0",
        300,
        "The two-character adverb 步步 moves across a long unchanged interval. "
        "Projection isolates exactly the moved word at both evaluation levels, "
        "whereas ChERRANT places one W over the complete intervening character span.",
    ),
    (
        "nasgec_exam",
        "test",
        "T0",
        1991,
        "The quantifier phrase 一位 moves leftward. Projection records the two-character/"
        "two-token phrase and its endpoints; ChERRANT's W includes the unchanged relative clause.",
    ),
    (
        "nacgec",
        "test",
        "T3",
        3133,
        "The negator 没有 moves before 把. Projection links only the moved material, "
        "while ChERRANT's conventional W spans the entire intervening object phrase.",
    ),
    (
        "nasgec_exam",
        "test",
        "T1",
        14,
        "This is a multi-block reordering rather than an unambiguous one-block move. "
        "The projection pipeline therefore uses its documented encompassing-W fallback; "
        "ChERRANT fragments the same change into one insertion and two deletions.",
    ),
    (
        "fcgec",
        "validation",
        "T0",
        270,
        "The first and last coordinated predicates exchange positions. Projection uses "
        "one exact-permutation W fallback, while ChERRANT represents four character substitutions.",
    ),
)


def read_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig").replace("\ufeff", "").strip()
    return [] if not text else text.split("\n\n")


def edit_lines(block: str) -> list[str]:
    return [line for line in block.splitlines() if line.startswith("A ")]


def edit_categories(block: str) -> list[str]:
    return [line.split("|||", 2)[1] for line in edit_lines(block)]


def edit_categories_from_text(text: str) -> list[str]:
    if not text:
        return []
    return [part.split("|||", 2)[1] for part in text.split(" ; ")]


def cherrant_surface_pair(block: str) -> tuple[str, str]:
    """Return the single normalized source/target pair stored by ChERRANT."""

    lines = [line for line in block.splitlines() if line.strip()]
    source_lines = [line for line in lines if line.startswith("S ")]
    target_lines = [line for line in lines if line.startswith("T")]
    if len(source_lines) != 1 or not target_lines:
        raise ValueError("Expected one ChERRANT S line and at least one T line")
    source = "".join(source_lines[0][2:].split())
    targets = set()
    for target_line in target_lines:
        target_fields = target_line.split(maxsplit=1)
        if len(target_fields) != 2:
            raise ValueError("Malformed ChERRANT T line")
        targets.add("".join(target_fields[1].split()))
    if len(targets) != 1:
        raise ValueError("ChERRANT alignment alternatives disagree on target text")
    return source, targets.pop()


def _max_permutation_displacement(
    source_tokens: Sequence[str], target_tokens: Sequence[str]
) -> int:
    target_positions: dict[str, deque[int]] = defaultdict(deque)
    for index, token in enumerate(target_tokens):
        target_positions[token].append(index)
    return max(
        (
            abs(source_index - target_positions[token].popleft())
            for source_index, token in enumerate(source_tokens)
        ),
        default=0,
    )


def word_order_records(block_text: str) -> list[dict[str, Any]]:
    block = parse_block(block_text, unit="word")
    records: list[dict[str, Any]] = []
    movements = validate_linked_movements(block.source_units, block.edits)
    for movement in movements.values():
        lines = [
            line
            for line in edit_lines(block_text)
            if f"LINK={movement.link_id};" in line
        ]
        records.append(
            {
                "representation": "linked U-M",
                "origin": f"{movement.origin_start}:{movement.origin_end}",
                "destination": movement.destination,
                "moved_material": " ".join(movement.material),
                "envelope_tokens": movement.envelope_length,
                "max_token_movement": min(
                    abs(movement.destination - movement.origin_start),
                    abs(movement.destination - movement.origin_end),
                ),
                "annotation": " ; ".join(lines),
            }
        )

    source_tokens = block.source_units
    for line in edit_lines(block_text):
        fields = line[2:].split("|||")
        if fields[1] != "W":
            continue
        start, end = (int(value) for value in fields[0].split())
        target_tokens = tuple(fields[2].split())
        source_span = source_tokens[start:end]
        if Counter(source_span) != Counter(target_tokens):
            raise ValueError(f"W is not an exact word permutation: {line}")
        records.append(
            {
                "representation": "encompassing W",
                "origin": f"{start}:{end}",
                "destination": "",
                "moved_material": "",
                "envelope_tokens": end - start,
                "max_token_movement": _max_permutation_displacement(
                    source_span, target_tokens
                ),
                "annotation": line,
            }
        )
    return records


def collect_candidates(minimum_movement: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in load_specs():
        word_dir = WORD_ROOT / spec.dataset / spec.split / "word"
        character_dir = CHAR_ROOT / spec.dataset / spec.split / "char"
        cherrant_dir = CHERRANT_ROOT / spec.dataset / spec.split / "char"
        for stage in ROUNDS:
            word_blocks = read_blocks(
                word_dir / f"hypothesis.{stage}.projection.word.m2"
            )
            character_blocks = read_blocks(
                character_dir / f"hypothesis.{stage}.projection.char.m2"
            )
            cherrant_blocks = read_blocks(cherrant_dir / f"hypothesis.{stage}.char.m2")
            if not (
                len(word_blocks)
                == len(character_blocks)
                == len(cherrant_blocks)
                == spec.rows
            ):
                raise ValueError(f"{spec.dataset}/{stage}: block-count mismatch")
            for row_id, (word, character, cherrant) in enumerate(
                zip(word_blocks, character_blocks, cherrant_blocks), start=1
            ):
                records = word_order_records(word)
                if not records:
                    continue
                source_tokens, targets = targets_from_word_m2_block(word)
                source = "".join(source_tokens)
                target = "".join(targets[0])
                cherrant_source, cherrant_target = cherrant_surface_pair(cherrant)
                if (source, target) != (cherrant_source, cherrant_target):
                    continue
                for record in records:
                    if int(record["max_token_movement"]) < minimum_movement:
                        continue
                    rows.append(
                        {
                            "dataset": spec.dataset,
                            "split": spec.split,
                            "stage": stage,
                            "row_id": row_id,
                            **record,
                            "source": source,
                            "target": target,
                            "source_word_representation": " ".join(source_tokens),
                            "projection_character_categories": ",".join(
                                edit_categories(character)
                            ),
                            "projection_character_edits": " ; ".join(
                                edit_lines(character)
                            ),
                            "cherrant_character_categories": ",".join(
                                edit_categories(cherrant)
                            ),
                            "cherrant_character_edits": " ; ".join(
                                edit_lines(cherrant)
                            ),
                        }
                    )
    rows.sort(
        key=lambda row: (
            -int(row["max_token_movement"]),
            -int(row["envelope_tokens"]),
            row["dataset"],
            row["stage"],
            int(row["row_id"]),
        )
    )
    return rows


def write_table(
    lines: list[str], headers: Sequence[str], rows: Iterable[Sequence[str]]
) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    lines.append("")


def write_outputs(output: Path, rows: Sequence[dict[str, Any]]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with (output / "candidates.tsv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    by_case: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for row in rows:
        key = (row["dataset"], row["split"], row["stage"], int(row["row_id"]))
        by_case.setdefault(key, row)

    selected: list[tuple[dict[str, Any], str]] = []
    for dataset, split, stage, row_id, explanation in CURATED_CASES:
        key = (dataset, split, stage, row_id)
        if key not in by_case:
            raise ValueError(f"Curated alignment case is missing: {key}")
        selected.append((by_case[key], explanation))

    lines = [
        "# Qualitative Alignment Examples",
        "",
        "These five real saved model outputs were manually selected and inspected for representational clarity. They demonstrate how the final projection M2 files encode order changes; they are not claims that every generated correction is linguistically optimal.",
        "",
        "## Summary",
        "",
    ]
    write_table(
        lines,
        ("Dataset", "Stage", "Row", "Projection word form", "ChERRANT character form"),
        (
            (
                row["dataset"],
                row["stage"],
                str(row["row_id"]),
                row["representation"],
                ", ".join(edit_categories_from_text(row["cherrant_character_edits"])),
            )
            for row, _explanation in selected
        ),
    )
    for index, (row, explanation) in enumerate(selected, start=1):
        lines.extend(
            [
                f"## Example {index}: {row['dataset']} {row['stage']} row {row['row_id']}",
                "",
                f"**Source:** {row['source']}",
                "",
                f"**System output:** {row['target']}",
                "",
                f"**Assessment:** {explanation}",
                "",
                "**Projection word M2**",
                "",
                "```text",
                row["annotation"].replace(" ; ", "\n"),
                "```",
                "",
                "**Projection character M2**",
                "",
                "```text",
                row["projection_character_edits"].replace(" ; ", "\n"),
                "```",
                "",
                "**ChERRANT character M2**",
                "",
                "```text",
                row["cherrant_character_edits"].replace(" ; ", "\n"),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation Boundary",
            "",
            "The first three examples support the narrow claim that linked projection can isolate moved material and retain both origin and destination when a conventional contiguous W would absorb a long unchanged interval. The final two examples show the documented fallback for multi-block permutations. These examples do not establish aggregate alignment accuracy and should be presented as qualitative evidence only.",
            "",
        ]
    )
    (output / "QUALITATIVE_ALIGNMENT_EXAMPLES.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--minimum-movement", type=int, default=4)
    args = parser.parse_args()
    rows = collect_candidates(args.minimum_movement)
    if not rows:
        raise RuntimeError("No long-distance word-order candidates found")
    write_outputs(args.output, rows)
    print(f"Candidates: {len(rows)}")
    print(args.output / "QUALITATIVE_ALIGNMENT_EXAMPLES.md")


if __name__ == "__main__":
    main()
