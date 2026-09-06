#!/usr/bin/env python3
"""Run and evaluate the selected sentence-level scoreboard datasets through T3."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PREPARED = ROOT / "data/benchmarks/prepared"
RUNS = ROOT / "runs"


SPECS = {
    "nlpcc2018": ("nlpcc2018/test", "m2", False),
    "mucgec": ("mucgec/test", "m2", False),
    "yaclc": ("yaclc/validation", "para", False),
    "fcgec": ("fcgec/validation", "para", False),
    "nacgec": ("nacgec/test", "para", False),
    "nasgec_exam": ("nasgec_exam/test", "para", False),
    "cefe_track3": ("cefe_track3/validation", "para", False),
}


def run_name(dataset: str, prepared_subdir: str) -> str:
    split = prepared_subdir.split("/")[1]
    suffix = "_bpe_fixed" if dataset == "nasgec_exam" else ""
    return f"{dataset}_{split}_all_T3_deepseek_v4_pro_paper_converged{suffix}"


def line_count(path: Path) -> int:
    with path.open(encoding="utf-8") as stream:
        return sum(1 for _ in stream)


def result_is_complete(path: Path, expected_rows: int) -> bool:
    if not path.exists():
        return False
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return len(rows) == expected_rows and all(row.get("ok") and "T3" in row for row in rows)


def run_command(command: list[str]) -> None:
    print("$", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", nargs="+", choices=sorted(SPECS), default=list(SPECS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    status_path = RUNS / "scoreboard_t3_status.json"
    if status_path.exists():
        previous_status = json.loads(status_path.read_text(encoding="utf-8"))
    else:
        previous_status = []
    status_by_dataset = {row["dataset"]: row for row in previous_status}
    for dataset in args.datasets:
        prepared_subdir, gold_kind, bpe = SPECS[dataset]
        prepared_dir = PREPARED / prepared_subdir
        input_path = prepared_dir / "pipeline.tsv"
        expected_rows = line_count(input_path)
        name = run_name(dataset, prepared_subdir)
        result_jsonl = RUNS / f"{name}.jsonl"
        result_tsv = RUNS / f"{name}.tsv"

        complete = result_is_complete(result_jsonl, expected_rows)
        if args.force or not complete:
            run_args = [
                    sys.executable,
                    "scripts/run_iterative_gec.py",
                    "--input",
                    str(input_path),
                    "--limit",
                    "0",
                    "--max-t",
                    "3",
                    "--run-name",
                    name,
                    "--prompt-variant",
                    "paper",
                    "--workers",
                    str(args.workers),
                    "--checkpoint-every",
                    str(args.checkpoint_every),
                ]
            if result_jsonl.exists() and not args.force:
                run_args.extend(["--resume-partial-jsonl", str(result_jsonl)])
            run_command(run_args)
            complete = result_is_complete(result_jsonl, expected_rows)
        else:
            print(f"Skipping complete run: {dataset} ({expected_rows} rows)", flush=True)
        if not complete:
            raise RuntimeError(f"Incomplete result after run: {result_jsonl}")

        eval_command = [
            sys.executable,
            "scripts/evaluate_cherrant.py",
            "--results",
            str(result_tsv),
            "--rounds",
            "T0",
            "T1",
            "T2",
            "T3",
            "--granularity",
            "char",
        ]
        if gold_kind == "m2":
            eval_command.extend(["--gold-m2", str(prepared_dir / "gold.m2")])
        else:
            eval_command.extend(["--gold-para", str(prepared_dir / "gold.para")])
        if bpe:
            eval_command.append("--bpe")
        run_command(eval_command)

        summary_path = RUNS / "cherrant_eval" / name / "char" / "summary.tsv"
        with summary_path.open(encoding="utf-8") as stream:
            metrics = list(csv.DictReader(stream, delimiter="\t"))
        status_by_dataset[dataset] = {
            "dataset": dataset,
            "prepared_split": prepared_subdir,
            "rows": expected_rows,
            "run_name": name,
            "scores": {row["round"]: float(row["F0.5"]) for row in metrics},
        }
        status_path.write_text(
            json.dumps(list(status_by_dataset.values()), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
