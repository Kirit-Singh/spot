# Stage-2 Direct — handoff after the code-only audit NO-GO

Answers the audit checkpoint
`~/.spot-runs/20260712T021343Z/DIRECT_CODEONLY_AUDIT_CHECKPOINT.md`
(sha256 `3a1c30f2fa636bf7e99e034a04065f9aebecaec0bdd14afdd3f76ed8d359e73c`), which was
verified byte-for-byte before any edit, alongside its stream
(sha256 `4fb9a97c2a410999b99607dd83843565d45d7fcf8d4501cf69d3f5a0e487c3a0`).

Both blockers are closed. **No independent GO has been obtained, so nothing downstream
has started** — see *Deliberately not done*.

---

## P0 — determined evidence could be downgraded to ambiguous

### What was actually wrong

The lane verified contributor COMPLETENESS (a determined scope names every guide the
source kept for it) and then took `evidence_state` itself entirely on trust. A scope
labelled `ambiguous` was examined by nothing on either side. "The identity is unknown"
was treated as a confession no source could contradict.

The forgery was free, and it needed no hand-editing at all:

1. collapse one determined scope's manifest rows to a single ambiguous row citing
   nothing;
2. let the **honest producer** regenerate the record table and the replay report.

Every count then balances by construction (determined−1, ambiguous+1, named unchanged,
complete == determined, records == offsets_proven) and every hash is correct, because
the producer computed them. The manifest and the report agree perfectly. And the raw
source is still holding that scope's two kept targeting guides.

The victim loses its mask, its score and its rank; the screen ships one fewer ranked
target. The audit built exactly this and the standalone verifier exited 0, 31/31 green.

My previous remediation missed it because it derived the determined/ambiguous split from
the **manifest rows** — which is the document under attack.

### The rule now enforced

```
provable(scope) = { g : the raw source kept a row for this (target, condition)
                        whose guide_type is TARGETING }

provable non-empty  ->  DETERMINABLE. `determined` is mandatory, and the named guide
                        set must be exactly provable(scope)  (completeness, next door).
provable empty      ->  genuinely non-determinable. `ambiguous` is the only honest label.
```

Two failure classes, named separately because they are different acts: a **downgrade**
deletes evidence the source holds; an **overclaim** invents evidence it does not.

### Where

| file | what |
|---|---|
| `analysis/direct/replay.py:172` | `source_provable_guides` — the source rule, guide_type-filtered |
| `analysis/direct/replay.py:198` | `classify_scopes` — claimed state vs source state |
| `analysis/direct/replay.py:340` | wired into `check_completeness`; a downgrade forces `INCOMPLETE` |
| `analysis/direct/verify_classification.py` | **new** — the standalone restatement (independent, not shared) |
| `analysis/direct/verify_source.py:279` | strict path calls it; both partition halves bound separately |
| `analysis/direct/verify_source.py:412` | pinned-report path requires the rule id and zero downgrades |
| `analysis/direct/manifest_replay.py` | **new** — the release gate, split out of `manifest_validate` |
| `analysis/direct/manifest_schema.py:117` | rule id + 5 report fields now **required** |
| `analysis/direct/preflight.py:95` | fresh-vs-pinned agreement now includes the classification |
| `analysis/direct/schemas/stage02_contributor_evidence.schema.json` | `n_scopes_downgraded`/`n_scopes_overclaimed` pinned to `const: 0` |

Runtime and standalone are **independent implementations**, as the checkpoint required.
The generator derives it in `replay.py`; the verifier restates it in
`verify_classification.py` and imports nothing from the generator (enforced — below).

### Only the raw source can catch it

A fully resealed downgrade is invisible to every document the producer wrote, *including
the pinned report* — a forger with the old code simply emits `n_scopes_downgraded: 0`.
`tests/direct/test_source_classification.py::test_the_forged_run_is_INTERNALLY_PERFECT`
asserts the non-strict verifier **passes** the forged run. That is not a gap; it is the
reason strict replay is the release gate and why `production` / `research_only` may not
skip it.

### Mutation proof (not vacuous)

The forger in the tests is the **pre-fix producer itself** (`_manifest_trusting_classify`),
so the run under test is sealed by an honest program and is malformed in no way a
consistency check can reach. Reverting the two classification call-sites and re-running:

```
tests/direct/test_source_classification.py + test_manifest_attacks.py
  pre-fix code : 11 failed, 33 passed
  fixed code   : 44 passed
```

The refusals are asserted **by named check**, and asserted *not* to be incidental
(no sha256 / run_id / schema / directory-name failure among them).

Covered: downgrade of any scope · overclaim · genuinely-unprovable scope (no false
positive) · non-targeting controls never make a scope determinable · victim really loses
its rank · fresh-replay refusal in both release lanes · the two rules leave no gap
(relabel → source refutes the *label*; drop a guide → source refutes the *set*).

### Diagnostic ordering (found while fixing this)

`verdict` folds completeness in, so it can never be a record-level diagnosis: a report
with one shrunken scope said *"refused, 0 failed records"* — a sentence that names the
wrong thing and then contradicts itself. Causes are now diagnosed specific-first
(classification → n_failed → non-targeting → incomplete scopes), and the summary last.

