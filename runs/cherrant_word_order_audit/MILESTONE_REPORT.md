# Milestone Report

This report documents the current milestone on ChERRANT label analysis and projection-based representation of long-distance word-order changes.

## 1. ChERRANT Label Inventory and Word-Order Detection

### 1.1 Character-level labels

At character granularity, ChERRANT writes four coarse labels to M2:

| Label | ChERRANT meaning | Underlying alignment operation |
| --- | --- | --- |
| `M` | Missing material | Insertion (`I`) |
| `R` | Redundant material | Deletion (`D`) |
| `S` | Substitution | Substitution (`S`) |
| `W` | Word/character-order error | Transposition (`T`) |

Character mode does not attach POS or spelling subtypes. The label conventions must be kept distinct:

| System | Coarse labels | Meaning |
| --- | --- | --- |
| ChERRANT character M2 | `M/R/S/W` | missing, redundant, substitution, word order |
| Standard ERRANT | `M/R/U` prefixes | missing, replacement, unnecessary |
| Projection M2 used in this work | `M/R/U/W` | missing, replacement, unnecessary, word order |

In particular, ChERRANT's `R` means *redundant/deletion*, while standard ERRANT and the projection M2 use `R` for *replacement* and `U` for *unnecessary/deletion*.

### 1.2 Word-level refinements

At word granularity, ChERRANT refines M/R/S as follows:

- A single-token insertion or deletion becomes `M:<POS>` or `R:<POS>`.
- Multi-token insertions/deletions become `M:OTHER` or `R:OTHER`.
- A substitution may become `S:SPELL`, `S:<POS>`, or `S:OTHER`.
- The coarse POS inventory includes NOUN, VERB, ADJ, CONJ, PRON, ADV, AUX, NUM, PREP, QUAN, PUNCT, and OTHER; `MC` is also available for missing-component markers.
- A transposition remains the coarse label `W`; ChERRANT does not add a POS subtype to W.

The present comparison uses character-level ChERRANT output, so the observed labels are M/R/S/W without these word-level subtypes.

### 1.3 How ChERRANT decides W

ChERRANT has two routes to W:

1. **Direct dynamic-programming transposition.** Starting with a span of two tokens, it expands backward and compares the sorted source and target spans. If the sorted spans are equal, the alignment receives an internal `T<n>` operation; the classifier converts every T operation to the M2 label `W`. ChERRANT does not emit `T` as a final M2 label.
2. **Local merger heuristics.** After alignment, ChERRANT can merge `S-M-S` or `D-M-I`/`I-M-D` edit patterns into a T/W operation. These checks allow exact swaps and several near-match cases based on edit distance or cyclic rotation.

### 1.4 Minimum and maximum length

- The direct transposition search has a **minimum span length of two** characters or words.
- The inspected implementation has **no fixed maximum span length**. In particular, there is no two-character, three-character, or three-word cap.
- The merger inspects local sequences of three edit groups, but that is a structural pattern, not a three-character/three-word maximum.
- In practice, W still depends on the minimum-cost alignment path. A long permutation can therefore be decomposed into M/R/S before the classifier sees it, even though there is no formal length cap.

### 1.5 Empirical check on the saved outputs

Across the eight datasets and four saved stages, ChERRANT processed **80,852 sentence outputs** and generated **113,821 character edits**: M=36,220, R=29,061, S=40,544, and W=7,996. W appears in 7,553 sentence-stage outputs.

### 1.6 Current `errant_compare` and more than three references

The current upstream ERRANT 3.0.2 comparator was checked separately because two unrelated uses of the number three can be confused:

- `-cat {1,2,3}` still denotes exactly three **error-category reporting tiers**: operation, main category, and the full combined category.
- The number of **gold references is not capped at three**. `errant_compare` reads every annotator/coder ID in an M2 block and iterates over every hypothesis-reference combination.
- The ChERRANT comparator used in the current pipeline behaves the same way when `--max_answer_num` is omitted. All formal runs omit this option, so every reference is retained.
- In a synthetic five-reference test, both comparators loaded reference IDs 0--4 and matched the hypothesis only against ID 4, confirming that the fifth reference is evaluated.
- In a real YACLC check, where every sentence has 4--11 references, upstream ERRANT 3.0.2 and the current ChERRANT comparator produced the same projection-character T0 result: P=0.5740, R=0.5841, and F0.5=0.5760.

