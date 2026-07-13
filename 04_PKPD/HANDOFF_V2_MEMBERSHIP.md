# Stage-4 → UI / packer: the v2 membership producer contract

**Status: NATIVE v2 ADMISSION IS CLOSED.** This is the contract the UI pins against; it is not an
invitation to render anything yet. The machine-readable form is `HANDOFF_V2_MEMBERSHIP.json`,
**generated from the code** so it cannot drift from what is enforced.

There is no UI wrapper here, by design. This is what Stage 4 *produces* and what it *refuses*.

## The one entry point

```
analysis/projection.py :: build_v2_projection(
    scorecards, store_candidates, stage3_selection_view, row_kind,
    *, stage3_receipt_path, stage3_bundle_dir, stage3_store_dir, arm_summaries) -> dict
```

Everything below is enforced inside it. There is no second door, and no flag that skips a gate.

## What a displayed row means

Every displayed row makes one claim: *this candidate is on an arm this selection selected*. That is the
one claim a projection cannot be trusted to make about itself, so Stage 4 **re-derives it** from the
candidate's typed arm-key columns and refuses any row it cannot reproduce.

The rows Stage 4 reads come from the **selection view** — already filtered by Stage 3 to one selection.
Stage 4 does not currently load the global candidate store, and the emitted document says so (see
*Honest counts*).

```
store   candidates.{observed_perturbation,inverse_direction_hypothesis,
                    pathway_hypothesis,opposed,unresolved}_arm_keys   <- ground truth
view    candidates.view_arm_keys_by_origin                            <- the claim under test
        membership = store_keys ∩ selection.selected_arms  (EXACT full-string equality)
```

`arm_keys` is the **exact union** of the five typed columns — measured, not assumed: 19/19 candidates
in W16's bundle, zero either way. A key in the union that no typed class supports is refused, so a
sixth evidence class must be added deliberately rather than discovered silently.

**Note the parquet encoding.** Stage 3 writes these columns as **JSON strings**, not native lists.
Iterating one yields *characters* — and the selected key `,` appears in every serialized list, so a
naive `for k in value` matched **all 19 real candidates** against a two-arm selection. 100 % membership,
no error. Decode them; never iterate them.

## The selection is ORDERED, and that is the point

`selected_arm_keys` is a set, and a set is symmetric. Swapping which arm is **A** and which is **B**,
or swapping the roles, leaves it bit-for-bit identical — yet a role swap asks the **opposite**
question: it searches for drugs that push *toward* the program the question wanted to move *away
from*. So the ordered per-role records are bound too:

| field | rule |
|---|---|
| slots | exactly `{A, B}` in `selected_arms.arms`, `selection.roles`, `selection.poles` |
| roles | pinned: `A = away_from_A`, `B = toward_B` |
| conditions | non-empty, ordered; arity by mode (`direct_within_condition`=1, `temporal_cross_condition`=2), endpoints distinct |
| pole condition | A sits at `conditions[0]`, B at `conditions[-1]` |
| arm context | ordered; `(condition,)` or `(from_condition, to_condition)` — reversing the endpoints reverses time |
| `desired_change` | **derived**, never trusted: toward+high→increase, toward+low→decrease, away+high→decrease, away+low→increase |
| `arm_key` | must rebuild from its own lane/program/desired_change/context |

Every one of these is **mandatory**. A check that only runs when its field happens to be present is
not a check — deleting `poles.B` left the A side perfectly consistent and silently became a different
question, one with nothing to contrast against.

## Evidence class: exactly ONE column, derived from the arm's state

An arm's `arm_evidence_state` is authoritative and maps to exactly one typed column (W16's
`MEMBERSHIP_FOR_STATE`, inverted). The arm must be **in that column and absent from the other four**.

| state | column |
|---|---|
| `observed_perturbation` | `observed_perturbation_arm_keys` |
| `inverse_direction_hypothesis` | `inverse_direction_hypothesis_arm_keys` |
| `pathway_hypothesis` | `pathway_hypothesis_arm_keys` |
| `opposed` | `opposed_arm_keys` |
| `unresolved` | `unresolved_arm_keys` |

Moving an arm between columns leaves the **union identical**, so every set-based check passes while the
candidate is silently promoted. An earlier version asked each column *"is your count positive?"* — so an
arm in **both** `observed` and `opposed`, with counts 1/1, satisfied both and was admitted as two
placements. It is one arm. Asking five plausibility questions can never establish that exactly one is
right.

`conflicting` and `not_annotated` map to **no column**, deliberately: Stage 3 *preserves* a
contradiction rather than resolving it, and there is no column that honestly holds "the sources
disagree". Stage 4 **refuses** such an arm rather than skipping it — skipping is how the contradiction
got displayed in the first place.

