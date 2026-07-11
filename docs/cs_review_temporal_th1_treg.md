# Claude Science — independent read on the temporal Th1→Treg logic

_Verbatim response from a Claude Science session (project "spot pipeline robustness", frame d95a7a3a), 2026-07-11. Posed the design logic + findings for an independent immunology opinion; CS did not generate the numbers it is commenting on (generator ≠ verifier). It independently predicted the TBX21 two-arm result before seeing the split._

---

Happy to give you a straight read. Overall your instincts are good and mostly on the conservative side, which is the right side to err on here — but there are a few places where I'd tighten the framing, and one (your 3c reading) where I'd push back fairly hard. Going point by point.

## 1) Cross-sectional + no velocity → descriptive shift + causal levers

Fair, and I wouldn't call it too conservative — I'd call it correct, and I'd actually push it a touch further.

You're right on the mechanics: Flex is probe-based against spliced transcripts, so there are no intronic/nascent reads and velocity is genuinely off the table. But I wouldn't mourn that, because velocity over an 8–48hr activation time course would be unreliable even on standard 3′ chemistry — the dynamical-model assumptions break down badly in strongly perturbed/activating systems. So you've lost nothing real. And even a working velocity field would not license the "a Th1 becomes a Treg" claim; only clonal lineage tracing with longitudinal sampling could, and you don't have it. So the reframe into (a) population-level program shift and (b) per-timepoint causal knockdown levers is exactly the right decomposition.

Two things I'd add so the framing doesn't quietly overreach:

- Your (a) is a shift in *marker-panel scores*, not a shift in lineage. Keep saying "program" and resist "the population is differentiating into Treg." In this system (TCR/CD28 activation, no TGF-β/iTreg or Th1 polarizing cytokines that I can see), you're mostly watching activation-induced expression of Th1-like and Treg-like *modules* within a bulk-activated pool — not fate commitment. The word "becoming" in the user's goal is biologically loaded and I'd retire it.
- Your (b) is clean *because CRISPRi is an intervention* — that's the one genuinely causal handle you have, and comparing a KD's effect at 8hr vs 48hr is legitimate as "how the intervention's effect on the program differs by snapshot." Just don't let "compared across timepoints" slide into "the lever changes as the cell transits" — same trap as (a), one level up.

## 2) Drop the naive anchor

Agree it should go — and I'd go further than you: drop it at **both** stim timepoints, not just 48hr.

Your 48hr case is airtight: 2.5% >0.5, ~0.1% strict — anchoring a diff-in-diff on that residual is anchoring on cells that *failed to activate*, which is a selected, weird, non-random subset (anergic / poorly transduced / low-TCR / bystander), so any "naive→X @48hr" estimate is both underpowered and confounded. But look at your own 8hr numbers: median −0.10, 4.4% >0.5. That's almost as collapsed. The naive anchor was never well-posed at 8hr either; keeping it there just for symmetry would import the same selection problem in slightly milder form. Be consistent and drop it at 8hr too. (The collapse itself is a nice positive control that the scoring works — SELL/CCR7/TCF7/LEF1 falling off on activation is textbook.)

On the two replacements, I'd separate their jobs rather than treat them as interchangeable:

- **Within-timepoint Th1↔Treg contrast** — this is the clean one for the *axis* question, and I'd make it the primary. No baseline, no cross-state confound.
- **Rest as common baseline** — useful for the *descriptive* "how far did the whole program move 8→48" question, but I'd keep it out of the causal-axis analysis. Resting and 48hr cells differ in essentially everything (activation, proliferation, metabolism), so a Rest-anchored contrast smears activation into the Th1/Treg axis. Use it to describe magnitude of drift, not to define levers.

## 3a) TBX21 as top toward-Treg lever — signal or panel artifact?

Both, and the honest answer is "reassuring positive control, but not yet evidence of genuine downstream regulation." Your circularity worry is the right worry.

T-bet is *the* Th1 master TF; its KD de-Th1-ing cells is guaranteed by definition, so TBX21 landing at the top is a sanity check that your metric points the right way — good. But with a ~4-gene panel, "TBX21 KD lowers the Th1 panel" risks being close to tautological: you may be measuring T-bet's effect on its own direct targets (IFNG, CXCR3, IL12RB2…), which is what T-bet *is*, not interesting downstream program regulation. Concretely, here's how I'd separate the two:

