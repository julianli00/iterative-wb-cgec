# Kimi K2.6 vs. DeepSeek V4 Pro

Both models are compared on the same eight dataset splits, paper prompts, T0-T3 stage mapping, convergence rule, gold references, projection-based MRU+W/WO evaluation, and select-best GLEU protocol. DeepSeek used disabled thinking and temperature 0.000001; Kimi K2.6 used disabled thinking and its provider-fixed non-thinking temperature of 0.6.

## Overall Comparison

| Metric | DeepSeek same-stage wins | Kimi same-stage wins | DeepSeek best-stage wins | WB helps DeepSeek | WB helps Kimi |
| --- | ---: | ---: | ---: | ---: | ---: |
| Character F0.5 | 29/32 | 3/32 | 8/8 datasets | 7/8 | 3/8 |
| Word F0.5 | 29/32 | 3/32 | 8/8 datasets | 6/8 | 2/8 |
| Character GLEU | 31/32 | 1/32 | 8/8 datasets | 3/8 | 0/8 |
| Word GLEU | 31/32 | 1/32 | 8/8 datasets | 3/8 | 0/8 |

`WB helps` means that at least one of T1, T2, or T3 is higher than T0 for that model and dataset. `Best-stage wins` compares each model's highest T0-T3 score for every dataset.

## Primary Character F0.5

| Dataset | DeepSeek best | Stage | Kimi best | Stage | DeepSeek - Kimi |
| --- | ---: | --- | ---: | --- | ---: |
| NLPCC2018 | 39.87 | T1 | 36.80 | T3 | +3.07 |
| MuCGEC | 48.17 | T1 | 44.19 | T2 | +3.98 |
| YACLC | 63.05 | T2 | 60.86 | T1 | +2.19 |
| FlaCGEC | 44.06 | T2 | 34.71 | T0 | +9.35 |
| FCGEC | 23.79 | T2 | 18.52 | T0 | +5.27 |
| NaCGEC | 33.03 | T2 | 28.70 | T0 | +4.33 |
| NaSGEC-Exam | 33.95 | T3 | 27.35 | T0 | +6.60 |
| CEFE Track 3 | 46.67 | T0 | 40.67 | T0 | +6.00 |

## Interpretation

1. DeepSeek is the stronger GEC model under this experiment. It has the higher best-stage score for every dataset under all four evaluation metrics.
2. Kimi is competitive only at Raw T0 on a few datasets: it beats DeepSeek at T0 for NLPCC2018, MuCGEC, and YACLC under both M2 metrics, and for YACLC under both GLEU metrics.
3. DeepSeek wins every structured T1-T3 cell across all four metrics. It therefore follows the structured WB prompt more effectively than Kimi.
4. WB-aware prompting is beneficial much more often for DeepSeek. Kimi's structured stages fail to beat Raw on every dataset under both GLEU evaluations.
5. Further projection remains mixed for both models. T2/T3 occasionally recover a small amount over T1, but do not produce consistent monotonic improvement.
6. The comparison is not decoding-identical because Kimi enforces temperature 0.6 in non-thinking mode while DeepSeek was run near deterministically. The prompts, data, pipeline, and evaluation are otherwise aligned.

Both result packages passed independent 128-cell reconstruction audits.
