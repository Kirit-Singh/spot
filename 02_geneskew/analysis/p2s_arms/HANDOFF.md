# P2S v2 reusable-arm SECONDARY lane — handoff to W1 / W12 / W16

Branch `agent/stage2-p2s-arms`. Package `02_geneskew/analysis/p2s_arms/`.
Spec: `docs/superpowers/specs/2026-07-13-p2s-arms-secondary-adapter-design.md`.

`lane_role = secondary_non_gating`, and the artifact says so in its own bytes.

**Zero bytes changed under `analysis/direct/`.** The legacy pair-bound lane
(`analysis/perturb2state/`) is preserved untouched and still passes. Full Stage-2 suite:
**1661 passed, 9 skipped**.

---

## 1. What it does

Reconstruction support for ONE independently admitted reusable Direct arm:

    direct | program_id | desired_change | condition

There is no A/B pair anywhere. **A within-condition pair is a JOIN of two independently
computed support lanes**, done by the consumer.

The pair binding in v1 was in the *science*, not the output names: it fitted
`mean_expr_g ~ 1 + z_A + z_B + activation + donor` — **both** programs in one model — so an
arm's value depended on which other program shared the fit. The same `arm_key` would carry
one value in the treg/th1 pair and another in treg/th17, cached and served interchangeably.
v2 refits per program:

    mean_expr_g ~ 1 + z_program + activation + donor(K-1)      WLS, weight = n_cells
                                                               lstsq on sqrt(W)D, sqrt(W)Y
    2-D pseudobulk grid on (z_program, activation) — the axes that are regressed on

ONE fit per (program, condition). `increase` is the fit; `decrease` is its **exact
negation** — one measurement and a sign, so the two arms cannot disagree about a magnitude
they share. `support_status` therefore flips `supported <-> opposed` between the arms; both
are stated, and **neither may ever be fused**.

**Temporal**: P2S emits **no temporal artifact at all**. A temporal question's endpoints
resolve to two *Direct* arm keys that already exist, and the consumer joins them. A DiD
claim needs a field that is a function of both endpoints — there is no file in which to
write one. `armref.parse` refuses a temporal or pathway key **by name**.

---

## 2. → W1 (Direct all-arm producer) — **one scheduling requirement, please read**

### What P2S consumes, and refuses

| Bound | Source | Refusal |
|---|---|---|
| Admitted programs | `base_portable` on the bound Stage-1 v3 release, via `direct.scorer_view.view` | derived, never a copied count; Th9 excluded because the release says so |
| The arm | must appear in `arm_bundle.json`'s `arms[]` manifest | `ArmMismatchError` |
| Scorer view | bundle's `method.scorer_view_sha256` == the one re-derived from the bound release | `ScorerMismatchError` |
| Arm rows | `arm_rows_sha256` **recomputed** from the shipped `arms.parquet` == the bundle's claim | `AlteredRankError` |
| Verifier report | `verdict == "admit"` | `VerifierRejectedError` |

P2S reads `arm_bundle.json` + `arms.parquet` from the bundle directory — the **real** files
`run_arms.py` writes. (v1's reviewer returned `conditional_not_mergeable` because "Perturb2State
cannot read a single artifact the direct lane actually produces"; its tests were green against
a *fictional* bundle. The v2 fixtures build the bundle through `direct.arm_bundle.build`, so
if your bundle shape moves, our tests break — which is what we want.)

### THE SCHEDULING REQUIREMENT

**Integrate P2S before you freeze the final commit and before the real Direct run.**

`direct/code_digest.py` digests **every `.py` and `.json` under `02_geneskew/`**, and that
flows straight into your run id:

    code_identity -> run_binding -> bundle_run_id = sha256(binding)[:16]

which is stamped into **`arms.parquet`** (every row), **`arm_bundle.json`**, and the
**output directory name**. So landing this lane's source files *does* move
`arm_bundle_run_id`. That is the digest working correctly — the code tree changed.

* **We prove:** at one frozen commit, *executing* vs *omitting* the P2S lane leaves every
  Direct artifact byte-identical, run ids included.
* **We do not claim:** pre-merge and post-merge run ids are identical. They are not.

What is invariant across the digest change is the **science**: `arm_rows_sha256` is taken
over `canonical_rows()`, whose explicit 14-key projection excludes `arm_bundle_run_id`. Arm
values and ranks do not move. We test this row-by-row and rank-by-rank, not just by file hash.

→ **Freeze once, with P2S already in the tree.** Otherwise the run ids shift under you when
it lands.

### One defect found in your neighbourhood (not fixed here — it is your lane)

