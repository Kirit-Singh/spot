"""THE SIGN RULE, RESTATED for the independent verifier. Imports NOTHING from ``druglink``.

WHAT THIS MODULE IS FOR
-----------------------
The producer serializes, on every edge, what it decided about a target's direction. A verifier
that READ that decision could only prove the producer agreed with itself. So this module writes
the rule out AGAIN, from the contract, and the verifier RE-DERIVES the sign from the two facts
Stage 2 actually measured — the SIGNED ``arm_value`` and ``evaluable`` — and then REQUIRES the
producer's serialized token to equal what the re-derivation says. A disagreement is a NAMED
REFUSAL (:data:`GATE_SERIALIZED_MODULATION_DISAGREES_WITH_THE_SIGN`), never a reconciliation.

TWO FACTS, NEITHER DERIVED FROM THE OTHER
-----------------------------------------
    observed_perturbation_modality   what the screen DID      "CRISPRi_knockdown"  (verbatim)
    the SIGN STATE                   whether it HELPED        (from the SIGNED arm_value)

    not evaluable / arm_value is null  ->  not_evaluable                 (STATED)
    |arm_value| <= SIGN_EPS            ->  no_directional_response       (STATED)
    arm_value  >  SIGN_EPS             ->  the perturbation SUPPORTS the arm's desired change
    arm_value  < -SIGN_EPS             ->  the perturbation OPPOSES it

The value arrives ALREADY ORIENTED to its arm's ``desired_change`` (Stage-2's own per-arm
convention, stated explicitly in their temporal lane). It is NEVER re-oriented here: doing so
would apply the orientation twice and invert half a release.

THE TWO GOVERNING SENTENCES
---------------------------
**An INHIBITOR always phenocopies CRISPRi — and on a NEGATIVE row what it phenocopies is the
UNDESIRED effect.** So a negative row never becomes support: it becomes an explicit
INHIBITOR-OPPOSED flag. The drug is kept, it is named, and it never ranks.

**An AGONIST never phenocopies CRISPRi.** On a negative row it is only the UNTESTED INVERSE of a
deleterious result — an experiment nobody ran. NO AGONIST MAY REACH SUPPORTED EVIDENCE BY SIGN
INVERSION, and that is checked at ANY DEPTH, over the document and every table
(:func:`agonists_in_supported_evidence`), not merely where an edge is built.

NOTHING IS HARDCODED TO CRISPRi. The modality is DECLARED per row; what each modality DOES to a
target is one small table; and the phenocopying mechanism set FOLLOWS from it by asking the
restated direction engine what each drug action does. Declare CRISPRa and the set becomes the
ACTIVATORS, with no edit here.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from . import policy
from . import v2_direction as D

# --------------------------------------------------------------------------- #
# EPSILON. BOUND from upstream, never retuned, and never a magic number in a compare.
#
# Stage-2 Direct declares the sign tolerance once (``direct/config.py:186``) and applies it in
# ``disposition.desired_modulation`` — the rule the arm values Stage 3 consumes were computed
# under. A Stage-3 epsilon of its own would draw the zero band in a different place from the
# lane that computed the numbers, and rows in the gap would carry a direction one stage believes
# and the other denies. It is NOT a threshold on effect SIZE: it is the band inside which a
# float's sign carries no information.
# --------------------------------------------------------------------------- #
SIGN_EPS = 1e-9
SIGN_EPS_BASIS = "stage-2 direct config.SIGN_EPS=1e-9 (direct/disposition.py::desired_modulation)"

SIGN_NOT_EVALUABLE = "not_evaluable"
SIGN_NO_DIRECTIONAL_RESPONSE = "no_directional_response"
SIGN_SUPPORTS_DESIRED_CHANGE = "perturbation_supports_the_desired_change"
SIGN_OPPOSES_DESIRED_CHANGE = "perturbation_opposes_the_desired_change"
SIGN_STATES = (SIGN_NOT_EVALUABLE, SIGN_NO_DIRECTIONAL_RESPONSE,
               SIGN_SUPPORTS_DESIRED_CHANGE, SIGN_OPPOSES_DESIRED_CHANGE)

# The typed row contract W3 serializes. Asserted by EXACT TOKEN — there is NO ALIAS LAYER here
# or anywhere: an unknown token is a NAMED REFUSAL, never a coercion.
FIELD_MODALITY = "observed_perturbation_modality"
FIELD_NAMESPACE = "target_id_namespace"
FIELD_MODULATION = "desired_target_modulation"
FIELD_PHENOCOPY_CLASS = "phenocopy_class"
FIELD_ARM_VALUE = "arm_value"
FIELD_EVALUABLE = "evaluable"
W3_REQUIRED_ROW_FIELDS = (FIELD_MODALITY, FIELD_NAMESPACE, FIELD_MODULATION,
                          FIELD_PHENOCOPY_CLASS, FIELD_EVALUABLE)

NS_ENSEMBL_GENE = "ensembl_gene_id"
NS_SYMBOL = "gene_symbol"
W3_NAMESPACES = (NS_ENSEMBL_GENE, NS_SYMBOL)

# THE MODALITY, and the ONE table that says what it did to the target. Never derived from the
# program, and never from the sign.
MODALITY_CRISPRI = "CRISPRi_knockdown"
MODALITY_CRISPRA = "CRISPRa_activation"
ACTION_INHIBIT = "inhibit_target"
ACTION_ACTIVATE = "activate_target"
MODALITY_PERFORMED_ACTION = {MODALITY_CRISPRI: ACTION_INHIBIT,
                             MODALITY_CRISPRA: ACTION_ACTIVATE}
INVERSE_ACTION = {ACTION_INHIBIT: ACTION_ACTIVATE, ACTION_ACTIVATE: ACTION_INHIBIT}

# Which drug intervention effects PHENOCOPY each target action, in the restated engine's own
# effect vocabulary. No drug word is restated here: the mechanism set is DERIVED by asking the
# engine what each action type does.
ACTION_PHENOCOPY_EFFECTS = {
    ACTION_INHIBIT: (D.ABUNDANCE_REDUCTION, D.FUNCTIONAL_INHIBITION),
    ACTION_ACTIVATE: (D.FUNCTIONAL_ACTIVATION,),
}

MOD_DECREASE = "decrease"
MOD_INCREASE = "increase"
MOD_NO_DIRECTION = "no_direction_evidence"
MOD_NOT_EVALUATED = "not_evaluated"
TARGET_MODULATIONS = (MOD_DECREASE, MOD_INCREASE, MOD_NO_DIRECTION, MOD_NOT_EVALUATED)

# (modality, sign) -> the token. The MODALITY says which action was performed; the SIGN says
# whether performing it helped. ONLY BOTH TOGETHER NAME A DIRECTION.
#
#   CRISPRi (it LOWERED the target):  helped -> "decrease"   harmed -> "increase"
#   CRISPRa (it RAISED the target):   helped -> "increase"   harmed -> "decrease"
#
# There is deliberately no second token->sign map: the token's MEANING depends on the modality,
# so a modality-blind map would be right for one lane and silently inverted for the other.
MODULATION_FOR = {
    (MODALITY_CRISPRI, SIGN_SUPPORTS_DESIRED_CHANGE): MOD_DECREASE,
    (MODALITY_CRISPRI, SIGN_OPPOSES_DESIRED_CHANGE): MOD_INCREASE,
    (MODALITY_CRISPRA, SIGN_SUPPORTS_DESIRED_CHANGE): MOD_INCREASE,
    (MODALITY_CRISPRA, SIGN_OPPOSES_DESIRED_CHANGE): MOD_DECREASE,
    (MODALITY_CRISPRI, SIGN_NO_DIRECTIONAL_RESPONSE): MOD_NO_DIRECTION,
    (MODALITY_CRISPRA, SIGN_NO_DIRECTIONAL_RESPONSE): MOD_NO_DIRECTION,
    (MODALITY_CRISPRI, SIGN_NOT_EVALUABLE): MOD_NOT_EVALUATED,
    (MODALITY_CRISPRA, SIGN_NOT_EVALUABLE): MOD_NOT_EVALUATED,
}

# "increase" on a CRISPRi arm is a statement about an experiment NOBODY RAN. The screen cannot
# say a drug could raise anything, so pharmacologic reversibility is NOT assumed and the row
# licenses an explicitly-labelled, non-rankable inverse hypothesis — never supported agonism.
PHARMACOLOGIC_REVERSIBILITY_ASSUMED = False

PHENOCOPY_RELATION = {MODALITY_CRISPRI: "putative_crispri_phenocopy",
                      MODALITY_CRISPRA: "putative_crispra_phenocopy"}
PHENOCOPY_RELATIONS = frozenset(PHENOCOPY_RELATION.values())
RELATION_UNTESTED_INVERSE = "untested_inverse_of_the_tested_perturbation"
RELATION_EFFECT_NOT_ENUMERATED = "mechanism_effect_not_enumerated_no_phenocopy_claim"
EVIDENCE_RELATIONS = tuple(sorted(
    PHENOCOPY_RELATIONS | {RELATION_UNTESTED_INVERSE, RELATION_EFFECT_NOT_ENUMERATED}))

EVIDENCE_IS_EQUIVALENCE = False
PHENOCOPY_CAVEAT = (
    "PUTATIVE PHENOCOPY, NOT EQUIVALENCE. A drug acting on the PROTEIN is not the genetic "
    "perturbation of the TRANSCRIPT that was measured: they differ in modality (protein vs "
    "mRNA), in degree (partial, reversible occupancy vs sustained knockdown), in timing, and "
    "in off-target profile. This edge may SUGGEST a hypothesis; it can never CONFIRM one.")
INVERSE_CAVEAT = (
    "NOT A PHENOCOPY, AND NOT A MEASUREMENT. The screen knocked this target DOWN and the arm "
    "moved the WRONG way. That a drug doing the OPPOSITE would move it the right way is the "
    "UNTESTED INVERSE of a deleterious result — an experiment nobody ran. Pharmacologic "
    "reversibility is NOT assumed. This record may never be read as supported evidence.")

MATCH_COMPATIBLE = "phenocopies_the_perturbation_that_helped"
MATCH_PHENOCOPIES_UNDESIRED = "phenocopies_the_perturbation_that_harmed"
MATCH_UNTESTED_INVERSE = "untested_inverse_direction_never_supported"
MATCH_OPPOSES_OBSERVED_BENEFIT = "runs_against_the_perturbation_that_helped"
MATCH_EFFECT_UNKNOWN = "mechanism_effect_unknown"
MATCH_NO_DIRECTIONAL_RESPONSE = "arm_shows_no_directional_response"
MATCH_ARM_NOT_EVALUABLE = "arm_not_evaluable"
MATCH_STATUSES = (MATCH_COMPATIBLE, MATCH_PHENOCOPIES_UNDESIRED, MATCH_UNTESTED_INVERSE,
                  MATCH_OPPOSES_OBSERVED_BENEFIT, MATCH_EFFECT_UNKNOWN,
                  MATCH_NO_DIRECTIONAL_RESPONSE, MATCH_ARM_NOT_EVALUABLE)

# --------------------------------------------------------------------------- #
# Named gates. Every refusal cites one, so it can be grepped, tested and quoted.
# --------------------------------------------------------------------------- #
GATE_MODALITY_NOT_DECLARED = "stage2_declared_no_observed_perturbation_modality_for_this_row"
GATE_UNKNOWN_MODALITY = "the_declared_perturbation_modality_performs_no_known_target_action"
GATE_EVALUABILITY_NOT_DECLARED = "stage2_declared_no_evaluability_for_this_row"
GATE_PHENOCOPY_CLASS_NOT_DECLARED = "stage2_declared_no_phenocopy_class_for_this_row"
GATE_NAMESPACE_NOT_DECLARED = "stage2_declared_no_target_id_namespace_for_this_row"
GATE_UNKNOWN_NAMESPACE = "the_declared_target_id_namespace_is_not_a_typed_contract_namespace"
GATE_UNKNOWN_SERIALIZED_MODULATION = \
    "the_row_carries_a_modulation_token_from_neither_stage2_lane_vocabulary"
GATE_SERIALIZED_MODULATION_DISAGREES_WITH_THE_SIGN = \
    "stage2s_own_modulation_token_disagrees_with_the_sign_of_the_value_it_was_derived_from"
GATE_MODULATION_DERIVED_FROM_MODALITY_ALONE = \
    "the_target_modulation_was_derived_from_the_modality_without_the_observed_sign"
GATE_NON_PHENOCOPY_IN_SUPPORTED_EVIDENCE = \
    "a_mechanism_that_does_not_phenocopy_the_declared_modality_reached_supported_evidence"
GATE_SUPPORTED_ON_A_NON_SUPPORTING_SIGN = \
    "an_edge_claims_observed_support_on_a_row_whose_sign_does_not_support_the_desired_change"
GATE_EDGE_SIGN_DISAGREES_WITH_ITS_OWN_ARM_VALUE = \
    "an_edges_sign_state_is_not_the_sign_of_the_arm_value_it_carries"
GATE_NO_EVIDENCE_RELATION = "an_edge_does_not_declare_its_relation_to_the_perturbation"
GATE_CLAIMS_EQUIVALENCE = "an_edge_claims_the_drug_is_EQUIVALENT_to_the_perturbation"
GATE_SIGN_READ_FROM_AN_INFERRED_ROW = \
    "a_crispri_sign_was_read_from_a_pathway_enrichment_row_that_has_none"
GATE_MODALITY_VOCABULARY_DIVERGENCE = \
    "the_bundles_modality_vocabulary_is_not_the_one_the_verifier_restates"


class SignRuleError(ValueError):
    """A named, fail-closed refusal. The row yields ZERO edges."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


