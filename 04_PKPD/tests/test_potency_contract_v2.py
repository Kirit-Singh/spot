"""Potency: the relation, the exact source string, and the assay it was measured in.

The audit: `PotencyRecord` had value / binding-state / assay / context, but no structured
activity, assay, target or document id, no relation, no confidence and no validity comment.
"Hiding those in free text would make independent reconstruction weak."

Two rules carry the science here.

`relation` — ChEMBL records `IC50 > 10000 nM` as often as `IC50 = 47 nM`. A ">" is a
statement that the assay *ran out of range*, not a measurement. Reading its magnitude as a
point estimate turns "we could not reach the effect" into "the effect happens at 10 uM".

`metric` — MEC, IC50, IC90, EC50 and Ki stay DISTINCT and no transform between them is
supplied. Deriving an MEC from an IC50 needs an unbound fraction and a declared PD model.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from analysis.assay_records import AssayBinding, Relation
from analysis.evidence_records import PotencyRecord, Provenance

SHA = "d" * 64


def _prov() -> Provenance:
    return Provenance(
        source_record_id="src.chembl.act.1",
        source_url="https://www.ebi.ac.uk/chembl/api/data/activity/1.json",
        access_date="2026-07-13",
        release_version="ChEMBL_37",
        raw_response_sha256=SHA,
        extraction_transform="$.activities[0].standard_value",
    )


def _binding(**over) -> AssayBinding:
    base = dict(
        activity_id="CHEMBL_ACT_18904231",
        assay_id="CHEMBL_ASSAY_688343",
        assay_type="F",
        assay_description="Inhibition of human CDK4/cyclin D1 in a cell-free kinase assay",
        experimental_system="cell_free_kinase_assay",
        target_id="CHEMBL301",
        target_organism="Homo sapiens",
        target_uniprot_accession="P11802",
        document_id="CHEMBL_DOC_1148306",
        confidence_score=9,
        validity_comment=None,
    )
    base.update(over)
    return AssayBinding(**base)


def _potency(**over) -> PotencyRecord:
    base = dict(
        potency_id="pot.1",
        candidate_id="cand.1",
        active_moiety_id="moiety.1",
        metric="MEC",
        value_source_string="47",
        units="nM",
        binding_state="free",
        assay="cell-free kinase assay",
        biological_context="GBM",
        evidence_type="in_vitro",
        provenance=_prov(),
    )
    base.update(over)
    return PotencyRecord(**base)


# --------------------------------------------------------- v1 rows keep working (req 7)

def test_a_v1_potency_row_without_an_assay_binding_still_validates():
    """The v1 contract is not broken by the v2 extension — it is superseded by it."""
    p = _potency()
    assert p.assay_binding is None


def test_relation_defaults_to_equality_which_is_the_v1_reading():
    """A v1 row carried a bare magnitude, and the engine read it as a point estimate. The
    default must therefore BE equality, or v1 rows would silently change meaning."""
    assert _potency().relation is Relation.EQ


# ------------------------------------------------------------------------ the relation

def test_a_potency_carries_its_relation_and_its_exact_source_string():
    p = _potency(relation=Relation.GT, value_source_string="10000", units="nM")
    assert p.relation is Relation.GT
    assert p.value_source_string == "10000"


def test_the_relation_vocabulary_is_exactly_the_six_a_source_can_state():
    assert {r.value for r in Relation} == {"=", "<", ">", "<=", ">=", "~"}


def test_a_greater_than_potency_is_not_a_point_estimate():
    """`IC50 > 10 uM` means the assay ran out of range. It is not the sentence
    `IC50 = 10 uM`, and `is_point_estimate` is what stops the margin code from reading it
    as one."""
    assert _potency(relation=Relation.EQ).is_point_estimate is True
    assert _potency(relation=Relation.GT).is_point_estimate is False
    assert _potency(relation=Relation.LT).is_point_estimate is False
    assert _potency(relation=Relation.APPROX).is_point_estimate is False


# -------------------------------------------------------------- the metrics stay apart

def test_mec_ic50_ic90_ec50_and_ki_are_distinct_metrics():
    assert set(PotencyRecord.model_fields["metric"].annotation.__args__) == {
        "MEC", "IC50", "IC90", "EC50", "Ki", "target_concentration",
    }


def test_an_ic50_cannot_be_relabelled_an_mec_by_carrying_a_richer_assay_binding():
    """A complete ChEMBL activity record makes an IC50 better DOCUMENTED. It does not make
    it a minimum effective concentration."""
    p = _potency(metric="IC50", assay_binding=_binding())
    assert p.metric == "IC50"
    assert p.is_target_concentration is False
    assert _potency(metric="MEC").is_target_concentration is True
    assert _potency(metric="target_concentration").is_target_concentration is True


# -------------------------------------------------------------------- the assay binding

def test_an_assay_binding_carries_activity_assay_target_and_document_ids():
    b = _binding()
    assert (b.activity_id, b.assay_id, b.target_id, b.document_id) == (
        "CHEMBL_ACT_18904231", "CHEMBL_ASSAY_688343", "CHEMBL301", "CHEMBL_DOC_1148306")


def test_the_assay_binding_carries_type_system_and_organism():
    b = _binding()
    assert b.assay_type == "F"
    assert b.experimental_system == "cell_free_kinase_assay"
    assert b.target_organism == "Homo sapiens"


def test_a_validity_comment_is_preserved_not_dropped():
    """ChEMBL flags 'Potential author error' / 'Outside typical range' on activities. A
    curator's doubt about a number travels WITH the number or it is lost."""
    b = _binding(validity_comment="Outside typical range")
    assert b.validity_comment == "Outside typical range"


def test_confidence_is_the_sources_curation_score_and_is_bounded_as_the_source_bounds_it():
    """ChEMBL target confidence is 0-9. This is a SOURCE-REPORTED curation field, never a
    spot-computed score."""
    assert _binding(confidence_score=0).confidence_score == 0
    assert _binding(confidence_score=9).confidence_score == 9
    with pytest.raises(ValidationError):
        _binding(confidence_score=10)
    with pytest.raises(ValidationError):
        _binding(confidence_score=-1)


def test_an_assay_binding_with_no_target_organism_is_refused():
    """A Ki against the MOUSE orthologue is not a Ki against the human target, and the
    audit is explicit that species differences matter."""
    with pytest.raises(ValidationError):
        _binding(target_organism="")


def test_a_potency_may_carry_its_assay_binding():
    p = _potency(assay_binding=_binding())
    assert p.assay_binding is not None
    assert p.assay_binding.activity_id == "CHEMBL_ACT_18904231"
