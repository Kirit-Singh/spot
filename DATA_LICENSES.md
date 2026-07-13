# Data and reference licenses

spot's original code is MIT-licensed; see `LICENSE`. Dataset and database content does
**not** become MIT merely because it is processed by spot. The table below records the
terms verified for sources that are bundled, referenced by executable analysis code, or
admitted to the current release design. `THIRD_PARTY_NOTICES.md` gives the corresponding
attribution and version details.

Verified against official provider records on **2026-07-13**.

| Source and material used | Status in spot | Verified terms | Release obligation |
|---|---|---|---|
| **Primary Human CD4+ T Cell Perturb-seq** (Marson GWCD4i), Virtual Cells Platform | Source of the derived Stage-1 artifacts and Stage-2 effect-universe crosswalk. Public HF revision `e5fcf98b56a9302921d402e97fc5a190bd88f9a6` currently contains the 3.84-GB source H5AD and historical v2 40k display seed; the v3 396k score Parquet is staged locally and **not yet published**. | The official dataset page identifies release v1.0 (22 Dec 2025) as **MIT**. Platform access/use is also governed by the Virtual Cells Platform Acceptable Use Policy. The accompanying preprint text is separately CC BY 4.0. | Preserve the provider's MIT declaration and standard terms, attribution and dataset identity; cite DOI `10.64898/2025.12.23.696273`; record the immutable source revision and hashes. Do not infer a copyright holder not supplied by the dataset record. Do not describe staged v3 outputs as public until the superseding-release checklist passes. |
| **Reactome pathway data** | Validated external Stage-2 development cache; raw cache remains outside Git and no pathway result is admitted to the current public release | Reactome database data and data-derived files are **CC0 1.0**. This does not describe Reactome software (generally Apache-2.0) or illustrations/branding (CC BY 4.0). | Attribution is encouraged. Record the exact Reactome release and source-file hashes. Frozen development cache: V97, released 30 Jun 2026 (release news record created 23 Jun 2026). |
| **Gene Ontology ontology and annotation data** | Validated external Stage-2 development cache; raw cache remains outside Git and no pathway result is admitted to the current public release | GO data and data products are **CC BY 4.0**. The human GAF is produced through UniProt-GOA/EMBL-EBI; copyrightable UniProt database content is also CC BY 4.0. | Attribute the Gene Ontology Consortium and UniProt-GOA, link the licenses, identify the exact ontology and annotation releases, and retain notices of changes. Frozen development inputs: `go-basic` 2026-06-15 and `goa_human` GOC snapshot 2026-05-21. |
| **ChEMBL database content** | Stage-3 source when a release-specific query/cache is admitted; no unpinned database dump belongs in Git | **CC BY-SA 3.0 Unported**. ChEMBL also warns that some included calculated properties originate from commercial software and may carry additional restrictions. | Give attribution and identify the ChEMBL release/DOI. Redistributed adaptations of ChEMBL content must use CC BY-SA 3.0; exclude commercially calculated fields unless their terms are separately cleared. |
| **UniProt database content** | Identifier/target evidence source when admitted by a Stage-3 manifest | Copyrightable database content is **CC BY 4.0**. UniProt notes that patents or other third-party rights may still apply and disclaims medical use. | Attribute UniProt, link the license, pin the release/query and preserve source accessions. Do not imply that CC BY clears patents or other rights. |
| **Perturb2StateModel** (`emdann/pert2state_model`) | Optional, secondary Stage-2 software; not a replacement for measured perturbation effects | **MIT**, copyright (c) 2025 Emma Dann, verified at commit `2c2e30959ffafadecc6af5d4d7b5bde868ab5313`. | If copied or substantially vendored, preserve the upstream copyright and permission notice. Always identify the exact commit and keep its outputs secondary and separately attributed. |
| **Authors' GWCD4i analysis code** (`emdann/GWT_perturbseq_analysis_2025`) | Reference/reproduction code; not the license source for the biological dataset | **MIT**, copyright (c) 2025 Emma Dann, verified at commit `848d62fc2b7027f7218d6fc5f5b0c37255dc94af`. | Preserve its MIT notice if code is copied or substantially vendored. Dataset terms still come from the Virtual Cells Platform record. |

## Not admitted by this file

A source mentioned in a plan is not automatically cleared for use or redistribution.
DrugBank, SIDER, DrugComb, LINCS, DepMap, Open Targets, DGIdb and other prospective
sources require their own version-specific verification before their data enters an
artifact. This file deliberately makes no blanket license claim for them. In particular,
full DrugBank datasets must not be described as unrestricted public data; any future use
must identify the exact licensed or separately designated Open Data package.

The following prospective regulatory sources are kept distinct because their terms and
evidentiary roles are not interchangeable. None is admitted to a current spot artifact:

| Prospective source | Verified boundary | Required handling before admission |
|---|---|---|
| **openFDA API** | The provider states that openFDA is generally **CC0**, with marked exceptions where third-party rights are asserted. Responses are unvalidated and carry source metadata such as `meta.last_updated`. Terms: <https://open.fda.gov/terms/>. | Preserve the exact response, metadata, disclaimer and any per-record rights exception. Never present an openFDA field as independently validated by FDA. |
| **FDA Adverse Event Reporting System (FAERS)** | FAERS is a distinct spontaneous-report system, not a synonym or license label for the openFDA access layer. **FAERS is signal evidence only**: reports cannot establish incidence, causality, or that a product is safe or unsafe. FDA overview: <https://www.fda.gov/drugs/surveillance/fda-adverse-event-reporting-system-faers>. | A future adapter must pin the precise FDA source/export and terms, retain report limitations, and prevent causal/incidence/safety claims. No adapter is currently admitted. |
| **ClinicalTrials.gov** | It is **not labelled public domain here**. Its terms explicitly discuss third-party rights and international copyright limitations. Terms: <https://clinicaltrials.gov/about-site/terms-conditions>. | Verify the exact API/export terms and record provenance before use. No adapter or trial record is currently admitted. |

No Human Protein Atlas data is included in the current release inventory.

Official license records:

- Virtual Cells dataset: <https://virtualcellmodels.cziscience.com/dataset/genome-scale-tcell-perturb-seq>
- Virtual Cells Acceptable Use Policy: <https://virtualcellmodels.cziscience.com/acceptable-use-policy>
- Reactome: <https://reactome.org/license>
- Gene Ontology: <https://geneontology.org/docs/go-citation-policy/>
- ChEMBL: <https://chembl.gitbook.io/chembl-interface-documentation/frequently-asked-questions/general-questions>
- UniProt: <https://www.uniprot.org/help/license>
- openFDA: <https://open.fda.gov/terms/>
- FAERS: <https://www.fda.gov/drugs/surveillance/fda-adverse-event-reporting-system-faers>
- ClinicalTrials.gov: <https://clinicaltrials.gov/about-site/terms-conditions>
