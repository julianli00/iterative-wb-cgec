# Final Projection Artifact Audit

**Status: PASS**

This audit uses only saved model outputs and local evaluation artifacts; it makes no LLM or API calls.

## Coverage

- Saved DeepSeek rows: 20,213
- Fixed gold-informed source segmentations: 20,213
- M2 files validated: 104
- M2 blocks parsed and reconstructed: 262,769
- Physical M2 annotations checked: 795,161
- Linked movements checked as reciprocal U--M pairs: 13,907
- Character M2, word M2, character GLEU, and word GLEU each contain all 8 datasets x 4 stages.

## Invariants

- Every saved row has non-empty T0--T3 output and successful API metadata.
- Every linked movement passed syntax, reciprocal-coordinate, material-identity, non-overlap, and reconstruction checks.
- The fixed evaluation-side source segmentation preserves the learner characters.
- The word-M2 and word-GLEU source segmentation is byte-for-byte identical across T0--T3 for every sentence.
- No BPE is used in any final result.

## Threshold Sensitivity

| Unit | L_max values | Maximum F0.5 range | Mean F0.5 range |
| --- | --- | --- | --- |
| character | 2, 3, 4 | 0.0000 | 0.0000 |
| word | 2, 3, 4 | 0.0100 | 0.0016 |

The reported setting is `L_max_char = 3` and `L_max_word = 3`. Character scores are invariant across the tested values; word scores vary by at most 0.0100 F0.5 points.
