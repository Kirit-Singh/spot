# Stage-2 solver-lock (env-lock) binding — producer contract ⇄ independent verifier

The Stage-2 deterministic solver lock is committed verbatim on the producer
(`stage02_solver_lock.txt`, sha256 **`2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe`**,
commit `c1f8e80`). Committing the file is not the same as **binding** it: a lock nobody's
identity depends on can be swapped or dropped and nothing would notice. This spec defines the
binding W18 lands and the named gates W4 verifies from the shipped bytes, for the **pathway**
and **temporal** lanes.

## What exists today

`runid.env_lock_block(path) -> {name, sha256, status}` already hashes the env-lock file and
`environment_lock` is bound into `run_binding` for pathway (`run_pathway_arms.py:173`),
direct-arms (`run_arms.py:230`) and temporal (`run_temporal.py:195`). But `--env-lock` is
**optional** (`default=None`): a run given no lock binds
`{sha256: null, status: "environment_lock_not_supplied"}` and still admits, and a run given the
*wrong* lock binds a different sha and still admits — nothing checks the sha against the pinned
release.

## Producer contract (W18) — across all 15 invocations

1. **`--env-lock` is accepted and REQUIRED** by every one of the 15 invocations (the 3
   signature-matrix Step-0 emitters + the direct / temporal / pathway all-arm producers).
   A run with no lock REFUSES at the producer (`REFUSE_ENV_LOCK_ABSENT` or equivalent).
2. **The FULL lock sha256 is BOUND into method/run provenance.** `environment_lock.sha256`
   enters `run_binding` (→ `pathway_run_id` / `temporal_run_id`) as it does today, and — so it
   is part of *what the run is*, not a loose sidecar — the same sha is carried where the method
   identity is hashed. A run that swapped the lock keeps neither the same run id nor the same
   method id.
3. The bound value must equal the **pinned Stage-2 solver lock** sha
   `2983d140…`. Pathway and temporal run the same `spot-run` env, so both bind the same lock;
   the Stage-1 lock (`stage01_solver_lock.txt`, a different env) is refused by sha.

## Independent verifier gates (W4) — from shipped bytes

Read `run_binding.environment_lock` from the shipped provenance and verify:

| Gate | Requirement |
|---|---|
| `the_stage2_solver_lock_is_bound_into_the_run_identity` | `environment_lock.status == "locked"` **and** `environment_lock.sha256 == 2983d140…` (the pinned Stage-2 lock). The block is inside `run_binding`, so it is covered by the existing run-id re-derivation (`V_IDENTITY` / the temporal id gate). |

Named refusals:

- **MISSING** — `status != "locked"` or `sha256 is null` → REFUSE (fail-closed: an unbound
  environment is not a reproducible one).
- **SWAPPED** — `sha256 != 2983d140…` → REFUSE (a different lock, however self-consistent after
  the run id is resealed).

The pinned sha `2983d140…` **is** frozen in the verifier — unlike a per-run value (the W10 mask),
it is a released, committed pin (`c1f8e80`), and the whole point is to check bound == pinned.

## Attack (resealed) — must fail at the named gate

Corrupt `run_binding.environment_lock` (drop it → missing; change the sha → swapped) and reseal
the run id from the binding. Every internal statement agrees; the run id re-derives; only the
comparison to the pinned lock refuses it.

## Scope

- **Pathway:** implemented in `verify_signature_matrix.py` + `test_signature_matrix_forgery.py`
  (this branch), verified against the real `environment_lock` binding.
- **Temporal:** the same gate is added to `temporal/verify_temporal.py` (a separate lane/verifier)
  once W18's producer commit lands.
- Real-run W10 Direct-mask verification remains separately required and unaffected by this gate.
