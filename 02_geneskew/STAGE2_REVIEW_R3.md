# spot Stage-2 — Claude Science review R3 of the rewritten plan (2026-07-10)

_Independent CS read of the rewritten STAGE2_PLAN.md, verified against GWCD4i.DE_stats.h5ad
obs/layers, the two .h5mu matrices, the cell-level assigned_guide.h5ad obs, the sgRNA library
table, and the sample metadata. Verdict: large honest improvement, numbers exact; six mechanical/
strategic refinements below. (A verifier sub-agent also flagged one unsupported sourcing claim in
the review's own prose — the 'no IL-12/IFN-γ per sample metadata' line — the metadata has no
cytokine columns; treat that reasoning as a prior, not a data check.)_

---

I've verified the plan against the actual `GWCD4i.DE_stats.h5ad` obs/layers, the two `.h5mu` matrices, the cell-level `assigned_guide.h5ad` obs, the sgRNA library table, and the sample metadata. Here is my read.

## Bottom line

The rewrite is a large, honest improvement — every headline number I could check is exactly right, and the framing corrections (the 3,341 reframe, the null policy, the scLDM demotion, the scVI-checkpoint removal) hold up against the files. But two things in the parts you flagged are still wrong at the data level: the **off-target mask points at fields that cannot supply the mask genes** (§6), and the **effect vectors are not where the plan implies** (the main `X` is empty). And on your question (b), the data can't answer the B-sparsity question at all — which itself is the argument for pushing harder toward the one-sided default. Details below.

## (a) Retained numbers and the eligibility/multiplicity framing — correct

Every retained statistic reproduces exactly from `GWCD4i.DE_stats.h5ad`:

- 33,983 target×condition rows; 11,526 unique targets (`obs.target_contrast` and `target_contrast_gene_name` agree); 10,282-gene universe (`var`).
- Condition split: **Rest 11,287 / Stim8hr 11,415 / Stim48hr 11,281** — matches the plan digit-for-digit.
- The 3,341 reframe is exactly right: `n_total_de_genes > 75 & n_cells_target > 50` → **3,341 rows spanning 1,860 unique genes**. It is unambiguously a post-hoc *outcome* ascertainment, and calling it that (not an eligibility criterion, not the multiplicity family) is the correct fix.
- FOXP3 Stim48: one row, `n_total_de_genes = 4`, `n_downstream = 3`, `n_cells_target = 1,360`, and `ontarget_significant = True`. All correct.

The pre-outcome eligibility logic is sound. One quantitative refinement worth writing into §7/§17 so nobody corrects multiplicity over the wrong denominator: once your own pre-outcome gates apply, the tested family is **materially smaller than 11,281**. In Stim48 specifically: `ontarget_significant == True` holds for **7,195** rows, `low_target_gex == True` for 2,431, and `n_cells_target > 50` for 11,146. If eligibility requires detectable on-target repression (as §7 says), the family you correct over is ~7k, not ~11k. The plan's "emit the actual tested family size at run time" already covers this — just don't let the 11,281 figure read as the correction family anywhere.

## (b) Same-timepoint Stim48 default vs. the one-sided fallback — push harder toward one-sided, and here's the data reason

The decisive finding: **there is no functional state annotation anywhere in the released cell files.** The `Dx_Stim48hr.assigned_guide.h5ad` obs carries only `PuroR, guide_group, guide_id, guide_type, lane_id, low_quality, n_genes_by_counts, pct_counts_mt, perturbed_gene_id/name, top_guide_UMI_counts, total_counts` — no cluster/leiden/celltype/FOXP3/Th1/Treg label. So the sparsity and donor-stability of pole **B (Th1-like at Stim48) is genuinely unmeasurable from the released metadata** — you cannot count B until Stage-1 actually clusters the cells. Your `not_evaluated` / "empirical question" framing is therefore the correct posture: neither you nor I can pre-declare B is fine.

That unmeasurability is itself the argument for reweighting, not just keeping a fallback:

