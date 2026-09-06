#!/usr/bin/env python3
"""Run a traceable, uniform ChERRANT character-level evaluation.

The existing preliminary evaluation mixes official reference M2 files with
references generated from parallel text.  This script preserves those files
and writes a separate evaluation tree where every dataset is scored against a
reference M2 generated from ``gold.para``.  When an official M2 is available,
it is retained and scored as an additional comparison condition.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PREPARED = ROOT / "data/benchmarks/prepared"
MANIFEST = PREPARED / "manifest.json"
RUNS = ROOT / "runs"
CHERRANT = ROOT / "external_tools/MuCGEC/scorers/ChERRANT"
DEFAULT_OUTPUT = RUNS / "standardized_m2_eval"
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

T_LINE = re.compile(r"^T(?P<coder>\d+)(?:-A(?P<alignment>\d+))?\s+(?P<target>.*)$")


def normalize_text(text: str) -> str:
    return "".join((text or "").replace("\ufeff", "").split())


def clean_cell(text: str) -> str:
    return (text or "").replace("\ufeff", "").replace("\t", " ").replace("\n", " ").strip()


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def discover_cherrant_python() -> Path:
    configured = os.environ.get("CHERRANT_PYTHON")
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        [
            Path(sys.executable),
            Path(sys.executable).parent.parent / "envs/fixwb/bin/python",
        ]
    )
    checked: set[Path] = set()
    for candidate in candidates:
        if candidate in checked or not candidate.exists():
            continue
        checked.add(candidate)
        probe = subprocess.run(
            [str(candidate), "-c", "import ltp, opencc, torch"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if probe.returncode == 0:
            return candidate
    raise RuntimeError(
        "No Python interpreter with the ChERRANT dependencies was found. "
        "Set CHERRANT_PYTHON or pass --cherrant-python."
    )


@dataclass(frozen=True)
class DatasetSpec:
    dataset: str
    split: str
    rows: int
    gold_para: Path
    gold_m2: Path | None
    result_tsv: Path
    previous_eval_dir: Path
    bpe: bool
    official_m2_bpe: bool


@dataclass
class M2Block:
    source: str
    reference_ids: set[int]
    targets: dict[int, set[str]]
    target_line_counts: Counter[int]
    noop_ids: set[int]

    @property
    def target_set(self) -> set[str]:
        return {target for targets in self.targets.values() for target in targets}


def load_run_names() -> dict[str, str]:
    """Return default prediction runs, optionally overridden by a JSON map."""

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


def load_specs() -> list[DatasetSpec]:
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))
    run_names = load_run_names()
    specs: list[DatasetSpec] = []
    for record in records:
        dataset = record["dataset"]
        run_name = run_names[dataset]
        gold_m2 = ROOT / record["gold_m2"] if record.get("gold_m2") else None
        specs.append(
            DatasetSpec(
                dataset=dataset,
                split=record["split"],
                rows=int(record["rows"]),
                gold_para=ROOT / record["gold_para"],
                gold_m2=gold_m2,
                result_tsv=RUNS / f"{run_name}.tsv",
                previous_eval_dir=RUNS / "cherrant_eval" / run_name / "char",
                bpe=bool(record.get("cherrant_bpe", False)),
                official_m2_bpe=bool(record.get("official_m2_bpe", False)),
            )
        )
    return specs


def split_m2_blocks(path: Path) -> list[list[str]]:
    text = path.read_text(encoding="utf-8-sig").replace("\ufeff", "").strip()
    if not text:
        return []
    return [[line for line in block.splitlines() if line.strip()] for block in text.split("\n\n")]


def detokenize_m2_text(text: str, *, bpe: bool = False) -> str:
    tokens = text.split()
    if bpe:
        tokens = [token[2:] if token.startswith("##") else token for token in tokens]
    return normalize_text("".join(tokens))


def parse_m2(path: Path, *, bpe: bool = False) -> list[M2Block]:
    parsed: list[M2Block] = []
    for index, lines in enumerate(split_m2_blocks(path), start=1):
        if not lines or not lines[0].startswith("S "):
            raise ValueError(f"Invalid M2 block {index} in {path}")
        source = detokenize_m2_text(lines[0][2:], bpe=bpe)
        reference_ids: set[int] = set()
        targets: dict[int, set[str]] = {}
        target_line_counts: Counter[int] = Counter()
        noop_ids: set[int] = set()
        for line in lines[1:]:
            target_match = T_LINE.match(line)
            if target_match:
                coder = int(target_match.group("coder"))
                target = target_match.group("target")
                reference_ids.add(coder)
                target_line_counts[coder] += 1
                targets.setdefault(coder, set()).add(
                    source
                    if target.strip() == "没有错误"
                    else detokenize_m2_text(target, bpe=bpe)
                )
                if target.strip() == "没有错误":
                    noop_ids.add(coder)
                continue
            if line.startswith("A "):
                fields = line[2:].split("|||")
                if len(fields) < 2:
                    raise ValueError(f"Invalid M2 edit in block {index} of {path}: {line}")
                try:
                    coder = int(fields[-1])
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid M2 annotator id in block {index} of {path}: {line}"
                    ) from exc
                reference_ids.add(coder)
                if fields[1] == "noop":
                    noop_ids.add(coder)
                    targets.setdefault(coder, set()).add(source)
        if not reference_ids:
            reference_ids.add(0)
            targets.setdefault(0, set()).add(source)
            noop_ids.add(0)
        parsed.append(M2Block(source, reference_ids, targets, target_line_counts, noop_ids))
    return parsed


def audit_m2(path: Path, *, bpe: bool = False) -> dict[str, Any]:
    blocks = parse_m2(path, bpe=bpe)
    reference_counts = Counter(len(block.reference_ids) for block in blocks)
    extra_alignment_targets = sum(
        max(0, count - 1)
        for block in blocks
        for count in block.target_line_counts.values()
    )
    return {
        "path": display_path(path),
        "sentences": len(blocks),
        "total_references": sum(len(block.reference_ids) for block in blocks),
        "reference_count_distribution": {
            str(count): sentences for count, sentences in sorted(reference_counts.items())
        },
        "max_references": max(reference_counts, default=0),
        "sentences_with_more_than_3_references": sum(
            count for refs, count in reference_counts.items() if refs > 3
        ),
        "noop_references": sum(len(block.noop_ids) for block in blocks),
        "target_lines": sum(sum(block.target_line_counts.values()) for block in blocks),
        "extra_alignment_target_lines": extra_alignment_targets,
    }


def compare_reference_m2(
    official_path: Path,
    generated_path: Path,
    cherrant_python: Path | None = None,
    *,
    official_bpe: bool = False,
    generated_bpe: bool = False,
) -> dict[str, Any]:
    official = parse_m2(official_path, bpe=official_bpe)
    generated = parse_m2(generated_path, bpe=generated_bpe)
    if len(official) != len(generated):
        raise ValueError(
            f"Official/generated M2 row mismatch: {len(official)} != {len(generated)}"
        )
    source_matches = 0
    reference_count_matches = 0
    target_set_matches = 0
    official_only_targets = 0
    generated_only_targets = 0
    mismatch_examples: list[dict[str, Any]] = []
    for index, (official_block, generated_block) in enumerate(
        zip(official, generated), start=1
    ):
        source_matches += official_block.source == generated_block.source
        reference_count_matches += (
            len(official_block.reference_ids) == len(generated_block.reference_ids)
        )
        official_targets = official_block.target_set
        generated_targets = generated_block.target_set
        target_set_matches += official_targets == generated_targets
        official_only_targets += len(official_targets - generated_targets)
        generated_only_targets += len(generated_targets - official_targets)
        if official_targets != generated_targets and len(mismatch_examples) < 10:
            mismatch_examples.append(
                {
                    "sentence": index,
                    "official_only": sorted(official_targets - generated_targets),
                    "generated_only": sorted(generated_targets - official_targets),
                }
            )
    result = {
        "sentences": len(official),
        "matching_sources": source_matches,
        "matching_reference_counts": reference_count_matches,
        "matching_target_sets": target_set_matches,
        "official_only_targets": official_only_targets,
        "generated_only_targets": generated_only_targets,
        "raw_target_mismatch_examples": mismatch_examples,
    }
    if cherrant_python:
        flattened = [
            target for block in official for target in sorted(block.target_set)
        ]
        simplified = iter(simplify_texts(flattened, cherrant_python))
        matches_after_t2s = 0
        for official_block, generated_block in zip(official, generated):
            simplified_official = {
                normalize_text(next(simplified))
                for _target in sorted(official_block.target_set)
            }
            matches_after_t2s += simplified_official == generated_block.target_set
        result["matching_target_sets_after_t2s"] = matches_after_t2s
    return result


def filter_m2_references(source: Path, destination: Path, limit: int) -> None:
    output_blocks: list[str] = []
    for block_number, lines in enumerate(split_m2_blocks(source), start=1):
        if not lines or not lines[0].startswith("S "):
            raise ValueError(f"Invalid M2 block {block_number} in {source}")
        kept = [lines[0]]
        for line in lines[1:]:
            target_match = T_LINE.match(line)
            if target_match:
                if int(target_match.group("coder")) < limit:
                    kept.append(line)
                continue
            if line.startswith("A "):
                fields = line[2:].split("|||")
                if int(fields[-1]) < limit:
                    kept.append(line)
        output_blocks.append("\n".join(kept))
    destination.write_text("\n\n".join(output_blocks) + "\n", encoding="utf-8")


def para_rows(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return [[clean_cell(cell) for cell in row] for row in csv.reader(stream, delimiter="\t")]


def simplify_texts(texts: Iterable[str], cherrant_python: Path) -> list[str]:
    values = list(texts)
    proc = subprocess.run(
        [
            str(cherrant_python),
            "-c",
            (
                "import json,sys; from opencc import OpenCC; "
                "cc=OpenCC('t2s'); values=json.load(sys.stdin); "
                "json.dump([cc.convert(value) for value in values], sys.stdout, "
                "ensure_ascii=False)"
            ),
        ],
        input=json.dumps(values, ensure_ascii=False),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode:
        raise RuntimeError(f"OpenCC validation conversion failed:\n{proc.stderr}")
    converted = json.loads(proc.stdout)
    if len(converted) != len(values):
        raise ValueError("OpenCC validation conversion changed the number of strings")
    return converted


def write_cherrant_parallel(rows: Iterable[Iterable[str]], destination: Path) -> None:
    """Write raw tab-separated fields for ChERRANT's ``line.split`` reader."""
    with destination.open("w", encoding="utf-8", newline="") as stream:
        for row in rows:
            stream.write("\t".join(clean_cell(cell) for cell in row) + "\n")


