# Paper Inputs for Sections 5.2, 5.3, and 6

This file answers the applicable red placeholders in the 2026-08-19 manuscript. Items requiring models or software not present in the workspace are marked pending rather than guessed.

## Section 5.2: Gold-informed Source Representation

Replace `[EXACT CHARACTER-SEQUENCE SIMILARITY MEASURE]` with:

> raw character-level Levenshtein distance after removing the byte-order mark and all whitespace, selecting the reference with minimum distance

Replace `[TIE-BREAKING RULE]` with:

> the earliest reference in the dataset's original reference order

Audit fact: a non-first reference was selected for 3,697/20,213 sources, and the projected gold-informed segmentation differed from direct LTP for 2,121/20,213 sources.

## Section 5.3: Edit-based Evaluation

Use `3` for both `[CHARACTER THRESHOLD]` and `[WORD THRESHOLD]`.

Recommended clarification:

> We set `L_max_char = 3` and `L_max_word = 3` before final scoring. A pure reordering whose contiguous source envelope contains at most three evaluation units is serialized as one conventional W. When a larger change is an unambiguous one-block movement, it is serialized as linked U and M records with reciprocal FROM/TO coordinates. Mixed lexical changes, ambiguous alignments, crossing movements, and multi-block permutations are not forced into a link; they retain a round-trippable ordinary or encompassing-W representation. Sensitivity runs with thresholds 2, 3, and 4 leave all character F0.5 values unchanged and change word F0.5 by at most 0.01 points.

Comparator wording correction:

> In standard span-based correction mode, ordinary edits match on source span and correction material; the operation label is retained for category reporting but is not part of the default correction key. A linked movement is converted to one logical item and matched strictly on origin interval, destination boundary, moved material, and evaluation unit. It is reported as `WO`, separately from bounded `W`, while still contributing exactly one edit to the aggregate score. The local LINK identifier is ignored across files. Validated origin-side U records are excluded only after their reciprocal M record passes validation.

Normalization statement:

> Byte-order marks and whitespace are removed. No BPE, word segmentation, or OpenCC conversion is applied to character evaluation. Word evaluation uses the fixed gold-informed source segmentation and LTP-segmented hypotheses/references, without BPE or OpenCC.

## Section 6.1.5: Model and Inference Configuration

| Model | Identifier | Provider | Access dates | Temp. | Top-p | Max output | Samples | Kmax |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DeepSeek | deepseek-v4-pro | DeepSeek API | 2026-07-16 to 2026-07-20 | 0.000001 | provider default (omitted) | provider default (omitted) | 1 | 3 |
| Other models | pending | pending | pending | pending | pending | pending | pending | pending |

Paste-ready decoding description:

> We generated one correction per source and condition. The request set temperature to 0.000001 and disabled thinking. It did not set top-p, max_tokens, or a random seed, so provider defaults applied to the omitted fields and exact deterministic decoding should not be claimed. Requests used a 90-second timeout and up to two retries. The final saved DeepSeek files contain no failed rows, empty T0-T3 outputs, or fallback requests without the disabled-thinking field.

Paste-ready output normalization description:

> Response cleaning removes surrounding whitespace and quotation marks, Markdown code fences, recognized Chinese answer labels, and explanation text following recognized explanation headers. It then removes whitespace from the returned Chinese sentence. The final corpus contained no empty stage outputs. The current implementation does not apply a separate grammaticality or semantic-validity filter after this cleaning step.

## Section 6.2.2: Edit Results (Table 5)

Each cell is precision/recall/F0.5 x 100.

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

Paste-ready result summary:

> Direct-WB raises character F0.5 on 7 of eight datasets and word F0.5 on 6 of eight. The improvement is primarily precision-driven: recall decreases on every dataset at character level and on every dataset at word level, while precision generally rises, indicating more conservative correction under explicit boundaries. The strongest Direct-WB gains are +6.96 character F0.5 on MuCGEC and +6.00 word F0.5 on MuCGEC; CEFE Track 3 decreases at both levels but contains only 19 sources. After Direct-WB, Projected-WB and Iterative Projected-WB differ by at most a few tenths of an F0.5 point and do not improve monotonically. The character- and word-based results therefore agree on the main conservative effect of explicit boundaries and on the limited aggregate effect of additional projection passes, while differing on individual dataset rankings.

## Section 6.2.3: GLEU Results (Table 6)

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

Paste-ready GLEU interpretation:

> Character- and word-based GLEU produce the same broad pattern. Direct-WB improves over Raw on YACLC, FCGEC, and NaSGEC-Exam, but decreases on the other 5 datasets. Once boundaries are displayed, projection and further iteration change corpus GLEU only slightly: the largest T1-T3 spread is 0.10 character points and 0.12 word points. The disagreement between GLEU and edit-based F0.5 is plausible because GLEU gives partial credit to reference-supported n-grams and penalizes retained source material, whereas edit scoring requires exact localized correction agreement and weights precision more heavily.

## Additional Section 7 Facts Available Now

- First projection changes S1: 1,666/20,213 (8.24%).
- Stops after Direct/Projected/reaches T3: 18,547/1,414/252.
- Two-cycles S1-S2-S1: 194 (0.96%); handled by Kmax, not reported as convergence.
- Boundary operations through S3: 1,016 splits and 1,295 merges.
- Threshold sensitivity: character max range 0.0000; word max range 0.0100 F0.5 points.
- Five manually inspected ChERRANT/projection examples are in `runs/final_alignment_examples/QUALITATIVE_ALIGNMENT_EXAMPLES.md`.

## Red Items That Remain Pending

- Model 2 and cross-model results: GPT, Claude, Kimi, and Qwen outputs do not yet exist.
- C-based LTP versus Python LTP consistency: no C-based segmentation output or runnable dependency is present; the formal experiments use Python `ltp` 4.2.14.
- Any cross-system comparison table requiring published scores under exactly the same unit, reference set, normalization, and comparator must remain pending unless comparability is established.
