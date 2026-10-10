#!/usr/bin/env python3
"""Prepare and run the isolated MuCGEC dev selected-gold R/D/P experiment."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any, Callable

try:
    from run_iterative_gec import (
        PROMPT_RAW_PAPER, PROMPT_SEGMENTED_PAPER, call_llm, load_wb_module,
        project_with_existing_boundaries, segmentation_signature,
    )
except ModuleNotFoundError:
    from scripts.run_iterative_gec import (
        PROMPT_RAW_PAPER, PROMPT_SEGMENTED_PAPER, call_llm, load_wb_module,
        project_with_existing_boundaries, segmentation_signature,
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "runs/mucgec_dev_gold_first"
DEFAULT_WB = ROOT / "external_tools/chinese-wb-fixing"
DEFAULT_SHAPE = ROOT / "external_tools/wb-shape-data/triplet_no_dup_threshold.csv"
CONDITIONS = ("R", "D", "P")
CSV_FIELDS = ("Index", "Target_ID", "Target_Text", "Source_Text")
MODELS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "model": "deepseek-v4-pro", "base_url": "https://api.deepseek.com/v1",
        "temperature": 0.000001, "max_tokens": None, "thinking_disabled": True,
    },
    "kimi": {
        "model": "kimi-k2.6", "base_url": "https://api.moonshot.ai/v1",
        "temperature": None, "max_tokens": 512, "thinking_disabled": True,
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def raw_text(value: str) -> str:
    return "".join(value.replace("\ufeff", "").split())


def canonical_segmented(value: str) -> str:
    return " ".join(value.replace("\ufeff", "").split())


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def identity_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_tsv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, Any]]:
    rows = []
    seen_ids: set[str] = set()
    seen_sources: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(CSV_FIELDS):
            raise ValueError(f"Expected CSV columns {CSV_FIELDS!r}")
        for position, original in enumerate(reader, 1):
            if set(original) != set(CSV_FIELDS) or any(
                not isinstance(value, str) or not value.strip() for value in original.values()
            ):
                raise ValueError(f"Malformed or empty CSV row {position}")
            identifier = original["Index"]
            if not identifier.isascii() or not identifier.isdecimal():
                raise ValueError(f"Invalid Index at CSV row {position}")
            source = raw_text(original["Source_Text"])
            target_segmented = canonical_segmented(original["Target_Text"])
            if not source or not raw_text(target_segmented):
                raise ValueError(f"Empty surface text at CSV row {position}")
            if identifier in seen_ids or source in seen_sources:
                raise ValueError(f"Duplicate Index or raw source at CSV row {position}")
            if any("\t" in value or "\n" in value or "\r" in value for value in original.values()):
                raise ValueError(f"Embedded tab/newline at CSV row {position}")
            seen_ids.add(identifier)
            seen_sources.add(source)
            rows.append({
                "id": identifier, "csv_row": position, "target_id": original["Target_ID"],
                "source": source, "target": raw_text(target_segmented),
                "target_segmented": target_segmented, "original": original,
            })
    if not rows:
        raise ValueError("The CSV contains no data rows")
    return rows


def prepare_row(
    row: dict[str, Any], *, segment: Callable[[str], str],
    project: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    direct = canonical_segmented(segment(row["source"]))
    projection = project(source_segmented=direct, target_segmented=row["target_segmented"])
    projected = canonical_segmented(projection["projected"])
    for condition, value in (("D", direct), ("P", projected)):
        if raw_text(value) != row["source"]:
            raise ValueError(f"{condition} changed source characters for ID {row['id']}")
    return {
        **row, "R_input": row["source"], "D_input": direct, "P_input": projected,
        "projection_stats": projection["stats"],
        "carry_P_from_D": segmentation_signature(direct) == segmentation_signature(projected),
    }


def prepare(csv_path: Path, output: Path, wb_repo: Path, shape_path: Path) -> None:
    rows = read_csv(csv_path)
    if csv_path.resolve().is_relative_to(output.resolve()):
        raise ValueError("Keep the read-only input CSV outside the experiment output directory")
    config = {
        "version": "selected-gold-rdp-v1", "input_sha256": file_hash(csv_path),
        "rows": len(rows), "reference_scope": "one CSV-selected gold Target per source",
        "source_human_boundaries": "provenance only; removed before every condition",
        "target_boundaries": "CSV Target_Text tokens, never selected or segmented again",
        "threshold": 0.85, "bert_model": "bert-base-chinese",
        "word_m2_source": "fixed gold-informed P_input for all R/D/P",
        "word_gleu_source": {"R": "D_input", "D": "D_input", "P": "P_input"},
        "word_reference": "supplied Target_Text segmentation",
        "convergence": "normalized P == D carries D prediction forward; R is always independent",
        "wb_sha256": file_hash(
            wb_repo / "src/pipeline/alignment/step2_similarity_alignment_projection.py"
        ),
        "shape_sha256": file_hash(shape_path),
        "projection_runner_sha256": file_hash(Path(__file__).with_name("run_iterative_gec.py")),
    }
    output.mkdir(parents=True, exist_ok=True)
    config_path = output / "preparation_config.json"
    if config_path.exists() and read_json(config_path) != config:
        raise ValueError("Preparation configuration changed; use a new output directory")
    atomic_json(config_path, config)
    if (output / "prepared_manifest.json").exists():
        load_prepared(output)
        print(f"Reusing {len(rows)} verified prepared inputs", flush=True)
        return
    records_dir = output / "prepared_rows"
    records_dir.mkdir(exist_ok=True)
    wb = None
    shape = None
    prepared = []
    for row in rows:
        path = records_dir / f"{row['id']}.json"
        if path.exists():
            record = read_json(path)
            if any(record.get(key) != value for key, value in row.items()):
                raise ValueError(f"Prepared row does not match input ID {row['id']}")
        else:
            if wb is None:
                wb = load_wb_module(wb_repo)
                wb.load_bert_model("bert-base-chinese")
                shape = wb.load_shape_table(str(shape_path))
            record = prepare_row(
                row, segment=wb.ltp_segment,
                project=lambda **kwargs: project_with_existing_boundaries(
                    wb_module=wb, shape_table=shape, threshold=0.85, **kwargs
                ),
            )
            atomic_json(path, record)
        prepared.append(record)
        if len(prepared) % 50 == 0:
            print(f"Prepared {len(prepared)}/{len(rows)} inputs", flush=True)
    prepared_path = output / "prepared.jsonl"
    with prepared_path.open("w", encoding="utf-8") as stream:
        for record in prepared:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    write_tsv(
        output / "inputs.tsv",
        ["id", "csv_row", "target_id", "source", "target_segmented",
         "R_input", "D_input", "P_input", "carry_P_from_D"],
        prepared,
    )
    for condition in CONDITIONS:
        (output / f"{condition}.inputs.txt").write_text(
            "\n".join(row[f"{condition}_input"] for row in prepared) + "\n", encoding="utf-8"
        )
    atomic_json(output / "prepared_manifest.json", {
        "config_sha256": file_hash(config_path), "prepared_sha256": file_hash(prepared_path),
        "rows": len(prepared), "carry_forward_rows": sum(r["carry_P_from_D"] for r in prepared),
        "completed_utc": utc_now(),
    })
    load_prepared(output)
    print(f"Prepared all {len(prepared)} rows; P == D for {sum(r['carry_P_from_D'] for r in prepared)}",
          flush=True)


def load_prepared(output: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = read_json(output / "prepared_manifest.json")
    config = read_json(output / "preparation_config.json")
    if manifest["config_sha256"] != file_hash(output / "preparation_config.json"):
        raise ValueError("Preparation configuration hash mismatch")
    if manifest["prepared_sha256"] != file_hash(output / "prepared.jsonl"):
        raise ValueError("Prepared input hash mismatch")
    with (output / "prepared.jsonl").open(encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    if not rows or len(rows) != manifest["rows"] or len(rows) != config["rows"]:
        raise ValueError("Prepared row count mismatch")
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate prepared row IDs")
    for row in rows:
        if row["source"] != raw_text(row["original"]["Source_Text"]):
            raise ValueError("Prepared source provenance mismatch")
        if row["target_segmented"] != canonical_segmented(row["original"]["Target_Text"]):
            raise ValueError("Prepared target boundaries changed")
        if row["target"] != raw_text(row["target_segmented"]):
            raise ValueError("Prepared target surface mismatch")
        if row["R_input"] != row["source"]:
            raise ValueError("Raw condition contains boundaries")
        if any(raw_text(row[f"{c}_input"]) != row["source"] for c in CONDITIONS):
            raise ValueError("A prepared condition changed source characters")
        same = segmentation_signature(row["D_input"]) == segmentation_signature(row["P_input"])
        if row["carry_P_from_D"] != same:
            raise ValueError("Invalid normalized-boundary carry-forward marker")
    return rows, manifest


def request_spec(row: dict[str, Any], condition: str, run_identity: str) -> dict[str, Any]:
    if condition not in CONDITIONS:
        raise ValueError(f"Unsupported condition {condition}")
    template = PROMPT_RAW_PAPER if condition == "R" else PROMPT_SEGMENTED_PAPER
    return {
        "run_identity": run_identity, "id": row["id"], "condition": condition,
        "prompt": template.format(sentence=row[f"{condition}_input"]),
    }


def generate_row(
    row: dict[str, Any], *, model_config: dict[str, Any], run_identity: str,
    journal: Path, api_key: str, call_model: Callable[..., Any] = call_llm,
    retry_failed: bool = False, stopped: threading.Event | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": row["id"], "target_id": row["target_id"], "source": row["source"],
        "target": row["target"], "meta": {},
    }
    for condition in CONDITIONS:
        spec = request_spec(row, condition, run_identity)
        path = journal / f"{row['id']}.{condition}.json"
        prior = read_json(path) if path.exists() else None
        if prior is not None:
            if prior["request"] != spec:
                raise ValueError(f"Checkpoint identity mismatch: ID {row['id']}/{condition}")
            if prior["status"] == "completed":
                prediction = prior["prediction"]
                if not prediction or raw_text(prediction) != prediction:
                    raise ValueError("Invalid saved prediction")
                result[condition] = prediction
                result["meta"][condition] = prior["meta"]
                continue
            if prior["status"] == "started":
                raise RuntimeError(
                    f"Unresolved in-flight request {row['id']}/{condition}; reconcile receipt "
                    "before resuming to avoid a duplicate paid call"
                )
            if not retry_failed:
                raise RuntimeError(
                    f"Recorded failure for {row['id']}/{condition}; inspect it before --retry-failed"
                )
        if stopped is not None and stopped.is_set():
            raise RuntimeError("Stopped after another request failed; completed receipts are retained")
        if condition == "P" and row["carry_P_from_D"]:
            prediction = result["D"]
            meta = {"carried_from": "D", "reason": "normalized_boundaries_unchanged"}
            atomic_json(path, {
                "request": spec, "status": "completed", "prediction": prediction,
                "meta": meta, "completed_utc": utc_now(), "responses": [],
            })
        else:
            receipt: dict[str, Any] = {
                "request": spec, "status": "started", "started_utc": utc_now(),
                "responses": [], "previous_failures": [],
            }
            if prior:
                receipt["previous_failures"] = [*prior.get("previous_failures", []), {
                    key: value for key, value in prior.items() if key != "previous_failures"
                }]
            atomic_json(path, receipt)

            def observe(response: dict[str, Any]) -> None:
                receipt["responses"].append({**response, "recorded_utc": utc_now()})
                atomic_json(path, receipt)

            try:
                prediction, meta = call_model(
                    prompt=spec["prompt"], api_key=api_key, **model_config,
                    timeout=180, retries=3, sleep_seconds=2.0,
                    request_key=f"{run_identity}:{row['id']}:{condition}",
                    strict_settings=True, response_observer=observe,
                )
                if not prediction or raw_text(prediction) != prediction:
                    raise ValueError("The returned prediction is empty or still segmented")
                if meta.get("fallback_without_thinking"):
                    raise ValueError("Nonthinking setting was removed by the provider wrapper")
                receipt.update(
                    status="completed", prediction=prediction, meta=meta, completed_utc=utc_now()
                )
                atomic_json(path, receipt)
            except Exception as exc:
                if stopped is not None:
                    stopped.set()
                receipt.update(
                    status="failed", error=str(exc).replace(api_key, "[REDACTED]"),
                    failed_utc=utc_now(),
                )
                atomic_json(path, receipt)
                raise
        result[condition] = prediction
        result["meta"][condition] = meta
    return result


def generate(
    output: Path, model: str, *, api_key: str, limit: int = 0, workers: int = 4,
    retry_failed: bool = False,
) -> None:
    if model not in MODELS or not api_key.strip() or workers < 1 or limit < 0:
        raise ValueError("Supply a configured model, nonempty runtime API key and valid run sizes")
    rows, manifest = load_prepared(output)
    model_dir = output / model
    model_dir.mkdir(exist_ok=True)
    with (model_dir / ".generation.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        config = {
            "version": "selected-gold-rdp-generation-v1", "provider": model, **MODELS[model],
            "prepared_sha256": manifest["prepared_sha256"],
            "raw_prompt": PROMPT_RAW_PAPER, "segmented_prompt": PROMPT_SEGMENTED_PAPER,
            "conditions": list(CONDITIONS), "carry_forward": "P from D if normalized inputs match",
            "strict_settings": True, "top_p": "omitted", "seed": "omitted",
            "runner_sha256": file_hash(Path(__file__)),
            "api_wrapper_sha256": file_hash(Path(__file__).with_name("run_iterative_gec.py")),
        }
        config_path = model_dir / "generation_config.json"
        if config_path.exists() and read_json(config_path) != config:
            raise ValueError("Generation identity/configuration changed; use a new run")
        atomic_json(config_path, config)
        run_identity = identity_hash(config)
        journal = model_dir / "requests"
        journal.mkdir(exist_ok=True)
        selected_rows = rows[:limit] if limit else rows
        completed: dict[str, dict[str, Any]] = {}
        stopped = threading.Event()
        atomic_json(model_dir / "status.json", {
            "status": "running", "requested_rows": len(selected_rows), "total_rows": len(rows),
            "started_utc": utc_now(),
        })
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(
                        generate_row, row, model_config=MODELS[model], run_identity=run_identity,
                        journal=journal, api_key=api_key, retry_failed=retry_failed, stopped=stopped,
                    ): row["id"] for row in selected_rows
                }
                try:
                    for future in as_completed(futures):
                        result = future.result()
                        completed[result["id"]] = result
                        if len(completed) % 25 == 0 or len(completed) == len(selected_rows):
                            print(f"{model}: {len(completed)}/{len(selected_rows)} R/D/P rows complete",
                                  flush=True)
                except Exception:
                    stopped.set()
                    for future in futures:
                        future.cancel()
                    raise
        except Exception as exc:
            atomic_json(model_dir / "status.json", {
                "status": "failed", "error": str(exc).replace(api_key, "[REDACTED]"),
                "failed_utc": utc_now(), "note": "Successful condition receipts are retained",
            })
            raise
        results = [completed[row["id"]] for row in selected_rows]
        # Pilot snapshots never overwrite an existing full-corpus deliverable.
        prefix = "predictions" if len(results) == len(rows) else "pilot_predictions"
        with (model_dir / f"{prefix}.jsonl").open("w", encoding="utf-8") as stream:
            for result in results:
                stream.write(json.dumps(result, ensure_ascii=False) + "\n")
        write_tsv(
            model_dir / f"{prefix}.tsv",
            ["id", "target_id", "source", "target", *CONDITIONS], results,
        )
        atomic_json(model_dir / "status.json", {
            "status": "completed" if len(results) == len(rows) else "pilot_completed",
            "rows": len(results), "total_rows": len(rows), "completed_utc": utc_now(),
            "predictions_sha256": file_hash(model_dir / f"{prefix}.jsonl"),
            "conditions": list(CONDITIONS),
        })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_RUN)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--input", type=Path, required=True)
    prep.add_argument("--wb-repo", type=Path, default=DEFAULT_WB)
    prep.add_argument("--shape-table", type=Path, default=DEFAULT_SHAPE)
    run = commands.add_parser("generate")
    run.add_argument("--model", choices=MODELS, required=True)
    run.add_argument("--limit", type=int, default=0)
    run.add_argument("--workers", type=int, default=4)
    run.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == "prepare":
        prepare(args.input, args.output, args.wb_repo, args.shape_table)
    else:
        key_name = f"{args.model.upper()}_API_KEY"
        api_key = os.environ.get(key_name)
        if not api_key:
            parser.error(f"Set {key_name} in the process environment; no .env is read automatically")
        generate(
            args.output, args.model, api_key=api_key, limit=args.limit,
            workers=args.workers, retry_failed=args.retry_failed,
        )


if __name__ == "__main__":
    main()
