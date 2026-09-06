from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
ERRANT_COMPARE = ROOT / "external_tools/errant/errant/commands/compare_m2.py"
CHERRANT_COMPARE = (
    ROOT
    / "external_tools/MuCGEC/scorers/ChERRANT/compare_m2_for_evaluation.py"
)


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ErrantCompareMultiReferenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.args = SimpleNamespace(
            dt=False,
            ds=False,
            cse=False,
            single=False,
            multi=False,
            filt=[],
            beta=0.5,
            verbose=False,
        )
        self.hypothesis = (
            "S 我 喜 欢 茶\n"
            "A 2 3|||S|||咖 啡|||REQUIRED|||-NONE-|||0"
        )
        corrections = ("水", "奶", "果 汁", "可 乐", "咖 啡")
        self.reference = "\n".join(
            ["S 我 喜 欢 茶"]
            + [
                f"A 2 3|||S|||{correction}|||REQUIRED|||-NONE-|||{index}"
                for index, correction in enumerate(corrections)
            ]
        )

    def assert_fifth_reference_is_used(
        self,
        module: ModuleType,
        *,
        cherrant: bool,
    ) -> None:
        if cherrant:
            hypothesis_edits = module.simplify_edits(self.hypothesis, None)
            reference_edits = module.simplify_edits(self.reference, None)
        else:
            hypothesis_edits = module.simplify_edits(self.hypothesis)
            reference_edits = module.simplify_edits(self.reference)
        hypothesis = module.process_edits(hypothesis_edits, self.args)
        references = module.process_edits(reference_edits, self.args)

        self.assertEqual(list(references), [0, 1, 2, 3, 4])
        comparisons = {
            reference_id: module.compareEdits(
                hypothesis[0], references[reference_id]
            )[:3]
            for reference_id in references
        }
        self.assertEqual(comparisons[0], (0, 1, 1))
        self.assertEqual(comparisons[4], (1, 0, 0))

    def test_upstream_errant_uses_fifth_reference(self) -> None:
        self.assert_fifth_reference_is_used(
            load_module("upstream_errant_compare", ERRANT_COMPARE),
            cherrant=False,
        )

    def test_cherrant_comparator_uses_fifth_reference(self) -> None:
        self.assert_fifth_reference_is_used(
            load_module("cherrant_compare", CHERRANT_COMPARE),
            cherrant=True,
        )


if __name__ == "__main__":
    unittest.main()
