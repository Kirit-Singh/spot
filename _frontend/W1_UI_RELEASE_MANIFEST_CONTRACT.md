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
and sets `RealArtifactResolution.manifest` — only when `admission === 'admitted'`.

_Deployment is HELD until real admitted artifacts arrive; the branch is committed but not redeployed._
