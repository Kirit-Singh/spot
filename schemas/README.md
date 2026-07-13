# spot shared artifact schemas

Versioned, content-addressed cross-stage contracts. All canonical hashes use **stable key ordering,
stable row ordering, defined float rounding, and EXCLUDE timestamps / display-only labels / machine-local
paths**. Prefer running the named verifier (expect exit 0) over trusting any hash copied into this file —
provenance/display edits legitimately re-derive a registry's self/raw hash without changing the science.

## `spot.stage01_program_registry.v3`
Served at `01_programs/app/data/stage01_program_registry_v3.json`; emitted by
`01_programs/analysis/gen_stage1_provenance.py` (marker provenance) over the frozen scoring registry.
Per-program: `program_id`, `score_field`, `role`, `base_portable`, panel + frozen `control` symbols/Ensembl
(honest `null` for genes absent from the effect universe), coefficients, `scoring_method`, effect-universe
coverage, and structured per-marker `marker_provenance`/`panel_provenance` — **bounded locators that record
where each marker was reported for its program, not a validation of cell/program identity**. A locator's
citation is provisional until an independent citation-verifier lane marks it `verified`; a `verified` locator
confirms the *reference*, never that the score is a cell type or that the marker proves lineage/function.

Frozen, citation-invariant scientific identities: scores canonical `43c4296d…`, frozen validation raw
`1c14cd28…`, **scorer projection** `008c1da1…` (the scoring-core invariant that must never move). The
registry `registry_sha256` (canon over ordered content, `ensure_ascii=True`, excluding only that field) and
its raw hash re-derive on provenance/display edits — **verify with `verify_stage1_provenance.py`** (fail-
closed; re-derives every marker record from pinned source artifacts and re-checks the scorer projection).
`spot.stage01_program_registry.v1` (`stage01_program_registry.json`) is `HISTORICAL_NOT_CURRENT`.

## `spot.stage01_selection.v3`
Schema: `01_programs/analysis/stage2_bridge/schemas/spot.stage01_selection.v3.schema.json`. Deterministic
**materializer**: `01_programs/analysis/stage2_bridge/emit_selection_contract.py` `build_contract(...)`,
mirrored byte-for-byte in the Stage-1 app `01_programs/app/01_page.html`. Independent semantic verifier:
`01_programs/analysis/stage2_bridge/verify_selection_contract.py`.

The generic selector emits the **same typed contract** for ANY (program A, direction A, program B,
direction B, condition/mode):
- `execution_status` — `ready` | `refused` | `awaiting_estimator`; `analysis_mode` —
  `within_condition` | `temporal_cross_condition`; bound `estimator` (id/status/method identity).
- Two **ordered, separate poles** A/B and `combined_objective: null` — **no** combined/balanced/weighted
  objective (that is Stage-2's).
- Two **independent per-program arms** `{away_from_A, toward_B}`, each keyed by the perturbation's
  **desired change** (`increase|decrease`), never the pole `high|low` or the role — frozen mapping:
  `away_from_A(high)=decrease`, `away_from_A(low)=increase`, `toward_B(high)=increase`, `toward_B(low)=decrease`.
  Arm keys: `direct|program|desired_change|condition`, `temporal|program|desired_change|from|to`,
  `pathway|program|desired_change|condition|source`. `arm_keys.py` is the single source of truth.

`selection_id = sha256(canonical_content)[:16]`, where `canonical_content` (scientific content only — no
timestamps/labels/paths/floats) binds the executable **scorer VIEW** hash
(`registry_scorer_view_sha256 = 5d1d8c36…`), the source h5ad (`2edc6d31…`), the HF revision (`e5fcf98b…`),
and `stage1_method_version=stage1-continuous-v3.0.1`. The whole artifact is additionally bound by
`full_contract_content_sha256`. Refuse only an exactly-identical `(program, pole, condition)` tuple; the
frozen selector admits 3,540 valid ordered selections over 10 base-portable programs. The retired
`spot.stage01_selection.v1` (`contrast_id`, `balanced_a_to_b`/`away_from_a` objectives, v2 method) is gone.

### `stage01_stage2_registry_view.json` (scorer VIEW)
The minimal executable projection `selection_id` binds (canonical `5d1d8c36…`, rebuilt independently by
`01_programs/analysis/stage2_bridge/build_registry_view.py`): programs, panel/control symbols + Ensembl, coefficients,
`base_portable`. Excludes display labels, citations and provenance, so those never move `selection_id`.

## Downstream (Stage 2/3/4)
Each downstream stage owns its current schema + verifier: Stage-2 emits two independent reusable arms and
their gene/pathway outputs (no combined score; any pair-derived Pareto/concordance is join-time display
only). Stage-3 maps verified Stage-2 arms/pathway nodes to direction-compatible ChEMBL/UniProt evidence.
Stage-4 emits six separate evidence lanes with **no** composite score, ranking, traffic light or
recommendation. Each references the exact upstream artifact hash for referential integrity; see the
respective stage README + verifier for the authoritative current schema IDs and entry points.
