# Tables 5 and 6 Evaluation Audit

**Status: PASS.** All checks use saved T0-T3 outputs; no LLM or API calls are made.

## Reproduction

The audit reconstructs every M2 score from the final hypothesis/reference files and every GLEU score from the saved source, hypothesis, and all-reference text inputs.

| Metric | Cells | Maximum absolute difference (x100) |
| --- | --- | --- |
| Character F0.5 | 32 | 0.000000000 |
| Word F0.5 | 32 | 0.000000000 |
| Character GLEU | 32 | 0.000000500 |
| Word GLEU | 32 | 0.000000000 |

The stage-to-input mapping also passes: T0 is the Raw output, T1 is Direct-WB, T2 is the first projected-boundary output, and T3 is the next iterative output. Whenever a projected segmentation is unchanged, the previous correction is carried forward without a new generation.

## What The Tables Show

| Metric | Any structured > Raw | Direct > Raw | Projected > Raw | Iterative > Raw | Projected >/=/< Direct | Iterative >/=/< Projected |
| --- | --- | --- | --- | --- | --- | --- |
| Character F0.5 | 3/8 | 3/8 | 2/8 | 3/8 | 4/0/4 | 4/2/2 |
| Word F0.5 | 2/8 | 2/8 | 2/8 | 2/8 | 4/0/4 | 3/2/3 |
| Character GLEU | 0/8 | 0/8 | 0/8 | 0/8 | 2/2/4 | 5/2/1 |
| Word GLEU | 0/8 | 0/8 | 0/8 | 0/8 | 3/0/5 | 3/2/3 |

Across character/word F0.5, a structured condition is higher than Raw on 3/8 and 2/8 datasets, respectively. For character/word GLEU, the corresponding counts are 0/8 and 0/8. Projected and Iterative are not consistently above Direct.

## Why Projection Changes Are Small

- 18,487/20,213 sentences (91.46%) stop after Direct-WB, so T2 and T3 are exact carry-forwards of T1.
- 1,432/20,213 (7.08%) stop after the first projected pass.
- Only 294/20,213 (1.45%) reach a second projected generation at T3.

## Raw Versus WB-aware Output Behavior

| Stage | Condition | Normalized source copies | Copy rate | Mean char distance from source | Same as previous stage |
| --- | --- | --- | --- | --- | --- |
| T0 | Raw | 1,772 | 8.77% | 3.293 | - |
| T1 | Direct-WB | 5,877 | 29.08% | 2.238 | 8,427 |
| T2 | Projected-WB | 5,960 | 29.49% | 2.203 | 19,610 |
| T3 | Iterative Projected-WB | 5,913 | 29.25% | 2.214 | 20,010 |

Raw is not the more source-preserving condition in these outputs. It changes the source much more aggressively. GLEU rewards reference-supported n-grams and penalizes source n-grams that a reference changes, whereas F0.5 rewards exact localized edits and weights precision more heavily. The two metrics can therefore rank the same outputs differently without an evaluation error.

## Projection-affected Rows

The following deltas re-evaluate only rows where the first projection actually changes S1 into S2. Positive values favor Projected-WB over Direct-WB.

| Dataset | N | Char F0.5 delta | Word F0.5 delta | Char GLEU delta | Word GLEU delta |
| --- | --- | --- | --- | --- | --- |
| nlpcc2018 | 199 | -0.2500 | +0.8100 | -1.2654 | -1.2047 |
| mucgec | 587 | +0.5800 | +0.1900 | -0.6882 | -0.7344 |
| yaclc | 111 | -3.0400 | -1.5100 | -2.1634 | -2.0050 |
| flacgec | 142 | +3.4500 | +2.6000 | +0.0488 | -0.1690 |
| fcgec | 131 | +1.1900 | +0.6400 | +0.7879 | +1.0801 |
| nacgec | 421 | -0.0700 | -0.4100 | +0.3791 | +0.3284 |
| nasgec_exam | 132 | -1.5800 | -0.8400 | +0.0572 | +0.2109 |
| cefe_track3 | 3 | -13.5100 | -10.2000 | -0.7503 | -1.1012 |

The affected subset is mixed rather than uniformly positive. This confirms that the small corpus-level effect is not merely a scoring dilution artifact: projection helps some datasets and hurts others.

## Conclusion

The Table 5 and Table 6 values are correctly evaluated under the manuscript's stated protocol. The current Kimi-k2.6 results do not support a universal claim that Direct-WB, Projected-WB, or further Iterative Projected-WB is better than Raw. The appropriate interpretation is a model- and dataset-dependent empirical result, rather than an evaluator problem.
