#!/usr/bin/env python3
"""Score the selected-gold MuCGEC dev experiment without resegmenting its targets."""

from __future__ import annotations

import argparse
import importlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

try:
    from evaluation_segmentation import LtpSegmentationCache
    from movement_aware_compare import _f_score_unrounded, evaluate, parse_file
    from projection_character_m2 import (
        TwoStepCharacterAligner, render_m2_block, targets_from_m2_block,
    )
    from projection_word_m2 import (
        projection_word_edits_from_character_edits, render_word_m2_block,
        targets_from_word_m2_block,
    )
    from run_gold_reference_experiment import (
        CONDITIONS, DEFAULT_RUN, DEFAULT_SHAPE, DEFAULT_WB, MODELS, ROOT,
        atomic_json, file_hash, identity_hash, load_prepared, raw_text, read_json,
        request_spec, utc_now, write_tsv,
    )
    from run_projection_m2_evaluation import CachedConverter, PairCache
except ModuleNotFoundError:
    from scripts.evaluation_segmentation import LtpSegmentationCache
    from scripts.movement_aware_compare import _f_score_unrounded, evaluate, parse_file
    from scripts.projection_character_m2 import (
        TwoStepCharacterAligner, render_m2_block, targets_from_m2_block,
    )
    from scripts.projection_word_m2 import (
        projection_word_edits_from_character_edits, render_word_m2_block,
        targets_from_word_m2_block,
    )
    from scripts.run_gold_reference_experiment import (
        CONDITIONS, DEFAULT_RUN, DEFAULT_SHAPE, DEFAULT_WB, MODELS, ROOT,
        atomic_json, file_hash, identity_hash, load_prepared, raw_text, read_json,
        request_spec, utc_now, write_tsv,
    )
    from scripts.run_projection_m2_evaluation import CachedConverter, PairCache


METRICS = (
    "character_precision", "character_recall", "character_f05", "character_gleu",
    "word_precision", "word_recall", "word_f05", "word_gleu",
)


def load_predictions(
    run: Path, model: str, rows: list[dict[str, Any]], prepared_hash: str,
) -> list[dict[str, Any]]:
    directory = run / model
    status = read_json(directory / "status.json")
    path = directory / "predictions.jsonl"
    if status["status"] != "completed" or status["rows"] != len(rows):
        raise ValueError(f"{model}: all R/D/P rows must be completed before final evaluation")
    if status["predictions_sha256"] != file_hash(path):
        raise ValueError(f"{model}: prediction hash mismatch")
    config = read_json(directory / "generation_config.json")
    if config["prepared_sha256"] != prepared_hash:
        raise ValueError(f"{model}: prepared-input lineage mismatch")
    if any(config.get(key) != value for key, value in MODELS[model].items()):
        raise ValueError(f"{model}: historical model settings changed")
    with path.open(encoding="utf-8") as stream:
        predictions = [json.loads(line) for line in stream]
    if len(predictions) != len(rows):
        raise ValueError(f"{model}: prediction count mismatch")
    for row, prediction in zip(rows, predictions):
        for key in ("id", "target_id", "source", "target"):
            if prediction[key] != row[key]:
                raise ValueError(f"{model}: prediction order or {key} mismatch")
        for condition in CONDITIONS:
            value = prediction[condition]
            if not isinstance(value, str) or not value or raw_text(value) != value:
                raise ValueError(f"{model}: invalid {condition} prediction")
            receipt = read_json(directory / "requests" / f"{row['id']}.{condition}.json")
            if (
                receipt["status"] != "completed" or receipt["prediction"] != value
                or receipt["request"] != request_spec(row, condition, identity_hash(config))
                or receipt["meta"] != prediction["meta"][condition]
            ):
                raise ValueError(f"{model}: prediction/request-receipt mismatch")
            should_carry = condition == "P" and row["carry_P_from_D"]
            if should_carry != (receipt["meta"].get("carried_from") == "D"):
                raise ValueError(f"{model}: carry-forward provenance mismatch")
            if should_carry and value != prediction["D"]:
                raise ValueError(f"{model}: converged P must equal D")
    return predictions


