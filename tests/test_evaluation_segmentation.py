from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from scripts.evaluation_segmentation import (
    FixedSourceSegmentation,
    load_fixed_segmentations,
    select_closest_reference,
    write_fixed_segmentations,
)


class EvaluationSegmentationTests(unittest.TestCase):
    def test_closest_reference_uses_distance_and_first_tie(self) -> None:
        selected = select_closest_reference(
            "我爱饭", ["我爱吃饭", "我爱米饭", "我爱饭"]
        )
        self.assertEqual(selected.index, 2)
        self.assertEqual(selected.distance, 0)

        tied = select_closest_reference("甲乙", ["甲丙", "丁乙"])
        self.assertEqual(tied.index, 0)

    def test_fixed_segmentation_round_trip(self) -> None:
        record = FixedSourceSegmentation(
            row_index=0,
            item_id="x",
            source="我喜欢苹果",
            selected_reference_index=1,
            selected_reference="我很喜欢苹果",
            selected_reference_normalized="我很喜欢苹果",
            levenshtein_distance=1,
            source_ltp="我 喜欢 苹果",
            selected_reference_ltp="我 很 喜欢 苹果",
            fixed_source_segmentation="我 喜欢 苹果",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixed.tsv"
            write_fixed_segmentations(path, [record])
            loaded = load_fixed_segmentations(
                path, expected_sources=["我喜欢苹果"]
            )
        self.assertEqual(loaded, [record])


if __name__ == "__main__":
    unittest.main()
