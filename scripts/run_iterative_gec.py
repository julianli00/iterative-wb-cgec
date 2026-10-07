#!/usr/bin/env python3
"""Run an iterative WB-aware CGEC pipeline.

This recovers the old notebook pipeline as a repeatable script:

S0 -> T0
S1 = LTP(S0) -> T1
S2 = project WB from LTP(T1) onto S1 -> T2
S3 = project WB from LTP(T2) onto S2 -> T3

When the normalized projected boundary vector no longer changes, the
iteration has reached a fixed point. T_i and all later requested rounds are
then carried forward from T_{i-1} without another LLM call.
"""

from __future__ import annotations

import argparse
import copy
import csv
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Callable

import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "flaCGEC_test.json.tsv"
DEFAULT_OUT_DIR = ROOT / "runs"
DEFAULT_WB_REPO = ROOT.parent / "chinese-wb-fixing"
DEFAULT_SHAPE_TABLE = Path(
    ROOT.parent
    / "fixing_wb/transformer/data/0423/triplet_no_dup_threshold.csv"
)

PROMPT_RAW_PAPER = (
    "请改正下列句子的语法错误，并尽量只做最小限度的修改。"
    "仅输出修改后的句子（正常语句格式，不含分词），不要输出其他内容。"
    "句子如下：{sentence}"
)

PROMPT_SEGMENTED_PAPER = (
    "以下句子是已分词的结构化输入。请在保持原有词语边界的基础上"
    "改正语法错误，并尽量只做最小限度的修改。输出时请将修改后的句子"
    "以正常语句格式（不含分词）呈现，不要输出其他内容。"
    "句子如下：{sentence}"
)

PROMPT_RAW_STRICT = (
    "你是一个中文语法纠错系统。请只改正下列句子的语法错误，"
    "尽量最小化修改；不要润色，不要替换同义词，不要额外增删信息，"
    "除非这是改正语法错误所必需的。只输出改正后的完整句子，"
    "不要解释。句子如下：{sentence}"
)

PROMPT_SEGMENTED_STRICT = (
    "你是一个中文语法纠错系统。下面的句子用空格标出了词边界，"
    "空格只作为结构信息。请基于这些词边界只改正语法错误，"
    "尽量最小化修改；不要润色，不要替换同义词，不要额外增删信息。"
    "输出正常中文句子，不保留分词空格；只输出句子，不要解释。"
    "句子如下：{sentence}"
)


PROMPT_VARIANTS = {
    "paper": (PROMPT_RAW_PAPER, PROMPT_SEGMENTED_PAPER),
    "strict": (PROMPT_RAW_STRICT, PROMPT_SEGMENTED_STRICT),
}

_HTTP_LOCAL = threading.local()


class RequestRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._interval = 0.0
        self._next_allowed = 0.0

    def configure(self, max_rpm: float) -> None:
        with self._lock:
            self._interval = 60.0 / max_rpm if max_rpm > 0 else 0.0
            self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait_seconds = max(0.0, self._next_allowed - now)
            self._next_allowed = max(now, self._next_allowed) + self._interval
        if wait_seconds:
            time.sleep(wait_seconds)


_API_RATE_LIMITER = RequestRateLimiter()


def segmentation_signature(segmented: str) -> tuple[str, tuple[int, ...]]:
    """Return source text and inter-character word-boundary positions."""

    tokens = segmented.split()
    positions: list[int] = []
    cursor = 0
    for token in tokens[:-1]:
        cursor += len(token)
        positions.append(cursor)
    return "".join(tokens), tuple(positions)


