#!/usr/bin/env python3
"""Prepare usable scoreboard datasets for the iterative WB-CGEC pipeline.

Each prepared split contains a headerless ``pipeline.tsv`` (source plus one
reference), a multi-reference ``gold.para``, optional official ``gold.m2``,
and metadata describing the source and evaluation caveats.
"""

from __future__ import annotations

from copy import deepcopy
import csv
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "data/benchmarks/upstream"
PREPARED = ROOT / "data/benchmarks/prepared"
CHERRANT = ROOT / "external_tools/MuCGEC/scorers/ChERRANT"


def clean(text: Any) -> str:
    return str(text or "").replace("\ufeff", "").replace("\t", " ").replace("\n", " ").strip()


def ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = clean(value)
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def detokenize_m2_text(text: str, *, bpe: bool = False) -> str:
    tokens = text.split()
    if bpe:
        tokens = [token[2:] if token.startswith("##") else token for token in tokens]
    return clean("".join(tokens))


def parse_m2(path: Path, *, bpe: bool = False) -> tuple[list[str], list[list[str]]]:
    sources: list[str] = []
    references: list[list[str]] = []
    blocks = path.read_text(encoding="utf-8-sig").strip().split("\n\n")
    for block_number, block in enumerate(blocks, start=1):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or not lines[0].startswith("S "):
            raise ValueError(f"Invalid M2 block {block_number} in {path}")
        source = detokenize_m2_text(lines[0][2:], bpe=bpe)
        refs: list[str] = []
        for line in lines[1:]:
            if not line.startswith("T"):
                continue
            _, target = line.split(" ", 1)
            if target.strip() == "没有错误":
                refs.append(source)
            else:
                refs.append(detokenize_m2_text(target, bpe=bpe))
        sources.append(source)
        references.append(ordered_unique(refs) or [source])
    return sources, references


def copy_sanitized_m2(source: Path, destination: Path) -> None:
    """Copy M2 gold while removing BOMs left at concatenated shard boundaries."""
    text = source.read_text(encoding="utf-8-sig").replace("\ufeff", "")
    destination.write_text(text, encoding="utf-8")


def convert_fcgec_operations(sentence: str, operations: list[dict[str, Any]]) -> list[str]:
    """Reproduce FCGEC's official ``convert_operator2seq`` conversion."""

    unpacked: list[dict[str, Any]] = []
    old_mode = True
    for operation in operations:
        if old_mode:
            for key in ("Insert", "Modify"):
                if key in operation and isinstance(operation[key][0]["label"], list):
                    old_mode = False
                    break
        if old_mode:
            unpacked.append(operation)
            continue
        for key in ("Insert", "Modify"):
            for item in operation.get(key, []):
                for label in item["label"]:
                    new_item = deepcopy(item)
                    new_item["label"] = label
                    unpacked.append({key: [new_item]})

    def apply_one(operation: dict[str, Any]) -> str:
        current = sentence
        if "Switch" in operation:
            current = "".join(current[index] for index in operation["Switch"])
        tagged = [[char, "O", ""] for char in current]
        for index in operation.get("Delete", []):
            tagged[index][1] = "D"
        for item in operation.get("Insert", []):
            if item["pos"] == -1:
                tagged.append(["", "IH", item["label"]])
            else:
                tagged[item["pos"]][1] = item["tag"]
                tagged[item["pos"]][2] = item["label"]
        for item in operation.get("Modify", []):
            tagged[item["pos"]][1] = item["tag"]
            tagged[item["pos"]][2] = item["label"]

        output = ""
        index = 0
        while index < len(tagged):
            char, tag, label = tagged[index]
            if tag == "O":
                output += char
            elif tag == "D":
                index += 1
                continue
            elif tag == "IH":
                output = label + output
            elif tag.startswith("INS"):
                output += char + label
            elif tag.startswith("MOD"):
                span = int(tag.split("+")[0].split("_")[-1])
                output += label
                index += span - 1
            index += 1
        return output

    return ordered_unique(apply_one(operation) for operation in unpacked)


