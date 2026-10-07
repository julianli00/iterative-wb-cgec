#!/usr/bin/env python3
"""Extract tokenized M2 references and generate language-independent MRU/W M2."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
import sqlite3
import tempfile
import time
import unicodedata
from typing import Any, Iterable, Iterator, Sequence

if __package__:
    from .movement_aware_compare import parse_block as parse_scoring_block, scored_edits
    from .punctuation_m2 import EDIT_POLICY, mixes_punctuation_and_words
    from .projection_word_m2 import WordEdit, apply_word_edits
    from .tokenized_m2 import TokenizedRecord, iter_m2, iter_m2_blocks, iter_pairs_jsonl, read_records
    from .transformer_token_alignment import (
        DEFAULT_MODEL, IMPLEMENTATION_VERSION, TokenAlignment,
        TransformerTokenAligner, TransformerTokenEncoder, generic_edits,
    )
else:
    from movement_aware_compare import parse_block as parse_scoring_block, scored_edits
    from punctuation_m2 import EDIT_POLICY, mixes_punctuation_and_words
    from projection_word_m2 import WordEdit, apply_word_edits
    from tokenized_m2 import TokenizedRecord, iter_m2, iter_m2_blocks, iter_pairs_jsonl, read_records
    from transformer_token_alignment import (
        DEFAULT_MODEL, IMPLEMENTATION_VERSION, TokenAlignment,
        TransformerTokenAligner, TransformerTokenEncoder, generic_edits,
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pair_key(source: Sequence[str], target: Sequence[str]) -> str:
    payload = json.dumps([list(source), list(target)], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def output_paths(input_path: Path, output_dir: Path, *, annotated: bool) -> dict[str, Path]:
    stem = input_path.stem.removesuffix(".pairs")
    paths = {
        "pairs": output_dir / f"{stem}.pairs.jsonl",
        "tsv": output_dir / f"{stem}.pairs.tsv",
        "audit": output_dir / f"{stem}.audit.json",
    }
    if annotated:
        paths["m2"] = output_dir / f"{stem}.generic.m2"
        paths["alignment"] = output_dir / f"{stem}.alignments.jsonl"
    return paths


def validate_output_paths(inputs: Sequence[Path], outputs: Sequence[Path]) -> None:
    """Protect every batch input, including aliases, before opening any output."""

    def aliases(left: Path, right: Path) -> bool:
        # Conservative portable names also catch collisions before files exist on macOS/Windows.
        left_name = unicodedata.normalize("NFC", str(left.resolve())).casefold()
        right_name = unicodedata.normalize("NFC", str(right.resolve())).casefold()
        return left_name == right_name or (
            left.exists() and right.exists() and left.samefile(right)
        )

    for index, path in enumerate(outputs):
        if any(aliases(path, source) for source in inputs):
            raise ValueError(f"Output path aliases a protected input: {path}")
        if any(aliases(path, previous) for previous in outputs[:index]):
            raise ValueError(f"Output paths overlap: {path}")
        if path.exists() and not path.is_file():
            raise ValueError(f"Output path is not a regular file: {path}")


class PairCache:
    def __init__(self, path: Path, config: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS config (value TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS pairs (key TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        expected = json.dumps(config, ensure_ascii=False, sort_keys=True)
        existing = self.connection.execute("SELECT value FROM config").fetchall()
        if existing and existing != [(expected,)]:
            self.connection.close()
            raise ValueError("Alignment cache configuration differs; use a new cache path")
        if not existing:
            self.connection.execute("INSERT INTO config VALUES (?)", (expected,))
        self.connection.commit()

    def get(self, source: Sequence[str], target: Sequence[str]) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT payload FROM pairs WHERE key = ?", (pair_key(source, target),)
        ).fetchone()
        return None if row is None else json.loads(row[0])

    def put(self, source: Sequence[str], target: Sequence[str], payload: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT INTO pairs VALUES (?, ?)",
            (pair_key(source, target), json.dumps(payload, ensure_ascii=False)),
        )

    def commit(self) -> None:
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


class FrozenAlignmentAligner:
    """Rebuild edits from a read-only alignment snapshot, never from its old edit labels."""

    def __init__(self, path: Path, *, l_max: int = 3) -> None:
        if l_max < 2:
            raise ValueError("Word-order envelope limit must be at least two")
        self.path = path.resolve(strict=True)
        self.source_sha256 = file_sha256(self.path)
        self.connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        self.closed = False
        self.l_max = l_max
        self.reused = 0
        try:
            rows = self.connection.execute("SELECT value FROM config").fetchall()
            if len(rows) != 1:
                raise ValueError("Frozen alignment cache must contain exactly one configuration")
            config = json.loads(rows[0][0])
            if (
                not isinstance(config, dict)
                or config.get("implementation") not in {"generic-token-mruw-v1", IMPLEMENTATION_VERSION}
                or not isinstance(config.get("encoder"), dict)
                or config.get("exact_alignment") != "LCS, deletion-first ties"
                or config.get("residual_alignment") != "monotonic maximum sum of cosine-minus-threshold within exact-anchor gaps"
            ):
                raise ValueError("Unsupported frozen alignment cache format")
            threshold = config.get("similarity_threshold")
            if type(threshold) not in (int, float) or not math.isfinite(threshold) or not -1 <= threshold < 1:
                raise ValueError("Frozen cache has an invalid similarity threshold")
            self.threshold = threshold
            self.metadata = {
                **config,
                "implementation": IMPLEMENTATION_VERSION,
                "edit_policy": EDIT_POLICY,
                "edit_refinement": "separate standalone Unicode punctuation/symbol tokens from words in every source/correction span",
                "l_max_tokens": l_max,
                "frozen_alignment_cache_sha256": self.source_sha256,
                "frozen_alignment_source_implementation": config["implementation"],
                "transformer_reexecuted": False,
            }
        except (ValueError, TypeError, sqlite3.Error):
            self.connection.close()
            raise

    def convert_many(
        self, pairs: Sequence[tuple[Sequence[str], Sequence[str]]], *, batch_size: int = 16
    ) -> list[tuple[list[WordEdit], TokenAlignment]]:
        if batch_size < 1:
            raise ValueError("Batch size must be positive")
        results = []
        for source, target in pairs:
            row = self.connection.execute(
                "SELECT payload FROM pairs WHERE key = ?", (pair_key(source, target),)
            ).fetchone()
            if row is None:
                raise ValueError("Pair is missing from the frozen alignment cache; no inference fallback is allowed")
            payload = json.loads(row[0])
            if not isinstance(payload, dict) or "alignment" not in payload:
                raise ValueError("Cached pair has no reusable alignment")
            alignment = TokenAlignment.from_json(payload["alignment"])
            if any(score <= self.threshold for score in alignment.cosine_scores.values()):
                raise ValueError("Frozen similarity link does not exceed its recorded threshold")
            results.append((generic_edits(source, target, alignment, l_max=self.l_max), alignment))
            self.reused += 1
        return results

    def close(self) -> None:
        if self.closed:
            return
        self.connection.close()
        self.closed = True
        if file_sha256(self.path) != self.source_sha256:
            raise ValueError("Frozen input alignment cache changed during relabeling")


def decode_edits(payload: dict[str, Any]) -> list[WordEdit]:
    return [
        WordEdit(**{**record, "correction": tuple(record["correction"])})
        for record in payload["edits"]
    ]


def render_record(record: TokenizedRecord, edits_by_reference: Sequence[Sequence[WordEdit]]) -> str:
    record.validate()
    if len(edits_by_reference) != len(record.references):
        raise ValueError(f"{record.identifier}: generated reference count mismatch")
    lines = ["S " + " ".join(record.source_tokens)]
    for reference, edits in zip(record.references, edits_by_reference):
        if apply_word_edits(record.source_tokens, edits) != reference.target_tokens:
            raise ValueError(f"{record.identifier}: generated reference does not reconstruct target")
        if edits:
            for edit in edits:
                correction = " ".join(edit.correction)
                if correction.startswith("|") or correction.endswith("|"):
                    # Padding prevents a literal pipe from joining an M2 field delimiter.
                    line = (
                        f"A {edit.source_start} {edit.source_end}|||{edit.edit_type}||| "
                        f"{correction} |||-REQUIRED-|||{edit.comment}|||{reference.annotator_id}"
                    )
                else:
                    line = edit.m2_line(reference.annotator_id)
                lines.append(line)
        else:
            lines.append(
                "A -1 -1|||noop|||-NONE-|||REQUIRED|||-NONE-|||"
                f"{reference.annotator_id}"
            )
    return "\n".join(lines)


def audit_generated(
    m2: Path, pairs: Path, *, require_separate_punctuation: bool = False
) -> dict[str, Any]:
    """Independently reconstruct serialized offsets and validate linked scoring."""

    counts: Counter[str] = Counter()
    labels: Counter[str] = Counter()
    logical: Counter[str] = Counter()
    mixed_edits = 0
    iterator = itertools.zip_longest(iter_pairs_jsonl(pairs), iter_m2(m2), iter_m2_blocks(m2))
    for expected, actual, block in iterator:
        if expected is None or actual is None or block is None:
            raise ValueError("Generated M2 and extracted pairs have different record counts")
        if expected.source_tokens != actual.source_tokens:
            raise ValueError(f"{m2}: source tokens changed in block {actual.identifier}")
        expected_refs = [(ref.annotator_id, ref.target_tokens) for ref in expected.references]
        actual_refs = [(ref.annotator_id, ref.target_tokens) for ref in actual.references]
        if expected_refs != actual_refs:
            raise ValueError(f"{m2}: target/reference identity or order changed in block {actual.identifier}")
        raw = "\n".join(block[2])
        parsed = parse_scoring_block(raw, unit="word")
        for edit in parsed.edits:
            if edit.edit_type not in {"M", "R", "U", "W", "noop"}:
                raise ValueError(f"{m2}: non-generic operation {edit.edit_type!r}")
            material = edit.correction if isinstance(edit.correction, tuple) else ()
            if mixes_punctuation_and_words(
                (*parsed.source_units[edit.source_start:edit.source_end], *material)
            ):
                mixed_edits += 1
                if require_separate_punctuation:
                    raise ValueError(f"{m2}: an edit mixes punctuation and lexical tokens")
            width = edit.source_end - edit.source_start
            if (
                (edit.edit_type == "M" and (width != 0 or not material))
                or (edit.edit_type == "U" and (width <= 0 or material))
                or (edit.edit_type in {"R", "W"} and (width <= 0 or not material))
            ):
                raise ValueError(f"{m2}: invalid generic {edit.edit_type} span/correction")
            labels[edit.edit_type] += 1
            if edit.edit_type == "W":
                source_span = parsed.source_units[edit.source_start:edit.source_end]
                if (
                    not isinstance(edit.correction, tuple)
                    or source_span == edit.correction
                    or Counter(source_span) != Counter(edit.correction)
                ):
                    raise ValueError(f"{m2}: W is not an exact token permutation")
        scored = scored_edits(parsed, unit="word")
        if list(scored) != [ref.annotator_id for ref in expected.references]:
            raise ValueError(f"{m2}: scorer lost annotator identity/order")
        for edits in scored.values():
            for categories in edits.values():
                logical.update("WO" if category == "W-LD" else category for category in categories if category != "noop")
        counts["sources"] += 1
        counts["references"] += len(expected.references)
        counts["source_tokens"] += len(expected.source_tokens)
        counts["target_tokens"] += sum(len(ref.target_tokens) for ref in expected.references)
    if counts["sources"] == 0:
        raise ValueError("Cannot audit an empty corpus: no M2/pair records were found")
    return {
        "status": "PASS",
        **dict(counts),
        "physical_annotations": dict(sorted(labels.items())),
        "logical_operations": dict(sorted(logical.items())),
        "source_tokens_unchanged": True,
        "target_tokens_and_reference_ids_order_unchanged": True,
        "linked_movements_validated_and_scored_once": True,
        "mixed_punctuation_lexical_edits": mixed_edits,
        "punctuation_separation_required": require_separate_punctuation,
        "pairs_sha256": file_sha256(pairs),
        "generic_m2_sha256": file_sha256(m2),
    }


def _batches(records: Iterable[TokenizedRecord], size: int) -> Iterator[list[TokenizedRecord]]:
    iterator = iter(records)
    while batch := list(itertools.islice(iterator, size)):
        yield batch


def convert_file(
    input_path: Path,
    *,
    input_format: str,
    output_dir: Path,
    aligner: TransformerTokenAligner | FrozenAlignmentAligner | None = None,
    cache: PairCache | None = None,
    batch_size: int = 16,
    overwrite: bool = False,
) -> dict[str, Any]:
    if batch_size < 1:
        raise ValueError("Batch size must be positive")
    if (aligner is None) != (cache is None):
        raise ValueError("Alignment and cache must either both be present or both be absent")
    input_path = input_path.resolve(strict=True)
    output_dir = output_dir.resolve()
    stem = input_path.stem.removesuffix(".pairs")
    paths = output_paths(input_path, output_dir, annotated=aligner is not None)
    validate_output_paths([input_path], list(paths.values()))
    audit_path = paths.pop("audit")
    for path in [*paths.values(), audit_path]:
        if path.exists() and not overwrite:
            raise FileExistsError(f"Output already exists: {path}; use --overwrite intentionally")
    output_dir.mkdir(parents=True, exist_ok=True)
    before_hash = file_sha256(input_path)
    started = time.monotonic()
    temporary: dict[str, Path] = {}
    counts: Counter[str] = Counter()
    skipped: Counter[str] = Counter()
    try:
        with ExitStack() as stack:
            streams = {}
            for kind in paths:
                stream = stack.enter_context(tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", newline="", dir=output_dir,
                    prefix=f".{stem}.{kind}.", suffix=".partial", delete=False,
                ))
                streams[kind] = stream
                temporary[kind] = Path(stream.name)
            import csv

            tsv_writer = csv.writer(streams["tsv"], delimiter="\t", lineterminator="\n")
            for batch in _batches(read_records(input_path, input_format), batch_size):
                payloads: dict[str, dict[str, Any]] = {}
                missing: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
                if aligner is not None:
                    assert cache is not None
                    for record in batch:
                        for reference in record.references:
                            key = pair_key(record.source_tokens, reference.target_tokens)
                            if key in payloads or key in missing:
                                counts["reused_pairs"] += 1
                                continue
                            payload = cache.get(record.source_tokens, reference.target_tokens)
                            if payload is None:
                                missing[key] = record.source_tokens, reference.target_tokens
                            else:
                                payloads[key] = payload
                                counts["reused_pairs"] += 1
                    converted = aligner.convert_many(list(missing.values()), batch_size=batch_size)
                    if len(converted) != len(missing):
                        raise ValueError("Transformer alignment returned an incomplete batch")
                    for (key, pair), (edits, alignment) in zip(missing.items(), converted):
                        payload = {"edits": [asdict(edit) for edit in edits], "alignment": alignment.to_json()}
                        cache.put(*pair, payload)
                        payloads[key] = payload
                        counts["new_pairs"] += 1
                    cache.commit()
                for record in batch:
                    record.validate()
                    counts["sources"] += 1
                    counts["references"] += len(record.references)
                    counts["source_tokens"] += len(record.source_tokens)
                    counts["target_tokens"] += sum(len(ref.target_tokens) for ref in record.references)
                    skipped.update(
                        annotation.label for ref in record.references for annotation in ref.skipped_annotations
                    )
                    streams["pairs"].write(json.dumps(record.to_json(), ensure_ascii=False) + "\n")
                    tsv_writer.writerow([
                        " ".join(record.source_tokens),
                        *(" ".join(ref.target_tokens) for ref in record.references),
                    ])
                    if aligner is not None:
                        all_edits = []
                        for reference in record.references:
                            payload = payloads[pair_key(record.source_tokens, reference.target_tokens)]
                            all_edits.append(decode_edits(payload))
                            streams["alignment"].write(json.dumps({
                                "id": record.identifier,
                                "annotator_id": reference.annotator_id,
                                **payload["alignment"],
                            }) + "\n")
                            counts["exact_anchors"] += len(payload["alignment"]["exact"])
                            counts["similarity_anchors"] += len(payload["alignment"]["similarity"])
                        streams["m2"].write(render_record(record, all_edits) + "\n\n")
                if counts["sources"] % 1000 < len(batch):
                    print(f"[{input_path.name}] {counts['sources']:,} sources; {counts['new_pairs']:,} new pair annotations", flush=True)
        if counts["sources"] == 0:
            raise ValueError(f"No source records in {input_path}")
        after_hash = file_sha256(input_path)
        if before_hash != after_hash:
            raise ValueError(f"Input changed during conversion: {input_path}")
        audit = (
            audit_generated(temporary["m2"], temporary["pairs"], require_separate_punctuation=True)
            if aligner is not None else {"status": "PASS"}
        )
        for kind, path in paths.items():
            temporary[kind].replace(path)
        report = {
            "input": str(input_path),
            "input_format": input_format,
            "input_sha256_before": before_hash,
            "input_sha256_after": after_hash,
            "counts": dict(counts),
            "skipped_noncorrection_annotations": dict(sorted(skipped.items())),
            "outputs": {kind: str(path) for kind, path in paths.items()},
            "validation": audit,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "new_llm_calls": 0,
        }
        audit_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[{input_path.name}] complete: {counts['sources']:,} sources, {counts['references']:,} references", flush=True)
        return report
    finally:
        for path in temporary.values():
            if path.exists():
                path.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("extract", "generate", "relabel"):
        command = commands.add_parser(name)
        command.add_argument("inputs", type=Path, nargs="+")
        command.add_argument("--output-dir", required=True, type=Path)
        command.add_argument("--input-format", choices=("m2", "jsonl", "tsv"), default="m2")
        command.add_argument("--batch-size", type=int, default=16)
        command.add_argument("--overwrite", action="store_true")
        if name == "generate":
            command.add_argument("--model", default=DEFAULT_MODEL)
            command.add_argument("--revision")
            command.add_argument("--device", default="cpu")
            command.add_argument("--allow-download", action="store_true")
            command.add_argument("--similarity-threshold", type=float, default=0.60)
            command.add_argument("--l-max", type=int, default=3)
            command.add_argument("--cache", type=Path)
            command.add_argument("--torch-threads", type=int, default=4)
        elif name == "relabel":
            command.add_argument("--alignment-cache", type=Path, required=True)
            command.add_argument("--l-max", type=int, default=3)
            command.add_argument("--cache", type=Path)
    audit = commands.add_parser("audit")
    audit.add_argument("--m2", required=True, type=Path)
    audit.add_argument("--pairs", required=True, type=Path)
    audit.add_argument("--output", type=Path)
    audit.add_argument("--require-separate-punctuation", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "audit":
        if args.output is not None:
            validate_output_paths([args.m2, args.pairs], [args.output])
        report = audit_generated(
            args.m2, args.pairs, require_separate_punctuation=args.require_separate_punctuation
        )
        content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output is not None:
            args.output.write_text(content, encoding="utf-8")
        print(content)
        return
    if args.batch_size < 1:
        raise ValueError("Batch size must be positive")
    for path in args.inputs:
        if not path.is_file():
            raise FileNotFoundError(path)
    args.inputs = [path.resolve(strict=True) for path in args.inputs]
    stems = [path.stem.removesuffix(".pairs") for path in args.inputs]
    if len(stems) != len(set(stems)):
        raise ValueError("Input basenames collide; use separate output directories")
    config_path = args.output_dir / "run_config.json"
    annotated = args.command != "extract"
    planned = [config_path, *(
        destination
        for path in args.inputs
        for destination in output_paths(path, args.output_dir, annotated=annotated).values()
    )]
    protected = list(args.inputs)
    if args.command == "relabel":
        protected.append(args.alignment_cache)
    output_cache = (args.cache or args.output_dir / "alignment_cache.sqlite3") if annotated else None
    validate_output_paths(protected, planned + ([output_cache] if output_cache is not None else []))
    if not args.overwrite:
        for path in planned:
            if path.exists():
                raise FileExistsError(f"Output already exists: {path}; choose a new directory or --overwrite")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    aligner = None
    cache = None
    if args.command == "relabel":
        assert output_cache is not None
        aligner = FrozenAlignmentAligner(args.alignment_cache, l_max=args.l_max)
        try:
            cache = PairCache(output_cache, aligner.metadata)
        except (ValueError, OSError, sqlite3.Error):
            aligner.close()
            raise
    if args.command == "generate":
        encoder = TransformerTokenEncoder(
            args.model, revision=args.revision, device=args.device,
            allow_download=args.allow_download, threads=args.torch_threads,
        )
        aligner = TransformerTokenAligner(encoder, threshold=args.similarity_threshold, l_max=args.l_max)
        assert output_cache is not None
        cache = PairCache(output_cache, aligner.metadata)
    config: dict[str, Any] = {
        "status": "running",
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "operation": args.command,
        "input_format": args.input_format,
        "batch_size": args.batch_size,
        "inputs": [str(path.resolve()) for path in args.inputs],
        "alignment": aligner.metadata if aligner is not None else None,
        "edit_policy": EDIT_POLICY if aligner is not None else None,
        "tokenization": "supplied tokens preserved without resegmentation, case conversion, or OpenCC; internal Transformer subwords are not M2 offset units",
        "extraction": "original source offsets; references and annotator order retained; noop/UNK/Um preserved as skipped metadata",
        "new_llm_calls": 0,
        "files": [],
    }
    try:
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for path in args.inputs:
            config["files"].append(convert_file(
                path, input_format=args.input_format, output_dir=args.output_dir,
                aligner=aligner, cache=cache, batch_size=args.batch_size, overwrite=args.overwrite,
            ))
            config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if isinstance(aligner, FrozenAlignmentAligner):
            config["transformer_inference"] = {
                "encoded_sentences": 0,
                "encoded_windows": 0,
                "reused_alignment_records": aligner.reused,
            }
            aligner.close()
        elif aligner is not None:
            config["transformer_inference"] = dict(aligner.encoder.stats)
        config["status"] = "completed"
        config["completed_utc"] = datetime.now(timezone.utc).isoformat()
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
        config["status"] = "failed"
        config["error"] = f"{type(exc).__name__}: {exc}"
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise
    finally:
        if cache is not None:
            cache.close()
        if isinstance(aligner, FrozenAlignmentAligner):
            aligner.close()


if __name__ == "__main__":
    main()
