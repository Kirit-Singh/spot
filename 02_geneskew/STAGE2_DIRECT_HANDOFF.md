# Stage-2 Direct — handoff

Branch `agent/stage2-direct-v3`. Checkpoint-committed, **not pushed**. No deploy, no PR.

**READY-FOR-REAL-RUN** — code + fixtures only. No real data was touched: no DE, no
pseudobulk, no tcefold. The real run and the content-addressed bundle freeze are a
separate gated dispatch.

```
tests/            959 passed,  6 skipped
tests/direct      930 passed,  5 skipped   (shuffled seeds 1 / 7 / 20260712: identical)
ruff              clean          compileall  clean
modules           all <= 500     schemas     3, all valid
```

Skips are opt-in only: 5 real-release tests (`SPOT_STAGE2_RELEASE_TESTS` unset) + 1
pre-existing `pert2state_model` import skip.

---

## Where this started

An independent audit returned **NO-GO** on two blockers. Both are closed and re-audited
to a fresh **GO** (`~/.spot-runs/20260712T021343Z/DIRECT_CODEONLY_AUDIT_2.md`).

**P0 — determined evidence could be downgraded to ambiguous.** The lane checked
contributor *completeness* but took `evidence_state` itself on trust: an `ambiguous` label
was examined by nothing, on either side. Collapse one determined scope's rows to a single
ambiguous row, let the honest producer regenerate the records and report, and every count
balances, every hash is correct — while the raw source goes on holding that scope's kept
targeting guides. The victim silently loses its mask, score and rank.

The source now classifies, and only the source:

```
provable(scope) = { g : source kept a row for (target, condition), guide_type == TARGETING }
non-empty -> `determined` mandatory.   empty -> `ambiguous` is the only honest label.
```

Runtime derives it (`replay.py`); the standalone verifier restates it independently
(`verify_classification.py`). A fully resealed downgrade is invisible to every document
the producer wrote — *including the pinned report* — and is caught only by fresh strict
replay. That is why release lanes may not skip it, and there is now a test asserting the
non-strict verifier **passes** the forged run.

**P1 — P2S called the retired combined ranking API.** Fixed without restoring it.

The re-audit wrote 37 of its own attacks, reverted the fix and reproduced the mutation
counts, and found two defects of mine in the module splits (a `NameError` under
`get_type_hints`, seven dead imports). Both fixed; GO re-pinned to the new digest.

---

## What was built

### 1. Gate B — Stage-1 v3 selection adapter (`stage1_v3.py`)

Validates against the **pinned** schema (`f4c2c2cc…`, checked before use — a schema that
can be swapped validates whatever the swapper wanted). Routes `within_condition`; refuses
`temporal_cross_condition` as `awaiting_estimator`.

That refusal is the most important thing in the module. The two estimators answer
different questions, and the within-condition projection would happily consume a temporal
selection and return numbers. **The numbers would look exactly like an answer.** There
would be nothing wrong with them except that they answer a question nobody asked.

Generic by construction — no program id, no condition, asserted by an AST scan over
executable tokens. Both poles validated against the current effect universe; an
unavailable pole is refused with its *own* reason codes and counts, never summarised into
"failed". Combined Stage-1 objective refused. The historical selectability artifact is
provenance and can never become a live gate.

**Identifier hierarchy:** `selection_id -> stage2_run_id`, binding `direct_method_version`,
`direct_config_sha256`, `effect_universe_sha256`, `perturbation_source_hashes`,
`mask_method_version`, `pathway_method_version`.

45 mutation tests, each failing at a **named** gate.

### 2. Direct two-arm effects — confirmed, plus row identity

The screen already satisfied the two-arm contract. What it could not do was **describe
itself**: a row carried only `run_id`, so you had to join back to provenance before you
could say what produced it. Added, per row: `direct_method_version`,
`direct_config_sha256`, `effect_source_sha256`, `mask_method_version`, and
`estimate_mask_sha256` — *this* estimate's own masked gene set, null when unresolved (an
absent mask and an empty one are opposite claims).

The verifier re-derives all five, computing the config hash from its **own** restated
policy — so a run that loosened a threshold and honestly hashed the loosened policy is
caught by the row, not merely by the binding.

Screen is now 99 columns.