There is **no independent verifier for the all-arm bundle yet**. `arm_bundle.json` is touched
only by `arm_bundle.py` and `run_arms.py`. P2S *requires* a verifier report with
`verdict == "admit"` and will refuse without one. Whatever emits it, please give it a
`verifier_id` and a `report_sha256`.

---

## 3. → W12 (verification)

`analysis/p2s_arms/verify_p2s_arms.py` — typed, fail-closed, `admit`/`reject`, exit 0/1.

    python -m p2s_arms.verify_p2s_arms --out-dir <p2s run dir> [--report out.json]

It **imports nothing** from `p2s_arms` and **nothing** from `direct` (asserted by a test). It
reads the shipped bytes off disk — never a caller's dict — and reimplements from the written
spec: its own canonical hash, the arm-key grammar, the frozen role×pole→desired_change
mapping, the support-status rule, the key-name firewall, and an **exact column allowlist per
file**. A rank or gate column is rejected by *absence from the allowlist*, not by a name rule
that would have to guess what it was called.

It re-derives the **sign-transform law**: if `increase` and `decrease` coefficients are not
exact negations, someone re-fitted the second arm, and the two can now disagree.

**The firewall is real and it bit us.** It refuses
`p_value|q_value|q_val|qval|fdr|pval|padj|adj_|significance|combined|balanced|weighted|score`
plus a standalone `p`/`q` token, at any depth. It caught two names during development:

* legacy's `logfc_zscore_agreement` — contains **"score"** → renamed `effect_layer_agreement`;
* our own `scores_are_read_not_recomputed` → renamed `stage1_values_read_by_barcode_never_recomputed`.

Only `scorer_view_sha256` / `scorer_view_id` are exempt, by exact spelling, because they are
Direct's own field names for the admitted-program view and renaming them would break the join.
Negative declarations (`combined_objective_permitted`, `p2s_may_rank_or_gate`,
`coefficients_are_causal_effects`, `coefficients_are_significance_tests`, `temporal_did_claimed`,
`validates_direct_by_agreement`) are exempt **only while they still say `false`**.

**No `production_eligible` field.** The historical 0/33 LOMO selectability result is
descriptive evidence about single-marker dependence, not a production gate; a field pinned to
it would read as one. The lane binds `base_portable` and `lane_role` instead, and a verifier
check asserts `production_eligible` is absent. Any LOMO diagnostic stays separately traceable.

---

## 4. → W16 (UI) — the fixture, and what may be shown

### The fixture (synthetic data, REAL artifact, verifier-ADMITTED)

    /home/tcelab/.spot-runs/20260713T-p2s-arms/ui-fixture/e732f1c551f91e2f/

Regenerate anywhere, deterministically (seed 42):

    cd 02_geneskew/analysis
    python -m p2s_arms.make_ui_fixture --out-root <dir outside every tracked tree>

Six files; `p2s_verification.json` carries `verdict: admit` from the independent verifier. It
is **not** committed — it is a generated artifact, and `outputs/` is gitignored by design.

### `p2s_arm_support.parquet` — the table to render

```
arm_key  program_id  desired_change  condition  target_id
n_runs  n_selected_runs  selection_frequency  positive_frequency  negative_frequency
median_coefficient  coefficient_min  coefficient_max
lodo_sign_agreement  n_lodo_runs  effect_layer_agreement  n_effect_layers
support_status  opposed
```

`support_status ∈ {p2s_supported, p2s_opposed, p2s_mixed, p2s_weak, p2s_not_selected}`.

**There is no rank column, in any file.** A lane with no rank column has no surface on which
to reorder anything.

### Rules for the panel

* **Key by `arm_key`.** Never by a role or a pole. Never `away_from_A` / `toward_B`.
* **Always show the denominator.** `selection_frequency` without `n_runs` turns
  one-nonzero-of-eight into a flawless `1.0`.
* **A target SUPPORTED on one arm and OPPOSED on the other is not a contradiction** — it is
  the sign transform, and it is the normal case. Show both as they are; never fuse them.
  In the fixture, `T00` is `p2s_supported` on `increase` and `p2s_opposed` on `decrease`.
* **`lodo_sign_agreement` is not replication.** LODO fits overlap; they are not independent
  replicates, and `null` means no evidence, not perfect agreement.
* **Never** rank, gate, promote, demote, or filter a Direct target by this. Never present
  agreement with Direct as *validating* Direct.
* Coefficients are **conditional reconstruction weights** — not p-values, not standard
  errors, not causal effects. `coef_fit_variation` is fit variation, not inference.
* A temporal question's endpoint support is **two Direct arm-support lanes**, joined by you
  and labelled as endpoints. There is no temporal P2S artifact, and no DiD.

