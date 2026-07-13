# Native → compact UI projection handoff (W1 / W6 / W16)

The browser renders **compact route projections** (my stable schema); the offline packager
`_frontend/deploy/pack_ui_projections.mjs` **derives** those projections from the admitted **native**
Stage-2/3/4 bundles + external admission receipts. Compact rows are never hand-authored.

This document pins the native→compact field mapping the packager currently implements (against the
audit handoff `UI_REAL_ARTIFACT_BINDING_HANDOFF.md` §6–§8). **The native field names below are the
intended pinning point** — confirm/adjust them against the FINAL producer schemas when they publish:
Stage-2 (**W16**), Stage-3 v2 (**W6**), Stage-4 (**W1**). Changing a native field name is a one-line
edit in the corresponding `nativeTo*` adapter + its fixture test; the browser schema does not move.

## Pipeline

```
admitted native bundle (JSON) ──nativeTo*Projection──▶ compact projection ──content-address──▶ served .ui.json
admitted receipt (JSON) ─────────buildManifest───────▶ spot.ui_release_manifest.v1 ───────────▶ served .ui_release.json
                                                    └─▶ results/current.json (routes + inventory, canonical hashes)
```

Content hashes: `content_hash` / `projection_content_hash` = `sha256(canonicalJson(obj))` (the browser's
exact canonical form); `inventory[].sha256` = sha256 of the raw served file bytes. The packager and the
browser loader hash identically — proven by the round-trip test
`src/mpa/__tests__/projectionPackagerRoundTrip.test.ts`.

## Pack spec (input the packager consumes)

```jsonc
{
  "stage1_binding": { "release_method_version": "...", "registry_scorer_view_sha256": "<64hex>" },
  "routes": {
    "targets":  { "native": <stage2 aggregate>, "receipt": <admitted receipt> },
    "pathways": { "native": <stage2 aggregate>, "receipt": <admitted receipt> },
    "drugs":    { "native": <stage3 v2 bundle>, "receipt": <admitted receipt> },
    "pksafety": { "native": <stage4 release>,   "receipt": <admitted receipt> }
  }
}
```

### Receipt (run metadata — NEVER invented; the packager refuses if a required field is missing)

`release_revision`, `raw_sha256`, `canonical_sha256`, `method_code_sha256`, `environment`,
`last_run_utc`, `generator_status`, `verifier_status` (must be an admitted token:
`admit|admitted|pass|passed|verified|ok`), `reproduce_command`, `cs_notebook_url` (string URL **or**
`null` — must be present), `artifact_paths[]` (≥1), `source_artifact_ids[]`. `stage_label` + `method_id`
are code-bound (below), not receipt-supplied.

## Native field mapping (confirm against final producer schemas)

- **Stage-2 (W16)** — `native.{direct,temporal,pathwayByContext}` carry `base_records[]` + `arms[]` as
  **arrays** (§6); the packager keys them into objects by `base_key` / `arm_key`, values unchanged, and
  keeps `arm.records` a native array. `native.{analysis_mode,pathway_source,release_conditions}` required.
  The browser then resolves the JoinedView from these bundles + the stored v3 selection.
  **Open:** native rows are emitted as parquet (`arms.parquet` etc.); supply a JSON representation of the
  documented columns (or an agreed parquet→JSON extraction) for the packager to consume.
- **Stage-3 v2 (W6)** — `native.{bundle_id, manifest_sha256, upstream_stage2_run, candidates[]}`; each
  candidate carries the §7 workflow-state fields (`candidate_id`, `active_moiety_id`, `preferred_name`,
  `identity_status`, `form_ids`, `target_ensembls`, `n_edges`, `n_direct_gene_edges`,
  `development_state_aggregate`, `n_potency_rows`, `potency_state`, `observed_perturbation_arms`,
  `inverse_direction_support`, `pathway_hypothesis_arms`, `stage3_evidence_classes`,
  `disease_context_review_{status,result}`, `stage4_assessment_status`, `source_record_ids`). Deprecated
  fields (`gbm_context`, `directness`, scalar `mechanism_direction`) are NOT emitted.
- **Stage-4 (W1)** — `native.{scorecard_set_id, stage4_method_version, upstream_stage3_bundle,
  candidates[]}`; each candidate carries `active_moiety`, `compound_ids`, `target`, `mechanism`,
  `production_eligible` (+ `_reason`), and `lanes.{delivery,cns_mpo,transporters,exposure,nebpi,safety}`.
  A missing/not-evaluated lane stays `null` — never `safe`/`brain penetrant`/0.

## Code-bound route identities (the browser firewall enforces these)

