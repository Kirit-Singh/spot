# Stage-1 state/CTL registry integration map

Date checked: 2026-07-12  
Mode: read-only review; no repository file was edited

## Result

The state/CTL supplement is internally consistent with the measured panels in
`01_programs/app/data/stage01_program_registry_v3.json`. Its 21 unique base-program
rows close the 21 state/CTL gaps identified by the prior panel audit. Six additional
rows are correctly marked as inherited aliases and do not inflate coverage.

When combined with the completed lineage supplement:

- registry measured primary-panel pairs: **53**;
- already primary-located in the prior ledger: **18**;
- lineage supplement completions/corrections: **14**;
- state/CTL supplement completions: **21**;
- measured pairs left without a bounded primary locator: **0**;
- supplement rows outside the current measured panels: **0**.

This supports a **conditional GO for a provenance-only registry release**. It does
not change the scorer, panel membership, controls, scores, validation result, or the
0/33 production-selectability result.

## Inputs checked

- Current registry: `01_programs/app/data/stage01_program_registry_v3.json`
  - raw SHA-256: `dd1a50a1111ac8784e7303a5d4b81b44cd780490222e820611b942e07d8682e0`
  - current internal `registry_sha256`:
    `c308106dc22a2a9e705efa5eb0aadc2658790b09e206845c35bbf71e731fafb2`
- Prior marker ledger:
  `stage1-panel-source-audit/science-final-v4/stage01_panel_provenance_ledger.csv`
  - SHA-256: `596a4435cbd729dbcbfa68df2adef730b1807fa9c0e8c39f0f102c284c4f3461`
- State/CTL supplement: `state_ctl_primary_source_completion.csv`
  - SHA-256: `febef35db329de0ecae95ca2654d6b3afd0e1b3b804b19fd46d11e0fe76df42f`
- Lineage supplement: `../lineage/lineage_primary_source_completion.csv`
  - SHA-256: `ff35c27cf210a225cab4c8e072ba3f585ec841a091b0518aff352ae6f22c8ff8`

## Exact program/gene integration map

The quoted “current” rationales and citations below are the current registry values.
The replacement wording is deliberately association-level and is suitable for the
registry's per-gene rationale. Exact article metadata and locators should be stored in
a structured per-gene provenance record rather than flattened into an undifferentiated
program-level citation string.

### `cd4_ctl_like` (`stage01_program_registry_v3.json`, program begins line 1320)

Current program citation: `Patil et al., Sci Immunol 2018 3:eaan8664 (human CD4-CTL; GZMH)`.
It remains valid for GNLY, PRF1, GZMH, GZMB, and NKG7. Add Kar et al. for KLRD1.

| Gene | Current rationale | Replacement primary locator | Exact bounded rationale |
|---|---|---|---|
| KLRD1 | `CD94, NK/CTL receptor` | Kar et al. 2024, PMID 38501302, PMCID PMC7616077, DOI 10.1111/imm.13783; Results section “hCMV-reactive CD4-CTLs and CD8-CTLs show similar transcriptomic profile,” Fig. 5d and 5g, Results paragraphs corresponding to P30-P32 | `KLRD1 RNA is associated with a primary human hCMV-reactive cytotoxic T-cell pre-effector program that contains both CD4 and CD8 cells; it is not a CD4-CTL-specific identity marker.` |

Do not retain “CD94 receptor” as the evidentiary claim for this row: the located source
supports KLRD1 RNA association, not receptor function.

### `diff_naive` (program begins line 1848)

Current program citations: `Sallusto et al., Nature 1999 401:708 (CCR7 naive/memory)`
and `Gattinoni et al., Nat Med 2011 (TCF7/LEF1 stemness)`. Sallusto remains attached
to CCR7; Gattinoni remains usable for the CD62L/IL7R naive-memory phenotype but must
not be represented as direct TCF7/LEF1 support. Add Szabo and Ahrends.

