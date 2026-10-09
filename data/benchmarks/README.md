# Benchmark availability and preparation

## What is available

As checked on **2026-10-09**, all eight prepared splits exist in the original
local research workspace: **16 source/reference files, 20,213 sources, and
38,000 complete references**. "Local: yes" below refers to that workspace,
not to the contents of a fresh clone.

**Only FCGEC validation is distributed here: two files containing 2,000
sources and 2,550 references. The other 14 files are not published.** A
publisher making data downloadable does not by itself permit redistribution;
repository code licenses must not be substituted for dataset-specific terms.

| Dataset | Split | Sources | References | Local pair | Public pair in this repository | Pinned publisher source and access route |
| --- | --- | ---: | ---: | --- | --- | --- |
| NLPCC2018 | test | 2,000 | 2,183 | Yes | Not published; redistribution permission unverified | [NLPCC2018_GEC at `6cd5ecad110f`](https://github.com/zhaoyyoo/NLPCC2018_GEC/tree/6cd5ecad110f). Obtain through the publisher's instructions; request redistribution permission before sharing a copy. |
| MuCGEC | test | 6,000 | 13,119 | Yes | Restricted; no third-party redistribution under the data sharing agreement | [CGECData at `19daf271e3d9`](https://github.com/SUDA-LA/CGECData/tree/19daf271e3d9fc6875078a74f4e0245cc8aa59e4). Read the MuCGEC/NaSGEC sharing agreement and obtain access from the publisher for the recipient's own organization. |
| YACLC | validation | 1,000 | 8,931 | Yes | Restricted; written BLCU ICALL permission required to redistribute | [YACLC at `bf17c54e8f55`](https://github.com/blcuicall/YACLC/tree/bf17c54e8f55d36b019bef782eccbb1cdd027e81). Follow its publisher access instructions and seek written permission before reproducing or sharing downloaded data. |
| FlaCGEC | test | 1,325 | 1,325 | Yes | Not published; redistribution permission unverified | [FlaCGEC at `79850e3fe3b6`](https://github.com/hyDududu/FlaCGEC/tree/79850e3fe3b6ce8893345790d1e114a2a7b25e31). Obtain the test data from the publisher under its terms; ask for redistribution permission. |
| FCGEC | validation | 2,000 | 2,550 | Yes | **Published**, subject to the upstream license and noncommercial academic data-use conditions | [FCGEC at `851cfb043e9cca8bc2f866d46987e10b24b1b9d6`](https://github.com/xlxwalex/FCGEC/tree/851cfb043e9cca8bc2f866d46987e10b24b1b9d6). Use the prepared pair below with its accompanying license and notice, or obtain the original validation JSON from the publisher. |
| NaCGEC | test | 5,869 | 6,978 | Yes | Not published; redistribution permission unverified | [NaCGEC at `da54f1e3ccb9`](https://github.com/masr2000/NaCGEC/tree/da54f1e3ccb9). Obtain the released test references from the publisher and seek permission before republishing. |
| NaSGEC-Exam | test | 2,000 | 2,895 | Yes | Restricted; no third-party redistribution under the data sharing agreement | [CGECData at `19daf271e3d9`](https://github.com/SUDA-LA/CGECData/tree/19daf271e3d9fc6875078a74f4e0245cc8aa59e4). Follow the NaSGEC access procedure and the MuCGEC/NaSGEC agreement, including organizational-use restrictions. |
| CEFE Track 3 | validation | 19 | 19 | Yes | Not published; competition-only terms, validation redistribution permission unestablished | [2023CCL_CEFE at `db121b8cae3e`](https://github.com/cubenlp/2023CCL_CEFE/tree/db121b8cae3e). Contact the organizers for access and permission compatible with the intended use; do not assume the competition terms cover outside use or redistribution. |

The restriction review uses YACLC's explicit prohibition on reproducing,
republishing, distributing, or transmitting downloaded data without written
permission; CGECData's **2025-02-18 MuCGEC/NaSGEC sharing agreement**, which
limits use to the recipient organization and prohibits third-party spread;
and CEFE's competition-only conditions. No affirmative dataset redistribution
license was identified for NLPCC2018, FlaCGEC, or NaCGEC. This is a record of
the publication decision, not a grant of rights to any dataset. The controlling
publisher documents include the
[MuCGEC/NaSGEC sharing agreement](https://github.com/SUDA-LA/CGECData/blob/19daf271e3d9fc6875078a74f4e0245cc8aa59e4/2025.02.18_MuCGEC_NaSGEC_Sharing_Agreement.docx),
[YACLC access conditions](https://github.com/blcuicall/YACLC/blob/bf17c54e8f55d36b019bef782eccbb1cdd027e81/README.md#how-to-obtain-the-dataset),
and [CEFE data conditions](https://github.com/cubenlp/2023CCL_CEFE/blob/db121b8cae3e/README.md#3-评测数据).

The [prepared-file inventory](prepared_files.json) records all 16 local file
paths, byte counts, SHA256 hashes, and per-dataset publication decisions.
It contains metadata only, not the withheld source or reference text. These
hashes help recipients identify the same prepared inputs after obtaining
the data lawfully; they do not grant access or redistribution rights.

Recipients, including collaborators, must obtain withheld datasets from their
original publishers under the applicable terms or secure actual written
redistribution permission. This repository does not accept agreements on a
recipient's behalf, provide a bulk downloader for restricted data, or offer
private-repository/archive copies as a workaround.

## Published FCGEC validation pair

Read the [modification, attribution, and data-use notice](prepared/fcgec/validation/NOTICE.md)
and the [exact upstream Apache 2.0 license](licenses/FCGEC-Apache-2.0.txt)
alongside the data. The notice includes the pinned original JSON hash and
the authors' citation.

- [`pipeline.tsv`](prepared/fcgec/validation/pipeline.tsv): headerless UTF-8 TSV;
  each row contains the source sentence and its first prepared reference.
- [`gold.para`](prepared/fcgec/validation/gold.para): headerless UTF-8 TSV;
  each row contains a one-based sequential ID, the same source, and all
  complete prepared references in order.

Both files have 2,000 aligned source rows; `gold.para` has 2,550 references.
The first reference in every `gold.para` row is the reference in the
corresponding `pipeline.tsv` row. Use a TSV-aware reader rather than splitting
on arbitrary whitespace.

These are **derived-format files**, not an unchanged mirror of the original
`data/FCGEC_valid.json`. The existing
[`prepare_fcgec`, `convert_fcgec_operations`, and `write_split` implementation](../../scripts/prepare_scoreboard_datasets.py)
reconstructs complete targets from the publisher's operations, uses the source
as the reference for no-error records, removes BOMs, replaces embedded tabs
and newlines with spaces, trims surrounding whitespace, and removes duplicate
references while preserving their first occurrence. It retains source order
and assigns the prepared one-based IDs. The publisher's UUIDs, operation
annotations, and error-category fields are not included in these two files.
No new model output or experimental result is generated for publication.

The upstream repository supplies Apache License 2.0 and separately states
that FCGEC data are for **noncommercial and academic research only**, not for
illegal or discriminatory purposes. Those data-use conditions are retained;
this project does not relicense the corpus as MIT or claim that the other
benchmarks share FCGEC's license.

FCGEC validation is not the hidden test set. Its test labels remain behind
the publisher's [CodaBench evaluation service](https://www.codabench.org/competitions/15596/);
the scores here must not be represented as official hidden-test results.

## Remaining local preparation

The selection policy is test-first where public gold exists; otherwise a
validation/development split is explicitly labelled as such. YACLC and FCGEC
use validation, and CEFE's 19 validation sentences are descriptive only.
NaSGEC-Exam is evaluated without BPE under the final protocol. NaSGEC-Media
and NaSGEC-Thesis are outside the evaluated eight-split collection; MCSCSet
and CCTC are also not part of this publication.

Other prepared splits remain at local-only
`data/benchmarks/prepared/<dataset>/<split>/` paths. Their `metadata.json`
files and the collection manifest are public provenance records, not evidence
that the referenced `pipeline.tsv`, `gold.para`, or official `gold.m2` is
distributed here.

After independently obtaining the required original inputs and checking their
terms, the existing preparation script can rebuild the local files:

```bash
python3 scripts/prepare_scoreboard_datasets.py
```

This script reads local inputs; it neither obtains publisher permission nor
makes model calls. It expects the full local input collection and is not
needed just to use the published FCGEC pair. Saved predictions, model assets,
and other experiment inputs remain local-only, so the two published files do
not make a fresh clone sufficient to reproduce every archived experiment.
