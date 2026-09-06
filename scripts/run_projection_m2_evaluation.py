#!/usr/bin/env python3
"""Evaluate CGEC outputs with projection-derived character M2 files.

For every source/target pair, this runner uses the WB project's two-step
character alignment, writes standard S/A-only M2, and scores T0--T3 with the
existing ChERRANT comparator. The corresponding ChERRANT-generated M2 files
are scored with the same comparator and beta values as a controlled baseline.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any, Callable, Sequence

try:
    from projection_character_m2 import (
        DEFAULT_SHAPE_TABLE,
        DEFAULT_WB_REPO,
        CharacterEdit,
        TwoStepCharacterAligner,
        apply_edits,
        label_transpositions,
        normalize_text,
        render_m2_block,
        validate_m2_targets,
    )
    from movement_m2 import DEFAULT_L_MAX_CHAR
    from standardize_m2_evaluation import (
        CHERRANT,
        ROOT,
        ROUNDS,
        DatasetSpec,
        load_result_rows,
        load_specs,
        para_rows,
        parse_compare_output,
    )
except ModuleNotFoundError:
    from scripts.projection_character_m2 import (
        DEFAULT_SHAPE_TABLE,
        DEFAULT_WB_REPO,
        CharacterEdit,
        TwoStepCharacterAligner,
        apply_edits,
        label_transpositions,
        normalize_text,
        render_m2_block,
        validate_m2_targets,
    )
    from scripts.movement_m2 import DEFAULT_L_MAX_CHAR
    from scripts.standardize_m2_evaluation import (
        CHERRANT,
        ROOT,
        ROUNDS,
        DatasetSpec,
        load_result_rows,
        load_specs,
        para_rows,
        parse_compare_output,
    )


DEFAULT_OUTPUT = ROOT / "runs/projection_character_m2_eval_final"
DEFAULT_BASELINE_ROOT = ROOT / "runs/standardized_m2_eval"
DEFAULT_PYTHON = Path(sys.executable)
IMPLEMENTATION_VERSION = "projection-character-m2-v4-linked-movement"
BETAS = (0.5, 1.0, 2.0)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_target_normalizer(name: str) -> Callable[[str], str]:
    if name == "none":
        return normalize_text
    if name == "t2s":
        try:
            from opencc import OpenCC
        except ImportError as exc:
            raise RuntimeError(
                "OpenCC is required for --target-normalization t2s"
            ) from exc
        converter = OpenCC("t2s")
        return lambda text: normalize_text(converter.convert(normalize_text(text)))
    raise ValueError(f"Unsupported target normalization: {name}")


class PairCache:
    """Persistent source-target conversion cache for resumable long runs."""

    def __init__(self, path: Path, config: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pair_cache (
                cache_key TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_utc TEXT NOT NULL
            )
            """
        )
        self.connection.commit()
        self.config_json = json.dumps(config, ensure_ascii=False, sort_keys=True)
        self.pending_writes = 0

    def key(self, source: str, target: str) -> str:
        digest = hashlib.sha256()
        for value in (self.config_json, source, target):
            digest.update(value.encode("utf-8"))
            digest.update(b"\0")
        return digest.hexdigest()

    def get(self, source: str, target: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT payload FROM pair_cache WHERE cache_key = ?",
            (self.key(source, target),),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, source: str, target: str, payload: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO pair_cache
                (cache_key, source, target, payload, created_utc)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                self.key(source, target),
                source,
                target,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.pending_writes += 1
        if self.pending_writes >= 50:
            self.commit()

    def commit(self) -> None:
        self.connection.commit()
        self.pending_writes = 0

    def close(self) -> None:
        self.commit()
        self.connection.close()

    def entry_count(self) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) FROM pair_cache"
        ).fetchone()
        return int(row[0])


