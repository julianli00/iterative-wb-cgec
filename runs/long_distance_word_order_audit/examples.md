# Long-distance Word-order Candidates

These are automatically selected qualitative candidates, not adjudicated gold claims. They have a projection word-level W span with a token moving at least four positions. Repeated T0--T3 instances with identical source and target strings are shown only once here; the TSV retains every candidate.

## 1. nasgec_exam T1 row 14

- Maximum token movement: 21
- Source: 市教研室通过多年的努力，评价方法得当、操作程序公开透明、让所有人都心服口服的一套高考质量评估方案出台了。
- Target: 市教研室通过多年的努力，出台了一套评价方法得当、操作程序公开透明、让所有人都心服口服的高考质量评估方案。
- Projection word W: `A 7 30|||W|||出台 了 一 套 评价 方法 得当 、 操作 程序 公开 透明 、 让 所有 人 都 心服口服 的 高考 质量 评估 方案|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 12 51|||W|||出台了一套评价方法得当、操作程序公开透明、让所有人都心服口服的高考质量评估方案|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 12 12|||M|||出 台 了 一 套|||REQUIRED|||-NONE-|||0 ; A 38 40|||R|||-NONE-|||REQUIRED|||-NONE-|||0 ; A 48 51|||R|||-NONE-|||REQUIRED|||-NONE-|||0`

## 2. nacgec T0 row 361

- Maximum token movement: 16
- Source: 建设全面体现新发展理念的国家中心城市，不仅需要传承文化、做优文创，提升发展“软实力”，而且需要壮大经济、做强产业，增强发展“硬实力”。
- Target: 建设全面体现新发展理念的国家中心城市，不仅需要壮大经济、做强产业，增强发展“硬实力”，而且需要传承文化、做优文创，提升发展“软实力”。
- Projection word W: `A 13 40|||W|||壮大 经济 、 做 强 产业 ， 增强 发展 “ 硬 实力 ” ， 而且 需要 传承 文化 、 做 优 文创 ， 提升 发展 “ 软|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 23 63|||W|||壮大经济、做强产业，增强发展“硬实力”，而且需要传承文化、做优文创，提升发展“软|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 23 27|||S|||壮 大 经 济|||REQUIRED|||-NONE-|||0 ; A 29 32|||S|||强 产 业|||REQUIRED|||-NONE-|||0 ; A 33 35|||S|||增 强|||REQUIRED|||-NONE-|||0 ; A 38 39|||S|||硬|||REQUIRED|||-NONE-|||0 ; A 47 51|||S|||传 承 文 化|||REQUIRED|||-NONE-|||0 ; A 53 56|||S|||优 文 创|||REQUIRED|||-NONE-|||0 ; A 57 59|||S|||提 升|||REQUIRED|||-NONE-|||0 ; A 62 63|||S|||软|||REQUIRED|||-NONE-|||0`

## 3. nacgec T2 row 776

- Maximum token movement: 15
- Source: 欣赏诗歌，由于它极精练，我们不仅要努力寻求它的诗句之外包含的不尽的韵味，而且要努力把握它以少量字词包含着的丰富的含义。
- Target: 欣赏诗歌，由于它极精练，我们不仅要努力把握它以少量字词包含着的不尽的含义，而且要努力寻求它的诗句之外包含的丰富的韵味。
- Projection word W: `A 12 37|||W|||把握 它 以 少量 字词 包含 着 的 不尽 的 含义 ， 而且 要 努力 寻求 它 的 诗句 之外 包含 的 丰富 的 韵味|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 19 58|||W|||把握它以少量字词包含着的不尽的含义，而且要努力寻求它的诗句之外包含的丰富的韵味|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 19 21|||S|||把 握|||REQUIRED|||-NONE-|||0 ; A 22 27|||S|||以 少 量 字 词|||REQUIRED|||-NONE-|||0 ; A 29 29|||M|||着|||REQUIRED|||-NONE-|||0 ; A 33 35|||S|||含 义|||REQUIRED|||-NONE-|||0 ; A 41 43|||S|||寻 求|||REQUIRED|||-NONE-|||0 ; A 44 49|||S|||的 诗 句 之 外|||REQUIRED|||-NONE-|||0 ; A 51 52|||R|||-NONE-|||REQUIRED|||-NONE-|||0 ; A 56 58|||S|||韵 味|||REQUIRED|||-NONE-|||0`

