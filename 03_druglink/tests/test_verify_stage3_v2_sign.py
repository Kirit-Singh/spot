"""THE SIGN RULE AND THE BRIDGE, attacked — in the INDEPENDENT VERIFIER's own restatement.

WHAT THESE TESTS ARE, AND WHAT THEY ARE NOT
-------------------------------------------
These exercise DETERMINISTIC LOGIC: the sign re-derivation, the phenocopy set, the emitted-row
gates and the bridge's refusals. They are TEST VECTORS, not a release.

They are deliberately NOT an end-to-end admission. There is no admitted Stage-2 native aggregate
+ W3 bridge on this host to build one from (W3's bridge is code-only; no ``stage3_bridge.json``
exists anywhere), and FABRICATING those bytes to turn a suite green is precisely the defect this
lane exists to catch — a fixture that can drift from the producer without a test failing is how a
loader ends up parsing a schema nobody emits. So the end-to-end gate stays RED and is reported as
such, and what is testable without inventing bytes is tested here.

Every REFUSAL test below is honest in a way a pass test cannot be: a refusal cannot be
manufactured by a friendly fixture. Each asserts the verifier refuses BY NAME — a test that
merely asserted "it failed" would pass against a verifier that failed for the wrong reason.
"""
from __future__ import annotations

import json
import os

import pytest

from verifier import v2_bridge as B
from verifier import v2_table_checks as K
from verifier import v2_contract as C
from verifier import v2_sign as S
from verifier.report import Report

CRISPRI = S.MODALITY_CRISPRI
CRISPRA = S.MODALITY_CRISPRA


def _failed(rep: Report, gate: str) -> list[str]:
    return [n for n, _d in rep.failures if f"[{gate}]" in n]


# --------------------------------------------------------------------------- #
# 1. THE SIGN, RE-DERIVED FROM THE SIGNED VALUE. Never read.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value,evaluable,expected", [
    (2.5, True, S.SIGN_SUPPORTS_DESIRED_CHANGE),
    (-1.5, True, S.SIGN_OPPOSES_DESIRED_CHANGE),
    (0.0, True, S.SIGN_NO_DIRECTIONAL_RESPONSE),
    (1e-10, True, S.SIGN_NO_DIRECTIONAL_RESPONSE),      # inside the epsilon band
    (-1e-10, True, S.SIGN_NO_DIRECTIONAL_RESPONSE),
    (None, True, S.SIGN_NOT_EVALUABLE),
    (2.5, False, S.SIGN_NOT_EVALUABLE),                 # a value nobody could evaluate
])
def test_the_sign_state_is_derived_from_the_SIGNED_arm_value(value, evaluable, expected):
    assert S.observed_sign_state(value, evaluable=evaluable,
                                 origin_is_measured=True) == expected


def test_SIGN_EPS_is_the_one_stage2_computed_the_values_under():
    """Bound from Stage-2 Direct config, never retuned: a Stage-3 epsilon of its own would draw
    the zero band in a different place from the lane that computed the numbers."""
    assert S.SIGN_EPS == 1e-9
    assert "direct" in S.SIGN_EPS_BASIS


def test_a_pathway_row_has_NO_sign_to_read():
    """A gene-set enrichment is a SET-LEVEL statistic. Nobody knocked down a set."""
    with pytest.raises(S.SignRuleError) as exc:
        S.observed_sign_state(2.5, evaluable=True, origin_is_measured=False, arm_key="p|1")
    assert S.GATE_SIGN_READ_FROM_AN_INFERRED_ROW in str(exc.value)


# --------------------------------------------------------------------------- #
# 2. THE TWO GOVERNING SENTENCES.
# --------------------------------------------------------------------------- #
def test_an_INHIBITOR_on_a_NEGATIVE_row_is_OPPOSED_never_supported():
    """It DOES phenocopy the knockdown — and the knockdown moved the arm the WRONG way, so what
    it phenocopies is the UNDESIRED effect. Kept, named, and never ranked."""
    got = S.classify(action_type="INHIBITOR", modality=CRISPRI,
                     sign_state=S.SIGN_OPPOSES_DESIRED_CHANGE, origin_is_measured=True)
    assert got["mechanism_phenocopies_modality"] is True
    assert got["mechanism_match_status"] == S.MATCH_PHENOCOPIES_UNDESIRED
    assert got["directional_evidence_status"] == "opposed"
    assert got["observed_perturbation_support"] is False