def migrate_legacy_cache(
    path: Path, cache: PairCache, *, l_max_char: int
) -> dict[str, int]:
    """Reuse v1 projection alignments while adding deterministic W labels."""

    stats = {"read": 0, "migrated": 0, "already_present": 0}
    cache_path = Path(
        cache.connection.execute("PRAGMA database_list").fetchone()[2]
    ).resolve()
    if not path.exists() or path.resolve() == cache_path:
        return stats
    legacy = sqlite3.connect(path)
    try:
        for source, target, payload_text in legacy.execute(
            "SELECT source, target, payload FROM pair_cache"
        ):
            stats["read"] += 1
            if cache.get(source, target) is not None:
                stats["already_present"] += 1
                continue
            payload = json.loads(payload_text)
            edits = [CharacterEdit(**record) for record in payload["edits"]]
            edits = label_transpositions(
                source, target, edits, l_max=l_max_char
            )
            if apply_edits(source, edits) != target:
                raise ValueError("Migrated edits failed round-trip validation")
            cache.put(
                source,
                target,
                {
                    "edits": [asdict(edit) for edit in edits],
                    "alignment_stats": payload["alignment_stats"],
                },
            )
            stats["migrated"] += 1
    finally:
        legacy.close()
        cache.commit()
    return stats


class CachedConverter:
    def __init__(
        self,
        cache: PairCache,
        aligner_factory: Callable[[], TwoStepCharacterAligner],
        *,
        force: bool,
    ) -> None:
        self.cache = cache
        self.aligner_factory = aligner_factory
        self.force = force
        self._aligner: TwoStepCharacterAligner | None = None
        self.cache_hits = 0
        self.cache_misses = 0

    @property
    def aligner(self) -> TwoStepCharacterAligner:
        if self._aligner is None:
            self._aligner = self.aligner_factory()
        return self._aligner

    def convert(
        self, source: str, target: str
    ) -> tuple[list[CharacterEdit], dict[str, int], bool]:
        return self.convert_many([(source, target)])[0]

    def convert_many(
        self,
        pairs: Sequence[tuple[str, str]],
        *,
        embedding_batch_size: int = 32,
    ) -> list[tuple[list[CharacterEdit], dict[str, int], bool]]:
        normalized = [
            (normalize_text(source), normalize_text(target))
            for source, target in pairs
        ]
        results: list[
            tuple[list[CharacterEdit], dict[str, int], bool] | None
        ] = [None] * len(normalized)
        missing_positions: dict[tuple[str, str], list[int]] = {}
        for index, (source, target) in enumerate(normalized):
            payload = None if self.force else self.cache.get(source, target)
            if payload is not None:
                edits = [
                    CharacterEdit(**record) for record in payload["edits"]
                ]
                if apply_edits(source, edits) != target:
                    raise ValueError("Cached edits failed round-trip validation")
                results[index] = (edits, payload["alignment_stats"], True)
                self.cache_hits += 1
            else:
                missing_positions.setdefault((source, target), []).append(index)

        unique_missing = list(missing_positions)
        if unique_missing:
            converted = self.aligner.convert_many(
                unique_missing,
                embedding_batch_size=embedding_batch_size,
            )
            for (source, target), (edits, alignment) in zip(
                unique_missing, converted
            ):
                alignment_stats = {
                    "exact": len(alignment.exact),
                    "fuzzy_raw": len(alignment.fuzzy_raw),
                    "fuzzy_monotonic": len(alignment.fuzzy_monotonic),
                    "fuzzy_rejected": (
                        len(alignment.fuzzy_raw)
                        - len(alignment.fuzzy_monotonic)
                    ),
                    "unaligned_source_after_exact": len(
                        alignment.unaligned_source
                    ),
                    "unaligned_target_after_exact": len(
                        alignment.unaligned_target
                    ),
                }
                self.cache.put(
                    source,
                    target,
                    {
                        "edits": [asdict(edit) for edit in edits],
                        "alignment_stats": alignment_stats,
                    },
                )
                positions = missing_positions[(source, target)]
                for offset, position in enumerate(positions):
                    duplicate = offset > 0
                    results[position] = (
                        edits,
                        alignment_stats,
                        duplicate,
                    )
                    if duplicate:
                        self.cache_hits += 1
                    else:
                        self.cache_misses += 1

        if any(result is None for result in results):
            raise RuntimeError("Internal error: an alignment result is missing")
        return [result for result in results if result is not None]

    def _convert_unbatched(
        self, source: str, target: str
    ) -> tuple[list[CharacterEdit], dict[str, int], bool]:
        """Direct single-pair implementation retained for regression tests."""

        source = normalize_text(source)
        target = normalize_text(target)
        payload = None if self.force else self.cache.get(source, target)
        if payload is not None:
            edits = [CharacterEdit(**record) for record in payload["edits"]]
            if apply_edits(source, edits) != target:
                raise ValueError("Cached edits failed round-trip validation")
            self.cache_hits += 1
            return edits, payload["alignment_stats"], True

        edits, alignment = self.aligner.convert(source, target)
        alignment_stats = {
            "exact": len(alignment.exact),
            "fuzzy_raw": len(alignment.fuzzy_raw),
            "fuzzy_monotonic": len(alignment.fuzzy_monotonic),
            "fuzzy_rejected": (
                len(alignment.fuzzy_raw) - len(alignment.fuzzy_monotonic)
            ),
            "unaligned_source_after_exact": len(alignment.unaligned_source),
            "unaligned_target_after_exact": len(alignment.unaligned_target),
        }
        self.cache.put(
            source,
            target,
            {
                "edits": [asdict(edit) for edit in edits],
                "alignment_stats": alignment_stats,
            },
        )
        self.cache_misses += 1
        return edits, alignment_stats, False


