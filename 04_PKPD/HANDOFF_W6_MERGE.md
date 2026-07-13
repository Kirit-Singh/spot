# W6 merge handoff — Stage-4 evidence contract v2

Self-contained. You should not need any other document to execute or abort this merge.

**This does not certify the Stage-4 chain as ready.** It certifies two things and nothing more:
that the v1 contract is frozen and provably still verifies, and that the v2 contract is wired and
green *on this branch*. The final chain remains gated — see §6.

---

## 1. Exact commits

| | |
|---|---|
| **This branch** | `agent/stage4-pk-schema` @ **`9965f201a2347b32c7eec4218c0e2c7e1c8a8aaa`** (`9965f20`) |
| Pushed | yes — `origin/agent/stage4-pk-schema` is at the same SHA |
| Base | `e410d72` (9 commits: `f32b251 … 9965f20`) |
| **Hard dependency** | W8 @ **`b287f72`** — on `origin/agent/stage4-acquisition-core` |
| Is W8 an ancestor of this branch? | **No.** It is a separate lane and must land first. |

Reviewed-but-not-merged. Nothing here has been merged to `main`.

---

## 2. Dependency: W8 lands first, and why it is not optional

Three files in this branch are **byte-identical copies of W8's**, adopted verbatim after both
lanes independently built the same thing:

| file | status |
|---|---|
| `analysis/acquisition.py` | identical to `b287f72` |
| `analysis/selection.py` | identical to `b287f72` |
| `analysis/organ_system.py` | identical to `b287f72` |

`analysis/acquisition.py` **does not exist in the common base `e410d72`.** Both lanes created it,
for the same purpose. Earlier revisions of this branch declared a rival `SourceAcquisitionRecord`;
it is deleted. If W8 does **not** land first, or if an older revision of this branch is used, the
merged tree will fail to import — not conflict, *fail to import*, which surfaces as an
`ImportError` far from its cause.

Because all three are byte-identical, the merge is a **no-op** for them and the "W8 wins duplicate
conflicts" rule never has to fire. If git nonetheless reports a conflict in any of the three:
**take W8's side unconditionally.** Mine is a copy, not a fork.

### The one file both lanes genuinely EDIT

`analysis/schemas_export.py`. W8 adds `acquisition_manifest_schema()`; this branch adds the v2
evidence models and version-aware table export. **W8's addition is already pre-merged into this
branch**, so it should apply cleanly. If it conflicts, keep **both** additions — they are
independent functions and independent `GENERATED` entries.

---

## 3. Merge sequence

Ordered so the frozen-v1 proof runs against **every intermediate state**, not only the final one.
A merge that breaks v1 must be caught at the step that broke it.

```bash
# 1. W8 first.
git merge origin/agent/stage4-acquisition-core     # b287f72

# 2. Then this branch.
git merge origin/agent/stage4-pk-schema            # 9965f20
#    Conflicts in acquisition.py / selection.py / organ_system.py -> take W8's side.
#    Conflict in schemas_export.py -> keep BOTH additions.

# 3. Post-merge sanity: the rival type must be gone.
grep -rn "SourceAcquisitionRecord" 04_PKPD/ && echo "STOP: stale revision merged"
```

---

## 4. Test gates, in order

Run from `04_PKPD/`. Each gate is a stop condition, not a report.

| # | gate | command | expected |
|---|---|---|---|
| 1 | **v1 freeze** | `pytest tests/test_contract_version_freeze.py -q` | **15 passed** |
| 2 | v2 contract | `pytest tests/test_contract_profile.py tests/test_acquisition_contract.py tests/test_organ_system.py tests/test_v2_bundle_door.py tests/test_unbound_and_ratios.py tests/test_exposure_contract_v2.py tests/test_potency_contract_v2.py -q` | **100 passed** |
| 3 | full suite | `pytest tests/ -q` | **1068 passed, 3 skipped** |
| 4 | lint / types | `ruff check analysis/ verifier/ tests/` and `mypy --ignore-missing-imports analysis verifier` | clean; 64 files |

**Gate 1 is the one that matters.** It asserts:

* v1 `evidence_inputs_sha256` == `8999c5a38c8df8bb85ef2ca16cf5dd6decdddea81f4b48069cb61b680c47c6f5`
  (identical to `e410d72`, pre-v2);
* a v1 bundle carries **no** v2 cell — not even a null one;
* the **seven** v1 method files are present and unedited;
* the checked-in historical release `tests/fixtures/historical_v1_release/fed2a8347d155a23/` —
  emitted by `e410d72`'s code, verified by *that* commit's verifier — still verifies under the
  merged code: **212 checks, 0 failed**.

**If gate 1 fails, the merge broke v1 and must not land.** Do not "fix forward".

### Three edits that silently break every release ever emitted

Watch for these in any follow-on work:

1. editing any of the **seven v1 method files** (`METHOD_FILES_V1`), or adding one to that map —
   v2 method content goes in **new** files;
2. adding a column to the shared input-column declaration instead of to `V2_ADDED_COLUMNS`;
3. padding a v1 row with null v2 columns. A null `relation` is not "no concept of a relation"; it
   is "this row has one and nobody knows it", which is a different and false claim.

v1 must remain a strict column **prefix** of v2.

---

## 5. What this branch contains

* **v1 frozen and provable.** `analysis/contract_v1_frozen.py` (verbatim from `e410d72`, never
  edited); v1 schema files pinned by sha256; the historical release above as the proof artifact.
  **Absent `evidence_contract_version` means v1** — a release written before the field existed is
  still a release.
* **v2 wired, not merely declared.** `contract_profile.py` is a *gate*, called by `run_pipeline`
  before anything is computed, so a bundle declaring v2 while carrying none of it stops before it
  can emit a document that reads like a result. Path: `evidence_bundle.py` (reads
  `spot.stage04_evidence_bundle.v2`) → `run_stage4.py` → gate → emit → independent verifier
  reconstructs on the v2 contract.
* A **v1 bundle passes the gate and is marked NOT acquisition-complete.** That is correct, not a
  failure: v1 is a legitimate contract, it is simply not a claim that anything was acquired.
* No network code. No drug ranking. No change to Stage-3 admission. No p/q values, no combined
  clinical score, no `safe` flag — the last three are *enforced* by the forbidden-name scan, not
  merely documented.

---

## 6. NOT ready — the remaining gate

**The Stage-4 chain is not certified end-to-end by this handoff, and I am not claiming it is.**

* **Stage-4 final remains gated on the externally admitted real Stage-3 v2 interface.** That
  interface is not this branch's to deliver, and not mine to declare ready. Until it is admitted
  externally, a green suite here means the *contract* holds — not that the chain runs on real
  Stage-3 output.
* **No real-source acquisition run has been admitted.** The audit's verdict stands: *method and
  contract = go-with-repair; real-source Stage-4 run = no-go*. This branch repairs the contract.
  It does not fetch anything, and it does not make a real bundle exist.
* **Open question for W8, not fixed here:** W8 enforces deterministic selection *at acquisition
  time* (`selection.py` raises on zero / many / truncated result sets) but does not record the
  proof of that selection in the emitted artifact. A reader therefore cannot see *which* identity
  pin `exactly_one` matched, or whether the result set was complete. I had built those fields;
  they were deleted along with my rival record, and I did not re-add them because that would mean
  forking W8's `AcquisitionRecord`. If that provenance is wanted, the fields belong on W8's model
  and the call is W8's.
