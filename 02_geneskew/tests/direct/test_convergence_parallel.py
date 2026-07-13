"""Ordered process chunks are an execution optimization, never a scientific change."""
from __future__ import annotations

import json

import pytest
from direct import convergence, pathway_arms, run_pathway_arms


def _vec(offset: float) -> dict[str, float]:
    # Enough shared genes for the production minimum; varied signs exercise the left fold.
    return {f"G{i:03d}": ((-1.0 if i % 3 == 0 else 1.0) * (i + 1 + offset))
            for i in range(40)}


@pytest.fixture
def inputs():
    signatures = {f"T{i}": _vec(i / 10.0) for i in range(8)}
    bundle = {"sets": {
        "P:1": {"genes_target": ["T0", "T1", "T2", "T3"],
                "n_genes_target": 4},
        "P:2": {"genes_target": ["T2", "T3", "T4", "T5", "T6"],
                "n_genes_target": 5},
        "P:3": {"genes_target": ["T0", "T6", "T7"],
                "n_genes_target": 3},
    }}
    return bundle, signatures


def test_two_workers_are_byte_identical_to_the_frozen_serial_order(inputs):
    bundle, signatures = inputs
    serial = convergence.pairwise_within_sets(
        bundle, signatures, workers=1, chunk_size=1)
    parallel = convergence.pairwise_within_sets(
        bundle, signatures, workers=2, chunk_size=1)

    assert parallel == serial
    assert json.dumps(parallel, sort_keys=True, separators=(",", ":")) == \
        json.dumps(serial, sort_keys=True, separators=(",", ":"))
    assert [(r["target_a"], r["target_b"]) for r in parallel] == sorted(
        (r["target_a"], r["target_b"]) for r in serial)


def test_parallel_execution_does_not_change_convergence_claims(inputs):
    bundle, signatures = inputs
    serial_pairs = convergence.pairwise_within_sets(bundle, signatures)
    parallel_pairs = convergence.pairwise_within_sets(
        bundle, signatures, workers=3, chunk_size=2)
    assert convergence.converge_sets(bundle, signatures, parallel_pairs) == \
        convergence.converge_sets(bundle, signatures, serial_pairs)


def test_complete_convergence_artifact_and_hash_are_unchanged(inputs):
    bundle, signatures = inputs
    serial = pathway_arms.convergence_artifact(
        bundle=bundle, signatures=signatures, condition="Rest", source="fixture",
        readout_universe_sha256="a" * 64, pairwise_workers=1,
        pair_chunk_size=1)
    parallel = pathway_arms.convergence_artifact(
        bundle=bundle, signatures=signatures, condition="Rest", source="fixture",
        readout_universe_sha256="a" * 64, pairwise_workers=3,
        pair_chunk_size=2)
    assert parallel == serial
    assert parallel["convergence_sha256"] == serial["convergence_sha256"]
    assert parallel["convergence_method_id"] == convergence.METHOD_ID


@pytest.mark.parametrize("case", ["zero", "supportive", "mixed"])
def test_streamed_supportive_evidence_is_byte_identical_to_full_records(case):
    base = _vec(0.0)
    same = _vec(0.1)
    opposed = {gene: -value for gene, value in base.items()}
    orthogonal = {gene: (value if i % 2 else -value)
                  for i, (gene, value) in enumerate(base.items())}
    signatures_by_case = {
        "zero": {"T0": base, "T1": opposed, "T2": orthogonal},
        "supportive": {"T0": base, "T1": same, "T2": _vec(0.2)},
        "mixed": {"T0": base, "T1": same, "T2": opposed},
    }
    signatures = signatures_by_case[case]
    members = sorted(signatures)
    bundle = {"sets": {"P:STREAM": {
        "name": "stream equivalence", "genes_target": members,
        "genes_in_target_universe": members, "n_genes_target": len(members),
        "n_genes_in_target_universe": len(members),
        "n_source_symbols": len(members), "target_source_coverage": 1.0,
    }}}

    full = pathway_arms.convergence_artifact(
        bundle=bundle, signatures=signatures, condition="Rest", source="fixture",
        readout_universe_sha256="c" * 64, pairwise_workers=2,
        pair_chunk_size=1, compact_pair_evidence=False)
    streamed = pathway_arms.convergence_artifact(
        bundle=bundle, signatures=signatures, condition="Rest", source="fixture",
        readout_universe_sha256="c" * 64, pairwise_workers=2,
        pair_chunk_size=1, compact_pair_evidence=True)

    assert streamed == full
    assert streamed["convergence_sha256"] == full["convergence_sha256"]
    assert json.dumps(streamed, sort_keys=True, separators=(",", ":")) == \
        json.dumps(full, sort_keys=True, separators=(",", ":"))


@pytest.mark.parametrize("workers,chunk", [(0, 10), (-1, 10), (2, 0), (2, -1)])
def test_invalid_execution_topology_fails_closed(inputs, workers, chunk):
    bundle, signatures = inputs
    with pytest.raises(convergence.ConvergenceExecutionError):
        convergence.pairwise_within_sets(
            bundle, signatures, workers=workers, chunk_size=chunk)


def test_cli_exposes_explicit_execution_only_controls():
    parser = run_pathway_arms.build_parser()
    defaults = {a.dest: a.default for a in parser._actions}
    assert defaults["convergence_workers"] == convergence.DEFAULT_PAIRWISE_WORKERS
    assert defaults["convergence_chunk_size"] == convergence.DEFAULT_PAIR_CHUNK_SIZE


