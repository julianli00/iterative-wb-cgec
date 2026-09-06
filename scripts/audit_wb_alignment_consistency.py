#!/usr/bin/env python3
"""Audit that the CGEC pipeline uses the chinese-wb-fixing WB alignment code."""

from __future__ import annotations

import argparse
import csv
import importlib.util
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "runs/flaCGEC_20_T3_deepseek_v4_flash.tsv"
DEFAULT_WB_REPO = ROOT.parent / "chinese-wb-fixing"
DEFAULT_SHAPE_TABLE = Path(
    ROOT.parent
    / "fixing_wb/transformer/data/0423/triplet_no_dup_threshold.csv"
)


def import_module_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def git_head(repo: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--wb-repo", type=Path, default=DEFAULT_WB_REPO)
    parser.add_argument("--shape-table", type=Path, default=DEFAULT_SHAPE_TABLE)
    parser.add_argument("--threshold", type=float, default=0.85)
    parser.add_argument("--bert-model", default="bert-base-chinese")
    args = parser.parse_args()

    run_module = import_module_from_path(
        "run_iterative_gec", ROOT / "scripts/run_iterative_gec.py"
    )
    wb_module = run_module.load_wb_module(args.wb_repo)

    print(f"WB repo: {args.wb_repo}")
    print(f"WB repo HEAD: {git_head(args.wb_repo)}")
    print(f"WB module: {args.wb_repo / 'src/pipeline/alignment/step2_similarity_alignment_projection.py'}")
    print(f"Shape table: {args.shape_table}")
    print(f"Threshold: {args.threshold}")

    wb_module.load_bert_model(args.bert_model)
    shape_table = wb_module.load_shape_table(str(args.shape_table))

    rows = list(csv.DictReader(args.results.open(encoding="utf-8"), delimiter="\t"))
    mismatches: list[tuple[str, str, str, str]] = []

    for row in rows:
        t1_ltp = wb_module.ltp_segment(row["T1"])
        original = wb_module.process_pair(
            row["S1"],
            t1_ltp,
            shape_table,
            args.threshold,
        )["projected"]
        adapter = run_module.project_with_existing_boundaries(
            wb_module=wb_module,
            source_segmented=row["S1"],
            target_segmented=t1_ltp,
            shape_table=shape_table,
            threshold=args.threshold,
        )["projected"]
        recorded = row["S2"]
        if original != adapter or adapter != recorded:
            mismatches.append((row["id"], original, adapter, recorded))

    print(f"Checked rows: {len(rows)}")
    print(f"S1->S2 mismatches against original process_pair: {len(mismatches)}")
    for row_id, original, adapter, recorded in mismatches[:10]:
        print(f"\nMismatch id={row_id}")
        print(f"original process_pair: {original}")
        print(f"current adapter:       {adapter}")
        print(f"recorded S2:           {recorded}")

    if mismatches:
        raise SystemExit(1)

    print("PASS: first projection round is consistent with chinese-wb-fixing process_pair.")


if __name__ == "__main__":
    main()
