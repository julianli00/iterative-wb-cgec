"""Exact token anchors plus contextual Transformer similarity for residual tokens."""

from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass, replace
import hashlib
import importlib.metadata
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__:
    from .movement_m2 import destination_comment, origin_comment, renumber_movement_links
    from .punctuation_m2 import EDIT_POLICY, edit_mixes_punctuation, separate_punctuation_edits
    from .projection_word_m2 import WordEdit, apply_word_edits, edits_from_token_alignment
    from .tokenized_m2 import validate_tokens
else:
    from movement_m2 import destination_comment, origin_comment, renumber_movement_links
    from punctuation_m2 import EDIT_POLICY, edit_mixes_punctuation, separate_punctuation_edits
    from projection_word_m2 import WordEdit, apply_word_edits, edits_from_token_alignment
    from tokenized_m2 import validate_tokens


DEFAULT_MODEL = "google-bert/bert-base-multilingual-cased"
DEFAULT_REVISION = "3f076fdb1ab68d5b2880cb87a0886f315b8146f8"
IMPLEMENTATION_VERSION = "generic-token-mruw-v2"


def exact_token_anchors(source: Sequence[str], target: Sequence[str]) -> dict[int, int]:
    """Longest common token subsequence, with a deterministic deletion-first tie break."""

    if tuple(source) == tuple(target):
        return {index: index for index in range(len(source))}
    lengths = [[0] * (len(target) + 1) for _ in range(len(source) + 1)]
    for source_index, token in enumerate(source, start=1):
        for target_index, other in enumerate(target, start=1):
            lengths[source_index][target_index] = (
                lengths[source_index - 1][target_index - 1] + 1
                if token == other
                else max(lengths[source_index - 1][target_index], lengths[source_index][target_index - 1])
            )
    source_index, target_index = len(source), len(target)
    anchors: dict[int, int] = {}
    while source_index and target_index:
        if source[source_index - 1] == target[target_index - 1]:
            source_index -= 1
            target_index -= 1
            anchors[target_index] = source_index
        elif lengths[source_index - 1][target_index] >= lengths[source_index][target_index - 1]:
            source_index -= 1
        else:
            target_index -= 1
    return dict(sorted(anchors.items()))


def residual_gaps(
    exact: Mapping[int, int], source_size: int, target_size: int
) -> list[tuple[range, range]]:
    boundaries = [(-1, -1), *sorted(exact.items()), (target_size, source_size)]
    return [
        (range(left_source + 1, right_source), range(left_target + 1, right_target))
        for (left_target, left_source), (right_target, right_source) in zip(boundaries, boundaries[1:])
        if right_source > left_source + 1 and right_target > left_target + 1
    ]


def similarity_anchors(
    source_indices: Sequence[int],
    target_indices: Sequence[int],
    similarities: Sequence[Sequence[float]],
    *,
    threshold: float,
) -> dict[int, int]:
    """Maximum-score noncrossing residual matching above a cosine threshold."""

    if not math.isfinite(threshold) or not -1 <= threshold < 1:
        raise ValueError("Similarity threshold must be finite and in [-1, 1)")
    m, n = len(source_indices), len(target_indices)
    best = [[0.0] * (n + 1) for _ in range(m + 1)]
    steps = [[""] * (n + 1) for _ in range(m + 1)]
    for i, source_index in enumerate(source_indices, start=1):
        for j, target_index in enumerate(target_indices, start=1):
            similarity = float(similarities[source_index][target_index])
            if not math.isfinite(similarity) or not -1.00001 <= similarity <= 1.00001:
                raise ValueError("Transformer cosine similarity is not finite or outside [-1, 1]")
            score = best[i - 1][j]
            step = "delete"
            if best[i][j - 1] > score:
                score, step = best[i][j - 1], "insert"
            candidate = best[i - 1][j - 1] + similarity - threshold
            if similarity > threshold and candidate > score:
                score, step = candidate, "match"
            best[i][j], steps[i][j] = score, step
    matches: dict[int, int] = {}
    i, j = m, n
    while i and j:
        if steps[i][j] == "match":
            matches[target_indices[j - 1]] = source_indices[i - 1]
            i -= 1
            j -= 1
        elif steps[i][j] == "delete":
            i -= 1
        else:
            j -= 1
    return dict(sorted(matches.items()))


