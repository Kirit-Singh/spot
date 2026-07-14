# Independent scientific review — spot Stage-1 CD4 nomenclature map

_Reviewer: independent read of `stage1_pipeline.py`, `cluster_scores.py`, `label_clusters.py`,
the emitted overlay, and the marker sidecar. Every headline number below was reproduced directly
from the emitted overlay (`stage01_umap_seed.json`, 40k) and `marker_expr_sidecar.json` without
re-running the heavy compute. Two follow-up checks (§ "Follow-up checks") were run at the author's
request and are appended verbatim._

---

## Overall verdict

The analysis is sound, and unusually honest about its own limits. I reproduced every headline
number directly from the emitted overlay and the marker sidecar without re-running the heavy
compute: 82.1% no functional call, Th1 12.0% overall (32.2% of the 8hr-activated compartment),
the Treg cluster at 6.3%, and the cluster-vs-FDR-Treg Jaccard at 0.077. The confound-aware design
is the right instinct for a polyclonally-activated substrate, the permutation-FDR floor is a
genuine improvement over the earlier absolute-threshold method it replaced, and the two validation
checks (cluster 5, marker re-inclusion) are real tests rather than decoration.

The weakest point is not in the machinery — it's a biological interpretation question about what
the "Treg" cluster actually *is*, given the starting material. I'll take that after the four
judgment calls.

## The four judgment calls

**1) Treg as the Leiden cluster, not the per-cell FDR call — yes, this is correct as the primary
definition.** The two sets *should* have low Jaccard; 0.08 is expected, not alarming, because they
measure different things. The FDR call asks "does this one cell's FOXP3/IKZF2/CTLA4/CCR8/TNFRSF18
panel clear significance against its own expression-matched null" — and on 3′ Flex data with FOXP3
captured in only 27.5% of cluster-Tregs (verified from the sidecar: 698/2538), a per-cell panel
call is guaranteed to miss the ~72% of true Tregs where FOXP3 simply dropped out. The cluster
definition borrows strength across the scVI manifold and is robust to that per-gene dropout. And
the cluster is unambiguously Treg-enriched: I measured CTLA4 at 74.4% detection vs 5.1% in naive
clusters, FOXP3 at 27.5% vs 6.8% (a 4× enrichment despite dropout), IKZF2 3× enriched. For a
Stage-2 target where you need a defined, complete, stable population to test perturbation effects
against, the cluster is the correct unit. Using the FDR call as primary would throw away
three-quarters of your target for no gain.

**2) Dropping IL2RA / GZMB+NKG7 — fair de-confounding for the target, but slightly too blunt for
CD4-CTL specifically.** The direction is right and the CD25 case is airtight: IL2RA is detected in
99.2% of cluster-1 cells and *still* 40.3% of naive cells — it is dominated by activation, so
keeping it in the Treg panel would score activation, not Treg identity. Your own validation
confirms the trade: for Treg, dropping gives 55% coherence and re-including collapses it to 30%.
Crucially, the drop also wins on *absolute* coherent yield for Treg (12.5%×55% ≈ 6.9% vs
conditioned 18.2%×30% ≈ 5.5%), so you are not under-calling the target.