### Summary-verdict consistency (per your mid-turn note)

`manifest_replay.py::_require_summary_is_derived` requires the top-level verdicts to be
what the report's own fields **derive**, as an equivalence in both directions:

```
complete  <->  no incomplete scope, no non-targeting citation, no downgrade,
               no overclaim, every offset proof confirmed
replayed  <->  no failed record AND complete
```

A forged *or omitted* summary fails here even when every field underneath is honest.
Mutations: `test_replay_arithmetic.py::test_an_OMITTED_top_level_verdict_is_refused`,
`test_a_WRONG_top_level_verdict_is_refused_by_summary_consistency` (5 values).

---

## P1 — Perturb2State integration regression

`tests/perturb2state/test_stability_integration.py:72` called the retired
`direct.projection.rank_rows(..., "balanced_a_to_b")`, and ranked a `balanced_skew`
column. Both are gone; Direct publishes two independent rankings and no combined
objective.

**No combined ranking API was restored.** The test now asserts the contract the
checkpoint specified:

- both arms' **score and rank columns are byte-identical** across the P2S merge
  (`pd.testing.assert_series_equal`, dtype-checked, row order asserted first);
- P2S gives the *opposed, bottom-ranked* target its strongest support and it **stays
  last in both arms** — the promotion a combined objective would have allowed;
- P2S adds **only** `perturb2state_*` fields, and no combined/headline column re-enters;
- `rank_rows` is asserted **absent**, `rank_arm` present, `COMBINED_OBJECTIVE_PERMITTED`
  and `HEADLINE_ARM_PERMITTED` both `False`.

---

## Verification

```
python -m pytest tests/           ->  823 passed,   6 skipped   (was 779 passed, 1 FAILED, 6 skipped)
python -m pytest tests/direct     ->  803 passed,   5 skipped
shuffled tests/direct, seeds 1 / 7 / 20260712  ->  803 passed, 5 skipped  (each)
```

Skips are opt-in only: 5 real-release tests (`SPOT_STAGE2_RELEASE_TESTS` unset) and 1
pre-existing `pert2state_model` import skip. Flag confirmed unset.

Structural: `compileall` clean · every module ≤ 500 lines · both JSON schemas valid ·
canonical fixture conforms · no debris.

Systematic proofs (AST, docstrings excluded):
- no executable remnant of the retired pinned-preflight gate anywhere (`verify_binding`
  names it only to refuse it);
- every `balanced_skew` / `combined_*` occurrence in Direct is a **denylist entry or a
  refusal flag** — nothing restored;
- the verifier's only dense layer read is `read_pooled` (the pooled-main DE, required);
  no support layer is ever opened;
- **independence hardened** (checkpoint's low-priority item): the scan now *discovers*
  every `verify_*` module (9) and every producer module (24) instead of hardcoding six
  and eighteen, and asserts no verifier imports any producer. It previously omitted
  `verify_method`, `verify_project` — and would have omitted `verify_classification`.

---

## Deliberately NOT done — blocked on independent code-only GO

Per the stated order, **none** of this has begun, and I am the sole writer:

- pathway layer (gene sets, enrichment, convergence clustering);
- generic typed Stage-1 selection contract (A / direction_A / B / direction_B / analysis
  mode; same-condition vs cross-condition temporal estimator);
- explicit Stage-2 combined ordering (frozen rule or Pareto over the two arms);
- Stage-1 bridge materialization;
- strict preflight and any real tcefold run. No real DE / pseudobulk file was opened;
  everything ran on synthetic fixtures.

---

## For the next auditor

1. **P2S keeps an internal `combined_A_to_B` signature lane** (`analysis/perturb2state/
   config.py:49`, `SUPPORT_LANE`). It feeds `perturb2state_support_status` — a secondary
   support field — and is **not** a Direct rank. The audit did not flag it and I did not
   change it, but it is the nearest thing to a combined objective still in the tree and
   you should decide about it explicitly rather than inherit it.
2. `manifest_validate.py` was split into `manifest_validate.py` (sources + rows) and
   `manifest_replay.py` (the release gate); `verify_source.py` was split to extract
   `verify_classification.py`. Both splits were forced by the 500-line limit and are
   purely structural.
3. The strongest single thing to re-attack: build a downgraded run with
   `_manifest_trusting_classify` patched in, then confirm **strict** verification fails
   on the named source-classification check and **non-strict** still passes. If
   non-strict ever starts passing a *fresh* release lane, the gate has been bypassed.

## Files changed (18)

`analysis/direct/`: `replay.py` · `manifest_schema.py` · `manifest_validate.py` ·
`manifest_replay.py` (new) · `manifest.py` · `preflight.py` · `verify_source.py` ·
`verify_classification.py` (new) · `verify_evidence.py` ·
`schemas/stage02_contributor_evidence.schema.json`

`tests/direct/`: `test_source_classification.py` (new) · `test_manifest_attacks.py` ·
`test_determinism.py` · `test_source_replay.py` · `test_replay_arithmetic.py` ·
`test_contributor_schema.py` · `test_audit_probes.py`

`tests/perturb2state/`: `test_stability_integration.py`

No commit, push, reset or clean. No other worktree touched.
