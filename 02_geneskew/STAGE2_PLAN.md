# spot Stage-2 — design plan: perturbations that skew induced-Treg(48h) → inflammatory Th1(8h)

_Design memo. No heavy compute run. Grounded in the Stage-1 chain
(`stage1_pipeline.py`, `cluster_scores.py`, `label_clusters.py`,
`verify_reproduce.py`, `reproduce.sh`), the Stage-1 review
(`REVIEW_MEMO.md`), and the Marson dataset layout under
`/mnt/tcenas/datasets/raw/public/marson2025_gwcd4_perturbseq/`._

---

## 0. What Stage-2 is, in one paragraph

Stage-1 built a nomenclature map of the **non-targeting-control (NTC)** CD4
cells only, and established the target: the "Treg" cluster is **activation-induced
FOXP3⁺ regulatory-like cells at 48 h**, not natural Tregs (FOXP3⁺CTLA4⁺ rises
~26× Rest→48 h while Helios/IKZF2 stays flat — Follow-up 1 in `REVIEW_MEMO.md`).
The only coherent inflammatory effector skew in the reference is **Th1, best
expressed in the 8 h-activated compartment** (32.2% of it). Stage-2 turns to the
**perturbation** arm — ~3,341 gene knockdowns (CRISPRi), across Rest/Stim8hr/Stim48hr,
4 donors — and asks: *which knockdowns push cells off the induced-Treg(48h) state and
toward the Th1(8h) inflammatory program?* Concretely, which knockdowns **de-repress
the inflammatory Th1 program and reverse induced-FOXP3**. The deliverable mirrors
Stage-1's reproducible chain: notebooks + scripts + gated outputs, plus a program
registry that later stages reuse.

The whole design rests on one directional object — a signed **"induced-Treg → Th1"
program axis** in gene space — and one cheap primary metric: the **projection of each
perturbation's genome-wide DE vector onto that axis**. Everything else is
de-confounding, power gating, and reproducibility scaffolding around those two things.

---

## 1. Defining transcriptional PROGRAMS and quantifying change between clusters

### 1.1 What a "program" is, so it is reusable across stages

A **program** is a named, signed, weighted vector over a fixed gene universe, plus
its provenance. Nothing more. Stage-1's marker panels (the `FUNC`/`DS` dicts) are the
degenerate case: binary weights, hand-curated. Stage-2 generalizes to data-derived
continuous weights but keeps the same primitive, so any stage can load a program and
**project new data onto it** by a dot product. The registry entry (schema in §4) is:

```
program_id, display_name, method, gene_universe_id,
weights: { gene_symbol: signed_weight },   # sign convention explicit
provenance: { source_cells, contrast, params, seed, code_hash },
sign_convention: "positive = <state A>, negative = <state B>"
```

This is what makes a program reusable: it is decoupled from the embedding and the
cell set that produced it. A Stage-3 dataset with a different gene panel can still
project onto the intersection of gene universes.

### 1.2 The three candidate methods, and what I recommend

**The central design question is how to define the induced-Treg → Th1 axis.** Four
primitives are on the table; the tradeoffs matter:

1. **Marker panels (Masopust et al.), Stage-1 style.** *Interpretable, cross-stage
   stable, tiny.* But sparse and 3′-dropout-sensitive (FOXP3 detected in only 27.5%
   of cluster-Tregs). Good as an **anchor / sanity readout**, too thin to be the sole
   directional axis.
2. **NMF on the NTC reference.** *Unsupervised, yields coherent co-expression
   programs with non-negative, additive loadings — naturally "program-like."* But NMF
   factors are not guaranteed to align with the Treg↔Th1 contrast; you must post-hoc
   identify which factor is the inflammatory one, and factor identity drifts with k and
   initialization. Best used to **discover and register reusable programs** (e.g. an
   "inflammatory/IFN-response" factor, a "regulatory" factor), not to define the
   directional metric.