| route | stage_label | method_id |
|-------|-------------|-----------|
| targets | `Targets` | `spot.stage02.direct.masked_program_projection · spot.stage02.pareto.two_arm.v1 · spot.stage02.temporal_cross_condition.v1` |
| pathways | `Pathways` | `spot.stage02.pathway.ranked_arm_enrichment.v2 · spot.stage02.pathway.signature_convergence.v2` |
| drugs | `Drugs` | `stage3-druglink-v4-workflow-states · schema spot.stage03_drug_annotation.v1` |
| pksafety | `PK & Safety` | `stage4-evidence-v2 · cns_mpo_wager2010_v1 · nebpi_source_framing_v2 · safety_taxonomy_v2` |

### ⚠ REQUIRED before admitted deployment: Drugs method identity v1 → v2

The Drugs `method_id` above still references `schema spot.stage03_drug_annotation.v1`. When W6 publishes
the final Stage-3 **v2** schema, update the Drugs identity to the final v2 string in BOTH:
`_frontend/src/mpa/stageMethods.ts` (the hashed static definition — re-pin the drugs manifest hash) AND
`_frontend/deploy/pack_ui_projections.mjs` (`ROUTES.drugs.method_id`), and update this table. The two
must stay byte-identical or the browser firewall rejects the manifest. This is a blocking pre-admitted-
deploy item (the exact v2 identity string is W6's to publish — do not guess it).

## UPDATE — binding gates now enforced (feed these exact shapes)

The shell now REFUSES anything that isn't a complete, chained, same-release admitted result. When you
provide native + receipts in these shapes, the packager binds and the browser renders; otherwise it stays
unbound (never partial/stale).

### results/current.json (packager-emitted; the browser fail-closes on all of it)
- `stage1_binding.registry_scorer_view_sha256` MUST equal the active v3 selection's scorer binding —
  a result from a different Stage-1 release is refused on every route (#1).
- `chain = { stage2_run_id, stage3_bundle_id, stage4_scorecard_set_id }` — the browser binds a route only
  if its projection's upstream ids match EXACTLY: Stage-2 `run_id`==stage2_run_id; Drugs
  `upstream_stage2_run`==stage2_run_id & `bundle_id`==stage3_bundle_id; PK&Safety
  `upstream_stage3_bundle`==stage3_bundle_id & `scorecard_set_id`==stage4_scorecard_set_id. The packager
  derives the chain and REFUSES a receipt-A-over-data-B mismatch at pack time (#6).

### Stage-2 native aggregate = the COMPLETE generic release (#2, W16)
Provide the WHOLE release; a missing slot is refused (`incomplete_release`), never rendered empty:
```jsonc
{
  "run_id": "<stage2 run id>",
  "analysis_mode": "within_condition" | "temporal_cross_condition",
  "release_conditions": ["Rest","Stim8hr","Stim48hr"],
  "pathway_sources": ["reactome","go_bp"],
  "pathway_source": "reactome",                     // active source for the view
  "directByCondition":  { "<cond>": <direct bundle> },                 // one per condition (3)
  "temporalByPair":     { "<from>__<to>": <temporal bundle> },         // one per ORDERED pair (6)
  "pathwayByContext":   { "<cond>|<source>": <pathway bundle> }        // one per (condition,source) (6)
}
```
Each bundle: native `base_records[]` + `arms[]` arrays (the packager keys them to objects by
base_key/arm_key; `arm.records` stays an array). The browser SELECTS the requested condition/pair at join
time and parses ONLY that slot (production namespace enforced). **Still to pin (W16):** Direct row values
come from `arms.parquet` joined 1:1 to `target_identity.json` by immutable key — supply a JSON
representation of those columns (or an agreed parquet→JSON extraction) so the packager reopens + hashes
the admitted native bytes (#3/#7 rederivation, not scalar status).

### Stage-3 v2 (#4, W6) + Stage-4 scorecard_set.v1 (#5, W1) — NEXT units, awaiting published fields
The Drugs/PK&Safety native adapters currently map the documented §7/§8 fields. When the final schemas
publish, provide: Stage-3 `spot.stage03_drug_annotation.v2` per-origin/arm-key candidate model + manifest
(update `ROUTES.drugs.method_id` v1→v2 in both stageMethods.ts and the packager, re-pin the drugs hash);
Stage-4 `spot.stage04_scorecard_set.v1` nested `active_moiety`, `production_eligible`, lane arrays/objects,
and upstream binding. The strict adapters + fixtures are in place to pin against — no compact rows are
hand-authored.

_Deployment stays HELD until real admitted native artifacts + receipts exist. The packager writes nothing
unless invoked with a real spec; production results are never committed._
