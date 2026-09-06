#!/usr/bin/env python3
"""Rebuild the scoreboard T3 experiment summary from durable run artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
MANIFEST = ROOT / "data/benchmarks/prepared/manifest.json"


RUN_NAMES = {
    "nlpcc2018": "nlpcc2018_test_all_T3_deepseek_v4_pro_paper_converged",
    "mucgec": "mucgec_test_all_T3_deepseek_v4_pro_paper_converged",
    "yaclc": "yaclc_validation_all_T3_deepseek_v4_pro_paper_converged",
    "flacgec": "flaCGEC_all_T10_deepseek_v4_pro_paper_converged",
    "fcgec": "fcgec_validation_all_T3_deepseek_v4_pro_paper_converged",
    "nacgec": "nacgec_test_all_T3_deepseek_v4_pro_paper_converged",
    "nasgec_exam": "nasgec_exam_test_all_T3_deepseek_v4_pro_paper_converged_bpe_fixed",
    "cefe_track3": "cefe_track3_validation_all_T3_deepseek_v4_pro_paper_converged",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def read_scores(run_name: str) -> dict[str, float]:
    path = RUNS / "cherrant_eval" / run_name / "char" / "summary.tsv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as stream:
        rows = csv.DictReader(stream, delimiter="\t")
        return {
            row["round"]: 100 * float(row["F0.5"])
            for row in rows
            if row["round"] in {"T0", "T1", "T2", "T3"}
        }


def successful_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("ok") and "T3" in row]


def boundary_positions(segmented_text: str) -> set[int]:
    positions: set[int] = set()
    offset = 0
    tokens = segmented_text.split()
    for token in tokens[:-1]:
        offset += len(token)
        positions.add(offset - 1)
    return positions


def projection_counts(rows: list[dict[str, Any]]) -> tuple[int, int]:
    splits = 0
    merges = 0
    for row in rows:
        for stage in (2, 3):
            previous = row.get(f"S{stage - 1}")
            current = row.get(f"S{stage}")
            if not previous or not current:
                continue
            previous_boundaries = boundary_positions(previous)
            current_boundaries = boundary_positions(current)
            splits += len(current_boundaries - previous_boundaries)
            merges += len(previous_boundaries - current_boundaries)
    return splits, merges


def token_counts(rows: list[dict[str, Any]]) -> tuple[int, int, int]:
    calls = 0
    prompt_tokens = 0
    completion_tokens = 0
    for row in rows:
        for call in row.get("meta", {}).get("api", []):
            if int(call.get("T", 0)) > 3:
                continue
            calls += 1
            usage = call.get("usage") or {}
            prompt_tokens += int(usage.get("prompt_tokens", 0))
            completion_tokens += int(usage.get("completion_tokens", 0))
    return calls, prompt_tokens, completion_tokens


def convergence_count(rows: list[dict[str, Any]]) -> int:
    total = 0
    for row in rows:
        convergence = row.get("meta", {}).get("convergence") or {}
        at_s = convergence.get("at_S")
        if convergence.get("converged") and at_s is not None and int(at_s) <= 3:
            total += 1
    return total


def build_summary() -> list[dict[str, Any]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    summary: list[dict[str, Any]] = []
    for item in manifest:
        dataset = item["dataset"]
        run_name = RUN_NAMES[dataset]
        rows = read_jsonl(RUNS / f"{run_name}.jsonl")
        successes = successful_rows(rows)
        expected = int(item["rows"])
        if len(successes) == expected and len(rows) == expected:
            status = "complete"
        elif successes:
            status = "partial"
        else:
            status = "not started"

        scores = read_scores(run_name) if status == "complete" else {}
        splits, merges = projection_counts(successes)
        calls, prompt_tokens, completion_tokens = token_counts(successes)
        summary.append(
            {
                "dataset": dataset,
                "split": item["split"],
                "rows": expected,
                "successful_rows": len(successes),
                "status": status,
                "T0": scores.get("T0"),
                "T1": scores.get("T1"),
                "T2": scores.get("T2"),
                "T3": scores.get("T3"),
                "converged_by_T3": convergence_count(successes),
                "projection_splits_through_S3": splits,
                "projection_merges_through_S3": merges,
                "api_calls_through_T3": calls,
                "prompt_tokens_through_T3": prompt_tokens,
                "completion_tokens_through_T3": completion_tokens,
                "run_name": run_name,
            }
        )
    return summary


def format_score(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def write_outputs(summary: list[dict[str, Any]]) -> None:
    tsv_path = RUNS / "scoreboard_t3_summary.tsv"
    with tsv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(summary)

    lines = [
        "# Scoreboard T3 Experiment Summary",
        "",
        "Scores are ChERRANT character/span F0.5 multiplied by 100. Runs use "
        "`deepseek-v4-pro`, temperature `0.000001`, disabled thinking, the paper "
        "prompts, LTP segmentation, and the `chinese-wb-fixing` projection.",
        "",
        "| Dataset | Split | Progress | T0 | T1 | T2 | T3 | Converged by T3 | Splits | Merges |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        display = {
            **row,
            "T0": format_score(row["T0"]),
            "T1": format_score(row["T1"]),
            "T2": format_score(row["T2"]),
            "T3": format_score(row["T3"]),
            "splits": row["projection_splits_through_S3"],
            "merges": row["projection_merges_through_S3"],
        }
        lines.append(
            "| {dataset} | {split} | {successful_rows:,}/{rows:,} | {T0} | {T1} | "
            "{T2} | {T3} | {converged_by_T3:,} | {splits:,} | {merges:,} |".format(
                **display,
            )
        )
    lines.extend(
        [
            "",
            "A score is shown only after every row in the selected split has a successful T3 output.",
            "FlaCGEC was already extended through T10; this table reports its T0-T3 prefix.",
            "",
        ]
    )
    (RUNS / "scoreboard_t3_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    summary = build_summary()
    write_outputs(summary)
    print(RUNS / "scoreboard_t3_summary.tsv")
    print(RUNS / "scoreboard_t3_summary.md")


if __name__ == "__main__":
    main()
