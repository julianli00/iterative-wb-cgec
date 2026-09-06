# Final Projection-based DeepSeek CGEC Evaluation

Generated: 2026-08-22 23:54 UTC

**Artifact audit: PASS.** This document supersedes the earlier preliminary reports in this workspace.

## Scope

- Model outputs: saved `deepseek-v4-pro` T0-T3 results; evaluation made no LLM/API calls.
- Decoding used one sample, temperature `0.000001`, disabled thinking, and the paper's Chinese prompts.
- Conditions: T0 Raw, T1 Direct-WB, T2 Projected-WB, and T3 Iterative Projected-WB.
- Final numeric metrics: projection character M2, projection word M2, character GLEU, and word GLEU.
- Normalization: remove BOM and whitespace only; no OpenCC and no BPE.
- ChERRANT is retained only for qualitative alignment examples, not as a competing final score table.

## Dataset Coverage

| Dataset | Split | N | References | Multi-ref. | >3 refs. | Max refs. |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| NLPCC2018 | test | 2,000 | 2,183 | 183 | 0 | 2 |
| MuCGEC | test | 6,000 | 13,119 | 4,268 | 557 | 8 |
| YACLC | validation | 1,000 | 8,931 | 1,000 | 1,000 | 11 |
| FlaCGEC | test | 1,325 | 1,325 | 0 | 0 | 1 |
| FCGEC | validation | 2,000 | 2,550 | 351 | 47 | 8 |
| NaCGEC | test | 5,869 | 6,978 | 1,083 | 4 | 5 |
| NaSGEC-Exam | test | 2,000 | 2,895 | 819 | 5 | 4 |
| CEFE Track 3 | validation | 19 | 19 | 0 | 0 | 1 |

Total: **20,213 sources**, **38,000 references**, and **7,704 multi-reference sources**.

YACLC, FCGEC, and CEFE Track 3 use validation gold because public test gold is unavailable. CEFE Track 3 has only 19 sources and is interpreted descriptively.

## Final Evaluation Protocol

- All available references are retained. M2 and GLEU independently apply sentence-level select-best; there is no three-reference cap.
- For word evaluation, the closest gold reference is selected by minimum raw-character Levenshtein distance after BOM/whitespace removal; ties use the earliest reference.
- Its LTP boundaries are projected to the learner source once. That fixed source segmentation is then shared by all T0-T3 hypotheses, every reference, and both word metrics.
- Ordinary edits use M/R/U/W. Pure reorderings with an envelope of at most three units use W. An unambiguous one-block movement beyond three units uses linked U-M, is scored once, and is reported separately as WO; ambiguous, mixed, or multi-block cases use a round-trippable fallback.
- Linked movements match strictly on origin, destination, moved material, and evaluation unit. The local link identifier is not part of the cross-file key.

## Gold-informed Source Segmentation

The closest-reference selector chose a non-first reference for **3,697/20,213** sources (18.29%). Projection changed the direct LTP source segmentation for **2,121/20,213** sources (10.49%).

## Edit-based Results

Each cell is precision/recall/F0.5 x 100 from the movement-aware comparator.

| Dataset | Char Raw | Char Direct | Char Projected | Char Iterative | Word Raw | Word Direct | Word Projected | Word Iterative |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NLPCC2018 | 32.99/40.18/34.22 | 42.99/30.89/39.87 | 42.87/30.82/39.76 | 42.76/30.92/39.72 | 31.70/40.84/33.19 | 39.69/31.67/37.78 | 39.61/31.61/37.70 | 39.58/31.71/37.71 |
| MuCGEC | 40.70/43.40/41.21 | 53.96/33.71/48.17 | 53.99/33.58/48.14 | 53.88/33.68/48.11 | 40.31/44.10/41.02 | 51.76/34.40/47.02 | 51.77/34.25/46.96 | 51.78/34.32/47.00 |
| YACLC | 57.39/58.44/57.60 | 66.48/51.94/62.96 | 66.84/51.39/63.05 | 66.67/51.54/62.97 | 59.13/59.37/59.17 | 68.22/53.84/64.76 | 68.48/53.21/64.76 | 68.33/53.55/64.75 |
| FlaCGEC | 43.12/43.00/43.10 | 46.42/36.04/43.89 | 46.67/35.99/44.06 | 46.56/36.21/44.04 | 40.29/44.51/41.07 | 42.49/37.28/41.34 | 42.83/37.36/41.61 | 42.82/37.57/41.66 |
| FCGEC | 18.34/38.01/20.46 | 23.63/23.63/23.63 | 23.85/23.55/23.79 | 23.70/23.63/23.69 | 15.82/37.87/17.91 | 18.89/23.68/19.69 | 19.00/23.48/19.76 | 18.91/23.56/19.69 |
| NaCGEC | 30.33/39.19/31.76 | 35.49/25.02/32.75 | 35.88/25.06/33.03 | 35.60/25.05/32.83 | 27.88/40.14/29.69 | 29.68/26.00/28.87 | 29.98/26.06/29.10 | 29.74/26.05/28.92 |
| NaSGEC-Exam | 27.23/42.31/29.32 | 36.24/26.95/33.90 | 36.08/26.54/33.66 | 36.32/26.93/33.95 | 26.35/44.71/28.71 | 32.71/29.47/32.01 | 32.97/29.23/32.15 | 33.11/29.60/32.34 |
| CEFE Track 3 | 46.67/46.67/46.67 | 46.88/33.33/43.35 | 46.88/33.33/43.35 | 46.88/33.33/43.35 | 40.00/45.45/40.98 | 37.21/36.36/37.04 | 37.21/36.36/37.04 | 37.21/36.36/37.04 |

