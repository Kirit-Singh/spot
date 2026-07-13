# Admitted compact UI projection handoff

The Stage-2 browser payload is W3's exact, selection-independent
`spot.stage02_display_projection.v1` document. The UI packager does **not** derive, re-rank,
re-cap, or rename its rows. The authoritative artifacts remain the admitted Direct, temporal,
and pathway bundles named by the projection.

Stage-3 and Stage-4 retain their existing native-to-compact adapters. This document describes
the Stage-2 boundary that differs from those routes.

## Data path

```text
admitted native Stage-2 bundles
  └─ W3 display_projection.py → stage2_display_projection.json
       └─ independent verify_display_projection.py → verification receipt
            └─ pack_ui_projections.mjs
                 ├─ results/stage02/stage2_display_projection.json
                 ├─ results/stage02/display_projection.verification.json
                 ├─ results/manifests/{targets,pathways}.ui_release.json
                 └─ results/current.json
```

The route's `spot.ui_release_manifest.v1` remains the admitted run-status source for the
header's shared **Methods & Provenance** drawer. There is no separate methods page and no
methods/caveat banner on the Stage-2 canvas.

## Pack input

Each Stage-2 route receives the same W3 projection and independent receipt. Release order,
active pathway source, and run identity are explicit input; none is inferred from arm keys.

```jsonc
{
  "stage1_binding": {
    "release_method_version": "...",
    "registry_scorer_view_sha256": "<64hex>",
    "selection_schema_raw_sha256": "<64hex>",
    "release_self_sha256": "<64hex>"
  },
  "routes": {
    "targets": {
      "projection": "<spot.stage02_display_projection.v1 object>",
      "display_verifier_receipt": "<independent receipt object>",
      "compact_release": {
        "run_id": "<admitted Stage-2 run id>",
        "release_conditions": ["Rest", "Stim8hr", "Stim48hr"],
        "pathway_sources": ["reactome", "go_bp"],
        "active_pathway_source": "reactome"
      },
      "receipt": "<ui_release run receipt>"
    },
    "pathways": "<same projection/receipt/release shape>",
    "drugs": { "native": "<Stage-3 bundle>", "receipt": "<ui_release receipt>" },
    "pksafety": { "native": "<Stage-4 bundle>", "receipt": "<ui_release receipt>" }
  }
}
```

The packager refuses non-admitted display receipts, altered release order, differing run ids
or projection bytes between the two Stage-2 routes, and p/q/FDR or combined/balanced/rank fields
inside projected arms.

## W3 projection fields admitted by the browser

- top-level schema/method/cap policy and null-only selection/combined sentinels;
- `bindings.native_bundles` with lane, bundle id, and exact source-file raw hashes;
- Direct/temporal arms with context, native rank, target id, arm value, total/evaluable/ranked/
  emitted counts, frozen cap 100, and prefix status;
- pathway arms with condition/source context, `set_id`, producer-supplied optional values,
  whole-arm coverage counts, frozen cap 50, and explicit unranked native emission order;
- producer `projection_sha256` bound to the release metadata;
- independent receipt
  `spot.stage02.display_projection.independent_verifier.v1`, with generator≠verifier,
  reconstruction from admitted native bytes, zero failures, and `verdict=admit`.

The browser independently verifies the exact served-file hash, parsed canonical-content hash,
receipt file hash, receipt canonical hash, and all strict schema/count/key gates before resolving
an active selection.

## `results/current.json` Stage-2 metadata

Every bound Targets/Pathways route carries typed `compact_stage2` metadata:

- `run_id` (must equal `chain.stage2_run_id`);
- release conditions exactly `Rest`, `Stim8hr`, `Stim48hr`, in that order;
- pathway sources exactly `reactome`, `go_bp`, in that order, plus the active source;
- projection raw, canonical, and producer-self hashes;
- independent verifier id, same-origin receipt path, receipt raw hash, and receipt canonical hash.

Stage-3/4 routes must not carry this block.

## Runtime selection join

For any admitted program pair:

- same-condition selection resolves exactly two Direct arms and two same-condition pathway arms;
- ordered cross-condition selection resolves exactly two temporal arms, plus the A/from and B/to
  endpoint pathway arms;
- desired changes are derived from the pole roles and high/low directions using the frozen arm-key
  function;
- a missing exact arm fails closed. The UI never substitutes another program, condition, direction,
  or pathway source;
- there is no combined score, cross-arm ranking, p/q/FDR, or browser-derived pathway ranking.

The compact canvas displays only producer fields. Optional columns disappear when the producer
provided no values; pathway names are not invented when W3 provides only `set_id`. Count and prefix
metadata remain visible so a capped view cannot read as the complete release.

## Verification

Focused tests cover arbitrary program/direction pairs, all three within-condition choices, all six
ordered temporal pairs, raw/canonical/self and receipt hash attacks, missing arms, malformed counts,
unknown fields, p/q/FDR, combined/balanced fields, exact rendering, and the packager→browser round trip.
The full frontend test, typecheck, lint, and production build remain the merge gate.