1. **B is anchored on a weak pole.** These are in-vitro anti-CD3/CD28 bulk activations with no Th1-polarizing cytokines (no IL-12/IFN-γ, per the sample metadata — standard stim, not skew). A canonical Th1 program is a biological prior to be *minority and poorly polarized* at 48 h. Pole A (induced FOXP3⁺CTLA4⁺) is concrete and marker-anchored; pole B is not. This is a prior, not a measurement — but it points the same way as the missing labels.
2. **The projection statistic inherits B's noise.** The `total_skew` two-pole score estimates `b_up` against that weak pole, so the two-pole statistic is the *less* trustworthy of the two even before sparsity is measured. The one-sided "regulatory-program reduction" is anchored on the measurable pole.

So I'd go further than "same-timepoint two-pole primary, one-sided as fallback." I'd **run both unconditionally, report the one-sided regulatory-reduction as the headline statistic, and let `total_skew` drive ranking only when the G-sep and G-frac gates on B actually pass.** That's a stronger, less self-fulfilling stance than a fallback you invoke by judgment, and it survives the case where B is real but faint.

One more point that supports the same-timepoint choice more strongly than the plan claims: **all four Stim48 samples are in run R2** (verified in `sample_metadata.suppl_table.csv`). So within Stim48 there is *no run/donor confound* — good for `~ donor + state`. The cross-timepoint 48→8h sensitivity, by contrast, **confounds run with donor**: donors CE0008162/CE0010866 have their 8 h in R1 but their 48 h in R2. The plan calls 48→8h "descriptive sensitivity" but doesn't flag that it is also batch-confounded. Say so — it removes any temptation to lean on it.

## (c) Null policy — sound, feasible, one clarification needed

The core logic checks out against the files:

- **No NTC/non-targeting row exists in `DE_stats`.** The only control-string target is `KNTC1`, which is a real kinetochore gene, not a control. So raw NTC cannot be projected as a target-vs-NTC statistic — correct, and correctly the reason you can't shortcut the null.
- **The §9(A) pseudo-target null is feasible**, because non-targeting guides *do* exist one level down: the cell-level `guide_type` field has categories `['non-targeting', 'targeting']`. Building matched pseudo-target groups from NTC guides and rerunning the identical DE model is a real, available construction. Good.
- The (A)/(B) dichotomy with **no undefined parametric fallback** is the right discipline.

Two things to add for completeness:

