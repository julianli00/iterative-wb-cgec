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
    required = {"id", "source", "target", "S1", "S2", "S3", *ROUNDS}
    missing = required - set(rows[0] if rows else [])
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    failed = [row.get("id", "") for row in rows if any(not row.get(stage) for stage in ROUNDS)]
    if failed:
        raise ValueError(f"{path}: {len(failed)} rows have empty stage outputs")
    if len({row["id"] for row in rows}) != expected_rows:
        raise ValueError(f"{path}: duplicate source IDs")
    jsonl_path = path.with_suffix(".jsonl")
    records = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(records) != expected_rows:
        raise ValueError(f"{jsonl_path}: incomplete raw results")
    for row, record in zip(rows, records):
        if not record.get("ok") or any(row[field] != record.get(field) for field in required):
            raise ValueError(f"{jsonl_path}: unsuccessful or inconsistent row {row['id']}")


def save_generation_config(path: Path, config: dict[str, Any]) -> None:
    if path.exists() and config["backend"] == "copilot":
        previous = json.loads(path.read_text(encoding="utf-8"))
        for field in ("model", "backend", "thinking", "temperature", "max_tokens", "prompt_variant", "max_t", "projection_threshold"):
            if previous.get(field) != config[field]:
                raise ValueError(f"Cannot reuse a run with changed {field}: {path}")
    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--backend", choices=("http", "copilot"), default="http")
    parser.add_argument("--base-url", default="https://api.moonshot.ai/v1")
    parser.add_argument("--run-tag")
    parser.add_argument("--thinking", choices=("disabled", "omit"), default="omit")
    parser.add_argument(
        "--temperature",
        default="omit",
        help="Numeric temperature or 'omit' for models with a provider-fixed value",
    )
    parser.add_argument("--max-tokens", type=int, help="HTTP default: 512; Copilot: provider default")
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

    if args.backend == "copilot" and (
        args.temperature != "omit" or args.max_tokens is not None or args.thinking != "omit"
    ):
        parser.error("Copilot uses provider defaults; omit temperature, thinking and max-tokens")
    if args.backend == "http" and args.max_tokens is None:
        args.max_tokens = 512
    api_key = read_api_key(prompt=args.api_key_stdin) if args.backend == "http" else None
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.datasets:
        selected = set(args.datasets)
        known = {record["dataset"] for record in records}
        unknown = selected - known
        if unknown:
            parser.error(f"Unknown datasets: {sorted(unknown)}")
        records = [record for record in records if record["dataset"] in selected]

    run_tag = args.run_tag or slug(
        args.model + ("_copilot_default" if args.backend == "copilot" else "")
    )
    metadata_root = RUNS / run_tag
    metadata_root.mkdir(parents=True, exist_ok=True)
    run_names_path = metadata_root / "run_names.json"
    run_names: dict[str, str] = (
        json.loads(run_names_path.read_text(encoding="utf-8"))
        if run_names_path.exists()
        else {}
    )
    env = dict(os.environ)
    env["LLM_MAX_RPM"] = str(args.max_rpm)
    if api_key is not None:
        env.update(
            {
                "LLM_API_KEY": api_key,
                "LLM_BASE_URL": args.base_url,
                "LLM_MODEL": args.model,
                "LLM_TEMPERATURE": args.temperature,
                "LLM_MAX_TOKENS": str(args.max_tokens),
                "LLM_THINKING": args.thinking,
            }
        )

    balance_before = check_balance(args.base_url, api_key) if api_key is not None else None
    if balance_before:
        print(
            f"Available balance before run: ${float(balance_before['available_balance']):.4f}",
            flush=True,
        )

    config = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "model": args.model,
        "backend": args.backend,
        "base_url": args.base_url if args.backend == "http" else None,
        "thinking": args.thinking if args.backend == "http" else "provider default",
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "provider_temperature_note": (
            "kimi-k2.6 non-thinking uses the provider-fixed temperature 0.6"
            if args.model == "kimi-k2.6" and args.temperature == "omit"
            else None
        ),
        "prompt_variant": "paper",
        "max_t": 3,
        "convergence": "carry T_(i-1) forward when normalized boundary signatures match",
        "projection_threshold": 0.85,
        "workers": args.workers,
        "max_rpm": args.max_rpm,
        "limit": args.limit,
        "datasets": [record["dataset"] for record in records],
        "datasets_completed": [],
        "run_names_file": str(run_names_path),
        "available_balance_before": balance_before,
        "api_key_saved": False,
    }
    config_path = metadata_root / "generation_config.json"
    save_generation_config(config_path, config)

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
            "--backend",
            args.backend,
            "--model",
            args.model,
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
                if proc.returncode:
                    raise ValueError(f"Generation process exited with status {proc.returncode}")
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
            config.update(
                status="failed",
                failed_dataset=dataset,
                error=str(last_validation_error),
            )
            save_generation_config(config_path, config)
            raise RuntimeError(
                f"{dataset} did not complete after {args.dataset_repair_passes} passes"
            ) from last_validation_error
        run_names_path.write_text(
            json.dumps(run_names, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        config["datasets_completed"].append(dataset)
        save_generation_config(config_path, config)

    balance_after = check_balance(args.base_url, api_key) if api_key is not None else None
    config.update(
        status="completed",
        completed_utc=datetime.now(timezone.utc).isoformat(),
        available_balance_after=balance_after,
    )
    save_generation_config(config_path, config)
    print(f"\nRun map: {metadata_root / 'run_names.json'}", flush=True)
    if balance_after:
        print(
            f"Available balance after run: ${float(balance_after['available_balance']):.4f}",
            flush=True,
        )


if __name__ == "__main__":
    main()