## 4. nacgec T0 row 3619

- Maximum token movement: 15
- Source: 中国本土作家首获诺贝尔文学奖，不仅代表着蕴含中国特色、风格的中国文学已走向世界，更标志着莫言的作品被世界认同。
- Target: 中国本土作家首获诺贝尔文学奖，不仅标志着莫言的作品被世界认同，更代表着蕴含中国特色、风格的中国文学已走向世界。
- Projection word W: `A 10 33|||W|||标志 着 莫言 的 作品 被 世界 认同 ， 更 代表 着 蕴含 中国 特色 、 风格 的 中国 文学 已 走向 世界|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 17 54|||W|||标志着莫言的作品被世界认同，更代表着蕴含中国特色、风格的中国文学已走向世界|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 17 17|||M|||标 志 着 莫 言 的 作 品 被 世 界 认 同 ， 更|||REQUIRED|||-NONE-|||0 ; A 37 50|||R|||-NONE-|||REQUIRED|||-NONE-|||0 ; A 52 54|||R|||-NONE-|||REQUIRED|||-NONE-|||0`

## 5. nacgec T0 row 5064

- Maximum token movement: 14
- Source: 平民文化的重新崛起，不仅会对我国整个社会文化的建设大有裨益，更会对我国电影产业的发展起到巨大推动作用。
- Target: 平民文化的重新崛起，不仅会对我国电影产业的发展起到巨大推动作用，更会对我国整个社会文化的建设大有裨益。
- Projection word W: `A 7 30|||W|||会 对 我国 电影 产业 的 发展 起 到 巨大 推动 作用 ， 更 会 对 我国 整个 社会 文化 的 建设 大有裨益|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 12 50|||W|||会对我国电影产业的发展起到巨大推动作用，更会对我国整个社会文化的建设大有裨益|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 16 22|||S|||电 影 产 业|||REQUIRED|||-NONE-|||0 ; A 23 25|||S|||发 展 起 到 巨|||REQUIRED|||-NONE-|||0 ; A 26 29|||S|||推 动 作 用|||REQUIRED|||-NONE-|||0 ; A 35 39|||S|||整 个 社 会 文 化|||REQUIRED|||-NONE-|||0 ; A 40 45|||S|||建 设|||REQUIRED|||-NONE-|||0 ; A 46 50|||S|||有 裨 益|||REQUIRED|||-NONE-|||0`

## 6. nasgec_exam T0 row 1964

- Maximum token movement: 14
- Source: 刘量程的《一个人的村庄》、梭罗的《瓦尔登湖》等中外散文佳作，都具有积极的思想倾向，因而文笔清新自然，又充满思辨色彩，耐人咀嚼。
- Target: 刘量程的《一个人的村庄》、梭罗的《瓦尔登湖》等中外散文佳作，文笔清新自然，又充满思辨色彩，耐人咀嚼，因而都具有积极的思想倾向。
- Projection word W: `A 18 39|||W|||， 文笔 清新 自然 ， 又 充满 思辨 色彩 ， 耐 人 咀嚼 ， 因而 都 具有 积极 的 思想 倾向|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 29 62|||W|||，文笔清新自然，又充满思辨色彩，耐人咀嚼，因而都具有积极的思想倾向|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 29 40|||R|||-NONE-|||REQUIRED|||-NONE-|||0 ; A 41 43|||R|||-NONE-|||REQUIRED|||-NONE-|||0 ; A 62 62|||M|||， 因 而 都 具 有 积 极 的 思 想 倾 向|||REQUIRED|||-NONE-|||0`

## 7. nacgec T0 row 5131

