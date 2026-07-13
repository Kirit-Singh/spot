"""run_stage3 consumes the THREE typed origins and the ADMITTED universe store — and, while
the detached-clone matrix is red, produces NO candidate bundle at all.

Stage-3's producer knew two origins and no universe store. This wires it to what Stage 2
actually admits:

    direct_target                  same-condition measured
    temporal_cross_time_measured   cross-time DiD measured — a DISTINCT estimand
    endpoint_pathway_context       inferred; nobody perturbed it

plus the universe store an INDEPENDENT verifier admitted (``bdf41b69…``), bound by exact id.

THE GATE IS THE POINT OF THIS COMMIT
------------------------------------
``arm_query.DETACHED_CLONE_MATRIX_GREEN`` is False. So a production consumption REFUSES, and
Stage 3 writes nothing. There is no fabricated candidate bundle here and there must not be one:
a synthetic number that reaches a bundle is a synthetic number that reaches Stage 4. The wiring
is real, the refusal is real, and the candidates wait for a real admitted Stage-2 bundle.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))

from druglink import admitted_universe as au    # noqa: E402
from druglink import arm_query as aq            # noqa: E402
from druglink import direction as d             # noqa: E402
from druglink import run_stage3                 # noqa: E402
from druglink import v2_input_loader as v2      # noqa: E402


# the SAME fixtures the admitted loader's own tests use — a second, subtly different bundle
# shape here would be testing my invention rather than the shipped contract
from test_v2_input_loader import _D, _adm, _direct_bundle  # noqa: E402,F401


class TestTheProducerKnowsTheThreeTypedOrigins:
    def test_run_stage3_counts_every_typed_origin_separately(self):
        # counted SEPARATELY, never pooled: a measured target and an inferred neighbour are
        # not two of the same thing
        assert set(run_stage3.V2_ORIGINS) == {
            d.ORIGIN_DIRECT_TARGET, d.ORIGIN_TEMPORAL_CROSS_TIME,
            d.ORIGIN_ENDPOINT_PATHWAY}
        # ...and the V1 document's origins are UNCHANGED: Stage 4 binds those bytes by SHA
        assert set(run_stage3.ORIGINS) == {d.ORIGIN_DIRECT_TARGET, d.ORIGIN_PATHWAY_NODE}

    def test_the_producer_never_declares_a_combined_objective(self):
        # a pooled/blended objective under ANY name would fuse the origins the lane exists to
        # keep apart
        banned = ("combined_score", "combined_rank", "merged_evidence", "fused_evidence",
                  "overall_evidence", "aggregate_evidence", "unified_score",
                  "blended_score", "origin_agnostic_rank", "cross_origin_score")
        src = open(os.path.join(os.path.dirname(__file__), "..", "analysis", "druglink",
                                "run_stage3.py")).read()
        for name in banned:
            assert name not in src


class TestProductionIsGatedAndNothingIsFabricated:
    def test_a_production_consumption_REFUSES_while_the_matrix_is_red(self):
        assert aq.DETACHED_CLONE_MATRIX_GREEN is False
        with pytest.raises(v2.ProductionConsumptionGated):
            v2.load_admitted_stage2_inputs(direct_arm_bundle=_D,
                                           direct_admission=_adm(_D),
                                           require_production=True)

    def test_the_v2_loader_reports_that_it_is_gated(self):
        out = v2.load_admitted_stage2_inputs(direct_arm_bundle=_D,
                                             direct_admission=_adm(_D))
        assert out["production_consumption_gated"] is True
        assert out["combined_objective_permitted"] is False

    def test_the_v2_CLI_writes_NO_bundle_while_gated(self, tmp_path, capsys):
        out_root = str(tmp_path / "out")
        rc = run_stage3.main([
            "--v2", "--artifact-class", "analysis",
            "--universe-store", str(tmp_path / "no-store"),
            "--output-root", out_root])
        assert rc != 0, "a gated v2 run must not report success"
        # NOTHING was written. A fabricated bundle is a synthetic number on its way to Stage 4.
        assert not os.path.exists(out_root) or not os.listdir(out_root)
        assert "REFUSED" in capsys.readouterr().out


class TestTheAdmittedUniverseStoreIsBoundNotAdmitted:
    def test_the_v2_path_REFUSES_a_store_that_was_never_admitted(self, tmp_path):
        with pytest.raises(au.AdmittedUniverseError) as exc:
            run_stage3.load_v2_inputs(
                universe_store=str(tmp_path / "missing"),
                universe_targets=[{"target_id": "ENSG1",
                                   "target_id_namespace": "ensembl"}])
        assert exc.value.reason == au.REFUSE_STORE_NOT_FOUND

    def test_there_is_NO_fixture_fallback_for_a_missing_store(self, tmp_path):
        # the failure mode the contract names: a missing admitted artifact quietly becoming a
        # synthetic one
        with pytest.raises(au.AdmittedUniverseError):
            run_stage3.load_v2_inputs(
                universe_store=str(tmp_path / "missing"),
                universe_targets=[{"target_id": "ENSG1",
                                   "target_id_namespace": "ensembl"}])


class TestMeasuredAndInferredNeverMerge:
    def test_the_three_origins_land_in_separate_collections(self):
        out = v2.load_admitted_stage2_inputs(direct_arm_bundle=_D,
                                             direct_admission=_adm(_D))
        measured = {lev["origin_type"] for lev in out["measured_levers"]}
        inferred = {n["origin_type"] for n in out["pathway_nodes"]}
        assert not (measured & inferred)
        assert measured <= d.MEASURED_ORIGINS

    def test_an_inferred_node_can_never_carry_observed_support(self):
        got = d.translate(desired_modulation=d.MOD_DECREASE,
                          effect=d.FUNCTIONAL_INHIBITION, arm_evaluable=True,
                          target_entity_is_single_protein=True,
                          origin_type=d.ORIGIN_ENDPOINT_PATHWAY)
        assert got["observed_perturbation_support"] is False

    def test_the_run_binds_the_store_id_when_a_store_IS_supplied(self):
        block = au.binding_block(store_id=au.ADMITTED_STORE_ID,
                                 verify={"ok": True, "violations": [],
                                         "verify_policy_version": "x"})
        assert block["store_id"] == au.ADMITTED_STORE_ID
        assert block["producer_admits_store"] is False
        assert json.dumps(block)          # serialisable into the bundle
