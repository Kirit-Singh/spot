# Perturb2State SECONDARY adapter — the v2 reusable-arm lane

Status: APPROVED, frozen. 2026-07-13.
Package: `02_geneskew/analysis/p2s_arms/` · Tests: `02_geneskew/tests/p2s_arms/`

---

## 1. What this is

A **secondary, non-gating** reconstruction-support lane for the round-4 reusable-arm
system. It consumes ONE independently admitted reusable Direct arm, identified by

    direct | program_id | desired_change | condition

and emits reconstruction-support evidence keyed by that arm. It is not part of
"complete Stage-2" (= Direct + Pareto + temporal + pathway), it cannot gate that set,
and it cannot alter it.

`lane_role = secondary_non_gating`. The artifact says so in its own bytes.

### What it may do
* add reconstruction-support evidence for each reusable arm **separately**;
* flag negative/**opposed** coefficients, and keep them opposed.

### What it may not do
* promote, demote, rescue, admit, gate, reorder, or re-rank any Direct target;
* validate a Direct result merely by agreeing with it;
* enter a combined / balanced / weighted objective, or emit a composite rank;
* emit any p / q / FDR / significance quantity;
* claim temporal DiD, fate, lineage, or per-cell tracking;
* alter Direct's arm values, ranks, or `arm_rows_sha256`.

---

## 2. The legacy lane, and why v2 does not build on it

`02_geneskew/analysis/perturb2state/` is the pair-bound v1 lane. It is **preserved
byte-for-byte** and v2 imports nothing from it.

The pair binding in v1 is not cosmetic — it is in the science. `config.py:43`:

    mean_expr_g ~ 1 + z_A + z_B + activation + donor(K-1)

Both programs' scores are covariates in ONE fit, and the away/toward signatures are read
off `z_A`/`z_B`. An arm computed this way depends on **which other program shared the
model**, so the same `arm_key` would carry different values depending on the pair that
requested it — cached, and served interchangeably by the UI. That is precisely the failure
`direct/arm_keys.py` exists to prevent.

Three further reasons v2 does not import v1:

* `stability.integration_lane` hard-raises on any lane outside `config.LANES`, and that
  refusal is a tested behaviour — v2's arm keys would raise;
* `model_runner` reads the legacy config's seed and grid, so v2 could not own its own pin;
* `run_p2s.build()` is already dead at `run_p2s.py:180` — `direct.io_data.load_registry`
  returns a 4-key dict and it is unpacked into 3 names. No test calls `build()`, so nothing
  caught it. **v2 does not fix this** (that would modify a frozen lane); it is reported
  upward instead.

The genuinely reusable numerics are ~30 lines of masked-matrix construction. v2
re-implements them and stays self-contained, so the frozen lane can eventually be retired.

---

## 3. The one primitive

P2S v2 computes exactly one thing: **reconstruction support for a within-condition Direct
arm**. Everything else is a join performed by the consumer.

### 3.1 The base signature — per program, never per pair

Per `(program P, condition C)`, over pseudobulk units:

    2-D quantile pseudobulk grid, per donor:  (z_P decile) x (activation decile)
                                              = 10 x 10 = 100 units/donor

    design:   mean_expr_g ~ 1 + z_P + activation + donor(K-1 dummies)
    weights:  n_cells_unit
    solved:   lstsq on sqrt(W)*D and sqrt(W)*Y     — NEVER the normal equations

    base_sig(P, C) = the fitted coefficient on z_P, per gene,
                     z-scored across the readout gene universe

Binning is on **exactly the axes that are regressed on**. Legacy binned on `(z_A, z_B)`
because those were its two regressors; v2's regressors are `(z_P, activation)`, so it bins
on those. Binning on `z_P` alone would average activation away inside each bin and strip
the covariate of the leverage it exists to have — the confound would leak back into
`beta_P`.

Stage-1 v3 scores are **read by barcode**, never silently recomputed.

### 3.2 The arm target — one fit, two arms

    y(direct|P|increase|C) = +base_sig(P, C)
    y(direct|P|decrease|C) = -base_sig(P, C)

ONE fit, on `increase`. The `decrease` arm is the **exact negation** of its coefficients,
not a re-estimate — so the two arms of a program in a condition cannot disagree about a
magnitude they share. This mirrors `direct/arm_bundle.py`'s doctrine.

It is valid here because the ElasticNet objective is symmetric in `b` (`positive=False` is
required and enforced): substituting `y -> -y, b -> -b` leaves the loss and both penalty
terms unchanged, so the minimiser is exactly `-b*`, the CV-selected alpha is the same, and
the reconstruction metrics are sign-invariant and therefore identical. `support_status`
flips `supported <-> opposed`.

**The sign transform is local to `p2s_arms`.** It has its own quantity name
(`p2s_base_coefficient`) and does NOT extend `direct.arm_keys.SIGN_TRANSFORM_APPLIES_TO` —
that tuple is emitted inside Direct's hashed `method_block()`, so adding to it would change
Direct's bytes.

### 3.3 The reconstruction

    beta = ElasticNet(y ~ P_matrix)

`P_matrix` = genes x eligible perturbation targets, masked coordinates set to 0. Only
direct-screen ELIGIBLE targets become columns. Target, panel and control genes are excluded
from the readout and gene-CV universe, and the universe is hashed.

`beta` are **conditional reconstruction weights**. They are not p-values, not standard
errors, not causal effects, and not validation. `coef_sem` from the upstream model is
emitted as `coef_fit_variation` and is fit variation, not inference. Gene-fold CV is
labelled `reconstruction_gene_cv` and never donor / guide / holdout / external validation.

### 3.4 Temporal endpoints — absent by construction

A `temporal_cross_condition` question's endpoints resolve to two Direct arm keys that
already exist:

    temporal|P|increase|Stim8hr|Stim48hr
       endpoint @from  ->  direct|P|increase|Stim8hr
       endpoint @to    ->  direct|P|increase|Stim48hr

The consumer joins them. **P2S emits no temporal artifact at all.** A DiD claim requires a
field that is a function of both endpoints; no artifact exists in which to write one. This
is absence by construction, not a prohibition enforced by a check. The verifier proves the
negative it can actually prove: no emitted key is keyed on an ordered condition pair.

P2S never validates or reorders the primary temporal gene ranks.

---

## 4. Bindings — what a run must bind

| Bound thing | Source | Refusal on mismatch |
|---|---|---|
| Admitted program set | `base_portable` on the bound Stage-1 v3 release / scorer view | derived, never copied; never from a legacy registry |
| Th9 | excluded — the release says non-portable | `Th9RefusedError` |
| actadj / sensitivity poles, research namespaces | refused by the Stage-1 firewall | refuse |
| The arm | must appear in the bound all-arm bundle's manifest | `ArmMismatchError` |
| `scorer_view_sha256` | bundle's must equal the one derived from the bound release | `ScorerMismatchError` |
| `arm_rows_sha256` | recomputed from `arms.parquet` must equal the bundle's claim | `AlteredRankError` |
| The all-arm verifier report | verdict must be ADMIT | refuse |
| Upstream model | `emdann/pert2state_model`, commit `2c2e3095…`, MIT, version `0.0.1` | `UpstreamDriftError` |

The 10 admitted programs are `diff_naive, diff_activated, diff_memory, diff_checkpoint,
treg_like, cd4_ctl_like, th1_like, th2_like, th17_like, tfh_like` — **derived**, never
hard-coded as a count.

The **LOMO 0/33 selectability result is descriptive evidence about single-marker dependence,
not a production blocker.** It does not suppress a base-portable arm. It is separately
traceable downstream. There is no `production_eligible` field.

### Upstream identity is resolved at RUNTIME, not echoed

The run resolves the module's source path, its git commit, package version, source-tree
content hash, and the environment lock, and **refuses on any mismatch**. It emits the
commit, version and tree hash — and **never a machine-local path**.

---

## 5. Strictly secondary — the invariant, stated exactly

**PROVEN AND TESTED:** at one frozen integrated commit, executing or omitting the P2S lane
leaves every Direct / temporal / pathway artifact byte-identical, including run ids and
ranks. This holds structurally: P2S writes only into its own output directory, no module
under `analysis/direct/` imports `p2s_arms`, and v2 changes zero bytes under
`analysis/direct/`.

**NOT CLAIMED:** that adding the P2S source files leaves Direct's content-addressed run id
unchanged. It does not, and it should not.

`direct/code_digest.py` digests **every `.py` and `.json` under `02_geneskew/`**, and that
digest flows: `code_identity` -> `run_binding` -> `bundle_run_id = sha256(binding)[:16]`,
which is stamped into `arms.parquet` (every row), into `arm_bundle.json`, and into the
output directory name. So new source files legitimately move the repository code digest and
therefore the run id. The code tree changed; the digest says so. Hiding that would be the
defect, not the fix.

What is invariant under the digest change is the **science**: `arm_rows_sha256` is computed
over `canonical_rows()`, whose explicit 14-key projection excludes `arm_bundle_run_id`. Arm
values, arm ranks and `arm_rows_sha256` do not move.

**Consequence for W1:** integrate P2S **before** the final commit is frozen and before the
real Direct run, so there is exactly one run-id generation. Pre-merge and post-merge run ids
are not claimed identical.

---

## 6. Output — content-addressed, keyed by arm_key

Written to `<out_root>/<p2s_run_id>/`, atomic, never overwritten by biology id.

| File | Contents |
|---|---|
| `p2s_arm_support.parquet` | THE consumer table: one row per (arm_key, target) |
| `p2s_coefficients.parquet` | per (arm_key, run, target) reconstruction weight |
| `p2s_reconstruction.parquet` | per (arm_key, run) gene-CV reconstruction metrics |
| `p2s_support.json` | the bundle document: method, bindings, counts, content hashes |
| `p2s_provenance.json` | run binding, upstream identity, env, UTC run time, argv |

`p2s_arm_support.parquet` columns, per arm_key:

    arm_key, program_id, desired_change, condition, target_id,
    selection_frequency, positive_frequency, negative_frequency,
    median_coefficient, coefficient_min, coefficient_max,
    lodo_sign_agreement, effect_layer_agreement,
    support_status, opposed

`support_status` in `{p2s_supported, p2s_opposed, p2s_mixed, p2s_weak, p2s_not_selected}`.
Selected = nonzero-selection frequency >= 0.50; sign-dominant = >= 0.75 of selected runs.

**No rank column is emitted anywhere.** That removes the surface on which P2S could reorder
anything. Zero coefficients never disappear from coverage; a nonzero-of-few never renders as
1.0 without its denominator; overlapping donor-pair / LODO estimates are never called
independent replicates.

**Missing stays missing, never zero.** A program with no surviving panel genes, or an
unresolved Direct estimate, yields a refused arm — not a reconstruction of zeros.

### Field-name firewall

Every emitted key, at any depth, is checked against the round-4 firewall:

    p_value|q_value|q_val|qval|fdr|pval|padj|adj_|significance
    |combined|balanced|weighted|score        (+ a standalone p or q token)

This kills a legacy name: `logfc_zscore_agreement` contains **"score"** and is renamed
`effect_layer_agreement`.

Exempt only while they still say `false` — the negative declarations:

    combined_objective_permitted:        false
    p2s_may_rank_or_gate:                false
    coefficients_are_causal_effects:     false
    coefficients_are_significance_tests: false

No machine-local paths. No private data. Public sources only.

---

## 7. The independent verifier

`verify_p2s_arms.py`. Typed, fail-closed, ADMIT/REJECT. It imports **nothing** from
`p2s_arms` and nothing from `direct`. It loads the shipped bytes off disk — never a caller's
dict — and reimplements, from the written spec:

* its own content hash (not the generator's helper);
* the arm-key grammar, and the frozen role x pole -> desired_change mapping, **re-derived**;
* the support-status rule;
* its own copy of the key-name firewall and the negative declarations;
* an exact column allowlist per emitted file — so a rank or gate column is rejected by
  absence from the allowlist, not merely by name.

A verifier that imported the generator's rules would agree with it by construction.

---

## 8. Determinism and the model pin

    seed              = 42                    (deterministic wrapper)
    positive          = False                 (REQUIRED: a negative coefficient is the
                                               INVERSE of the measured knockdown = OPPOSED)
    l1_ratio grid     validated: every entry in [0, 1], else refuse
    alpha grid        frozen before unblinding, on compute + sparsity grounds only
    n_splits          = 5   gene-fold CV
    n_repeats         = 1
    configs           pca_off, pca_on_50

Two runs at seed 42 produce byte-identical coefficients. A changed seed is recorded and
changes the run id.

Hashes captured: model (upstream commit + source-tree hash), environment lock, every input,
the gene universe, the code identity, and the run's UTC time.

---

## 9. Tests

Deterministic logic is tested; IO is smoke-or-skip. Fixtures are **clearly synthetic** —
planted contributors, fake `ENSG…` ids, `lane = synthetic`. No real model run until W1
supplies the final admitted bundles.

### The 10 mutations

| # | Mutation | Expected |
|---|---|---|
| 1 | arm_key absent from the bound bundle | refuse |
| 2 | bundle `scorer_view_sha256` != derived from the bound release | refuse |
| 3 | planted negative contributor | stays `p2s_opposed`; never converted to support, never dropped |
| 4 | program with no surviving panel | arm refused — missing stays missing, never zero |
| 5 | a rank tampered in `arms.parquet` | recomputed `arm_rows_sha256` != claim -> refuse |
| 6 | any rank / gate / promotion field emitted | verifier REJECT |
| 7 | upstream commit / version / tree-hash drift | refuse |
| 8 | two runs at seed 42 | byte-identical coefficients |
| 9 | numerical non-regression over canonical Direct arm rows/ranks | unchanged |
| 10 | same commit, P2S executed vs omitted | Direct artifacts byte-identical |

Plus a **static** test: no module under `analysis/direct/` imports `p2s_arms`.

---

## 10. Real run

Real compute runs on **tcefold**, never tcedirector: tcedirector reads
`GWCD4i.DE_stats.h5ad` non-deterministically (stable mtime/size, differing sha on re-read),
while tcefold is stable at the pin `c355f535`. The run binds that pin and its integrity gate
refuses any non-pin.

The exact tcefold command ships with the handoff. No real run until W1 supplies the final
admitted bundles.