CD4-CTL is the exception, and your notebook already caught it: the conditioned variant (c) recovers
23.9%×37% ≈ 8.8% coherent cells versus 11.4%×61% ≈ 7.0% for the drop — about 26% *more* real CTL
signal. So for CD4-CTL the binary drop does trade away recall you could keep. The clean answer for
both is not "drop vs keep" but the conditioned approach you already prototyped: regress out the
activation component and retain the informative marker. I'd move CD4-CTL to that. It's low-stakes
here (CTL isn't the Stage-1 target), but it's the one place "am I under-calling" has a real yes.
One caveat you flagged and I'll second: the coherence metric is graded against the drop's own
argmax panel, so it's mildly circular and reads as a purity proxy, not ground truth.

**3) Memory cluster 5 relabelled "Resting," not Tscm — the negative call is solid; the positive
label is the weak part.** Tscm requires FAS/CD95 gained *while stemness is retained*. I verified
from the sidecar that cluster 5 has neither: FAS is not elevated (52.0% vs 58.1% in naive), and
stemness is clearly lost (TCF7 19.6% vs 43.7%, LEF1 51.5% vs 78.7%, SELL 36.8% vs 75.7%). So "not
Tscm" is correct and well-supported. But "Resting" is a label about *condition* (cluster 5 is 96%
Rest per `cluster_scores.json`), whereas the *phenotype* — stemness collapsed, GZMB up — is not a
resting-naive phenotype. The more likely reading of a 342-cell (40k-overlay; 3,383 full-set),
Rest-dominant cluster with a coordinated TCF7/SELL/LEF1 drop is a low-quality or low-complexity
population (ambient/low-UMI) rather than a distinct biological state. I'd check median UMI/gene
counts for cluster 5 before committing to any positive label; "unresolved/low-complexity" would be
more defensible than "Resting." Either way it's 0.9% and not the target, so it doesn't threaten the
funnel — but the label as written slightly over-reads the data. **[This hypothesis was tested — see
Follow-up check 2 below; it was refuted. Cluster 5 is NOT low-complexity.]**

**4) 82% no-call — honest, and if anything a sign the method got the answer right.** This is the
expected result for a Th0 polyclonal (anti-CD3/CD28) stim from a naive-enriched input: bead/plate
activation delivers no cytokine-polarizing signal, so most cells legitimately never commit to a
defined Th program. Roughly half the cells are naive or cycling (Naive 21.6% + Cycling 26.5%) and
should be ~100% null by construction; the only coherent effector skew is Th1 in the 8hr compartment
(32.2%), which fits bystander IFN-γ/T-bet from strong acute TCR signaling. The permutation floor is
doing real work, not just being conservative — the clearest evidence is that the old
absolute-threshold method's Th2 call (11%, driven entirely by PTGDR2 with IL4/IL5/IL13 at
dropout-zero) collapses to 1.3% under the FDR floor. That artifact deserved to die. So 82% is the
biologically correct answer. The one honest residual: some no-calls in the shallowest cells are
power-limited rather than truly null, which is exactly the right way to fail given your stated
principle of saying "insufficient power" out loud.

## Where it's most likely wrong

**The single biggest scientific risk is the identity of the Treg cluster, not its detection.** The
input is bead-isolated *naive* CD4, and cluster 1 is 98.9% Stim48hr (from `cluster_scores.json`,
`cond["1"]`). A FOXP3⁺CTLA4⁺ population that appears almost exclusively after 48h of polyclonal
activation, arising from a naive starting pool, is the textbook setting for **activation-induced
FOXP3** — transiently induced in human conventional CD4 T cells by TCR signaling *without*
conferring bona fide Treg lineage or suppressive identity. Two things in your own data lean this
way: the cluster is essentially absent at Rest and 8hr, and Helios/IKZF2 — the marker that
distinguishes thymic/stable Tregs from induced FOXP3⁺ Tconv — is low (5.9% detection, only 3×
naive, versus CTLA4's near-ubiquity). This is not a reason to abandon the target, but it changes
what the target *means*: Stage-2 may be finding perturbations that modulate **induced FOXP3⁺
regulatory-like cells at 48h**, not natural Tregs, and the downstream drug/PK/PD interpretation
should carry that qualifier. The cleanest disambiguation is to check whether any
FOXP3⁺CTLA4⁺IKZF2⁺ signature exists in the *Rest* compartment (residual nTregs) versus being purely
48h-induced — if it's purely 48h, the induced-FOXP3 framing is the honest one. **[This was tested —
see Follow-up check 1 below.]**

