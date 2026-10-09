# AI Handoff: Iterative WB-CGEC

Historical handoff prepared on 2026-09-18, with later result updates.
This public copy contains compact evidence, not the original local research
workspace, raw generations, full manuscript, or private records.

> **Dataset publication update (2026-10-09):** only the FCGEC validation
> `pipeline.tsv` and `gold.para` are included, with 2,000 sources and 2,550
> references, under the upstream license and noncommercial academic data-use
> conditions. All eight pairs exist in the original research workspace, but
> the other 14 files are not redistributed. Read the
> [dataset availability and licensing guide](data/benchmarks/README.md) before
> obtaining or sharing any dataset; do not infer permission from public access.

> **Default result presentation (user instruction, 2026-09-21):** compare only
> Kimi, DeepSeek, and GPT-5.6 Sol, and present evaluation results plus their
> recorded calling parameters. Give each model its own chapter and result table. Use
> [the three-model evaluation comparison](paper/arr_october_2026/KIMI_DEEPSEEK_GPT56_EVALUATION_RESULTS.md)
> for the complete four-metric R/D/P/I tables. Its current Word GLEU is the
> revised S1/S1/S2/S3 version; older fixed-source word-GLEU values are historical.
> Preserve existing experiment records and audits separately from this presentation.

> **Latest statistical documentation (2026-09-29):** the
> [GPT-5.6 Sol statistics and execution answers](paper/arr_october_2026/GPT_STATISTICS_ANSWERS_20260929.md)
> document completed inference, source coverage, recorded settings, and limitations.
> Full manuscript revisions, delivery archives, and Overleaf build materials
> remain local-only; they are not included in this public copy.

## Archived experiment notes

> **GPT-5.6 Sol nonthinking experiment completed 2026-09-21:** all 20,213
> sources and four metrics are complete in
> [the Sol results report](paper/arr_october_2026/GPT56_SOL_NONTHINKING_RESULTS.md).
> All 43,495 successful formal calls report `none` and zero reasoning tokens.
> Temperature/top-p are unexposed defaults, not minimum values; the attempted
> output-cap override did not work. Reuse the saved outputs under
> `runs/gpt_5_6_sol_copilot_nothinking/`; do not regenerate them for evaluation.
> On Direct/T1 character F0.5, Sol is below DeepSeek and GPT-6 on all seven
> formal datasets and above Kimi on four. These are point estimates, not
> between-model significance tests or a GPT-6 thinking ablation.

> **Word-GLEU revision (approved 2026-09-19, evaluated 2026-09-20):** Kimi and
> DeepSeek now use saved S1/S1/S2/S3 as the word-GLEU source for T0/T1/T2/T3.
> See [the revised results and paired statistics](paper/arr_october_2026/KIMI_DEEPSEEK_REVISED_WORD_GLEU_20260919.md)
> and [the complete four-metric report](paper/arr_october_2026/KIMI_DEEPSEEK_FOUR_METRICS_REVISED_WORD_GLEU_20260919.md).
> These were recomputed from the 16 authoritative JSONL files, with zero new
> model calls and unchanged input hashes. The older fixed-source word-GLEU
> values below are historical; M2, character GLEU, and primary conclusions
> remain unchanged. Word M2 still uses shared fixed gold-informed boundaries.

## Start here

1. Read this file, `README.md`, and `paper/arr_october_2026/KIMI_DEEPSEEK_GPT56_EVALUATION_RESULTS.md` for current results. `TABLES_AND_ANALYSIS.md` is a historical analysis whose fixed-source word-GLEU columns are superseded.
2. Inspect `git status` and the latest commit before changing anything.
3. Treat `.env` as private. Never print, quote, or commit API keys.
4. Reuse the saved model outputs. Do not make new LLM calls unless the user explicitly asks for a new generation experiment.
5. Except for the published FCGEC validation source/reference pair, source corpora, per-sentence generations, M2 files, and bootstrap draws remain in the original local research workspace under `runs/` and `data/benchmarks/prepared/`. They are not supplied by this public clone; do not assume they exist here.

## Research goal and pipeline

The project tests whether explicit and iteratively projected word boundaries improve Chinese grammatical error correction (CGEC). The four evaluated conditions are:

- **R / T0 / Raw:** prompt the unsegmented learner sentence.
- **D / T1 / Direct:** segment the learner sentence with LTP and prompt that input.
- **P / T2 / Projected:** project word boundaries derived from `T1` back onto the learner source, then prompt again.
- **I / T3 / Iterative:** project from `T2` once more and prompt again.

When two adjacent projected inputs have the same normalized character sequence and inter-character boundary vector, the row has converged. The pipeline carries the preceding correction forward and does not call the LLM again. Projection supports both boundary splits and merges.

The evaluation protocol is:

