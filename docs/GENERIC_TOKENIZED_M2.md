# Generic MRU/W M2 from tokenized source–target pairs

`scripts/generic_m2.py` implements two separate steps:

1. Reconstruct every complete target from an existing M2 annotation file,
   retaining the original source tokens, reference IDs, and reference order.
2. Realign the **supplied token sequences** using exact anchors plus
   Transformer similarity, then produce generic M/R/U/W annotations.

This is a local annotation/conversion tool, not a correction model. It makes
no generative LLM/API calls. It does not change the existing Chinese
experiments or their scores.

The current generic edit policy is **`punctuation-separated-v2`**: an edit
cannot contain both standalone punctuation/symbol tokens and lexical tokens,
whether on the source side, correction side, or across the two sides. See
[the punctuation revision and worked examples](GENERIC_M2_PUNCTUATION_REVISION_20261006.md).

## Quick start

Extraction needs only Python 3.9 or newer:

```bash
python3 -m scripts.generic_m2 extract /path/to/input.m2 \
  --output-dir runs/generic_extract
```

Generation additionally needs PyTorch, Transformers, NumPy, and safetensors:

```bash
python3 -m pip install -r requirements-generic-m2.txt
python3 -m scripts.generic_m2 generate /path/to/input.m2 \
  --output-dir runs/generic_annotations \
  --allow-download
```

Use an existing compatible environment instead of installing into a shared
environment. The development environment used for the attached English files
has PyTorch 2.7.1, Transformers 4.54.1, and NumPy 2.0.2.

The first generation command above explicitly permits downloading the pinned
pretrained encoder. **Without `--allow-download`, loading is offline-only**.
No source sentences or references are uploaded: only pretrained model assets
are downloaded.