def test_an_AGONIST_NEVER_phenocopies_a_knockdown_and_is_never_supported():
    """On a negative row it is the UNTESTED INVERSE of a deleterious result — an experiment
    nobody ran. It never wears a phenocopy label."""
    got = S.classify(action_type="AGONIST", modality=CRISPRI,
                     sign_state=S.SIGN_OPPOSES_DESIRED_CHANGE, origin_is_measured=True)
    assert got["mechanism_phenocopies_modality"] is False
    assert got["evidence_relation"] == S.RELATION_UNTESTED_INVERSE
    assert got["evidence_relation"] not in S.PHENOCOPY_RELATIONS
    assert got["directional_evidence_status"] == "inverse_direction_hypothesis"
    assert got["observed_perturbation_support"] is False
    assert got["observed_compatible_action"] is None, "an opposing sign supports NOTHING"
    assert got["untested_inverse_action"] == S.ACTION_ACTIVATE
    assert S.PHARMACOLOGIC_REVERSIBILITY_ASSUMED is False


def test_an_INHIBITOR_on_a_POSITIVE_row_is_the_only_SUPPORTED_class():
    got = S.classify(action_type="INHIBITOR", modality=CRISPRI,
                     sign_state=S.SIGN_SUPPORTS_DESIRED_CHANGE, origin_is_measured=True)
    assert got["observed_perturbation_support"] is True
    assert got["evidence_relation"] == "putative_crispri_phenocopy"
    assert got["evidence_is_equivalence"] is False, "a phenocopy is NEVER an equivalence"
    assert got["desired_target_modulation"] == S.MOD_DECREASE


# --------------------------------------------------------------------------- #
# 3. NOT HARDCODED TO CRISPRi: the phenocopying set FOLLOWS THE DECLARED MODALITY.
# --------------------------------------------------------------------------- #
def test_a_CRISPRa_arm_FLIPS_the_phenocopying_mechanism_set():
    """Declare CRISPRa and the compatible set becomes the ACTIVATORS — with no edit to the rule.

    The set is DERIVED by asking the restated engine what each action type does, never typed out
    as a list of drug words.
    """
    assert S.phenocopies("INHIBITOR", CRISPRI) and not S.phenocopies("AGONIST", CRISPRI)
    assert S.phenocopies("AGONIST", CRISPRA) and not S.phenocopies("INHIBITOR", CRISPRA)

    crispri = set(S.phenocopying_actions(CRISPRI))
    crispra = set(S.phenocopying_actions(CRISPRA))
    assert {"INHIBITOR", "ANTAGONIST", "DEGRADER"} <= crispri
    assert {"AGONIST", "ACTIVATOR"} <= crispra
    assert not (crispri & crispra), "the two sets are disjoint, or the flip means nothing"


def test_on_a_CRISPRa_arm_the_AGONIST_is_the_supported_one_and_the_INHIBITOR_is_not():
    """The mirror image, and the proof the rule is modality-general rather than CRISPRi-shaped."""
    agonist = S.classify(action_type="AGONIST", modality=CRISPRA,
                         sign_state=S.SIGN_SUPPORTS_DESIRED_CHANGE, origin_is_measured=True)
    assert agonist["observed_perturbation_support"] is True
    assert agonist["evidence_relation"] == "putative_crispra_phenocopy"
    # CRISPRa RAISED the target and it helped -> raising it is what the data supports.
    assert agonist["desired_target_modulation"] == S.MOD_INCREASE

    inhibitor = S.classify(action_type="INHIBITOR", modality=CRISPRA,
                           sign_state=S.SIGN_SUPPORTS_DESIRED_CHANGE, origin_is_measured=True)
    assert inhibitor["observed_perturbation_support"] is False
    assert inhibitor["mechanism_match_status"] == S.MATCH_OPPOSES_OBSERVED_BENEFIT

    # And on a CRISPRa arm the knockdown moved the WRONG way: the agonist phenocopies the HARM.
    harmed = S.classify(action_type="AGONIST", modality=CRISPRA,
                        sign_state=S.SIGN_OPPOSES_DESIRED_CHANGE, origin_is_measured=True)
    assert harmed["directional_evidence_status"] == "opposed"
    assert harmed["observed_perturbation_support"] is False


