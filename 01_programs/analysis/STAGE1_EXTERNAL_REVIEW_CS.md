# spot Stage-1 — Claude Science reconciliation of the external assessment (2026-07-10)

_Independent Claude Science read of the external Stage-1 review (EXTERNAL_ASSESSMENT.md), done
by reading the deployed code AND empirically reproducing the contested numbers from the actual
data on tcedirector. Bottom line: the external reviewer is mostly right about the machinery; the
earlier "lockable" memo was a scientific-judgment review that didn't execute the implementation.
One external claim (blocker #1's causal direction) is wrong. Verbatim below._

---

I've now read all six code files and both memos, and independently reproduced the contested numbers from the actual data. Here is my honest take.

---

# Independent assessment of the external review of spot Stage-1

I read the deployed code (`stage1_pipeline.py`, `label_clusters.py`, `cluster_scores.py`, `verify_reproduce.py`, `reproduce.sh`, `render_notebook.py`), and — because the objects are on disk — I reconstructed the scoring pipeline from the shipped matrix and reran it. My reimplementation reproduces the committed reference cell-for-cell (func and ds counts both exact on the 40k overlay), so when I report a number below, it comes from code that provably matches the deployed pipeline, not from a paraphrase.

Bottom line first: **the external reviewer is mostly right about the machinery, and the two of you are not really in contradiction — you were reviewing different things.** The earlier "lockable" memo (`REVIEW_MEMO.md`) is a *scientific* review that assumed the pipeline was implemented as described; the external reviewer actually audited the implementation and the release artifacts. Most of what they found is real. But their single most alarming claim — that blocker #1 *manufactures* significant CTL calls — is not just overstated, it points the wrong way, and I can show that from the code.

## The three you flagged

### Blocker #1 — non-exchangeable null (residualized observed vs. raw null): **valid as a bug, wrong on direction/severity**

What the code actually does, confirmed: the observed CD4-CTL score is residualized against an activation score via `np.polyfit(S_act, Rf[:,ctl], 1)` (lines ~204–205), and then the 500-permutation null draws *raw* random panels (line ~218) with no residualization. So observed and null undergo different transformations. **The structural criticism is correct** — this is not a clean permutation test, and presenting the resulting q as a per-lineage FDR is not defensible. The reviewer is right that it needs fixing, and right that "size- and expression-matched" oversells what the random panel draw actually matches (it matches size; the random panel's own bin composition floats).

But their stated *consequence* — that this "can manufacture significant residual CTL calls" — is backwards, and this matters because it's the headline that makes #1 a blocker. I measured it three ways on the full 396k:

- Raw observed vs. raw null (no residualization): **42.2%** of cells reach p<0.05.
- **As-coded** (residualized observed vs. raw null): **25.2%**.
- Correct null (residualize the null panels the same way): **26.7%**.

Residualizing the observed score drops its mean from +0.227 to ≈0. Comparing a mean-0 observed score against a raw null (also ≈0-mean for random panels) lands *close to* the properly matched null and slightly **more conservative**. When I run the full pipeline with a correctly residualized null, gated CD4-CTL calls go **up**, from 573→664 on the 40k (5,936→6,801 on the full population) — about +16%. So the mismatch is real but it *suppresses* CTL calls, it does not inflate them. The reviewer asserted a direction they did not test; the honest statement is "invalid null calibration, effect is mildly conservative for CTL, magnitude ~90 cells on 40k." **Verdict: the finding is valid (it's a genuine methodological defect worth fixing), but the severity framing is overstated and the causal direction as written is wrong.**

One thing the reviewer gets exactly right and you should not lose in the direction argument: because CD4-CTL is the *only* one of the seven lineages that is residualized, it alone is tested against a null on a different scale than its observed score, while the other six are internally consistent. That asymmetry is untidy regardless of sign.

### Blocker #2 — Treg guaranteed by construction; state labels leak condition: **valid**

Confirmed line by line in `label_clusters.py`. The Treg cluster is chosen as `max(..., key=lambda cl: Z[cl]["Treg"])` over eligible clusters with no absolute threshold, no null, and no "no-Treg" branch. I tested the failure mode the reviewer describes: I set every cluster's Treg z-score to −5 (i.e., simulate a dataset with no Treg signal at all) and reran the rule — it still labels a cluster "Treg" (cluster 12, with a fake z of −4.99). **A Treg cluster exists unconditionally.** That is precisely the reviewer's point, and it is correct.

The condition-leakage claim is also correct: step 3 assigns Naive/Memory vs. Activated using `cond[cl].get("Rest",0) > 0.5` — i.e., a cluster's *experimental timepoint composition* decides a label that the UI presents as a transcriptional state. That is leakage of the design variable into the annotation. And the differentiation axis (`Rd.argmax(1)`) is always assigned with no unresolved option, as claimed.

I'll add the nuance the reviewer omits, because it partly explains the earlier memo: the *actual* winning cluster (cluster 1) is a genuinely strong Treg candidate — Treg z = 1.61, and it's the only cluster that is Treg-high while not strongly activated. So on *this* dataset the forced rule happens to pick a defensible cluster. The problem the reviewer identifies is that nothing in the rule *guarantees* that; the safety comes from the data, not the method. For a pipeline meant to generalize and to be "locked," that's a real blocker. **Verdict: valid.**

### Major #4 — "CP10k vs. median gives byte-identical calls" is false: **valid, and the reviewer's numbers are exactly right**

This is the one you most wanted checked, and it's the cleanest result. First the math: `normalize_total` sets each cell's total to a target `T` (median ≈ 9,819 for the authors' default; 10,000 for CP10k), so the two differ by a global scalar α = 10000/9819 = 1.0184 applied *before* log1p. Since log1p(α·x) is not a global additive or multiplicative constant on the log-scale values, `score_genes` (panel mean minus bin-matched control mean) and the 25-bin expression-quantile assignments are **not** invariant. The reviewer's "log(1+αx) is not a global shift" is correct.

Then the empirics. The file on disk named `ntc_clustered.cp10k.bak.h5ad` is actually **byte-identical to the median object** — it is mislabeled and is *not* a CP10k matrix (worth fixing, and it may be why someone earlier believed the calls were identical — they may have "compared" two copies of the same object). So I reconstructed a true CP10k matrix exactly from the shipped `.X` via `log1p(α·expm1(X))`, held cells/genes/Leiden/seed fixed, and reran. Results:

- **394 / 40,000 functional calls changed.**
- **633 / 40,000 differentiation calls changed.**
- No-call 33,004 → 33,056; Th1 4,550 → 4,478; Treg 1,051 → 1,097.

These match the reviewer's reported numbers **exactly**, down to the cell. So the "byte-identical calls" claim is empirically false, the reviewer's math is right, and the direction/magnitude they report is right. **Verdict: valid.** The correct framing is the reviewer's: freeze median normalization as part of the method and present alt-normalization as a sensitivity analysis (it moves ~1% of calls — small, but not zero, and definitely not "byte-identical").

## The other six

**Major #3 (blocker) — embedding not paper-exact or publicly regenerable: largely valid, one part I can't check.** I confirmed the shipped h5ad has **empty `.uns`, `.obsm`, `.layers`, `.obsp`, `.varm`** — there is no stored latent representation, no UMAP coordinates, no provenance manifest, nothing to audit the embedding from. I also confirmed the subsample is **exactly 33,000 per donor×condition (4 donors × 3 conditions = 396,000)**, i.e., a quota-balanced sample, *not* the authors' NTC population weighting. So "paper-exact" and "reproduces Suppl Fig 2" are not supportable as written, and displayed percentages are prevalences in an equal-weighted sample. The specific scVI hyperparameters the authors used vs. what `run_scvi_embedding.py` encodes — the reviewer says several were omitted — I did not rerun the GPU job to check, and notably `run_scvi_embedding.py` itself says the hyperparameters were transcribed from a user instruction and the source notebook "was NOT fetched, opened, or verified." So the "paper-exact" claim was never actually grounded in the authors' code by the pipeline's own admission. **Verdict: valid on auditability and sampling; the specific param-diff is plausible but I can't independently confirm the authors' true config.**

**Major #5 — "byte-reproducible / 100% cell-for-cell" is false: valid.** I built a **zero-cell** overlay carrying the correct aggregate `nomen_counts` metadata and ran `verify_reproduce.py` against it — it **passed, exit 0, "match 100.0%."** The verifier only compares aggregate count dictionaries (`overlap()` of `nomen_counts` + `n_total_cells`/`n_shown`); it never checks per-cell membership or barcode identity, so "cell-for-cell" is not what it verifies. I also confirmed `reproduce.sh` emits `stage01_umap_seed.emitted.json` and then `cp`s it to `data/stage01_umap_seed.json` *outside* the gated step — the same point your own earlier memo (`REVIEW_MEMO.md`) already flagged. **Verdict: valid.**

**Major #6 — Masopust used as confirmation, not framework; UI language crosses into functional identity: valid, and this is a judgment/wording issue more than a code bug.** The code uses short custom transcript panels, drops CD25/CD127, and treats non-detection (e.g. `CD27==0`, `IFNG==0`) as negative-marker evidence — on 3′/Flex data where dropout is heavy, absence-of-detection is weak evidence of absence. Calling the outputs "real CTL calls" / "FDR rejects real Tregs" overstates what a transcriptional compatibility score can establish. Your own earlier memo reached the same biological conclusion (the "Treg" is most likely activation-induced FOXP3 at 48h, not natural Treg) and even ran follow-ups confirming it. So this isn't a contested point between the two reviews — both agree the biology needs a suggestive-language qualifier. **Verdict: valid.**

**Major #7 — shipped artifacts internally inconsistent: valid, every number reproduces.** I confirmed: legacy `funcc` disagrees with `func` for **13,606** cells and `dsc` vs `ds` for **11,333**; the records file (`stage01_cell_records.json`) disagrees with the overlay on **1,693 functional + 1,917 differentiation** labels and contains **40,002** entries vs the overlay's 40,000; and `meta.nomen_method` still describes the retired absolute-floor method ("floor 0.20/margin 0.06"). `render_notebook.py` indeed does **not execute anything** — it parses the trailing `#`-comment block of each `# %%` cell as "captured output," so the UI's "full executable notebook — every code cell and output" is false; those outputs are hand-written comments in the source. **Verdict: valid.**

**Major #8 — a stranger can't install/reproduce: partially valid, partially unverifiable here.** There is **no `requirements.txt`, lockfile, Dockerfile, or environment.yml** anywhere in `spot-design/` — I searched. That alone supports "cannot reproduce from documented requirements." I confirmed the shipped `obs` has **17 columns, not 18** (matches the reviewer; the HF card is wrong). The specific `pip install` ResolutionImpossible (numpy==2.3 vs pandas==2.2→needs numpy<2) and the RAM/runtime numbers live in a README I don't have (no README.md exists in the granted `spot-design/` tree), so I can't confirm those two specifics — though for what it's worth, my own faithful rerun peaked at ~24.6 GB RSS, which flatly contradicts any "runs on 16 GB / 3 min" claim and supports the reviewer's ~20 GB / ≥24 GB-required direction. **Verdict: valid on the checkable parts (no lockfile, 17 vs 18 cols, RAM); the exact dependency-clash text is unverified for lack of the README.**

**Minor #9 — privacy/licensing absolutes contradicted by history: valid, low stakes.** I didn't audit the HF revision history or the license text diff (those are outside the code and I'd be taking the reviewer's word on published-history artifacts). The one concrete, checkable claim — coded donor/library IDs in the object — is true: the `obs` carries `donor`, `donor_id`, `lane_id`, `guide_id`, so "anonymous" is the wrong word; "coded/linkable" is right. **Verdict: valid as far as I can check; appropriately filed as minor.**

## Reconciliation — why the earlier read said "lockable"

This is the part that matters most for your calibration, so I'll be candid.

**The two reviews don't actually contradict each other on facts — they contradict on scope and on one word ("lockable").** Reading `REVIEW_MEMO.md`, the earlier reviewer did something specific and limited: they *reproduced headline numbers from the emitted overlay and the marker sidecar* and evaluated the *scientific judgment calls* (is the cluster-Treg the right unit? is dropping CD25 fair? is 82% no-call honest?). On those questions the earlier memo is genuinely good — its biological instincts are sound, it caught the activation-induced-FOXP3 problem, it ran real follow-ups, and it even flagged the `reproduce.sh` staging gap and the stale brief/log/mirror. It was not naive.

What the earlier read **missed** is exactly the two things you can only catch by executing the implementation rather than reading its described behavior:

1. **Blocker #1 (the null mismatch) is invisible from the overlay.** You cannot see it in the emitted counts, the sidecar, or the numbers the notebook prints — those all look internally consistent because they *are* the output of the (buggy) pipeline. To find it you have to read the null-generation loop next to the residualization line and notice they operate on differently-transformed statistics. The earlier memo explicitly says it "reproduced every headline number without re-running the heavy compute" — that method, by construction, cannot detect a bug that is baked identically into both the number and its reference. It even praised the FDR floor as "a genuine improvement" and "doing real work," which is true *relative to the old absolute threshold* but sidesteps whether the permutation semantics are valid. That's the blind spot: it graded the null against its own output.

2. **Blocker #2's "forced by construction" is invisible unless you perturb the inputs.** On this dataset the argmax rule picks a real Treg cluster, so every number it produces looks right. The defect only shows up when you ask "what would this rule do if there were no Tregs?" — a counterfactual the earlier memo never ran. Its judgment-call #1 actually *defends* the cluster-as-target choice on the merits (correctly, for a Stage-2 target), which is a different question from "is the selection rule falsifiable." The reviewer answered "is this a good target?" and skipped "could this rule ever *not* find a target?"

The honest one-line reconciliation: **the earlier review validated the science on the assumption the code did what it said; the external review audited the code and the release, and the code has two genuine statistical defects plus a pile of real reproducibility/labeling problems.** The earlier "lockable" was a scientifically-informed but implementation-trusting read. On the evidence I can reproduce, **the external reviewer's "not lockable" is the correct call** — not because the biology is wrong (both reviews actually agree the biology is roughly right and honestly caveated), but because a pipeline you intend to *lock* cannot ship with an invalid permutation null presented as an FDR, a target that exists by construction, a verifier that passes zero cells at "100%", and no way to regenerate or audit the embedding.

Where I'd temper the external reviewer: **blocker #1's impact is smaller and opposite-signed** to how theyframed it (fixing the null adds ~16% more CTL calls; it does not manufacture them), and CD4-CTL is not the Stage-2 target anyway, so the *scientific* stakes of #1 are lower than "blocker" suggests even though the *methodological* defect is real. And **major #4 moves ~1% of calls** — real, worth fixing, fatal to a "byte-identical" claim, but not something that overturns the headline biology. So I'd rank the true release-blockers as: **#2 (forced Treg) > #3 (unauditable/non-regenerable embedding) > #1 (invalid null, but conservative and off-target) > #5/#7 (verifier + artifact inconsistency)**, with #4/#6/#8/#9 as must-fix-before-lock but not conceptual blockers.

Files saved:
- [extreview_verification.csv]({{artifact:0e2dc874-5ffa-47a5-94b0-fcaeaa816b54}}) — all 20 checked claims with what the code does, my independent result, and the verdict note.
- [extreview_verification_summary.json]({{artifact:4b82f8df-1763-42bc-ad69-5e7b3b82f489}}) — machine-readable summary of the key reproduced numbers (394/633 CP10k changes, 573→664 CTL null-fix, α=1.0184, cp10k.bak-is-median flag).

A caveat on my own limits, in the same spirit: I did not rerun the ~1h GPU scVI/Leiden embedding, so I take the raw→latent→cluster step as given (the Leiden labels I used are the shipped ones); and I could not check the README-specific text (no README in the granted tree) or the HF revision history. Everything else above is reproduced from the actual deployed code and data.
