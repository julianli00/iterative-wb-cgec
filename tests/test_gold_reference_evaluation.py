from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import evaluate_gold_reference_experiment as evaluation
from scripts import run_gold_reference_experiment as experiment
from scripts.projection_character_m2 import CharacterEdit


class GoldReferenceEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.row = {
            "id": "1", "csv_row": 1, "target_id": "11", "source": "我爱中问。",
            "target": "我爱中文。", "target_segmented": "我 爱 中文 。",
            "R_input": "我爱中问。", "D_input": "我 爱 中 问 。", "P_input": "我 爱 中问 。",
            "original": {
                "Index": "1", "Target_ID": "11", "Source_Text": "我爱 中问。",
                "Target_Text": "我 爱 中文 。",
            },
            "carry_P_from_D": False, "projection_stats": {},
        }
        self.edits = [CharacterEdit(3, 4, 3, 4, "R", "文")]

    def test_word_m2_uses_fixed_gold_source_and_provided_reference_tokens(self) -> None:
        char, word = evaluation.render_pair(
            self.row, self.row["target"], self.row["target_segmented"], self.edits
        )
        self.assertTrue(char.startswith("S 我 爱 中 问 。"))
        self.assertTrue(word.startswith("S 我 爱 中问 。"))
        self.assertNotIn("S 我 爱 中 问 。", word)
        paths = evaluation.save_blocks(self.root, "fixture", [(char, word)])
        for unit in ("character", "word"):
            metrics, selections = evaluation.score_m2(paths[unit], paths[unit], unit)
            self.assertEqual(metrics[f"{unit}_f05"], 100)
            self.assertEqual(metrics[f"{unit}_tp"], 1)
            self.assertEqual(selections[0]["reference"], 0)

    def test_gleu_sources_follow_condition_and_reuse_supplied_target_tokens(self) -> None:
        for condition in experiment.CONDITIONS:
            gleu = Mock()
            gleu.calculate_gleu_score.side_effect = [0.85, 0.65]
            char, word, source = evaluation.gleu_scores(
                gleu, self.row, condition, "我爱中文。", "我 爱 中文 。"
            )
            self.assertEqual((char, word), (85, 65))
            self.assertEqual(source, self.row["P_input" if condition == "P" else "D_input"])
            first, second = gleu.calculate_gleu_score.call_args_list
            self.assertEqual(first.args, (self.row["source"], "我爱中文。", self.row["target"]))
            self.assertEqual(first.kwargs, {"n": 4, "tokenization": "char"})
            self.assertEqual(second.args, (source, "我 爱 中文 。", self.row["target_segmented"]))
            self.assertEqual(second.kwargs["tokenization"], "word")

    def test_invalid_gleu_is_not_a_success_shaped_score(self) -> None:
        for value in (float("nan"), float("inf"), -0.01, 100):
            gleu = Mock()
            gleu.calculate_gleu_score.return_value = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                evaluation.gleu_scores(gleu, self.row, "R", self.row["target"], self.row["target_segmented"])

    def test_deltas_use_unrounded_metrics(self) -> None:
        values = {"R": 10.004, "D": 10.005, "P": 10.006}
        scores = [
            {"model": model, "condition": condition, **{key: values[condition] for key in evaluation.METRICS}}
            for model in experiment.MODELS for condition in experiment.CONDITIONS
        ]
        deltas = evaluation.differences(scores)
        self.assertEqual(len(deltas), 4)
        for row in deltas:
            self.assertAlmostEqual(
                row["character_f05"], 0.002 if row["comparison"] == "P-R" else 0.001
            )

    def test_tokenization_diagnostic_preserves_reference_and_only_reads_hypothesis_tokens(self) -> None:
        prediction = {"R": self.row["target"], "D": self.row["source"], "P": "我爱语法。"}
        segments = {
            self.row["target"]: "我 爱 中 文 。", self.row["source"]: self.row["D_input"],
            "我爱语法。": "我 爱 语法 。",
        }
        records = evaluation.tokenization_audit_records([self.row], [prediction], segments, "kimi")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["check"], "exact_reference_text")
        self.assertFalse(records[0]["boundaries_match"])
        self.assertEqual(records[0]["expected_segmented"], "我 爱 中文 。")
        self.assertTrue(records[1]["boundaries_match"])
        summary = evaluation.summarize_tokenization_audit(records)
        self.assertEqual(summary["reference_tokenization_mismatch_predictions"], 1)
        self.assertEqual(summary["distinct_reference_mismatch_sources"], 1)
        self.assertEqual(summary["unchanged_source_tokenization_mismatches"], 0)
        self.assertEqual(self.row["target_segmented"], "我 爱 中文 。")

    def test_tokenization_diagnostic_does_not_claim_reference_coverage_without_exact_matches(self) -> None:
        prediction = {condition: "我爱语法。" for condition in experiment.CONDITIONS}
        records = evaluation.tokenization_audit_records(
            [self.row], [prediction], {"我爱语法。": "我 爱 语法 。"}, "kimi"
        )
        self.assertEqual(records, [])
        self.assertEqual(evaluation.summarize_tokenization_audit(records)["exact_reference_text_predictions"], 0)

    def fixture_run(self) -> tuple[Path, Path, str]:
        wb = self.root / "wb"
        module = wb / "src/pipeline/alignment/step2_similarity_alignment_projection.py"
        module.parent.mkdir(parents=True)
        module.write_text("# Synthetic dependency fingerprint only.\n")
        shape = self.root / "shape.csv"
        shape.write_text("CharA,CharB,similarity\n")
        config_path = self.root / "preparation_config.json"
        experiment.atomic_json(config_path, {
            "rows": 1, "reference_scope": "selected single reference",
            "wb_sha256": experiment.file_hash(module), "shape_sha256": experiment.file_hash(shape),
        })
        path = self.root / "prepared.jsonl"
        path.write_text(json.dumps(self.row, ensure_ascii=False) + "\n")
        prepared_hash = experiment.file_hash(path)
        experiment.atomic_json(self.root / "prepared_manifest.json", {
            "rows": 1, "carry_forward_rows": 0, "config_sha256": experiment.file_hash(config_path),
            "prepared_sha256": prepared_hash,
        })
        for model in experiment.MODELS:
            folder = self.root / model
            config = {
                "prepared_sha256": prepared_hash, **experiment.MODELS[model],
                "conditions": list(experiment.CONDITIONS),
            }
            experiment.atomic_json(folder / "generation_config.json", config)

            def fake_call(**kwargs):
                data = {
                    "model": kwargs["model"], "usage": {"completion_tokens": 5},
                    "choices": [{"finish_reason": "stop", "message": {"content": self.row["target"]}}],
                }
                kwargs["response_observer"]({"attempt": 1, "http_status": 200, "response": data})
                return self.row["target"], {"model": kwargs["model"], "format_retries": 0}

            prediction = experiment.generate_row(
                self.row, model_config=experiment.MODELS[model],
                run_identity=experiment.identity_hash(config),
                journal=folder / "requests", api_key="synthetic-key", call_model=fake_call,
            )
            path = folder / "predictions.jsonl"
            path.write_text(json.dumps(prediction, ensure_ascii=False) + "\n")
            experiment.atomic_json(folder / "status.json", {
                "status": "completed", "rows": 1, "predictions_sha256": experiment.file_hash(path),
            })
        return wb, shape, prepared_hash

    def test_prediction_load_verifies_real_condition_receipts(self) -> None:
        _, _, prepared_hash = self.fixture_run()
        rows = evaluation.load_predictions(self.root, "kimi", [self.row], prepared_hash)
        self.assertEqual(rows[0]["P"], self.row["target"])
        receipt_path = self.root / "kimi/requests/1.P.json"
        receipt = experiment.read_json(receipt_path)
        receipt["prediction"] = "替换结果"
        experiment.atomic_json(receipt_path, receipt)
        with self.assertRaisesRegex(ValueError, "receipt mismatch"):
            evaluation.load_predictions(self.root, "kimi", [self.row], prepared_hash)

    def segmentation_bundle(self, prepared_hash: str) -> tuple[Path, dict]:
        bundle = {
            "schema": "ltp-output-segmentations-v1",
            "prepared_sha256": prepared_hash,
            "prediction_sha256": {
                model: experiment.file_hash(self.root / model / "predictions.jsonl")
                for model in experiment.MODELS
            },
            "model": {
                "model_id": "LTP/base", "model_revision": "fixture-pinned-revision",
                "ltp_version": "4.2.14", "python_version": "3.11.9", "batch_size": 32,
            },
            "segmentations": {self.row["target"]: self.row["target_segmented"]},
        }
        path = self.root / "base_segmentations.json"
        experiment.atomic_json(path, bundle)
        return path, bundle

    def test_saved_segmentation_bundle_is_bound_to_exact_input_and_output_files(self) -> None:
        _, _, prepared_hash = self.fixture_run()
        path, bundle = self.segmentation_bundle(prepared_hash)
        predictions = {
            model: evaluation.load_predictions(self.root, model, [self.row], prepared_hash)
            for model in experiment.MODELS
        }
        segments, model = evaluation.load_saved_segmentations(
            path, prepared_hash=prepared_hash, prediction_hashes=bundle["prediction_sha256"],
            predictions=predictions,
        )
        self.assertEqual(segments, {self.row["target"]: self.row["target_segmented"]})
        self.assertEqual(model["model_id"], "LTP/base")
        self.assertEqual(model["batch_size"], 32)
        changes = [
            {"schema": "unknown"},
            {"prepared_sha256": "another input"},
            {"prediction_sha256": {"deepseek": "different"}},
            {"model": {"model_id": "LTP/base"}},
            {"model": {**bundle["model"], "batch_size": True}},
            {"segmentations": {}},
            {"segmentations": {self.row["target"]: "修改 的 文字"}},
            {"segmentations": {self.row["target"]: "我  爱 中文 。"}},
            {"segmentations": {self.row["target"]: "\ufeff我 爱 中文 。"}},
            {"segmentations": {**bundle["segmentations"], "额外": "额 外"}},
        ]
        for change in changes:
            with self.subTest(change=change):
                experiment.atomic_json(path, {**copy.deepcopy(bundle), **change})
                with self.assertRaises(ValueError):
                    evaluation.load_saved_segmentations(
                        path, prepared_hash=prepared_hash,
                        prediction_hashes=bundle["prediction_sha256"], predictions=predictions,
                    )

    def test_incomplete_or_modified_predictions_are_rejected(self) -> None:
        _, _, prepared_hash = self.fixture_run()
        status_path = self.root / "kimi/status.json"
        status = experiment.read_json(status_path)
        experiment.atomic_json(status_path, {**status, "status": "pilot_completed"})
        with self.assertRaisesRegex(ValueError, "must be completed"):
            evaluation.load_predictions(self.root, "kimi", [self.row], prepared_hash)
        experiment.atomic_json(status_path, status)
        with (self.root / "kimi/predictions.jsonl").open("a") as stream:
            stream.write("\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            evaluation.load_predictions(self.root, "kimi", [self.row], prepared_hash)

    def test_accounting_keeps_rejected_responses_separate_from_accepted_predictions(self) -> None:
        self.fixture_run()
        path = self.root / "kimi/requests/1.D.json"
        receipt = experiment.read_json(path)
        receipt["previous_failures"] = [{
            "responses": [
                {"attempt": 1, "http_status": 429, "error_body": "Rate limited"},
                {"attempt": 2, "http_status": 200, "response": {
                    "choices": [{"finish_reason": "length", "message": {"content": "截断"}}],
                    "usage": {"completion_tokens_details": {"reasoning_tokens": 1}},
                }},
            ],
        }]
        experiment.atomic_json(path, receipt)
        counts = evaluation.generation_accounting(self.root, "kimi", [self.row])
        self.assertEqual(counts["accepted_api_predictions"], 3)
        self.assertEqual(counts["http_success_responses"], 4)
        self.assertEqual(counts["http_error_responses"], 1)
        self.assertEqual(counts["truncated_responses"], 1)
        self.assertEqual(counts["rate_limited_responses"], 1)
        self.assertEqual(counts["responses_with_nonzero_reasoning_counter"], 1)

    def run_synthetic_evaluation(self, *, saved_segments: bool) -> None:
        wb, shape, prepared_hash = self.fixture_run()
        bundle_path = self.segmentation_bundle(prepared_hash)[0] if saved_segments else None
        fake_repo = self.root / "synthetic_repo"
        code = fake_repo / "scripts"
        code.mkdir(parents=True)
        for name in (
            "projection_character_m2.py", "projection_word_m2.py", "movement_m2.py",
            "movement_aware_compare.py", "evaluation_segmentation.py",
            "evaluate_gold_reference_experiment.py",
        ):
            (code / name).write_text("# Synthetic fingerprint.\n")
        gleu_root = fake_repo / "external_tools/multi-reference-GLEU"
        gleu_root.mkdir(parents=True)
        (gleu_root / "gleu_wrapper.py").write_text("# Synthetic fingerprint.\n")
        converter = Mock()
        converter.convert_many.side_effect = lambda pairs, **kwargs: [(self.edits, {}, True) for _ in pairs]
        segmentation = Mock()
        segmentation.get_many.return_value = {self.row["target"]: self.row["target_segmented"]}
        gleu = Mock()
        gleu.calculate_gleu_score.return_value = 1.0
        output = self.root / "evaluation"
        with (
            patch.object(evaluation, "ROOT", fake_repo),
            patch.object(evaluation, "CachedConverter", return_value=converter),
            patch.object(evaluation, "LtpSegmentationCache", return_value=segmentation),
            patch.object(evaluation.importlib, "import_module", return_value=gleu),
        ):
            evaluation.run_evaluation(
                self.root, output, wb_repo=wb, shape_path=shape, batch_size=2,
                hypothesis_segmentations=bundle_path,
            )
        manifest = experiment.read_json(output / "evaluation_manifest.json")
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(len(manifest["scores"]), 6)
        self.assertEqual(len(manifest["deltas"]), 4)
        for score in manifest["scores"]:
            self.assertTrue(all(score[key] == 100 for key in evaluation.METRICS))
        self.assertEqual(segmentation.get_many.call_count, 0 if saved_segments else 2)
        self.assertEqual(segmentation.close.call_count, 0 if saved_segments else 1)
        for call in segmentation.get_many.call_args_list:
            self.assertEqual(call.args[0], [self.row["target"]] * 3)
        with (output / "kimi/P.gleu_inputs.tsv").open() as stream:
            inputs = list(csv.DictReader(stream, delimiter="\t"))
        self.assertEqual(inputs[0]["word_source"], self.row["P_input"])
        self.assertEqual(inputs[0]["word_reference"], self.row["target_segmented"])
        self.assertNotIn("T3", (output / "metrics.tsv").read_text())
        for relative, digest in manifest["artifacts"].items():
            self.assertEqual(experiment.file_hash(output / relative), digest)
        self.assertEqual(manifest["generation"]["kimi"]["http_responses"], 3)
        self.assertEqual(manifest["tokenization_audit"]["exact_reference_text_predictions"], 6)
        self.assertEqual(manifest["tokenization_audit"]["reference_tokenization_mismatch_predictions"], 0)
        if saved_segments:
            self.assertEqual(manifest["config"]["ltp_model"], "LTP/base")
            self.assertEqual(manifest["config"]["ltp_batch_size"], 32)
            self.assertEqual(
                manifest["config"]["saved_hypothesis_segmentations"]["sha256"],
                experiment.file_hash(bundle_path),
            )
            report = (output / "RESULTS.md").read_text()
            self.assertIn("LTP/small", report)
            self.assertIn("LTP/base", report)
            self.assertIn("zero reference/output tokenization mismatches", report)
        else:
            self.assertEqual(manifest["config"]["ltp_model"], "LTP/small")
            self.assertNotIn("saved_hypothesis_segmentations", manifest["config"])

    def test_full_synthetic_evaluation_has_six_conditions_without_new_inference(self) -> None:
        self.run_synthetic_evaluation(saved_segments=False)

    def test_saved_base_segmentations_cannot_fall_back_to_default_ltp(self) -> None:
        self.run_synthetic_evaluation(saved_segments=True)


if __name__ == "__main__":
    unittest.main()
