# Stage-1 lineage registry integration map

## Scope

Read-only comparison of:

- `01_programs/app/data/stage01_program_registry_v3.json` at raw SHA-256
  `dd1a50a1111ac8784e7303a5d4b81b44cd780490222e820611b942e07d8682e0` and internal
  `registry_sha256=c308106dc22a2a9e705efa5eb0aadc2658790b09e206845c35bbf71e731fafb2`;
- `lineage_primary_source_completion.csv` at SHA-256
  `ff35c27cf210a225cab4c8e072ba3f585ec841a091b0518aff352ae6f22c8ff8`;
- the Stage-1 README, current pointer, release manifest, and full-release attestation.

The completion file covers 14 measured marker-program rows. It does not change a panel gene, control
gene, coefficient, bin, normalization, score, coordinate, or validation result.

## Exact registry changes

The registry currently stores citations at program level rather than gene level. The “current citation”
listed below is therefore the complete current program-level array. Integration should add structured
marker-level provenance so that a citation cannot be interpreted as support for every marker in its
program.

### `th1_like`

Current registry location: `stage01_program_registry_v3.json:43-52`.

Current citations: `Szabo et al., Cell 2000 100:655 (T-bet/Th1)`; `Zhu & Paul, Blood 2008
112:1557 (Th subsets)`.

| Gene | Current rationale | Replacement primary locator | Exact replacement rationale |
|---|---|---|---|
| `CXCR3` | `Th1 chemokine receptor; canonical Th1 trafficking marker` | Bonecchi et al. 1998, PMID 9419219, PMCID PMC2199181, DOI 10.1084/jem.187.1.129; Results and Discussion paragraph beginning “We generated Th1 and Th2 lines”; Figures 2B, 3, 4 | `CXCR3 is a human Th1-associated chemokine receptor and trafficking marker; it is preferentially expressed by polarized Th1 cells and supports responsiveness to CXCR3 ligands, but is not Th1- or CD4-specific.` |
| `IL12RB2` | `IL-12 receptor β2, required for Th1 commitment` | Rogge et al. 1997, PMID 9120388, PMCID PMC2196163, DOI 10.1084/jem.185.5.825; Results “Selective Expression of the IL-12R beta2 Chain in Th1 Cells”; Figures 3A-B, 4, 5 | `IL12RB2 encodes the signaling IL-12 receptor beta-2 chain, which is selectively enriched in human Th1 versus Th2 cells and is induced during Th1-polarizing activation; do not describe it as required for Th1 commitment on this evidence.` |

### `th2_like`

Current registry location: `stage01_program_registry_v3.json:281-290`.

Current citations: `Zhu, Cytokine 2015 75:14 (Th2/GATA3)`; `Nagata et al., J Immunol 1999
(CRTH2/PTGDR2)`.

| Gene | Current rationale | Replacement primary locator | Exact replacement rationale |
|---|---|---|---|
| `IL4` | `signature Th2 cytokine / master driver` | Wambre et al. 2011, PMID 21849680, PMCID PMC3445433, DOI 10.4049/jimmunol.1101283; Results “IL-5 expression is restricted to a minority subpopulation of IL-4+, IL-5+, IL-13+ Th2 cells”; Figure 1A-I, especially 1B and 1D-G | `IL4 is a human Th2-associated cytokine frequently coexpressed with IL13; use it as a type-2 cytokine-program component, not as a lineage-exclusive marker or as proof of a master-driver state.` |
| `IL5` | `Th2 effector cytokine (eosinophil)` | Wambre et al. 2011, PMID 21849680, PMCID PMC3445433, DOI 10.4049/jimmunol.1101283; same Results section; Figure 1A and 1C-G; opening Discussion paragraph | `IL5 is a human Th2 effector cytokine enriched in a minority, more highly differentiated Th2 subpopulation; it is not a universal Th2 marker.` |
| `IL13` | `Th2 effector cytokine` | Wambre et al. 2011, PMID 21849680, PMCID PMC3445433, DOI 10.4049/jimmunol.1101283; same Results section; Figure 1A-I, especially 1B and 1D-G | `IL13 is a human Th2-associated effector cytokine frequently coexpressed with IL4; use it as a type-2 cytokine-program component, not a lineage-exclusive marker.` |

