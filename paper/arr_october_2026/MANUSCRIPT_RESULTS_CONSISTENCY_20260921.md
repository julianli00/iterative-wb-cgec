# 论文与当前三模型结果的一致性核对

**结论：当前正式结果报告已正确采用新版 Word GLEU，但新上传的 15 页 PDF 尚未同步。** 应更新论文中的相关分数、方法描述和模型范围，不应为了迁就旧稿而修改已经核验的评分结果。

- 核对对象：`_ARR_October_2026__prompting_CGEC (2).pdf`（仅保留于本地，不在公开仓库分发），以下页码均为 PDF 实体页码。
- 审计记录中的 PDF SHA256：`8f968a0a6a943486f6aaf6c6f7c9420f69f0be7440690111c9deed2dc1a06609`。
- 当前正式来源：[Kimi、DeepSeek、GPT-5.6 Sol 独立结果与参数](KIMI_DEEPSEEK_GPT56_EVALUATION_RESULTS.md)。
- 本报告直接整理已完成的逐页审计记录，没有重新读取或修改 PDF，没有重算指标、重新抽样或改动评分器。

## 当前正式报告已经正确

当前报告按 **Kimi → DeepSeek → GPT-5.6 Sol** 分为三个独立章节，每个模型都有调用参数表和独立的 32 行评测表。

全部 **96 个 Word GLEU 值**已与完成的 condition-source 产物逐格核对：R/D 使用 S1，P 使用 S2，I 使用 S3；hypotheses 与全部完整 references 继续使用 LTP。其余 **288 个指标值保持不变**，默认报告没有混入旧 fixed-source Word GLEU。

本次分模型排版前，这 96 个值就已经是新版，因此展示调整没有改变任何指标值。保留历史实验文件，不等于继续把历史数值用于当前正式报告；PDF 是另一份尚未同步的文档。

## 数值逐格核对

| PDF 位置 | 核对内容 | 一致部分 | 需要同步的部分 |
| --- | --- | --- | --- |
| 第 3 页，Table 1 | 两模型四指标，共 256 格 | 192 格 M2 / Character GLEU 全部一致 | 64 格 Word GLEU 全部仍为旧 fixed-source 值 |
| 第 14 页，Table 7 | 两模型 Character / Word GLEU，共 128 格 | 64 格 Character GLEU 全部一致 | 重复使用相同的 64 格旧 Word GLEU |
| 第 13 页，Table 6 | 两模型字符 / 词 M2，共 128 格 | 128 格全部一致 | 不需要修改这些分数 |
| 第 13 页，Table 5 | 主指标差值、区间和等效标记 | 132 个显示数字和 20 个 E 标记全部一致 | 不需要修改现有两模型的这些结果 |
| 第 9 页，Table 3 | 数据集统计 | 45 个显示数字全部一致 | 不需要修改这些数字 |

Table 1 与 Table 7 中是 **64 个不同的旧 Word GLEU 分数、重复出现于 128 个位置**，不是 128 个不同实验条件。它们均能对应历史 shared-fixed-source 分数。

以下例子按 R / D / P / I 排列：

| 模型 / 数据集 | PDF 中的旧 Word GLEU | 当前新版 Word GLEU |
| --- | --- | --- |
| DeepSeek / NLPCC2018 | 64.35 / 60.87 / 60.87 / 60.85 | 63.86 / 60.07 / 59.93 / 59.89 |
| Kimi / YACLC | 74.35 / 73.29 / 73.06 / 73.04 | 74.15 / 73.06 / 72.73 / 72.57 |

应同时替换这两张表中的 Word GLEU 列，并复核这些指标组内的粗体标记。不要改动已匹配的字符 M2、词 M2 或 Character GLEU。

既有审计还明确列出了 DeepSeek 的三处最佳 Word GLEU 标记变化：

| 数据集 | 旧最佳条件与分数 | 新最佳条件与分数 |
| --- | --- | --- |
| YACLC | I：74.87 | D：74.54 |
| FCGEC | P：88.98 | D：88.57 |
| NaSGEC-Exam | I：87.34 | D：86.95 |

## 模型范围与调用参数

**PDF 的下游 CGEC 实验仍只有 DeepSeek 和 Kimi。** GPT-5.6 Sol 确实已经出现在第 9 页 Table 2，但那里是独立的 **1,079 句 intrinsic 词边界实验**，不是当前 **20,213 句下游 GEC 实验**。因此不能说 Sol 从未出现在 PDF，也不能说论文已经纳入 Sol 的下游结果。

第 8–10 页 Appendix D、尤其第 10 页 Table 4 的两个已有模型配置，与记录的基线一致：

| 模型 | PDF 与记录的关系 |
| --- | --- |
| Kimi | `kimi-k2.6`，关闭 thinking；请求省略 temperature，非思考模式由服务端固定为 0.6；显式 `max_tokens=512` |
| DeepSeek | `deepseek-v4-pro`，显式 `temperature=0.000001`，关闭 thinking；`max_tokens` 省略，使用服务端默认 |
| GPT-5.6 Sol | Table 4 缺少下游配置；当前实验是 `gpt-5.6-sol`、显式 `reasoningEffort=none`、已验证 `maxPromptTokens=8192` 输入上限；temperature、top_p 与实际输出上限为未暴露的服务端默认 |

Sol 的下游设置不应自动套用到 Table 2 的 intrinsic 实验。如果论文拟覆盖当前三模型实验，需要补入 Sol 的下游结果、参数及相应叙述，并更新模型数量、对比数量和合并统计范围。完整的请求设置、文档默认值和未暴露项见当前报告各模型的参数表。

