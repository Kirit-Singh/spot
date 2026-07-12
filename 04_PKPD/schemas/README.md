# Stage-4 schemas

**Generated from the code** — `python -m analysis.schemas_export`. A test regenerates them
and compares byte-for-byte, so the published contract cannot silently drift from the
enforced one. Do not hand-edit.

They follow the repo-wide cross-stage convention (root `schemas/README.md`):
`spot.stageNN_*.vN`, content-addressed, canonical hashing (sorted keys, stable row order,
fixed float rounding, timestamps/labels/machine-local paths excluded).

| file | what it is |
|---|---|
| `spot.stage03_drug_candidate_set.v1.schema.json` | **PROVISIONAL, ADAPTER-BOUND.** What Stage 4 is willing to *consume*. Stage 3 has not landed (`03_druglink/` is scaffolding), so this was authored unilaterally by Stage 4 and is **not agreed with Stage 3**. Carries `x-spot-stage3-contract-status`. Expect reconciliation via an adapter + a version bump. |
| `spot.stage04_evidence_inputs.v1.schema.json` | The nine evidence input records (property, potency, transporter, exposure, delivery, NEBPI, safety, source, context). One row per actual observation, each bound to a source response hash. |
| `spot.stage04_evidence_tables.v1.schema.json` | The four parquet tables: exact column order, dtypes and sort key. Row/column order is part of the contract — `content_sha256` is taken over the canonical rows in this shape. |

## Emitted artifacts

`outputs/<scorecard_set_id>/` holds eight files, written atomically:

- `delivery_evidence.parquet`, `transporter_evidence.parquet`, `exposure_evidence.parquet`,
  `safety_evidence.parquet` — the four evidence tables above
- `scorecards.json` (`spot.stage04_scorecard_set.v1`) — the six lanes per candidate, kept
  separate, plus a per-candidate provenance chain from every displayed field to a source
  response hash and a declared transform. Ordering is declared `is_ranking: false`.
- `manifest.json` (`spot.stage04_manifest.v1`) — the id derivation inputs, every method file
  hash, the source registry, the evidence-input hash, the environment lock, float rules, and
  per-artifact `content_sha256` + `file_sha256`
- `verification.json` (`spot.stage04_verification.v1`) — independent re-derivation: ~208
  checks over hashes, dtypes, row order and the scientific invariants
- `selection.json` (`spot.stage04_selection.v1`) — always `no_selection_emitted` in this
  pass. Stage 4 does not rank.
