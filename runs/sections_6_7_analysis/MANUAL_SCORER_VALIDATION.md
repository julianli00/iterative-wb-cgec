# Manual Scorer Validation

**Status: PASS.** This two-sentence fixture is intentionally small enough to calculate by hand.

## Sentence 1: linked long-distance word order

The hypothesis and reference use different local link identifiers (`w1` and `w7`) but the same origin, destination, and moved material. Each file contains two physical M2 records (`U` and `M`), which the comparator validates and collapses into **one logical `WO` edit**. The result is one `WO` true positive, not two true positives.

## Sentence 2: ordinary edits

Both sides replace `茶` with `咖啡`, giving one `R` true positive. The hypothesis alone inserts `今天`, giving one `M` false positive. The reference alone deletes `很`, giving one `U` false negative.

## Hand calculation

| Logical operation | TP | FP | FN |
| --- | --- | --- | --- |
| M | 0 | 1 | 0 |
| R | 1 | 0 | 0 |
| U | 0 | 0 | 1 |
| W | 0 | 0 | 0 |
| WO (linked M+U) | 1 | 0 | 0 |
| Total | 2 | 1 | 1 |

- Precision = `2 / (2 + 1) = 0.6667`.
- Recall = `2 / (2 + 1) = 0.6667`.
- F0.5 = `1.25 x TP / (1.25 x TP + FP + 0.25 x FN) = 2.5 / 3.75 = 0.6667`.
- Changing only the movement destination produces one `WO` FP and one `WO` FN, confirming strict origin/destination/material matching.

The program output exactly matches all hand-calculated counts and scores.