| Gene | Current rationale | Replacement primary locator | Exact bounded rationale |
|---|---|---|---|
| TCF7 | `TCF1, naive/stemness transcription factor` | Szabo et al. 2019, PMID 31624246, PMCID PMC6797728, DOI 10.1038/s41467-019-12464-3; Results describe CCR7/SELL/TCF7 resting CD4 cells as naive or TCM; Fig. 1c; Supplementary Data 3 `cluster1` row 16 and Data 4 `cluster1` row 14 | `TCF7 RNA supports a resting human CD4 naive/central-memory axis; it should not be read as naive-specific identity or as proof of stemness.` |
| LEF1 | `naive/stemness transcription factor` | Szabo 2019; Fig. 1c; Supplementary Data 3 `cluster1` row 29 and Data 4 `cluster1` row 51 | `LEF1 RNA supports a resting human CD4 naive/central-memory axis; it should not be read as naive-specific identity or as proof of stemness.` |
| MAL | `naive T-cell membrane marker` | Szabo 2019; Fig. 1c; Supplementary Data 3 `cluster1` row 809 and Data 4 `cluster2` row 3. Corroboration: Ahrends et al. 2021, PMID 33345332, PMCID PMC8248321, DOI 10.1002/eji.202048603, Results “MAL is preferentially expressed on naive and central memory CD4 T cells,” Fig. 6A-B | `MAL RNA is associated with a resting human CD4 state and is enriched on naive relative to effector-memory cells, while overlap with central memory prevents a naive-specific interpretation.` |

CCR7, SELL, and IL7R are not supplement gaps; retain their existing primary mappings
and bounded naive/central-memory interpretation.

### `diff_activated` (program begins line 2149)

Current program citation: `Shipkova & Wieland, Clin Chim Acta 2012 (CD69/CD25/HLA-DR activation)`.
It is a review and did not yield exact support for most of the measured panel in the
prior audit. It should not remain the authoritative marker-source field. Replace the
measured-marker evidence with the primary sources below. HLA-DRA stays intended-only.

| Gene | Current rationale | Replacement primary locator | Exact bounded rationale |
|---|---|---|---|
| CD69 | `early activation marker` | Szabo 2019; anti-CD3/CD28 activation in Fig. 1a; activated-CD4 cluster mapping in Fig. 1c; Supplementary Data 3 `cluster4` row 21 and Data 4 `cluster4` row 61 | `CD69 RNA is enriched in primary human activated CD4 T-cell clusters; it supports an activation-associated RNA component, not a distinct cell identity.` |
| IL2RA | `CD25, activation / high-affinity IL-2R` | Szabo 2019; Fig. 1a/c; Supplementary Data 3 `cluster4` row 51 and Data 4 `cluster4` row 23 | `IL2RA RNA is enriched in primary human activated CD4 T-cell clusters; it supports an activation-associated RNA component but overlaps Treg expression.` |
| CD38 | `activation ectoenzyme` | Shi et al. 2021, PMID 34394094, PMCID PMC8363247, DOI 10.3389/fimmu.2021.700152; Methods “Defining Cell State Scores” and Fig. 3A use CD38 in a human scRNA activation module. Corroboration: Funderburg et al. 2008, PMID 18382686, PMCID PMC2271052, DOI 10.1371/journal.pone.0001915; Fig. 1 and Fig. 4B show induced CD38 protein in human T cells | `CD38 has primary human support as an activation-associated T-cell marker and has been used in a human single-cell RNA activation score; within this panel it should be read only as activation-associated RNA, not as identity or mechanism.` |
| MKI67 | `Ki-67, proliferation` | Shifrut et al. 2018, PMID 30449619, PMCID PMC6689405, DOI 10.1016/j.cell.2018.10.024; Results “SLICE Paired with Single Cell RNA-Seq,” Fig. 4B, and activation/cell-cycle clusters 10-12 | `MKI67 RNA supports the proliferating/cycling arm of a stimulated human T-cell program; it should not be interpreted as activation-specific or as a cell identity marker.` |
| TNFRSF9 | `4-1BB/CD137, activation costimulation` | Szabo 2019; Fig. 1c; Supplementary Data 4 `cluster4` row 1664 and `cluster5` row 53 | `TNFRSF9 RNA is enriched in primary human activated CD4 T-cell clusters; it supports an activation-associated RNA component, not a distinct identity.` |

HLA-DRA handling is unchanged: it remains in `panel_genes_intended`, absent from
`panel_genes_measured`, recorded in `coverage.genes_absent`, and contributes zero to
the score. Do not count it in the measured-provenance denominator or add it to the
measured panel merely to close a citation row.

### `diff_memory` (program begins line 2396)

Current program citations: `Sallusto et al., Nature 1999 401:708 (memory subsets)`
and `Mahnke et al., Eur J Immunol 2013 (CD27/CD45RA)`. Neither is an exact source for
this six-gene panel. Keep them only as optional context, not marker evidence; add Rose
and Szabo as the authoritative marker sources.