### `th17_like`

Current registry location: `stage01_program_registry_v3.json:525-535`.

Current citations: `Ivanov et al., Cell 2006 126:1121 (RORγt/Th17)`; `Acosta-Rodriguez et
al., Nat Immunol 2007 (CCR6/CD161)`.

| Gene | Current rationale | Replacement primary locator | Exact replacement rationale |
|---|---|---|---|
| `IL23R` | `IL-23 receptor, Th17 maintenance` | Di Meglio et al. 2011, PMID 21364948, PMCID PMC3043090, DOI 10.1371/journal.pone.0017160; Results “Study of circulating Th17 cells in IL23R R381Q gene variant carriers,” Figure 1A; IL-23 effector-response Results, Figure 6A-D | `IL23R is a human memory-Th17-associated receptor that marks IL-23 responsiveness and supports Th17 effector signaling; it should not be described as required for the initial differentiation step or as Th17-exclusive.` |
| `KLRB1` | `CD161, human Th17-associated surface marker` | Cosmi et al. 2008, PMID 18663128, PMCID PMC2525581, DOI 10.1084/jem.20080397; Results “Human Th17, but neither Th1 nor Th2, clones express CD161 on their surface,” Figure 1A-C; following Results section, Figure 2A-B | `KLRB1/CD161 is a human Th17-associated surface marker and precursor feature, but it has low specificity and should not be treated as sufficient for Th17 identity.` |

The Acosta-Rodriguez citation may remain mapped to the markers it supports, but it must no longer be
presented as the source for `KLRB1`/CD161.

### `tfh_like`

Current registry location: `stage01_program_registry_v3.json:764-770`.

Current citation: `Crotty, Immunity 2019 50:1132 (Tfh; CXCR5/BCL6/IL21)`.

| Gene | Current rationale | Replacement primary locator | Exact replacement rationale |
|---|---|---|---|
| `CXCR5` | `Tfh follicle-homing receptor (canonical)` | Schaerli et al. 2000, PMID 11104798, PMCID PMC2193097, DOI 10.1084/jem.192.11.1553; Results “CXCR5+ T Cells in Blood and Tonsils” and “B Cell Helper Function of CXCR5+ T Cells”; Table I, Figure 3B, Figures 4-5 | `CXCR5 is a human follicular-homing and B-cell-helper-associated receptor used to mark a Tfh-like program; it is not Tfh- or CD4-specific in mixed-cell data because B cells also express CXCR5.` |
| `BCL6` | `Tfh master transcription factor` | Kroenke et al. 2012, PMID 22427637, PMCID PMC3324673, DOI 10.4049/jimmunol.1103246; Results “Bcl6 protein is expressed by human Tfh and GC Tfh,” Figure 1A-C; “Bcl6 instructs the conversion of Tfh to GC Tfh,” Figure 2C-D and 2K; Figure 3 | `BCL6 is a central human Tfh-program transcriptional regulator that is enriched in CXCR5-positive tonsillar Tfh cells and can induce major Tfh migration and T:B-interaction modules; it is not T-cell-specific because germinal-center B cells also express BCL6.` |
| `IL21` | `signature Tfh effector cytokine` | Kroenke et al. 2012, PMID 22427637, PMCID PMC3324673, DOI 10.4049/jimmunol.1103246; Figure 1D; Results “Helper cytokines IL-4 and IL-21,” Figure 5; “Maf induces IL-21 secretion,” Figure 7B-C | `IL21 is a prominent human Tfh/GC-Tfh helper cytokine and supports a Tfh-like effector program, but it is shared with other CD4 and innate-like lymphocyte states and is not sufficient for Tfh identity.` |

### `treg_like`

Current registry location: `stage01_program_registry_v3.json:1002-1011`.

Current citations: `Hori et al., Science 2003 299:1057 (FOXP3)`; `Thornton et al., J Immunol
2010 (Helios/IKZF2)`.