# --------------------------------------------------------------------------- #
# 1. THE SIGN, RE-DERIVED. Never read off the row it is meant to check.
# --------------------------------------------------------------------------- #
def observed_sign_state(arm_value: Any, *, evaluable: bool,
                        origin_is_measured: bool, arm_key: str = "") -> str:
    """The sign state, re-derived from the SIGNED value Stage 2 measured.

    IT APPLIES ONLY TO A MEASURED LANE. A pathway record is a GENE-SET ENRICHMENT — a set-level
    statistic with a leading edge — and nobody knocked down a set, so it has no sign to read.
    Reading one from it would hand a set-level number a direction it never had.
    """
    if not origin_is_measured:
        raise SignRuleError(
            GATE_SIGN_READ_FROM_AN_INFERRED_ROW,
            f"arm {arm_key!r} asked for the sign of an INFERRED row (arm_value={arm_value!r}). "
            "A pathway record is a gene-set enrichment, not a measured per-target knockdown "
            "effect: a direction is never inherited from set membership")
    if not evaluable or arm_value is None:
        return SIGN_NOT_EVALUABLE
    value = float(arm_value)
    if value > SIGN_EPS:
        return SIGN_SUPPORTS_DESIRED_CHANGE
    if value < -SIGN_EPS:
        return SIGN_OPPOSES_DESIRED_CHANGE
    return SIGN_NO_DIRECTIONAL_RESPONSE