def load_result_rows(spec: DatasetSpec) -> list[dict[str, str]]:
    if not spec.result_tsv.exists():
        raise FileNotFoundError(f"Missing result TSV: {spec.result_tsv}")
    with spec.result_tsv.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if len(rows) != spec.rows:
        raise ValueError(
            f"{spec.dataset}: result row mismatch {len(rows)} != {spec.rows}"
        )
    missing = [round_name for round_name in ROUNDS if round_name not in rows[0]]
    if missing:
        raise ValueError(f"{spec.dataset}: missing result columns {missing}")
    return rows


def write_hypothesis_para(
    rows: list[dict[str, str]], round_name: str, destination: Path
) -> None:
    write_cherrant_parallel(
        (
            [str(index), row["source"], row[round_name]]
            for index, row in enumerate(rows, start=1)
        ),
        destination,
    )


def validate_m2_sources(
    path: Path, expected_sources: Iterable[str], *, bpe: bool = False
) -> None:
    blocks = parse_m2(path, bpe=bpe)
    expected = [normalize_text(source) for source in expected_sources]
    actual = [block.source for block in blocks]
    if len(actual) != len(expected):
        raise ValueError(f"M2/source row mismatch for {path}: {len(actual)} != {len(expected)}")
    for index, (actual_source, expected_source) in enumerate(zip(actual, expected), start=1):
        if actual_source != expected_source:
            raise ValueError(f"M2/source mismatch at row {index} in {path}")


