# docs/history — preserved adversarial & remediation record

The stage READMEs are kept short. The long adversarial-falsification, robustness, and
remediation history is **not deleted** — it lives in the documents catalogued here. Cite
these when you need the "why" behind a current decision.

## Stage 1 — CD4 programs
- `01_programs/REMEDIATION_STATEMENT.md` — why the stage reports continuous scores, not
  cell-type calls.
- `01_programs/analysis/STAGE1_REMEDIATION_METHOD.md` — the frozen method spec.
- `01_programs/analysis/STAGE1_REMEDIATION_CHANGES.md` — old-vs-new change report
  (donor × condition score distributions).
- `01_programs/analysis/STAGE1_EXTERNAL_REVIEW_CS.md`,
  `01_programs/analysis/STAGE1_EXTERNAL_REVIEW_HANDOFF.md`,
  `01_programs/analysis/STAGE1_REMEDIATION_REVIEW_CS.md`,
  `01_programs/analysis/REVIEW_MEMO.md` — independent Claude Science reviews.
- `STAGE1_T7B_LOMO_ESTIMAND_MEMO.md` — the T7b LOMO estimand memo.

## Stage 2 — gene skew
- `02_geneskew/STAGE2_PLAN.md` — design decisions and schemas (GO/essentiality left
  unresolved in §17: specify-and-pin or omit, never promise).
- `02_geneskew/STAGE2_REVIEW.md`, `STAGE2_REVIEW_R2.md`, `STAGE2_REVIEW_R3.md` — review rounds.
- `HANDOVER_temporal_th1_treg.md`, `cs_review_temporal_th1_treg.md` — the temporal /
  cross-condition exploration and its independent review.

## Cross-stage
- `HANDOVER.md` — the running build handover.
- `HANDOFF_W12_routingReason_logic_fix.md` — routing-reason fix record.
- `REVIEWER_dataset_decomposition_prompt.md`, `REVIEWER_stage1_verification_prompt.md` —
  the independent-reviewer prompts (generator ≠ verifier).
- `spot_buildout_plan.md` — the full build plan.
- `STAGE_UI_DESIGN_CONTRACT.md` — the shell / hand-off UI contract.

Paths above are relative to `docs/` unless they start with a stage folder.