def link_residual_movements(
    source: Sequence[str], edits: Sequence[WordEdit], *, l_max: int
) -> list[WordEdit]:
    """Recognize unique exact U/M moves even when an intervening lexical edit exists."""

    deletions: dict[tuple[str, ...], list[int]] = {}
    insertions: dict[tuple[str, ...], list[int]] = {}
    for index, edit in enumerate(edits):
        if edit.comment != "NONE":
            continue
        if edit.edit_type == "U":
            material = tuple(source[edit.source_start:edit.source_end])
            deletions.setdefault(material, []).append(index)
        elif edit.edit_type == "M":
            insertions.setdefault(edit.correction, []).append(index)
    output = list(edits)
    next_link = len(edits) + 1
    for material, origins in deletions.items():
        destinations = insertions.get(material, [])
        if not material or len(origins) != 1 or len(destinations) != 1:
            continue
        origin_index, destination_index = origins[0], destinations[0]
        origin, destination = edits[origin_index], edits[destination_index]
        point = destination.source_start
        if origin.source_start <= point <= origin.source_end:
            continue
        if max(origin.source_end, point) - min(origin.source_start, point) <= l_max:
            continue
        link_id = f"w{next_link}"
        next_link += 1
        output[origin_index] = replace(origin, comment=origin_comment(link_id, point))
        output[destination_index] = replace(
            destination,
            comment=destination_comment(link_id, origin.source_start, origin.source_end),
        )
    return renumber_movement_links(source, output)


@dataclass(frozen=True)
class TokenAlignment:
    exact: dict[int, int]
    similarity: dict[int, int]
    cosine_scores: dict[int, float]

    @property
    def combined(self) -> dict[int, int]:
        return dict(sorted({**self.exact, **self.similarity}.items()))

    def to_json(self) -> dict[str, Any]:
        return {
            "exact": [[target, source] for target, source in sorted(self.exact.items())],
            "similarity": [
                {"target": target, "source": source, "cosine": self.cosine_scores[target]}
                for target, source in sorted(self.similarity.items())
            ],
        }

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> TokenAlignment:
        if not isinstance(value, dict) or set(value) != {"exact", "similarity"}:
            raise ValueError("Cached alignment must contain exact and similarity links")
        exact: dict[int, int] = {}
        fuzzy: dict[int, int] = {}
        scores: dict[int, float] = {}
        if not isinstance(value["exact"], list) or not isinstance(value["similarity"], list):
            raise ValueError("Cached alignment links must be arrays")
        for pair in value["exact"]:
            if not isinstance(pair, list) or len(pair) != 2 or any(type(index) is not int for index in pair):
                raise ValueError("Malformed cached exact link")
            target, source = pair
            if target in exact:
                raise ValueError("Duplicate target in cached exact links")
            exact[target] = source
        for link in value["similarity"]:
            if not isinstance(link, dict) or set(link) != {"source", "target", "cosine"}:
                raise ValueError("Malformed cached similarity link")
            source, target, score = link["source"], link["target"], link["cosine"]
            if type(source) is not int or type(target) is not int or type(score) not in (float, int):
                raise ValueError("Cached similarity link has invalid types")
            if target in exact or target in fuzzy or not math.isfinite(score) or not -1.00001 <= score <= 1.00001:
                raise ValueError("Duplicate or invalid cached similarity link")
            fuzzy[target] = source
            scores[target] = float(score)
        return cls(exact, fuzzy, scores)