def test_the_modulation_is_NEVER_derived_from_the_modality_alone():
    """The retired rule mapped CRISPRi -> 'inhibit the target in EVERY arm'. It never read the
    sign, so a gene whose knockdown made things WORSE was still matched to inhibitors."""
    assert S.desired_target_modulation(CRISPRI, S.SIGN_SUPPORTS_DESIRED_CHANGE) == S.MOD_DECREASE
    assert S.desired_target_modulation(CRISPRI, S.SIGN_OPPOSES_DESIRED_CHANGE) == S.MOD_INCREASE
    assert S.desired_target_modulation(CRISPRA, S.SIGN_SUPPORTS_DESIRED_CHANGE) == S.MOD_INCREASE
    assert S.desired_target_modulation(CRISPRA, S.SIGN_OPPOSES_DESIRED_CHANGE) == S.MOD_DECREASE
    assert not hasattr(C, "MODULATION_TO_DESIRED"), "the modality->modulation collapse is RETIRED"
    assert not hasattr(C, "PERTURBATION_MODALITY"), "the modality is DECLARED per row"


# --------------------------------------------------------------------------- #
# 4. THE PRODUCER'S SERIALIZED TOKEN IS A CHECK, NEVER AN INPUT.
# --------------------------------------------------------------------------- #
def _row(**over):
    row = {"target_id": "ENSG1", S.FIELD_NAMESPACE: "ensembl_gene_id",
           S.FIELD_MODALITY: CRISPRI, S.FIELD_ARM_VALUE: 2.5, S.FIELD_EVALUABLE: True,
           S.FIELD_MODULATION: S.MOD_DECREASE, S.FIELD_PHENOCOPY_CLASS: "transcript_knockdown",
           "rank": 1}
    row.update(over)
    return row


def test_a_serialized_modulation_that_DISAGREES_with_the_sign_is_REFUSED_by_name():
    """THE WHOLE POINT OF THE REWRITE. The producer says 'decrease'; the SIGNED value says the
    knockdown made things worse. The verifier does not reconcile — it refuses."""
    row = _row(arm_value=-1.5, desired_target_modulation=S.MOD_DECREASE)
    sign = S.observed_sign_state(row[S.FIELD_ARM_VALUE], evaluable=True, origin_is_measured=True)
    assert sign == S.SIGN_OPPOSES_DESIRED_CHANGE

    with pytest.raises(S.SignRuleError) as exc:
        S.check_serialized_modulation(row, sign, modality=CRISPRI, arm_key="a1")
    assert S.GATE_SERIALIZED_MODULATION_DISAGREES_WITH_THE_SIGN in str(exc.value)


def test_the_honest_token_is_ACCEPTED_so_the_gate_above_is_not_vacuous():
    row = _row(arm_value=-1.5, desired_target_modulation=S.MOD_INCREASE)
    assert S.check_serialized_modulation(row, S.SIGN_OPPOSES_DESIRED_CHANGE,
                                         modality=CRISPRI, arm_key="a1") == S.MOD_INCREASE


def test_an_unknown_modulation_token_is_a_named_refusal_never_a_no_direction():
    """Degrading an unknown term to 'no direction' would make a vocabulary drift look exactly
    like a target that was examined and found directionless."""
    with pytest.raises(S.SignRuleError) as exc:
        S.check_serialized_modulation(_row(desired_target_modulation="probably_down"),
                                      S.SIGN_SUPPORTS_DESIRED_CHANGE, modality=CRISPRI,
                                      arm_key="a1")
    assert S.GATE_UNKNOWN_SERIALIZED_MODULATION in str(exc.value)


