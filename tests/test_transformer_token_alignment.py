from __future__ import annotations

import itertools
import random
import unittest

import numpy as np

from scripts.movement_aware_compare import parse_block, scored_edits
from scripts.projection_word_m2 import apply_word_edits
from scripts.tokenized_m2 import Reference, TokenizedRecord, parse_m2_block
from scripts.generic_m2 import render_record
from scripts.transformer_token_alignment import (
    TransformerTokenAligner,
    accumulate_subwords,
    align_with_similarities,
    exact_token_anchors,
    generic_edits,
    similarity_anchors,
)


class FakeEncoder:
    metadata = {"model": "test-encoder"}

    def __init__(self) -> None:
        self.calls = []

    def get_many(self, texts, *, batch_size):
        self.calls.append(list(texts))
        vocabulary = sorted({token for text in texts for token in text})
        index = {token: i for i, token in enumerate(vocabulary)}
        vectors = np.eye(len(vocabulary), dtype=np.float32)
        return {tuple(text): vectors[[index[token] for token in text]] for text in texts}


class TransformerTokenAlignmentTests(unittest.TestCase):
    def align(self, source, target, similarities=None):
        return align_with_similarities(source, target, similarities=similarities, threshold=0.6)

    def test_exact_anchor_indices_refer_to_supplied_tokens(self) -> None:
        source = ("我", "喜欢", "the", "café")
        target = ("我", "喜爱", "the", "café")
        self.assertEqual(exact_token_anchors(source, target), {0: 0, 2: 2, 3: 3})

    def test_similarity_controls_residual_alignment(self) -> None:
        source = ("I", "eat", "foods", ".")
        target = ("I", "usually", "consume", "food", ".")
        similarities = [[0.0] * len(target) for _ in source]
        similarities[1][2] = 0.95
        similarities[2][3] = 0.90
        alignment = self.align(source, target, similarities)
        self.assertEqual(alignment.exact, {0: 0, 4: 3})
        self.assertEqual(alignment.similarity, {2: 1, 3: 2})
        edits = generic_edits(source, target, alignment)
        self.assertEqual([edit.edit_type for edit in edits], ["M", "R"])
        self.assertEqual(edits[0].correction, ("usually",))
        self.assertEqual(edits[1].correction, ("consume", "food"))
        self.assertEqual(apply_word_edits(source, edits), target)

    def test_similarity_cannot_cross_an_exact_anchor(self) -> None:
        source, target = ("A", "fixed", "B"), ("X", "fixed", "Y")
        similarities = [[0.0, 0.0, 0.99], [0.0, 1.0, 0.0], [0.99, 0.0, 0.0]]
        alignment = self.align(source, target, similarities)
        self.assertEqual(alignment.exact, {1: 1})
        self.assertEqual(alignment.similarity, {})

    def test_residual_matches_are_noncrossing_and_above_threshold(self) -> None:
        scores = [[0.7, 0.99], [0.98, 0.7]]
        result = similarity_anchors([0, 1], [0, 1], scores, threshold=0.6)
        self.assertEqual(result, {1: 0})
        self.assertEqual(similarity_anchors([0], [0], [[0.6]], threshold=0.6), {})

    def test_invalid_or_missing_similarities_are_explicit_errors(self) -> None:
        for scores in (None, [[0.9, 0.3]], [[float("nan")]], [[2.0]]):
            with self.subTest(scores=scores), self.assertRaises(ValueError):
                self.align(("old",), ("new",), scores)
        with self.assertRaises(ValueError):
            align_with_similarities(("a",), ("a",), similarities=None, exact={0: 2})

    def test_short_permutation_and_long_movement(self) -> None:
        for source, target, categories in (
            (("I", "am", "here"), ("I", "here", "am"), ["W"]),
            (("Slowly", "I", "crossed", "the", "room"), ("I", "crossed", "the", "room", "Slowly"), ["U", "M"]),
            (("我", "很", "喜欢", "这些", "书"), ("很", "喜欢", "这些", "书", "我"), ["U", "M"]),
        ):
            with self.subTest(source=source):
                alignment = self.align(source, target)
                edits = generic_edits(source, target, alignment)
                self.assertEqual([edit.edit_type for edit in edits], categories)
                self.assertEqual(apply_word_edits(source, edits), target)
                if categories == ["U", "M"]:
                    text = render_record(TokenizedRecord("1", source, (Reference(4, target),)), [edits])
                    logical = scored_edits(parse_block(text, unit="word"), unit="word")
                    self.assertEqual(len(logical[4]), 1)
                    self.assertEqual(next(iter(logical[4].values())), ["W-LD"])

    def test_long_movement_with_an_intervening_replacement_is_linked(self) -> None:
        source = ("Yesterday", "I", "see", "a", "bird", ".")
        target = ("I", "saw", "a", "bird", "Yesterday", ".")
        similarities = [[0.0] * len(target) for _ in source]
        similarities[2][1] = 0.95
        edits = generic_edits(source, target, self.align(source, target, similarities))
        self.assertEqual([edit.edit_type for edit in edits], ["U", "R", "M"])
        self.assertEqual(edits[0].comment, "LINK=w1;TO=5")
        self.assertEqual(edits[2].comment, "LINK=w1;FROM=0:1")
        self.assertEqual(apply_word_edits(source, edits), target)

    def test_repeated_tokens_are_not_mistaken_for_a_permutation(self) -> None:
        source, target = ("a", "a", "b"), ("a", "b", "b")
        similarities = [[0.0] * 3 for _ in source]
        edits = generic_edits(source, target, self.align(source, target, similarities))
        self.assertNotIn("W", [edit.edit_type for edit in edits])
        self.assertEqual(apply_word_edits(source, edits), target)

    def test_pure_insert_delete_identity_need_no_encoder(self) -> None:
        encoder = FakeEncoder()
        aligner = TransformerTokenAligner(encoder)
        pairs = [((), ("a",)), (("a",), ()), (("a",), ("a",))]
        results = aligner.convert_many(pairs)
        self.assertEqual(encoder.calls, [])
        for (source, target), (edits, _) in zip(pairs, results):
            self.assertEqual(apply_word_edits(source, edits), target)

    def test_character_and_word_input_preserve_the_supplied_granularity(self) -> None:
        encoder = FakeEncoder()
        aligner = TransformerTokenAligner(encoder)
        pairs = [
            (tuple("我爱饭"), tuple("我爱吃饭")),
            (("我", "爱", "饭"), ("我", "爱", "吃饭")),
            (("They", "go", "."), ("They", "went", ".")),
            (("Je", "suis", "ici", "."), ("Nous", "sommes", "ici", ".")),
            (("café", "##literal"), ("Café", "##literal")),
        ]
        results = aligner.convert_many(pairs)
        for (source, target), (edits, _) in zip(pairs, results):
            text = render_record(TokenizedRecord("1", source, (Reference(0, target),)), [edits])
            reconstructed = parse_m2_block(text.splitlines(), identifier="1", context="test")
            self.assertEqual(reconstructed.source_tokens, source)
            self.assertEqual(reconstructed.references[0].target_tokens, target)

    def test_pooling_averages_all_subwords_across_overflow_windows(self) -> None:
        totals = np.zeros((3, 2), dtype=np.float64)
        counts = np.zeros(3, dtype=np.int64)
        accumulate_subwords(totals, counts, np.array([[99, 99], [2, 4], [4, 6], [8, 10], [99, 99]]), [None, 0, 0, 1, None])
        accumulate_subwords(totals, counts, np.array([[99, 99], [10, 12], [6, 8], [99, 99]]), [None, 1, 2, None])
        np.testing.assert_array_equal(counts, [2, 2, 1])
        np.testing.assert_allclose(totals / counts[:, None], [[3, 5], [9, 11], [6, 8]])
        with self.assertRaisesRegex(ValueError, "word IDs"):
            accumulate_subwords(totals, counts, np.ones((1, 2)), [3])

    def test_exhaustive_small_token_sequences_roundtrip(self) -> None:
        sequences = [tuple(sequence) for size in range(4) for sequence in itertools.product(("a", "b"), repeat=size)]
        for source, target in itertools.product(sequences, repeat=2):
            scores = [[0.7] * len(target) for _ in source]
            edits = generic_edits(source, target, self.align(source, target, scores))
            self.assertEqual(apply_word_edits(source, edits), target, (source, target))

    def test_seeded_mixed_script_pairs_roundtrip_through_serialized_m2(self) -> None:
        randomizer = random.Random(20261006)
        vocabulary = ("a", "A", "中", "é", "هذا", ".", "word")
        for index in range(250):
            source = tuple(randomizer.choices(vocabulary, k=randomizer.randrange(10)))
            target = tuple(randomizer.choices(vocabulary, k=randomizer.randrange(10)))
            scores = [[randomizer.random() for _ in target] for _ in source]
            alignment = self.align(source, target, scores)
            edits = generic_edits(source, target, alignment)
            record = TokenizedRecord(str(index), source, (Reference(7, target),))
            rendered = render_record(record, [edits])
            restored = parse_m2_block(rendered.splitlines(), identifier=str(index), context="random fixture")
            self.assertEqual(restored.source_tokens, source)
            self.assertEqual(restored.references[0].target_tokens, target)
            self.assertEqual(restored.references[0].annotator_id, 7)


if __name__ == "__main__":
    unittest.main()
