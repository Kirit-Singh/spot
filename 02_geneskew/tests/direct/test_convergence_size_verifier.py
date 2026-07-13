"""Independent attacks on the prospective >500 convergence-endpoint ceiling."""
from __future__ import annotations

import json

import numpy as np
from direct import verify_rules as R
from direct import verify_signature_matrix as V


def _set(set_id: str, targets: list[str], readout: list[str] | None = None) -> dict:
    return {
        "set_id": set_id,
        "name": set_id,
        "genes_target": targets,
        "genes_readout": targets if readout is None else readout,
        "n_source_symbols": len(targets),
    }


def _record(source: dict, available: set[str]) -> dict:
    targets = sorted(set(source["genes_target"]))
    readout = sorted(set(source["genes_readout"]))
    endpoints = sorted(set(targets) & available)
    evaluable = len(endpoints) <= V.MAX_CONVERGENCE_SET_SIZE
    return {
        "set_id": source["set_id"],
        "method_id": V.CONVERGENCE_METHOD_ID,
        "convergence_size_policy_id": V.CONVERGENCE_SIZE_POLICY_ID,
        "convergence_size_basis": V.CONVERGENCE_SIZE_BASIS,
        "max_convergence_set_size": V.MAX_CONVERGENCE_SET_SIZE,
        "n_genes_in_set": len(targets),
        "n_source_symbols": len(targets),
        "n_genes_in_target_universe": len(targets),
        "n_genes_in_readout_universe": len(readout),
        "target_source_coverage": 1.0,
        "readout_source_coverage": round(len(readout) / len(targets), 6),
        "global_coverage_disposition": "rankable",
        "global_coverage_policy_passed": True,
        "n_measured_convergence_endpoints": len(endpoints),
        "n_measured_perturbations": len(endpoints),
        "measured_perturbations": endpoints,
        "convergence_evaluable": evaluable,
        "convergence_claim_eligible": evaluable,
        "convergence_size_disposition": (
            V.SIZE_EVALUABLE if evaluable else V.SIZE_TOO_LARGE),
        "convergent": False,
        "convergence_refused_reason": (
            "fewer_than_two_perturbations_converge" if evaluable else V.SIZE_TOO_LARGE),
        "n_supporting_perturbations": 0,
        "supporting_perturbations": [],
        "n_intra_set_components": 0,
        "intra_set_components": [],
        "n_supportive_pairs": 0,
        "pairwise_support": [],
    }


def _fixture(tmp_path):
    at = [f"AT{i:04d}" for i in range(500)]
    over = [f"OVER{i:04d}" for i in range(501)]
    off_readout, on_readout = "OFF_READOUT_TARGET", "ON_READOUT_TARGET"
    sets = [
        _set("GO:BOUNDARY500", at),
        _set("GO:0008150", over),
        _set("GO:OFFREADOUT", [off_readout, on_readout], [on_readout]),
    ]
    ids = at + over + [off_readout, on_readout]
    rr = {
        "targets": ids,
        "bitmap": np.ones((len(ids), 1), dtype=np.uint8),
        "values": np.zeros((len(ids), 1), dtype=np.float64),
        "gene_ids": ["READOUT_COORDINATE"],
        "n_genes": 1,
    }
    gs = tmp_path / "gene_sets.source.json"
    gs.write_text(json.dumps({"sets": sets}) + "\n")
    available = set(ids)
    records = [_record(source, available) for source in sets]
    doc = {
        "schema_version": V.CONVERGENCE_SCHEMA,
        "convergence_method_id": V.CONVERGENCE_METHOD_ID,
        "convergence_size_policy_id": V.CONVERGENCE_SIZE_POLICY_ID,
        "convergence_size_basis": V.CONVERGENCE_SIZE_BASIS,
        "max_convergence_set_size": V.MAX_CONVERGENCE_SET_SIZE,
        "n_sets": len(records),
        "n_convergence_evaluable_sets": 2,
        "n_convergence_non_evaluable_sets": 1,
        # The 501-member root contributes zero. The 2-member off-readout control contributes 1.
        "n_intra_set_pairs": 500 * 499 // 2 + 1,
        "sets": records,
    }
    doc["convergence_sha256"] = R.content_sha256(doc)
    return doc, rr, str(gs)


def _reseal(doc):
    doc["convergence_sha256"] = R.content_sha256(
        {k: v for k, v in doc.items() if k != "convergence_sha256"})


def test_honest_500_501_boundary_and_off_readout_endpoint_admit(tmp_path):
    doc, rr, gs = _fixture(tmp_path)
    ok, detail = V._verify_convergence_size(doc, rr, gs)
    assert ok, detail
    records = {r["set_id"]: r for r in doc["sets"]}
    assert records["GO:BOUNDARY500"]["convergence_evaluable"] is True
    assert records["GO:0008150"]["convergence_evaluable"] is False
    assert records["GO:OFFREADOUT"]["measured_perturbations"] == [
        "OFF_READOUT_TARGET", "ON_READOUT_TARGET"]


def test_oversized_root_forged_as_convergent_is_rejected_after_reseal(tmp_path):
    doc, rr, gs = _fixture(tmp_path)
    root = next(r for r in doc["sets"] if r["set_id"] == "GO:0008150")
    root.update({
        "convergent": True,
        "convergence_claim_eligible": True,
        "n_supporting_perturbations": 2,
        "supporting_perturbations": ["OVER0000", "OVER0001"],
        "n_supportive_pairs": 1,
        "pairwise_support": [{"target_a": "OVER0000", "target_b": "OVER0001"}],
        "convergence_refused_reason": None,
    })
    _reseal(doc)
    ok, detail = V._verify_convergence_size(doc, rr, gs)
    assert not ok and "oversized set carries" in detail


def test_omitting_the_oversized_root_is_rejected_after_reseal(tmp_path):
    doc, rr, gs = _fixture(tmp_path)
    doc["sets"] = [r for r in doc["sets"] if r["set_id"] != "GO:0008150"]
    doc["n_sets"] = 2
    doc["n_convergence_non_evaluable_sets"] = 0
    _reseal(doc)
    ok, detail = V._verify_convergence_size(doc, rr, gs)
    assert not ok and "source set inventory" in detail


def test_resealed_method_or_limit_change_is_rejected(tmp_path):
    doc, rr, gs = _fixture(tmp_path)
    doc["max_convergence_set_size"] = 501
    _reseal(doc)
    ok, detail = V._verify_convergence_size(doc, rr, gs)
    assert not ok and "max_convergence_set_size" in detail


def test_dropping_a_valid_off_readout_target_endpoint_is_rejected(tmp_path):
    doc, rr, gs = _fixture(tmp_path)
    record = next(r for r in doc["sets"] if r["set_id"] == "GO:OFFREADOUT")
    record["measured_perturbations"] = ["ON_READOUT_TARGET"]
    record["n_measured_perturbations"] = 1
    record["n_measured_convergence_endpoints"] = 1
    _reseal(doc)
    ok, detail = V._verify_convergence_size(doc, rr, gs)
    assert not ok and "OFFREADOUT" in detail