def http_session() -> requests.Session:
    session = getattr(_HTTP_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        _HTTP_LOCAL.session = session
    return session


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def load_wb_module(wb_repo: Path):
    module_path = wb_repo / "src/pipeline/alignment/step2_similarity_alignment_projection.py"
    if not module_path.exists():
        raise FileNotFoundError(f"WB projection module not found: {module_path}")
    spec = importlib.util.spec_from_file_location("wb_step2_projection", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import WB projection module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["wb_step2_projection"] = module
    spec.loader.exec_module(module)
    return module


def read_tsv(path: Path, limit: int, start: int = 0) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        for idx, parts in enumerate(reader):
            if idx < start:
                continue
            if limit and len(rows) >= limit:
                break
            if len(parts) < 2:
                raise ValueError(f"Line {idx + 1} has fewer than 2 TSV columns")
            rows.append({"id": str(idx), "source": parts[0], "target": parts[1]})
    return rows


def read_jsonl(path: Path, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            if limit and len(rows) >= limit:
                break
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"Line {line_number} in {path} is not a JSON object")
            rows.append(row)
    return rows


def infer_completed_t(row: dict[str, Any]) -> int:
    completed = [
        int(match.group(1))
        for key in row
        if (match := re.fullmatch(r"T(\d+)", key)) and row.get(key) is not None
    ]
    if not completed:
        raise ValueError("Resume row has no completed T stage")
    return max(completed)


def result_matches_input(
    result: dict[str, Any], input_row: dict[str, str], max_t: int
) -> bool:
    return bool(
        result.get("ok")
        and result.get("id") == input_row["id"]
        and result.get("source") == input_row["source"]
        and result.get("target") == input_row["target"]
        and result.get(f"T{max_t}") is not None
    )


def auth_header(api_key: str) -> str:
    if api_key.lower().startswith("bearer "):
        return api_key
    return f"Bearer {api_key}"


def chat_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def strip_llm_response(text: str) -> str:
    text = text.replace("\r", "\n").strip()
    text = re.sub(r"^```(?:text|txt|中文)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)

    split_patterns = [
        r"修改后的句子[：:]\s*",
        r"修改后[：:]\s*",
        r"改正后[：:]\s*",
        r"最终输出(?:（[^）]*）)?[：:]\s*",
        r"修改为[：:]\s*",
        r"修正后[：:]\s*",
    ]
    for pattern in split_patterns:
        parts = re.split(pattern, text, flags=re.I)
        if len(parts) > 1:
            text = parts[-1]
            break

    text = re.split(r"\n+\s*(?:修改说明|说明|理由|解释)[：:]", text, maxsplit=1)[0]
    text = re.sub(r"\s+", "", text)
    return text.strip(" \t\n\r\"'“”")


def gec_output_format_error(prompt: str, raw_text: str, cleaned_text: str) -> str | None:
    """Reject clear instruction-following failures before WB projection."""

    if not cleaned_text:
        return "empty correction"
    source_hint = prompt.rsplit("句子如下：", 1)[-1]
    source_length = len(re.sub(r"\s+", "", source_hint))
    maximum_length = max(128, source_length * 4)
    if len(cleaned_text) > maximum_length:
        return (
            f"correction has {len(cleaned_text)} characters; expected at most "
            f"{maximum_length} for a {source_length}-character source"
        )
    analysis_markers = (
        "等等，让我重新考虑",
        "重新分析：",
        "最终判断：",
        "我决定：",
    )
    if any(marker in raw_text for marker in analysis_markers):
        return "response contains model self-analysis instead of only a correction"
    return None


def sentence_from_prompt(prompt: str) -> str:
    """Recover the stage input as an unsegmented identity fallback."""

    return re.sub(r"\s+", "", prompt.rsplit("句子如下：", 1)[-1])


def call_llm(
    *,
    prompt: str,
    api_key: str,
    base_url: str,
    model: str,
    temperature: float | None,
    max_tokens: int | None,
    thinking_disabled: bool,
    timeout: int,
    retries: int,
    sleep_seconds: float,
    request_key: str = "",
) -> tuple[str, dict[str, Any]]:
    headers = {
        "Authorization": auth_header(api_key),
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if thinking_disabled:
        payload["thinking"] = {"type": "disabled"}

    last_error: str | None = None
    used_fallback_without_thinking = False
    format_retries = 0
    for attempt in range(retries + 1):
        current_payload = dict(payload)
        if used_fallback_without_thinking:
            current_payload.pop("thinking", None)
        try:
            _API_RATE_LIMITER.wait()
            response = http_session().post(
                chat_url(base_url),
                headers=headers,
                json=current_payload,
                timeout=timeout,
            )
            if response.status_code >= 400:
                body = response.text[:1000]
                if response.status_code == 400 and (
                    "content_filter" in body or "high risk" in body.lower()
                ):
                    return sentence_from_prompt(prompt), {
                        "model": model,
                        "usage": None,
                        "fallback_without_thinking": used_fallback_without_thinking,
                        "format_retries": format_retries,
                        "content_filter_fallback": True,
                    }
                if (
                    "thinking" in current_payload
                    and response.status_code == 400
                    and "thinking" in body.lower()
                ):
                    used_fallback_without_thinking = True
                    last_error = f"HTTP {response.status_code}: {body}"
                    continue
                raise RuntimeError(f"HTTP {response.status_code}: {body}")
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            cleaned_content = strip_llm_response(content)
            format_error = gec_output_format_error(prompt, content, cleaned_content)
            if format_error:
                format_retries += 1
                last_error = f"Invalid GEC output format: {format_error}"
                if attempt >= retries:
                    break
                time.sleep(sleep_seconds * (2**attempt))
                continue
            meta = {
                "model": data.get("model"),
                "usage": data.get("usage"),
                "fallback_without_thinking": used_fallback_without_thinking,
                "format_retries": format_retries,
                "content_filter_fallback": False,
            }
            return cleaned_content, meta
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt >= retries:
                break
            time.sleep(sleep_seconds * (2**attempt))
    raise RuntimeError(last_error or "Unknown LLM call failure")


def ltp_segment(wb_module: Any, text: str) -> str:
    return wb_module.ltp_segment(text)


def project_with_existing_boundaries(
    *,
    wb_module: Any,
    source_segmented: str,
    target_segmented: str,
    shape_table: Any,
    threshold: float,
) -> dict[str, Any]:
    """Project target WB onto the current source segmentation.

    The standalone P2 function recomputes LTP(source) as its base. For this
    iterative experiment, the current S_i boundaries are the base boundaries.
    We therefore reuse the same P2 alignment/projection helpers but seed them
    with get_word_final_positions(source_segmented).
    """
    source_chars = source_segmented.replace(" ", "")
    target_chars = target_segmented.replace(" ", "")
    if not source_chars:
        return {"projected": source_segmented, "stats": {}}

    base_word_final = wb_module.get_word_final_positions(source_segmented)
    step1_aligned, unaligned_src, unaligned_tgt = wb_module.exact_alignment_ins_del_only(
        source_chars, target_chars
    )
    emb_sim_matrix = wb_module.compute_embedding_similarity(source_chars, target_chars)
    step2_aligned = wb_module.align_similar_chars_4feat_t2s(
        source_chars,
        target_chars,
        unaligned_src,
        unaligned_tgt,
        emb_sim_matrix,
        shape_table,
        threshold,
    )
    all_aligned = {**step1_aligned, **step2_aligned}
    final_word_final, projected_boundaries, skipped_boundaries = (
        wb_module.project_boundaries_conservatively(
            target_text=target_segmented,
            aligned=all_aligned,
            base_boundaries=base_word_final,
        )
    )
    final_word_final, merged_spans, merge_skips = wb_module.apply_exact_match_merge_constraint(
        target_text=target_segmented,
        aligned=all_aligned,
        word_final_positions=final_word_final,
    )
    final_word_final.add(len(source_chars) - 1)
    matched_src_step2 = set(step2_aligned.values())
    projected = wb_module.positions_to_segmented(source_chars, final_word_final)
    return {
        "projected": projected,
        "stats": {
            "step1_aligned": len(step1_aligned),
            "step2_aligned": len(step2_aligned),
            "still_unaligned_src": len([x for x in unaligned_src if x not in matched_src_step2]),
            "still_unaligned_tgt": len([x for x in unaligned_tgt if x not in step2_aligned]),
            "projected_boundaries": len(projected_boundaries),
            "skipped_boundaries": len(skipped_boundaries),
            "merged_spans": len(merged_spans),
            "merge_skips": len(merge_skips),
        },
    }


def write_outputs(
    rows: list[dict[str, Any]],
    jsonl_path: Path,
    tsv_path: Path,
    max_t: int,
) -> None:
    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    fieldnames: list[str] = ["id", "source", "target", "S1", "T0", "T1"]
    for idx in range(2, max_t + 1):
        fieldnames.extend([f"S{idx}", f"T{idx}"])
    with tsv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, delimiter="\t", fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def resume_run(
    args: argparse.Namespace,
    *,
    resume_jsonl: Path,
    wb_module: Any,
    shape_table: Any,
    segmented_prompt_template: str,
    api_key: str,
    base_url: str,
    model: str,
    temperature: float | None,
    max_tokens: int | None,
    thinking_disabled: bool,
    jsonl_path: Path,
    tsv_path: Path,
    call_model: Callable[..., tuple[str, dict[str, Any]]] | None = None,
) -> None:
    call_model = call_model or call_llm
    previous_rows = read_jsonl(resume_jsonl, args.limit)
    if not previous_rows:
        raise RuntimeError(f"No rows found in resume file: {resume_jsonl}")

    completed_stages = {infer_completed_t(row) for row in previous_rows}
    if len(completed_stages) != 1:
        raise ValueError(f"Resume rows end at different T stages: {sorted(completed_stages)}")
    resume_t = completed_stages.pop()
    if args.max_t <= resume_t:
        raise ValueError(
            f"--max-t must be greater than the completed resume stage T{resume_t}"
        )

    print(f"Resume JSONL: {resume_jsonl}")
    print(f"Resume stage: T{resume_t}")
    print(f"Resume rows: {len(previous_rows)}")

    completed: list[dict[str, Any]] = []
    total_api_calls_added = 0
    for idx, previous_result in enumerate(previous_rows, start=1):
        started = time.time()
        result = copy.deepcopy(previous_result)
        prior_seconds = float(result.get("seconds", 0.0) or 0.0)
        api_calls_before = len(result.get("meta", {}).get("api", []))

        try:
            if not result.get("ok", False):
                raise ValueError(f"Cannot resume failed row id={result.get('id')}")

            result.setdefault("meta", {})
            result["meta"].setdefault("api", [])
            result["meta"].setdefault("projection", [])
            result["meta"].setdefault("resumes", []).append(
                {"from_T": resume_t, "through_T": args.max_t}
            )

            convergence = result["meta"].get("convergence") or {}
            if convergence.get("converged"):
                for later_idx in range(resume_t + 1, args.max_t + 1):
                    result[f"S{later_idx}"] = result[f"S{resume_t}"]
                    result[f"T{later_idx}"] = result[f"T{resume_t}"]
                carried_rounds = set(convergence.get("carried_rounds", []))
                carried_rounds.update(range(resume_t + 1, args.max_t + 1))
                convergence["carried_rounds"] = sorted(carried_rounds)
                result["meta"]["convergence"] = convergence
            else:
                s_values = {resume_t: result[f"S{resume_t}"]}
                t_values = {resume_t: result[f"T{resume_t}"]}
                result["meta"]["convergence"] = None

                for t_idx in range(resume_t + 1, args.max_t + 1):
                    previous_s = s_values[t_idx - 1]
                    previous_t_ltp = ltp_segment(wb_module, t_values[t_idx - 1])
                    projection = project_with_existing_boundaries(
                        wb_module=wb_module,
                        source_segmented=previous_s,
                        target_segmented=previous_t_ltp,
                        shape_table=shape_table,
                        threshold=args.projection_threshold,
                    )
                    s_values[t_idx] = projection["projected"]
                    result[f"S{t_idx}"] = s_values[t_idx]
                    result["meta"]["projection"].append(
                        {"S": t_idx, **projection["stats"]}
                    )

                    if segmentation_signature(s_values[t_idx]) == segmentation_signature(
                        previous_s
                    ):
                        t_values[t_idx] = t_values[t_idx - 1]
                        result[f"T{t_idx}"] = t_values[t_idx]

                        carried_rounds = [t_idx]
                        for later_idx in range(t_idx + 1, args.max_t + 1):
                            s_values[later_idx] = s_values[t_idx]
                            t_values[later_idx] = t_values[t_idx]
                            result[f"S{later_idx}"] = s_values[later_idx]
                            result[f"T{later_idx}"] = t_values[later_idx]
                            carried_rounds.append(later_idx)

                        result["meta"]["convergence"] = {
                            "converged": True,
                            "at_S": t_idx,
                            "unchanged_from_S": t_idx - 1,
                            "carried_from_T": t_idx - 1,
                            "carried_rounds": carried_rounds,
                        }
                        break

                    prompt = segmented_prompt_template.format(sentence=s_values[t_idx])
                    t_values[t_idx], meta = call_model(
                        prompt=prompt,
                        api_key=api_key,
                        base_url=base_url,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        thinking_disabled=thinking_disabled,
                        timeout=args.timeout,
                        retries=args.retries,
                        sleep_seconds=args.sleep,
                        request_key=f"{args.run_name}:{result['id']}:T{t_idx}",
                    )
                    result["meta"]["api"].append({"T": t_idx, **meta})
                    result[f"T{t_idx}"] = t_values[t_idx]

                if result["meta"]["convergence"] is None:
                    result["meta"]["convergence"] = {
                        "converged": False,
                        "checked_through_S": args.max_t,
                    }

            result.pop("error", None)
            result["ok"] = True
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["error"] = str(exc)

        extension_seconds = round(time.time() - started, 3)
        result["extension_seconds"] = extension_seconds
        result["seconds"] = round(prior_seconds + extension_seconds, 3)
        api_calls_added = len(result.get("meta", {}).get("api", [])) - api_calls_before
        total_api_calls_added += max(api_calls_added, 0)
        completed.append(result)
        write_outputs(completed, jsonl_path, tsv_path, args.max_t)
        status = "ok" if result.get("ok") else "error"
        print(
            f"[{idx}/{len(previous_rows)}] {status} id={result.get('id')} "
            f"api_calls_added={api_calls_added} seconds={extension_seconds}"
        )
        if not result.get("ok") and args.stop_on_error:
            break
        if args.row_sleep:
            time.sleep(args.row_sleep)

    ok_count = sum(1 for row in completed if row.get("ok"))
    print(
        f"Done. ok={ok_count}/{len(completed)} "
        f"new_api_calls={total_api_calls_added}"
    )


def run(args: argparse.Namespace) -> None:
    if getattr(args, "backend", "http") == "copilot":
        try:
            from copilot_llm import CopilotClient
        except ModuleNotFoundError:
            from scripts.copilot_llm import CopilotClient
        with CopilotClient(
            model=args.model,
            state_dir=args.out_dir / "copilot_state" / args.run_name,
            journal=args.out_dir / f"{args.run_name}.requests.jsonl",
            clean=strip_llm_response,
            validate=gec_output_format_error,
            source_from_prompt=sentence_from_prompt,
            rate_limit=_API_RATE_LIMITER.wait,
        ) as client:
            _run(args, copilot_client=client)
    else:
        _run(args)


def _run(args: argparse.Namespace, *, copilot_client: Any = None) -> None:
    if args.max_t < 1:
        raise ValueError("--max-t must be at least 1")

    if copilot_client is not None:
        env = dict(os.environ)
        api_key = ""
        base_url = "copilot-sdk"
        model = copilot_client.model
        temperature = None
        max_tokens = None
        thinking_disabled = False
        call_model = copilot_client.call_llm
    else:
        env = {**load_env(ROOT / ".env"), **os.environ}
        api_key = env.get("LLM_API_KEY") or env.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise RuntimeError("LLM_API_KEY or DEEPSEEK_API_KEY is missing")
        base_url = env.get(
            "LLM_BASE_URL",
            env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        )
        model = env.get("LLM_MODEL", env.get("DEEPSEEK_MODEL", "deepseek-v4-pro"))
        temperature_value = env.get(
            "LLM_TEMPERATURE",
            env.get("DEEPSEEK_TEMPERATURE", "0.000001"),
        ).strip()
        temperature = (
            None
            if temperature_value.lower() in {"", "none", "omit"}
            else float(temperature_value)
        )
        max_tokens_value = env.get("LLM_MAX_TOKENS", "").strip()
        max_tokens = int(max_tokens_value) if max_tokens_value else None
        thinking_value = env.get(
            "LLM_THINKING",
            env.get("DEEPSEEK_THINKING", ""),
        )
        thinking_disabled = thinking_value.lower() == "disabled"
        call_model = call_llm
    max_rpm = float(env.get("LLM_MAX_RPM", "0"))
    _API_RATE_LIMITER.configure(max_rpm)

    wb_repo = Path(env.get("WB_FIXING_REPO", str(DEFAULT_WB_REPO)))
    shape_path = Path(env.get("WB_SHAPE_TABLE", str(DEFAULT_SHAPE_TABLE)))

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / f"{args.run_name}.jsonl"
    tsv_path = out_dir / f"{args.run_name}.tsv"

    resume_jsonl = getattr(args, "resume_jsonl", None)
    partial_resume_jsonl = getattr(args, "resume_partial_jsonl", None)
    matching_resume_jsonl = getattr(args, "resume_matching_jsonl", None)
    resume_options = [resume_jsonl, partial_resume_jsonl, matching_resume_jsonl]
    if sum(option is not None for option in resume_options) > 1:
        raise ValueError(
            "--resume-jsonl, --resume-partial-jsonl, and --resume-matching-jsonl "
            "cannot be combined"
        )
    print(f"Input: {resume_jsonl or args.input}")
    print(f"Row limit: {args.limit or 'all'}")
    print(f"Max T: T{args.max_t}")
    print(f"Prompt variant: {args.prompt_variant}")
    print(f"Model: {model}")
    print(f"Base URL: {base_url}")
    print(f"Temperature: {temperature if temperature is not None else 'omitted'}")
    print(f"Max tokens: {max_tokens if max_tokens is not None else 'omitted'}")
    print(f"Thinking disabled: {thinking_disabled}")
    print(f"Request limit: {max_rpm:g} RPM" if max_rpm else "Request limit: provider-managed")
    print(f"Output JSONL: {jsonl_path}")
    print(f"Output TSV: {tsv_path}")

    wb_module = load_wb_module(wb_repo)
    wb_module.load_bert_model(args.bert_model)
    shape_table = wb_module.load_shape_table(str(shape_path))
    raw_prompt_template, segmented_prompt_template = PROMPT_VARIANTS[args.prompt_variant]

    if resume_jsonl:
        resume_run(
            args,
            resume_jsonl=resume_jsonl,
            wb_module=wb_module,
            shape_table=shape_table,
            segmented_prompt_template=segmented_prompt_template,
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking_disabled=thinking_disabled,
            jsonl_path=jsonl_path,
            tsv_path=tsv_path,
            call_model=call_model,
        )
        return

    completed: list[dict[str, Any]] = []
    start_index = 0
    matching_input_rows: list[dict[str, str]] | None = None
    matching_completed: dict[str, dict[str, Any]] = {}
    if matching_resume_jsonl:
        matching_input_rows = read_tsv(args.input, args.limit)
        previous_rows = read_jsonl(matching_resume_jsonl, 0)
        previous_by_id = {str(row.get("id")): row for row in previous_rows}
        data_rows: list[dict[str, str]] = []
        for input_row in matching_input_rows:
            previous = previous_by_id.get(input_row["id"])
            if previous and result_matches_input(previous, input_row, args.max_t):
                matching_completed[input_row["id"]] = previous
            else:
                data_rows.append(input_row)
        total_rows = len(matching_input_rows)
        print(
            f"Matching resume: retained {len(matching_completed)} rows and will "
            f"process {len(data_rows)} rows from {matching_resume_jsonl}"
        )
    elif partial_resume_jsonl:
        previous_rows = read_jsonl(partial_resume_jsonl, 0)
        for previous_row in previous_rows:
            if not previous_row.get("ok") or f"T{args.max_t}" not in previous_row:
                break
            completed.append(previous_row)
        start_index = len(completed)
        print(
            f"Partial resume: retained {start_index} successful rows from "
            f"{partial_resume_jsonl}"
        )

    if matching_input_rows is None:
        remaining_limit = max(args.limit - start_index, 0) if args.limit else 0
        data_rows = read_tsv(args.input, remaining_limit, start=start_index)
        total_rows = start_index + len(data_rows)
    print(f"Rows loaded: {len(data_rows)} remaining ({total_rows} total)")
    wb_lock = threading.Lock()

    def process_row(row: dict[str, str]) -> dict[str, Any]:
        started = time.time()
        result: dict[str, Any] = {
            "id": row["id"],
            "source": row["source"],
            "target": row["target"],
            "meta": {"api": [], "projection": [], "convergence": None},
        }
        try:
            source = row["source"]
            s_values: dict[int, str] = {}
            t_values: dict[int, str] = {}

            prompt = raw_prompt_template.format(sentence=source)
            t_values[0], meta = call_model(
                prompt=prompt,
                api_key=api_key,
                base_url=base_url,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                thinking_disabled=thinking_disabled,
                timeout=args.timeout,
                retries=args.retries,
                sleep_seconds=args.sleep,
                request_key=f"{args.run_name}:{row['id']}:T0",
            )
            result["meta"]["api"].append({"T": 0, **meta})
            result["T0"] = t_values[0]

            with wb_lock:
                s_values[1] = ltp_segment(wb_module, source)
            result["S1"] = s_values[1]

            prompt = segmented_prompt_template.format(sentence=s_values[1])
            t_values[1], meta = call_model(
                prompt=prompt,
                api_key=api_key,
                base_url=base_url,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                thinking_disabled=thinking_disabled,
                timeout=args.timeout,
                retries=args.retries,
                sleep_seconds=args.sleep,
                request_key=f"{args.run_name}:{row['id']}:T1",
            )
            result["meta"]["api"].append({"T": 1, **meta})
            result["T1"] = t_values[1]

            for t_idx in range(2, args.max_t + 1):
                previous_s = s_values[t_idx - 1]
                with wb_lock:
                    previous_t_ltp = ltp_segment(wb_module, t_values[t_idx - 1])
                    projection = project_with_existing_boundaries(
                        wb_module=wb_module,
                        source_segmented=previous_s,
                        target_segmented=previous_t_ltp,
                        shape_table=shape_table,
                        threshold=args.projection_threshold,
                    )
                s_values[t_idx] = projection["projected"]
                result[f"S{t_idx}"] = s_values[t_idx]
                result["meta"]["projection"].append({"S": t_idx, **projection["stats"]})

                if segmentation_signature(s_values[t_idx]) == segmentation_signature(
                    previous_s
                ):
                    t_values[t_idx] = t_values[t_idx - 1]
                    result[f"T{t_idx}"] = t_values[t_idx]

                    carried_rounds = [t_idx]
                    for later_idx in range(t_idx + 1, args.max_t + 1):
                        s_values[later_idx] = s_values[t_idx]
                        t_values[later_idx] = t_values[t_idx]
                        result[f"S{later_idx}"] = s_values[later_idx]
                        result[f"T{later_idx}"] = t_values[later_idx]
                        carried_rounds.append(later_idx)

                    result["meta"]["convergence"] = {
                        "converged": True,
                        "at_S": t_idx,
                        "unchanged_from_S": t_idx - 1,
                        "carried_from_T": t_idx - 1,
                        "carried_rounds": carried_rounds,
                    }
                    break

                prompt = segmented_prompt_template.format(sentence=s_values[t_idx])
                t_values[t_idx], meta = call_model(
                    prompt=prompt,
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    thinking_disabled=thinking_disabled,
                    timeout=args.timeout,
                    retries=args.retries,
                    sleep_seconds=args.sleep,
                    request_key=f"{args.run_name}:{row['id']}:T{t_idx}",
                )
                result["meta"]["api"].append({"T": t_idx, **meta})
                result[f"T{t_idx}"] = t_values[t_idx]

            if result["meta"]["convergence"] is None:
                result["meta"]["convergence"] = {
                    "converged": False,
                    "checked_through_S": args.max_t,
                }

            result["ok"] = True
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["error"] = str(exc)

        result["seconds"] = round(time.time() - started, 3)
        return result

    workers = max(1, int(getattr(args, "workers", 1)))
    checkpoint_every = max(1, int(getattr(args, "checkpoint_every", 1)))
    progress_every = max(1, int(getattr(args, "progress_every", 1)))
    print(f"Workers: {workers}")
    if workers == 1:
        result_stream = map(process_row, data_rows)
        executor = None
    else:
        executor = ThreadPoolExecutor(max_workers=workers)
        result_stream = executor.map(process_row, data_rows)

    try:
        if matching_input_rows is not None:
            for processed, (row, result) in enumerate(
                zip(data_rows, result_stream), start=1
            ):
                matching_completed[row["id"]] = result
                if (
                    processed % checkpoint_every == 0
                    or processed == len(data_rows)
                    or not result.get("ok")
                ):
                    available = [
                        matching_completed[input_row["id"]]
                        for input_row in matching_input_rows
                        if input_row["id"] in matching_completed
                    ]
                    write_outputs(available, jsonl_path, tsv_path, args.max_t)
                status = "ok" if result.get("ok") else "error"
                if (
                    processed % progress_every == 0
                    or processed == len(data_rows)
                    or not result.get("ok")
                ):
                    print(
                        f"[{processed}/{len(data_rows)} repaired; "
                        f"{len(matching_completed)}/{total_rows} total] {status} "
                        f"id={row['id']} seconds={result['seconds']}"
                    )
                if not result.get("ok") and args.stop_on_error:
                    break
                if args.row_sleep:
                    time.sleep(args.row_sleep)
            completed = [
                matching_completed[input_row["id"]]
                for input_row in matching_input_rows
                if input_row["id"] in matching_completed
            ]
            write_outputs(completed, jsonl_path, tsv_path, args.max_t)
        else:
            for idx, (row, result) in enumerate(
                zip(data_rows, result_stream), start=start_index + 1
            ):
                completed.append(result)
                if idx % checkpoint_every == 0 or idx == total_rows or not result.get("ok"):
                    write_outputs(completed, jsonl_path, tsv_path, args.max_t)
                status = "ok" if result.get("ok") else "error"
                if idx % progress_every == 0 or idx == total_rows or not result.get("ok"):
                    print(
                        f"[{idx}/{total_rows}] {status} id={row['id']} "
                        f"seconds={result['seconds']}"
                    )
                if not result.get("ok") and args.stop_on_error:
                    break
                if args.row_sleep:
                    time.sleep(args.row_sleep)
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)

    ok_count = sum(1 for row in completed if row.get("ok"))
    print(f"Done. ok={ok_count}/{len(completed)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("http", "copilot"), default="http")
    parser.add_argument("--model", default="gpt-6-astra", help="Model for the Copilot backend")
    parser.add_argument("--input", type=Path, default=DEFAULT_DATA)
    parser.add_argument(
        "--resume-jsonl",
        type=Path,
        help="Continue from an existing JSONL result without repeating earlier API calls",
    )
    parser.add_argument(
        "--resume-partial-jsonl",
        type=Path,
        help="Keep the contiguous successful prefix and retry the remaining input rows",
    )
    parser.add_argument(
        "--resume-matching-jsonl",
        type=Path,
        help=(
            "Reuse successful rows whose id, source, target, and requested T stage "
            "match the current input; process only changed or missing rows"
        ),
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-t", type=int, default=3)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--run-name", default="flaCGEC_20_T3_deepseek_v4_pro")
    parser.add_argument("--prompt-variant", choices=sorted(PROMPT_VARIANTS), default="paper")
    parser.add_argument("--projection-threshold", type=float, default=0.85)
    parser.add_argument("--bert-model", default="bert-base-chinese")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument("--row-sleep", type=float, default=0.0)
    parser.add_argument("--workers", type=int, default=1, help="Concurrent rows; WB model access remains serialized")
    parser.add_argument("--checkpoint-every", type=int, default=1, help="Rewrite output files every N rows")
    parser.add_argument("--progress-every", type=int, default=1, help="Print progress every N rows")
    parser.add_argument("--stop-on-error", action="store_true", default=True)
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