| Gene | Current rationale | Replacement primary locator | Exact bounded rationale |
|---|---|---|---|
| ITGAL | `LFA-1α, memory adhesion` | Rose et al. 2023, PMID 37012418, PMCID PMC10070634, DOI 10.1038/s42003-023-04747-9; Results “The shared transcriptional programs of human CD4+ and CD8+ MTC,” Fig. 1e | `ITGAL RNA is associated with a human CD8 memory T-cell transcriptional profile and can support the adhesion-like portion of the module; it is not memory- or CD4-specific.` |
| FAS | `CD95, memory/activation apoptosis receptor` | Szabo 2019; Fig. 1c; Supplementary Data 3 `cluster8` row 121 and Data 4 `cluster7` row 28 | `FAS RNA is enriched in resting human CD8 effector-/tissue-resident-memory clusters; it supports a memory/activation-associated RNA component, not memory identity.` |
| CD58 | `LFA-3, memory adhesion` | Szabo 2019; Fig. 1c; Supplementary Data 3 `cluster8` row 1396 | `CD58 RNA was enriched in one primary human resting CD8 effector-/tissue-resident-memory cluster and can support an adhesion-like RNA component; it is not a memory-specific marker.` |
| ITGA4 | `VLA-4α, memory adhesion/trafficking` | Rose 2023; Results “The shared transcriptional programs of human CD4+ and CD8+ MTC,” Fig. 1e | `ITGA4 RNA is associated with a human CD8 memory T-cell transcriptional profile and can support the adhesion-like portion of the module; it is not memory- or CD4-specific.` |
| S100A4 | `memory-associated calcium-binding protein` | Szabo 2019; Fig. 1c; Supplementary Data 3 `cluster8` row 1229 | `S100A4 RNA was enriched in one primary human resting CD8 effector-/tissue-resident-memory cluster; it supports a memory-associated RNA component but not memory identity or function.` |
| CD27 | `memory costimulatory receptor` | Szabo 2019; Fig. 1c; Supplementary Data 3 `cluster10` row 190 | `CD27 RNA was enriched in one primary human activated CD8 effector-/tissue-resident-memory cluster; it supports a non-terminal memory-associated RNA component, not memory identity.` |

### `diff_checkpoint` (program begins line 2644)

Current program citation: `Wherry & Kurachi, Nat Rev Immunol 2015 15:486 (exhaustion; PD-1/TOX/TIM-3/LAG3/TIGIT)`.
It is a review, predates the cited TOX evidence, omits ENTPD1, and must not remain the
authoritative source for this panel. A single human primary study supplies the bounded
RNA association for all six genes.

Primary source for all rows: Lowery et al. 2022, PMID 35113651, PMCID PMC8996692,
DOI 10.1126/science.abl5447; Results beginning “Restricting the gene expression
analysis,” Fig. 2G-H, Table S8, and the later minimal activation/dysfunction gene-set
analysis. HAVCR2's explicit result is CD8-only; the other five are reported in shared
CD4/CD8 NeoTCR states.

| Gene | Current rationale | Exact source scope | Exact bounded rationale |
|---|---|---|---|
| PDCD1 | `PD-1, exhaustion/checkpoint` | Shared verified CD4 and CD8 NeoTCR TIL state | `PDCD1 RNA is part of a primary human CD4/CD8 tumor-reactive dysfunctional T-cell expression program; it supports a checkpoint-high RNA component but not exhaustion identity or function.` |
| TOX | `exhaustion master transcription factor` | Shared verified CD4 and CD8 NeoTCR TIL state | `TOX RNA is part of a primary human CD4/CD8 tumor-reactive dysfunctional T-cell expression program; it supports a checkpoint-high RNA association without claiming master-regulator function or cell identity.` |
| HAVCR2 | `TIM-3, checkpoint` | Explicit result is in CD8 NeoTCR TILs | `HAVCR2 RNA is associated with a primary human CD8 tumor-reactive dysfunctional T-cell program; it supports a checkpoint-high RNA component but not CD4 transfer, exhaustion identity, or function.` |
| LAG3 | `checkpoint` | Shared verified CD4 and CD8 NeoTCR TIL state, plus explicit CD8 statement | `LAG3 RNA is part of a primary human CD4/CD8 tumor-reactive dysfunctional T-cell expression program; it supports a checkpoint-high RNA component but not exhaustion identity or function.` |
| TIGIT | `checkpoint` | Shared verified CD4 and CD8 NeoTCR TIL state | `TIGIT RNA is part of a primary human CD4/CD8 tumor-reactive dysfunctional T-cell expression program; it supports a checkpoint-high RNA component but not exhaustion identity or function.` |
| ENTPD1 | `CD39, exhaustion/Treg ectoenzyme` | Shared verified CD4 and CD8 NeoTCR TIL state, plus explicit CD8 statement | `ENTPD1 RNA is part of a primary human CD4/CD8 tumor-reactive dysfunctional T-cell expression program; it supports a checkpoint-high RNA association without claiming exhaustion identity or ectoenzyme function.` |

