#!/usr/bin/env python3
"""Run the frozen T0--T3 pipeline over every prepared scoreboard dataset."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/benchmarks/prepared/manifest.json"
RUNS = ROOT / "runs"
DEFAULT_PYTHON = Path(sys.executable)
ROUNDS = ("T0", "T1", "T2", "T3")


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def read_api_key(*, prompt: bool) -> str:
    key = os.environ.get("LLM_API_KEY", "").strip()
    if not key and prompt:
        key = getpass.getpass("LLM API key: ").strip()
    if not key:
        raise RuntimeError("Set LLM_API_KEY or use --api-key-stdin")
    return key


def check_balance(base_url: str, api_key: str) -> dict[str, Any] | None:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/users/me/balance",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, ValueError) as exc:
        print(f"Balance check unavailable: {exc}", flush=True)
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def validate_result(path: Path, expected_rows: int) -> None:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if len(rows) != expected_rows:
        raise ValueError(f"{path}: {len(rows)} rows, expected {expected_rows}")
    required = {"id", "source", "target", "S1", *ROUNDS}
    missing = required - set(rows[0] if rows else [])
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    failed = [row.get("id", "") for row in rows if any(not row.get(stage) for stage in ROUNDS)]
    if failed:
        raise ValueError(f"{path}: {len(failed)} rows have empty stage outputs")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="https://api.moonshot.ai/v1")
    parser.add_argument("--run-tag")
    parser.add_argument("--thinking", choices=("disabled", "omit"), default="omit")
    parser.add_argument(
        "--temperature",
        default="omit",
        help="Numeric temperature or 'omit' for models with a provider-fixed value",
    )
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--max-t", type=int, default=3)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-rpm", type=float, default=0)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--retry-sleep", type=float, default=3.0)
    parser.add_argument("--dataset-repair-passes", type=int, default=10)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--datasets", nargs="+")
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--api-key-stdin", action="store_true")
    args = parser.parse_args()

    if args.max_t != 3:
        parser.error("This scoreboard runner is intentionally frozen at T3")
    if not args.python.exists():
        parser.error(f"Python interpreter does not exist: {args.python}")

    api_key = read_api_key(prompt=args.api_key_stdin)
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.datasets:
        selected = set(args.datasets)
        known = {record["dataset"] for record in records}
        unknown = selected - known
        if unknown:
            parser.error(f"Unknown datasets: {sorted(unknown)}")
        records = [record for record in records if record["dataset"] in selected]

    run_tag = args.run_tag or slug(args.model)
    metadata_root = RUNS / run_tag
    metadata_root.mkdir(parents=True, exist_ok=True)
    run_names: dict[str, str] = {}
    env = dict(os.environ)
    env.update(
        {
            "LLM_API_KEY": api_key,
            "LLM_BASE_URL": args.base_url,
            "LLM_MODEL": args.model,
            "LLM_TEMPERATURE": args.temperature,
            "LLM_MAX_TOKENS": str(args.max_tokens),
            "LLM_THINKING": args.thinking,
            "LLM_MAX_RPM": str(args.max_rpm),
        }
    )

    balance_before = check_balance(args.base_url, api_key)
    if balance_before:
        print(
            f"Available balance before run: ${float(balance_before['available_balance']):.4f}",
            flush=True,
        )

    for position, record in enumerate(records, start=1):
        dataset = record["dataset"]
        split = record["split"]
        expected_rows = min(int(record["rows"]), args.limit) if args.limit else int(record["rows"])
        run_name = f"{dataset}_{split}_all_T3_{run_tag}_paper_converged"
        if args.limit:
            run_name = f"{dataset}_{split}_{args.limit}_T3_{run_tag}_paper_converged"
        run_names[dataset] = run_name
        result_jsonl = RUNS / f"{run_name}.jsonl"
        result_tsv = RUNS / f"{run_name}.tsv"
        base_command = [
            str(args.python),
            str(ROOT / "scripts/run_iterative_gec.py"),
            "--input",
            str(ROOT / record["pipeline_input"]),
            "--limit",
            str(args.limit),
            "--max-t",
            "3",
            "--out-dir",
            str(RUNS),
            "--run-name",
            run_name,
            "--prompt-variant",
            "paper",
            "--workers",
            str(args.workers),
            "--checkpoint-every",
            str(args.checkpoint_every),
            "--progress-every",
            str(args.progress_every),
            "--timeout",
            str(args.timeout),
            "--retries",
            str(args.retries),
            "--sleep",
            str(args.retry_sleep),
        ]
        print(
            f"\n[{position}/{len(records)}] {dataset}/{split}: {expected_rows} rows",
            flush=True,
        )
        last_validation_error: Exception | None = None
        for repair_pass in range(1, args.dataset_repair_passes + 1):
            command = list(base_command)
            if result_jsonl.exists():
                command.extend(["--resume-matching-jsonl", str(result_jsonl)])
            proc = subprocess.run(command, cwd=ROOT, env=env, check=False)
            try:
                validate_result(result_tsv, expected_rows)
            except (FileNotFoundError, ValueError) as exc:
                last_validation_error = exc
                if repair_pass >= args.dataset_repair_passes:
                    break
                print(
                    f"{dataset}: repair pass {repair_pass} incomplete "
                    f"(exit={proc.returncode}): {exc}",
                    flush=True,
                )
                time.sleep(max(args.retry_sleep, 1.0))
                continue
            last_validation_error = None
            break
        if last_validation_error is not None:
            raise RuntimeError(
                f"{dataset} did not complete after {args.dataset_repair_passes} passes"
            ) from last_validation_error
        (metadata_root / "run_names.json").write_text(
            json.dumps(run_names, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    balance_after = check_balance(args.base_url, api_key)
    config = {
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "base_url": args.base_url,
        "thinking": args.thinking,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "provider_temperature_note": (
            "kimi-k2.6 non-thinking uses the provider-fixed temperature 0.6"
            if args.model == "kimi-k2.6" and args.temperature == "omit"
            else None
        ),
        "prompt_variant": "paper",
        "max_t": 3,
        "convergence": "carry T_(i-1) forward when S_i equals S_(i-1)",
        "projection_threshold": 0.85,
        "workers": args.workers,
        "max_rpm": args.max_rpm,
        "limit": args.limit,
        "datasets": [record["dataset"] for record in records],
        "run_names_file": str(metadata_root / "run_names.json"),
        "available_balance_before": balance_before,
        "available_balance_after": balance_after,
        "api_key_saved": False,
    }
    (metadata_root / "generation_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nRun map: {metadata_root / 'run_names.json'}", flush=True)
    if balance_after:
        print(
            f"Available balance after run: ${float(balance_after['available_balance']):.4f}",
            flush=True,
        )


if __name__ == "__main__":
    main()