- Maximum token movement: 14
- Source: 历时21个月的厄尔尼诺事件不仅对农业生产和全球粮食市场的影响显现出来，而且对全球气候也产生明显影响。
- Target: 历时21个月的厄尔尼诺事件不仅对全球气候产生明显影响，而且对农业生产和全球粮食市场的影响也显现出来。
- Projection word W: `A 8 28|||W|||对 全球 气候 产生 明显 影响 ， 而且 对 农业 生产 和 全球 粮食 市场 的 影响 也 显现 出来|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 15 49|||W|||对全球气候产生明显影响，而且对农业生产和全球粮食市场的影响也显现出来|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 15 15|||M|||对 全 球 气 候 产 生 明 显 影 响 ， 而 且|||REQUIRED|||-NONE-|||0 ; A 30 30|||M|||也|||REQUIRED|||-NONE-|||0 ; A 34 49|||R|||-NONE-|||REQUIRED|||-NONE-|||0`

## 8. nacgec T0 row 2348

- Maximum token movement: 13
- Source: 我们所倡导的“工匠精神”不仅仅体现在更多的普通人身上，它还应体现在少部分具备高超技艺的人身上，唯有如此，才能凸显出其真正的社会价值。
- Target: 我们所倡导的“工匠精神”不仅仅体现在少部分具备高超技艺的人身上，它还应体现在更多的普通人身上，唯有如此，才能凸显出其真正的社会价值。
- Projection word W: `A 11 28|||W|||少部分 具备 高超 技艺 的 人 身上 ， 它 还 应 体现 在 更 多 的 普通人|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 18 43|||W|||少部分具备高超技艺的人身上，它还应体现在更多的普通|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 18 20|||S|||少 部 分 具 备 高 超 技 艺|||REQUIRED|||-NONE-|||0 ; A 21 23|||R|||-NONE-|||REQUIRED|||-NONE-|||0 ; A 33 42|||S|||更 多|||REQUIRED|||-NONE-|||0 ; A 43 43|||M|||普 通|||REQUIRED|||-NONE-|||0`

## 9. nacgec T1 row 2348

- Maximum token movement: 13
- Source: 我们所倡导的“工匠精神”不仅仅体现在更多的普通人身上，它还应体现在少部分具备高超技艺的人身上，唯有如此，才能凸显出其真正的社会价值。
- Target: 我们倡导的“工匠精神”不仅仅体现在少部分具备高超技艺的人身上，它还应体现在更多的普通人身上，唯有如此，才能凸显出其真正的社会价值。
- Projection word W: `A 11 28|||W|||少部分 具备 高超 技艺 的 人 身上 ， 它 还 应 体现 在 更 多 的 普通人|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 2 3|||U|||-NONE-|||-REQUIRED-|||NONE|||0 ; A 18 43|||W|||少部分具备高超技艺的人身上，它还应体现在更多的普通|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 2 3|||R|||-NONE-|||REQUIRED|||-NONE-|||0 ; A 18 20|||S|||少 部 分 具 备 高 超 技 艺|||REQUIRED|||-NONE-|||0 ; A 21 23|||R|||-NONE-|||REQUIRED|||-NONE-|||0 ; A 33 42|||S|||更 多|||REQUIRED|||-NONE-|||0 ; A 43 43|||M|||普 通|||REQUIRED|||-NONE-|||0`

## 10. nasgec_exam T0 row 1421