**Second: three inconsistent method descriptions coexist in the workbench**, which is a
reproducibility landmine even though the deployed science is correct. `REVIEW_BRIEF.md` describes
the *old* absolute-floor method entirely (top>0.20, margin>0.06, 49% no-call, Treg 9%);
`label_clusters.log` on disk records a *three*-Treg-cluster assignment (1, 4, 12) that disagrees
with the deployed single-Treg `cluster_labels.json`; and the models-dir `stage01_umap_seed.json`
mirror still holds the old 48.8%-no-call calls. The actual deployed workbench file
(`/home/tcelab/spot-design/data/stage01_umap_seed.json`) and `stage1_pipeline.py` are
self-consistent and correct (verified per-cell function calls: 82.1% no-call, Treg-*called* 2.7% —
distinct from the Treg *cluster*'s 6.3% of cells cited in the Overall verdict; the two differ by
design, see judgment call 1) — but a reviewer who pulls the
wrong copy or reads the brief will get a different story. Also minor: `reproduce.sh` step [3]
claims the pipeline emits `data/stage01_umap_seed.json`, but the code writes
`stage01_umap_seed.emitted.json` — the rename to the served filename happens outside the gated
chain, so `verify_reproduce.py` isn't actually gating the file the workbench paints. I'd delete or
regenerate the stale artifacts and make the pipeline write the served filename directly.

**Third, smaller, methodological:** function assignment is argmax-over-7-then-test-the-winner's-q.
The permutation null absorbs most of the multiplicity, but you're still selecting the max before
testing it, which is a mild selective-inference optimism on the borderline calls. It won't move the
headline numbers (the winners clear comfortably or not at all), but it's worth a sentence in the
methods rather than presenting q<0.05 as a clean per-lineage FDR.

## Net

The pipeline is rigorous where it matters: the confound handling is directionally right, the FDR
floor is honest and demonstrably killed a real artifact, and the cluster-based Treg definition is
the correct call for a Stage-2 target. The corrections I'd prioritize are (1) reframe/qualify the
Treg cluster as likely activation-induced FOXP3 given the naive input and 98.9%-48h composition —
this is the one that could change the biology of the whole funnel; (2) clean up the stale
brief/log/mirror so the reproducible chain and its documentation tell one story; and (3) switch
CD4-CTL from hard-drop to the conditioned variant you already built. Judgment calls 1, 3 (the
negative half), and 4 I'd sign off on as-is; call 2 is right for the target and slightly blunt for
the non-target.

---

# Follow-up checks (run after the review, at the author's request)

Both were run on the cheapest sufficient source. Check 1 used the 40k marker sidecar
(`marker_expr_sidecar.json`) + emitted overlay — no 14 GB load. Check 2 read only the small 1-D
`obs` QC arrays from the HDF5 (`total_counts`, `n_genes_by_counts`, `pct_counts_mt`, `L0.8`,
`low_quality`) via h5py — the `.X` count matrix was never touched, so it ran on the full 396k
population, not just the subsample.

## Follow-up 1 — Induced vs natural Treg: is there ANY FOXP3⁺IKZF2⁺ (Helios⁺) signature at Rest?

**Answer: the FOXP3⁺CTLA4⁺ Treg signal is essentially 48h-induced. There is no meaningful residual
natural-Treg (Helios⁺) population in the Rest compartment.** This confirms the induced-FOXP3
framing.

Per-condition rates across all 40k cells (all clusters, not just cluster 1):

| Condition | FOXP3⁺ | IKZF2⁺ (Helios) | FOXP3⁺ & IKZF2⁺ | FOXP3⁺ & CTLA4⁺ |
|-----------|--------|-----------------|-----------------|-----------------|
| Rest (n=13,331)     | 6.75%  | 2.41% | **0.21%** (28 cells) | 0.86% |
| Stim8hr (n=13,324)  | 8.68%  | 5.04% | 0.74% | 5.82% |
| Stim48hr (n=13,345) | 28.18% | 5.38% | 1.54% | **22.41%** |

