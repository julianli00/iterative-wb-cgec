"""Isolated, journaled Copilot SDK calls for the existing GEC runner."""

from __future__ import annotations

from concurrent.futures import Future, TimeoutError as FutureTimeout
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any, Callable
import uuid


BRIDGE = Path(__file__).parent / "copilot/gec_bridge.mjs"
LOGGER = logging.getLogger(__name__)


class CopilotClient:
    def __init__(
        self,
        *,
        model: str,
        state_dir: Path,
        journal: Path,
        clean: Callable[[str], str],
        validate: Callable[[str, str, str], str | None],
        source_from_prompt: Callable[[str], str],
        rate_limit: Callable[[], None],
    ) -> None:
        self.model = model
        self.state_dir = state_dir
        self.journal = journal
        self.clean = clean
        self.validate = validate
        self.source_from_prompt = source_from_prompt
        self.rate_limit = rate_limit
        self._lock = threading.Lock()
        self._journal_lock = threading.Lock()
        self._pending: dict[str, Future[dict[str, Any]]] = {}
        self._cached: dict[str, dict[str, Any]] = {}
        self._process: subprocess.Popen[str] | None = None
        self._closing = False
        self.metadata: dict[str, Any] = {}
        if journal.exists():
            with journal.open(encoding="utf-8") as stream:
                for line in stream:
                    record = json.loads(line)
                    if record.get("ok"):
                        self._cached[record["cache_key"]] = record

    def __enter__(self) -> CopilotClient:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        self._stderr = (self.state_dir / "bridge.stderr.log").open("a", encoding="utf-8")
        ready: Future[dict[str, Any]] = Future()
        self._pending["ready"] = ready
        self._process = subprocess.Popen(
            ["node", str(BRIDGE), self.model, str(self.state_dir.resolve())],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_responses, daemon=True)
        self._reader.start()
        try:
            self.metadata = ready.result(timeout=120)
        except (RuntimeError, FutureTimeout):
            self.close()
            raise
        (self.state_dir / "runtime_metadata.json").write_text(
            json.dumps(self.metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self.close()

    def _fail_pending(self, error: Exception) -> None:
        with self._lock:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(error)
            self._pending.clear()

    def _read_responses(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        try:
            for line in self._process.stdout:
                response = json.loads(line)
                with self._lock:
                    future = self._pending.pop(response["id"], None)
                if future is None:
                    raise RuntimeError(f"Unexpected Copilot response ID: {response['id']}")
                future.set_result(response)
        except (ValueError, KeyError, OSError, RuntimeError) as exc:
            self._fail_pending(exc)
            return
        if not self._closing:
            self._fail_pending(
                RuntimeError(
                    f"Copilot bridge exited unexpectedly; see {self.state_dir / 'bridge.stderr.log'}"
                )
            )

    def _request(self, prompt: str, timeout: int) -> dict[str, Any]:
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("Copilot client has not been started")
        request_id = uuid.uuid4().hex
        future: Future[dict[str, Any]] = Future()
        with self._lock:
            if self._process.poll() is not None:
                raise RuntimeError("Copilot bridge is no longer running")
            self._pending[request_id] = future
            self._process.stdin.write(
                json.dumps(
                    {"id": request_id, "action": "generate", "prompt": prompt, "timeout": timeout},
                    ensure_ascii=False,
                )
                + "\n"
            )
            self._process.stdin.flush()
        return future.result(timeout=timeout + 60)

    def _record(self, record: dict[str, Any]) -> None:
        with self._journal_lock:
            with self.journal.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            if record["ok"]:
                self._cached[record["cache_key"]] = record

    def call_llm(
        self,
        *,
        prompt: str,
        model: str,
        temperature: float | None,
        max_tokens: int | None,
        thinking_disabled: bool,
        timeout: int,
        retries: int,
        sleep_seconds: float,
        request_key: str,
        api_key: str = "",
        base_url: str = "",
    ) -> tuple[str, dict[str, Any]]:
        if model != self.model:
            raise ValueError("Copilot model changed within a run")
        if temperature is not None or max_tokens is not None or thinking_disabled:
            raise ValueError("The Copilot backend requires provider-default generation settings")
        if not request_key:
            raise ValueError("A stable per-source/per-stage request key is required")
        cache_key = hashlib.sha256(
            json.dumps(
                [request_key, model, prompt, self.metadata],
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        cached = self._cached.get(cache_key)
        if cached:
            return cached["correction"], dict(cached["metadata"])
        last_error = ""
        format_retries = 0
        for attempt in range(retries + 1):
            self.rate_limit()
            record: dict[str, Any] = {
                "cache_key": cache_key,
                "request_key": request_key,
                "model": model,
                "prompt": prompt,
                "attempt": attempt,
                "timestamp": time.time(),
                "ok": False,
            }
            try:
                response = self._request(prompt, timeout)
            except (OSError, RuntimeError, FutureTimeout) as exc:
                record.update(error=str(exc), usage_unknown=True)
                self._record(record)
                raise
            record["response"] = response
            if not response["ok"]:
                last_error = response["error"]
            else:
                raw = response["result"]["content"]
                metadata = dict(response["result"]["metadata"])
                filtered = metadata["content_filter_fallback"]
                correction = self.source_from_prompt(prompt) if filtered else self.clean(raw)
                error = None if filtered else self.validate(prompt, raw, correction)
                if error is None:
                    metadata["format_retries"] = format_retries
                    metadata["request_key"] = request_key
                    record.update(
                        ok=True,
                        raw_response=raw,
                        correction=correction,
                        metadata=metadata,
                    )
                    self._record(record)
                    return correction, metadata
                last_error = f"Invalid GEC output format: {error}"
                format_retries += 1
            record["error"] = last_error
            self._record(record)
            LOGGER.warning("Copilot request %s attempt %s failed: %s", request_key, attempt + 1, last_error)
            if attempt < retries:
                time.sleep(sleep_seconds * (2**attempt))
        raise RuntimeError(last_error)

    def close(self) -> None:
        if self._process is None:
            return
        self._closing = True
        if self._process.poll() is None:
            assert self._process.stdin is not None
            self._process.stdin.write('{"action":"shutdown"}\n')
            self._process.stdin.flush()
            self._process.stdin.close()
            try:
                self._process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self._process.terminate()
                self._process.wait(timeout=10)
                raise RuntimeError("Copilot bridge did not shut down in time")
        self._reader.join(timeout=5)
        self._stderr.close()
        if self._process.stdout is not None:
            self._process.stdout.close()
        if self._process.returncode:
            raise RuntimeError(
                f"Copilot bridge failed with exit {self._process.returncode}; "
                f"see {self.state_dir / 'bridge.stderr.log'}"
            )