- Maximum token movement: 13
- Source: 我们所倡导的“工匠精神”经不仅仅体现在更多的普通人身上，它还应体现在少部分具备高超技艺的人身上，唯有如此，才能凸显出其真正的社会价值。
- Target: 我们所倡导的“工匠精神”不仅应体现在少部分具备高超技艺的人身上，它还应体现在更多的普通人身上，唯有如此，才能凸显出其真正的社会价值。
- Projection word W: `A 12 29|||W|||少部分 具备 高超 技艺 的 人 身上 ， 它 还 应 体现 在 更 多 的 普通人|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 12 13|||U|||-NONE-|||-REQUIRED-|||NONE|||0 ; A 15 16|||R|||应|||-REQUIRED-|||NONE|||0 ; A 19 44|||W|||少部分具备高超技艺的人身上，它还应体现在更多的普通|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 12 13|||R|||-NONE-|||REQUIRED|||-NONE-|||0 ; A 15 16|||S|||应|||REQUIRED|||-NONE-|||0 ; A 19 21|||S|||少 部 分 具 备 高 超 技 艺|||REQUIRED|||-NONE-|||0 ; A 22 24|||R|||-NONE-|||REQUIRED|||-NONE-|||0 ; A 34 43|||S|||更 多|||REQUIRED|||-NONE-|||0 ; A 44 44|||M|||普 通|||REQUIRED|||-NONE-|||0`

## 11. nacgec T0 row 2538

- Maximum token movement: 13
- Source: 作为最大的发展中国家和碳排放大国，中国的选择不仅决定着世界的未来，而且决定着未来自身的核心竞争力与综合发展前景。
- Target: 作为最大的发展中国家和碳排放大国，中国的选择不仅决定着自身未来的核心竞争力与综合发展前景，而且决定着世界的未来。
- Projection word W: `A 16 32|||W|||自身 未来 的 核心 竞争力 与 综合 发展 前景 ， 而且 决定 着 世界 的 未来|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 27 55|||W|||自身未来的核心竞争力与综合发展前景，而且决定着世界的未来|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 27 38|||S|||自 身|||REQUIRED|||-NONE-|||0 ; A 40 42|||R|||-NONE-|||REQUIRED|||-NONE-|||0 ; A 55 55|||M|||， 而 且 决 定 着 世 界 的 未 来|||REQUIRED|||-NONE-|||0`

## 12. nacgec T1 row 2538

- Maximum token movement: 13
- Source: 作为最大的发展中国家和碳排放大国，中国的选择不仅决定着世界的未来，而且决定着未来自身的核心竞争力与综合发展前景。
- Target: 作为最大的发展中国家和碳排放大国，中国的选择不仅决定着自身的未来核心竞争力与综合发展前景，而且决定着世界的未来。
- Projection word W: `A 16 32|||W|||自身 的 未来 核心 竞争力 与 综合 发展 前景 ， 而且 决定 着 世界 的 未来|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 27 55|||W|||自身的未来核心竞争力与综合发展前景，而且决定着世界的未来|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 27 29|||S|||自 身|||REQUIRED|||-NONE-|||0 ; A 30 38|||R|||-NONE-|||REQUIRED|||-NONE-|||0 ; A 40 43|||R|||-NONE-|||REQUIRED|||-NONE-|||0 ; A 55 55|||M|||， 而 且 决 定 着 世 界 的 未 来|||REQUIRED|||-NONE-|||0`

## 13. nacgec T0 row 741

- Maximum token movement: 13
- Source: 这次环保大会，吸引了来自一百多个国家与地区的专业人士参加这次近年来规模最大、议程最多的会议，并取得了预期的效果。
- Target: 这次环保大会吸引了来自一百多个国家与地区的专业人士参加，这次近年来规模最大、议程最多的会议取得了预期的效果。
- Projection word W: `A 3 17|||W|||吸引 了 来自 一百 多 个 国家 与 地区 的 专业 人士 参加 ，|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 6 28|||W|||吸引了来自一百多个国家与地区的专业人士参加，|||-REQUIRED-|||NONE|||0 ; A 45 47|||U|||-NONE-|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 6 7|||R|||-NONE-|||REQUIRED|||-NONE-|||0 ; A 28 28|||M|||，|||REQUIRED|||-NONE-|||0 ; A 45 47|||R|||-NONE-|||REQUIRED|||-NONE-|||0`

## 14. nacgec T0 row 1723

