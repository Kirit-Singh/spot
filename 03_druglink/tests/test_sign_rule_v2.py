"""THE SIGN RULE: the four sign cases, the agonist that must never rank, and the regression that the modality-fixed rule can never return."""
from __future__ import annotations

import pytest

from druglink import modality_v2 as mv2
from druglink import stage2_aggregate as sa
from sign_fixture_v2 import (
    CRISPRA,
    CRISPRI,
    MEASURED_LANES,
    aggregate,
    arm,
    by_action,
    edges_for,
    load_store,
    pick_drug_known,
    typed_row,
)

@pytest.fixture(scope="module")
def store():
    return load_store()


@pytest.fixture(scope="module")
def drug_known(store):
    return pick_drug_known(store)


# =========================================================================== #
# 1. THE FOUR SIGN CASES, on every MEASURED lane. Each a NAMED outcome.
# =========================================================================== #
@pytest.mark.parametrize("lane", MEASURED_LANES)
def test_a_POSITIVE_row_matches_inhibitors_and_is_RANKABLE_AS_SUPPORTED(store, drug_known, lane):
    edges = edges_for(store, [arm(lane, [typed_row(drug_known, arm_value=1.5)])])
    inhibitors = by_action(edges, "INHIBITOR")
    assert inhibitors, "NON-VACUITY: the positive row must actually produce inhibitor edges"

    for edge in inhibitors:
        assert edge["observed_sign_state"] == mv2.SIGN_SUPPORTS_DESIRED_CHANGE
        assert edge["desired_target_modulation"] == mv2.MOD_DECREASE
        assert edge["directional_evidence_status"] == "observed_perturbation"
        assert edge["observed_perturbation_support"] is True      # RANKABLE AS SUPPORTED
        assert edge["mechanism_phenocopies_modality"] is True
        assert edge["evidence_relation"] == "putative_crispri_phenocopy"
        assert edge["observed_compatible_action"] == mv2.ACTION_INHIBIT
        assert edge["untested_inverse_action"] is None


@pytest.mark.parametrize("lane", MEASURED_LANES)
def test_a_NEGATIVE_row_flags_the_INHIBITOR_OPPOSED_and_does_not_drop_it(store, drug_known, lane):
    """The inhibitor DOES phenocopy the knockdown — and on this row the knockdown HARMED the arm.

    So it is OPPOSED, it is KEPT, it names its reason, and it never ranks. Under the retired
    modality-fixed rule this exact edge was `observed_perturbation` with support=True.
    """
    edges = edges_for(store, [arm(lane, [typed_row(drug_known, arm_value=-1.5)])])
    inhibitors = by_action(edges, "INHIBITOR")
    assert inhibitors, "NON-VACUITY: the negative row must still EMIT the inhibitor edges"

    for edge in inhibitors:
        assert edge["observed_sign_state"] == mv2.SIGN_OPPOSES_DESIRED_CHANGE
        assert edge["directional_evidence_status"] == "opposed"          # NOT dropped
        assert edge["mechanism_match_status"] == mv2.MATCH_PHENOCOPIES_UNDESIRED
        assert edge["observed_perturbation_support"] is False            # NOT supported
        assert edge["stage3_evidence_class"] != "measured_perturbation"
        # It phenocopies the perturbation — that is exactly WHY it is opposed here.
        assert edge["mechanism_phenocopies_modality"] is True
        # The screen supports NO action on this target. It does not support the inverse either.
        assert edge["observed_compatible_action"] is None
        assert edge["untested_inverse_action"] == mv2.ACTION_ACTIVATE
        assert edge["pharmacologic_reversibility_assumed"] is False


@pytest.mark.parametrize("lane", MEASURED_LANES)
def test_a_ZERO_row_is_no_directional_response_and_SAYS_SO(store, drug_known, lane):
    edges = edges_for(store, [arm(lane, [typed_row(drug_known, arm_value=0.0)])])
    assert edges, "NON-VACUITY: the zero row still emits edges — it is not a silence"
    for edge in edges:
        assert edge["observed_sign_state"] == mv2.SIGN_NO_DIRECTIONAL_RESPONSE
        assert edge["desired_target_modulation"] == mv2.MOD_NO_DIRECTION      # STATED
        assert edge["directional_evidence_status"] == "unresolved"
        assert edge["observed_perturbation_support"] is False


