# Stage-3 — handoff at the wall clock. NOTHING WAS COMMITTED, and here is exactly why.

**Last commit on `agent/stage3-druglink`: `bda4ccc`** (prefetch manifest corrected). Everything
below this line is **UNCOMMITTED and dirty on purpose.**

## Why nothing was committed

A selective commit of the pathway-invariant adapters was attempted and **could not be proven
clean**, so per the rule it was abandoned rather than shipped. Two hard failures, found by staging
the adapter set, stashing everything else, and running the gates against *exactly* what would land:

1. **Line gate breached.** The four >500-line splits live in the same working set as the selection
   view. Committing the adapters alone drags in the *pre-split* `selection_view.py` (502),
   `view_projection.py` (503), `test_selection_view_projection_seal.py` (540).
2. **`test_frozen_contract` fails.** `schemas/spot.stage03_drug_annotation.v2.json` and the
   published W12 view fixture (`selection_view.fixture.v1.json`) are **coupled by a pin**. Commit
   the schema without the fixture and the pin names a schema set that no longer exists.

Either could have been forced green by hand-editing a pin. That is the one thing this lane does not
do.

## What IS proven (and is NOT a claim about the current tree)

The bridge consumer was proven end to end **against an earlier tree**:
CLI exit 0 → `fx_b04f43a54855f3ec`; independent verifier **147/147**. **That result does not certify
the tree as it now stands** — files changed after it. It is reported as history, not as a
guarantee.

Focused gates that pass on the current tree (98 passed / 2 skipped):
`test_stage2_bridge_consumer` · `test_v2_cli_artifact_class` · `test_v2_cli_bridge_gate` ·
`test_frozen_contract` · `test_arm_query_v2` · `test_run_stage3_v2_wiring`
Plus, committed and green: `test_prefetch_manifest` (17).

## BLOCKER 1 — W18: the pathway lane is not admitted

**W18's pathway fixture `117ccc4` is not admitted by verifier `0bf73cd3`: it CRASHES with
`KeyError: pathway_run_id`.** Its forgery refusals were therefore **vacuous** — the gate never ran,
and every "refusal" was an exception escaping, which from outside looks exactly like a judgement.

**An ADMIT from a gate that cannot run carries no information. Neither does a REFUSE.**

Stage-3 is fail-closed here already: pathway contributes zero, checked by
`[the_pathway_lane_contributed_nothing]` and `[the_pathway_lane_contributed_a_typed_target_row]`.

### ⚠ ZERO IS A FAIL-CLOSED TEMPORARY STATE — NOT THE INTENDED RESULT

Pathway counts **must not be re-pinned to zero**. Doing so would launder W18's admission defect
into Stage-3's expected science, and the next reader would inherit "pathway yields nothing" as a
finding rather than a blockage.

**These 14 tests are BLOCKED ON W18** — they assert the pathway lane's real behaviour and must be
restored, not rewritten:

```
test_candidates_v2.py::TestAnInferredNodeIsNeverAMeasurement::test_a_pathway_RECORD_with_a_measured_rank_is_REFUSED_at_build
test_candidates_v2.py::TestAnInferredNodeIsNeverAMeasurement::test_a_pathway_edge_carries_no_rank_no_support_and_no_modality
test_candidates_v2.py::TestAnInferredNodeIsNeverAMeasurement::test_a_pathway_edge_claiming_observed_support_is_REFUSED
test_candidates_v2.py::TestAnInferredNodeIsNeverAMeasurement::test_a_pathway_edge_with_a_measured_rank_is_REFUSED
test_candidates_v2.py::TestDirectionIsNeverInheritedFromSetMembership::test_a_node_with_its_own_sourced_direction_is_a_pathway_HYPOTHESIS
test_candidates_v2.py::TestSummariesSeparateWhatTheEvidenceSeparates::test_an_inferred_summary_carries_no_rank_and_no_support
test_candidates_v2.py::TestTheBuildIsNonVacuous::test_all_five_directional_statuses_are_really_present
test_candidates_v2.py::TestTheBuildIsNonVacuous::test_all_three_typed_origins_are_really_present
test_artifacts_v2.py::TestAnInferredEdgeIsRefusedAMeasuredRank::test_a_pathway_origin_edge_carrying_a_rank_is_REFUSED_at_WRITE
test_artifacts_v2.py::TestAnInferredEdgeIsRefusedAMeasuredRank::test_an_origin_swapped_edge_is_REFUSED_at_WRITE
+ 4 more in the same two classes
```

