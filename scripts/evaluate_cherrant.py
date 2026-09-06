#!/usr/bin/env python3
"""Evaluate CGEC predictions with ChERRANT char-level P/R/F0.5."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "runs/flaCGEC_20_T3_deepseek_v4_flash_paper_prompt_v2.tsv"
DEFAULT_CHERRANT = ROOT / "external_tools/MuCGEC/scorers/ChERRANT"
DEFAULT_OUT_DIR = ROOT / "runs/cherrant_eval"


def clean_cell(text: str) -> str:
    return (
        (text or "")
        .replace("\ufeff", "")
        .replace("\t", " ")
        .replace("\n", " ")
        .strip()
    )


def write_cherrant_parallel(rows: list[list[str]], path: Path) -> None:
    """Write raw TSV because ChERRANT splits lines without CSV decoding."""
    with path.open("w", encoding="utf-8", newline="") as stream:
        for row in rows:
            stream.write("\t".join(clean_cell(cell) for cell in row) + "\n")


def run_cmd(cmd: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed with code {proc.returncode}: {' '.join(cmd)}\n{proc.stdout}"
        )
    return proc.stdout


def parse_cherrant_output(output: str) -> dict[str, float]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for line in lines:
        if re.match(r"^\d+\s+\d+\s+\d+\s+", line):
            parts = line.split()
            return {
                "TP": int(parts[0]),
                "FP": int(parts[1]),
                "FN": int(parts[2]),
                "Prec": float(parts[3]),
                "Rec": float(parts[4]),
                "F0.5": float(parts[5]),
            }
    raise ValueError(f"Could not parse ChERRANT output:\n{output}")


def write_hypothesis_files(rows: list[dict[str, str]], rounds: list[str], out_dir: Path) -> None:
    for round_name in rounds:
        hyp_path = out_dir / f"{round_name}.para"
        write_cherrant_parallel(
            [
                [str(idx), row["source"], row[round_name]]
                for idx, row in enumerate(rows, start=1)
            ],
            hyp_path,
        )


def detokenize_m2_text(text: str, *, bpe: bool = False) -> str:
    tokens = clean_cell(text).split()
    if bpe:
        tokens = [token[2:] if token.startswith("##") else token for token in tokens]
    return "".join(tokens)


def m2_sources(path: Path, *, bpe: bool = False) -> list[str]:
    sources: list[str] = []
    for block in path.read_text(encoding="utf-8-sig").strip().split("\n\n"):
        first = next((line for line in block.splitlines() if line.strip()), "")
        if not first.startswith("S "):
            raise ValueError(f"Invalid M2 block in {path}")
        sources.append(detokenize_m2_text(first[2:], bpe=bpe))
    return sources


def para_sources(path: Path) -> list[str]:
    with path.open(encoding="utf-8", newline="") as stream:
        return ["".join(clean_cell(row[1]).split()) for row in csv.reader(stream, delimiter="\t")]


def validate_gold_sources(rows: list[dict[str, str]], gold_sources: list[str], path: Path) -> None:
    result_sources = ["".join(clean_cell(row["source"]).split()) for row in rows]
    if len(result_sources) != len(gold_sources):
        raise ValueError(
            f"Gold/result row mismatch for {path}: {len(gold_sources)} != {len(result_sources)}"
        )
    for index, (result_source, gold_source) in enumerate(zip(result_sources, gold_sources), start=1):
        if result_source != gold_source:
            raise ValueError(f"Gold/result source mismatch at row {index} for {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--cherrant-dir", type=Path, default=DEFAULT_CHERRANT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--rounds", nargs="+", default=["T0", "T1", "T2", "T3"])
    parser.add_argument("--granularity", choices=["char", "word"], default="char")
    gold_group = parser.add_mutually_exclusive_group()
    gold_group.add_argument("--gold-para", type=Path, help="External id/source/reference(s) TSV")
    gold_group.add_argument("--gold-m2", type=Path, help="Official reference M2 file")
    parser.add_argument("--bpe", action="store_true", help="Use ChERRANT BPE tokenization")
    args = parser.parse_args()

    rows = list(csv.DictReader(args.results.open(encoding="utf-8"), delimiter="\t"))
    if not rows:
        raise RuntimeError(f"No rows found in {args.results}")

    run_name = args.results.stem
    out_dir = args.out_dir / run_name / args.granularity
    out_dir.mkdir(parents=True, exist_ok=True)
    write_hypothesis_files(rows, args.rounds, out_dir)

    python = sys.executable
    gold_m2 = out_dir / f"gold.{args.granularity}.m2"
    if args.gold_m2:
        validate_gold_sources(
            rows,
            m2_sources(args.gold_m2, bpe=args.bpe),
            args.gold_m2,
        )
        shutil.copyfile(args.gold_m2, gold_m2)
    else:
        gold_path = out_dir / "gold.para"
        if args.gold_para:
            validate_gold_sources(rows, para_sources(args.gold_para), args.gold_para)
            with args.gold_para.open(encoding="utf-8", newline="") as stream:
                write_cherrant_parallel(list(csv.reader(stream, delimiter="\t")), gold_path)
        else:
            write_cherrant_parallel(
                [
                    [str(index), row["source"], row["target"]]
                    for index, row in enumerate(rows, start=1)
                ],
                gold_path,
            )
        gold_cmd = [
            python,
            "parallel_to_m2.py",
            "-f",
            str(gold_path),
            "-o",
            str(gold_m2),
            "-g",
            args.granularity,
            "-s",
            "all",
        ]
        if args.bpe:
            gold_cmd.append("--bpe")
        run_cmd(gold_cmd, cwd=args.cherrant_dir)

    summary: list[dict[str, float | str]] = []
    for round_name in args.rounds:
        hyp_m2 = out_dir / f"{round_name}.{args.granularity}.m2"
        hyp_cmd = [
                python,
                "parallel_to_m2.py",
                "-f",
                str(out_dir / f"{round_name}.para"),
                "-o",
                str(hyp_m2),
                "-g",
                args.granularity,
            ]
        if args.bpe:
            hyp_cmd.append("--bpe")
        run_cmd(hyp_cmd, cwd=args.cherrant_dir)
        compare_output = run_cmd(
            [
                python,
                "compare_m2_for_evaluation.py",
                "-hyp",
                str(hyp_m2),
                "-ref",
                str(gold_m2),
                "--beta",
                "0.5",
            ],
            cwd=args.cherrant_dir,
        )
        metrics = parse_cherrant_output(compare_output)
        metrics["round"] = round_name
        summary.append(metrics)
        (out_dir / f"{round_name}.compare.txt").write_text(compare_output, encoding="utf-8")

    summary_path = out_dir / "summary.tsv"
    with summary_path.open("w", encoding="utf-8", newline="") as f:
        fieldnames = ["round", "TP", "FP", "FN", "Prec", "Rec", "F0.5"]
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary)

    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Rows: {len(rows)}")
    print(f"Granularity: {args.granularity}")
    print(f"Gold: {args.gold_m2 or args.gold_para or 'results target column'}")
    print(f"BPE: {args.bpe}")
    print(f"Summary: {summary_path}")
    print("round\tTP\tFP\tFN\tPrec\tRec\tF0.5")
    for row in summary:
        print(
            f"{row['round']}\t{row['TP']}\t{row['FP']}\t{row['FN']}\t"
            f"{row['Prec']:.4f}\t{row['Rec']:.4f}\t{row['F0.5']:.4f}"
        )


if __name__ == "__main__":
    main()
