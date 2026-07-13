# Stage-3 → W12 (frontend) and W6 (Stage-4): the SELECTION VIEW

**What this is.** Stage-3's scientific store is deliberately **selection-independent**: it holds
every arm, every edge, every candidate, every disposition, and it re-ranks nothing. That is what
makes it reusable. But a user asks **one** question, and must see the answer to **that** question.

The **selection view** is the seam:

```
materialize(admitted v2 store, verified Stage-1 v3 selection) -> view      # a PURE FUNCTION
```

It **filters** and **annotates** rows the store already contains. It invents no candidate, no
rank, no score, no edge; it never re-ranks; it never promotes; it never writes back.

> **The view is a QUERY, not an artifact.** No release file represents one selection. If the
> global release held one question's answer, the store would stop being reusable and every other
> question would be wrong or a re-run — the same failure as writing an A/B role into an arm, one
> level up. Cached views are fine, but they are a **cache**: keyed by `selection_id`, regenerable
> from the store at any time, discardable without loss.

* schema — `schemas/spot.stage03_selection_view.v1.json` (`$id: spot.stage03_selection_view.v1`)
* worked example — **`selection_view.fixture.v1.json`** (build against this today)
* regenerate it — `python 03_druglink/tests/emit_view_fixture.py`
* code — `analysis/druglink/{selection_v3,arm_selection,selection_view,view_contract}.py`

---

## 1. The two identities. BOTH required, and they are NOT the same thing

Stage-1 emits both. Stage-3 **re-derives both independently** and refuses a contract that declares
anything else. Reading an id you never recomputed is reading a label.

| id | what it answers | rule |
|---|---|---|
| **`question_id`** | *WHICH QUESTION is this?* | `sha256(canonical_json({A:{program_id,direction,condition:conditions[0]}, B:{program_id,direction,condition:conditions[-1]}, analysis_mode}))[:16]` |
| **`selection_id`** | *WHICH RUN of that question?* | `sha256(canonical_json(canonical_content))[:16]` |

`canonical_json = json.dumps(o, sort_keys=True, separators=(",",":"), ensure_ascii=True)`
(byte-identical to `jq -cS`). **16 lowercase hex, not 64.**
(`selection_full_sha256` is `selection_id`'s full 64-hex form.)

**`question_id` is BIOLOGY-ONLY** — no method, no registry, no source binding. The same biological
question keeps **one** `question_id` across method / registry / source revisions.
**`selection_id` is METHOD/INPUT-BOUND** — it also covers the scorer view, the source h5ad and the
method version, so it moves when the method does.

Bind **both**, keep them **distinct**. With only `selection_id`, a method bump looks like a brand
new question. With only `question_id`, a stale run masquerades as the current one.

**The CONDITION lives INSIDE each pole** — A at `conditions[0]`, B at `conditions[-1]` — never in a
sibling array. Drop it and *"the same program, in the same direction, at two different times"*
collapses into one pole compared with itself, and two different questions get one id.

Verified against Stage-1's own emitted bytes (`539431d`,
`stage01_selection_temporal_ready_example.json`), and pinned in `tests/test_selection_view.py`:

```
canonical string  {"A":{"condition":"Stim8hr","direction":"high","program_id":"treg_like"},
                   "B":{"condition":"Stim48hr","direction":"high","program_id":"th1_like"},
                   "analysis_mode":"temporal_cross_condition"}
question_id       3203d63970720d4f
selection_id      7a77f6b314b9c0f3
```

---

## 2. From the question to the arms

A reusable arm is keyed `lane|program_id|desired_change|<context…>`. **The pole and the role are
never in the key.** The role→pole→change map is frozen, and Stage-3 restates it independently and
then requires the aggregate's published `desired_change_by_role_and_pole` to agree:

```
away_from_A(high) -> DECREASE        toward_B(high) -> INCREASE
away_from_A(low)  -> INCREASE        toward_B(low)  -> DECREASE
```

| mode | GENE arms | PATHWAY context arms |
|---|---|---|
| `within_condition` | the two **DIRECT** arms, both at the one condition | condition-matched, same condition |
| `temporal_cross_condition` | the two **TEMPORAL DiD** arms of the **ORDERED** pair (never same-time Direct ranks) | the **ENDPOINTS**: A at `from_condition`, B at `to_condition` |