def write_split(
    dataset: str,
    split: str,
    sources: list[str],
    references: list[list[str]],
    metadata: dict[str, Any],
    *,
    gold_m2: Path | None = None,
) -> dict[str, Any]:
    if len(sources) != len(references):
        raise ValueError(f"{dataset}/{split}: source/reference count mismatch")
    if not sources:
        raise ValueError(f"{dataset}/{split}: no rows")

    out_dir = PREPARED / dataset / split
    out_dir.mkdir(parents=True, exist_ok=True)

    normalized_sources = [clean(source) for source in sources]
    normalized_refs = [ordered_unique(refs) or [source] for source, refs in zip(normalized_sources, references)]
    with (out_dir / "pipeline.tsv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        for source, refs in zip(normalized_sources, normalized_refs):
            writer.writerow([source, refs[0]])
    with (out_dir / "gold.para").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        for index, (source, refs) in enumerate(zip(normalized_sources, normalized_refs), start=1):
            writer.writerow([index, source, *refs])

    if gold_m2 is not None:
        copy_sanitized_m2(gold_m2, out_dir / "gold.m2")

    record = {
        "dataset": dataset,
        "split": split,
        "rows": len(sources),
        "average_references": round(sum(map(len, normalized_refs)) / len(normalized_refs), 3),
        "pipeline_input": str((out_dir / "pipeline.tsv").relative_to(ROOT)),
        "gold_para": str((out_dir / "gold.para").relative_to(ROOT)),
        "gold_m2": str((out_dir / "gold.m2").relative_to(ROOT)) if gold_m2 else None,
        **metadata,
    }
    (out_dir / "metadata.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return record


def prepare_nlpcc2018() -> dict[str, Any]:
    gold = CHERRANT / "samples/nlpcc2018_official.ref.m2.char"
    sources, refs = parse_m2(gold)
    return write_split(
        "nlpcc2018",
        "test",
        sources,
        refs,
        {
            "selection": "official public test gold, ChERRANT character-level conversion",
            "evaluation": "ChERRANT char/span F0.5; original shared task also reports word-level M2",
            "source_url": "https://github.com/zhaoyyoo/NLPCC2018_GEC",
            "source_path": "data/benchmarks/upstream/nlpcc2018/Data.zip",
        },
        gold_m2=gold,
    )


def prepare_mucgec() -> dict[str, Any]:
    gold = UPSTREAM / "cgecdata/MuCGEC/v1-NAACL22/mucgec.test.m2"
    sources, refs = parse_m2(gold)
    return write_split(
        "mucgec",
        "test",
        sources,
        refs,
        {
            "selection": "official public test gold released by CGECData",
            "evaluation": "ChERRANT char/span F0.5",
            "source_url": "https://github.com/SUDA-LA/CGECData",
            "source_path": str(gold.relative_to(ROOT)),
        },
        gold_m2=gold,
    )


def prepare_yaclc() -> dict[str, Any]:
    path = UPSTREAM / "yaclc/valid.jsonl"
    sources: list[str] = []
    refs: list[list[str]] = []
    for line in path.open(encoding="utf-8"):
        row = json.loads(line)
        sources.append(row["sentence_text"])
        refs.append(
            ordered_unique(
                anno["correction"]
                for anno in row["sentence_annos"]
                if anno["is_grammatical"] == 1
            )
        )
    return write_split(
        "yaclc",
        "validation",
        sources,
        refs,
        {
            "selection": "validation gold; public test contains sources only",
            "evaluation": "ChERRANT char/span F0.5 over grammatical-correction references only",
            "source_url": "https://github.com/blcuicall/YACLC",
            "source_path": str(path.relative_to(ROOT)),
            "comparability_note": "validation result, not an official hidden-test score",
        },
    )


def prepare_flacgec() -> dict[str, Any]:
    path = UPSTREAM / "flacgec/data/test.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    sources = [row["source"] for row in data.values()]
    refs = [[row["target"]] for row in data.values()]
    return write_split(
        "flacgec",
        "test",
        sources,
        refs,
        {
            "selection": "public test source-target pairs",
            "evaluation": "ChERRANT char/span F0.5 for this iterative experiment",
            "source_url": "https://github.com/hyDududu/FlaCGEC",
            "source_path": str(path.relative_to(ROOT)),
            "run_note": "full T0-T10 run already completed in this workspace",
        },
    )


def prepare_fcgec() -> dict[str, Any]:
    path = UPSTREAM / "fcgec/data/FCGEC_valid.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    sources: list[str] = []
    refs: list[list[str]] = []
    for row in data.values():
        source = row["sentence"]
        if row["error_flag"] == 1:
            targets = convert_fcgec_operations(source, json.loads(row["operation"]))
        else:
            targets = [source]
        if not targets:
            raise ValueError("FCGEC operation conversion produced no reference")
        sources.append(source)
        refs.append(targets)
    return write_split(
        "fcgec",
        "validation",
        sources,
        refs,
        {
            "selection": "validation gold; test labels remain hidden behind CodaBench",
            "evaluation": "ChERRANT char/span F0.5",
            "source_url": "https://github.com/xlxwalex/FCGEC",
            "evaluation_url": "https://www.codabench.org/competitions/15596/",
            "source_path": str(path.relative_to(ROOT)),
            "comparability_note": "validation result, not an official hidden-test score",
        },
    )


def prepare_nacgec() -> dict[str, Any]:
    path = UPSTREAM / "nacgec/data/nacgec.test.ref.para"
    sources: list[str] = []
    refs: list[list[str]] = []
    with path.open(encoding="utf-8") as stream:
        for row in csv.reader(stream, delimiter="\t"):
            sources.append(row[1])
            refs.append(ordered_unique(row[2:]))
    return write_split(
        "nacgec",
        "test",
        sources,
        refs,
        {
            "selection": "official test ground truth released after the shared task",
            "evaluation": "ChERRANT char/span F0.5; official final score also averages word-level M2",
            "source_url": "https://github.com/masr2000/NaCGEC",
            "source_path": str(path.relative_to(ROOT)),
        },
    )


def prepare_nasgec_exam() -> dict[str, Any]:
    gold = UPSTREAM / "cgecdata/NaSGEC/v1-ACL23/NaSGEC/NaSGEC-Exam/nasgec.exam.test.m2"
    sources, refs = parse_m2(gold, bpe=True)
    return write_split(
        "nasgec_exam",
        "test",
        sources,
        refs,
        {
            "selection": "public NaSGEC-Exam test gold; Media and Thesis require a signed agreement",
            "evaluation": (
                "uniform ChERRANT character/span F0.5 without BPE; the official "
                "BPE M2 is retained for provenance only"
            ),
            "official_m2_bpe": True,
            "source_url": "https://github.com/SUDA-LA/CGECData",
            "source_path": str(gold.relative_to(ROOT)),
        },
        gold_m2=gold,
    )


def prepare_cefe() -> dict[str, Any]:
    path = UPSTREAM / "cefe/track3/datas/val.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return write_split(
        "cefe_track3",
        "validation",
        [row["sent"] for row in data],
        [[row["revisedSent"]] for row in data],
        {
            "selection": "only public Track 3 validation gold; test labels are unavailable",
            "evaluation": "exploratory ChERRANT char/span F0.5",
            "source_url": "https://github.com/cubenlp/2023CCL_CEFE",
            "source_path": str(path.relative_to(ROOT)),
            "comparability_note": "only 19 validation sentences; diagnostic, not a robust benchmark",
        },
    )


def main() -> None:
    records = [
        prepare_nlpcc2018(),
        prepare_mucgec(),
        prepare_yaclc(),
        prepare_flacgec(),
        prepare_fcgec(),
        prepare_nacgec(),
        prepare_nasgec_exam(),
        prepare_cefe(),
    ]
    PREPARED.mkdir(parents=True, exist_ok=True)
    (PREPARED / "manifest.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("dataset\tsplit\trows\tavg_refs\tgold_m2")
    for record in records:
        print(
            f"{record['dataset']}\t{record['split']}\t{record['rows']}\t"
            f"{record['average_references']}\t{bool(record['gold_m2'])}"
        )


if __name__ == "__main__":
    main()