def desired_target_modulation(modality: str, sign_state: str) -> str:
    """From (modality, SIGN) — never from the modality alone. On an opposing sign it names what
    would be NEEDED: a refusal with a reason, not an activator lead."""
    return MODULATION_FOR.get((modality, sign_state), sign_state)


def observed_compatible_action(modality: str, sign_state: str) -> Optional[str]:
    """The target action the DATA supports. ONLY a supporting sign yields one; on an opposing
    sign the answer is None — returning the inverse is precisely how an agonist becomes a
    recommendation."""
    if sign_state == SIGN_SUPPORTS_DESIRED_CHANGE:
        return MODALITY_PERFORMED_ACTION[modality]
    return None


def untested_inverse_action(modality: str, sign_state: str) -> Optional[str]:
    if sign_state == SIGN_OPPOSES_DESIRED_CHANGE:
        return INVERSE_ACTION[MODALITY_PERFORMED_ACTION[modality]]
    return None


# --------------------------------------------------------------------------- #
# 2. What the typed row must DECLARE. A missing field is a refusal, never a default.
# --------------------------------------------------------------------------- #
def declared_modality(record: Mapping[str, Any], *, arm_key: str) -> str:
    modality = record.get(FIELD_MODALITY)
    if modality in (None, ""):
        raise SignRuleError(
            GATE_MODALITY_NOT_DECLARED,
            f"arm {arm_key!r} carries a row with no {FIELD_MODALITY}. Without it there is "
            "nothing to phenocopy, and defaulting one would match drugs against an experiment "
            "nobody described")
    if str(modality) not in MODALITY_PERFORMED_ACTION:
        raise SignRuleError(
            GATE_UNKNOWN_MODALITY,
            f"arm {arm_key!r} declares {FIELD_MODALITY}={modality!r}, which performs no target "
            f"action this contract knows ({sorted(MODALITY_PERFORMED_ACTION)}). The compatible "
            "mechanism set FOLLOWS the modality, so an unknown modality has none")
    return str(modality)


