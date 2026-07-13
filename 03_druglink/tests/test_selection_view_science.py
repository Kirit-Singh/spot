"""WHAT MUST SURVIVE THE PROJECTION — and the STRICT contract a browser receives.

A filter is easy. A filter that does not quietly destroy the science is the whole job:

  * the typed origins stay SEPARATE (direct / temporal are distinct MEASURED estimands, never
    fused; endpoint pathway context is INFERRED and sources nothing);
  * an inverse-direction hypothesis stays HYPOTHESIS-ONLY;
  * a null rank stays NULL — never 0, never last, never "best";
  * a filtered-out row is COUNTED, never silently dropped;
  * and nothing that leaves for a browser carries a machine-local path, a pooled objective, a
    p/q/FDR, or a field nobody agreed to.
"""
from __future__ import annotations

import json
import os

import pytest

from druglink import assertions_v2 as av
from druglink import bundle_v2 as bv2
from druglink import direction as dr
from druglink import selection_view as sv
from druglink import view_contract as vc

from selection_world import (
    EMIT_SCRIPT, FIXTURE_PATH, TEMPORAL, WITHIN,
    _conditions, _programs, _verified, _view,
)


# =========================================================================== #
# THE SCIENCE THAT MUST SURVIVE THE PROJECTION.
# =========================================================================== #
class TestTheScienceSurvivesTheProjection:

    def test_the_role_is_assigned_at_JOIN_TIME_and_an_arm_is_A_here_and_B_there(self, world):
        programs, conditions = _programs(world), _conditions(world)
        # ONE arm — `direct|P|decrease|c` — reached as A in one question and B in another.
        as_a = _verified(world, a=programs[0], b=programs[1], mode=WITHIN,
                         conditions=[conditions[0]], a_dir="high", b_dir="high")
        as_b = _verified(world, a=programs[1], b=programs[0], mode=WITHIN,
                         conditions=[conditions[0]], a_dir="high", b_dir="low")
        arm = f"direct|{programs[0]}|decrease|{conditions[0]}"
        v1, v2 = _view(world, as_a), _view(world, as_b)
        assert arm in v1["selected_arms"]["gene_arm_keys"]
        assert arm in v2["selected_arms"]["gene_arm_keys"]

        roles = [tuple(sorted({r for e in v["tables"]["target_drug_edges"]
                               if e["arm_key"] == arm
                               for r in e["selection_roles"]}))
                 for v in (v1, v2)]
        assert roles == [("away_from_A",), ("toward_B",)]

    def test_the_typed_origins_stay_separate_in_the_candidate_arm_maps(self, world):
        programs, conditions = _programs(world), _conditions(world)
        view = _view(world, _verified(world, a=programs[0], b=programs[1], mode=TEMPORAL,
                                      conditions=[conditions[0], conditions[1]]))
        for candidate in view["tables"]["candidates"]:
            maps = candidate["view_arm_keys_by_origin"]
            assert set(maps) == set(dr.V2_ORIGIN_TYPES)
            # MEASURED evidence landed in the temporal slot and NOWHERE else...
            assert maps[dr.ORIGIN_TEMPORAL_CROSS_TIME]
            assert maps[dr.ORIGIN_DIRECT_TARGET] == []
            # ...and the INFERRED slot exists, separately, and sources no edge.
            assert candidate["view_n_edges_by_origin"][dr.ORIGIN_ENDPOINT_PATHWAY] == 0

    def test_the_store_global_candidate_counts_are_NOT_overwritten_by_the_view(self, world):
        programs, conditions = _programs(world), _conditions(world)
        view = _view(world, _verified(world, a=programs[0], b=programs[1], mode=WITHIN,
                                      conditions=[conditions[0]]))
        by_id = {c["candidate_id"]: c for c in world["tables"]["candidates"]}
        for candidate in view["tables"]["candidates"]:
            store_row = by_id[candidate["candidate_id"]]
            assert candidate["n_edges_by_origin"] == store_row["n_edges_by_origin"]
            assert candidate["arm_keys"] == store_row["arm_keys"]
            # ...and the view's own, narrower counts travel BESIDE them, never instead.
            assert sum(candidate["view_n_edges_by_origin"].values()) <= \
                sum(store_row["n_edges_by_origin"].values())

    def test_a_pathway_arm_never_sources_a_drug_edge_in_the_view(self, world):
        programs, conditions = _programs(world), _conditions(world)
        view = _view(world, _verified(world, a=programs[0], b=programs[1], mode=WITHIN,
                                      conditions=[conditions[0]]))
        pathway_keys = set(k for keys in
                           view["selected_arms"]["pathway_context_arm_keys"].values()
                           for k in keys)
        assert pathway_keys, "the pathway context arms must be selected to be excluded"
        for edge in view["tables"]["target_drug_edges"]:
            assert edge["arm_key"] not in pathway_keys
            assert edge["origin_type"] in dr.MEASURED_ORIGINS

    def test_the_ENDPOINT_pathway_arm_membership_is_preserved_as_arm_slots(self, world):
        programs, conditions = _programs(world), _conditions(world)
        view = _view(world, _verified(world, a=programs[0], b=programs[1], mode=TEMPORAL,
                                      conditions=[conditions[0], conditions[2]]))
        slots = {s["arm_key"]: s for s in view["tables"]["arm_slots"]}
        expected = set(view["selected_arms"]["gene_arm_keys"])
        for keys in view["selected_arms"]["pathway_context_arm_keys"].values():
            expected |= set(keys)
        # BOTH kinds of membership survive: the measured arms AND the inferred context arms.
        assert set(slots) == expected
        assert view["missingness"]["pathway_lane_admitted"] is False
        assert view["missingness"]["pathway_context_absence_reason"]

    def test_an_inverse_direction_hypothesis_is_never_observed_support(self, world):
        programs, conditions = _programs(world), _conditions(world)
        seen = False
        for condition in conditions:
            view = _view(world, _verified(world, a=programs[0], b=programs[1], mode=WITHIN,
                                          conditions=[condition], a_dir="low", b_dir="high"))
            for edge in view["tables"]["target_drug_edges"]:
                if edge["directional_evidence_status"] == "inverse_direction_hypothesis":
                    seen = True
                    assert edge["observed_perturbation_support"] is False
                    assert edge["stage3_evidence_class"] == "inverse_direction_hypothesis"
                    assert edge["evidence_relation"] != "putative_crispri_phenocopy"
        assert seen, "the fixture must actually produce an inverse hypothesis to prove this"

    def test_a_null_rank_stays_null_and_never_becomes_a_zero(self, world):
        programs, conditions = _programs(world), _conditions(world)
        view = _view(world, _verified(world, a=programs[0], b=programs[1], mode=WITHIN,
                                      conditions=[conditions[0]]))
        unranked = [e for e in view["tables"]["target_drug_edges"] if e["arm_rank"] is None]
        assert unranked, "the fixture must carry a RETAINED unranked row to prove this"
        for edge in unranked:
            assert edge["arm_rank"] is not 0            # noqa: F632 — identity is the point
            assert edge["arm_rank_status"] == av.UNRANKED
        assert view["missingness"]["n_edges_with_a_null_rank"] == len(unranked)

    def test_filtered_out_rows_are_COUNTED_not_silently_dropped(self, world):
        programs, conditions = _programs(world), _conditions(world)
        view = _view(world, _verified(world, a=programs[0], b=programs[1], mode=WITHIN,
                                      conditions=[conditions[0]]))
        counts = {c["table"]: c for c in view["counts"]}
        assert set(counts) == set(sv.PROJECTED_TABLES)
        for name, count in counts.items():
            assert count["n_in_store"] == len(world["tables"][name])
            assert count["n_in_view"] == len(view["tables"][name])
            assert count["n_filtered_out"] == count["n_in_store"] - count["n_in_view"]
        # The point of the count: the store is much bigger than the answer.
        assert counts["target_drug_edges"]["n_filtered_out"] > 0

    def test_an_arm_that_no_drug_evidence_reached_SAYS_SO_by_name(self, world):
        view = _view(world, _verified(world, a=_programs(world)[0], b=_programs(world)[1],
                                      mode=WITHIN, conditions=[_conditions(world)[0]]))
        for entry in view["arm_evidence"]:
            assert entry["arm_evidence_state"]
            assert entry["n_ranked"] <= entry["n_records"]
        # The pathway context arms reached no drug evidence, and the view NAMES them.
        assert view["missingness"]["arms_with_no_drug_evidence"]

    def test_the_view_carries_no_pooled_objective_and_no_p_q_or_fdr(self, world):
        view = _view(world, _verified(world, a=_programs(world)[0], b=_programs(world)[1],
                                      mode=WITHIN, conditions=[_conditions(world)[0]]))
        bv2.check_no_combined_objective(view)
        bv2.check_no_pq_fdr(view)
        assert view["inference_status"] == "not_calibrated"