Multiple M2 files can be processed in one run:

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
python3 -m scripts.generic_m2 generate /path/to/m2/*.m2 \
  --output-dir runs/generic_annotations \
  --batch-size 16 --torch-threads 4
```

The persistent alignment cache avoids duplicate inference when component and
combined corpus files contain the same pairs. Every original record still
appears in its own output; caching does **not** deduplicate the corpus.
Existing output paths are protected unless `--overwrite` is explicitly used.
Even with `--overwrite`, configuration, cache, and data output paths must not
alias any batch input or each other, including through symbolic or hard links.
Output names must also be distinct ignoring case and Unicode normalization,
so an archive remains safe on case-insensitive filesystems.
Cache configuration mismatches are errors: use a new output/cache path when
changing the model or alignment settings.

### Reuse existing Transformer alignments without another model pass

```bash
python3 -m scripts.generic_m2 relabel /path/to/old_outputs/*.pairs.jsonl \
  --input-format jsonl \
  --alignment-cache /path/to/old_outputs/alignment_cache.sqlite3 \
  --output-dir runs/generic_annotations_punctuation_v2
```

This reads the old cache in read-only mode, validates the saved exact and
similarity links, ignores its old edit labels, and regenerates annotations
with the current punctuation policy. A missing pair or incompatible cache is
an error; the command never silently falls back to encoder inference. The
old cache and outputs remain intact. This command needs only the standard
library, not PyTorch or Transformers. `generate` remains available for new
pairs requiring new local encoder computation.

## What each input file produces

For `input.m2`, extraction writes:

- `input.pairs.jsonl`: authoritative token arrays, reference IDs/order, and
  skipped non-correction annotation metadata.
- `input.pairs.tsv`: headerless, tab-separated `source`, `target_1`, ...,
  `target_n`, with spaces separating the existing tokens.
- `input.audit.json`: counts, input SHA256 before/after, and extraction metadata.

Generation also writes:

- `input.generic.m2`: generic M/R/U/W physical records, plus `noop` when a
  complete reference is identical to the source.
- `input.alignments.jsonl`: exact and similarity token links, with cosine
  values for accepted residual links.
- An expanded audit proving token-exact target reconstruction, reference
  identity/order preservation, and linked-movement validity.
- `run_config.json`: frozen model/alignment settings, progress/completion
  status, output manifests, and actual encoder inference counters.

Large corpora, generated source/reference text, and model caches belong in
ignored local output directories. Their original data licenses still apply;
this tool does not grant redistribution rights.

## Input formats

### Standard M2

Use `--input-format m2` (the default). Source positions are offsets in the
original supplied token sequence. Replacements are applied simultaneously:
earlier insertions do not shift the coordinates of later annotations.
Multiple insertions at the same boundary retain their file order.

Annotators are reconstructed independently in first-appearance order. Neither
identical references nor nonconsecutive annotator IDs are discarded.
`noop`, `UNK`, and `Um` are non-correction markers: they do not rewrite the
source, but remain in the extraction JSON and are counted in the audit.
The attached W&I/LOCNESS files' `UNK` spans contain unchanged material, so
ignoring those markers does not omit a textual correction.

An S-only block is treated explicitly as one identity reference with annotator
ID 0. Empty token sequences are supported. Overlapping edits for one reference,
out-of-range offsets, malformed annotations, mixed `noop`/actual edits, and
unsupported record prefixes cause an error rather than a guessed target.
`REQUIRED` and the repository's historical `-REQUIRED-` spelling are accepted.
Other requirement policies are rejected rather than silently deciding whether
to apply them.

The supplied [M2-to-sentence reference](https://github.com/asimokby/GEC-M2Format-to-Sentence)
was inspected at revision `bad0a1efdb2af5d88641167d743ea44eebfb1261`.
Its interface is useful as an illustration, but directly changing list lengths
at original M2 offsets is unsafe with multiple insertions and variable-length
replacements. It also does not group all annotator references. The extractor
here is an independent implementation; no upstream code was copied.

### Tokenized TSV pairs

```bash
python3 -m scripts.generic_m2 generate pairs.tsv \
  --input-format tsv --output-dir runs/from_pairs
```

There is no header. Every row contains source and at least one target field.
Additional target fields become independent references with IDs 0, 1, ...
An empty target field is an empty target sentence, **not** a missing reference.
Standard TSV/CSV quoting is supported.

For example, the two fields below are separated by a tab:

```text
I go to school .	I went to school .
我 喜欢 苹果 。	我 很 喜欢 苹果 。
我 喜 欢 苹 果 。	我 很 喜 欢 苹 果 。
```

The second row is Chinese word-tokenized input, while the third is
character-tokenized input. The program does not guess either representation.
An unsegmented string passed as one token remains one token.

TSV preserves token sequences and reference order, but has no field for
arbitrary original annotator IDs or skipped annotation metadata. Use JSONL
when those must survive extraction and regeneration exactly.

### Token-array JSONL

```json
{"id":"example-1","source_tokens":["I","go","."],"references":[{"annotator_id":7,"target_tokens":["I","went","."]},{"annotator_id":2,"target_tokens":["I","go","."]}]}
```

```bash
python3 -m scripts.generic_m2 generate input.pairs.jsonl \
  --input-format jsonl --output-dir runs/from_jsonl
```

The extraction JSONL uses this same schema. It may additionally include
`skipped_annotations` within each reference. IDs and reference order are
preserved when rendering M2.

## Transformer alignment

The default encoder is multilingual cased BERT:

- Model: `google-bert/bert-base-multilingual-cased`.
- Pinned revision: `3f076fdb1ab68d5b2880cb87a0886f315b8146f8`.
- Contextual representations: final-layer hidden states.
- Token pooling: mean over **all subwords assigned to each original token**.
- Evaluation mode, seed 0, CPU by default.
- Default cosine threshold: `0.60`, configurable with
  `--similarity-threshold`.

A different compatible fast-tokenizer encoder can be selected with `--model`
and `--revision`; a local safetensors model directory is also supported.
Remote custom model code is not trusted or executed. Resolved revisions or
local model file hashes are recorded.

Exact token matches first form a longest common subsequence with deterministic
ties. Between consecutive exact anchors, the aligner chooses a noncrossing
set of residual correspondences maximizing the sum of cosine similarity minus
the threshold. Only similarities strictly above the threshold are eligible.
No fuzzy correspondence may cross a fixed exact anchor.

The similarity threshold is an **explicit engineering default**, not a
linguistically calibrated accuracy threshold. All scores/accepted links are
available for audit. Transformer similarity affects how residual replacements,
insertions, and deletions are grouped; it does not change any source or target
token.

After alignment, adjacent same-type edit spans and unaligned gaps can produce
multi-token edits. The generic converter refines any span mixing standalone
punctuation and words with a deterministic minimum-cost local token alignment.
Substitution across the punctuation/word distinction is forbidden. It then
merges only consecutive same-type subedits whose source/correction units stay
homogeneous. This handles already-mixed gaps as well as adjacent replacements,
insertions, deletions, and mixed word-order envelopes. The frozen Transformer
links remain unchanged; this is a rule for the emitted edit boundaries.

Pure lexical multiword spans remain possible, as do punctuation-only spans.
The rule is a punctuation boundary constraint, **not** a syntactic or semantic
phrase recognizer. Multiword lexical grouping still comes from alignment
continuity. Attached punctuation inside a token such as `can't`, `mother-in-law`,
`3.14`, or `word,` is not split: the supplied tokenization remains authoritative.
Standalone Unicode punctuation and symbol-only tokens are separated from words,
including English and Chinese punctuation.

Unlike the original Chinese character pipeline, this generic aligner does
not concatenate words, run LTP, or use Chinese glyph/pinyin tables. Its
language-independent interface preserves the exact supplied units, while the
encoder determines language coverage and similarity quality. Supporting an
input language structurally is not proof of accurate alignment in that
language.

Transformer subword tokenization is internal only. M2 offsets always count
the **original supplied tokens**, not subwords. Tokens such as literal
`##text`, case, punctuation, and Unicode characters are not normalized away.
The M2 field delimiter `|||` and whitespace inside a single token are
unrepresentable in this whitespace-tokenized format and are rejected.
A single literal `-NONE-` as correction material is also rejected because it
is ambiguous with the M2 deletion sentinel.

Long encoder inputs use all nonoverlapping overflow windows rather than
silently dropping a suffix. A token split across windows pools all of its
subwords. Missing word IDs, zero coverage, and non-finite embeddings are
errors. Each window has independent contextual boundaries, so representations
near a window edge may differ from those from a longer-context model.

## Generic labels and long-distance order changes

- **M:** target material inserted at an empty source span.
- **R:** nonempty source material replaced by nonempty target material.
- **U:** source material deleted.
- **W:** an exact permutation of tokens, preserving duplicate counts.

For a short permutation, the generator emits a single W span. For a detected
long, unchanged single-block movement, it emits reciprocal linked U/M records
under the existing movement-aware protocol:

```text
S Yesterday I saw the bird .
A 0 1|||U|||-NONE-|||-REQUIRED-|||LINK=w1;TO=5|||0
A 5 5|||M|||Yesterday|||-REQUIRED-|||LINK=w1;FROM=0:1|||0
```

These reconstruct `I saw the bird Yesterday .`. They encode **one logical
long-distance W**, reported separately as `WO` by the repository's scorer.
They are not two independent correction operations.

The default `--l-max 3` uses the movement's source envelope in **supplied token
units**, not the number of moved tokens. Unique exact U/M block pairs can also
be linked across intervening ordinary edits. Complex permutations that cannot
be decomposed into a validated single-block movement may remain conventional
W spans even when their envelope is longer than this threshold.

Movement detection is conservative: lexical changes, ambiguous repeated moved
material, or unsupported multi-block structure are not grounds to invent a
link. Some linguistic reordering may remain represented by ordinary edits.
Conversely, identical distant deletion/insertion material can reflect two
independent grammatical changes rather than an intended movement, especially
for frequent function words. A valid linked representation alone cannot
resolve that linguistic ambiguity; movement labels need human assessment
before making annotation-accuracy claims.
Token-exact reconstruction demonstrates serialization correctness, **not**
human-level grammatical annotation accuracy.

Under the punctuation-separated policy, a W span or linked block that mixes
punctuation and words is decomposed as needed. Affected links are removed
before refinement, and eligible homogeneous exact U/M moves are linked again
afterwards. A linguistically related punctuation-plus-word correction can
therefore be represented as several operations intentionally; the target
token sequence is unchanged.

For linked scoring, use the movement-aware comparator rather than an
unmodified scorer that counts the U and M separately:

```bash
python3 -m scripts.movement_aware_compare \
  --hypothesis output.generic.m2 --reference gold.generic.m2 --unit word
```

Here `--unit word` means “use each whitespace-delimited supplied token as one
unit,” including when an application supplies Chinese characters as tokens.

## Audit and tests

Audit a serialized file independently from the generation pass:

```bash
python3 -m scripts.generic_m2 audit \
  --m2 runs/generic_annotations/input.generic.m2 \
  --pairs runs/generic_annotations/input.pairs.jsonl \
  --require-separate-punctuation \
  --output runs/generic_annotations/input.independent-audit.json
```

The audit reconstructs every target from the serialized M2, verifies all
references and their identities/order, rejects non-generic labels, validates
the movement links, and checks that the comparator represents a linked pair
as one logical movement. The flag additionally rejects any punctuation/lexical
mixed edit; newly generated/relabelled runs always require this constraint.
Without the flag, `audit` can still inspect historical v1 M2 and reports the
number of mixed edits rather than assuming the new policy. Failed runs do not publish partially written data
files; `run_config.json` must say `completed` before a run is treated as
complete. An empty corpus cannot pass an audit; a legitimate record with an
empty source/target is supported. Frozen-cache integrity is checked before a
relabel run is marked completed.

```bash
python3 -m unittest discover -s tests -v
```

Tests cover original-coordinate extraction, same-boundary insertions,
multi-reference/noop preservation, Chinese character/word and English token
inputs, Unicode/case preservation, residual similarity, noncrossing anchors,
word-order cases, linked scoring, overflow pooling, cache reuse, and explicit
failure on invalid data. Tests also cover synthetic punctuation/capitalization
examples, multilingual punctuation, homogeneous phrase retention, and read-only
relabeling without loading a Transformer.
