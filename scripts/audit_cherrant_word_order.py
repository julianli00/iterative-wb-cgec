#!/usr/bin/env python3
"""Audit ChERRANT labels and long-distance word-order representations."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Sequence

from standardize_m2_evaluation import ROOT, ROUNDS, load_specs


CHERRANT_ROOT = ROOT / "runs/standardized_m2_eval"
LONG_DISTANCE = ROOT / "runs/long_distance_word_order_audit/candidates.tsv"
DEFAULT_OUTPUT = ROOT / "runs/cherrant_word_order_audit"
MILESTONE_EXAMPLE_KEYS = (
    ("nasgec_exam", "T1", "14"),
    ("nacgec", "T0", "3619"),
    ("nacgec", "T0", "5064"),
    ("nasgec_exam", "T0", "1964"),
    ("nacgec", "T0", "5214"),
    ("fcgec", "T0", "270"),
    ("fcgec", "T0", "1817"),
    ("nacgec", "T0", "1193"),
    ("flacgec", "T0", "1039"),
    ("mucgec", "T0", "3398"),
)


def read_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig").strip()
    return [] if not text else text.split("\n\n")


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def edit_labels(block: str) -> list[str]:
    labels = []
    for line in block.splitlines():
        if not line.startswith("A "):
            continue
        fields = line[2:].split("|||")
        if len(fields) != 6:
            raise ValueError(f"Malformed M2 edit: {line}")
        labels.append(fields[1])
    return labels


def coarse_label(label: str) -> str:
    return label.split(":", 1)[0]


def scan_hypothesis_labels() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in load_specs():
        directory = CHERRANT_ROOT / spec.dataset / spec.split / "char"
        for stage in ROUNDS:
            path = directory / f"hypothesis.{stage}.char.m2"
            blocks = read_blocks(path)
            if len(blocks) != spec.rows:
                raise ValueError(
                    f"{spec.dataset}/{stage}: {len(blocks)} blocks != {spec.rows}"
                )
            labels = [label for block in blocks for label in edit_labels(block)]
            coarse = Counter(coarse_label(label) for label in labels)
            fine = Counter(labels)
            rows.append(
                {
                    "dataset": spec.dataset,
                    "split": spec.split,
                    "stage": stage,
                    "sentences": spec.rows,
                    "edits": sum(coarse[label] for label in ("M", "R", "S", "W")),
                    "M": coarse["M"],
                    "R": coarse["R"],
                    "S": coarse["S"],
                    "W": coarse["W"],
                    "noop": coarse["noop"],
                    "NA": coarse["NA"],
                    "other_labels": ",".join(
                        f"{label}:{count}"
                        for label, count in sorted(fine.items())
                        if coarse_label(label) not in {"M", "R", "S", "W", "noop", "NA"}
                    ),
                    "sentences_with_W": sum(
                        "W" in {coarse_label(label) for label in edit_labels(block)}
                        for block in blocks
                    ),
                }
            )
    return rows


def write_tsv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def add_table(lines: list[str], headers: Sequence[str], rows: Iterable[Sequence[str]]) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append(
        "| "
        + " | ".join("---" if index == 0 else "---:" for index in range(len(headers)))
        + " |"
    )
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")


def unique_candidates(rows: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    result = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (row["dataset"], row["source"], row["target"])
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def report_examples(rows: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    """Select clean, high-movement examples with complete-looking W spans."""

    preferred = (
        ("nasgec_exam", "T1", "14"),
        ("nacgec", "T0", "3619"),
        ("nacgec", "T0", "5064"),
    )
    indexed = {
        (row["dataset"], row["stage"], row["row_id"]): row
        for row in rows
    }
    selected = [indexed[key] for key in preferred if key in indexed]
    if len(selected) == len(preferred):
        return selected
    return unique_candidates(rows)[:3]


def milestone_examples(rows: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    indexed = {
        (row["dataset"], row["stage"], row["row_id"]): row
        for row in rows
    }
    missing = [key for key in MILESTONE_EXAMPLE_KEYS if key not in indexed]
    if missing:
        raise KeyError(f"Missing milestone examples: {missing}")
    return [indexed[key] for key in MILESTONE_EXAMPLE_KEYS]


def parse_edit_line(line: str) -> tuple[int, int, str, str]:
    fields = line[2:].split("|||")
    if not line.startswith("A ") or len(fields) != 6:
        raise ValueError(f"Malformed M2 edit line: {line}")
    start, end = (int(value) for value in fields[0].split())
    return start, end, fields[1], fields[2].replace(" ", "")


def readable_edits(
    source: str,
    serialized: str,
    *,
    projection_labels: bool,
) -> list[str]:
    descriptions = []
    for line in serialized.split(" ; "):
        if not line:
            continue
        start, end, label, correction = parse_edit_line(line)
        source_span = source[start:end]
        if label == "M":
            action = f'insert "{correction}" at boundary {start}'
        elif label == "U" or (label == "R" and not projection_labels and correction == "-NONE-"):
            action = f'delete "{source_span}" at {start}:{end}'
        elif label == "W":
            action = (
                f'reorder "{source_span}" as "{correction}" '
                f'at {start}:{end}'
            )
        else:
            action = (
                f'replace "{source_span}" with "{correction}" '
                f'at {start}:{end}'
            )
        descriptions.append(f"`{label}`: {action}")
    return descriptions


def build_milestone_report(
    label_rows: Sequence[dict[str, Any]],
    candidates: Sequence[dict[str, str]],
) -> str:
    totals = Counter()
    for row in label_rows:
        totals.update(
            {
                key: int(row[key])
                for key in ("sentences", "edits", "M", "R", "S", "W", "sentences_with_W")
            }
        )

    lines = [
        "# Milestone Report",
        "",
        "This report documents the current milestone on ChERRANT label analysis and projection-based representation of long-distance word-order changes.",
        "",
        "## 1. ChERRANT Label Inventory and Word-Order Detection",
        "",
        "### 1.1 Character-level labels",
        "",
        "At character granularity, ChERRANT writes four coarse labels to M2:",
        "",
        "| Label | ChERRANT meaning | Underlying alignment operation |",
        "| --- | --- | --- |",
        "| `M` | Missing material | Insertion (`I`) |",
        "| `R` | Redundant material | Deletion (`D`) |",
        "| `S` | Substitution | Substitution (`S`) |",
        "| `W` | Word/character-order error | Transposition (`T`) |",
        "",
        "Character mode does not attach POS or spelling subtypes. The label conventions must be kept distinct:",
        "",
        "| System | Coarse labels | Meaning |",
        "| --- | --- | --- |",
        "| ChERRANT character M2 | `M/R/S/W` | missing, redundant, substitution, word order |",
        "| Standard ERRANT | `M/R/U` prefixes | missing, replacement, unnecessary |",
        "| Projection M2 used in this work | `M/R/U/W` | missing, replacement, unnecessary, word order |",
        "",
        "In particular, ChERRANT's `R` means *redundant/deletion*, while standard ERRANT and the projection M2 use `R` for *replacement* and `U` for *unnecessary/deletion*.",
        "",
        "### 1.2 Word-level refinements",
        "",
        "At word granularity, ChERRANT refines M/R/S as follows:",
        "",
        "- A single-token insertion or deletion becomes `M:<POS>` or `R:<POS>`.",
        "- Multi-token insertions/deletions become `M:OTHER` or `R:OTHER`.",
        "- A substitution may become `S:SPELL`, `S:<POS>`, or `S:OTHER`.",
        "- The coarse POS inventory includes NOUN, VERB, ADJ, CONJ, PRON, ADV, AUX, NUM, PREP, QUAN, PUNCT, and OTHER; `MC` is also available for missing-component markers.",
        "- A transposition remains the coarse label `W`; ChERRANT does not add a POS subtype to W.",
        "",
        "The present comparison uses character-level ChERRANT output, so the observed labels are M/R/S/W without these word-level subtypes.",
        "",
        "### 1.3 How ChERRANT decides W",
        "",
        "ChERRANT has two routes to W:",
        "",
        "1. **Direct dynamic-programming transposition.** Starting with a span of two tokens, it expands backward and compares the sorted source and target spans. If the sorted spans are equal, the alignment receives an internal `T<n>` operation; the classifier converts every T operation to the M2 label `W`. ChERRANT does not emit `T` as a final M2 label.",
        "2. **Local merger heuristics.** After alignment, ChERRANT can merge `S-M-S` or `D-M-I`/`I-M-D` edit patterns into a T/W operation. These checks allow exact swaps and several near-match cases based on edit distance or cyclic rotation.",
        "",
        "### 1.4 Minimum and maximum length",
        "",
        "- The direct transposition search has a **minimum span length of two** characters or words.",
        "- The inspected implementation has **no fixed maximum span length**. In particular, there is no two-character, three-character, or three-word cap.",
        "- The merger inspects local sequences of three edit groups, but that is a structural pattern, not a three-character/three-word maximum.",
        "- In practice, W still depends on the minimum-cost alignment path. A long permutation can therefore be decomposed into M/R/S before the classifier sees it, even though there is no formal length cap.",
        "",
        "### 1.5 Empirical check on the saved outputs",
        "",
        f"Across the eight datasets and four saved stages, ChERRANT processed **{totals['sentences']:,} sentence outputs** and generated **{totals['edits']:,} character edits**: M={totals['M']:,}, R={totals['R']:,}, S={totals['S']:,}, and W={totals['W']:,}. W appears in {totals['sentences_with_W']:,} sentence-stage outputs.",
        "",
        "### 1.6 Current `errant_compare` and more than three references",
        "",
        "The current upstream ERRANT 3.0.2 comparator was checked separately because two unrelated uses of the number three can be confused:",
        "",
        "- `-cat {1,2,3}` still denotes exactly three **error-category reporting tiers**: operation, main category, and the full combined category.",
        "- The number of **gold references is not capped at three**. `errant_compare` reads every annotator/coder ID in an M2 block and iterates over every hypothesis-reference combination.",
        "- The ChERRANT comparator used in the current pipeline behaves the same way when `--max_answer_num` is omitted. All formal runs omit this option, so every reference is retained.",
        "- In a synthetic five-reference test, both comparators loaded reference IDs 0--4 and matched the hypothesis only against ID 4, confirming that the fifth reference is evaluated.",
        "- In a real YACLC check, where every sentence has 4--11 references, upstream ERRANT 3.0.2 and the current ChERRANT comparator produced the same projection-character T0 result: P=0.5740, R=0.5841, and F0.5=0.5760.",
        "",
        "Accordingly, the current results already implement evaluation with more than three references; no pipeline or score-table update is required.",
        "",
        "## 2. Long-distance Word-Order Annotation Examples",
        "",
        "All examples below are real T0--T3 system outputs, not manually authored gold references. Each has a projection word-level W span in which at least one token moves four or more positions. They were selected from cases where ChERRANT did not emit W. The examples illustrate representational differences and should still be manually adjudicated before use as final paper evidence.",
        "",
    ]

    for index, row in enumerate(milestone_examples(candidates), start=1):
        word_start, word_end, word_label, _correction = parse_edit_line(
            row["projection_word_W"]
        )
        projection_edits = readable_edits(
            row["source"],
            row["projection_character_edits"],
            projection_labels=True,
        )
        cherrant_edits = readable_edits(
            row["source"],
            row["cherrant_character_edits"],
            projection_labels=False,
        )
        lines.extend(
            [
                f"### Example {index}: {row['dataset']} {row['stage']} row {row['row_id']}",
                "",
                f"**Source:** {row['source']}",
                "",
                f"**GEC system output:** {row['target']}",
                "",
                f"**Movement:** one projection W span over {row['word_span_tokens']} tokens (`{word_start}:{word_end}`), with a maximum token displacement of {row['max_token_movement']} positions.",
                "",
                "**Projection word representation:**",
                "",
                f"> `{row['source_word_span']}`",
                ">",
                f"> becomes `{row['target_word_span']}`",
                "",
                "**Projection character M2:**",
                "",
                *[f"- {description}" for description in projection_edits],
                "",
                "**ChERRANT character M2:**",
                "",
                *[f"- {description}" for description in cherrant_edits],
                "",
                f"**Summary:** Projection uses {len(projection_edits)} character edit(s), including `{row['projection_character_categories']}`; ChERRANT fragments the change into {len(cherrant_edits)} edit(s): `{row['cherrant_character_categories']}`.",
                "",
            ]
        )

    lines.extend(
        [
            "## 3. Key Findings",
            "",
            "ChERRANT is capable of producing W and does so thousands of times in the saved outputs. Its direct W rule has no fixed maximum length. However, in the long-distance cases above, the dynamic-programming path typically commits to insertions, deletions, or substitutions, and the local merger cannot recover the complete movement. Projection alignment reconnects corresponding material across distance and can serialize the moved region as one round-trippable W span at both character and word levels.",
            "",
            "This supports a qualitative claim that projection can provide a more coherent representation of some long-distance word-order errors. It does not, by itself, establish that every projection W is correct; the selected examples require manual linguistic confirmation.",
            "",
            "## 4. Implementation References",
            "",
            "- ChERRANT direct transposition: [`alignment.py`](../../external_tools/MuCGEC/scorers/ChERRANT/modules/alignment.py), lines 247--289.",
            "- ChERRANT transposition merger: [`merger.py`](../../external_tools/MuCGEC/scorers/ChERRANT/modules/merger.py), lines 96--165.",
            "- ChERRANT label mapping: [`classifier.py`](../../external_tools/MuCGEC/scorers/ChERRANT/modules/classifier.py), lines 97--143.",
            "- Current upstream ERRANT comparator: [`compare_m2.py`](../../external_tools/errant/errant/commands/compare_m2.py), especially lines 105--120, 126--194, and 203--266.",
            "- Full candidate inventory: [`../long_distance_word_order_audit/candidates.tsv`](../long_distance_word_order_audit/candidates.tsv).",
            "- Dataset-by-stage label counts: [`label_counts.tsv`](label_counts.tsv).",
            "",
        ]
    )
    return "\n".join(lines)


def build_report(
    label_rows: Sequence[dict[str, Any]],
    candidates: Sequence[dict[str, str]],
) -> str:
    stage_totals: dict[str, Counter[str]] = {
        stage: Counter() for stage in ROUNDS
    }
    for row in label_rows:
        stage_totals[row["stage"]].update(
            {
                key: int(row[key])
                for key in ("sentences", "edits", "M", "R", "S", "W", "sentences_with_W")
            }
        )
    overall = Counter()
    for totals in stage_totals.values():
        overall.update(totals)

    cherrant_edit_counts = [
        len([item for item in row["cherrant_character_edits"].split(" ; ") if item])
        for row in candidates
    ]
    cherrant_categories = Counter(
        category
        for row in candidates
        for category in row["cherrant_character_categories"].split(",")
        if category
    )
    category_sequences = Counter(
        row["cherrant_character_categories"] or "(none)" for row in candidates
    )
    unique = unique_candidates(candidates)
    projection_character_w = sum(
        "W" in row["projection_character_categories"].split(",")
        for row in candidates
    )

    lines = [
        "# ChERRANT Label and Long-distance Word-order Audit",
        "",
        "## Direct Answers",
        "",
        "1. **Character-level ChERRANT emits M/R/S/W.** M is missing text (insertion), R is redundant text (deletion), S is substitution, and W is transposition/word order. Character mode has no POS or spelling subtypes.",
        "2. **Word-level ChERRANT refines M/R/S but leaves W coarse.** It can emit M:<POS>, R:<POS>, S:<POS>, S:SPELL, and OTHER variants; W remains W.",
        "3. **Direct W detection is a contiguous-span permutation test.** During dynamic-programming alignment, ChERRANT expands a candidate span from length two upward and compares sorted source and target tokens. Equal sorted spans receive a transposition T operation, which the classifier maps to W.",
        "4. **There is no fixed maximum span length in the inspected ChERRANT implementation.** The search continues until a matching permutation is found or the sentence boundary is reached.",
        "5. **ChERRANT also has local transposition merge heuristics.** S-M-S and D-M-I/I-M-D patterns can become T/W under exact, edit-distance, or rotation checks.",
        "6. **Long-distance movement is often fragmented rather than labeled W.** If the alignment path does not choose one transposition and the local three-edit merger does not apply, ChERRANT represents the movement as several M/R/S edits.",
        "",
        "## Code Evidence",
        "",
        "- [`alignment.py`](../../external_tools/MuCGEC/scorers/ChERRANT/modules/alignment.py): lines 247--262 implement the sorted-span transposition search; lines 264--289 prioritize and store T operations.",
        "- [`merger.py`](../../external_tools/MuCGEC/scorers/ChERRANT/modules/merger.py): lines 96--165 implement S-M-S and D-M-I/I-M-D transposition merges.",
        "- [`classifier.py`](../../external_tools/MuCGEC/scorers/ChERRANT/modules/classifier.py): lines 97--143 map T/D/I/S to W/R/M/S in character mode and add fine-grained labels only in word mode.",
        "",
        "## Labels in the Saved Character M2 Outputs",
        "",
        "Counts below cover all saved T0--T3 hypothesis M2 files for the eight datasets.",
        "",
    ]
    stage_table = []
    for stage in ROUNDS:
        totals = stage_totals[stage]
        stage_table.append(
            [
                stage,
                f"{totals['sentences']:,}",
                f"{totals['edits']:,}",
                f"{totals['M']:,}",
                f"{totals['R']:,}",
                f"{totals['S']:,}",
                f"{totals['W']:,}",
                f"{totals['sentences_with_W']:,}",
            ]
        )
    stage_table.append(
        [
            "Total",
            f"{overall['sentences']:,}",
            f"{overall['edits']:,}",
            f"{overall['M']:,}",
            f"{overall['R']:,}",
            f"{overall['S']:,}",
            f"{overall['W']:,}",
            f"{overall['sentences_with_W']:,}",
        ]
    )
    add_table(
        lines,
        ("Stage", "Sentence outputs", "Edits", "M", "R", "S", "W", "Outputs with W"),
        stage_table,
    )
    lines.extend(
        [
            "The complete dataset-by-stage counts are in [`label_counts.tsv`](label_counts.tsv).",
            "",
            "## Long-distance Word-order Representation",
            "",
            f"The projection audit found **{len(candidates):,} stage-level W candidates** with a token moving at least four positions. After removing identical source-target repeats across T0--T3, **{len(unique):,} distinct candidates** remain.",
            "",
            f"- Projection character M2 also labels W in **{projection_character_w:,}/{len(candidates):,}** stage-level candidates.",
            "- ChERRANT W is absent from these candidates by construction; the audit selected cases where projection found W and ChERRANT did not.",
            f"- ChERRANT uses a mean of **{mean(cherrant_edit_counts):.2f}** character edits per candidate (median {median(cherrant_edit_counts):.1f}, maximum {max(cherrant_edit_counts)}), compared with one projection word-level W span.",
            "- ChERRANT's fragmented edit labels across these candidates are: "
            + ", ".join(f"{label}={count:,}" for label, count in sorted(cherrant_categories.items()))
            + ".",
            "- The most common ChERRANT label sequences are: "
            + "; ".join(
                f"`{sequence}` ({count})"
                for sequence, count in category_sequences.most_common(5)
            )
            + ".",
            "",
        ]
    )

    for index, row in enumerate(report_examples(candidates), start=1):
        lines.extend(
            [
                f"### Example {index}: {row['dataset']} {row['stage']} row {row['row_id']}",
                "",
                f"- Source: {row['source']}",
                f"- Target: {row['target']}",
                f"- Movement: maximum {row['max_token_movement']} token positions across a {row['word_span_tokens']}-token W span.",
                f"- Projection word M2: `{row['projection_word_W']}`",
                f"- Projection character M2: `{row['projection_character_edits']}`",
                f"- ChERRANT character M2: `{row['cherrant_character_edits']}`",
                "",
            ]
        )

    lines.extend(
        [
            "## Interpretation",
            "",
            "ChERRANT can label short or long contiguous permutations as W, so it is not inherently limited to two or three characters. Its limitation for the examples above is the alignment path: distant clause movement is frequently decomposed into insertion, deletion, and substitution operations before classification. The projection alignment explicitly reconnects identical or similar characters across distance, allowing the complete moved region to be serialized as one round-trippable W edit at both character and word levels.",
            "",
            "These examples demonstrate a representational difference, not automatic proof that every projection W is linguistically correct. The final paper examples should be manually adjudicated.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    label_rows = scan_hypothesis_labels()
    candidates = read_tsv(LONG_DISTANCE)
    if not candidates:
        raise RuntimeError("No long-distance candidates are available")
    DEFAULT_OUTPUT.mkdir(parents=True, exist_ok=True)
    write_tsv(DEFAULT_OUTPUT / "label_counts.tsv", label_rows)
    (DEFAULT_OUTPUT / "MILESTONE_REPORT.md").write_text(
        build_milestone_report(label_rows, candidates), encoding="utf-8"
    )
    print(DEFAULT_OUTPUT / "MILESTONE_REPORT.md")


if __name__ == "__main__":
    main()
