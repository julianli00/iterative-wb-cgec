import unittest

from scripts.summarize_scoreboard_t3 import boundary_positions, projection_counts


class ScoreboardSummaryTest(unittest.TestCase):
    def test_projection_counts_actual_boundary_additions_and_removals(self):
        rows = [
            {
                "S1": "研究 生命",
                "S2": "研究生 命",
                "S3": "研究生 命",
            }
        ]

        self.assertEqual(boundary_positions("研究 生命"), {1})
        self.assertEqual(boundary_positions("研究生 命"), {2})
        self.assertEqual(projection_counts(rows), (1, 1))


if __name__ == "__main__":
    unittest.main()