## Inherited and alias handling

### Activation-adjusted CTL sensitivity lane

`cd4_ctl_like_actadj` is an algorithmic residualized display, not a distinct biological
program. It should reference the six base `cd4_ctl_like` marker-provenance records.
The supplement's KLRD1 alias must resolve to the Kar record above with:

- `base_program_id: cd4_ctl_like`;
- `provenance_inherited: true`;
- no additional unique-gap count;
- bounded rationale: `Inherited from cd4_ctl_like: KLRD1 supports only a shared human cytotoxic T-cell RNA association; activation residualization does not create or validate a separate biological program.`

Do not create a second independent KLRD1 source claim for the sensitivity lane.
Keep `stage2_selectable=false` and `not_selectable_reason=role_sensitivity_display_only`.

### Activation predictor aliases

The five predictor genes must point to their base `diff_activated` provenance records:

| Predictor | Base record | Alias handling |
|---|---|---|
| CD69 | `diff_activated.marker_provenance.CD69` | Inherit Szabo locator; predictor use does not validate another biological program. |
| CD38 | `diff_activated.marker_provenance.CD38` | Inherit Shi plus Funderburg mixed support; retain the RNA-module/protein-induction distinction. |
| MKI67 | `diff_activated.marker_provenance.MKI67` | Inherit Shifrut; retain proliferation-generic scope. |
| TNFRSF9 | `diff_activated.marker_provenance.TNFRSF9` | Inherit Szabo; activation association only. |
| IL2RA | `diff_activated.marker_provenance.IL2RA` | Inherit Szabo; retain Treg overlap. |

These aliases are attribution pointers only, are not panel rows, and must not be counted
again in provenance coverage.

## Recommended registry representation

Do not encode this completion only as another program-wide free-text `citations` list.
Add a structured `marker_provenance` object keyed by measured gene with, at minimum:

```json
{
  "source_type": "primary_research",
  "pmid": "...",
  "pmcid": "...",
  "doi": "...",
  "exact_locator": "...",
  "support_level": "...",
  "species_lineage_scope": "...",
  "claim_scope_limit": "...",
  "provenance_inherited": false
}
```

For corroborated rows (MAL and CD38), store the corroborating source separately rather
than merging two evidence classes into one claim. For intended-only HLA-DRA, store
`measured_in_object=false` and `contributes_to_score=false`; do not pretend it has a
measured-marker locator.

After integrating both supplements:

- change each program's `citations_verification_status` from
  `UNVERIFIED_ASSERTED_not_tool_retrieved` to a bounded, source-specific status such as
  `PRIMARY_LOCATORS_VERIFIED_BOUNDED`;
- replace the top-level `citations_provenance_note` with a machine-readable summary
  that cites the two supplement artifacts and their checksums;
- retain Masopust as naming-only and never attach it to a marker row;
- retain the existing program IDs, score fields, panel order, and biological labels.

If `spot.stage01_program_registry.v3` is defined as a closed schema, bump only the
registry/provenance schema (or add a separate `panel_provenance_schema_version`) for
the new structured field. Do **not** use a scorer `method_version` bump to represent a
literature-metadata revision. If v3 explicitly permits additive fields, the schema label
may remain v3, but its contract tests must begin validating `marker_provenance`.

## Hash and identifier impact

### Must change

1. `stage01_program_registry_v3.json`
   - raw file SHA-256;
   - internal `registry_sha256` (it hashes all registry content except itself, including
     rationale/citation metadata).
2. Hash-bound pointer/attestation artifacts that embed the registry hash or its status:
   - `stage01_current.json`: registry raw/canonical hashes, panel-provenance status/note,
     `self_canonical_sha256`, and therefore raw file SHA;
   - `stage01_release_manifest.json`: registry raw hash, provenance gate/status,
     `not_lockable_reasons`, any newly listed provenance-ledger artifacts,
     `self_canonical_sha256`, and raw file SHA;
   - `analysis/stage01_full_release_verification.json`: v3 registry raw hash,
     current/release-manifest raw hashes, panel-provenance scope/status,
     `self_canonical_sha256`, and raw file SHA.
3. Any generator/verifier/test source changed to regenerate and enforce these fields;
   its recorded code hash and the final verification receipt must change.
4. New Stage-1 selection artifacts must bind the new registry raw/canonical hashes.
   Any Stage-2 cache keyed by those provenance bindings must be invalidated or re-keyed.