## BLOCKER 2 — a REAL candidate-ID join defect (not stale-test noise)

Surfaced while migrating the fixture factory to the native contract:

```
[a_candidate_id_is_not_the_same_identity_in_every_table]
target_drug_edges references candidate_id='AM:INCHIKEY:FIXTUREKEYBBBBBBBBBBBBBBBBB-N',
which is in NO candidate row. A reference nobody can resolve is a join that silently drops.
```

An edge names a candidate that does not exist. **This is a production join defect, not a fixture
artefact** — the gate is doing its job and must not be silenced. It is the whole reason the fixture
migration is left dirty rather than committed.

## BLOCKER 3 — the fixture factory migration is incomplete

`tests/candidates_v2_fixture.py` still builds the retired
`spot.stage02_aggregate_run_manifest.v1`, correctly refused by
`[manifest_is_not_the_native_stage2_run_manifest_schema]`. My migration to the native factory got
past that and past the namespace vocabulary, then hit BLOCKER 2 — so it was **reverted**, not
half-landed.

Two findings from that attempt, worth keeping:
- the fixture store used `NS = "fixture"`, an identity space nobody agreed to. The admitted
  vocabulary is exactly `ensembl_gene_id` / `gene_symbol`.
- the fixture must carry a **symbol-only** target (as the real store carries MTRNR2L1/4/8, OCLM),
  or the row contract and the store name their namespaces differently and the join refuses.

## STAGE-3 IS NOT PRODUCTION-READY

No run may be described as such while BLOCKERS 1–3 stand.

## Exact dirty file list

```
M  STAGE3_V2_EMISSION_RUNBOOK.md          M  analysis/druglink/view_projection.py
M  analysis/druglink/arm_query.py         M  schemas/spot.stage03_drug_annotation.v2.json
M  analysis/druglink/artifacts_v2.py      M  selection_view.fixture.v1.json
M  analysis/druglink/bundle_v2.py         M  tests/native_aggregate_fixture.py
M  analysis/druglink/run_stage3_v2.py     M  tests/sign_fixture_v2.py
M  analysis/druglink/selection_view.py    M  tests/test_arm_query_v2.py
M  analysis/druglink/stage2_aggregate.py  M  tests/test_frozen_contract.py
M  analysis/druglink/stage2_contract.py   M  tests/test_run_stage3_v2_wiring.py
M  verifier/v2_bridge.py                  M  tests/test_selection_view_projection_seal.py
M  verifier/v2_contract.py                M  verifier/v2_rebuild.py
M  verifier/v2_reconstruct.py             M  verifier/verify_stage3_v2.py

?? analysis/druglink/selection_admission.py     ?? tests/test_selection_view_projection_store.py
?? analysis/druglink/stage2_bridge.py           ?? tests/test_stage2_bridge_consumer.py
?? analysis/druglink/stage2_bridge_contract.py  ?? tests/test_v2_emission_end_to_end.py
?? analysis/druglink/view_projection_tables.py  ?? tests/w3_bridge_fixture.py
?? verifier/v2_bundles.py                       ?? verifier/v2_reconstruct_util.py
```

Line gate clean, ruff clean, v1 schema byte-identical (`361d0833…`) across all of it.

## Durable artifacts (safe to use)

```
admitted universe   /home/tcelab/.spot-runs/stage3-universe-20260713/store_w3tokens   625c921f…
W3 v3 chain         /home/tcelab/.spot-runs/stage3-universe-20260713/w3_v3_chain/
prefetch manifest   …/prefetch/prefetch_manifest.ed29138bbf3210ac.json  (COMMITTED, green)
```
