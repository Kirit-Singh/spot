# Stage-2 — temporal cross-condition estimator (method)

`estimator_id: spot.stage02.temporal_cross_condition.v1`
`inference_status: not_calibrated` — no p, no q, no significance.
Code: `analysis/direct/temporal/`. Frozen policy: `analysis/direct/temporal/batch_policy.v1.json`.

This is the **descriptive cross-timepoint lane** the plan reserved (§18: "48→8h only as
descriptive sensitivity"), now with an explicit estimand, an explicit confound policy, and an
independent verifier. It is a strictly **additive layer** on top of the within-condition direct
screen: it computes one new quantity and writes its own artifact, and it cannot move a
within-condition score, rank, tier or `run_id`.

---

## 1. The estimand

For a target and an **ordered** condition pair (`from_condition → to_condition`), and for each
arm **independently**:

```
temporal_did(arm) = arm_value(arm, to_condition) − arm_value(arm, from_condition)
```

`arm_value` is **exactly** the within-condition Stage-2 arm value — the masked program
projection `delta_p(X) = mean(P_p \ M_X) − mean(C_p \ M_X)`, scored by the same
`run_screen.condition_rows` pass that produces `screen.parquet`. Both endpoints are recomputed by
that one code path; nothing is re-fitted, re-scaled or re-derived here.

The within-condition arm value is already a difference (panel mean − control mean, after the
estimate's own contributor mask). The cross-condition difference of two such values is therefore
a **difference-in-differences**.

### What it is

A change in a **population-level program projection** between two condition populations.

### What it is **not**

It is **not** lineage tracing, **not** fate mapping, **not** a per-cell transition probability,
and **not** a rate. No cell is followed from one condition to the next — the release fits each
culture condition as a **separate cell population**. A reader who takes this for a trajectory has
been misled, so the estimator emits no rate, no velocity, no slope and no elapsed time, and there
is no function in the subpackage that could produce one (enforced by
`test_temporal_estimand.py::TestTheEstimandIsNotAFateClaim`).

Both arms (`away_from_A`, `toward_B`) stay separate end to end, exactly as within-condition:
there is **no combined temporal objective**, no averaged DiD and no headline temporal rank. The
verifier refuses any column that looks like one.

### Coverage

**All six directed comparisons** over {Rest, Stim8hr, Stim48hr} — `Rest↔Stim8hr`,
`Rest↔Stim48hr`, `Stim8hr↔Stim48hr`, both directions each. **None is refused.** A confounded
comparison is flagged and badged, never withheld: suppressing it would hide the confound instead
of reporting it, and nobody can audit a comparison that was never written down.

---

## 2. The batch confound policy

Locked from the batch diagnostic
`~/.spot-runs/20260712T021343Z/temporal-batch-diagnostic/` (`REPORT.md`, sha256
`9f1146211f50…`; verdict **MODERATE**). The measured composition table and every statistic below
are pinned in `batch_policy.v1.json` with the diagnostic's hashes; nothing is re-typed by hand.

### The design

| condition | replicate | donors |
|---|---|---|
| Rest | R1 / R2 | R1={D1,D2}, R2={D3,D4} |
| Stim8hr | R1 / R2 | R1={D1,D2}, R2={D3,D4} |
| Stim48hr | **R2 only** | all four donors |

Batch is **perfectly aliased with donor** in every condition. Stim48hr is single-batch.

### The additive batch effect: negligible, and it cancels

The replicate main effect explains **0.12–0.42 %** of program-projection variance
(`fvar_replicate_main` 0.0012–0.0042), is **sign-inconsistent** across programs, and **cancels in
a difference-of-differences** regardless. **No correction is applied**, and
`batch_correction_applied` is `false` on every record.

### The flag is derived, not declared

The policy ships the measured donor→replicate composition; the code **derives** the flag:

> a pair is `batch_partially_confounded` **exactly when at least one donor sits in a different
> replicate at the two endpoints.**

When every donor keeps its replicate, the batch offset attaches to the same donors at both
endpoints and cancels in the DiD. This derivation reproduces the locked verdict without the code
ever naming a condition, so a release with a different design gets a correct answer rather than a
stale allowlist:

- **`Rest ↔ Stim8hr` — CLEAN.** Identical batch+donor composition at both endpoints; every donor
  keeps its replicate; time is not confounded with batch. `batch_status =
  batch_balanced_identical_composition`. Surfaced normally.
- **Any `Stim48hr` pair — `batch_partially_confounded`.** D1 and D2 flip R1→R2; D3 and D4 do not.
  Time is confounded with batch on 2 of 4 donors. The record names exactly which donors moved
  (`donors_changing_replicate = "D1;D2"`) and which did not.

### What could not be estimated

A **pure batch effect** — and a pure batch×perturbation interaction separated from donor — is
**not identifiable** in this design. Batch is aliased 1:1 with the {D1,D2}-vs-{D3,D4} donor split,
and Stim48hr carries no batch contrast at all. There is no R1 Stim48hr, so the batch bias on the
Stim48hr endpoint **can never be measured directly, only bounded** by transfer from Rest/Stim8hr.
More cells would not fix this. Every record carries this note
(`not_identifiable_quantity` / `not_identifiable_reason`).

---

## 3. The reliability threshold

The batch×perturbation interaction does **not bias** the DiD (it is donor noise, symmetric across
shared donors), but its **noise floor is large relative to the temporal signal** — 0.6×–2.0× the
temporal DiD signal std. Per-target Stim48hr calls are therefore **fragile**, and the estimator
says so in machine fields rather than leaving a reader to assume precision it does not have.

Per arm, from that arm's **own program**:

```
reliability_threshold = k × interaction_std(program),      k = 2.0   (frozen before any result)
badge = above_interaction_floor   iff  |temporal_did| ≥ reliability_threshold
        within_interaction_floor  otherwise
```

`interaction_std` is the per-program **batch-aligned split** (`split1_batchAligned`, Rest)
interaction spread from the diagnostic — the split that actually carries the batch contrast:

| program | interaction_std | threshold (k=2) |
|---|---|---|
| diff_naive | 0.157 | 0.314 |
| diff_activated | 0.227 | 0.454 |
| diff_memory | 0.082 | 0.163 |
| diff_checkpoint | 0.471 | 0.942 |
| treg_like | 0.357 | 0.714 |
| cd4_ctl_like | 0.756 | 1.512 |
| th1_like | 0.229 | 0.459 |
| th2_like | 0.491 | 0.982 |
| th17_like | 0.435 | 0.869 |
| tfh_like | 0.412 | 0.823 |

The badge is a **precision statement, not a significance test** (`inference_status =
not_calibrated`, `reliability_is_a_significance_test = false`). The **exact threshold, the exact
k, the comparator and the raw ratio ship on every record**, so a consumer can re-derive the badge
instead of trusting it. A program with **no measured floor** gets
`interaction_floor_unavailable_for_program` — an unmeasured floor is never a cleared one.

**Extra-caution programs.** `th17_like`, `th2_like`, `tfh_like` have sparse effective panels and
near-zero cross-half reproducibility (r ≈ 0.0–0.15); `th9_like` is not stage-2 selectable and is
listed so it cannot re-enter unflagged. Records carry `sparse_panel_caution`.

---

## 4. Display policy — METHODS-ONLY

The batch flag and the reliability badge are **machine fields for provenance and methods
traceability**. They are **not a UI display**.

- The UI shows **all comparisons plainly**. Nothing is hidden, filtered or suppressed.
- **No inline batch flags. No per-comparison reliability badges.** No caveat in the main canvas.
- The 48-hour batch confound and the precision limitation are documented **once — here** — and
  surfaced through the **methods/provenance drawer**, per the editorial policy that limitations
  live in the drawer, never as a per-row caveat.

This is bound into the method hash (`ui_renders_inline_batch_flag: false`,
`ui_hard_filters_confounded_pairs: false`, `ui_shows_all_comparisons: true`), so a run that
started hiding comparisons could not keep the estimator's identity.

---

## 5. What each record carries

One row per **(target, ordered condition pair)** in `temporal.parquet`:

- both arms' **values at each endpoint**, and the **DiD** per arm;
- each arm's **own rank at each endpoint**, over that endpoint's own population;
- each endpoint's **`joint_status` and `pareto_tier`**;
- the **donor and guide denominators at each condition** (support is unavailable in this release
  pass — enumerated, never projected);
- **`batch_partially_confounded`** + the typed `batch_status` + which donors moved;
- the **reliability badge, the exact threshold, k, and the ratio**, per arm;
- the **not-identifiable note**;
- `inference_status = not_calibrated` and the reason.

Also emitted: `endpoints.parquet` (the within-condition rows both endpoints came from),
`temporal_provenance.json`, `temporal_verification.json`.

---

## 6. Additivity, and how it is enforced

`code_tree_sha256` lists only the `.py` files **directly** in the direct package directory, so
the `temporal` **subpackage is invisible to it**. The dependency is one-way — nothing in `direct`
imports `direct.temporal`. Therefore **no temporal code can move a within-condition `run_id`,
score, rank or tier.** This is asserted structurally *and* numerically
(`test_temporal_invariance.py`), against a golden hash of the within-condition screen captured
**before** any temporal code existed.

The temporal run has **its own** id and **its own** method hash, which binds the within-condition
method, both code trees, the frozen batch policy, k, and the display policy.

> **Note on `run_id`.** Extracting the shared within-condition pass edited `run_screen.py`, so the
> direct **`code_tree_sha256` — and hence `run_id` — changed by design**: the run binding covers
> the code that produced it. Every *scientific* value is byte-identical (golden screen-content
> hash `e9b72535…` and mask hash `f3eea380…` both unchanged), which is the invariant that matters
> and the one the test pins.

## 7. Verification (generator ≠ verifier)

`verify_temporal.py` reads the shipped bytes back off disk and re-derives, from them alone: every
DiD from the endpoint values; every temporal status; every badge and threshold from the frozen
policy; every batch verdict from the composition table; the **antisymmetry** of the whole artifact
(reversing a pair must negate it exactly); that no combined objective and no p/q appeared; and
that **the endpoints are the within-condition values**. Thirteen mutation tests
(`test_temporal_verifier.py`) corrupt one claim each and require the owning check to fail — a
verifier that only ever passes is a rubber stamp.

**Tests: 86** (estimand 17, policy 19, run 26, invariance 11, verifier 13).
