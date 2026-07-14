# Data & reference licenses

**spot's own code is MIT** (see `LICENSE`). **The data are not.** This file is the authoritative
per-source ledger: what spot queries, under what terms, and what it may redistribute.

**Third-party data ARE tracked in this repo** — a small amount, deliberately. Earlier versions of
this file said the opposite; that was false, and a reader who believed it would have treated
CC BY-SA 3.0 content as MIT. What is tracked, and under what license:

| Tracked bytes | Origin | License |
|---|---|---|
| `04_PKPD/tests/fixtures/stage3*/**.parquet` — Stage-3 wire-bundle fixtures | **ChEMBL-derived** facts (ChEMBL target/molecule ids, target classes, mechanisms) | **CC BY-SA 3.0** — attribution + share-alike on redistributed derivatives. **Not MIT.** |
| the same bundles' protein records | **UniProt-derived** accessions | **CC BY 4.0** — attribution. **Not MIT.** |

Everything else is fetched at run time. **Raw public responses are never committed**: they are
cached outside the working tree under the caller's run root, addressed by SHA-256, and only the
*manifest* (locator + access time + raw hash + terms) enters Git. Stage 4's `RunRoot` refuses a
cache inside the tree, and `04_PKPD/tests/test_release_hygiene_scan.py` fails the build if a
response payload is ever tracked.

**There is no project-wide use restriction, because there cannot be one.** Reuse follows **each
row's own licence and terms**. They genuinely differ, and flattening them into a single blanket
label was the confusion the audit flagged: one label at once over-restricts the CC0 and CC BY
sources and under-states the share-alike and no-blanket-licence ones.

**spot's code being MIT does not override anyone's data terms, and their terms do not restrict
the code.** The two travel separately. Read the row for the source you intend to use; where a row
and the code disagree, the per-source registry wins (see the boundary note at the end).

## Fetched at run time — permissive, attribution required
| Source | License | Primary locator / attribution |
|---|---|---|
| Reactome (Stage 2 gene sets) | **CC0** for data-derived files; bind the release (V97) + source hashes | https://reactome.org/license |
| Gene Ontology (GO-BP) | **CC BY 4.0** — include GOC attribution, copyright and disclaimer | https://geneontology.org/docs/go-citation-policy/ |
| UniProt | **CC BY 4.0** for copyrightable database content; retain the other-rights disclaimer | https://www.uniprot.org/help/license |
| Grossman et al., Neuro-Oncology 2026 (NEBPI) | **CC BY 4.0** | doi:10.1093/neuonc/noag051 · PMC13338342 |
| Masopust et al., Nat Rev Immunol 2026 (nomenclature) | **CC BY 4.0** | doi:10.1038/s41577-025-01238-2 |
| Marson CD4 Perturb-seq — CZI dataset | **MIT** (dataset); retain version/producer attribution + AUP | https://virtualcellmodels.cziscience.com/dataset/genome-scale-tcell-perturb-seq |
| Marson preprint | **CC BY 4.0** — licensed separately from the dataset | bioRxiv doi:10.64898/2025.12.23.696273 |
| RDKit (CNS-MPO descriptors) | BSD-3-Clause | RDKit |

## Share-alike — usable; copyleft on redistributed derivatives
| Source | License | Note |
|---|---|---|
| ChEMBL | **CC BY-SA 3.0** | Redistributed **adaptations must stay share-alike and visibly attributed** — this covers the tracked Stage-3 bundle fixtures above, and any ChEMBL-derived data package |

## Queried, but **no blanket license** — used without redistribution
Public endpoints spot reads at run time whose terms do **not** grant blanket reuse. Nothing from
them is bundled; only facts and short quotations are encoded, with locators and hashes.

| Source | Terms | Stage-4 use |
|---|---|---|
| DailyMed SPL v2 | **No blanket public-domain assertion.** NLM publishes no blanket license statement for the web service; government and third-party label content coexist, and some SPL content visibly carries third-party copyright. NLM also warns that in-use labelling may differ from current FDA-approved labelling | label identity + labelled safety sections. **Live label text is never committed** |
| openFDA / Drugs@FDA | **Generally CC0, with marked record-level exceptions** where third-party rights are asserted. Data are unvalidated; the original response and its disclaimer are retained | approval / application cross-check |
| PubChem PUG REST | NCBI usage policy: no NCBI restriction on molecular data; **third-party rights may exist** in individual records | structure + PubChem-computed descriptors. **Never logD7.4 or pKa** — PubChem has neither, so CNS-MPO stays incomplete rather than fabricated |
| RxNorm (RxNav) | NLM terms; carries **source-vocabulary restrictions** for some content | identity crosswalk only |
| Wager et al. 2010 (CNS-MPO) | **ACS copyright.** *Not* in the PMC open-access subset | Only the **numeric method parameters** (facts) and short locators are encoded. The article HTML/JATS is **never committed or uploaded** |

## Not public domain, and not treated as such
| Source | Why | Status |
|---|---|---|
| ClinicalTrials.gov | Its [terms](https://clinicaltrials.gov/about-site/terms-conditions) preserve third-party and international copyright and impose attribution/currentness obligations, so it **may not be relabelled US public domain** | **no adapter** |
| FAERS | If ever added, FAERS is **signal evidence only** — it cannot establish incidence, causality or safety | **no adapter** |
| **DrugBank** | **No valid public license has been established for this project.** Not queried, not parsed, and **no `drugbank_id` is populated** on any public-only production path | **forbidden**, enforced in code (`04_PKPD/analysis/public_sources.py :: assert_fetch_permitted`). Use ChEMBL instead |

## Carried in the Stage-3 → Stage-4 contract
| Source | License | Note |
|---|---|---|
| LINCS L1000 / Connectivity Map | CC BY 4.0 | Broad Institute LINCS / CMap. The Stage-3 contract carries a `lincs_support` table that Stage 4 consumes; it is **suggestive evidence, never confirmatory** |

## Listed historically — not on the current implemented path
Retained so a reader is not told they were silently dropped. **No current adapter queries these**,
and none is a dependency of the current Stage-1→4 chain. Owning lanes should confirm removal.

DepMap / CCLE / DEMETER2 / PRISM (CC BY 4.0) · Open Targets (CC0 1.0) · DGIdb (open) ·
SIDER (CC BY-NC-SA 4.0) · DrugComb (CC BY-NC-SA 4.0)

---

**Boundary.** This is a provenance and licensing ledger, not legal advice. Terms were read from
the primary locators above; **verify current terms before any commercial or redistribution use**,
and note that share-alike (ChEMBL) and non-commercial (SIDER, DrugComb) obligations survive
redistribution. Every stage records the license per source in its own provenance, and the
per-source registry (`04_PKPD/method/sources.json`,
`04_PKPD/method/acquisition_sources_v1.json`) is authoritative where this file and the code
disagree.
