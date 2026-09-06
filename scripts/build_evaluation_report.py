#!/usr/bin/env python3
"""Build one report from the finalized iterative CGEC evaluations."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
MANIFEST = ROOT / "data/benchmarks/prepared/manifest.json"
M2_SCORES = RUNS / "projection_character_m2_eval/scores.long.tsv"
GLEU_SCORES = RUNS / "character_gleu_select_best/scores.long.tsv"
REFERENCE_SCOPE = RUNS / "standardized_m2_eval/scores.all_vs_first3.tsv"
PIPELINE_SUMMARY = RUNS / "scoreboard_t3_summary.tsv"
FLA_T10 = (
    RUNS
    / "cherrant_eval/flaCGEC_all_T10_deepseek_v4_pro_paper_converged/char/summary.tsv"
)
OUTPUT = RUNS / "ALL_EVALUATIONS.md"

STAGES = ("T0", "T1", "T2", "T3")
ALIGNMENTS = ("cherrant", "projection")
BETAS = (0.5, 1.0, 2.0)
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


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def add_table(lines: list[str], headers: list[str], rows: list[list[str]]) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append(
        "| "
        + " | ".join(
            "---" if index < 2 else "---:" for index, _header in enumerate(headers)
        )
        + " |"
    )
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")


def score(value: float) -> str:
    return f"{value:.2f}"


def signed(value: float) -> str:
    return f"{value:+.2f}"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    order = [record["dataset"] for record in manifest]
    metadata = {record["dataset"]: record for record in manifest}

    m2_rows = read_tsv(M2_SCORES)
    m2: dict[tuple[str, str, str, float], float] = {}
    for row in m2_rows:
        key = (
            row["dataset"],
            row["alignment"],
            row["round"],
            float(row["beta"]),
        )
        m2[key] = float(row["F_beta"]) * 100.0

    gleu_rows = read_tsv(GLEU_SCORES)
    gleu = {
        (row["dataset"], row["stage"]): float(row["gleu_select_best_x100"])
        for row in gleu_rows
    }
    gleu_metadata = {
        row["dataset"]: {
            "sentences": int(row["sentences"]),
            "references": int(row["references"]),
            "multi_reference_sentences": int(row["multi_reference_sentences"]),
        }
        for row in gleu_rows
    }
    for dataset in order:
        stats_path = (
            RUNS
            / "character_gleu_select_best"
            / dataset
            / metadata[dataset]["split"]
            / "stats.json"
        )
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        gleu_metadata[dataset]["max_references"] = int(stats["max_references"])
        gleu_metadata[dataset]["sentences_more_than_3_references"] = sum(
            int(sentences)
            for references, sentences in stats["reference_count_distribution"].items()
            if int(references) > 3
        )

    pipeline_rows = {row["dataset"]: row for row in read_tsv(PIPELINE_SUMMARY)}
    reference_scope = {
        (row["dataset"], row["round"]): float(row["all_minus_first3_x100"])
        for row in read_tsv(REFERENCE_SCOPE)
        if row["reference_origin"] == "generated"
    }
    fla_t10 = read_tsv(FLA_T10)

    detail_rows = read_tsv(RUNS / "character_gleu_select_best/sentence_scores.tsv")
    later_reference_sentences = {
        (row["dataset"], row["id"])
        for row in detail_rows
        if int(row["selected_reference"]) >= 3
    }

    lines: list[str] = [
        "# Consolidated Evaluation Report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Scope",
        "",
        "This report consolidates the finalized evaluations of the iterative word-boundary-aware Chinese grammatical error correction pipeline. The same saved DeepSeek outputs are evaluated at T0--T3 under three conditions:",
        "",
        "1. uniform ChERRANT character-level M2 evaluation;",
        "2. projection-based character-level M2 evaluation; and",
        "3. character-based multi-reference GLEU-select-best.",
        "",
        "Pilot runs, the no-`t2s` projection diagnostic, and the preliminary mixed-M2 scoreboard are not treated as formal results. A historical FlaCGEC T0--T10 diagnostic is retained separately at the end.",
        "",
        "## Experimental Setup",
        "",
        "- Model: `deepseek-v4-pro`.",
        "- Decoding: thinking disabled; temperature `0.000001`.",
        "- Prompting: the paper's Chinese baseline and structured prompts.",
        "- T0: unsegmented learner sentence.",
        "- T1: LTP-segmented learner sentence.",
        "- T2: first word-boundary projection from T1.",
        "- T3: second word-boundary projection from T2.",
        "- Convergence: when the projected segmentation is unchanged, the prior output is carried forward without another LLM call.",
        "",
        "## Dataset Coverage",
        "",
    ]

    coverage_rows: list[list[str]] = []
    for dataset in order:
        record = metadata[dataset]
        item = gleu_metadata[dataset]
        coverage_rows.append(
            [
                DISPLAY_NAMES[dataset],
                record["split"],
                f"{item['sentences']:,}",
                f"{item['references']:,}",
                f"{item['multi_reference_sentences']:,}",
                f"{item['sentences_more_than_3_references']:,}",
                str(item["max_references"]),
            ]
        )
    add_table(
        lines,
        [
            "Dataset",
            "Split",
            "Sentences",
            "References",
            "Multi-ref sentences",
            ">3 refs",
            "Max refs",
        ],
        coverage_rows,
    )
    total_sentences = sum(item["sentences"] for item in gleu_metadata.values())
    total_references = sum(item["references"] for item in gleu_metadata.values())
    total_multi = sum(item["multi_reference_sentences"] for item in gleu_metadata.values())
    total_more_than_3 = sum(
        item["sentences_more_than_3_references"] for item in gleu_metadata.values()
    )
    lines.extend(
        [
            f"Total: **{total_sentences:,} sentences**, **{total_references:,} references**, and **{total_multi:,} multi-reference sentences**; **{total_more_than_3:,} sentences** have more than three references.",
            "",
            "For both M2 methods, the same complete reference set and the same comparator are used. GLEU independently scores every available reference and selects the highest sentence-level score. No first-three-reference cap is applied.",
            "",
            "### Effect of Using All References",
            "",
            "The following values are the uniform ChERRANT F0.5 difference between using all generated references and retaining only annotator IDs 0--2. Positive values show the benefit of references beyond the first three.",
            "",
        ]
    )
    reference_scope_rows = []
    for dataset in order:
        reference_scope_rows.append(
            [
                DISPLAY_NAMES[dataset],
                metadata[dataset]["split"],
                *[signed(reference_scope[(dataset, stage)]) for stage in STAGES],
            ]
        )
    add_table(lines, ["Dataset", "Split", *STAGES], reference_scope_rows)
    lines.extend(
        [
            "Using all references is especially important for YACLC (+14.35 to +15.35 points) and also affects MuCGEC (+0.40 to +0.58). Effects on the other splits are at most 0.02 points because they have fewer references or later references rarely change the selected edit match.",
            "",
            "## Pipeline Diagnostics",
            "",
        ]
    )
    diagnostic_rows: list[list[str]] = []
    for dataset in order:
        row = pipeline_rows[dataset]
        sentences = int(row["rows"])
        converged = int(row["converged_by_T3"])
        diagnostic_rows.append(
            [
                DISPLAY_NAMES[dataset],
                metadata[dataset]["split"],
                f"{sentences:,}",
                f"{converged:,} ({converged / sentences * 100:.1f}%)",
                f"{int(row['projection_splits_through_S3']):,}",
                f"{int(row['projection_merges_through_S3']):,}",
            ]
        )
    add_table(
        lines,
        ["Dataset", "Split", "N", "Converged by T3", "WB splits", "WB merges"],
        diagnostic_rows,
    )
    converged_total = sum(int(row["converged_by_T3"]) for row in pipeline_rows.values())
    split_total = sum(int(row["projection_splits_through_S3"]) for row in pipeline_rows.values())
    merge_total = sum(int(row["projection_merges_through_S3"]) for row in pipeline_rows.values())
    lines.extend(
        [
            f"Overall, **{converged_total:,}/{total_sentences:,} ({converged_total / total_sentences * 100:.1f}%)** sentences converged by T3. Projection performed **{split_total:,} splits** and **{merge_total:,} merges**, confirming that it supports both boundary operations.",
            "",
            "## Evaluation 1: Uniform ChERRANT Character M2",
            "",
            "Reference and hypothesis M2 files are generated uniformly at character granularity, without BPE, using all textual references. ChERRANT target normalization applies Traditional-to-Simplified conversion. Scores are corpus-level F0.5 multiplied by 100.",
            "",
        ]
    )
    cherrant_rows = []
    for dataset in order:
        cherrant_rows.append(
            [
                DISPLAY_NAMES[dataset],
                metadata[dataset]["split"],
                f"{metadata[dataset]['rows']:,}",
                *[score(m2[(dataset, "cherrant", stage, 0.5)]) for stage in STAGES],
            ]
        )
    add_table(lines, ["Dataset", "Split", "N", *STAGES], cherrant_rows)

    lines.extend(
        [
            "The best structured stage exceeds T0 on seven of eight splits; NaCGEC is the exception. Most of the gain occurs at T0 to T1, while T1--T3 changes are small and non-monotonic.",
            "",
            "## Evaluation 2: Projection-based Character M2",
            "",
            "Gold references and hypotheses are regenerated with the same projection-based character alignment. The source-target pairs, reference sets, normalization, edit comparator, and beta values are otherwise controlled. Scores are corpus-level F0.5 multiplied by 100.",
            "",
        ]
    )
    projection_rows = []
    for dataset in order:
        projection_rows.append(
            [
                DISPLAY_NAMES[dataset],
                metadata[dataset]["split"],
                f"{metadata[dataset]['rows']:,}",
                *[score(m2[(dataset, "projection", stage, 0.5)]) for stage in STAGES],
            ]
        )
    add_table(lines, ["Dataset", "Split", "N", *STAGES], projection_rows)

    lines.extend(
        [
            "### Alignment Effect: Projection minus ChERRANT",
            "",
        ]
    )
    delta_rows = []
    for dataset in order:
        delta_rows.append(
            [
                DISPLAY_NAMES[dataset],
                metadata[dataset]["split"],
                *[
                    signed(
                        m2[(dataset, "projection", stage, 0.5)]
                        - m2[(dataset, "cherrant", stage, 0.5)]
                    )
                    for stage in STAGES
                ],
            ]
        )
    add_table(lines, ["Dataset", "Split", *STAGES], delta_rows)
    lines.extend(
        [
            "Projection-based M2 raises F0.5 on seven of eight splits relative to ChERRANT-generated M2; MuCGEC decreases slightly. FlaCGEC changes by about 13 points. These score changes demonstrate alignment sensitivity, but higher downstream scores alone do not prove that an alignment is linguistically more accurate.",
            "",
            "## Evaluation 3: Character GLEU Select-best",
            "",
            "GLEU uses character 1--4 grams. For each sentence and stage, it scores every gold reference, selects the highest reference score, and macro-averages the selected scores. BOM and whitespace are removed; no BPE, word segmentation, or OpenCC conversion is applied. Values are multiplied by 100.",
            "",
        ]
    )
    gleu_table = []
    for dataset in order:
        item = gleu_metadata[dataset]
        gleu_table.append(
            [
                DISPLAY_NAMES[dataset],
                metadata[dataset]["split"],
                f"{item['sentences']:,}",
                f"{item['references']:,}",
                *[score(gleu[(dataset, stage)]) for stage in STAGES],
            ]
        )
    add_table(
        lines,
        ["Dataset", "Split", "N", "References", *STAGES],
        gleu_table,
    )
    lines.extend(
        [
            "YACLC, FCGEC, and NaSGEC-Exam obtain a higher structured-stage GLEU than T0. GLEU often favors conservative outputs that preserve source n-grams, so its ranking need not match edit-based M2 F0.5.",
            "",
            "## Cross-metric Best Stage",
            "",
        ]
    )
    best_rows = []
    for dataset in order:
        ch_best = max(STAGES, key=lambda stage: m2[(dataset, "cherrant", stage, 0.5)])
        pr_best = max(STAGES, key=lambda stage: m2[(dataset, "projection", stage, 0.5)])
        gl_best = max(STAGES, key=lambda stage: gleu[(dataset, stage)])
        best_rows.append(
            [
                DISPLAY_NAMES[dataset],
                metadata[dataset]["split"],
                f"{ch_best} ({score(m2[(dataset, 'cherrant', ch_best, 0.5)])})",
                f"{pr_best} ({score(m2[(dataset, 'projection', pr_best, 0.5)])})",
                f"{gl_best} ({score(gleu[(dataset, gl_best)])})",
            ]
        )
    add_table(
        lines,
        ["Dataset", "Split", "ChERRANT F0.5", "Projection F0.5", "GLEU"],
        best_rows,
    )

    lines.extend(
        [
            "## F1 and F2 Summary",
            "",
            "F1 and F2 were computed with the same M2 comparator. The table reports the best T0--T3 stage for each beta and alignment method.",
            "",
        ]
    )
    beta_best_rows = []
    for dataset in order:
        cells = [DISPLAY_NAMES[dataset], metadata[dataset]["split"]]
        for beta in (1.0, 2.0):
            for alignment in ALIGNMENTS:
                best = max(STAGES, key=lambda stage: m2[(dataset, alignment, stage, beta)])
                cells.append(f"{best} ({score(m2[(dataset, alignment, best, beta)])})")
        beta_best_rows.append(cells)
    add_table(
        lines,
        ["Dataset", "Split", "ChERRANT F1", "Projection F1", "ChERRANT F2", "Projection F2"],
        beta_best_rows,
    )

    lines.extend(
        [
            "## Main Findings",
            "",
            "- Structured prompting is beneficial under character M2 F0.5 on most datasets, with the largest change generally occurring at T0 to T1.",
            "- Additional WB-projection iterations produce small, dataset-dependent, and non-monotonic changes; the process usually converges by T3.",
            "- Projection changes both split and merge boundaries and changes extracted M2 edits substantially enough to alter corpus scores.",
            "- ChERRANT and projection M2 use exactly the same multi-reference setup; only character alignment and resulting edits differ.",
            "- GLEU provides a complementary surface-similarity view and is more favorable to conservative outputs on several datasets.",
            f"- GLEU selected the fourth-or-later reference for **{len(later_reference_sentences):,} unique sentences**, confirming that all references were available to select-best.",
            "- The large FlaCGEC projection delta and the small negative MuCGEC delta warrant qualitative alignment analysis before claiming that projection is universally more accurate.",
            "",
            "## Verification",
            "",
            "- 20,213 saved model outputs were reused; no evaluation rerun called the LLM.",
            "- 38,000 gold references were retained.",
            "- 118,852 projection M2 gold/prediction targets were reconstructed exactly from serialized S/A edits.",
            "- 80,852 GLEU sentence-stage scores were audited and re-aggregated exactly.",
            "- The GLEU CLI was cross-checked against the report runner after fixing the upstream character-tokenization scope bug.",
            "- 35 repository tests passed after the GLEU integration.",
            "",
            "## Historical FlaCGEC T0--T10 Diagnostic",
            "",
            "The earlier direct ChERRANT run extended FlaCGEC to T10. It predates the uniform M2 regeneration, so it is useful only for iteration-depth diagnostics and should not replace the formal T0--T3 table above.",
            "",
        ]
    )
    add_table(
        lines,
        ["Stage", "Precision", "Recall", "F0.5 x100"],
        [
            [
                row["round"],
                score(float(row["Prec"]) * 100),
                score(float(row["Rec"]) * 100),
                score(float(row["F0.5"]) * 100),
            ]
            for row in fla_t10
        ],
    )
    lines.extend(
        [
            "The score plateaus after T2; T8/T10 are only 0.07 points above T2 in this historical evaluation. This supports an empirical iteration limit rather than monotonic improvement through T10.",
            "",
            "## Full Stage-level Metrics",
            "",
            "All M2 values and GLEU values below are multiplied by 100.",
            "",
        ]
    )
    full_rows = []
    for dataset in order:
        for stage in STAGES:
            full_rows.append(
                [
                    DISPLAY_NAMES[dataset],
                    stage,
                    score(m2[(dataset, "cherrant", stage, 0.5)]),
                    score(m2[(dataset, "cherrant", stage, 1.0)]),
                    score(m2[(dataset, "cherrant", stage, 2.0)]),
                    score(m2[(dataset, "projection", stage, 0.5)]),
                    score(m2[(dataset, "projection", stage, 1.0)]),
                    score(m2[(dataset, "projection", stage, 2.0)]),
                    score(gleu[(dataset, stage)]),
                ]
            )
    add_table(
        lines,
        [
            "Dataset",
            "Stage",
            "Ch F0.5",
            "Ch F1",
            "Ch F2",
            "Proj F0.5",
            "Proj F1",
            "Proj F2",
            "GLEU",
        ],
        full_rows,
    )

    lines.extend(
        [
            "## Source Artifacts",
            "",
            "- Uniform ChERRANT M2: [`standardized_m2_eval/`](standardized_m2_eval/)",
            "- All-reference versus first-three audit: [`standardized_m2_eval/scores.all_vs_first3.tsv`](standardized_m2_eval/scores.all_vs_first3.tsv)",
            "- Projection M2 method and scores: [`projection_character_m2_eval/`](projection_character_m2_eval/)",
            "- GLEU method and scores: [`character_gleu_select_best/`](character_gleu_select_best/)",
            "- Pipeline diagnostics: [`scoreboard_t3_summary.tsv`](scoreboard_t3_summary.tsv)",
            "- Projection alignment spot checks: [`projection_character_m2_eval/ALIGNMENT_SPOTCHECK.md`](projection_character_m2_eval/ALIGNMENT_SPOTCHECK.md)",
            "",
            "## Superseded or Diagnostic Results",
            "",
            "- `scoreboard_t3_summary.md` contains preliminary M2 values produced before uniform reference regeneration; use the formal ChERRANT table in this report instead.",
            "- `projection_character_m2_eval_no_t2s_diagnostic/` intentionally omits target `t2s` normalization and is not a controlled paper result.",
            "- `projection_character_m2_eval_pilot*/` and the 20-sentence Flash runs are smoke tests, not final evaluations.",
        ]
    )

    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
