"""The pathway-node lane: inferred, never measured, never merged with gene evidence.

Stage 2 measures direct targets and may also propose pathway nodes. A node was NEVER
PERTURBED, so:

  * it can never be an ``observed_perturbation`` — only a ``pathway_hypothesis``;
  * it must state its OWN direction — "in the same pathway" is not evidence about a
    gene, and no direction propagates between sibling nodes;
  * its programmatic evidence must be ARM-SPECIFIC, and it must cite a contributing
    perturbation that really exists in THIS screen on THAT arm;
  * a gene that is both a measured target and an inferred node holds TWO separate
    levers, and neither borrows the other's rank, tier or support.

**Stage 2 OWNS and EMITS this document.** The schema name and required fields are a
Stage-3 CONSUMER PROPOSAL pending the Stage-2 owner's agreement — the lane is NOT
frozen, and Stage 3 neither edits Stage 2 nor freezes a Stage-2 contract. The documents
built here are TEST INPUTS against the proposed consumer contract; they are not a
Stage-2 output and not a scientific finding.
"""
from __future__ import annotations

import copy

import pytest

from druglink import acquisition, pathways, run_stage3, workflow as wf
from druglink.direction import ORIGIN_DIRECT_TARGET, ORIGIN_PATHWAY_NODE

CTLA4 = "ENSG00000163599"
IL2RA = "ENSG00000134460"


def _enrichment():
    """A COMPUTED enrichment: numeric, with the context that makes it reproducible."""
    return {"method_id": "enrich.v1",
            "statistic_name": "hypergeometric_odds_ratio",
            "enrichment_value": 3.7,                 # NUMERIC, not stringified
            "inference_status": "not_calibrated",
            "rounding_rule": "ieee754_float64_no_rounding",
            "gene_set_release": "GO-2026-05",
            "gene_set_sha256": "b" * 64,
            "universe_binding": {"universe_id": "stage2_common_universe",
                                 "universe_sha256": "c" * 64, "n_genes": 18000}}


def _prog(arm):
    """Arm-specific computed evidence, repeating the COMPLETE parent binding inline.

    A node must bind a hash-bound parent enrichment: either a parent_enrichment_ref, or —
    as here — the full gene-set release + universe binding repeated inline. Neither is
    a dangling parent, and a dangling parent is refused.
    """
    return {"method_id": "enrich.v1", "desired_arm": arm,
            "statistic_name": "hypergeometric_odds_ratio",
            "enrichment_value": 3.7,
            "inference_status": "not_calibrated",
            "rounding_rule": "ieee754_float64_no_rounding",
            "gene_set_release": "GO-2026-05",
            "gene_set_sha256": "b" * 64,
            "universe_binding": {"universe_id": "stage2_common_universe",
                                 "universe_sha256": "c" * 64, "n_genes": 18000}}



def _doc(direct, nodes, pathway_id="GO:0042110"):
    return {
        "schema_version": pathways.PATHWAY_SCHEMA,
        "artifact_class": "analysis",
        "direct_run_id": direct.run_id,
        "direct_run_binding_sha256": direct.binding_sha256,
        "method": {"pathway_method_version": "test-only"},
        "pathways": [{
            "pathway_id": pathway_id,
            "pathway_source": "GO",
            "pathway_source_release": "2026-05",
            "pathway_source_sha256": "a" * 64,
            "computed_enrichment": _enrichment(),
            "nodes": nodes,
        }],
    }


def _node(ensembl, arm, modulation, contributors):
    return {
        "target_ensembl": ensembl,
        "desired_arm": arm,
        "desired_target_modulation": modulation,
        "evidence_status": "computed_enrichment_member",
        "programmatic_evidence": _prog(arm),
        "contributing_perturbations": [
            {"target_ensembl": c, "desired_arm": arm} for c in contributors],
    }


# --------------------------------------------------------------------------- #
# The lane is optional, and its absence is explicit. It is NOT frozen.
# --------------------------------------------------------------------------- #
def test_absent_pathway_lane_is_explicitly_not_evaluated(loaded_direct,
                                                         analysis_build):
    loaded = pathways.load(None, artifact_class="analysis", direct=loaded_direct)
    assert loaded["levers"] == []
    assert loaded["ref"]["pathway_lane"] == "not_evaluated"

    doc = analysis_build["document"]
    assert doc["pathway_hypotheses"]["pathway_lane"] == "not_evaluated"
    assert doc["pathway_hypotheses"]["n_nodes"] == 0
    assert analysis_build["tables"]["pathway_nodes"] == []
    assert doc["gene_and_pathway_evidence_are_never_merged"] is True