---

## 5. The real run — tcefold ONLY

Real compute runs on **tcefold**, never tcedirector: tcedirector reads
`GWCD4i.DE_stats.h5ad` **non-deterministically** (stable mtime/size, differing sha256 on
re-read: `c355f535` → `dc503816`), while tcefold is stable at the pin `c355f535`. A run whose
inputs hash differently on two reads cannot be content-addressed at all.

**Not yet runnable: it needs W1's final admitted bundles.** When they exist:

```bash
ssh tcefold
cd ~/spot/02_geneskew/analysis
source /home/tcelab/spot_stage2/venv/bin/activate     # the pinned env

# 0. prepare the cell matrix ONCE per condition (h5ad -> npz; scores READ BY BARCODE)
#    required arrays: barcodes, donors, gene_ids, expr, score__<program_id> ...

# 1. one arm (its sibling comes free — one fit, two arms)
python -m p2s_arms.run_p2s_arms \
  --arm-key 'direct|treg_like|increase|Stim48hr' \
  --bundle-dir   <W1's ADMITTED all-arm bundle dir for Stim48hr> \
  --verifier-report <that bundle's independent verifier report .json> \
  --stage1-release  <the bound v3 release manifest> \
  --release-kind production \
  --cells    <prepared cells.npz> \
  --effects  <effects.parquet> \
  --masks    <the Direct lane's masks.parquet> \
  --eligible <eligible.parquet> \
  --upstream-tree-sha256 <pin, once recorded from the verified checkout> \
  --env-lock <the Linux env lock> \
  --lane production \
  --out-root /home/tcelab/.spot-runs/<ts>/p2s-arms      # OUTSIDE every tracked tree

# 2. generator != verifier
python -m p2s_arms.verify_p2s_arms --out-dir <run dir> --report <run dir>/p2s_verification.json
```

The upstream pin (`emdann/pert2state_model` @ `2c2e3095…`, MIT, `0.0.1`) is **resolved at
runtime** — module path, git commit, package version, source-tree content hash, dirty-tree
check — and the run **refuses on any mismatch**. The tree hash catches what a commit id
cannot: a file **edited** under a pinned commit. No machine-local path is ever emitted.

Grid per arm: `all_donor × {zscore, log_fc} × {pca_off, pca_on_50}` = 4 fits, plus one
LODO fit per donor. Seed 42; `positive=False` (required — it is what keeps opposed
contributors opposed *and* what makes the two arms an exact sign transform).

---

## 6. Test matrix — 99 passed, 2 skipped

The 10 contracted mutations, plus the static proof:

| # | Mutation | Result |
|---|---|---|
| 1 | arm_key absent from the bound bundle | refused |
| 2 | scorer-view mismatch (incl. same ids, different panels) | refused |
| 3 | planted negative contributor | stays `p2s_opposed`; never converted, never dropped |
| 4 | program with no surviving panel | refused — missing stays missing, never zero |
| 5 | a rank (or value) tampered in `arms.parquet` | refused via recomputed `arm_rows_sha256` |
| 6 | rank / gate / promotion column, or a forbidden statistic at any depth | verifier REJECT |
| 7 | upstream commit / version / **edited-file** / dirty-tree drift | refused |
| 8 | two runs at seed 42 | byte-identical coefficients |
| 9 | numerical non-regression over canonical Direct rows **and ranks** | unchanged |
| 10 | same commit, P2S executed vs omitted | Direct artifacts byte-identical |

Plus: no module under `analysis/direct/` imports `p2s_arms`; this branch changed zero bytes
under `analysis/direct/` (asserted against git); the verifier imports nothing from the
generator or from Direct; v2 emits no pair-named output; a **stand-in model may never run
outside the synthetic lane**; laundering an opposed target into support is rejected; breaking
the sign transform is rejected.

The 2 skips are the real upstream package (not installed on tcedirector — the real run is on
tcefold) and one git-topology guard.

---

## 7. Known defect in the frozen legacy lane (reported, NOT fixed)

`analysis/perturb2state/run_p2s.py:180` is **dead**:

```python
programs, reg_sha, reg = io_data.load_registry(args.registry)   # 3 names
```

`direct.io_data.load_registry` returns a **4-key dict**. Unpacking it into 3 names raises
`ValueError: too many values to unpack`. No test calls `build()`, so nothing caught it.
(`temporal_exploration/screen_th1_treg_temporal.py:10` has the identical stale unpack.)

Not fixed here: the lane is frozen for compatibility, and editing it would change bytes this
handoff promises are unchanged. v2 imports nothing from it, so v2 is unaffected.
