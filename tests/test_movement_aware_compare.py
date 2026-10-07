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

    def test_sentence_local_selection_is_not_order_dependent_corpus_greedy(self) -> None:
        first_hypothesis = parse_block(
            "S 甲 乙 丙 丁 戊\n"
            "A 0 1|||R|||一|||-REQUIRED-|||NONE|||0\n"
            "A 1 2|||R|||二|||-REQUIRED-|||NONE|||0\n"
            "A 2 3|||R|||三|||-REQUIRED-|||NONE|||0\n"
            "A 3 4|||R|||四|||-REQUIRED-|||NONE|||0\n"
            "A 4 5|||R|||五|||-REQUIRED-|||NONE|||0",
            unit="character",
        )
        first_reference = first_hypothesis
        second_hypothesis = parse_block(
            "S 甲 乙 丙 丁 戊 己\n"
            "A 0 1|||R|||一|||-REQUIRED-|||NONE|||0",
            unit="character",
        )
        second_reference = parse_block(
            "S 甲 乙 丙 丁 戊 己\n"
            "A 0 1|||R|||一|||-REQUIRED-|||NONE|||0\n"
            "A 1 2|||R|||二|||-REQUIRED-|||NONE|||0\n"
            "A 2 3|||R|||三|||-REQUIRED-|||NONE|||0\n"
            "A 3 4|||R|||四|||-REQUIRED-|||NONE|||0\n"
            "A 4 5|||R|||五|||-REQUIRED-|||NONE|||0\n"
            "A 5 6|||R|||六|||-REQUIRED-|||NONE|||0\n"
            "A -1 -1|||noop|||-NONE-|||-REQUIRED-|||NONE|||1",
            unit="character",
        )

        sentence_counts, _categories, sentence_selections = evaluate(
            [first_hypothesis, second_hypothesis],
            [first_reference, second_reference],
            beta=0.5,
        )
        corpus_counts, _categories, corpus_selections = evaluate(
            [first_hypothesis, second_hypothesis],
            [first_reference, second_reference],
            beta=0.5,
            selection_mode="corpus",
        )

        self.assertEqual(sentence_selections[1]["reference"], 0)
        self.assertEqual(dict(sentence_counts), {"tp": 6, "fp": 0, "fn": 5})
        self.assertEqual(corpus_selections[1]["reference"], 1)
        self.assertEqual(dict(corpus_counts), {"tp": 5, "fp": 1, "fn": 0})


if __name__ == "__main__":
    unittest.main()
