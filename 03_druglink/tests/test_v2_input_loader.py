"""The unified Stage-3 v2 input loader: consumes admitted Stage-2 Direct + temporal +
pathway arm bundles, keeps typed origins SEPARATE (measured direct/temporal vs inferred
pathway), preserves arbitrary ordered axes/conditions, binds exact admission hashes, and
enforces no-combined-score / no-fixture-fallback / no-self-admission. Production
consumption stays GATED until the independent detached-clone matrix is green.
"""
from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "analysis")))

from druglink import v2_input_loader as v2         # noqa: E402
from druglink.arm_query import ExternalAdmission    # noqa: E402


def _adm(sha="d" * 64):
    return ExternalAdmission(verifier_id="stage2_independent_verifier.v1",
                             producer_commit="abc123", bundle_sha256=sha, verdict="admit")


def _direct_bundle():
    return {"schema_version": "spot.stage02_direct_arm_bundle.v1", "condition": "Rest",
            "perturbation": {"perturbation_modality": "CRISPRi_knockdown"},
            "base_records": [{"base_key": "bk1", "target_id": "ENSG1",
                              "target_id_namespace": "ensembl_gene",
                              "target_ensembl": "ENSG1", "target_symbol": "G1",
                              "released_estimate_id": "e1"}],
            "arms": [{"arm_key": "direct|treg|decrease|Rest", "program_id": "treg",
                      "desired_change": "decrease",
                      "records": [{"base_key": "bk1", "target_id": "ENSG1",
                                   "arm_value": "-1.2", "rank": 1, "evaluable": True,
                                   "desired_target_modulation":
                                       "supports_target_inhibition"}]}]}


def _temporal_bundle():
    return {"schema_version": "spot.stage02_temporal_arm_bundle.v1",
            "context": {"from_condition": "Rest", "to_condition": "Stim48hr"},
            "perturbation": {"perturbation_modality": "CRISPRi_knockdown"},
            "base_records": [{"base_key": "bk2", "target_id": "ENSG2",
                              "target_id_namespace": "ensembl_gene",
                              "target_ensembl": "ENSG2",
                              "from_released_estimate_id": "e2a",
                              "to_released_estimate_id": "e2b"}],
            "arms": [{"arm_key": "temporal|treg|increase|Rest|Stim48hr",
                      "program_id": "treg", "desired_change": "increase",
                      "records": [{"base_key": "bk2", "target_id": "ENSG2",
                                   "arm_value": "0.8", "rank": 1, "evaluable": True,
                                   "desired_target_modulation":
                                       "supports_target_inhibition",
                                   "temporal_status": "evaluable"}]}]}


def _pathway_bundle():
    return {"schema_version": "spot.stage02_pathway_arm_bundle.v1",
            "verification_ref": {"verifier_id": "stage2_pathway_independent_verifier.v1"}}


def _pathway_node(target="ENSG3", hyp=True, own_dir=False):
    n = {"target_id": target, "target_id_namespace": "ensembl_gene", "set_id": "R-HSA-1",
         "is_hypothesis": hyp, "membership_source": "Reactome",
         "membership_sha256": "m" * 64}
    if own_dir:
        n.update({"desired_target_modulation": "supports_target_inhibition",
                  "modulation_source_id": "src1", "modulation_evidence_locator": "loc1",
                  "modulation_evidence_sha256": "s" * 64})
    return n


def _full():
    return v2.load_admitted_stage2_inputs(
        direct_arm_bundle=_direct_bundle(), direct_admission=_adm("a" * 64),
        temporal_arm_bundles=[(_temporal_bundle(), _adm("b" * 64))],
        pathway_arm_bundle=_pathway_bundle(), pathway_nodes=[_pathway_node()],
        measured_target_ids={"ENSG1", "ENSG2"})


def test_measured_and_pathway_origins_are_separate():
    r = _full()
    assert all(l["origin_type"] == "direct_target" for l in r["measured_levers"])
    assert {l["target_id"] for l in r["measured_levers"]} == {"ENSG1", "ENSG2"}
    assert all(n["origin_type"] == "pathway_node" for n in r["pathway_nodes"])
    assert {n["target_id"] for n in r["pathway_nodes"]} == {"ENSG3"}
    # no target is BOTH a measured lever and an inferred pathway node
    assert not ({l["target_id"] for l in r["measured_levers"]}
                & {n["target_id"] for n in r["pathway_nodes"]})


def test_ordered_temporal_axis_preserved_from_to():
    r = _full()
    tl = next(l for l in r["measured_levers"] if l["target_id"] == "ENSG2")
    assert tl["time_scope"] == "cross_time"
    assert tl["from_condition"] == "Rest" and tl["to_condition"] == "Stim48hr"
    dl = next(l for l in r["measured_levers"] if l["target_id"] == "ENSG1")
    assert dl["time_scope"] == "same_time" and dl["condition"] == "Rest"


def test_self_admission_is_refused():
    with pytest.raises(Exception):
        ExternalAdmission(verifier_id="stage2_producer_selfcheck.v1", producer_commit="x",
                          bundle_sha256="d" * 64, verdict="admit")  # not "independent"


def test_missing_admission_is_refused_no_default():
    with pytest.raises(Exception):
        v2.load_admitted_stage2_inputs(direct_arm_bundle=_direct_bundle(),
                                       direct_admission=None)


def test_admission_hashes_bound_per_lane():
    r = _full()
    assert r["admission_binding"]["direct"]["external_bundle_sha256"] == "a" * 64
    assert r["admission_binding"]["temporal"][0]["external_bundle_sha256"] == "b" * 64
    assert "independent" in r["admission_binding"]["pathway"]["verifier_id"]


def test_no_combined_score_arms_independent_counts_per_lane():
    r = _full()
    assert r["arms_are_independent"] is True
    assert r["combined_objective_permitted"] is False
    assert "combined_score" not in r and "combined_score" not in r["counts"]
    assert r["counts"]["per_lane"]["direct"]["n_levers"] == 1
    assert r["counts"]["per_lane"]["temporal"][0]["n_levers"] == 1
    assert r["counts"]["n_measured_levers"] == 2 and r["counts"]["n_pathway_nodes"] == 1


def test_pathway_node_without_own_direction_is_inert():
    r = v2.load_admitted_stage2_inputs(
        pathway_arm_bundle=_pathway_bundle(),
        pathway_nodes=[_pathway_node(hyp=True, own_dir=False)],
        measured_target_ids=set())
    n = r["pathway_nodes"][0]
    assert n["may_improve_drug_ordering"] is False
    assert n["desired_target_modulation"] == "direction_unresolved"


def test_pathway_membership_never_promotes_to_measured():
    r = v2.load_admitted_stage2_inputs(
        pathway_arm_bundle=_pathway_bundle(),
        pathway_nodes=[_pathway_node(target="ENSG1")],       # also a measured target
        measured_target_ids={"ENSG1"})
    assert r["pathway_nodes"][0]["node_class"] == "measured_perturbation_target"


def test_production_consumption_is_gated_until_matrix_green():
    with pytest.raises(Exception):
        v2.load_admitted_stage2_inputs(direct_arm_bundle=_direct_bundle(),
                                       direct_admission=_adm(), require_production=True)
    assert _full()["production_consumption_gated"] is True


def test_no_fixture_fallback_missing_lanes_stay_empty():
    r = v2.load_admitted_stage2_inputs()          # nothing supplied
    assert r["measured_levers"] == [] and r["pathway_nodes"] == []
