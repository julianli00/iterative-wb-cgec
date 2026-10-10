from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from scripts.run_projection_m2_evaluation import write_global_outputs


class ProjectionReportTests(unittest.TestCase):
    def test_new_model_report_does_not_require_cherrant_baseline(self) -> None:
        spec = SimpleNamespace(dataset="fixture", split="test")
        rounds = ("T0", "T1", "T2", "T3")
        rows = [
            {
                "dataset": spec.dataset,
                "split": spec.split,
                "sentences": 1,
                "alignment": "projection",
                "round": stage,
                "beta": 0.5,
                "F_beta": 1.0,
            }
            for stage in rounds
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_global_outputs(output, rows, [spec], rounds)
            self.assertTrue((output / "scores.projection.f05.tsv").is_file())
            self.assertFalse((output / "scores.cherrant.f05.tsv").exists())
            report = (output / "scores.f05_comparison.md").read_text()
            self.assertIn("sentence-local select-best", report)
            self.assertIn("n/a", report)


if __name__ == "__main__":
    unittest.main()