@pytest.mark.parametrize("field,gate", [
    (S.FIELD_MODALITY, S.GATE_MODALITY_NOT_DECLARED),
    (S.FIELD_EVALUABLE, S.GATE_EVALUABILITY_NOT_DECLARED),
    (S.FIELD_PHENOCOPY_CLASS, S.GATE_PHENOCOPY_CLASS_NOT_DECLARED),
    (S.FIELD_NAMESPACE, S.GATE_NAMESPACE_NOT_DECLARED),
])
def test_a_row_missing_a_typed_contract_field_is_REFUSED_never_defaulted(field, gate):
    row = _row(**{field: None})
    reader = {S.FIELD_MODALITY: S.declared_modality, S.FIELD_EVALUABLE: S.evaluable_of,
              S.FIELD_PHENOCOPY_CLASS: S.phenocopy_class_of, S.FIELD_NAMESPACE: S.namespace_of}
    with pytest.raises(S.SignRuleError) as exc:
        reader[field](row, arm_key="a1")
    assert gate in str(exc.value)


def test_an_UNKNOWN_namespace_token_is_refused_and_never_coerced():
    """NO ALIAS LAYER. Coercing an unrecognised token onto a known one would let a genuinely
    different namespace join a store that never covered it."""
    with pytest.raises(S.SignRuleError) as exc:
        S.namespace_of(_row(target_id_namespace="ensembl_gene"), arm_key="a1")
    assert S.GATE_UNKNOWN_NAMESPACE in str(exc.value)


# --------------------------------------------------------------------------- #
# 5. THE GATES ON THE EMITTED ROWS. Each refusal NAMES itself.
# --------------------------------------------------------------------------- #
def _edge(**over):
    verdict = S.classify(action_type="INHIBITOR", modality=CRISPRI,
                         sign_state=S.SIGN_SUPPORTS_DESIRED_CHANGE, origin_is_measured=True)
    edge = {"edge_id": "e1", "arm_key": "a1", "origin_is_measured": True,
            "arm_value_source_string": "2.5", "arm_evaluable": True,
            "action_type_source": "INHIBITOR", **verdict}
    edge.update(over)
    return edge


def test_the_honest_edge_passes_so_every_refusal_below_is_non_vacuous():
    assert C.edge_refusals(_edge()) == []


def test_an_edge_whose_SIGN_disagrees_with_its_own_arm_value_is_refused():
    """The producer flipped the state and kept the value it came from."""
    got = C.edge_refusals(_edge(observed_sign_state=S.SIGN_SUPPORTS_DESIRED_CHANGE,
                                arm_value_source_string="-1.5"))
    assert any(S.GATE_EDGE_SIGN_DISAGREES_WITH_ITS_OWN_ARM_VALUE in r for r in got)


def test_a_NEGATIVE_row_marked_as_SUPPORTED_is_refused():
    got = C.edge_refusals(_edge(observed_sign_state=S.SIGN_OPPOSES_DESIRED_CHANGE,
                                arm_value_source_string="-1.5",
                                desired_target_modulation=S.MOD_INCREASE,
                                observed_perturbation_support=True))
    assert any(S.GATE_SUPPORTED_ON_A_NON_SUPPORTING_SIGN in r for r in got)


def test_an_AGONIST_carrying_SUPPORT_is_refused():
    """No agonist may reach supported evidence by sign inversion."""
    got = C.edge_refusals(_edge(action_type_source="AGONIST",
                                mechanism_phenocopies_modality=False,
                                observed_perturbation_support=True))
    assert any(S.GATE_NON_PHENOCOPY_IN_SUPPORTED_EVIDENCE in r for r in got)


def test_a_modulation_derived_from_the_MODALITY_ALONE_is_refused():
    """The old rule: CRISPRi -> 'decrease', whatever the sign said."""
    got = C.edge_refusals(_edge(observed_sign_state=S.SIGN_OPPOSES_DESIRED_CHANGE,
                                arm_value_source_string="-1.5",
                                desired_target_modulation=S.MOD_DECREASE))
    assert any(S.GATE_MODULATION_DERIVED_FROM_MODALITY_ALONE in r for r in got)


def test_an_edge_claiming_EQUIVALENCE_is_refused():
    got = C.edge_refusals(_edge(evidence_is_equivalence=True))
    assert any(S.GATE_CLAIMS_EQUIVALENCE in r for r in got)


