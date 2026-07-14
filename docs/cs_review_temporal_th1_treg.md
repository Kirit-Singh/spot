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

---

## Round 2 — CS ran the checks (verified, 2026-07-11)

_CS reproduced the spot metric verbatim (corr 0.520, TBX21 top — same as `explore2.py`), then ran checks (i)–(v) + the reciprocal-pole control. Two came out against its own predictions, flagged plainly. Metrics in `cs_review_metrics.json`._

Done. Here's what the checks actually show — and two of them came out **against** what I predicted last turn, which I'll flag plainly.

## First, the reproduction is clean

I ran your frozen library verbatim (`projection.py`/`masks.py`/`config.py`, poles `A=th1_like` away / `B=treg_like` toward, 30kb mask via `sgrna_library_metadata`). I get **corr(balanced_8, balanced_48) = 0.520** on n=6,620 eligible-both, TBX21 top at 48hr with balanced 1.04 growing +0.72 from 8hr. Same numbers as your `explore2.py`. So everything below is on your metric, not a lookalike.

## (i) KD depth — my top confound is *wrong*, and this helps you

I predicted the effect grows because dCas9-KRAB knocks down deeper by 48hr. It's the opposite. On-target `log_fc` of the target's own gene:
- **TBX21: −4.47 @8hr → −4.04 @48hr** (effect_size −15.9 → −9.2)
- **SOCS1: −1.37 @8hr → −0.60 @48hr** (effect_size −8.7 → −4.6)

The knockdown is *weaker* at 48hr for both, while the projected skew grows. So "effect grows" is **not** a KD-depth artifact — that confound is dead. (Note the mechanism: TBX21 `baseMean` drops 180→51, i.e. T-bet is being turned off by the culture itself between 8 and 48hr, so there's less transcript for CRISPRi to remove.) This materially strengthens the user's "signalling getting stronger" reading against the confound I was most worried about — though panel C below still complicates it.

## (ii) Two-arm split — TBX21 is a Th1 off-switch, full stop

This confirms my prediction hard. TBX21 balanced 1.04 @48hr decomposes into **away-from-Th1 = +2.16, toward-Treg = −0.08**. The entire skew is the Th1-down arm; the Treg arm is *negative*. Calling TBX21 a "toward-Treg lever" is a metric artifact of summing two arms — it does nothing toward the Treg pole. PPP1R14B is the same pattern (away +0.90, toward −0.06). By contrast, 27 of the top-30 have genuine both-arm movement (CMIP toward +0.74, GATB +0.57, HCCS +0.56 are real Treg-up). **Recommendation: rank on `min(away, toward)` or report both arms, never the sum alone — the sum manufactures a Treg lever out of a pure Th1 collapse.** The augmented table has both arms for all 11,210 targets.

## (iii) LOO on the Th1 panel — TBX21 is robust, not a single-gene artifact

With TBX21 masked, the surviving Th1 panel is CXCR3/IFNG/IL12RB2. At 48hr the away arm is +2.16, and dropping any single gene leaves it strongly positive: drop CXCR3 → +1.73, drop IFNG → +1.59, drop IL12RB2 → +3.15. Both CXCR3 (−3.0) and IFNG (−3.3) fall hard on their own. So TBX21 KD coordinately collapses multiple Th1 markers, not one direct target — it survives LOO. That's genuine downstream program regulation, not a panel artifact. (IL12RB2 barely moves, so it's diluting the signal — dropping it *raises* the arm.)

## (iv) Footprint — sorts the field cleanly, and flags your worries

Eligible-both DE-breadth is very skewed (median `n_total_de_genes` = 3, p90 = 144, p99 = 1599). Against that:
- **TBX21**: 403 DE genes (94th pct) — broad, but that's expected for a lineage master TF, and LOO says it's coherent. Acceptable.
- **SOCS1**: **1 DE gene, 0 downstream** (11th pct). This is the surprise — SOCS1 KD is *not* a sledgehammer here; it barely does anything transcriptionally. Combined with what you found (no donor-pair data, single-guide at 8hr), **SOCS1 is far weaker than its ranking suggests** and I would not carry it forward. Its balanced 0.26 rests on almost nothing.
- **Genuine sledgehammers in the top set: HCCS (1231), POLG2 (616), MEN1 (2157)** — mitochondrial/chromatin essential machinery, high both-arm scores that are almost certainly nonspecific stress. Down-weight.
- **8hr-dominant set**: SMARCE1 (3267 DE), ATP2A2 (3260), KIF20A (1780) dominate the largest-shrinking levers — broad-footprint, consistent with the essential-gene/stress category. PDIA3/DARS1/COG5 are more modest (11–27 DE). IL21R (107 DE, real Treg-up arm 0.44) remains the one mechanistically interesting early lever.

## (v) The 0.52 — this is the finding that most changes the story

I decomposed the 0.52 using the 6 donor-pair modalities. **Within-timepoint reliability (two disjoint donor-halves, same time) is only r = 0.227 at both 8hr and 48hr.** That alone means the skew is noisy and the honest ceiling is low. But the apples-to-apples version is sharper and reveals a **donor confound**, not just noise:

