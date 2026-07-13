# Stage-2 ← Stage-1 consumer repair (W-consumer-v3)

**Branch** `agent/stage2-stage1-consumer-v3` · **commit** `b4981cdd2deb056232531bf3f32c614a867f2d20`
· **base** `9bd5895` · **Stage-1 contract** `539431dd8d87a3d763fb69ab44ed44bc98631d5a`
(branch `stage1-temporal-estimator-repair`). Coordinated by the orchestrator.

Stage-1 artifacts are consumed **as data, read from git at the pinned commit**. No Stage-1 UI
change is merged, and nothing Stage-1 owns is copied into `02_geneskew/`.

## Pins — all four verified against the real bytes

| what | pin | where it is enforced |
|---|---|---|
| selection schema (raw) | `f8104283…c4c1d` | `stage1_v3.SCHEMA_SHA256`, checked in `load_schema()` before use |
| v3 release (raw) | `0c336546…bef73` | `stage1_release_v3.ADMITTED_STAGE1_V3`, checked in `load(admit=…)` |
| v3 release (self) | `2262430931…24a11` | same, re-derived from bytes, never read |
| temporal method | `343f20db…587c4b5` | **bound, not gated** — see the escalation below |

The previous pins were **stale**: schema `f4c2c2cc…` (a superseded schema whose only copy
lived at `~/.spot-runs/…/stage1-ui-contract/`, outside the repo — so every Gate-B test was
green against a schema no commit records), and release `55899ac` / self `9bc85170…`.
Both are now named as RETIRED rather than deleted.

## What changed

**`analysis/direct/stage1_v3.py`** (+232)
- schema pin → `f810…`; `STAGE1_CONTRACT_COMMIT`; the stale pin kept as `RETIRED_SCHEMA_SHA256`.
- `derive_question_id()` — Stage-1's exact ordered biology-only recipe:
  `sha256(canonical_json({A:{program_id,direction,condition:conditions[0]}, B:{…,condition:conditions[-1]}, analysis_mode}))[:16]`.
  Published as `QUESTION_ID_RULE_ID` / `QUESTION_ID_RULE`. **Refused on mismatch**
  (`REFUSE_QUESTION_ID`), checked *after* the biology-split and endpoint gates so the refusal
  names the defect, not its consequence.
- **endpoint identity** (`ENDPOINT_RULE`): pole A @ `conditions[0]`, pole B @ `conditions[-1]`.
  Refuse only when `(program, direction, condition)` is identical on **both** poles
  (`REFUSE_DEGENERATE_AXIS`). Same program+direction at *different* times now **admits**.
- new impossible-tuple refusals: `REFUSE_DUPLICATE_ENDPOINT` (a "temporal" contract naming one
  condition twice — a DiD of Rest against Rest) and `REFUSE_ESTIMATOR_INCOHERENT` (the bound
  `estimator` block contradicting the contract it rides on; the block was previously never read).