@pytest.mark.parametrize("lane", MEASURED_LANES)
def test_a_NON_EVALUABLE_row_is_not_evaluable_and_SAYS_SO(store, drug_known, lane):
    edges = edges_for(store, [arm(lane, [typed_row(drug_known, arm_value=None,
                                                   evaluable=False, rank=None)])])
    assert edges, "NON-VACUITY: a non-evaluable row is carried, never dropped"
    for edge in edges:
        assert edge["observed_sign_state"] == mv2.SIGN_NOT_EVALUABLE
        assert edge["desired_target_modulation"] == mv2.MOD_NOT_EVALUATED     # STATED
        assert edge["directional_evidence_status"] == "unresolved"
        assert edge["observed_perturbation_support"] is False
        # A null rank is a STATE. It never became 0.
        assert edge["arm_rank"] is None
        assert edge["arm_rank_status"] == "unranked_by_source"
        assert edge["arm_value_status"] == "not_stated_by_source"


# =========================================================================== #
# 2. THE CRITICAL ONE. No agonist reaches supported evidence, at any depth.
# =========================================================================== #
@pytest.mark.parametrize("lane", MEASURED_LANES)
def test_a_NEGATIVE_row_NEVER_PROMOTES_AN_AGONIST_to_supported_evidence(store, lane):
    """An agonist NEVER phenocopies CRISPRi. On a negative row it is the UNTESTED INVERSE of a
    deleterious result — never observed support, never a measurement's class, never a phenocopy.
    """
    row = next(r for r in store.rows
               if any(d.get("action_type_source") == "AGONIST" for d in (r.get("drugs") or [])))
    target = (str(row["target_id"]), str(row["target_id_namespace"]))
    edges = edges_for(store, [arm(lane, [typed_row(target, arm_value=-2.0)])])
    agonists = by_action(edges, "AGONIST")
    assert agonists, "NON-VACUITY: the agonist edges must actually exist to prove they never rank"

    for edge in agonists:
        assert edge["directional_evidence_status"] == "inverse_direction_hypothesis"
        assert edge["observed_perturbation_support"] is False
        assert edge["stage3_evidence_class"] == "inverse_direction_hypothesis"
        assert edge["mechanism_phenocopies_modality"] is False
        # It wears the UNTESTED-INVERSE relation, never a phenocopy label.
        assert edge["evidence_relation"] == mv2.RELATION_UNTESTED_INVERSE
        assert edge["evidence_relation"] not in mv2.PHENOCOPY_RELATIONS

    # AND AT ANY DEPTH, over every table the bundle will carry.
    tables = __import__("druglink.candidates_v2", fromlist=["x"]).build(
        artifact_class="fixture", aggregate=aggregate([arm(lane, [typed_row(target,
                                                                            arm_value=-2.0)])]),
        store=store)
    assert tables["target_drug_edges"], "NON-VACUITY"
    for payload in tables.values():
        mv2.check_no_agonist_supported(payload)     # raises if one ever did


def test_the_no_agonist_walk_ACTUALLY_FIRES_on_a_forged_row():
    """The gate is not decoration: hand it the forgery and it must REFUSE."""
    forged = {"candidates": [{"nested": {"mechanism_phenocopies_modality": False,
                                         "observed_perturbation_support": True,
                                         "action_type_source": "AGONIST"}}]}
    with pytest.raises(mv2.ModalityError) as exc:
        mv2.check_no_agonist_supported(forged)
    assert exc.value.gate == mv2.GATE_NON_PHENOCOPY_IN_SUPPORTED_EVIDENCE


# =========================================================================== #
# 3. THE REGRESSION. The old rule can never come back.
# =========================================================================== #
def test_a_modulation_DERIVED_FROM_THE_MODALITY_ALONE_is_REFUSED_BY_NAME():
    """THE DEFECT ITSELF.

    The retired rule was ``MODALITY_TO_MODULATION = {"CRISPRi knockdown": "decrease/..."}`` —
    inhibit in EVERY arm, whatever the sign. On a NEGATIVE row it yields "decrease" where the
    sign re-derives "increase". That is the inversion, and it is refused by name.
    """
    edge = {
        "edge_id": "E", "action_type_source": "INHIBITOR",
        "observed_perturbation_modality": CRISPRI,
        "observed_sign_state": mv2.SIGN_OPPOSES_DESIRED_CHANGE,   # the knockdown HARMED the arm
        "desired_target_modulation": mv2.MOD_DECREASE,            # ...but the modality "fixed" it
        "mechanism_phenocopies_modality": True,
        "evidence_relation": "putative_crispri_phenocopy",
        "evidence_relation_caveat": "x", "evidence_is_equivalence": False,
    }
    with pytest.raises(mv2.ModalityError) as exc:
        mv2.check_sign_rule(edge)
    assert exc.value.gate == mv2.GATE_MODULATION_DERIVED_FROM_MODALITY_ALONE