def _size_bundle(n: int, set_id: str = "GO:SIZE") -> dict:
    members = [f"T{i:05d}" for i in range(n)]
    return {"sets": {set_id: {
        "name": set_id,
        "genes_target": members,
        "genes_in_target_universe": members,
        "n_genes_target": n,
        "n_genes_in_target_universe": n,
        "n_source_symbols": n,
        "target_source_coverage": 1.0,
    }}}


def test_convergence_size_boundary_is_inclusive_at_500_and_refuses_501():
    one = _size_bundle(1)["sets"]["GO:SIZE"]
    at = _size_bundle(500)["sets"]["GO:SIZE"]
    over = _size_bundle(501)["sets"]["GO:SIZE"]
    one_member = convergence.convergence_size_disposition(
        one, {"T00000": {}})
    at_boundary = convergence.convergence_size_disposition(
        at, {f"T{i:05d}": {} for i in range(500)})
    over_boundary = convergence.convergence_size_disposition(
        over, {f"T{i:05d}": {} for i in range(501)})

    # Max-only policy: do not import enrichment's >=3 rule or rewrite the existing
    # single-target refusal semantics while fixing giant roots.
    assert one_member["convergence_evaluable"] is True
    assert at_boundary["convergence_evaluable"] is True
    assert at_boundary["n_measured_convergence_endpoints"] == 500
    assert at_boundary["convergence_size_disposition"] == convergence.SIZE_EVALUABLE
    assert over_boundary["convergence_evaluable"] is False
    assert over_boundary["n_measured_convergence_endpoints"] == 501
    assert over_boundary["convergence_size_disposition"] == convergence.SIZE_TOO_LARGE


def test_giant_go_root_emits_coverage_but_generates_no_pairs(monkeypatch):
    # GO:0008150 (biological_process) has 10,371 target-universe members in the pinned
    # bundle. Its presence must be visible, but it cannot make ~54M pair calls or a claim.
    n_root = 10_371
    bundle = _size_bundle(n_root, "GO:0008150")
    signatures = {f"T{i:05d}": _vec(i / 10.0) for i in range(501)}

    def forbidden_cosine(*_args, **_kwargs):
        raise AssertionError("an oversized set attempted a pair computation")

    monkeypatch.setattr(convergence, "cosine_on_shared", forbidden_cosine)
    pairs = convergence.pairwise_within_sets(bundle, signatures)
    records = convergence.converge_sets(bundle, signatures, pairs)

    assert pairs == []
    assert len(records) == 1
    record = records[0]
    assert record["set_id"] == "GO:0008150"
    assert record["n_source_symbols"] == n_root
    assert record["n_genes_in_target_universe"] == n_root
    assert record["n_measured_convergence_endpoints"] == 501
    assert record["target_source_coverage"] == 1.0
    assert record["convergence_evaluable"] is False
    assert record["convergence_claim_eligible"] is False
    assert record["convergent"] is False
    assert record["convergence_refused_reason"] == convergence.SIZE_TOO_LARGE
    assert record["n_supportive_pairs"] == 0
    assert record["pairwise_support"] == []
    assert record["supporting_perturbations"] == []
    assert record["intra_set_components"] == []


def test_size_policy_and_limits_are_bound_into_artifact_and_hash():
    bundle = _size_bundle(501)
    signatures = {f"T{i:05d}": _vec(i / 10.0) for i in range(501)}
    doc = pathway_arms.convergence_artifact(
        bundle=bundle, signatures=signatures, condition="Rest", source="go_bp",
        readout_universe_sha256="b" * 64)

    assert doc["schema_version"] == "spot.stage02_pathway_convergence.v2"
    assert doc["convergence_method_id"] == convergence.METHOD_ID
    assert doc["convergence_size_policy_id"] == convergence.CONVERGENCE_SIZE_POLICY_ID
    assert doc["convergence_size_basis"] == convergence.CONVERGENCE_SIZE_BASIS
    assert doc["max_convergence_set_size"] == 500
    assert doc["n_convergence_evaluable_sets"] == 0
    assert doc["n_convergence_non_evaluable_sets"] == 1

    from direct.hashing import content_hash
    mutated = dict(doc)
    mutated["max_convergence_set_size"] = 501
    mutated.pop("convergence_sha256")
    assert content_hash(mutated) != doc["convergence_sha256"]


def test_target_absent_from_readout_membership_remains_a_signature_endpoint():
    # Convergence endpoints are perturbed targets. The readout universe is the coordinate
    # axis inside each vector, not a second membership filter on the perturbation target.
    off_readout = "TARGET_WITH_SIGNATURE_NOT_IN_PATHWAY_READOUT_MEMBERS"
    on_readout = "TARGET_IN_BOTH_UNIVERSES"
    bundle = {"sets": {"P:OFFREADOUT": {
        "name": "two target members",
        "genes_target": [off_readout, on_readout],
        "genes_in_target_universe": [off_readout, on_readout],
        "n_genes_target": 2,
        "n_genes_in_target_universe": 2,
        "genes_readout": [on_readout],
        "genes_in_universe": [on_readout],
        "n_genes_in_universe": 1,
        "n_source_symbols": 2,
        "target_source_coverage": 1.0,
        "readout_source_coverage": 0.5,
    }}}
    signatures = {off_readout: _vec(0.0), on_readout: _vec(0.1)}
    pairs = convergence.pairwise_within_sets(bundle, signatures)
    record = convergence.converge_sets(bundle, signatures, pairs)[0]

    assert record["n_genes_in_readout_universe"] == 1
    assert record["n_genes_in_target_universe"] == 2
    assert record["n_measured_convergence_endpoints"] == 2
    assert record["measured_perturbations"] == sorted([off_readout, on_readout])
    assert record["convergent"] is True
