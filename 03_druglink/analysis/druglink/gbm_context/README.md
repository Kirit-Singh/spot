# Stage-3 v2 — GBM disease-context evidence (descriptive, NON-RANKING, NON-GATING)

The deferred "dual-mechanism bonus" axis from the design spec
(`docs/superpowers/specs/2026-07-08-...`: *"never a filter, so an immune target is never
dropped for lacking glioma-cell dependency"*), built as a **descriptive** evidence overlay.

For each gene in the selected Stage-2 arms (joined on its **Ensembl id, never a symbol**)
it emits **three SEPARATE axes** plus a typed, **SUGGESTIVE** compatibility state:

| axis | source | meaning |
|------|--------|---------|
| `immune_axis` | Stage-2 arm `desired_change` | desired immune-program perturbation (increase / decrease), per arm |
| `tumor_axis` | DepMap Public 26Q1 | tumor-cell dependency **direction + coverage** across named GBM/glioma cell lines (a line is dependent iff CRISPRGeneDependency **> 0.5, strict**, matching the frozen engine) |
| `disease_axis` | Open Targets Data 26.06 | GBM/glioma target–disease association evidence (datatype breakdown) |
| `compatibility` | derived | per immune direction: `dual_mechanism_compatible_suggestive` / `immune_axis_only_no_tumor_dependency` / `tumor_context_not_evaluated` — categorical, **never a number, never causal** |

It **never ranks, gates, or alters** any Stage-2 output; immune-cell effect and tumor-cell
context stay **separate** (never fused into one score); **missing evidence is
`not_evaluated`** and is never invented; **no p/q and no overall rank** ever reach a field.

## Sources (verified against primary/official APIs on 2026-07-13 — nothing hallucinated)
- **Open Targets Platform, Data 26.06** — GraphQL `api.platform.opentargets.org/api/v4/graphql`,
  licence **CC0 1.0**. Disease ids verified live: **glioblastoma `MONDO_0018177`**, **glioma
  `MONDO_0021042`** (`EFO_0000519` is null/deprecated and was NOT used). Association via
  `Target.associatedDiseases(Bs: [diseaseIds])`. OT's aggregated scores are carried as
  `open_targets_reported_upstream` with `used_for_gating_or_ranking: false`.
- **DepMap Public 26Q1** — licence **CC BY 4.0**. Byte pinning + the dependency computation
  are **owned by the Stage-2 DepMap lane** (`02_geneskew/analysis/depmap`), whose official
  catalog is fail-closed and currently **empty (0 entries)**. **No tumor-cell coverage is
  claimed** until that catalog is populated: an `official` dependency handoff is **refused**
  while `DEPMAP_OFFICIAL_CATALOG_POPULATED` is false; the tumor axis stays `not_evaluated`
  (`coverage_claimed: false`) with the release identity + strict-`>0.5` inclusion rule recorded.
  The dependency-call rule mirrors the frozen engine exactly (`DEPENDENCY_PROB_THRESHOLD=0.5`,
  `DEPENDENCY_PROB_STRICT=True`); `is_dependent_line(0.5)` is **False**.

## Trace every number to the exact bytes
Each gene's `disease_axis.source_provenance` records `endpoint`, `http_status`,
`api_version` (26.6.3), `data_version` (26.06), `raw_sha256`, `license`, and the
`response_artifact` basename — so a displayed disease score traces to the exact pinned
response. The handoff also carries a top-level `raw_response_artifacts` manifest
(basename + sha256 + endpoint + status + versions + licence, **basenames only, never a
machine-local path**). The run pins each raw public response to
`<out>.artifacts/` (a gitignored runtime sidecar, **not** inventoried by path); the same
bytes regenerate byte-identically on re-run (sha-pinned). The six real smoke responses are
preserved in-repo under `example_raw_responses/` (CC0), basenames matching the manifest.

## No tissue/organ axis
The immune effect is an **in-vitro CD4+ T-cell (blood) Perturb-seq** assay — donor × condition
× perturbation only, **no tissue/organ axis** and none inferred. The tumor context is a discrete
GBM/glioma **cell-line** panel (not a tissue-expression gradient); the disease context is the
GBM/glioma **disease** category. All three are recorded in `provenance.TISSUE_ORGAN_AXIS`.

## Handoff for W16 (`build_handoff` → JSON)
`handoff_id: spot.stage03.gbm_context.v1`, `join_key: target_ensembl`. W16 merges each
`genes[<ENSG>]` into the Stage-3 v2 candidates **by stable gene identity**, keeping its own
ranks. Carries `sources` (+ licences), `tissue_organ_axis`, `depmap_release_provenance`, and a
`run_provenance` block (UTC timestamp, `code_sha256`, env, rerun command, populated-vs-missing).

## Files
- `states.py` — pure typed-state logic (immune / tumor / disease / compatibility); no network.
- `ot_disease.py` — Open Targets acquisition (transport is a parameter; fail-closed on data-version drift; refuses target mis-attribution).
- `depmap_bridge.py` — pinned DepMap release identity + inclusion rule; validates/consumes a per-gene dependency handoff; refuses a foreign or unverified release.
- `build_gbm_context.py` — assembles the per-gene records + the handoff.
- `provenance.py` — source pins + licences, tissue-axis record, deterministic code hash, env, rerun command, populated-vs-missing.
- `run_gbm_context.py` — CLI + testable `run()`.
- `tests/gbm_context/` — 37 tests (synthetic fixtures + a real pinned OT response + a network-gated live smoke).

## Rerun
```
python -m druglink.gbm_context.run_gbm_context \
  --arms <selected_arms.json> --out gbm_context_handoff.json \
  --live-open-targets [--depmap-handoff <depmap_dependency_handoff.json>] \
  [--run-class real_open_targets_smoke]
```
`selected_arms.json` is a list of Stage-2 arm rows (`target_ensembl`, `target_symbol`,
`desired_change`, `program_id`, `arm_key`).

## Populated vs still missing (real run, `run_class: real_open_targets_smoke`, 6 real genes)
- **Populated:** `immune_direction` (Stage-2 arm) and `disease_association` (live Open Targets,
  real scores — e.g. EGFR↔glioblastoma 0.654, CTLA4 0.349, FOXP3 0.100).
- **Still missing (`not_evaluated`):** `tumor_dependency` (DepMap) — awaiting the Stage-2 DepMap
  lane pinning its official 26Q1 bytes; the contract + `compatibility` dual-mechanism path are
  ready and unit-tested, and will populate as soon as a validated dependency handoff is supplied.
- `example_handoff.smoke.json` is that real smoke output (6 representative real immune genes —
  **illustrative, not the final Stage-2 selection**).

## Methods & Provenance drawer payload (Stage-3 / Drugs tab)
`stage3_methods_manifest.drugs.json` is the compact machine-readable `StageMethodsManifest`
(`_frontend/src/domain/methodsManifest.ts`) rendered by the ONE shared header drawer. It is
emitted by `emit_methods_manifest.py` **from the run handoff's own recorded provenance** (never
re-typed), and canonicalised with the UI's exact rule
(`sort_keys, separators=(",",":"), ensure_ascii=True` → sha256), so W12 can pin it in
`STAGE_METHODS_HASHES.drugs` and the adapter's fail-closed content gate accepts it.