3. **scVI-based differential expression (`scvi-tools` skill available).** The Stage-1
   scVI model already exists (`/mnt/tcenas/models/spot_scvi`). scVI/scANVI Bayesian DE
   between the induced-Treg-48h cluster and the Th1-8h region gives a **batch-corrected,
   donor-aware** signed effect per gene. *Strong* — it handles the 4-donor batch
   structure the same way the embedding did. Cost: it is model-tied and less transparent
   than a plain contrast.
4. **Pseudobulk cluster-contrast DE (DESeq2/edgeR with donor as covariate).**
   Directly computes the signed logFC between the two cell states on the NTC cells,
   donor-controlled. *Most transparent and most directly "the axis we want."* Cost:
   needs a heavy cell-level load; less principled batch handling than scVI.

**Recommendation — a layered definition, primary axis + anchors + discovery:**

- **Primary axis** = the signed induced-Treg-48h **vs** Th1-8h contrast, computed on
  the NTC reference cells, **donor-controlled**. Compute it two ways — scVI DE (3) and
  pseudobulk DESeq2 (4) — and keep the axis only on genes where the two agree in sign;
  this is a cheap robustness gate and gives an honest weight vector. Sign convention:
  **positive = Th1-inflammatory, negative = induced-Treg**.
- **Anchor programs** = the Stage-1 interpretable panels, reused verbatim:
  *induced-Treg program* {FOXP3, CTLA4, CCR8, TNFRSF18, IKZF2} and *Th1-inflammatory
  program* {TBX21, CXCR3, IFNG, IL12RB2, (STAT1/IFN-response)}. These give an orthogonal,
  human-readable readout and let us report "reverse-FOXP3" separately from "de-repress-Th1."
- **Discovery programs (optional)** = NMF factors on the NTC reference, registered by
  id, used to interpret *what else* moves and to seed future stages.

### 1.3 Quantifying change between clusters (induced-Treg-48h vs Th1-8h)

Two complementary quantities, both saved:

- **Signed per-gene contrast** (the axis itself): logFC + z-score + q-value per gene,
  induced-Treg-48h vs Th1-8h, donor-controlled. This *is* the program axis.
- **Program-level scores per cluster**: score every cell on the anchor programs with
  the Stage-1 permutation-FDR machinery (reused verbatim), then summarize by cluster ×
  timepoint. This restates Stage-1's finding in program terms and validates that the
  axis separates the two clusters as expected (positive controls for the whole method).

**Why the axis lives in the DE gene universe.** The perturbation scoring (§2) works in
the `DE_stats` 10,282-gene space. The axis must therefore be **restricted to the
intersection** of the reference gene universe (18,130) and the DE universe (10,282),
and we must verify the load-bearing genes (FOXP3, CTLA4, CXCR3, TBX21, IFNG) survive
that intersection with measurable baseline — flagged as risk R3.

---

## 2. Core question: scoring the SKEW induced by each knockdown

### 2.1 The primary metric — a directional program-shift on the DE vector

For each perturbation *X* in a given condition, `DE_stats` gives a genome-wide signed
effect vector **δ_X** (use `zscore` = logFC/lfcSE as the default; logFC as a sensitivity
check) over the shared gene universe. With the axis weight vector **w** (§1.2, unit-normalized):

- **SkewScore(X) = δ_X · ŵ** — the projection of the knockdown's transcriptional effect
  onto the induced-Treg→Th1 axis. **Positive = the knockdown pushes the transcriptome
  toward Th1-inflammatory / away from induced-Treg** (the wanted direction).
- **Decompose it** into an **inflammatory-up component** (projection onto the Th1
  anchor program) and a **Treg-down component** (projection onto the induced-Treg anchor,
  sign-flipped; and, called out separately, the **FOXP3 and CTLA4 logFC** themselves).
  Reporting both lets us distinguish a knockdown that only de-represses Th1 from one that
  actually reverses induced-FOXP3, and rank on the combination.

