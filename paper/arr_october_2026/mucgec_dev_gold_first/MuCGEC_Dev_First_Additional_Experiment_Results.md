# MuCGEC Dev: First Additional Experiment Results

**The R/D/P experiment is complete for DeepSeek and Kimi on the supplied 1,079 MuCGEC dev source–Target pairs, using one preselected Target per Source.**

## Data

| Item | Data used in this experiment |
|---|---|
| Dataset | MuCGEC dev, restricted to the supplied 1,079-pair subset |
| Input file actually used | `levcos+human.csv` |
| Source count | 1,079 unique Source sentences |
| Target count | 1,079 preselected Gold Targets; one Target per Source |
| CSV columns | `Index`, `Target_ID`, `Target_Text`, `Source_Text` |
| Source WB in the CSV | Provided human segmentation; removed before constructing R_input/D_input/P_input |
| Target WB in the CSV | Provided LTP segmentation, subsequently reproduced exactly with LTP/base; not human-annotated target WB |
| Evaluation reference scope | The single selected Target in each CSV row, not the full multi-reference release |
| Conditions and coverage | R, D and P for each of two GEC models: 6,474 saved output records, including carry-forwards |
| Dates | GEC generation: October 9, 2026; base-aligned word evaluation: October 10, 2026 |

The subsequently supplied `FINAL_seg_merged_with_labeled.csv` has exactly the same Source, Target, WB, identifiers and row order. It only adds `Source_Type` (`lev`: 953 rows; `cos`: 126 rows). That label was not used to alter prompting or scoring.

The original `levcos+human.csv` SHA256 is `6c1df24a16c81e688468e8a3179ac1bc3abffe89de2ae1018b5ba066e016251e`. Its content was not overwritten during resegmentation.

## Models and settings

### GEC models

| Model | API model identifier | Temperature | Output-token setting | Thinking |
|---|---|---|---|---|
| DeepSeek | `deepseek-v4-pro` | `0.000001`, explicitly set | `max_tokens` omitted; provider default | Disabled |
| Kimi | `kimi-k2.6` | Omitted; endpoint-fixed `0.6` in non-thinking mode | `max_tokens=512`, explicitly set | Disabled |

Top-p and seed were omitted for both models. The original paper prompts were retained: the raw prompt for R and the same segmented-input prompt for D/P. Both ask for minimal grammatical corrections and an output sentence without segmentation spaces. There is one evaluated output per Source and condition; no GPT model was used in this additional experiment.

### Word-boundary and alignment models

| Role | Model/setup actually used |
|---|---|
| D_input generation | `LTP/small`, `ltp==4.2.14`, Python 3.9.23 |
| Target boundaries used to construct P_input | Supplied CSV WB; all 1,079 Target segmentations are reproducible with `LTP/base` |
| Current R_output/D_output/P_output evaluation segmentation | `LTP/base`, `ltp==4.2.14`, Python 3.11.9 |
| Character alignment for projection and M2 | Existing two-step WB aligner with `bert-base-chinese`, the retained shape table and similarity threshold `0.85` |

The base evaluation uses PyTorch 2.7.1 and Transformers 4.54.1, CPU evaluation mode, `tasks=["cws"]`, batch size 32, and no custom dictionary. The base checkpoint revision is `97d6e77d2d7e93c435ec0fb297800f54964323be`.

**Important distinction:** the LTP/base update applies to output evaluation, not to the already-completed prompting inputs. D_input still uses its original small-model WB, and P_input remains the original projection onto that D_input.

## Conditions

- **R:** unsegmented Source → LLM grammatical error correction → R_output.
- **D:** Source segmented with the generation-time LTP/small model → LLM grammatical error correction → D_output.
- **P:** project the supplied Target's existing LTP word boundaries onto the Source, using D_input as the starting segmentation → LLM grammatical error correction → P_output.

The supplied Target was not reselected or replaced. P does not use D_output as its projection target, and no I condition was run. Human Source boundaries were removed before constructing the inputs. The LLM received Source with the relevant boundary presentation, not the complete Target as additional prompt context.

For 782 sources with identical normalized D_input/P_input boundaries, P_output was carried forward from D_output under the existing convergence rule. All three output conditions are available for every source.

All sources remain in the evaluation. Kimi's two content-filter rejections use the recorded identity fallback (output equals Source), following the existing protocol, rather than removing those cases.

## LTP alignment update

Using **Python 3.11.9, ltp 4.2.14 and LTP/base**, we reproduced the supplied Target word boundaries for **all 1,079 Targets**. We then used the same verified base checkpoint to resegment all saved R/D/P outputs for evaluation: 6,474 condition records, comprising 3,443 unique output texts.

The previous mismatch affected 113 condition records across 35 source sentences: their output text exactly matched Target, but their LTP/small output segmentation differed from the supplied Target segmentation. **All of these mismatches are now resolved.** Across all 634 condition outputs whose text exactly matches Target, the word boundaries now match as well.

