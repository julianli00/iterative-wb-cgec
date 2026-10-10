#!/usr/bin/env python3
"""Evaluate existing T0--T3 predictions with character GLEU select-best."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import importlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PREPARED = ROOT / "data/benchmarks/prepared"
MANIFEST = PREPARED / "manifest.json"
RUNS = ROOT / "runs"
DEFAULT_OUTPUT = RUNS / "character_gleu_select_best"
GLEU_ROOT = ROOT / "external_tools/multi-reference-GLEU"
ROUNDS = ("T0", "T1", "T2", "T3")

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


def load_run_names() -> dict[str, str]:
    names = dict(RUN_NAMES)
    override_path = os.environ.get("CGEC_RUN_NAMES_FILE")
    if not override_path:
        return names
    path = Path(override_path)
    if not path.is_absolute():
        path = ROOT / path
    overrides = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(overrides, dict):
        raise ValueError(f"Run-name override must be a JSON object: {path}")
    unknown = set(overrides) - set(names)
    if unknown:
        raise ValueError(f"Unknown datasets in run-name override: {sorted(unknown)}")
    names.update({str(key): str(value) for key, value in overrides.items()})
    return names


def normalize_character_text(text: str) -> str:
    """Remove BOM and whitespace so only surface characters form n-grams."""

    return "".join((text or "").replace("\ufeff", "").split())


def read_gold_para(path: Path) -> list[tuple[str, str, list[str]]]:
    rows: list[tuple[str, str, list[str]]] = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for line_number, row in enumerate(csv.reader(stream, delimiter="\t"), start=1):
            if len(row) < 3:
                raise ValueError(f"{path}:{line_number}: expected ID, source, and reference")
            identifier = row[0]
            source = normalize_character_text(row[1])
            references = [normalize_character_text(value) for value in row[2:]]
            references = [value for value in references if value]
            if not references:
                raise ValueError(f"{path}:{line_number}: no non-empty reference")
            rows.append((identifier, source, references))
    return rows


def read_predictions(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    required = {"id", "source", *ROUNDS}
    missing = required - set(rows[0] if rows else [])
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    return rows


def load_gleu_module():
    if not GLEU_ROOT.exists():
        raise FileNotFoundError(f"Missing GLEU implementation: {GLEU_ROOT}")
    sys.path.insert(0, str(GLEU_ROOT))
    return importlib.import_module("gleu_wrapper")


def calculate_select_best(
    gleu: Any,
    source: str,
    hypothesis: str,
    references: list[str],
    *,
    max_n: int,
) -> tuple[float, int]:
    scores = [
        float(
            gleu.calculate_gleu_score(
                source,
                hypothesis,
                reference,
                n=max_n,
                tokenization="char",
            )
        )
        for reference in references
    ]
    selected_index, selected_score = max(enumerate(scores), key=lambda item: item[1])
    return selected_score, selected_index


def write_lines(path: Path, values: list[str]) -> None:
    path.write_text("\n".join(values) + "\n", encoding="utf-8")


def write_references(path: Path, references: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        for row in references:
            if any("\t" in reference or "\n" in reference for reference in row):
                raise ValueError(f"Reference contains a TSV-breaking character: {path}")
            # The upstream reader uses line.split("\t"), not csv.reader.  Keep
            # literal quotation marks untouched so the saved input round-trips.
            stream.write("\t".join(row) + "\n")


def format_markdown(compact_rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Character-based GLEU Select-best",
        "",
        "Scores are sentence-level multi-reference GLEU-select-best, averaged over each corpus and multiplied by 100. Character n-grams up to order 4 are used.",
        "",
        "| Dataset | Split | N | References | Multi-ref sentences | T0 | T1 | T2 | T3 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in compact_rows:
        lines.append(
            "| {dataset} | {split} | {sentences:,} | {references:,} | "
            "{multi_reference_sentences:,} | {T0:.2f} | {T1:.2f} | "
            "{T2:.2f} | {T3:.2f} |".format(**row)
        )
    lines.extend(
        [
            "",
            "For each sentence and stage, GLEU is computed against every available gold reference; the highest reference score is selected, and the selected sentence scores are macro-averaged.",
            "",
            "Normalization removes BOM characters and whitespace only. No BPE, word segmentation, OpenCC conversion, or LLM calls are used.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    run_names = load_run_names()
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--datasets", nargs="+", choices=sorted(run_names))
    parser.add_argument("--max-n", type=int, default=4)
    args = parser.parse_args()

    if args.max_n < 1:
        raise ValueError("--max-n must be positive")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.datasets:
        selected = set(args.datasets)
        records = [record for record in records if record["dataset"] in selected]
    gleu = load_gleu_module()

    long_rows: list[dict[str, Any]] = []
    compact_rows: list[dict[str, Any]] = []
    sentence_score_path = output / "sentence_scores.tsv"
    with sentence_score_path.open("w", encoding="utf-8", newline="") as score_stream:
        score_writer = csv.DictWriter(
            score_stream,
            delimiter="\t",
            lineterminator="\n",
            fieldnames=[
                "dataset",
                "split",
                "id",
                "stage",
                "reference_count",
                "selected_reference",
                "gleu_select_best",
            ],
        )
        score_writer.writeheader()

        for record in records:
            dataset = record["dataset"]
            split = record["split"]
            gold_path = ROOT / record["gold_para"]
            prediction_path = RUNS / f"{run_names[dataset]}.tsv"
            gold_rows = read_gold_para(gold_path)
            prediction_rows = read_predictions(prediction_path)
            expected_rows = int(record["rows"])
            if len(gold_rows) != expected_rows or len(prediction_rows) != expected_rows:
                raise ValueError(
                    f"{dataset}: row mismatch gold={len(gold_rows)}, "
                    f"predictions={len(prediction_rows)}, expected={expected_rows}"
                )

            originals: list[str] = []
            references_by_sentence: list[list[str]] = []
            hypotheses = {stage: [] for stage in ROUNDS}
            identifiers: list[str] = []
            for index, ((gold_id, source, references), prediction) in enumerate(
                zip(gold_rows, prediction_rows), start=1
            ):
                prediction_source = normalize_character_text(prediction["source"])
                if source != prediction_source:
                    raise ValueError(f"{dataset}: source mismatch at row {index}")
                prediction_id = prediction.get("id", "")
                if prediction_id and int(prediction_id) + 1 != int(gold_id):
                    raise ValueError(f"{dataset}: ID mismatch at row {index}")
                identifiers.append(gold_id)
                originals.append(source)
                references_by_sentence.append(references)
                for stage in ROUNDS:
                    hypotheses[stage].append(normalize_character_text(prediction[stage]))

            input_dir = output / dataset / split / "inputs"
            input_dir.mkdir(parents=True, exist_ok=True)
            write_lines(input_dir / "original.txt", originals)
            write_references(input_dir / "references.tsv", references_by_sentence)
            for stage in ROUNDS:
                write_lines(input_dir / f"hypothesis.{stage}.txt", hypotheses[stage])

            reference_count = sum(map(len, references_by_sentence))
            multi_reference_sentences = sum(
                len(references) > 1 for references in references_by_sentence
            )
            reference_distribution = Counter(map(len, references_by_sentence))
            compact: dict[str, Any] = {
                "dataset": dataset,
                "split": split,
                "sentences": expected_rows,
                "references": reference_count,
                "multi_reference_sentences": multi_reference_sentences,
            }
            for stage in ROUNDS:
                selected_scores: list[float] = []
                for identifier, source, hypothesis, references in zip(
                    identifiers,
                    originals,
                    hypotheses[stage],
                    references_by_sentence,
                ):
                    score, selected_index = calculate_select_best(
                        gleu,
                        source,
                        hypothesis,
                        references,
                        max_n=args.max_n,
                    )
                    if not math.isfinite(score):
                        raise ValueError(
                            f"{dataset}/{stage}/{identifier}: non-finite GLEU {score}"
                        )
                    selected_scores.append(score)
                    score_writer.writerow(
                        {
                            "dataset": dataset,
                            "split": split,
                            "id": identifier,
                            "stage": stage,
                            "reference_count": len(references),
                            "selected_reference": selected_index,
                            "gleu_select_best": f"{score:.12f}",
                        }
                    )
                corpus_score = math.fsum(selected_scores) / len(selected_scores)
                compact[stage] = corpus_score * 100.0
                long_rows.append(
                    {
                        "dataset": dataset,
                        "split": split,
                        "sentences": expected_rows,
                        "references": reference_count,
                        "multi_reference_sentences": multi_reference_sentences,
                        "stage": stage,
                        "gleu_select_best": corpus_score,
                        "gleu_select_best_x100": corpus_score * 100.0,
                    }
                )
                gleu.clear_caches()
            compact_rows.append(compact)
            stats = {
                "dataset": dataset,
                "split": split,
                "sentences": expected_rows,
                "references": reference_count,
                "multi_reference_sentences": multi_reference_sentences,
                "max_references": max(reference_distribution),
                "reference_count_distribution": {
                    str(count): sentences
                    for count, sentences in sorted(reference_distribution.items())
                },
            }
            (output / dataset / split / "stats.json").write_text(
                json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                f"{dataset}/{split}: "
                + " ".join(f"{stage}={compact[stage]:.2f}" for stage in ROUNDS),
                flush=True,
            )

    long_path = output / "scores.long.tsv"
    with long_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            delimiter="\t",
            lineterminator="\n",
            fieldnames=list(long_rows[0]),
        )
        writer.writeheader()
        for row in long_rows:
            writer.writerow(
                {
                    **row,
                    "gleu_select_best": f"{row['gleu_select_best']:.12f}",
                    "gleu_select_best_x100": f"{row['gleu_select_best_x100']:.6f}",
                }
            )

    compact_path = output / "scores.compact.tsv"
    compact_fields = [
        "dataset",
        "split",
        "sentences",
        "references",
        "multi_reference_sentences",
        *ROUNDS,
    ]
    with compact_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            delimiter="\t",
            lineterminator="\n",
            fieldnames=compact_fields,
        )
        writer.writeheader()
        for row in compact_rows:
            writer.writerow(
                {
                    **row,
                    **{stage: f"{row[stage]:.6f}" for stage in ROUNDS},
                }
            )

    (output / "scores.md").write_text(format_markdown(compact_rows), encoding="utf-8")
    config = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation": "multi-reference GLEU select-best",
        "tokenization": "character",
        "max_n": args.max_n,
        "aggregation": "maximum reference score per sentence, macro-average over sentences",
        "normalization": "remove BOM and whitespace; no OpenCC conversion",
        "rounds": list(ROUNDS),
        "llm_calls": False,
        "gleu_source": "https://doi.org/10.5281/zenodo.18206055",
        "gleu_upstream_commit": "d550c76dd66228eb2c05b197efc49040a2dafe37",
        "local_patch": "fix upstream character-tokenization global assignment",
        "datasets": [row["dataset"] for row in compact_rows],
    }
    (output / "run_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    method = f"""# Character-based GLEU Evaluation

