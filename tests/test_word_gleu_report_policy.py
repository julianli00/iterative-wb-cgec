from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts import audit_final_projection_artifacts as artifacts
from scripts import audit_tables_5_6 as tables
from scripts import build_final_projection_report as report
from scripts import build_sections_6_7_analysis as sections
from scripts.word_gleu_protocol import CONDITION_SOURCE_COLUMNS, LEGACY_SOURCE_DESCRIPTION


STAGES = tuple(CONDITION_SOURCE_COLUMNS)


def saved_row() -> dict[str, str]:
    return {
        "id": "0",
        "source": "甲乙丙丁",
        "S1": "甲乙 丙丁",
        "S2": "甲 乙丙 丁",
        "S3": "甲乙丙 丁",
        **{stage: "甲乙丙戊" for stage in STAGES},
    }


def condition_sources(row: dict[str, str]) -> dict[str, list[str]]:
    return {stage: [row[column]] for stage, column in CONDITION_SOURCE_COLUMNS.items()}


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_tsv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def write_config(root: Path, policy: str = "condition", **overrides) -> None:
    config = {"hypothesis_and_reference_segmentation": "LTP"}
    if policy == "condition":
        config.update(
            source_segmentation_policy=policy,
            source_stage_mapping=dict(CONDITION_SOURCE_COLUMNS),
            status="completed",
        )
    else:
        config.update(
            source_segmentation=LEGACY_SOURCE_DESCRIPTION,
            completed_utc="2026-09-18T00:00:00+00:00",
        )
    config.update(overrides)
    write_text(root / "run_config.json", json.dumps(config))


class WordGleuReportSourceTests(unittest.TestCase):
    def test_condition_accepts_projected_sources_different_from_word_m2(self) -> None:
        row = saved_row()
        self.assertEqual(
            artifacts.assert_word_gleu_sources(
                condition_sources(row), [row], fixed_sources=["甲 乙 丙 丁"]
            ),
            1,
        )

    def test_condition_normalizes_whitespace_and_bom_not_boundaries(self) -> None:
        row = saved_row()
        sources = condition_sources(row)
        sources["T0"] = ["\ufeff 甲乙\t　丙丁 "]
        self.assertEqual(artifacts.assert_word_gleu_sources(sources, [row]), 1)

    def test_every_condition_requires_its_saved_source_stage(self) -> None:
        row = saved_row()
        for stage, column in CONDITION_SOURCE_COLUMNS.items():
            with self.subTest(stage=stage):
                sources = condition_sources(row)
                sources[stage] = [row["S2" if column != "S2" else "S1"]]
                with self.assertRaisesRegex(ValueError, f"does not match {column}"):
                    artifacts.assert_word_gleu_sources(sources, [row])

    def test_saved_projection_must_preserve_learner_text(self) -> None:
        row = saved_row()
        row["S2"] = "甲 乙丙 戊"
        with self.assertRaisesRegex(ValueError, "changed learner text"):
            artifacts.assert_word_gleu_sources(condition_sources(row), [row])

    def test_missing_saved_segmentation_does_not_fall_back_to_fixed_gold(self) -> None:
        row = saved_row()
        sources = condition_sources(row)
        del row["S1"]
        with self.assertRaisesRegex(ValueError, "Missing or empty S1"):
            artifacts.assert_word_gleu_sources(
                sources, [row], fixed_sources=["甲 乙 丙 丁"]
            )

    def test_missing_stage_or_rows_is_rejected(self) -> None:
        row = saved_row()
        for mutation in ("stage", "rows", "saved_rows"):
            with self.subTest(mutation=mutation):
                sources = condition_sources(row)
                results = [row]
                if mutation == "stage":
                    del sources["T3"]
                elif mutation == "rows":
                    sources["T2"] = []
                else:
                    results = []
                with self.assertRaises(ValueError):
                    artifacts.assert_word_gleu_sources(sources, results, expected_rows=1)

    def test_fixed_gold_retains_stage_invariance_and_word_m2_anchor(self) -> None:
        row = saved_row()
        fixed = ["甲 乙 丙 丁"]
        sources = {stage: list(fixed) for stage in STAGES}
        self.assertEqual(
            artifacts.assert_word_gleu_sources(
                sources, [row], source_policy="fixed-gold", fixed_sources=fixed
            ),
            1,
        )
        sources["T2"] = [row["S2"]]
        with self.assertRaisesRegex(ValueError, "varies by stage"):
            artifacts.assert_word_gleu_sources(
                sources, [row], source_policy="fixed-gold", fixed_sources=fixed
            )
        with self.assertRaisesRegex(ValueError, "differ from fixed word M2"):
            artifacts.assert_word_gleu_sources(
                {stage: [row["S1"]] for stage in STAGES},
                [row],
                source_policy="fixed-gold",
                fixed_sources=fixed,
            )

    def test_word_m2_stage_invariance_is_not_relaxed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f"{stage}.m2" for stage in STAGES]
            for stage, path in zip(STAGES, paths):
                write_text(path, f"S {saved_row()[CONDITION_SOURCE_COLUMNS[stage]]}\n")
            with self.assertRaisesRegex(ValueError, "not stage-invariant"):
                artifacts.assert_stage_invariant(paths, expected_rows=1)