Accordingly, the current results already implement evaluation with more than three references; no pipeline or score-table update is required.

## 2. Long-distance Word-Order Annotation Examples

All examples below are real T0--T3 system outputs, not manually authored gold references. Each has a projection word-level W span in which at least one token moves four or more positions. They were selected from cases where ChERRANT did not emit W. The examples illustrate representational differences and should still be manually adjudicated before use as final paper evidence.

### Example 1: nasgec_exam T1 row 14

**Source:** 市教研室通过多年的努力，评价方法得当、操作程序公开透明、让所有人都心服口服的一套高考质量评估方案出台了。

**GEC system output:** 市教研室通过多年的努力，出台了一套评价方法得当、操作程序公开透明、让所有人都心服口服的高考质量评估方案。

**Movement:** one projection W span over 23 tokens (`7:30`), with a maximum token displacement of 21 positions.

**Projection word representation:**

> `评价 方法 得当 、 操作 程序 公开 透明 、 让 所有 人 都 心服口服 的 一 套 高考 质量 评估 方案 出台 了`
>
> becomes `出台 了 一 套 评价 方法 得当 、 操作 程序 公开 透明 、 让 所有 人 都 心服口服 的 高考 质量 评估 方案`

**Projection character M2:**

- `W`: reorder "评价方法得当、操作程序公开透明、让所有人都心服口服的一套高考质量评估方案出台了" as "出台了一套评价方法得当、操作程序公开透明、让所有人都心服口服的高考质量评估方案" at 12:51

**ChERRANT character M2:**

- `M`: insert "出台了一套" at boundary 12
- `R`: delete "一套" at 38:40
- `R`: delete "出台了" at 48:51

**Summary:** Projection uses 1 character edit(s), including `W`; ChERRANT fragments the change into 3 edit(s): `M,R,R`.

### Example 2: nacgec T0 row 3619

**Source:** 中国本土作家首获诺贝尔文学奖，不仅代表着蕴含中国特色、风格的中国文学已走向世界，更标志着莫言的作品被世界认同。

**GEC system output:** 中国本土作家首获诺贝尔文学奖，不仅标志着莫言的作品被世界认同，更代表着蕴含中国特色、风格的中国文学已走向世界。

**Movement:** one projection W span over 23 tokens (`10:33`), with a maximum token displacement of 15 positions.

**Projection word representation:**

> `代表 着 蕴含 中国 特色 、 风格 的 中国 文学 已 走向 世界 ， 更 标志 着 莫言 的 作品 被 世界 认同`
>
> becomes `标志 着 莫言 的 作品 被 世界 认同 ， 更 代表 着 蕴含 中国 特色 、 风格 的 中国 文学 已 走向 世界`

**Projection character M2:**

- `W`: reorder "代表着蕴含中国特色、风格的中国文学已走向世界，更标志着莫言的作品被世界认同" as "标志着莫言的作品被世界认同，更代表着蕴含中国特色、风格的中国文学已走向世界" at 17:54

**ChERRANT character M2:**

- `M`: insert "标志着莫言的作品被世界认同，更" at boundary 17
- `R`: delete "世界，更标志着莫言的作品被" at 37:50
- `R`: delete "认同" at 52:54

**Summary:** Projection uses 1 character edit(s), including `W`; ChERRANT fragments the change into 3 edit(s): `M,R,R`.

### Example 3: nacgec T0 row 5064

**Source:** 平民文化的重新崛起，不仅会对我国整个社会文化的建设大有裨益，更会对我国电影产业的发展起到巨大推动作用。

**GEC system output:** 平民文化的重新崛起，不仅会对我国电影产业的发展起到巨大推动作用，更会对我国整个社会文化的建设大有裨益。

**Movement:** one projection W span over 23 tokens (`7:30`), with a maximum token displacement of 14 positions.

**Projection word representation:**