- Maximum token movement: 12
- Source: 已有4000多年历史的中国春节，蕴含着丰富的民族传统文化底蕴，不但成了开展中外文明交流互鉴的最佳平台，而且是中国人的最重要的传统节日。
- Target: 已有4000多年历史的中国春节，蕴含着丰富的民族传统文化底蕴，不仅是中国人的最重要的传统节日，而且成了开展中外文明交流互鉴的最佳平台。
- Projection word W: `A 20 41|||W|||是 中国 人 的 最 重要 的 传统 节日 ， 而且 成 了 开展 中外 文明 交流 互鉴 的 最佳 平台|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 32 33|||R|||仅是中国人的最重要的传统节日，而且|||-REQUIRED-|||NONE|||0 ; A 50 66|||U|||-NONE-|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 32 33|||S|||仅 是 中 国 人 的 最 重 要 的 传 统 节 日 ， 而 且|||REQUIRED|||-NONE-|||0 ; A 50 66|||R|||-NONE-|||REQUIRED|||-NONE-|||0`

## 15. nacgec T0 row 5214

- Maximum token movement: 12
- Source: 阅读中国古典诗词，不仅能为我们的一生奠定良好的文化基础，而且能提高我们的语文素养和能力。
- Target: 阅读中国古典诗词，不仅能提高我们的语文素养和能力，而且能为我们的一生奠定良好的文化基础。
- Projection word W: `A 6 26|||W|||能 提高 我们 的 语文 素养 和 能力 ， 而且 能 为 我们 的 一生 奠定 良好 的 文化 基础|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 11 43|||W|||能提高我们的语文素养和能力，而且能为我们的一生奠定良好的文化基础|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 12 13|||S|||提 高|||REQUIRED|||-NONE-|||0 ; A 16 27|||S|||语 文 素 养 和 能 力|||REQUIRED|||-NONE-|||0 ; A 31 33|||S|||为|||REQUIRED|||-NONE-|||0 ; A 36 43|||S|||一 生 奠 定 良 好 的 文 化 基 础|||REQUIRED|||-NONE-|||0`

## 16. nacgec T0 row 4948

- Maximum token movement: 12
- Source: 战国时孟子“生于忧患，死于安乐”的论断，不仅对一个国家的生存发展具有重要意义，而且对个人的成长更具有启示作用。
- Target: 战国时孟子“生于忧患，死于安乐”的论断，不仅对个人的成长具有启示作用，而且对一个国家的生存发展更具有重要意义。
- Projection word W: `A 16 35|||W|||对 个人 的 成长 具有 启示 作用 ， 而且 对 一个 国家 的 生存 发展 更 具有 重要 意义|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 22 54|||W|||对个人的成长具有启示作用，而且对一个国家的生存发展更具有重要意义|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 23 24|||R|||-NONE-|||REQUIRED|||-NONE-|||0 ; A 25 27|||S|||人|||REQUIRED|||-NONE-|||0 ; A 28 32|||S|||成 长|||REQUIRED|||-NONE-|||0 ; A 34 38|||S|||启 示 作 用|||REQUIRED|||-NONE-|||0 ; A 42 42|||M|||一|||REQUIRED|||-NONE-|||0 ; A 43 44|||S|||国 家|||REQUIRED|||-NONE-|||0 ; A 45 47|||S|||生 存 发 展|||REQUIRED|||-NONE-|||0 ; A 50 54|||S|||重 要 意 义|||REQUIRED|||-NONE-|||0`

## 17. nacgec T0 row 4489

- Maximum token movement: 12
- Source: 我们所倡导的“工匠精神”，既体现在更多的普通人身上，还应体现在少部分具备高超技艺的人身上，唯有如此，才能凸显出真正的社会价值。
- Target: 我们所倡导的“工匠精神”，既应体现在少部分具备高超技艺的人身上，还应体现在更多的普通人身上，唯有如此，才能凸显出真正的社会价值。
- Projection word W: `A 12 28|||W|||少部分 具备 高超 技艺 的 人 身上 ， 还 应 体现 在 更 多 的 普通人|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 14 14|||M|||应|||-REQUIRED-|||NONE|||0 ; A 17 41|||W|||少部分具备高超技艺的人身上，还应体现在更多的普通|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 14 14|||M|||应|||REQUIRED|||-NONE-|||0 ; A 17 19|||S|||少 部 分 具 备 高 超 技 艺|||REQUIRED|||-NONE-|||0 ; A 20 22|||R|||-NONE-|||REQUIRED|||-NONE-|||0 ; A 31 40|||S|||更 多|||REQUIRED|||-NONE-|||0 ; A 41 41|||M|||普 通|||REQUIRED|||-NONE-|||0`

