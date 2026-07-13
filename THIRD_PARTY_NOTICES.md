# Third-party notices

This file records exact, independently verified attributions for third-party material
used or referenced by spot. It does not replace the upstream license text.

## Primary Human CD4+ T Cell Perturb-seq

- **Dataset:** *Primary Human CD4+ T Cell Perturb-seq*, Virtual Cells Platform v1.0,
  released 22 December 2025.
- **Source producers:** Ronghui Zhu, Emma Dann, Jun Yan, Justine Reyes Retana,
  Ryunosuke Goto, Reese C. Guitche, Lillian K. Petersen, Mineto Ota,
  Jonathan K. Pritchard and Alexander Marson.
- **Official record:** <https://virtualcellmodels.cziscience.com/dataset/genome-scale-tcell-perturb-seq>
- **Dataset license:** MIT, as declared by the official dataset record. The record
  links the standard MIT terms but does not expose an upstream copyright notice; spot
  therefore does not invent one.
- **Additional platform terms:** <https://virtualcellmodels.cziscience.com/acceptable-use-policy>
  (effective 2 January 2026).
- **Preprint:** Zhu R, Dann E, et al. *Genome-scale perturb-seq in primary human CD4+
  T cells maps context-specific regulators of T cell programs and human immune traits.*
  DOI <https://doi.org/10.64898/2025.12.23.696273>. The preprint text is CC BY 4.0;
  this is separate from the dataset's MIT declaration.
- **Authors' code:** `emdann/GWT_perturbseq_analysis_2025` at
  `848d62fc2b7027f7218d6fc5f5b0c37255dc94af`, MIT, copyright (c) 2025
  Emma Dann. Upstream `LICENSE` SHA-256:
  `c475d3e1e7f7be9870c2dd8504180458d791676e843b077bcaa71d28bb414648`.

spot distributes only the derived/public artifacts named by its release manifests.
The large public Stage-1 source and score artifacts are identified by immutable
Hugging Face revision and per-file hashes; local acquisition paths are not provenance.

## Perturb2StateModel

The optional secondary Stage-2 lane refers to `emdann/pert2state_model` at commit
`2c2e30959ffafadecc6af5d4d7b5bde868ab5313`.

> MIT License — Copyright (c) 2025, Emma Dann

The exact upstream `LICENSE` has SHA-256
`d48090a9395192c9e988a495f5fe0bc96c5194b3611435baf4b2a4ca8000657e` and is available at
<https://github.com/emdann/pert2state_model/blob/2c2e30959ffafadecc6af5d4d7b5bde868ab5313/LICENSE>.
If upstream code is copied or substantially vendored, its complete MIT notice must be
retained with the copy.

## Reactome V97 pathway data

Reactome V97 was released 23 June 2026. The current Stage-2 cache uses human pathway
annotation files from that release. Reactome database data and files derived from it are
CC0 1.0; software, diagrams and branding have different licenses and are not included by
that statement.

- Release notice: <https://reactome.org/about/news/295-v97-released>
- License: <https://reactome.org/license>
- Frozen raw files: `ReactomePathways.gmt.zip`
  (`8c1dbc8578431da5d2d5118262718c60b553a9be3398e93658daa069e4a9afd4`) and
  `ReactomePathways.txt`
  (`f6d7a2bf89b5bcfe0250a0bc7f51bff94641447911712b8ff129f5b55e52df3a`).

Attribution is encouraged: Reactome is a collaboration among the Ontario Institute for
Cancer Research, Oregon Health & Science University, New York University Langone
Medical Center and EMBL-EBI.

## Gene Ontology Biological Process data

Gene Ontology data and data products are CC BY 4.0. The Stage-2 cache uses
`go-basic` release 2026-06-15 and the human GOA GOC snapshot 2026-05-21. Raw-file pins:

- `go-basic.obo`:
  `c72fc198a86983d55e43aac585d1ffdbeb6e3601475b3f18b6045acdc0a0734c`
- `goa_human.gaf.gz`:
  `db472faff1785878521693af62646546cea6af4a386609dd01c72c0554a46a30`

Required attribution: Gene Ontology Consortium and UniProt-GOA/EMBL-EBI; license
<https://creativecommons.org/licenses/by/4.0/>; source and citation policy
<https://geneontology.org/docs/go-citation-policy/>. spot's propagated BP sets are
modified derivatives and are identified as such in their run manifest.

## ChEMBL and UniProt

No unversioned ChEMBL or UniProt dump is bundled in Git. When a content-addressed
Stage-3 artifact uses them:

- ChEMBL database content is CC BY-SA 3.0 Unported. Record the exact release/DOI,
  preserve attribution and apply share-alike to redistributed adaptations. Do not
  redistribute commercially calculated properties without separately clearing them.
  Official terms: <https://chembl.gitbook.io/chembl-interface-documentation/frequently-asked-questions/general-questions>.
- Copyrightable UniProt database content is CC BY 4.0. Record the release/query and
  accessions, preserve attribution, and retain UniProt's warning that patents or other
  rights may apply. Official terms: <https://www.uniprot.org/help/license>.

License records above were rechecked against the official provider pages on 13 July
2026. Downloaded database bytes are admitted only when a run manifest also records the
exact version, URL, hash and transformation.