This was an **evaluation-only update**. D_input retains its generation-time LTP/small boundaries, and P_input retains the original projection from the supplied Target boundaries onto D_input. All Source/Target text, prompting inputs, GEC outputs and character-level scores remain unchanged. No new correction-LLM calls were made.

## Results

All scores are on a 0–100 scale. P−R and P−D are percentage-point differences calculated from unrounded scores.

### DeepSeek — deepseek-v4-pro

| Condition | Char Precision | Char Recall | Char F0.5 | Char GLEU | Word Precision | Word Recall | Word F0.5 | Word GLEU |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| R | 31.85 | 33.93 | 32.24 | 71.22 | 30.95 | 34.85 | 31.66 | 61.28 |
| D | 45.86 | 22.57 | 38.01 | 67.54 | 40.96 | 23.46 | 35.65 | 55.93 |
| P | 45.53 | 22.75 | 37.94 | 67.64 | 41.07 | 23.69 | 35.81 | 56.05 |
| P−R | +13.69 | −11.18 | +5.69 | −3.58 | +10.12 | −11.16 | +4.16 | −5.24 |
| P−D | −0.32 | +0.18 | −0.08 | +0.10 | +0.11 | +0.23 | +0.17 | +0.12 |

### Kimi — kimi-k2.6

| Condition | Char Precision | Char Recall | Char F0.5 | Char GLEU | Word Precision | Word Recall | Word F0.5 | Word GLEU |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| R | 36.34 | 28.19 | 34.35 | 70.16 | 35.07 | 29.16 | 33.70 | 59.70 |
| D | 41.05 | 21.47 | 34.72 | 67.28 | 37.21 | 22.16 | 32.76 | 55.53 |
| P | 42.36 | 21.95 | 35.72 | 67.45 | 38.36 | 22.64 | 33.68 | 55.80 |
| P−R | +6.01 | −6.23 | +1.36 | −2.71 | +3.29 | −6.52 | −0.02 | −3.90 |
| P−D | +1.31 | +0.49 | +1.00 | +0.17 | +1.15 | +0.48 | +0.92 | +0.26 |

## Interpretation

For **DeepSeek**, P is close to D: character F0.5 decreases by 0.08 points, while word F0.5 increases by 0.17 points.

For **Kimi**, P improves over D by 1.00 point in character F0.5 and 0.92 points in word F0.5. Compared with R, however, P's word F0.5 is nearly unchanged and slightly lower (−0.02 points).

R has the highest character and word GLEU for both models. Thus, gold-reference-guided projection does not produce consistent gains across both models and all metrics. These are descriptive comparisons; no new significance or equivalence test was performed.

## Evaluation and reproducibility

Character and word Precision/Recall/F0.5 use the existing projection-derived M2 scorer, with linked U–M movements counted once as WO and both movement thresholds set to 3. Word M2 uses the same fixed P_input source segmentation for every model and condition. Word GLEU retains the established condition-source policy: D_input for R/D, and P_input for P. Output words use LTP/base; Target words retain the supplied, base-compatible tokens. Character GLEU remains character-based. No BPE or OpenCC is used.

Because word GLEU uses condition-specific Source boundaries, its score can change with Source segmentation even when output text is unchanged. Also, this is a selected-single-reference dev subset, not the previous MuCGEC test multi-reference evaluation; the absolute scores should not be compared directly across those settings.

The revised word scores supersede the previous small-model output-tokenization scores for this additional experiment. The earlier results remain preserved separately.

## Project status

The first additional experiment is complete. The prompting paper retains its negative-result framing: providing boundaries can help in some settings, but projected and iterative boundaries do not consistently add gains across models and metrics. The current work does not establish statistical significance or practical equivalence for this dev subset.

The proposed second experiment projecting from R_output will not be run under the current plan. A human-annotated Target-WB experiment is not currently feasible and remains a possible future direction. These are scope decisions, not new empirical results.

## Public artifacts and data restrictions

This progress record publishes code, model/protocol metadata and aggregate metrics only. The MuCGEC CSVs, individual Source/Target sentences, per-sentence predictions and segmentations, M2 files, API request journals, model weights and local environments are not redistributed. API credentials are never part of the publication. Obtain the dataset through its publisher under the applicable terms; see the repository's [data availability documentation](../../../data/benchmarks/README.md).

Files: [unrounded metrics](metrics.tsv), [P−R/P−D differences](deltas.tsv), [previous versus base-aligned word scores](word_metrics_previous_vs_base.tsv), [experiment metadata](experiment_metadata.json), and [validation summary](validation_summary.json). The [experiment protocol](../../../docs/MUCGEC_GOLD_REFERENCE_EXPERIMENT.md) describes the local workflow and retained artifacts.
