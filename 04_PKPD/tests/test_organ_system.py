"""organ_system in the v2 contract: source-backed or `unspecified`, and never a classifier.

The extractor and its evidence shape belong to ACQUISITION (`analysis/organ_system.py`). This
file tests the half W9 owns: that the v2 SCHEMA carries acquisition's fields faithfully, that
the v2 PROFILE refuses a value with no source behind it, and — the rule that actually protects
the science — that an absent or incomplete organ system changes no other lane.

Why that last one matters: an organ system is a LABEL on a finding. The moment a missing one
could downgrade a candidate, "unspecified" would stop being an honest answer and start being a
penalty, and the pressure to fill it in by inference would be irresistible. So it must be inert,
and inertness is a property you test rather than promise.
"""

from __future__ import annotations

import pytest

from analysis.contract_profile import CONTROLLED_ORGAN_SYSTEMS, contract_violations
from analysis.firewall import Rejection
from analysis.organ_system import (
    UNSPECIFIED,
    LabelRef,
    OrganSystemEvidence,
    extract_organ_system,
    refuse_inferred_organ_system,
)
from analysis.safety_records import EvidenceState, SafetyEvidenceRecord

import fixtures as fx


# --------------------------------------------------------------- the controlled vocabulary

def test_the_controlled_vocabulary_is_the_one_the_brief_asked_for():
    assert CONTROLLED_ORGAN_SYSTEMS == {
        "immune_infectious", "hematologic", "cardiovascular", "hepatic", "renal", "neurologic",
        "pulmonary", "gastrointestinal", "endocrine_metabolic", "reproductive", "dermatologic",
        "ocular", "musculoskeletal", "other", "unspecified",
    }


def test_a_controlled_value_outside_the_vocabulary_is_refused():
    inputs = fx.stage4_inputs_v2()
    r = inputs.safety_records[0]
    inputs.safety_records[0] = r.model_copy(update={
        "organ_system_evidence": OrganSystemEvidence(
            organ_system="bone_marrow_ish", value_kind="controlled_value",
            evidence_state="observed", source_key="dailymed",
            source_record_id="src.fixture.label.dailymed", setid="S1", label_version="1",
            raw_response_sha256=None, locator="section 34071-1")})
    codes = {v.code for v in contract_violations(inputs)}
    assert "organ_system_outside_controlled_vocabulary" in codes


def test_a_source_term_is_carried_verbatim_and_not_normalised_into_the_vocabulary():
    """"Nervous system disorders" is what the source said. Mapping it to `neurologic` here
    would be a classifier — the very thing acquisition refuses to be — and the mapping would be
    invisible in the artifact."""
    inputs = fx.stage4_inputs_v2()
    r = inputs.safety_records[0]
    inputs.safety_records[0] = r.model_copy(update={
        "organ_system_evidence": OrganSystemEvidence(
            organ_system="Nervous system disorders", value_kind="source_term",
            evidence_state="observed", source_key="dailymed",
            source_record_id="src.fixture.label.dailymed", setid="S1", label_version="1",
            raw_response_sha256=None, locator="reactions.soc")})
    assert contract_violations(inputs) == []
    assert inputs.safety_records[0].organ_system == "Nervous system disorders"


# ------------------------------------------------------------------------ never inferred

@pytest.mark.parametrize("hint", ["target CTLA4", "anti-PD-1 drug class",
                                  "gene expression in microglia", "the mechanism"])
def test_classifying_from_biology_raises_rather_than_being_available(hint):
    with pytest.raises(Rejection) as exc:
        refuse_inferred_organ_system(hint)
    assert exc.value.code == "organ_system_inference_refused"


def test_an_absent_source_field_yields_unspecified_and_still_says_where_it_looked():
    """The distinction that makes `unspecified` trustworthy: it is not silence. The record still
    carries the bytes and the source it checked, so "unspecified" cannot be read as "never
    checked"."""
    e = extract_organ_system(
        LabelRef(source_record_id="src.dailymed.x", setid="S1", label_version="40",
                 raw_response_sha256="a" * 64, structured={}),
        source_key="dailymed")
    assert e.organ_system == UNSPECIFIED
    assert e.evidence_state == "not_evaluated"
    assert e.source_record_id == "src.dailymed.x"
    assert e.raw_response_sha256 == "a" * 64
    assert e.reason


