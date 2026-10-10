from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from scripts.run_model_scoreboard_t3 import save_generation_config, validate_result


class ModelScoreboardTests(unittest.TestCase):
    def test_copilot_resume_rejects_changed_experiment_settings(self) -> None:
        config = {
            "backend": "copilot",
            "model": "gpt-6-astra",
            "thinking": "provider default",
            "temperature": "omit",
            "max_tokens": None,
            "prompt_variant": "paper",
            "max_t": 3,
            "projection_threshold": 0.85,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            save_generation_config(path, config)
            save_generation_config(path, {**config, "workers": 2})
            with self.assertRaisesRegex(ValueError, "changed model"):
                save_generation_config(path, {**config, "model": "another-model"})
            self.assertEqual(json.loads(path.read_text())["model"], "gpt-6-astra")

    def test_validation_requires_successful_matching_raw_records(self) -> None:
        row = {
            "id": "0", "source": "source", "target": "reference",
            "S1": "source", "S2": "source", "S3": "source",
            "T0": "correction", "T1": "correction", "T2": "correction", "T3": "correction",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "output.tsv"
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(row), delimiter="\t")
                writer.writeheader()
                writer.writerow(row)
            raw = path.with_suffix(".jsonl")
            raw.write_text(json.dumps({**row, "ok": True}) + "\n")
            validate_result(path, 1)
            raw.write_text(json.dumps({**row, "ok": False}) + "\n")
            with self.assertRaisesRegex(ValueError, "unsuccessful"):
                validate_result(path, 1)


if __name__ == "__main__":
    unittest.main()