def evaluable_of(record: Mapping[str, Any], *, arm_key: str) -> bool:
    """``bool(None)`` is False, so a MISSING flag would silently become 'not evaluable' — a row
    nobody assessed, reported as one that was assessed and found wanting."""
    value = record.get(FIELD_EVALUABLE)
    if not isinstance(value, bool):
        raise SignRuleError(
            GATE_EVALUABILITY_NOT_DECLARED,
            f"arm {arm_key!r} carries a row with {FIELD_EVALUABLE}={value!r}. Evaluability is "
            "Stage-2's finding, never Stage-3's default")
    return value


def phenocopy_class_of(record: Mapping[str, Any], *, arm_key: str) -> str:
    """W3's own token, REQUIRED and carried verbatim — and deliberately never branched on: a
    closed vocabulary invented here would be a fabricated contract."""
    value = record.get(FIELD_PHENOCOPY_CLASS)
    if value in (None, ""):
        raise SignRuleError(
            GATE_PHENOCOPY_CLASS_NOT_DECLARED,
            f"arm {arm_key!r} carries a row with no {FIELD_PHENOCOPY_CLASS}; it is part of the "
            "typed row contract, and a row that does not carry it is a row this contract refuses")
    return str(value)


def namespace_of(record: Mapping[str, Any], *, arm_key: str) -> str:
    """The row's OWN namespace token, asserted EXACTLY and returned VERBATIM. PER ROW, never per
    release, and never guessed from the id's shape. There is NO alias map."""
    declared = record.get(FIELD_NAMESPACE)
    if declared in (None, ""):
        raise SignRuleError(
            GATE_NAMESPACE_NOT_DECLARED,
            f"arm {arm_key!r} carries a target with no {FIELD_NAMESPACE}. A namespace-less id "
            "is a name, and names are not identities")
    if str(declared) not in W3_NAMESPACES:
        raise SignRuleError(
            GATE_UNKNOWN_NAMESPACE,
            f"arm {arm_key!r} declares {FIELD_NAMESPACE}={declared!r}; the typed row contract "
            f"is exactly {list(W3_NAMESPACES)}. This is asserted, not normalised: coercing an "
            "unrecognised token onto a known one would let a genuinely different namespace join "
            "a store that never covered it")
    return str(declared)


