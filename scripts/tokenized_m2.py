"""Lossless token-sequence extraction from standard, possibly multi-reference M2."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence


NON_CORRECTION_TYPES = frozenset({"noop", "UNK", "Um"})


def validate_tokens(tokens: Sequence[str], *, context: str) -> tuple[str, ...]:
    if isinstance(tokens, str):
        raise ValueError(f"{context}: expected a token sequence, not an unsegmented string")
    result = tuple(tokens)
    for index, token in enumerate(result):
        if not isinstance(token, str) or not token:
            raise ValueError(f"{context}: token {index} must be a non-empty string")
        if any(character.isspace() for character in token) or "|||" in token:
            raise ValueError(f"{context}: token {index} contains whitespace or the M2 field delimiter")
    return result


@dataclass(frozen=True)
class Annotation:
    start: int
    end: int
    label: str
    correction: tuple[str, ...]
    required: str
    comment: str
    annotator_id: int


@dataclass(frozen=True)
class Reference:
    annotator_id: int
    target_tokens: tuple[str, ...]
    skipped_annotations: tuple[Annotation, ...] = ()


@dataclass(frozen=True)
class TokenizedRecord:
    identifier: str
    source_tokens: tuple[str, ...]
    references: tuple[Reference, ...]

    def validate(self) -> None:
        if not isinstance(self.identifier, str) or not self.identifier:
            raise ValueError("A non-empty record identifier is required")
        validate_tokens(self.source_tokens, context=f"{self.identifier}/source")
        if not self.references:
            raise ValueError(f"{self.identifier}: at least one complete reference is required")
        ids: set[int] = set()
        for reference in self.references:
            if type(reference.annotator_id) is not int or reference.annotator_id < 0:
                raise ValueError(f"{self.identifier}: annotator IDs must be nonnegative integers")
            if reference.annotator_id in ids:
                raise ValueError(f"{self.identifier}: duplicate annotator ID {reference.annotator_id}")
            ids.add(reference.annotator_id)
            validate_tokens(reference.target_tokens, context=f"{self.identifier}/reference")
            for annotation in reference.skipped_annotations:
                if (
                    annotation.label not in NON_CORRECTION_TYPES
                    or annotation.annotator_id != reference.annotator_id
                    or type(annotation.start) is not int
                    or type(annotation.end) is not int
                    or annotation.required not in {"REQUIRED", "-REQUIRED-"}
                    or not isinstance(annotation.comment, str)
                ):
                    raise ValueError(f"{self.identifier}: invalid skipped annotation metadata")
                if (annotation.start, annotation.end) != (-1, -1) and not (
                    0 <= annotation.start <= annotation.end <= len(self.source_tokens)
                ):
                    raise ValueError(f"{self.identifier}: skipped annotation has invalid offsets")
                if annotation.label == "noop" and (
                    (annotation.start, annotation.end) != (-1, -1) or annotation.correction
                ):
                    raise ValueError(f"{self.identifier}: invalid noop metadata")
                validate_tokens(annotation.correction, context=f"{self.identifier}/skipped annotation")

    def to_json(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.identifier,
            "source_tokens": list(self.source_tokens),
            "references": [
                {
                    "annotator_id": reference.annotator_id,
                    "target_tokens": list(reference.target_tokens),
                    "skipped_annotations": [
                        asdict(annotation) for annotation in reference.skipped_annotations
                    ],
                }
                for reference in self.references
            ],
        }


def _annotation(line: str, source_size: int, *, context: str) -> Annotation:
    fields = line[2:].split("|||")
    if len(fields) != 6:
        raise ValueError(f"{context}: an A record must contain exactly six fields")
    span = fields[0].split()
    if len(span) != 2:
        raise ValueError(f"{context}: expected two source token offsets")
    try:
        start, end = map(int, span)
        annotator = int(fields[5])
    except ValueError as exc:
        raise ValueError(f"{context}: invalid integer offset or annotator ID") from exc
    label = fields[1].strip()
    if not label or annotator < 0:
        raise ValueError(f"{context}: empty annotation label or negative annotator ID")
    if fields[3] not in {"REQUIRED", "-REQUIRED-"}:
        raise ValueError(f"{context}: unsupported annotation requirement {fields[3]!r}")
    if (start, end) == (-1, -1):
        if label not in NON_CORRECTION_TYPES:
            raise ValueError(f"{context}: only non-correction records may use -1 -1")
    elif not (0 <= start <= end <= source_size) or label == "noop":
        raise ValueError(f"{context}: invalid source token span for {label}")
    correction = () if fields[2] in {"", "-NONE-"} else tuple(fields[2].split())
    validate_tokens(correction, context=context)
    if label == "noop" and correction:
        raise ValueError(f"{context}: noop must not supply correction material")
    return Annotation(start, end, label, correction, fields[3], fields[4], annotator)


def apply_annotations(
    source: Sequence[str], annotations: Sequence[Annotation], *, context: str
) -> tuple[str, ...]:
    """Apply replacements at original offsets; equal-position insertions keep file order."""

    tokens = tuple(source)
    active = [annotation for annotation in annotations if annotation.label not in NON_CORRECTION_TYPES]
    if any(annotation.label == "noop" for annotation in annotations) and active:
        raise ValueError(f"{context}: noop is mixed with actual corrections for one annotator")
    output: list[str] = []
    cursor = 0
    for annotation in sorted(active, key=lambda item: (item.start, item.end)):
        if not 0 <= annotation.start <= annotation.end <= len(tokens):
            raise ValueError(f"{context}: correction span is outside the source")
        if annotation.start < cursor:
            raise ValueError(f"{context}: overlapping corrections for the same annotator")
        output.extend(tokens[cursor:annotation.start])
        output.extend(annotation.correction)
        cursor = annotation.end
    output.extend(tokens[cursor:])
    return tuple(output)


def parse_m2_block(
    lines: Sequence[str], *, identifier: str, context: str
) -> TokenizedRecord:
    if not lines or not (lines[0] == "S" or lines[0].startswith("S ")):
        raise ValueError(f"{context}: block must begin with an S record")
    source = validate_tokens(tuple(lines[0][2:].split()), context=context)
    grouped: dict[int, list[Annotation]] = {}
    for index, line in enumerate(lines[1:], start=2):
        if not line.startswith("A "):
            raise ValueError(f"{context}, block line {index}: expected an A record")
        annotation = _annotation(line, len(source), context=f"{context}, block line {index}")
        grouped.setdefault(annotation.annotator_id, []).append(annotation)
    if not grouped:
        grouped[0] = []
    references = tuple(
        Reference(
            annotator_id,
            apply_annotations(source, annotations, context=f"{context}/annotator {annotator_id}"),
            tuple(annotation for annotation in annotations if annotation.label in NON_CORRECTION_TYPES),
        )
        for annotator_id, annotations in grouped.items()
    )
    record = TokenizedRecord(identifier, source, references)
    record.validate()
    return record


def iter_m2_blocks(path: Path) -> Iterator[tuple[int, int, list[str]]]:
    block: list[str] = []
    block_number = 0
    start_line = 1
    with path.open(encoding="utf-8-sig") as stream:
        for line_number, raw in enumerate(stream, start=1):
            line = raw.rstrip("\r\n")
            if not line.strip():
                if block:
                    block_number += 1
                    yield block_number, start_line, block
                    block = []
                continue
            if not block:
                start_line = line_number
            block.append(line)
    if block:
        block_number += 1
        yield block_number, start_line, block


def iter_m2(path: Path) -> Iterator[TokenizedRecord]:
    for block_number, start_line, block in iter_m2_blocks(path):
        yield parse_m2_block(
            block, identifier=str(block_number),
            context=f"{path}:{start_line}/block {block_number}",
        )


def iter_pairs_jsonl(path: Path) -> Iterator[TokenizedRecord]:
    seen_ids: set[str] = set()
    with path.open(encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            context = f"{path}:{line_number}"
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{context}: invalid JSON") from exc
            if not isinstance(value, dict) or set(value) - {"id", "source_tokens", "references"}:
                raise ValueError(f"{context}: expected id, source_tokens and references")
            source = value.get("source_tokens")
            refs = value.get("references")
            identifier = value.get("id", str(line_number))
            if not isinstance(source, list) or not isinstance(refs, list):
                raise ValueError(f"{context}: source_tokens and references must be arrays")
            references = []
            for ref in refs:
                if not isinstance(ref, dict) or set(ref) - {
                    "annotator_id", "target_tokens", "skipped_annotations"
                }:
                    raise ValueError(f"{context}: invalid reference object")
                target = ref.get("target_tokens")
                if not isinstance(target, list):
                    raise ValueError(f"{context}: target_tokens must be an array")
                skipped = []
                ignored = ref.get("skipped_annotations", [])
                if not isinstance(ignored, list):
                    raise ValueError(f"{context}: skipped_annotations must be an array")
                for item in ignored:
                    if not isinstance(item, dict) or item.get("label") not in NON_CORRECTION_TYPES:
                        raise ValueError(f"{context}: invalid skipped annotation")
                    if not isinstance(item.get("correction"), list):
                        raise ValueError(f"{context}: skipped correction must be a token array")
                    try:
                        skipped.append(Annotation(**{**item, "correction": tuple(item["correction"])}))
                    except (KeyError, TypeError) as exc:
                        raise ValueError(f"{context}: malformed skipped annotation") from exc
                references.append(Reference(ref.get("annotator_id"), tuple(target), tuple(skipped)))
            record = TokenizedRecord(identifier, tuple(source), tuple(references))
            record.validate()
            if record.identifier in seen_ids:
                raise ValueError(f"{context}: duplicate record ID {record.identifier!r}")
            seen_ids.add(record.identifier)
            yield record


def iter_pairs_tsv(path: Path) -> Iterator[TokenizedRecord]:
    """Read headerless source/target[/target...] fields without retokenizing their units."""

    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row_number, row in enumerate(csv.reader(stream, delimiter="\t"), start=1):
            if len(row) < 2:
                raise ValueError(f"{path}:row {row_number}: expected source and at least one target")
            record = TokenizedRecord(
                str(row_number),
                tuple(row[0].split()),
                tuple(Reference(index, tuple(value.split())) for index, value in enumerate(row[1:])),
            )
            record.validate()
            yield record


def read_records(path: Path, input_format: str) -> Iterable[TokenizedRecord]:
    if input_format == "m2":
        return iter_m2(path)
    if input_format == "jsonl":
        return iter_pairs_jsonl(path)
    if input_format == "tsv":
        return iter_pairs_tsv(path)
    raise ValueError(f"Unknown input format: {input_format}")
