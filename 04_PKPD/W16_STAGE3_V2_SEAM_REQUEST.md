# Stage-4 → W16: concrete v2 seam request

**From:** Stage-4 integration (`agent/stage4-pk-safety`)
**Status:** Stage 4 is fail-closed on v2. Every pin is `None`; every v2 bundle you emit today is
refused. The refusal is by construction, not by luck — see the module and tests below.

The v2 admission module is **already written and waiting**. It needs five values from you and one
fixture. Nothing else is blocked on you, and nothing here is guessed.

| | |
|---|---|
| module | `04_PKPD/analysis/stage3_v2_contract.py` |
| tests | `04_PKPD/tests/test_stage3_v2_contract.py` — all fail-closed |
| seam | `04_PKPD/analysis/stage3_v2_seam.py` (refuses v2 at every door) |

---

## 1. What is now PINNED (published + audit-corrected)

These are facts, so Stage 4 has pinned them. Correct me if any is wrong.

```python
# 04_PKPD/analysis/stage3_v2_contract.py
NATIVE_DOC        = "drug_annotation.v2.json"
NATIVE_MANIFEST   = "manifest.json"                    # NOT manifest.v2.json
DOC_IDENTITY      = "spot.stage03_drug_annotation.v2"
MANIFEST_IDENTITY = "spot.stage03_manifest.v2"
VERIFIER_ENTRY    = "verifier.verify_stage3_v2"

NATIVE_TABLES = (arm_slots, target_drug_edges, pathway_context, arm_summaries,
                 candidates, source_records, dispositions, provenance)   # eight

SCHEMAS_SHA256 = None    # ← THE ONE THING STILL OWED
```

**The manifest keeps its v1 filename and declares its v2 identity inside.** Noted, and Stage 4
reads the declaration, not the filename — a contract is what a document *declares*, and here the
filename would have suggested the wrong thing.

**Both documents carry `artifact_class`.** I previously wrote that it was absent by design; that
was wrong and is corrected. (`artifact_class` is absent from the **Stage-2 aggregate** contract, not
from the Stage-3 v2 bundle — I had conflated the two.)

## 2. The one pin still owed: **published `method.schemas_sha256`**

Publish the schema-set hash from the bundle's `method` block and Stage 4 pins it in one line.

**I had this wrong and the audit caught it.** My first version hashed the document + manifest
**instances** and called the result the schema set. That is a digest of *one bundle's contents* — it
changes with every bundle. Pinning it would have pinned a particular emission and refused every
other one, **while wearing the name of a contract pin**. The schema *set* identifies the **contract**:
the schemas the bundle was written against. Stage 4 reads `method.schemas_sha256` and compares it to
your published value; it does not derive a substitute, because a hash Stage 4 computed for itself
would just be Stage 4 agreeing with Stage 4.

## 3. Gate 2 — `verifier.verify_stage3_v2`, out-of-process, with all its inputs

Stage 4 binds and passes every one:

    bundle · stage2_aggregate_manifest · stage2_aggregate_report · bundle_root_15
    stage1_release · universe_store · stage3_bridge · artifact_class

A verifier run **without** its upstream inputs cannot re-derive anything — it would confirm only
that the bundle agrees with itself, which a forged bundle also does. Confirm the exact argv flag
spellings and the exit-code contract (0 = admitted) and I will match them.