Corroboration is scoped to the **selected active arms**: an inactive arm is never displayed, never
hashed, and cannot promote anything.

## The receipt: W16's schema, read from disk

**`spot.stage03_membership_receipt.v1`** — W16's, not Stage-4's. I previously coined
`spot.stage03_independent_receipt.v2` and verified *that*: two schemas for one handoff, each side
happily verifying its own idea of the document and neither verifying the other. It is deleted.

Stage 4 does not re-verify Stage 3; `verifier_id` names the out-of-process verifier that did. Stage 4
**reads the receipt's bytes** and recomputes every hash it states. A dict the caller passes in is
refused: the caller *is* Stage 4, and a proof you write for yourself about bytes you never read is not
a proof.

Hash rules, reproduced exactly (verified byte-for-byte against W16's emitted fixture):

```
receipt_sha256           sha256(canonical_json(receipt − receipt_sha256))
view.raw_sha256          sha256 of the view file's BYTES at the bundle-relative view.path
view.canonical_sha256    sha256(canonical_json(the whole view document))
view.view_content_sha256 sha256(canonical_json(view − view_id − view_content_sha256))
view.view_id             view_content_sha256[:16]

canonical_json = json.dumps(sort_keys=True, separators=(",", ":"),
                            ensure_ascii=True, allow_nan=False)   # floats rejected
```

`bundle_dir` is **required** — the re-hash used to run only `if bundle_dir:`, so omitting it skipped
every artifact check and a receipt with sealed fake hashes over an **empty** bundle was admitted. Every
referenced artifact must exist as a **regular, bundle-relative file**; absolute and traversing paths are
refused. Missing is a refusal, not a skipped step: *nothing to compare* is not *nothing wrong*.

Refused: a self-hash that does not recompute; a **self-signed** receipt (`generator_id == verifier_id` —
the two named ids are the fact, not the boolean the producer also publishes); a dirty producer tree; a
verdict other than `admit`; a **retired** membership rule masquerading as the one in force; a view or
table whose on-disk bytes do not re-hash to what the receipt declares. An edited on-disk receipt is
refused **even when the caller's dict is clean**.

**Everything projected comes from the receipt-loaded view.** Loading the receipt and then projecting
the *caller's* copy was the sharpest hole here: changing one field of that copy
(`selection.question_id` → `FORGED_QUESTION_ID`) while the on-disk bytes stayed untouched was admitted,
and the forged question was emitted. A caller copy is now permitted only if it is **canonically
identical** to the bound bytes. The corroborating tables (`candidates`, `arm_summaries`) travel inside
the hash-bound view — W16 ships no parquet in the bundle — so they are never taken from a caller list.

The emitted `stage3_receipt` carries only authoritative fields and bound identities: no view document,
no table rows, no internal keys.

## The join

Duplicate ids are refused on **both** sides before anything is joined: a dict join keeps the last row
and silently discards the rest, so two candidates sharing an id means one is displayed carrying the
other's evidence, and no count looks wrong. Every Stage-4 scorecard candidate must resolve **exactly
once** to an admitted Stage-3 candidate — a foreign one is refused, not shown as "out of view".
`out_of_view` is permitted **only** for a candidate that exists upstream, and
`displayed + out_of_view == scorecards in`, counted before emit.

## Honest counts

The rows come from the **selection view**, which Stage 3 has already filtered to one selection. So the
emitted document says `n_stage3_view_candidates` and `source_is_selection_view: true`, and
`store_is_global_and_was_not_filtered` is **false** unless a run actually loads and hashes the global
store (`stage3_store_dir`). The earlier wording claimed a global, unfiltered store over
selection-filtered bytes Stage 4 never loaded.

## Still owed — the pins stay closed until these exist

1. An **`artifact_class=analysis`** bundle. W16's exported view and receipt are `artifact_class:
   fixture` — the real shape, from the real producer, judged by the real verifier, but **not
   production**. Build against them; do not report their contents as results.
2. `method.schemas_sha256` — the v2 schema-set identity, from a **clean committed** producer.
3. `verifier.verify_stage3_v2` entry point + exact inputs (gate 2, out-of-process). **The receipt alone
   is not admission** — W16 says so in the receipt itself; admission is the receipt **plus** the full
   hash-bound view it names.
4. The **canonicalization rule** behind the store's `content_sha256` (per-table canonical hashes are
   cross-checked, not independently recomputed).
5. Pathway currently contributes **zero** — a fail-closed state pending W18, not a result.

## Fixture limits worth knowing

W16's fixture is **candidate-saturated**: every arm key is held by all 19 candidates, so in-view /
out-of-view discrimination cannot be demonstrated on it (the synthetic suite carries those cases). It
is **not** class-saturated — candidate 0 is 90 `observed` + 90 `opposed` — which is why the
evidence-class promotion attack *is* expressible on real bytes, and is.