def test_the_pathway_contract_is_a_consumer_proposal_not_frozen():
    """Stage 2 owns this document. Stage 3 proposes; it does not freeze."""
    assert pathways.PATHWAY_SCHEMA == "spot.stage02_pathway_hypotheses.v1"
    assert pathways.PATHWAY_CONTRACT_STATUS == (
        "consumer_proposal_pending_stage2_owner_agreement")
    assert pathways.NOT_EVALUATED["pathway_contract_status"] == (
        "consumer_proposal_pending_stage2_owner_agreement")


# --------------------------------------------------------------------------- #
# Admission: bound to THIS run; each node states its own direction.
# --------------------------------------------------------------------------- #
def test_pathway_document_must_bind_this_direct_run(loaded_direct):
    doc = _doc(loaded_direct, [_node(CTLA4, "away_from_A", "decrease", [IL2RA])])

    admitted = pathways.admit(doc, artifact_class="analysis", direct=loaded_direct)
    assert admitted["ref"]["pathway_lane"] == "evaluated"
    assert len(admitted["levers"]) == 1

    with pytest.raises(pathways.PathwayError, match="different question"):
        pathways.admit(dict(doc, direct_run_id="0000000000000000"),
                       artifact_class="analysis", direct=loaded_direct)
    with pytest.raises(pathways.PathwayError, match="binding hash"):
        pathways.admit(dict(doc, direct_run_binding_sha256="0" * 64),
                       artifact_class="analysis", direct=loaded_direct)


def test_a_node_must_state_its_own_direction(loaded_direct):
    """A node never inherits a direction from its pathway or its siblings."""
    bad = _doc(loaded_direct, [_node(CTLA4, "away_from_A", "decrease", [IL2RA])])
    del bad["pathways"][0]["nodes"][0]["desired_target_modulation"]
    with pytest.raises(pathways.PathwayError, match="never inherits a direction"):
        pathways.admit(bad, artifact_class="analysis", direct=loaded_direct)

    # Two nodes in ONE pathway may want OPPOSITE directions. They are not equivalent,
    # and neither one's direction leaks into the other.
    mixed = _doc(loaded_direct, [
        _node(CTLA4, "away_from_A", "decrease", [IL2RA]),
        _node(IL2RA, "away_from_A", "increase", [CTLA4]),
    ])
    admitted = pathways.admit(mixed, artifact_class="analysis", direct=loaded_direct)
    by_gene = {lever["target_ensembl"]: lever for lever in admitted["levers"]}
    assert by_gene[CTLA4]["arm_desired_target_modulation"] == "decrease"
    assert by_gene[IL2RA]["arm_desired_target_modulation"] == "increase"

    # A node belongs to ONE arm, and must be an accession, not a symbol.
    with pytest.raises(pathways.PathwayError, match="desired_arm"):
        pathways.admit(_doc(loaded_direct, [_node(CTLA4, "both", "decrease", [IL2RA])]),
                       artifact_class="analysis", direct=loaded_direct)
    with pytest.raises(pathways.PathwayError, match="Ensembl"):
        pathways.admit(
            _doc(loaded_direct, [_node("CTLA4", "away_from_A", "decrease", [IL2RA])]),
            artifact_class="analysis", direct=loaded_direct)


def test_a_node_must_cite_a_real_contributing_perturbation(loaded_direct):
    """A node no measured perturbation supports is a guess, and is barred from edges."""
    orphan = _doc(loaded_direct,
                  [_node(CTLA4, "away_from_A", "decrease", ["ENSG09999999999"])])
    admitted = pathways.admit(orphan, artifact_class="analysis", direct=loaded_direct)

    lever = admitted["levers"][0]
    assert lever["contributing_perturbations"] == []
    assert lever["gene_target_drug_edge_permitted"] is False
    assert any(d["state"] == "no_contributing_perturbation"
               for d in admitted["dispositions"])

    # A valid citation is bound to the MEASURED arm lever, by id.
    ok = _doc(loaded_direct, [_node(CTLA4, "away_from_A", "decrease", [IL2RA])])
    lever = pathways.admit(ok, artifact_class="analysis",
                           direct=loaded_direct)["levers"][0]
    cite = lever["contributing_perturbations"][0]
    assert cite["contributing_perturbation_id"]
    assert cite["perturbed_target_ensembl"] == IL2RA
    assert cite["desired_arm"] == "away_from_A"
    assert cite["arm_rank"] is not None and cite["arm_evidence_tier"]


