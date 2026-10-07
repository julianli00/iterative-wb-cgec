from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.tokenized_m2 import (
    Reference,
    TokenizedRecord,
    iter_m2,
    iter_pairs_jsonl,
    iter_pairs_tsv,
    parse_m2_block,
    validate_tokens,
)


class TokenizedM2Tests(unittest.TestCase):
    def parse(self, text: str):
        return parse_m2_block(text.splitlines(), identifier="1", context="fixture")

    def test_insertions_use_original_offsets_and_keep_file_order(self) -> None:
        record = self.parse(
            "S I go school .\n"
            "A 2 2|||M:PREP|||to|||REQUIRED|||-NONE-|||0\n"
            "A 0 0|||M:ADV|||Usually|||REQUIRED|||-NONE-|||0\n"
            "A 2 2|||M:DET|||the|||REQUIRED|||-NONE-|||0\n"
            "A 1 2|||R:VERB|||went|||REQUIRED|||-NONE-|||0"
        )
        self.assertEqual(record.references[0].target_tokens, ("Usually", "I", "went", "to", "the", "school", "."))
        self.assertEqual(record.source_tokens, ("I", "go", "school", "."))

    def test_reference_ids_and_order_are_preserved_including_noop(self) -> None:
        record = self.parse(
            "S I go .\n"
            "A -1 -1|||noop|||-NONE-|||REQUIRED|||-NONE-|||7\n"
            "A 1 2|||R:VERB|||went|||REQUIRED|||-NONE-|||2\n"
            "A 0 0|||M:ADV|||Yesterday|||REQUIRED|||-NONE-|||2\n"
            "A 1 2|||R:OTHER|||go|||REQUIRED|||-NONE-|||9"
        )
        self.assertEqual([r.annotator_id for r in record.references], [7, 2, 9])
        self.assertEqual(record.references[0].target_tokens, record.source_tokens)
        self.assertEqual(record.references[1].target_tokens, ("Yesterday", "I", "went", "."))
        self.assertEqual(record.references[2].target_tokens, record.source_tokens)

    def test_unknown_annotations_are_preserved_as_provenance_not_applied(self) -> None:
        record = self.parse(
            "S Hard text .\n"
            "A 0 1|||UNK|||Hard|||REQUIRED|||-NONE-|||0\n"
            "A 1 2|||R:NOUN|||sentence|||REQUIRED|||-NONE-|||0"
        )
        self.assertEqual(record.references[0].target_tokens, ("Hard", "sentence", "."))
        self.assertEqual(record.references[0].skipped_annotations[0].label, "UNK")

    def test_empty_and_identity_sentences_are_representable(self) -> None:
        self.assertEqual(self.parse("S ").references[0].target_tokens, ())
        self.assertEqual(self.parse("S word").references[0].target_tokens, ("word",))
        insertion = self.parse("S \nA 0 0|||M|||word|||REQUIRED|||-NONE-|||0")
        self.assertEqual(insertion.references[0].target_tokens, ("word",))
        deletion = self.parse("S word\nA 0 1|||U|||-NONE-|||REQUIRED|||-NONE-|||0")
        self.assertEqual(deletion.references[0].target_tokens, ())

    def test_language_independent_extraction_preserves_case_punctuation_and_substrings(self) -> None:
        record = self.parse(
            "S 我 喜歡 NLP ##token café 。\n"
            "A 1 2|||R|||喜欢|||REQUIRED|||-NONE-|||0"
        )
        self.assertEqual(record.references[0].target_tokens, ("我", "喜欢", "NLP", "##token", "café", "。"))
        self.assertEqual(record.source_tokens[1], "喜歡")

    def test_linked_edits_apply_simultaneously(self) -> None:
        record = self.parse(
            "S Slowly I crossed the room .\n"
            "A 0 1|||U|||-NONE-|||-REQUIRED-|||LINK=w1;TO=5|||4\n"
            "A 5 5|||M|||Slowly|||-REQUIRED-|||LINK=w1;FROM=0:1|||4"
        )
        self.assertEqual(record.references[0].target_tokens, ("I", "crossed", "the", "room", "Slowly", "."))

    def test_overlapping_edits_fail_instead_of_losing_corrections(self) -> None:
        with self.assertRaisesRegex(ValueError, "overlapping"):
            self.parse(
                "S I go school .\n"
                "A 0 2|||R|||We went|||REQUIRED|||-NONE-|||0\n"
                "A 1 2|||R|||went|||REQUIRED|||-NONE-|||0"
            )

    def test_invalid_m2_records_fail_with_context(self) -> None:
        fixtures = [
            "S I go\nA 0 3|||R|||We|||REQUIRED|||-NONE-|||0",
            "S I go\nA -1 -1|||R|||We|||REQUIRED|||-NONE-|||0",
            "S I go\nA 0 0|||noop|||-NONE-|||REQUIRED|||-NONE-|||0",
            "S I go\nA 0 1|||R|||We|||OPTIONAL|||-NONE-|||0",
            "S I go\nA 0 1|||R|||We|||REQUIRED|||-NONE-|||-1",
            "S I go\nT I went",
            "S I go\nA -1 -1|||noop|||-NONE-|||REQUIRED|||-NONE-|||0\nA 1 2|||R|||went|||REQUIRED|||-NONE-|||0",
        ]
        for text in fixtures:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "fixture"):
                self.parse(text)

    def test_streaming_handles_bom_crlf_and_missing_final_blank_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.m2"
            path.write_bytes(b"\xef\xbb\xbfS A\r\n\r\n\r\nS B\r\nA -1 -1|||noop|||-NONE-|||REQUIRED|||-NONE-|||0")
            records = list(iter_m2(path))
        self.assertEqual([r.identifier for r in records], ["1", "2"])
        self.assertEqual([r.source_tokens for r in records], [("A",), ("B",)])

    def test_jsonl_roundtrip_preserves_annotators_and_skipped_records(self) -> None:
        record = self.parse("S A B\nA 0 1|||UNK|||A|||REQUIRED|||-NONE-|||3")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pairs.jsonl"
            path.write_text(json.dumps(record.to_json()) + "\n")
            self.assertEqual(list(iter_pairs_jsonl(path)), [record])
            path.write_text((json.dumps(record.to_json()) + "\n") * 2)
            with self.assertRaisesRegex(ValueError, "duplicate record ID"):
                list(iter_pairs_jsonl(path))

    def test_tokenized_tsv_keeps_empty_targets_and_multiple_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pairs.tsv"
            path.write_text("I go .\tI went .\tI go .\nword\t\n\tword\n")
            records = list(iter_pairs_tsv(path))
        self.assertEqual(len(records[0].references), 2)
        self.assertEqual(records[1].references[0].target_tokens, ())
        self.assertEqual(records[2].source_tokens, ())
        self.assertEqual(records[2].references[0].target_tokens, ("word",))

    def test_invalid_token_units_and_duplicate_reference_ids_fail(self) -> None:
        for tokens in ("not an array", ["two words"], [""], ["a|||b"], [None]):
            with self.subTest(tokens=tokens), self.assertRaises(ValueError):
                validate_tokens(tokens, context="fixture")
        with self.assertRaisesRegex(ValueError, "duplicate annotator ID"):
            TokenizedRecord("x", ("a",), (Reference(0, ("b",)), Reference(0, ("c",)))).validate()

    def test_jsonl_rejects_invalid_skipped_annotation_provenance(self) -> None:
        record = self.parse("S a\nA 0 1|||UNK|||a|||REQUIRED|||-NONE-|||3")
        value = record.to_json()
        value["references"][0]["skipped_annotations"][0]["annotator_id"] = 4
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pairs.jsonl"
            path.write_text(json.dumps(value) + "\n")
            with self.assertRaisesRegex(ValueError, "invalid skipped annotation"):
                list(iter_pairs_jsonl(path))


if __name__ == "__main__":
    unittest.main()
