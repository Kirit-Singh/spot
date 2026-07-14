# Stage-4 evidence contract v2 — handoff to W6 (cross-check) and merge sequence

Branch `agent/stage4-pk-schema`, six commits on `e410d72` (`f32b251 … 293ce61`).
Not pushed. Awaiting review.

---

## 1. The v1 regression W6 found, and its repair

W6 was right, and the cause was worse than the symptom. The v2 columns were added to the
**shared** column declaration, so:

* **v1 content began hashing under a v2 shape.** `evidence_inputs_sha256` for the unchanged v1
  fixture moved off `8999c5a3…`. A content digest that changes when the content did not is not a
  content digest.
* **the independent verifier began demanding `relation` of releases written before that column
  existed**, so a historical release became *unverifiable* — which is not the same answer as
  *wrong*, and only one of the two is safe to act on.

One mutable declaration was serving two contracts. Repaired by carrying **both** — not by
weakening v2, and not by padding v1 with null v2 columns (a null `relation` is not "no concept of
a relation"; it is "this row has one and nobody knows it", a different and false claim).

### Restoration, exactly

| | |
|---|---|
| v1 `evidence_inputs_sha256` | `8999c5a38c8df8bb85ef2ca16cf5dd6decdddea81f4b48069cb61b680c47c6f5` |
| identical to | `e410d72` (pre-v2), recomputed from that commit's worktree |
| v1 tables emitted | 10 (the two v2 lanes do not exist for a v1 release) |
| v1 method files | 7 — **unedited**; v2 content is in NEW files |
| v1 parquet columns | a strict **prefix** of v2's |

### The proof is an artifact, not an assertion

`tests/fixtures/historical_v1_release/fed2a8347d155a23/` is a **real release**, emitted by the
code at `e410d72` and verified by *that commit's* verifier (212 checks, 0 failed). It is checked
in unchanged. Today's code verifies it: **212 checks, 0 failed**, `scope=full_reconstruction`.

Its manifest carries **no** `evidence_contract_version` field — it predates the field. **Absent
means v1.** Any other reading makes every artifact ever written unreadable the moment a v2 exists.

Frozen by test, not by intention:

* `analysis/contract_v1_frozen.py` — the v1 declaration, copied verbatim from `e410d72`. Never
  edited. The digest is pinned in it.
* `schemas/spot.stage04_evidence_*.v1.schema.json` — pinned by sha256; superseded by v2, never
  rewritten.
* the seven v1 method files — pinned present-and-unedited; **editing one breaks every release
  ever emitted**, so v2 method content went into new files.

---

## 2. What v2 is, and that it is wired rather than declared

A schema that declares a field and never requires it has not added a rule — it has added a place
to put a null. So `analysis/contract_profile.py` is a **gate**, called by `run_pipeline` *before
anything is computed*: a bundle that declares v2 while carrying none of it stops before it can
produce a document that reads like a result.

End-to-end: `evidence_bundle.py` reads `spot.stage04_evidence_bundle.v2` → `run_stage4.py` carries
the version into the run → `run_pipeline` gates → emit writes the v2 tables → the independent
verifier reconstructs on the v2 contract.

A **v1 bundle passes the gate and is marked NOT acquisition-complete.** That is not a failure;
v1 is a legitimate contract, it is simply not a claim that anything was acquired.

---

## 3. Alignment with W8 (`b287f72`, authoritative) — no competing implementations

**Three** files are W8's, adopted verbatim: `analysis/selection.py`, `analysis/organ_system.py`
and `analysis/acquisition.py`. My rivals to all three are gone.

The third one was found late, and only because the conflict surface was checked mechanically
rather than trusted. `analysis/acquisition.py` **does not exist in the common base `e410d72`** —
both lanes created it, for the same purpose, citing the same audit finding (§4.7). "W8 wins the
duplicate" would therefore have deleted `SourceAcquisitionRecord` out from under every module
that imports it, and the merged tree would not have imported at all. That is a broken merge, not
a clean one, and it would have surfaced as an ImportError rather than as a conflict.

All three are now **byte-identical to `b287f72`**, verified by hash. The merge is a genuine
no-op and "W8 wins" never has to fire.

* **Selection.** My whole rival vocabulary is deleted along with my rival record. W8 enforces
  selection **at acquisition time** — `selection.py` raises on zero/many/truncated — and does not
  record the proof of that selection in the artifact. **Open question for W8, not something I
  will fork their record over:** an artifact reader cannot currently see *how* a record was
  selected (`exactly_one` on which pin? was the result set complete?). If that provenance is
  wanted in the emitted manifest, the fields belong on W8's `AcquisitionRecord`.
* **Acquisition record.** W8's is a superset of what I had: `origin`
  (`fetched_public` / `reused_from_stage3` / `synthetic_fixture`), licence status, and the
  outside-Git cache binding. Fixtures now build records with W8's own `fixture_record`, so every
  one is `origin=synthetic_fixture` / `evidence_state=not_applicable` — labelled synthetic bytes
  are not an observation of anything and can never become a public record.
* **organ_system.** W8's `OrganSystemEvidence` field-for-field (14 bound columns). The controlled
  vocabulary applies **only** where W8 says `value_kind='controlled_value'`; a `source_term` stays
  **verbatim**, because normalising "Nervous system disorders" → `neurologic` here would *be* the
  classifier `organ_system.py` refuses to be. `unspecified` + `not_evaluated` is what every real
  extraction returns today (no ledgered source carries the field) and it still names the record
  and bytes it looked at — so "unspecified" can never be read as "never checked".
* W8's **missing-version refusal** is preserved as a contract rule: a `label_supported` finding
  without `label_version`, or without `setid`/`application_number`, is a profile violation.

W8's four open items for W9 are closed: `contract_profile.py` (previously referenced but
nonexistent), fraction-unbound uniqueness/ownership/provenance, organ_system consumption, and the
v2 path through `evidence_bundle.py` / `run_stage4.py`.

