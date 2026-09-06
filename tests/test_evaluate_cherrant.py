from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/evaluate_cherrant.py"
SPEC = importlib.util.spec_from_file_location("evaluate_cherrant", MODULE_PATH)
assert SPEC and SPEC.loader
EVALUATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATE)


class EvaluateCherrantTest(unittest.TestCase):
    def test_m2_sources_detokenize_bpe_continuation_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "gold.m2"
            path.write_text("S 编 号 57 ##1\nA -1 -1|||noop||||||REQUIRED|||-NONE-|||0\n", encoding="utf-8")

            self.assertEqual(EVALUATE.m2_sources(path, bpe=True), ["编号571"])
            self.assertEqual(EVALUATE.m2_sources(path, bpe=False), ["编号57##1"])

    def test_parallel_writer_does_not_csv_escape_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "hypothesis.para"
            EVALUATE.write_cherrant_parallel(
                [["1", '他说“好”', '他说“可以”']],
                path,
            )

            self.assertEqual(path.read_text(encoding="utf-8"), '1\t他说“好”\t他说“可以”\n')


if __name__ == "__main__":
    unittest.main()
