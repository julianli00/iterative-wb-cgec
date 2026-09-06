from __future__ import annotations

import unittest

from scripts.prepare_scoreboard_datasets import (
    convert_fcgec_operations,
    copy_sanitized_m2,
    detokenize_m2_text,
    parse_m2,
)


class DatasetPreparationTest(unittest.TestCase):
    def test_fcgec_multi_reference_modify(self) -> None:
        sentence = "降低了适应症范围"
        operations = [
            {
                "Modify": [
                    {"pos": 0, "tag": "MOD_2", "label": ["缩小", "缩减"]}
                ]
            }
        ]
        self.assertEqual(
            convert_fcgec_operations(sentence, operations),
            ["缩小了适应症范围", "缩减了适应症范围"],
        )

    def test_parse_m2_uses_source_for_noop(self) -> None:
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gold.m2"
            path.write_text("S 没 有 错 误\nT0 没有错误\nA -1 -1|||noop|||-NONE-|||REQUIRED|||-NONE-|||0\n", encoding="utf-8")
            sources, refs = parse_m2(path)
        self.assertEqual(sources, ["没有错误"])
        self.assertEqual(refs, [["没有错误"]])

    def test_embedded_m2_bom_is_removed(self) -> None:
        from pathlib import Path
        import tempfile

        content = (
            "S 第 一 句\nT0 第一句\n\n"
            "S \ufeff 第 二 句\nT0 第二句\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.m2"
            destination = Path(tmp) / "destination.m2"
            source.write_text(content, encoding="utf-8")
            sources, _ = parse_m2(source)
            copy_sanitized_m2(source, destination)

            self.assertEqual(sources, ["第一句", "第二句"])
            self.assertNotIn("\ufeff", destination.read_text(encoding="utf-8"))

    def test_bpe_continuation_markers_are_not_learner_text(self) -> None:
        self.assertEqual(detokenize_m2_text("57 ##1 多 亿", bpe=True), "571多亿")
        self.assertEqual(detokenize_m2_text("31 ##∶ ##20", bpe=True), "31∶20")
        self.assertEqual(detokenize_m2_text("# #", bpe=True), "##")


if __name__ == "__main__":
    unittest.main()