Endpoint pathway panels are two *within-condition* readings side by side. They are **never** a
statistic computed across time — nothing was measured across time, so naming one would invent it.

**Arm keys are matched by EXACT string equality. Never a prefix, never a substring.** The release
holds **six** temporal arms for every `(program, desired_change)` — one per ordered pair — and they
differ **only** in their context. A prefix match resolves all six; taking the first answers a
question about different time points and looks exactly like the right answer.

### One reusable arm may carry BOTH roles — and that is correct

`away_from_A(high)` and `toward_B(low)` are **both** `decrease`. So a selection naming one program
with opposite poles resolves both roles onto a **single** arm. Stage-1 admits exactly that
selection (its only self-comparison refusal is same program **+** same direction **+**
`within_condition`). One arm serving both roles is the reusable-arm design working, not breaking.

The view states it: `selected_arms.one_arm_carries_both_roles`, and `gene_arm_keys` holds **one**
key. Every projected row carries `selection_roles` — a **list** — so a shared arm is neither
double-counted nor mistaken for a single-role one.

---

## 3. What the view contains

Top level: `selection`, `selected_arms`, `store`, `admission`, `origin_type`, `arm_evidence`,
`tables`, `counts`, `guarantees`, `missingness`, plus the four negative declarations
(`combined_objective_permitted`, `candidate_rank_permitted`, `headline_arm_permitted`,
`p_q_fdr_permitted` — all `false`) and `inference_status: not_calibrated`.

**The global store ships EIGHT tables**
(`arm_slots`, `target_drug_edges`, `pathway_context`, `arm_summaries`, `candidates`,
`source_records`, `dispositions`, `provenance`).
The view **projects seven** of them. `provenance` is deliberately **not** projected: it describes
the *store*, not this question. Open it via `store.bundle_id`.

### Binding fields (`view.store`)

| field | meaning |
|---|---|
| `bundle_id`, `canonical_content_sha256` | the global v2 bundle this was projected from (document file `drug_annotation.v2.json`; bundle manifest `manifest.json`; **both** carry `artifact_class`) |
| `table_hashes` | the store's own per-table content hashes |
| `stage2_manifest_self_hash` / `_raw_` / `_canonical_` | the admitted Stage-2 aggregate |
| `method_sha256`, `code_tree_sha256`, **`schemas_sha256`** | the method identity. `schemas_sha256` **is** the schema identity — bind that one |
| `universe_store_id`, `direction_vocabulary_digest` | the universe and the direction vocabulary every edge was classified under |

`view.admission` carries the W3 **receipt** — the JOIN — binding the aggregate manifest, the
aggregate report **and** the bridge, by **raw AND canonical** bytes.

### The science that survives the projection

* **Typed origins stay separate.** `direct_target` and `temporal_cross_time_measured` are both
  MEASURED and are **distinct estimands, never fused**. `endpoint_pathway_context` is INFERRED —
  nobody perturbed it. Each candidate carries `view_arm_keys_by_origin` and `view_n_edges_by_origin`
  keyed by all three origins. **Collapse those maps and you can no longer tell a measured lever
  from a pathway context member** — the one distinction this stage exists to protect.
* **`view_*` fields never overwrite the store's global ones.** A candidate carries the store's
  global `n_edges_by_origin` / `arm_keys` **and**, beside them, this question's narrower
  `view_n_edges_by_origin` / `view_arm_keys_by_origin`. The prefix says which is which.
* **`inverse_direction_hypothesis` is HYPOTHESIS-ONLY.** Queued for a *look*; never observed
  support, never promoted, never sharing a tier with a measurement. **Stage-4 must carry the class
  verbatim and may not raise it.**
* **Pathway is CONTEXT.** It never sources a drug edge. (Today the pathway lane is **not
  admitted** — its verifier fails open — so `pathway_context` is empty and
  `missingness.pathway_context_absence_reason` says so by name. That is a stated absence, not a
  silent zero.)
* **Explicit missingness.** A **null `arm_rank` is VALID and stays null** — never `0`, never last,
  never "best". `arm_rank_status` says which (`ranked` / `unranked_by_source` /
  `not_applicable_inferred_origin`). `n_ranked` counts **ranks**, never rows.
