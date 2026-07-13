"""The v2 pathway bridge: a direction is NEVER inherited from membership or enrichment.

These test the deterministic rules only. The end-to-end fixtures wait on W18/W4's pathway
arm contract being admitted — but the rules do not, because the rules are what the fixtures
will be checked AGAINST. Writing them after the fixture would let the fixture decide what is
true.

The defect this whole module exists to prevent is quiet and plausible: a gene sits in a set
that is enriched for "decrease", so it inherits "decrease", so it becomes direction-COMPATIBLE,
so a drug that inhibits it sorts above a drug backed by an actual measurement. Every step
reads reasonably. The result is guilt by association wearing the costume of a measurement.
"""
from __future__ import annotations

import pytest

from druglink import join_semantics as js
from druglink import pathway_bridge as pb

MEASURED = {"ENSG00000163599"}          # CTLA4 — really perturbed
UNMEASURED = "ENSG00000134460"          # in the set, nobody touched it


def _node(**over):
    node = {"target_id": UNMEASURED, "target_id_namespace": "ensembl",
            "set_id": "GO:0042110", "membership_source": "GO-BP",
            "membership_sha256": "b" * 64}
    node.update(over)
    return node


def _sourced(**over):
    """An unmeasured node that brought its OWN source-backed direction, with the bytes."""
    return _node(desired_target_modulation="supports_target_inhibition",
                 modulation_source_id="chembl:mechanism",
                 modulation_evidence_locator="CHEMBL1778/mechanism",
                 modulation_evidence_sha256="c" * 64, **over)


# --------------------------------------------------------------------------- #
# The two evidence classes stay apart.
# --------------------------------------------------------------------------- #
def test_a_measured_target_is_a_lever_and_an_unmeasured_member_is_not():
    measured = pb.classify(_node(target_id="ENSG00000163599"),
                           measured_target_ids=MEASURED)
    inferred = pb.classify(_node(), measured_target_ids=MEASURED)

    assert measured == pb.MEASURED_LEVER
    assert inferred == pb.PATHWAY_CONTEXT
    assert measured in pb.MEASURED_CLASSES
    assert inferred in pb.INFERRED_CLASSES
    assert not (pb.MEASURED_CLASSES & pb.INFERRED_CLASSES), "the classes must not overlap"


def test_membership_in_an_enriched_set_does_not_promote_a_node_to_measured():
    """The whole point. Being in a strongly enriched set is not being perturbed."""
    node = _node(enrichment_value=9.9, leading_edge=True, peak_rank=1)
    assert pb.classify(node, measured_target_ids=MEASURED) != pb.MEASURED_LEVER


# --------------------------------------------------------------------------- #
# A direction is never inherited.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("claim", sorted(pb.INHERITED_DIRECTION_CLAIMS))
def test_every_inherited_direction_claim_is_refused_by_name(claim):
    node = _node(**{claim: "decrease"})
    with pytest.raises(pb.PathwayBridgeError, match="INHERITED direction"):
        pb.classify(node, measured_target_ids=MEASURED)


def test_there_is_no_direction_provenance_meaning_inherited():
    """The refusal cannot be routed around, because no such provenance exists to route to."""
    for prov in pb.DIRECTION_PROVENANCES:
        assert "pathway" not in prov and "enrich" not in prov and "member" not in prov
    assert set(pb.DIRECTION_PROVENANCES) == {pb.DIRECTION_FROM_OWN_ARM,
                                             pb.DIRECTION_FROM_OWN_SOURCE}


# --------------------------------------------------------------------------- #
# Direction resolution — three outcomes, and only three.
# --------------------------------------------------------------------------- #
def test_a_measured_lever_keeps_ITS_OWN_arm_direction():
    got = pb.resolve_direction(_node(target_id="ENSG00000163599"),
                               node_class=pb.MEASURED_LEVER,
                               measured_modulation="supports_target_inhibition")
    assert got["desired_target_modulation"] == "supports_target_inhibition"
    assert got["direction_provenance"] == pb.DIRECTION_FROM_OWN_ARM
    assert got["may_improve_drug_ordering"] is True


def test_stage3_will_not_invent_a_direction_for_a_measured_lever():
    with pytest.raises(pb.PathwayBridgeError, match="no arm modulation"):
        pb.resolve_direction(_node(target_id="ENSG00000163599"),
                             node_class=pb.MEASURED_LEVER, measured_modulation=None)


def test_an_unmeasured_node_with_no_direction_of_its_own_is_direction_unresolved():
    got = pb.resolve_direction(_node(), node_class=pb.PATHWAY_CONTEXT)
    assert got["desired_target_modulation"] == pb.DIRECTION_UNRESOLVED
    assert got["direction_is_compatible"] is False
    assert got["may_improve_drug_ordering"] is False
    assert "never inherited" in got["direction_unresolved_reason"]


def test_an_unmeasured_node_WITH_its_own_source_backed_direction_is_compatible():
    got = pb.resolve_direction(_sourced(), node_class=pb.PATHWAY_CONTEXT)
    assert got["desired_target_modulation"] == "supports_target_inhibition"
    assert got["direction_provenance"] == pb.DIRECTION_FROM_OWN_SOURCE
    assert got["may_improve_drug_ordering"] is True
    # ...and it had to bring the bytes.
    assert got["modulation_evidence_sha256"] == "c" * 64


@pytest.mark.parametrize("drop", sorted(pb.REQUIRED_SOURCE_DIRECTION))
def test_a_source_backed_direction_missing_ANY_of_its_evidence_falls_back_to_unresolved(drop):
    """A locator without a hash, or a hash without a locator, is not a binding."""
    node = _sourced()
    node.pop(drop)
    got = pb.resolve_direction(node, node_class=pb.PATHWAY_CONTEXT)
    assert got["desired_target_modulation"] == pb.DIRECTION_UNRESOLVED
    assert got["may_improve_drug_ordering"] is False


