from __future__ import annotations

import unittest
from pathlib import Path
import sys


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from scripts.run_word_gleu_evaluation import (
    calculate_select_best_word,
    load_gleu_module,
)


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


if __name__ == "__main__":
    unittest.main()