1. **Confirm TBX21 is masked from its own panel.** If TBX21 is a panel member and your 30kb mask removes it, you're now scoring the TBX21 KD on ~3 genes — extremely fragile. Report exact panel membership and what survives masking *for this KD specifically*.
2. **Leave-one-out on the panel.** Recompute the away-from-Th1 score dropping each Th1 marker in turn. If it collapses when you drop one gene (say IFNG), it's a single-direct-target artifact; if it's robust across LOO, it's a coordinated program effect. This is the cheapest decisive check with a 4-gene panel.
3. **Score against an orthogonal, larger Th1 signature** (a curated Th1-vs-other-CD4 module, TBX21 + cis neighbors masked). Still ranks high → genuine.
4. **The decomposition I care about most: split the balanced skew into its two arms.** "away-from-Th1 + toward-Treg" — for TBX21 I'd bet almost the entire 1.04 is the Th1-down arm and ~0 is Treg-up. If so, TBX21 is a **Th1 off-switch, not a Treg lever**, and calling it a "toward-Treg lever" overstates it unless the axis is genuinely reciprocal in this data. Report both half-scores for every top hit; don't let the summed metric hide which pole is doing the work.
5. **Test the reciprocal pole as a symmetry control.** Does FOXP3 (or IKZF2/Helios, IL2RA) come out as the top *toward-Th1* lever? If the master Treg regulators score symmetrically on the other pole, you have a real bipolar axis. If FOXP3 KD does nothing, your "Treg pole" is weakly defined and the whole thing is really a Th1 readout with a Treg-flavored label — which also bears on 3d.

## 3b) corr = 0.52 → "partly shared, partly time-specific"?

Loosely fair for "partly shared" (r²≈0.27), but 0.52 *on its own* cannot support the "partly time-specific" half, and I wouldn't lean on it as written.

The problem is attenuation: a chunk of the 0.48 "not shared" is just measurement noise in the per-target skew at each timepoint, not biology. To claim biological time-specificity you need the **reliability ceiling** — the within-timepoint reproducibility of the skew (donor-split or split-half at 8hr, and again at 48hr). If within-8hr split-half is ~0.6, then a cross-timepoint 0.52 is essentially at the noise floor and the levers are *more shared than they look* — "time-specific" would be mostly an artifact. If within-timepoint reliability is ~0.9, then 0.52 is genuine divergence. That one control decides the interpretation; without it the number is ambiguous.

Two smaller things: (i) a global Pearson over ~6,600 mostly-near-zero targets is dominated by the null mass and by outliers like TBX21 at 1.04 — report Spearman too, and better yet report rank concordance of the *top* hits (overlap of top-50, or Spearman on the powered/strong subset), because your actual claims ("TBX21 grows, PDIA3 is 8hr-specific") are hit-level, not global. (ii) Frame it as r² so "partly shared" doesn't get read as "mostly shared."

## 3c) "effect grows 8→48 = signalling getting stronger"

This is where I'd push back hardest. "Signalling getting stronger" is *one* explanation, and not the most parsimonious for a TF KD. A growing projected effect is consistent with at least five things, and you can't attribute it without ruling out the confounds:

1. **KD depth increases over time.** dCas9-KRAB has more time to deplete the transcript and the protein to decay by 48hr, so the target is more completely off later. If TBX21 is repressed 50% at 8hr and 85% at 48hr, the effect grows partly because the *knockdown* is deeper, not because the pathway got stronger. This is the single biggest confound in any CRISPRi time-course "effect grows" claim, and it's checkable directly from the target's own log_fc. **Check this first.**
2. **TF→target kinetic lag.** For a TF specifically, at 8hr the protein hasn't fully fallen and downstream targets haven't re-equilibrated; by 48hr the full cascade has played out. Larger 48hr effect is then just kinetics of protein turnover + target response — expected regardless of signalling strength. For TBX21 this is arguably the most likely explanation.
3. **Program dynamic range grows.** If the Th1/Treg panels have more spread at 48hr (programs more developed), the *same* fractional perturbation projects onto a larger absolute skew — the readout got more sensitive, not the lever stronger. Normalize the skew by the program's dynamic range at each timepoint before comparing.
4. **Target expression grows.** If T-bet is barely on at 8hr, there's little to remove; more to remove at 48hr. Growing effect = target more expressed later, again not "stronger signalling."
5. Genuinely increased pathway engagement — your reading. Plausible, but it's #5 on the list, not the default.

So I'd reframe the claim to "the knockdown's transcriptional consequence on the program is larger at 48hr" and then adjudicate. On your proposed corroboration — checking whether the gene's own expression / pathway activity rises in NTC over time — it's a **fair supporting line but weak, and it's not the one I'd prioritize.** Almost anything Th1-associated rises 8→48 in an activating culture, so "T-bet goes up in NTC" is nearly guaranteed and doesn't discriminate your #5 from #1–#4. The KD-depth check (#1) and the dynamic-range normalization (#3) are far more informative because they directly attack the confounds. Do those; treat the NTC-expression rise as a nice-to-have consistency check, not the corroboration.