def test_an_edge_claiming_SUPPORT_on_a_NON_SUPPORTING_sign_is_REFUSED_BY_NAME():
    edge = {
        "edge_id": "E", "action_type_source": "INHIBITOR",
        "observed_perturbation_modality": CRISPRI,
        "observed_sign_state": mv2.SIGN_OPPOSES_DESIRED_CHANGE,
        "desired_target_modulation": mv2.MOD_INCREASE,            # correctly derived...
        "observed_perturbation_support": True,                    # ...but claims support anyway
        "mechanism_phenocopies_modality": True,
        "evidence_relation": "putative_crispri_phenocopy",
        "evidence_relation_caveat": "x", "evidence_is_equivalence": False,
    }
    with pytest.raises(mv2.ModalityError) as exc:
        mv2.check_sign_rule(edge)
    assert exc.value.gate == mv2.GATE_SUPPORTED_ON_A_NON_SUPPORTING_SIGN


def test_STAGE2s_OWN_TOKEN_DISAGREEING_WITH_THE_SIGN_is_REFUSED_BY_NAME():
    """The orientation is VERIFIED, not assumed. If Stage-2's token and the value's sign part
    company, one of us has the orientation backwards — and that is a whole release inverted."""
    record = {mv2.FIELD_ARM_VALUE: -1.0, mv2.FIELD_EVALUABLE: True,
              mv2.FIELD_MODULATION: mv2.MOD_DECREASE}          # says "supports"; the sign says no
    with pytest.raises(mv2.ModalityError) as exc:
        mv2.check_serialized_modulation(record, mv2.SIGN_OPPOSES_DESIRED_CHANGE,
                                        modality=CRISPRI, arm_key="A")
    assert exc.value.gate == mv2.GATE_SERIALIZED_MODULATION_DISAGREES_WITH_THE_SIGN


# =========================================================================== #
# 4. NOTHING IS HARDCODED TO CRISPRi.
# =========================================================================== #
def test_a_CRISPRa_arm_follows_the_DECLARED_modality_and_matches_ACTIVATORS(store):
    """Declare CRISPRa and the phenocopying set becomes the ACTIVATORS — with no code edit.

    On a POSITIVE CRISPRa row, raising the target HELPED, so an AGONIST is the phenocopy and is
    rankable as supported, while the INHIBITOR is the one that is opposed. The mirror image of
    CRISPRi, derived from the declaration rather than typed in.
    """
    row = next(r for r in store.rows
               if any(d.get("action_type_source") == "AGONIST" for d in (r.get("drugs") or []))
               and any(d.get("action_type_source") == "INHIBITOR"
                       for d in (r.get("drugs") or [])))
    target = (str(row["target_id"]), str(row["target_id_namespace"]))
    edges = edges_for(store, [arm(sa.LANE_DIRECT,
                                  [typed_row(target, arm_value=1.5, modality=CRISPRA)])])
    agonists, inhibitors = by_action(edges, "AGONIST"), by_action(edges, "INHIBITOR")
    assert agonists and inhibitors, "NON-VACUITY: both mechanisms must be present"

    for edge in agonists:            # the CRISPRa phenocopy: SUPPORTED
        assert edge["mechanism_phenocopies_modality"] is True
        assert edge["evidence_relation"] == "putative_crispra_phenocopy"
        assert edge["directional_evidence_status"] == "observed_perturbation"
        assert edge["observed_perturbation_support"] is True
        assert edge["desired_target_modulation"] == mv2.MOD_INCREASE
    for edge in inhibitors:          # and now the INHIBITOR is the non-phenocopy
        assert edge["mechanism_phenocopies_modality"] is False
        assert edge["observed_perturbation_support"] is False

    assert mv2.phenocopying_actions(CRISPRA) != mv2.phenocopying_actions(CRISPRI)