> `会 对 我国 整个 社会 文化 的 建设 大有裨益 ， 更 会 对 我国 电影 产业 的 发展 起 到 巨大 推动 作用`
>
> becomes `会 对 我国 电影 产业 的 发展 起 到 巨大 推动 作用 ， 更 会 对 我国 整个 社会 文化 的 建设 大有裨益`

**Projection character M2:**

- `W`: reorder "会对我国整个社会文化的建设大有裨益，更会对我国电影产业的发展起到巨大推动作用" as "会对我国电影产业的发展起到巨大推动作用，更会对我国整个社会文化的建设大有裨益" at 12:50

**ChERRANT character M2:**

- `S`: replace "整个社会文化" with "电影产业" at 16:22
- `S`: replace "建设" with "发展起到巨" at 23:25
- `S`: replace "有裨益" with "推动作用" at 26:29
- `S`: replace "电影产业" with "整个社会文化" at 35:39
- `S`: replace "发展起到巨" with "建设" at 40:45
- `S`: replace "推动作用" with "有裨益" at 46:50

**Summary:** Projection uses 1 character edit(s), including `W`; ChERRANT fragments the change into 6 edit(s): `S,S,S,S,S,S`.

### Example 4: nasgec_exam T0 row 1964

**Source:** 刘量程的《一个人的村庄》、梭罗的《瓦尔登湖》等中外散文佳作，都具有积极的思想倾向，因而文笔清新自然，又充满思辨色彩，耐人咀嚼。

**GEC system output:** 刘量程的《一个人的村庄》、梭罗的《瓦尔登湖》等中外散文佳作，文笔清新自然，又充满思辨色彩，耐人咀嚼，因而都具有积极的思想倾向。

**Movement:** one projection W span over 21 tokens (`18:39`), with a maximum token displacement of 14 positions.

**Projection word representation:**

> `， 都 具有 积极 的 思想 倾向 ， 因而 文笔 清新 自然 ， 又 充满 思辨 色彩 ， 耐 人 咀嚼`
>
> becomes `， 文笔 清新 自然 ， 又 充满 思辨 色彩 ， 耐 人 咀嚼 ， 因而 都 具有 积极 的 思想 倾向`

**Projection character M2:**

- `W`: reorder "，都具有积极的思想倾向，因而文笔清新自然，又充满思辨色彩，耐人咀嚼" as "，文笔清新自然，又充满思辨色彩，耐人咀嚼，因而都具有积极的思想倾向" at 29:62

**ChERRANT character M2:**

- `R`: delete "，都具有积极的思想倾向" at 29:40
- `R`: delete "因而" at 41:43
- `M`: insert "，因而都具有积极的思想倾向" at boundary 62

**Summary:** Projection uses 1 character edit(s), including `W`; ChERRANT fragments the change into 3 edit(s): `R,R,M`.

### Example 5: nacgec T0 row 5214

**Source:** 阅读中国古典诗词，不仅能为我们的一生奠定良好的文化基础，而且能提高我们的语文素养和能力。

**GEC system output:** 阅读中国古典诗词，不仅能提高我们的语文素养和能力，而且能为我们的一生奠定良好的文化基础。

**Movement:** one projection W span over 20 tokens (`6:26`), with a maximum token displacement of 12 positions.

**Projection word representation:**

> `能 为 我们 的 一生 奠定 良好 的 文化 基础 ， 而且 能 提高 我们 的 语文 素养 和 能力`
>
> becomes `能 提高 我们 的 语文 素养 和 能力 ， 而且 能 为 我们 的 一生 奠定 良好 的 文化 基础`

**Projection character M2:**

- `W`: reorder "能为我们的一生奠定良好的文化基础，而且能提高我们的语文素养和能力" as "能提高我们的语文素养和能力，而且能为我们的一生奠定良好的文化基础" at 11:43

**ChERRANT character M2:**

- `S`: replace "为" with "提高" at 12:13
- `S`: replace "一生奠定良好的文化基础" with "语文素养和能力" at 16:27
- `S`: replace "提高" with "为" at 31:33
- `S`: replace "语文素养和能力" with "一生奠定良好的文化基础" at 36:43

**Summary:** Projection uses 1 character edit(s), including `W`; ChERRANT fragments the change into 4 edit(s): `S,S,S,S`.