1. **Distinguish the per-gene DE null (which already exists) from the skew null (which doesn't).** `DE_stats` ships `layers/p_value` and `layers/adj_p_value` (both 33,983×10,282) — the authors' per-gene DE significance is already in the file. Your §9 is about the null for the *axis-projection / skew* statistic, which is a weighted sum across genes and is **not** calibrated by the per-gene q-values. Right now a careful reader could see "no calibrated null" next to a file that visibly contains `adj_p_value` and think you missed it. Add one sentence: the existing per-gene q-values do not calibrate the projection score; §9 concerns the skew statistic specifically.
2. **Freeze the axis inside the null.** §9(A) says "project the resulting DE vectors" — make explicit that the pseudo-targets are projected onto the *same frozen A→B axis*, with only the target vectors permuted. If the axis is re-estimated per pseudo-target you conflate axis-estimation noise into the null and it stops meaning what you want.

## (d) Still wrong, missing, or self-fulfilling

**1. The off-target mask points at the wrong fields (real, load-bearing defect).** §6 says the DE_stats `neighboring_gene_KD` and `distal_offtarget_flag` fields "carry" the neighboring/proximal/distal off-target coordinates for `M_X`. They don't — both are **booleans** (`neighboring_gene_KD`: 2,619 True; `distal_offtarget_flag`: 433 True). They tell you a row *has* such an effect, not *which genes* to mask. The actual off-target gene identities live in `sgrna_library_metadata.suppl_table.csv`: `nearby_gene_within_2kb/10kb/20kb/30kb`, `nearest_within2kb_nontarget_gene_id/name`, `nearest_nontarget_gene_id/name`, `distance_to_closest_target_tss`. So `M_X` *is* constructible — but by joining the sgRNA library to each target's guides, not by reading two boolean obs columns. Because the entire "unmasked score is self-fulfilling" safeguard rests on masking the right genes, this needs to be corrected, and the neighborhood window (2/10/20/30 kb) becomes a preregistration choice the plan should name.

**2. The effect vectors are not in `X` (unnamed, and `X` is empty).** §1/§6 describe the measured effect vectors as living in `DE_stats`, but the main `X` is a null dataset (`encoding-type: null`). The vectors are in **`layers/`**: `log_fc`, `lfcSE`, `zscore`, `p_value`, `adj_p_value`, `baseMean`, each 33,983×10,282. An implementer following the plan literally hits an empty `X`. Name the layer (`log_fc` for `d_{X,g}`, `lfcSE` for the z-score sensitivity).

**3. Donor replication is thinner than §8 implies.** `by_donors.h5mu` ships **six leave-two-in pair matrices** (CE0006864/CE0008162/CE0008678/CE0010866 → 6 pairs, ~4,880×10,273 each), not per-donor vectors, over **4 donors total**. True leave-one-donor-out on the DE side isn't in the released files — you'd recompute from cells. Your "LODO where feasible" hedge is honest, but with n=4 a single donor reversal is 25% of the evidence, and the released granularity is pairs. State the effective donor n (4) and the pair-level granularity explicitly so "donor-reversal flags / LODO rank stability" isn't read as higher-resolution than it is. (Separately: the pair matrices span 10,273 genes vs. the main file's 10,282 — a 9-gene mismatch your §13 missing-gene policy should resolve on a named common set.)

**4. The primary ranked table is composition-confounded until §10 — say so at the screen stage.** Even with a correct target mask, `total_skew` is computed on whole-condition bulk KD-vs-NTC vectors. A KD that shifts *population composition* (kills activated cells, stalls proliferation) moves the bulk vector along the axis with zero cell-intrinsic reprogramming — your R1 ascertainment risk. The plan catches this only downstream in §10 (viability/UMI/cycle). I'd make the proliferation/viability confound explicit at the screen stage: the primary ranked table mixes intrinsic reprogramming with composition shift, and `screen_only` hits must not be read as intrinsic until §10 separates them. Right now §10 is doing load-bearing deconfounding that the ranked table's framing doesn't advertise.

**5. FOXP3 probably can't serve as the sign-validation positive control (G-sign).** FOXP3 Stim48 has `ontarget_significant = True` but only 3 downstream DE genes — i.e., the knockdown *worked* on-target yet produced almost no transcriptional footprint at 48 h. So the natural positive control for the default contrast is itself underpowered to move the axis, and G-sign will likely stay "not behaviorally validated" for the default contrast. That's consistent with your G-sign wording, but the plan should say what it *does* when the obvious positive control is too quiet to validate the sign — otherwise most contrasts ship with an unvalidated sign and no stated contingency.

**6. Minor wording seam.** §1 calls the vectors "knockdown-vs-NTC effect vectors" while §9 says there's no NTC in the table. Both are true — the DESeq2 contrast *is* against the pooled NTC, but the NTC group has no self-vs-self row — yet placed apart they read as a contradiction. One clause reconciling them will save a future reader the same double-take I had.

Nothing in the plan is over-claimed in the biological direction — the "cannot claim" list in §2 and the status vocabulary in §10 are appropriately strict, and I found no place where a hedge is quietly dropped. The weaknesses are all in the mechanical layer (where the mask/vectors actually live, how much donor resolution exists) and in one strategic call (making one-sided the headline rather than the fallback), not in the epistemics.

If it's useful I can turn the §6 mask into a concrete recipe — the exact sgRNA-library join and the per-target `M_X` gene set — and name the layer/gene-intersection fixes as a short redline against the specific lines. Say the word and I'll draft it; you asked for prose only this round, so I've left it here.
