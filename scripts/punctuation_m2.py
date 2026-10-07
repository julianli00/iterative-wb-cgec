"""Refine generic edit spans without merging standalone punctuation with words."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
import unicodedata
from typing import Sequence

if __package__:
    from .movement_m2 import parse_link_comment
    from .projection_word_m2 import WordEdit
else:
    from movement_m2 import parse_link_comment
    from projection_word_m2 import WordEdit


EDIT_POLICY = "punctuation-separated-v2"


@lru_cache(maxsize=8192)
def is_punctuation_token(token: str) -> bool:
    """Punctuation/symbol-only tokens; keep apostrophes, hyphens and decimals inside words."""

    categories = [unicodedata.category(character) for character in token]
    return bool(categories) and any(category[0] in "PS" for category in categories) and all(
        category[0] in "PSM" or category == "Cf" for category in categories
    )


def mixes_punctuation_and_words(tokens: Sequence[str]) -> bool:
    kinds = {is_punctuation_token(token) for token in tokens}
    return len(kinds) > 1


def edit_mixes_punctuation(source: Sequence[str], edit: WordEdit) -> bool:
    return mixes_punctuation_and_words(
        (*source[edit.source_start:edit.source_end], *edit.correction)
    )


def _split_span(
    source: Sequence[str], target: Sequence[str], edit: WordEdit
) -> list[WordEdit]:
    """Minimum-cost refinement inside one edit; cross-type substitutions are forbidden."""

    source_span = source[edit.source_start:edit.source_end]
    target_span = target[edit.target_start:edit.target_end]
    if tuple(target_span) != edit.correction:
        raise ValueError("Edit target offsets disagree with correction material")
    m, n = len(source_span), len(target_span)
    source_kinds = [is_punctuation_token(token) for token in source_span]
    target_kinds = [is_punctuation_token(token) for token in target_span]
    costs = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        costs[i][0] = i
    for j in range(n + 1):
        costs[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = min(costs[i - 1][j] + 1, costs[i][j - 1] + 1)
            if source_kinds[i - 1] == target_kinds[j - 1]:
                cost = min(cost, costs[i - 1][j - 1] + (source_span[i - 1] != target_span[j - 1]))
            costs[i][j] = cost
    reversed_edits = []
    i, j = m, n
    while i or j:
        source_end, target_end = i, j
        if (
            i and j
            and source_kinds[i - 1] == target_kinds[j - 1]
            and costs[i][j] == costs[i - 1][j - 1] + (source_span[i - 1] != target_span[j - 1])
        ):
            i -= 1
            j -= 1
            if source_span[i] == target_span[j]:
                continue
            kind = "R"
        elif i and costs[i][j] == costs[i - 1][j] + 1:
            i -= 1
            kind = "U"
        else:
            j -= 1
            kind = "M"
        reversed_edits.append(WordEdit(
            edit.source_start + i,
            edit.source_start + source_end,
            edit.target_start + j,
            edit.target_start + target_end,
            kind,
            tuple(target_span[j:target_end]),
        ))
    atoms = list(reversed(reversed_edits))
    merged: list[WordEdit] = []
    for atom in atoms:
        if merged:
            previous = merged[-1]
            if (
                previous.edit_type == atom.edit_type
                and previous.source_end == atom.source_start
                and previous.target_end == atom.target_start
            ):
                candidate = WordEdit(
                    previous.source_start, atom.source_end,
                    previous.target_start, atom.target_end,
                    atom.edit_type, previous.correction + atom.correction,
                )
                if not edit_mixes_punctuation(source, candidate):
                    merged[-1] = candidate
                    continue
        merged.append(atom)
    return merged


def separate_punctuation_edits(
    source: Sequence[str], target: Sequence[str], edits: Sequence[WordEdit]
) -> list[WordEdit]:
    """Retain homogeneous spans and split mixed MRU/W spans; remove invalidated links."""

    mixed_links = set()
    for edit in edits:
        if edit_mixes_punctuation(source, edit):
            link = parse_link_comment(edit.comment)
            if link is not None:
                mixed_links.add(link.link_id)
    result = []
    for edit in edits:
        link = parse_link_comment(edit.comment)
        if link is not None and link.link_id in mixed_links:
            edit = replace(edit, comment="NONE")
        if edit_mixes_punctuation(source, edit):
            result.extend(_split_span(source, target, edit))
        else:
            result.append(edit)
    if any(edit_mixes_punctuation(source, edit) for edit in result):
        raise ValueError("Punctuation refinement left a mixed punctuation/lexical edit")
    return result
