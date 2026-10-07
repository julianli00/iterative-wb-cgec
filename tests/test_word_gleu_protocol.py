from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.word_gleu_protocol import (
    CONDITION_SOURCE_COLUMNS,
    LEGACY_SOURCE_DESCRIPTION,
    load_source_policy,
    select_source_segmentation,
    source_policy_from_config,
)


class WordGleuProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.row = {
            "id": "0",
            "source": "研究生命",
            "S1": "研究 生命",
            "S2": "研究生 命",
            "S3": "研 究 生命",
        }

    def test_condition_mapping_uses_actual_saved_source_boundaries(self) -> None:
        for stage, column in CONDITION_SOURCE_COLUMNS.items():
            with self.subTest(stage=stage):
                self.assertEqual(select_source_segmentation(self.row, stage), self.row[column])

    def test_condition_policy_does_not_use_gold_informed_source(self) -> None:
        self.assertEqual(
            select_source_segmentation(self.row, "T2", fixed_source="研 究 生 命"),
            "研究生 命",
        )

    def test_whitespace_normalization_preserves_boundary_vectors(self) -> None:
        row = {**self.row, "S2": "\ufeff研究生  \u3000命"}
        self.assertEqual(select_source_segmentation(row, "T2"), "研究生 命")

    def test_missing_boundaries_cannot_fall_back_to_another_condition(self) -> None:
        row = dict(self.row)
        del row["S2"]
        with self.assertRaisesRegex(ValueError, "Missing or empty S2"):
            select_source_segmentation(row, "T2")

    def test_changed_source_characters_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "changed learner text"):
            select_source_segmentation({**self.row, "S2": "研究 人生"}, "T2")

    def test_fixed_policy_is_explicit_and_requires_fixed_source(self) -> None:
        for stage in CONDITION_SOURCE_COLUMNS:
            self.assertEqual(
                select_source_segmentation(
                    self.row, stage, source_policy="fixed-gold", fixed_source="研 究生 命"
                ),
                "研 究生 命",
            )
        with self.assertRaisesRegex(ValueError, "fixed gold-informed source"):
            select_source_segmentation(self.row, "T0", source_policy="fixed-gold")

    def test_unknown_policy_and_stage_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown word-GLEU source policy"):
            select_source_segmentation(self.row, "T0", source_policy="guess")
        with self.assertRaisesRegex(ValueError, "Unknown word-GLEU stage"):
            select_source_segmentation(self.row, "T4")

    def test_policy_metadata_requires_the_exact_condition_mapping(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid source-stage mapping"):
            source_policy_from_config({"source_segmentation_policy": "condition"})
        with self.assertRaisesRegex(ValueError, "Missing or unknown"):
            source_policy_from_config({})

    def test_metadata_rejects_mixed_or_incomplete_evaluations(self) -> None:
        config = {
            "source_segmentation_policy": "condition",
            "source_stage_mapping": CONDITION_SOURCE_COLUMNS,
            "hypothesis_and_reference_segmentation": "LTP",
            "status": "completed",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "run_config.json"
            path.write_text(json.dumps(config))
            self.assertEqual(load_source_policy(root, expected_policy="condition"), "condition")
            with self.assertRaisesRegex(ValueError, "policy mismatch"):
                load_source_policy(root, expected_policy="fixed-gold")
            path.write_text(json.dumps({**config, "status": "running"}))
            with self.assertRaisesRegex(ValueError, "not complete"):
                load_source_policy(root)

    def test_historical_fixed_metadata_is_recognized_without_relabeling(self) -> None:
        config = {
            "source_segmentation": LEGACY_SOURCE_DESCRIPTION,
            "hypothesis_and_reference_segmentation": "LTP",
            "completed_utc": "2026-09-18T00:00:00Z",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "run_config.json").write_text(json.dumps(config))
            self.assertEqual(load_source_policy(root, expected_policy="fixed-gold"), "fixed-gold")
            with self.assertRaisesRegex(ValueError, "policy mismatch"):
                load_source_policy(root, expected_policy="condition")


if __name__ == "__main__":
    unittest.main()
