from __future__ import annotations

import unittest

from scripts.projection_character_m2 import edits_from_alignment
from scripts.projection_word_m2 import (
    apply_word_edits,
    edits_from_token_alignment,
    projection_word_edits,
    projection_word_edits_from_character_edits,
    render_word_m2_block,
    targets_from_word_m2_block,
    token_alignment_from_character_alignment,
)


class ProjectionWordM2Tests(unittest.TestCase):
    def test_character_votes_form_token_alignment(self) -> None:
        alignment = token_alignment_from_character_alignment(
            "我 喜欢 苹果",
            "我 喜爱 苹果",
            {0: 0, 1: 1, 2: 2, 3: 3, 4: 4},
        )
        self.assertEqual(alignment, {0: 0, 1: 1, 2: 2})

    def test_projected_replacement(self) -> None:
        edits = projection_word_edits(
            "我 喜欢 苹果",
            "我 喜爱 苹果",
            {0: 0, 1: 1, 2: 2, 3: 3, 4: 4},
        )
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].edit_type, "R")
        self.assertEqual(edits[0].correction, ("喜爱",))

    def test_adjacent_word_swap_is_word_order(self) -> None:
        source = ("我", "爱", "你")
        target = ("我", "你", "爱")
        edits = edits_from_token_alignment(source, target, {0: 0, 1: 2})
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].edit_type, "W")
        self.assertEqual(edits[0].correction, ("你", "爱"))
        self.assertEqual(apply_word_edits(source, edits), target)

    def test_long_distance_word_move_is_linked_word_order(self) -> None:
        source = ("旅游", "去", "陌生", "的", "地方")
        target = ("去", "陌生", "的", "地方", "旅游")
        edits = edits_from_token_alignment(
            source,
            target,
            {target_index: source_index for target_index, source_index in enumerate(range(1, 5))},
        )
        self.assertEqual([edit.edit_type for edit in edits], ["U", "M"])
        self.assertEqual(edits[0].comment, "LINK=w1;TO=5")
        self.assertEqual(edits[1].comment, "LINK=w1;FROM=0:1")
        self.assertEqual(apply_word_edits(source, edits), target)

    def test_character_word_order_is_preserved_at_word_level(self) -> None:
        source = "旅游去陌生的地方"
        target = "去陌生的地方旅游"
        character_edits = edits_from_alignment(
            source,
            target,
            {
                target_index: source_index
                for target_index, source_index in enumerate(range(2, len(source)))
            },
        )
        edits = projection_word_edits_from_character_edits(
            "旅游 去 陌生 的 地方",
            "去 陌生 的 地方 旅游",
            character_edits,
        )

        self.assertEqual([edit.edit_type for edit in edits], ["U", "M"])
        self.assertEqual(edits[0].comment, "LINK=w1;TO=5")

    def test_word_m2_multi_reference_round_trip(self) -> None:
        source = "我 喜欢 苹果"
        target_0 = "我 喜爱 苹果"
        target_1 = source
        edits_0 = projection_word_edits(
            source,
            target_0,
            {0: 0, 1: 1, 2: 2, 3: 3, 4: 4},
        )
        block = render_word_m2_block(
            source,
            [(target_0, edits_0), (target_1, [])],
        )
        actual_source, targets = targets_from_word_m2_block(block)
        self.assertEqual(actual_source, ("我", "喜欢", "苹果"))
        self.assertEqual(
            targets,
            {
                0: ("我", "喜爱", "苹果"),
                1: ("我", "喜欢", "苹果"),
            },
        )


if __name__ == "__main__":
    unittest.main()