Primary screen is run in **Stim48hr** (where the induced-Treg state exists);
Stim8hr and Rest are scored too, as specificity context (a real hit should act where
the induced-Treg program is present).

### 2.2 Separating specific program-shifters from essential-gene sledgehammers

This is the review's standing principle, and the metric must build it in:

- **Cosine, not just dot product.** A pan-essential knockdown produces a huge broad δ_X
  that projects onto *everything*. Report **specificity = cos(δ_X, w) = SkewScore /
  ‖δ_X‖** alongside the raw projection. A specific program-shifter has **high cosine**;
  a sledgehammer has **high ‖δ_X‖ but low cosine**. Rank on cosine-weighted skew, and
  show both axes in the output so the two classes are visually separable.
- **Breadth covariate.** Carry `n_total_de_genes`, `n_downstream`, `n_up/n_down` from
  `DE_stats` as an explicit breadth flag. Genes with a very broad footprint get a
  **"broad-DE-footprint" tag**, not silent inclusion.
- **Housekeeping/essential annotation.** Tag ribosomal/spliceosomal/core-essential
  targets (and cross-check against DepMap common-essential in §3) so a viability artifact
  is never reported as a program-shifter.

### 2.3 Power gating — say "insufficient power" out loud

Never rank a knockdown the data cannot support. Gate on `DE_stats.obs`:

- `ontarget_significant == False` or `ontarget_effect_category == "no on-target KD"`
  → **the perturbation didn't knock the gene down**; excluded, reported as
  "no on-target KD," not as a null result.
- `low_target_gex == True` (unreliable KD estimate), small `n_cells_target`,
  `single_guide_estimate == True` → **insufficient power** tier, reported separately and
  never mixed into the ranked hits.

This mirrors the Stage-1 discipline (the permutation-FDR floor that killed the Th2
artifact) — underpowered knockdowns are labeled, not scored.

### 2.4 Reproducibility of a hit (built into the dataset)

The dataset ships per-guide and per-donor DE precisely for this:

- **Cross-guide agreement** — require the skew to hold for both guides
  (`guide_correlation_signif`; or recompute SkewScore on `by_guide` modalities and
  require concordant sign).
- **Cross-donor agreement** — require the skew to replicate across donor pairs
  (`donor_correlation_hits_*`; or SkewScore on `by_donors` modalities). A hit driven by
  one donor is demoted.

### 2.5 Calling significance, not just ranking (3,341-way multiplicity)

Ranking alone over 3,341 perturbations invites false positives. Build an **empirical
null** for SkewScore from the **NTC guides** (many NTC pseudobulks exist): their
projection distribution is the "no real perturbation" null. Per-perturbation empirical
p = tail probability against the NTC-guide null, BH-adjusted across the screen. This is
the natural analogue of Stage-1's permutation-FDR floor, and it is honest about
multiplicity.

### 2.6 Sign bookkeeping and positive controls

These are **CRISPRi knockdowns** (target repressed). So a top positive hit is a gene
that **normally maintains the induced-Treg state / represses inflammation**. Anchors:

- **FOXP3 knockdown** should score strongly positive (reverses induced-FOXP3) — the
  canonical positive control that fixes the sign.
- Knockdowns of the induction axis (e.g. TGFβ/SMAD, IL2–STAT5 nodes) are expected
  supporting positives.
- **NTC guides** score ≈ 0 (negative control; also the null in §2.5).

If FOXP3 KD does not land positive, the sign or the axis is wrong — this is the
first gate before any ranking is trusted.

### 2.7 Two scoring views — cheap primary, expensive confirmatory

1. **Transcriptional-shift (primary, cheap):** the §2.1 projection on `DE_stats`.
   Runs over all 3,341 perturbations in minutes, no cell-level load. This is the screen.
