# spot shared artifact schemas (§11)

Versioned, content-addressed cross-stage contracts. All canonical hashes use
**stable key ordering, stable row ordering, defined float rounding, and EXCLUDE
timestamps / display-only labels / machine-local paths** (§11).

## `spot.stage01_program_registry.v1`
Emitted at `01_programs/app/data/stage01_program_registry.json` by
`01_programs/analysis/build_program_registry.py`. Per-program: `program_id`,
`score_field`, `display_label`, `family`, `role`, `stage2_selectable`
(+`stage2_unavailable_reason`), panel + exact frozen `control` symbols & Ensembl
(honest `null` for genes absent from the effect universe), coefficients, `seed`,
`scoring_method`, `method_hash`, display-transform metadata (frozen quantiles),
panel/control coverage in the 10,282-gene effect universe, source universe id/hash,
`source_citation`. Top-level `registry_sha256` (canon over ordered scientific
content, excludes `created_at`) = `1ac9f6b2c3a738e0f44119add5c4f72f61225372fedb3fa6dd8d5f6ae19e95fa`.

## `spot.stage01_selection.v1`
**Canonical reference implementation**: `02_geneskew/analysis/direct/contrast.py`
+ `hashing.py`; a produced example is
`02_geneskew/outputs/26b866f2ad813d71/stage01_selection.json`. Any producer (the
Stage-1 UI "Identify genes", Stage-2) MUST reproduce the identical `contrast_id`
for the same scientific content.

`contrast_id` = first 16 hex chars of `sha256(canonical_json(canonical_content))`,
where `canonical_json = json.dumps(obj, sort_keys=True, separators=(",",":"))` and
`canonical_content` (scientific content ONLY — no timestamps/labels/paths) =
```
{ "A": {"program_id","score_field","direction"},
  "B": {"program_id","score_field","direction"},
  "analysis_condition", "dataset_id", "donor_scope",
  "effect_universe_id", "objective",
  "program_registry_sha256", "source_h5ad_sha256",
  "source_hf_revision", "stage1_method_version" }
```
Constants for this dataset: `dataset_id="marson2025_gwcd4_perturbseq"`,
`effect_universe_id="marson2025_gwcd4_perturbseq : GWCD4i.DE_stats.h5ad"`,
`donor_scope="all"`, `stage1_method_version="stage1-continuous-v2"`,
`source_hf_repo="KiritSingh/spot-CD4-Marson"`,
`source_hf_revision="e5fcf98b56a9302921d402e97fc5a190bd88f9a6"`,
`source_h5ad_sha256="2edc6d31…50e43"`,
`program_registry_sha256="1ac9f6b2…"`.
Supported `objective`: `balanced_a_to_b`, `away_from_a`.
The canonical default demo contrast (treg_like-high → th1_like-high, Stim48hr,
all donors, balanced_a_to_b) has `contrast_id = 26b866f2ad813d71`.

## Downstream (to be finalized as those stages land)
`spot.stage02_axis.v1`, `spot.stage02_gene_lever_set.v1`,
`spot.stage03_drug_candidate_set.v1`, `spot.stage04_scorecard_set.v1` — each
references the exact upstream artifact hash for referential integrity (§11).