def test_no_agonist_reaches_supported_evidence_AT_ANY_DEPTH():
    """Walked over the whole document and every table: an agonist reaches a consumer through a
    summary or a nested block, not through the builder that already has a gate."""
    buried = {"method": {"tables": [{"rows": [
        {"mechanism_phenocopies_modality": False, "observed_perturbation_support": True,
         "action_type_source": "AGONIST"}]}]}}
    hits = C.agonists_in_supported_evidence(buried)
    assert hits and "observed_perturbation_support" in hits[0]

    assert not C.agonists_in_supported_evidence(
        {"rows": [{"mechanism_phenocopies_modality": False,
                   "observed_perturbation_support": False}]})


def _rebuilt(**over):
    """A COMPLETE reconstruction skeleton. The real one always carries every table; a stub that
    omitted one would be testing the verifier's tolerance for a bug it does not have."""
    out = {name: [] for name in C.RECONSTRUCTED_TABLES}
    out.update({"target_drug_edges": [{"edge_id": "e"}], "source_records": [{}],
                "candidates": []})
    out.update(over)
    return out


def _emitted(**over):
    out = {name: [] for name in C.TABLES}
    out.update(over)
    return out


def test_a_hit_count_that_counted_ROWS_NOT_RANKS_is_refused():
    """Stage 2 RETAINS unrankable targets with rank:null, so 'in the ranking' is NOT 'in the
    rows' — and a count from rows inflates by exactly the targets the arm could not evaluate."""
    rep = Report()
    K.check_tables(rep, doc={}, manifest={}, rebuilt=_rebuilt(),
                   emitted=_emitted(arm_slots=[{"arm_slot_id": "s1", "n_records": 5,
                                                "n_ranked": 5}]))
    assert not _failed(rep, C.GATE_HIT_COUNT_COUNTED_ROWS_NOT_RANKS), "5 of 5 is legal"

    rep = Report()
    K.check_tables(rep, doc={}, manifest={}, rebuilt=_rebuilt(),
                   emitted=_emitted(arm_slots=[{"arm_slot_id": "s1", "n_records": 3,
                                                "n_ranked": 5}]))
    assert _failed(rep, C.GATE_HIT_COUNT_COUNTED_ROWS_NOT_RANKS)


def test_a_NULL_rank_coerced_to_ZERO_is_refused():
    """A 0 sorts, and it sorts as BEST — a first place for a target nobody ranked."""
    rep = Report()
    K.check_tables(rep, doc={}, manifest={}, rebuilt=_rebuilt(),
                   emitted=_emitted(target_drug_edges=[{"edge_id": "e1", "arm_rank": 0}]))
    assert _failed(rep, C.GATE_NULL_RANK_COERCED_TO_ZERO)


def test_a_PATHWAY_ORIGIN_edge_or_a_pathway_CONTEXT_row_is_refused():
    """The lane is NOT ADMITTED (its verifier fails open), so it must contribute ZERO — and the
    zero is CHECKED, by name, rather than assumed from a table nobody emitted."""
    rep = Report()
    K.check_tables(rep, doc={}, manifest={}, rebuilt=_rebuilt(),
                   emitted=_emitted(target_drug_edges=[
                       {"edge_id": "p1", "origin_type": "endpoint_pathway_context"}]))
    assert _failed(rep, C.GATE_PATHWAY_LANE_CONTRIBUTED)

    rep = Report()
    K.check_tables(rep, doc={}, manifest={}, rebuilt=_rebuilt(),
                   emitted=_emitted(pathway_context=[{"pathway_context_id": "c1"}]))
    assert _failed(rep, C.GATE_PATHWAY_LANE_CONTRIBUTED)


def test_an_ENRICHMENT_VALUE_sourcing_an_edge_is_refused():
    rep = Report()
    K.check_tables(rep, doc={}, manifest={}, rebuilt=_rebuilt(),
                   emitted=_emitted(target_drug_edges=[{"edge_id": "e1",
                                                        "enrichment_value": "2.1"}]))
    assert _failed(rep, C.GATE_ENRICHMENT_SOURCED_AN_EDGE)