This run reuses the saved T0--T3 predictions selected by the run-name map and makes no LLM or API calls.

## Method

- Evaluator: Park's multi-reference GLEU v1 ({config['gleu_source']}).
- Upstream commit: `{config['gleu_upstream_commit']}`.
- Tokenization: Unicode characters, n-grams 1 through {args.max_n}.
- Multi-reference aggregation: compute GLEU against every reference, select the highest score for each sentence, then macro-average the selected sentence scores.
- Normalization: remove BOM and all whitespace. No BPE, word segmentation, or OpenCC conversion.
- Inputs: the same prepared source/reference pairs and saved T0--T3 hypotheses used by the character M2 experiments.

## Upstream correction

The archived v1 `set_tokenization` function assigns `split_ngram` in local scope, so `--token char` silently retains word tokenization. The vendored copy changes that assignment to the module global and clears tokenization-dependent caches. Regression tests verify that an unspaced Chinese string produces individual character n-grams.

## Outputs

- `scores.compact.tsv`: one row per dataset, GLEU x 100 for T0--T3.
- `scores.long.tsv`: raw 0--1 and x100 scores by dataset and stage.
- `scores.md`: report-ready Markdown table.
- `sentence_scores.tsv`: selected score and selected reference index for every sentence and stage.
- `<dataset>/<split>/inputs/`: exact normalized source, references, and hypotheses used for scoring.
- `<dataset>/<split>/stats.json`: reference-density audit.
"""
    (output / "METHOD.md").write_text(method, encoding="utf-8")


if __name__ == "__main__":
    main()