# --------------------------------------------------------------------------- #
# An unresolved node is INERT. This is the one that protects the ordering.
# --------------------------------------------------------------------------- #
def test_a_direction_unresolved_node_contributes_exactly_zero_to_drug_ordering():
    unresolved = pb.resolve_direction(_node(), node_class=pb.PATHWAY_CONTEXT)
    assert pb.ordering_contribution(unresolved) == 0.0, (
        "an unresolved node must not improve drug ordering — not by a small weight, not "
        "as a tie-break, not at all")

    resolved = pb.resolve_direction(_sourced(), node_class=pb.PATHWAY_CONTEXT)
    assert pb.ordering_contribution(resolved) == 1.0


# --------------------------------------------------------------------------- #
# Bindings.
# --------------------------------------------------------------------------- #
def test_a_pathway_record_missing_any_binding_is_refused():
    full = {k: "x" for k in pb.REQUIRED_PATHWAY_BINDINGS}
    pb.require_bindings(full)                       # complete -> admitted
    for k in pb.REQUIRED_PATHWAY_BINDINGS:
        partial = dict(full)
        partial[k] = None
        with pytest.raises(pb.PathwayBridgeError, match="missing bindings"):
            pb.require_bindings(partial)


# --------------------------------------------------------------------------- #
# Admission: independent verifier, and no cross-time pathway statistic.
# --------------------------------------------------------------------------- #
def _bundle(**over):
    """A pathway bundle whose admission actually BINDS it (audit 0ec6ec99, B4).

    A verifier NAME is not an admission: the gate now requires a verdict, the bundle's own
    digest, the producer commit and an addressable report. Anyone can type the word
    "independent" into a string field.
    """
    from druglink.arm_query import bundle_digest
    b = {"schema_version": pb.PATHWAY_ARM_BUNDLE_SCHEMA}
    b.update(over)
    ref = b.get("verification_ref")
    if ref is None:
        payload = {k: v for k, v in b.items() if k != "verification_ref"}
        b["verification_ref"] = {
            "verifier_id": "spot.stage02.pathway.arm.independent_verifier.v1",
            "verdict": "admit", "bundle_sha256": bundle_digest(payload),
            "producer_commit": "abc1234", "report_sha256": "d" * 64}
    return b


def test_an_admitted_bundle_passes():
    pb.require_admitted_bundle(_bundle())


def test_a_self_verified_bundle_is_refused():
    """B6 / M4b / the temporal lane, a third time: self-verification proves nothing.

    Fully bound, so the ONLY thing wrong is the verifier's identity — otherwise this would
    pass at the unbound-name gate and prove nothing about self-verification.
    """
    from druglink.arm_query import bundle_digest
    payload = {"schema_version": pb.PATHWAY_ARM_BUNDLE_SCHEMA}
    bad = dict(payload)
    bad["verification_ref"] = {
        "verifier_id": "spot.stage02.pathway.verifier.v1",       # NOT independent
        "verdict": "admit", "bundle_sha256": bundle_digest(payload),
        "producer_commit": "abc1234", "report_sha256": "d" * 64}
    with pytest.raises(pb.PathwayBridgeError, match="not an INDEPENDENT verifier"):
        pb.require_admitted_bundle(bad)


def test_an_unverified_bundle_is_refused():
    with pytest.raises(pb.PathwayBridgeError, match="unbound_name"):
        pb.require_admitted_bundle(_bundle(verification_ref={}))


def test_a_verifier_NAME_alone_is_not_an_admission():
    """The audit's exact probe (0ec6ec99, B4): a friendly word in a string field."""
    bad = _bundle(verification_ref={"verifier_id": "totally_independent_but_unbound"})
    with pytest.raises(pb.PathwayBridgeError, match="unbound_name"):
        pb.require_admitted_bundle(bad)


def test_a_bundle_carrying_a_cross_time_pathway_statistic_is_refused_at_any_depth():
    bad = _bundle(sets=[{"set_id": "GO:1", "stats": {"temporal_enrichment": 2.0}}])
    with pytest.raises(js.JoinSemanticsError, match="ACROSS TIME"):
        pb.require_admitted_bundle(bad)


# --------------------------------------------------------------------------- #
# Cross-time endpoints are ENDPOINT CONTEXT, never temporal enrichment.
# --------------------------------------------------------------------------- #
def test_cross_time_panels_are_endpoint_contexts_A_at_from_and_B_at_to():
    ctx = pb.endpoint_context(js.TEMPORAL_CROSS_CONDITION,
                              from_condition="Rest", to_condition="Stim48hr")
    assert ctx["pathway_context_type"] == js.ENDPOINT_PATHWAY_CONTEXT
    assert ctx["arm_A_endpoint_condition"] == "Rest"
    assert ctx["arm_B_endpoint_condition"] == "Stim48hr"
    assert ctx["endpoints_are_within_condition_readings"] is True
    assert ctx["is_temporal_enrichment"] is False
    assert ctx["is_longitudinal_statistic"] is False


def test_a_cross_time_panel_missing_an_endpoint_is_refused():
    with pytest.raises(pb.PathwayBridgeError, match="BOTH endpoints"):
        pb.endpoint_context(js.TEMPORAL_CROSS_CONDITION, from_condition="Rest")


def test_a_same_time_panel_is_condition_matched_not_endpoint():
    ctx = pb.endpoint_context(js.WITHIN_CONDITION)
    assert ctx["pathway_context_type"] == js.PATHWAY_CONTEXT[js.WITHIN_CONDITION]
    assert "arm_A_endpoint_condition" not in ctx
