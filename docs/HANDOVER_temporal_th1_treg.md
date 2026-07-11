# spot — handoff: temporal Th1→Treg lever exploration + naive-baseline check

_Prepared 2026-07-11. **Exploratory** analysis layered on the frozen Stages 1–2
(branch `stage1-remediation`, PR #16). These are exploratory numbers, **not frozen
artifacts** — no hashes minted, nothing committed as a locked contract; everything is
regenerable from the scripts below. An independent Claude Science read is in
`docs/cs_review_temporal_th1_treg.md` and is summarised at the end._

---

## 1. The question (as it evolved)
Not "watch a cell become a Treg" (untestable here — see §2) but: **reverse-engineer the
causal gene levers that push CD4 T cells along a Th1-like ↔ Treg-like axis, and see how
those levers change from 8 hr to 48 hr** ("is the signalling getting stronger, is it a
druggable target").

## 2. Honest boundary (holds)
Marson GWCD4i is a **cross-sectional** snapshot (Rest / Stim8hr / Stim48hr), **not
lineage-traced**; 10x **Flex** (probe-based, spliced-only) rules out RNA velocity. No
cell-level Th1→Treg fate transition is claimable. Reframed to **(a)** a descriptive
population-level *program-score* shift over time and **(b)** causal per-timepoint
knockdown levers compared across timepoints. (b) is causal *because CRISPRi is an
intervention* — the one genuine causal handle. The word "becoming" is retired; (a) is a
shift in **marker-panel scores within a bulk-activated pool** (no TGF-β/iTreg or Th1
polarizing cytokines in this system), not fate commitment.

## 3. Part A — naive-baseline feasibility check
The user proposed a diff-in-diff anchored to a same-timepoint **naive** baseline
(naive→Th1 @8 hr vs naive→Treg @48 hr). That needs a real naive population at each
timepoint. Checked on the frozen 40k display overlay (stratified ~13.3k/condition,
scaled ×9.9 to the 396k scoring universe); `diff_naive_score` per cell:

| condition | naive median | % naive-high (>0.5) | strict resting-naive (naive>0.5 & activated<0) |
|---|---|---|---|
| Rest     | **+0.639** | **64.4%** (~85k full) | 60.2% |
| Stim8hr  | −0.097 | 4.4% (~5.8k) | 0.5% |
| Stim48hr | −0.138 | 2.5% (~3.2k) | **0.1% (~178 cells)** |

**Verdict: drop the naive anchor — at *both* stim timepoints, not just 48 hr.** The
48 hr residual (~0.1%) is cells that *failed to activate* — a selected, confounded,
underpowered subset — and 8 hr (4.4%) is nearly as collapsed. Replacements, with
**separated jobs**: the **within-timepoint Th1↔Treg contrast** is the primary causal-axis
analysis (no baseline, no cross-state confound); **Rest as a common baseline** is useful
only to *describe* how far the whole program drifted 8→48, kept **out** of the causal
axis (Rest vs 48 hr differ in ~everything — activation, proliferation, metabolism — which
would smear activation into the axis).

Companion descriptive shift (same table): **Th1-like peaks at 8 hr** (median +0.28, 37%
>0.5) and collapses by 48 hr (median −0.30, 5.8%); **Treg-like rises** through stim (8 hr
5.5% → 48 hr 8.1%). The population-level "Th1 early, Treg later" pattern is real — as a
program-score redistribution, not cell fate. (The naive collapse is itself a positive
control that the scoring works: SELL/CCR7/TCF7/LEF1 fall off on activation, textbook.)

## 4. Part B — direct Th1→Treg lever screen, 8 hr vs 48 hr
**Method (byte-faithful to the frozen direct screen):** reuse the committed
`02_geneskew/analysis/direct` projection/mask library. Poles **A = th1_like (away-from),
B = treg_like (toward)**; `balanced_skew = mean(away_from_Th1, toward_Treg)`. Target +
30 kb-neighborhood **masked**. Panel-minus-bin-matched-control means. **No p/q**
(`inference_status = not_calibrated`). Run at Stim8hr and Stim48hr from the pinned
`DE_stats.h5ad`. `registry_sha = 1ac9f6b2`. Panels: **Th1 = CXCR3, TBX21, IFNG, IL12RB2**
(controls 150); **Treg = FOXP3, IKZF2, CTLA4, CCR8, TNFRSF18** (controls 250). Eligible =
guide significantly repressed target + powered + resolved mask.

**Coverage:** 11,415 targets @8 hr (7,128 eligible), 11,281 @48 hr (7,163 eligible),
**6,620 eligible in both**. Pearson corr of `balanced_skew`(8 hr, 48 hr) among
eligible-both = **0.52**.

**Top toward-Treg levers @48 hr:** TBX21 (1.04), HCCS, POLG2, PRELID1, MEN1, ATP6V1E1,
GATB, CMIP, SUCLA2. **@8 hr:** DARS1, PDIA3, EFHD2, COG5, AKAP11, SND1, IL21R, LTB4R
(mostly ER/secretory/translational/metabolic; collapse by 48 hr). **Largest time-increase
(diff 8→48):** TBX21 (+0.72), SOCS1 (+0.60), PPP1R14B (+0.58).

### 4.1 The decomposition is the story — read the two arms, not the sum
`balanced_skew` is the mean of two arms. At 48 hr:

| gene | away_from_Th1 | toward_Treg | balanced | reading |
|---|---|---|---|---|
| **TBX21** | **+2.16** | **−0.08** | 1.04 | pure **Th1 off-switch**, *not* a Treg lever |
| **SOCS1** | +0.27 | +0.24 | 0.26 | genuinely **bidirectional** (mild de-Th1 **and** pro-Treg) |

TBX21's whole score is the Th1-down arm; it does not induce Treg. **`balanced_skew` alone
can rank a "kills-Th1-without-making-Treg" gene at the top.** Any downstream step must read
the **away/toward split**, not the summed number. SOCS1 is the more honestly "Th1→Treg"
lever despite smaller magnitude — but see the SOCS1 red flags in §6.

**Internal-validity signal:** TBX21 (the Th1 master TF) emerging blind as the top
away-from-Th1 lever is a strong sanity check that the projection captures real regulation.
TBX21 is itself in the 4-gene Th1 panel but is **masked from its own projection**, so the
signal is carried by the surviving genes (CXCR3/IFNG/IL12RB2) dropping — not
self-measurement. **This must be verified, not assumed** (§5).

## 5. Interpretive claims — status is *suggestive*, and three need controls before use
- **"Temporal change is real" (corr 0.52 → partly shared / partly time-specific):** the
  "partly time-specific" half is **not yet supported**. 0.52 is attenuated by
  per-target measurement noise; you need the **within-timepoint reliability ceiling**
  (donor-split or split-half reproducibility of the skew at 8 hr and at 48 hr). If
  within-timepoint reliability ≈ 0.6, the cross-timepoint 0.52 is at the noise floor and
  the levers are *more shared than they look*. Also report **Spearman + top-50 overlap**
  (claims are hit-level, not global) and frame as **r² ≈ 0.27**.
- **"Effect grows 8→48 = signalling getting stronger":** **do not state this yet.** At
  least five explanations, and the confounds dominate for a TF knockdown: (1) **CRISPRi
  KD depth increases with time** — dCas9-KRAB has longer to deplete transcript + protein
  by 48 hr; check the target's own log_fc at 8 vs 48 **first**; (2) **TF→target kinetic
  lag**; (3) **program dynamic range grows** (normalize the skew by each timepoint's
  program spread); (4) target expression grows; (5) genuinely stronger signalling — #5 of
  5, not the default. The proposed corroboration (gene's own expression rising in NTC) is
  **too weak** — almost anything Th1-associated rises in an activating culture. Prioritise
  the KD-depth (#1) and dynamic-range (#3) checks.
- **"Favourable druggable target":** Stage 3 (not built). See §6 — several of these hits
  fail the druggability sniff test on their own terms.

## 6. What an external reviewer should demand / run (verification checklist)
1. **TBX21 circularity vs genuine downstream:** leave-one-out on the 4-gene Th1 panel
   (collapses when dropping one gene ⇒ single-direct-target artifact; robust ⇒ real
   program effect); report exact surviving-panel count for the TBX21 KD; re-score against
   a larger orthogonal Th1 signature (TBX21 + cis neighbours masked).
2. **Two-arm split for every top hit** (away vs toward) — already shown for TBX21/SOCS1;
   extend to all shortlisted genes.
3. **Reciprocal-pole symmetry control:** does FOXP3 / IKZF2 / IL2RA come out as the top
   *toward-Th1* lever? If the master Treg regulators score symmetrically, the axis is a
   real bipolar axis; if FOXP3 KD does nothing, the "Treg pole" is weakly defined and the
   readout is really "Th1 vs generic activation."
4. **Is the Treg pole actually Treg or just "activated"?** With no TGF-β polarization the
   Treg panel may ride on IL2RA/CTLA4/TIGIT/LAG3 — up on *any* activated Tconv. Check the
   panel discriminates Treg from activated Tconv (FOXP3, IKZF2) and how many NTC cells
   express Treg markers at all.
5. **Within-timepoint reliability ceiling** for the 0.52 (§5).
6. **KD-depth and dynamic-range** confound checks for the "grows over time" claim (§5).
7. **Global DE-footprint breadth** (sledgehammer vs specific shifter): **SOCS1** is the
   worry — a JAK/STAT negative regulator whose KD amplifies cytokine signalling broadly
   (genome-wide footprint that nonspecifically moves any secreted-marker panel), and it
   restrains **both** STAT1 (pro-Th1) and STAT5 (pro-Treg) so a toward-Treg score is not
   mechanistically given. The **8 hr-dominant set** (PDIA3, DARS1, COG5) looks like
   secretory/translational essential-gene stress artifacts (IL21R is the interesting one).
8. **Donor + guide reproducibility** (intra-donor validity, the user's ask) — **NOT yet
   computed for this contrast**; the frozen screen computes guide/donor support, the
   temporal exploration did not. A hit robust across 4 donors + independent guides is worth
   an order of magnitude more at the druggability gate.
9. **Eligibility asymmetry** before calling anything "time-specific" (fewer cells / weaker
   KD at one timepoint ≠ biology).
10. **Direction, KD≠drug, RNA≠function:** these are loss-of-function levers modelling
    *inhibition*. For anti-tumor immunotherapy you generally want *less* Treg / *more*
    effector, so a "toward-Treg lever" is a **liability, not a hit** — **fix the intended
    therapeutic direction before ranking.** TBX21 (a TF) is historically undruggable;
    SOCS1 loss-of-function causes human autoinflammation (a red flag for "inhibit to
    promote Treg"). CRISPRi is chronic/near-complete/from-t0; a drug is acute/partial. And
    4 marker genes moving ≠ suppressive function — needs arrayed KD + protein/functional
    readout.

## 7. Reproduce
- **Baseline:** `02_geneskew/analysis/temporal_exploration/baseline_naive_populations.py`
  (reads the frozen 40k overlay `stage01_umap_seed.json`).
- **Temporal screen:** `02_geneskew/analysis/temporal_exploration/screen_th1_treg_temporal.py`
  on tcedirector (reuses `direct/` projection lib; reads pinned `DE_stats.h5ad`; writes
  `work/temporal/{th1_to_treg_Stim8hr,Stim48hr,merged}.csv` + `summary.json`).
  `registry_sha = 1ac9f6b2`.

## 8. Independent second opinion (Claude Science)
Full verbatim read in **`docs/cs_review_temporal_th1_treg.md`**. It endorsed the reframe
and the naive-drop (extending it to 8 hr), **independently predicted** the TBX21
two-arm result (Th1-down dominant, Treg-up ≈ 0) before seeing the split, and supplied the
control list in §6. It flagged that the 0.52 cannot support "time-specific" without a
reliability ceiling, that "signalling getting stronger" is premature until the KD-depth /
dynamic-range confounds are ruled out, and that SOCS1 is a druggability red flag. CS has
the DE_stats + NTC on granted paths and **offered to run** checks (1)(2)(5)(7) and the
KD-depth confound — a natural next pass. **Generator ≠ verifier:** the numbers here were
produced by the exploration driver; CS and the external reviewer are the independent
checks.
