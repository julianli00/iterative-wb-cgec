from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts import generic_m2
from scripts.generic_m2 import PairCache, audit_generated, convert_file, file_sha256
from scripts.tokenized_m2 import iter_pairs_jsonl, iter_pairs_tsv
from scripts.transformer_token_alignment import TokenAlignment, exact_token_anchors, generic_edits


class ExactFixtureAligner:
    metadata = {"fixture": "exact"}

    def __init__(self) -> None:
        self.converted = 0

    def convert_many(self, pairs, *, batch_size):
        result = []
        for source, target in pairs:
            alignment = TokenAlignment(exact_token_anchors(source, target), {}, {})
            result.append((generic_edits(source, target, alignment), alignment))
            self.converted += 1
        return result


class GenericM2Tests(unittest.TestCase):
    def test_full_extract_generate_and_audit_preserves_multiple_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.m2"
            source.write_text(
                "S I go school .\n"
                "A 2 2|||M:PREP|||to|||REQUIRED|||-NONE-|||7\n"
                "A 2 2|||M:DET|||the|||REQUIRED|||-NONE-|||7\n"
                "A -1 -1|||noop|||-NONE-|||REQUIRED|||-NONE-|||3\n\n"
                "S Slowly I crossed the room .\n"
                "A 0 1|||U:ADV|||-NONE-|||REQUIRED|||-NONE-|||0\n"
                "A 5 5|||M:ADV|||Slowly|||REQUIRED|||-NONE-|||0\n",
                encoding="utf-8",
            )
            digest = file_sha256(source)
            out = root / "out"
            aligner = ExactFixtureAligner()
            cache = PairCache(root / "cache.sqlite3", aligner.metadata)
            try:
                report = convert_file(source, input_format="m2", output_dir=out, aligner=aligner, cache=cache)
                self.assertEqual(report["validation"]["sources"], 2)
                self.assertEqual(report["validation"]["references"], 3)
                self.assertEqual(report["validation"]["logical_operations"]["WO"], 1)
                self.assertEqual(file_sha256(source), digest)
                pairs = list(iter_pairs_jsonl(out / "input.pairs.jsonl"))
                self.assertEqual([ref.annotator_id for ref in pairs[0].references], [7, 3])
                self.assertEqual(pairs[0].references[0].target_tokens, ("I", "go", "to", "the", "school", "."))
                old_calls = aligner.converted
                second = convert_file(source, input_format="m2", output_dir=root / "second", aligner=aligner, cache=cache)
                self.assertEqual(aligner.converted, old_calls)
                self.assertEqual(second["counts"]["reused_pairs"], 3)
                self.assertEqual((out / "input.generic.m2").read_bytes(), (root / "second/input.generic.m2").read_bytes())
            finally:
                cache.close()

    def test_extract_outputs_can_be_reused_without_m2_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "fixture.m2"
            source.write_text("S a b\nA 0 2|||R:OTHER|||b a|||REQUIRED|||-NONE-|||4\n")
            report = convert_file(source, input_format="m2", output_dir=root / "extract")
            self.assertNotIn("m2", report["outputs"])
            jsonl = root / "extract/fixture.pairs.jsonl"
            records = list(iter_pairs_jsonl(jsonl))
            tsv_records = list(iter_pairs_tsv(root / "extract/fixture.pairs.tsv"))
            self.assertEqual(records[0].source_tokens, tsv_records[0].source_tokens)
            self.assertEqual(records[0].references[0].target_tokens, tsv_records[0].references[0].target_tokens)
            aligner = ExactFixtureAligner()
            cache = PairCache(root / "cache.sqlite3", aligner.metadata)
            try:
                generated = convert_file(jsonl, input_format="jsonl", output_dir=root / "generated", aligner=aligner, cache=cache)
                self.assertEqual(generated["validation"]["logical_operations"], {"W": 1})
                text = (root / "generated/fixture.generic.m2").read_text()
                self.assertIn("|||4", text)
            finally:
                cache.close()

    def test_extract_empty_target_survives_tsv_and_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "fixture.tsv"
            source.write_text("word\t\n")
            report = convert_file(source, input_format="tsv", output_dir=root / "out")
            self.assertEqual(report["counts"]["references"], 1)
            self.assertEqual(list(iter_pairs_tsv(root / "out/fixture.pairs.tsv"))[0].references[0].target_tokens, ())
            self.assertEqual(list(iter_pairs_jsonl(root / "out/fixture.pairs.jsonl"))[0].references[0].target_tokens, ())

    def test_incompatible_cache_settings_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.sqlite3"
            cache = PairCache(path, {"threshold": 0.6})
            cache.close()
            with self.assertRaisesRegex(ValueError, "configuration differs"):
                PairCache(path, {"threshold": 0.7})

    def test_failure_does_not_publish_partial_outputs_or_change_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invalid.m2"
            source.write_text("S a\n\nS b\nA 9 10|||R|||c|||REQUIRED|||-NONE-|||0\n")
            before = file_sha256(source)
            with self.assertRaisesRegex(ValueError, "invalid source token span"):
                convert_file(source, input_format="m2", output_dir=root / "out", batch_size=1)
            self.assertEqual(file_sha256(source), before)
            self.assertEqual(list((root / "out").iterdir()), [])

    def test_overwrite_requires_explicit_permission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "fixture.tsv"
            source.write_text("one\tone\n")
            convert_file(source, input_format="tsv", output_dir=root / "out")
            with self.assertRaises(FileExistsError):
                convert_file(source, input_format="tsv", output_dir=root / "out")

    def test_audit_rejects_changed_reference_and_non_generic_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pairs = root / "pairs.jsonl"
            pairs.write_text(json.dumps({"id": "1", "source_tokens": ["a"], "references": [{"annotator_id": 0, "target_tokens": ["b"]}]}) + "\n")
            m2 = root / "output.m2"
            m2.write_text("S a\nA 0 1|||R:LEX|||b|||REQUIRED|||-NONE-|||0\n")
            with self.assertRaisesRegex(ValueError, "non-generic"):
                audit_generated(m2, pairs)
            m2.write_text("S a\nA 0 1|||R|||c|||REQUIRED|||-NONE-|||0\n")
            with self.assertRaisesRegex(ValueError, "target/reference"):
                audit_generated(m2, pairs)

    def test_audit_rejects_structurally_invalid_generic_operations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pairs = root / "pairs.jsonl"
            m2 = root / "output.m2"
            for operation, target in (("U", ["b"]), ("M", ["b"]), ("W", ["a"])):
                with self.subTest(operation=operation):
                    pairs.write_text(json.dumps({"id": "1", "source_tokens": ["a"], "references": [{"annotator_id": 0, "target_tokens": target}]}) + "\n")
                    m2.write_text(f"S a\nA 0 1|||{operation}|||{target[0]}|||REQUIRED|||-NONE-|||0\n")
                    with self.assertRaises(ValueError):
                        audit_generated(m2, pairs)

    def test_literal_pipe_corrections_do_not_merge_with_m2_delimiters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "pipes.tsv"
            source.write_text("a b\ta | b\na b\t|a b|\n")
            aligner = ExactFixtureAligner()
            cache = PairCache(root / "cache.sqlite3", aligner.metadata)
            try:
                result = convert_file(source, input_format="tsv", output_dir=root / "out", aligner=aligner, cache=cache)
                self.assertEqual(result["validation"]["sources"], 2)
                targets = [record.references[0].target_tokens for record in iter_pairs_jsonl(root / "out/pipes.pairs.jsonl")]
                self.assertEqual(targets, [("a", "|", "b"), ("|a", "b|")])
            finally:
                cache.close()

    def test_empty_files_do_not_pass_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            m2, pairs = root / "empty.m2", root / "empty.jsonl"
            m2.write_text("")
            pairs.write_text("")
            with self.assertRaisesRegex(ValueError, "empty corpus"):
                audit_generated(m2, pairs)

    def test_one_empty_sentence_is_distinct_from_an_empty_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            m2, pairs = root / "empty-sentence.m2", root / "pairs.jsonl"
            m2.write_text("S \nA -1 -1|||noop|||-NONE-|||REQUIRED|||-NONE-|||0\n")
            pairs.write_text(json.dumps({"id": "1", "source_tokens": [], "references": [{"annotator_id": 0, "target_tokens": []}]}) + "\n")
            result = audit_generated(m2, pairs, require_separate_punctuation=True)
            self.assertEqual(result["sources"], 1)
            self.assertEqual(result["references"], 1)

    def test_cli_run_config_cannot_overwrite_a_pair_input_even_with_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "run_config.json"
            original = json.dumps({"id": "1", "source_tokens": ["a"], "references": [{"annotator_id": 0, "target_tokens": ["b"]}]}) + "\n"
            source.write_text(original)
            args = SimpleNamespace(command="extract", inputs=[source], output_dir=root, input_format="jsonl", batch_size=1, overwrite=True)
            with mock.patch.object(generic_m2, "parse_args", return_value=args):
                with self.assertRaisesRegex(ValueError, "protected input"):
                    generic_m2.main()
            self.assertEqual(source.read_text(), original)

    def test_batch_output_cannot_overwrite_a_later_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "one.m2"
            later = root / "one.generic.m2"
            source.write_text("S one\n")
            later.write_text("S another\n")
            args = SimpleNamespace(command="generate", inputs=[source, later], output_dir=root, batch_size=1, overwrite=True, cache=None)
            with (
                mock.patch.object(generic_m2, "parse_args", return_value=args),
                mock.patch.object(generic_m2, "TransformerTokenEncoder") as encoder,
            ):
                with self.assertRaisesRegex(ValueError, "protected input"):
                    generic_m2.main()
                encoder.assert_not_called()
            self.assertEqual(source.read_text(), "S one\n")
            self.assertEqual(later.read_text(), "S another\n")
            self.assertFalse((root / "run_config.json").exists())

    def test_output_cache_cannot_alias_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "one.m2"
            source.write_text("S one\n")
            out = root / "out"
            args = SimpleNamespace(command="generate", inputs=[source], output_dir=out, batch_size=1, overwrite=True, cache=out / "run_config.json")
            with (
                mock.patch.object(generic_m2, "parse_args", return_value=args),
                mock.patch.object(generic_m2, "TransformerTokenEncoder") as encoder,
            ):
                with self.assertRaisesRegex(ValueError, "Output paths overlap"):
                    generic_m2.main()
                encoder.assert_not_called()
            self.assertFalse(out.exists())

    def test_batch_preflight_uses_resolved_symlink_input_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "actual.m2"
            source.write_text("S first\n")
            alias = root / "alias.m2"
            alias.symlink_to(source)
            later = root / "actual.generic.m2"
            later.write_text("S second\n")
            args = SimpleNamespace(
                command="generate", inputs=[alias, later], output_dir=root,
                batch_size=1, overwrite=True, cache=None,
            )
            with (
                mock.patch.object(generic_m2, "parse_args", return_value=args),
                mock.patch.object(generic_m2, "TransformerTokenEncoder") as encoder,
            ):
                with self.assertRaisesRegex(ValueError, "protected input"):
                    generic_m2.main()
                encoder.assert_not_called()
            self.assertEqual(source.read_text(), "S first\n")
            self.assertEqual(later.read_text(), "S second\n")
            self.assertFalse((root / "run_config.json").exists())

    def test_alias_guards_detect_symbolic_and_hard_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input"
            source.write_text("keep unchanged")
            symbolic = root / "symbolic"
            symbolic.symlink_to(source)
            hard = root / "hard"
            os.link(source, hard)
            for alias in (symbolic, hard):
                with self.subTest(alias=alias):
                    with self.assertRaisesRegex(ValueError, "protected input"):
                        generic_m2.validate_output_paths([source], [alias])
            with self.assertRaisesRegex(ValueError, "Output paths overlap"):
                generic_m2.validate_output_paths([], [symbolic, hard])
            self.assertEqual(source.read_text(), "keep unchanged")

    def test_uncreated_output_names_must_be_portably_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for first, second in (
                ("Example.m2", "example.m2"),
                ("caf\u00e9.m2", "cafe\u0301.m2"),
            ):
                with self.subTest(first=first, second=second):
                    with self.assertRaisesRegex(ValueError, "Output paths overlap"):
                        generic_m2.validate_output_paths([], [root / first, root / second])
            self.assertEqual(list(root.iterdir()), [])

    def test_existing_later_output_is_rejected_before_writing_any_batch_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = [root / "one.m2", root / "two.m2"]
            for source in sources:
                source.write_text("S source\n")
            out = root / "out"
            out.mkdir()
            existing = out / "two.pairs.tsv"
            existing.write_text("previous output")
            args = SimpleNamespace(command="extract", inputs=sources, output_dir=out, input_format="m2", batch_size=1, overwrite=False)
            with mock.patch.object(generic_m2, "parse_args", return_value=args):
                with self.assertRaises(FileExistsError):
                    generic_m2.main()
            self.assertEqual([path.name for path in out.iterdir()], ["two.pairs.tsv"])
            self.assertEqual(existing.read_text(), "previous output")


if __name__ == "__main__":
    unittest.main()
