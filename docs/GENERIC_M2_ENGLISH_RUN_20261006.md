# English M2 conversion: completed run

> This report records the original v1 annotation counts. The subsequent
> [punctuation-separated v2 revision](GENERIC_M2_PUNCTUATION_REVISION_20261006.md)
> replaces mixed punctuation/word edit spans in a separate output directory.
> The original v1 files and target sentences are preserved.

The nine attached W&I/LOCNESS BEA-2019 M2 files have been processed through
both requested steps:

1. Extract the tokenized source and all complete targets from the original
   annotations.
2. Generate new generic M/R/U/W M2 using exact-token anchors plus contextual
   multilingual Transformer similarity.

All input files retain their original SHA256 hashes. No correction LLM/API was
called. All original source and reconstructed target token sequences were
preserved, and every generated M2 file passed independent reconstruction.

## Output coverage

Counts below are **logical operations**, so each linked U/M pair contributes
one `WO`, not an additional M plus U.

| Input file | Source/reference records | M | R | U | W | WO |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `A.dev.gold.bea19.m2` | 1,037 | 841 | 1,668 | 416 | 19 | 12 |
| `A.train.gold.bea19.m2` | 10,493 | 8,246 | 16,253 | 3,808 | 239 | 168 |
| `ABC.train.gold.bea19.m2` | 34,308 | 19,123 | 34,863 | 8,577 | 704 | 407 |
| `ABCN.dev.gold.bea19.m2` | 4,384 | 2,388 | 4,193 | 1,005 | 60 | 45 |
| `B.dev.gold.bea19.m2` | 1,290 | 804 | 1,404 | 349 | 27 | 16 |
| `B.train.gold.bea19.m2` | 13,032 | 7,360 | 13,244 | 3,429 | 318 | 164 |
| `C.dev.gold.bea19.m2` | 1,069 | 373 | 594 | 151 | 11 | 14 |
| `C.train.gold.bea19.m2` | 10,783 | 3,517 | 5,366 | 1,340 | 147 | 75 |
| `N.dev.gold.bea19.m2` | 988 | 370 | 527 | 89 | 3 | 3 |
| **All file occurrences** | **77,384** | **43,022** | **78,112** | **19,164** | **1,528** | **904** |

**The combined files overlap their component files.** The `ABC.train` file is
the same record multiset as A/B/C training files; `ABCN.dev` is the same as
A/B/C/N development files. Use the combined pair, or the component files, not
both when assembling a corpus.

The combined files contain 34,308 training and 4,384 development records:
**38,692 records**, with **37,793 distinct tokenized source–target pairs**.
Repeated records remain in the outputs. Persistent pair caching only avoids
repeating the alignment computation.

## Model and annotation policy

| Setting | Value |
| --- | --- |
| Contextual encoder | `google-bert/bert-base-multilingual-cased` |
| Model revision | `3f076fdb1ab68d5b2880cb87a0886f315b8146f8` |
| Representation | Final-layer hidden states, mean-pooled over all subwords belonging to each supplied token |
| Exact anchors | Longest common token subsequence; deterministic deletion-first ties |
| Residual alignment | Noncrossing maximum-sum matching inside exact-anchor gaps |
| Similarity threshold | Cosine strictly above 0.60; heuristic default, not a calibrated linguistic accuracy threshold |
| Word-order envelope | `l_max=3` supplied tokens for linking eligible long block moves |
| Device / batch / CPU threads | CPU / 16 / 4 |
| Software | Python in the existing `fixwb` environment; PyTorch 2.7.1, Transformers 4.54.1, NumPy 2.0.2 |
| Generative model calls | 0 |

M2 uses the original input tokens as its offset units. Internal Transformer
subwords never replace those units. The generator is separate from the
Chinese-specific character/glyph pipeline and does not call LTP or change
historical evaluation results.

There are 78,872 accepted similarity anchors across all file occurrences,
in addition to 1,313,254 exact anchors. The completed full pass reports 56
unknown encoder subwords; their original source/target tokens were retained
unchanged. These vocabulary-level unknowns are distinct from the corpus's
original `UNK` annotation markers.

The nine supplied files each contain a single annotator per source, but the
extractor and renderer also preserve multiple complete references,
nonconsecutive annotator IDs, identical references, and identity corrections.
Those cases are covered by tests rather than invented additional dataset rows.

## Files

The full local outputs are under:

```text
runs/generic_m2_20261006/
  extracted/                         # Step 1 outputs
  generated/
    <input-stem>.pairs.jsonl          # Authoritative token arrays/references
    <input-stem>.pairs.tsv            # Readable tokenized source/targets
    <input-stem>.generic.m2           # New generic annotations
    <input-stem>.alignments.jsonl     # Exact and similarity link evidence
    <input-stem>.audit.json           # Per-file validation and hashes
    alignment_cache.sqlite3           # Configuration-locked pair cache
    run_config.json                  # Completed generation configuration
  extraction_validation.json
  duplicate_coverage_audit.json
  FINAL_AUDIT.json
```

The original attached files are not modified or committed. Generated learner
text and annotation files remain ignored by Git; their source data licensing
and redistribution restrictions still apply.

## Validation performed

- All **77,384** extracted source/reference records matched an independent
  right-to-left original-coordinate edit-application oracle, including
  multiple insertions at the same source boundary.
- All **77,384** generated M2 records reconstructed the exact expected target
  token sequence under both the regular reader and an independent reverse
  splicing implementation.
- JSONL, readable TSV, generated M2, and original source/reference sequences
  agree; original annotator order and identity are retained.
- Every physical annotation is M, R, U, W, or the required `noop` identity
  marker. Invalid source spans or incompatible operation/correction shapes
  are rejected.
- All **904** linked movements across file occurrences passed reciprocal
  coordinate/material checks and were counted exactly once by the scorer.
- The combined/component corpus overlap was checked as a multiset.
- Real local-encoder checks exercised English, Chinese word-level, Chinese
  character-level, and a 550-token input requiring five Transformer windows;
  all original token positions remained covered.
- Focused tests and the complete repository suite passed, including
  multilingual synthetic pairs and short-sequence round-trip checks.

These checks establish extraction, coordinate, and serialization correctness.
They **do not establish that the new alignment or W/WO labels are linguistically
more accurate than the original annotations**. In particular, distant identical
insertions/deletions may be independent grammatical changes rather than an
intended movement. The generic error labels and similarity threshold require
qualitative assessment before making annotation-accuracy claims.

## Reproduce

After the pinned model is locally cached:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false \
/path/to/compatible/python -m scripts.generic_m2 generate \
  /path/to/m2/*.m2 \
  --output-dir runs/generic_m2_reproduction \
  --batch-size 16 --torch-threads 4
```

See [the generic input/output and alignment documentation](GENERIC_TOKENIZED_M2.md)
for separate extraction, arbitrary tokenized TSV/JSONL input, long-distance
movement scoring, and standalone audit commands.