2. **Compositional-shift (confirmatory, expensive, shortlist only):** for the top hits,
   go to the cell-level guide-assigned files and test whether knockdown of *X* actually
   **moves cells out of the induced-Treg cluster** toward the Th1 region in the scVI
   embedding (a change in cluster/neighborhood composition, not just mean expression).
   This is the direct phenotype but costs a heavy load (12 × ~150 GB), so it is reserved
   for a shortlist — the same "run heavy once" discipline as Stage-1's embedding step.

The primary metric answers "does the average transcriptome shift along the axis"; the
confirmatory view answers "do cells actually leave the induced-Treg state." Both are
reported; only the shortlist gets the second.

---

## 3. Handoff to DepMap

### 3.1 What we hand off

A **ranked candidate table**, GRCh38, one row per gene, carrying: HGNC symbol +
Ensembl ID; desired direction (KD de-represses inflammation); SkewScore, its
inflammatory-up / Treg-down decomposition, and cosine-specificity; the power tier and
cross-guide/cross-donor reproducibility flags; and the breadth/essential tags. We hand
off **genes with an explicit direction and a specificity score**, not a bare list —
DepMap is used to triage that table, not to re-rank it.

### 3.2 How DepMap is framed — and its honest limits

DepMap is a **viability CRISPR screen in ~1,100 cancer cell lines**, not primary CD4
T cells. So it cannot validate an immune phenotype. Its three legitimate uses here:

1. **Essentiality / safety triage (primary use).** For each candidate compute the
   DepMap gene-effect (Chronos) profile and the **common-essential** flag. A
   pan-essential gene is a sledgehammer whose "program shift" is likely a viability
   artifact and whose knockdown would be broadly toxic — **demote or exclude**. This is
   an *orthogonal* corroboration of the §2.2 cosine/breadth filter, from an independent
   dataset, and it is the most defensible DepMap use given the context gap.
2. **Lineage-stratified dependency.** Restrict to **blood/lymphoid lineage** lines
   (T-ALL, lymphoma) and ask whether the candidate is *selectively* required there. This
   is context-framing: it is the closest DepMap proxy to a T-lineage dependency, stated
   as a proxy, not as primary-cell truth.
3. **Co-essentiality / pathway partners.** Genes that share a candidate's dependency
   profile nominate pathway partners and mechanism — useful for interpreting *how* a hit
   maintains the induced-Treg state, and for expanding the candidate set to co-functional
   genes.

Every DepMap statement carries the qualifier: **cancer lines ≠ primary CD4; DepMap
triages essentiality and mechanism, it does not confirm the skew phenotype.**

### 3.3 Access — a real dependency to resolve

**There is no DepMap skill or MCP connector in the catalog** (confirmed by search;
closest are cBioPortal `mcp-cancer-models` for genomics and STRING `mcp-protein-annotation`
for interaction networks — neither is the CRISPR gene-effect matrix). So DepMap gene-effect
data must come from a **DepMap portal / figshare download behind a network grant**
(`depmap.org` / the public release CSVs), loaded once and cached as an artifact. Fallbacks
if that grant is declined: **STRING** (available now) covers the co-essentiality-like
pathway-partner use, and **cBioPortal** (available now) covers lineage genomics — but
neither replaces the essentiality triage, which genuinely needs the DepMap matrix. This
is flagged as risk R6 and should be settled before Part 3 is executed.

---

## 4. Reusable-artifact plan — mirroring Stage-1's chain

### 4.1 The chain, one file per role (parallels Stage-1 exactly)