| Gene | Current rationale | Replacement primary locator | Exact replacement rationale |
|---|---|---|---|
| `IKZF2` | `Helios, (thymic) Treg stability marker` | Akimova et al. 2011, PMID 21918685, PMCID PMC3168881, DOI 10.1371/journal.pone.0024226; Abstract; Figures 1B, 3E-F, 4, 6B; Discussion conclusion | `IKZF2/Helios is enriched in activated human Tregs but is also induced by T-cell activation and proliferation; do not call it a Treg-stability marker or a reliable thymic-origin discriminator.` |
| `CTLA4` | `Treg effector checkpoint molecule` | Jonuleit et al. 2001, PMID 11390435, PMCID PMC2193380, DOI 10.1084/jem.193.11.1285; Results before Figure 2 and Figure 2A-B; blocking experiments in Figures 4 and 6; Discussion | `CTLA4 is enriched intracellularly and persists after activation in suppressive human CD4+CD25+ regulatory cells; treat it as a Treg-associated checkpoint with substantial activation overlap, not as a Treg-specific identity marker or a proven sole effector mechanism.` |
| `CCR8` | `tissue/effector Treg chemokine receptor` | Plitas et al. 2016, PMID 27851913, PMCID PMC5134901, DOI 10.1016/j.immuni.2016.10.032; Results “CCR8 is Expressed by Intratumoral Treg Cells”; Figure 6A-E and Figure 7B-E | `CCR8 marks an activated tissue/tumor-resident human Treg state and is enriched over conventional CD4 T cells in multiple tumors; it is context-dependent and should not be treated as a universal peripheral-Treg marker.` |
| `TNFRSF18` | `GITR, Treg-associated costimulatory receptor` | Levings et al. 2002, PMID 12438424, PMCID PMC2193983, DOI 10.1084/jem.20021139; Results “Expression of CTLA-4 and GITR on CD25+CD4+ T Cell Clones,” Figure 6 and following functional paragraph; Discussion | `TNFRSF18/GITR is associated with suppressive human CD25+CD4+ T-cell clones, but it is also activation-induced on conventional effector T cells; use it as a Treg-associated costimulatory-receptor component, not a Treg-specific marker or proof of suppressive necessity.` |

Thornton 2010 may be retained only as the original thymic-origin hypothesis. It cannot support the
current “stability marker” wording. Hori 2003 remains mapped to `FOXP3`, not to the four rows above.

### `th9_like`

No completion-row change. The supplement records that `IL9` and `SPI1` were already located to Chang
2010 in the prior Stage-1 ledger. Do not infer from that fact that the current program-level Kaplan
review is primary evidence; retain gene-level primary mapping to Chang.

## Primary-source verification

All 11 distinct replacement articles were checked against NCBI PubMed metadata and NCBI PMC full
text. Titles, years, PMIDs, PMCIDs, and DOIs match the completion CSV. The named Results sections and
figure ranges exist, and the bounded claims match the experiments described. Specific checks included:

- CXCR3 preferential expression and IP-10 response in human polarized lines/clones (Figures 2-4);
- IL12RB2 selective human Th1 expression, activation/cytokine regulation, and IL-12 binding (Figures
  3-5), without a universal-necessity result;
- the human Th2 Figure-1 hierarchy, including minority IL5-positive cells and broader IL4/IL13
  expression;
- IL23R/CCR6 phenotyping and IL-23-dependent effector response (Figures 1 and 6);
- human CD161-positive Th17 enrichment (Figures 1-2);
- CXCR5-positive human T-cell phenotype, B-cell help, and follicular localization; PMC encodes Figure
  3 as anchored subfigures `F3a`/`F3b`, and Figures 4-5 are present;
- BCL6 enrichment/transduction and IL21/Maf results in human tonsillar CD4 cells;
- Helios induction with activation/proliferation and the article's rejection of natural-versus-induced
  Treg discrimination;
- CTLA4 expression plus the negative blocking result (Figures 4 and 6);
- CCR8 enrichment, CCL1 migration, and activation/proliferation context (Figures 6-7);
- GITR expression-function association plus the negative perturbation result (Figure 6).

