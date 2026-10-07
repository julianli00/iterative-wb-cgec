from __future__ import annotations

import itertools
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts import generic_m2
from scripts.generic_m2 import (
    FrozenAlignmentAligner,
    PairCache,
    audit_generated,
    convert_file,
    file_sha256,
    pair_key,
    render_record,
)
from scripts.movement_aware_compare import parse_block, scored_edits
from scripts.projection_word_m2 import apply_word_edits, edits_from_token_alignment
from scripts.punctuation_m2 import EDIT_POLICY, edit_mixes_punctuation, is_punctuation_token
from scripts.tokenized_m2 import Reference, TokenizedRecord, iter_m2
from scripts.transformer_token_alignment import TokenAlignment, exact_token_anchors, generic_edits


FROZEN_CONFIG = {
    "implementation": "generic-token-mruw-v1",
    "encoder": {"model": "fixture"},
    "similarity_threshold": 0.6,
    "l_max_tokens": 3,
    "exact_alignment": "LCS, deletion-first ties",
    "residual_alignment": "monotonic maximum sum of cosine-minus-threshold within exact-anchor gaps",
}


class PunctuationM2Tests(unittest.TestCase):
    def annotate(self, source, target, *, aligned=None):
        alignment = TokenAlignment(
            exact_token_anchors(source, target) if aligned is None else {},
            {} if aligned is None else aligned,
            {} if aligned is None else {index: 0.9 for index in aligned},
        )
        edits = generic_edits(source, target, alignment)
        self.assertEqual(apply_word_edits(source, edits), tuple(target))
        self.assertTrue(all(not edit_mixes_punctuation(source, edit) for edit in edits))
        return edits

    def test_synthetic_it_capitalization_example(self) -> None:
        source = tuple("This synthetic example places a boundary after several tokens , it ends here .".split())
        target = (*source[:9], ".", "It", *source[11:])
        edits = self.annotate(source, target, aligned={i: i for i in range(len(source))})
        record = TokenizedRecord("1", source, (Reference(0, target),))
        text = render_record(record, [edits])
        self.assertIn("A 9 10|||R|||.|||-REQUIRED-|||NONE|||0", text)
        self.assertIn("A 10 11|||R|||It|||-REQUIRED-|||NONE|||0", text)
        self.assertNotIn("A 9 11|||", text)

    def test_synthetic_however_capitalization_example(self) -> None:
        source = tuple("This synthetic sentence contains some extra context so that the next boundary appears here , however , we still preserve every token .".split())
        target = (*source[:14], ".", "However", *source[16:])
        edits = self.annotate(source, target, aligned={i: i for i in range(len(source))})
        text = render_record(TokenizedRecord("2", source, (Reference(0, target),)), [edits])
        self.assertIn("A 14 15|||R|||.|||-REQUIRED-|||NONE|||0", text)
        self.assertIn("A 15 16|||R|||However|||-REQUIRED-|||NONE|||0", text)
        self.assertNotIn("A 14 16|||", text)

    def test_mixed_unaligned_gap_is_split_not_only_adjacent_replacements(self) -> None:
        edits = self.annotate((",", "however"), (".", "However"))
        self.assertEqual([(e.source_start, e.source_end, e.correction) for e in edits], [(0, 1, (".",)), (1, 2, ("However",))])

    def test_lexical_multiword_replacement_is_still_grouped(self) -> None:
        edits = self.annotate(
            ("We", "utilise", "mass", "transport", "."),
            ("We", "use", "public", "transport", "."),
            aligned={i: i for i in range(5)},
        )
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].edit_type, "R")
        self.assertEqual((edits[0].source_start, edits[0].source_end), (1, 3))
        self.assertEqual(edits[0].correction, ("use", "public"))

    def test_punctuation_breaks_a_larger_gap_into_lexical_runs(self) -> None:
        source = ("old", "phrase", ",", "other", "words")
        target = ("new", "expression", ".", "different", "words")
        edits = self.annotate(source, target)
        self.assertTrue(any(len(edit.correction) > 1 for edit in edits))
        self.assertTrue(any(edit.correction == (".",) for edit in edits))

    def test_mixed_insertions_and_deletions_are_split(self) -> None:
        target = (".", "However", "sometimes", ",")
        insertions = self.annotate((), target)
        self.assertEqual([e.correction for e in insertions], [(".",), ("However", "sometimes"), (",",)])
        self.assertEqual([e.edit_type for e in insertions], ["M"] * 3)
        deletions = self.annotate(target, ())
        self.assertEqual([(e.source_start, e.source_end) for e in deletions], [(0, 1), (1, 3), (3, 4)])
        self.assertEqual([e.edit_type for e in deletions], ["U"] * 3)

    def test_punctuation_appearing_only_on_one_side_does_not_join_words(self) -> None:
        for source, target in (
            (("old", "words"), ("new", ",", "expression")),
            (("old", ",", "words"), ("new", "expression")),
            ((",",), ("However",)),
            (("However",), (".",)),
        ):
            with self.subTest(source=source, target=target):
                self.annotate(source, target)

    def test_punctuation_inside_a_token_is_not_retokenized(self) -> None:
        for token in ("can't", "mother-in-law", "3.14", "'s", "word,", "中文。"):
            self.assertFalse(is_punctuation_token(token), token)
        for token in (",", ".", "—", "...", "。", "，", "¿", "«", "$", "+", "。️"):
            self.assertTrue(is_punctuation_token(token), token)
        source = ("can't", "3.14")
        target = ("cannot", "3.15")
        edits = self.annotate(source, target, aligned={0: 0, 1: 1})
        self.assertEqual(edits[0].correction, target)

    def test_chinese_and_arabic_standalone_punctuation(self) -> None:
        for source, target in (
            (("你好", "，", "他"), ("您好", "。", "她")),
            (("你", "好", "，", "他"), ("您", "好", "。", "她")),
            (("هذا", "،", "نص"), ("هذه", "؛", "جملة")),
        ):
            with self.subTest(source=source):
                self.annotate(source, target)

    def test_word_order_never_reintroduces_mixed_spans(self) -> None:
        edits = self.annotate(("left", ",", "right"), ("right", ",", "left"))
        self.assertTrue(all(not edit_mixes_punctuation(("left", ",", "right"), edit) for edit in edits))

    def test_mixed_linked_movement_is_split_and_relinked_safely(self) -> None:
        source = ("Yesterday", ",", "I", "saw", "the", "bird", ".")
        target = ("I", "saw", "the", "bird", "Yesterday", ",", ".")
        edits = self.annotate(source, target)
        text = render_record(TokenizedRecord("1", source, (Reference(0, target),)), [edits])
        self.assertTrue(scored_edits(parse_block(text, unit="word"), unit="word"))
        self.assertTrue(any("LINK=" in edit.comment for edit in edits))

    def test_shared_historical_word_pipeline_still_has_its_original_merger(self) -> None:
        source, target = (",", "it"), (".", "It")
        edits = edits_from_token_alignment(source, target, {0: 0, 1: 1})
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].correction, (".", "It"))

    def test_exhaustive_punctuation_and_word_token_roundtrips(self) -> None:
        sequences = [tuple(seq) for size in range(4) for seq in itertools.product(("a", "b", ","), repeat=size)]
        for source, target in itertools.product(sequences, repeat=2):
            self.annotate(source, target)

    def test_audit_can_reject_old_mixed_edits_without_rejecting_legacy_structural_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            m2, pairs = root / "old.m2", root / "pairs.jsonl"
            record = TokenizedRecord("1", (",", "it"), (Reference(0, (".", "It")),))
            pairs.write_text(json.dumps(record.to_json()) + "\n")
            m2.write_text("S , it\nA 0 2|||R|||. It|||-REQUIRED-|||NONE|||0\n")
            self.assertEqual(audit_generated(m2, pairs)["mixed_punctuation_lexical_edits"], 1)
            with self.assertRaisesRegex(ValueError, "mixes punctuation"):
                audit_generated(m2, pairs, require_separate_punctuation=True)

    def make_snapshot(self, path, source, target):
        cache = PairCache(path, FROZEN_CONFIG)
        alignment = TokenAlignment(exact_token_anchors(source, target), {}, {})
        # Deliberately unusable old edit labels: relabeling must use only the frozen links.
        cache.put(source, target, {"edits": "not used", "alignment": alignment.to_json()})
        cache.commit()
        cache.close()

    def test_frozen_cache_relabels_without_loading_a_transformer_or_modifying_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = (",", "it"), (".", "It")
            snapshot = root / "old.sqlite3"
            self.make_snapshot(snapshot, source, target)
            before = file_sha256(snapshot)
            pairs = root / "pairs.jsonl"
            pairs.write_text(json.dumps(TokenizedRecord("1", source, (Reference(7, target),)).to_json()) + "\n")
            with mock.patch("scripts.generic_m2.TransformerTokenEncoder", side_effect=AssertionError("no encoder calls")):
                aligner = FrozenAlignmentAligner(snapshot)
                cache = PairCache(root / "new.sqlite3", aligner.metadata)
                try:
                    report = convert_file(pairs, input_format="jsonl", output_dir=root / "out", aligner=aligner, cache=cache)
                    self.assertEqual(report["validation"]["mixed_punctuation_lexical_edits"], 0)
                    self.assertEqual(aligner.metadata["edit_policy"], EDIT_POLICY)
                    restored = list(iter_m2(root / "out/pairs.generic.m2"))
                    self.assertEqual(restored[0].references[0].target_tokens, target)
                finally:
                    cache.close()
                    aligner.close()
            self.assertEqual(file_sha256(snapshot), before)

    def test_missing_frozen_pair_is_not_recomputed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.sqlite3"
            self.make_snapshot(path, ("a",), ("b",))
            aligner = FrozenAlignmentAligner(path)
            try:
                with self.assertRaisesRegex(ValueError, "no inference fallback"):
                    aligner.convert_many([(("missing",), ("pair",))])
            finally:
                aligner.close()

    def test_invalid_cached_links_fail_closed(self) -> None:
        bad = [
            {"exact": [[0, 0], [0, 1]], "similarity": []},
            {"exact": [[0, 0]], "similarity": [{"target": 0, "source": 1, "cosine": 0.9}]},
            {"exact": [], "similarity": [{"target": 0, "source": 0, "cosine": float("nan")}]},
        ]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                TokenAlignment.from_json(value)

    def test_changed_frozen_cache_marks_run_failed_before_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "source.sqlite3"
            self.make_snapshot(snapshot, ("a",), ("b",))
            pairs = root / "input.jsonl"
            pairs.write_text(json.dumps(TokenizedRecord("1", ("a",), (Reference(0, ("b",)),)).to_json()) + "\n")
            args = SimpleNamespace(
                command="relabel", inputs=[pairs], output_dir=root / "out",
                input_format="jsonl", batch_size=1, overwrite=False,
                alignment_cache=snapshot, l_max=3, cache=None,
            )
            convert = generic_m2.convert_file

            def concurrent_change(*args, **kwargs):
                result = convert(*args, **kwargs)
                with snapshot.open("ab") as stream:
                    stream.write(b"concurrent change")
                return result

            with (
                mock.patch.object(generic_m2, "parse_args", return_value=args),
                mock.patch.object(generic_m2, "convert_file", side_effect=concurrent_change),
            ):
                with self.assertRaisesRegex(ValueError, "changed during relabeling"):
                    generic_m2.main()
            config = json.loads((root / "out/run_config.json").read_text())
            self.assertEqual(config["status"], "failed")
            self.assertNotIn("completed_utc", config)


if __name__ == "__main__":
    unittest.main()