- **content_sha256** `b195a4c0b4ff9ab85338e7d745b7f2f1df723745a23d7ea737004995a742db8e` (4333 bytes;
  the stored file is already canonical, so the raw-byte sha256 equals the content hash).
  Independently recomputed with a node replica of `canonicalJson` — same value.
- **source_chain:** `chembl_37`, `uniprot_2026_02`, **`open_targets_26_06`** (CC0 1.0;
  `canonical_sha256` content-addresses the 6 pinned raw responses, each individually sha256'd in
  the handoff), **`depmap_public_26q1`** (CC BY 4.0; every hash **null** — not retrieved, official
  catalog empty, **no coverage claimed**).
- **Run-status stays `null`** (method/code hash, environment, last-run, reproduce command,
  release, generator/verifier, artifact paths): no admitted Stage-3 candidate bundle is bound to
  the page, and the drawer renders an absent field as "unavailable" rather than inventing one.
- The previously stale limitation ("… Open Targets … and DepMap-PRISM are not [wired]") is
  **corrected**: Open Targets disease association is now wired; DepMap dependency is explicitly
  `not_evaluated` with the strict `> 0.5` rule stated.

Regenerate: `python -m druglink.gbm_context.emit_methods_manifest --handoff example_handoff.smoke.json --out stage3_methods_manifest.drugs.json`
