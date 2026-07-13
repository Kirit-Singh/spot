# Stage-3 dev preview — real drugs, two selections

**`treg_like decrease → th1_like increase`** at **Rest** and **Stim8hr**. Real Stage-2 Direct arms,
real ChEMBL/UniProt universe. **No fixtures. No invented values.**

## Paths + hashes

```
/home/tcelab/.spot-runs/stage3-ui-dev-20260713/
  stage03_drugs_rest.json    content_sha256 40546baccb1f1a2b46971fa962dc3ad7527a9df94721daec6d1d9117834a7701
  stage03_drugs_stim8.json   content_sha256 baf21007b332b04ebca37e65a6a595a483cda44fc1f0961a8c1a5b2154a33e74
  *.sidecar.json             internal only — exact filesystem paths live HERE, never in the served doc
```

**HASHES MOVED.** An AGONIST row was correctly `opposed` and still carried
`evidence_relation: putative_crispri_phenocopy`. An agonist phenocopies **nothing that was tested** —
CRISPRi never tested activation. `evidence_relation` is now decided by the frozen
`modality_rule.classify`, and the invariant holds on every row: **relation is a phenocopy IFF
`mechanism_phenocopies_modality` is true** (0 violations, 0 equivalence claims).

TNFRSF18 / TRX-518 [AGONIST] @ Rest now reads:
`status=opposed`, `relation=untested_inverse_of_the_tested_perturbation`,
`mechanism_phenocopies_modality=false`.

Raw arm ranks and values are **unchanged**.

Schema: `spot.stage03_ui_drugs.v1`

## What's in it

| | Rest | Stim8hr |
|---|---|---|
| evaluable targets / arm | 6,815 | 7,118 |
| shown (display top-N by Stage-2 rank) | 200 | 200 |
| drug rows | 142 | 73 |
| `observed_perturbation` (inhibitor, supporting sign) | 70 | 32 |
| `opposed` | 60 | 8 |
| `unresolved` (action not enumerable) | 12 | 33 |
| real gene symbols | 400/400 | 400/400 |

Real example: **TNFRSF18** (ENSG00000186891), rank 15, value 1.369 → **AEE-788** [INHIBITOR],
`chembl:CHEMBL_37:drug_mechanism/4614`.

## Rules it follows

- **Direction is the frozen engine** (`direction.py`), not a local copy. `PARTIAL AGONIST` →
  `unknown`, deliberately: its net effect is not enumerable from the action string, and guessing
  would manufacture a direction the source never asserted.
- **The sign decides.** `value > +ε` → inhibition observed-compatible. `value < −ε` → an inhibitor
  is **opposed**, and an agonist is an **untested inverse hypothesis** — CRISPRi never tested
  activation, so it is never "supported".
- **Identity is Stage-2's**, from `target_identity.json` (symbol, namespace, modality). Never inferred
  from an id's shape.
- **`top_n` is display truncation, not scientific filtering** — `n_evaluable` gives the full set.
- **Pathway contexts are empty**, and say why (`pathway_context_status`): the GO-BP bundle carries arm
  summaries, not gene sets. A null `set_id` would be context that names nothing.
- **`admission.receipt_verified: false`** — the aggregate receipt chain was bypassed for this preview.
  It is a field, not a footnote.
