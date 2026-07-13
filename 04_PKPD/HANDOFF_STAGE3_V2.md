# Stage-4 → W16: what Stage 4 needs before it can admit `spot.stage03_drug_annotation.v2`

**Status: the seam is CLOSED, and every v2 bundle is refused today.** That is deliberate, and it is
not readiness. Stage 4's v2 tests prove exactly one thing — that the door is shut. They prove
nothing about whether Stage 4 can *read* a v2 bundle, because no real one exists to read.

The authority is code, not this file: `analysis/stage3_v2_seam.py`. If the two ever disagree,
believe the code.

```
STAGE3_V2_SCHEMA_SET_SHA256 = None     # analysis/stage3_v2_seam.py:53   ← unpinned = closed
STAGE3_V2_VERIFIER_ENTRY    = None     # analysis/stage3_v2_seam.py:64   ← unnamed  = closed
```

---

## The four blockers. All yours to close.

### 1. ONE canonical document filename

You emit **`drug_annotation.v2.json`**; your fixture uses an underscore variant. Stage 4
*discovers* a contract by DECLARATION — it reads every JSON in the bundle and asks what it says it
is — so it sees both, and refuses both. But the **v2 adapter must open a real file**, and two names
for one document is a contract with a hole in it.

Give me one name for the document and one for the manifest. Not a preference — a commitment.

### 2. The schema-set sha256, **published by you**

Stage 4 re-derives it from the bundle's own bytes and compares against the pin. A hash Stage 4
computes for itself pins nothing — it would just be Stage 4 agreeing with Stage 4.

### 3. The **v2** external-verifier entry point

Stage 4 currently shells out to `python -m verifier.verify_stage3`. **That is v1's verifier.** Point
it at a v2 bundle and it judges the v2 contract by v1's rules, or judges nothing at all — and
either way it exits, and the bundle gets recorded as externally verified.

That is not a weaker gate. It is **a gate that reports PASS without having looked**, while the
operator believes gate 2 ran. Stage 4 will not call it on a v2 bundle. Name the v2 entry point.

### 4. Your fixture carries a stale `DISP_NON_RANKABLE_ASSERTION`

A fixture that disagrees with the contract it is meant to demonstrate **will be believed over the
contract** — by me, by the next reader, and by whatever gets built against it.

---

## The Stage-2 aggregate you must actually consume

You currently expect an **invented** Stage-2 aggregate envelope. A Stage-3 bundle standing on a
synthetic Stage-2 shape carries synthetic numbers into Stage 4 **under a real bundle's name** — and
every hash downstream would be a self-consistent hash of a fiction. That is the failure a green
test suite cannot see, and the reason this is a blocker rather than a nit.

The real one:

| | |
|---|---|
| manifest | `spot.stage02_run_manifest.v3_topology_only`, carrying `bundles[]` + `stage1_v3_release` |
| external report | `spot.stage02_run_manifest_verification.v1` |
| report must carry | `verdict=admit` · `generator_is_not_verifier=true` · `n_failed=0` · manifest hashes equal · `topology`/`release`/`admission` all true |
| **absent by design** | **no `artifact_class`, no `admits` block** |

That last row is load-bearing in both directions. An earlier version of this seam *required*
`artifact_class == analysis` of a v2 bundle — a **v1** concept — which would have refused every real
v2 bundle for a field you never agreed to emit. Stage 4 does not get to invent your fields, not
even the ones it is used to. If I have assumed anything else about v2 below, say so and I will
remove it.

## What Stage 4 will check of the v2 bundle

Requirements on the **contract**, not claims about its fields:

- `schema_version == spot.stage03_drug_annotation.v2`, stated in the document
- one canonical document + manifest filename (blocker 1)
- a published schema-set sha256 Stage 4 re-derives from the bundle's own bytes (blocker 2)
- gate 2: your v2 external verifier has **passed**, out-of-process (blocker 3). Emitted is not admitted
- built on the real Stage-2 aggregate above — not an invented envelope
- an immutable candidate identifier per candidate, stable across the whole chain
- per-source provenance: locator, licence/terms, `raw_sha256`, and the source's own release
- an explicit typed **origin** per lever, so MEASURED and INFERRED are never fused
- explicit missingness — a lane you did not evaluate says so, rather than arriving empty
- **no** combined objective, **no** p/q value, **no** rank

---

## What happens the moment you commit a real bundle

1. Stage 4 pins your exact schema set + verifier entry — **deliberately**, one edit each, after
   re-reading your handoff. Never a silent widening to accept whatever arrived.
2. Stage 4 writes the **actual v2 adapter** — against the fields you published. Not a v1 wrapper:
   a v1 reader that "works" on a v2 bundle is the misreading, not the fix.
3. `SPOT_STAGE3_V2_BUNDLE=<your exact path>` and the literal chain runs on those bytes:

   ```
   run_acquire → run_materialize → verify_bundle
     → run_stage4 --require-external-verifier → verify_stage4
   ```

   The harness is already written and armed (`tests/test_stage3_v2_real_chain.py`). It **skips**
   today, loudly, naming what is missing. **A skip is not a pass**, and it is not counted as one.
4. Mutation attacks land with it: a swapped bundle, a swapped verification report, a swapped schema
   set — each must be refused **by name**, because a bundle that verifies against *someone else's*
   report is the exact shape of a self-consistent lie.
5. Stage 4 emits its native `scorecard_set.v1`.

Until all of that: no drug is ranked, and no real Stage-4 result is claimed.
