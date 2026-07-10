# Data & Reference Licenses

spot's own code is **MIT** (see `LICENSE`). This file records the licenses and required
attributions for the third-party **datasets, databases, and reference frameworks** spot
queries. **No third-party data is bundled in this repo** — spot fetches public data at
run time, and every stage records the license per source in its provenance.

**Intended use:** academic / non-commercial (e.g. the Life Sciences hackathon). All
sources below permit this. Sources marked ⚠ are *non-commercial* — swap them before any
commercial or data-redistribution use (swaps noted).

## Open — permissive (incl. commercial), attribution required
| Source | License | Attribution / citation |
|---|---|---|
| DepMap / CCLE / DEMETER2 / PRISM | CC BY 4.0 | Broad Institute DepMap — Corsello 2020 (PRISM), Ghandi 2019 (CCLE), McFarland 2018 (DEMETER2) |
| LINCS L1000 / Connectivity Map | CC BY 4.0 | Broad Institute LINCS / CMap |
| Open Targets | CC0 1.0 | Open Targets Platform |
| DGIdb | open | Drug–Gene Interaction Database |
| FAERS / OpenFDA | US public domain | U.S. FDA |
| ClinicalTrials.gov | US public domain | U.S. NIH / NLM |
| RDKit (CNS-MPO descriptors) | BSD-3-Clause | RDKit |
| Grossman et al., Neuro-Oncology 2026 (NEBPI) | CC BY 4.0 | doi:10.1093/neuonc/noag051 |
| Masopust et al., Nat Rev Immunol 2026 (nomenclature) | CC BY 4.0 | doi:10.1038/s41577-025-01238-2 |
| Marson CD4 Perturb-seq (CZI Virtual Cells Platform) | MIT | Zhu, Dann, … Marson 2025; cite bioRxiv doi:10.64898/2025.12.23.696273; CZI Acceptable Use Policy applies |

## Share-alike — usable; copyleft on redistributed derivatives
| Source | License | Note |
|---|---|---|
| ChEMBL | CC BY-SA 3.0 | share-alike applies only if we redistribute *derived* ChEMBL data |

## ⚠ Non-commercial — OK for academic/hackathon; swap before commercial
| Source | License | Commercial swap |
|---|---|---|
| DrugBank | academic CC BY-NC (commercial = paid) | DGIdb + ChEMBL |
| SIDER | CC BY-NC-SA 4.0 | OpenFDA / FAERS |
| DrugComb | CC BY-NC-SA 4.0 | academic-only / open alternative |

## To confirm
- _(none outstanding — the Marson CZI Perturb-seq license was confirmed **MIT** from the
  dataset's Croissant metadata across all 12 splits; listed above. The derived NTC-subset
  embedding is redistributed on HF ([KiritSingh/spot-CD4-Marson](https://huggingface.co/datasets/KiritSingh/spot-CD4-Marson))
  under MIT with attribution.)_

_Licenses per knowledge as of 2026-01; verify current terms for any commercial use._
