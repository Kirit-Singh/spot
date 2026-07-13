# Stage-3 → Stage-4 / UI: which candidates may be shown for a selection

**Schema:** `spot.stage03_candidate_membership.v1`
**Rule id:** `spot.stage03.candidate_membership.exact_arm_key.v1`
**Module:** `druglink.candidate_membership`

---

## The rule, in one line

> **A candidate may be displayed for a selection only if its evidence lives in one of the arms that
> selection names — matched by EXACT string equality on the WHOLE arm key.**

The global store stays global and reusable. Display is a **deterministic projection** over it. No
consumer may load a candidate out of the store and render it under a question without proving it
belongs there.

## Why this exists

The store is selection-independent, and must stay so. But nothing forced a consumer to prove
membership — so a candidate could be loaded and shown under **any** selection.

Nothing crashes. Nothing fails a schema. The drug is real, its edges are real, its provenance is
real — **and it is being shown as an answer to a question it has no evidence in.** That is the worst
thing this pipeline can emit: not a broken number, but a true fact under a false heading, where
every check it passes makes it more convincing.

---

## The filter rule (implement exactly this)

```
selected  = set(view.selected_arms.all_arm_keys)          # the arms THIS question names
shown     = { c for c in store.candidates
              if set(c.arm_keys) & selected }             # EXACT string equality, whole key
```

**Do not**:

| never | because |
|---|---|
| prefix / `startswith` match | `direct\|treg_like\|decrease\|Rest` and `…\|Stim48hr` differ **only** in the context tail. A prefix match equates them, and the user is shown a drug from one condition under a question about another. |
| match on a display **name** | two arms can share a label and be different arms. **The full key is the identity; a name is not a binding.** |
| normalise / infer a key | if the two strings differ, they are two arms. |
| trust the candidate's own `arm_keys` | it is a **claim**. Stage-3 re-derives it from the evidence and refuses a mismatch — but a consumer holding only the store should filter on it *and* verify the membership hash below. |

## The fields (existing v2 names — the stale v1 `*_arms` names are **not** revived)

On each **candidate row** (global store):

| field | meaning |
|---|---|
| `arm_keys` | every arm any edge of this candidate came from |
| `observed_perturbation_arm_keys` | arms where a knockdown was measured and its sign **supported** the desired change |
| `inverse_direction_hypothesis_arm_keys` | **untested inverse** — hypothesis-only, never observed support |
| `opposed_arm_keys` | the tested intervention **opposed** the desired change |
| `pathway_hypothesis_arm_keys` | inferred context — **never** a measurement |
| `unresolved_arm_keys` | no direction could be resolved |

On the **selection view**:

| field | meaning |
|---|---|
| `selection.selection_id` | *which run* of the question (method/input-bound) |
| `selection.question_id` | *which question* (biology-only; stable across method revisions) |
| `selection.analysis_mode` | `within_condition` \| `temporal_cross_condition` |
| `selected_arms.all_arm_keys` | **the exact arm keys this question names** — the filter set |
| `view_arm_keys_by_origin`, `view_roles` | per-origin arms and A/B roles, assigned **at join time** |
| `candidate_membership_sha256` | binds the membership of exactly what this view shows |

## Verify, don't trust

```python
from druglink import candidate_membership as cm

cm.check_view_binding(view, edges=edges, arm_summaries=arm_summaries,
                      pathway_context=pathway_context)   # raises MembershipError
```

Named refusals:

| gate | fires when |
|---|---|
| `a_candidate_is_displayed_for_a_selection_it_has_no_evidence_in` | the core defect |
| `a_displayed_candidate_carries_an_arm_the_selection_does_not_name` | a **foreign arm** added |
| `a_displayed_candidate_lost_an_arm_the_evidence_gives_it` | a **real arm dropped** |
| `a_candidates_published_arm_membership_is_not_what_the_evidence_produces` | the candidate's own list widened or narrowed |
| `the_view_does_not_carry_the_selection_identity_it_claims` | no `selection_id` / `question_id` / `analysis_mode` |
| `the_candidate_membership_projection_is_not_the_one_the_view_binds` | condition or view swapped while the rows stayed |

**Membership is RE-DERIVED from `target_drug_edges` + `arm_summaries`** (and, for pathway context,
exactly-matched `pathway_context` rows) — never read from the candidate row. A published list a
consumer trusts is a *claim*; a list re-derived from the rows that carry the evidence is a *fact*.

## Two properties that are not negotiable

**Pathway never promotes.** Pathway context *contextualises* a measured edge; it never grants a
candidate membership of a question. (Pathway currently contributes **zero** — that is a
**fail-closed state pending W18**, whose verifier crashes and whose refusals were therefore vacuous.
**It is not a result, and must not be pinned as one.**)

**Generic.** No program, condition, direction or selection is privileged anywhere in the contract —
there is no Treg/Th1 special case, and a test enforces that by AST inspection of the module's
executable code.
