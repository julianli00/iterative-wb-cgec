from __future__ import annotations

import contextlib
import csv
from dataclasses import replace
import io
import json
import math
from pathlib import Path
import shutil
import unittest
from unittest import mock
import uuid

import numpy as np

from scripts import run_paired_bootstrap_analysis as analysis
from scripts.movement_aware_compare import M2Block, ParsedEdit
from scripts.word_gleu_protocol import LEGACY_SOURCE_DESCRIPTION
from scripts.run_paired_bootstrap_analysis import (
    bca_interval,
    boundary_f1,
    boundary_positions,
    correction_relevant_positions,
    micro_f05,
    validate_reference_m2,
)


class PairedBootstrapAnalysisTests(unittest.TestCase):
    def fixture_directory(self) -> Path:
        directory = Path(f".paired-analysis-fixture-{uuid.uuid4().hex}")
        directory.mkdir()
        self.addCleanup(shutil.rmtree, directory)
        return directory

    def test_boundary_positions_compare_vectors_not_whitespace(self) -> None:
        self.assertEqual(
            boundary_positions("进入 餐厅 问\u3000 『 几 个 人 』"),
            boundary_positions("进入 餐厅 问 \u3000 『 几 个 人 』"),
        )
        self.assertNotEqual(boundary_positions("研究 生命"), boundary_positions("研究生 命"))

    def test_boundary_f1(self) -> None:
        self.assertEqual(boundary_f1(frozenset(), frozenset()), 1.0)
        self.assertAlmostEqual(
            boundary_f1(frozenset({1, 2}), frozenset({2, 3})), 0.5
        )

    def test_relevant_positions_include_span_edges_and_insertions(self) -> None:
        block = M2Block(
            source_units=tuple("甲乙丙丁"),
            unit="character",
            edits=(
                ParsedEdit(1, 3, "R", "改", "", 0),
                ParsedEdit(4, 4, "M", "。", "", 0),
            ),
        )
        self.assertEqual(correction_relevant_positions(block), frozenset({1, 2, 3, 4}))

    def test_micro_f05_pools_counts(self) -> None:
        counts = np.asarray([10, 5, 2])
        expected = 1.25 * 10 / (1.25 * 10 + 5 + 0.25 * 2) * 100
        self.assertAlmostEqual(float(micro_f05(counts)), expected)

    def test_bca_interval_contains_constant_statistic(self) -> None:
        low, high = bca_interval(
            np.ones(100), 1.0, np.ones(10), 0.95
        )
        self.assertEqual((low, high), (1.0, 1.0))

    def test_reference_m2_validation_preserves_reference_order(self) -> None:
        block = "\n".join(
            [
                "S 甲 乙",
                "A 1 2|||R|||丙|||REQUIRED|||-NONE-|||0",
                "A -1 -1|||noop|||-NONE-|||REQUIRED|||-NONE-|||1",
            ]
        )
        path = self.fixture_directory() / "reference.m2"
        path.write_text(block, encoding="utf-8")
        self.assertEqual(
            validate_reference_m2(
                path,
                unit="character",
                gold_records=[["id", "甲乙", "甲丙", "甲乙"]],
            ),
            (1, 2),
        )
        with self.assertRaisesRegex(ValueError, "text/order mismatch"):
            validate_reference_m2(
                path,
                unit="character",
                gold_records=[["id", "甲乙", "甲乙", "甲丙"]],
            )

    def model_config(self) -> dict:
        return {
            "key": "gpt6",
            "display": "GPT-6 Astra",
            "identifier": "gpt-6-astra",
            "provider": "GitHub Copilot (OpenAI model)",
            "access_date": "2026-09-18",
            "temperature": "provider default",
            "top_p": "provider default",
            "max_output": "provider default (unexposed)",
            "thinking": "provider default (diagnostic effective reasoning: medium)",
            "run_names": {"nlpcc2018": "nlpcc2018_test_all_T3_gpt_6_astra_copilot_default_paper_converged"},
            "char_root": "projection_character_m2",
            "word_root": "projection_word_m2",
            "char_gleu": "character_gleu/sentence_scores.tsv",
            "word_gleu": "word_gleu_condition/sentence_scores.tsv",
        }

    def test_custom_config_accepts_object_and_list_without_historical_files(self) -> None:
        directory = self.fixture_directory()
        path = directory / "models.json"
        config = self.model_config()
        for payload in (config, [config]):
            with self.subTest(payload_type=type(payload).__name__):
                path.write_text(json.dumps(payload), encoding="utf-8")
                model, = analysis.load_models(path)
                self.assertEqual(model.key, "gpt6")
                self.assertEqual(model.cached_selector_policy, "sentence")
                self.assertEqual(model.word_gleu_source_policy, "condition")
                self.assertEqual(model.char_root, analysis.ROOT / config["char_root"])
                self.assertEqual(model.word_gleu, analysis.ROOT / config["word_gleu"])
                self.assertEqual(model.raw_root, analysis.ROOT / "runs")
                self.assertEqual(model.run_names, config["run_names"])
                self.assertIn("provider default", model.thinking)

    def test_config_run_map_and_paths_are_repository_relative(self) -> None:
        directory = self.fixture_directory()
        config = self.model_config()
        run_map_path = directory / "run_names.json"
        run_map_path.write_text(json.dumps(config["run_names"]), encoding="utf-8")
        config["run_names"] = str(run_map_path)
        config["raw_root"] = str(directory / "raw")
        config["char_root"] = str((directory / "character").resolve())
        config["cached_selector_policy"] = "corpus"
        path = directory / "models.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        model, = analysis.load_models(path)
        self.assertEqual(model.char_root, (directory / "character").resolve())
        self.assertEqual(model.raw_root, analysis.ROOT / directory / "raw")
        self.assertEqual(model.cached_selector_policy, "corpus")
        self.assertEqual(model.run_names, self.model_config()["run_names"])

    def test_config_list_keeps_each_models_declared_cache_policy(self) -> None:
        directory = self.fixture_directory()
        path = directory / "models.json"
        config = self.model_config()
        other = {
            **config, "key": "other", "display": "Other model",
            "cached_selector_policy": "corpus", "char_root": "other/character",
        }
        path.write_text(json.dumps([config, other]), encoding="utf-8")
        models = analysis.load_models(path)
        self.assertEqual([model.key for model in models], ["gpt6", "other"])
        self.assertEqual([model.cached_selector_policy for model in models], ["sentence", "corpus"])
        self.assertEqual(models[1].char_root, analysis.ROOT / "other/character")

    def test_config_rejects_invalid_fields_and_ambiguous_models(self) -> None:
        directory = self.fixture_directory()
        path = directory / "models.json"
        config = self.model_config()
        missing = {key: value for key, value in config.items() if key != "char_gleu"}
        for payload, message in (
            ([], "nonempty list"),
            ([False], "must be an object"),
            (missing, "missing="),
            ({**config, "cached_selector": "sentence"}, "unknown="),
            ({**config, "cached_selector_policy": "auto"}, "cached_selector_policy"),
            ({**config, "word_gleu_source_policy": "auto"}, "word_gleu_source_policy"),
            ({**config, "temperature": 0.5}, "temperature must be a nonempty string"),
            ({**config, "char_root": ""}, "char_root must be a nonempty path"),
            ({**config, "run_names": {"nlpcc2018": 42}}, "dataset-to-run-stem"),
            ([config, config], "duplicate model keys"),
            ([config, {**config, "key": "other"}], "duplicate model display names"),
        ):
            with self.subTest(message=message):
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    analysis.load_models(path)

    def test_default_models_keep_historical_cached_selector_and_settings(self) -> None:
        run_names = {"nlpcc2018": "saved_kimi"}
        with mock.patch.object(Path, "read_text", return_value=json.dumps(run_names)) as read:
            models = analysis.load_models()
        read.assert_called_once()
        self.assertEqual([model.key for model in models], ["deepseek", "kimi"])
        self.assertEqual([model.cached_selector_policy for model in models], ["corpus", "corpus"])
        self.assertEqual([model.thinking for model in models], ["disabled", "disabled"])
        self.assertEqual(models[0].temperature, "0.000001")
        self.assertEqual(models[1].run_names, run_names)
        self.assertEqual(models[1].max_output, "512 tokens")
        self.assertEqual([model.word_gleu_source_policy for model in models], ["condition", "condition"])
        self.assertEqual(models[0].word_gleu, analysis.ROOT / "runs/word_gleu_condition_select_best/sentence_scores.tsv")
        self.assertEqual(models[1].word_gleu, analysis.ROOT / "runs/kimi_k2_6/word_gleu_condition/sentence_scores.tsv")

    def test_fixed_gold_historical_reproduction_requires_explicit_selection(self) -> None:
        with mock.patch.object(Path, "read_text", return_value=json.dumps({"nlpcc2018": "saved_kimi"})):
            models = analysis.load_models(word_gleu_source_policy="fixed-gold")
        self.assertEqual([model.word_gleu_source_policy for model in models], ["fixed-gold", "fixed-gold"])
        self.assertEqual([model.cached_selector_policy for model in models], ["corpus", "corpus"])
        self.assertEqual(models[0].word_gleu, analysis.ROOT / "runs/word_gleu_select_best_final/sentence_scores.tsv")
        self.assertEqual(models[1].word_gleu, analysis.ROOT / "runs/kimi_k2_6/word_gleu/sentence_scores.tsv")
        args = analysis.parse_args(["--word-gleu-source-policy", "fixed-gold"])
        self.assertEqual(analysis.analysis_output(args), analysis.HISTORICAL_OUTPUT.resolve())

    def test_cli_keeps_frozen_defaults_and_protects_historical_output(self) -> None:
        args = analysis.parse_args([])
        self.assertTrue(analysis.frozen_analysis_design(args))
        self.assertEqual(analysis.analysis_output(args), analysis.DEFAULT_OUTPUT.resolve())
        args.model_config = Path("gpt.json")
        with self.assertRaisesRegex(ValueError, "must not overwrite historical tables"):
            analysis.analysis_output(args)
        args.output = analysis.HISTORICAL_OUTPUT / "nested"
        with self.assertRaisesRegex(ValueError, "must not overwrite historical tables"):
            analysis.analysis_output(args)
        args.output = self.fixture_directory() / "analysis"
        self.assertEqual(analysis.analysis_output(args), args.output.resolve())
        args.word_gleu_source_policy = "condition"
        with self.assertRaisesRegex(ValueError, "in the model config"):
            analysis.analysis_output(args)
        with self.assertRaisesRegex(ValueError, "in the model config"):
            analysis.load_models(Path("gpt.json"), word_gleu_source_policy="fixed-gold")
        future = analysis.parse_args(["--output", str(analysis.HISTORICAL_OUTPUT)])
        with self.assertRaisesRegex(ValueError, "must not overwrite historical tables"):
            analysis.analysis_output(future)
        self.assertEqual(analysis.CONDITION_SOURCE_COLUMNS, {"T0": "S1", "T1": "S1", "T2": "S2", "T3": "S3"})

    def test_nonpositive_bootstrap_settings_fail_before_loading_data(self) -> None:
        for flag in ("--replicates", "--chunk-size"):
            with self.subTest(flag=flag):
                with self.assertRaisesRegex(ValueError, "must be positive"):
                    analysis.main([flag, "0"])

    def test_analysis_output_cannot_mix_or_relabel_word_gleu_policies(self) -> None:
        directory = self.fixture_directory()
        config_path = directory / "model.json"
        config_path.write_text(json.dumps(self.model_config()), encoding="utf-8")
        model, = analysis.load_models(config_path)
        fixed = replace(model, word_gleu_source_policy="fixed-gold")
        output = directory / "analysis"
        output.mkdir()
        analysis.validate_output_word_gleu_policy(output, [model])
        (output / "bootstrap_secondary.csv").write_text("metric,delta_points\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unversioned analysis artifacts"):
            analysis.validate_output_word_gleu_policy(output, [model])
        analysis.validate_output_word_gleu_policy(output, [fixed])
        path = output / "analysis_config.json"
        path.write_text(json.dumps({"word_gleu_segmentation": {"source_policy_by_model": {"gpt6": "fixed-gold"}}}), encoding="utf-8")
        analysis.validate_output_word_gleu_policy(output, [fixed])
        with self.assertRaisesRegex(ValueError, "policies differ"):
            analysis.validate_output_word_gleu_policy(output, [model])
        path.write_text(json.dumps({"word_gleu_segmentation": {"source_policy_by_model": {"gpt6": "condition"}}}), encoding="utf-8")
        analysis.validate_output_word_gleu_policy(output, [model])
        with self.assertRaisesRegex(ValueError, "policies differ"):
            analysis.validate_output_word_gleu_policy(output, [fixed])
        path.write_text(json.dumps({"source_outputs": "historical saved runs"}), encoding="utf-8")
        analysis.validate_output_word_gleu_policy(output, [fixed])
        with self.assertRaisesRegex(ValueError, "no explicit word-GLEU policy"):
            analysis.validate_output_word_gleu_policy(output, [model])

    def write_analysis_fixture(
        self, *, policy: str = "sentence", all_datasets: bool = False,
        word_policy: str = "condition", legacy_word_gleu: bool = False,
    ) -> Path:
        directory = self.fixture_directory()
        word_gleu_root = directory / ("word_gleu_condition" if word_policy == "condition" else "word_gleu")
        config = self.model_config()
        config.update(
            run_names="run_names.json",
            raw_root="raw",
            cached_selector_policy=policy,
            word_gleu_source_policy=word_policy,
            word_gleu=str(word_gleu_root.relative_to(directory) / "sentence_scores.tsv"),
        )
        (directory / "model.json").write_text(json.dumps(config), encoding="utf-8")
        sources = ("甲乙丙丁戊", "甲乙丙丁戊己")
        targets = ("一二三四五", "一二三四五六")

        def m2(source: str, target: str, *, extra_noop: bool = False) -> str:
            lines = ["S " + " ".join(source)]
            lines.extend(
                f"A {index} {index + 1}|||R|||{after}|||REQUIRED|||-NONE-|||0"
                for index, (before, after) in enumerate(zip(source, target))
                if before != after
            )
            if extra_noop:
                lines.append("A -1 -1|||noop|||-NONE-|||REQUIRED|||-NONE-|||1")
            return "\n".join(lines)

        manifests = []
        names = {}
        caches = {"character": [], "word": []}
        gleu_rows = []
        gleu_summaries = []
        datasets = list(analysis.DISPLAY_NAMES) if all_datasets else ["nlpcc2018"]
        for dataset in datasets:
            split = "validation" if dataset in {"yaclc", "fcgec", "cefe_track3"} else "test"
            n = 19 if dataset == "cefe_track3" else 2
            run_name = f"{dataset}_{split}_all_T3_gpt_6_astra_copilot_default_paper_converged"
            names[dataset] = run_name
            gold_relative = Path("gold") / dataset / "gold.para"
            gold_path = directory / gold_relative
            gold_path.parent.mkdir(parents=True, exist_ok=True)
            gold_rows = []
            raw_rows = []
            records = []
            references = []
            hypotheses = []
            fixed_rows = []
            for index in range(n):
                variant = index % 2
                source, target = sources[variant], targets[variant]
                source_id = str(index)
                gold_rows.append([source_id, source, target, *([source] if variant else [])])
                hypothesis = target if not variant else "一" + source[1:]
                projected = source[0] + " " + source[1] + " " + source[2:]
                row = {
                    "id": source_id, "source": source,
                    **{stage: hypothesis for stage in analysis.STAGES},
                    "S1": source[:2] + " " + source[2:], "S2": projected, "S3": projected,
                }
                raw_rows.append(row)
                records.append(
                    {
                        **row,
                        "meta": {
                            "api": [
                                {"T": stage, "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}
                                for stage in range(3)
                            ]
                        },
                    }
                )
                references.append(m2(source, target, extra_noop=bool(variant)))
                hypotheses.append(m2(source, hypothesis))
                fixed_rows.append({"fixed_source_segmentation": " ".join(source)})
            with gold_path.open("w", encoding="utf-8", newline="") as handle:
                csv.writer(handle, delimiter="\t").writerows(gold_rows)
            manifests.append({"dataset": dataset, "split": split, "rows": n, "gold_para": str(gold_relative)})
            analysis.write_rows(directory / "raw" / f"{run_name}.tsv", raw_rows, list(raw_rows[0]))
            (directory / "raw" / f"{run_name}.jsonl").write_text(
                "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
                encoding="utf-8",
            )
            analysis.write_rows(
                directory / "runs/gold_fixed_source_segmentation" / dataset / split / "fixed_source_segmentation.tsv",
                fixed_rows,
                ["fixed_source_segmentation"],
            )
            for unit in ("character", "word"):
                leaf = directory / f"projection_{unit}_m2" / dataset / split / ("char" if unit == "character" else "word")
                leaf.mkdir(parents=True, exist_ok=True)
                for stage in analysis.STAGES:
                    reference_path = leaf / (
                        "reference.projection.all.char.m2" if unit == "character" else f"reference.{stage}.projection.word.m2"
                    )
                    hypothesis_path = leaf / f"hypothesis.{stage}.projection.{'char' if unit == 'character' else 'word'}.m2"
                    reference_path.write_text("\n\n".join(references) + "\n", encoding="utf-8")
                    hypothesis_path.write_text("\n\n".join(hypotheses) + "\n", encoding="utf-8")
                    _counts, _selected, sentence, corpus, _refs = analysis.evaluate_stage(
                        hypothesis_path, reference_path, unit=unit
                    )
                    caches[unit].append(
                        {
                            "dataset": dataset, "round": stage, "beta": 0.5, "alignment": "projection",
                            "F_beta": (sentence if policy == "sentence" else corpus) / 100.0,
                        }
                    )
            for stage in analysis.STAGES:
                inputs = word_gleu_root / dataset / split / "inputs"
                inputs.mkdir(parents=True, exist_ok=True)
                source_lines = [
                    row[analysis.CONDITION_SOURCE_COLUMNS[stage]]
                    if word_policy == "condition" else fixed["fixed_source_segmentation"]
                    for row, fixed in zip(raw_rows, fixed_rows)
                ]
                (inputs / f"source.{stage}.txt").write_text("\n".join(source_lines) + "\n", encoding="utf-8")
                for index in range(n):
                    gleu_rows.append(
                        {
                            "dataset": dataset, "stage": stage, "id": str(index),
                            "gleu_select_best": 0.5, "selected_reference": 0,
                            "reference_count": 1 + index % 2,
                        }
                    )
                gleu_summaries.append({"dataset": dataset, "stage": stage, "gleu_select_best_x100": 50.0})
        for unit in ("character", "word"):
            analysis.write_rows(directory / f"projection_{unit}_m2" / "scores.long.tsv", caches[unit], list(caches[unit][0]))
            gleu_root = word_gleu_root if unit == "word" else directory / "character_gleu"
            scores = gleu_rows
            summaries = gleu_summaries
            if unit == "word" and not legacy_word_gleu:
                scores = [{**row, "source_segmentation_policy": word_policy} for row in scores]
                summaries = [{**row, "source_segmentation_policy": word_policy} for row in summaries]
            analysis.write_rows(gleu_root / "sentence_scores.tsv", scores, list(scores[0]))
            analysis.write_rows(gleu_root / "scores.long.tsv", summaries, list(summaries[0]))
        if legacy_word_gleu:
            word_config = {
                "source_segmentation": LEGACY_SOURCE_DESCRIPTION,
                "hypothesis_and_reference_segmentation": "LTP",
                "completed_utc": "2026-09-01T00:00:00+00:00",
            }
        else:
            word_config = {
                "source_segmentation_policy": word_policy,
                "source_stage_mapping": dict(analysis.CONDITION_SOURCE_COLUMNS) if word_policy == "condition" else None,
                "hypothesis_and_reference_segmentation": "LTP",
                "status": "completed",
                "completed_utc": "2026-09-19T00:00:00+00:00",
            }
        (word_gleu_root / "run_config.json").write_text(json.dumps(word_config), encoding="utf-8")
        (directory / "manifest.json").write_text(json.dumps(manifests), encoding="utf-8")
        (directory / "run_names.json").write_text(json.dumps(names), encoding="utf-8")
        return directory

    def fixture_inputs(self, directory: Path) -> tuple:
        model, = analysis.load_models(directory / "model.json")
        dataset, = analysis.load_datasets()
        char_gleu = analysis.load_gleu(model.char_gleu, [dataset])
        word_gleu = analysis.load_gleu(model.word_gleu, [dataset])
        return model, dataset, char_gleu, word_gleu

    def test_word_gleu_requires_explicit_completed_metadata(self) -> None:
        directory = self.write_analysis_fixture()
        with mock.patch.multiple(analysis, ROOT=directory.resolve(), MANIFEST=directory / "manifest.json"):
            model, _dataset, _char, _word = self.fixture_inputs(directory)
            path = model.word_gleu.parent / "run_config.json"
            original = json.loads(path.read_text(encoding="utf-8"))
            cases = [
                ([], "must be an object"),
                ({}, "(?i)missing or unknown"),
                ({**original, "source_segmentation_policy": "unknown"}, "(?i)missing or unknown"),
                ({**original, "status": "running"}, "not complete"),
                ({**original, "status": "failed"}, "not complete"),
                ({key: value for key, value in original.items() if key != "status"}, "not complete"),
                ({key: value for key, value in original.items() if key != "source_segmentation_policy"}, "(?i)missing or unknown"),
                ({**original, "source_stage_mapping": None}, "source-stage mapping"),
                ({**original, "source_stage_mapping": {**analysis.CONDITION_SOURCE_COLUMNS, "T0": "source"}}, "source-stage mapping"),
                ({**original, "hypothesis_and_reference_segmentation": "character"}, "must use LTP"),
                ({key: value for key, value in original.items() if key != "hypothesis_and_reference_segmentation"}, "must use LTP"),
            ]
            for config, message in cases:
                with self.subTest(config=config):
                    path.write_text(json.dumps(config), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, message):
                        analysis.validate_word_gleu_metadata(model)
            path.unlink()
            with self.assertRaisesRegex(ValueError, "missing word-GLEU policy metadata"):
                analysis.validate_word_gleu_metadata(model)

    def test_word_gleu_metadata_uses_shared_protocol_helpers(self) -> None:
        directory = self.write_analysis_fixture()
        with mock.patch.multiple(analysis, ROOT=directory.resolve(), MANIFEST=directory / "manifest.json"):
            model, _dataset, _char, _word = self.fixture_inputs(directory)
            config = json.loads((model.word_gleu.parent / "run_config.json").read_text(encoding="utf-8"))
            with (
                mock.patch.object(analysis, "source_policy_from_config", wraps=analysis.source_policy_from_config) as detect,
                mock.patch.object(analysis, "load_source_policy", wraps=analysis.load_source_policy) as load,
            ):
                metadata = analysis.validate_word_gleu_metadata(model)
            detect.assert_called_once_with(config)
            load.assert_called_once_with(
                model.word_gleu.parent, expected_policy="condition", require_completed=True
            )
            self.assertEqual(metadata.policy, "condition")
            self.assertFalse(metadata.legacy_fixed)

    def test_fixed_gold_legacy_metadata_only_passes_when_explicitly_declared(self) -> None:
        directory = self.write_analysis_fixture(word_policy="fixed-gold", legacy_word_gleu=True)
        with mock.patch.multiple(analysis, ROOT=directory.resolve(), MANIFEST=directory / "manifest.json"):
            model, dataset, char_gleu, word_gleu = self.fixture_inputs(directory)
            metadata = analysis.validate_word_gleu_metadata(model)
            self.assertTrue(metadata.legacy_fixed)
            analysis.validate_gleu_summary(model, "word", word_gleu)
            block, _audit = analysis.load_block(model, dataset, char_gleu, word_gleu)
            self.assertTrue(all(row["metadata_format"] == "legacy-fixed" for row in block.word_gleu_source_audit))
            self.assertTrue(all(row["legacy_unlabeled_sentences"] == dataset.rows for row in block.word_gleu_source_audit))
            self.assertEqual(block.word_gleu_sources["T0"], block.fixed_boundaries)
            with self.assertRaisesRegex(ValueError, "policy mismatch"):
                analysis.load_block(
                    replace(model, word_gleu_source_policy="condition"), dataset, char_gleu, word_gleu
                )
            path = metadata.config_path
            original = json.loads(path.read_text(encoding="utf-8"))
            for config, message in (
                ({key: value for key, value in original.items() if key != "completed_utc"}, "not complete"),
                ({**original, "source_segmentation": "unspecified source"}, "(?i)missing or unknown"),
                ({**original, "source_segmentation_policy": None}, "missing explicit"),
                ({**original, "status": None}, "missing explicit"),
            ):
                with self.subTest(config=config):
                    path.write_text(json.dumps(config), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, message):
                        analysis.validate_word_gleu_metadata(model)

    def test_new_fixed_gold_artifacts_still_require_completed_status_and_labels(self) -> None:
        directory = self.write_analysis_fixture(word_policy="fixed-gold")
        with mock.patch.multiple(analysis, ROOT=directory.resolve(), MANIFEST=directory / "manifest.json"):
            model, dataset, char_gleu, word_gleu = self.fixture_inputs(directory)
            metadata = analysis.validate_word_gleu_metadata(model)
            self.assertFalse(metadata.legacy_fixed)
            analysis.load_block(model, dataset, char_gleu, word_gleu)
            path = metadata.config_path
            config = json.loads(path.read_text(encoding="utf-8"))
            config["source_segmentation"] = LEGACY_SOURCE_DESCRIPTION
            del config["status"]
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not completed"):
                analysis.validate_word_gleu_metadata(model)
            config["status"] = "completed"
            path.write_text(json.dumps(config), encoding="utf-8")
            del word_gleu[(dataset.dataset, "T0")][0]["source_segmentation_policy"]
            with self.assertRaisesRegex(ValueError, "row policy mismatch"):
                analysis.load_block(model, dataset, char_gleu, word_gleu)
            config["source_stage_mapping"] = analysis.CONDITION_SOURCE_COLUMNS
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must not declare condition"):
                analysis.validate_word_gleu_metadata(model)

    def test_word_gleu_rejects_mixed_or_unlabeled_sentence_and_summary_rows(self) -> None:
        directory = self.write_analysis_fixture()
        with mock.patch.multiple(analysis, ROOT=directory.resolve(), MANIFEST=directory / "manifest.json"):
            model, dataset, char_gleu, word_gleu = self.fixture_inputs(directory)
            analysis.validate_gleu_summary(model, "character", char_gleu)
            row = word_gleu[(dataset.dataset, "T2")][0]
            for label in ("fixed-gold", "", None):
                with self.subTest(label=label):
                    if label is None:
                        row.pop("source_segmentation_policy", None)
                    else:
                        row["source_segmentation_policy"] = label
                    with self.assertRaisesRegex(ValueError, "row policy mismatch"):
                        analysis.load_block(model, dataset, char_gleu, word_gleu)
            row["source_segmentation_policy"] = "condition"
            path = model.word_gleu.parent / "scores.long.tsv"
            summaries = analysis.read_tsv(path)
            summaries[0]["source_segmentation_policy"] = "fixed-gold"
            analysis.write_rows(path, summaries, list(summaries[0]))
            with self.assertRaisesRegex(ValueError, "row policy mismatch"):
                analysis.validate_gleu_summary(model, "word", word_gleu)

    def test_word_gleu_source_inputs_match_saved_stages_not_just_source_text(self) -> None:
        directory = self.write_analysis_fixture()
        with mock.patch.multiple(analysis, ROOT=directory.resolve(), MANIFEST=directory / "manifest.json"):
            model, dataset, char_gleu, word_gleu = self.fixture_inputs(directory)
            block, _audit = analysis.load_block(model, dataset, char_gleu, word_gleu)
            self.assertEqual(block.word_gleu_sources["T0"], block.word_gleu_sources["T1"])
            self.assertEqual(block.word_gleu_sources["T0"], block.boundaries["D"])
            self.assertEqual(block.word_gleu_sources["T2"], block.boundaries["P"])
            self.assertEqual(block.word_gleu_sources["T3"], block.boundaries["I"])
            self.assertNotEqual(block.word_gleu_sources["T0"], block.boundaries["R"])
            path = model.word_gleu.parent / dataset.dataset / dataset.split / "inputs/source.T0.txt"
            path.write_text("\n".join(block.sources) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source boundaries mismatch.*expected S1"):
                analysis.load_block(model, dataset, char_gleu, word_gleu)
            path.write_text("\n".join(block.word_gleu_sources["T2"]) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source boundaries mismatch.*expected S1"):
                analysis.load_block(model, dataset, char_gleu, word_gleu)
            path.write_text(
                "\n".join(" \t " + line.replace(" ", " \u3000\t  ") + "  " for line in block.word_gleu_sources["T0"]) + "\n",
                encoding="utf-8",
            )
            normalized_block, _audit = analysis.load_block(model, dataset, char_gleu, word_gleu)
            self.assertEqual(normalized_block.word_gleu_sources["T0"], block.word_gleu_sources["T0"])
            path.write_text(block.word_gleu_sources["T0"][0] + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source-input row count mismatch"):
                analysis.load_block(model, dataset, char_gleu, word_gleu)
            path.unlink()
            with self.assertRaisesRegex(ValueError, "Missing word-GLEU source inputs"):
                analysis.load_block(model, dataset, char_gleu, word_gleu)

    def test_condition_word_gleu_does_not_change_fixed_word_m2_invariant(self) -> None:
        directory = self.write_analysis_fixture()
        with mock.patch.multiple(analysis, ROOT=directory.resolve(), MANIFEST=directory / "manifest.json"):
            model, dataset, char_gleu, word_gleu = self.fixture_inputs(directory)
            raw_rows, _records = analysis.load_raw_records(model, dataset)
            path = directory / "runs/gold_fixed_source_segmentation" / dataset.dataset / dataset.split / "fixed_source_segmentation.tsv"
            analysis.write_rows(
                path,
                [{"fixed_source_segmentation": row["S1"]} for row in raw_rows],
                ["fixed_source_segmentation"],
            )
            with self.assertRaisesRegex(ValueError, "word M2 source segmentation.*shared fixed-gold"):
                analysis.load_block(model, dataset, char_gleu, word_gleu)

    def test_word_gleu_can_change_with_identical_hypotheses_without_changing_edit_scores(self) -> None:
        directory = self.write_analysis_fixture()
        with mock.patch.multiple(analysis, ROOT=directory.resolve(), MANIFEST=directory / "manifest.json"):
            model, dataset, char_gleu, word_gleu = self.fixture_inputs(directory)
            for stage in ("T2", "T3"):
                for row in word_gleu[(dataset.dataset, stage)]:
                    row["gleu_select_best"] = "0.25"
            block, _audit = analysis.load_block(model, dataset, char_gleu, word_gleu)
            self.assertEqual(block.outputs["T1"], block.outputs["T2"])
            self.assertNotEqual(block.word_gleu_sources["T1"], block.word_gleu_sources["T2"])
            draws = analysis.bootstrap_block(block, replicates=32, seed=20260915, chunk_size=8)
            np.testing.assert_array_equal(draws["character_f05"]["P-D"], np.zeros(32))
            np.testing.assert_array_equal(draws["word_f05"]["P-D"], np.zeros(32))
            np.testing.assert_array_equal(draws["character_gleu"]["P-D"], np.zeros(32))
            np.testing.assert_array_equal(draws["word_gleu"]["P-D"], np.full(32, -25.0))
            record = analysis.interval_record(
                block, "word_gleu", ("P-D", "D", "P"), draws["word_gleu"]["P-D"],
                replicates=32, seed=20260915,
            )
            self.assertEqual(record["word_gleu_source_policy"], "condition")
            self.assertEqual(record["delta_points"], -25.0)

    def test_reports_label_explicit_mixed_policies_without_pooling_them(self) -> None:
        directory = self.fixture_directory()
        config = self.model_config()
        fixed = {
            **config, "key": "historical", "display": "Historical reproduction",
            "word_gleu_source_policy": "fixed-gold", "word_gleu": "word_gleu/sentence_scores.tsv",
        }
        path = directory / "models.json"
        path.write_text(json.dumps([config, fixed]), encoding="utf-8")
        models = analysis.load_models(path)
        report = analysis.word_gleu_policy_report(models)
        self.assertIn("MIXED WORD-GLEU POLICIES", report)
        self.assertIn("| GPT-6 Astra | condition | S1 | S1 | S2 | S3 |", report)
        self.assertIn("| Historical reproduction | fixed-gold | fixed-gold | fixed-gold | fixed-gold | fixed-gold |", report)
        self.assertIn("Do not pool", report)
        args = analysis.parse_args(["--model-config", str(path), "--output", str(directory / "analysis")])
        payload = analysis.config_payload(args, models)
        self.assertEqual(
            payload["word_gleu_segmentation"]["source_policy_by_model"],
            {"gpt6": "condition", "historical": "fixed-gold"},
        )

    def test_cached_selector_validation_keeps_sentence_counts_and_both_audits(self) -> None:
        for policy in ("corpus", "sentence"):
            with self.subTest(policy=policy):
                directory = self.write_analysis_fixture(policy=policy)
                with (
                    mock.patch.object(analysis, "ROOT", directory.resolve()),
                    mock.patch.object(analysis, "MANIFEST", directory / "manifest.json"),
                ):
                    model, dataset, char_gleu, word_gleu = self.fixture_inputs(directory)
                    block, audit = analysis.load_block(model, dataset, char_gleu, word_gleu)
                    np.testing.assert_array_equal(block.char_counts.sum(axis=0), [[6, 0, 5]] * 4)
                    np.testing.assert_array_equal(block.word_counts.sum(axis=0), [[6, 0, 5]] * 4)
                    self.assertEqual(len(audit), 8)
                    self.assertTrue(all(row["configured_selector_reproduces_cached"] for row in audit))
                    self.assertTrue(all(row["cached_selector_policy"] == policy for row in audit))
                    self.assertTrue(all(row["legacy_reproduces_cached"] == (policy == "corpus") for row in audit))
                    self.assertTrue(all(row["sentence_local_reproduces_cached"] == (policy == "sentence") for row in audit))
                    other = "sentence" if policy == "corpus" else "corpus"
                    with self.assertRaisesRegex(ValueError, f"{other} selector score.*does not reproduce"):
                        analysis.load_block(replace(model, cached_selector_policy=other), dataset, char_gleu, word_gleu)

    def test_custom_selector_does_not_bypass_complete_gold_reference_validation(self) -> None:
        directory = self.write_analysis_fixture()
        with (
            mock.patch.object(analysis, "ROOT", directory.resolve()),
            mock.patch.object(analysis, "MANIFEST", directory / "manifest.json"),
        ):
            model, dataset, char_gleu, word_gleu = self.fixture_inputs(directory)
            _hypothesis, reference = analysis.m2_paths(model, dataset, "T0", "word")
            reference.write_text(
                reference.read_text(encoding="utf-8").replace(
                    "A -1 -1|||noop|||-NONE-|||REQUIRED|||-NONE-|||1\n", ""
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "reference IDs mismatch"):
                analysis.load_block(model, dataset, char_gleu, word_gleu)

    def test_custom_main_keeps_frozen_dataset_totals_check(self) -> None:
        directory = self.write_analysis_fixture(all_datasets=True)
        with (
            mock.patch.object(analysis, "ROOT", directory.resolve()),
            mock.patch.object(analysis, "MANIFEST", directory / "manifest.json"),
        ):
            with self.assertRaisesRegex(ValueError, "Dataset-statistics mismatch"):
                analysis.main(
                    ["--model-config", str(directory / "model.json"), "--output", str(directory / "analysis")]
                )
        self.assertFalse((directory / "analysis").exists())

    def test_custom_main_requires_complete_run_name_coverage(self) -> None:
        directory = self.write_analysis_fixture(all_datasets=True)
        names_path = directory / "run_names.json"
        names = json.loads(names_path.read_text(encoding="utf-8"))
        del names["mucgec"]
        names_path.write_text(json.dumps(names), encoding="utf-8")
        with (
            mock.patch.object(analysis, "ROOT", directory.resolve()),
            mock.patch.object(analysis, "MANIFEST", directory / "manifest.json"),
        ):
            with self.assertRaisesRegex(ValueError, "run_names coverage mismatch: missing=.*mucgec"):
                analysis.main(
                    ["--model-config", str(directory / "model.json"), "--output", str(directory / "analysis")]
                )
        self.assertFalse((directory / "analysis").exists())

    def test_custom_main_writes_all_outputs_without_historical_models(self) -> None:
        directory = self.write_analysis_fixture(all_datasets=True)
        output = directory / "analysis"
        with (
            mock.patch.object(analysis, "ROOT", directory.resolve()),
            mock.patch.object(analysis, "MANIFEST", directory / "manifest.json"),
            mock.patch.object(analysis, "build_paper_report", side_effect=AssertionError("historical report used")),
        ):
            statistics = analysis.build_dataset_statistics(analysis.load_datasets())
            totals = {
                key: sum(row[key] for row in statistics)
                for key in ("sentences", "references", "multi_reference_sentences", "sentences_over_3_references")
            }
            totals["max_references"] = max(row["max_references"] for row in statistics)
            with mock.patch.object(analysis, "EXPECTED_DATASET_TOTALS", totals), contextlib.redirect_stdout(io.StringIO()):
                analysis.main(
                    [
                        "--model-config", str(directory / "model.json"), "--output", str(output),
                        "--replicates", "64", "--chunk-size", "16",
                    ]
                )
        expected = {
            "table_2_dataset_statistics.tsv", "table_2_dataset_statistics.md",
            "table_3_model_configuration.tsv", "table_3_model_configuration.md",
            "PAPER_TABLES.tex", "analysis_config.json", "scorer_selection_audit.tsv", "word_gleu_source_audit.tsv",
            "sentence_level_scores.tsv", "bootstrap_primary.csv", "bootstrap_secondary.csv",
            "equivalence_sensitivity.csv", "changed_boundary_diagnostics.csv", "convergence_and_cost.csv",
            "validation.log", "PAPER_TABLES_AND_ANALYSIS.md", "README_ANALYSIS_COMPLIANCE.md",
        }
        self.assertEqual({path.name for path in output.iterdir()}, expected)
        for name in expected:
            text = (output / name).read_text(encoding="utf-8")
            self.assertNotIn("DeepSeek", text, name)
            self.assertNotIn("Kimi", text, name)
            self.assertNotIn("Thinking was disabled", text, name)
            self.assertNotIn("512 tokens", text, name)
        exported = analysis.read_tsv(output / "sentence_level_scores.tsv")
        self.assertEqual(len(exported), totals["sentences"] * 4)
        self.assertTrue(all(row["word_gleu_source_policy"] == "condition" for row in exported))
        self.assertTrue(all(row["word_m2_source_policy"] == "fixed-gold" for row in exported))
        self.assertTrue(all(row["word_gleu_source_stage"] == analysis.CONDITION_SOURCE_COLUMNS[row["stage"]] for row in exported))
        audit = analysis.read_tsv(output / "scorer_selection_audit.tsv")
        self.assertEqual(len(audit), 64)
        self.assertTrue(all(row["cached_selector_policy"] == "sentence" for row in audit))
        validation = (output / "validation.log").read_text(encoding="utf-8")
        self.assertIn("PASS sentence-local mode reproduces all 64 cached M2 table cells", validation)
        self.assertIn("SKIP frozen historical-model run invariants", validation)
        self.assertNotIn("all 128", validation)
        self.assertIn("NONSTANDARD frozen analysis design", validation)
        self.assertIn("word-GLEU policy=condition", validation)
        self.assertIn("word M2 retains shared fixed-gold source boundaries", validation)
        word_audit = analysis.read_tsv(output / "word_gleu_source_audit.tsv")
        self.assertEqual(len(word_audit), 32)
        self.assertTrue(all(row["source_segmentation_policy"] == "condition" for row in word_audit))
        self.assertTrue(all(row["completion_evidence"] == "status=completed" for row in word_audit))
        self.assertTrue(all(row["source_boundaries_match_saved"] == "True" for row in word_audit))
        self.assertTrue(all(len(row["source_inputs_sha256"]) == 64 for row in word_audit))
        config = json.loads((output / "analysis_config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["models"][0]["key"], "gpt6")
        self.assertEqual(config["models"][0]["cached_selector_policy"], "sentence")
        self.assertEqual(config["seed"], 20260915)
        self.assertEqual(config["bootstrap_replicates"], 64)
        self.assertFalse(config["word_gleu_segmentation"]["retokenized_by_analysis"])
        self.assertEqual(config["word_gleu_segmentation"]["source_policy_by_model"], {"gpt6": "condition"})
        self.assertEqual(config["word_gleu_segmentation"]["source_stage_mapping_by_model"]["gpt6"], analysis.CONDITION_SOURCE_COLUMNS)
        self.assertEqual(config["word_m2_segmentation"]["source_policy"], "fixed-gold")
        for name, count in (
            ("bootstrap_primary.csv", 24), ("bootstrap_secondary.csv", 72),
            ("equivalence_sensitivity.csv", 42), ("changed_boundary_diagnostics.csv", 16),
            ("convergence_and_cost.csv", 8),
        ):
            with (output / name).open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), count, name)
            for row in rows:
                if name.startswith("bootstrap_"):
                    self.assertEqual(row["word_gleu_source_policy"], "condition" if row["metric"] == "word_gleu" else "")
                    if row["dataset_key"] == "cefe_track3":
                        self.assertEqual(row["bootstrap_replicates"], "0")
                        self.assertEqual(row["ci95_bca_low"], "")
                        self.assertEqual(row["equivalent"], "")
                    else:
                        self.assertEqual(row["bootstrap_replicates"], "64")
                        self.assertEqual(float(row["delta_points"]), 0.0)
                if name == "equivalence_sensitivity.csv":
                    self.assertNotEqual(row["dataset_key"], "cefe_track3")
                    self.assertEqual(row["equivalent"], "True")
                if name == "changed_boundary_diagnostics.csv" and row["dataset_key"] == "cefe_track3":
                    self.assertTrue(math.isnan(float(row["changed_subset_char_f05_ci95_bca_low"])))
                    self.assertTrue(math.isnan(float(row["mean_sentence_boundary_f1_delta_ci95_bca_low"])))
        report = (output / "PAPER_TABLES_AND_ANALYSIS.md").read_text(encoding="utf-8")
        self.assertIn("| GPT-6 Astra | P-D | 7 | 0 | 0 | 7 | 7 | 7 |", report)
        self.assertIn("CEFE Track 3 (n=19)", report)
        self.assertIn("**NONSTANDARD ANALYSIS SETTINGS:**", report)
        self.assertIn("diagnostic effective reasoning: medium", report)
        self.assertIn("| GPT-6 Astra | condition | S1 | S1 | S2 | S3 |", report)
        self.assertIn("even with an identical hypothesis", report)
        self.assertIn("word M2 still uses shared fixed gold-informed", report)
        self.assertNotIn("Word GLEU is unchanged", report)
        self.assertIn("0/0 (NA)", report)
        checklist = (output / "README_ANALYSIS_COMPLIANCE.md").read_text(encoding="utf-8")
        self.assertIn("SKIPPED", checklist)
        self.assertIn("NONSTANDARD; not the frozen final analysis", checklist)

    def test_explicit_fixed_gold_main_records_legacy_metadata_exceptions_honestly(self) -> None:
        directory = self.write_analysis_fixture(all_datasets=True, word_policy="fixed-gold", legacy_word_gleu=True)
        output = directory / "analysis"
        with mock.patch.multiple(analysis, ROOT=directory.resolve(), MANIFEST=directory / "manifest.json"):
            statistics = analysis.build_dataset_statistics(analysis.load_datasets())
            totals = {
                key: sum(row[key] for row in statistics)
                for key in ("sentences", "references", "multi_reference_sentences", "sentences_over_3_references")
            }
            totals["max_references"] = max(row["max_references"] for row in statistics)
            with mock.patch.object(analysis, "EXPECTED_DATASET_TOTALS", totals), contextlib.redirect_stdout(io.StringIO()):
                analysis.main(
                    [
                        "--model-config", str(directory / "model.json"), "--output", str(output),
                        "--replicates", "16", "--chunk-size", "8",
                    ]
                )
        audit = analysis.read_tsv(output / "word_gleu_source_audit.tsv")
        self.assertEqual(len(audit), 32)
        self.assertTrue(all(row["source_segmentation_policy"] == "fixed-gold" for row in audit))
        self.assertTrue(all(row["metadata_format"] == "legacy-fixed" for row in audit))
        self.assertTrue(all(row["completion_evidence"].startswith("legacy completed_utc=") for row in audit))
        self.assertTrue(all(row["policy_labeled_sentences"] == "0" for row in audit))
        log = (output / "validation.log").read_text(encoding="utf-8")
        self.assertIn("word-GLEU policy=fixed-gold", log)
        self.assertIn("SKIP GPT-6 Astra new-format word-GLEU status/policy metadata", log)
        report = (output / "PAPER_TABLES_AND_ANALYSIS.md").read_text(encoding="utf-8")
        self.assertIn("| GPT-6 Astra | fixed-gold | fixed-gold | fixed-gold | fixed-gold | fixed-gold |", report)
        config = json.loads((output / "analysis_config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["word_gleu_segmentation"]["source_policy_by_model"], {"gpt6": "fixed-gold"})

    def test_historical_report_declares_actual_word_gleu_policy(self) -> None:
        for policy in ("condition", "fixed-gold"):
            with self.subTest(policy=policy):
                directory = self.write_analysis_fixture(word_policy=policy)
                with mock.patch.multiple(analysis, ROOT=directory.resolve(), MANIFEST=directory / "manifest.json"):
                    model, dataset, char_gleu, word_gleu = self.fixture_inputs(directory)
                    block, _audit = analysis.load_block(model, dataset, char_gleu, word_gleu)
                    statistics = analysis.build_dataset_statistics([dataset])
                    with mock.patch.object(Path, "read_text", return_value=json.dumps({"nlpcc2018": "saved_kimi"})):
                        models = analysis.load_models(word_gleu_source_policy=policy)
                blocks = [replace(block, model=model) for model in models]
                primary = [
                    analysis.interval_record(
                        value, "character_f05", contrast, np.zeros(32), replicates=32, seed=20260915
                    )
                    for value in blocks
                    for contrast in analysis.CONTRASTS
                ]
                boundaries = [
                    {
                        "model": model.display, "contrast": contrast,
                        "changed_boundary_sentences": 1, "sentences": dataset.rows,
                        "changed_subset_output_changes": 0, "boundary_f1_closer_sentences": 0,
                        "boundary_f1_farther_sentences": 0, "correction_relevant_overlap_positions": 0,
                        "changed_boundary_positions": 1,
                    }
                    for model in models for contrast in ("P-D", "I-P")
                ]
                report = analysis.build_paper_report(
                    statistics, models, blocks, primary, [], [], boundaries,
                    [analysis.convergence_record(value) for value in blocks],
                )
                self.assertIn("## Word GLEU source policy", report)
                self.assertIn(f"| DeepSeek | {policy} |", report)
                self.assertIn(f"| Kimi | {policy} |", report)
                self.assertIn("Word GLEU source policy", report)
                self.assertIn("even with an identical hypothesis", report)
                self.assertIn("word M2 still uses shared fixed gold-informed", report)
                self.assertNotIn("all are near-zero endpoint cases", report)

    def test_custom_latex_uses_configured_metadata_and_escapes_it(self) -> None:
        directory = self.fixture_directory()
        config = self.model_config()
        config.update(display="Model & sample_1", identifier="model_1", provider="Provider #1 100%")
        path = directory / "model.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        models = analysis.load_models(path)
        row, = analysis.configured_model_latex_rows(models)
        self.assertIn(r"Model \& sample\_1", row)
        self.assertIn(r"\texttt{model\_1}", row)
        self.assertIn(r"Provider \#1 100\%", row)
        self.assertIn(config["thinking"], row)
        self.assertNotIn("disabled", row)


if __name__ == "__main__":
    unittest.main()