## 18. fcgec T0 row 270

- Maximum token movement: 12
- Source: 《河南省行政机关政策文件解读实施办法》规定：把政策文件与群众利益的关系讲明白，让群众用得上、信得过、记得住、听得懂。
- Target: 《河南省行政机关政策文件解读实施办法》规定：把政策文件与群众利益的关系讲明白，让群众听得懂、信得过、记得住、用得上。
- Projection word W: `A 25 40|||W|||听 得 懂 、 信 得 过 、 记 得 住 、 用 得 上|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 42 57|||W|||听得懂、信得过、记得住、用得上|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 42 43|||S|||听|||REQUIRED|||-NONE-|||0 ; A 44 45|||S|||懂|||REQUIRED|||-NONE-|||0 ; A 54 55|||S|||用|||REQUIRED|||-NONE-|||0 ; A 56 57|||S|||上|||REQUIRED|||-NONE-|||0`

## 19. fcgec T1 row 270

- Maximum token movement: 12
- Source: 《河南省行政机关政策文件解读实施办法》规定：把政策文件与群众利益的关系讲明白，让群众用得上、信得过、记得住、听得懂。
- Target: 《河南省行政机关政策文件解读实施办法》规定：把政策文件与群众利益的关系讲明白，让群众听得懂、记得住、信得过、用得上。
- Projection word W: `A 25 40|||W|||听 得 懂 、 记 得 住 、 信 得 过 、 用 得 上|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 42 57|||W|||听得懂、记得住、信得过、用得上|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 42 43|||S|||听|||REQUIRED|||-NONE-|||0 ; A 44 45|||S|||懂|||REQUIRED|||-NONE-|||0 ; A 46 47|||S|||记|||REQUIRED|||-NONE-|||0 ; A 48 49|||S|||住|||REQUIRED|||-NONE-|||0 ; A 50 51|||S|||信|||REQUIRED|||-NONE-|||0 ; A 52 53|||S|||过|||REQUIRED|||-NONE-|||0 ; A 54 55|||S|||用|||REQUIRED|||-NONE-|||0 ; A 56 57|||S|||上|||REQUIRED|||-NONE-|||0`

## 20. nacgec T0 row 1193

- Maximum token movement: 11
- Source: 广受好评的电视节目《经典咏流传》不但提高了大众对经典诗词的鉴赏水平，而且唤起了人们对经典诗词的记忆。
- Target: 广受好评的电视节目《经典咏流传》不但唤起了人们对经典诗词的记忆，而且提高了大众对经典诗词的鉴赏水平。
- Projection word W: `A 11 30|||W|||唤起 了 人们 对 经典 诗词 的 记忆 ， 而且 提高 了 大众 对 经典 诗词 的 鉴赏 水平|||-REQUIRED-|||NONE|||0`
- Projection character edits: `A 18 49|||W|||唤起了人们对经典诗词的记忆，而且提高了大众对经典诗词的鉴赏水平|||-REQUIRED-|||NONE|||0`
- ChERRANT character edits: `A 18 20|||S|||唤 起|||REQUIRED|||-NONE-|||0 ; A 21 23|||S|||人 们|||REQUIRED|||-NONE-|||0 ; A 29 33|||S|||记 忆|||REQUIRED|||-NONE-|||0 ; A 36 38|||S|||提 高|||REQUIRED|||-NONE-|||0 ; A 39 41|||S|||大 众|||REQUIRED|||-NONE-|||0 ; A 47 49|||S|||鉴 赏 水 平|||REQUIRED|||-NONE-|||0`
