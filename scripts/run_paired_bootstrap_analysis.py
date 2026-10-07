#!/usr/bin/env python3
"""Build dataset/model tables and paired-bootstrap analysis artifacts.

Without --model-config, reuse the historical DeepSeek and Kimi T0--T3 runs
with condition-specific word GLEU. --word-gleu-source-policy fixed-gold
explicitly reproduces the archived fixed-source analysis. With --model-config,
analyze only the declared saved runs; --output must point outside the historical
analysis directory. No model API is called.

The config is one ModelSpec JSON object or a nonempty list of them. Required
string fields are key, display, identifier, provider, access_date, temperature,
top_p, max_output, and thinking (the declared reasoning setting, not a boolean).
Required paths are char_root, word_root, char_gleu, and word_gleu. run_names is
either a dataset-to-run-stem object or a path to such a JSON object. raw_root
optionally locates the run-stem TSV/JSONL files (default: runs). Relative paths
inside the config, including a run_names file, are repository-relative.
cached_selector_policy is "sentence" by default for custom configs, or "corpus"
for a historical cache. The built-in historical models retain "corpus".
Both selectors are audited; all inferential edit counts remain sentence-local.
One saved sample and stages T0--T3 (Kmax=3) are required for every model.
word_gleu_source_policy defaults to "condition": T0/T1 source=S1, T2=S2,
T3=S3, using saved word boundaries. Set "fixed-gold" explicitly to reproduce
historical fixed-source scores. Completed run_config.json policy metadata,
sentence/summary policy labels, and exported source inputs are validated.
Identifiable legacy fixed-source metadata is accepted only for "fixed-gold".
The CLI policy option controls built-in models only; custom configs declare
their policies per model. Existing analysis directories cannot be reused for
a different declared word-GLEU policy.

For GPT-6, use key gpt6, identifier gpt-6-astra, and paths beneath
runs/gpt_6_astra_copilot_default: projection_character_m2, projection_word_m2,
character_gleu/sentence_scores.tsv, word_gleu_condition/sentence_scores.tsv, and
run_names.json. Record provider-default decoding/reasoning settings as such,
not as disabled thinking or inferred numeric defaults. Write its analysis to
runs/gpt_6_astra_copilot_default/paired_analysis. Word M2, independently of word
GLEU, still uses runs/gold_fixed_source_segmentation. Word-GLEU hypotheses/references
remain LTP; character GLEU and both M2 metrics are unchanged. This script does
not retokenize GLEU inputs. Built-in condition analyses default to
runs/paired_bootstrap_analysis_condition; explicit fixed-gold reproduction
defaults to the original runs/paired_bootstrap_analysis.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict, dataclass, field, fields
import hashlib
import json
import math
from pathlib import Path
import platform
from typing import Any, Iterable, Sequence

import numpy as np
from scipy.stats import norm

try:
    from movement_aware_compare import M2Block, evaluate, f_score, parse_file, split_blocks
    from projection_character_m2 import targets_from_m2_block
    from projection_word_m2 import targets_from_word_m2_block
    from standardize_m2_evaluation import RUN_NAMES as DEEPSEEK_RUN_NAMES
    from word_gleu_protocol import (
        CONDITION_SOURCE_COLUMNS,
        SOURCE_POLICIES,
        load_source_policy,
        select_source_segmentation,
        source_policy_from_config,
    )
except ModuleNotFoundError:
    from scripts.movement_aware_compare import (
        M2Block,
        evaluate,
        f_score,
        parse_file,
        split_blocks,
    )
    from scripts.projection_character_m2 import targets_from_m2_block
    from scripts.projection_word_m2 import targets_from_word_m2_block
    from scripts.standardize_m2_evaluation import RUN_NAMES as DEEPSEEK_RUN_NAMES
    from scripts.word_gleu_protocol import (
        CONDITION_SOURCE_COLUMNS,
        SOURCE_POLICIES,
        load_source_policy,
        select_source_segmentation,
        source_policy_from_config,
    )


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/benchmarks/prepared/manifest.json"
HISTORICAL_OUTPUT = ROOT / "runs/paired_bootstrap_analysis"
DEFAULT_OUTPUT = ROOT / "runs/paired_bootstrap_analysis_condition"
STAGES = ("T0", "T1", "T2", "T3")
CONDITIONS = ("R", "D", "P", "I")
STAGE_TO_CONDITION = dict(zip(STAGES, CONDITIONS))
CONTRASTS = (
    ("D-R", "R", "D"),
    ("P-D", "D", "P"),
    ("I-P", "P", "I"),
)
INFERENTIAL_DATASETS = {
    "nlpcc2018",
    "mucgec",
    "yaclc",
    "flacgec",
    "fcgec",
    "nacgec",
    "nasgec_exam",
}
DISPLAY_NAMES = {
    "nlpcc2018": "NLPCC2018",
    "mucgec": "MuCGEC",
    "yaclc": "YACLC",
    "flacgec": "FlaCGEC",
    "fcgec": "FCGEC",
    "nacgec": "NaCGEC",
    "nasgec_exam": "NaSGEC-Exam",
    "cefe_track3": "CEFE Track 3",
}
PRIMARY_MARGIN = 0.50
SENSITIVITY_MARGINS = (0.25, 0.50, 1.00)
EXPECTED_DATASET_TOTALS = {
    "sentences": 20213,
    "references": 38000,
    "multi_reference_sentences": 7704,
    "sentences_over_3_references": 1613,
    "max_references": 11,
}


@dataclass(frozen=True)
class DatasetSpec:
    dataset: str
    split: str
    rows: int
    gold_para: Path


@dataclass(frozen=True)
class ModelSpec:
    key: str
    display: str
    identifier: str
    provider: str
    access_date: str
    temperature: str
    top_p: str
    max_output: str
    thinking: str
    run_names: dict[str, str]
    char_root: Path
    word_root: Path
    char_gleu: Path
    word_gleu: Path
    cached_selector_policy: str = "corpus"
    raw_root: Path = ROOT / "runs"
    word_gleu_source_policy: str = "condition"

    def __post_init__(self) -> None:
        if self.cached_selector_policy not in {"corpus", "sentence"}:
            raise ValueError(
                f"{self.key}: cached_selector_policy must be 'corpus' or 'sentence'"
            )
        if self.word_gleu_source_policy not in SOURCE_POLICIES:
            raise ValueError(
                f"{self.key}: word_gleu_source_policy must be 'condition' or 'fixed-gold'"
            )


@dataclass(frozen=True)
class WordGleuMetadata:
    policy: str
    legacy_fixed: bool
    completion_evidence: str
    config_path: Path


@dataclass
class BlockData:
    model: ModelSpec
    dataset: DatasetSpec
    source_ids: list[str]
    sources: list[str]
    outputs: dict[str, list[str]]
    boundaries: dict[str, list[str]]
    fixed_boundaries: list[str]
    char_counts: np.ndarray
    word_counts: np.ndarray
    char_selected: np.ndarray
    word_selected: np.ndarray
    char_gleu: np.ndarray
    word_gleu: np.ndarray
    char_gleu_selected: np.ndarray
    word_gleu_selected: np.ndarray
    reference_counts: np.ndarray
    call_counts: np.ndarray
    prompt_tokens: np.ndarray
    completion_tokens: np.ndarray
    total_tokens: np.ndarray
    format_retries: np.ndarray
    filter_fallbacks: np.ndarray
    reference_blocks: list[M2Block]
    legacy_scores: dict[str, dict[str, float]]
    validated_reference_blocks: int
    validated_references: int
    word_gleu_sources: dict[str, list[str]] = field(default_factory=dict)
    word_gleu_source_audit: list[dict[str, Any]] = field(default_factory=list)


def normalize_text(value: str) -> str:
    return "".join((value or "").replace("\ufeff", "").split())


def stable_seed(base_seed: int, *parts: str) -> int:
    digest = hashlib.sha256(":".join((str(base_seed), *parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_rows(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    delimiter = "\t" if path.suffix == ".tsv" else ","
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
            delimiter=delimiter,
        )
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def load_datasets() -> list[DatasetSpec]:
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [
        DatasetSpec(
            dataset=record["dataset"],
            split=record["split"],
            rows=int(record["rows"]),
            gold_para=ROOT / record["gold_para"],
        )
        for record in records
    ]


def config_path(value: Any, *, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty path string")
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_model_config(path: Path) -> list[ModelSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = [payload] if isinstance(payload, dict) else payload
    if not isinstance(records, list) or not records:
        raise ValueError("Model config must be a model object or a nonempty list of model objects")
    required = {
        "key", "display", "identifier", "provider", "access_date", "temperature",
        "top_p", "max_output", "thinking", "run_names", "char_root", "word_root",
        "char_gleu", "word_gleu",
    }
    allowed = {field.name for field in fields(ModelSpec)}
    path_fields = {"char_root", "word_root", "char_gleu", "word_gleu", "raw_root"}
    models: list[ModelSpec] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"Model config entry {index} must be an object")
        missing, unknown = required - set(record), set(record) - allowed
        if missing or unknown:
            raise ValueError(
                f"Model config entry {index}: missing={sorted(missing)}, unknown={sorted(unknown)}"
            )
        values = dict(record)
        values.setdefault("cached_selector_policy", "sentence")
        values.setdefault("word_gleu_source_policy", "condition")
        values.setdefault("raw_root", "runs")
        for name, value in values.items():
            if name not in path_fields | {"run_names"} and (
                not isinstance(value, str) or not value.strip()
            ):
                raise ValueError(f"Model config entry {index}: {name} must be a nonempty string")
        for name in path_fields:
            values[name] = config_path(values[name], field=name)
        run_names = values["run_names"]
        if isinstance(run_names, str):
            run_names = json.loads(
                config_path(run_names, field="run_names").read_text(encoding="utf-8")
            )
        if not isinstance(run_names, dict) or not run_names or any(
            not isinstance(key, str) or not key.strip()
            or not isinstance(value, str) or not value.strip()
            for key, value in run_names.items()
        ):
            raise ValueError("run_names must be a nonempty dataset-to-run-stem JSON object")
        values["run_names"] = dict(run_names)
        models.append(ModelSpec(**values))
    if len({model.key for model in models}) != len(models):
        raise ValueError("Model config contains duplicate model keys")
    if len({model.display for model in models}) != len(models):
        raise ValueError("Model config contains duplicate model display names")
    return models


def load_models(
    model_config: Path | None = None,
    *,
    word_gleu_source_policy: str | None = None,
) -> list[ModelSpec]:
    if model_config is not None:
        if word_gleu_source_policy is not None:
            raise ValueError("Declare word_gleu_source_policy in the model config, not with the CLI policy option")
        return load_model_config(model_config)
    policy = word_gleu_source_policy or "condition"
    if policy not in SOURCE_POLICIES:
        raise ValueError(f"Unknown word-GLEU source policy: {policy}")
    kimi_names = json.loads((ROOT / "runs/kimi_k2_6/run_names.json").read_text())
    return [
        ModelSpec(
            key="deepseek",
            display="DeepSeek",
            identifier="deepseek-v4-pro",
            provider="DeepSeek",
            access_date="2026-07-16 to 2026-07-19",
            temperature="0.000001",
            top_p="provider default",
            max_output="8,192 tokens (provider default; omitted)",
            thinking="disabled",
            run_names=dict(DEEPSEEK_RUN_NAMES),
            char_root=ROOT / "runs/projection_character_m2_eval_final",
            word_root=ROOT / "runs/projection_word_m2_eval_final",
            char_gleu=ROOT / "runs/character_gleu_select_best/sentence_scores.tsv",
            word_gleu=ROOT / (
                "runs/word_gleu_condition_select_best/sentence_scores.tsv"
                if policy == "condition" else "runs/word_gleu_select_best_final/sentence_scores.tsv"
            ),
            word_gleu_source_policy=policy,
        ),
        ModelSpec(
            key="kimi",
            display="Kimi",
            identifier="kimi-k2.6",
            provider="Moonshot AI",
            access_date="2026-08-30 to 2026-08-31",
            temperature="0.6 (provider-fixed, non-thinking)",
            top_p="provider default",
            max_output="512 tokens",
            thinking="disabled",
            run_names=kimi_names,
            char_root=ROOT / "runs/kimi_k2_6/projection_character_m2",
            word_root=ROOT / "runs/kimi_k2_6/projection_word_m2",
            char_gleu=ROOT / "runs/kimi_k2_6/character_gleu/sentence_scores.tsv",
            word_gleu=ROOT / (
                "runs/kimi_k2_6/word_gleu_condition/sentence_scores.tsv"
                if policy == "condition" else "runs/kimi_k2_6/word_gleu/sentence_scores.tsv"
            ),
            word_gleu_source_policy=policy,
        ),
    ]


def read_gold_para(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle, delimiter="\t"))


def validate_reference_m2(
    path: Path,
    *,
    unit: str,
    gold_records: Sequence[Sequence[str]],
) -> tuple[int, int]:
    """Verify that serialized M2 keeps every complete gold reference in order."""

    blocks = split_blocks(path)
    if len(blocks) != len(gold_records):
        raise ValueError(
            f"{path}: expected {len(gold_records)} reference blocks, found {len(blocks)}"
        )
    reference_count = 0
    for row_index, (block, gold) in enumerate(zip(blocks, gold_records)):
        expected_source = normalize_text(gold[1])
        expected_targets = [normalize_text(target) for target in gold[2:]]
        if unit == "character":
            source, targets = targets_from_m2_block(block)
            reconstructed = [normalize_text(targets[index]) for index in sorted(targets)]
        elif unit == "word":
            source_tokens, targets = targets_from_word_m2_block(block)
            source = "".join(source_tokens)
            reconstructed = [
                normalize_text("".join(targets[index])) for index in sorted(targets)
            ]
        else:
            raise ValueError(f"Unsupported reference-M2 unit: {unit}")
        if normalize_text(source) != expected_source:
            raise ValueError(f"{path}: source mismatch at row {row_index}")
        if sorted(targets) != list(range(len(expected_targets))):
            raise ValueError(f"{path}: reference IDs mismatch at row {row_index}")
        if reconstructed != expected_targets:
            raise ValueError(f"{path}: gold reference text/order mismatch at row {row_index}")
        reference_count += len(reconstructed)
    return len(blocks), reference_count


def build_dataset_statistics(specs: Sequence[DatasetSpec]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for spec in specs:
        records = read_gold_para(spec.gold_para)
        if len(records) != spec.rows:
            raise ValueError(f"{spec.dataset}: expected {spec.rows} gold rows, found {len(records)}")
        counts = [len(record) - 2 for record in records]
        if any(count < 1 for count in counts):
            raise ValueError(f"{spec.dataset}: a gold row has no reference")
        result.append(
            {
                "dataset": DISPLAY_NAMES[spec.dataset],
                "dataset_key": spec.dataset,
                "split": spec.split,
                "sentences": len(records),
                "references": sum(counts),
                "multi_reference_sentences": sum(count > 1 for count in counts),
                "sentences_over_3_references": sum(count > 3 for count in counts),
                "max_references": max(counts),
            }
        )
    return result


def load_gleu(path: Path, datasets: Sequence[DatasetSpec]) -> dict[tuple[str, str], list[dict[str, str]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in read_tsv(path):
        grouped.setdefault((row["dataset"], row["stage"]), []).append(row)
    expected = {(spec.dataset, stage) for spec in datasets for stage in STAGES}
    if set(grouped) != expected:
        missing = sorted(expected - set(grouped))
        extra = sorted(set(grouped) - expected)
        raise ValueError(f"GLEU coverage mismatch in {path}: missing={missing}, extra={extra}")
    return grouped


def validate_word_gleu_metadata(model: ModelSpec) -> WordGleuMetadata:
    path = model.word_gleu.parent / "run_config.json"
    if not path.is_file():
        raise ValueError(f"{model.key}: missing word-GLEU policy metadata: {path}")
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"{path}: word-GLEU run config must be an object")
    policy = source_policy_from_config(config)
    completed_utc = config.get("completed_utc")
    legacy_fixed = (
        "source_segmentation_policy" not in config
        and "status" not in config
    )
    if legacy_fixed:
        if not isinstance(completed_utc, str) or not completed_utc.strip():
            raise ValueError(f"{path}: legacy word-GLEU run is not completed")
        completion_evidence = f"legacy completed_utc={completed_utc}"
    else:
        if config.get("source_segmentation_policy") != policy:
            raise ValueError(f"{path}: missing explicit word-GLEU source policy in new-format metadata")
        if config.get("status") is None:
            raise ValueError(f"{path}: word-GLEU run is not completed")
        completion_evidence = "status=completed"
    confirmed_policy = load_source_policy(
        model.word_gleu.parent,
        expected_policy=model.word_gleu_source_policy,
        require_completed=True,
    )
    if policy != confirmed_policy:
        raise ValueError(f"{path}: word-GLEU policy metadata changed during validation")
    if policy == "fixed-gold" and config.get("source_stage_mapping") is not None:
        raise ValueError(f"{path}: fixed-gold word GLEU must not declare condition source stages")
    return WordGleuMetadata(policy, legacy_fixed, completion_evidence, path)


def validate_word_gleu_row_policy(
    row: dict[str, str], metadata: WordGleuMetadata, *, path: Path
) -> None:
    if metadata.legacy_fixed and "source_segmentation_policy" not in row:
        return
    if row.get("source_segmentation_policy") != metadata.policy:
        raise ValueError(
            f"{path}: word-GLEU row policy mismatch at "
            f"{row.get('dataset')}/{row.get('stage')}/{row.get('id', 'summary')}: "
            f"{row.get('source_segmentation_policy')!r} != {metadata.policy!r}"
        )


def validate_word_gleu_sources(
    model: ModelSpec,
    dataset: DatasetSpec,
    raw_rows: Sequence[dict[str, str]],
    fixed_boundaries: Sequence[str],
    grouped: dict[tuple[str, str], list[dict[str, str]]],
) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    metadata = validate_word_gleu_metadata(model)
    sources: dict[str, list[str]] = {}
    audit: list[dict[str, Any]] = []
    for stage in STAGES:
        rows = grouped.get((dataset.dataset, stage), [])
        if len(rows) != dataset.rows:
            raise ValueError(f"{model.key}/{dataset.dataset}/{stage}: word-GLEU row count mismatch")
        for row in rows:
            validate_word_gleu_row_policy(row, metadata, path=model.word_gleu)
        path = (
            model.word_gleu.parent / dataset.dataset / dataset.split
            / "inputs" / f"source.{stage}.txt"
        )
        if not path.is_file():
            raise ValueError(f"Missing word-GLEU source inputs: {path}")
        contents = path.read_bytes()
        lines = contents.decode("utf-8-sig").splitlines()
        if len(lines) != dataset.rows:
            raise ValueError(f"{path}: word-GLEU source-input row count mismatch")
        normalized = [" ".join(line.replace("\ufeff", "").split()) for line in lines]
        for index, (row, fixed, observed) in enumerate(zip(raw_rows, fixed_boundaries, normalized)):
            expected = select_source_segmentation(
                row, stage, source_policy=metadata.policy, fixed_source=fixed
            )
            if observed != expected:
                raise ValueError(
                    f"{path}: word-GLEU source boundaries mismatch at row {index}; "
                    f"expected {CONDITION_SOURCE_COLUMNS[stage] if metadata.policy == 'condition' else 'fixed-gold'}"
                )
        sources[stage] = normalized
        audit.append(
            {
                "model": model.display,
                "model_key": model.key,
                "dataset": DISPLAY_NAMES[dataset.dataset],
                "dataset_key": dataset.dataset,
                "split": dataset.split,
                "stage": stage,
                "condition": STAGE_TO_CONDITION[stage],
                "source_segmentation_policy": metadata.policy,
                "source_stage": CONDITION_SOURCE_COLUMNS[stage] if metadata.policy == "condition" else "fixed-gold",
                "hypothesis_and_reference_segmentation": "LTP",
                "metadata_format": "legacy-fixed" if metadata.legacy_fixed else "explicit-policy",
                "policy_labeled_sentences": sum("source_segmentation_policy" in row for row in rows),
                "legacy_unlabeled_sentences": sum("source_segmentation_policy" not in row for row in rows),
                "completion_evidence": metadata.completion_evidence,
                "run_config": str(metadata.config_path),
                "sentence_scores": str(model.word_gleu),
                "source_inputs": str(path),
                "source_inputs_sha256": hashlib.sha256(contents).hexdigest(),
                "validated_sentences": len(normalized),
                "source_boundaries_match_saved": True,
            }
        )
    return sources, audit


def cached_m2_scores(model: ModelSpec, unit: str) -> dict[tuple[str, str], float]:
    root = model.char_root if unit == "character" else model.word_root
    values: dict[tuple[str, str], float] = {}
    for row in read_tsv(root / "scores.long.tsv"):
        if row["round"] not in STAGES or float(row["beta"]) != 0.5:
            continue
        if unit == "character" and row.get("alignment") != "projection":
            continue
        values[(row["dataset"], row["round"])] = float(row["F_beta"]) * 100.0
    return values


def validate_gleu_summary(model: ModelSpec, unit: str, grouped: dict[tuple[str, str], list[dict[str, str]]]) -> None:
    score_path = (model.char_gleu if unit == "character" else model.word_gleu).parent / "scores.long.tsv"
    summaries = read_tsv(score_path)
    if unit == "word":
        metadata = validate_word_gleu_metadata(model)
        for row in summaries:
            validate_word_gleu_row_policy(row, metadata, path=score_path)
    expected = {
        (row["dataset"], row["stage"]): float(row["gleu_select_best_x100"])
        for row in summaries
    }
    for key, rows in grouped.items():
        observed = float(np.mean([float(row["gleu_select_best"]) for row in rows]) * 100.0)
        if key not in expected or not math.isclose(observed, expected[key], abs_tol=1e-6):
            raise ValueError(
                f"{model.key}/{unit} GLEU summary mismatch for {key}: "
                f"sentence mean={observed}, cached={expected.get(key)}"
            )


def parse_api_metadata(records: Sequence[dict[str, Any]]) -> tuple[np.ndarray, ...]:
    n = len(records)
    shape = (n, len(STAGES))
    calls = np.zeros(shape, dtype=np.int64)
    prompt = np.zeros(shape, dtype=np.int64)
    completion = np.zeros(shape, dtype=np.int64)
    total = np.zeros(shape, dtype=np.int64)
    retries = np.zeros(shape, dtype=np.int64)
    fallbacks = np.zeros(shape, dtype=np.int64)
    for row_index, record in enumerate(records):
        for api in record.get("meta", {}).get("api", []):
            stage_index = int(api["T"])
            if not 0 <= stage_index < len(STAGES):
                continue
            calls[row_index, stage_index] += 1
            usage = api.get("usage") or {}
            prompt[row_index, stage_index] += int(usage.get("prompt_tokens") or 0)
            completion[row_index, stage_index] += int(usage.get("completion_tokens") or 0)
            total[row_index, stage_index] += int(usage.get("total_tokens") or 0)
            retries[row_index, stage_index] += int(api.get("format_retries") or 0)
            fallbacks[row_index, stage_index] += int(bool(api.get("content_filter_fallback")))
    return calls, prompt, completion, total, retries, fallbacks


def load_raw_records(model: ModelSpec, dataset: DatasetSpec) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    run_name = model.run_names[dataset.dataset]
    tsv_path = model.raw_root / f"{run_name}.tsv"
    jsonl_path = model.raw_root / f"{run_name}.jsonl"
    rows = read_tsv(tsv_path)
    records = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) != dataset.rows or len(records) != dataset.rows:
        raise ValueError(
            f"{model.key}/{dataset.dataset}: expected {dataset.rows} raw rows, "
            f"found TSV={len(rows)}, JSONL={len(records)}"
        )
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError(f"{model.key}/{dataset.dataset}: duplicate source IDs")
    for index, (row, record) in enumerate(zip(rows, records)):
        if str(row["id"]) != str(record["id"]):
            raise ValueError(f"{model.key}/{dataset.dataset}: ID mismatch at row {index}")
        if normalize_text(row["source"]) != normalize_text(record["source"]):
            raise ValueError(f"{model.key}/{dataset.dataset}: source mismatch at row {index}")
        for stage in STAGES:
            if normalize_text(row[stage]) != normalize_text(record[stage]):
                raise ValueError(f"{model.key}/{dataset.dataset}: {stage} mismatch at row {index}")
    return rows, records


def m2_paths(model: ModelSpec, dataset: DatasetSpec, stage: str, unit: str) -> tuple[Path, Path]:
    base = (model.char_root if unit == "character" else model.word_root) / dataset.dataset / dataset.split
    leaf = base / ("char" if unit == "character" else "word")
    if unit == "character":
        reference = leaf / "reference.projection.all.char.m2"
        hypothesis = leaf / f"hypothesis.{stage}.projection.char.m2"
    else:
        reference = leaf / f"reference.{stage}.projection.word.m2"
        hypothesis = leaf / f"hypothesis.{stage}.projection.word.m2"
    return hypothesis, reference


def evaluate_stage(
    hypothesis_path: Path,
    reference_path: Path,
    *,
    unit: str,
) -> tuple[np.ndarray, np.ndarray, float, float, list[M2Block]]:
    hypothesis = parse_file(hypothesis_path, unit=unit)
    reference = parse_file(reference_path, unit=unit)
    sentence_counts, _categories, selections = evaluate(
        hypothesis, reference, beta=0.5, selection_mode="sentence"
    )
    legacy_counts, _legacy_categories, _legacy_selections = evaluate(
        hypothesis, reference, beta=0.5, selection_mode="corpus"
    )
    per_sentence = np.asarray(
        [[row["TP"], row["FP"], row["FN"]] for row in selections], dtype=np.int64
    )
    selected = np.asarray([row["reference"] for row in selections], dtype=np.int64)
    score = f_score(
        sentence_counts["tp"], sentence_counts["fp"], sentence_counts["fn"], 0.5
    )[2] * 100
    legacy_score = f_score(
        legacy_counts["tp"], legacy_counts["fp"], legacy_counts["fn"], 0.5
    )[2] * 100
    return per_sentence, selected, score, legacy_score, reference


def load_fixed_boundaries(dataset: DatasetSpec) -> list[str]:
    path = (
        ROOT
        / "runs/gold_fixed_source_segmentation"
        / dataset.dataset
        / dataset.split
        / "fixed_source_segmentation.tsv"
    )
    rows = read_tsv(path)
    if len(rows) != dataset.rows:
        raise ValueError(f"{dataset.dataset}: fixed-boundary row count mismatch")
    return [row["fixed_source_segmentation"] for row in rows]


def load_block(
    model: ModelSpec,
    dataset: DatasetSpec,
    char_gleu_rows: dict[tuple[str, str], list[dict[str, str]]],
    word_gleu_rows: dict[tuple[str, str], list[dict[str, str]]],
) -> tuple[BlockData, list[dict[str, Any]]]:
    raw_rows, json_records = load_raw_records(model, dataset)
    gold_records = read_gold_para(dataset.gold_para)
    fixed_boundaries = load_fixed_boundaries(dataset)
    word_gleu_sources, word_gleu_source_audit = validate_word_gleu_sources(
        model, dataset, raw_rows, fixed_boundaries, word_gleu_rows
    )
    fixed_tokens = [
        tuple(value.replace("\ufeff", "").split()) for value in fixed_boundaries
    ]
    n = dataset.rows
    char_counts = np.zeros((n, 4, 3), dtype=np.int64)
    word_counts = np.zeros((n, 4, 3), dtype=np.int64)
    char_selected = np.zeros((n, 4), dtype=np.int64)
    word_selected = np.zeros((n, 4), dtype=np.int64)
    legacy_scores: dict[str, dict[str, float]] = {"character": {}, "word": {}}
    cached_scores = {
        "character": cached_m2_scores(model, "character"),
        "word": cached_m2_scores(model, "word"),
    }
    reference_blocks: list[M2Block] | None = None
    validated_reference_paths: set[Path] = set()
    validated_reference_blocks = 0
    validated_references = 0
    score_audit: list[dict[str, Any]] = []
    for stage_index, stage in enumerate(STAGES):
        for unit, counts_store, selected_store in (
            ("character", char_counts, char_selected),
            ("word", word_counts, word_selected),
        ):
            hypothesis_path, reference_path = m2_paths(model, dataset, stage, unit)
            if reference_path not in validated_reference_paths:
                block_count, reference_count = validate_reference_m2(
                    reference_path,
                    unit=unit,
                    gold_records=gold_records,
                )
                validated_reference_blocks += block_count
                validated_references += reference_count
                validated_reference_paths.add(reference_path)
            counts, selected, corrected, legacy, references = evaluate_stage(
                hypothesis_path, reference_path, unit=unit
            )
            if counts.shape != (n, 3):
                raise ValueError(f"{model.key}/{dataset.dataset}/{stage}/{unit}: count shape mismatch")
            if unit == "word":
                for index, reference in enumerate(references):
                    if reference.source_units != fixed_tokens[index]:
                        raise ValueError(
                            f"{model.key}/{dataset.dataset}/{stage}: word M2 source segmentation "
                            f"does not match shared fixed-gold boundaries at row {index}"
                        )
            counts_store[:, stage_index, :] = counts
            selected_store[:, stage_index] = selected
            legacy_scores[unit][stage] = legacy
            cached = cached_scores[unit].get((dataset.dataset, stage))
            legacy_matches = cached is not None and math.isclose(legacy, cached, abs_tol=0.0051)
            sentence_matches = cached is not None and math.isclose(corrected, cached, abs_tol=0.0051)
            configured_score, configured_matches = (
                (legacy, legacy_matches)
                if model.cached_selector_policy == "corpus"
                else (corrected, sentence_matches)
            )
            if not configured_matches:
                raise ValueError(
                    f"{model.key}/{dataset.dataset}/{stage}/{unit}: "
                    f"{model.cached_selector_policy} selector score {configured_score} "
                    f"does not reproduce cached score {cached}"
                )
            if unit == "character" and reference_blocks is None:
                reference_blocks = references
            score_audit.append(
                {
                    "model": model.display,
                    "dataset": DISPLAY_NAMES[dataset.dataset],
                    "dataset_key": dataset.dataset,
                    "split": dataset.split,
                    "stage": stage,
                    "unit": unit,
                    "legacy_corpus_greedy_f05": legacy,
                    "cached_table_f05": cached,
                    "legacy_reproduces_cached": legacy_matches,
                    "sentence_local_f05": corrected,
                    "delta_sentence_minus_legacy": corrected - legacy,
                    "cached_selector_policy": model.cached_selector_policy,
                    "configured_selector_reproduces_cached": configured_matches,
                    "sentence_local_reproduces_cached": sentence_matches,
                }
            )
    if reference_blocks is None:
        raise AssertionError("character references were not loaded")

    def gleu_arrays(
        grouped: dict[tuple[str, str], list[dict[str, str]]]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        values = np.zeros((n, 4), dtype=np.float64)
        selected = np.zeros((n, 4), dtype=np.int64)
        reference_counts = np.zeros((n, 4), dtype=np.int64)
        expected_ids = [record[0] for record in gold_records]
        for stage_index, stage in enumerate(STAGES):
            rows = grouped[(dataset.dataset, stage)]
            if len(rows) != n:
                raise ValueError(f"{model.key}/{dataset.dataset}/{stage}: GLEU row count mismatch")
            if [row["id"] for row in rows] != expected_ids:
                raise ValueError(f"{model.key}/{dataset.dataset}/{stage}: GLEU ID/order mismatch")
            values[:, stage_index] = [float(row["gleu_select_best"]) for row in rows]
            selected[:, stage_index] = [int(row["selected_reference"]) for row in rows]
            reference_counts[:, stage_index] = [int(row["reference_count"]) for row in rows]
            if np.any(selected[:, stage_index] < 0) or np.any(
                selected[:, stage_index] >= reference_counts[:, stage_index]
            ):
                raise ValueError(f"{model.key}/{dataset.dataset}/{stage}: invalid selected GLEU reference")
        return values, selected, reference_counts

    char_gleu, char_gleu_selected, char_reference_counts = gleu_arrays(char_gleu_rows)
    word_gleu, word_gleu_selected, word_reference_counts = gleu_arrays(word_gleu_rows)
    if not np.array_equal(char_reference_counts, word_reference_counts):
        raise ValueError(f"{model.key}/{dataset.dataset}: character/word reference counts differ")
    if not np.all(char_reference_counts == char_reference_counts[:, [0]]):
        raise ValueError(f"{model.key}/{dataset.dataset}: reference counts differ by stage")
    call_data = parse_api_metadata(json_records)
    outputs = {stage: [normalize_text(row[stage]) for row in raw_rows] for stage in STAGES}
    boundaries = {
        "R": [normalize_text(row["source"]) for row in raw_rows],
        "D": [row["S1"] for row in raw_rows],
        "P": [row["S2"] for row in raw_rows],
        "I": [row["S3"] for row in raw_rows],
    }
    sources = [normalize_text(row["source"]) for row in raw_rows]
    for index, source in enumerate(sources):
        if "".join(reference_blocks[index].source_units) != source:
            raise ValueError(f"{model.key}/{dataset.dataset}: M2 source mismatch at row {index}")
        for condition in ("D", "P", "I"):
            if normalize_text(boundaries[condition][index]) != source:
                raise ValueError(
                    f"{model.key}/{dataset.dataset}: {condition} boundaries alter source at row {index}"
                )
        if normalize_text(fixed_boundaries[index]) != source:
            raise ValueError(f"{model.key}/{dataset.dataset}: fixed segmentation source mismatch at row {index}")
    return (
        BlockData(
            model=model,
            dataset=dataset,
            source_ids=[row["id"] for row in raw_rows],
            sources=sources,
            outputs=outputs,
            boundaries=boundaries,
            fixed_boundaries=fixed_boundaries,
            char_counts=char_counts,
            word_counts=word_counts,
            char_selected=char_selected,
            word_selected=word_selected,
            char_gleu=char_gleu,
            word_gleu=word_gleu,
            char_gleu_selected=char_gleu_selected,
            word_gleu_selected=word_gleu_selected,
            reference_counts=char_reference_counts[:, 0],
            call_counts=call_data[0],
            prompt_tokens=call_data[1],
            completion_tokens=call_data[2],
            total_tokens=call_data[3],
            format_retries=call_data[4],
            filter_fallbacks=call_data[5],
            reference_blocks=reference_blocks,
            legacy_scores=legacy_scores,
            validated_reference_blocks=validated_reference_blocks,
            validated_references=validated_references,
            word_gleu_sources=word_gleu_sources,
            word_gleu_source_audit=word_gleu_source_audit,
        ),
        score_audit,
    )


def micro_f05(counts: np.ndarray) -> np.ndarray:
    values = np.asarray(counts, dtype=np.float64)
    numerator = 1.25 * values[..., 0]
    denominator = numerator + values[..., 1] + 0.25 * values[..., 2]
    return np.divide(
        numerator,
        denominator,
        out=np.ones_like(numerator, dtype=np.float64),
        where=denominator != 0,
    ) * 100.0


def bca_interval(
    draws: np.ndarray,
    observed: float,
    jackknife: np.ndarray,
    level: float,
) -> tuple[float, float]:
    draws = np.asarray(draws, dtype=np.float64)
    jackknife = np.asarray(jackknife, dtype=np.float64)
    count = len(draws)
    proportion = float(np.mean(draws < observed))
    proportion = min(max(proportion, 1.0 / (2 * count)), 1.0 - 1.0 / (2 * count))
    z0 = norm.ppf(proportion)
    centered = float(np.mean(jackknife)) - jackknife
    denominator = 6.0 * float(np.sum(centered**2)) ** 1.5
    acceleration = float(np.sum(centered**3)) / denominator if denominator else 0.0

    def adjusted_quantile(q: float) -> float:
        z = norm.ppf(q)
        divisor = 1.0 - acceleration * (z0 + z)
        transformed = norm.cdf(z0 + (z0 + z) / divisor) if divisor else q
        return min(max(float(transformed), 0.0), 1.0)

    alpha = (1.0 - level) / 2.0
    low_q, high_q = adjusted_quantile(alpha), adjusted_quantile(1.0 - alpha)
    low, high = np.quantile(draws, [low_q, high_q])
    return float(low), float(high)


def jackknife_edit(counts: np.ndarray, earlier: int, later: int) -> np.ndarray:
    totals = counts.sum(axis=0)
    earlier_scores = micro_f05(totals[earlier] - counts[:, earlier, :])
    later_scores = micro_f05(totals[later] - counts[:, later, :])
    return later_scores - earlier_scores


def jackknife_mean(values: np.ndarray, earlier: int, later: int) -> np.ndarray:
    n = len(values)
    if n < 2:
        return np.asarray([0.0])
    differences = (values[:, later] - values[:, earlier]) * 100.0
    return (differences.sum() - differences) / (n - 1)


def bootstrap_block(
    block: BlockData,
    *,
    replicates: int,
    seed: int,
    chunk_size: int,
) -> dict[str, dict[str, np.ndarray]]:
    n = block.dataset.rows
    rng = np.random.default_rng(stable_seed(seed, block.model.key, block.dataset.dataset, "main"))
    char_draws = {name: np.empty(replicates) for name, _early, _late in CONTRASTS}
    word_draws = {name: np.empty(replicates) for name, _early, _late in CONTRASTS}
    char_gleu_draws = {name: np.empty(replicates) for name, _early, _late in CONTRASTS}
    word_gleu_draws = {name: np.empty(replicates) for name, _early, _late in CONTRASTS}
    feature_matrix = np.column_stack(
        [
            block.char_counts.reshape(n, 12),
            block.word_counts.reshape(n, 12),
            *[
                (block.char_gleu[:, CONDITIONS.index(late)] - block.char_gleu[:, CONDITIONS.index(early)])[:, None]
                for _name, early, late in CONTRASTS
            ],
            *[
                (block.word_gleu[:, CONDITIONS.index(late)] - block.word_gleu[:, CONDITIONS.index(early)])[:, None]
                for _name, early, late in CONTRASTS
            ],
        ]
    ).astype(np.float64, copy=False)
    probabilities = np.full(n, 1.0 / n)
    for start in range(0, replicates, chunk_size):
        stop = min(replicates, start + chunk_size)
        weights = rng.multinomial(n, probabilities, size=stop - start).astype(np.float64)
        sampled = weights @ feature_matrix
        sampled_char = sampled[:, :12].reshape(-1, 4, 3)
        sampled_word = sampled[:, 12:24].reshape(-1, 4, 3)
        char_scores = micro_f05(sampled_char)
        word_scores = micro_f05(sampled_word)
        for contrast_index, (name, early, late) in enumerate(CONTRASTS):
            early_index, late_index = CONDITIONS.index(early), CONDITIONS.index(late)
            char_draws[name][start:stop] = char_scores[:, late_index] - char_scores[:, early_index]
            word_draws[name][start:stop] = word_scores[:, late_index] - word_scores[:, early_index]
            char_gleu_draws[name][start:stop] = sampled[:, 24 + contrast_index] / n * 100.0
            word_gleu_draws[name][start:stop] = sampled[:, 27 + contrast_index] / n * 100.0
    return {
        "character_f05": char_draws,
        "word_f05": word_draws,
        "character_gleu": char_gleu_draws,
        "word_gleu": word_gleu_draws,
    }


def interval_record(
    block: BlockData,
    metric: str,
    contrast: tuple[str, str, str],
    draws: np.ndarray | None,
    *,
    replicates: int,
    seed: int,
) -> dict[str, Any]:
    name, early, late = contrast
    early_index, late_index = CONDITIONS.index(early), CONDITIONS.index(late)
    if metric == "character_f05":
        values = block.char_counts
        scores = micro_f05(values.sum(axis=0))
        jackknife = jackknife_edit(values, early_index, late_index)
    elif metric == "word_f05":
        values = block.word_counts
        scores = micro_f05(values.sum(axis=0))
        jackknife = jackknife_edit(values, early_index, late_index)
    elif metric == "character_gleu":
        values = block.char_gleu
        scores = values.mean(axis=0) * 100.0
        jackknife = jackknife_mean(values, early_index, late_index)
    elif metric == "word_gleu":
        values = block.word_gleu
        scores = values.mean(axis=0) * 100.0
        jackknife = jackknife_mean(values, early_index, late_index)
    else:
        raise ValueError(metric)
    observed = float(scores[late_index] - scores[early_index])
    inferential = block.dataset.dataset in INFERENTIAL_DATASETS
    record: dict[str, Any] = {
        "model": block.model.display,
        "dataset": DISPLAY_NAMES[block.dataset.dataset],
        "dataset_key": block.dataset.dataset,
        "split": block.dataset.split,
        "metric": metric,
        "word_gleu_source_policy": block.model.word_gleu_source_policy if metric == "word_gleu" else "",
        "contrast": name,
        "n_sentences": block.dataset.rows,
        "n_clusters": block.dataset.rows,
        "resampling_unit": "source sentence",
        "earlier_score": float(scores[early_index]),
        "later_score": float(scores[late_index]),
        "delta_points": observed,
        "ci95_bca_low": "",
        "ci95_bca_high": "",
        "ci90_bca_low": "",
        "ci90_bca_high": "",
        "ci95_percentile_low": "",
        "ci95_percentile_high": "",
        "ci90_percentile_low": "",
        "ci90_percentile_high": "",
        "percentile_conclusion_differs": "",
        "percentile_equivalence_differs": "",
        "equivalence_margin": PRIMARY_MARGIN if metric == "character_f05" and name in {"P-D", "I-P"} else "",
        "equivalent": "",
        "meaningful_gain_excluded": "",
        "interpretation": "descriptive only (n=19)" if not inferential else "",
        "bootstrap_replicates": replicates if inferential else 0,
        "seed": seed,
    }
    if not inferential:
        return record
    if draws is None:
        raise ValueError("Inferential record is missing bootstrap draws")
    ci95 = bca_interval(draws, observed, jackknife, 0.95)
    ci90 = bca_interval(draws, observed, jackknife, 0.90)
    pct95 = tuple(float(value) for value in np.quantile(draws, [0.025, 0.975]))
    pct90 = tuple(float(value) for value in np.quantile(draws, [0.05, 0.95]))
    direction_bca = 1 if ci95[0] > 0 else -1 if ci95[1] < 0 else 0
    direction_pct = 1 if pct95[0] > 0 else -1 if pct95[1] < 0 else 0
    record.update(
        {
            "ci95_bca_low": ci95[0],
            "ci95_bca_high": ci95[1],
            "ci90_bca_low": ci90[0],
            "ci90_bca_high": ci90[1],
            "ci95_percentile_low": pct95[0],
            "ci95_percentile_high": pct95[1],
            "ci90_percentile_low": pct90[0],
            "ci90_percentile_high": pct90[1],
            "percentile_conclusion_differs": direction_bca != direction_pct,
        }
    )
    if direction_bca > 0:
        interpretation = "evidence of improvement"
    elif direction_bca < 0:
        interpretation = "evidence of deterioration"
    else:
        interpretation = "inconclusive"
    if metric == "character_f05" and name in {"P-D", "I-P"}:
        equivalent = ci90[0] > -PRIMARY_MARGIN and ci90[1] < PRIMARY_MARGIN
        percentile_equivalent = pct90[0] > -PRIMARY_MARGIN and pct90[1] < PRIMARY_MARGIN
        gain_excluded = ci90[1] < PRIMARY_MARGIN
        record["equivalent"] = equivalent
        record["percentile_equivalence_differs"] = equivalent != percentile_equivalent
        record["meaningful_gain_excluded"] = gain_excluded
        if equivalent:
            interpretation = "practically equivalent"
        elif gain_excluded:
            interpretation = "meaningful gain excluded; harm or uncertainty remains"
    record["interpretation"] = interpretation
    return record


def boundary_positions(segmented: str) -> frozenset[int]:
    tokens = segmented.split()
    if len(tokens) <= 1:
        return frozenset()
    offsets: list[int] = []
    cursor = 0
    for token in tokens[:-1]:
        cursor += len(token)
        offsets.append(cursor)
    return frozenset(offsets)


def boundary_f1(predicted: frozenset[int], reference: frozenset[int]) -> float:
    if not predicted and not reference:
        return 1.0
    denominator = len(predicted) + len(reference)
    return 2.0 * len(predicted & reference) / denominator if denominator else 1.0


def pooled_boundary_scores(
    predicted: Sequence[frozenset[int]], reference: Sequence[frozenset[int]]
) -> tuple[float, float, float]:
    tp = sum(len(left & right) for left, right in zip(predicted, reference))
    predicted_total = sum(map(len, predicted))
    reference_total = sum(map(len, reference))
    precision = tp / predicted_total if predicted_total else 1.0
    recall = tp / reference_total if reference_total else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def correction_relevant_positions(block: M2Block) -> frozenset[int]:
    positions: set[int] = set()
    source_length = len(block.source_units)
    for edit in block.edits:
        if edit.edit_type == "noop":
            continue
        start = max(0, min(source_length, edit.source_start))
        end = max(0, min(source_length, edit.source_end))
        if start == end:
            positions.add(start)
        else:
            positions.update(range(min(start, end), max(start, end) + 1))
    return frozenset(positions)


def bootstrap_subset_edit(
    counts: np.ndarray,
    indices: np.ndarray,
    earlier: int,
    later: int,
    *,
    replicates: int,
    seed: int,
    chunk_size: int,
) -> tuple[float, float, float]:
    subset = counts[indices]
    n = len(subset)
    observed_scores = micro_f05(subset.sum(axis=0))
    observed = float(observed_scores[later] - observed_scores[earlier])
    if n < 2:
        return observed, math.nan, math.nan
    rng = np.random.default_rng(seed)
    probabilities = np.full(n, 1.0 / n)
    features = subset[:, [earlier, later], :].reshape(n, 6).astype(np.float64)
    draws = np.empty(replicates)
    for start in range(0, replicates, chunk_size):
        stop = min(replicates, start + chunk_size)
        weights = rng.multinomial(n, probabilities, size=stop - start).astype(np.float64)
        sampled = (weights @ features).reshape(-1, 2, 3)
        scores = micro_f05(sampled)
        draws[start:stop] = scores[:, 1] - scores[:, 0]
    local_counts = subset[:, [earlier, later], :]
    totals = local_counts.sum(axis=0)
    jackknife = micro_f05(totals[1] - local_counts[:, 1, :]) - micro_f05(
        totals[0] - local_counts[:, 0, :]
    )
    low, high = bca_interval(draws, observed, jackknife, 0.95)
    return observed, low, high


def bootstrap_mean_values(
    differences: np.ndarray,
    *,
    replicates: int,
    seed: int,
    chunk_size: int,
) -> tuple[float, float, float]:
    values = np.asarray(differences, dtype=np.float64)
    n = len(values)
    observed = float(values.mean()) if n else math.nan
    if n < 2:
        return observed, math.nan, math.nan
    rng = np.random.default_rng(seed)
    probabilities = np.full(n, 1.0 / n)
    draws = np.empty(replicates)
    for start in range(0, replicates, chunk_size):
        stop = min(replicates, start + chunk_size)
        weights = rng.multinomial(n, probabilities, size=stop - start).astype(np.float64)
        draws[start:stop] = weights @ values / n
    jackknife = (values.sum() - values) / (n - 1)
    low, high = bca_interval(draws, observed, jackknife, 0.95)
    return observed, low, high


def boundary_diagnostics(
    block: BlockData,
    *,
    replicates: int,
    seed: int,
    chunk_size: int,
    descriptive_only: bool = False,
) -> list[dict[str, Any]]:
    vectors = {
        condition: [boundary_positions(value) for value in block.boundaries[condition]]
        for condition in ("D", "P", "I")
    }
    fixed = [boundary_positions(value) for value in block.fixed_boundaries]
    relevant = [correction_relevant_positions(value) for value in block.reference_blocks]
    rows: list[dict[str, Any]] = []
    for contrast, early, late in (("P-D", "D", "P"), ("I-P", "P", "I")):
        earlier_index, later_index = CONDITIONS.index(early), CONDITIONS.index(late)
        changed = np.asarray(
            [index for index, pair in enumerate(zip(vectors[early], vectors[late])) if pair[0] != pair[1]],
            dtype=np.int64,
        )
        added = [vectors[late][index] - vectors[early][index] for index in changed]
        removed = [vectors[early][index] - vectors[late][index] for index in changed]
        output_changed_all = np.asarray(
            [left != right for left, right in zip(block.outputs[STAGES[earlier_index]], block.outputs[STAGES[later_index]])]
        )
        changed_output_subset = int(output_changed_all[changed].sum()) if len(changed) else 0
        earlier_f1 = np.asarray([boundary_f1(vectors[early][i], fixed[i]) for i in changed])
        later_f1 = np.asarray([boundary_f1(vectors[late][i], fixed[i]) for i in changed])
        if descriptive_only:
            subset_scores = micro_f05(block.char_counts[changed].sum(axis=0))
            subset_delta = float(subset_scores[later_index] - subset_scores[earlier_index])
            f1_delta = float((later_f1 - earlier_f1).mean() * 100.0) if len(changed) else math.nan
            subset_low = subset_high = f1_low = f1_high = math.nan
        else:
            subset_delta, subset_low, subset_high = bootstrap_subset_edit(
                block.char_counts,
                changed,
                earlier_index,
                later_index,
                replicates=replicates,
                seed=stable_seed(seed, block.model.key, block.dataset.dataset, contrast, "changed-edit"),
                chunk_size=chunk_size,
            )
            f1_delta, f1_low, f1_high = bootstrap_mean_values(
                (later_f1 - earlier_f1) * 100.0,
                replicates=replicates,
                seed=stable_seed(seed, block.model.key, block.dataset.dataset, contrast, "boundary-f1"),
                chunk_size=chunk_size,
            )
        pooled_early = pooled_boundary_scores([vectors[early][i] for i in changed], [fixed[i] for i in changed])
        pooled_late = pooled_boundary_scores([vectors[late][i] for i in changed], [fixed[i] for i in changed])
        changed_positions = [added_row | removed_row for added_row, removed_row in zip(added, removed)]
        changed_position_total = sum(map(len, changed_positions))
        overlap_positions = sum(
            len(changed_positions[offset] & relevant[index]) for offset, index in enumerate(changed)
        )
        overlap_sentences = sum(
            bool(changed_positions[offset] & relevant[index]) for offset, index in enumerate(changed)
        )
        rows.append(
            {
                "model": block.model.display,
                "dataset": DISPLAY_NAMES[block.dataset.dataset],
                "dataset_key": block.dataset.dataset,
                "split": block.dataset.split,
                "contrast": contrast,
                "sentences": block.dataset.rows,
                "changed_boundary_sentences": len(changed),
                "changed_boundary_percent": len(changed) / block.dataset.rows * 100.0,
                "boundary_positions_added": sum(map(len, added)),
                "boundary_positions_removed": sum(map(len, removed)),
                "changed_subset_output_changes": changed_output_subset,
                "changed_subset_output_change_percent": changed_output_subset / len(changed) * 100.0 if len(changed) else 0.0,
                "all_output_changes": int(output_changed_all.sum()),
                "all_output_change_percent": float(output_changed_all.mean() * 100.0),
                "changed_subset_char_f05_delta": subset_delta,
                "changed_subset_char_f05_ci95_bca_low": subset_low,
                "changed_subset_char_f05_ci95_bca_high": subset_high,
                "gold_informed_boundary_precision_earlier": pooled_early[0] * 100.0,
                "gold_informed_boundary_recall_earlier": pooled_early[1] * 100.0,
                "gold_informed_boundary_f1_earlier": pooled_early[2] * 100.0,
                "gold_informed_boundary_precision_later": pooled_late[0] * 100.0,
                "gold_informed_boundary_recall_later": pooled_late[1] * 100.0,
                "gold_informed_boundary_f1_later": pooled_late[2] * 100.0,
                "boundary_f1_closer_sentences": int(np.sum(later_f1 > earlier_f1)),
                "boundary_f1_tied_sentences": int(np.sum(later_f1 == earlier_f1)),
                "boundary_f1_farther_sentences": int(np.sum(later_f1 < earlier_f1)),
                "mean_sentence_boundary_f1_delta": f1_delta,
                "mean_sentence_boundary_f1_delta_ci95_bca_low": f1_low,
                "mean_sentence_boundary_f1_delta_ci95_bca_high": f1_high,
                "changed_boundary_positions": changed_position_total,
                "correction_relevant_overlap_positions": overlap_positions,
                "correction_relevant_overlap_position_percent": overlap_positions / changed_position_total * 100.0 if changed_position_total else 0.0,
                "correction_relevant_overlap_sentences": overlap_sentences,
                "correction_relevant_overlap_sentence_percent": overlap_sentences / len(changed) * 100.0 if len(changed) else 0.0,
                "endpoint_convention": "closed source-span edges; insertion uses its inter-character position",
                "diagnostic_subset": True,
            }
        )
    return rows


def convergence_record(block: BlockData) -> dict[str, Any]:
    n = block.dataset.rows
    direct_calls = int(block.call_counts[:, 1].sum())
    projected_calls = int(block.call_counts[:, 2].sum())
    iterative_calls = int(block.call_counts[:, 3].sum())
    scores = micro_f05(block.char_counts.sum(axis=0))
    normalized_unchanged_recalled_p = sum(
        boundary_positions(block.boundaries["D"][index])
        == boundary_positions(block.boundaries["P"][index])
        and block.call_counts[index, 2] == 1
        for index in range(n)
    )
    normalized_unchanged_recalled_i = sum(
        boundary_positions(block.boundaries["P"][index])
        == boundary_positions(block.boundaries["I"][index])
        and block.call_counts[index, 3] == 1
        for index in range(n)
    )
    return {
        "model": block.model.display,
        "dataset": DISPLAY_NAMES[block.dataset.dataset],
        "dataset_key": block.dataset.dataset,
        "split": block.dataset.split,
        "sentences": n,
        "raw_calls": int(block.call_counts[:, 0].sum()),
        "direct_calls": direct_calls,
        "projected_calls_added": projected_calls,
        "iterative_calls_added": iterative_calls,
        "projection_calls_added_total": projected_calls + iterative_calls,
        "added_calls_percent_of_direct": (projected_calls + iterative_calls) / direct_calls * 100.0 if direct_calls else math.nan,
        "stopped_after_direct": int(np.sum((block.call_counts[:, 2] == 0) & (block.call_counts[:, 3] == 0))),
        "stopped_after_projected": int(np.sum((block.call_counts[:, 2] == 1) & (block.call_counts[:, 3] == 0))),
        "reached_iterative": int(np.sum(block.call_counts[:, 3] == 1)),
        "mean_wb_aware_calls_per_source": (direct_calls + projected_calls + iterative_calls) / n,
        "normalized_unchanged_but_projected_recalled": normalized_unchanged_recalled_p,
        "normalized_unchanged_but_iterative_recalled": normalized_unchanged_recalled_i,
        "prompt_tokens_all_conditions": int(block.prompt_tokens.sum()),
        "completion_tokens_all_conditions": int(block.completion_tokens.sum()),
        "total_tokens_all_conditions": int(block.total_tokens.sum()),
        "format_retries": int(block.format_retries.sum()),
        "content_filter_identity_fallbacks": int(block.filter_fallbacks.sum()),
        "projected_minus_direct_f05": float(scores[2] - scores[1]),
        "iterative_minus_projected_f05": float(scores[3] - scores[2]),
        "projected_delta_per_1000_added_calls": float((scores[2] - scores[1]) / projected_calls * 1000.0) if projected_calls else math.nan,
        "iterative_delta_per_1000_added_calls": float((scores[3] - scores[2]) / iterative_calls * 1000.0) if iterative_calls else math.nan,
        "monetary_cost": "not compared; pricing and billing were not independently verified",
    }


def sentence_export_rows(block: BlockData) -> Iterable[dict[str, Any]]:
    for row_index, source_id in enumerate(block.source_ids):
        for stage_index, stage in enumerate(STAGES):
            condition = CONDITIONS[stage_index]
            yield {
                "model": block.model.display,
                "model_identifier": block.model.identifier,
                "dataset": DISPLAY_NAMES[block.dataset.dataset],
                "dataset_key": block.dataset.dataset,
                "split": block.dataset.split,
                "source_id": source_id,
                "cluster_id": source_id,
                "condition": condition,
                "stage": stage,
                "reference_count": int(block.reference_counts[row_index]),
                "char_tp": int(block.char_counts[row_index, stage_index, 0]),
                "char_fp": int(block.char_counts[row_index, stage_index, 1]),
                "char_fn": int(block.char_counts[row_index, stage_index, 2]),
                "word_tp": int(block.word_counts[row_index, stage_index, 0]),
                "word_fp": int(block.word_counts[row_index, stage_index, 1]),
                "word_fn": int(block.word_counts[row_index, stage_index, 2]),
                "char_gleu": float(block.char_gleu[row_index, stage_index]),
                "word_gleu": float(block.word_gleu[row_index, stage_index]),
                "word_gleu_source_policy": block.model.word_gleu_source_policy,
                "word_gleu_source_stage": (
                    CONDITION_SOURCE_COLUMNS[stage]
                    if block.model.word_gleu_source_policy == "condition" else "fixed-gold"
                ),
                "word_gleu_source_segmentation": block.word_gleu_sources[stage][row_index],
                "word_m2_source_policy": "fixed-gold",
                "selected_char_edit_reference": int(block.char_selected[row_index, stage_index]),
                "selected_word_edit_reference": int(block.word_selected[row_index, stage_index]),
                "selected_char_gleu_reference": int(block.char_gleu_selected[row_index, stage_index]),
                "selected_word_gleu_reference": int(block.word_gleu_selected[row_index, stage_index]),
                "selected_edit_reference": int(block.char_selected[row_index, stage_index]),
                "selected_gleu_reference": int(block.char_gleu_selected[row_index, stage_index]),
                "hypothesis_normalized": block.outputs[stage][row_index],
                "boundary_representation": block.boundaries[condition][row_index],
                "model_calls": int(block.call_counts[row_index, stage_index]),
                "prompt_tokens": int(block.prompt_tokens[row_index, stage_index]),
                "completion_tokens": int(block.completion_tokens[row_index, stage_index]),
                "total_tokens": int(block.total_tokens[row_index, stage_index]),
                "format_retries": int(block.format_retries[row_index, stage_index]),
                "content_filter_identity_fallback": int(block.filter_fallbacks[row_index, stage_index]),
            }


def interpretation_for_margin(ci90_low: float, ci90_high: float, ci95_low: float, ci95_high: float, margin: float) -> tuple[bool, bool, str]:
    equivalent = ci90_low > -margin and ci90_high < margin
    gain_excluded = ci90_high < margin
    if equivalent:
        text = "practically equivalent"
    elif gain_excluded:
        text = "meaningful gain excluded; harm or uncertainty remains"
    elif ci95_low > 0:
        text = "evidence of improvement"
    elif ci95_high < 0:
        text = "evidence of deterioration"
    else:
        text = "inconclusive"
    return equivalent, gain_excluded, text


def config_payload(args: argparse.Namespace, models: Sequence[ModelSpec]) -> dict[str, Any]:
    configured_models = [
        {
            name: str(value.relative_to(ROOT) if value.is_relative_to(ROOT) else value)
            if isinstance(value, Path) else value
            for name, value in asdict(model).items()
        }
        for model in models
    ]
    return {
        "analysis": "paired bootstrap and practical-equivalence analysis",
        "source_outputs": f"saved T0--T3 {' and '.join(model.display for model in models)} runs; no new API calls",
        "models": configured_models,
        "model_config": str(args.model_config) if args.model_config is not None else None,
        "historical_run_invariants": "required; see validation.log" if args.model_config is None else "skipped for custom model configuration",
        "conditions": STAGE_TO_CONDITION,
        "seed": args.seed,
        "bootstrap_replicates": args.replicates,
        "bootstrap_chunk_size": args.chunk_size,
        "scale": "0--100 metric points",
        "primary_metric": "projection-based character-level micro F0.5",
        "secondary_metrics": [
            "projection-based word-level micro F0.5",
            "character GLEU select-best",
            "word GLEU select-best",
        ],
        "contrasts": [name for name, _early, _late in CONTRASTS],
        "reference_selection": {
            "edit": "highest unrounded sentence-level F0.5; ties: TP desc, FP asc, FN asc, then first annotator order",
            "gleu": "highest sentence-level GLEU across complete references; independent by unit and metric",
        },
        "resampling": {
            "unit": "source sentence",
            "pairing": "same multinomial source weights for all conditions and metrics within each model-dataset block",
            "cluster_limitation": "reliable document/learner identifiers are unavailable; source sentences are resampled",
        },
        "estimation_interval": "paired 95% BCa bootstrap",
        "equivalence_interval": "paired 90% BCa bootstrap",
        "equivalence_margin": PRIMARY_MARGIN,
        "sensitivity_margins": list(SENSITIVITY_MARGINS),
        "inferential_datasets": sorted(INFERENTIAL_DATASETS),
        "descriptive_only": ["cefe_track3"],
        "word_gleu_segmentation": {
            "source_policy_by_model": {
                model.key: model.word_gleu_source_policy for model in models
            },
            "source_stage_mapping_by_model": {
                model.key: dict(CONDITION_SOURCE_COLUMNS)
                if model.word_gleu_source_policy == "condition" else None
                for model in models
            },
            "hypotheses_and_references": "LTP",
            "retokenized_by_analysis": False,
            "required_artifact_checks": [
                "completed run_config.json with matching declared policy",
                "sentence and summary policy labels (identifiable legacy fixed-gold excepted)",
                "exported source inputs match saved condition or fixed-gold boundaries",
            ],
        },
        "word_m2_segmentation": {
            "source_policy": "fixed-gold",
            "source": "shared fixed gold-informed source segmentation for all conditions",
            "fixed_source_root": "runs/gold_fixed_source_segmentation",
        },
        "boundary_endpoint_convention": "a span [start,end) contributes inter-character positions start through end, including both edges; an insertion contributes start",
        "software": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": __import__("scipy").__version__,
            "evaluator": "scripts/movement_aware_compare.py",
        },
    }


def output_fields(rows: Sequence[dict[str, Any]]) -> list[str]:
    return list(rows[0]) if rows else []


def format_interval(value: Any) -> str:
    return "NA" if value == "" or (isinstance(value, float) and math.isnan(value)) else f"{float(value):+.2f}"


def word_gleu_policy_report(models: Sequence[ModelSpec]) -> str:
    policies = {model.word_gleu_source_policy for model in models}
    lines = [
        "## Word GLEU source policy",
        "",
        markdown_table(
            ["Model", "Word GLEU policy", "R/T0 source", "D/T1 source", "P/T2 source", "I/T3 source"],
            [
                (
                    model.display, model.word_gleu_source_policy,
                    *[
                        CONDITION_SOURCE_COLUMNS[stage]
                        if model.word_gleu_source_policy == "condition" else "fixed-gold"
                        for stage in STAGES
                    ],
                )
                for model in models
            ],
        ),
        "",
        "Condition-specific word GLEU uses saved direct LTP S1 for both R/T0 and D/T1, "
        "saved S2 for P/T2, and saved S3 for I/T3. `fixed-gold` is explicit historical "
        "reproduction using one shared gold-informed source segmentation at all stages.",
        "",
        "Word-GLEU hypotheses and complete references remain LTP-segmented. Character GLEU "
        "and both M2 metrics are unchanged: word M2 still uses shared fixed gold-informed source "
        "boundaries, validated independently of the word-GLEU policy. Analysis does not retokenize inputs.",
        "",
        "Word GLEU depends on source n-grams: a difference can arise from source segmentation "
        "even with an identical hypothesis. Values from condition and fixed-gold policies are not "
        "interchangeable. Completion metadata, row policy labels, and exported source boundaries "
        "are checked in `word_gleu_source_audit.tsv`; identifiable legacy fixed-gold metadata is "
        "accepted only when explicitly selected.",
    ]
    if len(policies) > 1:
        lines.extend(
            [
                "",
                "**MIXED WORD-GLEU POLICIES:** model-specific results are labeled separately. "
                "Do not pool or attribute cross-policy word-GLEU differences to model quality.",
            ]
        )
    return "\n".join(lines)


def configured_model_table(models: Sequence[ModelSpec]) -> str:
    return markdown_table(
        [
            "Model", "Identifier/version", "Provider", "Access date", "Temperature",
            "Top-p", "Max output", "Reasoning/thinking", "Samples", "Kmax",
            "Cached edit selector", "Word GLEU source policy",
        ],
        [
            (
                model.display, model.identifier, model.provider, model.access_date,
                model.temperature, model.top_p, model.max_output, model.thinking,
                1, 3, model.cached_selector_policy, model.word_gleu_source_policy,
            )
            for model in models
        ],
    )


def latex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in value)


def configured_model_latex_rows(models: Sequence[ModelSpec]) -> list[str]:
    return [
        " & ".join(
            [
                latex_escape(model.display),
                r"\texttt{" + latex_escape(model.identifier) + "}",
                *[
                    latex_escape(value)
                    for value in (
                        model.provider, model.access_date, model.temperature,
                        model.top_p, model.max_output, model.thinking,
                    )
                ],
                "1",
                "3",
                latex_escape(model.word_gleu_source_policy),
            ]
        ) + r" \\"
        for model in models
    ]


def frozen_analysis_design(args: argparse.Namespace) -> bool:
    return (args.seed, args.replicates, args.chunk_size) == (20260915, 50000, 1000)


def build_configured_report(
    dataset_rows: Sequence[dict[str, Any]],
    models: Sequence[ModelSpec],
    blocks: Sequence[BlockData],
    primary: Sequence[dict[str, Any]],
    secondary: Sequence[dict[str, Any]],
    sensitivity: Sequence[dict[str, Any]],
    boundary_rows: Sequence[dict[str, Any]],
    convergence_rows: Sequence[dict[str, Any]],
    *,
    args: argparse.Namespace,
) -> str:
    def ratio(numerator: int, denominator: int) -> str:
        percent = f"{numerator / denominator * 100:.2f}%" if denominator else "NA"
        return f"{numerator:,}/{denominator:,} ({percent})"

    def directional_counts(rows: Sequence[dict[str, Any]]) -> tuple[int, int, int]:
        improvements = sum(row["ci95_bca_low"] > 0 for row in rows)
        deteriorations = sum(row["ci95_bca_high"] < 0 for row in rows)
        return improvements, deteriorations, len(rows) - improvements - deteriorations

    formal_primary = [row for row in primary if row["dataset_key"] in INFERENTIAL_DATASETS]
    formal_secondary = [row for row in secondary if row["dataset_key"] in INFERENTIAL_DATASETS]
    inferential_names = [row["dataset"] for row in dataset_rows if row["dataset_key"] in INFERENTIAL_DATASETS]
    descriptive = [row for row in dataset_rows if row["dataset_key"] not in INFERENTIAL_DATASETS]
    sections = [
        "# Configured-model paired-bootstrap analysis",
        "",
        "Models analyzed: " + ", ".join(model.display for model in models) + ".",
        "This report describes only the configured saved runs, not a comparison against unprovided historical runs. "
        "Frozen historical-model invariants are **SKIPPED**, not passed; reference, cache, coverage, and carry-forward checks still apply to every configured run.",
        "",
        "## Dataset statistics",
        "",
        markdown_table(
            ["Dataset", "Split", "Sentences", "References", "Multi-ref.", ">3 refs.", "Max refs."],
            [
                (
                    row["dataset"], row["split"].title(), f"{row['sentences']:,}",
                    f"{row['references']:,}", f"{row['multi_reference_sentences']:,}",
                    f"{row['sentences_over_3_references']:,}", row["max_references"],
                )
                for row in dataset_rows
            ],
        ),
        "",
        "Counts include every complete textual reference in `gold.para`; no source instances or references are removed after inspecting results. "
        "See `table_2_dataset_statistics.tsv` for totals.",
        "",
        "## Model and inference configuration",
        "",
        configured_model_table(models),
        "",
        "These are the declared generation settings, not settings inferred from score tables. "
        "Provider-default settings are not claims of disabled reasoning, deterministic decoding, a known numeric sampling value, or a verified output cap. "
        "One saved output is evaluated per source and condition; Kmax=3 denotes the last saved stage T3. "
        "Analysis reuses R/T0 (Raw), D/T1 (Direct), P/T2 (Projected), and I/T3 (Iterative) and makes no model/API calls.",
        "",
        "## Statistical protocol",
        "",
        f"Each model-dataset block uses {args.replicates:,} paired source-level bootstrap replicates, "
        f"base seed {args.seed}, and chunk size {args.chunk_size:,}. Stable model/dataset-specific seeds are derived from this base seed. "
        "The same sampled source weights are shared across conditions and metrics within a block. "
        "The primary outcome is projection-based character micro-F0.5, recomputed from pooled TP/FP/FN in every resample, not an average of sentence F-scores. "
        "Estimation uses 95% BCa intervals; P-D and I-P equivalence requires the 90% BCa interval strictly inside +/-0.50 points, "
        "with +/-0.25 and +/-1.00 sensitivity analyses. All scores and differences are on the 0--100 scale.",
        "",
        "Inferential datasets: " + ", ".join(inferential_names) + ".",
        "Descriptive only: " + ", ".join(f"{row['dataset']} (n={row['sentences']})" for row in descriptive)
        + "; no bootstrap intervals or equivalence decisions are reported for these datasets, including boundary subsets.",
        "",
        "Edit references are selected independently by sentence using the highest unrounded F0.5 "
        "(ties: more TP, fewer FP, fewer FN, then first annotator order). "
        "The configured cached selector is only a cache-validation policy: both corpus-greedy and sentence-local scores are audited, "
        "but all primary and secondary edit estimates use sentence-local counts. "
        "Character and word GLEU independently select the highest-scoring complete reference per sentence. "
        "This script reads and validates saved GLEU scores; it does not retokenize them.",
        "",
        word_gleu_policy_report(models),
        "",
    ]
    if not frozen_analysis_design(args):
        sections.extend(
            [
                "**NONSTANDARD ANALYSIS SETTINGS:** this is not the prescribed final 50,000-replicate, "
                "seed-20260915, chunk-1000 analysis. The actual settings above and in `analysis_config.json` govern these outputs.",
                "",
            ]
        )
    sections.extend(
        [
            "## Primary character micro-F0.5 contrasts",
            "",
            "Each cell is a difference in points with its paired 95% BCa interval. "
            "`E` denotes the separate 90% BCa practical-equivalence decision at +/-0.50. "
            "An interval containing zero is inconclusive, not evidence of no difference. "
            "Intervals are per-comparison; no multiple-comparison adjustment is applied.",
            "",
        ]
    )
    primary_map = {(row["model"], row["dataset_key"], row["contrast"]): row for row in primary}
    for model in models:
        table_rows = []
        for block in blocks:
            if block.model.key != model.key:
                continue
            cells = []
            for name, _early, _late in CONTRASTS:
                row = primary_map[(model.display, block.dataset.dataset, name)]
                if row["ci95_bca_low"] == "":
                    cell = f"{row['delta_points']:+.2f} [descriptive]"
                else:
                    marker = " E" if row.get("equivalent") is True else ""
                    cell = f"{row['delta_points']:+.2f} [{row['ci95_bca_low']:+.2f}, {row['ci95_bca_high']:+.2f}]{marker}"
                cells.append(cell)
            table_rows.append((DISPLAY_NAMES[block.dataset.dataset], block.dataset.rows, *cells))
        sections.extend(
            [
                f"### {model.display}", "",
                markdown_table(["Dataset", "N", "D-R", "P-D", "I-P"], table_rows), "",
            ]
        )
    finding_rows = []
    for model in models:
        for contrast, _early, _late in CONTRASTS:
            selected = [
                row for row in formal_primary
                if row["model"] == model.display and row["contrast"] == contrast
            ]
            finding_rows.append(
                (
                    model.display, contrast, len(selected), *directional_counts(selected),
                    sum(row["equivalent"] is True for row in selected) if contrast != "D-R" else "not tested",
                    sum(row["meaningful_gain_excluded"] is True for row in selected) if contrast != "D-R" else "not tested",
                )
            )
    sections.extend(
        [
            "## Computed primary findings", "",
            markdown_table(
                [
                    "Model", "Contrast", "Comparisons", "95% improvement", "95% deterioration",
                    "95% inconclusive", "Equivalent +/-0.50", "Gain >=0.50 excluded",
                ],
                finding_rows,
            ),
            "",
            "D-R estimates the effect of presenting word-boundary-aware input. P-D and I-P estimate incremental projection and iteration effects. "
            "These counts summarize separate within-dataset comparisons; they are not a pooled effect or a test of between-model differences. "
            "Directional evidence and practical equivalence are not mutually exclusive. Excluding a meaningful gain does not establish equivalence if harm remains plausible.",
            "",
        ]
    )
    for title, character, word in (
        ("Absolute sentence-local edit scores", lambda block: micro_f05(block.char_counts.sum(axis=0)), lambda block: micro_f05(block.word_counts.sum(axis=0))),
        ("Absolute GLEU scores", lambda block: block.char_gleu.mean(axis=0) * 100.0, lambda block: block.word_gleu.mean(axis=0) * 100.0),
    ):
        sections.extend(
            [
                f"## {title}", "",
                markdown_table(
                    ["Model", "Dataset", "Word source policy", "Char R", "Char D", "Char P", "Char I", "Word R", "Word D", "Word P", "Word I"],
                    [
                        (
                            block.model.display, DISPLAY_NAMES[block.dataset.dataset],
                            block.model.word_gleu_source_policy if title == "Absolute GLEU scores" else "fixed-gold",
                            *[f"{value:.2f}" for value in character(block)],
                            *[f"{value:.2f}" for value in word(block)],
                        )
                        for block in blocks
                    ],
                ),
                "",
            ]
        )
    secondary_findings = []
    sensitivity_findings = []
    robustness = []
    for model in models:
        for metric in ("word_f05", "character_gleu", "word_gleu"):
            for contrast, _early, _late in CONTRASTS:
                selected = [
                    row for row in formal_secondary
                    if row["model"] == model.display and row["metric"] == metric and row["contrast"] == contrast
                ]
                secondary_findings.append(
                    (
                        model.display, metric,
                        model.word_gleu_source_policy if metric == "word_gleu" else "fixed-gold" if metric == "word_f05" else "character",
                        contrast, len(selected), *directional_counts(selected),
                    )
                )
        for margin in SENSITIVITY_MARGINS:
            selected = [
                row for row in sensitivity
                if row["model"] == model.display and row["equivalence_margin"] == margin
            ]
            sensitivity_findings.append(
                (
                    model.display, f"+/-{margin:.2f}", len(selected),
                    sum(row["equivalent"] is True for row in selected),
                    sum(row["meaningful_gain_excluded"] is True for row in selected),
                )
            )
        model_primary = [row for row in formal_primary if row["model"] == model.display]
        model_secondary = [row for row in formal_secondary if row["model"] == model.display]
        robustness.append(
            (
                model.display,
                sum(row.get("percentile_conclusion_differs") is True for row in model_primary),
                sum(row.get("percentile_equivalence_differs") is True for row in model_primary),
                sum(row.get("percentile_conclusion_differs") is True for row in model_secondary),
            )
        )
    sections.extend(
        [
            "## Exploratory secondary outcomes", "",
            markdown_table(
                ["Model", "Metric", "Source policy", "Contrast", "Comparisons", "95% improvement", "95% deterioration", "95% inconclusive"],
                secondary_findings,
            ),
            "",
            "Full effect estimates and intervals are in `bootstrap_secondary.csv`; these metrics do not replace the pre-specified primary outcome.",
            "",
            "## Equivalence sensitivity and interval robustness", "",
            markdown_table(["Model", "Margin", "P-D/I-P comparisons", "Equivalent", "Meaningful gain excluded"], sensitivity_findings),
            "",
            "Counts of conclusions that differ between BCa and ordinary percentile intervals:", "",
            markdown_table(["Model", "Primary direction", "Primary equivalence", "Secondary direction"], robustness),
            "",
            "BCa remains the pre-specified analysis. Flagged comparisons and both interval endpoints are retained in the bootstrap CSV files; "
            "sensitivity to interval construction should be considered when interpreting those comparisons.",
            "",
            "## Boundary intervention and recorded cost", "",
        ]
    )
    for model in models:
        model_boundaries = [row for row in boundary_rows if row["model"] == model.display]
        model_cost = [row for row in convergence_rows if row["model"] == model.display]
        for contrast in ("P-D", "I-P"):
            selected = [row for row in model_boundaries if row["contrast"] == contrast]
            changed = sum(row["changed_boundary_sentences"] for row in selected)
            total = sum(row["sentences"] for row in selected)
            corrections = sum(row["changed_subset_output_changes"] for row in selected)
            closer = sum(row["boundary_f1_closer_sentences"] for row in selected)
            farther = sum(row["boundary_f1_farther_sentences"] for row in selected)
            overlap = sum(row["correction_relevant_overlap_positions"] for row in selected)
            positions = sum(row["changed_boundary_positions"] for row in selected)
            sections.append(
                f"- {model.display} {contrast}: normalized boundaries changed for {ratio(changed, total)} sources; "
                f"corrections changed for {ratio(corrections, changed)} of those sources. "
                f"{closer:,} moved closer to and {farther:,} farther from fixed gold-informed boundaries. "
                f"Correction-relevant spans overlapped {ratio(overlap, positions)} changed boundary positions."
            )
        direct = sum(row["direct_calls"] for row in model_cost)
        added = sum(row["projection_calls_added_total"] for row in model_cost)
        tokens = sum(row["total_tokens_all_conditions"] for row in model_cost)
        retries = sum(row["format_retries"] for row in model_cost)
        fallbacks = sum(row["content_filter_identity_fallbacks"] for row in model_cost)
        unchanged_calls = sum(
            row["normalized_unchanged_but_projected_recalled"] + row["normalized_unchanged_but_iterative_recalled"]
            for row in model_cost
        )
        sections.append(
            f"- {model.display}: {direct:,} Direct calls and {added:,} additional Projected/Iterative calls "
            f"(added/Direct: {ratio(added, direct)}); {tokens:,} recorded tokens across all conditions; "
            f"{retries:,} recorded format retries and {fallbacks:,} content-filter identity fallbacks. "
            f"{unchanged_calls:,} calls were recorded after unchanged normalized boundary vectors."
        )
    sections.extend(
        [
            "",
            "## Limitations and reproducibility", "",
            "Boundary-change subsets are intervention-selected diagnostics, not randomized subgroups. "
            "The fixed source segmentations used for word M2 and boundary diagnostics are gold-informed proxies, not manually annotated gold word boundaries. "
            "Boundary summaries above include descriptive datasets; CEFE contributes no inferential intervals. "
            "Reliable document/learner cluster IDs were unavailable, so source-level intervals do not account for within-document dependence. "
            "One saved decode per condition cannot quantify repeated-API sampling variability.",
            "",
            "Calls, retries, fallbacks, and tokens are totals from saved API metadata, not independently measured billing records. "
            "Missing usage fields contribute zero to the token ledger, which is not evidence of zero token consumption. "
            "A declared provider-default output limit does not establish a numeric cap or rule out truncation. "
            "Monetary costs are not inferred from token totals because pricing and billing records were not independently verified.",
            "",
            "## Artifacts", "",
            "- `table_2_dataset_statistics.tsv`, `table_3_model_configuration.tsv`, and `PAPER_TABLES.tex`: manuscript tables.",
            "- `sentence_level_scores.tsv`: counts, references, scores, outputs, boundaries, and API metadata for every configured source and condition.",
            "- `bootstrap_primary.csv`, `bootstrap_secondary.csv`, and `equivalence_sensitivity.csv`: effect estimates, intervals, decisions, and robustness checks.",
            "- `changed_boundary_diagnostics.csv` and `convergence_and_cost.csv`: intervention coverage, diagnostic subset estimates, stopping, and recorded costs.",
            "- `scorer_selection_audit.tsv`: both edit selectors and the explicit cached-selector validation policy.",
            "- `word_gleu_source_audit.tsv`: completed word-GLEU metadata, policy labels, and source-file boundary checks.",
            "- `analysis_config.json`, `validation.log`, and `README_ANALYSIS_COMPLIANCE.md`: settings, software, passed checks, skipped historical checks, and limitations.",
            "",
        ]
    )
    return "\n".join(sections)


def build_configured_compliance(
    args: argparse.Namespace, audit_rows: Sequence[dict[str, Any]], models: Sequence[ModelSpec]
) -> str:
    design_status = "Complete" if frozen_analysis_design(args) else "NONSTANDARD; not the frozen final analysis"
    policies = Counter(row["cached_selector_policy"] for row in audit_rows)
    policy_summary = ", ".join(f"{policy}: {count} cells" for policy, count in sorted(policies.items()))
    return "\n".join(
        [
            "# Configured-model analysis compliance", "",
            markdown_table(
                ["Requirement", "Status", "Evidence"],
                [
                    (
                        "50,000 paired BCa replicates, seed 20260915, chunk 1000",
                        design_status,
                        f"Actual: {args.replicates:,} replicates, seed {args.seed}, chunk {args.chunk_size}; `analysis_config.json`",
                    ),
                    ("Saved R/T0, D/T1, P/T2, I/T3 with no post-hoc exclusions", "Complete", "`sentence_level_scores.tsv`"),
                    ("Dataset totals and exact complete gold reference text/count/order", "Complete", "`validation.log`"),
                    ("Sentence-local edit selection; independent character/word GLEU selection", "Complete", "`sentence_level_scores.tsv` and `scorer_selection_audit.tsv`"),
                    ("Declared word-GLEU source policy, completion metadata, and source inputs", "Complete", "`word_gleu_source_audit.tsv` and `analysis_config.json`"),
                    ("Unchanged shared fixed-gold word-M2 sources", "Complete", "`validation.log`; independent of word-GLEU policy"),
                    ("Declared cached M2 selector reproduced; both selectors audited", "Complete", policy_summary + "; `scorer_selection_audit.tsv`"),
                    ("Frozen historical-model run invariants", "SKIPPED", "Custom model configuration; frozen historical invariants not checked"),
                    ("Paired source-level micro-F0.5; 95%/90% BCa and percentile intervals", "Complete", "`bootstrap_primary.csv` and `bootstrap_secondary.csv`"),
                    ("Equivalence +/-0.50 with +/-0.25 and +/-1.00 sensitivity", "Complete", "`equivalence_sensitivity.csv`"),
                    ("Seven inferential datasets; CEFE Track 3 descriptive only", "Complete", "Bootstrap CSVs; no CEFE boundary-subset intervals"),
                    ("Boundary coverage, split/merge counts, outputs, relevant spans and proxy proximity", "Complete", "`changed_boundary_diagnostics.csv`"),
                    ("Carry-forward, convergence, calls, tokens, and efficiency", "Complete", "`validation.log` and `convergence_and_cost.csv`"),
                ],
            ),
            "",
            "## Recorded limitations", "",
            "- Frozen historical-model invariants are not evidence for or against these configured runs.",
            "- Source-sentence resampling cannot account for unavailable document/learner clusters or repeated model decodes.",
            "- Boundary-change subsets are diagnostic; their fixed comparison boundaries and word-M2 sources are gold-informed proxies.",
            "- Provider defaults are recorded as declared, not assumed to disable reasoning or imply a numeric output cap.",
            "- Tokens are recorded metadata totals; absent usage contributes zero and cannot establish true zero consumption. No dated monetary-cost comparison is made.",
            "- Word-GLEU differences can arise from source segmentation even with an identical hypothesis; hypotheses/references remain LTP.",
            "",
            word_gleu_policy_report(models),
            "",
        ]
    )


def build_paper_report(
    dataset_rows: Sequence[dict[str, Any]],
    models: Sequence[ModelSpec],
    blocks: Sequence[BlockData],
    primary: Sequence[dict[str, Any]],
    secondary: Sequence[dict[str, Any]],
    sensitivity: Sequence[dict[str, Any]],
    boundary_rows: Sequence[dict[str, Any]],
    convergence_rows: Sequence[dict[str, Any]],
) -> str:
    total = {
        key: sum(int(row[key]) for row in dataset_rows)
        for key in (
            "sentences",
            "references",
            "multi_reference_sentences",
            "sentences_over_3_references",
        )
    }
    observed_max_completion = {
        model.key: max(
            int(block.completion_tokens.max())
            for block in blocks
            if block.model.key == model.key
        )
        for model in models
    }
    sections = [
        "# ARR October 2026: Tables and Analysis",
        "",
        "> Numbering note: in the supplied PDF, dataset statistics are Table 2; Table 3 is the model and inference configuration. Both are completed below.",
        "",
        "## Table 2. Dataset statistics",
        "",
        markdown_table(
            ["Dataset", "Split", "Sentences", "References", "Multi-ref.", ">3 refs.", "Max refs."],
            [
                (
                    row["dataset"],
                    row["split"].title(),
                    f"{row['sentences']:,}",
                    f"{row['references']:,}",
                    f"{row['multi_reference_sentences']:,}",
                    f"{row['sentences_over_3_references']:,}",
                    row["max_references"],
                )
                for row in dataset_rows
            ]
            + [["Total", "", f"{total['sentences']:,}", f"{total['references']:,}", f"{total['multi_reference_sentences']:,}", f"{total['sentences_over_3_references']:,}", max(row["max_references"] for row in dataset_rows)]],
        ),
        "",
        "Statistics count complete textual references in `gold.para`. Multi-ref. is the number of source instances with more than one reference; `>3 refs.` counts instances with at least four references.",
        "",
        word_gleu_policy_report(models),
        "",
        "## Table 3. Model and inference configuration",
        "",
        markdown_table(
            ["Model", "Identifier/version", "Provider", "Access date", "Temperature", "Top-p", "Max output", "Samples", "Kmax", "Word GLEU source policy"],
            [
                (model.display, model.identifier, model.provider, model.access_date, model.temperature, model.top_p, model.max_output, 1, 3, model.word_gleu_source_policy)
                for model in models
            ],
        ),
        "",
        "Each model produced one correction per source and condition. Thinking was disabled. DeepSeek used a near-zero temperature, whereas Kimi's non-thinking endpoint fixed temperature at 0.6; neither provider exposed a reproducible sampling seed. Thus the saved outputs are fixed for evaluation, but the original decoding should not be described as strictly deterministic.",
        "",
        "Responses were normalized by removing code fences, known answer prefixes, trailing explanation sections, whitespace, and surrounding quotation marks. Empty, explicit self-analysis, or implausibly long responses were retried. Successful retries and Kimi content-filter identity fallbacks remain in the evaluation; no cases were removed after inspecting results. DeepSeek omitted `max_tokens`, so the provider's 8,192-token non-thinking default applied; its longest saved completion was "
        f"{observed_max_completion['deepseek']} tokens. Kimi was capped at 512 output tokens, and its longest saved completion was {observed_max_completion['kimi']} tokens. Neither model approached its output cap. `Kmax=3` denotes the last saved iterative stage T3.",
        "",
        "## Primary paired-bootstrap results",
        "",
        "Cells report the character-level micro-F0.5 difference in points and its paired 95% BCa interval. `E` means that the paired 90% BCa interval lies strictly inside the pre-defined +/-0.50-point equivalence region. CEFE Track 3 is descriptive only.",
        "",
    ]
    primary_map = {(row["model"], row["dataset_key"], row["contrast"]): row for row in primary}
    for model in models:
        table_rows = []
        for block in [value for value in blocks if value.model.key == model.key]:
            cells = []
            for name, _early, _late in CONTRASTS:
                row = primary_map[(model.display, block.dataset.dataset, name)]
                if row["ci95_bca_low"] == "":
                    cell = f"{row['delta_points']:+.2f} [descriptive]"
                else:
                    marker = " E" if row.get("equivalent") is True else ""
                    cell = f"{row['delta_points']:+.2f} [{row['ci95_bca_low']:+.2f}, {row['ci95_bca_high']:+.2f}]{marker}"
                cells.append(cell)
            table_rows.append((DISPLAY_NAMES[block.dataset.dataset], *cells))
        sections.extend(
            [
                f"### {model.display}",
                "",
                markdown_table(["Dataset", "D-R", "P-D", "I-P"], table_rows),
                "",
            ]
        )

    absolute_rows = []
    for block in blocks:
        char_scores = micro_f05(block.char_counts.sum(axis=0))
        word_scores = micro_f05(block.word_counts.sum(axis=0))
        absolute_rows.append(
            (
                block.model.display,
                DISPLAY_NAMES[block.dataset.dataset],
                *[f"{value:.2f}" for value in char_scores],
                *[f"{value:.2f}" for value in word_scores],
            )
        )
    sections.extend(
        [
            "## Corrected absolute edit scores",
            "",
            "These values use sentence-local select-best for both models and should replace edit-score rows computed with the historical order-dependent corpus-greedy reference selector.",
            "",
            markdown_table(
                ["Model", "Dataset", "Char R", "Char D", "Char P", "Char I", "Word R", "Word D", "Word P", "Word I"],
                absolute_rows,
            ),
            "",
            "## Absolute GLEU scores",
            "",
            "GLEU is character- or word-ngram based and independently selects the highest-scoring complete reference for each sentence.",
            "",
            markdown_table(
                ["Model", "Dataset", "Word GLEU source policy", "Char R", "Char D", "Char P", "Char I", "Word R", "Word D", "Word P", "Word I"],
                [
                    (
                        block.model.display,
                        DISPLAY_NAMES[block.dataset.dataset],
                        block.model.word_gleu_source_policy,
                        *[f"{value:.2f}" for value in block.char_gleu.mean(axis=0) * 100.0],
                        *[f"{value:.2f}" for value in block.word_gleu.mean(axis=0) * 100.0],
                    )
                    for block in blocks
                ],
            ),
            "",
            "## Main findings",
            "",
        ]
    )
    pd_ip = [row for row in primary if row["contrast"] in {"P-D", "I-P"} and row["dataset_key"] in INFERENTIAL_DATASETS]
    equivalent_count = sum(row["equivalent"] is True for row in pd_ip)
    gain_excluded_count = sum(row["meaningful_gain_excluded"] is True for row in pd_ip)
    directional_improvements = sum(row["ci95_bca_low"] != "" and row["ci95_bca_low"] > 0 for row in pd_ip)
    directional_harms = sum(row["ci95_bca_high"] != "" and row["ci95_bca_high"] < 0 for row in pd_ip)
    sections.extend(
        [
            f"- Across the {len(pd_ip)} formal P-D and I-P comparisons, {equivalent_count} satisfy the +/-0.50-point practical-equivalence criterion and {gain_excluded_count} exclude a gain of at least 0.50 points.",
            f"- The paired 95% BCa intervals show {directional_improvements} projection/iteration improvements and {directional_harms} deteriorations; the remaining comparisons are directionally inconclusive.",
            "- D-R measures the full effect of presenting word-boundary-aware input. P-D and I-P isolate the incremental effects of projected boundaries and another iteration, respectively.",
            "- Results are estimated separately by model and dataset. CEFE Track 3 (n=19) is retained only as a descriptive diagnostic.",
            "- Sentence resampling preserves pairing across all four conditions and metrics. Document/learner cluster identifiers were unavailable, so the intervals do not account for within-document dependence.",
            "- Boundary-change subset analyses, proximity to fixed gold-informed boundaries, correction-span overlap, convergence, calls, and token totals are reported in the accompanying CSV files.",
            "",
            "### Interpretation by model",
            "",
            "- DeepSeek benefits clearly from Direct WB-aware prompting on NLPCC2018, MuCGEC, YACLC, FCGEC, and NaSGEC-Exam, but the projected and iterative stages are mostly equivalent to their preceding stages. The clearest later-stage exception is NaCGEC: P-D improves by 0.28 points, followed by a 0.20-point I-P deterioration.",
            "- Kimi does not reproduce the broad Direct gains: D-R improves on MuCGEC, is inconclusive on NLPCC2018 and YACLC, and deteriorates on FlaCGEC, FCGEC, NaCGEC, and NaSGEC-Exam. Kimi FlaCGEC P-D is the main positive projection exception (+0.67 points; 95% BCa interval +0.19 to +1.20).",
            "- Raw character GLEU is higher than Direct on 5/8 DeepSeek datasets and all 8/8 Kimi datasets. This metric-level disagreement with edit F0.5 supports reporting both correction accuracy and overall n-gram similarity rather than treating either metric as sufficient alone.",
            "",
            "### Robustness check",
            "",
        ]
    )
    primary_robustness = [row for row in primary if row.get("percentile_conclusion_differs") is True]
    secondary_robustness = [row for row in secondary if row.get("percentile_conclusion_differs") is True]
    equivalence_robustness = [row for row in primary if row.get("percentile_equivalence_differs") is True]
    if primary_robustness:
        details = "; ".join(
            f"{row['model']} {row['dataset']} {row['contrast']} (BCa {row['ci95_bca_low']:+.3f} to {row['ci95_bca_high']:+.3f}; percentile {row['ci95_percentile_low']:+.3f} to {row['ci95_percentile_high']:+.3f})"
            for row in primary_robustness
        )
        sections.append(
            f"- One primary directional conclusion is sensitive to interval construction: {details}. Both upper endpoints are near zero, so this should be described as a small, directionally fragile effect."
        )
    else:
        sections.append("- No primary directional conclusion changes between BCa and percentile intervals.")
    sections.append(
        f"- {len(secondary_robustness)} exploratory secondary-metric directional conclusions differ between BCa and percentile intervals; both intervals and word-GLEU source policies are recorded in `bootstrap_secondary.csv`."
    )
    if equivalence_robustness:
        details = "; ".join(
            f"{row['model']} {row['dataset']} {row['contrast']} (BCa 90% {row['ci90_bca_low']:+.3f} to {row['ci90_bca_high']:+.3f}; percentile 90% {row['ci90_percentile_low']:+.3f} to {row['ci90_percentile_high']:+.3f})"
            for row in equivalence_robustness
        )
        sections.append(
            f"- {len(equivalence_robustness)} primary practical-equivalence conclusion is interval-sensitive: {details}. The pre-specified BCa result is retained, but the boundary-margin conclusion should be described as fragile."
        )
    else:
        sections.append("- No primary practical-equivalence conclusion changes between BCa and percentile 90% intervals.")
    sections.extend(
        [
            "",
            "## Boundary intervention and cost",
            "",
        ]
    )
    for model in models:
        model_boundaries = [row for row in boundary_rows if row["model"] == model.display]
        model_cost = [row for row in convergence_rows if row["model"] == model.display]
        for contrast in ("P-D", "I-P"):
            selected = [row for row in model_boundaries if row["contrast"] == contrast]
            changed = sum(row["changed_boundary_sentences"] for row in selected)
            total_sentences = sum(row["sentences"] for row in selected)
            output_changes = sum(row["changed_subset_output_changes"] for row in selected)
            closer = sum(row["boundary_f1_closer_sentences"] for row in selected)
            farther = sum(row["boundary_f1_farther_sentences"] for row in selected)
            overlap = sum(row["correction_relevant_overlap_positions"] for row in selected)
            positions = sum(row["changed_boundary_positions"] for row in selected)
            sections.append(
                f"- {model.display} {contrast}: normalized boundaries changed for {changed:,}/{total_sentences:,} sources ({changed / total_sentences * 100:.2f}%); "
                f"{output_changes:,}/{changed:,} changed-boundary sources produced a different correction ({output_changes / changed * 100:.2f}%); "
                f"{closer:,} moved closer to and {farther:,} moved farther from the fixed gold-informed boundaries. "
                f"Correction-relevant gold spans covered {overlap:,}/{positions:,} changed boundary positions ({overlap / positions * 100:.2f}%)."
            )
        direct_calls = sum(row["direct_calls"] for row in model_cost)
        added_calls = sum(row["projection_calls_added_total"] for row in model_cost)
        token_total = sum(row["total_tokens_all_conditions"] for row in model_cost)
        whitespace_recalls = sum(
            row["normalized_unchanged_but_projected_recalled"]
            + row["normalized_unchanged_but_iterative_recalled"]
            for row in model_cost
        )
        format_retries = sum(row["format_retries"] for row in model_cost)
        filter_fallbacks = sum(row["content_filter_identity_fallbacks"] for row in model_cost)
        sections.append(
            f"- {model.display} required {added_calls:,} projected/iterative calls beyond {direct_calls:,} Direct calls "
            f"({added_calls / direct_calls * 100:.2f}% extra) and recorded {token_total:,} tokens across Raw through Iterative. "
            f"The saved metadata records {format_retries:,} format retries and {filter_fallbacks:,} content-filter identity fallbacks. "
            f"The historical outputs contain {whitespace_recalls} calls triggered only by whitespace formatting despite an unchanged normalized boundary vector; future runs now stop on the normalized signature."
        )
    sections.extend(
        [
            "",
            "## Reproducibility and interpretation",
            "",
            "The primary outcome is corpus micro-F0.5, recomputed from pooled TP/FP/FN in every resample rather than averaging sentence F-scores. Character and word GLEU select the best complete reference independently at sentence level and are secondary outcomes. A confidence interval crossing zero is not described as evidence of no difference; equivalence is claimed only from the 90% interval and the frozen practical margin.",
            "",
            "The fixed word-M2 sources and boundary-diagnostic comparison segmentations are gold-informed proxies, not manually annotated gold word boundaries. Word GLEU uses the separately declared source policy above. Changed-boundary analyses are diagnostic because their subset is selected by the intervention. API-call randomness is not represented because only one decoded output exists for each condition.",
            "",
            "## Files",
            "",
            "- `table_2_dataset_statistics.tsv`: verified dataset counts.",
            "- `table_3_model_configuration.tsv`: model and decoding configuration.",
            "- `sentence_level_scores.tsv`: per-model, per-source, per-condition counts and scores.",
            "- `bootstrap_primary.csv`: character F0.5 contrasts and BCa intervals.",
            "- `bootstrap_secondary.csv`: word F0.5 and character/word GLEU intervals.",
            "- `equivalence_sensitivity.csv`: +/-0.25, +/-0.50, and +/-1.00 analyses.",
            "- `changed_boundary_diagnostics.csv`: intervention coverage and alignment diagnostics.",
            "- `convergence_and_cost.csv`: stopping, calls, tokens, and efficiency.",
            "- `scorer_selection_audit.tsv`: sentence-local versus legacy corpus-greedy selection.",
            "- `word_gleu_source_audit.tsv`: policy, completion metadata, and exported source-boundary validation.",
            "- `validation.log`: integrity and reproducibility checks.",
            "",
        ]
    )
    return "\n".join(sections)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--model-config",
        type=Path,
        help="JSON ModelSpec object/list; analyze only declared models, without implicitly loading historical models",
    )
    parser.add_argument(
        "--word-gleu-source-policy",
        choices=SOURCE_POLICIES,
        help="built-in models only: condition (default) or explicit fixed-gold historical reproduction",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="analysis directory; built-ins choose a policy-specific default, custom configs require a separate directory",
    )
    parser.add_argument("--seed", type=int, default=20260915)
    parser.add_argument("--replicates", type=int, default=50000)
    parser.add_argument("--chunk-size", type=int, default=1000)
    return parser.parse_args(argv)


def analysis_output(args: argparse.Namespace) -> Path:
    if args.model_config is not None and args.word_gleu_source_policy is not None:
        raise ValueError("Declare word_gleu_source_policy in the model config, not with the CLI policy option")
    if args.model_config is not None and args.output is None:
        raise ValueError("--model-config requires --output; custom analyses must not overwrite historical tables")
    default_policy = args.word_gleu_source_policy or "condition"
    default_output = HISTORICAL_OUTPUT if default_policy == "fixed-gold" else DEFAULT_OUTPUT
    output = (args.output or default_output).resolve()
    historical = HISTORICAL_OUTPUT.resolve()
    if (args.model_config is not None or default_policy != "fixed-gold") and (
        output == historical or historical in output.parents
    ):
        raise ValueError(
            f"This analysis requires --output outside the historical analysis directory {historical}; "
            "condition/custom analyses must not overwrite historical tables"
        )
    return output


def validate_output_word_gleu_policy(output: Path, models: Sequence[ModelSpec]) -> None:
    path = output / "analysis_config.json"
    expected = {model.key: model.word_gleu_source_policy for model in models}
    if not path.is_file():
        unversioned = any(
            (output / name).exists()
            for name in ("sentence_level_scores.tsv", "bootstrap_primary.csv", "bootstrap_secondary.csv")
        )
        if unversioned and set(expected.values()) != {"fixed-gold"}:
            raise ValueError(f"{output}: unversioned analysis artifacts; choose a separate output directory")
        return
    previous = json.loads(path.read_text(encoding="utf-8"))
    segmentation = previous.get("word_gleu_segmentation", {}) if isinstance(previous, dict) else {}
    policies = segmentation.get("source_policy_by_model") if isinstance(segmentation, dict) else None
    if policies is None:
        if set(expected.values()) == {"fixed-gold"}:
            return
        raise ValueError(f"{output}: previous analysis has no explicit word-GLEU policy; choose a separate output directory")
    if policies != expected:
        raise ValueError(
            f"{output}: analysis word-GLEU policies differ from existing artifacts; "
            "choose a separate output directory rather than mixing or overwriting policies"
        )


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    if args.replicates < 1:
        raise ValueError("--replicates must be positive")
    if args.chunk_size < 1:
        raise ValueError("--chunk-size must be positive")
    output = analysis_output(args)
    custom_models = args.model_config is not None
    datasets = load_datasets()
    models = load_models(
        args.model_config, word_gleu_source_policy=args.word_gleu_source_policy
    )
    validate_output_word_gleu_policy(output, models)
    expected_datasets = {dataset.dataset for dataset in datasets}
    for model in models:
        missing = expected_datasets - set(model.run_names)
        extra = set(model.run_names) - expected_datasets
        if missing or extra:
            raise ValueError(
                f"{model.key}: run_names coverage mismatch: missing={sorted(missing)}, extra={sorted(extra)}"
            )
    statistics = build_dataset_statistics(datasets)
    actual_total = {
        "sentences": sum(row["sentences"] for row in statistics),
        "references": sum(row["references"] for row in statistics),
        "multi_reference_sentences": sum(row["multi_reference_sentences"] for row in statistics),
        "sentences_over_3_references": sum(row["sentences_over_3_references"] for row in statistics),
        "max_references": max(row["max_references"] for row in statistics),
    }
    if actual_total != EXPECTED_DATASET_TOTALS:
        raise ValueError(f"Dataset-statistics mismatch: {actual_total} != {EXPECTED_DATASET_TOTALS}")
    output.mkdir(parents=True, exist_ok=True)

    table2_fields = [
        "dataset",
        "dataset_key",
        "split",
        "sentences",
        "references",
        "multi_reference_sentences",
        "sentences_over_3_references",
        "max_references",
    ]
    table2_total = {
        "dataset": "Total",
        "dataset_key": "",
        "split": "",
        **actual_total,
    }
    write_rows(
        output / "table_2_dataset_statistics.tsv",
        [*statistics, table2_total],
        table2_fields,
    )
    table2_markdown = markdown_table(
        ["Dataset", "Split", "Sentences", "References", "Multi-ref.", ">3 refs.", "Max refs."],
        [
            (
                row["dataset"],
                row["split"].title(),
                f"{row['sentences']:,}",
                f"{row['references']:,}",
                f"{row['multi_reference_sentences']:,}",
                f"{row['sentences_over_3_references']:,}",
                row["max_references"],
            )
            for row in statistics
        ]
        + [[
            "Total", "", f"{actual_total['sentences']:,}", f"{actual_total['references']:,}",
            f"{actual_total['multi_reference_sentences']:,}", f"{actual_total['sentences_over_3_references']:,}",
            actual_total["max_references"],
        ]],
    )
    (output / "table_2_dataset_statistics.md").write_text(
        "# Table 2. Dataset statistics\n\n"
        + table2_markdown
        + "\n\nStatistics count complete textual references in `gold.para`. "
        "Multi-ref. counts source instances with more than one complete reference.\n",
        encoding="utf-8",
    )
    model_rows = [
        {
            "model": model.display,
            "identifier_version": model.identifier,
            "provider": model.provider,
            "access_date": model.access_date,
            "temperature": model.temperature,
            "top_p": model.top_p,
            "max_output": model.max_output,
            "samples": 1,
            "Kmax": 3,
            "thinking": model.thinking,
            "word_gleu_source_policy": model.word_gleu_source_policy,
        }
        for model in models
    ]
    write_rows(output / "table_3_model_configuration.tsv", model_rows, output_fields(model_rows))
    table3_markdown = markdown_table(
        ["Model", "Identifier/version", "Provider", "Access date", "Temperature", "Top-p", "Max output", "Samples", "Kmax", "Word GLEU source policy"],
        [
            (
                row["model"],
                row["identifier_version"],
                row["provider"],
                row["access_date"],
                row["temperature"],
                row["top_p"],
                row["max_output"],
                row["samples"],
                row["Kmax"],
                row["word_gleu_source_policy"],
            )
            for row in model_rows
        ],
    )
    model_note = "Thinking was disabled for both models; one saved output was evaluated per source and condition."
    if custom_models:
        table3_markdown = configured_model_table(models)
        model_note = (
            "Decoding and reasoning settings are declared per model; provider defaults are not assumed to disable reasoning "
            "or imply numeric caps. One saved output is evaluated per source and condition."
        )
    (output / "table_3_model_configuration.md").write_text(
        "# Table 3. Model and inference configuration\n\n"
        + table3_markdown
        + "\n\n" + model_note + "\n",
        encoding="utf-8",
    )
    latex_rows = [
        " & ".join(
            [
                row["dataset"],
                row["split"].title(),
                f"{row['sentences']:,}",
                f"{row['references']:,}",
                f"{row['multi_reference_sentences']:,}",
                f"{row['sentences_over_3_references']:,}",
                str(row["max_references"]),
            ]
        )
        + r" \\"
        for row in statistics
    ]
    model_latex_rows = [
        r"DeepSeek & \texttt{deepseek-v4-pro} & DeepSeek & 2026-07-16--19 & $10^{-6}$ & default & 8,192 tokens (default) & 1 & 3 \\",
        r"Kimi & \texttt{kimi-k2.6} & Moonshot AI & 2026-08-30--31 & 0.6 fixed & default & 512 tokens & 1 & 3 \\",
    ]
    model_latex_columns = "llllllllrl"
    model_latex_header = r"Model & Identifier & Provider & Access date & Temp. & Top-$p$ & Max output & Samples & $K_{\max}$ & Word GLEU source \\"
    model_latex_caption = "Model and inference configuration. Thinking was disabled for both models. Word-M2 sources remain fixed-gold independently of word GLEU."
    if custom_models:
        model_latex_rows = configured_model_latex_rows(models)
        model_latex_columns = "llllllllrrl"
        model_latex_header = r"Model & Identifier & Provider & Access date & Temp. & Top-$p$ & Max output & Reasoning & Samples & $K_{\max}$ & Word GLEU source \\"
        model_latex_caption = "Model and declared inference configuration. Reasoning and provider-default settings are reported as configured. Word-M2 sources remain fixed-gold independently of word GLEU."
    else:
        model_latex_rows = [
            row.removesuffix(r" \\") + " & " + latex_escape(model.word_gleu_source_policy) + r" \\"
            for row, model in zip(model_latex_rows, models)
        ]
    latex = "\n".join(
        [
            r"\begin{table*}[t]",
            r"\centering",
            r"\small",
            r"\begin{tabular}{llrrrrr}",
            r"\toprule",
            r"Dataset & Split & Sentences & References & Multi-ref. & $>3$ refs. & Max refs. \\",
            r"\midrule",
            *latex_rows,
            r"\midrule",
            " & ".join(
                [
                    "Total", "", f"{actual_total['sentences']:,}", f"{actual_total['references']:,}",
                    f"{actual_total['multi_reference_sentences']:,}", f"{actual_total['sentences_over_3_references']:,}",
                    str(actual_total["max_references"]),
                ]
            ) + r" \\",
            r"\bottomrule",
            r"\end{tabular}",
            r"\caption{Dataset statistics. References count complete textual corrections.}",
            r"\label{tab:dataset_statistics}",
            r"\end{table*}",
            "",
            r"\begin{table*}[t]",
            r"\centering",
            r"\small",
            r"\begin{tabular}{" + model_latex_columns + "}",
            r"\toprule",
            model_latex_header,
            r"\midrule",
            *model_latex_rows,
            r"\bottomrule",
            r"\end{tabular}",
            r"\caption{" + model_latex_caption + "}",
            r"\label{tab:model_configuration}",
            r"\end{table*}",
            "",
        ]
    )
    (output / "PAPER_TABLES.tex").write_text(latex, encoding="utf-8")
    (output / "analysis_config.json").write_text(
        json.dumps(config_payload(args, models), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    blocks: list[BlockData] = []
    audit_rows: list[dict[str, Any]] = []
    word_gleu_audit: list[dict[str, Any]] = []
    for model in models:
        validate_word_gleu_metadata(model)
        char_gleu = load_gleu(model.char_gleu, datasets)
        word_gleu = load_gleu(model.word_gleu, datasets)
        validate_gleu_summary(model, "character", char_gleu)
        validate_gleu_summary(model, "word", word_gleu)
        for dataset in datasets:
            print(f"loading {model.display}/{DISPLAY_NAMES[dataset.dataset]}", flush=True)
            block, audit = load_block(model, dataset, char_gleu, word_gleu)
            blocks.append(block)
            audit_rows.extend(audit)
            word_gleu_audit.extend(block.word_gleu_source_audit)
    write_rows(output / "scorer_selection_audit.tsv", audit_rows, output_fields(audit_rows))
    write_rows(output / "word_gleu_source_audit.tsv", word_gleu_audit, output_fields(word_gleu_audit))

    export_fields = list(next(iter(sentence_export_rows(blocks[0]))))
    export_path = output / "sentence_level_scores.tsv"
    with export_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=export_fields, delimiter="\t")
        writer.writeheader()
        for block in blocks:
            writer.writerows(sentence_export_rows(block))

    primary_rows: list[dict[str, Any]] = []
    secondary_rows: list[dict[str, Any]] = []
    sensitivity_rows: list[dict[str, Any]] = []
    boundary_rows: list[dict[str, Any]] = []
    convergence_rows: list[dict[str, Any]] = []
    for block in blocks:
        inferential = block.dataset.dataset in INFERENTIAL_DATASETS
        print(f"bootstrapping {block.model.display}/{DISPLAY_NAMES[block.dataset.dataset]}", flush=True)
        draws = (
            bootstrap_block(
                block,
                replicates=args.replicates,
                seed=args.seed,
                chunk_size=args.chunk_size,
            )
            if inferential
            else {metric: {name: None for name, _early, _late in CONTRASTS} for metric in ("character_f05", "word_f05", "character_gleu", "word_gleu")}
        )
        for contrast in CONTRASTS:
            primary = interval_record(
                block,
                "character_f05",
                contrast,
                draws["character_f05"][contrast[0]],
                replicates=args.replicates,
                seed=args.seed,
            )
            primary_rows.append(primary)
            for metric in ("word_f05", "character_gleu", "word_gleu"):
                secondary_rows.append(
                    interval_record(
                        block,
                        metric,
                        contrast,
                        draws[metric][contrast[0]],
                        replicates=args.replicates,
                        seed=args.seed,
                    )
                )
            if inferential and contrast[0] in {"P-D", "I-P"}:
                for margin in SENSITIVITY_MARGINS:
                    equivalent, gain_excluded, interpretation = interpretation_for_margin(
                        float(primary["ci90_bca_low"]),
                        float(primary["ci90_bca_high"]),
                        float(primary["ci95_bca_low"]),
                        float(primary["ci95_bca_high"]),
                        margin,
                    )
                    sensitivity_rows.append(
                        {
                            "model": primary["model"],
                            "dataset": primary["dataset"],
                            "dataset_key": primary["dataset_key"],
                            "contrast": primary["contrast"],
                            "metric": "character_f05",
                            "delta_points": primary["delta_points"],
                            "ci90_bca_low": primary["ci90_bca_low"],
                            "ci90_bca_high": primary["ci90_bca_high"],
                            "ci95_bca_low": primary["ci95_bca_low"],
                            "ci95_bca_high": primary["ci95_bca_high"],
                            "equivalence_margin": margin,
                            "equivalent": equivalent,
                            "meaningful_gain_excluded": gain_excluded,
                            "interpretation": interpretation,
                        }
                    )
        boundary_rows.extend(
            boundary_diagnostics(
                block,
                replicates=args.replicates,
                seed=args.seed,
                chunk_size=args.chunk_size,
                descriptive_only=custom_models and not inferential,
            )
        )
        convergence_rows.append(convergence_record(block))

    write_rows(output / "bootstrap_primary.csv", primary_rows, output_fields(primary_rows))
    write_rows(output / "bootstrap_secondary.csv", secondary_rows, output_fields(secondary_rows))
    write_rows(output / "equivalence_sensitivity.csv", sensitivity_rows, output_fields(sensitivity_rows))
    write_rows(output / "changed_boundary_diagnostics.csv", boundary_rows, output_fields(boundary_rows))
    write_rows(output / "convergence_and_cost.csv", convergence_rows, output_fields(convergence_rows))

    validation: list[str] = []
    validation.append("PASS dataset totals: " + json.dumps(actual_total, sort_keys=True))
    validation.append(
        "PASS exact gold-reference text/count/order across character and word M2: "
        f"{sum(block.validated_reference_blocks for block in blocks):,} blocks; "
        f"{sum(block.validated_references for block in blocks):,} references"
    )
    validation.append(f"PASS sentence-level export rows: {sum(block.dataset.rows for block in blocks) * 4}")
    if any(np.any(block.char_counts < 0) or np.any(block.word_counts < 0) for block in blocks):
        raise ValueError("negative edit count")
    validation.append("PASS all TP/FP/FN values are nonnegative integers")
    if any(np.any((block.char_gleu < 0) | (block.char_gleu > 1)) or np.any((block.word_gleu < 0) | (block.word_gleu > 1)) for block in blocks):
        raise ValueError("GLEU scale mismatch")
    validation.append("PASS all GLEU values use the [0,1] storage scale")
    validation.append("PASS cached character- and word-GLEU corpus summaries reproduced from sentence scores")
    validation.append("PASS word M2 retains shared fixed-gold source boundaries across all stages, independently of word GLEU")
    for model in models:
        selected = [row for row in word_gleu_audit if row["model_key"] == model.key]
        source_rows = sum(row["validated_sentences"] for row in selected)
        validation.append(
            f"PASS {model.display} word-GLEU policy={model.word_gleu_source_policy}: "
            f"completion and source boundaries validated for {len(selected)} files / {source_rows:,} rows"
        )
        legacy_rows = sum(row["legacy_unlabeled_sentences"] for row in selected)
        if any(row["metadata_format"] == "legacy-fixed" for row in selected):
            validation.append(
                f"SKIP {model.display} new-format word-GLEU status/policy metadata: explicitly selected "
                f"identifiable legacy fixed-gold config with completed_utc; {legacy_rows:,} unlabeled sentence rows"
            )
    historical_whitespace_recalls = 0
    for block in blocks:
        for stage_index, stage in enumerate(STAGES):
            condition = CONDITIONS[stage_index]
            if condition in {"P", "I"}:
                previous = CONDITIONS[stage_index - 1]
                for index in range(block.dataset.rows):
                    same_vector = boundary_positions(block.boundaries[condition][index]) == boundary_positions(block.boundaries[previous][index])
                    called = block.call_counts[index, stage_index] == 1
                    if same_vector and called:
                        historical_whitespace_recalls += 1
                    if same_vector and not called and block.outputs[stage][index] != block.outputs[STAGES[stage_index - 1]][index]:
                        raise ValueError(
                            f"unchanged boundary did not carry output: {block.model.key}/{block.dataset.dataset}/{index}/{stage}"
                        )
    validation.append("PASS unchanged projected boundaries carry the preceding correction by construction")
    if custom_models:
        validation.append(
            f"INFO configured-run calls after a normalized-unchanged boundary vector: {historical_whitespace_recalls}"
        )
        validation.append(
            "SKIP frozen historical-model run invariants: custom model configuration; only declared runs were loaded and validated"
        )
    else:
        validation.append(
            f"INFO historical calls made after a normalized-unchanged boundary vector: {historical_whitespace_recalls}; future runs now compare normalized boundary signatures"
        )
        kimi_blocks = [block for block in blocks if block.model.key == "kimi"]
        kimi_total = sum(block.dataset.rows for block in kimi_blocks)
        kimi_direct = sum(int(np.sum((block.call_counts[:, 2] == 0) & (block.call_counts[:, 3] == 0))) for block in kimi_blocks)
        kimi_projected = sum(int(np.sum((block.call_counts[:, 2] == 1) & (block.call_counts[:, 3] == 0))) for block in kimi_blocks)
        kimi_iterative = sum(int(np.sum(block.call_counts[:, 3] == 1)) for block in kimi_blocks)
        kimi_added = sum(int(block.call_counts[:, 2:].sum()) for block in kimi_blocks)
        if (kimi_total, kimi_direct, kimi_projected, kimi_iterative, kimi_added) != (20213, 18487, 1432, 294, 2020):
            raise ValueError(
                "Kimi invariant mismatch: "
                f"{(kimi_total, kimi_direct, kimi_projected, kimi_iterative, kimi_added)}"
            )
        validation.append("PASS Kimi invariants: N=20,213; stop D=18,487; stop P=1,432; reach I=294; added calls=2,020")
    selection_changes = sum(abs(float(row["delta_sentence_minus_legacy"])) >= 0.005 for row in audit_rows)
    for policy, count in sorted(Counter(row["cached_selector_policy"] for row in audit_rows).items()):
        label = "legacy corpus-greedy" if policy == "corpus" else "sentence-local"
        validation.append(f"PASS {label} mode reproduces all {count} cached M2 table cells")
    validation.append(
        f"PASS scorer audit completed: sentence-local selection changes {selection_changes} of {len(audit_rows)} displayed model/dataset/stage/unit scores"
    )
    validation.append(
        "INFO percentile robustness: "
        f"primary_direction={sum(row.get('percentile_conclusion_differs') is True for row in primary_rows)}, "
        f"primary_equivalence={sum(row.get('percentile_equivalence_differs') is True for row in primary_rows)}, "
        f"secondary_direction={sum(row.get('percentile_conclusion_differs') is True for row in secondary_rows)}"
    )
    settings_status = "INFO" if custom_models else "PASS"
    validation.extend(
        [
            f"{settings_status} bootstrap seed: {args.seed}",
            f"{settings_status} bootstrap replicates: {args.replicates}",
            "PASS paired 95% and 90% BCa intervals plus percentile robustness intervals generated",
            f"INFO Python {platform.python_version()}",
            f"INFO NumPy {np.__version__}",
            "INFO SciPy " + __import__("scipy").__version__,
            "INFO no reliable document/learner IDs were available; source-sentence bootstrap used",
        ]
    )
    if custom_models:
        validation.append("PASS CEFE Track 3 is descriptive only, including boundary subsets")
        design_status = "PASS" if frozen_analysis_design(args) else "NONSTANDARD"
        validation.append(
            f"{design_status} frozen analysis design (replicates=50000, seed=20260915, chunk=1000); "
            f"actual replicates={args.replicates}, seed={args.seed}, chunk={args.chunk_size}"
        )
    (output / "validation.log").write_text("\n".join(validation) + "\n", encoding="utf-8")
    report_builder = build_configured_report if custom_models else build_paper_report
    report = report_builder(
        statistics,
        models,
        blocks,
        primary_rows,
        secondary_rows,
        sensitivity_rows,
        boundary_rows,
        convergence_rows,
        **({"args": args} if custom_models else {}),
    )
    (output / "PAPER_TABLES_AND_ANALYSIS.md").write_text(report, encoding="utf-8")
    checklist = """# README analysis compliance

