from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts.copilot_llm import CopilotClient
from scripts import run_iterative_gec
from scripts.run_iterative_gec import (
    gec_output_format_error,
    sentence_from_prompt,
    strip_llm_response,
)


class CopilotBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def client(self) -> CopilotClient:
        client = CopilotClient(
            model="gpt-6-astra",
            state_dir=self.root / "state",
            journal=self.root / "requests.jsonl",
            clean=strip_llm_response,
            validate=gec_output_format_error,
            source_from_prompt=sentence_from_prompt,
            rate_limit=lambda: None,
        )
        client.metadata = {"model": "gpt-6-astra", "settings": "default"}
        return client

    def response(self, text: str = "corrected") -> dict:
        return {
            "ok": True,
            "result": {
                "content": text,
                "metadata": {"model": "gpt-6-astra", "content_filter_fallback": False},
            },
        }

    def call(self, client: CopilotClient, **overrides):
        arguments = {
            "prompt": "句子如下：原 句",
            "model": "gpt-6-astra",
            "temperature": None,
            "max_tokens": None,
            "thinking_disabled": False,
            "timeout": 1,
            "retries": 0,
            "sleep_seconds": 0,
            "request_key": "run:0:T0",
        }
        arguments.update(overrides)
        return client.call_llm(**arguments)

    def test_completed_request_survives_restart_without_regeneration(self) -> None:
        client = self.client()
        with mock.patch.object(client, "_request", return_value=self.response()) as request:
            expected = self.call(client)
            self.assertEqual(self.call(client), expected)
            self.assertEqual(request.call_count, 1)
        restarted = self.client()
        with mock.patch.object(restarted, "_request", side_effect=AssertionError("new call")):
            self.assertEqual(self.call(restarted), expected)

    def test_cache_does_not_cross_sources_stages_or_changed_prompts(self) -> None:
        client = self.client()
        with mock.patch.object(client, "_request", return_value=self.response()) as request:
            self.call(client)
            self.call(client, request_key="run:1:T0")
            self.call(client, request_key="run:0:T1")
            self.call(client, prompt="句子如下：新原句")
            self.assertEqual(request.call_count, 4)

    def test_nondefault_settings_are_rejected(self) -> None:
        client = self.client()
        for overrides in ({"temperature": 0.0}, {"max_tokens": 512}, {"thinking_disabled": True}):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(ValueError, "provider-default"):
                self.call(client, **overrides)

    def test_format_retries_are_journaled_and_not_silently_accepted(self) -> None:
        client = self.client()
        with mock.patch.object(
            client, "_request", side_effect=[self.response(""), self.response("corrected")]
        ):
            with self.assertLogs("scripts.copilot_llm", level="WARNING"):
                correction, metadata = self.call(client, retries=1)
        self.assertEqual(correction, "corrected")
        self.assertEqual(metadata["format_retries"], 1)
        rows = [json.loads(line) for line in client.journal.read_text().splitlines()]
        self.assertEqual([row["ok"] for row in rows], [False, True])

    def test_provider_failure_is_reported_not_identity_fallback(self) -> None:
        client = self.client()
        with mock.patch.object(client, "_request", return_value={"ok": False, "error": "quota exhausted"}):
            with self.assertLogs("scripts.copilot_llm", level="WARNING"):
                with self.assertRaisesRegex(RuntimeError, "quota exhausted"):
                    self.call(client)

    def test_explicit_content_filter_uses_recorded_identity_fallback(self) -> None:
        client = self.client()
        response = self.response("")
        response["result"]["metadata"]["content_filter_fallback"] = True
        with mock.patch.object(client, "_request", return_value=response):
            correction, metadata = self.call(client)
        self.assertEqual(correction, "原句")
        self.assertTrue(metadata["content_filter_fallback"])

    def test_bridge_failure_is_journaled_with_unknown_usage(self) -> None:
        client = self.client()
        with mock.patch.object(client, "_request", side_effect=RuntimeError("bridge stopped")):
            with self.assertRaisesRegex(RuntimeError, "bridge stopped"):
                self.call(client)
        record = json.loads(client.journal.read_text())
        self.assertFalse(record["ok"])
        self.assertTrue(record["usage_unknown"])

    def test_copilot_pipeline_ignores_dotenv_and_http_settings(self) -> None:
        input_path = self.root / "input.tsv"
        input_path.write_text("原句\t改句\n", encoding="utf-8")
        args = SimpleNamespace(
            input=input_path, out_dir=self.root, run_name="copilot-test",
            max_t=3, limit=0, prompt_variant="paper", bert_model="fake",
            projection_threshold=0.85, timeout=1, retries=0, sleep=0,
            row_sleep=0, stop_on_error=True,
        )
        wb = mock.Mock()
        wb.ltp_segment.return_value = "原 句"
        client = mock.Mock(model="gpt-6-astra")
        client.call_llm.return_value = ("改句", {"model": "gpt-6-astra"})
        with (
            mock.patch.dict(os.environ, {"LLM_TEMPERATURE": "not-a-number", "LLM_MAX_TOKENS": "not-an-int"}),
            mock.patch.object(run_iterative_gec, "load_env", side_effect=AssertionError("must not read dotenv")),
            mock.patch.object(run_iterative_gec, "load_wb_module", return_value=wb),
            mock.patch.object(run_iterative_gec, "project_with_existing_boundaries", return_value={"projected": "原 句", "stats": {}}),
        ):
            run_iterative_gec._run(args, copilot_client=client)
        self.assertEqual(client.call_llm.call_count, 2)
        for call in client.call_llm.call_args_list:
            self.assertIsNone(call.kwargs["temperature"])
            self.assertIsNone(call.kwargs["max_tokens"])
            self.assertFalse(call.kwargs["thinking_disabled"])
            self.assertEqual(call.kwargs["api_key"], "")
        row = json.loads((self.root / "copilot-test.jsonl").read_text())
        self.assertEqual([row[stage] for stage in ("T1", "T2", "T3")], ["改句"] * 3)

    def test_node_session_isolation_and_usage_contract(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts/copilot/gec_bridge.test.mjs"
        completed = subprocess.run(
            ["node", "--test", str(script)], capture_output=True, text=True, check=False
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