def align_with_similarities(
    source: Sequence[str],
    target: Sequence[str],
    *,
    similarities: Sequence[Sequence[float]] | None,
    threshold: float = 0.60,
    exact: Mapping[int, int] | None = None,
) -> TokenAlignment:
    source = validate_tokens(source, context="alignment source")
    target = validate_tokens(target, context="alignment target")
    if not math.isfinite(threshold) or not -1 <= threshold < 1:
        raise ValueError("Similarity threshold must be finite and in [-1, 1)")
    anchors = dict(exact) if exact is not None else exact_token_anchors(source, target)
    previous_source = previous_target = -1
    for target_index, source_index in sorted(anchors.items()):
        if not (previous_source < source_index < len(source) and previous_target < target_index < len(target)):
            raise ValueError("Exact anchors must be in-range and strictly monotonic")
        if source[source_index] != target[target_index]:
            raise ValueError("Exact anchor tokens differ")
        previous_source, previous_target = source_index, target_index
    gaps = residual_gaps(anchors, len(source), len(target))
    if gaps:
        if similarities is None or len(similarities) != len(source) or any(
            len(row) != len(target) for row in similarities
        ):
            raise ValueError("Residual alignment requires a source-by-target similarity matrix")
    fuzzy: dict[int, int] = {}
    for source_indices, target_indices in gaps:
        assert similarities is not None
        fuzzy.update(similarity_anchors(source_indices, target_indices, similarities, threshold=threshold))
    return TokenAlignment(
        anchors, fuzzy,
        {target_index: float(similarities[source_index][target_index]) for target_index, source_index in fuzzy.items()},
    )


def generic_edits(
    source: Sequence[str], target: Sequence[str], alignment: TokenAlignment, *, l_max: int = 3
) -> list[WordEdit]:
    source = validate_tokens(source, context="edit source")
    target = validate_tokens(target, context="edit target")
    for target_index, source_index in alignment.exact.items():
        if not 0 <= source_index < len(source) or not 0 <= target_index < len(target):
            raise ValueError("Exact alignment index lies outside the token sequence")
        if source[source_index] != target[target_index]:
            raise ValueError("Exact alignment does not match identical tokens")
    edits = edits_from_token_alignment(source, target, alignment.combined, l_max=l_max)
    edits = separate_punctuation_edits(source, target, edits)
    edits = link_residual_movements(source, edits, l_max=l_max)
    if apply_word_edits(source, edits) != target:
        raise ValueError("Generic M2 edits do not reconstruct the original target tokens")
    for edit in edits:
        if edit_mixes_punctuation(source, edit):
            raise ValueError("Generic edit crosses a punctuation/lexical boundary")
        if edit.correction == ("-NONE-",):
            raise ValueError("A literal single-token -NONE- correction is ambiguous in standard M2")
        if edit.edit_type == "W" and Counter(source[edit.source_start:edit.source_end]) != Counter(edit.correction):
            raise ValueError("W must be an exact token permutation")
    return edits


def accumulate_subwords(
    totals: Any, counts: Any, hidden: Any, word_ids: Sequence[int | None]
) -> None:
    """Mean-pooling accumulator; offsets always refer to original supplied tokens."""

    import numpy as np

    hidden = np.asarray(hidden)
    if hidden.ndim != 2 or hidden.shape[0] < len(word_ids) or hidden.shape[1] != totals.shape[1]:
        raise ValueError("Subword hidden-state shape mismatch")
    positions = [index for index, word_id in enumerate(word_ids) if word_id is not None]
    indices = [word_ids[index] for index in positions]
    if any(type(index) is not int or not 0 <= index < len(totals) for index in indices):
        raise ValueError("Tokenizer word IDs do not match original token offsets")
    vectors = hidden[positions]
    if not np.isfinite(vectors).all():
        raise ValueError("Transformer returned non-finite embeddings")
    np.add.at(totals, indices, vectors)
    np.add.at(counts, indices, 1)


