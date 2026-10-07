# Independent recheck of the punctuation-separated M2 package

## Outcome

The delivered v2 **annotation data pass the independent checks below**. No
changes to the nine M2 files, sentence pairs, Transformer links, or punctuation
grouping policy were required by this review.

The review did find command-line/audit edge-case defects. These were reproduced
using disposable fixtures, repaired, and regression-tested. The refreshed
**v2.1 delivery** contains the same annotation data with the corrected tools.
This is not a new model run or a new set of target sentences.

## Independent checks on the actual ZIP

The verification reads the delivered ZIP directly. Its data checks use a
separate standard-library parser and reverse original-coordinate edit
application; they do not import the generator's M2 reader, reconstruction,
punctuation, or movement-validation helpers.

| Check | Result |
| --- | --- |
| Delivered files | All nine generic M2 files present |
| Records | All 77,384 file-record occurrences checked |
| Source tokens | Match the frozen, previously verified extracted pairs |
| Target tokens | Every complete target reconstructed exactly |
| TSV and JSONL | Token sequences and reference ordering agree |
| Annotator IDs/order | Preserved, including identity references |
| Mixed punctuation/lexical edits | **0**, checking source and correction together |
| Generic operation shapes | M inserts, U deletes, R replaces, W is a nonidentity exact token permutation |
| Linked U/M movements | All **1,060** pairs have reciprocal coordinates and identical moved material; each contributes one logical WO |
| Duplicate corpus coverage | Combined training/development files equal the multisets of their component files |
| Packaging | ZIP integrity and every manifest checksum pass; no missing or duplicate members |

The counts include combined/component duplicates. The canonical combined
training and development files contain **38,692 records** and **530 linked
movements**; they must not be concatenated with their component files.

Logical operation totals across all nine delivered files are unchanged:
M=47,748; R=80,536; U=21,320; W=1,452; WO=1,060.

The previously verified preservation of 14,044 existing multiword lexical
M/R/U spans remains valid: the review does not modify the edit-construction
algorithm or any output bytes. Some spans carry new movement metadata from
the earlier punctuation revision; this was already documented.

The independent input evidence is the archived extraction and its hashes.
The original attached raw-M2 directory is no longer available at its previous
path; this review does not claim to have reread missing raw files. It checks
the generated data against the previously validated, unchanged token pairs.

## Problems reproduced and repaired

### 1. Output/input path collisions

Previously, a specially chosen output directory plus `--overwrite` could let
`run_config.json` overwrite a same-named JSONL input before conversion rejected
it. Batch outputs also needed protection against aliasing another input or
the configured output cache.

The CLI now validates every planned configuration, cache, audit, and data
destination **before opening output files or loading a Transformer**. Inputs
are protected even when `--overwrite` is supplied. Duplicate destinations,
symbolic links, and hard links are checked explicitly. Existing later-batch
outputs are rejected before earlier outputs are written.
The preflight and converter use the same resolved input filenames. Destination
names must also be distinct under case-insensitive, Unicode-normalized
comparison, including before any files exist.

These collisions were not present in the completed nine-file run and did not
affect its results.

### 2. Empty audit inputs

Previously, an empty M2 file accompanied by an empty pair file could receive a
structural `PASS` without containing any records.

An empty corpus now fails explicitly. A real M2 record representing an empty
source or empty target is still supported and tested.

### 3. Finalization ordering

Frozen alignment-cache integrity is now verified before publishing a
`completed` run status. A changed source cache produces `failed`, rather than
a completion marker followed by a closing-time error.

## Further edge-case validation

The focused tests use synthetic fixtures preserving both reported
punctuation/capitalization fragments and their offsets, and cover
punctuation present on only one side, mixed unaligned gaps, insertions,
deletions, word order, split movement links, and retention of lexical phrases.
Contractions, hyphenated words, decimal numbers, literal pipe tokens,
multilingual punctuation, nonconsecutive annotator IDs, and empty sequences
are also covered.

An additional fixed-seed check exercised **5,000** source/target pairs of
length 0–20, including repeated tokens, English/Chinese/Arabic-script material,
punctuation, symbols, emoji, contractions, and literal pipes. Reconstruction,
punctuation separation, and linked scoring passed. These synthetic checks
assess implementation invariants, not linguistic accuracy.

The refreshed focused suite passes under both Python 3.9 and Python 3.10.
The full repository suite is also run separately. None of these checks calls
a correction model or executes a Transformer forward pass.

## What is not claimed

This review does **not** establish that every automatic alignment or error
label is a human gold-standard decision. Pure lexical spans are still grouped
by alignment continuity, not by a syntactic phrase parser. A distant identical
deletion/insertion may be a structural movement representation even when a
human would prefer two independent corrections.

The supported conclusion is specific: the advisor's punctuation/capitalization
examples are separated correctly, no standalone punctuation is mixed into a
lexical edit in the delivered data, and all token sequences/coordinates and
linked representations satisfy the verified contracts.
