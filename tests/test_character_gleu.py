from __future__ import annotations

import csv
import importlib
from pathlib import Path
import sys
import tempfile
import unittest

from scripts.run_character_gleu_evaluation import (
    GLEU_ROOT,
    calculate_select_best,
    normalize_character_text,
    read_gold_para,
    write_references,
)


if str(GLEU_ROOT) not in sys.path:
    sys.path.insert(0, str(GLEU_ROOT))
gleu = importlib.import_module("gleu_wrapper")


class CharacterGleuTests(unittest.TestCase):
    def tearDown(self) -> None:
        gleu.clear_caches()
        gleu.set_tokenization("word")

    def test_character_tokenization_is_actually_character_based(self) -> None:
        gleu.set_tokenization("char")
        self.assertEqual(gleu.split_ngram(1, "甲乙"), ["甲", "乙"])
        self.assertEqual(gleu.split_ngram(2, "甲乙"), ["甲乙"])

    def test_select_best_uses_all_references(self) -> None:
        score, selected = calculate_select_best(
            gleu,
            "我爱饭。",
            "我爱吃饭。",
            ["我喜欢吃饭。", "我爱吃饭。", "我爱米饭。", "我吃饭。"],
            max_n=4,
        )
        self.assertEqual(selected, 1)
        self.assertAlmostEqual(score, 1.0)

    def test_character_and_word_tokenization_differ_without_spaces(self) -> None:
        character_score = gleu.calculate_gleu_score(
            "甲乙丙丁", "甲乙丙丁", "甲乙丙丁", tokenization="char"
        )
        word_score = gleu.calculate_gleu_score(
            "甲乙丙丁", "甲乙丙丁", "甲乙丙丁", tokenization="word"
        )
        self.assertAlmostEqual(character_score, 1.0)
        self.assertNotEqual(
            gleu.split_char_ngram(1, "甲乙丙丁"),
            gleu.split_word_ngram(1, "甲乙丙丁"),
        )
        self.assertAlmostEqual(word_score, 1.0)

    def test_gold_reader_keeps_every_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gold.para"
            with path.open("w", encoding="utf-8", newline="") as stream:
                csv.writer(stream, delimiter="\t", lineterminator="\n").writerow(
                    ["1", "我 爱 饭", "我爱吃饭", "我喜欢吃饭", "我爱米饭", "我吃饭"]
                )
            rows = read_gold_para(path)
        self.assertEqual(rows, [("1", "我爱饭", ["我爱吃饭", "我喜欢吃饭", "我爱米饭", "我吃饭"])])

    def test_normalization_removes_bom_and_whitespace_only(self) -> None:
        self.assertEqual(normalize_character_text("\ufeff我 爱\n飯"), "我爱飯")

    def test_reference_writer_matches_upstream_plain_tsv_reader(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "references.tsv"
            write_references(path, [['他说“可以”。', '他说"可以"。']])
            text = path.read_text(encoding="utf-8")
        self.assertEqual(text, '他说“可以”。\t他说"可以"。\n')
        self.assertNotIn('""可以""', text)


if __name__ == "__main__":
    unittest.main()