def load_saved_segmentations(
    path: Path, *, prepared_hash: str, prediction_hashes: dict[str, str],
    predictions: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, str], dict[str, Any]]:
    bundle = read_json(path)
    if not isinstance(bundle, dict) or bundle.get("schema") != "ltp-output-segmentations-v1":
        raise ValueError("Unsupported saved segmentation bundle")
    if bundle.get("prepared_sha256") != prepared_hash:
        raise ValueError("Saved segmentations have different prepared inputs")
    if bundle.get("prediction_sha256") != prediction_hashes:
        raise ValueError("Saved segmentations have different prediction files")
    model = bundle.get("model")
    if not isinstance(model, dict) or any(
        not isinstance(model.get(key), str) or not model[key].strip()
        for key in ("model_id", "model_revision", "ltp_version", "python_version")
    ):
        raise ValueError("Saved segmentations require explicit model and runtime provenance")
    if type(model.get("batch_size")) is not int or model["batch_size"] < 1:
        raise ValueError("Saved segmentations require a positive batch size")
    expected_texts = {
        row[condition] for rows in predictions.values()
        for row in rows for condition in CONDITIONS
    }
    segmented = bundle.get("segmentations")
    if not isinstance(segmented, dict) or set(segmented) != expected_texts:
        raise ValueError("Saved segmentations must cover exactly every unique output text")
    for text, value in segmented.items():
        if (
            not isinstance(value, str) or not value or value != " ".join(value.split())
            or "\ufeff" in value or raw_text(value) != text
        ):
            raise ValueError("Saved segmentation changed output text or has invalid separators")
    return segmented, model


def render_pair(
    row: dict[str, Any], target: str, target_segmented: str, edits: Any,
) -> tuple[str, str]:
    character_block = render_m2_block(row["source"], [(target, edits)])
    word_edits = projection_word_edits_from_character_edits(
        row["P_input"], target_segmented, edits, l_max=3,
    )
    word_block = render_word_m2_block(row["P_input"], [(target_segmented, word_edits)])
    source, reconstructed = targets_from_m2_block(character_block)
    if source != row["source"] or reconstructed != {0: target}:
        raise ValueError("Serialized character M2 did not reconstruct its target")
    source_tokens, reconstructed_tokens = targets_from_word_m2_block(word_block)
    if source_tokens != tuple(row["P_input"].split()) or reconstructed_tokens != {
        0: tuple(target_segmented.split())
    }:
        raise ValueError("Serialized word M2 did not reconstruct its target tokens")
    return character_block, word_block


def save_blocks(directory: Path, name: str, blocks: list[tuple[str, str]]) -> dict[str, Path]:
    paths = {}
    for index, unit in enumerate(("character", "word")):
        path = directory / f"{name}.{unit}.m2"
        path.write_text("\n\n".join(block[index] for block in blocks) + "\n", encoding="utf-8")
        paths[unit] = path
    return paths


def score_m2(hypothesis: Path, reference: Path, unit: str) -> tuple[dict[str, Any], list[dict]]:
    counts, categories, selections = evaluate(
        parse_file(hypothesis, unit=unit), parse_file(reference, unit=unit),
        beta=0.5, selection_mode="sentence",
    )
    precision, recall, score = _f_score_unrounded(
        counts["tp"], counts["fp"], counts["fn"], 0.5
    )
    return {
        f"{unit}_precision": precision * 100, f"{unit}_recall": recall * 100,
        f"{unit}_f05": score * 100,
        f"{unit}_tp": counts["tp"], f"{unit}_fp": counts["fp"], f"{unit}_fn": counts["fn"],
        f"{unit}_categories": categories,
    }, selections