# --------------------------------------------------------------------------- #
# 6. THE W3 BRIDGE. It may ADD identity and modality; it may never CHANGE a measurement.
# --------------------------------------------------------------------------- #
NATIVE = {"target_id": "ENSG1", "arm_value": -1.5, "evaluable": True, "rank": 7}
AGG = {"arms": [{"lane": "direct", "arm_key": "direct|Rest|P0|increase",
                 "records": [dict(NATIVE)]}],
       "manifest_raw_sha256": "a" * 64, "manifest_canonical_sha256": "b" * 64,
       "report_raw_sha256": "c" * 64}


def _bridge_row(**over):
    row = {"schema_version": "spot.stage02_stage3_row.v1", "lane": "direct",
           "arm_key": "direct|Rest|P0|increase", "program_id": "P0", "target_id": "ENSG1",
           "target_id_namespace": "ensembl_gene_id",
           "observed_perturbation_modality": CRISPRI,
           "perturbation_target_effect": "target_transcript_reduced",
           "program_effect_direction": "increase",
           # The NATIVE value is NEGATIVE, so the honest tokens are the OPPOSED ones.
           "desired_target_modulation": S.MOD_INCREASE,
           "phenocopy_class": "inhibitor_opposed",
           "arm_value": -1.5, "evaluable": True, "rank": 7}
    row.update(over)
    return row


def _write_bridge(root, rows, contexts=()):
    doc = {"schema_version": B.BRIDGE_SCHEMA, "rule_id": "r",
           "bindings": {k: {"x": 1} for k in B.REQUIRED_BINDINGS},
           "target_rows": list(rows), "pathway_contexts": list(contexts)}
    doc[B.SELF_HASH_FIELD] = B.bridge_self_hash(doc)
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, B.BRIDGE_FILE), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, sort_keys=True)
    return doc


def _admit(root, rows, contexts=()):
    _write_bridge(root, rows, contexts)
    rep = Report()
    B.admit_bridge(rep, bridge_root=str(root), aggregate=AGG)
    return rep


def test_a_bridge_that_CHANGES_a_native_arm_value_is_refused_by_name(tmp_path):
    """THE RULE THAT MAKES A BRIDGE SAFE. It supplies identity and modality — it may never
    restate a number the admitted native ranking already states. A bridge free to re-measure is
    a forged value wearing an admitted release's hashes, and every sign downstream follows it."""
    rep = _admit(tmp_path / "b", [_bridge_row(arm_value=2.5,
                                              desired_target_modulation=S.MOD_DECREASE,
                                              phenocopy_class="inhibition_observed_compatible")])
    assert _failed(rep, B.GATE_BRIDGE_CHANGED_A_NATIVE_VALUE)


def test_a_bridge_row_whose_MODULATION_disagrees_with_the_NATIVE_sign_is_refused(tmp_path):
    """The value stays honest; only the token is flipped. The sign is re-derived from the NATIVE
    ranking, so the flip has nowhere to hide."""
    rep = _admit(tmp_path / "b",
                 [_bridge_row(desired_target_modulation=S.MOD_DECREASE,
                              phenocopy_class="inhibition_observed_compatible")])
    assert _failed(rep, C.GATE_SERIALIZED_MODULATION_DISAGREES_WITH_THE_SIGN)


def test_an_ORPHAN_bridge_row_the_native_bytes_never_produced_is_refused(tmp_path):
    rep = _admit(tmp_path / "b", [_bridge_row(), _bridge_row(target_id="ENSG_INVENTED")])
    assert _failed(rep, B.GATE_BRIDGE_ORPHAN_ROW)


def test_a_DROPPED_row_is_refused_because_a_dropped_row_looks_like_one_that_never_existed(
        tmp_path):
    rep = _admit(tmp_path / "b", [])
    assert _failed(rep, B.GATE_BRIDGE_DROPPED_A_ROW)
    assert _failed(rep, B.GATE_BRIDGE_ZERO_EVIDENCE), "a bridge with no evidence is not a bridge"