## GLEU Results

Character/word 1-4 gram GLEU uses sentence-level select-best over every reference and macro-averaging; values are x 100.

| Dataset | Char Raw | Char Direct | Char Projected | Char Iterative | Word Raw | Word Direct | Word Projected | Word Iterative |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NLPCC2018 | 73.20 | 70.66 | 70.62 | 70.63 | 64.35 | 60.87 | 60.87 | 60.85 |
| MuCGEC | 75.92 | 74.36 | 74.31 | 74.37 | 67.84 | 65.32 | 65.25 | 65.30 |
| YACLC | 79.86 | 81.44 | 81.39 | 81.42 | 73.12 | 74.86 | 74.82 | 74.87 |
| FlaCGEC | 84.13 | 80.94 | 80.92 | 81.03 | 77.68 | 73.28 | 73.34 | 73.40 |
| FCGEC | 91.77 | 92.76 | 92.78 | 92.77 | 87.45 | 88.92 | 88.98 | 88.95 |
| NaCGEC | 89.67 | 88.91 | 88.93 | 88.92 | 85.02 | 83.79 | 83.83 | 83.80 |
| NaSGEC-Exam | 90.95 | 91.27 | 91.24 | 91.27 | 86.63 | 87.33 | 87.33 | 87.34 |
| CEFE Track 3 | 82.74 | 81.00 | 81.00 | 81.00 | 75.95 | 71.35 | 71.35 | 71.35 |

## Main Findings

- A structured stage exceeds Raw on **7/8** datasets in character F0.5 and **6/8** in word F0.5.
- Direct-WB minus Raw ranges from -3.32 to +6.96 character F0.5 points and from -3.94 to +6.00 word F0.5 points.
- Direct-WB generally increases precision and lowers recall, indicating more conservative correction. CEFE Track 3 is too small for a stable dataset-level inference.
- After Direct-WB, the largest within-dataset T1-T3 spread is only 0.29 character F0.5 and 0.33 word F0.5; projection and further iteration are therefore small and non-monotonic at corpus level.
- A structured stage exceeds Raw on **3/8** datasets in character GLEU and **3/8** in word GLEU. GLEU uses source-aware n-gram overlap rather than exact localized edit matching, so the two metrics need not rank stages alike.

## Iteration Diagnostics

- The first projection changes S1 for 1,666/20,213 sources (8.24%).
- 18,547 stop after Direct-WB, 1,414 stop after Projected-WB, and 252 reach T3; the median is 1 and mean is 1.095 WB-aware passes.
- There are 194 S1-S2-S1 two-cycles (0.96%). The implementation follows the paper's maximum-pass policy rather than claiming convergence for these cases.
- Projection performs 1,016 boundary splits and 1,295 boundary merges through S3, confirming that it supports both operations.

## Validation and Sensitivity

- `L_max_char = 3`: F0.5 is identical under tested values 2, 3, and 4 (maximum range 0.0000).
- `L_max_word = 3`: the maximum F0.5 range under 2, 3, and 4 is 0.0100 points.
- The final files contain 6,296 character-level and 3,237 word-level linked movements across references and T0-T3 hypotheses.
- The artifact audit parsed/reconstructed 262,769 M2 blocks and validated 13,907 linked-pair instances across all stored stage-specific files.
- All 60 repository tests pass.

## Qualitative Evidence

Five manually inspected examples compare final projection character/word annotations with ChERRANT. The evidence supports a narrow representational claim: linked projection isolates moved material and preserves origin/destination, while multi-block permutations use the documented fallback. It is not an aggregate alignment-accuracy claim.

## Pending Experiments

- GPT, Claude, Kimi, and Qwen have not yet been run; the same frozen pipeline should be applied after their outputs are available.
- A C-based-LTP versus Python-LTP consistency comparison is not available in this workspace and is not used by the formal projection results.
- Model 2 fields and cross-model interpretation in the current manuscript must remain pending rather than being inferred from DeepSeek.

## Reproducibility Artifacts

- Tables 5 and 6 audit: [`tables_5_6_evaluation_audit/AUDIT.md`](tables_5_6_evaluation_audit/AUDIT.md)
- Machine-readable scores: [`FINAL_PROJECTION_EVALUATIONS.tsv`](FINAL_PROJECTION_EVALUATIONS.tsv)
- Full artifact audit: [`final_projection_audit/AUDIT.md`](final_projection_audit/AUDIT.md)
- Alignment examples: [`final_alignment_examples/QUALITATIVE_ALIGNMENT_EXAMPLES.md`](final_alignment_examples/QUALITATIVE_ALIGNMENT_EXAMPLES.md)
- Paper-ready inputs: [`PAPER_SECTION_5_3_6_INPUTS.md`](PAPER_SECTION_5_3_6_INPUTS.md)
- Sections 6-7 analysis: [`sections_6_7_analysis/PAPER_SECTIONS_6_7.md`](sections_6_7_analysis/PAPER_SECTIONS_6_7.md)