---

## 4. Merge sequence for W6

v1 is frozen and v2 is green, so the order below is chosen so that **the frozen-v1 proof runs
against every intermediate state**, not just the final one.

1. **Land W8 first — `b287f72`** (confirmed authoritative for every duplicated file). It owns
   `analysis/selection.py`, `analysis/organ_system.py` and `analysis/acquisition.py`.
2. **Then this branch** (`e410d72..bd7a403`). It carries byte-identical copies of all three, so
   they merge as no-ops. **If git reports a conflict in any of them, W8's version wins** — mine
   is a copy, not a fork. `analysis/schemas_export.py` is the one genuinely shared file that both
   lanes *edit*; W8's `acquisition_manifest_schema()` is already pre-merged into mine, so it
   should apply cleanly.
3. **Re-run the frozen-v1 proof on the merge commit** — this is the gate, and it is one command:
   ```
   pytest 04_PKPD/tests/test_contract_version_freeze.py -q     # must exit 0
   ```
   It asserts the v1 digest is `8999c5a3…`, that a v1 bundle carries no v2 cell (not even a null
   one), that the seven v1 method files are unedited, and that the checked-in historical release
   still verifies. **If any of these fail, the merge broke v1 and must not land.**
4. **Then the v2 suites:**
   ```
   pytest 04_PKPD/tests/test_contract_profile.py \
          04_PKPD/tests/test_acquisition_contract.py \
          04_PKPD/tests/test_organ_system.py \
          04_PKPD/tests/test_v2_bundle_door.py \
          04_PKPD/tests/test_unbound_and_ratios.py \
          04_PKPD/tests/test_exposure_contract_v2.py -q
   ```
5. **Then the whole suite** (1095 passed, 3 skipped on this branch), plus
   `ruff check` and `mypy --ignore-missing-imports analysis verifier`.

### Watch-outs for the merge

* **Any edit to a v1 method file breaks every release ever emitted.** The seven are pinned by a
  test. v2 method content belongs in a new file.
* **`analysis/evidence_bundle.py` and `analysis/run_stage4.py`** are touched by this branch and
  were explicitly *not* touched by W8 — should be clean.
* **After merging, grep for `SourceAcquisitionRecord`.** It should return nothing. If it appears,
  an older revision of this branch got in and the tree will not import.
* `analysis/firewall.py` moved its `Provenance` import to `contracts` (the cycle W8's
  `organ_system.py` would otherwise hit). Keep that.

---

## 5. Out of scope / not done

* **No network code.** No fetch client anywhere in `analysis/` on this branch; the acquisition
  record is the contract a fetch must satisfy, not a fetch.
* **No drug ranking**, no change to Stage-3 admission, no p/q values, no combined clinical score,
  no `safe` flag (the last three are now *enforced* by the forbidden-name scan, not merely
  declared).
* **Stage-4 final remains gated on the externally admitted real Stage-3 v2 interface**, which is
  not this branch's to deliver or to declare ready.