## Hash and version integration

### Must change if the registry is corrected in place

1. `stage01_program_registry_v3.json`
   - update the 14 `selection_rationale` values;
   - add gene-level structured primary citations/locators and evidence limits;
   - replace `citations_verification_status=UNVERIFIED_ASSERTED_not_tool_retrieved` for completed
     programs only after the 24/24 lineage rows are rechecked as one integrated registry;
   - update `citations_provenance_note` so Masopust remains naming-only;
   - recompute both the raw file SHA-256 and internal `registry_sha256`.
2. `stage01_current.json`
   - replace both references to the old registry raw SHA and the research-preview internal registry
     hash;
   - update only the provenance-status fields justified by the full registry audit;
   - recompute its raw and `self_canonical_sha256` hashes.
3. `stage01_release_manifest.json`
   - replace the registry raw SHA and any now-stale provenance status/reason;
   - replace the updated `stage01_current.json` raw SHA;
   - recompute its raw and `self_canonical_sha256` hashes.
4. `stage01_full_release_verification.json`
   - replace `inputs_by_hash.v3_registry_raw_sha256`,
     `outputs_by_hash.current_raw_sha256`, and `outputs_by_hash.release_manifest_raw_sha256`;
   - update the provenance scope statement and recompute its self hash.
5. Reproducibility code/tests that currently generate the literal pending-audit status
   (`gen_stage1_t8.py` and its independent verification/mutation expectations) must be updated before
   regenerating the pointer/manifest. Their raw hashes then change in the manifest/attestation.
6. `01_programs/README.md:121-123` must stop saying the lineage registry citations are wholly pending,
   but the global panel-provenance status must not be promoted until the state/CTL programs are also
   integrated and independently checked.
7. Any materialized Stage-1 selection, Stage-2 axis, Direct-screen, or Perturb2State artifact that
   embeds `program_registry_sha256` must be regenerated/re-keyed. The current Direct contrast hash
   includes the registry hash, so its `contrast_id` changes even though the numerical axis does not.

No new hash value should be written until the integrated registry is serialized and independently
rehashed. Do not predict a replacement hash.

### Must remain byte-identical

- `method_version=stage1-continuous-v3.0.1` (citation repair is not a scoring-method change);
- `stage01_scores_full.parquet`, raw SHA-256
  `de63b496e8121c77babe380e0c3b5ddfd66f9ce67d0d4e80f55645d177e27e5f`;
- score canonical-content SHA-256
  `43c4296d5166740c334441a69df23bb440a073382bbe79628a3bb89e43d51316`;
- `stage01_umap_overlay_v3.json` (`1fe05f33112c12af970ab5269ad64b1e0211f09143c991c2be982493c002366b`),
  `stage01_summary_v3.json` (`5e4153bdfa83cc0e77cd2980db024675006124b521b18de4fa970a8ff8bd2b13`),
  and frozen coordinates (`a7164168aaf61466ca699e1b00633c37ecef88705db443fb7fb0d00a86ccbbf6`);
- panel intended/measured lists, gene IDs, bins, control draws, candidate counts, seeds, coefficients,
  roles, normalization, and scoring-method fields;
- `stage01_controls_v3.csv`, `stage01_bins_v3.csv`, control pool/method, input manifest, gate spec,
  `stage01_validation.json`, validation semantics, and `stage01_selectability_v3.json`.

The integration gate should compare the pre- and post-change scoring projection of the registry after
dropping provenance-only keys and require exact equality. It should also re-derive the unchanged score
hashes rather than rerun or rewrite the 396,000-cell score table.

## Identifier-design note

The current single `registry_sha256` covers both scorer content and citations/rationales, while Stage-2
uses that hash inside the biological contrast identifier. This makes a citation correction invalidate a
numerically unchanged contrast. At this integration boundary, add a separately named scorer-spec hash
covering panels, controls, coefficients, normalization, seeds, and roles, plus a provenance hash covering
marker rationales and sources. Keep the existing whole-registry hash for file integrity. Future Stage-2
scientific identifiers should bind the scorer-spec hash and record the provenance hash separately.

