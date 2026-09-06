#!/usr/bin/env python3
"""Generate character-level M2 edits from WB two-step alignments.

The implementation follows ``character_m2_README.md``:

* source and target are aligned character by character;
* exact identical-character alignment is followed by the WB project's
  four-feature alignment for the remaining characters;
* M2 blocks contain one character-tokenized ``S`` line and ``A`` lines only;
* edit labels are M (missing), R (replacement), U (unnecessary), and W
  (word/character order).

The pure edit-generation functions are intentionally independent from the
large WB dependencies so they can be tested without loading BERT or LTP.
"""

from __future__ import annotations

import argparse
from collections import Counter, OrderedDict
import csv
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping, Sequence

try:
    from movement_m2 import (
        DEFAULT_L_MAX_CHAR,
        destination_comment,
        origin_comment,
        renumber_movement_links,
        simultaneous_reconstruction,
    )
except ModuleNotFoundError:
    from scripts.movement_m2 import (
        DEFAULT_L_MAX_CHAR,
        destination_comment,
        origin_comment,
        renumber_movement_links,
        simultaneous_reconstruction,
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WB_REPO = ROOT.parent / "chinese-wb-fixing"
DEFAULT_SHAPE_TABLE = Path(
    ROOT.parent
    / "fixing_wb/transformer/data/0423/triplet_no_dup_threshold.csv"
)

NO_CORRECTION = "-NONE-"
PUNCTUATION = set(
    "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
    "！？｡＂＃＄％＆＇（）＊＋，－／：；＜＝＞＠［＼］＾＿｀｛｜｝～"
    "｟｠｢｣､、〃》「」『』【】〔〕〖〗〘〙〚〛〜〝〞〟–—‘’“”„‟…‧."
)


@dataclass(frozen=True)
class CharacterEdit:
    """One projected edit, with target offsets retained for verification."""

    source_start: int
    source_end: int
    target_start: int
    target_end: int
    edit_type: str
    correction: str
    comment: str = "NONE"

    def m2_line(self, annotator_id: int) -> str:
        return (
            f"A {self.source_start} {self.source_end}|||{self.edit_type}|||"
            f"{self.correction}|||-REQUIRED-|||{self.comment}|||{annotator_id}"
        )


@dataclass(frozen=True)
class AlignmentResult:
    """Exact and fuzzy target-to-source character alignments."""

    exact: dict[int, int]
    fuzzy_raw: dict[int, int]
    fuzzy_monotonic: dict[int, int]
    unaligned_source: tuple[int, ...]
    unaligned_target: tuple[int, ...]

    @property
    def combined(self) -> dict[int, int]:
        return {**self.exact, **self.fuzzy_monotonic}


def normalize_text(text: str) -> str:
    """Remove segmentation and other whitespace from a Chinese sentence."""

    return re.sub(r"\s+", "", str(text))


def _longest_increasing_candidates(
    candidates: Sequence[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Return a deterministic maximum monotonic target/source subsequence."""

    if not candidates:
        return []

    ordered = sorted(candidates)
    paths: list[tuple[tuple[int, int], ...]] = []
    for index, pair in enumerate(ordered):
        best: tuple[tuple[int, int], ...] = (pair,)
        for earlier in range(index):
            previous = ordered[earlier]
            if previous[0] >= pair[0] or previous[1] >= pair[1]:
                continue
            candidate = paths[earlier] + (pair,)
            if len(candidate) > len(best) or (
                len(candidate) == len(best) and candidate < best
            ):
                best = candidate
        paths.append(best)

    return list(min(paths, key=lambda path: (-len(path), path)))


def select_monotonic_fuzzy_alignment(
    *,
    exact: Mapping[int, int],
    fuzzy: Mapping[int, int],
    source_length: int,
    target_length: int,
) -> dict[int, int]:
    """Keep fuzzy pairs that do not cross the monotonic exact alignment.

    The WB similarity aligner is greedy and can return crossing target-to-source
    pairs. Standard M2 edits require ordered, non-overlapping source spans, so
    exact pairs are treated as fixed anchors and the longest increasing fuzzy
    subsequence is retained inside each interval between those anchors.
    """

    exact_pairs = sorted(exact.items())
    previous_tgt = -1
    previous_src = -1
    for target_index, source_index in exact_pairs:
        if not (0 <= target_index < target_length):
            raise ValueError(f"Exact target index out of range: {target_index}")
        if not (0 <= source_index < source_length):
            raise ValueError(f"Exact source index out of range: {source_index}")
        if target_index <= previous_tgt or source_index <= previous_src:
            raise ValueError("Exact alignment is not strictly monotonic")
        previous_tgt = target_index
        previous_src = source_index

    selected: dict[int, int] = {}
    boundaries = [(-1, -1), *exact_pairs, (target_length, source_length)]
    for (left_tgt, left_src), (right_tgt, right_src) in zip(
        boundaries, boundaries[1:]
    ):
        interval_candidates = [
            (target_index, source_index)
            for target_index, source_index in fuzzy.items()
            if left_tgt < target_index < right_tgt
            and left_src < source_index < right_src
            and target_index not in exact
            and source_index not in exact.values()
        ]
        selected.update(
            dict(_longest_increasing_candidates(interval_candidates))
        )
    return selected


def _make_edit(
    source_start: int,
    source_end: int,
    target_start: int,
    target_end: int,
    target: str,
) -> CharacterEdit | None:
    if source_start == source_end and target_start == target_end:
        return None
    if source_start == source_end:
        edit_type = "M"
        correction = target[target_start:target_end]
    elif target_start == target_end:
        edit_type = "U"
        correction = NO_CORRECTION
    else:
        edit_type = "R"
        correction = target[target_start:target_end]
    return CharacterEdit(
        source_start=source_start,
        source_end=source_end,
        target_start=target_start,
        target_end=target_end,
        edit_type=edit_type,
        correction=correction,
    )


def _merge_same_type_edits(edits: Sequence[CharacterEdit]) -> list[CharacterEdit]:
    """Merge adjacent atomic edits only when their operation type is identical."""

    merged: list[CharacterEdit] = []
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
            correction = (
                NO_CORRECTION
                if edit.edit_type == "U"
                else previous.correction + edit.correction
            )
            merged[-1] = CharacterEdit(
                source_start=previous.source_start,
                source_end=edit.source_end,
                target_start=previous.target_start,
                target_end=edit.target_end,
                edit_type=edit.edit_type,
                correction=correction,
            )
        else:
            merged.append(edit)
    return merged


def _as_transposition(
    source: str,
    target: str,
    edits: Sequence[CharacterEdit],
) -> CharacterEdit | None:
    """Collapse a projected permutation span into one round-trippable W edit.

    ChERRANT's direct transposition check compares sorted source and target
    spans.  Counter equality is the equivalent multiset test and, unlike the
    JP-ERRANT ``set`` check, preserves repeated-character counts.  A sequence
    of edits may contain unchanged text between its endpoints; this is what
    allows a distant delete/insert move to become one W annotation.
    """

    if not edits:
        return None
    source_start = min(edit.source_start for edit in edits)
    source_end = max(edit.source_end for edit in edits)
    target_start = min(edit.target_start for edit in edits)
    target_end = max(edit.target_end for edit in edits)
    source_span = source[source_start:source_end]
    target_span = target[target_start:target_end]
    if (
        len(source_span) < 2
        or len(target_span) < 2
        or source_span == target_span
        or Counter(source_span) != Counter(target_span)
    ):
        return None
    return CharacterEdit(
        source_start=source_start,
        source_end=source_end,
        target_start=target_start,
        target_end=target_end,
        edit_type="W",
        correction=target_span,
    )


def _levenshtein_distance(left: str, right: str) -> int:
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


def _is_rotation(left: str, right: str) -> bool:
    return len(left) == len(right) and right in left + left


def _as_cherrant_merge_transposition(
    source: str,
    target: str,
    edits: Sequence[CharacterEdit],
) -> CharacterEdit | None:
    """Mirror ChERRANT's tolerant S-M-S and D-M-I merge heuristics."""

    if len(edits) != 2:
        return None
    first, second = edits
    is_transposition = False
    if first.edit_type == second.edit_type == "R":
        source_first = source[first.source_start : first.source_end]
        target_first = target[first.target_start : first.target_end]
        source_second = source[second.source_start : second.source_end]
        target_second = target[second.target_start : second.target_end]
        lengths = [
            len(source_first),
            len(target_first),
            len(source_second),
            len(target_second),
        ]
        if min(lengths) == 1:
            is_transposition = (
                source_first == target_second and target_first == source_second
            )
        elif all(lengths):
            is_transposition = (
                _levenshtein_distance(source_first, target_second) <= 1
                and _levenshtein_distance(target_first, source_second) <= 1
            )
    elif {first.edit_type, second.edit_type} == {"M", "U"}:
        deletion = first if first.edit_type == "U" else second
        insertion = first if first.edit_type == "M" else second
        deleted = source[deletion.source_start : deletion.source_end]
        inserted = target[insertion.target_start : insertion.target_end]
        longer, shorter = (
            (deleted, inserted)
            if len(deleted) >= len(inserted)
            else (inserted, deleted)
        )
        if (
            longer
            and shorter
            and longer not in PUNCTUATION
            and shorter not in PUNCTUATION
            and len(longer) - len(shorter) <= 1
        ):
            if len(shorter) == 1:
                is_transposition = longer == shorter
            else:
                is_transposition = (
                    _levenshtein_distance(longer, shorter) <= 1
                    or _is_rotation(longer, shorter)
                )
    if not is_transposition:
        return None

    source_start = min(edit.source_start for edit in edits)
    source_end = max(edit.source_end for edit in edits)
    target_start = min(edit.target_start for edit in edits)
    target_end = max(edit.target_end for edit in edits)
    if source_start == source_end or target_start == target_end:
        return None
    return CharacterEdit(
        source_start,
        source_end,
        target_start,
        target_end,
        "W",
        target[target_start:target_end],
    )


def label_transpositions(
    source: str,
    target: str,
    edits: Sequence[CharacterEdit],
    *,
    l_max: int = DEFAULT_L_MAX_CHAR,
) -> list[CharacterEdit]:
    """Label pure reorderings as bounded W or linked long-distance U--M."""

    if l_max < 2:
        raise ValueError("l_max must be at least 2")

    labeled: list[CharacterEdit] = []
    index = 0
    while index < len(edits):
        transposition: CharacterEdit | None = None
        end_index = index
        for candidate_end in range(index, len(edits)):
            candidate_slice = edits[index : candidate_end + 1]
            candidate = _as_transposition(
                source,
                target,
                candidate_slice,
            )
            if candidate is not None:
                transposition = candidate
                end_index = candidate_end
                break
        if transposition is None:
            labeled.append(edits[index])
            index += 1
        else:
            candidate_slice = edits[index : end_index + 1]
            linked = _linked_character_movement(
                source,
                candidate_slice,
                transposition,
                link_id=f"w{len(labeled) + 1}",
                l_max=l_max,
            )
            labeled.extend(linked if linked is not None else [transposition])
            index = end_index + 1
    return renumber_movement_links(tuple(source), labeled)


def _linked_character_movement(
    source: str,
    edits: Sequence[CharacterEdit],
    transposition: CharacterEdit,
    *,
    link_id: str,
    l_max: int,
) -> list[CharacterEdit] | None:
    """Return a linked pair only for an alignment-supported one-block move."""

    if transposition.source_end - transposition.source_start <= l_max:
        return None
    if len(edits) != 2 or {edit.edit_type for edit in edits} != {"M", "U"}:
        return None
    deletion = next(edit for edit in edits if edit.edit_type == "U")
    insertion = next(edit for edit in edits if edit.edit_type == "M")
    moved = source[deletion.source_start : deletion.source_end]
    if not moved or moved != insertion.correction:
        return None
    if deletion.source_start < insertion.source_start < deletion.source_end:
        return None
    linked = []
    for edit in edits:
        if edit.edit_type == "U":
            linked.append(
                CharacterEdit(
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
                CharacterEdit(
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


def edits_from_alignment(
    source: str,
    target: str,
    alignment: Mapping[int, int],
    *,
    l_max: int = DEFAULT_L_MAX_CHAR,
) -> list[CharacterEdit]:
    """Convert a monotonic target-to-source alignment into M/R/U/W edits."""

    source = normalize_text(source)
    target = normalize_text(target)
    pairs = sorted(alignment.items())

    previous_target = -1
    previous_source = -1
    for target_index, source_index in pairs:
        if not (0 <= target_index < len(target)):
            raise ValueError(f"Target index out of range: {target_index}")
        if not (0 <= source_index < len(source)):
            raise ValueError(f"Source index out of range: {source_index}")
        if target_index <= previous_target or source_index <= previous_source:
            raise ValueError("Combined alignment must be strictly monotonic")
        previous_target = target_index
        previous_source = source_index

    edits: list[CharacterEdit] = []
    source_cursor = 0
    target_cursor = 0
    for target_index, source_index in pairs:
        gap = _make_edit(
            source_cursor,
            source_index,
            target_cursor,
            target_index,
            target,
        )
        if gap is not None:
            edits.append(gap)

        if source[source_index] != target[target_index]:
            edits.append(
                CharacterEdit(
                    source_start=source_index,
                    source_end=source_index + 1,
                    target_start=target_index,
                    target_end=target_index + 1,
                    edit_type="R",
                    correction=target[target_index],
                )
            )
        source_cursor = source_index + 1
        target_cursor = target_index + 1

    tail = _make_edit(
        source_cursor,
        len(source),
        target_cursor,
        len(target),
        target,
    )
    if tail is not None:
        edits.append(tail)

    edits = _merge_same_type_edits(edits)
    edits = label_transpositions(source, target, edits, l_max=l_max)
    reconstructed = apply_edits(source, edits)
    if reconstructed != target:
        raise ValueError(
            "Projection edits failed round-trip validation: "
            f"{source!r} -> {reconstructed!r}, expected {target!r}"
        )
    return edits


def apply_edits(source: str, edits: Sequence[CharacterEdit]) -> str:
    """Apply all edits simultaneously against original-source coordinates."""

    source = normalize_text(source)
    return "".join(simultaneous_reconstruction(tuple(source), edits))


def render_m2_block(
    source: str,
    references: Sequence[tuple[str, Sequence[CharacterEdit]]],
) -> str:
    """Render one source and one or more target edit sets as an M2 block."""

    source = normalize_text(source)
    lines = [f"S {' '.join(source)}"]
    for annotator_id, (target, edits) in enumerate(references):
        target = normalize_text(target)
        if apply_edits(source, edits) != target:
            raise ValueError(
                f"Annotator {annotator_id} edits do not reconstruct its target"
            )
        if edits:
            lines.extend(edit.m2_line(annotator_id) for edit in edits)
        else:
            lines.append(
                "A -1 -1|||noop|||-NONE-|||REQUIRED|||-NONE-|||"
                f"{annotator_id}"
            )
    return "\n".join(lines)


def targets_from_m2_block(block: str) -> tuple[str, dict[int, str]]:
    """Reconstruct every annotator target using only serialized S/A lines."""

    lines = [line for line in block.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("S "):
        raise ValueError("M2 block does not start with an S line")
    if any(line.startswith("T") for line in lines[1:]):
        raise ValueError("Projection M2 must not contain T lines")
    source = "".join(lines[0][2:].split())
    grouped: dict[int, list[CharacterEdit]] = {}
    for line in lines[1:]:
        if not line.startswith("A "):
            raise ValueError(f"Unsupported M2 line: {line}")
        fields = line[2:].split("|||")
        if len(fields) != 6:
            raise ValueError(f"Invalid M2 A line: {line}")
        span = fields[0].split()
        if len(span) != 2:
            raise ValueError(f"Invalid M2 span: {line}")
        start, end = (int(value) for value in span)
        edit_type = fields[1]
        correction = fields[2]
        annotator_id = int(fields[-1])
        grouped.setdefault(annotator_id, []).append(
            CharacterEdit(
                start,
                end,
                0,
                0,
                edit_type,
                correction,
                fields[4],
            )
        )

    reconstructed: dict[int, str] = {}
    for annotator_id, edits in grouped.items():
        if len(edits) == 1 and edits[0].edit_type == "noop":
            if (edits[0].source_start, edits[0].source_end) != (-1, -1):
                raise ValueError("noop edit must use the -1 -1 span")
            reconstructed[annotator_id] = source
            continue
        if any(edit.edit_type not in {"M", "R", "U", "W"} for edit in edits):
            raise ValueError("Unsupported edit type")
        reconstructed[annotator_id] = apply_edits(source, edits)
    return source, reconstructed


def validate_m2_targets(
    path: Path,
    expected: Sequence[tuple[str, Sequence[str]]],
) -> dict[str, int]:
    """Validate a completed M2 file against its original source/targets."""

    text = path.read_text(encoding="utf-8-sig").replace("\ufeff", "").strip()
    blocks = [] if not text else text.split("\n\n")
    if len(blocks) != len(expected):
        raise ValueError(
            f"M2 block count mismatch in {path}: "
            f"{len(blocks)} != {len(expected)}"
        )
    references = 0
    for row_number, (block, (source, targets)) in enumerate(
        zip(blocks, expected), start=1
    ):
        actual_source, actual_targets = targets_from_m2_block(block)
        normalized_targets = [
            normalize_text(target) for target in targets
        ]
        if actual_source != normalize_text(source):
            raise ValueError(f"M2 source mismatch at row {row_number} in {path}")
        expected_ids = set(range(len(normalized_targets)))
        if set(actual_targets) != expected_ids:
            raise ValueError(
                f"M2 annotator IDs mismatch at row {row_number} in {path}"
            )
        for annotator_id, target in enumerate(normalized_targets):
            if actual_targets[annotator_id] != target:
                raise ValueError(
                    f"M2 target mismatch at row {row_number}, annotator "
                    f"{annotator_id} in {path}"
                )
        references += len(normalized_targets)
    return {"sentences": len(blocks), "references": references}


def load_wb_module(wb_repo: Path) -> Any:
    module_path = (
        wb_repo / "src/pipeline/alignment/step2_similarity_alignment_projection.py"
    )
    if not module_path.exists():
        raise FileNotFoundError(f"WB alignment module not found: {module_path}")
    spec = importlib.util.spec_from_file_location(
        "wb_projection_character_m2", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import WB alignment module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TwoStepCharacterAligner:
    """Adapter for the WB project's exact + four-feature alignment."""

    def __init__(
        self,
        *,
        wb_repo: Path = DEFAULT_WB_REPO,
        shape_table: Path = DEFAULT_SHAPE_TABLE,
        threshold: float = 0.85,
        bert_model: str = "bert-base-chinese",
        embedding_cache_size: int = 64,
        l_max_char: int = DEFAULT_L_MAX_CHAR,
    ) -> None:
        self.module = load_wb_module(wb_repo)
        self.threshold = threshold
        self.module.load_bert_model(bert_model)
        self.shape_table = self.module.load_shape_table(str(shape_table))
        self.embedding_cache_size = max(0, embedding_cache_size)
        self.l_max_char = l_max_char
        self._embedding_cache: OrderedDict[str, Any] = OrderedDict()

    def _get_embeddings(self, text: str) -> Any:
        return self._get_embeddings_many([text], batch_size=1)[text]

    def _get_embeddings_many(
        self, texts: Sequence[str], *, batch_size: int
    ) -> dict[str, Any]:
        unique_texts = list(dict.fromkeys(texts))
        result: dict[str, Any] = {}
        missing: list[str] = []
        for text in unique_texts:
            cached = self._embedding_cache.get(text)
            if cached is None:
                missing.append(text)
            else:
                self._embedding_cache.move_to_end(text)
                result[text] = cached

        for start in range(0, len(missing), batch_size):
            batch = missing[start : start + batch_size]
            inputs = self.module.tokenizer(
                [list(text) for text in batch],
                return_tensors="pt",
                is_split_into_words=True,
                padding=True,
            )
            inputs = {
                key: value.to(self.module.device)
                for key, value in inputs.items()
            }
            with self.module.torch.no_grad():
                outputs = self.module.model(**inputs)
            for batch_index, text in enumerate(batch):
                embeddings = outputs.last_hidden_state[
                    batch_index, 1 : len(text) + 1, :
                ].cpu()
                if len(embeddings) != len(text):
                    raise ValueError(
                        "BERT character embedding length mismatch for "
                        f"{text!r}: {len(embeddings)} != {len(text)}"
                    )
                result[text] = embeddings
                if self.embedding_cache_size:
                    self._embedding_cache[text] = embeddings
                    self._embedding_cache.move_to_end(text)
                    while len(self._embedding_cache) > self.embedding_cache_size:
                        self._embedding_cache.popitem(last=False)
        return result

    def _embedding_similarity(self, source: str, target: str) -> Any:
        source_embeddings = self._get_embeddings(source)
        target_embeddings = self._get_embeddings(target)
        similarity = self.module.torch.cosine_similarity(
            source_embeddings.unsqueeze(1),
            target_embeddings.unsqueeze(0),
            dim=2,
        )
        return similarity.cpu().numpy()

    def align(self, source: str, target: str) -> AlignmentResult:
        return self.align_many([(source, target)])[0]

    def align_many(
        self,
        pairs: Sequence[tuple[str, str]],
        *,
        embedding_batch_size: int = 32,
    ) -> list[AlignmentResult]:
        if embedding_batch_size < 1:
            raise ValueError("embedding_batch_size must be at least 1")

        prepared: list[
            tuple[str, str, dict[int, int], list[int], list[int]]
        ] = []
        texts_needing_embeddings: list[str] = []
        for source, target in pairs:
            source = normalize_text(source)
            target = normalize_text(target)
            if source == target:
                exact = {index: index for index in range(len(source))}
                unaligned_source: list[int] = []
                unaligned_target: list[int] = []
            else:
                exact, unaligned_source, unaligned_target = (
                    self.module.exact_alignment_ins_del_only(source, target)
                )
            prepared.append(
                (
                    source,
                    target,
                    exact,
                    unaligned_source,
                    unaligned_target,
                )
            )
            if source and target and unaligned_source and unaligned_target:
                texts_needing_embeddings.extend((source, target))

        embeddings = self._get_embeddings_many(
            texts_needing_embeddings,
            batch_size=embedding_batch_size,
        )
        results: list[AlignmentResult] = []
        for (
            source,
            target,
            exact,
            unaligned_source,
            unaligned_target,
        ) in prepared:
            fuzzy_raw: dict[int, int] = {}
            if source and target and unaligned_source and unaligned_target:
                similarity = self.module.torch.cosine_similarity(
                    embeddings[source].unsqueeze(1),
                    embeddings[target].unsqueeze(0),
                    dim=2,
                ).numpy()
                fuzzy_raw = self.module.align_similar_chars_4feat_t2s(
                    source,
                    target,
                    unaligned_source,
                    unaligned_target,
                    similarity,
                    self.shape_table,
                    self.threshold,
                )

            fuzzy_monotonic = select_monotonic_fuzzy_alignment(
                exact=exact,
                fuzzy=fuzzy_raw,
                source_length=len(source),
                target_length=len(target),
            )
            results.append(
                AlignmentResult(
                    exact=dict(exact),
                    fuzzy_raw=dict(fuzzy_raw),
                    fuzzy_monotonic=fuzzy_monotonic,
                    unaligned_source=tuple(unaligned_source),
                    unaligned_target=tuple(unaligned_target),
                )
            )
        return results

    def _align_unbatched(self, source: str, target: str) -> AlignmentResult:
        """Retained as a direct equivalent for batch-regression checks."""

        source = normalize_text(source)
        target = normalize_text(target)
        exact, unaligned_source, unaligned_target = (
            self.module.exact_alignment_ins_del_only(source, target)
        )

        fuzzy_raw: dict[int, int] = {}
        if source and target and unaligned_source and unaligned_target:
            embedding_similarity = self._embedding_similarity(source, target)
            fuzzy_raw = self.module.align_similar_chars_4feat_t2s(
                source,
                target,
                unaligned_source,
                unaligned_target,
                embedding_similarity,
                self.shape_table,
                self.threshold,
            )

        fuzzy_monotonic = select_monotonic_fuzzy_alignment(
            exact=exact,
            fuzzy=fuzzy_raw,
            source_length=len(source),
            target_length=len(target),
        )
        return AlignmentResult(
            exact=dict(exact),
            fuzzy_raw=dict(fuzzy_raw),
            fuzzy_monotonic=fuzzy_monotonic,
            unaligned_source=tuple(unaligned_source),
            unaligned_target=tuple(unaligned_target),
        )

    def convert(self, source: str, target: str) -> tuple[list[CharacterEdit], AlignmentResult]:
        alignment = self.align(source, target)
        edits = edits_from_alignment(
            source, target, alignment.combined, l_max=self.l_max_char
        )
        return edits, alignment

    def convert_many(
        self,
        pairs: Sequence[tuple[str, str]],
        *,
        embedding_batch_size: int = 32,
    ) -> list[tuple[list[CharacterEdit], AlignmentResult]]:
        alignments = self.align_many(
            pairs, embedding_batch_size=embedding_batch_size
        )
        return [
            (
                edits_from_alignment(
                    source, target, alignment.combined, l_max=self.l_max_char
                ),
                alignment,
            )
            for (source, target), alignment in zip(pairs, alignments)
        ]


def read_pairs_tsv(
    path: Path,
    *,
    source_column: int,
    target_start_column: int,
    limit: int = 0,
) -> Iterable[tuple[str, list[str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for row_number, row in enumerate(reader, start=1):
            if limit and row_number > limit:
                break
            if len(row) <= source_column or len(row) <= target_start_column:
                raise ValueError(f"TSV row {row_number} has too few columns")
            source = row[source_column]
            targets = [
                target
                for target in row[target_start_column:]
                if normalize_text(target)
            ]
            if not targets:
                raise ValueError(f"TSV row {row_number} has no target")
            yield source, targets


def write_projection_m2(
    pairs: Iterable[tuple[str, Sequence[str]]],
    output_path: Path,
    aligner: TwoStepCharacterAligner,
) -> dict[str, int]:
    blocks: list[str] = []
    stats = {
        "sentences": 0,
        "references": 0,
        "edits": 0,
        "exact_alignments": 0,
        "fuzzy_alignments_raw": 0,
        "fuzzy_alignments_monotonic": 0,
    }
    for source, targets in pairs:
        converted: list[tuple[str, Sequence[CharacterEdit]]] = []
        for target in targets:
            edits, alignment = aligner.convert(source, target)
            converted.append((target, edits))
            stats["references"] += 1
            stats["edits"] += len(edits)
            stats["exact_alignments"] += len(alignment.exact)
            stats["fuzzy_alignments_raw"] += len(alignment.fuzzy_raw)
            stats["fuzzy_alignments_monotonic"] += len(
                alignment.fuzzy_monotonic
            )
        blocks.append(render_m2_block(source, converted))
        stats["sentences"] += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate projection-based character M2 from a TSV"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-column", type=int, default=1)
    parser.add_argument("--target-start-column", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--wb-repo", type=Path, default=DEFAULT_WB_REPO)
    parser.add_argument("--shape-table", type=Path, default=DEFAULT_SHAPE_TABLE)
    parser.add_argument("--threshold", type=float, default=0.85)
    parser.add_argument("--bert-model", default="bert-base-chinese")
    parser.add_argument("--embedding-cache-size", type=int, default=64)
    parser.add_argument("--stats", type=Path)
    args = parser.parse_args()

    aligner = TwoStepCharacterAligner(
        wb_repo=args.wb_repo,
        shape_table=args.shape_table,
        threshold=args.threshold,
        bert_model=args.bert_model,
        embedding_cache_size=args.embedding_cache_size,
    )
    stats = write_projection_m2(
        read_pairs_tsv(
            args.input,
            source_column=args.source_column,
            target_start_column=args.target_start_column,
            limit=args.limit,
        ),
        args.output,
        aligner,
    )
    stats_text = json.dumps(stats, ensure_ascii=False, indent=2)
    if args.stats:
        args.stats.parent.mkdir(parents=True, exist_ok=True)
        args.stats.write_text(stats_text + "\n", encoding="utf-8")
    print(stats_text)


if __name__ == "__main__":
    main()