def test_an_organ_system_that_was_not_observed_cannot_be_asserted_on_a_row():
    with pytest.raises(Exception):
        SafetyEvidenceRecord(
            evidence_id="SAF-X", candidate_id="C1", active_moiety_id="M1",
            evidence_state=EvidenceState.LABEL_SUPPORTED,
            organ_system_evidence=OrganSystemEvidence(
                organ_system="hematologic", value_kind="controlled_value",
                evidence_state="not_evaluated",  # nobody observed it
                source_key="dailymed", source_record_id="src.x", setid=None,
                label_version=None, raw_response_sha256=None, locator="l"))


def test_unknown_stays_unspecified_on_a_row_with_no_classification():
    r = SafetyEvidenceRecord(evidence_id="SAF-1", candidate_id="C1", active_moiety_id="M1",
                             evidence_state=EvidenceState.NOT_EVALUATED)
    assert r.organ_system_evidence is None
    assert r.organ_system == UNSPECIFIED


# ------------------------------------- an incomplete category changes nothing else (the rule)

def test_organ_system_is_inert_removing_it_changes_no_other_lane():
    """The load-bearing test.

    Run the whole engine twice — once with every organ-system classification present, once with
    all of them stripped — and require every other lane to be identical: CNS-MPO, exposure
    margins, NEBPI classes, transporter observations, delivery, production eligibility. If an
    absent organ system could move any of them, `unspecified` would be a penalty rather than an
    honest answer, and the pressure to fill it in by inference would be irresistible.
    """
    from analysis.method_config import load_method_bundle
    from analysis.contract_version import ContractVersion
    from analysis.pipeline import run_pipeline

    method = load_method_bundle(version=ContractVersion.V2)

    with_organ = fx.stage4_inputs_v2()
    without = fx.stage4_inputs_v2()
    without.safety_records = [r.model_copy(update={"organ_system_evidence": None})
                              for r in without.safety_records]

    a = run_pipeline(with_organ, method)
    b = run_pipeline(without, method)

    # The SAFETY lane legitimately differs (that is where the field lives). Every OTHER
    # lane must be untouched.
    assert [c.candidate_id for c in a.candidates] == [c.candidate_id for c in b.candidates]
    for ca, cb in zip(a.candidates, b.candidates):
        assert ca.cns_mpo.status == cb.cns_mpo.status
        assert ca.cns_mpo.total_published == cb.cns_mpo.total_published
        assert [(m.measurement_id, r.status, r.margin_canonical_decimal)
                for m, r in ca.exposure] == [
            (m.measurement_id, r.status, r.margin_canonical_decimal) for m, r in cb.exposure]
        assert [(n.context_id, n.nebpi_class, n.nebpi_status) for n in ca.nebpi] == [
            (n.context_id, n.nebpi_class, n.nebpi_status) for n in cb.nebpi]
        assert ca.transporters == cb.transporters
        assert ca.delivery == cb.delivery
        assert ca.production_eligible == cb.production_eligible
        assert ca.eligibility_reason_code == cb.eligibility_reason_code


def test_a_missing_organ_system_does_not_make_a_v2_bundle_incomplete():
    """`unspecified` is what every real extraction returns today (no ledgered source carries the
    field). If that failed the v2 profile, no real bundle could ever be acquisition-complete."""
    inputs = fx.stage4_inputs_v2()
    inputs.safety_records = [r.model_copy(update={"organ_system_evidence": None})
                             for r in inputs.safety_records]
    assert contract_violations(inputs) == []


# ------------------------------------------------------- no p/q, no score, no 'safe' flag

def test_the_v2_forbidden_field_names_are_actually_enforced_not_merely_declared():
    """A forbidden-name list nothing reads is a comment.

    p/q values imply a hypothesis test this stage does not run; an organ-system score would
    recreate the single combined clinical verdict the whole taxonomy exists to prevent.
    """
    from analysis.contract_version import ContractVersion
    from analysis.method_config import load_method_bundle
    from analysis.safety import assert_no_forbidden_fields

    method = load_method_bundle(version=ContractVersion.V2)
    forbidden = set(method.forbidden_fields)

    for name in ("p_value", "q_value", "fdr", "organ_system_score", "toxicity_score",
                 "is_safe", "composite_score", "clinical_recommendation"):
        assert name in forbidden, f"{name} is not enforced"

    for name in ("p_value", "q_value", "organ_system_score"):
        with pytest.raises(Exception):
            assert_no_forbidden_fields({"lanes": {name: 0.01}}, method.forbidden_fields, "test")