| Requirement | Status | Evidence |
| --- | --- | --- |
| Freeze seed, replicates, scale, margins, contrasts, and inferential datasets | Complete | `analysis_config.json` |
| Reuse complete saved R/D/P/I outputs without post-hoc exclusions | Complete | `sentence_level_scores.tsv` and `validation.log` |
| Preserve identical complete gold references and annotator order across character/word M2 | Complete | `validation.log` |
| Sentence-local select-best for complete edit references | Complete | `scripts/movement_aware_compare.py` and `scorer_selection_audit.tsv` |
| Independent character/word GLEU select-best | Complete | `sentence_level_scores.tsv` and cached-summary validation |
| Paired source-level resampling with corpus micro-F0.5 | Complete | `bootstrap_primary.csv` and `bootstrap_secondary.csv` |
| 50,000 paired 95%/90% BCa intervals | Complete | bootstrap CSV files |
| Ordinary percentile robustness check | Complete | bootstrap CSV flags and paper report |
| Practical equivalence at +/-0.50 with +/-0.25 and +/-1.00 sensitivity | Complete | `equivalence_sensitivity.csv` |
| CEFE Track 3 treated descriptively | Complete | bootstrap CSV files |
| Boundary coverage, split/merge direction, changed-output, changed-subset performance | Complete | `changed_boundary_diagnostics.csv` |
| Proximity to fixed gold-informed boundaries | Complete | `changed_boundary_diagnostics.csv` |
| Overlap with correction-relevant spans | Complete | `changed_boundary_diagnostics.csv` |
| Convergence, calls, tokens, and efficiency | Complete | `convergence_and_cost.csv` |
| Reproducibility and software versions | Complete | `analysis_config.json` and `validation.log` |

