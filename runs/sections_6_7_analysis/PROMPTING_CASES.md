# Prompting and Projection Cases

These cases are selected by reproducible criteria from saved outputs. Boundary error is symmetric difference from the fixed gold-informed evaluation segmentation; it is not a claim of unique linguistic gold segmentation. GLEU deltas are character-based sentence-level select-best values.

## Case 1: Direct boundaries become closer to the gold-informed segmentation

- Dataset/row: `cefe_track3` / `3`
- Boundary error S1 -> S2: `6 -> 1`
- Character GLEU T1 -> T2: `+0.0000`
- Source: 个人兴趣固然重要，更重要的是学会将兴趣发展到多层次，多方面，一味地追求快乎是不可取得，更应满足社会和国家的需要，因为只有人民有发展的动力，国家才会有前徒可塑。
- Direct boundaries (S1): 个人 兴趣 固然 重要 ， 更 重要 的 是 学会 将 兴趣 发展 到 多 层次 ， 多 方面 ， 一味 地 追求 快 乎 是 不可 取得 ， 更 应 满足 社会 和 国家 的 需要 ， 因为 只有 人民 有 发展 的 动力 ， 国家 才 会 有 前徒可塑 。
- Projected boundaries (S2): 个人 兴趣 固然 重要 ， 更 重要 的 是 学会 将 兴趣 发展 到 多 层次 ， 多 方面 ， 一味 地 追求 快 乎 是 不 可取 得 ， 更 应 满足 社会 和 国家 的 需要 ， 因为 只有 人民 有 发展 的 动力 ， 国家 才 会 有 前徒 可 塑 。
- Raw correction (T0): 个人兴趣固然重要，更重要的是学会将兴趣发展到多层次、多方面，一味地追求快是不可取的，更应满足社会和国家的需要，因为只有人民有发展的动力，国家才会有前途可塑。
- Direct correction (T1): 个人兴趣固然重要，更重要的是学会将兴趣发展到多层次、多方面，一味地追求快乎是不可取的，更应满足社会和国家的需要，因为只有人民有发展的动力，国家才会有前途可塑。
- Projected correction (T2): 个人兴趣固然重要，更重要的是学会将兴趣发展到多层次、多方面，一味地追求快乎是不可取的，更应满足社会和国家的需要，因为只有人民有发展的动力，国家才会有前途可塑。
- References: 个人兴趣固然重要，更重要的是学会将兴趣发展到多层次、多方面，一味地追求快乐是不可取的，我们更应满足社会和国家的需要，因为只有人民有发展的动力，国家才会有前途可塑。

## Case 2: Closer projected boundaries improve the correction score

- Dataset/row: `mucgec` / `4496`
- Boundary error S1 -> S2: `1 -> 0`
- Character GLEU T1 -> T2: `+0.7222`
- Source: 应该分要分班。
- Direct boundaries (S1): 应该 分 要 分 班 。
- Projected boundaries (S2): 应该 分 要 分班 。
- Raw correction (T0): 应该要分班。
- Direct correction (T1): 应该分班就要分班。
- Projected correction (T2): 应该要分班。
- References: 应该要分班。

## Case 3: Changed boundaries leave the correction unchanged

- Dataset/row: `nacgec` / `2595`
- Boundary error S1 -> S2: `4 -> 0`
- Character GLEU T1 -> T2: `+0.0000`
- Source: 即兴演讲是面对某一情境或话题，兴之所至，有感而发的感受。
- Direct boundaries (S1): 即兴 演讲 是 面对 某 一 情境 或 话题 ， 兴 之 所 至 ， 有 感 而 发 的 感受 。
- Projected boundaries (S2): 即兴 演讲 是 面对 某 一 情境 或 话题 ， 兴 之 所至 ， 有感而发 的 感受 。
- Raw correction (T0): 即兴演讲是面对某一情境或话题，兴之所至、有感而发地进行的表达。
- Direct correction (T1): 即兴演讲是面对某一情境或话题，兴之所至，有感而发的表达。
- Projected correction (T2): 即兴演讲是面对某一情境或话题，兴之所至，有感而发的表达。
- References: 即兴演讲是面对某一情境或话题，兴之所至，有感而发的演讲。

## Case 4: Projection moves away from the gold-informed segmentation and hurts

- Dataset/row: `mucgec` / `4821`
- Boundary error S1 -> S2: `0 -> 1`
- Character GLEU T1 -> T2: `-0.5333`
- Source: 老人们说：人在一天，无法前往一千里，而是一种精神，很容易前行在一天一千里
- Direct boundaries (S1): 老人 们 说 ： 人 在 一 天 ， 无法 前往 一千 里 ， 而是 一 种 精神 ， 很 容易 前行 在 一 天 一千 里
- Projected boundaries (S2): 老人 们 说 ： 人 在 一 天 ， 无法 前往 一千 里 ， 而是 一 种 精神 ， 很 容易 前 行 在 一 天 一千 里
- Raw correction (T0): 老人们说：人在一天，无法前往一千里，而是一种精神，很容易在一天前行一千里。
- Direct correction (T1): 老人们说：人在一天，无法前往一千里，而是一种精神，很容易在一天前行一千里。
- Projected correction (T2): 老人们说：人在一天，无法前往一千里，而是一种精神，很容易前行在一天一千里。
- References: 老人们说：“人在一天内，无法前行一千里，而是一种精神，很容易在一天内前行一千里。” / 老人们说：“人在一天内，无法前行一千里，而有一种精神，很容易在一天内前行一千里。”

## Case 5: Conservative rule leaves an already stable case unchanged

- Dataset/row: `nlpcc2018` / `451`
- Boundary error S1 -> S2: `1 -> 1`
- Character GLEU T1 -> T2: `+0.0000`
- Source: 可有多少机率他或是她已经身在稳定的工作生活呢？
- Direct boundaries (S1): 可 有 多少 机率 他 或是 她 已经 身 在 稳定 的 工作 生活 呢 ？
- Projected boundaries (S2): 可 有 多少 机率 他 或是 她 已经 身 在 稳定 的 工作 生活 呢 ？
- Raw correction (T0): 可有多少几率他或她已经身在稳定的工作生活中呢？
- Direct correction (T1): 可有多少机率他或是她已经身在稳定的工作生活呢？
- Projected correction (T2): 可有多少机率他或是她已经身在稳定的工作生活呢？
- References: 可有多少机率他或是她已经拥有稳定的工作生活呢？
