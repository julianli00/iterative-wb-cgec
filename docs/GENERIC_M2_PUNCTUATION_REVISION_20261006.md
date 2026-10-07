# Punctuation-separated generic M2: explanation and revision

## Why the original edits were merged

The first version grouped edits by **alignment continuity**, not by a
linguistic phrase parser:

1. Gaps between token-alignment anchors became M/R/U spans.
2. Consecutive edits were merged when they had the same operation type and
   contiguous source and target offsets.
3. Eligible exact permutations were represented as W or linked U/M movement.

For both reported punctuation/capitalization fragments, the saved Transformer alignment
already matched the punctuation and the following word separately. The two
one-token R edits were subsequently merged because both source and target
offsets were adjacent:

| Example | Saved token matches | Cosine values |
| --- | --- | --- |
| `, it` to `. It` | comma to period; `it` to `It` | 0.825823; 0.869013 |
| `, however` to `. However` | comma to period; `however` to `However` | 0.774292; 0.833037 |

The similarity values support token correspondences, **not** a conclusion
that punctuation plus the next word is one linguistic phrase. The original
merger had no punctuation constraint, which caused the reported issue.

## Current behavior

The current generic policy, `punctuation-separated-v2`, does not allow an
emitted edit to mix standalone punctuation/symbol tokens with lexical tokens.
It checks both the replaced source span and the correction material.

The following synthetic illustrations preserve the reported fragment offsets
without reproducing the original learner sentences:

```text
S This synthetic example places a boundary after several tokens , it ends here .
A 9 10|||R|||.|||-REQUIRED-|||NONE|||0
A 10 11|||R|||It|||-REQUIRED-|||NONE|||0
```

```text
S This synthetic sentence contains some extra context so that the next boundary appears here , however , we still preserve every token .
A 14 15|||R|||.|||-REQUIRED-|||NONE|||0
A 15 16|||R|||However|||-REQUIRED-|||NONE|||0
```

These synthetic examples show only the punctuation/capitalization edits under
discussion; they are not corpus quotations. Offsets are zero-based and half-open.

Pure lexical multiword edits remain possible. For example,
`utilise mass` to `use public` can remain one contiguous lexical R span.
This is still an alignment-based grouping heuristic: removing mixed
punctuation/word spans does **not** establish that every remaining span is a
syntactic constituent or a semantically independent correction.

### Boundary rule

- Punctuation/symbol-only tokens are identified from Unicode categories.
- A gap already containing punctuation and words is split, not merely
  prevented from merging with a neighboring edit.
- Inside such a span, deterministic local token alignment forbids
  punctuation-to-word substitutions. Consecutive same-type subedits merge
  only within a homogeneous punctuation or lexical run.
- Insertions and deletions use the same boundary rule as replacements.
- Mixed W envelopes or linked blocks are decomposed; any affected movement
  links are rebuilt only for valid homogeneous exact moved material.
- Punctuation **inside one supplied token** is not retokenized: `can't`,
  `mother-in-law`, `3.14`, and `word,` remain single tokens.
- Target sentences, tokenization, annotator identity, and reference order
  are unchanged.

## Regeneration and validation

All nine original English result files were regenerated from the verified
saved token pairs and the original Transformer links. No encoder inference or
generative model call was needed.

| Check | Result |
| --- | ---: |
| Source/reference record occurrences across nine files | 77,384 |
| Distinct cached source-target pairs | 37,793 |
| Mixed punctuation/lexical edits in v1 | 7,952 |
| Mixed punctuation/lexical edits in v2 | **0** |
| Records whose edit annotations changed | 6,326 |
| Existing multiword lexical M/R/U spans preserved | 14,044 |
| Preserved lexical spans gaining valid link metadata | 22 |
| New Transformer inference | 0 |
| New generative LLM calls | 0 |

The counts include combined/component-file duplicates. The combined training
and development files contain 38,692 records; do not concatenate them with
their component files.

For every output, validation independently checked exact target reconstruction,
absence of mixed punctuation/lexical edit material, unchanged reference
identity/order, and unchanged extracted JSONL/TSV pairs. The saved Transformer
alignment files are byte-for-byte unchanged. All v1 M2 files and the original
alignment cache remain unchanged.

The original local `m2/` input directory was no longer present when
this revision ran. The regeneration therefore used the saved extraction
JSONL files whose SHA256 hashes matched the completed original extraction
audit; it did not substitute unverified inputs.

## New files and reproducing the change

New outputs are separate from v1:

```text
runs/generic_m2_punctuation_v2_20261006/
  generated/
    <stem>.generic.m2
    <stem>.pairs.jsonl
    <stem>.pairs.tsv
    <stem>.alignments.jsonl
    <stem>.audit.json
    alignment_cache.sqlite3
    run_config.json
  PUNCTUATION_REVISION_AUDIT.json
```

```bash
python3 -m scripts.generic_m2 relabel \
  runs/generic_m2_20261006/generated/*.pairs.jsonl \
  --input-format jsonl \
  --alignment-cache runs/generic_m2_20261006/generated/alignment_cache.sqlite3 \
  --output-dir runs/generic_m2_punctuation_v2_20261006/generated \
  --batch-size 128
```

The frozen cache is read-only; old cached edit labels are not reused. Missing
pairs or invalid links cause errors, not an automatic model-inference fallback.
The original Chinese experimental M2 helpers and scores are unchanged: this
new policy applies only to the separate generic tokenized-M2 generator.

## Short reply to the advisor

> You're right—the original rule merged adjacent edits of the same type when
> their source and target spans were contiguous; it wasn't checking linguistic
> phrase boundaries. That's why the punctuation change and capitalization
> change ended up in one R edit. I've separated standalone punctuation from
> lexical edits, so these are now two edits (comma to period, and `it` to `It`
> / `however` to `However`). Contiguous multiword lexical edits are still
> allowed. I've regenerated the files using the saved alignments and checked
> that all target sentences remain unchanged.
