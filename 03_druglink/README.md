# 03_druglink — link gene levers to direction-compatible drugs

Map the **verified Stage-2 levers and pathway nodes** to drugs whose annotated action is
**compatible with the required direction** of change. This is a **direction-aware
annotation**, not a ranking or a recommendation. Brain penetrance and exposure are the
filter (Stage 04), so this stage does **not** require glioma-cell activity.

## Method
Target → drug over **ChEMBL / UniProt** with **Open Targets** disease context. Each
candidate carries the drug's verbatim mechanism/action annotation and a **typed
direction-compatibility** flag (compatible / incompatible / ambiguous), evaluated per lever
origin — measured direct targets and inferred pathway nodes are kept separate and never
merged. No composite score, no traffic light; DepMap/CCLE glioma-dependency is a **deferred,
descriptive** axis, never a filter.

## Inputs
- The verified Stage-2 arms / pathway nodes and their required directions.

## Outputs
- Per-lever candidate drug annotations with direction-compatibility and full provenance
  (source database, release, exact record).

## Reproduce
Runs as a Claude Science specialist (drug repurposing) in its own lane. This branch packages the
stage's **admitted** artifact + receipt; the artifact shape and entry point are taken from that
final receipt rather than restated here. Cross-stage contract expectations: `schemas/README.md`.

## Provenance & licenses
Every annotation cites its source database and release. Queried sources and their licenses
are recorded in `DATA_LICENSES.md`.