- `bind()` / `V3Selection` / `binding_block()` carry **all three ids, distinct**:
  `question_id` (which biology — stable across method revisions), `selection_id` (which
  contract asked it — binds scorer view, source, method), `selection_biology_sha256`
  (Stage-2's own run key). `as_selection` no longer substitutes the biology hash for `question_id`.

**`analysis/direct/stage1_release_v3.py`** (+50) — `ADMITTED_STAGE1_V3` + `load(admit=…)`,
refusing a non-admitted release by name (`REFUSE_NOT_ADMITTED`) on raw bytes **and** on the
independently derived self hash. `admit=None` keeps the loader generic so the synthetic
negative fixtures still reach the invariant each one targets.

**`analysis/direct/verify_binding.py`** (+59) — `verify_identity` re-derived only the legacy
32-hex recipe, so a **v3 run's identity was unverifiable**: the check could only ever have
failed on an honest run, and it was never called on one. It now branches on the v3 block in
`run_binding` (which is hashed into `run_id`, so a run cannot lie about it to be checked by the
laxer recipe), derives the question_id **from the axis that actually ran**, and cross-checks the
bound endpoints against that axis. The legacy path is untouched.

**`analysis/direct/run_screen.py`** (+12) — the v3 `id_check` now publishes `question_id`,
`question_id_rederived`, `endpoints` and the contract marker.

**Tests** — `fixtures_stage1_contract.py` (new, 200): stages the schema / release / Stage-1's own
fixtures from git at `539431dd`, skipping loudly when the ref is absent, and re-implements the
question_id recipe **independently** (a test where the gate agrees with itself proves nothing).
`test_stage1_question_id.py` (new, 348) and `test_verify_identity_v3.py` (new, 183).
`test_v3_axis_identity.py`: the test asserting the *defect* — that same program+direction across
different times is refused — is **inverted**; it contradicted its own module docstring.

## Test counts

Full Stage-2: **1823 passed, 4 skipped, 0 failed** (baseline at `9bd5895`: 1770 / 4 / 0).
**+53 tests, no regressions, and no pre-existing failures** — the 4 skips are the same
pre-existing opt-in ones (`test_manifest_build`, `test_release_integration`).

Focused: `test_stage1_v3` 49 · `test_stage1_question_id` 37 · `test_verify_identity_v3` 11 ·
`test_stage1_v3_selection_id` 10 · `test_v3_axis_identity` 15 · `test_stage1_release_v3` 25 ·
`test_temporal_v3` 13 · `test_cli_v3` 19 · `test_preflight_v3_parity` 17 · `test_stage1_interop` 15.

Four independent implementations of the question_id recipe agree: the gate, a literal
re-implementation, `jq -cS | sha256sum` (out of process), and the verifier's own derivation —
plus **Stage-1's own emitted fixtures re-derive**, which is the only check here that could not
have been faked by the gate agreeing with itself.

## Scientific bytes: preserved, and proven

A real v3 screen built at the base commit and at this one emits five parquets whose **only
differing column is `run_id`**:

```
contributing_guides · donor_support · guide_support · masks · screen
  -> 1 changed column each: ['run_id']
```

Every scientific column (scores, deltas, ranks, guides, donors, masks) is byte-for-byte
identical. **The run id moves** because the run binding now carries the contract's `question_id`
and endpoints — that is the repair, not a side effect. Editing `stage1_v3.py` also moves
`code_tree_sha256`, which feeds the same id. No production run was launched.

## ESCALATION — the temporal method hash does not match, and I did not force it to

Stage-1's contract declares `estimator.method_sha256 = 343f20db…`, which its own comment says is
the **estimand-identity** hash (content hash of the estimand block), *"NOT a code-tree or
batch/confound policy hash"*, re-derived from `spot-stage2-temporal-arms @ 276a9ad`.

On **this** branch there is no `temporal/arms` package, and `stage1_v3.estimator_registry()`
returns `4aac8881…` — a code-tree + batch-policy hash. The two measure different things, and
this branch cannot re-derive Stage-1's value.

Gating on equality would **fail-closed on the authoritative contract** and make the required
positive temporal fixture impossible — a false refusal is as damaging as a false admission. So
the declared method identity is **bound and carried** into `bind()` so any verifier can compare
it against the method Stage-2 actually executes, the *enum coherence* of the estimator block **is**
enforced, and the divergence is raised here rather than papered over. **This needs an orchestrator
decision**: either Stage-1 re-pins to the temporal method this lane ships, or the `temporal/arms`
lane lands here and the two are reconciled — at which point the equality gate should be added.

## Debt (flagged, not silently fixed)

`stage1_v3.py` is 979 lines (793 at base) against the ≤500-line rule — a pre-existing breach I
have grown. The natural split is the id/endpoint derivations (`question_id`, `selection_id`,
endpoints, the published rules) into `stage1_v3_ids.py`. I did not do it here: it would balloon
the diff an independent verifier must check, and CLAUDE.md says never reorganize silently.