def validate_generated_reference(
    path: Path, gold_para: Path, cherrant_python: Path, *, bpe: bool = False
) -> dict[str, int]:
    parallel = para_rows(gold_para)
    validate_m2_sources(path, (row[1] for row in parallel), bpe=bpe)
    blocks = parse_m2(path, bpe=bpe)
    flattened_targets = [target for row in parallel for target in row[2:]]
    simplified_targets = iter(simplify_texts(flattened_targets, cherrant_python))
    reference_count_mismatches = 0
    target_set_mismatches = 0
    for row, block in zip(parallel, blocks):
        expected_count = len(row) - 2
        if block.reference_ids != set(range(expected_count)):
            reference_count_mismatches += 1
        expected_targets = {
            normalize_text(next(simplified_targets)) for _target in row[2:]
        }
        if block.target_set != expected_targets:
            target_set_mismatches += 1
    if reference_count_mismatches:
        raise ValueError(
            f"Generated reference IDs disagree with gold.para in "
            f"{reference_count_mismatches} rows: {path}"
        )
    return {"target_set_mismatches_after_normalization": target_set_mismatches}


def validate_hypothesis_m2(
    path: Path,
    rows: list[dict[str, str]],
    round_name: str,
    expected_targets: list[str],
    *,
    bpe: bool = False,
) -> None:
    validate_m2_sources(path, (row["source"] for row in rows), bpe=bpe)
    for index, (block, row) in enumerate(
        zip(parse_m2(path, bpe=bpe), rows), start=1
    ):
        expected_target = normalize_text(expected_targets[index - 1])
        if block.reference_ids != {0}:
            raise ValueError(f"Unexpected hypothesis annotator IDs at row {index} in {path}")
        if block.target_set != {expected_target}:
            raise ValueError(f"Hypothesis target mismatch at row {index} in {path}")