def _empty_conversion_stats() -> dict[str, int]:
    return {
        "pairs": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "edits": 0,
        "M": 0,
        "R": 0,
        "U": 0,
        "W": 0,
        "W_LD": 0,
        "exact_alignments": 0,
        "fuzzy_alignments_raw": 0,
        "fuzzy_alignments_monotonic": 0,
        "fuzzy_alignments_rejected": 0,
    }


def _record_conversion(
    stats: dict[str, int],
    edits: Sequence[CharacterEdit],
    alignment_stats: dict[str, int],
    cached: bool,
) -> None:
    stats["pairs"] += 1
    stats["cache_hits" if cached else "cache_misses"] += 1
    stats["edits"] += len(edits)
    for edit in edits:
        stats[edit.edit_type] += 1
    stats["W_LD"] += sum(1 for edit in edits if "FROM=" in edit.comment)
    stats["exact_alignments"] += alignment_stats["exact"]
    stats["fuzzy_alignments_raw"] += alignment_stats["fuzzy_raw"]
    stats["fuzzy_alignments_monotonic"] += alignment_stats[
        "fuzzy_monotonic"
    ]
    stats["fuzzy_alignments_rejected"] += alignment_stats["fuzzy_rejected"]


def _write_block(handle: Any, block: str, block_index: int) -> None:
    if block_index:
        handle.write("\n")
    handle.write(block)
    handle.write("\n")


