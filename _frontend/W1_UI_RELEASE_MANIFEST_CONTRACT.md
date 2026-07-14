# UI release manifest — packaging contract for W1

After a **real Stage-2/3/4 run** whose result has passed independent verification, package a compact
`UiReleaseManifest` per route and hand it (plus its pinned content hash) to the shell. The drawer then
replaces the one-line *"No admitted … bundle bound"* status with the exact admitted run rows.

**This is fail-closed.** A manifest that is incomplete, non-admitted, mislabelled, or hash-mismatched is
rejected and the route stays unbound. Do not hand over a provisional or partial manifest.

## Files (already in this repo, on branch `agent/ui-stage234`)

- `src/domain/uiReleaseManifest.ts` — the `UiReleaseManifest` type + `UI_RELEASE_SCHEMA_VERSION` +
  `isAdmittedVerifier` (the admission vocabulary).
- `src/adapters/uiReleaseManifestAdapter.ts`:
  - `packageUiReleaseManifest(input)` → `{ manifest, content_hash }` — **the interface to call.** It
    validates through the same gate (so you cannot package an invalid manifest) and returns the pinned
    `content_hash` (sha256 over the canonical JSON).
  - `parseUiReleaseManifest(raw, contentHash, stageLabel, methodId)` — the shell's fail-closed bind.
  - `mergeAdmittedManifest(staticDef, admitted)` — overlays the admitted run onto the static route
    method-definition (the definition prose is preserved; only run-status fields are bound).
- `src/mpa/StageIsland.tsx` — consumes `RealArtifactResolution.manifest` (the merged manifest) ahead of
  the static definition.
- Tests: `src/adapters/__tests__/uiReleaseManifestAdapter.test.ts` (schema / admission / mutation / merge).

## Schema (`spot.ui_release_manifest.v1`)

```ts
{
  schema_version: 'spot.ui_release_manifest.v1',
  stage_label: 'Targets' | 'Pathways' | 'Drugs' | 'PK & Safety',   // MUST equal the route label
  method_id:   string,                                              // MUST equal the static route method_id
  release_revision: string,                                        // result content addresses
  raw_sha256: string,
  canonical_sha256: string,
  method_code_sha256: string,                                      // admitted-run identity (all required)
  environment: string,
  last_run_utc: string,            // ISO-8601 UTC
  generator_status: string,
  verifier_status: string,         // MUST be an admitted token: admit|admitted|pass|passed|verified|ok
  reproduce_command: string,       // reproduces THIS admitted artifact
  cs_notebook_url: string | null,  // real Claude-Science notebook URL, or null
  artifact_paths: string[],        // nonempty — emitted result artifacts
  source_artifact_ids: string[],   // preserved source artifact IDs (appended to the References chain)
}
```

## Exact code-bound values per route

`stage_label` / `method_id` must match these EXACTLY (from `src/mpa/stageMethods.ts`):

| route     | stage_label   | method_id |
|-----------|---------------|-----------|
| targets   | `Targets`     | `spot.stage02.direct.masked_program_projection · spot.stage02.pareto.two_arm.v1 · spot.stage02.temporal_cross_condition.v1` |
| pathways  | `Pathways`    | `spot.stage02.pathway.ranked_arm_enrichment.v2 · spot.stage02.pathway.signature_convergence.v2` |
| drugs     | `Drugs`       | `stage3-druglink-v4-workflow-states · schema spot.stage03_drug_annotation.v1` |
| pksafety  | `PK & Safety` | `stage4-evidence-v2 · cns_mpo_wager2010_v1 · nebpi_source_framing_v2 · safety_taxonomy_v2` |

## Fail-closed gates (in order)

1. **content-address** — `sha256(canonicalJson(manifest)) == content_hash` (byte-exact; the same
   `ensure_ascii=True`, sorted-key canonical form as Stage-1 / Python `hashlib`).
2. **schema** — `schema_version === 'spot.ui_release_manifest.v1'`.
3. **firewall** — `stage_label` and `method_id` equal the code-bound route/method.
4. **admission** — `verifier_status` is EXACTLY an admitted token (whole-string; `not passed` /
   `pending` / `unverified` / `failed` are rejected).
5. **completeness** — every run field nonempty; `artifact_paths` nonempty.

Reject → route stays unbound (static definition + one-line status). Never a partial run claim.

## Handoff

Serve each `manifest` alongside its `content_hash`. A real `resolveProductionRealArtifact()`
(or its per-route equivalent) fetches the manifest, calls `parseUiReleaseManifest(...)` with the pinned
`content_hash` + code-bound `stageLabel`/`methodId`, then `mergeAdmittedManifest(staticDef, admitted)`,
and sets `RealRouteResolution.manifest` — only when `admission === 'admitted'`.

## Serving the results tree (pre-run infrastructure — now in place)

The shell now has the full FAIL-CLOSED loading + deploy seam; W1 supplies the bytes:

1. **`results/current.json`** (`spot.ui_results_current.v1`, `src/domain/uiResultsCurrent.ts`) — the SINGLE
   mutable downstream pointer, served OUTSIDE `data/` (so the pinned Stage-1 digest never moves). It binds:
   - `stage1_binding` — `{ release_method_version, registry_scorer_view_sha256 }` (the Stage-1 release the
     results descend from);
   - `routes[<route>]` — `{ manifest_path, content_hash, projection_path, projection_content_hash }`
     (per route; a route absent → unbound). Parsed fail-closed by `parseUiResultsCurrent`.
   - **plus a deploy-only `inventory[]`** — `{ path, sha256 }` for EVERY file under `results/` (except
     `current.json`). `deploy/validate_results_tree.py` re-hashes each file and REFUSES an unlisted file,
     hash mismatch, partial tree, missing route manifest, or malformed pointer. (The browser adapter
     ignores `inventory`; it fetches specific paths and verifies their pinned `content_hash`.)
2. **Route resolution** (`src/mpa/resolveRouteArtifact.ts`) — `resolveRouteArtifact(page, { fetchText,
   loadProjection })`: loads `current.json` → the route's ui_release manifest (via `loadRouteReleaseManifest`,
   fail-closed) → merges → the route's native projection. Returns a route-discriminated
   `RealRouteResolution` ONLY when the manifest is admitted AND a matching projection is bound; else null.
   **W1 wires `loadProjection`** to parse the native Stage-2/3/4 bundles into a `RouteProjection`
   (`{kind:'stage2',view,bundles}` | `{kind:'stage3',artifact:Stage3UiArtifact}` |
   `{kind:'stage4',artifact:Stage4UiArtifact}`); the pre-run default returns null (route stays unbound).
   Stage-3/Stage-4 UI models: `src/domain/stage3UiArtifact.ts`, `src/domain/stage4UiArtifact.ts`
   (native workflow states / evidence lanes; missing stays typed-missing; no `gbm_context`/`directness`/
   inferred `safe`/`brain penetrant`).
3. **Deploy** (`deploy/deploy_8347.sh`) — set `SPOT_RESULTS_SRC=<staged results tree>`; the deploy validates
   it, hygiene-scans every result JSON, copies it under served `results/`, classifies it `downstream-data`
   in `release_manifest.json`, and remote-byte-verifies it. ABSENT → clean UNBOUND deploy (Stage-1 digest
   byte-identical). Never put results under `data/`.

_Deployment is HELD until real admitted artifacts arrive; the branch is committed but not redeployed._