The decisive contrast is the two co-expression columns. FOXP3⁺CTLA4⁺ — the signature the Treg
cluster is built on — rises **~26-fold** from Rest (0.86%) to Stim48hr (22.41%), tracking
activation almost perfectly. FOXP3⁺IKZF2⁺ (Helios⁺, the thymic/stable-Treg discriminator) barely
moves on an absolute basis (0.21% → 1.54%) and, unlike CTLA4, does not scale with the FOXP3
expansion. At Rest, genuine FOXP3⁺Helios⁺ double-positives number **28 cells out of 13,331 (0.21%)**,
and they are not concentrated in any Treg-like cluster — they scatter across clusters 0, 2, 3, 5
(the naive/cycling/resting mass), i.e. sporadic FOXP3 detection in resting Tconv, not a coherent
residual nTreg island. Of all Rest FOXP3⁺ cells, only 1 sits in the Treg cluster (cluster 1); the
Treg cluster itself is 2,517/2,538 Stim48hr in the overlay (99.2%).

Interpretation: this is the expected picture for a bead-isolated *naive* CD4 starting pool.
Circulating natural Tregs are a small fraction of naive-gated CD4 and here they are essentially
absent at Rest, while the FOXP3⁺CTLA4⁺ population materializes only after 48h of polyclonal
stimulation. The Stage-1 "Treg" target is therefore best described as **activation-induced FOXP3⁺
regulatory-like cells at 48h**, not natural/thymic Tregs. The target is still valid and coherent;
the label should carry that qualifier, and Stage-2 hits should be read as modulators of induced
FOXP3⁺ conventional cells. (Caveat: IKZF2 at 3′ has real dropout, so the absolute Helios⁺ rate is
an undercount — but the *contrast* between CTLA4 scaling 26× and IKZF2 staying flat is dropout-robust,
because both are measured the same way.)

## Follow-up 2 — Cluster-5 QC: is the "Memory/Resting" cluster low-complexity/ambient?

**Answer: no. The low-complexity/ambient hypothesis is refuted.** Cluster 5 has essentially the
same sequencing depth and gene complexity as the bona fide naive clusters. Full 396k population,
from `obs`:

| Group | n | median UMI | median genes | median mt% | low_quality flagged |
|-------|---|-----------|--------------|-----------|---------------------|
| Cluster 5 (Memory/'Resting') | 3,383 | 6,018 | 3,117 | 0.23% | 0.0% |
| Naive clusters (2,3)         | 85,588 | 6,373 | 3,174 | 0.35% | 0.0% |
| — cluster 2                  | 71,491 | 6,149 | 3,105 | 0.31% | 0.0% |
| — cluster 3                  | 14,097 | 7,647 | 3,526 | 0.65% | 0.0% |
| Treg cluster 1               | 25,125 | 6,694 | 3,256 | 0.29% | 0.0% |
| All cells                    | 396,000 | 9,819 | 4,129 | 0.36% | 0.0% |

Cluster 5's median UMI (6,018) and genes/cell (3,117) are within ~6% and ~2% of the naive-cluster
medians (6,373 / 3,174), its mitochondrial fraction is *lower* than naive (0.23% vs 0.35%), and
none of its cells are flagged `low_quality`. This is a normal-depth, clean population — not ambient
or low-complexity droplets.

**This revises the review.** My speculation in judgment call 3 that cluster 5 might be a low-UMI
artifact is wrong. Cluster 5 is a genuine, well-sequenced ~0.9% Rest-dominant population whose
phenotype is stemness-low (TCF7/SELL/LEF1 reduced), FAS-not-elevated, GZMB-up. So the *negative*
call stands and is in fact strengthened — it is decisively **not Tscm** (Tscm requires retained
stemness, which is absent) — but the population is real, not technical. A more accurate positive
label than "Resting" would be a **differentiated/effector-memory-like resting population** (loss of
naive stemness markers with effector GZMB), i.e. closer to an antigen-experienced Tem/Temra-like
resting state than to either naive or Tscm. It remains 0.9% and off the target path, so this does
not affect the funnel — but "Resting" undersells a phenotype that has genuinely moved off the naive
program.

_(All follow-up numbers are reproducible from `marker_expr_sidecar.json` + `stage01_umap_seed.json`
for check 1, and from the `obs` group of `ntc_clustered.h5ad` — QC columns only, no `.X` — for
check 2.)_
