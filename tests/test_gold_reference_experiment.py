from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import run_gold_reference_experiment as experiment
from scripts import run_iterative_gec as iterative


class GoldReferenceFixtures:
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.original = {
            "Index": "1", "Target_ID": "9",
            "Target_Text": "我 喜欢 中文 。", "Source_Text": "我喜 欢中 文 。",
        }

    def write_csv(self, rows: list[dict[str, str]]) -> Path:
        path = self.root / "input.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=experiment.CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def row(self) -> dict:
        return experiment.read_csv(self.write_csv([self.original]))[0]

    def prepare(self, row: dict, projected: str = "我喜 欢 中文 。") -> dict:
        self.segment = Mock(return_value="我 喜 欢 中文 。")
        self.project = Mock(return_value={"projected": projected, "stats": {"exact": 5}})
        return experiment.prepare_row(row, segment=self.segment, project=self.project)


class GoldReferenceInputTests(GoldReferenceFixtures, unittest.TestCase):
    def test_only_raw_source_is_sent_to_ltp(self) -> None:
        result = self.prepare(self.row())
        self.segment.assert_called_once_with("我喜欢中文。")
        self.project.assert_called_once_with(
            source_segmented="我 喜 欢 中文 。", target_segmented="我 喜欢 中文 。"
        )
        self.assertEqual(result["R_input"], "我喜欢中文。")

    def test_human_boundary_changes_do_not_affect_inputs(self) -> None:
        before = self.prepare(self.row())
        self.original["Source_Text"] = "我 喜欢 中 文。"
        after = self.prepare(self.row())
        for key in ("R_input", "D_input", "P_input", "carry_P_from_D"):
            self.assertEqual(before[key], after[key])

    def test_target_tokens_are_preserved(self) -> None:
        self.original["Target_Text"] = "\ufeff我  喜欢\u3000中 文 。 "
        row = self.row()
        self.prepare(row)
        self.assertEqual(self.project.call_args.kwargs["target_segmented"], "我 喜欢 中 文 。")
        self.assertEqual(row["original"]["Target_Text"], self.original["Target_Text"])
        self.assertEqual(self.segment.call_count, 1)

    def test_projection_cannot_change_characters(self) -> None:
        with self.assertRaisesRegex(ValueError, "P changed source"):
            self.prepare(self.row(), "我 喜欢 英文 。")

    def test_direct_segmentation_cannot_change_characters(self) -> None:
        with self.assertRaisesRegex(ValueError, "D changed source"):
            experiment.prepare_row(
                self.row(), segment=lambda source: "改动 原文",
                project=lambda **kwargs: {"projected": "我喜欢中文。", "stats": {}},
            )

    def test_boundary_equivalence_drives_carry_forward(self) -> None:
        result = self.prepare(self.row(), "我   喜\t欢 中文 。")
        self.assertTrue(result["carry_P_from_D"])

    def test_duplicate_raw_sources_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            experiment.read_csv(self.write_csv([
                self.original, {**self.original, "Index": "2", "Source_Text": "我 喜欢 中文。"},
            ]))

    def test_invalid_rows_fail_closed(self) -> None:
        for change in (
            {"Index": "../1"}, {"Source_Text": ""}, {"Target_Text": " \ufeff "},
            {"Target_Text": "我\n喜欢中文。"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                experiment.read_csv(self.write_csv([{**self.original, **change}]))

    def test_empty_csv_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "no data"):
            experiment.read_csv(self.write_csv([]))

    def test_gold_and_human_boundaries_are_absent_from_prompts(self) -> None:
        self.original["Target_Text"] = "完全 不同 的 金标准 句子"
        row = self.prepare(self.row())
        for condition in experiment.CONDITIONS:
            spec = experiment.request_spec(row, condition, "run")
            self.assertNotIn(row["target"], spec["prompt"])
            self.assertNotIn(row["original"]["Source_Text"], spec["prompt"])
            self.assertTrue(spec["prompt"].endswith(row[f"{condition}_input"]))
        with self.assertRaises(ValueError):
            experiment.request_spec(row, "I", "run")


class GoldReferenceGenerationTests(GoldReferenceFixtures, unittest.TestCase):
    def generate(self, row: dict, call: Mock, **kwargs) -> dict:
        return experiment.generate_row(
            row, model_config=experiment.MODELS["deepseek"], run_identity="frozen",
            journal=self.root / "requests", api_key="synthetic-private-token",
            call_model=call, **kwargs,
        )

    def test_three_conditions_and_exact_settings(self) -> None:
        row = self.prepare(self.row())
        call = Mock(return_value=("我喜欢中文。", {"model": "deepseek-v4-pro"}))
        result = self.generate(row, call)
        self.assertEqual(call.call_count, 3)
        for condition, invocation in zip(experiment.CONDITIONS, call.call_args_list):
            self.assertTrue(invocation.kwargs["strict_settings"])
            self.assertEqual(invocation.kwargs["temperature"], 0.000001)
            self.assertIsNone(invocation.kwargs["max_tokens"])
            self.assertTrue(invocation.kwargs["prompt"].endswith(row[f"{condition}_input"]))
            self.assertEqual(result[condition], "我喜欢中文。")

    def test_convergence_carries_only_d_to_p(self) -> None:
        row = self.prepare(self.row(), "我 喜 欢 中文 。")
        call = Mock(side_effect=[("R结果", {}), ("D结果", {})])
        result = self.generate(row, call)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(result["P"], result["D"])
        self.assertNotEqual(result["R"], result["D"])
        self.assertEqual(result["meta"]["P"]["carried_from"], "D")

    def test_resume_never_repeats_successful_calls(self) -> None:
        row = self.prepare(self.row())
        call = Mock(return_value=("结果", {}))
        first = self.generate(row, call)
        call.reset_mock()
        self.assertEqual(self.generate(row, call), first)
        call.assert_not_called()

    def test_success_before_later_failure_is_retained(self) -> None:
        row = self.prepare(self.row())
        call = Mock(side_effect=[("原始结果", {}), RuntimeError("API rejected request")])
        with self.assertRaisesRegex(RuntimeError, "API rejected"):
            self.generate(row, call)
        after = Mock(return_value=("分词结果", {}))
        with self.assertRaisesRegex(RuntimeError, "Recorded failure"):
            self.generate(row, after)
        after.assert_not_called()
        result = self.generate(row, after, retry_failed=True)
        self.assertEqual(after.call_count, 2)
        self.assertEqual(result["R"], "原始结果")
        self.assertEqual(len(experiment.read_json(self.root / "requests/1.D.json")["previous_failures"]), 1)

    def test_pending_request_blocks_automatic_reissue(self) -> None:
        row = self.prepare(self.row())
        experiment.atomic_json(self.root / "requests/1.R.json", {
            "request": experiment.request_spec(row, "R", "frozen"), "status": "started",
        })
        call = Mock()
        with self.assertRaisesRegex(RuntimeError, "Unresolved in-flight"):
            self.generate(row, call, retry_failed=True)
        call.assert_not_called()

    def test_config_or_prompt_mismatch_blocks_resume(self) -> None:
        row = self.prepare(self.row())
        call = Mock(return_value=("结果", {}))
        self.generate(row, call)
        row["R_input"] = "另一句"
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.generate(row, call)

    def test_api_key_is_not_written_to_receipts(self) -> None:
        row = self.prepare(self.row())
        call = Mock(side_effect=RuntimeError("bad synthetic-private-token"))
        with self.assertRaises(RuntimeError):
            self.generate(row, call)
        text = (self.root / "requests/1.R.json").read_text()
        self.assertNotIn("synthetic-private-token", text)
        self.assertIn("[REDACTED]", text)


class StrictProviderTests(unittest.TestCase):
    def call(self, response: Mock, **kwargs):
        with patch.object(iterative, "http_session") as session:
            session.return_value.post.return_value = response
            self.session = session.return_value
            return iterative.call_llm(
                prompt=iterative.PROMPT_RAW_PAPER.format(sentence="原文"),
                api_key="synthetic-key", base_url="https://provider.invalid/v1",
                model="expected-model", temperature=None, max_tokens=512,
                thinking_disabled=True, timeout=10, retries=3, sleep_seconds=0,
                strict_settings=True, **kwargs,
            )

    def response(self, **changes) -> Mock:
        data = {
            "model": "expected-model", "id": "fixture",
            "choices": [{"finish_reason": "stop", "message": {"content": "结果"}}],
            "usage": {"completion_tokens": 2},
        }
        data.update(changes)
        return Mock(status_code=200, json=Mock(return_value=data))

    def test_success_records_raw_receipt_and_omits_temperature(self) -> None:
        observer = Mock()
        prediction, meta = self.call(self.response(), response_observer=observer)
        self.assertEqual(prediction, "结果")
        self.assertEqual(meta["raw_content"], "结果")
        self.assertEqual(meta["finish_reason"], "stop")
        observer.assert_called_once()
        payload = self.session.post.call_args.kwargs["json"]
        self.assertNotIn("temperature", payload)
        self.assertEqual(payload["thinking"], {"type": "disabled"})

    def test_model_finish_reason_and_reasoning_are_strict(self) -> None:
        for response in (
            self.response(model="replacement-model"),
            self.response(choices=[{"finish_reason": "length", "message": {"content": "结果"}}]),
            self.response(choices=[{
                "finish_reason": "stop", "message": {"content": "结果", "reasoning_content": "分析"},
            }]),
        ):
            with self.subTest(response=response), self.assertRaises(iterative.LLMConfigurationError):
                self.call(response)
            self.assertEqual(self.session.post.call_count, 1)

    def test_empty_reasoning_does_not_require_a_zero_usage_counter(self) -> None:
        response = self.response(
            usage={"completion_tokens_details": {"reasoning_tokens": 1}},
            choices=[{"finish_reason": "stop", "message": {
                "content": "结果", "reasoning_content": "",
            }}],
        )
        _, meta = self.call(response)
        self.assertEqual(meta["usage"]["completion_tokens_details"]["reasoning_tokens"], 1)
        self.assertEqual(self.session.post.call_args.kwargs["json"]["thinking"], {"type": "disabled"})

    def test_auth_and_unsupported_settings_do_not_retry_or_relax(self) -> None:
        for status, body in ((401, "unauthorized"), (400, "unsupported thinking"), (404, "model")):
            with self.subTest(status=status), self.assertRaises(iterative.LLMConfigurationError):
                self.call(Mock(status_code=status, text=body))
            self.assertEqual(self.session.post.call_count, 1)

    def test_content_filter_identity_fallback_is_explicit(self) -> None:
        prediction, meta = self.call(Mock(status_code=400, text="content_filter"))
        self.assertEqual(prediction, "原文")
        self.assertTrue(meta["content_filter_fallback"])
        self.assertEqual(self.session.post.call_count, 1)

    def test_receipt_write_failure_cannot_repeat_paid_call(self) -> None:
        with self.assertRaisesRegex(iterative.LLMConfigurationError, "persist"):
            self.call(self.response(), response_observer=Mock(side_effect=OSError("disk full")))
        self.assertEqual(self.session.post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
