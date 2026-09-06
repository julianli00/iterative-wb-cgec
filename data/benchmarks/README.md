# Scoreboard Dataset Preparation

The local benchmark collection follows a test-first policy: use public test
gold when it is available; otherwise use a public validation/development split
with gold and label the resulting score as validation rather than test.

| Dataset | Selected split | Rows | Gold status | T3 decision |
| --- | --- | ---: | --- | --- |
| NLPCC2018 | test | 2,000 | Public multi-reference M2 | Run |
| MuCGEC | test | 6,000 | Public multi-reference M2 from CGECData | Run |
| YACLC | validation | 1,000 | Public multi-reference annotations; test is source-only | Run as validation |
| FlaCGEC | test | 1,325 | Public source-target pairs | Already run through T10 |
| FCGEC | validation | 2,000 | Public operation labels; test gold is hidden | Run as validation |
| NaCGEC | test | 5,869 | Public multi-reference ground truth | Run |
| NaSGEC-Exam | test | 2,000 | Public multi-reference M2 | Run without BPE under the final protocol |
| CEFE Track 3 | validation | 19 | Public source-target pairs; test gold is hidden | Diagnostic only |
| MCSCSet | test | 19,650 | Public source-target pairs | Exclude from core GEC run: medical spelling correction only |
| CCTC | test | document-level | Official Baidu link, not locally accessible | Requires data access and a document-level pipeline |

NaSGEC-Media and NaSGEC-Thesis are not included because their publisher asks
users to sign and send the sharing agreement. NaSGEC-Exam may be used directly
under the repository's sharing terms.

Prepared data live under `data/benchmarks/prepared/<dataset>/<split>/`:

- `pipeline.tsv`: headerless source and one reference for the current runner.
- `gold.para`: ID, source, and all available references.
- `gold.m2`: official M2 gold when the publisher provides it.
- `metadata.json`: source URL, split rationale, and evaluation caveats.

Rebuild the prepared files:

```bash
python3 scripts/prepare_scoreboard_datasets.py
```

Run selected datasets through T3 and evaluate them with ChERRANT:

```bash
python3 scripts/run_scoreboard_t3.py --workers 4 --checkpoint-every 25
```

The experiment uses `deepseek-v4-pro`, temperature `0.000001`, disabled
thinking, the paper's Chinese prompts, LTP initial segmentation, and the WB
alignment/projection implementation from `chinese-wb-fixing`. Once adjacent
projected segmentations are identical, later LLM calls are skipped and the
previous output is carried forward.
