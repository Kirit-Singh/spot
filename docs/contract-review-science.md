<!-- Claude Science executed review (agentic, on tcedirector) of the
     spot_contracts Hit/Evidence schema, 2026-07-07. Findings were run
     against the real package + real Marson suppl-table columns, then
     adjudicated by Fable and applied. See contract-design-notes.md Rev 3. -->

# Adversarial review — spot Hit/Evidence contract (`spot_contracts` v0.1.0)

Scope: trustworthy cross-dataset confirmation + honest model→prioritization (a
prediction must never count as replication). Public data only; defensive target
discovery. Findings below are **executed against the real package**, not read off
the source.

## 0. Data status (what I could actually open)
- **Requested precomputed files ABSENT at the NAS path** `/mnt/.../marson2025_gwcd4_perturbseq/`:
  `GWCD4i.DE_stats.h5ad`, `GWCD4i.pseudobulk_merged.h5ad`, and `suppl_tables/` are not there.
- The five raw per-donor files that *are* there are **truncated mid-download** — HDF5
  superblock advertises ~140–156 GB but only 29–44 GB is on disk (all carry temp/hash
  suffixes like `.fD19681e`). `h5py.File(...)` raises "truncated file" on every one. Not usable.
- The **small supplementary CSVs are complete** at `~/projects/spot/.scratch/marson2025/suppl_tables/`:
  `DE_stats.suppl_table.csv` (33,983 rows), `sgrna_library_metadata.suppl_table.csv` (31,109),
  `sample_metadata.suppl_table.csv` (11 samples / donors×condition). Faithfulness checked against these.

## 1. Adversarial construction — edges the contract should forbid but accepts
Each row: I built the object; "ACCEPTED" = no guard fired.

| # | Attempted edge | Result |
|---|---|---|
| A | `replication` + `confirmed` whose `provenance.dataset_id` == the hit's own dataset, corroborating itself | **ACCEPTED — no independence guard** |
| B | A model output (`knowledge_level=prediction`, `agent_type=computational_model`) labeled `evidence_type=replication` + `verdict=confirmed` | **ACCEPTED — firewall bypassed** |
| C | `predictive` evidence with `weight=1.0` (design says "capped weight") | **ACCEPTED — no cap** |
| D | `confirmed`/`agree` whose attached `measurement` points the **opposite** direction to the hit | **ACCEPTED — measurement not reconciled to agreement** |
| E | `replication`/`confirmed`/`agree` where hit metric is `log2fc` but evidence `measurement` is `wald` (incomparable), opposite sign | **ACCEPTED — cross-metric not blocked** |
| F | Evidence carrying the context it was evaluated in | **`context` silently dropped — no such field on Evidence** |
| G | Unknown/misspelled field (`typo_field=…`); `schema_version="99.0.0"` ≠ hit's | **ACCEPTED, silently — `extra=ignore`, no version check** |

The one guard that *did* fire is the narrow one: `evidence_type=PREDICTIVE` + `verdict=CONFIRMED`
is rejected. Finding **B** shows that guard is one relabel away from useless.

## 2. Faithfulness to the real Marson columns
- **`ontarget_effect_size` is NOT log2fc.** Observed range **−58.5 … +7.09, median −6.3**
  (n=33,983). A log2FC of −58 = 2⁻⁵⁸ fold — biologically impossible. The column's metric is
  unpinned, yet nothing stops a producer setting `Metric.LOG2FC`; the signed-direction validator
  then happily accepts it and Lane A would compare magnitudes across datasets **as if** they were
  log2FC. This is the exact "incomparable metrics compared" failure the design says it prevents.
- **No p-value column exists** — only `ontarget_significant` (bool) and `ontarget_effect_category`
  (`no on-target KD` / `on-target KD` / `putative off-target`). `Measurement` has only
  `pval_raw/pval_adj` and `Selection.fdr_cutoff`; a boolean significance call and a 3-level effect
  category have no faithful home. They must be flattened into `Check`s, losing their native meaning.
- **Off-target has no first-class check.** `offtarget_flag` / "putative off-target" is the primary
  CRISPRi false-positive source, but `CheckName` has only `guide_efficiency`; off-target falls to
  `OTHER`. For a CRISPRi-seeded product that gate deserves to be named.