### 3. Pareto joint ordering (`pareto.py`, `spot.stage02.pareto.two_arm.v1`)

Pre-registered before any real ranking was inspected.

The requirement pulls against itself — an explicit joint ordering that does *not* erase
the components — and every easy way to satisfy the first violates the second. A weighted
sum, a mean, a balanced skew: any single number answering both arms must fix an exchange
rate between "moved away from A" and "moved toward B" that nobody has. Fix it wrongly, and
there is no way to fix it rightly, and a target that moves hard away from A while
**opposing B** outranks one that genuinely moves toward B.

Dominance needs no exchange rate. Tier 1 is the non-dominated frontier; peel and repeat.
A tier is an *order*, not a score: no units, not averageable, and two targets in one tier
are **incomparable**, not tied. Only jointly-evaluable targets are tiered; everything else
is `null` — not tier 0, not last, not a sentinel. `joint_status` is derived from the arm
*directions*, independently of the tier; deriving one from the other would make the pair
circular and destroy their only cross-check.

**How to read `joint_status` (corrected — M4).** `opposed` means **at least one evaluable
arm moved below `-sign_eps`**: the target was measured and it moves the wrong way. That
includes the bidirectional case (one arm favourable, the other opposing), which is the
same finding stated more strongly. `not_evaluable` means **no directional claim can be
made** — an arm that could not be scored (missing / non-finite / not evaluable), or two
arms that are both *neutral*, inside the sign tolerance and pointing nowhere.

Previously `away=-1,toward=-1` and `away=-1,toward=0` were labelled `not_evaluable`
although both arms had been scored. That merged a measured negative result into the
missing-data bucket, which is precisely where a reader stops looking. **This is a
label-only correction:** arm values, arm ranks and Pareto tiers are byte-identical —
`dominates()` reads the raw values and never the label.

The tier is the one field a downstream consumer has an obvious motive to rewrite — one
cell edit promotes a target to the frontier, breaks no arithmetic, contradicts no other
column. So `verify_pareto.py` **re-derives it from the emitted arm values**.

38 tests: dominance, exact ties, float-boundary (the next float above 1.0 is not a tie),
one-arm-missing, opposed-on-frontier, row-permutation invariance over all 120 orderings,
numeric combined-field injection (rejected), downstream tier-rewrite (rejected by name).
Both arms proven byte-identical with and without the joint fields, by building the run
twice with `assign_tiers` replaced by a no-op.

### 4. Pathway layer

Built on the **full target-masked perturbation signatures**, not the marker panels. That
distinction is the design: the panels *are* the axis the arms are scored on, so two
targets that both move the program agree on the panel **by construction** — agreement
there is close to circular.

- **(A) Ranked-arm enrichment** (`enrichment.py`) — a weighted running-sum statistic over
  one arm's ranking, with the **leading edge**: the members actually responsible. "Pathway
  P is enriched" is not checkable; "these six of its genes are the ones at the top" is.
  Once per arm, never summed across arms.

  **No p/q/FDR.** There is no calibrated null here, and permuting targets would test a
  hypothesis about the ranking's *shape* while producing a number that looks like a
  p-value and would be read as one within a week.

- **(B) Signature convergence** (`convergence.py`) — cosine on the **shared unmasked
  support**. Each signature has its own mask, so two targets have different holes, and the
  size of the intersection ships with every pair: a similarity over 11 shared genes is not
  the same claim as one over 11,000. Clusters are connected components over a frozen
  threshold — no seed, no k, no resolution, three knobs that would each be a place to tune
  the answer after seeing it.

  **A convergence claim requires ≥2 measured perturbations.** One target is one
  experiment, and calling it a pathway result launders an observation into a mechanism.
  Such sets are still emitted, flagged `single_target_support` — deleting them would hide
  how thin the evidence is. The rule is pinned in the schema, not only in the code.

Every set is emitted, including untestable ones, with a named reason: a pathway missing
from the table is indistinguishable from one that was tested and found nothing.

Gene sets are pinned (`source` + `release_id` + raw sha256 — "Reactome" is not a version),
namespace-enforced (a symbol-keyed set against an Ensembl universe overlaps in nothing,
and the "no enrichment" it returns is a failed join wearing a null result), and **bound to
the exact effect universe** the statistic is relative to. Parameterised by release +
universe, so the real Reactome/GO-BP bundle drops in unchanged.

