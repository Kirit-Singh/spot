# Stage-4 → W12: the store is GLOBAL, selection is a PROJECTION

> **STATUS: PARTIAL — v1 only, and not done.** Everything below is bound to Stage 3's **v1**
> contract (`spot.stage03_drug_annotation.v1`). Despite its name, `analysis/stage3_contract_v2.py`
> pins v1 and reads the old candidate keys. The true v2 seam (`stage3_v2_seam.py`) has
> `STAGE3_V2_SCHEMA_SET_SHA256 = None` and `STAGE3_V2_VERIFIER_ENTRY = None`, so **every W16 v2
> bundle is refused today**. Build against this shape, but do not treat it as final: the v2
> contract is still being coordinated with W16.

## The defect this fixes, because it is a display defect as much as an engine one

Stage 4 used to materialize **every** queued candidate in the Stage-3 bundle and call that a
scorecard set. That is a **global candidate display** — a catalogue of whatever Stage 3 happened to
queue — not the answer to anything.

It matters in the browser more than anywhere else. A candidate is queued because it moved *some*
arm of *some* question at *some* analysis condition. Render it in the same table as a candidate
selected for a **different arm**, and a reader compares two numbers that were never comparable. The
CNS-MPO was computed identically. The NEBPI class was derived identically. **The two rows still
mean different things** — and nothing on the page says so.

## The architecture, and a correction I had to make

My first fix was to filter at ADMISSION — and that was wrong. It makes the release a **singleton
selection** and throws away the reason the store exists. Acquiring a public label and a PubChem
record is the expensive, network-bound part of Stage 4, and it is **selection-independent**: the
same bytes answer every selection over the same candidate. Filter at admission and a second question
means a second full acquisition of evidence Stage 4 already holds.

So:

- **the store is GLOBAL** — the whole admitted Stage-3 candidate universe, acquired once, reusable;
- **selection is a PROJECTION** — a deterministic function of (store, verified active selection,
  Stage-3 arm membership) → the relevant scorecards;
- **candidate → arm provenance travels with every candidate**, so you can filter **any** selection
  client-side, with **no rerun**;
- the global release and `current.json` are **not** a singleton selection.

## What you render — TWO documents

### `spot.stage04_browser_projection.v1` — the store, with arm membership

**Nested objects are copied through VERBATIM. Do not stringify them.** `active_moiety`,
`compound_ids`, `production_eligible` and every lane are **objects**; `provenance_chain` is a list of
objects. Flattening them is not a formatting choice — it destroys evidence:

- a nested `null` means **NOT EVALUATED**, and `str(None)` is the string `"None"` — which is a *value*;
- `{"status": "incomplete", "total": null}` stringified reads as a **score**;
- a lane's missing-value semantics — the entire point of this stage — collapse into prose you then
  have to parse back, badly.

**Missing stays missing, nested.** A test asserts no leaf became a string and no `null` became
anything else.

Each candidate carries `stage3_arm_membership`, with the four arm claims **kept apart** — an
observed knockdown direction and a proposed inverse-direction hypothesis are *not* the same evidence:

```json
"stage3_arm_membership": {
  "arms": ["away_from_A"],
  "observed_perturbation_arms": ["away_from_A"],
  "inverse_direction_hypothesis_arms": [],
  "pathway_hypothesis_arms": [],
  "opposed_arms": [],
  "arm_evidence_states": [ { ... } ]
}
```

`in_active_view` is a **flag, never a gate** — the candidate stays in the store either way, because
the next selection may be exactly about it.

### `spot.stage04_selection_view.v1` — which question is active

```json
{
  "schema_id": "spot.stage04_selection_view.v1",
  "stage3_selection_view_id": "9157a6a35098bd77",
  "selection_id": "rq_43d32f0d13d6b71b1ec4e078b8955462",
  "question_id": "rq_b760ca49d4ab59bc8d2d668efc61e6de",
  "analysis_mode": "research_only",
  "analysis_condition": "StimX",
  "selected_arms": ["away_from_A", "toward_B"],
  "stage1_contract_sha256": "5ac4efa1…",
  "scope_note": "This scorecard set answers exactly this selection. Candidates outside these arms are not in it, and are not comparable to the ones that are.",
  "is_ranking": false
}
```

**Browser-safe by construction.** It carries ids, arms and the view id — **no candidate, no score,
no rank, no CNS-MPO, no NEBPI class**. A test asserts that, because a projection that leaked a
score would let a browser render a ranking the engine deliberately refuses to emit.

## What the UI must do with it

1. **Show the question.** `question_id` + `selected_arms` + `analysis_condition` are the scope of
   everything on the page. A scorecard table without them is the global display again, wearing a
   different hat.
2. **Show `scope_note` verbatim.** It is the sentence that stops a reader comparing across arms.
3. **A candidate outside the active view is EXCLUDED, not refused.** It stays in the store — the
   next selection may be exactly about it — and `select()` names it in `excluded_candidate_ids` so
   the exclusion is auditable rather than invisible. An empty `included` with a full `excluded` is
   the signature of a selection nobody's candidates answer: a finding, not an empty page.
4. **Never merge two view ids in one table.** `stage3_selection_view_id` is content-addressed: it
   changes if the question, the selection, the arms, the analysis mode **or the analysis condition**
   changes. Two different ids are two different questions. The engine refuses to build such a
   release (`mixed_candidate_set`); the UI must not reassemble one by joining two.
5. **`is_ranking: false` is not decoration.** Do not sort the table into an implied ranking. Stage 4
   emits a declared non-evaluative order, and a sortable column with a default sort *is* a ranking.

## The one that will bite you: same arm name, different time

`away_from_A` at **StimX** and `away_from_A` at **Stim48** are **not the same arm**. The arm string
alone cannot tell them apart, and a name collision is the easiest way for one to be read as the
other.

That is why `analysis_condition` is bound into `stage3_selection_view_id`. Two releases with
identical questions, identical selections and identical arm names still produce **different view
ids** if they were measured at different conditions. **Key any UI cache and any cross-release
comparison on the view id, never on the arm name.**

## What the engine now refuses, so you never receive it

| code | meaning |
|---|---|
| `selection_view_absent` | the bundle names no selection — an unfiltered global set |
| `selected_arms_empty` | a selection that selected nothing is not a selection |
| `selection_id_mismatch` / `question_id_mismatch` | the bundle disagrees with its own Stage-1 contract: one of the two ids is stale and Stage 4 cannot tell which |
| `mixed_candidate_set` | two views projected into one table: it answers neither |
| `stale_selection_view_id` | the evidence was acquired for one question and is being scored against another |

## Unchanged, and still true

Evidence states, CNS-MPO (still **incomplete** — PubChem supplies neither ClogD7.4 nor most-basic
pKa, and XLogP3 is not BioByte ClogP), NEBPI (**nothing is classified that was not measured**), and
the no-inference rule (absence of an exposure measurement is **not** evidence of impermeability) are
all exactly as before. Narrowing the release to one question does not license a conclusion inside
it.

The real replay still waits on W16/W3 bytes. No drug is ranked.
