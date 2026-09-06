#!/usr/bin/env python3
"""Shared linked-movement metadata and validation for projection M2 files."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Any, Iterable, Mapping, Sequence


NO_CORRECTION = "-NONE-"
DEFAULT_L_MAX_CHAR = 3
DEFAULT_L_MAX_WORD = 3

_LINK_RE = re.compile(r"w[1-9][0-9]*\Z")
_INTEGER_RE = re.compile(r"0|[1-9][0-9]*\Z")
_FROM_RE = re.compile(r"(0|[1-9][0-9]*):(0|[1-9][0-9]*)\Z")
_LINK_KEYS = frozenset({"LINK", "TO", "FROM"})


@dataclass(frozen=True)
class LinkMetadata:
    """Parsed comment metadata for one side of a linked movement."""

    link_id: str
    to: int | None = None
    from_start: int | None = None
    from_end: int | None = None

    @property
    def is_origin(self) -> bool:
        return self.to is not None

    @property
    def is_destination(self) -> bool:
        return self.from_start is not None


@dataclass(frozen=True)
class LinkedMovement:
    """One validated logical movement represented by linked U and M edits."""

    link_id: str
    origin_start: int
    origin_end: int
    destination: int
    material: tuple[str, ...]
    origin_edit: Any
    destination_edit: Any

    @property
    def envelope_start(self) -> int:
        return min(self.origin_start, self.destination)

    @property
    def envelope_end(self) -> int:
        return max(self.origin_end, self.destination)

    @property
    def envelope_length(self) -> int:
        return self.envelope_end - self.envelope_start


def origin_comment(link_id: str, destination: int) -> str:
    _validate_link_id(link_id)
    if destination < 0:
        raise ValueError("Movement destination must be non-negative")
    return f"LINK={link_id};TO={destination}"


def destination_comment(link_id: str, origin_start: int, origin_end: int) -> str:
    _validate_link_id(link_id)
    if origin_start < 0 or origin_end <= origin_start:
        raise ValueError("Movement origin must be a non-empty source interval")
    return f"LINK={link_id};FROM={origin_start}:{origin_end}"


def _validate_link_id(link_id: str) -> None:
    if not _LINK_RE.fullmatch(link_id):
        raise ValueError(f"Invalid movement link identifier: {link_id!r}")


def parse_link_comment(comment: str) -> LinkMetadata | None:
    """Parse a linked comment, rejecting malformed movement metadata.

    Ordinary free-text comments remain untouched. Once a reserved movement key
    occurs, however, the entire comment must follow the declared grammar.
    """

    value = str(comment).strip()
    if value in {"", "NONE", NO_CORRECTION}:
        return None
    parts = value.split(";")
    fields: dict[str, str] = {}
    contains_reserved_key = False
    for part in parts:
        if "=" not in part:
            if any(key in part.upper() for key in _LINK_KEYS):
                contains_reserved_key = True
            continue
        key, field_value = part.split("=", 1)
        key = key.strip().upper()
        if key in _LINK_KEYS:
            contains_reserved_key = True
        if key in fields:
            raise ValueError(f"Duplicate movement metadata key in {comment!r}")
        fields[key] = field_value.strip()

    if not contains_reserved_key:
        return None
    if set(fields) not in ({"LINK", "TO"}, {"LINK", "FROM"}):
        raise ValueError(f"Malformed movement metadata: {comment!r}")
    link_id = fields["LINK"]
    _validate_link_id(link_id)
    if "TO" in fields:
        if not _INTEGER_RE.fullmatch(fields["TO"]):
            raise ValueError(f"Invalid movement destination: {comment!r}")
        return LinkMetadata(link_id=link_id, to=int(fields["TO"]))

    match = _FROM_RE.fullmatch(fields["FROM"])
    if not match:
        raise ValueError(f"Invalid movement origin: {comment!r}")
    start, end = (int(value) for value in match.groups())
    if end <= start:
        raise ValueError(f"Movement origin is empty or reversed: {comment!r}")
    return LinkMetadata(link_id=link_id, from_start=start, from_end=end)


def correction_units(edit: Any) -> tuple[str, ...]:
    correction = edit.correction
    if edit.edit_type == "U" or correction == NO_CORRECTION:
        return ()
    if isinstance(correction, str):
        return tuple(correction)
    return tuple(correction)


def validate_linked_movements(
    source_units: Sequence[str], edits: Sequence[Any]
) -> dict[str, LinkedMovement]:
    """Validate every linked pair and return its logical movement object."""

    source = tuple(source_units)
    grouped: dict[str, list[tuple[Any, LinkMetadata]]] = {}
    for edit in edits:
        metadata = parse_link_comment(getattr(edit, "comment", "NONE"))
        if metadata is not None:
            grouped.setdefault(metadata.link_id, []).append((edit, metadata))

    movements: dict[str, LinkedMovement] = {}
    occupied_origins: list[tuple[int, int, str]] = []
    for link_id, members in grouped.items():
        if len(members) != 2:
            raise ValueError(f"{link_id} must occur exactly twice, found {len(members)}")
        origins = [member for member in members if member[1].is_origin]
        destinations = [member for member in members if member[1].is_destination]
        if len(origins) != 1 or len(destinations) != 1:
            raise ValueError(f"{link_id} must contain one U-TO and one M-FROM record")
        origin_edit, origin_meta = origins[0]
        destination_edit, destination_meta = destinations[0]
        if origin_edit.edit_type != "U":
            raise ValueError(f"{link_id} origin record must have type U")
        if correction_units(origin_edit):
            raise ValueError(f"{link_id} origin U record must delete material")
        if origin_edit.source_start >= origin_edit.source_end:
            raise ValueError(f"{link_id} origin U record must have a non-empty span")
        if destination_edit.edit_type != "M":
            raise ValueError(f"{link_id} destination record must have type M")
        if destination_edit.source_start != destination_edit.source_end:
            raise ValueError(f"{link_id} destination M record must have an empty span")
        if not correction_units(destination_edit):
            raise ValueError(f"{link_id} destination M record must insert material")

        assert origin_meta.to is not None
        assert destination_meta.from_start is not None
        assert destination_meta.from_end is not None
        if origin_meta.to != destination_edit.source_start:
            raise ValueError(f"{link_id} TO coordinate disagrees with the M boundary")
        if (
            destination_meta.from_start != origin_edit.source_start
            or destination_meta.from_end != origin_edit.source_end
        ):
            raise ValueError(f"{link_id} FROM coordinate disagrees with the U span")
        if not (0 <= origin_edit.source_start < origin_edit.source_end <= len(source)):
            raise ValueError(f"{link_id} origin lies outside the source")
        if not (0 <= destination_edit.source_start <= len(source)):
            raise ValueError(f"{link_id} destination lies outside the source")
        if origin_edit.source_start < destination_edit.source_start < origin_edit.source_end:
            raise ValueError(f"{link_id} destination lies inside its origin span")

        material = source[origin_edit.source_start : origin_edit.source_end]
        if material != correction_units(destination_edit):
            raise ValueError(f"{link_id} deleted and inserted material differ")
        for earlier_start, earlier_end, earlier_link in occupied_origins:
            if max(earlier_start, origin_edit.source_start) < min(
                earlier_end, origin_edit.source_end
            ):
                raise ValueError(
                    f"Linked movement origins overlap: {earlier_link} and {link_id}"
                )
        occupied_origins.append(
            (origin_edit.source_start, origin_edit.source_end, link_id)
        )
        movements[link_id] = LinkedMovement(
            link_id=link_id,
            origin_start=origin_edit.source_start,
            origin_end=origin_edit.source_end,
            destination=destination_edit.source_start,
            material=material,
            origin_edit=origin_edit,
            destination_edit=destination_edit,
        )

    _validate_non_overlapping_edits(edits, movements)
    return movements


def _validate_non_overlapping_edits(
    edits: Sequence[Any], movements: Mapping[str, LinkedMovement]
) -> None:
    linked_members = {
        id(movement.origin_edit)
        for movement in movements.values()
    } | {
        id(movement.destination_edit)
        for movement in movements.values()
    }
    occupied: list[tuple[int, int, Any]] = []
    for edit in edits:
        if edit.source_start == edit.source_end:
            continue
        for start, end, earlier in occupied:
            if max(start, edit.source_start) < min(end, edit.source_end):
                if id(edit) in linked_members or id(earlier) in linked_members:
                    raise ValueError("Linked movement overlaps another source edit")
        occupied.append((edit.source_start, edit.source_end, edit))


def renumber_movement_links(
    source_units: Sequence[str], edits: Sequence[Any]
) -> list[Any]:
    """Renumber links by origin and destination for deterministic serialization."""

    movements = validate_linked_movements(source_units, edits)
    ordered = sorted(
        movements.values(),
        key=lambda movement: (
            movement.origin_start,
            movement.origin_end,
            movement.destination,
            movement.link_id,
        ),
    )
    replacement_ids = {
        movement.link_id: f"w{index}"
        for index, movement in enumerate(ordered, start=1)
    }
    output: list[Any] = []
    for edit in edits:
        metadata = parse_link_comment(getattr(edit, "comment", "NONE"))
        if metadata is None:
            output.append(edit)
            continue
        link_id = replacement_ids[metadata.link_id]
        if metadata.is_origin:
            assert metadata.to is not None
            comment = origin_comment(link_id, metadata.to)
        else:
            assert metadata.from_start is not None
            assert metadata.from_end is not None
            comment = destination_comment(
                link_id, metadata.from_start, metadata.from_end
            )
        output.append(replace(edit, comment=comment))
    validate_linked_movements(source_units, output)
    return output


def simultaneous_reconstruction(
    source_units: Sequence[str], edits: Sequence[Any]
) -> tuple[str, ...]:
    """Apply ordinary and linked edits against unchanged original coordinates."""

    source = tuple(source_units)
    validate_linked_movements(source, edits)
    output: list[str] = []
    cursor = 0
    for edit in sorted(
        edits,
        key=lambda item: (
            item.source_start,
            item.source_end,
            0 if item.edit_type == "M" else 1,
        ),
    ):
        if edit.source_start < cursor:
            raise ValueError(f"Overlapping or out-of-order edit: {edit}")
        output.extend(source[cursor : edit.source_start])
        if edit.edit_type == "M":
            if edit.source_start != edit.source_end:
                raise ValueError("M edit must have an empty source span")
            output.extend(correction_units(edit))
            cursor = edit.source_start
        elif edit.edit_type in {"R", "W"}:
            if edit.source_start == edit.source_end:
                raise ValueError(f"{edit.edit_type} edit must have a source span")
            output.extend(correction_units(edit))
            cursor = edit.source_end
        elif edit.edit_type == "U":
            if edit.source_start == edit.source_end or correction_units(edit):
                raise ValueError("U edit must delete a non-empty source span")
            cursor = edit.source_end
        else:
            raise ValueError(f"Unsupported edit type: {edit.edit_type}")
    output.extend(source[cursor:])
    return tuple(output)


def iter_linked_comments(edits: Iterable[Any]) -> Iterable[LinkMetadata]:
    for edit in edits:
        metadata = parse_link_comment(getattr(edit, "comment", "NONE"))
        if metadata is not None:
            yield metadata
