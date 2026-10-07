from __future__ import annotations

import unittest
import csv
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from scripts.run_word_gleu_evaluation import (
    calculate_select_best_word,
    load_gleu_module,
)
from scripts import run_word_gleu_evaluation as evaluator
from scripts.word_gleu_protocol import LEGACY_SOURCE_DESCRIPTION


class WordGleuTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gleu = load_gleu_module()

    def tearDown(self) -> None:
        self.gleu.clear_caches()

    def test_word_tokenization_uses_spaces(self) -> None:
        self.gleu.set_tokenization("word")
        self.assertEqual(
            self.gleu.split_ngram(2, "我 喜欢 苹果"),
            ["我 喜欢", "喜欢 苹果"],
        )

    def test_select_best_uses_all_segmented_references(self) -> None:
        score, selected = calculate_select_best_word(
            self.gleu,
            "我 爱 饭 。",
            "我 爱 吃饭 。",
            ["我 喜欢 吃饭 。", "我 爱 吃饭 。", "我 吃饭 。"],
            max_n=4,
        )
        self.assertEqual(selected, 1)
        self.assertAlmostEqual(score, 1.0)

    def test_policy_change_cannot_overwrite_historical_scores(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "run_config.json").write_text(
                json.dumps({"source_segmentation": LEGACY_SOURCE_DESCRIPTION})
            )
            old_scores = root / "sentence_scores.tsv"
            old_scores.write_text("historical scores\n")
            args = SimpleNamespace(output=root, source_policy="condition")
            with self.assertRaisesRegex(ValueError, "separate output directory"):
                evaluator.prepare_run_config(args, ["fixture"])
            self.assertEqual(old_scores.read_text(), "historical scores\n")

    def test_runner_changes_only_source_and_does_not_need_fixed_segmentation(self) -> None:
        source = "我今天很喜欢吃米饭，但是妈妈喜欢面条。"
        gold = [[
            "1", source,
            "我今天很喜欢吃米饭，但是妈妈喜欢面包。",
            "我今天很喜欢吃面包，但是妈妈喜欢面包。",
        ]]
        row = {
            "id": "0", "source": source,
            "S1": "我 今天 很 喜欢 吃 米饭 ， 但是 妈妈 喜欢 面条 。",
            "S2": "我 今天 很 喜欢 吃 米饭 ， 但是 妈妈 喜欢 面 条 。",
            "S3": "我 今天 很 喜欢 吃 米饭 ， 但 是 妈妈 喜欢 面 条 。",
            **{stage: source for stage in ("T0", "T1", "T2", "T3")},
        }
        segmented = {
            source: row["S1"],
            gold[0][2]: "我 今天 很 喜欢 吃 米饭 ， 但是 妈妈 喜欢 面包 。",
            gold[0][3]: "我 今天 很 喜欢 吃 面包 ， 但是 妈妈 喜欢 面包 。",
        }
        segmenter = mock.Mock()
        segmenter.get_many.return_value = segmented
        spec = SimpleNamespace(dataset="fixture", split="test", rows=1, gold_para=Path("unused"))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "condition"
            with (
                mock.patch.object(sys, "argv", ["word-gleu", "--output", str(output)]),
                mock.patch.object(evaluator, "load_specs", return_value=[spec]),
                mock.patch.object(evaluator, "para_rows", return_value=gold),
                mock.patch.object(evaluator, "load_result_rows", return_value=[row]),
                mock.patch.object(evaluator, "LtpSegmentationCache", return_value=segmenter),
                mock.patch.object(evaluator, "load_fixed_segmentations", side_effect=AssertionError("fixed source must not be loaded")),
            ):
                evaluator.main()
            inputs = output / "fixture/test/inputs"
            for stage, source_column in (("T0", "S1"), ("T1", "S1"), ("T2", "S2"), ("T3", "S3")):
                self.assertEqual((inputs / f"source.{stage}.txt").read_text().strip(), row[source_column])
                self.assertEqual((inputs / f"hypothesis.{stage}.txt").read_text().strip(), segmented[source])
                self.assertEqual(
                    (inputs / f"references.{stage}.tsv").read_text().strip(),
                    "\t".join(segmented[reference] for reference in gold[0][2:]),
                )
            config = json.loads((output / "run_config.json").read_text())
            self.assertEqual(config["source_segmentation_policy"], "condition")
            self.assertEqual(config["status"], "completed")
            self.assertIsNone(config["fixed_segmentation_root"])
            with (output / "sentence_scores.tsv").open() as stream:
                scores = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual([item["reference_count"] for item in scores], ["2"] * 4)
            self.assertTrue(all(item["source_segmentation_policy"] == "condition" for item in scores))
            self.assertNotEqual(scores[1]["gleu_select_best"], scores[2]["gleu_select_best"])


if __name__ == "__main__":
    unittest.main()