class WordGleuReportMetadataTests(unittest.TestCase):
    modules = (artifacts, tables, report, sections)

    def test_package_imports_share_helpers_even_when_bare_module_loaded_first(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = """
import importlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd() / "scripts"))
importlib.import_module("audit_final_projection_artifacts")
shared = importlib.import_module("scripts.audit_final_projection_artifacts")
shared.WORD_GLEU_ROOT = Path("fixture-condition")
shared.LEGACY_WORD_GLEU_ROOT = Path("fixture-fixed-gold")
for name in (
    "audit_final_projection_artifacts",
    "audit_tables_5_6",
    "build_final_projection_report",
    "build_sections_6_7_analysis",
):
    module = importlib.import_module("scripts." + name)
    assert module.resolve_word_gleu_root is shared.resolve_word_gleu_root, name
    assert module.load_source_policy is shared.load_source_policy, name
    assert module.resolve_word_gleu_root() == shared.WORD_GLEU_ROOT, name
    assert module.resolve_word_gleu_root(source_policy="fixed-gold") == shared.LEGACY_WORD_GLEU_ROOT, name
    explicit = Path("fixture-explicit")
    assert module.resolve_word_gleu_root(explicit) == explicit, name
"""
        completed = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_all_defaults_are_condition_and_legacy_requires_explicit_policy(self) -> None:
        for root in (
            artifacts.WORD_GLEU_ROOT,
            tables.WORD_GLEU_ROOT,
            report.WORD_GLEU.parent,
            sections.WORD_GLEU_ROOT,
        ):
            self.assertEqual(root.name, "word_gleu_condition_select_best")
        parser = argparse.ArgumentParser()
        artifacts.add_word_gleu_arguments(parser)
        self.assertEqual(parser.parse_args([]).word_gleu_source_policy, "condition")
        legacy = parser.parse_args(["--word-gleu-source-policy", "fixed-gold"])
        self.assertEqual(
            artifacts.resolve_word_gleu_root(
                legacy.word_gleu_root, source_policy=legacy.word_gleu_source_policy
            ),
            artifacts.LEGACY_WORD_GLEU_ROOT,
        )

    def test_report_entrypoints_reject_legacy_metadata_in_condition_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_config(root, "fixed-gold")
            for module in self.modules:
                with self.subTest(module=module.__name__):
                    with (
                        mock.patch.object(sys, "argv", ["report", "--word-gleu-root", str(root)]),
                        mock.patch.object(module, "load_specs") as load_specs,
                        self.assertRaisesRegex(ValueError, "policy mismatch"),
                    ):
                        module.main()
                    load_specs.assert_not_called()

    def test_report_entrypoints_reject_incomplete_or_wrong_mapping_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for overrides in (
                {"status": "running"},
                {"source_stage_mapping": {**CONDITION_SOURCE_COLUMNS, "T0": "S2"}},
                {"hypothesis_and_reference_segmentation": "projected"},
            ):
                write_config(root, **overrides)
                for module in self.modules:
                    with self.subTest(module=module.__name__, overrides=overrides):
                        with (
                            mock.patch.object(sys, "argv", ["report", "--word-gleu-root", str(root)]),
                            mock.patch.object(module, "load_specs") as load_specs,
                            self.assertRaises(ValueError),
                        ):
                            module.main()
                        load_specs.assert_not_called()

    def test_missing_condition_run_never_falls_back_to_historical_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            condition = Path(directory) / "condition"
            legacy = Path(directory) / "legacy"
            write_config(legacy, "fixed-gold")
            with (
                mock.patch.object(artifacts, "WORD_GLEU_ROOT", condition),
                mock.patch.object(artifacts, "LEGACY_WORD_GLEU_ROOT", legacy),
                mock.patch.object(sys, "argv", ["report"]),
            ):
                for module in self.modules:
                    with self.subTest(module=module.__name__):
                        with self.assertRaises(FileNotFoundError) as error:
                            module.main()
                        self.assertIn(str(condition), str(error.exception))

    def test_audit_metadata_must_match_policy_mapping_and_root(self) -> None:
        root = Path("runs/word_gleu_condition_select_best")
        good = {"status": "PASS", **artifacts.word_gleu_source_metadata(root, "condition")}
        artifacts.require_word_gleu_audit(
            good, source_policy="condition", word_gleu_root=root
        )
        for overrides in (
            {"status": "FAIL"},
            {"word_gleu_source_policy": "fixed-gold"},
            {"word_gleu_source_stage_mapping": {"T0": "S1"}},
            {"word_gleu_root": str(root / "another-run")},
            {"word_gleu_root": None},
            {"word_gleu_root": 7},
            {"word_gleu_root": ""},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                artifacts.require_word_gleu_audit(
                    {**good, **overrides}, source_policy="condition", word_gleu_root=root
                )
        with self.assertRaisesRegex(ValueError, "policy mismatch"):
            artifacts.require_word_gleu_audit(
                {"status": "PASS"}, source_policy="condition", word_gleu_root=root
            )
        artifacts.require_word_gleu_audit(
            {"status": "PASS"}, source_policy="fixed-gold", word_gleu_root=root
        )


class WordGleuAuditIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.row = saved_row()
        self.spec = SimpleNamespace(
            dataset="cefe_track3",
            split="validation",
            rows=1,
            gold_para=self.root / "gold.para",
        )
        write_text(self.spec.gold_para, "1\t甲乙丙丁\t甲乙丙戊\n")
        self.char_m2 = self.root / "char_m2"
        self.word_m2 = self.root / "word_m2"
        self.char_gleu = self.root / "char_gleu"
        self.word_gleu = self.root / "word_gleu"
        self.output = self.root / "audit"
        self.char_dir = self.char_m2 / self.spec.dataset / self.spec.split / "char"
        self.word_dir = self.word_m2 / self.spec.dataset / self.spec.split / "word"
        m2 = "S 甲 乙 丙 丁\nA 3 4|||R|||戊|||REQUIRED|||-NONE-|||0\n"
        write_text(self.char_dir / "reference.projection.all.char.m2", m2)
        for stage in STAGES:
            write_text(self.char_dir / f"hypothesis.{stage}.projection.char.m2", m2)
            write_text(self.word_dir / f"reference.{stage}.projection.word.m2", m2)
            write_text(self.word_dir / f"hypothesis.{stage}.projection.word.m2", m2)
        m2_scores = [
            {
                "dataset": self.spec.dataset, "round": stage, "alignment": "projection",
                "beta": "0.5", "TP": 1, "FP": 0, "FN": 0,
                "Prec": 1, "Rec": 1, "F_beta": 1,
            }
            for stage in STAGES
        ]
        for root in (self.char_m2, self.word_m2):
            write_tsv(root / "scores.long.tsv", m2_scores)
        gleu_scores = [
            {"dataset": self.spec.dataset, "stage": stage, "gleu_select_best_x100": 100}
            for stage in STAGES
        ]
        for root in (self.char_gleu, self.word_gleu):
            write_tsv(root / "scores.long.tsv", gleu_scores)
        char_inputs = self.char_gleu / self.spec.dataset / self.spec.split / "inputs"
        self.word_inputs = self.word_gleu / self.spec.dataset / self.spec.split / "inputs"
        write_text(char_inputs / "original.txt", "甲乙丙丁\n")
        write_text(char_inputs / "references.tsv", "甲乙丙戊\n")
        for stage in STAGES:
            write_text(char_inputs / f"hypothesis.{stage}.txt", "甲乙丙戊\n")
            write_text(self.word_inputs / f"hypothesis.{stage}.txt", "甲 乙 丙 戊\n")
            write_text(self.word_inputs / f"references.{stage}.tsv", "甲 乙 丙 戊\n")
        self.set_source_policy("condition")

    def set_source_policy(self, policy: str) -> None:
        write_config(self.word_gleu, policy)
        for stage in STAGES:
            source = self.row[CONDITION_SOURCE_COLUMNS[stage]] if policy == "condition" else "甲 乙 丙 丁"
            write_text(self.word_inputs / f"source.{stage}.txt", source + "\n")

    def run_table_audit(self, policy: str = "condition") -> dict:
        arguments = [
            "audit", "--character-m2-root", str(self.char_m2),
            "--word-m2-root", str(self.word_m2),
            "--character-gleu-root", str(self.char_gleu),
            "--word-gleu-root", str(self.word_gleu),
            "--word-gleu-source-policy", policy,
            "--output", str(self.output),
        ]
        with (
            mock.patch.object(sys, "argv", arguments),
            mock.patch.object(tables, "load_specs", return_value=[self.spec]),
            mock.patch.object(tables, "load_result_rows", return_value=[self.row]),
            redirect_stdout(io.StringIO()),
        ):
            tables.main()
        return json.loads((self.output / "audit.json").read_text())

    def test_table_audit_accepts_condition_sources_not_fixed_word_m2(self) -> None:
        audit = self.run_table_audit()
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["word_gleu_source_policy"], "condition")
        self.assertEqual(audit["word_gleu_source_rows_validated"], 1)
        self.assertEqual(audit["published_cells_recomputed"], 16)
        self.assertEqual(audit["word_gleu_source_stage_mapping"], CONDITION_SOURCE_COLUMNS)

    def test_table_audit_rejects_wrong_condition_source_even_when_text_matches(self) -> None:
        write_text(self.word_inputs / "source.T2.txt", self.row["S1"] + "\n")
        with self.assertRaises(SystemExit) as error:
            self.run_table_audit()
        self.assertEqual(error.exception.code, 1)
        audit = json.loads((self.output / "audit.json").read_text())
        self.assertEqual(audit["status"], "FAIL")
        self.assertTrue(any("does not match S2" in issue for issue in audit["issues"]))

    def test_table_audit_explicitly_reproduces_legacy_fixed_gold(self) -> None:
        self.set_source_policy("fixed-gold")
        audit = self.run_table_audit("fixed-gold")
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["word_gleu_source_policy"], "fixed-gold")
        self.assertIsNone(audit["word_gleu_source_stage_mapping"])

    def test_final_artifact_audit_keeps_word_m2_fixed_but_validates_condition_gleu(self) -> None:
        fixed_root = self.root / "fixed"
        write_tsv(
            fixed_root / self.spec.dataset / self.spec.split / "fixed_source_segmentation.tsv",
            [{"source": self.row["source"], "fixed_source_segmentation": "甲 乙 丙 丁"}],
        )
        sensitivity = {
            unit: {"max_f0.5_x100_range": 0, "mean_f0.5_x100_range": 0}
            for unit in ("character", "word")
        }
        with (
            mock.patch.object(sys, "argv", ["audit", "--word-gleu-root", str(self.word_gleu), "--output", str(self.output)]),
            mock.patch.object(artifacts, "ROOT", self.root),
            mock.patch.object(artifacts, "CHARACTER_ROOT", self.char_m2),
            mock.patch.object(artifacts, "WORD_ROOT", self.word_m2),
            mock.patch.object(artifacts, "CHARACTER_GLEU_ROOT", self.char_gleu),
            mock.patch.object(artifacts, "FIXED_SEGMENTATION_ROOT", fixed_root),
            mock.patch.object(artifacts, "load_specs", return_value=[self.spec]),
            mock.patch.object(artifacts, "load_result_rows", return_value=[self.row]),
            mock.patch.object(artifacts, "model_run_audit", return_value={"rows": 1}),
            mock.patch.object(artifacts, "threshold_sensitivity", return_value=sensitivity),
            redirect_stdout(io.StringIO()),
        ):
            artifacts.main()
        audit = json.loads((self.output / "audit.json").read_text())
        self.assertEqual(audit["word_m2_stage_invariant_sources"], 1)
        self.assertEqual(audit["word_gleu_source_rows_validated"], 1)
        self.assertIsNone(audit["word_gleu_stage_invariant_sources"])