def gleu_scores(
    gleu: Any, row: dict[str, Any], condition: str, hypothesis: str, hypothesis_segmented: str,
) -> tuple[float, float, str]:
    # References already have LTP boundaries. Only hypotheses go through LTP here.
    word_source = row["P_input"] if condition == "P" else row["D_input"]
    character_score = float(gleu.calculate_gleu_score(
        row["source"], hypothesis, row["target"], n=4, tokenization="char",
    ))
    word_score = float(gleu.calculate_gleu_score(
        word_source, hypothesis_segmented, row["target_segmented"], n=4, tokenization="word",
    ))
    if not all(math.isfinite(value) and 0 <= value <= 1 for value in (character_score, word_score)):
        raise ValueError("GLEU returned an invalid probability")
    return character_score * 100, word_score * 100, word_source


def differences(scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = {(row["model"], row["condition"]): row for row in scores}
    return [
        {
            "model": model, "comparison": f"P-{baseline}",
            **{metric: index[(model, "P")][metric] - index[(model, baseline)][metric]
               for metric in METRICS},
        }
        for model in MODELS for baseline in ("R", "D")
    ]


def tokenization_audit_records(
    rows: list[dict[str, Any]], predictions: list[dict[str, Any]],
    segmentations: dict[str, str], model: str,
) -> list[dict[str, Any]]:
    records = []
    for row, prediction in zip(rows, predictions):
        for condition in CONDITIONS:
            target = prediction[condition]
            for check, expected_text, expected_tokens in (
                ("exact_reference_text", row["target"], row["target_segmented"]),
                ("unchanged_source_text", row["source"], row["D_input"]),
            ):
                if target == expected_text:
                    records.append({
                        "model": model, "condition": condition, "id": row["id"],
                        "target_id": row["target_id"], "check": check,
                        "expected_segmented": expected_tokens,
                        "hypothesis_segmented": segmentations[target],
                        "boundaries_match": expected_tokens.split() == segmentations[target].split(),
                    })
    return records


def summarize_tokenization_audit(records: list[dict[str, Any]]) -> dict[str, Any]:
    reference = [row for row in records if row["check"] == "exact_reference_text"]
    mismatches = [row for row in reference if not row["boundaries_match"]]
    unchanged = [row for row in records if row["check"] == "unchanged_source_text"]
    return {
        "exact_reference_text_predictions": len(reference),
        "reference_tokenization_mismatch_predictions": len(mismatches),
        "distinct_reference_mismatch_sources": len({row["id"] for row in mismatches}),
        "unchanged_source_predictions": len(unchanged),
        "unchanged_source_tokenization_mismatches": sum(not row["boundaries_match"] for row in unchanged),
        "scope": "Only already-segmented hypotheses with exact reference/source text; no reference resegmentation",
    }


def write_report(
    path: Path, scores: list[dict[str, Any]], deltas: list[dict[str, Any]],
    manifest: dict[str, Any], generation_summary: dict[str, Any],
    tokenization_summary: dict[str, Any],
    segmentation_model: dict[str, Any] | None = None,
) -> None:
    lines = [
        "# MuCGEC dev: first additional selected-gold experiment", "",
        f"**Scope:** {manifest['rows']:,} supplied source/selected-reference pairs; "
        "one reference per source. This is not the MuCGEC test split or a full multi-reference "
        "dev evaluation. Absolute scores should not be compared directly with those settings.", "",
        "**R:** raw source. **D:** LTP(raw source). **P:** existing WB projection from the "
        "CSV's selected Target and its supplied LTP tokens, onto the LTP-segmented raw source. "
        "The human source boundaries are retained only as provenance. Gold target text is never "
        "included in a GEC prompt. P is a gold-informed/oracle-style condition.", "",
        "**Evaluation:** historical projection-derived character/word M2; sentence-local "
        "complete-reference selection (one supplied reference here); linked U-M movements counted "
        "once as WO; L_max_char=L_max_word=3. Word M2 uses the same fixed gold-informed source "
        "segmentation for all conditions. Character GLEU uses characters everywhere. Word GLEU "
        "uses D inputs for R/D and P inputs for P; hypotheses use LTP and references retain their "
        "supplied tokens. No BPE or OpenCC.", "",
        "Condition-source word GLEU can change when source boundaries change even if the "
        "correction text is unchanged. Interpret it alongside character GLEU and both M2 scores.",
        "",
        f"**Convergence:** {manifest['carry_forward_rows']:,} inputs have identical normalized "
        "D/P boundaries. P carries D's output forward for these rows, as in the historical protocol. "
        "R and D are always separately prompted.", "",
        "All metrics are on a 0-100 scale; differences are percentage-point changes computed "
        "before rounding. No significance test or practical-equivalence claim is made here.", "",
    ]
    if segmentation_model is not None:
        lines += [
            "**Evaluation-only resegmentation:** all saved R/D/P outputs use "
            f"`{segmentation_model['model_id']}` at revision "
            f"`{segmentation_model['model_revision']}`, with "
            f"`ltp=={segmentation_model['ltp_version']}` and "
            f"Python {segmentation_model['python_version']}. "
            "No correction model was called again, and no generation input or output was changed.",
            "",
            "**Generation and evaluation are separate:** D_input retains its original "
            "LTP/small boundaries; P_input retains the original projection from the supplied "
            "Target boundaries onto that D_input. The fixed word-M2 source remains P_input, "
            "and word-GLEU source inputs remain D_input for R/D and P_input for P. "
            "This is not a rerun of the generation pipeline with a different LTP model.",
            "",
        ]
    if tokenization_summary["reference_tokenization_mismatch_predictions"]:
        lines += [
            "**Word-metric caveat:** "
            f"{tokenization_summary['reference_tokenization_mismatch_predictions']:,} of "
            f"{tokenization_summary['exact_reference_text_predictions']:,} predictions whose text "
            "exactly equals the selected reference nevertheless have different token boundaries "
            "under the current LTP segmenter. This identifies at least "
            f"{tokenization_summary['distinct_reference_mismatch_sources']:,} distinct affected "
            "source rows. The supplied reference boundaries were retained exactly as requested; "
            "they were not replaced with fresh LTP output. Consequently, word M2 and word GLEU "
            "also reflect this reference/hypothesis tokenization mismatch, not only correction "
            "quality. Character metrics are unaffected by this tokenization disagreement. "
            "This is a partial check using existing hypothesis segmentations, not a retokenization "
            "or consistency claim for all references. See `tokenization_diagnostics.tsv`.", "",
        ]
    elif segmentation_model is not None:
        lines += [
            "**Exact-Target check:** all "
            f"{tokenization_summary['exact_reference_text_predictions']:,} outputs whose text "
            "equals the supplied Target also have exactly the same word boundaries; "
            "there are zero reference/output tokenization mismatches in those cases.",
            "",
        ]
    lines += [
        "The same read-only check compared "
        f"{tokenization_summary['unchanged_source_predictions']:,} unchanged-source predictions "
        "with their saved direct-LTP inputs and found "
        f"{tokenization_summary['unchanged_source_tokenization_mismatches']:,} boundary mismatches.",
        "",
    ]
    if segmentation_model is not None and tokenization_summary["unchanged_source_tokenization_mismatches"]:
        lines += [
            "The unchanged-source comparison above is against the frozen generation-time "
            "D_input, not against a newly tokenized reference. Different evaluation and "
            "generation segmenters can produce these boundary differences even without "
            "a textual correction; actual prompting inputs are deliberately not rewritten.",
            "",
        ]
    for model, label in (("deepseek", "DeepSeek"), ("kimi", "Kimi")):
        lines += [
            f"## {label}", "",
            "| Condition | Char P | Char R | Char F0.5 | Char GLEU | Word P | Word R | Word F0.5 | Word GLEU |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for row in [r for r in scores if r["model"] == model]:
            lines.append("| " + row["condition"] + " | " +
                         " | ".join(f"{row[key]:.2f}" for key in METRICS) + " |")
        for row in [r for r in deltas if r["model"] == model]:
            lines.append("| " + row["comparison"] + " | " +
                         " | ".join(f"{row[key]:+.2f}" for key in METRICS) + " |")
        counts = generation_summary[model]
        lines += [
            "",
            f"Generation: {counts['accepted_api_predictions']:,} accepted API predictions, "
            f"{counts['content_filter_fallbacks']:,} explicit content-filter identity fallbacks, "
            f"and {counts['carried_predictions']:,} D-to-P carry-forwards. Recorded events: "
            f"{counts['format_retries']:,} format retries, "
            f"{counts['truncated_responses']:,} rejected truncated responses, and "
            f"{counts['rate_limited_responses']:,} rate-limit responses.",
            "",
        ]
    lines += [
        "## Generation configuration", "",
        "| Model | Identifier | Temperature | Output cap | Thinking |",
        "|---|---|---|---|---|",
        "| DeepSeek | deepseek-v4-pro | 0.000001, explicit | max_tokens omitted | disabled |",
        "| Kimi | kimi-k2.6 | omitted; historical endpoint fixed 0.6 | 512, explicit | disabled |", "",
        "The original paper prompts and response cleaning are reused. Top-p and seed are omitted. "
        "Every response and request identity is retained locally. The strict runner refuses model "
        "substitution, thinking-parameter removal and non-stop completions. Content-filter identity "
        "fallbacks, if any, are explicitly retained rather than dropping samples.", "",
        "Non-thinking refers to the explicit supported `thinking={\"type\":\"disabled\"}` request "
        "and empty returned reasoning content, not a claim that usage.reasoning_tokens is zero. "
        "Kimi can report a nonzero counter with an empty reasoning_content field; original usage "
        "values are retained, not overwritten.",
        "",
        "## Local artifacts", "",
        "- `../prepared.jsonl`, `../inputs.tsv`, `../{R,D,P}.inputs.txt`: provenance and frozen inputs.",
        "- `../{deepseek,kimi}/predictions.{jsonl,tsv}`: complete ordered predictions.",
        "- `../{deepseek,kimi}/requests/`: per-condition durable receipts and raw provider responses.",
        "- `metrics.tsv`, `deltas.tsv`: unrounded aggregate metrics and P-R/P-D differences.",
        "- `tokenization_diagnostics.tsv`: saved token comparisons for exact-reference/unchanged-source predictions.",
        "- `{deepseek,kimi}/`: hypothesis M2, LTP hypothesis segmentations, GLEU inputs, sentence counts.",
        "- `reference.{character,word}.m2`: common selected-gold references.",
        "- `evaluation_manifest.json`: protocol, implementation fingerprints and artifact hashes.", "",
        "This directory contains restricted learner data and predictions. Keep it local/ignored; "
        "no credentials are stored in these artifacts.", "",
    ]
    if any(value["recovered_response_receipts"] for value in generation_summary.values()):
        lines += [
            "A local validation failure was reconciled using the already saved provider response, "
            "without another API call. The original receipt, configuration and recovery explanation "
            "are preserved under the affected model's `recovery/` directory.", "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")


def generation_accounting(run: Path, model: str, rows: list[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "condition_predictions": len(rows) * 3, "executed_condition_requests": 0,
        "http_responses": 0, "carried_predictions": 0, "format_retries": 0,
        "content_filter_fallbacks": 0, "http_success_responses": 0,
        "accepted_api_predictions": 0, "http_error_responses": 0,
        "truncated_responses": 0, "rate_limited_responses": 0,
        "responses_with_nonzero_reasoning_counter": 0,
        "responses_with_nonempty_reasoning_content": 0,
        "recovered_response_receipts": 0,
    }
    for row in rows:
        for condition in CONDITIONS:
            receipt = read_json(run / model / "requests" / f"{row['id']}.{condition}.json")
            meta = receipt["meta"]
            totals["recovered_response_receipts"] += int("recovered_from_receipt" in receipt)
            if meta.get("carried_from"):
                totals["carried_predictions"] += 1
            else:
                totals["executed_condition_requests"] += 1
                totals["accepted_api_predictions"] += int(
                    not meta.get("content_filter_fallback", False)
                )
            histories = [*receipt.get("previous_failures", []), receipt]
            for history in histories:
                for response in history["responses"]:
                    totals["http_responses"] += 1
                    if response["http_status"] < 400:
                        totals["http_success_responses"] += 1
                        data = response["response"]
                        totals["truncated_responses"] += int(
                            data["choices"][0].get("finish_reason") == "length"
                        )
                        details = (data.get("usage") or {}).get("completion_tokens_details") or {}
                        totals["responses_with_nonzero_reasoning_counter"] += int(
                            bool(details.get("reasoning_tokens", 0))
                        )
                        totals["responses_with_nonempty_reasoning_content"] += int(
                            bool(data["choices"][0]["message"].get("reasoning_content"))
                        )
                    else:
                        totals["http_error_responses"] += 1
                        totals["rate_limited_responses"] += int(response["http_status"] == 429)
            totals["format_retries"] += meta.get("format_retries", 0)
            totals["content_filter_fallbacks"] += int(meta.get("content_filter_fallback", False))
    return totals


def run_evaluation(
    run: Path, output: Path, *, wb_repo: Path, shape_path: Path,
    batch_size: int = 32, ltp_batch_size: int = 64,
    hypothesis_segmentations: Path | None = None,
) -> None:
    rows, manifest = load_prepared(run)
    predictions = {
        model: load_predictions(run, model, rows, manifest["prepared_sha256"]) for model in MODELS
    }
    prediction_hashes = {
        model: file_hash(run / model / "predictions.jsonl") for model in MODELS
    }
    saved_segmentations = None
    segmentation_model = None
    if hypothesis_segmentations is not None:
        saved_segmentations, segmentation_model = load_saved_segmentations(
            hypothesis_segmentations, prepared_hash=manifest["prepared_sha256"],
            prediction_hashes=prediction_hashes, predictions=predictions,
        )
        ltp_batch_size = segmentation_model["batch_size"]
    if batch_size < 1 or ltp_batch_size < 1:
        raise ValueError("Batch sizes must be positive")
    reserved = [run.resolve() / name for name in (*MODELS, "prepared_rows", "implementations")]
    if output.resolve() == run.resolve() or any(
        output.resolve().is_relative_to(path) for path in reserved
    ):
        raise ValueError("Evaluation must not overwrite generation or preparation artifacts")
    output.mkdir(parents=True, exist_ok=True)
    preparation = read_json(run / "preparation_config.json")
    wb_hash = file_hash(
        wb_repo / "src/pipeline/alignment/step2_similarity_alignment_projection.py"
    )
    shape_hash = file_hash(shape_path)
    if wb_hash != preparation["wb_sha256"] or shape_hash != preparation["shape_sha256"]:
        raise ValueError("Evaluation WB/shape dependencies differ from the prepared experiment")
    code_names = (
        "projection_character_m2.py", "projection_word_m2.py", "movement_m2.py",
        "movement_aware_compare.py", "evaluation_segmentation.py",
        "evaluate_gold_reference_experiment.py",
    )
    gleu_path = ROOT / "external_tools/multi-reference-GLEU"
    config = {
        "prepared_sha256": manifest["prepared_sha256"], "reference_scope": preparation["reference_scope"],
        "prediction_sha256": prediction_hashes,
        "code_sha256": {name: file_hash(ROOT / "scripts" / name) for name in code_names},
        "gleu_wrapper_sha256": file_hash(gleu_path / "gleu_wrapper.py"),
        "wb_sha256": wb_hash, "shape_sha256": shape_hash,
        "threshold": 0.85, "l_max_char": 3, "l_max_word": 3, "beta": 0.5,
        "alignment_and_embedding_batch_size": batch_size, "ltp_batch_size": ltp_batch_size,
        "bert_model": "bert-base-chinese",
        "ltp_model": segmentation_model["model_id"] if segmentation_model else "LTP/small",
        "word_m2_source": "fixed P_input across all models and conditions",
        "word_gleu_source": {"R": "D_input", "D": "D_input", "P": "P_input"},
        "target_segmentation": "CSV tokens reused verbatim (whitespace canonicalized)",
        "hypothesis_segmentation": "LTP", "gleu": "1-4 grams; sentence macro-average",
        "multi_reference_selection": "sentence-local complete reference; one supplied reference",
        "model_config_sha256": {
            model: file_hash(run / model / "generation_config.json") for model in MODELS
        },
    }
    if hypothesis_segmentations is not None:
        config["saved_hypothesis_segmentations"] = {
            "sha256": file_hash(hypothesis_segmentations), "model": segmentation_model,
        }
    config_path = output / "evaluation_config.json"
    if config_path.exists() and read_json(config_path) != config:
        raise ValueError("Evaluation configuration changed; choose a new evaluation output directory")
    atomic_json(config_path, config)
    atomic_json(output / "status.json", {"status": "running", "started_utc": utc_now()})
    pair_cache = PairCache(output / "character_pairs.sqlite3", {
        "implementation": "projection-character-m2-v4-linked-movement",
        "threshold": 0.85, "l_max_char": 3, "wb_sha256": wb_hash, "shape_sha256": shape_hash,
        "code_sha256": config["code_sha256"]["projection_character_m2.py"],
    })
    segmenter = (
        LtpSegmentationCache(output / "hypothesis_ltp.sqlite3")
        if saved_segmentations is None else None
    )
    converter = CachedConverter(pair_cache, lambda: TwoStepCharacterAligner(
        wb_repo=wb_repo, shape_table=shape_path, threshold=0.85, l_max_char=3,
    ), force=False)
    sys.path.insert(0, str(gleu_path))
    gleu = importlib.import_module("gleu_wrapper")
    scores = []
    tokenization_records = []
    try:
        reference_blocks = []
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            converted = converter.convert_many([(r["source"], r["target"]) for r in batch],
                                               embedding_batch_size=batch_size)
            for row, (edits, _stats, _cached) in zip(batch, converted):
                reference_blocks.append(render_pair(row, row["target"], row["target_segmented"], edits))
        reference_paths = save_blocks(output, "reference", reference_blocks)
        print(f"Prepared {len(rows)} fixed single-reference character/word M2 blocks", flush=True)
        for model, model_predictions in predictions.items():
            directory = output / model
            directory.mkdir(exist_ok=True)
            hypotheses = [r[c] for r in model_predictions for c in CONDITIONS]
            if saved_segmentations is not None:
                segmentations = {text: saved_segmentations[text] for text in dict.fromkeys(hypotheses)}
            else:
                if segmenter is None:
                    raise RuntimeError("Missing hypothesis segmenter")
                segmentations = segmenter.get_many(hypotheses, batch_size=ltp_batch_size)
            tokenization_records.extend(
                tokenization_audit_records(rows, model_predictions, segmentations, model)
            )
            write_tsv(
                directory / "hypotheses.segmented.tsv", ["id", *CONDITIONS],
                [{"id": row["id"], **{c: segmentations[row[c]] for c in CONDITIONS}}
                 for row in model_predictions],
            )
            for condition in CONDITIONS:
                hypothesis_blocks = []
                for start in range(0, len(rows), batch_size):
                    batch = rows[start:start + batch_size]
                    target_batch = model_predictions[start:start + batch_size]
                    converted = converter.convert_many(
                        [(r["source"], p[condition]) for r, p in zip(batch, target_batch)],
                        embedding_batch_size=batch_size,
                    )
                    for row, prediction, (edits, _stats, _cached) in zip(batch, target_batch, converted):
                        target = prediction[condition]
                        hypothesis_blocks.append(render_pair(row, target, segmentations[target], edits))
                paths = save_blocks(directory, condition, hypothesis_blocks)
                score: dict[str, Any] = {"model": model, "condition": condition, "sentences": len(rows)}
                sentence_counts = {}
                for unit in ("character", "word"):
                    unit_metrics, selections = score_m2(paths[unit], reference_paths[unit], unit)
                    score.update(unit_metrics)
                    sentence_counts[unit] = selections
                sentence_rows, gleu_inputs = [], []
                for index, (row, prediction) in enumerate(zip(rows, model_predictions)):
                    target = prediction[condition]
                    char_gleu, word_gleu, word_source = gleu_scores(
                        gleu, row, condition, target, segmentations[target]
                    )
                    sentence_rows.append({
                        "id": row["id"], "target_id": row["target_id"],
                        **{f"{unit}_{key.lower()}": sentence_counts[unit][index][key]
                           for unit in ("character", "word") for key in ("TP", "FP", "FN")},
                        "character_gleu": char_gleu, "word_gleu": word_gleu,
                    })
                    gleu_inputs.append({
                        "id": row["id"], "character_source": " ".join(row["source"]),
                        "character_hypothesis": " ".join(target), "character_reference": " ".join(row["target"]),
                        "word_source": word_source, "word_hypothesis": segmentations[target],
                        "word_reference": row["target_segmented"],
                    })
                for unit in ("character", "word"):
                    score[f"{unit}_gleu"] = math.fsum(
                        r[f"{unit}_gleu"] for r in sentence_rows
                    ) / len(rows)
                write_tsv(directory / f"{condition}.sentence_scores.tsv", list(sentence_rows[0]), sentence_rows)
                write_tsv(directory / f"{condition}.gleu_inputs.tsv", list(gleu_inputs[0]), gleu_inputs)
                atomic_json(directory / f"{condition}.metrics.json", score)
                scores.append(score)
                print(f"Scored {model}/{condition}: char F0.5={score['character_f05']:.4f}, "
                      f"word F0.5={score['word_f05']:.4f}", flush=True)
    except Exception as exc:
        atomic_json(output / "status.json", {
            "status": "failed", "failed_utc": utc_now(), "error": str(exc),
        })
        raise
    finally:
        if segmenter is not None:
            segmenter.close()
        pair_cache.close()
    deltas = differences(scores)
    write_tsv(output / "metrics.tsv", ["model", "condition", "sentences", *METRICS], scores)
    write_tsv(output / "deltas.tsv", ["model", "comparison", *METRICS], deltas)
    accounting = {model: generation_accounting(run, model, rows) for model in MODELS}
    tokenization_summary = summarize_tokenization_audit(tokenization_records)
    write_tsv(
        output / "tokenization_diagnostics.tsv",
        ["model", "condition", "id", "target_id", "check", "expected_segmented",
         "hypothesis_segmented", "boundaries_match"],
        tokenization_records,
    )
    write_report(
        output / "RESULTS.md", scores, deltas, manifest, accounting, tokenization_summary,
        segmentation_model=segmentation_model,
    )
    artifact_paths = [
        path for path in output.rglob("*")
        if path.is_file() and path.suffix in {".m2", ".tsv", ".md"}
    ]
    atomic_json(output / "evaluation_manifest.json", {
        "config": config, "status": "completed", "completed_utc": utc_now(),
        "rows": len(rows), "scores": scores, "deltas": deltas, "generation": accounting,
        "tokenization_audit": tokenization_summary,
        "artifacts": {str(path.relative_to(output)): file_hash(path) for path in artifact_paths},
    })
    atomic_json(output / "status.json", {
        "status": "completed", "rows": len(rows), "conditions_scored": len(scores),
        "completed_utc": utc_now(),
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--wb-repo", type=Path, default=DEFAULT_WB)
    parser.add_argument("--shape-table", type=Path, default=DEFAULT_SHAPE)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--ltp-batch-size", type=int, default=64)
    parser.add_argument(
        "--hypothesis-segmentations", type=Path,
        help="Verified ltp-output-segmentations-v1 JSON bundle; avoids any implicit LTP model fallback",
    )
    args = parser.parse_args()
    os.umask(0o077)
    run_evaluation(
        args.run, args.output or args.run / "evaluation", wb_repo=args.wb_repo,
        shape_path=args.shape_table, batch_size=args.batch_size, ltp_batch_size=args.ltp_batch_size,
        hypothesis_segmentations=args.hypothesis_segmentations,
    )


if __name__ == "__main__":
    main()