- **`perturbation_type` is optional and unset.** Every Marson hit is CRISPRi; the type that makes
  the effect interpretable is not required.
- **Within-dataset ≠ replication.** `DE_stats` is already merged across the 2 donors, so multi-donor
  agreement inside Marson is `consistency`; genuine `replication` needs a second dataset. Nothing in
  the contract prevents mislabeling within-Marson donor agreement as replication (ties to A).
- Faithful mappings that *do* hold: `n_cells_target`→`Measurement.n`+`n_type=cells`;
  `culture_condition`→`context.stimulus`+`context.timepoint`; Ensembl `target_contrast`→
  `Subject.id`; effect==0 / "no on-target KD"→`Direction.NONE`. `target_baseMean` has no home (minor).

## 3. Prioritized fixes

### BLOCKING (a prediction can count as replication / a hit can confirm itself)
1. **Independence is unenforced (finding A).** Add a validator: `replication`/`consistency` evidence
   must have `provenance.dataset_id` ≠ every corroborated hit's dataset, and `hit_id ∉ corroborating_hit_ids`.
   Independence is the definition of cross-dataset confirmation; today it is a convention only.
2. **Evidence-type firewall is bypassable (finding B).** Gate on the *source of truth*, not the label:
   if `agent_type=computational_model` **or** `knowledge_level=prediction`, forbid
   `evidence_type ∈ {replication, consistency}` and forbid `verdict=confirmed`. The current single
   check (`predictive`+`confirmed`) only blocks the honestly-labeled case.
3. **`direction_agreement` is a free-text claim (finding D).** When `measurement` is present, derive
   agreement from `measurement.direction` vs the hit's direction and reject a hand-set value that
   contradicts it — mirror the reconciliation already done inside `Hit`. Otherwise `confirmed/agree`
   can carry an opposite-sign measurement.
4. **Cross-metric confirmation unblocked (finding E) + `ontarget_effect_size` mislabel hazard (§2).**
   The contract must carry the hit's metric on the Evidence (or a `units_reconciled`/`metric_match`
   `Check` that is *required* for `confirmed`), so "compare only within matching metric" is
   structural, not a Lane-A promise. Immediately: map `ontarget_effect_size`→`Metric.OTHER` +
   `metric_other="ontarget_effect_size"` until its semantics are pinned; do **not** call it log2fc.

### SHOULD-FIX
5. **Cap predictive weight (finding C).** Enforce `evidence_type=predictive ⇒ weight ≤ W_max`
   (design says capped). Pick W_max < any experimental replication weight so a model can prioritize
   but never outweigh a real replication.
6. **Set `extra="forbid"` on all models (finding G).** A data contract that silently drops unknown/
   misspelled fields loses data with no error — a producer typo becomes invisible data loss. Fail loud.
7. **Add evaluation `context` to Evidence (finding F).** "Confirm only within a matched context tuple"
   is unauditable if the edge doesn't record the context it was evaluated in. Add the same
   `dict[str, Term]` context field (core-axis validated) to `Evidence`, and ideally a
   `context_match` Check comparing it to the hit's context.
8. **Represent significance faithfully (§2).** Add an optional `significant: bool` (or require a
   `direction_fdr`/`effect_vs_noise` Check) so `ontarget_significant` isn't forced through a
   p-value field the source doesn't have.
9. **Version compatibility (finding G).** Reject or warn when `Evidence.schema_version` is
   incompatible with the hit it grades; today they can silently differ.

### NICE-TO-HAVE
10. **First-class off-target check** — add `CheckName.OFFTARGET` (CRISPRi's main false-positive mode).
11. **Require `perturbation_type` for perturbation subjects** (e.g. when `kind="perturbation"`).
12. **`Provenance.license`** — an MIT/public-data-only product should record each source's license on
    the edge so the "public data only" invariant is machine-checkable, not just documentary.
13. **`hit_content_hash` is optional and unchecked** — make it required on `confirmed` edges and
    document that it pins *which* version of the hit was confirmed (guards silent hit drift).
14. **`target_baseMean`** → optional home (e.g. an `x_base_mean` context term or a Check value) if kept.