Schema `stage02_pathway_record.v1`: `additionalProperties: false` throughout; typed Science
evidence refs `{science_evidence_id, sha256, record_type}` — free text is not a citation;
and **no primary-rank field may be written into a pathway record**. Claude Science may
interpret; an interpretation that can quietly edit its own evidence is not an
interpretation.

### 5. Perturb2State — `combined_A_to_B` resolved

P2S judged support on `combined_A_to_B`, which is `z(away) + z(toward)`: a combined
objective by another name. P2S never *ranked* with it, so neither audit flagged it — but it
was worse in one specific way. A single `perturb2state_support_status` cannot say **which
arm** it supports, and "supported" on a target whose support is entirely away-arm while its
toward arm is actively **opposed** is a sentence that means the opposite of what it looks
like.

Both remedies: support is **split** per arm (`perturb2state_away_from_A_*`,
`perturb2state_toward_B_*`, with an explicit per-arm `_opposed` flag — there is no unarmed
status left to misread), and the combined lane is **quarantined** as a reconstruction
diagnostic, excluded from the integration lane by name and carrying
`is_a_combined_objective: true` / `may_rank_or_gate: false` in the artifact itself.

Found on the way: the P2S lane was spelled `toward_b` (the **retired v2 casing**) while
Direct says `toward_B`. Nothing joined them, so nothing noticed — and the first code to
merge P2S onto the screen by lane name would have matched zero rows for that arm and
reported no support where support existed. Fixed and asserted.

---

## Honest boundaries — read these before the real run

1. **Gate B cannot re-derive `selection_id`.** The frozen contract does not publish
   Stage-1's derivation rule. Stage-2 carries it verbatim as a *citation* and keys its own
   results on `selection_biology_sha256` — the biology it actually read — so two different
   selections can never share a `stage2_run_id`. But a biology change that is fully
   resealed *and* leaves `selection_id` stale is correctly keyed by Stage-2 and **not
   flagged as stale**. Stage-1 publishing the derivation would close this. Recorded in the
   artifact as `selection_id_rule_id`.

2. **The `guide_type == "targeting"` assumption is untested against real data.** The entire
   P0 fix rests on that column meaning what we think it means in the real 44 GB source.

3. **The real 33,977 / 6 determined-ambiguous partition is untested.** If any of the 6
   released ambiguous scopes *does* have kept targeting guides, the run will refuse — and
   that would be a **finding**, not a bug.

4. **Strict replay is untested for tractability at 44 GB.** `source_provable_guides` is a
   Python loop over `np.flatnonzero(keep)`. Profile it before the first real run.

5. **The pathway thresholds are frozen but arbitrary.** `SIMILARITY_THRESHOLD = 0.5`,
   `MIN_SHARED_GENES = 10`, set sizes 3–500. They were frozen before any real signature was
   seen, which is the point — but they have not been sanity-checked against real data, and
   they should be reviewed *before* the run, not after.

6. **`STAGE2_PLAN.md` has no §7.6.** The pathway record was built to the field list given
   in the dispatch. If a newer plan exists, reconcile.

7. **Pre-existing mypy debt: 56 errors in 9 files** (`selection`, `trust`, `sources`,
   `manifest_validate`, `verify_source`, …), none of them mine. All 8 modules authored this
   session are mypy-clean. Cleaning the rest is a real task, not a lint pass.

8. **Ruff ceiling is 100 chars**, not the lane's ~88 house style — chosen so lint is
   genuinely clean without reflowing 27 lines of already-audited code. Stated in
   `ruff.toml`, not hidden.

---

## Commits (branch `agent/stage2-direct-v3`, not pushed)

```
fbd52d6  close audit P0 (evidence downgrade) + P1 (P2S two-arm), lint clean
082c933  Pareto joint ordering (pre-registered) + self-describing screen rows
089a321  resolve combined_A_to_B — support PER ARM, combined lane quarantined
646c201  pathway layer — per-arm enrichment + signature convergence, never fused
5ce2d98  Gate B — Stage-1 v3 selection adapter, generic, method-aware run id
```

## Next gated dispatch

Real tcefold run + content-addressed bundle freeze. Preconditions: methods freeze, the
pinned Reactome/GO-BP bundle, and an independent code-only GO on this build.