### Must remain byte-identical

- `method_version = stage1-continuous-v3.0.1` (no scoring-method change);
- source H5AD raw SHA and input matrix manifest;
- all `panel_genes_intended` and `panel_genes_measured` lists and their order;
- all controls, bins, eligible pool, seeds, and coefficients;
- `stage01_scores_full.parquet` and
  `scores_canonical_content_sha256 = 43c4296d5166740c334441a69df23bb440a073382bbe79628a3bb89e43d51316`;
- the 40k v3 overlay and its score values;
- the full 396k summary;
- frozen coordinates and coordinate hash;
- `stage01_validation.json`, gate specification, selectability artifact, and the 0/33
  production result;
- activation-adjustment slope `0.3832196947475601`, intercept
  `0.13373652013357928`, and all residualized scores.

A mutation test should assert that the score parquet, overlay, summary, controls,
coefficients, validation, and selectability hashes are unchanged across the provenance
revision.

### Identifier hierarchy issue to resolve explicitly

Scientifically, the biological question/contrast has not changed. Under the intended
hierarchy, `question_id`/biology-only `contrast_id` should remain stable, while a
registry-bound `selection_id` and any downstream `stage2_run_id` should change.

The current browser implementation does not preserve that separation:
`01_programs/app/01_page.html` lines 741-759 include both registry hashes in
`canonicalContent()`, and lines 823-825 derive `question_id`, `selection_id`, and
`contrast_id` from the same full hash. Therefore, without a code correction, all three
IDs will change after this metadata-only registry revision. Either:

1. restore the intended hierarchy before release (preferred), keeping the biology-only
   question/contrast ID stable and changing only the selection/provenance binding; or
2. accept the current mechanical behavior, record the ID migration, and reject all
   caches/artifacts bound to the old registry hash.

Do not silently reuse an old selection or Stage-2 run ID with the new registry hash.

## Primary-source verification performed

Official PubMed metadata and NCBI PMC full text were checked for the key source set:

- Kar 2024: PubMed metadata matches PMID 38501302 / PMCID PMC7616077 / DOI
  10.1111/imm.13783; PMC Fig. 5 and Results contain KLRD1, the pre-effector cluster,
  and the mixed CD4/CD8 composition described by the supplement.
- Szabo 2019: PMID 31624246 / PMCID PMC6797728 / DOI
  10.1038/s41467-019-12464-3; the main Results support the resting naive/TCM and
  activation-cluster scope. The official supplementary workbooks were independently
  read from `PMC6797728_SupplementaryFiles.zip`; every cited worksheet, row, gene,
  FDR, and log2 effect in the state/CTL CSV matched exactly.
- Ahrends 2021: PMID 33345332 / PMCID PMC8248321 / DOI 10.1002/eji.202048603;
  Fig. 6 and Results confirm uniform naive CD4 MAL expression plus substantial central
  memory overlap.
- Shi 2021: PMID 34394094 / PMCID PMC8363247 / DOI
  10.3389/fimmu.2021.700152; Methods explicitly include CD38 in the human scRNA
  activation score.
- Funderburg 2008: PMID 18382686 / PMCID PMC2271052 / DOI
  10.1371/journal.pone.0001915; Results/Figs. 1 and 4B support CD38 protein induction
  in human CD4/CD8 and purified memory CD4 T cells.
- Shifrut 2018: PMID 30449619 / PMCID PMC6689405 / DOI
  10.1016/j.cell.2018.10.024; Fig. 4 and Results explicitly place MKI67 in the
  stimulated cycling arm.
- Rose 2023: PMID 37012418 / PMCID PMC10070634 / DOI
  10.1038/s42003-023-04747-9; Results/Fig. 1e explicitly report higher ITGAL and
  ITGA4 expression in human CD8 memory T cells.
- Lowery 2022: PMID 35113651 / PMCID PMC8996692 / DOI
  10.1126/science.abl5447; Results/Fig. 2/Table S8 support the five shared CD4/CD8
  genes and the explicitly CD8-scoped HAVCR2 result exactly as bounded above.

## Merged-release readiness judgment

**Conditional GO for the provenance merge; not yet GO for the currently checked-in
release artifacts.** The evidence supplements close all measured-marker provenance
gaps with bounded primary sources, and no panel or numerical artifact needs to change.
The release becomes provenance-ready only after deterministic structured integration,
registry/pointer/manifest re-hashing, generator-verifier regeneration, and a mutation
test proving all numerical artifacts remain byte-identical. This provenance result does
not alter the frozen panel-robustness or production-selectability decisions.
