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
| `spot.stage04_evidence_inputs.v2.schema.json` | **Current.** The evidence input records, one row per actual observation, each bound to a source response hash — plus the v2 acquisition contract (see below). |
| `spot.stage04_evidence_tables.v2.schema.json` | **Current.** The parquet tables: exact column order, dtypes and sort key. Row/column order is part of the contract — `content_sha256` is taken over the canonical rows in this shape. |
| `spot.stage04_evidence_inputs.v1.schema.json` | **FROZEN.** Superseded by v2, never regenerated, bytes pinned by a test. |
| `spot.stage04_evidence_tables.v1.schema.json` | **FROZEN.** Superseded by v2, never regenerated, bytes pinned by a test. |

## v1 → v2

v2 adds what an ACQUISITION has to be able to show: a `SourceAcquisitionRecord` per source
(canonical query, `accessed_at_utc`, HTTP status / media type / selected headers, release or
`last_updated`, the exact terms URL, raw bytes + hash, a stable content hash for volatile
envelopes, the extraction transform, the adapter code hash, review status, and an explicit
observation state), structured assay bindings on potency and transporter rows, structured PK
metric / sampling / fraction-unbound / reported-vs-derived-ratio fields on exposure rows.

**The migration is additive.** Every v2 field is optional on the model, so a v1 document still
validates and still means exactly what it always meant. That is why the v1 files are frozen
rather than rewritten: "backwards compatible" is a claim about the *old* contract, and a claim
you can silently edit is not a guarantee.

**Validating is not being complete.** A v1 document does not become acquisition-complete by
passing the v2 models. To be acquisition-complete a document declares
`spot.stage04_evidence_bundle.v2` and satisfies `analysis/contract_profile.py`, which requires
the acquisition manifest and the per-lane bindings. Production acquisition requires v2; a v1
bundle is admissible for fixture and research runs and can never claim completeness.

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
