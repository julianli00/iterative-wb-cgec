#!/usr/bin/env python3
"""Prepare one gold-informed source segmentation per evaluation sentence."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Sequence

from evaluation_segmentation import (
    FixedSourceSegmentation,
    LtpSegmentationCache,
    fixed_segmentation_path,
    project_gold_boundaries_to_source,
    select_closest_reference,
    write_fixed_segmentations,
)
from projection_character_m2 import (
    DEFAULT_SHAPE_TABLE,
    DEFAULT_WB_REPO,
    AlignmentResult,
    TwoStepCharacterAligner,
    normalize_text,
)
from run_projection_m2_evaluation import load_target_normalizer
from standardize_m2_evaluation import (
    ROOT,
    DatasetSpec,
    load_result_rows,
    load_specs,
    para_rows,
)


DEFAULT_OUTPUT = ROOT / "runs/gold_fixed_source_segmentation"
DEFAULT_LTP_CACHE = ROOT / "runs/word_evaluation_shared/ltp_segmentation_cache.sqlite3"


class ProjectionCache:
    """Cache projected source segmentations, including alignment policy."""

    def __init__(self, path: Path, config: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projection (
                cache_key TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                source_segmented TEXT NOT NULL,
                target_segmented TEXT NOT NULL,
                projected TEXT NOT NULL,
                stats TEXT NOT NULL
            )
            """
        )
        self.connection.commit()
        self.config = json.dumps(config, ensure_ascii=False, sort_keys=True)

    def _key(
        self, source: str, target: str, source_segmented: str, target_segmented: str
    ) -> str:
        import hashlib

        digest = hashlib.sha256()
        for value in (
            self.config,
            source,
            target,
            source_segmented,
            target_segmented,
        ):
            digest.update(value.encode("utf-8"))
            digest.update(b"\0")
        return digest.hexdigest()

    def get(
        self, source: str, target: str, source_segmented: str, target_segmented: str
    ) -> tuple[str, dict[str, int]] | None:
        row = self.connection.execute(
            "SELECT projected, stats FROM projection WHERE cache_key = ?",
            (self._key(source, target, source_segmented, target_segmented),),
        ).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def put(
        self,
        source: str,
        target: str,
        source_segmented: str,
        target_segmented: str,
        projected: str,
        stats: dict[str, int],
    ) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO projection VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self._key(source, target, source_segmented, target_segmented),
                source,
                target,
                source_segmented,
                target_segmented,
                projected,
                json.dumps(stats, ensure_ascii=False, sort_keys=True),
            ),
        )

    def close(self) -> None:
        self.connection.commit()
        self.connection.close()


