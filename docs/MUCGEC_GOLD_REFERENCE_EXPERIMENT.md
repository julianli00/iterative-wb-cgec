# MuCGEC dev: first additional selected-gold experiment

This experiment is separate from the historical test-set T0--T3 runs. It uses
only DeepSeek and Kimi and produces **R, D and P**, not an iterative I condition
or the proposed projection-from-R-output experiment.

## Input contract

The private UTF-8 CSV must have these columns, in order:

```text
Index,Target_ID,Target_Text,Source_Text
```

Each row supplies one source and one already-selected, already-LTP-segmented
gold target. `Index` is a unique ASCII decimal identifier; sources must also
be unique after removing BOM/whitespace. The original four fields are preserved
in `prepared.jsonl`.

- **R:** strip the human source boundaries and use the historical raw paper prompt.
- **D:** run the same LTP model on that raw source and use the segmented paper prompt.
- **P:** project the supplied target boundaries onto D's source segmentation with
  the existing WB projection function, Chinese BERT/shape table and threshold 0.85.
  Use the segmented paper prompt on the resulting source, not on the target.

The target is **never reselected or resegmented**. Its token separators are only
canonicalized to single spaces. Human source boundaries are provenance only.
All three inputs must contain exactly the same learner characters.

P is a gold-informed/oracle-style condition: reference information supplies the
boundaries, but neither the target text nor human source segmentation is sent
as extra context to the correction model.

The supplied October 9 CSV contains 1,079 selected pairs, one reference each.
Evaluation uses that exact single-reference subset; do not silently substitute
the 6,000-row MuCGEC test gold or claim evaluation over all dev references.
Additional complete dev references would require a separately specified evaluation.

## Execution

Use the existing LTP/PyTorch/Transformers environment and cached Chinese models.
`runs/` is ignored; retain learner data, predictions and request receipts there,
not in public Git.

```bash
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false

python scripts/run_gold_reference_experiment.py prepare \
  --input /private/path/to/levcos+human.csv \
  --wb-repo external_tools/chinese-wb-fixing \
  --shape-table external_tools/wb-shape-data/triplet_no_dup_threshold.csv

# Supply DEEPSEEK_API_KEY and KIMI_API_KEY privately in the process environment.
# No credentials are read from .env automatically or written to run metadata.
python scripts/run_gold_reference_experiment.py generate --model deepseek --limit 8 --workers 1
python scripts/run_gold_reference_experiment.py generate --model kimi --limit 8 --workers 1

# Inspect the pilot receipts first. Full runs reuse successful pilot conditions.
python scripts/run_gold_reference_experiment.py generate --model deepseek --workers 4

# This account reported a 100 requests/minute organization limit; pace at 80.
python - <<'PY'
import os
from pathlib import Path
from scripts.run_iterative_gec import _API_RATE_LIMITER
from scripts.run_gold_reference_experiment import generate
_API_RATE_LIMITER.configure(80)
generate(
    Path("runs/mucgec_dev_gold_first"), "kimi",
    api_key=os.environ["KIMI_API_KEY"], workers=4,
)
PY

python scripts/evaluate_gold_reference_experiment.py
```

The default output root is `runs/mucgec_dev_gold_first`. For another experiment,
pass `--output /private/run/path` **before** `prepare`/`generate`; pass the same
path as `--run` to the evaluator.

| Model | Endpoint | Configuration |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-v4-pro`; temperature `0.000001`; thinking disabled; `max_tokens` omitted |
| Kimi | `https://api.moonshot.ai/v1` | `kimi-k2.6`; temperature omitted (endpoint-fixed 0.6 in non-thinking mode); thinking disabled; `max_tokens=512` |

Top-p and seed are omitted. Prompts and response cleaning come directly from
`run_iterative_gec.py`. The strict option rejects model substitution, unsupported
settings and non-stop completions rather than silently changing the experiment.
The historical explicit content-filter identity fallback remains recorded.

