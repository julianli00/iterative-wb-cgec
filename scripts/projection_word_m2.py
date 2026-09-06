#!/usr/bin/env python3
"""Generate coarse word-level M2 edits from WB character projection.

Source and target word boundaries are supplied by the iterative pipeline or
LTP.  Character correspondences come from the same two-step WB aligner used
by the character M2 experiment.  They vote for monotonic token anchors; gaps
between those anchors become M/R/U edits, and permutation spans become W.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Sequence

try:
    from movement_m2 import (
        DEFAULT_L_MAX_WORD,
        destination_comment,
        origin_comment,
        renumber_movement_links,
        simultaneous_reconstruction,
    )
except ModuleNotFoundError:
    from scripts.movement_m2 import (
        DEFAULT_L_MAX_WORD,
        destination_comment,
        origin_comment,
        renumber_movement_links,
        simultaneous_reconstruction,
    )

try:
    from projection_character_m2 import (
        AlignmentResult,
        CharacterEdit,
        NO_CORRECTION,
        apply_edits,
        normalize_text,
    )
except ModuleNotFoundError:  # Imported as ``scripts.projection_word_m2`` in tests.
    from scripts.projection_character_m2 import (
        AlignmentResult,
        CharacterEdit,
        NO_CORRECTION,
        apply_edits,
        normalize_text,
    )


@dataclass(frozen=True)
class WordEdit:
    """One word-indexed edit with target offsets retained for validation."""

    source_start: int
    source_end: int
    target_start: int
    target_end: int
    edit_type: str
    correction: tuple[str, ...]
    comment: str = "NONE"

    def m2_line(self, annotator_id: int) -> str:
        correction = (
            NO_CORRECTION
            if self.edit_type == "U"
            else " ".join(self.correction)
        )
        return (
            f"A {self.source_start} {self.source_end}|||{self.edit_type}|||"
            f"{correction}|||-REQUIRED-|||{self.comment}|||{annotator_id}"
        )


def segmented_tokens(text: str) -> tuple[str, ...]:
    """Parse a whitespace-segmented sentence and reject empty content."""

    tokens = tuple(str(text).replace("\ufeff", "").split())
    if not tokens and normalize_text(text):
        raise ValueError(f"Cannot parse segmented text: {text!r}")
    return tokens


def token_character_spans(tokens: Sequence[str]) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    cursor = 0
    for token in tokens:
        if not token:
            raise ValueError("Word segmentation contains an empty token")
        spans.append((cursor, cursor + len(token)))
        cursor += len(token)
    return tuple(spans)


def character_to_token(tokens: Sequence[str]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for token_index, (start, end) in enumerate(token_character_spans(tokens)):
        for character_index in range(start, end):
            mapping[character_index] = token_index
    return mapping


def _best_weighted_monotonic_pairs(
    weighted_pairs: Mapping[tuple[int, int], int],
) -> list[tuple[int, int]]:
    """Select a deterministic maximum-weight target/source token sequence."""

    ordered = sorted(weighted_pairs)
    if not ordered:
        return []
    paths: list[tuple[int, tuple[tuple[int, int], ...]]] = []
    for index, pair in enumerate(ordered):
        best = (weighted_pairs[pair], (pair,))
        for earlier in range(index):
            previous = ordered[earlier]
            if previous[0] >= pair[0] or previous[1] >= pair[1]:
                continue
            prior_weight, prior_path = paths[earlier]
            candidate = (prior_weight + weighted_pairs[pair], prior_path + (pair,))
            if candidate[0] > best[0] or (
                candidate[0] == best[0]
                and (
                    len(candidate[1]) > len(best[1])
                    or (
                        len(candidate[1]) == len(best[1])
                        and candidate[1] < best[1]
                    )
                )
            ):
                best = candidate
        paths.append(best)
    best_weight, best_path = min(
        paths,
        key=lambda item: (-item[0], -len(item[1]), item[1]),
    )
    del best_weight
    return list(best_path)


def token_alignment_from_character_alignment(
    source_segmented: str,
    target_segmented: str,
    character_alignment: Mapping[int, int] | AlignmentResult,
) -> dict[int, int]:
    """Aggregate projected character pairs into monotonic token anchors."""

    source_tokens = segmented_tokens(source_segmented)
    target_tokens = segmented_tokens(target_segmented)
    if normalize_text(source_segmented) != "".join(source_tokens):
        raise ValueError("Source segmentation does not preserve surface text")
    if normalize_text(target_segmented) != "".join(target_tokens):
        raise ValueError("Target segmentation does not preserve surface text")

    if isinstance(character_alignment, AlignmentResult):
        pairs = character_alignment.combined
    else:
        pairs = character_alignment
    source_lookup = character_to_token(source_tokens)
    target_lookup = character_to_token(target_tokens)
    votes: Counter[tuple[int, int]] = Counter()
    for target_character, source_character in pairs.items():
        if target_character not in target_lookup or source_character not in source_lookup:
            raise ValueError("Character alignment index is outside tokenized text")
        votes[(target_lookup[target_character], source_lookup[source_character])] += 1
    return dict(_best_weighted_monotonic_pairs(votes))


def character_alignment_from_edits(
    source: str,
    target: str,
    edits: Sequence[CharacterEdit],
) -> dict[int, int]:
    """Recover monotonic character anchors retained by projection M2 edits."""

    source = normalize_text(source)
    target = normalize_text(target)
    if apply_edits(source, edits) != target:
        raise ValueError("Character edits do not reconstruct the target")
    alignment: dict[int, int] = {}
    source_cursor = 0
    target_cursor = 0
    for edit in edits:
        source_unchanged = source[source_cursor : edit.source_start]
        target_unchanged = target[target_cursor : edit.target_start]
        if source_unchanged != target_unchanged:
            raise ValueError("Text outside projection edits is not identical")
        for offset in range(len(source_unchanged)):
            alignment[target_cursor + offset] = source_cursor + offset

        if edit.edit_type == "R":
            source_width = edit.source_end - edit.source_start
            target_width = edit.target_end - edit.target_start
            for offset in range(min(source_width, target_width)):
                alignment[edit.target_start + offset] = edit.source_start + offset
        source_cursor = edit.source_end
        target_cursor = edit.target_end

    source_unchanged = source[source_cursor:]
    target_unchanged = target[target_cursor:]
    if source_unchanged != target_unchanged:
        raise ValueError("Trailing text outside projection edits is not identical")
    for offset in range(len(source_unchanged)):
        alignment[target_cursor + offset] = source_cursor + offset
    return alignment


def _make_word_edit(
    source_start: int,
    source_end: int,
    target_start: int,
    target_end: int,
    target_tokens: Sequence[str],
) -> WordEdit | None:
    if source_start == source_end and target_start == target_end:
        return None
    if source_start == source_end:
        edit_type = "M"
    elif target_start == target_end:
        edit_type = "U"
    else:
        edit_type = "R"
    return WordEdit(
        source_start,
        source_end,
        target_start,
        target_end,
        edit_type,
        tuple(target_tokens[target_start:target_end]),
    )


def _merge_same_type_edits(edits: Sequence[WordEdit]) -> list[WordEdit]:
    merged: list[WordEdit] = []
    for edit in edits:
        if not merged:
            merged.append(edit)
            continue
        previous = merged[-1]
        source_contiguous = previous.source_end == edit.source_start
        target_contiguous = previous.target_end == edit.target_start
        insertion_contiguous = (
            previous.edit_type == "M"
            and edit.edit_type == "M"
            and previous.source_start == edit.source_start
            and target_contiguous
        )
        if previous.edit_type == edit.edit_type and (
            (source_contiguous and target_contiguous) or insertion_contiguous
        ):
            merged[-1] = WordEdit(
                previous.source_start,
                edit.source_end,
                previous.target_start,
                edit.target_end,
                edit.edit_type,
                previous.correction + edit.correction,
            )
        else:
            merged.append(edit)
    return merged


def _as_word_order(
    source_tokens: Sequence[str],
    target_tokens: Sequence[str],
    edits: Sequence[WordEdit],
) -> WordEdit | None:
    if not edits:
        return None
    source_start = min(edit.source_start for edit in edits)
    source_end = max(edit.source_end for edit in edits)
    target_start = min(edit.target_start for edit in edits)
    target_end = max(edit.target_end for edit in edits)
    source_span = tuple(source_tokens[source_start:source_end])
    target_span = tuple(target_tokens[target_start:target_end])
    if (
        len(source_span) < 2
        or len(target_span) < 2
        or source_span == target_span
        or Counter(source_span) != Counter(target_span)
    ):
        return None
    return WordEdit(
        source_start,
        source_end,
        target_start,
        target_end,
        "W",
        target_span,
    )


def _label_word_order(
    source_tokens: Sequence[str],
    target_tokens: Sequence[str],
    edits: Sequence[WordEdit],
    *,
    l_max: int = DEFAULT_L_MAX_WORD,
) -> list[WordEdit]:
    if l_max < 2:
        raise ValueError("l_max must be at least 2")
    labeled: list[WordEdit] = []
    index = 0
    while index < len(edits):
        word_order: WordEdit | None = None
        end_index = index
        for candidate_end in range(index, len(edits)):
            candidate = _as_word_order(
                source_tokens,
                target_tokens,
                edits[index : candidate_end + 1],
            )
            if candidate is not None:
                word_order = candidate
                end_index = candidate_end
                break
        if word_order is None:
            labeled.append(edits[index])
            index += 1
        else:
            candidate_slice = edits[index : end_index + 1]
            linked = _linked_word_movement(
                source_tokens,
                candidate_slice,
                word_order,
                link_id=f"w{len(labeled) + 1}",
                l_max=l_max,
            )
            labeled.extend(linked if linked is not None else [word_order])
            index = end_index + 1
    return renumber_movement_links(source_tokens, labeled)


def _linked_word_movement(
    source_tokens: Sequence[str],
    edits: Sequence[WordEdit],
    word_order: WordEdit,
    *,
    link_id: str,
    l_max: int,
) -> list[WordEdit] | None:
    if word_order.source_end - word_order.source_start <= l_max:
        return None
    if len(edits) != 2 or {edit.edit_type for edit in edits} != {"M", "U"}:
        return None
    deletion = next(edit for edit in edits if edit.edit_type == "U")
    insertion = next(edit for edit in edits if edit.edit_type == "M")
    moved = tuple(source_tokens[deletion.source_start : deletion.source_end])
    if not moved or moved != insertion.correction:
        return None
    if deletion.source_start < insertion.source_start < deletion.source_end:
        return None
    linked: list[WordEdit] = []
    for edit in edits:
        if edit.edit_type == "U":
            linked.append(
                WordEdit(
                    edit.source_start,
                    edit.source_end,
                    edit.target_start,
                    edit.target_end,
                    edit.edit_type,
                    edit.correction,
                    origin_comment(link_id, insertion.source_start),
                )
            )
        else:
            linked.append(
                WordEdit(
                    edit.source_start,
                    edit.source_end,
                    edit.target_start,
                    edit.target_end,
                    edit.edit_type,
                    edit.correction,
                    destination_comment(
                        link_id, deletion.source_start, deletion.source_end
                    ),
                )
            )
    return linked


def edits_from_token_alignment(
    source_tokens: Sequence[str],
    target_tokens: Sequence[str],
    alignment: Mapping[int, int],
    *,
    l_max: int = DEFAULT_L_MAX_WORD,
) -> list[WordEdit]:
    """Convert monotonic target/source token anchors into MRUW edits."""

    pairs = sorted(alignment.items())
    previous_target = -1
    previous_source = -1
    for target_index, source_index in pairs:
        if not (0 <= target_index < len(target_tokens)):
            raise ValueError(f"Target token index out of range: {target_index}")
        if not (0 <= source_index < len(source_tokens)):
            raise ValueError(f"Source token index out of range: {source_index}")
        if target_index <= previous_target or source_index <= previous_source:
            raise ValueError("Token alignment must be strictly monotonic")
        previous_target = target_index
        previous_source = source_index

    edits: list[WordEdit] = []
    source_cursor = 0
    target_cursor = 0
    for target_index, source_index in pairs:
        gap = _make_word_edit(
            source_cursor,
            source_index,
            target_cursor,
            target_index,
            target_tokens,
        )
        if gap is not None:
            edits.append(gap)
        if source_tokens[source_index] != target_tokens[target_index]:
            edits.append(
                WordEdit(
                    source_index,
                    source_index + 1,
                    target_index,
                    target_index + 1,
                    "R",
                    (target_tokens[target_index],),
                )
            )
        source_cursor = source_index + 1
        target_cursor = target_index + 1

    tail = _make_word_edit(
        source_cursor,
        len(source_tokens),
        target_cursor,
        len(target_tokens),
        target_tokens,
    )
    if tail is not None:
        edits.append(tail)
    edits = _merge_same_type_edits(edits)
    edits = _label_word_order(
        source_tokens, target_tokens, edits, l_max=l_max
    )
    if apply_word_edits(source_tokens, edits) != tuple(target_tokens):
        raise ValueError("Projection word edits failed round-trip validation")
    return edits


def projection_word_edits(
    source_segmented: str,
    target_segmented: str,
    character_alignment: Mapping[int, int] | AlignmentResult,
    *,
    l_max: int = DEFAULT_L_MAX_WORD,
) -> list[WordEdit]:
    source_tokens = segmented_tokens(source_segmented)
    target_tokens = segmented_tokens(target_segmented)
    alignment = token_alignment_from_character_alignment(
        source_segmented,
        target_segmented,
        character_alignment,
    )
    return edits_from_token_alignment(
        source_tokens, target_tokens, alignment, l_max=l_max
    )


def projection_word_edits_from_character_edits(
    source_segmented: str,
    target_segmented: str,
    character_edits: Sequence[CharacterEdit],
    *,
    l_max: int = DEFAULT_L_MAX_WORD,
) -> list[WordEdit]:
    source = normalize_text(source_segmented)
    target = normalize_text(target_segmented)
    alignment = character_alignment_from_edits(source, target, character_edits)
    return projection_word_edits(
        source_segmented, target_segmented, alignment, l_max=l_max
    )


def apply_word_edits(
    source_tokens: Sequence[str], edits: Sequence[WordEdit]
) -> tuple[str, ...]:
    return simultaneous_reconstruction(tuple(source_tokens), edits)


def render_word_m2_block(
    source_segmented: str,
    references: Sequence[tuple[str, Sequence[WordEdit]]],
) -> str:
    source_tokens = segmented_tokens(source_segmented)
    lines = ["S " + " ".join(source_tokens)]
    for annotator_id, (target_segmented, edits) in enumerate(references):
        target_tokens = segmented_tokens(target_segmented)
        if apply_word_edits(source_tokens, edits) != target_tokens:
            raise ValueError(
                f"Annotator {annotator_id} word edits do not reconstruct target"
            )
        if edits:
            lines.extend(edit.m2_line(annotator_id) for edit in edits)
        else:
            lines.append(
                "A -1 -1|||noop|||-NONE-|||REQUIRED|||-NONE-|||"
                f"{annotator_id}"
            )
    return "\n".join(lines)


def targets_from_word_m2_block(
    block: str,
) -> tuple[tuple[str, ...], dict[int, tuple[str, ...]]]:
    lines = [line for line in block.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("S "):
        raise ValueError("Word M2 block does not start with an S line")
    source_tokens = tuple(lines[0][2:].split())
    grouped: dict[int, list[WordEdit]] = {}
    noop_ids: set[int] = set()
    for line in lines[1:]:
        fields = line[2:].split("|||") if line.startswith("A ") else []
        if len(fields) != 6:
            raise ValueError(f"Invalid word M2 line: {line}")
        start, end = (int(value) for value in fields[0].split())
        edit_type = fields[1]
        correction = fields[2]
        comment = fields[4]
        annotator_id = int(fields[-1])
        if edit_type == "noop":
            if (start, end) != (-1, -1):
                raise ValueError("noop word edit must use -1 -1")
            noop_ids.add(annotator_id)
            continue
        if edit_type not in {"M", "R", "U", "W"}:
            raise ValueError(f"Unsupported word edit type: {edit_type}")
        correction_tokens = () if correction == NO_CORRECTION else tuple(correction.split())
        grouped.setdefault(annotator_id, []).append(
            WordEdit(start, end, 0, 0, edit_type, correction_tokens, comment)
        )
    reconstructed = {
        annotator_id: source_tokens for annotator_id in noop_ids
    }
    for annotator_id, edits in grouped.items():
        reconstructed[annotator_id] = apply_word_edits(source_tokens, edits)
    return source_tokens, reconstructed