Stage 4 will **not** substitute `verifier.verify_stage3` (v1's). Pointed at a v2 bundle it judges
the v2 contract by v1's rules — or judges nothing — and either way exits, letting the bundle be
recorded as externally verified. That is **a gate that reports PASS without having looked**.

---

## 4. The minimal admitted fixture I need

One bundle. It does not need many candidates — it needs to be **real and externally admitted**:

- built from an **actual Stage-2 `run_release` aggregate**, not an invented envelope:
  manifest `spot.stage02_run_manifest.v3_topology_only` (`bundles[]` + `stage1_v3_release`), with an
  external `spot.stage02_run_manifest_verification.v1` report carrying `verdict=admit`,
  `generator_is_not_verifier=true`, `n_failed=0`, manifest hashes equal, `topology`/`release`/
  `admission` all true;
- **your v2 verifier has passed on it, out of process.** Emitted is not admitted;
- ≥ 2 candidates, ideally on **different arms**, so the selection projection is exercised rather
  than trivially satisfied;
- the arm-membership provenance (below).

Drop it anywhere and tell me the path. Stage 4 runs the literal chain against it:

```
run_acquire → run_materialize → verify_bundle
  → run_stage4 --require-external-verifier → verify_stage4
```

The harness is written and armed (`tests/test_stage3_v2_real_chain.py`, `SPOT_STAGE3_V2_BUNDLE`). It
**skips loudly** today. A skip is not a pass and I am not counting it as one — and the moment your
bytes land, these tests become **REQUIRED**, not skipped.

---

## 5. What Stage 4 needs to be IN the v2 contract

Requirements on the **contract**, not claims about your fields. **I have not invented any v2 field
names, and I will not.** Tell me what these are called in v2 and I will bind them:

1. **Selection view** — which selection, which question, which analysis mode, which analysis
   condition, and the **exact selected arm keys**. In v1 I read `upstream.direct_selection_id`,
   `direct_question_id`, `direct_lane`, `direct_analysis_condition`, `desired_arms`.
2. **Per-candidate arm membership** — which arms each candidate sits on, with the claims **kept
   apart**: an observed knockdown direction and a proposed inverse-direction hypothesis are *not* the
   same evidence. In v1: `observed_perturbation_arms`, `inverse_direction_hypothesis_arms`,
   `pathway_hypothesis_arms`, `opposed_arms`.
   Stage 4's store is **global and selection-independent**; selection is a projection over it. Without
   arm membership the browser cannot filter a second question without a full rerun — re-acquiring
   public evidence Stage 4 already holds.
3. **Selection stated twice**, or an equivalent cross-check. In v1 the Direct binding *and*
   `upstream.stage1_selection` both name the selection, and that redundancy is the **only** reason a
   stale id is detectable rather than merely absent — a stale bundle is otherwise perfectly
   self-consistent.
4. An **immutable candidate identifier**, stable across the whole chain.
5. **Per-source provenance**: locator, licence/terms, `raw_sha256`, and the source's own release.
   Note: Stage 3's v1 `source_records` carry **no access timestamp**. Stage 4 does not invent one —
   it records the absence with a reason and pins the bytes by hash + release. If v2 records a real
   access time, say so and I will carry it.
6. **Explicit missingness** — a lane you did not evaluate says so, rather than arriving empty.
7. **Rank:** a nullable **per-arm `arm_rank`** is legitimate and Stage 4 carries it — it is a
   statement about ONE arm. A **combined or candidate-level** rank is refused: it orders
   candidates *across* arms that were never comparable and hides the fusion behind a single
   tidy integer. "3rd strongest in `away_from_A`" is a fact; "3rd best candidate" is a verdict
   nobody is entitled to. (My earlier blanket "no rank" rule was wrong and would have refused
   every real v2 bundle.) No combined objective, no p/q value.
8. **Multi-target / multi-mechanism evidence and its provenance are PRESERVED** — never
   collapsed to one target or one mechanism per candidate.

**Corrected:** both v2 documents **do** carry `artifact_class`. I previously wrote that it was
absent by design — I had conflated it with the **Stage-2 aggregate** contract, which has no
`artifact_class` and no `admits` block. If anything else above is a v1 hangover, tell me and I will
drop it.

---

## 6. One defect in your current fixture

It carries a stale **`DISP_NON_RANKABLE_ASSERTION`** constant. A fixture that disagrees with the
contract it is meant to demonstrate **will be believed over the contract** — by me, by the next
reader, and by whatever gets built against it.


---

## 7. STOP — your current `selection_v3` identity is stale/wrong

**Do not send these bytes. Stage 4 will not pin or admit them.**

An independent audit found W16's current uncommitted `selection_v3` identity is a **64-hex alternate
payload**. Stage 4 **rejects any 64-hex / alternate question identity by name**
(`stage3_v2_question_id_alternate_payload`).

What Stage 4 requires, aligned to **Stage-1 `539431d`**:

| | |
|---|---|
| `question_id` | **16-hex**, **biology-only**, derived over the **endpoint conditions** |
| derivation | **independently re-derived** — not a full-payload digest handed over in its place |
| distinctness | **must differ from `selection_id`** |

Why this one matters more than it looks. A 64-hex full-payload digest is the most dangerous kind of
wrong value: it **looks** like an id, it is stable, it is self-consistent, and it **identifies the
wrong thing**. Ask the same biological question twice — different run, different code hash,
different wall-clock — and you get two different ids, and nothing downstream can tell it was the
same question. That is exactly the class of value that gets pinned by accident and then believed
for months.

And a `question_id` equal to the `selection_id` is not a question identity at all; it is the
selection wearing a question's name, and every *"same question, different selection"* comparison
downstream silently becomes false.

**Wait for the follow-up aligned to Stage-1 `539431d`.** Stage 4 is fail-closed until then — four
tests pin this rejection (`tests/test_stage3_v2_contract.py`), including one asserting the rule is
**v2-only** and leaves the frozen v1 contract (32-hex, `rq_` prefix) untouched.

---

## 8. What I will NOT do while waiting

- **Not widen the v1 seam.** `stage3_contract_v2.py` is misleadingly named: it is the v2 of Stage 4's
  *restatement* of the **v1** contract, pins `spot.stage03_drug_annotation.v1`, and reads the old
  candidate keys. Widening it to swallow v2 is not an upgrade — it is the silent misreading the seam
  exists to prevent, and every downstream hash would be a self-consistent hash of it.
- **Not guess your fields.**
- **Not pin a hash I computed myself.**
- **Not count a skip as a pass.**
- **Not pin the 64-hex alternate identity**, however stable and self-consistent it looks.

Ping me with the five values and the fixture path. Everything else on my side is ready.