* **Filtered-out rows are COUNTED.** `view.counts` gives `n_in_store` / `n_in_view` /
  `n_filtered_out` per table. A dropped row and a row nobody found look identical, so nothing
  silently vanishes.
* **Row order is by content id. It is not a ranking.**

---

## 4. The guarantees (enum-locked in the schema; revoking one moves the view id)

```
the_view_is_a_pure_function_of_the_admitted_store_and_the_selection
the_view_never_re_ranks_or_re_orders_the_store
the_view_never_promotes_an_evidence_class
the_view_never_writes_back_to_the_store
the_view_is_not_a_release_artifact_and_no_release_holds_one_selection
the_view_only_filters_and_annotates_rows_the_store_already_contains
roles_are_assigned_at_join_time_never_stored_on_an_arm
arm_keys_are_matched_by_exact_string_equality_never_by_prefix
direct_and_temporal_are_distinct_estimands_never_fused
a_pathway_record_never_sources_a_drug_edge
an_inverse_direction_hypothesis_is_never_observed_support_and_is_never_promoted
a_null_rank_is_never_a_zero_and_never_sorts_as_best
filtered_out_rows_are_reported_as_counts_never_silently_dropped
a_cached_view_is_regenerable_from_the_store_and_discardable
row_order_is_by_content_id_and_is_not_a_ranking
```

## 5. Browser safety (STRICT)

`druglink.view_contract.validate(view)` runs before any view leaves, and **an unknown field is a
refusal, not an extra**:

* no machine-local or absolute filesystem path, at any depth;
* no combined / balanced / weighted / headline / composite objective, at any depth;
* no p, q, FDR or adjusted-p — Stage 3 is `not_calibrated`, so such a field would have the *form*
  of a calibrated statistic and none of the meaning;
* no retired promotion/eligibility vocabulary;
* bounded payloads (a cap is a **refusal**, never a truncation — a truncated table is a dropped
  row).

Row columns are **derived** from the producer's own column tuples, so the contract and the tables
cannot drift apart.

## 6. Named refusals (each has a test that makes it fire)

| gate | when |
|---|---|
| `the_selection_carries_no_question_id` | `question_id` absent |
| `the_question_id_does_not_derive_from_the_biology_the_selection_names` | it disagrees with our re-derivation |
| `the_selection_id_does_not_derive_from_its_own_canonical_content` | ditto, for the run id |
| `the_condition_count_does_not_match_the_analysis_mode` | 1 condition within / 2 across, in order |
| `the_arm_key_is_not_a_parseable_stage2_reusable_arm_key` | bogus key (a pole in the change slot, wrong context arity, unknown lane) |
| `the_selection_names_an_arm_the_admitted_aggregate_does_not_have` | mismatched arm |
| `the_arm_keys_stage3_derives_are_not_the_arm_keys_the_selection_declares` | Stage-1's own `arms` block disagrees with our independent derivation |
| `the_aggregate_publishes_no_role_and_pole_map_for_stage3_to_check_itself_against` | nothing to check ourselves against |
| `the_aggregate_publishes_a_role_and_pole_map_stage3_does_not_agree_with` | the two lanes key arms to opposite perturbations |
| `the_selection_was_minted_against_a_different_stage1_release_than_the_aggregate` | **stale** — including a RESEALED contract whose ids all recompute |
| `the_v2_bundle_was_not_built_over_the_aggregate_presented` | stale bundle |
| `the_stage2_aggregate_was_not_admitted_by_a_receipt` | **unadmitted** |
| `the_receipt_binds_bytes_that_are_not_the_aggregate_presented` | receipt over other bytes |
| `the_receipt_binds_no_bridge_so_it_joins_nothing` | a receipt that joins nothing |

A resealed selection is internally flawless — every id recomputes. The ids are therefore **not**
the last gate: the view also requires the selection to be about the **store in hand**.

## 7. Status

Implemented and tested against **sealed, non-production inputs of the correct native shape**
(`spot.stage02_run_manifest.v3_topology_only` with `bundles[]`). Nothing here is a scientific
finding: every program is `FIXTURE_PROG_*`, every target `FIXTURE_TGT_*`, and the artifact class is
`fixture`, which the analysis path refuses by name. The **final real replay awaits W3's bytes**.
