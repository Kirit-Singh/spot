# Stage-3 dev preview — real drugs, two selections

**`treg_like decrease → th1_like increase`** at **Rest** and **Stim8hr**. Real Stage-2 Direct arms,
real ChEMBL/UniProt universe. **No fixtures. No invented values.**

## Paths + hashes

```
/home/tcelab/.spot-runs/stage3-ui-dev-20260713/
  stage03_drugs_rest.json    content_sha256 ba0d522be4b9a7e25e4d015cfaf7d8c4b21a0564872ecb412fbae74f9f7dc32f
  stage03_drugs_stim8.json   content_sha256 f69e6e23a3b32b1c21a4f3e3c3b8a7174419659e47db440d8af0c27f9205971d
  *.sidecar.json             internal only — exact filesystem paths live HERE, never in the served doc
```

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