## Recorded limitations

- No reliable document, essay, or learner cluster identifiers are available, so the independent resampling unit is the source sentence.
- Only one saved decode exists per model, source, and condition; the intervals do not quantify repeated-API sampling variability.
- Provider pricing snapshots were not archived, so monetary costs are not compared. Calls and recorded tokens are reported instead.
- DeepSeek omitted `max_tokens`, so the documented 8,192-token non-thinking default applied; its longest saved completion was 200 tokens. Kimi's longest saved completion was 259 of its 512-token cap. Historical finish reasons were not stored, but the observed completion counts remain well below both caps, and the evaluation code performs no post-hoc truncation.
- Five historical calls were triggered by whitespace-only segmentation formatting despite unchanged normalized boundary vectors. Those outputs remain in the faithful analysis, while future pipeline runs now use normalized boundary signatures for convergence.
- The supplied draft's cached M2 scores use the historical corpus-greedy reference selector. They are exactly reproducible, but 10/128 displayed cells change under the README-required sentence-local selector; corrected values are in the paper report.
"""
    if custom_models:
        checklist = build_configured_compliance(args, audit_rows, models)
    else:
        checklist += "\n" + word_gleu_policy_report(models) + "\n"
    (output / "README_ANALYSIS_COMPLIANCE.md").write_text(checklist, encoding="utf-8")
    print(f"analysis complete: {output}", flush=True)


if __name__ == "__main__":
    main()