# =========================================================================== #
# THE BROWSER PROJECTION CONTRACT.
# =========================================================================== #
class TestTheBrowserProjectionContract:

    def test_the_view_satisfies_its_own_strict_contract(self, world):
        programs, conditions = _programs(world), _conditions(world)
        for mode, conds in ((WITHIN, [conditions[0]]),
                            (TEMPORAL, [conditions[0], conditions[1]])):
            view = _view(world, _verified(world, a=programs[0], b=programs[1], mode=mode,
                                          conditions=conds))
            vc.validate(view)

    def test_an_unknown_field_is_a_REFUSAL_and_not_an_extra(self, world):
        view = _view(world, _verified(world, a=_programs(world)[0], b=_programs(world)[1],
                                      mode=WITHIN, conditions=[_conditions(world)[0]]))
        view["tables"]["target_drug_edges"][0]["a_field_nobody_agreed_to"] = 1
        with pytest.raises(vc.ViewContractError) as exc:
            vc.check_rows(view)
        assert vc.GATE_UNKNOWN_FIELD in str(exc.value)

    def test_a_machine_local_path_can_never_cross_the_seam(self, world):
        view = _view(world, _verified(world, a=_programs(world)[0], b=_programs(world)[1],
                                      mode=WITHIN, conditions=[_conditions(world)[0]]))
        view["store"]["bundle_id"] = "/home/someone/secret/outputs/bundle"
        with pytest.raises(vc.ViewContractError) as exc:
            vc.check_browser_safe(view)
        assert vc.GATE_LOCAL_PATH in str(exc.value)

    def test_the_published_contract_names_every_projected_table(self):
        contract = vc.contract()
        assert set(contract["tables"]) == set(sv.PROJECTED_TABLES)
        assert contract["strict"] is True
        assert contract["guarantees"]["the_view_never_re_ranks_or_re_orders_the_store"] is True

    def test_the_checked_in_W12_fixture_is_a_LEGAL_view_of_the_CURRENT_contract(self, world):
        """W12 builds against this file today. If the contract moves, this fails — loudly.

        The volatile IDENTITY fields (bundle_id, code-tree hash, view_id…) move whenever any
        Stage-3 module changes, so they are not pinned: pinning them would make an unrelated
        edit fail here, and the next reader would weaken the check. What IS pinned is the SHAPE
        — every key at every level, and every column of every table — which is exactly what a
        frontend binds to.
        """
        with open(FIXTURE_PATH, encoding="utf-8") as fh:
            published = json.load(fh)
        vc.validate(published)                      # the checked-in bytes are a legal view

        programs, conditions = _programs(world), _conditions(world)
        fresh = _view(world, _verified(world, a=programs[0], b=programs[1], mode=TEMPORAL,
                                       conditions=[conditions[0], conditions[2]],
                                       a_dir="high", b_dir="high"))
        assert _shape(published) == _shape(fresh), (
            "the published W12 fixture no longer has the shape the materializer emits. "
            f"Regenerate it: python {os.path.relpath(EMIT_SCRIPT)}")


def _shape(node):
    """Every key at every level, and every column of every row. Values are NOT compared."""
    if isinstance(node, dict):
        return {k: _shape(v) for k, v in sorted(node.items())}
    if isinstance(node, list):
        merged: dict = {}
        for item in node:
            shape = _shape(item)
            if isinstance(shape, dict):
                merged.update(shape)
        return [merged] if merged else []
    return None


# --------------------------------------------------------------------------- #
# The regression test for the arm-slot target bug this round fixed.
# --------------------------------------------------------------------------- #
def test_a_record_with_no_target_id_never_invents_a_target_called_None(world):
    """A pathway record is a gene-set ENRICHMENT: it carries no target_id, and it must not
    acquire one. `str(None)` is the string "None", and `build_arm_slots` used to stringify the
    absent id — so every pathway arm slot reported ONE target, named "None", in a namespace named
    "None". An invented identity, in the one table whose job is to say honestly what each arm
    covered."""
    pathway_slots = [s for s in world["tables"]["arm_slots"] if s["lane"] == "pathway"]
    assert pathway_slots
    for slot in pathway_slots:
        assert slot["target_ids"] == []
        assert slot["n_targets"] == 0
        assert "None" not in slot["target_ids"]