def test_a_FORGED_bridge_self_hash_is_refused(tmp_path):
    root = tmp_path / "b"
    _write_bridge(root, [_bridge_row()])
    path = os.path.join(str(root), B.BRIDGE_FILE)
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc[B.SELF_HASH_FIELD] = "f" * 64
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, sort_keys=True)
    rep = Report()
    B.admit_bridge(rep, bridge_root=str(root), aggregate=AGG)
    assert _failed(rep, B.GATE_BRIDGE_SELF_HASH)


def test_a_bridge_that_BINDS_NOTHING_is_refused(tmp_path):
    root = tmp_path / "b"
    os.makedirs(root, exist_ok=True)
    doc = {"schema_version": B.BRIDGE_SCHEMA, "bindings": {}, "target_rows": [_bridge_row()],
           "pathway_contexts": []}
    doc[B.SELF_HASH_FIELD] = B.bridge_self_hash(doc)
    with open(os.path.join(str(root), B.BRIDGE_FILE), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, sort_keys=True)
    rep = Report()
    B.admit_bridge(rep, bridge_root=str(root), aggregate=AGG)
    assert _failed(rep, B.GATE_BRIDGE_BINDS_NOTHING)


def test_a_MISSING_bridge_is_a_NAMED_refusal_and_never_an_exception(tmp_path):
    rep = Report()
    assert B.admit_bridge(rep, bridge_root=str(tmp_path / "nope"), aggregate=AGG) is None
    assert _failed(rep, B.GATE_BRIDGE_NOT_ON_DISK)


@pytest.mark.parametrize("field", sorted(B.CTX_FORBIDDEN))
def test_a_pathway_context_that_SMUGGLES_a_target_evidence_field_is_refused(tmp_path, field):
    """An enrichment value is a statement about a GENE SET. Read as a target's arm value it would
    prescribe a drug for a pathway. W3 reached this same firewall independently — it is bound
    verbatim, not re-derived loosely."""
    ctx = {"schema_version": "v1", "lane": "pathway", "arm_key": "p|1", "gene_set_id": "GO:1",
           "is_a_crispri_target_row": False, "may_be_matched_to_a_drug_as_a_target": False,
           field: "smuggled"}
    rep = _admit(tmp_path / "b", [_bridge_row()], [ctx])
    assert _failed(rep, B.GATE_CTX_CARRIES_TARGET_EVIDENCE)


def test_a_pathway_context_must_DECLARE_itself_not_target_evidence(tmp_path):
    ctx = {"schema_version": "v1", "lane": "pathway", "arm_key": "p|1", "gene_set_id": "GO:1",
           "is_a_crispri_target_row": True, "may_be_matched_to_a_drug_as_a_target": False}
    rep = _admit(tmp_path / "b", [_bridge_row()], [ctx])
    assert _failed(rep, B.GATE_CTX_CARRIES_TARGET_EVIDENCE)


def test_an_honest_pathway_context_is_ADMITTED_so_the_firewall_is_not_vacuous(tmp_path):
    ctx = {"schema_version": "v1", "lane": "pathway", "arm_key": "p|1", "gene_set_id": "GO:1",
           "enrichment_value": 2.0, "is_a_crispri_target_row": False,
           "may_be_matched_to_a_drug_as_a_target": False}
    rep = _admit(tmp_path / "b", [_bridge_row()], [ctx])
    assert not _failed(rep, B.GATE_CTX_CARRIES_TARGET_EVIDENCE)
    assert not _failed(rep, B.GATE_CTX_UNKNOWN_FIELD)


# --------------------------------------------------------------------------- #
# 7. Independence. A verifier that imports the thing it verifies proves nothing.
# --------------------------------------------------------------------------- #
def test_the_verifier_imports_NOTHING_from_the_producer():
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "verifier")
    modules = sorted(f for f in os.listdir(root) if f.endswith(".py"))
    assert len(modules) > 15, "the scan must actually see the verifier package"
    for name in modules:
        with open(os.path.join(root, name), "r", encoding="utf-8") as fh:
            src = fh.read()
        assert "from druglink" not in src, f"{name} imports the producer"
        assert "import druglink" not in src, f"{name} imports the producer"