def check_serialized_modulation(record: Mapping[str, Any], sign_state: str, *,
                                modality: str, arm_key: str) -> str:
    """THE CENTRE OF THE VERIFIER. The producer's token is CHECKED, never obeyed.

    Stage 2 derives its modulation from the same signed value this module re-derives the sign
    from, so the two must agree. If they do not, one side has the orientation backwards — and a
    disagreement admitted here is an entire release of drugs matched to the wrong direction.
    """
    token = record.get(FIELD_MODULATION)
    if token in (None, "") or str(token) not in TARGET_MODULATIONS:
        raise SignRuleError(
            GATE_UNKNOWN_SERIALIZED_MODULATION,
            f"arm {arm_key!r} carries {FIELD_MODULATION}={token!r}, which is not one of the "
            f"typed contract's tokens {list(TARGET_MODULATIONS)}. Reading an unknown term as "
            "'no direction' would make a vocabulary drift look exactly like a target that was "
            "examined and found directionless")
    expected = desired_target_modulation(modality, sign_state)
    if str(token) != expected:
        raise SignRuleError(
            GATE_SERIALIZED_MODULATION_DISAGREES_WITH_THE_SIGN,
            f"arm {arm_key!r}: the producer serialized {FIELD_MODULATION}={token!r}, but "
            f"{FIELD_ARM_VALUE}={record.get(FIELD_ARM_VALUE)!r} with "
            f"{FIELD_EVALUABLE}={record.get(FIELD_EVALUABLE)!r} INDEPENDENTLY re-derives sign "
            f"{sign_state!r} (eps={SIGN_EPS!r}), which for modality {modality!r} means "
            f"{expected!r}. The verifier does not reconcile: one of the two has the orientation "
            "backwards, and admitting the disagreement would ship the inversion")
    return str(token)