| Stage-1 file | Stage-2 analogue | role |
|---|---|---|
| `run_scvi_embedding.py` (heavy, cached) | *(reused as-is — Stage-2 does not re-embed)* | GPU embedding, run once |
| `cluster_scores.py` (one 14 GB load → JSON) | `define_programs.py` (one heavy load → `stage02_programs.json`) | build the axis + anchor + NMF programs; the single expensive, offline-tunable load |
| `label_clusters.py` (no load, fixed rule → JSON) | `score_perturbations.py` (no cell load; reads programs + `DE_stats` → `stage02_perturbation_scores.json`) | the fixed scoring/gating rule; ranked table |
| `stage1_pipeline.py` (`# %%` notebook, emits overlay) | `stage2_pipeline.py` (`# %%` notebook, emits the ranked-knockdown overlay) | the narrative provenance notebook + emit step |
| `verify_reproduce.py` (gate on emitted counts) | `verify_reproduce_stage2.py` (gate on top-N hits + positive-control scores) | reproducibility gate |
| `reproduce.sh` | extend the same script with `[6..]` Stage-2 steps | one-command regeneration |
| `render_notebook.py` | reused as-is | notebook → HTML |

**Determinism discipline, reused verbatim:** a fixed `SEED` for the NTC-null and any
sampling; a committed `REFERENCE` block in `verify_reproduce_stage2.py` (top-N hit ids,
FOXP3-KD rank, NTC≈0 check) that the pipeline's own emitted numbers must match, exiting
nonzero on drift. Same gate philosophy that caught the Stage-1 Th2 artifact.

### 4.2 Output schemas

- **`stage02_programs.json`** — the program registry (§1.1 schema): axis + anchors +
  NMF factors, each a signed weight vector over the named gene universe, with provenance
  (source cells, contrast, params, seed, code hash). *This is the cross-stage-reusable
  artifact.*
- **`stage02_perturbation_scores.json`** — one record per perturbation × condition:
  `{target_gene, ensembl_id, condition, skew_score, inflammatory_up, treg_down,
  foxp3_logfc, ctla4_logfc, cosine_specificity, breadth (n_total_de_genes),
  power_tier, ontarget_effect, guide_concordance, donor_concordance, emp_p, q, rank,
  flags:[sledgehammer|underpowered|no_ontarget_kd]}`. The ranked screen output.
- **Overlay JSON** for the frontend — mirrors `stage01_umap_seed.json`: the ranked
  knockdowns with the two-axis (skew vs specificity) coordinates, decomposition, and
  flags, plus `meta.nomen_counts`-style summaries and an `emitted_at` stamp.
- **DepMap handoff table** (§3.1) as CSV + the DepMap-annotated result once §3.3 access
  is settled.

### 4.3 What is genuinely SHARED vs STAGE-SPECIFIC

**Shared (promote to a small `spotlib` common module, imported by both stages):**
- The **vectorized `score_genes` + permutation-FDR floor** machinery (currently inline
  in `stage1_pipeline.py`) — Stage-2 uses it for per-cell anchor scoring and for the
  NTC-null.
- **Gene-ID / symbol harmonization** (GRCh38; symbol ↔ Ensembl; gene-universe
  intersection) — MyGene is available (`mcp-genes-ontologies`) for the mapping.
- The **program registry read/write + projection** helpers (load a signed vector,
  intersect universes, project a δ vector).
- `render_notebook.py`, the `reproduce.sh` skeleton, and the `verify_reproduce`
  gate pattern.
- **The scVI embedding and Stage-1's `cluster_labels.json`** — Stage-2 *consumes* these
  as input (see §4.4), does not recompute them.

**Stage-2-specific:** the induced-Treg→Th1 **axis definition**; the **perturbation
projection + de-confounding + power gating** rule; the **NTC-guide null**; the **DepMap
handoff**; and all Stage-2 emitted JSON.

### 4.4 The explicit cross-stage dependency

Stage-2's most important input is **Stage-1's output**: the induced-Treg-48h cluster
and the Th1-8h region are *defined* in Stage-1 (`cluster_labels.json` +
`stage01_umap_seed.json`, keyed on `obs['L0.8']` and `obs['barcode']`). Stage-2 reads
those labels to pick the two cell groups the axis contrasts. This should be a hard,
version-pinned dependency in `reproduce.sh` (Stage-2 steps run *after* the Stage-1 gate
passes), so the chain tells one story end to end — and it fixes one of the review's
complaints (stale, inconsistent copies) by making the handoff explicit and gated.