class TransformerTokenEncoder:
    """Offline-by-default contextual encoder with complete, nonoverlapping overflow windows."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        revision: str | None = None,
        device: str = "cpu",
        allow_download: bool = False,
        cache_size: int = 256,
        threads: int = 4,
    ) -> None:
        import numpy as np
        import torch
        from transformers import AutoModel, AutoTokenizer

        if cache_size < 0 or threads < 1:
            raise ValueError("Embedding cache size must be nonnegative and CPU threads positive")
        if revision is None and model_name == DEFAULT_MODEL:
            revision = DEFAULT_REVISION
        torch.set_num_threads(threads)
        torch.manual_seed(0)
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name, revision=revision, use_fast=True,
            local_files_only=not allow_download, trust_remote_code=False,
        )
        if not self.tokenizer.is_fast:
            raise ValueError("A fast tokenizer with original word_ids is required")
        self.model = AutoModel.from_pretrained(
            model_name, revision=revision, local_files_only=not allow_download,
            trust_remote_code=False, use_safetensors=True,
        )
        self.model.to(device)
        self.model.eval()
        limits = [
            value for value in (
                self.tokenizer.model_max_length,
                getattr(self.model.config, "max_position_embeddings", None),
            )
            if isinstance(value, int) and 2 < value < 100000
        ]
        if not limits:
            raise ValueError("Cannot establish the encoder's supported context length")
        self.max_length = min(limits)
        self.device = device
        self.cache_size = cache_size
        self.cache: OrderedDict[tuple[str, ...], Any] = OrderedDict()
        self.stats: Counter[str] = Counter()
        self.np = np
        self.torch = torch
        self.metadata: dict[str, Any] = {
            "model": model_name,
            "requested_revision": revision,
            "resolved_revision": getattr(self.model.config, "_commit_hash", None),
            "tokenizer": type(self.tokenizer).__name__,
            "model_type": self.model.config.model_type,
            "pooling": "mean final-layer hidden states over every subword of each original token",
            "long_inputs": "all nonoverlapping overflow windows; no input token truncation",
            "max_subwords_per_window_including_specials": self.max_length,
            "device": device,
            "threads": threads,
            "seed": 0,
            "model_eval": True,
            "torch": torch.__version__,
            "transformers": importlib.metadata.version("transformers"),
            "numpy": np.__version__,
        }
        local = Path(model_name)
        if local.is_dir():
            weights = sorted(local.glob("*.safetensors"))
            if not weights:
                raise ValueError("Local Transformer directory contains no safetensors weights")
            fingerprints = {}
            for path in [*weights, *sorted(local.glob("*.json")), *sorted(local.glob("vocab.*"))]:
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                fingerprints[path.name] = digest.hexdigest()
            self.metadata["local_model_sha256"] = fingerprints
        elif not self.metadata["resolved_revision"]:
            raise ValueError("The remote encoder did not report a resolved model revision")

    def get_many(self, texts: Sequence[Sequence[str]], *, batch_size: int) -> dict[tuple[str, ...], Any]:
        if batch_size < 1:
            raise ValueError("Transformer batch size must be positive")
        unique = list(dict.fromkeys(validate_tokens(text, context="encoder input") for text in texts))
        if any(not text for text in unique):
            raise ValueError("Empty inputs should not be sent to the Transformer encoder")
        result = {}
        missing = []
        for text in unique:
            if text in self.cache:
                result[text] = self.cache[text]
                self.cache.move_to_end(text)
                self.stats["embedding_cache_hits"] += 1
            else:
                missing.append(text)
        for start in range(0, len(missing), batch_size):
            batch = missing[start:start + batch_size]
            encoded = self.tokenizer(
                [list(text) for text in batch],
                is_split_into_words=True, padding=False, truncation=True,
                max_length=self.max_length, stride=0, return_overflowing_tokens=True,
                return_attention_mask=True,
            )
            sample_indices = encoded["overflow_to_sample_mapping"]
            hidden_size = getattr(self.model.config, "hidden_size", None)
            if not isinstance(hidden_size, int) or hidden_size < 1:
                raise ValueError("Encoder configuration has no valid hidden_size")
            totals = [self.np.zeros((len(text), hidden_size), dtype=self.np.float64) for text in batch]
            counts = [self.np.zeros(len(text), dtype=self.np.int64) for text in batch]
            for window_start in range(0, len(sample_indices), batch_size):
                window_end = min(window_start + batch_size, len(sample_indices))
                features = [
                    {key: encoded[key][index] for key in self.tokenizer.model_input_names if key in encoded}
                    for index in range(window_start, window_end)
                ]
                inputs = self.tokenizer.pad(features, padding=True, return_tensors="pt")
                inputs = {key: value.to(self.device) for key, value in inputs.items()}
                with self.torch.inference_mode():
                    hidden = self.model(**inputs).last_hidden_state.float().cpu().numpy()
                for batch_index, window_index in enumerate(range(window_start, window_end)):
                    sample = sample_indices[window_index]
                    word_ids = encoded.word_ids(batch_index=window_index)
                    accumulate_subwords(totals[sample], counts[sample], hidden[batch_index], word_ids)
                    self.stats["encoded_subwords"] += sum(word_id is not None for word_id in word_ids)
                    self.stats["unknown_subwords"] += sum(
                        word_id is not None and token_id == self.tokenizer.unk_token_id
                        for word_id, token_id in zip(word_ids, encoded["input_ids"][window_index])
                    )
            self.stats["encoded_windows"] += len(sample_indices)
            self.stats["encoded_sentences"] += len(batch)
            self.stats["overflow_sentences"] += sum(value > 1 for value in Counter(sample_indices).values())
            for text, sums, count in zip(batch, totals, counts):
                if self.np.any(count == 0):
                    raise ValueError("Tokenizer dropped an original token; refusing truncated alignment")
                embeddings = (sums / count[:, None]).astype(self.np.float32)
                norms = self.np.linalg.norm(embeddings, axis=1, keepdims=True)
                if self.np.any(norms == 0) or not self.np.isfinite(norms).all():
                    raise ValueError("Transformer produced invalid token embedding norms")
                embeddings /= norms
                result[text] = embeddings
                if self.cache_size:
                    self.cache[text] = embeddings
                    self.cache.move_to_end(text)
                    while len(self.cache) > self.cache_size:
                        self.cache.popitem(last=False)
        return result


class TransformerTokenAligner:
    def __init__(self, encoder: TransformerTokenEncoder, *, threshold: float = 0.60, l_max: int = 3) -> None:
        if not math.isfinite(threshold) or not -1 <= threshold < 1 or l_max < 2:
            raise ValueError("Invalid similarity threshold or word-order envelope limit")
        self.encoder = encoder
        self.threshold = threshold
        self.l_max = l_max
        self.metadata = {
            "implementation": IMPLEMENTATION_VERSION,
            "encoder": encoder.metadata,
            "similarity_threshold": threshold,
            "l_max_tokens": l_max,
            "exact_alignment": "LCS, deletion-first ties",
            "residual_alignment": "monotonic maximum sum of cosine-minus-threshold within exact-anchor gaps",
            "movement_policy": "exact permutation W; unique long U/M block moves linked and scored once as WO",
            "edit_policy": EDIT_POLICY,
            "edit_refinement": "separate standalone Unicode punctuation/symbol tokens from words in every source/correction span",
        }

    def convert_many(
        self, pairs: Sequence[tuple[Sequence[str], Sequence[str]]], *, batch_size: int = 16
    ) -> list[tuple[list[WordEdit], TokenAlignment]]:
        prepared = []
        needs_embeddings = []
        for source, target in pairs:
            source = validate_tokens(source, context="alignment source")
            target = validate_tokens(target, context="alignment target")
            exact = exact_token_anchors(source, target)
            gaps = residual_gaps(exact, len(source), len(target))
            prepared.append((source, target, exact, gaps))
            if gaps:
                needs_embeddings.extend((source, target))
        embeddings = self.encoder.get_many(needs_embeddings, batch_size=batch_size) if needs_embeddings else {}
        results = []
        for source, target, exact, gaps in prepared:
            similarities = (embeddings[source] @ embeddings[target].T).tolist() if gaps else None
            alignment = align_with_similarities(
                source, target, similarities=similarities, threshold=self.threshold, exact=exact
            )
            results.append((generic_edits(source, target, alignment, l_max=self.l_max), alignment))
        return results
