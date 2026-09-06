# Qualitative Alignment Examples

These five real saved model outputs were manually selected and inspected for representational clarity. They demonstrate how the final projection M2 files encode order changes; they are not claims that every generated correction is linguistically optimal.

## Summary

| Dataset | Stage | Row | Projection word form | ChERRANT character form |
| --- | --- | --- | --- | --- |
| flacgec | T0 | 300 | linked U-M | W |
| nasgec_exam | T0 | 1991 | linked U-M | W |
| nacgec | T3 | 3133 | linked U-M | W |
| nasgec_exam | T1 | 14 | encompassing W | M, R, R |
| fcgec | T0 | 270 | encompassing W | S, S, S, S |

## Example 1: flacgec T0 row 300

**Source:** 人是地球上步步最聪明的动物，靠着智慧的头脑和灵巧的双手，造出了种种工具，使自己对世界的征服与改造深入，成为万物之灵。

**System output:** 人是地球上最聪明的动物，靠着智慧的头脑和灵巧的双手，造出了种种工具，使自己对世界的征服与改造步步深入，成为万物之灵。

**Assessment:** The two-character adverb 步步 moves across a long unchanged interval. Projection isolates exactly the moved word at both evaluation levels, whereas ChERRANT places one W over the complete intervening character span.

**Projection word M2**

```text
A 4 5|||U|||-NONE-|||-REQUIRED-|||LINK=w1;TO=34|||0
A 34 34|||M|||步步|||-REQUIRED-|||LINK=w1;FROM=4:5|||0
```

**Projection character M2**

```text
A 5 7|||U|||-NONE-|||-REQUIRED-|||LINK=w1;TO=48|||0
A 48 48|||M|||步步|||-REQUIRED-|||LINK=w1;FROM=5:7|||0
```

**ChERRANT character M2**

```text
A 5 48|||W|||最 聪 明 的 动 物 ， 靠 着 智 慧 的 头 脑 和 灵 巧 的 双 手 ， 造 出 了 种 种 工 具 ， 使 自 己 对 世 界 的 征 服 与 改 造 步 步|||REQUIRED|||-NONE-|||0
```

## Example 2: nasgec_exam T0 row 1991

**Source:** 他自费为在“文革”中被迫害致瘫八年的吉林省一位副省长配制了治疗中风的中药，并亲自煎好喂服。

**System output:** 他自费为一位在“文革”中被迫害致瘫八年的吉林省副省长配制了治疗中风的中药，并亲自煎好喂服。

**Assessment:** The quantifier phrase 一位 moves leftward. Projection records the two-character/two-token phrase and its endpoints; ChERRANT's W includes the unchanged relative clause.

**Projection word M2**

```text
A 3 3|||M|||一 位|||-REQUIRED-|||LINK=w1;FROM=16:18|||0
A 16 18|||U|||-NONE-|||-REQUIRED-|||LINK=w1;TO=3|||0
```

**Projection character M2**

```text
A 4 4|||M|||一位|||-REQUIRED-|||LINK=w1;FROM=21:23|||0
A 21 23|||U|||-NONE-|||-REQUIRED-|||LINK=w1;TO=4|||0
```

**ChERRANT character M2**

```text
A 4 23|||W|||一 位 在 “ 文 革 ” 中 被 迫 害 致 瘫 八 年 的 吉 林 省|||REQUIRED|||-NONE-|||0
```

## Example 3: nacgec T3 row 3133

**Source:** 与作家不同的是，摄影家们把自己对大自然中山川、草木、河流的独特感受没有倾注于笔下，而是直接聚焦于镜头，用画面与读者交流。

**System output:** 与作家不同的是，摄影家们没有把自己对大自然中山川、草木、河流的独特感受倾注于笔下，而是直接聚焦于镜头，用画面与读者交流。

**Assessment:** The negator 没有 moves before 把. Projection links only the moved material, while ChERRANT's conventional W spans the entire intervening object phrase.

**Projection word M2**

```text
A 8 8|||M|||没有|||-REQUIRED-|||LINK=w1;FROM=21:22|||0
A 21 22|||U|||-NONE-|||-REQUIRED-|||LINK=w1;TO=8|||0
```

**Projection character M2**

```text
A 12 12|||M|||没有|||-REQUIRED-|||LINK=w1;FROM=33:35|||0
A 33 35|||U|||-NONE-|||-REQUIRED-|||LINK=w1;TO=12|||0
```

**ChERRANT character M2**

```text
A 12 35|||W|||没 有 把 自 己 对 大 自 然 中 山 川 、 草 木 、 河 流 的 独 特 感 受|||REQUIRED|||-NONE-|||0
```

## Example 4: nasgec_exam T1 row 14

**Source:** 市教研室通过多年的努力，评价方法得当、操作程序公开透明、让所有人都心服口服的一套高考质量评估方案出台了。

**System output:** 市教研室通过多年的努力，出台了一套评价方法得当、操作程序公开透明、让所有人都心服口服的高考质量评估方案。

**Assessment:** This is a multi-block reordering rather than an unambiguous one-block move. The projection pipeline therefore uses its documented encompassing-W fallback; ChERRANT fragments the same change into one insertion and two deletions.

**Projection word M2**

```text
A 7 30|||W|||出台 了 一 套 评价 方法 得当 、 操作 程序 公开 透明 、 让 所有 人 都 心服口服 的 高考 质量 评估 方案|||-REQUIRED-|||NONE|||0
```

**Projection character M2**

```text
A 12 51|||W|||出台了一套评价方法得当、操作程序公开透明、让所有人都心服口服的高考质量评估方案|||-REQUIRED-|||NONE|||0
```

**ChERRANT character M2**

```text
A 12 12|||M|||出 台 了 一 套|||REQUIRED|||-NONE-|||0
A 38 40|||R|||-NONE-|||REQUIRED|||-NONE-|||0
A 48 51|||R|||-NONE-|||REQUIRED|||-NONE-|||0
```

## Example 5: fcgec T0 row 270

**Source:** 《河南省行政机关政策文件解读实施办法》规定：把政策文件与群众利益的关系讲明白，让群众用得上、信得过、记得住、听得懂。

**System output:** 《河南省行政机关政策文件解读实施办法》规定：把政策文件与群众利益的关系讲明白，让群众听得懂、信得过、记得住、用得上。

**Assessment:** The first and last coordinated predicates exchange positions. Projection uses one exact-permutation W fallback, while ChERRANT represents four character substitutions.

**Projection word M2**

```text
A 25 40|||W|||听 得 懂 、 信 得 过 、 记 得 住 、 用 得 上|||-REQUIRED-|||NONE|||0
```

**Projection character M2**

```text
A 42 57|||W|||听得懂、信得过、记得住、用得上|||-REQUIRED-|||NONE|||0
```

**ChERRANT character M2**

```text
A 42 43|||S|||听|||REQUIRED|||-NONE-|||0
A 44 45|||S|||懂|||REQUIRED|||-NONE-|||0
A 54 55|||S|||用|||REQUIRED|||-NONE-|||0
A 56 57|||S|||上|||REQUIRED|||-NONE-|||0
```

## Interpretation Boundary

The first three examples support the narrow claim that linked projection can isolate moved material and retain both origin and destination when a conventional contiguous W would absorb a long unchanged interval. The final two examples show the documented fallback for multi-block permutations. These examples do not establish aggregate alignment accuracy and should be presented as qualitative evidence only.