## 方法与文本描述需要同步

| PDF 位置 | 发现 | 应如何修改 |
| --- | --- | --- |
| 第 10 页，E.1 | 仍将 word evaluation 整体描述为共享 gold-informed source，与提示条件无关 | 分开写 Word M2 与 Word GLEU：前者仍用共享固定 gold-informed source；后者改为 R/D=S1、P=S2、I=S3。hypotheses 和完整 references 仍由 LTP 分词，Character GLEU 仍按字符计算 |
| 第 2 页，Section 2 | “Projected / Iterative 与 Direct 的 GLEU 差始终不超过 0.25”已不成立 | 修改该概括或限定到实际满足的指标；同时说明 source 边界变化本身也能影响 Word GLEU |
| 第 11 页，E.4 | 相同句级 F0.5 时写成 precision → recall → reference order | 对齐现有实现：最高未舍入句级 F0.5，之后依次更多 TP、更少 FP、更少 FN、先出现的完整参考答案；不修改评分器 |
| 第 11 页，Figure 1 / E.5 | 把普通短距 W 与 linked 长距移动都报告为 W | 当前报告区分 W 与 WO，linked 移动的内部逻辑键为 W-LD；linked U-M pair 仍只计一次，因此无需改变总分 |
| 第 9 页，D.3 | 只描述 BOM / whitespace 移除，容易被理解为原始生成回复没有其它清理 | 区分保存前的 generation cleaning 与保存后的 evaluation normalization：前者还剥离代码围栏、已知回答标签、解释尾段和外围引号；后者仍只移除 BOM / whitespace |

第 2 页概括的两个正式数据集反例，按显示精度计算：

| 模型 / 数据集 | 新版 Word GLEU 对比 | 显示分数差 |
| --- | --- | --- |
| DeepSeek / FlaCGEC | Direct 72.78 → Projected 72.48 | P-D 为 -0.30 |
| Kimi / YACLC | Direct 73.06 → Iterative 72.57 | I-D 为 -0.49 |

E.4 的规则差异并非仅措辞问题：候选计数 `TP/FP/FN=0/1/2` 与 `0/1/1` 的 F0.5、precision、recall 都相同，但现有实现选择 FN 更少的后者；PDF 当前描述会按参考顺序选择前者。应修正文中规则，而不是改变已核验的实现。

## 第 12 页 F.4：secondary 方向敏感数应由 6 改为 5

这里的范围仍是 **DeepSeek / Kimi、七个正式数据集、三个 secondary 指标和三个条件对比，共 126 项**，不包含 Sol、CEFE 或主指标字符 F0.5。

沿用不变的 Word F0.5 / Character GLEU 统计，并替换为新版 Word GLEU 的现有统计后，BCa 与 percentile 的方向分类不同的对比共 **5 项**：Word F0.5 为 0 项，Character GLEU 为 4 项，Word GLEU 为 1 项。

| 模型 | 数据集 | 指标 | 对比 | 差值 | 95% BCa | 95% percentile |
| --- | --- | --- | --- | --- | --- | --- |
| DeepSeek | NaCGEC | Character GLEU | P-D | +0.019249 | [+0.000539, +0.040585] | [-0.000251, +0.039655] |
| DeepSeek | NaSGEC-Exam | Character GLEU | I-P | +0.033965 | [+0.001401, +0.091454] | [-0.004329, +0.079512] |
| Kimi | YACLC | Character GLEU | P-D | -0.240134 | [-0.625065, -0.033337] | [-0.536999, +0.006604] |
| Kimi | FCGEC | Character GLEU | P-D | +0.051607 | [+0.006411, +0.148151] | [-0.003363, +0.121635] |
| Kimi | YACLC | Word GLEU revised | P-D | -0.328893 | [-0.787853, -0.015766] | [-0.725628, +0.024685] |

这是读取现有 `percentile_conclusion_differs` 标记并核对区间端点所得，不是重新抽样。主指标字符 F0.5 的既有稳健性结论保持不变。若加入 Sol，下游模型范围和合并计数需要相应更新，不能直接沿用这里的两模型计数 5。

## 可以保留的结果与核对边界

已匹配的 M2、Character GLEU、数据集统计，以及 Table 5 的既有两模型主指标结论，无需为了这次同步而改动。Raw 为最高 GLEU 的现有计数也保持不变：DeepSeek 为 5/8 个数据集，Kimi 为 8/8，字符和新版词 GLEU 均如此。

核对按 PDF 显示精度进行。本报告没有修改上传 PDF，也没有修改或重新编译 LaTeX；没有独立复现所有 intrinsic 词边界分数或外部引用结果。结论是论文尚未同步当前报告，不是要求重做已经核验的其它指标。

## 逐格记录与结构化证据

- [逐格对照 TSV](manuscript_results_consistency_20260921.tsv)：原样保存父会话审计的 512 条 Table 1 / 6 / 7 对照记录，其中 384 条一致、128 条为重复出现的旧 Word GLEU。
- [结构化 findings JSON](manuscript_results_consistency_20260921.json)：原样保存最新审计结论、PDF 标识、当前报告验证、参数核对、页码、修订建议及限制。
- [当前三模型独立结果与参数](KIMI_DEEPSEEK_GPT56_EVALUATION_RESULTS.md)：正式结果入口。

落盘依据为已完成的 `manuscript_consistency_findings.json`、`paper_v2_score_comparison.tsv`、`paper_v2_primary_and_text_claims.json` 与 `paper_v2_dataset_and_ranking_checks.json`；本步骤仅整理和保存这些审计产物。