def run_command(command: list[str], cwd: Path, command_log: list[dict[str, Any]]) -> str:
    started = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    command_log.append(
        {
            "started_utc": started,
            "cwd": str(cwd.relative_to(ROOT)),
            "command": command,
            "returncode": proc.returncode,
        }
    )
    if proc.returncode:
        raise RuntimeError(
            f"Command failed with code {proc.returncode}: {' '.join(command)}\n{proc.stdout}"
        )
    return proc.stdout


def generate_m2(
    parallel_path: Path,
    output_path: Path,
    *,
    bpe: bool,
    cherrant_python: Path,
    command_log: list[dict[str, Any]],
) -> None:
    command = [
        str(cherrant_python),
        "parallel_to_m2.py",
        "-f",
        str(parallel_path),
        "-o",
        str(output_path),
        "-g",
        "char",
        "-s",
        "all",
    ]
    if bpe:
        command.append("--bpe")
    run_command(command, CHERRANT, command_log)


def parse_compare_output(output: str) -> dict[str, int | float]:
    for line in output.splitlines():
        stripped = line.strip()
        if re.match(r"^\d+\s+\d+\s+\d+\s+", stripped):
            fields = stripped.split()
            return {
                "TP": int(fields[0]),
                "FP": int(fields[1]),
                "FN": int(fields[2]),
                "Prec": float(fields[3]),
                "Rec": float(fields[4]),
                "F0.5": float(fields[5]),
            }
    raise ValueError(f"Could not parse ChERRANT output:\n{output}")