Do not infer the thinking mode solely from `usage.reasoning_tokens`: Kimi can
return an empty `reasoning_content` alongside a nonzero accounting counter.
The request must explicitly disable thinking, the response must not contain
reasoning text, and reported usage is preserved verbatim. See the provider's
[parameter reference](https://platform.kimi.ai/docs/api/models-overview).

As in the historical pipeline, normalized-boundary equality between D and P
causes P to carry D's prediction forward. R and D are always independently
prompted. There are 782 such rows in the supplied CSV, leaving 297 rows that
require a distinct P request: 2,455 executed conditions per model before any
retries, and 3,237 saved condition predictions per model.

## Resume and provenance

Prepared inputs and generation configurations are fingerprinted. Per-condition
receipts are written before the request and atomically updated after responses.
Successful conditions are never requested again on resume; unresolved in-flight
requests require manual reconciliation to avoid duplicate paid calls. Failed
requests require inspection before explicit `--retry-failed`.

The runner preserves raw responses, usage, format retries, carry-forward markers
and content-filter fallbacks. A per-model process lock prevents concurrent
writers. Pilot exports never overwrite full-corpus predictions.

Code fingerprints are part of the generation identity. Do not edit the running
generation implementation and then resume it under a different identity. Exact
implementation snapshots for the October 9 run are retained in its ignored
`implementations/` directory; DeepSeek used `generation_v1`, and Kimi used
`generation_v2` after correcting a local zero-reasoning-counter check. API
request settings and prompts did not change. Kimi's first saved response was
revalidated offline, not generated twice; original receipt and recovery evidence
are in `kimi/recovery/`.

The completed October 9 generation has 4,928 recorded HTTP attempts: 2,455 for
DeepSeek and 2,473 for Kimi. Kimi's extra transport/validation events comprise
16 rate-limit responses, one format retry and one truncated response. Two
content-filter rejections use the historical identity fallback rather than
dropping the rows. The truncated response was rejected and retried with the
same 512-token cap; successful predictions were never regenerated.

## Evaluation and deliverables

Both M2 levels reuse the historical Chinese projection-derived aligner and
movement-aware scorer, with `L_max_char=L_max_word=3`. Linked reciprocal U--M
pairs count once as WO. Micro precision, recall and F0.5 use pooled counts,
not averages of sentence F-scores. Complete-reference selection remains
sentence-local; this input has only one reference per source.

Word M2 uses a single fixed gold-informed source segmentation (the prepared P
input) for every model and condition. Reference words are the supplied Target
tokens; prediction words come from LTP.

Character GLEU uses character-tokenized source, hypothesis and reference in
every condition. Word GLEU uses D's source tokens for R/D and P's source tokens
for P. Hypotheses use LTP; references reuse the supplied Target tokens. Both
levels use the existing 1--4-gram, sentence-macro GLEU implementation. No BPE,
OpenCC, alternate reference selection or alternate M2 tool is introduced.
Word GLEU can change due to source boundaries alone even when correction text
is unchanged; interpret it alongside character GLEU and both M2 levels.

An additional read-only tokenization check uses hypotheses whose raw text
already exactly matches the reference. In the supplied run, 113 of 634 such
condition predictions, covering at least 35 distinct source rows, have LTP
tokens different from the supplied reference tokens. This is a partial check,
not an audit of every reference. All 1,024 unchanged-source predictions agree
with their saved direct-LTP inputs. The provided reference boundaries were
retained unchanged for that generation and evaluation.
Word metrics therefore include this reference/hypothesis tokenization
disagreement. Character metrics are unaffected by that disagreement.
`tokenization_diagnostics.tsv` identifies every checked case.

### Base-model reproduction check, October 10

The user subsequently reported Python 3.11, `ltp==4.2.14`, and a Hugging Face
base checkpoint loaded from a local `LTP_base` folder for the CSV Target WB.
A separate diagnostic using Python 3.11.9 and `LTP/base` revision
`97d6e77d2d7e93c435ec0fb297800f54964323be` reproduced **all 1,079 Target token
sequences exactly** after whitespace canonicalization. All 35 previously
flagged source IDs matched, both individually and within batch-32 inference.

The checkpoint and tokenizer files were downloaded through `hf-mirror.com`
after official-domain connection timeouts, pinned and checked against the
mirrored metadata's SHA256/Git blob hashes. The native LTP loader's default
non-strict loading was retained, but all 247 model-state entries were explicitly
verified equal to the checkpoint. The only extra checkpoint entry was
`backbone.embeddings.position_ids`, now a nonpersistent Transformers buffer;
its value was verified equal, not removed or changed in the checkpoint.
The model ran in evaluation mode on CPU, with network access blocked during
inference and no custom dictionary.

Results are under the ignored run directory's
`ltp_base_reproduction_20261010/`: `comparison_summary.json`,
`all_target_comparison.tsv`, `pilot_35_comparison.tsv`, and a header-only
`remaining_mismatches.tsv`. The user's historical exact revision is still not
independently established, but this base setup is fully compatible with the
supplied Target tokenization. It should not be confused with the `LTP/small`
setup used for D inputs and hypothesis segmentation in the completed run.

That diagnostic left the original CSV, all generation inputs/outputs and
existing GEC scores unchanged, and made no correction-LLM calls. It only checked
Target reproduction. The user subsequently authorized the separate
base-aligned output evaluation below.

### Base-aligned output evaluation

The completed October 10 reevaluation covers all **6,474 condition outputs**
(3,443 unique texts). All 634 outputs exactly equal to a Target now have identical
Target/output tokenization, including all 113 previously flagged records from
35 source IDs. Original generation and character-level results are unchanged.
Current base-aligned tables are in `evaluation_ltp_base/RESULTS.md`,
`metrics.tsv` and `deltas.tsv`; `word_metrics_previous_vs_base.tsv` isolates
the scoring change from the previous small-model output segmentation.

`evaluation_ltp_base/` is separate from the historical `evaluation/` directory.
It uses the verified Python 3.11.9 / `ltp==4.2.14` / pinned `LTP/base` setup to
segment **all saved R_output/D_output/P_output texts**, not only the previously
flagged examples. Identical output texts share one saved segmentation.
The supplied Target tokens remain unchanged; the base reproduction above
established compatibility with all 1,079 Targets.

Only output evaluation segmentation changes. `D_input` remains the actual
LTP/small input used for generation, and `P_input` remains the original
projection from the supplied Target tokens onto that D input. The reference
word-M2 source stays fixed at P_input across all six model/condition groups.
Word GLEU still uses the actual saved D_input for R/D and P_input for P.
No GEC request, input boundary, output character, reference text or reference
selection is changed. This is **not** an all-base rerun of the prompting pipeline.

The evaluator accepts a separately prepared segmentation bundle:

```bash
python scripts/evaluate_gold_reference_experiment.py \
  --output runs/mucgec_dev_gold_first/evaluation_ltp_base \
  --hypothesis-segmentations \
    runs/mucgec_dev_gold_first/evaluation_ltp_base/hypothesis_segmentations.json
```

The `ltp-output-segmentations-v1` JSON bundle contains the prepared-input hash,
both prediction-file hashes, explicit model/revision/runtime metadata, and
a `segmentations` mapping from each unique raw output text to its tokenized
form. Missing or extra texts, mismatched hashes, changed output characters and
invalid token separators are rejected; the evaluator never falls back to
LTP/small for a missing base segmentation. Without this option the original
default behavior is retained.

The new report names the evaluation model separately from the frozen generation
model. Its exact-Target diagnostic must show equal tokens whenever an output
equals Target. A diagnostic comparing unchanged-source output tokens with
the old D_input may instead differ because D_input deliberately retains
generation-time LTP/small boundaries; it is not a reason to rewrite old inputs.

The evaluator requires complete ordered predictions, matching source/reference
identities, intact hashes and matching durable receipts. Every character/word
M2 block is reconstructed from its serialized edits before scoring.

Outputs under the run root:

- `prepared.jsonl`, `inputs.tsv`, `{R,D,P}.inputs.txt`: original fields, shared
  source inputs, projection statistics and convergence markers.
- `{deepseek,kimi}/predictions.{jsonl,tsv}` and `requests/`: all R/D/P predictions
  and their private durable receipts.
- `evaluation/RESULTS.md`, `metrics.tsv`, `deltas.tsv`: all eight metrics and
  P-R/P-D changes, computed before rounding.
- `evaluation/reference.{character,word}.m2` and per-model M2, segmented
  hypotheses, GLEU inputs, per-sentence counts, caches and integrity manifests.
- `evaluation/tokenization_diagnostics.tsv`: existing hypothesis tokenizations
  compared with supplied references or saved direct-LTP source inputs.

Positive deltas alone are not significance or practical-equivalence findings.
This first experiment does not add bootstrap inference or modify the historical
paired analyses.