# --------------------------------------------------------------------------- #
# A node is never a measurement.
# --------------------------------------------------------------------------- #
def test_a_pathway_node_is_never_an_observed_perturbation(loaded_direct,
                                                          analysis_cache):
    """The same real inhibitor: OBSERVED on the measured gene, only a HYPOTHESIS on the
    very same gene when it arrives as an inferred pathway node."""
    doc = _doc(loaded_direct, [_node(CTLA4, "away_from_A", "decrease", [IL2RA])])
    paths = pathways.admit(doc, artifact_class="analysis", direct=loaded_direct)

    acquired = acquisition.load_manifest(analysis_cache, "analysis",
                                         direct=loaded_direct)
    built = run_stage3.build(artifact_class="analysis", direct=loaded_direct,
                             acquired=acquired, pathway_hypotheses=paths)

    edges = [e for e in built["tables"]["target_drug_edges"]
             if e["target_ensembl"] == CTLA4 and e["desired_arm"] == "away_from_A"
             and e["lane"] == "direct_gene_mechanism"]
    by_origin: dict[str, set[str]] = {}
    for edge in edges:
        by_origin.setdefault(edge["origin_type"], set()).add(
            edge["directional_evidence_status"])

    # CTLA4 is BOTH a measured direct target and an inferred pathway node here, so the
    # SAME drug/target/arm yields TWO edges that must not merge.
    assert set(by_origin) == {ORIGIN_DIRECT_TARGET, ORIGIN_PATHWAY_NODE}
    assert wf.OBSERVED_PERTURBATION in by_origin[ORIGIN_DIRECT_TARGET]
    assert wf.PATHWAY_HYPOTHESIS in by_origin[ORIGIN_PATHWAY_NODE]
    assert wf.OBSERVED_PERTURBATION not in by_origin[ORIGIN_PATHWAY_NODE]

    for edge in edges:
        if edge["origin_type"] == ORIGIN_PATHWAY_NODE:
            assert edge["observed_perturbation_support"] is False
            assert edge["arm_rank"] is None       # a node has no measured rank
        else:
            assert edge["arm_rank"] is not None

    # Counts stay apart: a node never adds to a measured target's tally.
    per_arm = built["counts"]["per_arm"]["away_from_A"]
    assert per_arm[ORIGIN_DIRECT_TARGET]["n_observed_perturbation"] > 0
    assert per_arm[ORIGIN_PATHWAY_NODE]["n_observed_perturbation"] == 0
    assert per_arm[ORIGIN_PATHWAY_NODE]["n_pathway_hypothesis"] > 0

    # The candidate keeps the two apart.
    cand = next(c for c in built["tables"]["candidates"]
                if CTLA4 in c["target_ensembls"])
    states = {(s["desired_arm"], s["origin_type"]): s["arm_evidence_state"]
              for s in cand["arm_evidence_states"]}
    assert states[("away_from_A", ORIGIN_DIRECT_TARGET)] == wf.OBSERVED_PERTURBATION
    assert states[("away_from_A", ORIGIN_PATHWAY_NODE)] == wf.PATHWAY_HYPOTHESIS
    assert "away_from_A" in cand["observed_perturbation_arms"]
    assert "away_from_A" in cand["pathway_hypothesis_arms"]

    # A pathway hypothesis IS worth a Stage-4 look — and saying so is not evidence.
    assert cand["stage4_assessment_status"] == wf.QUEUED


def test_duplicate_pathway_node_key_is_refused(loaded_direct):
    dup = _doc(loaded_direct, [
        _node(CTLA4, "away_from_A", "decrease", [IL2RA]),
        _node(CTLA4, "away_from_A", "increase", [IL2RA]),   # same (pathway, gene, arm)
    ])
    with pytest.raises(pathways.PathwayError, match="duplicate immutable"):
        pathways.admit(dup, artifact_class="analysis", direct=loaded_direct)

    # The same gene in TWO pathways is fine: the pathway is part of the key, and BOTH
    # rows are retained rather than one silently winning.
    two = copy.deepcopy(_doc(loaded_direct,
                             [_node(CTLA4, "away_from_A", "decrease", [IL2RA])]))
    second = copy.deepcopy(two["pathways"][0])
    second["pathway_id"] = "GO:0002376"
    two["pathways"].append(second)
    admitted = pathways.admit(two, artifact_class="analysis", direct=loaded_direct)
    assert len(admitted["levers"]) == 2
    assert {lever["pathway_id"] for lever in admitted["levers"]} == {
        "GO:0042110", "GO:0002376"}