def generate_dataset_m2(
    spec: DatasetSpec,
    output_dir: Path,
    converter: CachedConverter,
    *,
    rounds: Sequence[str],
    limit: int,
    progress_every: int,
    alignment_batch_rows: int,
    embedding_batch_size: int,
    normalize_target: Callable[[str], str],
) -> tuple[dict[str, Path], dict[str, Any]]:
    gold_rows = para_rows(spec.gold_para)
    result_rows = load_result_rows(spec)
    row_count = min(len(result_rows), limit) if limit else len(result_rows)
    gold_rows = gold_rows[:row_count]
    result_rows = result_rows[:row_count]

    if len(gold_rows) != row_count:
        raise ValueError(
            f"{spec.dataset}: gold row mismatch {len(gold_rows)} != {row_count}"
        )

    for index, (gold_row, result_row) in enumerate(
        zip(gold_rows, result_rows), start=1
    ):
        if len(gold_row) < 3:
            raise ValueError(f"{spec.dataset}: no gold target at row {index}")
        if normalize_text(gold_row[1]) != normalize_text(result_row["source"]):
            raise ValueError(f"{spec.dataset}: source mismatch at row {index}")

    output_dir.mkdir(parents=True, exist_ok=True)
    final_paths = {
        "reference": output_dir / "reference.projection.all.char.m2",
        **{
            round_name: output_dir / f"hypothesis.{round_name}.projection.char.m2"
            for round_name in rounds
        },
    }
    temporary_paths = {
        name: path.with_suffix(path.suffix + ".tmp")
        for name, path in final_paths.items()
    }
    handles = {
        name: path.open("w", encoding="utf-8", newline="\n")
        for name, path in temporary_paths.items()
    }
    stats = {
        "dataset": spec.dataset,
        "split": spec.split,
        "sentences": row_count,
        "references": _empty_conversion_stats(),
        "hypotheses": {
            round_name: _empty_conversion_stats() for round_name in rounds
        },
    }

    cache_entries = 0
    try:
        for chunk_start in range(0, row_count, alignment_batch_rows):
            chunk_end = min(row_count, chunk_start + alignment_batch_rows)
            pair_requests: list[tuple[str, str]] = []
            request_layout: list[tuple[int, int]] = []
            for gold_row, result_row in zip(
                gold_rows[chunk_start:chunk_end],
                result_rows[chunk_start:chunk_end],
            ):
                source = result_row["source"]
                start = len(pair_requests)
                pair_requests.extend(
                    (source, normalize_target(target)) for target in gold_row[2:]
                )
                pair_requests.extend(
                    (source, normalize_target(result_row[round_name]))
                    for round_name in rounds
                )
                request_layout.append((start, len(gold_row) - 2))

            converted_pairs = converter.convert_many(
                pair_requests,
                embedding_batch_size=embedding_batch_size,
            )
            for local_index, (gold_row, result_row) in enumerate(
                zip(
                    gold_rows[chunk_start:chunk_end],
                    result_rows[chunk_start:chunk_end],
                )
            ):
                row_index = chunk_start + local_index
                pair_start, reference_count = request_layout[local_index]
                source = result_row["source"]
                converted_references: list[
                    tuple[str, Sequence[CharacterEdit]]
                ] = []
                for reference_offset, target in enumerate(gold_row[2:]):
                    normalized_target = normalize_target(target)
                    edits, alignment_stats, cached = converted_pairs[
                        pair_start + reference_offset
                    ]
                    _record_conversion(
                        stats["references"], edits, alignment_stats, cached
                    )
                    converted_references.append((normalized_target, edits))
                _write_block(
                    handles["reference"],
                    render_m2_block(source, converted_references),
                    row_index,
                )

                for round_offset, round_name in enumerate(rounds):
                    target = normalize_target(result_row[round_name])
                    edits, alignment_stats, cached = converted_pairs[
                        pair_start + reference_count + round_offset
                    ]
                    _record_conversion(
                        stats["hypotheses"][round_name],
                        edits,
                        alignment_stats,
                        cached,
                    )
                    _write_block(
                        handles[round_name],
                        render_m2_block(source, [(target, edits)]),
                        row_index,
                    )

            if chunk_end % progress_every == 0 or chunk_end == row_count:
                print(
                    f"[{spec.dataset}] M2 {chunk_end}/{row_count}; "
                    f"cache hits={converter.cache_hits}, "
                    f"misses={converter.cache_misses}",
                    flush=True,
                )
    finally:
        for handle in handles.values():
            handle.close()
        converter.cache.commit()

    for name, temporary_path in temporary_paths.items():
        os.replace(temporary_path, final_paths[name])
    stats["serialized_validation"] = {
        "reference": validate_m2_targets(
            final_paths["reference"],
            [
                (
                    result_row["source"],
                    [normalize_target(target) for target in gold_row[2:]],
                )
                for gold_row, result_row in zip(gold_rows, result_rows)
            ],
        ),
        **{
            round_name: validate_m2_targets(
                final_paths[round_name],
                [
                    (
                        row["source"],
                        [normalize_target(row[round_name])],
                    )
                    for row in result_rows
                ],
            )
            for round_name in rounds
        },
    }
    return final_paths, stats


def run_compare(
    *,
    hypothesis: Path,
    reference: Path,
    beta: float,
    python: Path,
    output_path: Path,
    unit: str = "character",
    limit: int = 0,
) -> dict[str, int | float]:
    command = [
        str(python),
        str(ROOT / "scripts/movement_aware_compare.py"),
        "-hyp",
        str(hypothesis),
        "-ref",
        str(reference),
        "--beta",
        str(beta),
        "--unit",
        unit,
    ]
    if limit:
        command.extend(["--start", "0", "--end", str(limit)])
    process = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(process.stdout, encoding="utf-8")
    if process.returncode:
        raise RuntimeError(
            f"Comparator failed ({process.returncode}): {' '.join(command)}\n"
            f"{process.stdout}"
        )
    metrics = parse_compare_output(process.stdout)
    metrics["F_beta"] = metrics.pop("F0.5")
    return metrics