# --------------------------------------------------------------------------- #
# 3. The phenocopying mechanism set — DERIVED from the declared modality, never typed out.
# --------------------------------------------------------------------------- #
def engine_actions() -> tuple[str, ...]:
    """Every action type the restated engine enumerates. Asked, never re-listed."""
    return tuple(sorted(D.ACTION_ABUNDANCE_REDUCTION | D.ACTION_FUNCTIONAL_INHIBITION
                        | D.ACTION_FUNCTIONAL_ACTIVATION | D.ACTION_EXPLICIT_UNKNOWN))


def phenocopying_actions(modality: str) -> tuple[str, ...]:
    """Declare CRISPRa and this set becomes the ACTIVATORS, with no edit here."""
    effects = ACTION_PHENOCOPY_EFFECTS[MODALITY_PERFORMED_ACTION[modality]]
    return tuple(a for a in engine_actions() if D.intervention_effect(a)[0] in effects)


def phenocopies(action_type: Optional[str], modality: str) -> bool:
    """Does this sourced mechanism do to the PROTEIN what the modality did to the TRANSCRIPT?

    An INHIBITOR always phenocopies CRISPRi. An AGONIST never does — whatever the sign says.
    """
    effect = D.intervention_effect(action_type)[0]
    return effect in ACTION_PHENOCOPY_EFFECTS[MODALITY_PERFORMED_ACTION[modality]]


def is_inverse_mechanism(action_type: Optional[str], modality: str) -> bool:
    effect = D.intervention_effect(action_type)[0]
    inverse = INVERSE_ACTION[MODALITY_PERFORMED_ACTION[modality]]
    return effect in ACTION_PHENOCOPY_EFFECTS[inverse]


def evidence_relation(action_type: Optional[str], modality: str) -> tuple[str, str]:
    """Only a mechanism that ACTUALLY phenocopies the declared modality wears the phenocopy
    label. An agonist on a CRISPRi arm phenocopies nothing that was tested."""
    if phenocopies(action_type, modality):
        return PHENOCOPY_RELATION[modality], PHENOCOPY_CAVEAT
    if is_inverse_mechanism(action_type, modality):
        return RELATION_UNTESTED_INVERSE, INVERSE_CAVEAT
    return RELATION_EFFECT_NOT_ENUMERATED, PHENOCOPY_CAVEAT


