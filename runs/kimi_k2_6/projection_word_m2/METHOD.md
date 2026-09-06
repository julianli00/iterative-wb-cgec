# Projection-based Word M2 Method

- Existing T0--T3 predictions are reused; no LLM calls are made.
- Every T0--T3 stage uses the same source segmentation: LTP boundaries from the closest gold reference are projected onto the learner source.
- The closest gold reference is selected by minimum raw character Levenshtein distance, with first-reference tie breaking.
- Gold references and corrected hypotheses are segmented with the same LTP installation.
- The saved WB projection character edits are aggregated into monotonic word anchors.
- Coarse labels are M, R, U, and W only; long-distance one-block movements use linked U--M records and count once as W-LD.
- Multiple references retain distinct annotator IDs in each stage-specific reference M2 file.
- No BPE is used.
