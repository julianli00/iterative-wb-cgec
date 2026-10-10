"""Source-segmentation policies shared by word GLEU and its artifact audits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


SOURCE_POLICIES = ("condition", "fixed-gold")
CONDITION_SOURCE_COLUMNS = {"T0": "S1", "T1": "S1", "T2": "S2", "T3": "S3"}
LEGACY_SOURCE_DESCRIPTION = "one fixed gold-informed projection shared by T0--T3"


def select_source_segmentation(
    row: Mapping[str, str],
    stage: str,
    *,
    source_policy: str = "condition",
    fixed_source: str | None = None,
) -> str:
    if source_policy not in SOURCE_POLICIES:
        raise ValueError(f"Unknown word-GLEU source policy: {source_policy}")
    if stage not in CONDITION_SOURCE_COLUMNS:
        raise ValueError(f"Unknown word-GLEU stage: {stage}")
    raw_source = row.get("source")
    if not isinstance(raw_source, str) or not raw_source.replace("\ufeff", "").split():
        raise ValueError(f"Missing or empty learner source for row {row.get('id')}")
    column = CONDITION_SOURCE_COLUMNS[stage]
    segmented = row.get(column) if source_policy == "condition" else fixed_source
    if not isinstance(segmented, str) or not segmented.replace("\ufeff", "").split():
        label = column if source_policy == "condition" else "fixed gold-informed source"
        raise ValueError(f"Missing or empty {label} for row {row.get('id')}/{stage}")
    tokens = segmented.replace("\ufeff", "").split()
    if "".join(tokens) != "".join(raw_source.replace("\ufeff", "").split()):
        raise ValueError(f"Source segmentation changed learner text at row {row.get('id')}/{stage}")
    return " ".join(tokens)


def source_policy_from_config(config: Mapping[str, Any]) -> str:
    policy = config.get("source_segmentation_policy")
    if policy is None and config.get("source_segmentation") == LEGACY_SOURCE_DESCRIPTION:
        return "fixed-gold"
    if policy == "condition":
        if config.get("source_stage_mapping") != CONDITION_SOURCE_COLUMNS:
            raise ValueError("Condition-specific word GLEU has an invalid source-stage mapping")
        return "condition"
    if policy == "fixed-gold":
        return "fixed-gold"
    raise ValueError("Missing or unknown word-GLEU source-segmentation policy")


def load_source_policy(
    root: Path,
    *,
    expected_policy: str | None = None,
    require_completed: bool = True,
) -> str:
    path = root / "run_config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"Expected a word-GLEU configuration object: {path}")
    policy = source_policy_from_config(config)
    if expected_policy is not None and policy != expected_policy:
        raise ValueError(f"Word-GLEU policy mismatch at {path}: {policy} != {expected_policy}")
    if config.get("hypothesis_and_reference_segmentation") != "LTP":
        raise ValueError(f"Word GLEU must use LTP hypotheses/references: {path}")
    if require_completed:
        status = config.get("status")
        completed = status == "completed" or (
            status is None and policy == "fixed-gold" and bool(config.get("completed_utc"))
        )
        if not completed:
            raise ValueError(f"Word-GLEU run is not complete: {path}")
    return policy
