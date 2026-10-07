from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CopilotEvaluationRunnerTests(unittest.TestCase):
    def test_full_and_selected_runs_only_invoke_offline_evaluators(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts/run_copilot_evaluations.sh"
        with tempfile.TemporaryDirectory() as directory:
            interpreter = Path(directory) / "python"
            interpreter.write_text(
                f"#!{sys.executable}\nimport json, sys\nprint('ARGV:' + json.dumps(sys.argv[1:]))\n"
            )
            interpreter.chmod(0o700)
            for datasets in ([], ["cefe_track3"]):
                with self.subTest(datasets=datasets):
                    completed = subprocess.run(
                        ["bash", str(script), *datasets],
                        env={**os.environ, "PYTHON_BIN": str(interpreter)},
                        text=True, capture_output=True, check=False,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    calls = [
                        json.loads(line.removeprefix("ARGV:"))
                        for line in completed.stdout.splitlines()
                        if line.startswith("ARGV:")
                    ]
                    self.assertEqual(len(calls), 5)
                    self.assertTrue(all("run_model_scoreboard" not in call[0] for call in calls))
                    for call in calls:
                        if datasets:
                            self.assertEqual(call[-2:], ["--datasets", "cefe_track3"])
                        else:
                            self.assertNotIn("--datasets", call)
                    self.assertEqual(calls[-1][0], "scripts/run_word_gleu_evaluation.py")
                    self.assertIn("--target-normalization", calls[-1])
                    policy_index = calls[-1].index("--source-policy")
                    self.assertEqual(calls[-1][policy_index + 1], "condition")
                    output_index = calls[-1].index("--output")
                    self.assertTrue(calls[-1][output_index + 1].endswith("/word_gleu_condition"))


if __name__ == "__main__":
    unittest.main()
