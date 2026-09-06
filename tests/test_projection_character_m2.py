from __future__ import annotations

import unittest
from pathlib import Path
import subprocess
import sys
import tempfile

from scripts.projection_character_m2 import (
    CharacterEdit,
    NO_CORRECTION,
    apply_edits,
    edits_from_alignment,
    render_m2_block,
    select_monotonic_fuzzy_alignment,
    targets_from_m2_block,
    validate_m2_targets,
)


class ProjectionCharacterM2Tests(unittest.TestCase):
    def test_noop_block_has_no_target_line(self) -> None:
        source = "我喜欢苹果。"
        edits = edits_from_alignment(
            source,
            source,
            {index: index for index in range(len(source))},
        )
        block = render_m2_block(source, [(source, edits)])

        self.assertEqual(edits, [])
        self.assertEqual(
            block,
            "S 我 喜 欢 苹 果 。\n"
            "A -1 -1|||noop|||-NONE-|||REQUIRED|||-NONE-|||0",
        )
        self.assertNotIn("\nT", block)

    def test_missing_character(self) -> None:
        source = "我吃饭"
        target = "我爱吃饭"
        edits = edits_from_alignment(source, target, {0: 0, 2: 1, 3: 2})

        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].edit_type, "M")
        self.assertEqual((edits[0].source_start, edits[0].source_end), (1, 1))
        self.assertEqual(edits[0].correction, "爱")
        self.assertEqual(apply_edits(source, edits), target)

    def test_unnecessary_character(self) -> None:
        source = "我很爱"
        target = "我爱"
        edits = edits_from_alignment(source, target, {0: 0, 1: 2})

        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].edit_type, "U")
        self.assertEqual((edits[0].source_start, edits[0].source_end), (1, 2))
        self.assertEqual(edits[0].correction, NO_CORRECTION)
        self.assertEqual(apply_edits(source, edits), target)

    def test_fuzzy_pair_becomes_replacement(self) -> None:
        source = "我喜欢"
        target = "我喜爱"
        edits = edits_from_alignment(source, target, {0: 0, 1: 1, 2: 2})

        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].edit_type, "R")
        self.assertEqual((edits[0].source_start, edits[0].source_end), (2, 3))
        self.assertEqual(edits[0].correction, "爱")
        self.assertEqual(apply_edits(source, edits), target)

    def test_adjacent_replacements_are_merged(self) -> None:
        source = "甲乙。"
        target = "丙丁。"
        edits = edits_from_alignment(source, target, {0: 0, 1: 1, 2: 2})

        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].edit_type, "R")
        self.assertEqual((edits[0].source_start, edits[0].source_end), (0, 2))
        self.assertEqual(edits[0].correction, "丙丁")

    def test_adjacent_swap_is_word_order(self) -> None:
        source = "我爱你"
        target = "我你爱"
        edits = edits_from_alignment(source, target, {0: 0, 1: 2})

        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].edit_type, "W")
        self.assertEqual((edits[0].source_start, edits[0].source_end), (1, 3))
        self.assertEqual(edits[0].correction, "你爱")
        self.assertEqual(apply_edits(source, edits), target)

    def test_long_distance_move_is_one_linked_word_order_edit(self) -> None:
        source = "旅游去陌生的地方"
        target = "去陌生的地方旅游"
        alignment = {
            target_index: source_index
            for target_index, source_index in enumerate(range(2, len(source)))
        }
        edits = edits_from_alignment(source, target, alignment)

        self.assertEqual([edit.edit_type for edit in edits], ["U", "M"])
        self.assertEqual(edits[0].comment, "LINK=w1;TO=8")
        self.assertEqual(edits[1].comment, "LINK=w1;FROM=0:2")
        self.assertEqual(apply_edits(source, edits), target)

    def test_threshold_can_keep_long_envelope_as_conventional_w(self) -> None:
        source = "旅游去陌生的地方"
        target = "去陌生的地方旅游"
        alignment = {
            target_index: source_index
            for target_index, source_index in enumerate(range(2, len(source)))
        }
        edits = edits_from_alignment(source, target, alignment, l_max=8)

        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].edit_type, "W")
        self.assertEqual(edits[0].comment, "NONE")

    def test_repeated_character_counts_do_not_create_word_order(self) -> None:
        source = "甲甲乙"
        target = "甲乙乙"
        edits = edits_from_alignment(source, target, {0: 0, 1: 1, 2: 2})

        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].edit_type, "R")

    def test_movement_with_lexical_change_falls_back_to_ordinary_edits(self) -> None:
        source = "旅游去陌生的地方"
        target = "去陌生的地方旅遊"
        alignment = {
            target_index: source_index
            for target_index, source_index in enumerate(range(2, len(source)))
        }
        edits = edits_from_alignment(source, target, alignment)

        self.assertEqual([edit.edit_type for edit in edits], ["U", "M"])
        self.assertTrue(all(edit.comment == "NONE" for edit in edits))
        self.assertEqual(apply_edits(source, edits), target)

    def test_malformed_link_is_rejected(self) -> None:
        source = "甲乙丙丁"
        edits = [
            CharacterEdit(0, 1, 0, 0, "U", NO_CORRECTION, "LINK=w1;TO=4"),
            CharacterEdit(4, 4, 3, 4, "M", "乙", "LINK=w1;FROM=0:1"),
        ]
        with self.assertRaisesRegex(ValueError, "material differ"):
            apply_edits(source, edits)

    def test_insertion_followed_by_replacement_round_trips(self) -> None:
        source = "甲乙"
        target = "丙丁乙"
        edits = edits_from_alignment(source, target, {0: 0, 2: 1})

        self.assertEqual([edit.edit_type for edit in edits], ["R", "M"])
        self.assertEqual(apply_edits(source, edits), target)

    def test_crossing_fuzzy_pairs_are_made_monotonic(self) -> None:
        selected = select_monotonic_fuzzy_alignment(
            exact={0: 0, 5: 5},
            fuzzy={1: 3, 2: 1, 3: 2, 4: 4},
            source_length=6,
            target_length=6,
        )

        self.assertEqual(selected, {2: 1, 3: 2, 4: 4})

    def test_multiple_references_have_distinct_annotators(self) -> None:
        source = "我爱饭"
        target_0 = "我爱吃饭"
        target_1 = source
        edits_0 = edits_from_alignment(
            source, target_0, {0: 0, 1: 1, 3: 2}
        )
        edits_1 = edits_from_alignment(
            source,
            target_1,
            {index: index for index in range(len(source))},
        )
        block = render_m2_block(
            source,
            [(target_0, edits_0), (target_1, edits_1)],
        )

        self.assertIn("|||0", block)
        self.assertIn(
            "A -1 -1|||noop|||-NONE-|||REQUIRED|||-NONE-|||1",
            block,
        )

    def test_cherrant_comparator_accepts_s_a_only_m2(self) -> None:
        source = "我吃饭"
        target = "我爱吃饭"
        edits = edits_from_alignment(source, target, {0: 0, 2: 1, 3: 2})
        block = render_m2_block(source, [(target, edits)]) + "\n"
        comparator = (
            Path(__file__).resolve().parents[1]
            / "external_tools/MuCGEC/scorers/ChERRANT/"
            "compare_m2_for_evaluation.py"
        )
        with tempfile.TemporaryDirectory() as directory:
            hypothesis = Path(directory) / "hyp.m2"
            reference = Path(directory) / "ref.m2"
            hypothesis.write_text(block, encoding="utf-8")
            reference.write_text(block, encoding="utf-8")
            process = subprocess.run(
                [
                    sys.executable,
                    str(comparator),
                    "-hyp",
                    str(hypothesis),
                    "-ref",
                    str(reference),
                    "--beta",
                    "0.5",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        self.assertEqual(process.returncode, 0, process.stdout)
        self.assertRegex(process.stdout, r"\b1\s+0\s+0\s+1\.0\s+1\.0\s+1\.0")

    def test_serialized_multi_reference_round_trip(self) -> None:
        source = "我很爱饭"
        target_0 = "我爱吃饭"
        target_1 = source
        edits_0 = edits_from_alignment(
            source,
            target_0,
            {0: 0, 1: 2, 3: 3},
        )
        edits_1 = edits_from_alignment(
            source,
            target_1,
            {index: index for index in range(len(source))},
        )
        block = render_m2_block(
            source,
            [(target_0, edits_0), (target_1, edits_1)],
        )
        actual_source, targets = targets_from_m2_block(block)

        self.assertEqual(actual_source, source)
        self.assertEqual(targets, {0: target_0, 1: target_1})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roundtrip.m2"
            path.write_text(block + "\n", encoding="utf-8")
            audit = validate_m2_targets(
                path,
                [(source, [target_0, target_1])],
            )
        self.assertEqual(audit, {"sentences": 1, "references": 2})


if __name__ == "__main__":
    unittest.main()
