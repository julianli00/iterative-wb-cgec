from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from scripts import run_iterative_gec


class FakeWBModule:
    def load_bert_model(self, _model_name: str) -> None:
        return None

    def load_shape_table(self, _path: str) -> dict:
        return {}

    def ltp_segment(self, text: str) -> str:
        if text == "原句":
            return "原 句"
        return "改 句"


class IterativeConvergenceTest(unittest.TestCase):
    def test_call_llm_can_omit_temperature_for_provider_fixed_models(self) -> None:
        response = mock.Mock(status_code=200)
        response.json.return_value = {
            "model": "kimi-k2.6",
            "choices": [{"message": {"content": "改正句"}}],
            "usage": {"total_tokens": 8},
        }
        session = mock.Mock()
        session.post.return_value = response

        with mock.patch.object(run_iterative_gec, "http_session", return_value=session):
            output, metadata = run_iterative_gec.call_llm(
                prompt="测试",
                api_key="secret",
                base_url="https://api.moonshot.ai/v1",
                model="kimi-k2.6",
                temperature=None,
                max_tokens=512,
                thinking_disabled=True,
                timeout=1,
                retries=0,
                sleep_seconds=0,
            )

        payload = session.post.call_args.kwargs["json"]
        self.assertNotIn("temperature", payload)
        self.assertEqual(payload["max_tokens"], 512)
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(output, "改正句")
        self.assertEqual(metadata["model"], "kimi-k2.6")

    def test_call_llm_retries_self_analysis_instead_of_projecting_it(self) -> None:
        malformed = mock.Mock(status_code=200)
        malformed.json.return_value = {
            "model": "kimi-k2.6",
            "choices": [
                {
                    "message": {
                        "content": "原句。等等，让我重新考虑。" + "分析" * 100
                    }
                }
            ],
            "usage": {},
        }
        valid = mock.Mock(status_code=200)
        valid.json.return_value = {
            "model": "kimi-k2.6",
            "choices": [{"message": {"content": "改正句。"}}],
            "usage": {},
        }
        session = mock.Mock()
        session.post.side_effect = [malformed, valid]

        with mock.patch.object(run_iterative_gec, "http_session", return_value=session):
            output, metadata = run_iterative_gec.call_llm(
                prompt="句子如下：原句。",
                api_key="secret",
                base_url="https://api.moonshot.ai/v1",
                model="kimi-k2.6",
                temperature=None,
                max_tokens=512,
                thinking_disabled=True,
                timeout=1,
                retries=1,
                sleep_seconds=0,
            )

        self.assertEqual(output, "改正句。")
        self.assertEqual(metadata["format_retries"], 1)
        self.assertEqual(session.post.call_count, 2)

    def test_content_filter_is_recorded_as_an_identity_fallback(self) -> None:
        response = mock.Mock(
            status_code=400,
            text='{"error":{"type":"content_filter","message":"high risk"}}',
        )
        session = mock.Mock()
        session.post.return_value = response

        with mock.patch.object(run_iterative_gec, "http_session", return_value=session):
            output, metadata = run_iterative_gec.call_llm(
                prompt="句子如下：我 爱 中文 。",
                api_key="secret",
                base_url="https://api.moonshot.ai/v1",
                model="kimi-k2.6",
                temperature=None,
                max_tokens=512,
                thinking_disabled=True,
                timeout=1,
                retries=5,
                sleep_seconds=0,
            )

        self.assertEqual(output, "我爱中文。")
        self.assertTrue(metadata["content_filter_fallback"])
        self.assertEqual(session.post.call_count, 1)

    def test_matching_resume_rejects_changed_source_or_target(self) -> None:
        result = {
            "id": "7",
            "source": "原句",
            "target": "改句",
            "T3": "输出",
            "ok": True,
        }
        self.assertTrue(
            run_iterative_gec.result_matches_input(
                result,
                {"id": "7", "source": "原句", "target": "改句"},
                3,
            )
        )
        self.assertFalse(
            run_iterative_gec.result_matches_input(
                result,
                {"id": "7", "source": "新原句", "target": "改句"},
                3,
            )
        )
        self.assertFalse(
            run_iterative_gec.result_matches_input(
                result,
                {"id": "7", "source": "原句", "target": "新改句"},
                3,
            )
        )

    def test_converged_segmentation_skips_later_llm_calls_and_carries_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            input_path = tmp_dir / "input.tsv"
            input_path.write_text("原句\t改句\n", encoding="utf-8")

            args = SimpleNamespace(
                input=input_path,
                limit=1,
                max_t=5,
                out_dir=tmp_dir,
                run_name="convergence_test",
                prompt_variant="paper",
                projection_threshold=0.85,
                bert_model="fake-bert",
                timeout=1,
                retries=0,
                sleep=0.0,
                row_sleep=0.0,
                stop_on_error=True,
            )

            llm_outputs = [
                ("T0-output", {"model": "fake"}),
                ("T1-output", {"model": "fake"}),
                ("T2-output", {"model": "fake"}),
            ]
            projections = [
                {"projected": "原句", "stats": {}},
                {"projected": "原句", "stats": {}},
            ]

            with (
                mock.patch.object(
                    run_iterative_gec,
                    "load_env",
                    return_value={
                        "DEEPSEEK_API_KEY": "test-key",
                        "DEEPSEEK_MODEL": "fake-model",
                    },
                ),
                mock.patch.object(
                    run_iterative_gec,
                    "load_wb_module",
                    return_value=FakeWBModule(),
                ),
                mock.patch.object(
                    run_iterative_gec,
                    "call_llm",
                    side_effect=llm_outputs,
                ) as call_llm,
                mock.patch.object(
                    run_iterative_gec,
                    "project_with_existing_boundaries",
                    side_effect=projections,
                ) as project,
            ):
                run_iterative_gec.run(args)

            self.assertEqual(call_llm.call_count, 3)
            self.assertEqual(project.call_count, 2)

            with (tmp_dir / "convergence_test.tsv").open(encoding="utf-8") as stream:
                row = next(csv.DictReader(stream, delimiter="\t"))

            self.assertEqual(row["T2"], "T2-output")
            self.assertEqual(row["T3"], "T2-output")
            self.assertEqual(row["T4"], "T2-output")
            self.assertEqual(row["T5"], "T2-output")
            self.assertEqual(row["S3"], row["S2"])
            self.assertEqual(row["S4"], row["S2"])
            self.assertEqual(row["S5"], row["S2"])

            jsonl_path = tmp_dir / "convergence_test.jsonl"
            result = json.loads(jsonl_path.read_text(encoding="utf-8"))
            self.assertEqual(
                result["meta"]["convergence"],
                {
                    "converged": True,
                    "at_S": 3,
                    "unchanged_from_S": 2,
                    "carried_from_T": 2,
                    "carried_rounds": [3, 4, 5],
                },
            )

    def test_resume_only_processes_rows_not_already_converged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            resume_path = tmp_dir / "previous.jsonl"
            previous_rows = [
                {
                    "id": "0",
                    "source": "原句",
                    "target": "改句",
                    "S1": "原 句",
                    "T0": "改句",
                    "T1": "改句",
                    "S2": "原 句",
                    "T2": "改句",
                    "S3": "原 句",
                    "T3": "改句",
                    "meta": {
                        "api": [],
                        "projection": [],
                        "convergence": {
                            "converged": True,
                            "at_S": 3,
                            "unchanged_from_S": 2,
                            "carried_from_T": 2,
                            "carried_rounds": [3],
                        },
                    },
                    "ok": True,
                    "seconds": 1.0,
                },
                {
                    "id": "1",
                    "source": "原句",
                    "target": "改句",
                    "S1": "原 句",
                    "T0": "改句",
                    "T1": "改句",
                    "S2": "原 句",
                    "T2": "改句",
                    "S3": "原句",
                    "T3": "改句",
                    "meta": {
                        "api": [],
                        "projection": [],
                        "convergence": {
                            "converged": False,
                            "checked_through_S": 3,
                        },
                    },
                    "ok": True,
                    "seconds": 1.0,
                },
            ]
            resume_path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in previous_rows),
                encoding="utf-8",
            )

            args = SimpleNamespace(
                input=tmp_dir / "unused.tsv",
                resume_jsonl=resume_path,
                limit=0,
                max_t=4,
                out_dir=tmp_dir,
                run_name="resume_test",
                prompt_variant="paper",
                projection_threshold=0.85,
                bert_model="fake-bert",
                timeout=1,
                retries=0,
                sleep=0.0,
                row_sleep=0.0,
                stop_on_error=True,
            )

            with (
                mock.patch.object(
                    run_iterative_gec,
                    "load_env",
                    return_value={
                        "DEEPSEEK_API_KEY": "test-key",
                        "DEEPSEEK_MODEL": "fake-model",
                    },
                ),
                mock.patch.object(
                    run_iterative_gec,
                    "load_wb_module",
                    return_value=FakeWBModule(),
                ),
                mock.patch.object(
                    run_iterative_gec,
                    "project_with_existing_boundaries",
                    return_value={"projected": "新 分词", "stats": {}},
                ) as project,
                mock.patch.object(
                    run_iterative_gec,
                    "call_llm",
                    return_value=("T4-output", {"model": "fake"}),
                ) as call_llm,
            ):
                run_iterative_gec.run(args)

            self.assertEqual(project.call_count, 1)
            self.assertEqual(call_llm.call_count, 1)

            with (tmp_dir / "resume_test.tsv").open(encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))

            self.assertEqual(rows[0]["S4"], rows[0]["S3"])
            self.assertEqual(rows[0]["T4"], rows[0]["T3"])
            self.assertEqual(rows[1]["S4"], "新 分词")
            self.assertEqual(rows[1]["T4"], "T4-output")

    def test_partial_resume_keeps_successful_prefix_and_retries_from_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            input_path = tmp_dir / "input.tsv"
            input_path.write_text("句零\t改零\n句一\t改一\n句二\t改二\n", encoding="utf-8")
            resume_path = tmp_dir / "partial.jsonl"
            resume_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "id": "0",
                                "source": "句零",
                                "target": "改零",
                                "S1": "句 零",
                                "T0": "改零",
                                "T1": "改零",
                                "S2": "句 零",
                                "T2": "改零",
                                "meta": {"api": [], "projection": [], "convergence": {}},
                                "ok": True,
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {"id": "1", "source": "句一", "target": "改一", "ok": False},
                            ensure_ascii=False,
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            args = SimpleNamespace(
                input=input_path,
                resume_jsonl=None,
                resume_partial_jsonl=resume_path,
                limit=0,
                max_t=2,
                out_dir=tmp_dir,
                run_name="partial",
                prompt_variant="paper",
                projection_threshold=0.85,
                bert_model="fake-bert",
                timeout=1,
                retries=0,
                sleep=0.0,
                row_sleep=0.0,
                workers=1,
                checkpoint_every=1,
                stop_on_error=True,
            )
            with (
                mock.patch.object(
                    run_iterative_gec,
                    "load_env",
                    return_value={"DEEPSEEK_API_KEY": "test-key", "DEEPSEEK_MODEL": "fake"},
                ),
                mock.patch.object(
                    run_iterative_gec, "load_wb_module", return_value=FakeWBModule()
                ),
                mock.patch.object(
                    run_iterative_gec,
                    "call_llm",
                    return_value=("改句", {"model": "fake"}),
                ) as call_llm,
                mock.patch.object(
                    run_iterative_gec,
                    "project_with_existing_boundaries",
                    side_effect=lambda **kwargs: {
                        "projected": kwargs["source_segmented"],
                        "stats": {},
                    },
                ),
            ):
                run_iterative_gec.run(args)

            self.assertEqual(call_llm.call_count, 4)
            with (tmp_dir / "partial.tsv").open(encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual([row["id"] for row in rows], ["0", "1", "2"])
            self.assertTrue(all(row["T2"] for row in rows))

    def test_matching_resume_only_reprocesses_changed_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            input_path = tmp_dir / "input.tsv"
            input_path.write_text(
                "句零\t改零\n句一修\t改一修\n句二\t改二\n", encoding="utf-8"
            )
            previous_rows = []
            for index, (source, target) in enumerate(
                [("句零", "改零"), ("句一旧", "改一旧"), ("句二", "改二")]
            ):
                previous_rows.append(
                    {
                        "id": str(index),
                        "source": source,
                        "target": target,
                        "S1": source,
                        "T0": target,
                        "T1": target,
                        "S2": source,
                        "T2": target,
                        "meta": {"api": [], "projection": [], "convergence": {}},
                        "ok": True,
                    }
                )
            resume_path = tmp_dir / "previous.jsonl"
            resume_path.write_text(
                "".join(
                    json.dumps(row, ensure_ascii=False) + "\n" for row in previous_rows
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                input=input_path,
                resume_jsonl=None,
                resume_partial_jsonl=None,
                resume_matching_jsonl=resume_path,
                limit=0,
                max_t=2,
                out_dir=tmp_dir,
                run_name="matching",
                prompt_variant="paper",
                projection_threshold=0.85,
                bert_model="fake-bert",
                timeout=1,
                retries=0,
                sleep=0.0,
                row_sleep=0.0,
                workers=1,
                checkpoint_every=1,
                stop_on_error=True,
            )
            with (
                mock.patch.object(
                    run_iterative_gec,
                    "load_env",
                    return_value={"DEEPSEEK_API_KEY": "test-key", "DEEPSEEK_MODEL": "fake"},
                ),
                mock.patch.object(
                    run_iterative_gec, "load_wb_module", return_value=FakeWBModule()
                ),
                mock.patch.object(
                    run_iterative_gec,
                    "call_llm",
                    return_value=("改句", {"model": "fake"}),
                ) as call_llm,
                mock.patch.object(
                    run_iterative_gec,
                    "project_with_existing_boundaries",
                    side_effect=lambda **kwargs: {
                        "projected": kwargs["source_segmented"],
                        "stats": {},
                    },
                ),
            ):
                run_iterative_gec.run(args)

            self.assertEqual(call_llm.call_count, 2)
            with (tmp_dir / "matching.tsv").open(encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual([row["id"] for row in rows], ["0", "1", "2"])
            self.assertEqual(rows[1]["source"], "句一修")
            self.assertEqual(rows[0]["source"], "句零")
            self.assertEqual(rows[2]["source"], "句二")


if __name__ == "__main__":
    unittest.main()
