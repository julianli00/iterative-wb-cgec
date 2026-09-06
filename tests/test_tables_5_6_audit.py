from __future__ import annotations

import unittest

from scripts.audit_tables_5_6 import levenshtein, rank_summary


class TablesFiveSixAuditTests(unittest.TestCase):
    def test_levenshtein(self) -> None:
        self.assertEqual(levenshtein("", "甲乙"), 2)
        self.assertEqual(levenshtein("甲乙丙", "甲丁丙"), 1)
        self.assertEqual(levenshtein("相同", "相同"), 0)

    def test_rank_summary_uses_printed_two_decimal_values(self) -> None:
        scores = {
            ("d", "T0"): {"score_x100": 10.001},
            ("d", "T1"): {"score_x100": 10.002},
            ("d", "T2"): {"score_x100": 10.009},
            ("d", "T3"): {"score_x100": 10.000},
        }
        result = rank_summary(scores, ["d"])
        self.assertEqual(result["structured_beats_raw"], 1)
        self.assertEqual(result["direct_beats_raw"], 0)
        self.assertEqual(result["projected_beats_direct"], 1)
        self.assertEqual(result["iterative_below_projected"], 1)


if __name__ == "__main__":
    unittest.main()
