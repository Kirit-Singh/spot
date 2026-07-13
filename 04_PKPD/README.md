# 04_PKPD — brain penetrance, exposure, safety

Score each drug for CNS delivery and tolerability, and present the evidence as **separate
lanes**. There is **no composite score, no ranking, no traffic light, and no
recommendation** — each lane stands on its own and cites its source.

## Method
- **Brain penetrance** — CNS-MPO / NEBPI descriptors (Grossman et al., *Neuro-Oncology*
  2026): ClogP, ClogD, TPSA, MW, HBD, pKa, plus P-gp / BCRP efflux. Reported as a screen
  (sufficiently / insufficiently / impermeable), **not** proof of CNS exposure.
- **Exposure** — half-life and exposure descriptors.
- **Safety** — co-medication and peri-operative signals against GBM standard-of-care
  concomitants (e.g. TMZ, radiotherapy, dexamethasone, levetiracetam), each reported as a
  typed, sourced evidence item rather than a combined verdict.

Descriptor calculation uses RDKit (BSD-3-Clause).

## Inputs
- The locked drug(s) from Stage 03.

## Outputs
- A per-drug evidence card: brain-penetrance screen + exposure + safety lanes, each with its
  own provenance. No lane is collapsed into an overall call.

## Reproduce
Runs as a Claude Science specialist (neuro-oncology PK/PD). **Not yet implemented in this
repo** — `analysis/` and `inputs/` are placeholders; the entry point and its verifier land
with the stage.

## Provenance & licenses
Brain-penetrance scoring is a *screen*, not a clinical determination. Queried sources and
their licenses are recorded in `DATA_LICENSES.md`.