# --------------------------------------------------------------------------- #
# 4. The classification. THE SIGN DECIDES; the modality only says what phenocopies what.
# --------------------------------------------------------------------------- #
def classify(*, action_type: Optional[str], modality: str, sign_state: str,
             origin_is_measured: bool) -> dict[str, Any]:
    """Classify ONE sourced mechanism against ONE arm row. Fail-closed.

    An incompatible mechanism is kept as an EXPLICIT non-match carrying its reason. Dropping it
    would make "this drug does the opposite of what the data supports" indistinguishable from
    "no drug was found".
    """
    effect, effect_reason = D.intervention_effect(action_type)
    relation, caveat = evidence_relation(action_type, modality)
    phenocopy = phenocopies(action_type, modality)
    inverse = is_inverse_mechanism(action_type, modality)

    if sign_state == SIGN_NOT_EVALUABLE:
        match, status, reason = (MATCH_ARM_NOT_EVALUABLE, policy.UNRESOLVED,
                                 policy.REASON_ARM_NOT_EVALUABLE)
    elif sign_state == SIGN_NO_DIRECTIONAL_RESPONSE:
        match, status, reason = (MATCH_NO_DIRECTIONAL_RESPONSE, policy.UNRESOLVED,
                                 policy.REASON_NO_DIRECTION)
    elif effect == D.EFFECT_UNKNOWN:
        match, status, reason = (MATCH_EFFECT_UNKNOWN, policy.UNRESOLVED,
                                 policy.REASON_ACTION_UNKNOWN)
    elif sign_state == SIGN_SUPPORTS_DESIRED_CHANGE:
        if phenocopy:
            match = MATCH_COMPATIBLE
            status, reason = ((policy.OBSERVED_PERTURBATION,
                               policy.REASON_ACTION_MATCHES_TESTED) if origin_is_measured
                              else (policy.PATHWAY_HYPOTHESIS, policy.REASON_PATHWAY_COMPATIBLE))
        else:
            match, status, reason = (MATCH_OPPOSES_OBSERVED_BENEFIT, policy.OPPOSED,
                                     policy.REASON_ACTION_OPPOSES)
    else:                                        # the perturbation OPPOSED the desired change
        if phenocopy:
            # THE INHIBITOR-OPPOSED FLAG. The inhibitor DOES phenocopy the knockdown — and the
            # knockdown moved this arm the WRONG way, so what it phenocopies is the UNDESIRED
            # effect. This is the row the retired modality-fixed rule ranked as SUPPORTED.
            match, status, reason = (MATCH_PHENOCOPIES_UNDESIRED, policy.OPPOSED,
                                     policy.REASON_ACTION_OPPOSES)
        elif inverse:
            # THE ONE THAT MAY NEVER BE PROMOTED. An agonist phenocopies NOTHING that was
            # tested; it is the untested inverse of a deleterious result.
            match, status, reason = (MATCH_UNTESTED_INVERSE,
                                     policy.INVERSE_DIRECTION_HYPOTHESIS,
                                     policy.REASON_INVERSE_ACTIVATION)
        else:
            match, status, reason = (MATCH_EFFECT_UNKNOWN, policy.UNRESOLVED,
                                     policy.REASON_ACTION_UNKNOWN)

    # Observed support requires ALL THREE: a measured origin, a MEASURED status, and a mechanism
    # that actually phenocopies what was done — on a SUPPORTING sign.
    support = (status in policy.MEASURED_EVIDENCE and origin_is_measured and phenocopy
               and sign_state == SIGN_SUPPORTS_DESIRED_CHANGE)
    return {
        "observed_perturbation_modality": modality,
        "observed_sign_state": sign_state,
        "desired_target_modulation": desired_target_modulation(modality, sign_state),
        "observed_compatible_action": observed_compatible_action(modality, sign_state),
        "untested_inverse_action": untested_inverse_action(modality, sign_state),
        "pharmacologic_reversibility_assumed": PHARMACOLOGIC_REVERSIBILITY_ASSUMED,
        "mechanism_match_status": match,
        "mechanism_phenocopies_modality": phenocopy,
        "intervention_effect": effect,
        "intervention_effect_reason": effect_reason,
        "evidence_relation": relation,
        "evidence_relation_caveat": caveat,
        "evidence_is_equivalence": EVIDENCE_IS_EQUIVALENCE,
        "directional_evidence_status": status,
        "directional_evidence_reason": reason,
        "observed_perturbation_support": support,
        "stage3_evidence_class": policy.evidence_class(status),
    }
