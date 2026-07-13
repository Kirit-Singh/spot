# Data & Reference Licenses

spot's own code is **MIT** (see `LICENSE`). This file records the licenses and required
attributions for the third-party **datasets, databases, and reference frameworks** spot uses
or plans to use. Sources are grouped by how spot touches them today, not by license family.

**Verification policy:** a field is filled only where it is verifiable from metadata in this
repo (or the source's own official page); unrecorded fields are `—`, never guessed. `Release /
accessed` is `—` for a source this repo does not pin. **Intended use:** academic /
non-commercial. Verify current terms before any commercial or redistribution use.

The **machine-readable, officially-verified** subset (with per-source official URL, verbatim
license quote, and verification date) is `schemas/source_license_inventory.json`; that file is
authoritative for the sources it lists and this table is the broader human-readable view.

## 1. Bundled (redistributed in this repo or on our Hugging Face)
The only third-party data spot redistributes is a **derived** subset; no upstream source
matrix is bundled.

| Source | License | Release / accessed | Attribution & redistribution |
|---|---|---|---|
| Marson CD4 perturb-seq — **derived NTC-subset embedding** | MIT (upstream CZI dataset MIT, confirmed from the dataset Croissant metadata across all 12 splits) | HF revision `e5fcf98b…` | Zhu, Dann, … Marson 2025; bioRxiv doi:10.64898/2025.12.23.696273. Redistributed by us on HF [`KiritSingh/spot-CD4-Marson`](https://huggingface.co/datasets/KiritSingh/spot-CD4-Marson) with attribution; CZI Virtual Cells Platform Acceptable Use Policy applies. |
| spot **derived display artifacts** (`01_programs/app/data/`) | MIT (spot's own output) | tracked in-repo | spot code output over the MIT source; carries the upstream attribution above. |

## 2. Queried external at run time (public; used by implemented stages)
Fetched at run time, not bundled; each stage records the license per source in its provenance.

| Source | License | Release / accessed | Attribution |
|---|---|---|---|
| Marson `GWCD4i.DE_stats` (+ `by_guide` / `by_donors`) — Stage 2 | MIT (as above) | — | Zhu, Dann, … Marson 2025; bioRxiv doi:10.64898/2025.12.23.696273. CZI Virtual Cells Platform. |
| Masopust et al., *Nat Rev Immunol* 2026 — T-cell **nomenclature** (Stage-1 program naming only) | CC BY 4.0 | doi:10.1038/s41577-025-01238-2 | reference framework; program *labels* follow this consensus (gene panels are spot's own curation). |

## 3. Planned — specified but not currently queried in production
Stages 3–5 (drug link, PK/PD, trial) are specified but not yet implemented in this repo, and
some Stage-3/4 axes are deferred. The sources below are **not** in current production; listing
a license here is not a claim that spot queries the source today.

| Source | License | Release / accessed | Attribution / note |
|---|---|---|---|
| DepMap / CCLE / DEMETER2 / PRISM | CC BY 4.0 | — | Broad Institute DepMap — Corsello 2020 (PRISM), Ghandi 2019 (CCLE), McFarland 2018 (DEMETER2). Deferred glioma-dependency axis. |
| Open Targets Platform | CC0 1.0 | — | Open Targets. Planned Stage-3 disease context. |
| ChEMBL | CC BY-SA 3.0 | — | EMBL-EBI ChEMBL. Share-alike applies only if we redistribute *derived* ChEMBL data. Planned Stage-3 target→drug. |
| UniProt | CC BY 4.0 | — | UniProt Consortium. Planned Stage-3 target crosswalk. |
| PubChem | NCBI: no restrictions on NCBI content (US public domain); depositor content may carry copyright | — | NCBI / NLM. Verify submitter terms before redistributing depositor content. Planned Stage-3 chemistry. |
| Gene Ontology (GO) | CC BY 4.0 | — | GO Consortium. **GO-BP is the only admitted pathway collection** (critical path); must name a dated release, and its GMT must hash to its pin. |
| Reactome | CC0 1.0 (annotation + interaction data; software/diagrams CC BY 4.0) | — | **PARKED** — not on the GO-BP-only critical path; not required and never advertised in the deployable UI bundle. Recorded for the record only. |
| LINCS L1000 / Connectivity Map | CC BY 4.0 | — | Broad Institute LINCS / CMap. Not in the current design; retained as a planned option only. |
| DGIdb | open (see DGIdb terms) | — | Drug–Gene Interaction Database. Not in the current design; retained as a planned option only. |
| openFDA / FAERS | CC0 1.0 (openFDA dedication; no FDA endorsement implied) | — | U.S. FDA. Planned Stage-4 safety signal. |
| DailyMed | NLM-produced content US-government public domain; manufacturer-submitted label (SPL) content may carry restrictions | — | NLM. Attribute "Courtesy of the National Library of Medicine". Planned Stage-4 label context. |
| ClinicalTrials.gov | **NLM Terms and Conditions — not blanket public domain** (records may contain material copyrighted by sponsors; attribute NLM, no endorsement implied) | — | U.S. NIH / NLM. Planned Stage-5 (placeholder). |
| Grossman et al., *Neuro-Oncology* 2026 — NEBPI framework | CC BY 4.0 | doi:10.1093/neuonc/noag051 | reference framework; planned Stage-4 brain-penetrance scoring. |
| RDKit (CNS-MPO descriptors) | BSD-3-Clause | — | RDKit (software library, not a dataset); planned Stage-4 descriptor calculation. |

## 4. Prohibited for redistribution / non-commercial — not used; swap before any commercial use
Not queried in current production. If ever used, keep non-commercial and swap before commercial
or data-redistribution use.

| Source | License | Commercial / open swap |
|---|---|---|
| DrugBank | academic CC BY-NC (commercial = paid) | ChEMBL (+ DGIdb) |
| SIDER | CC BY-NC-SA 4.0 | OpenFDA / FAERS |
| DrugComb | CC BY-NC-SA 4.0 | academic-only / open alternative |

---
_Licenses per knowledge as of 2026-01 and the sources' official pages; verify current terms for
any commercial or redistribution use. The upstream CZI dataset license was confirmed **MIT**
from the dataset Croissant metadata across all 12 splits._