def prepare_dataset(
    spec: DatasetSpec,
    *,
    output_root: Path,
    segmenter: LtpSegmentationCache,
    cache: ProjectionCache,
    aligner_factory: Callable[[], TwoStepCharacterAligner],
    normalize_target: Callable[[str], str],
    ltp_batch_size: int,
    alignment_batch_size: int,
    embedding_batch_size: int,
) -> dict[str, Any]:
    gold_rows = para_rows(spec.gold_para)
    result_rows = load_result_rows(spec)
    if len(gold_rows) != spec.rows or len(result_rows) != spec.rows:
        raise ValueError(f"{spec.dataset}: row-count mismatch")

    selected = []
    for row_index, (gold_row, result_row) in enumerate(zip(gold_rows, result_rows)):
        source = result_row["source"]
        if normalize_text(gold_row[1]) != normalize_text(source):
            raise ValueError(f"{spec.dataset}: source mismatch at row {row_index + 1}")
        choice = select_closest_reference(source, gold_row[2:])
        selected.append((row_index, gold_row, result_row, choice))

    normalized_targets = [
        normalize_target(choice.reference) for _index, _gold, _result, choice in selected
    ]
    target_segmentations = segmenter.get_many(
        normalized_targets, batch_size=ltp_batch_size
    )
    records: list[FixedSourceSegmentation | None] = [None] * len(selected)
    missing: list[
        tuple[int, list[str], dict[str, str], Any, str, str]
    ] = []
    cache_hits = 0
    stats_totals: Counter[str] = Counter()
    for row_index, gold_row, result_row, choice in selected:
        source = normalize_text(result_row["source"])
        source_ltp = result_row["S1"]
        if normalize_text(source_ltp) != source:
            raise ValueError(f"{spec.dataset}: S1 changed source at row {row_index + 1}")
        target = normalize_target(choice.reference)
        target_ltp = target_segmentations[target]
        cached = cache.get(source, target, source_ltp, target_ltp)
        if cached is None:
            missing.append((row_index, gold_row, result_row, choice, target, target_ltp))
            continue
        projected, projection_stats = cached
        cache_hits += 1
        stats_totals.update(projection_stats)
        records[row_index] = FixedSourceSegmentation(
            row_index=row_index,
            item_id=gold_row[0],
            source=source,
            selected_reference_index=choice.index,
            selected_reference=choice.reference,
            selected_reference_normalized=target,
            levenshtein_distance=choice.distance,
            source_ltp=source_ltp,
            selected_reference_ltp=target_ltp,
            fixed_source_segmentation=projected,
        )

    aligner: TwoStepCharacterAligner | None = None
    for start in range(0, len(missing), alignment_batch_size):
        batch = missing[start : start + alignment_batch_size]
        if aligner is None:
            aligner = aligner_factory()
        alignments: Sequence[AlignmentResult] = aligner.align_many(
            [(record[2]["source"], record[4]) for record in batch],
            embedding_batch_size=embedding_batch_size,
        )
        for record, alignment in zip(batch, alignments):
            row_index, gold_row, result_row, choice, target, target_ltp = record
            source = normalize_text(result_row["source"])
            source_ltp = result_row["S1"]
            projected, projection_stats = project_gold_boundaries_to_source(
                source_segmented=source_ltp,
                target_segmented=target_ltp,
                alignment=alignment,
                wb_module=aligner.module,
            )
            cache.put(
                source, target, source_ltp, target_ltp, projected, projection_stats
            )
            stats_totals.update(projection_stats)
            records[row_index] = FixedSourceSegmentation(
                row_index=row_index,
                item_id=gold_row[0],
                source=source,
                selected_reference_index=choice.index,
                selected_reference=choice.reference,
                selected_reference_normalized=target,
                levenshtein_distance=choice.distance,
                source_ltp=source_ltp,
                selected_reference_ltp=target_ltp,
                fixed_source_segmentation=projected,
            )
        cache.connection.commit()
        print(
            f"[{spec.dataset}] projected {min(start + len(batch), len(missing)):,}/"
            f"{len(missing):,} uncached rows",
            flush=True,
        )

    if any(record is None for record in records):
        raise RuntimeError(f"{spec.dataset}: fixed segmentation record missing")
    complete = [record for record in records if record is not None]
    destination = fixed_segmentation_path(output_root, spec.dataset, spec.split)
    write_fixed_segmentations(destination, complete)
    changed_from_ltp = sum(
        record.fixed_source_segmentation != record.source_ltp for record in complete
    )
    multi_reference = sum(len(row) > 3 for row in gold_rows)
    selected_nonfirst = sum(record.selected_reference_index > 0 for record in complete)
    summary = {
        "dataset": spec.dataset,
        "split": spec.split,
        "sentences": len(complete),
        "references": sum(len(row) - 2 for row in gold_rows),
        "multi_reference_sentences": multi_reference,
        "selected_nonfirst_reference": selected_nonfirst,
        "source_segmentation_changed_from_ltp": changed_from_ltp,
        "cache_hits": cache_hits,
        "cache_misses": len(missing),
        "projection_totals": dict(stats_totals),
        "output": str(destination.relative_to(ROOT)),
    }
    destination.with_name("stats.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    specs = load_specs()
    choices = [spec.dataset for spec in specs]
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", nargs="+", choices=choices, default=choices)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ltp-cache", type=Path, default=DEFAULT_LTP_CACHE)
    parser.add_argument("--ltp-batch-size", type=int, default=128)
    parser.add_argument("--alignment-batch-size", type=int, default=64)
    parser.add_argument("--embedding-batch-size", type=int, default=32)
    parser.add_argument("--wb-repo", type=Path, default=DEFAULT_WB_REPO)
    parser.add_argument("--shape-table", type=Path, default=DEFAULT_SHAPE_TABLE)
    parser.add_argument("--threshold", type=float, default=0.85)
    parser.add_argument("--bert-model", default="bert-base-chinese")
    parser.add_argument("--target-normalization", choices=("t2s", "none"), default="none")
    args = parser.parse_args()
    if min(args.ltp_batch_size, args.alignment_batch_size, args.embedding_batch_size) < 1:
        parser.error("Batch sizes must be positive")

    selected_specs = [spec for spec in specs if spec.dataset in args.datasets]
    args.output_root.mkdir(parents=True, exist_ok=True)
    normalize_target = load_target_normalizer(args.target_normalization)
    config = {
        "implementation": "gold-informed-source-segmentation-v1",
        "reference_selection": "minimum raw character Levenshtein distance; first-reference tie break",
        "source_base": "saved S1 LTP segmentation",
        "target_segmentation": "LTP",
        "projection": "exact plus four-feature raw fuzzy WB boundary projection",
        "threshold": args.threshold,
        "bert_model": args.bert_model,
        "target_normalization": args.target_normalization,
    }
    segmenter = LtpSegmentationCache(args.ltp_cache)
    projection_cache = ProjectionCache(
        args.output_root / "projection_cache.sqlite3", config
    )
    aligner: TwoStepCharacterAligner | None = None

    def get_aligner() -> TwoStepCharacterAligner:
        nonlocal aligner
        if aligner is None:
            aligner = TwoStepCharacterAligner(
                wb_repo=args.wb_repo,
                shape_table=args.shape_table,
                threshold=args.threshold,
                bert_model=args.bert_model,
            )
        return aligner

    summaries = []
    try:
        for spec in selected_specs:
            summaries.append(
                prepare_dataset(
                    spec,
                    output_root=args.output_root,
                    segmenter=segmenter,
                    cache=projection_cache,
                    aligner_factory=get_aligner,
                    normalize_target=normalize_target,
                    ltp_batch_size=args.ltp_batch_size,
                    alignment_batch_size=args.alignment_batch_size,
                    embedding_batch_size=args.embedding_batch_size,
                )
            )
    finally:
        segmenter.close()
        projection_cache.close()

    (args.output_root / "run_config.json").write_text(
        json.dumps(
            {
                "completed_utc": datetime.now(timezone.utc).isoformat(),
                **config,
                "datasets": [spec.dataset for spec in selected_specs],
                "llm_calls": False,
                "summaries": summaries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(args.output_root / "run_config.json")


if __name__ == "__main__":
    main()