## 3d) Before TBX21/SOCS1 go to a druggability step

Several things, roughly in order of how much they'd change my mind:

- **Sledgehammer vs specific shifter (your own project principle).** Pull the global DE-footprint breadth for both. TBX21 should be reasonably specific (lineage TF). **SOCS1 is the one I'd scrutinize** — it's a negative regulator of JAK/STAT, so its KD amplifies cytokine signalling broadly and can have a genome-wide footprint that nonspecifically moves any cytokine/secreted-marker-heavy panel. Also note the mechanistic surprise: SOCS1 restrains both STAT1 (pro-Th1) and STAT5 (pro-Treg/IL-2), so a *toward-Treg* score from SOCS1 KD is not a given — decompose its two arms and make sure it's Treg-up, not just an artifact of globally amplified STAT.
- **Is your Treg pole actually Treg, or just "activated"?** With no TGF-β/iTreg polarization, the Treg-like panel may be riding on IL2RA/CD25, CTLA4, TIGIT, LAG3 — all of which go up on *any* activated conventional CD4 T cell. If so, your axis is "Th1 vs generic activation," not "Th1 vs Treg," and every downstream biological claim shifts. Check that the Treg panel discriminates Treg from activated Tconv (FOXP3, IKZF2), and check how many NTC cells actually express the Treg markers at all.
- **Direction and druggability reality.** Your levers are *loss-of-function*, so they model *inhibiting* the target. TBX21 is a transcription factor — historically undruggable (no pocket; you'd be looking at degraders or upstream nodes). SOCS1 is worse as a therapeutic *target for inhibition*: human SOCS1 loss-of-function causes autoinflammation / immune dysregulation (haploinsufficiency syndrome), so "inhibit SOCS1 to promote Treg" is a red flag — the cell-autonomous marker effect likely won't survive contact with organism-level immunology.
- **Which therapeutic direction are you even chasing?** For anti-tumor immunotherapy you usually want *more* Th1/effector and *less* Treg (relieve suppression) — in which case a "toward-Treg lever" like TBX21-inhibition is a liability, not a hit. For tolerance induction it's the opposite. The same lever flips sign depending on the goal; state the goal before ranking, or you'll shortlist the wrong pole.
- **KD ≠ drug.** CRISPRi is chronic, near-complete, present from the start of activation. A drug is acute, partial, reversible. The 48hr KD phenotype reflects "program never got built"; a drug hitting an established program acutely may do something quite different.
- **Marker RNA ≠ function.** Moving 4 marker genes is not increased suppressive capacity or reduced IFNγ protein. Before druggability I'd want an arrayed KD + functional readout (flow for FOXP3/IFNγ protein, suppression assay).
- **Donor and guide reproducibility.** 4 donors — is TBX21/SOCS1 consistent across all four or driven by one or two? And do independent guides agree (the on-target gold standard, beyond just "guide repressed target")? A hit robust across donors and guides is worth an order of magnitude more at the druggability gate.
- **The 8hr-dominant set looks like the artifact category.** PDIA3 (PDI), DARS1 (tRNA synthetase), COG5 (Golgi) are secretory/translational machinery — their KD plausibly induces ER/secretory stress that nonspecifically perturbs any secreted-marker panel. That smells like the essential-gene sledgehammer your principles warn about, not a specific early lever. IL21R is the one genuinely interesting member. And separately: are the "8hr-specific" hits actually time-specific, or just underpowered at 48hr (fewer cells / weaker KD)? Check eligibility asymmetry before calling anything time-specific.

---

Net: your conservatism on 1 and 2 is right (extend the naive-drop to 8hr); the 0.52 needs a reliability ceiling before it means "time-specific"; and I'd stop using "signalling getting stronger" until the KD-depth and dynamic-range confounds are ruled out — the NTC-expression rise is too weak to carry that claim.

I have the DE_stats and NTC h5ad on the granted paths, so I can actually run the checks that would move this rather than just argue them — the ones I'd prioritize: (i) TBX21/SOCS1 target-KD depth at 8hr vs 48hr, (ii) the two-arm split (Th1-down vs Treg-up) for the top hits, (iii) LOO on the Th1 panel for TBX21, (iv) global DE-footprint breadth to sort shifters from sledgehammers, and (v) the within-timepoint reliability ceiling for the 0.52. Want me to take any of those on? If so, point me at where your frozen panels and the balanced-skew code live (spot repo?) so I reproduce your metric rather than a lookalike.