### Example 6: fcgec T0 row 270

**Source:** 《河南省行政机关政策文件解读实施办法》规定：把政策文件与群众利益的关系讲明白，让群众用得上、信得过、记得住、听得懂。

**GEC system output:** 《河南省行政机关政策文件解读实施办法》规定：把政策文件与群众利益的关系讲明白，让群众听得懂、信得过、记得住、用得上。

**Movement:** one projection W span over 15 tokens (`25:40`), with a maximum token displacement of 12 positions.

**Projection word representation:**

> `用 得 上 、 信 得 过 、 记 得 住 、 听 得 懂`
>
> becomes `听 得 懂 、 信 得 过 、 记 得 住 、 用 得 上`

**Projection character M2:**

- `W`: reorder "用得上、信得过、记得住、听得懂" as "听得懂、信得过、记得住、用得上" at 42:57

**ChERRANT character M2:**

- `S`: replace "用" with "听" at 42:43
- `S`: replace "上" with "懂" at 44:45
- `S`: replace "听" with "用" at 54:55
- `S`: replace "懂" with "上" at 56:57

**Summary:** Projection uses 1 character edit(s), including `W`; ChERRANT fragments the change into 4 edit(s): `S,S,S,S`.

### Example 7: fcgec T0 row 1817

**Source:** 《松花江上》《义勇军进行曲》《长城谣》……这些经典的抗战歌曲曾响彻中华大地。激昂的歌声、慷慨的歌词，不仅在唱响着当今的时代主旋律，同样也在述说着昨天的故事。

**GEC system output:** 《松花江上》《义勇军进行曲》《长城谣》……这些经典的抗战歌曲曾响彻中华大地。激昂的歌声、慷慨的歌词，不仅在述说着昨天的故事，同样也在唱响着当今的时代主旋律。

**Movement:** one projection W span over 17 tokens (`33:50`), with a maximum token displacement of 11 positions.

**Projection word representation:**

> `在 唱 响 着 当今 的 时代 主旋律 ， 同样 也 在 述说 着 昨天 的 故事`
>
> becomes `在 述说 着 昨天 的 故事 ， 同样 也 在 唱 响 着 当今 的 时代 主旋律`

**Projection character M2:**

- `W`: reorder "在唱响着当今的时代主旋律，同样也在述说着昨天的故事" as "在述说着昨天的故事，同样也在唱响着当今的时代主旋律" at 52:77

**ChERRANT character M2:**

- `S`: replace "唱响" with "述说" at 53:55
- `S`: replace "当今" with "昨天" at 56:58
- `S`: replace "时代主旋律" with "故事" at 59:64
- `S`: replace "述说" with "唱响" at 69:71
- `S`: replace "昨天" with "当今" at 72:74
- `S`: replace "故事" with "时代主旋律" at 75:77

**Summary:** Projection uses 1 character edit(s), including `W`; ChERRANT fragments the change into 6 edit(s): `S,S,S,S,S,S`.

### Example 8: nacgec T0 row 1193

**Source:** 广受好评的电视节目《经典咏流传》不但提高了大众对经典诗词的鉴赏水平，而且唤起了人们对经典诗词的记忆。

**GEC system output:** 广受好评的电视节目《经典咏流传》不但唤起了人们对经典诗词的记忆，而且提高了大众对经典诗词的鉴赏水平。

**Movement:** one projection W span over 19 tokens (`11:30`), with a maximum token displacement of 11 positions.

**Projection word representation:**

> `提高 了 大众 对 经典 诗词 的 鉴赏 水平 ， 而且 唤起 了 人们 对 经典 诗词 的 记忆`
>
> becomes `唤起 了 人们 对 经典 诗词 的 记忆 ， 而且 提高 了 大众 对 经典 诗词 的 鉴赏 水平`

**Projection character M2:**

- `W`: reorder "提高了大众对经典诗词的鉴赏水平，而且唤起了人们对经典诗词的记忆" as "唤起了人们对经典诗词的记忆，而且提高了大众对经典诗词的鉴赏水平" at 18:49

**ChERRANT character M2:**