class WordGleuReportRenderingTests(unittest.TestCase):
    def test_report_and_paper_prose_distinguish_word_m2_and_word_gleu(self) -> None:
        spec = SimpleNamespace(dataset="cefe_track3", split="validation", rows=1)
        m2 = {(spec.dataset, stage): report.M2Score(1, 0, 0, 100, 100, 100) for stage in STAGES}
        gleu = {(spec.dataset, stage): 100.0 for stage in STAGES}
        refs = {spec.dataset: {"references": 1, "multi_reference_sentences": 0, "more_than_three": 0, "max_references": 1}}
        fixed = {"selected_nonfirst": 0, "changed_from_ltp": 1}
        convergence = {
            "first_projection_changed": 1, "converged_after_direct": 0,
            "converged_after_projected": 0, "reached_t3": 1,
            "median_wb_aware_passes": 3, "mean_wb_aware_passes": 3,
            "two_cycles": 0, "splits": 1, "merges": 1,
        }
        movements = {unit: {"total_linked": 0} for unit in ("character", "word")}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for policy in ("condition", "fixed-gold"):
                audit = {
                    "status": "PASS", **artifacts.word_gleu_source_metadata(root, policy),
                    "threshold_sensitivity": {
                        unit: {"max_f0.5_x100_range": 0} for unit in ("character", "word")
                    },
                    "m2_blocks_validated": 13, "linked_movements_validated": 0,
                }
                with (
                    self.subTest(policy=policy),
                    mock.patch.object(report, "load_specs", return_value=[spec]),
                    mock.patch.object(report, "OUTPUT_MD", root / "report.md"),
                    mock.patch.object(report, "PAPER_OUTPUT", root / "paper.md"),
                ):
                    kwargs = {"word_gleu_source_policy": policy, "word_gleu_root": root}
                    report.build_report(m2, m2, gleu, gleu, refs, fixed, convergence, movements, audit, **kwargs)
                    report.build_paper_inputs(m2, m2, gleu, gleu, fixed, convergence, audit, **kwargs)
                    for path in (root / "report.md", root / "paper.md"):
                        text = path.read_text()
                        self.assertIn(artifacts.word_gleu_protocol_description(policy), text)
                        self.assertNotIn("both word metrics", text)
                        self.assertNotIn("Word evaluation uses the fixed", text)
                    self.assertIn("0/1 datasets in character GLEU", (root / "paper.md").read_text())

    def test_sections_report_uses_policy_matched_audit_rankings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table_audit = root / "tables"
            audit = {
                "status": "PASS", **artifacts.word_gleu_source_metadata(root, "condition"),
                "published_cells_recomputed": 16,
                "rankings_after_two_decimal_rounding": {
                    "character_m2": {"direct_beats_raw": 1},
                    "word_m2": {"direct_beats_raw": 1},
                    "character_gleu": {"structured_beats_raw": 0},
                    "word_gleu": {"structured_beats_raw": 1},
                },
                "stage_summary": [
                    {"stage": stage, "source_copy_percent": 0, "mean_character_distance_from_source": 1}
                    for stage in STAGES
                ],
                "dataset_diagnostics": [{"dataset": "fixture"}],
            }
            write_text(table_audit / "audit.json", json.dumps(audit))
            write_text(table_audit / "AUDIT.md", "**Status: PASS.**\n")
            alignment = root / "alignment.md"
            write_text(alignment, "Fixture alignment evidence.\n")
            aggregate = {
                (unit, stage, category): [1, 0, 0]
                for unit in ("character", "word") for stage in STAGES for category in sections.CATEGORIES
            }
            convergence = {
                "sentences": 1, "first_projection_changed": 1,
                "stopped_after_direct": 0, "stopped_after_projected": 0,
                "reached_T3": 1, "two_cycles": 0,
                "T2_output_changed_given_S2_changed": 0, "second_projection_changed": 1,
                "T3_output_changed_given_S3_changed": 0,
                "splits_through_S3": 1, "merges_through_S3": 1,
            }
            with mock.patch.object(sections, "ALIGNMENT_EXAMPLES", alignment):
                sections.build_paper_report(
                    root, {"TP": 2, "FP": 1, "FN": 1, "f0.5": 2 / 3},
                    aggregate, [convergence], [], word_gleu_root=root, table_audit=table_audit,
                )
            text = (root / "PAPER_SECTIONS_6_7.md").read_text()
            self.assertIn("0/1 datasets in character GLEU and 1/1 in word GLEU", text)
            self.assertIn(artifacts.word_gleu_protocol_description("condition"), text)
            self.assertNotIn("GLEU favors Raw on 5/8", text)
            del audit["word_gleu_source_policy"]
            write_text(table_audit / "audit.json", json.dumps(audit))
            with self.assertRaisesRegex(ValueError, "policy mismatch"):
                sections.build_paper_report(
                    root, {}, {}, [], [], word_gleu_root=root, table_audit=table_audit
                )


if __name__ == "__main__":
    unittest.main()