def evaluate_dataset(
    spec: DatasetSpec,
    output_dir: Path,
    projection_paths: dict[str, Path],
    *,
    baseline_root: Path,
    rounds: Sequence[str],
    python: Path,
    row_count: int,
    is_limited: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    baseline_dir = baseline_root / spec.dataset / spec.split / "char"
    baseline_reference = baseline_dir / "reference.generated.all.char.m2"

    for method in ("cherrant", "projection"):
        reference = (
            baseline_reference
            if method == "cherrant"
            else projection_paths["reference"]
        )
        if not reference.exists():
            if method == "cherrant":
                print(
                    f"[{spec.dataset}] baseline M2 unavailable; skipping comparison",
                    flush=True,
                )
                continue
            raise FileNotFoundError(reference)
        for round_name in rounds:
            hypothesis = (
                baseline_dir / f"hypothesis.{round_name}.char.m2"
                if method == "cherrant"
                else projection_paths[round_name]
            )
            if not hypothesis.exists():
                raise FileNotFoundError(hypothesis)
            for beta in BETAS:
                metrics = run_compare(
                    hypothesis=hypothesis,
                    reference=reference,
                    beta=beta,
                    python=python,
                    output_path=(
                        output_dir
                        / "comparisons"
                        / method
                        / f"{round_name}.beta{beta:g}.txt"
                    ),
                    unit="character",
                    limit=row_count if method == "cherrant" and is_limited else 0,
                )
                rows.append(
                    {
                        "dataset": spec.dataset,
                        "split": spec.split,
                        "sentences": row_count,
                        "alignment": method,
                        "round": round_name,
                        "beta": beta,
                        **metrics,
                    }
                )
    return rows


def write_dataset_outputs(
    output_dir: Path,
    rows: list[dict[str, Any]],
    stats: dict[str, Any],
) -> None:
    with (output_dir / "scores.long.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "generation_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_global_outputs(
    output_root: Path,
    rows: list[dict[str, Any]],
    specs: Sequence[DatasetSpec],
    rounds: Sequence[str],
) -> None:
    with (output_root / "scores.long.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    indexed = {
        (row["dataset"], row["alignment"], row["round"], row["beta"]): row
        for row in rows
    }
    table_rows: list[dict[str, Any]] = []
    for spec in specs:
        for round_name in rounds:
            old = indexed.get((spec.dataset, "cherrant", round_name, 0.5))
            new = indexed[(spec.dataset, "projection", round_name, 0.5)]
            table_rows.append(
                {
                    "dataset": spec.dataset,
                    "split": spec.split,
                    "sentences": new["sentences"],
                    "round": round_name,
                    "cherrant_F0.5_x100": (
                        "" if old is None else 100 * float(old["F_beta"])
                    ),
                    "projection_F0.5_x100": 100 * float(new["F_beta"]),
                    "projection_minus_cherrant_x100": (
                        ""
                        if old is None
                        else 100
                        * (float(new["F_beta"]) - float(old["F_beta"]))
                    ),
                }
            )

    with (output_root / "scores.f05_comparison.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(table_rows[0]), delimiter="\t"
        )
        writer.writeheader()
        writer.writerows(table_rows)

    markdown = [
        "# Projection-based Character M2 Evaluation",
        "",
        "Both methods use the same source-target pairs, all textual gold "
        "references, character offsets without BPE, the same ChERRANT "
        "comparator, and corpus-level F0.5 x 100. Only the character alignment "
        "and resulting M2 edits differ.",
        "",
        "| Dataset | Split | N | Stage | ChERRANT | Projection | Delta |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: |",
    ]
    for row in table_rows:
        old = row["cherrant_F0.5_x100"]
        delta = row["projection_minus_cherrant_x100"]
        markdown.append(
            f"| {row['dataset']} | {row['split']} | {row['sentences']:,} | "
            f"{row['round']} | "
            f"{'n/a' if old == '' else f'{old:.2f}'} | "
            f"{row['projection_F0.5_x100']:.2f} | "
            f"{'n/a' if delta == '' else f'{delta:+.2f}'} |"
        )
    markdown.extend(
        [
            "",
            "F1 and F2, together with TP/FP/FN and precision/recall, are retained "
            "in `scores.long.tsv`.",
            "",
        ]
    )
    (output_root / "scores.f05_comparison.md").write_text(
        "\n".join(markdown), encoding="utf-8"
    )

    for method, label in (
        ("cherrant", "ChERRANT-generated M2"),
        ("projection", "WB projection M2"),
    ):
        matrix_rows: list[dict[str, Any]] = []
        for spec in specs:
            row: dict[str, Any] = {
                "dataset": spec.dataset,
                "split": spec.split,
                "sentences": indexed[
                    (spec.dataset, method, rounds[0], 0.5)
                ]["sentences"],
            }
            for round_name in rounds:
                row[round_name] = 100 * float(
                    indexed[
                        (spec.dataset, method, round_name, 0.5)
                    ]["F_beta"]
                )
            matrix_rows.append(row)

        stem = f"scores.{method}.f05"
        with (output_root / f"{stem}.tsv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["dataset", "split", "sentences", *rounds],
                delimiter="\t",
            )
            writer.writeheader()
            writer.writerows(matrix_rows)

        matrix_markdown = [
            f"# {label}: Character-level F0.5",
            "",
            "Corpus-level F0.5 scores are multiplied by 100.",
            "",
            "| Dataset | Split | N | "
            + " | ".join(rounds)
            + " |",
            "| --- | --- | ---: | "
            + " | ".join("---:" for _round in rounds)
            + " |",
        ]
        for row in matrix_rows:
            matrix_markdown.append(
                f"| {row['dataset']} | {row['split']} | "
                f"{row['sentences']:,} | "
                + " | ".join(f"{row[round_name]:.2f}" for round_name in rounds)
                + " |"
            )
        matrix_markdown.append("")
        (output_root / f"{stem}.md").write_text(
            "\n".join(matrix_markdown), encoding="utf-8"
        )


def main() -> None:
    available_specs = load_specs()
    choices = [spec.dataset for spec in available_specs]
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", nargs="+", choices=choices, default=choices)
    parser.add_argument("--rounds", nargs="+", choices=ROUNDS, default=list(ROUNDS))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--baseline-root",
        type=Path,
        default=DEFAULT_BASELINE_ROOT,
        help="ChERRANT M2 root generated from the same model outputs",
    )
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--wb-repo", type=Path, default=DEFAULT_WB_REPO)
    parser.add_argument("--shape-table", type=Path, default=DEFAULT_SHAPE_TABLE)
    parser.add_argument("--threshold", type=float, default=0.85)
    parser.add_argument(
        "--l-max-char",
        type=int,
        default=DEFAULT_L_MAX_CHAR,
        help="Maximum character envelope serialized as one conventional W",
    )
    parser.add_argument("--bert-model", default="bert-base-chinese")
    parser.add_argument(
        "--target-normalization",
        choices=("t2s", "none"),
        default="none",
        help="Target normalization; final paper protocol uses none (BOM/whitespace only)",
    )
    parser.add_argument("--embedding-cache-size", type=int, default=64)
    parser.add_argument("--embedding-batch-size", type=int, default=32)
    parser.add_argument("--alignment-batch-rows", type=int, default=32)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--force-alignments", action="store_true")
    parser.add_argument(
        "--legacy-cache",
        type=Path,
        default=ROOT / "runs/projection_character_m2_eval/alignment_cache.sqlite3",
        help="Optional v1 cache whose alignments can be relabeled without BERT",
    )
    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit must be non-negative")
    if args.progress_every < 1:
        parser.error("--progress-every must be at least 1")
    if args.embedding_batch_size < 1:
        parser.error("--embedding-batch-size must be at least 1")
    if args.alignment_batch_rows < 1:
        parser.error("--alignment-batch-rows must be at least 1")

    args.output_root = args.output_root.resolve()
    args.baseline_root = args.baseline_root.resolve()
    if args.l_max_char < 2:
        parser.error("--l-max-char must be at least 2")
    if not args.python.exists():
        parser.error(f"Python interpreter does not exist: {args.python}")

    selected = [
        spec for spec in available_specs if spec.dataset in args.datasets
    ]
    normalize_target = load_target_normalizer(args.target_normalization)
    args.output_root.mkdir(parents=True, exist_ok=True)
    cache_config = {
        "implementation": IMPLEMENTATION_VERSION,
        "wb_repo": str(args.wb_repo.resolve()),
        "shape_table": str(args.shape_table.resolve()),
        "threshold": args.threshold,
        "bert_model": args.bert_model,
        "normalization": "remove_all_whitespace",
        "bpe": False,
        "l_max_char": args.l_max_char,
    }
    cache = PairCache(args.output_root / "alignment_cache.sqlite3", cache_config)
    migration_stats = (
        {"read": 0, "migrated": 0, "already_present": 0}
        if args.force_alignments
        else migrate_legacy_cache(
            args.legacy_cache, cache, l_max_char=args.l_max_char
        )
    )
    if migration_stats["read"]:
        print(f"Legacy alignment cache: {migration_stats}", flush=True)
    converter = CachedConverter(
        cache,
        lambda: TwoStepCharacterAligner(
            wb_repo=args.wb_repo,
            shape_table=args.shape_table,
            threshold=args.threshold,
            bert_model=args.bert_model,
            embedding_cache_size=args.embedding_cache_size,
            l_max_char=args.l_max_char,
        ),
        force=args.force_alignments,
    )

    all_scores: list[dict[str, Any]] = []
    completed_specs: list[DatasetSpec] = []
    try:
        for spec in selected:
            output_dir = args.output_root / spec.dataset / spec.split / "char"
            print(
                f"[{spec.dataset}] generating projection-based M2",
                flush=True,
            )
            projection_paths, stats = generate_dataset_m2(
                spec,
                output_dir,
                converter,
                rounds=args.rounds,
                limit=args.limit,
                progress_every=args.progress_every,
                alignment_batch_rows=args.alignment_batch_rows,
                embedding_batch_size=args.embedding_batch_size,
                normalize_target=normalize_target,
            )
            row_count = int(stats["sentences"])
            score_rows = evaluate_dataset(
                spec,
                output_dir,
                projection_paths,
                baseline_root=args.baseline_root,
                rounds=args.rounds,
                python=args.python,
                row_count=row_count,
                is_limited=bool(args.limit and args.limit < spec.rows),
            )
            write_dataset_outputs(output_dir, score_rows, stats)
            all_scores.extend(score_rows)
            completed_specs.append(spec)
            print(f"[{spec.dataset}] evaluation complete", flush=True)
    finally:
        cache_entries = cache.entry_count()
        cache.close()

    if not all_scores:
        raise RuntimeError("No scores were produced")
    write_global_outputs(
        args.output_root, all_scores, completed_specs, args.rounds
    )
    (args.output_root / "run_config.json").write_text(
        json.dumps(
            {
                "completed_utc": datetime.now(timezone.utc).isoformat(),
                "datasets": [spec.dataset for spec in completed_specs],
                "rounds": list(args.rounds),
                "limit": args.limit or None,
                "character_granularity": True,
                "bpe": False,
                "all_gold_references": True,
                "target_normalization": args.target_normalization,
                "source_normalization": "remove_all_whitespace_only",
                "m2_target_lines": False,
                "edit_types": ["M", "R", "U", "W"],
                "long_distance_word_order": {
                    "representation": "linked U--M scored once as W-LD",
                    "l_max_char": args.l_max_char,
                    "matching": "origin + destination + moved material + unit",
                },
                "betas": list(BETAS),
                "embedding_batch_size": args.embedding_batch_size,
                "alignment_batch_rows": args.alignment_batch_rows,
                "alignment": cache_config,
                "python": str(args.python),
                "comparator": "scripts/movement_aware_compare.py",
                "cherrant_baseline_root": str(args.baseline_root),
                "cache_hits": converter.cache_hits,
                "cache_misses": converter.cache_misses,
                "cache_entries": cache_entries,
                "legacy_cache_migration": migration_stats,
                "provenance": {
                    "wb_module_sha256": file_sha256(
                        args.wb_repo
                        / "src/pipeline/alignment/"
                        "step2_similarity_alignment_projection.py"
                    ),
                    "shape_table_sha256": file_sha256(args.shape_table),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(args.output_root / "scores.f05_comparison.md")


if __name__ == "__main__":
    main()
