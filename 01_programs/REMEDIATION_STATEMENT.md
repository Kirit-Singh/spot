# spot Stage-1 — remediation & retraction statement (2026-07)

We identified material overclaims and statistical defects in spot Stage-1 and have issued a
**superseding exploratory release**. We **retract** the previous claims that the embedding was
paper-exact, that CP10k and median normalization produced invariant calls, that the nomenclature
outputs were cell-for-cell byte-reproducible, and that the displayed functional subtypes were
calibrated cell-type calls.

The revised release describes the embedding as **spot-specific and paper-inspired**, **removes the
invalid permutation-FDR / q-value interpretation**, **eliminates forced Treg assignment**, **permits
unresolved cells**, and reports **continuous Treg-like and CD4 CTL-like transcriptional-compatibility
scores**. These scores are **descriptive and are not validated lineage identities.**

Reproduction now **pins the exact input revision and SHA-256** and verifies the **40,000-cell
overlay's per-barcode output** (every emitted barcode and its 12 scores) rather than aggregate
counts.

**Important validation remains outstanding**: leave-one-donor-out analysis, activation-matched
calibration, external-dataset confirmation, and protein or functional evidence. Stage-1 is therefore
an **exploratory candidate-program workbench, not a locked or confirmed biological taxonomy.**

## What is genuinely fixed vs what remains

**Fixed:** forced Treg assignment removed; cells/clusters may be unresolved; condition is no longer
an input to any label (though condition-associated biology remains in expression — a documented
limitation, not a solved confound); invalid p/q/FDR outputs removed; false
reproducibility/normalization/upstream-faithfulness claims corrected; reproduction verifies real
per-barcode outputs, not aggregate counts.

**Still unresolved (documented, not solved):** whether the Treg-like cells are biologically Tregs (or
the CD4 CTL-like cells cytotoxic); score calibration; the activation/timepoint confound; cross-donor
generalization (n=4; donor D2 diverges); and any protein / suppression / cytotoxicity / external
validation.

## Old vs new (exact; see `analysis/STAGE1_REMEDIATION_CHANGES.md` for provenance)

The previous 40,000-cell overlay emitted **categorical calls behind an invalid FDR**; those calls
are **withdrawn**. The superseding overlay emits **continuous scores only** — no categorical calls.

| Quantity | Previous artifact | Superseding artifact | Method |
|---|---|---|---|
| Cells | 40,000 | 40,000 | exact barcode count |
| Categorical function calls | `—` 33,004 · Th1 4,550 · Treg 1,051 · Th2 528 · CD4-CTL 573 · Tfh 236 · Th9 40 · Th17 18 | **none (withdrawn)** | categorical calls removed |
| Categorical differentiation | N 6,409 · A 21,072 · M 10,871 · chkpt 1,648 | **none (withdrawn)** | categorical calls removed |
| Program outputs | forced argmax + q<0.05 gate | 12 **continuous `*_like_score`** fields per cell | continuous, no threshold |
| Reproducibility gate | aggregate `nomen_counts` (a zero-cell overlay passed at "100%") | **per-barcode canonical-table hash** | exact per-barcode |

We do not publish a "% changed" figure between the categorical and continuous outputs because they
are different object types (calls vs scores); the categorical calls are withdrawn in full.

## Exact identifiers (verifiable)

- **Code:** github.com/Kirit-Singh/spot, branch `stage1-remediation` (draft PR). Key commits:
  `3ce7491` (Stage-1 continuous-score remediation), `6c06a33` (Stage-2 plan corrections), plus the
  HF-revision pin. Method frozen in `analysis/STAGE1_REMEDIATION_METHOD.md`.
- **Hugging Face (superseding revision):**
  `KiritSingh/spot-CD4-Marson` @ **`e5fcf98b56a9302921d402e97fc5a190bd88f9a6`** (the prior revision
  remains in the immutable HF history; it is not being erased).
- **Hashes:** `ntc_clustered.h5ad` SHA-256 `2edc6d318415c8b0ee779d707ab86e26ddb6f0274db51ab4a12f21ebfda50e43`;
  per-barcode `canonical_table_sha256` `6e1665d13eab1781407b43d232d089fb5fb6a6b9df5acd83cbbfb8fe3aed2755`;
  `barcode_set_sha256` `1224312e52231f4b2e07c192b39c6f9c69dd6e2d5b8bd64d936c17a9b2435a93`; n = 40,000.

This remediation removes unsupported inference and forced identity. It does **not** complete the
biological validation that still remains.