- Projection-derived character and word M2 evaluation with M/R/U/W labels.
- Short-range word order is a single W edit; linked long-distance movement is a reciprocal U-M pair scored once and reported as WO.
- No BPE and no OpenCC; normalization removes only BOM/whitespace where specified.
- `L_max_char = 3` and `L_max_word = 3`.
- Character and word GLEU use 1-4 grams.
- Every multi-reference metric selects the best complete reference independently per sentence. Edit scoring uses highest unrounded sentence F0.5 with deterministic tie-breaking; GLEU uses highest sentence GLEU.
- The primary metric is projection-based character corpus micro-F0.5 on a 0-100 scale. Secondary metrics are word F0.5 and character/word GLEU.

## Data and models

Eight benchmark splits were evaluated, totaling 20,213 source sentences and 38,000 complete references. Of these, 7,704 sources have multiple references and 1,613 have at least four.

| Dataset | Split | Sentences |
| --- | --- | ---: |
| NLPCC2018 | test | 2,000 |
| MuCGEC | test | 6,000 |
| YACLC | validation | 1,000 |
| FlaCGEC | test | 1,325 |
| FCGEC | validation | 2,000 |
| NaCGEC | test | 5,869 |
| NaSGEC-Exam | test | 2,000 |
| CEFE Track 3 | validation/descriptive only | 19 |

Historical two-model settings (the current three-model parameters are in the
linked formal report):

- **DeepSeek:** `deepseek-v4-pro`, thinking disabled, temperature `0.000001`, one sample. `max_tokens` was omitted; the documented non-thinking default is 8,192. The longest saved completion is 200 tokens.
- **Kimi:** `kimi-k2.6`, thinking disabled, provider-fixed non-thinking temperature `0.6`, one sample, `max_tokens=512`. The longest saved completion is 259 tokens.
- Neither model approached its output cap, so output-limit truncation did not affect the saved results.
- Be precise when explaining temperature: DeepSeek's near-zero value was explicitly chosen for this experiment; Kimi's 0.6 was fixed by that endpoint. The actual DeepSeek value is `0.000001`, not `0.0001`.

## Completed engineering work

1. `scripts/run_iterative_gec.py` now compares normalized boundary signatures for convergence, avoiding extra calls caused only by whitespace formatting.
2. `scripts/movement_aware_compare.py` now performs sentence-local multi-reference selection by default. The historical order-dependent corpus-greedy mode remains available as `selection_mode="corpus"` for audit/reproduction.
3. `scripts/run_paired_bootstrap_analysis.py` builds dataset/model tables, validates every serialized reference, exports sentence-level metrics, and runs the full paired analysis.
4. Tests cover normalized convergence, multi-reference selection, M2 reference preservation, boundary diagnostics, micro-F0.5, and BCa helpers.
5. Manuscript-ready Markdown, TSV, and LaTeX tables are in `paper/arr_october_2026/`.

The historical 2026-09-18 validation reported:

- 202,130 character/word M2 blocks and 380,000 serialized references checked for exact text, count, and annotator order.
- 161,704 sentence-condition rows exported.
- Historical corpus-greedy mode reproduced all 128 cached edit-score cells.
- Correct sentence-local selection changed 10 of those 128 displayed cells.
- 50,000 paired source-level BCa bootstrap replicates, seed `20260915`.
- 73 tests passed and `git diff --check` passed before handoff.

## Statistical analysis and conclusions

The analysis uses paired source-sentence resampling. It reports 95% BCa intervals for differences and 90% BCa intervals for practical equivalence, with a pre-specified equivalence margin of +/-0.50 points and sensitivity margins of +/-0.25 and +/-1.00. CEFE Track 3 has only 19 examples and is descriptive rather than inferential.

Historical DeepSeek/Kimi result (the later Sol analysis is documented separately):

- Across the 28 formal P-D and I-P comparisons, 20 meet the +/-0.50 practical-equivalence criterion and 23 exclude an improvement of at least +0.50 points.
- There are 2 directional improvements and 3 deteriorations; the other later-stage contrasts are inconclusive.
- DeepSeek often benefits from Direct WB input, but subsequent projection/iteration is mostly equivalent to the preceding stage.
- Kimi does not reproduce broad Direct gains. Its main positive projection exception is FlaCGEC P-D: +0.67 character F0.5 points, 95% BCa interval [+0.19, +1.20].
- Raw character GLEU exceeds Direct on 5/8 DeepSeek datasets and all 8/8 Kimi datasets.
- The defensible conclusion is that projection and iteration do **not consistently provide a practically meaningful downstream improvement**. Do not overstate this as "they never help."

## Important files

Current formal presentation:

- `paper/arr_october_2026/KIMI_DEEPSEEK_GPT56_EVALUATION_RESULTS.md`: separate model chapters, calling parameters, and four-metric results.
- `paper/arr_october_2026/kimi_deepseek_gpt56_evaluation_results.tsv`: model-grouped full-precision scores.
- `paper/arr_october_2026/kimi_deepseek_gpt56_call_parameters.tsv`: recorded parameters and evidence, separate from metric rows.

Historical compact deliverables and audits:

