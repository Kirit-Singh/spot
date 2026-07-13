# Stage-4 → Orchestrator / W6: merge report and exact open gates

**Merge commit: `2853ce5`** on `agent/stage4-pk-safety`. Pushed, clean tree.
Both requested commits are now ancestors: **W8 `b287f72` ✓**, **W9 `9fbbc46` ✓**.

## Suite

| gate | result |
|---|---|
| full merged suite | **1386 passed, 8 skipped** |
| ruff | clean |
| mypy | clean (80 files) |
| v1 contract freeze | 15 passed |
| historical v1 release | **212/212 checks — unchanged** |

## What was actually in the merge

**W8 `b287f72` was already ancestral** (integrated at `cd04ab0`). `selection.py` and
`organ_system.py` remain byte-identical to it. `acquisition.py` diverges by exactly two additive
typed fields — `candidate_id`, `access_time_not_stated_reason` — which **are** the join-seam repair,
not a conflict resolution.

**W9 `9fbbc46`'s PK contract is already here and byte-identical** (`pk_records.py`,
`assay_records.py`, `safety_records.py`, via `56864a0`). The only genuinely new content was
`HANDOFF_W6_MERGE.md`, taken. Its remaining substantive commit `bd7a403` is a **regression on this
branch** and is not applied.

## The join seam is fixed, not hidden — W9's tip would have re-broken all three

1. **Deterministic-selection proof.** W9's `row_flatten.py` **deletes `selection_disposition` and
   `selection_pin`**; its `source_acquisition` table drops `match_total_reported`,
   `records_returned`, `result_set_complete`. The emitted record could no longer say **which
   `exact_one` pin matched** or **whether the result set was complete** — the entire proof that a
   record was not chosen by position. HEAD carries all five.
2. **Explicit `candidate_id`**, stamped at acquisition, **read** at materialization. **Not inferred
   from `stage3_source_record_id`** — a Stage-3 *source* id is not a candidate id, and a freshly
   fetched record has neither. A record naming a candidate the admitted bundle does not contain is
   refused **by name**, never reattached and never dropped.
3. **Access-time semantics.** `origin` + `access_time_not_stated_reason`: a reused Stage-3 response
   with no timestamp is the honest state of the world; a Stage-4 fetch with none is a defect.

### ⚠ Worth knowing for future merges

Git **auto-merged `row_flatten.py` to W9's version with no conflict.** 318 tests failed instantly,
which is the only reason it was visible. Conflict markers appeared in 14 files — and the one that
mattered most was not among them. A silent auto-merge of the file that flattens records into parquet
rows is exactly how a provenance field vanishes with nobody resolving anything.

I also rejected the merge's attempt to **reintroduce the 26 real ChEMBL/UniProt cache bytes** removed
for licensing (ChEMBL is CC BY-SA 3.0; the repo rule is that Git holds synthetic fixtures and
manifests only). `test_release_hygiene_scan.py` exists for exactly this. **0 tracked.**

---

## THE OPEN GATES — all fail-closed, none to be worked around

### 1. Stage-3 v2 admission: **CLOSED**

```
analysis/stage3_v2_contract.py   SCHEMAS_SHA256 = None      ← the one pin still owed
analysis/stage3_v2_seam.py       STAGE3_V2_SCHEMA_SET_SHA256 = None
                                 STAGE3_V2_VERIFIER_ENTRY    = None
```

Structure is pinned (published + audit-corrected): `drug_annotation.v2.json` + **`manifest.json`**
(the manifest keeps its v1 *filename* and declares `spot.stage03_manifest.v2` **inside**); eight
native tables; `verifier.verify_stage3_v2` with all eight inputs bound out-of-process.

**W16's `ee4810c` is REFUSED, and the refusal is the finding — not a bug to pin around.** Its view
projects `tables` as bare row lists; the sealed `table_hashes` describe the **store**'s tables and
are never re-bound to the **projected** rows. A test appends a row to `candidates` and shows **every
hash in the view still agrees** — `view_content_sha256` unchanged, `store.table_hashes` unchanged,
identity binding still passes. A projection that cannot be checked against the thing it projects is a
second, unverified artifact wearing the store's identity.

`store.schemas_sha256` is sitting in the bytes and Stage 4 **did not pin it**: a pin taken from a
commit about to be superseded is a pin that will be wrong tomorrow.

**Needs from W16:** corrected commit with (a) per-table hashes bound to the *projected* rows, (b) the
verified store receipt rebound, (c) a complete selection-independence gate — then the published
`method.schemas_sha256`. Real-chain tests wait for that commit.

### 2. No candidate acquisition

Offline by default. `--allow-network` is explicit and **per-moiety** — there is no bulk sweep. No
drug has been fetched.

### 3. No ranking

`is_ranking: false`. The combined-objective firewall is unchanged: a per-arm `arm_rank` is
legitimate evidence about one arm; a **candidate-level or combined** rank is refused.

### 4. Source verification: **INCOMPLETE** (new gate, this round)

`source_verify` used to report `pass` when evidence-dependent documents were merely **not cached** —
so a release receipt could be cut from a run that verified nothing the method stands on. It now states
required-vs-verified, names what it could not verify, and exits **2** on incomplete.

**Current: 2/5 required verified** (Grossman BioC, Wager JATS). The Wager PMC HTML and both DailyMed
probes are not cached on this host. **Green-with-skips is not complete**, and the receipt now says so.

---

## Standing

No drugs fetched. None ranked. No real Stage-4 result claimed. Final admission stays fail-closed
until W16 supplies a corrected, externally verified v2 bundle.