- `S`: replace "提高" with "唤起" at 18:20
- `S`: replace "大众" with "人们" at 21:23
- `S`: replace "鉴赏水平" with "记忆" at 29:33
- `S`: replace "唤起" with "提高" at 36:38
- `S`: replace "人们" with "大众" at 39:41
- `S`: replace "记忆" with "鉴赏水平" at 47:49

**Summary:** Projection uses 1 character edit(s), including `W`; ChERRANT fragments the change into 6 edit(s): `S,S,S,S,S,S`.

### Example 9: flacgec T0 row 1039

**Source:** 现在很多人甚至享受丰厚的积分回馈，办理了等许多信用卡、商户积分卡。

**GEC system output:** 现在很多人甚至办理了许多信用卡、商户积分卡等，享受丰厚的积分回馈。

**Movement:** one projection W span over 14 tokens (`4:18`), with a maximum token displacement of 9 positions.

**Projection word representation:**

> `享受 丰厚 的 积分 回馈 ， 办理 了 等 许多 信用卡 、 商户 积分卡`
>
> becomes `办理 了 许多 信用卡 、 商户 积分卡 等 ， 享受 丰厚 的 积分 回馈`

**Projection character M2:**

- `W`: reorder "享受丰厚的积分回馈，办理了等许多信用卡、商户积分卡" as "办理了许多信用卡、商户积分卡等，享受丰厚的积分回馈" at 7:32

**ChERRANT character M2:**

- `R`: delete "享受丰厚的积分回馈，" at 7:17
- `R`: delete "等" at 20:21
- `M`: insert "等，享受丰厚的积分回馈" at boundary 32

**Summary:** Projection uses 1 character edit(s), including `W`; ChERRANT fragments the change into 3 edit(s): `R,R,M`.

### Example 10: mucgec T0 row 3398

**Source:** 昨天我跟我朋友在大学的图书馆一起学习汉语了。

**GEC system output:** 昨天我在大学的图书馆跟我朋友一起学习汉语了。

**Movement:** one projection W span over 8 tokens (`1:9`), with a maximum token displacement of 4 positions.

**Projection word representation:**

> `我 跟 我 朋友 在 大学 的 图书馆`
>
> becomes `我 在 大学 的 图书馆 跟 我 朋友`

**Projection character M2:**

- `W`: reorder "我跟我朋友在大学的图书馆" as "我在大学的图书馆跟我朋友" at 2:14

**ChERRANT character M2:**

- `R`: delete "我跟" at 2:4
- `R`: delete "朋友" at 5:7
- `M`: insert "跟我朋友" at boundary 14

**Summary:** Projection uses 1 character edit(s), including `W`; ChERRANT fragments the change into 3 edit(s): `R,R,M`.

## 3. Key Findings

ChERRANT is capable of producing W and does so thousands of times in the saved outputs. Its direct W rule has no fixed maximum length. However, in the long-distance cases above, the dynamic-programming path typically commits to insertions, deletions, or substitutions, and the local merger cannot recover the complete movement. Projection alignment reconnects corresponding material across distance and can serialize the moved region as one round-trippable W span at both character and word levels.

This supports a qualitative claim that projection can provide a more coherent representation of some long-distance word-order errors. It does not, by itself, establish that every projection W is correct; the selected examples require manual linguistic confirmation.

## 4. Implementation References

- ChERRANT direct transposition: [`alignment.py`](../../external_tools/MuCGEC/scorers/ChERRANT/modules/alignment.py), lines 247--289.
- ChERRANT transposition merger: [`merger.py`](../../external_tools/MuCGEC/scorers/ChERRANT/modules/merger.py), lines 96--165.
- ChERRANT label mapping: [`classifier.py`](../../external_tools/MuCGEC/scorers/ChERRANT/modules/classifier.py), lines 97--143.
- Current upstream ERRANT comparator: [`compare_m2.py`](../../external_tools/errant/errant/commands/compare_m2.py), especially lines 105--120, 126--194, and 203--266.
- Full candidate inventory: [`../long_distance_word_order_audit/candidates.tsv`](../long_distance_word_order_audit/candidates.tsv).
- Dataset-by-stage label counts: [`label_counts.tsv`](label_counts.tsv).
