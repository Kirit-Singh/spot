# Stage-2 ← Stage-1 consumer repair (W-consumer-v3)

**Branch** `agent/stage2-stage1-consumer-v3` · **commits** `b4981cd` (consumer repair) · `2044da8` (method identity + tuple space)
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
| temporal method | `343f20db…587c4b5` | **bound + preserved, never re-derived here** — a different quantity from this branch's code-tree hash; see *The method identity* below |

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

- `declared_method_identity()` + `REFUSE_METHOD_IDENTITY_MISSING` (`2044da8`) — the declared
  estimand identity, carried verbatim and labelled; see *The method identity* below.

**Tests** — `fixtures_stage1_contract.py` (new): stages the schema / release / Stage-1's own
fixtures from git at `539431dd`, skipping loudly when the ref is absent, exposes the release's
real enum space (`release_selector()`), and re-implements the question_id recipe
**independently** (a test where the gate agrees with itself proves nothing). New suites:
`test_stage1_question_id.py`, `test_stage1_tuple_space.py`, `test_stage1_method_identity.py`,
`test_verify_identity_v3.py`. `test_v3_axis_identity.py`: the test asserting the *defect* — that
same program+direction across different times is refused — is **inverted**; it contradicted its
own module docstring.

## Test counts

Full Stage-2: **1870 passed, 4 skipped, 0 failed** (baseline at `9bd5895`: 1770 / 4 / 0).
**+100 tests, no regressions, and no pre-existing failures** — the 4 skips are the same
pre-existing opt-in ones (`test_manifest_build`, `test_release_integration`). `ruff` clean.

Focused: `test_stage1_v3` 49 · `test_stage1_question_id` 37 · `test_stage1_tuple_space` 31 ·
`test_stage1_method_identity` 16 · `test_verify_identity_v3` 11 · `test_stage1_v3_selection_id` 10 ·
`test_v3_axis_identity` 15 · `test_stage1_release_v3` 25 · `test_temporal_v3` 13 · `test_cli_v3` 19 ·
`test_preflight_v3_parity` 17 · `test_stage1_interop` 15.

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

## The method identity: bound, preserved, never conflated (orchestrator decision, applied)

Two different hashes wear the name `method_sha256`, and they are **not** the same quantity:

| | what it is | who mints it |
|---|---|---|
| `contract.estimator.method_sha256` = `343f20db…` | Stage-1's **estimand-identity** hash — *what* is estimated. Stage-1 states it is *"NOT a code-tree or batch/confound policy hash"* | externally bound, from `spot-stage2-temporal-arms@276a9ad` |
| `estimator_registry()[…]["method_sha256"]` | an **implementation** binding over code trees + frozen batch policy — *which code* runs | this branch |

**They are never compared.** A gate on equality would refuse the authoritative contract — and
because the code-tree hash moves on *every* Stage-2 edit (this repair moved it,
`4aac8881…` → `91da96bd…`), it would break the contract whenever anyone touched the code. That
is not a safety property; it is an outage. `test_the_LOCAL_hash_moves_when_the_CODE_moves…`
demonstrates it rather than arguing it.

The declared identity is therefore:
- **verified and preserved through the fully verified Stage-1 bytes** — the contract's own
  re-derived `full_contract_content_sha256`, the pinned `f810` schema, the admitted `539431dd`
  release. Editing it in flight breaks the content hash (tested);
- carried verbatim into `bind()` and **into the run identity** (`binding_block`), so a run
  cannot be re-attributed to another method and Stage-3 receives it;
- **labelled**, in machine-readable form, so the limit travels with the value rather than
  living in a comment: `identity_kind=stage1_estimand_identity_hash`,
  `is_not=stage2_implementation_code_tree_hash`, `rederived_by_stage2_direct=false`,
  `rederivation_owner=spot.stage02.temporal.producer_verifier.W5_W11`,
  `anchored_by=[full_contract_content_sha256, selection_schema_sha256, admitted_stage1_v3_release]`.
  (Same *bound-as-declared* pattern the release loader already uses for the scorer projection hash.)

Re-deriving the **implementation-code** binding is left to the temporal producer/verifier
(**W5/W11**) and is explicitly out of scope here. The one check that can be made *without*
conflating the two is enforced: an estimator that **names** a method must **bind** one
(`REFUSE_METHOD_IDENTITY_MISSING`) — Stage-1's own words, *a contract naming no method hash has
admitted a word*. It is generic over any estimator, so the next one inherits it.

## The tuple space is walked, not sampled

`test_stage1_tuple_space.py` enumerates the cross-product rather than picking examples:

- **within_condition** — all 108 tuples (3 programs × 2 directions, squared, × 3 conditions):
  **90 admit, 18 refuse** (exactly the identical-endpoint cases);
- **temporal** — all **216** ordered tuples **admit**. *Nothing* in that space is degenerate:
  the conditions differ, so the endpoints differ, whatever the programs and directions say;
- **300** tuples over the **ten programs the authoritative release actually admits**, read from
  its selector rather than retyped;
- all **306** admitted questions get a **distinct, re-derivable** `question_id` (injective over
  the space), and `Rest→Stim48hr` ≠ `Stim48hr→Rest`;
- every **impossible** tuple refuses **by its own typed reason**: identical endpoint, a
  condition compared with itself, a condition count contradicting the mode, a
  direction/condition/mode outside its enum, a borrowed estimator, an incoherent estimator
  block, a named method with no bound identity.

Program ids are policed by the **effect universe**, not the schema (they are free strings
there) — so that is asserted where the check actually lives, not where it would look tidier.

## The identity split (done)

`stage1_v3.py` was 1092 lines against the ≤500 rule. The identity derivations — `question_id`,
`selection_id`, the pole/endpoint identities, the declared method identity, the biology key, and
their published rule ids — now live in **`analysis/direct/stage1_v3_ids.py`** (300 lines).
`stage1_v3.py` is **859**. **This module GATES; that one DERIVES.**

Behaviour is preserved exactly: all 29 identity names are **re-exported** from `stage1_v3` and
resolve to the *same objects* (asserted, not assumed — a shadowing copy would drift in silence),
so every lane, runner and test keeps naming them through the module it always did. An identity
that quietly changed its import path would be an identity that changed.

`stage1_v3_ids` imports **nothing but `hashing.content_hash`** (asserted by AST): identity must
not be able to move because a config, a policy or a release moved.

`stage1_v3.py` at 859 lines is still over the 500-line rule. What remains is genuinely the gate
(the refusal ladder in `validate`) plus the release/axis binding and the run-id block; the next
natural cut is `bind_axis` + `stage2_run_binding`/`stage2_run_id`. Not done here — it is a
different seam, and CLAUDE.md says never reorganize silently.
