# The single typed external Direct admission contract

**Owner: W10** (independent Direct verifier). Verifier head `3119900`, separate checkout.
Scope confirmed: **ratify + complete the existing report shape**; **stay in the verifier
checkout and hand the contract to W1** — no consumer-lane edits.

## Problem

Four consumers read W10's Direct admission verdict, and they disagree about its shape:

| Consumer | Reads today | Level |
|---|---|---|
| **P2S** (`p2s_arms/w10.py`) | `bound_artifact.*`, `gates[].passed`, `independent_of_generator`, re-derives `report_sha256`, pins `verifier_code_sha256` | per-bundle |
| **run-manifest** (`verify_bundle_rules.py`, `verify_lane_admission.py`) | top-level `bundle_id`, `checks[].status`, `fail_closed`, `generator_is_not_verifier`, `binds.arm_bundle_sha256`, native `ADMIT` token → `admitted` | release + bundle |
| **temporal** (`batch_policy.v1.json`) | a **`REPORT.md`** pinned by `report_sha256` — the ad-hoc Markdown seam | per-bundle |
| **Step0** (`run_stage2.sh`) | `W10_REPORT_DIR` of per-condition reports | per-bundle |

Three shapes and a Markdown file for one fact. A reader that normalises before comparing
(`.upper()`, regex over Markdown) has thrown away the only evidence it had.

## Design

**One self-hashed JSON report, ratified as the typed contract, completed, and published with
a schema + a shared validator.** The report shape W10 already emits (and P2S already consumes)
becomes THE contract; it is completed with the two missing provenance bindings and formalised
as a JSON Schema. Consumers converge on one validator; the Markdown seam is retired.

### 1. The report (envelope), self-hashed

The existing envelope, unchanged for P2S, plus two fields:

- `bound_artifact.mask_sha256` — the mask hash W10 already binds into the run identity but did
  not surface. The mask decides every base delta, so the admission must name it.
- `verifier_commit` — the git commit of the verifier checkout. `verifier_code_sha256` says
  *which code*; `verifier_commit` says *which history* — a checkout with a matching code digest
  but no commit is bytes on a disk, not a provenance claim (the same commit/digest/clean-tree
  distinction W10 already makes for the producer).

Every required binding, all already present except the two above: exact bundle/release bytes
(`bound_artifact.artifact_sha256`), bundle id (`arm_bundle_run_id`), condition, **mask hash**,
Stage-1 scorer identity (`stage1_scorer_view_canonical_sha256`,
`registry_scorer_projection_sha256`, `scorer_view_sha256`), environment lock
(`solver_lock_sha256`, `solver_lock_pinned_sha256`), **verifier commit** + code hash
(`verifier_commit`, `verifier_code_sha256`), spec (`spec_sha256`), gate inventory
(`gate_inventory`, `gate_inventory_sha256`, `gates`), and `verdict`. Self-hash: `report_sha256`
over the body without that field.

### 2. The published schema

`02_geneskew/analysis/direct/schemas/stage02_direct_admission.schema.json` — one JSON Schema
for the shared envelope. A `subject_kind` (`bundle` | `release`) discriminates the two
`bound_artifact` shapes; the envelope (verifier provenance, verdict, self-hash, gate inventory)
is common. Two `schema_version` strings remain
(`spot.stage02_direct_arm_bundle_verification.v1`, `spot.stage02_direct_release_verification.v1`),
both validated by the one schema+validator.

### 3. The shared validator — the single seam

`02_geneskew/analysis/direct/verify_arm_contract.py`. Imports nothing from the producer.
Public API:

- `validate(report: dict) -> None` — fail-closed. Raises `ContractError` (typed reason) on:
  a missing required field; an unknown `schema_version`; a **self-hash that does not re-derive**;
  a `verdict` not byte-exactly `ADMIT`/`REFUSE`; an **ADMIT that carries `n_failed>0` or any
  `failed_gates`**; a report not declaring `independent_of_generator: true`; a **self-admission**
  (verdict pending / `verifier_id` null); a missing provenance binding (no bundle bytes, no mask,
  no env lock).
- `load_and_validate(path) -> dict` — read JSON, validate, return the report.
- `disposition(report) -> "admitted" | "refused"` — the native-token → aggregate mapping,
  **byte-exact**, no case-fold; an unknown token raises. This is the run-manifest adapter,
  replacing its ad-hoc `NATIVE` table.
- CLI: `python -m direct.verify_arm_contract --report <path>` → exit 0 valid / 1 invalid.

### 4. Compatibility adapter (the only one)

`disposition()` + a `to_lane_admission(report) -> dict` projection that carries the native
`verdict` **verbatim** alongside the aggregate disposition, so a reader sees both what W10 said
and what the aggregate made of it — no transliteration. That is the sole adapter; P2S needs
none (it reads the ratified shape); temporal drops its Markdown pin for the JSON `report_sha256`;
Step0 keeps its `W10_REPORT_DIR` of the same JSON.

### 5. Fail-closed tests + re-run prior attacks

Against the validator: `{"verdict":"ADMIT"}` stub (missing fields) refuses; a tampered report
(self-hash) refuses; a REFUSE relabelled ADMIT without reseal refuses on the hash, with reseal
refuses on the ADMIT-with-failures rule; a self-admission refuses; a report missing the mask /
bundle bytes / env binding refuses. The verifier's own gates (wrong bundle, wrong mask, wrong
env, stale, self-admission) are unchanged and re-run.

## Consequence for W1 — the P2S pin refresh

Adding two fields edits `verify_arm_report.py`, so W10's `verifier_code_sha256` **changes**
(`3bc55ba5…` → new). P2S @ `019a6b6` pins the old value and will correctly refuse W10's new
reports until W1 refreshes `W10_VERIFIER_CODE_SHA256` to the new sha at the new W10 commit. This
is the documented coupling; the handoff carries the new commit + code sha + report schema hash.

## Out of scope (YAGNI)

No new envelope; no reshape of `bound_artifact`; no consumer-lane edits; no signing (flagged
for real-data production, not built here).