- `paper/arr_october_2026/TABLES_AND_ANALYSIS.md`: historical consolidated analysis; its fixed-source word-GLEU columns are not current results.
- `paper/arr_october_2026/PAPER_TABLES.tex`: compact historical dataset/two-model tables, not the full manuscript.
- `paper/arr_october_2026/table_2_dataset_statistics.tsv`
- `paper/arr_october_2026/table_3_model_configuration.tsv`: historical two-model configuration; the current three-model parameter TSV is authoritative.
- `paper/arr_october_2026/README_ANALYSIS_COMPLIANCE.md`
- `runs/FINAL_PROJECTION_EVALUATIONS.md`
- `runs/PAPER_SECTION_5_3_6_INPUTS.md`
- `runs/final_projection_audit/AUDIT.md`
- `runs/final_alignment_examples/QUALITATIVE_ALIGNMENT_EXAMPLES.md`
- `runs/kimi_k2_6/KIMI_VS_DEEPSEEK.md`
- `runs/sections_6_7_analysis/`

Local generated analysis artifacts, intentionally ignored by Git:

- `runs/paired_bootstrap_analysis/PAPER_TABLES_AND_ANALYSIS.md`
- `runs/paired_bootstrap_analysis/sentence_level_scores.tsv` (about 63 MB)
- `runs/paired_bootstrap_analysis/bootstrap_primary.csv`
- `runs/paired_bootstrap_analysis/bootstrap_secondary.csv`
- `runs/paired_bootstrap_analysis/equivalence_sensitivity.csv`
- `runs/paired_bootstrap_analysis/changed_boundary_diagnostics.csv`
- `runs/paired_bootstrap_analysis/convergence_and_cost.csv`
- `runs/paired_bootstrap_analysis/scorer_selection_audit.tsv`
- `runs/paired_bootstrap_analysis/validation.log`

In the supplied manuscript, dataset statistics are Table 2 and model configuration is Table 3.

## Historical follow-up checklist (2026-09-18)

The dataset tables and paired statistical analysis were complete at this
handoff. The checklist below records follow-up items from that date, not a
claim that they are all still unresolved. Later GPT statistics and coverage
answers supersede the corresponding missing-analysis concerns; manuscript
work remains outside this public snapshot.

1. Integrate the ready values and prose into the separately maintained LaTeX/Overleaf source; full manuscript files are local-only.
2. Extend operation-level M/R/U/W/WO analysis to Kimi. Existing operation analysis under `runs/sections_6_7_analysis/` is primarily DeepSeek-only.
3. Extend reference-density analysis to both models and reconcile it with the new sentence-local selector.
4. Complete or explicitly mark unavailable the C-based LTP versus Python LTP comparison requested by the mentor. The C implementation may require Linux.
5. Map and manually verify qualitative examples under the requested five reporting categories M, R, U, W, and WO.
6. Fill or remove the external previous-CGEC comparison section if no methodologically fair comparison can be established.
7. Rewrite the remaining manuscript red placeholders, limitations, and final discussion using the corrected tables and cautious negative-result framing.

## Historical reproduction

Run the test suite from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

The archived two-model fixed-source statistical analysis can be regenerated
from its local saved artifacts with the command below. It does not produce
the current revised three-model presentation:

```bash
python3 scripts/run_paired_bootstrap_analysis.py
```

This does not call an LLM, but it reads large ignored artifacts and performs 50,000 bootstrap replicates. Preserve seed `20260915`, chunk size `1000`, and the sentence-local reference-selection protocol unless a deliberate sensitivity analysis is requested.

## Prompt for the next AI

```text
You are taking over the iterative WB-CGEC research project in
/path/to/iterative-wb-cgec.

First read AI_HANDOFF.md, README.md, and
paper/arr_october_2026/KIMI_DEEPSEEK_GPT56_EVALUATION_RESULTS.md, then inspect git status and the
latest commit. Treat .env and all API credentials as private. Reuse the saved
Kimi, DeepSeek, and GPT-5.6 Sol T0-T3 outputs; do not make new LLM calls unless I explicitly
request them. Keep the final protocol unchanged: no BPE, sentence-local
select-best for every multi-reference metric, projection-derived character and
word M2, linked U-M pairs scored once as WO, and faithful saved carry-forward.
Use revised word-GLEU sources S1/S1/S2/S3; word M2 retains shared fixed-gold
sources. Present each model separately with its recorded calling parameters.
Do not present the archived fixed-source word-GLEU tables as current results.

The dataset/model tables and paired bootstrap/equivalence analysis are already
complete. The central finding is that Direct WB sometimes helps, especially
for DeepSeek, but projected and iterative WB do not consistently yield a
practically meaningful further gain. Consult the current results and later
statistical answers before treating any historical checklist item as unfinished;
follow my newest instruction as the source of truth. Before editing, verify
which saved artifacts are actually available in the workspace and the existing
tests; after editing, run focused tests plus the full suite and clearly report
what changed, what remains, and whether any result required new model calls.
```
