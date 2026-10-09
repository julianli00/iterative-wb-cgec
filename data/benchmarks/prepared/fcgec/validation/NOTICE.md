# FCGEC validation: modification, attribution, and data-use notice

**`pipeline.tsv` and `gold.para` are modified, prepared-format derivatives
of FCGEC validation, not the publisher's original JSON files.** This notice
applies to each file individually. Keep it and the accompanying license with
either file when sharing the data; the headerless data format is retained for
compatibility with the existing reader.

## Source and license

- Dataset: **FCGEC: Fine-Grained Corpus for Chinese Grammatical Error Correction**.
- Publisher repository: [xlxwalex/FCGEC](https://github.com/xlxwalex/FCGEC).
- Frozen source revision: `851cfb043e9cca8bc2f866d46987e10b24b1b9d6`.
- Original file: [`data/FCGEC_valid.json`](https://github.com/xlxwalex/FCGEC/blob/851cfb043e9cca8bc2f866d46987e10b24b1b9d6/data/FCGEC_valid.json).
- Original JSON SHA256:
  `6afb961cae85c0fce8aa97dd7e0c68907a704ff7b08e0b9aa337128e24fdf9f2`.
- [Exact upstream Apache License 2.0](../../../licenses/FCGEC-Apache-2.0.txt),
  copied without modification from the
  [pinned upstream LICENSE](https://github.com/xlxwalex/FCGEC/blob/851cfb043e9cca8bc2f866d46987e10b24b1b9d6/LICENSE).
  License-file SHA256:
  `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`.

FCGEC's separate
[upstream data-use conditions](https://github.com/xlxwalex/FCGEC/blob/851cfb043e9cca8bc2f866d46987e10b24b1b9d6/README.md#数据使用条件)
are retained in addition to the license:

> 通过下载数据或以任何方式访问FCGEC数据，您同意仅将数据用于非商业和学术研究目的。除此之外，这些数据不得用于任何非法或歧视性的目的。

English translation: by downloading or otherwise accessing FCGEC data, users
agree to use it only for **noncommercial and academic research purposes**.
The data must not be used for illegal or discriminatory purposes.

This distribution does not remove those conditions, grant broader commercial
rights, relicense FCGEC as MIT, or apply FCGEC's license to any other benchmark.
It is a downstream research-format conversion, not an official new FCGEC
release or an endorsement by the original authors.

## Changes from the original format

The existing
[`scripts/prepare_scoreboard_datasets.py`](../../../../../scripts/prepare_scoreboard_datasets.py)
conversion was used for the completed experiment; publication copies its
already prepared bytes without regenerating the corpus:

- Preserve the validation JSON's source-record order.
- Reconstruct complete textual references from the original edit operations;
  use the unchanged source as the reference for no-error records.
- Remove BOMs, replace embedded tabs and newlines with spaces, trim surrounding
  whitespace, and deduplicate complete references in first-occurrence order.
- Write `pipeline.tsv` as source plus first reference, without a header.
- Write `gold.para` as one-based sequential ID, source, and all complete
  prepared references, without a header.
- Omit the original UUIDs, operation records, and error-category fields from
  these two prepared files. No model-generated corrections are substituted.

Both files contain 2,000 aligned source rows. `gold.para` contains 2,550
complete references, including identity references. Every first reference
matches the corresponding reference in `pipeline.tsv`. These are validation
data, not the hidden FCGEC test labels.

| Prepared file | Bytes | SHA256 |
| --- | ---: | --- |
| `pipeline.tsv` | 664733 | `9e30d8121253dc3a1940c567e581784a65483ef5cf99bcf0ac0de3e78e185ca0` |
| `gold.para` | 769811 | `c19eb3033e83e11e0a3d31f63ac113e8aee286c89cb3d7619818bfdb9bd9f2ef` |

The [prepared-file inventory](../../../prepared_files.json) records local
availability and hashes for all eight benchmarks. Only this FCGEC pair is
redistributed; the other fourteen files must be obtained under their own
publisher terms.

## Citation

Lvxiaowei Xu, Jianwang Wu, Jiawei Peng, Jiayu Fu, and Ming Cai. 2022.
[FCGEC: Fine-Grained Corpus for Chinese Grammatical Error Correction](https://aclanthology.org/2022.findings-emnlp.137).
In *Findings of the Association for Computational Linguistics: EMNLP 2022*,
pages 1900-1918. Association for Computational Linguistics.

```bibtex
@inproceedings{xu2022fcgec,
    title = "{FCGEC}: Fine-Grained Corpus for {C}hinese Grammatical Error Correction",
    author = "Xu, Lvxiaowei  and
      Wu, Jianwang  and
      Peng, Jiawei  and
      Fu, Jiayu  and
      Cai, Ming",
    booktitle = "Findings of the Association for Computational Linguistics: EMNLP 2022",
    year = "2022",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/2022.findings-emnlp.137",
    pages = "1900--1918"
}
```
