from __future__ import annotations

from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest import mock

from scripts.standardize_m2_evaluation import (
    DatasetSpec,
    audit_m2,
    compare_reference_m2,
    detokenize_m2_text,
    filter_m2_references,
    load_run_names,
    parse_compare_output,
    parse_m2,
    write_cherrant_parallel,
)
from scripts.run_projection_m2_evaluation import evaluate_dataset


M2_WITH_FOUR_REFERENCES = """\
S 我 喜 欢 学 习
T0-A0 我 喜 欢 学 习
A -1 -1|||noop|||-NONE-|||REQUIRED|||-NONE-|||0
T1-A0 我 很 喜 欢 学 习
A 1 1|||M|||很|||REQUIRED|||-NONE-|||1
T1-A1 我 很 喜 欢 学 习
A 0 2|||S|||我 很 喜 欢|||REQUIRED|||-NONE-|||1
T2-A0 我 喜 爱 学 习
A 1 2|||S|||喜 爱|||REQUIRED|||-NONE-|||2
T3-A0 我 喜 欢 学 中文
A 3 3|||M|||中 文|||REQUIRED|||-NONE-|||3
"""


class StandardizedM2EvaluationTest(unittest.TestCase):
    def test_run_names_can_be_overridden_without_changing_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runs.json"
            path.write_text(json.dumps({"mucgec": "mucgec_kimi"}), encoding="utf-8")
            with mock.patch.dict(os.environ, {"CGEC_RUN_NAMES_FILE": str(path)}):
                names = load_run_names()

        self.assertEqual(names["mucgec"], "mucgec_kimi")
        self.assertIn("nlpcc2018", names)

    def test_parse_and_audit_distinguish_references_from_alignments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "all.m2"
            path.write_text(M2_WITH_FOUR_REFERENCES, encoding="utf-8")
            block = parse_m2(path)[0]
            audit = audit_m2(path)

        self.assertEqual(block.reference_ids, {0, 1, 2, 3})
        self.assertEqual(block.target_line_counts[1], 2)
        self.assertEqual(audit["total_references"], 4)
        self.assertEqual(audit["max_references"], 4)
        self.assertEqual(audit["sentences_with_more_than_3_references"], 1)
        self.assertEqual(audit["extra_alignment_target_lines"], 1)

    def test_filter_first_three_references_removes_fourth_annotator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "all.m2"
            destination = Path(tmp) / "first3.m2"
            source.write_text(M2_WITH_FOUR_REFERENCES, encoding="utf-8")
            filter_m2_references(source, destination, 3)
            block = parse_m2(destination)[0]
            text = destination.read_text(encoding="utf-8")

        self.assertEqual(block.reference_ids, {0, 1, 2})
        self.assertNotIn("T3-A0", text)
        self.assertNotIn("|||-NONE-|||3", text)

    def test_compare_reference_m2_collapses_alignment_variants(self) -> None:
        generated = M2_WITH_FOUR_REFERENCES.replace(
            "T1-A1 我 很 喜 欢 学 习\n"
            "A 0 2|||S|||我 很 喜 欢|||REQUIRED|||-NONE-|||1\n",
            "",
        )
        with tempfile.TemporaryDirectory() as tmp:
            official_path = Path(tmp) / "official.m2"
            generated_path = Path(tmp) / "generated.m2"
            official_path.write_text(M2_WITH_FOUR_REFERENCES, encoding="utf-8")
            generated_path.write_text(generated, encoding="utf-8")
            comparison = compare_reference_m2(official_path, generated_path)

        self.assertEqual(comparison["matching_sources"], 1)
        self.assertEqual(comparison["matching_reference_counts"], 1)
        self.assertEqual(comparison["matching_target_sets"], 1)

    def test_compare_reference_m2_can_detokenize_only_official_bpe(self) -> None:
        official = "S 编 号 57 ##1\nT0 编 号 57 ##1\nA -1 -1|||noop||||||REQUIRED|||-NONE-|||0\n"
        generated = "S 编 号 5 7 1\nT0 编 号 5 7 1\nA -1 -1|||noop||||||REQUIRED|||-NONE-|||0\n"
        with tempfile.TemporaryDirectory() as tmp:
            official_path = Path(tmp) / "official.m2"
            generated_path = Path(tmp) / "generated.m2"
            official_path.write_text(official, encoding="utf-8")
            generated_path.write_text(generated, encoding="utf-8")
            comparison = compare_reference_m2(
                official_path,
                generated_path,
                official_bpe=True,
            )

        self.assertEqual(comparison["matching_sources"], 1)
        self.assertEqual(comparison["matching_target_sets"], 1)

    def test_parse_compare_output(self) -> None:
        output = "TP\tFP\tFN\tPrec\tRec\tF0.5\n10 2 3 0.8333 0.7692 0.8197\n"
        metrics = parse_compare_output(output)
        self.assertEqual(metrics["TP"], 10)
        self.assertAlmostEqual(metrics["F0.5"], 0.8197)

    def test_cherrant_parallel_writer_does_not_csv_escape_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "parallel.tsv"
            write_cherrant_parallel(
                [["1", '祖母说"快走"', "祖母说：“快走。”"]],
                path,
            )
            text = path.read_text(encoding="utf-8")

        self.assertEqual(text, '1\t祖母说"快走"\t祖母说：“快走。”\n')
        self.assertNotIn('""', text)

    def test_bpe_detokenization_preserves_literal_hashes(self) -> None:
        self.assertEqual(detokenize_m2_text("57 ##1 多 亿", bpe=True), "571多亿")
        self.assertEqual(detokenize_m2_text("4 # # ～ ##6", bpe=True), "4##～6")

    def test_projection_comparison_uses_explicit_baseline_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline_root = root / "same_model_cherrant"
            baseline_dir = baseline_root / "sample" / "test" / "char"
            projection_dir = root / "projection" / "sample" / "test" / "char"
            baseline_dir.mkdir(parents=True)
            projection_dir.mkdir(parents=True)
            baseline_reference = baseline_dir / "reference.generated.all.char.m2"
            baseline_hypothesis = baseline_dir / "hypothesis.T0.char.m2"
            projection_reference = projection_dir / "reference.projection.all.char.m2"
            projection_hypothesis = projection_dir / "hypothesis.T0.projection.char.m2"
            for path in (
                baseline_reference,
                baseline_hypothesis,
                projection_reference,
                projection_hypothesis,
            ):
                path.write_text("S test\n", encoding="utf-8")
            spec = DatasetSpec(
                dataset="sample",
                split="test",
                rows=1,
                gold_para=root / "gold.para",
                gold_m2=None,
                result_tsv=root / "result.tsv",
                previous_eval_dir=root / "previous",
                bpe=False,
                official_m2_bpe=False,
            )
            with mock.patch(
                "scripts.run_projection_m2_evaluation.run_compare",
                return_value={
                    "TP": 1,
                    "FP": 0,
                    "FN": 0,
                    "Prec": 1.0,
                    "Rec": 1.0,
                    "F_beta": 1.0,
                },
            ) as compare:
                rows = evaluate_dataset(
                    spec,
                    projection_dir,
                    {"reference": projection_reference, "T0": projection_hypothesis},
                    baseline_root=baseline_root,
                    rounds=("T0",),
                    python=Path("python"),
                    row_count=1,
                    is_limited=False,
                )

        self.assertEqual(len(rows), 6)
        hypotheses = [call.kwargs["hypothesis"] for call in compare.call_args_list]
        self.assertEqual(hypotheses[:3], [baseline_hypothesis] * 3)
        self.assertEqual(hypotheses[3:], [projection_hypothesis] * 3)


if __name__ == "__main__":
    unittest.main()