---

## 5. Biggest risks and assumptions (ordered by how much they could bite)

**R1 — `DE_stats` is whole-condition pseudobulk, NOT cell-state-resolved. (Largest.)**
Each perturbation's Stim48hr DE vector is computed across *all* cells in that condition,
so it is dominated by the bulk activated population, not the induced-Treg subset
specifically. The primary metric (§2.1) therefore measures a **whole-Stim48hr shift
along the inflammatory axis** as a *proxy* for the induced-Treg→Th1 skew, not the
subset-specific effect. Mitigation: use the cheap projection as the screen, then
**confirm cell-state resolution on the shortlist** with cell-state-resolved DE from the
cell-level files (§2.7, compositional view). This limit must be stated wherever a hit is
reported.

**R2 — the axis is defined on NTC cells but applied to perturbed-cell DE.** Projecting a
perturbation's δ onto an NTC-derived axis assumes the co-expression structure (the axis)
is stable under perturbation. Reasonable for a mean-shift reading, but a perturbation
that *reshapes* the program (not just slides along it) is mis-scored. Reported as an
assumption; the anchor-program decomposition (§2.1) partly guards against it.

**R3 — gene-space mismatch and FOXP3 dropout.** The axis must be restricted to the
`DE_stats` 10,282-gene universe, and the load-bearing genes (FOXP3, CTLA4, CXCR3,
TBX21, IFNG) must survive with measurable baseline. FOXP3 has real 3′ dropout; if its DE
estimate is weak, the "reverse-FOXP3" readout leans on CTLA4 and the broader Treg anchor.
**Verify presence + baseMean before trusting the FOXP3-down component.**

**R4 — CRISPRi knockdown is partial and variable.** Many rows have no on-target KD
(seen directly: A1BG). Without the §2.3 power gate the screen scores noise. The gate is
load-bearing, not optional.

**R5 — essential-gene sledgehammers.** Broad-footprint knockdowns project onto
everything; §2.2 (cosine + breadth) and §3.2 (DepMap essentiality) are the two
independent guards. Residual risk remains for genes that are both essential *and*
genuinely regulatory.

**R6 — DepMap context gap + access.** Cancer lines ≠ primary CD4 (framing, §3.2), and
there is no DepMap connector in the catalog (access, §3.3). Both must be stated; access
must be arranged (network grant) or the essentiality-triage step scoped down to what
STRING/cBioPortal can support.

**R7 — multiplicity across 3,341 perturbations.** Handled by the NTC-guide empirical
null + BH (§2.5); without it, ranking over thousands of tests over-calls.

**R8 — sign bookkeeping.** Easy to flip the axis. FOXP3-KD-positive and NTC≈0 are the
gates that fix the sign before any ranking is trusted (§2.6).

---

## 6. Suggested execution order (when we do run)

1. `define_programs.py` — build the axis (scVI DE ∩ pseudobulk DESeq2), anchors, NMF;
   emit `stage02_programs.json`. Verify FOXP3/CTLA4/Th1 genes present + powered (R3).
2. `score_perturbations.py` — project every perturbation's `DE_stats` vector; gate power
   (R4); tag sledgehammers (R5); NTC-null p/q (R7); check FOXP3-KD sign + NTC≈0 (R8);
   emit `stage02_perturbation_scores.json`.
3. `stage2_pipeline.py` — narrative notebook, emit overlay; `verify_reproduce_stage2.py`
   gate; extend `reproduce.sh`; render HTML.
4. Shortlist → compositional confirmation on cell-level files (R1).
5. DepMap handoff + triage, once access (R6) is settled.
