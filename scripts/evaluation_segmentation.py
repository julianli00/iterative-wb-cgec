#!/usr/bin/env python3
"""Fixed gold-informed source segmentation used by word-level evaluation."""

from __future__ import annotations

from dataclasses import dataclass
import csv
from pathlib import Path
import sqlite3
from typing import Any, Callable, Sequence

try:
    from projection_character_m2 import AlignmentResult, normalize_text
except ModuleNotFoundError:
    from scripts.projection_character_m2 import AlignmentResult, normalize_text


@dataclass(frozen=True)
class ReferenceSelection:
    index: int
    reference: str
    distance: int


@dataclass(frozen=True)
class FixedSourceSegmentation:
    row_index: int
    item_id: str
    source: str
    selected_reference_index: int
    selected_reference: str
    selected_reference_normalized: str
    levenshtein_distance: int
    source_ltp: str
    selected_reference_ltp: str
    fixed_source_segmentation: str


def levenshtein_distance(left: str, right: str) -> int:
    """Compute unit-cost character Levenshtein distance."""

    left = normalize_text(left)
    right = normalize_text(right)
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1]
                    + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]


def select_closest_reference(
    source: str, references: Sequence[str]
) -> ReferenceSelection:
    """Select minimum raw character distance, breaking ties by input order."""

    if not references:
        raise ValueError("At least one gold reference is required")
    candidates = [
        ReferenceSelection(index, reference, levenshtein_distance(source, reference))
        for index, reference in enumerate(references)
    ]
    return min(candidates, key=lambda candidate: (candidate.distance, candidate.index))


class LtpSegmentationCache:
    """Persistent deterministic LTP CWS cache shared by word evaluations."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS segmentation "
            "(text TEXT PRIMARY KEY, segmented TEXT NOT NULL)"
        )
        self.connection.commit()
        self._model: Any | None = None

    @property
    def model(self) -> Any:
        if self._model is None:
            from ltp import LTP

            self._model = LTP()
        return self._model

    def get_many(self, texts: Sequence[str], *, batch_size: int) -> dict[str, str]:
        normalized = list(dict.fromkeys(normalize_text(text) for text in texts))
        result: dict[str, str] = {}
        for query_start in range(0, len(normalized), 500):
            query = normalized[query_start : query_start + 500]
            if not query:
                continue
            placeholders = ",".join("?" for _ in query)
            for text, segmented in self.connection.execute(
                f"SELECT text, segmented FROM segmentation WHERE text IN ({placeholders})",
                query,
            ):
                result[text] = segmented
        missing = [text for text in normalized if text not in result]
        for start in range(0, len(missing), batch_size):
            batch = missing[start : start + batch_size]
            pipeline = self.model.pipeline(batch, tasks=["cws"])
            for text, tokens in zip(batch, pipeline.cws):
                segmented = " ".join(tokens)
                if normalize_text(segmented) != text:
                    raise ValueError(f"LTP changed surface text: {text!r}")
                result[text] = segmented
                self.connection.execute(
                    "INSERT OR REPLACE INTO segmentation (text, segmented) VALUES (?, ?)",
                    (text, segmented),
                )
            self.connection.commit()
        return result

    def close(self) -> None:
        self.connection.commit()
        self.connection.close()


def project_gold_boundaries_to_source(
    *,
    source_segmented: str,
    target_segmented: str,
    alignment: AlignmentResult,
    wb_module: Any,
) -> tuple[str, dict[str, int]]:
    """Apply the WB project's projection helpers to a selected gold target."""

    source = normalize_text(source_segmented)
    target = normalize_text(target_segmented)
    if not source:
        return source_segmented, {
            "exact": 0,
            "fuzzy": 0,
            "projected_boundaries": 0,
            "skipped_boundaries": 0,
            "merged_spans": 0,
            "merge_skips": 0,
        }
    if target != normalize_text(target_segmented):
        raise AssertionError("Unexpected target normalization failure")
    base_boundaries = wb_module.get_word_final_positions(source_segmented)
    # This mirrors the original WB projection function: boundary transfer uses
    # the exact alignment plus the deterministic raw Step-2 fuzzy assignments.
    combined = {**alignment.exact, **alignment.fuzzy_raw}
    boundaries, projected, skipped = wb_module.project_boundaries_conservatively(
        target_text=target_segmented,
        aligned=combined,
        base_boundaries=base_boundaries,
    )
    boundaries, merged, merge_skips = wb_module.apply_exact_match_merge_constraint(
        target_text=target_segmented,
        aligned=combined,
        word_final_positions=boundaries,
    )
    boundaries.add(len(source) - 1)
    segmented = wb_module.positions_to_segmented(source, boundaries)
    if normalize_text(segmented) != source:
        raise ValueError("Gold-informed projection changed learner surface text")
    return segmented, {
        "exact": len(alignment.exact),
        "fuzzy": len(alignment.fuzzy_raw),
        "projected_boundaries": len(projected),
        "skipped_boundaries": len(skipped),
        "merged_spans": len(merged),
        "merge_skips": len(merge_skips),
    }


def write_fixed_segmentations(
    path: Path, records: Sequence[FixedSourceSegmentation]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(FixedSourceSegmentation.__dataclass_fields__)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for record in records:
            writer.writerow(record.__dict__)


def load_fixed_segmentations(
    path: Path,
    *,
    expected_sources: Sequence[str] | None = None,
) -> list[FixedSourceSegmentation]:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing fixed gold-informed segmentation: {path}. "
            "Run scripts/prepare_gold_source_segmentations.py first."
        )
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    records = [
        FixedSourceSegmentation(
            row_index=int(row["row_index"]),
            item_id=row["item_id"],
            source=row["source"],
            selected_reference_index=int(row["selected_reference_index"]),
            selected_reference=row["selected_reference"],
            selected_reference_normalized=row["selected_reference_normalized"],
            levenshtein_distance=int(row["levenshtein_distance"]),
            source_ltp=row["source_ltp"],
            selected_reference_ltp=row["selected_reference_ltp"],
            fixed_source_segmentation=row["fixed_source_segmentation"],
        )
        for row in rows
    ]
    if [record.row_index for record in records] != list(range(len(records))):
        raise ValueError(f"Fixed segmentation rows are not contiguous in {path}")
    if expected_sources is not None:
        if len(records) != len(expected_sources):
            raise ValueError(
                f"Fixed segmentation row mismatch: {len(records)} != {len(expected_sources)}"
            )
        for index, (record, source) in enumerate(
            zip(records, expected_sources), start=1
        ):
            if normalize_text(record.source) != normalize_text(source):
                raise ValueError(f"Fixed segmentation source mismatch at row {index}")
            if normalize_text(record.fixed_source_segmentation) != normalize_text(source):
                raise ValueError(f"Fixed segmentation changed source at row {index}")
    return records


def fixed_segmentation_path(root: Path, dataset: str, split: str) -> Path:
    return root / dataset / split / "fixed_source_segmentation.tsv"