def compare_m2(
    hypothesis: Path,
    reference: Path,
    output_path: Path,
    cherrant_python: Path,
    command_log: list[dict[str, Any]],
) -> dict[str, int | float]:
    output = run_command(
        [
            str(cherrant_python),
            "compare_m2_for_evaluation.py",
            "-hyp",
            str(hypothesis),
            "-ref",
            str(reference),
            "--beta",
            "0.5",
        ],
        CHERRANT,
        command_log,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")
    return parse_compare_output(output)


def clean_copy_m2(source: Path, destination: Path) -> None:
    destination.write_text(
        source.read_text(encoding="utf-8-sig").replace("\ufeff", ""),
        encoding="utf-8",
    )


def prepare_hypothesis_m2(
    spec: DatasetSpec,
    rows: list[dict[str, str]],
    round_name: str,
    out_dir: Path,
    *,
    force: bool,
    cherrant_python: Path,
    command_log: list[dict[str, Any]],
) -> tuple[Path, str]:
    para_path = out_dir / f"hypothesis.{round_name}.para"
    m2_path = out_dir / f"hypothesis.{round_name}.char.m2"
    write_hypothesis_para(rows, round_name, para_path)
    expected_targets = simplify_texts(
        (row[round_name] for row in rows), cherrant_python
    )

    if not force and m2_path.exists():
        try:
            validate_hypothesis_m2(
                m2_path, rows, round_name, expected_targets, bpe=spec.bpe
            )
            return m2_path, "existing standardized M2"
        except ValueError:
            pass

    previous = spec.previous_eval_dir / f"{round_name}.char.m2"
    if not force and previous.exists():
        clean_copy_m2(previous, m2_path)
        try:
            validate_hypothesis_m2(
                m2_path, rows, round_name, expected_targets, bpe=spec.bpe
            )
            return m2_path, str(previous.relative_to(ROOT))
        except ValueError:
            m2_path.unlink(missing_ok=True)

    generate_m2(
        para_path,
        m2_path,
        bpe=spec.bpe,
        cherrant_python=cherrant_python,
        command_log=command_log,
    )
    validate_hypothesis_m2(
        m2_path, rows, round_name, expected_targets, bpe=spec.bpe
    )
    return m2_path, "generated from result TSV"


def write_dataset_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "dataset",
        "split",
        "sentences",
        "reference_variant",
        "round",
        "TP",
        "FP",
        "FN",
        "Prec",
        "Rec",
        "F0.5",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def process_dataset(
    spec: DatasetSpec,
    output_root: Path,
    *,
    force_references: bool,
    force_hypotheses: bool,
    cherrant_python: Path,
    m2_workers: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    print(f"[{spec.dataset}] preparing standardized character M2 files", flush=True)
    rows = load_result_rows(spec)
    out_dir = output_root / spec.dataset / spec.split / "char"
    out_dir.mkdir(parents=True, exist_ok=True)
    command_log: list[dict[str, Any]] = []

    generated_parallel = out_dir / "reference.generated.all.para"
    write_cherrant_parallel(para_rows(spec.gold_para), generated_parallel)
    generated_all = out_dir / "reference.generated.all.char.m2"
    regenerate_reference = force_references or not generated_all.exists()
    if not regenerate_reference:
        try:
            validate_generated_reference(
                generated_all, spec.gold_para, cherrant_python, bpe=spec.bpe
            )
        except ValueError:
            regenerate_reference = True
    if regenerate_reference:
        generate_m2(
            generated_parallel,
            generated_all,
            bpe=spec.bpe,
            cherrant_python=cherrant_python,
            command_log=command_log,
        )
    generated_validation = validate_generated_reference(
        generated_all, spec.gold_para, cherrant_python, bpe=spec.bpe
    )
    generated_first3 = out_dir / "reference.generated.first3.char.m2"
    filter_m2_references(generated_all, generated_first3, 3)

    references = {
        "generated_all": generated_all,
        "generated_first3": generated_first3,
    }
    retained_references = dict(references)
    official_all: Path | None = None
    if spec.gold_m2:
        official_all = out_dir / "reference.official.all.char.m2"
        clean_copy_m2(spec.gold_m2, official_all)
        validate_m2_sources(
            official_all,
            (row["source"] for row in rows),
            bpe=spec.official_m2_bpe,
        )
        official_first3 = out_dir / "reference.official.first3.char.m2"
        filter_m2_references(official_all, official_first3, 3)
        retained_references["official_all"] = official_all
        retained_references["official_first3"] = official_first3
        if spec.official_m2_bpe == spec.bpe:
            references["official_all"] = official_all
            references["official_first3"] = official_first3

    hypotheses: dict[str, Path] = {}
    hypothesis_provenance: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(m2_workers, len(ROUNDS))) as executor:
        futures = {
            round_name: executor.submit(
                prepare_hypothesis_m2,
                spec,
                rows,
                round_name,
                out_dir,
                force=force_hypotheses,
                cherrant_python=cherrant_python,
                command_log=command_log,
            )
            for round_name in ROUNDS
        }
        for round_name in ROUNDS:
            hypothesis, source = futures[round_name].result()
            hypotheses[round_name] = hypothesis
            hypothesis_provenance[round_name] = source

    metric_rows: list[dict[str, Any]] = []
    for variant, reference in references.items():
        print(f"[{spec.dataset}] comparing against {variant}", flush=True)
        for round_name, hypothesis in hypotheses.items():
            metrics = compare_m2(
                hypothesis,
                reference,
                out_dir / "comparisons" / variant / f"{round_name}.compare.txt",
                cherrant_python,
                command_log,
            )
            metric_rows.append(
                {
                    "dataset": spec.dataset,
                    "split": spec.split,
                    "sentences": spec.rows,
                    "reference_variant": variant,
                    "round": round_name,
                    **metrics,
                }
            )

    audit: dict[str, Any] = {
        "dataset": spec.dataset,
        "split": spec.split,
        "sentences": spec.rows,
        "character_granularity": True,
        "bpe": spec.bpe,
        "official_m2_bpe": spec.official_m2_bpe,
        "official_m2_scored": "official_all" in references,
        "multi_cheapest_strategy": "all",
        "comparison_beta": 0.5,
        "gold_para": str(spec.gold_para.relative_to(ROOT)),
        "result_tsv": str(spec.result_tsv.relative_to(ROOT)),
        "generated_reference_validation": generated_validation,
        "references": {
            variant: audit_m2(
                path,
                bpe=(spec.official_m2_bpe if variant.startswith("official") else spec.bpe),
            )
            for variant, path in retained_references.items()
        },
        "hypothesis_provenance": hypothesis_provenance,
        "hypotheses": {
            round_name: audit_m2(path, bpe=spec.bpe)
            for round_name, path in hypotheses.items()
        },
        "commands": command_log,
    }
    if official_all:
        audit["official_vs_generated"] = compare_reference_m2(
            official_all,
            generated_all,
            cherrant_python,
            official_bpe=spec.official_m2_bpe,
            generated_bpe=spec.bpe,
        )
        if spec.official_m2_bpe != spec.bpe:
            audit["official_scoring_omitted_reason"] = (
                "official M2 uses BPE coordinates but uniform evaluation uses "
                "character-level non-BPE coordinates"
            )

    write_dataset_summary(out_dir / "summary.tsv", metric_rows)
    (out_dir / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[{spec.dataset}] complete", flush=True)
    return metric_rows, audit


def write_long_summary(output_root: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = list(rows[0])
    with (output_root / "scores.long.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def metric_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {
        (row["dataset"], row["reference_variant"], row["round"]): row
        for row in rows
    }


def write_uniform_scores(
    output_root: Path,
    specs: list[DatasetSpec],
    rows: list[dict[str, Any]],
) -> None:
    indexed = metric_index(rows)
    table_rows: list[dict[str, Any]] = []
    for spec in specs:
        table_rows.append(
            {
                "dataset": spec.dataset,
                "split": spec.split,
                "sentences": spec.rows,
                **{
                    round_name: 100
                    * float(indexed[(spec.dataset, "generated_all", round_name)]["F0.5"])
                    for round_name in ROUNDS
                },
            }
        )
    path = output_root / "scores.uniform.generated_all.tsv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["dataset", "split", "sentences", *ROUNDS],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(table_rows)

    markdown = [
        "# Uniform Character-level ChERRANT Evaluation",
        "",
        "All scores use reference M2 files generated from `gold.para`, all available "
        "textual references, character granularity without BPE, span correction, "
        "beta 0.5, and are multiplied by 100.",
        "",
        "| Dataset | Split | Sentences | T0 | T1 | T2 | T3 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in table_rows:
        markdown.append(
            f"| {row['dataset']} | {row['split']} | {row['sentences']:,} | "
            f"{row['T0']:.2f} | {row['T1']:.2f} | {row['T2']:.2f} | {row['T3']:.2f} |"
        )
    markdown.extend(
        [
            "",
            "The official-M2 and first-three-reference comparisons are retained in "
            "`scores.long.tsv` and each dataset's `comparisons/` directory.",
            "",
        ]
    )
    (output_root / "scores.uniform.generated_all.md").write_text(
        "\n".join(markdown), encoding="utf-8"
    )


def write_scope_deltas(output_root: Path, rows: list[dict[str, Any]]) -> None:
    indexed = metric_index(rows)
    delta_rows: list[dict[str, Any]] = []
    datasets = sorted({row["dataset"] for row in rows})
    for dataset in datasets:
        for origin in ("generated", "official"):
            all_key = f"{origin}_all"
            first3_key = f"{origin}_first3"
            if (dataset, all_key, "T0") not in indexed:
                continue
            for round_name in ROUNDS:
                all_score = 100 * float(indexed[(dataset, all_key, round_name)]["F0.5"])
                first3_score = 100 * float(
                    indexed[(dataset, first3_key, round_name)]["F0.5"]
                )
                delta_rows.append(
                    {
                        "dataset": dataset,
                        "reference_origin": origin,
                        "round": round_name,
                        "all_references_F0.5_x100": round(all_score, 4),
                        "first3_references_F0.5_x100": round(first3_score, 4),
                        "all_minus_first3_x100": round(all_score - first3_score, 4),
                    }
                )
    if not delta_rows:
        return
    with (output_root / "scores.all_vs_first3.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(delta_rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(delta_rows)


def write_preliminary_deltas(
    output_root: Path,
    specs: list[DatasetSpec],
    rows: list[dict[str, Any]],
) -> None:
    indexed = metric_index(rows)
    delta_rows: list[dict[str, Any]] = []
    for spec in specs:
        preliminary_path = spec.previous_eval_dir / "summary.tsv"
        if not preliminary_path.exists():
            continue
        with preliminary_path.open(encoding="utf-8", newline="") as stream:
            preliminary = {
                row["round"]: 100 * float(row["F0.5"])
                for row in csv.DictReader(stream, delimiter="\t")
                if row["round"] in ROUNDS
            }
        for round_name in ROUNDS:
            if round_name not in preliminary:
                continue
            standardized = 100 * float(
                indexed[(spec.dataset, "generated_all", round_name)]["F0.5"]
            )
            delta_rows.append(
                {
                    "dataset": spec.dataset,
                    "round": round_name,
                    "preliminary_F0.5_x100": round(preliminary[round_name], 4),
                    "standardized_F0.5_x100": round(standardized, 4),
                    "standardized_minus_preliminary_x100": round(
                        standardized - preliminary[round_name], 4
                    ),
                }
            )
    if not delta_rows:
        return
    with (output_root / "scores.preliminary_vs_standardized.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(delta_rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(delta_rows)


def write_audit_summary(output_root: Path, audits: list[dict[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for audit in audits:
        generated = audit["references"]["generated_all"]
        comparison = audit.get("official_vs_generated", {})
        rows.append(
            {
                "dataset": audit["dataset"],
                "split": audit["split"],
                "sentences": audit["sentences"],
                "generated_total_references": generated["total_references"],
                "generated_max_references": generated["max_references"],
                "sentences_over_3_references": generated[
                    "sentences_with_more_than_3_references"
                ],
                "generated_extra_alignment_target_lines": generated[
                    "extra_alignment_target_lines"
                ],
                "official_m2_available": "official_all" in audit["references"],
                "official_m2_bpe": audit["official_m2_bpe"],
                "official_m2_scored": audit["official_m2_scored"],
                "official_generated_matching_sources": comparison.get("matching_sources", ""),
                "official_generated_matching_reference_counts": comparison.get(
                    "matching_reference_counts", ""
                ),
                "official_generated_matching_target_sets": comparison.get(
                    "matching_target_sets", ""
                ),
                "official_generated_matching_target_sets_after_t2s": comparison.get(
                    "matching_target_sets_after_t2s", ""
                ),
            }
        )
    with (output_root / "m2_audit.summary.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    specs = load_specs()
    choices = [spec.dataset for spec in specs]
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", nargs="+", choices=choices, default=choices)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cherrant-python", type=Path)
    parser.add_argument("--m2-workers", type=int, default=4)
    parser.add_argument("--force-references", action="store_true")
    parser.add_argument("--force-hypotheses", action="store_true")
    args = parser.parse_args()
    if args.m2_workers < 1:
        parser.error("--m2-workers must be at least 1")

    args.output_root = args.output_root.resolve()
    selected = [spec for spec in specs if spec.dataset in args.datasets]
    cherrant_python = args.cherrant_python or discover_cherrant_python()
    print(f"ChERRANT Python: {cherrant_python}", flush=True)
    args.output_root.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    for spec in selected:
        metric_rows, audit = process_dataset(
            spec,
            args.output_root,
            force_references=args.force_references,
            force_hypotheses=args.force_hypotheses,
            cherrant_python=cherrant_python,
            m2_workers=args.m2_workers,
        )
        all_rows.extend(metric_rows)
        audits.append(audit)

    write_long_summary(args.output_root, all_rows)
    write_uniform_scores(args.output_root, selected, all_rows)
    write_scope_deltas(args.output_root, all_rows)
    write_preliminary_deltas(args.output_root, selected, all_rows)
    write_audit_summary(args.output_root, audits)
    (args.output_root / "run_config.json").write_text(
        json.dumps(
            {
                "completed_utc": datetime.now(timezone.utc).isoformat(),
                "datasets": [spec.dataset for spec in selected],
                "rounds": list(ROUNDS),
                "granularity": "char",
                "bpe": False,
                "multi_cheapest_strategy": "all",
                "beta": 0.5,
                "uniform_score_reference": "generated_all",
                "driver_python": sys.executable,
                "cherrant_python": str(cherrant_python),
                "m2_workers": args.m2_workers,
                "cherrant_dir": str(CHERRANT.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(args.output_root / "scores.uniform.generated_all.md")


if __name__ == "__main__":
    main()
