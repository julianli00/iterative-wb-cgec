from __future__ import annotations

import unittest

from scripts.movement_aware_compare import (
    compare_edits,
    evaluate,
    parse_block,
    scored_edits,
)


class MovementAwareCompareTests(unittest.TestCase):
    def block(self, origin: str, destination: str, *, link: str = "w1") -> str:
        return (
            "S 甲 乙 丙 丁 戊\n"
            f"A {origin}|||U|||-NONE-|||-REQUIRED-|||LINK={link};TO={destination}|||0\n"
            f"A {destination} {destination}|||M|||甲|||-REQUIRED-|||LINK={link};FROM={origin.replace(' ', ':')}|||0"
        )

    def test_link_identifier_is_local_and_not_part_of_match_key(self) -> None:
        hypothesis = scored_edits(
            parse_block(self.block("0 1", "5", link="w1"), unit="character"),
            unit="character",
        )[0]
        reference = scored_edits(
            parse_block(self.block("0 1", "5", link="w7"), unit="character"),
            unit="character",
        )[0]

        tp, fp, fn, categories = compare_edits(hypothesis, reference)
        self.assertEqual((tp, fp, fn), (1, 0, 0))
        self.assertEqual(categories, {"WO": [1, 0, 0]})

    def test_short_and_long_word_order_are_reported_separately(self) -> None:
        linked = scored_edits(
            parse_block(self.block("0 1", "5"), unit="character"),
            unit="character",
        )[0]
        short = scored_edits(
            parse_block(
                "S 甲 乙 丙 丁 戊\n"
                "A 1 3|||W|||丙乙|||-REQUIRED-|||NONE|||0",
                unit="character",
            ),
            unit="character",
        )[0]

        linked_counts = compare_edits(linked, linked)
        short_counts = compare_edits(short, short)
        self.assertEqual(linked_counts[3], {"WO": [1, 0, 0]})
        self.assertEqual(short_counts[3], {"W": [1, 0, 0]})

    def test_origin_is_part_of_strict_movement_identity(self) -> None:
        hypothesis = scored_edits(
            parse_block(self.block("0 1", "5"), unit="character"),
            unit="character",
        )[0]
        reference_block = (
            "S 甲 乙 丙 丁 戊\n"
            "A 1 2|||U|||-NONE-|||-REQUIRED-|||LINK=w1;TO=5|||0\n"
            "A 5 5|||M|||乙|||-REQUIRED-|||LINK=w1;FROM=1:2|||0"
        )
        reference = scored_edits(
            parse_block(reference_block, unit="character"), unit="character"
        )[0]

        tp, fp, fn, _categories = compare_edits(hypothesis, reference)
        self.assertEqual((tp, fp, fn), (0, 1, 1))

    def test_unpaired_link_fails_closed(self) -> None:
        block = parse_block(
            "S 甲 乙\nA 0 1|||U|||-NONE-|||-REQUIRED-|||LINK=w1;TO=2|||0",
            unit="character",
        )
        with self.assertRaisesRegex(ValueError, "exactly twice"):
            scored_edits(block, unit="character")

    def test_two_sentence_hand_calculation(self) -> None:
        hypothesis = [
            parse_block(self.block("0 1", "5", link="w1"), unit="character"),
            parse_block(
                "S 我 很 喜 欢 茶\n"
                "A 4 5|||R|||咖啡|||-REQUIRED-|||NONE|||0\n"
                "A 0 0|||M|||今天|||-REQUIRED-|||NONE|||0",
                unit="character",
            ),
        ]
        reference = [
            parse_block(self.block("0 1", "5", link="w7"), unit="character"),
            parse_block(
                "S 我 很 喜 欢 茶\n"
                "A 1 2|||U|||-NONE-|||-REQUIRED-|||NONE|||0\n"
                "A 4 5|||R|||咖啡|||-REQUIRED-|||NONE|||0",
                unit="character",
            ),
        ]

        counts, categories, _selections = evaluate(
            hypothesis, reference, beta=0.5
        )
        self.assertEqual(dict(counts), {"tp": 2, "fp": 1, "fn": 1})
        self.assertEqual(
            categories,
            {
                "M": [0, 1, 0],
                "R": [1, 0, 0],
                "U": [0, 0, 1],
                "WO": [1, 0, 0],
            },
        )


if __name__ == "__main__":
    unittest.main()