| Comparison | r |
|---|---|
| within-time, independent donors, same time | 0.227 |
| cross-time, **same** donors (AB@8 vs AB@48) | **0.48** |
| cross-time, **independent** donors + independent time | **0.169** |
| main screen (pooled 4-donor, 8 vs 48) | 0.520 |

The pooled 0.52 is high **because donor identity is shared across the two timepoints** — same 4 donors at 8 and 48hr, and donor-of-origin is a large, time-stable component of each target's skew. When you break the shared donor (independent donors *and* independent time), cross-time r falls to **0.169 — at or below the within-time noise floor of 0.227.** So the correct reading is the reverse of "partly shared, partly time-specific": **once you remove donor, there is very little reproducible cross-time signal at all — neither strongly shared nor cleanly time-specific.** The hit level says the same thing: **only 2/25, 8/50, 18/100 top toward-Treg levers overlap between 8 and 48hr (~16%)**, barely above chance. Any per-target "grows / is 8hr-specific" claim below the very top of the list is not supported by these data.

**Bottom line for 3b/3c: I would not say the lever set is "partly shared, partly time-specific" — the number is dominated by donor, and reproducibility is low. The safe claims are the top-of-list ones (TBX21 grows; the SMARCE1/ATP2A2 stress-levers shrink); the middle of the ranking is noise.** And "signalling getting stronger" survives the KD-depth confound but not the reproducibility one — for TBX21 specifically it holds at the individual-gene level (T-bet turns off in culture, the Th1 arm widens), but you can't generalize it across the lever set.

## The reciprocal-pole control — it failed, informatively

This is the check I'd weight most for the whole framing. On a toward-Th1 ranking, the Treg master regulators do **not** come out on top: **FOXP3 ranks 6317/6620** (near the bottom — its KD if anything reads slightly toward-Treg), IL2RA 1648, CTLA4 3522. And FOXP3 was genuinely, strongly knocked down (own log_fc −4.3 @8hr, −3.4 @48hr, significant) — so this isn't a failed-KD excuse. **Knocking out the Treg master TF does not push cells toward Th1 in this data.** That means your axis is **not a reciprocal Th1↔Treg see-saw** — it's largely a *Th1-program readout* with a Treg-flavored label. Which fits everything else: no TGF-β/iTreg polarization in this culture, so there isn't a real Treg program for FOXP3 to be the master of. The Treg "pole" is riding on activation-associated markers (CTLA4/IL2RA/TNFRSF18 all go up on any activated Tconv). I'd stop describing this as a Th1↔Treg axis and call it what it is: a **Th1-program dial**, with the "Treg" direction meaning "low Th1 / generically activated," not "committed Treg."

## Net recommendations

1. **Report both arms, rank on `min(away,toward)`.** Drop TBX21 and PPP1R14B from the "toward-Treg lever" list — they're pure Th1 off-switches (the metric summed them into a Treg score).
2. **Retire "partly shared, partly time-specific."** The 0.52 is a donor artifact; donor-independent cross-time r ≈ 0.17 ≈ noise. Only top-of-list temporal claims (TBX21↑, SMARCE1/ATP2A2↓) are defensible.
3. **Reframe the axis as a Th1 dial, not Th1↔Treg** — the reciprocal control (FOXP3 KD doesn't push toward Th1) shows the Treg pole isn't a real committed-Treg program in this culture.
4. **Drop SOCS1** — 1 DE gene, no downstream, no donor data, single-guide at 8hr. Its ranking is not backed by an effect.
5. **TBX21 is a valid *Th1 off-switch* hit** (survives LOO, donor+guide concordant per your run, KD is real). But it's a TF (historically undruggable by inhibition), and its "direction" is *reducing* Th1 — which is the wrong sign if the immunotherapy goal is anti-tumor effector enhancement. Confirm the therapeutic direction before it goes to druggability.

Deliverables:
- [spot_th1treg_review.png]({{artifact:6191b933-6b7c-4915-bbff-a190cc043ca3}}) — the four checks (TBX21 arms, KD depth, 0.52 decomposition, hit-level overlap)
- [spot_th1treg_review_table.csv]({{artifact:20052223-b429-4e1c-aca4-6c25d72f2b90}}) — all 11,210 targets × both timepoints with arms, KD depth, footprint, eligibility
- [spot_review_metrics.json]({{artifact:2763f1e5-1a1c-4f2d-acc2-d92c9c1a0c19}}) — the headline numbers

One caveat on my own reliability estimate: the within-timepoint ceiling uses 2-donor halves, so it's a floor on the true 4-donor reliability. Even Spearman-Brown'd up it only reaches ~0.36–0.41, still well under 0.52 — but if you want the airtight version, a per-donor (not per-pair) leave-one-out would nail the ceiling exactly. Want me to run that, or take the "report both arms + Th1-dial reframe" into a short methods note for the stage-2 writeup?
