"""THE SIGN RULE — the functions. The tokens and gate names live in
:mod:`druglink.modality_contract`; the refusals on emitted rows in
:mod:`druglink.modality_gates_v2`. Bind :mod:`druglink.modality_v2`, the one front door.

Split at the 500-line gate. The rule itself is unchanged and is documented on
``modality_contract``.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

from . import direction as dr
from . import workflow as wf
from .modality_contract import *          # noqa: F401,F403
from .modality_contract import (          # noqa: F401
    ACTION_PHENOCOPY_EFFECTS,
    ARM_VALUE_IS_PRE_ORIENTED_BY_STAGE2,
    EVIDENCE_IS_EQUIVALENCE,
    EVIDENCE_RELATIONS,
    FIELD_ARM_VALUE,
    FIELD_EVALUABLE,
    FIELD_MODALITY,
    FIELD_MODULATION,
    FIELD_NAMESPACE,
    FIELD_PHENOCOPY_CLASS,
    GATE_EVALUABILITY_NOT_DECLARED,
    GATE_MODALITY_NOT_DECLARED,
    GATE_NAMESPACE_MISTYPED,
    GATE_NAMESPACE_NOT_DECLARED,
    GATE_NAMESPACE_VOCABULARY_DIVERGENCE,
    GATE_PHENOCOPY_CLASS_NOT_DECLARED,
    GATE_SERIALIZED_MODULATION_DISAGREES_WITH_THE_SIGN,
    GATE_SIGN_READ_FROM_AN_INFERRED_ROW,
    GATE_UNKNOWN_MODALITY,
    GATE_UNKNOWN_NAMESPACE,
    GATE_UNKNOWN_SERIALIZED_MODULATION,
    INVERSE_ACTION,
    INVERSE_CAVEAT,
    MATCH_ARM_NOT_EVALUABLE,
    MATCH_COMPATIBLE,
    MATCH_EFFECT_UNKNOWN,
    MATCH_NO_DIRECTIONAL_RESPONSE,
    MATCH_OPPOSES_OBSERVED_BENEFIT,
    MATCH_PHENOCOPIES_UNDESIRED,
    MATCH_STATUSES,
    MATCH_UNTESTED_INVERSE,
    MODALITY_PERFORMED_ACTION,
    MODALITY_V2_POLICY_VERSION,
    MODULATION_FOR,
    PHARMACOLOGIC_REVERSIBILITY_ASSUMED,
    PHENOCOPY_CAVEAT,
    PHENOCOPY_RELATION,
    PHENOCOPY_RELATIONS,
    RELATION_EFFECT_NOT_ENUMERATED,
    RELATION_UNTESTED_INVERSE,
    SIGN_EPS,
    SIGN_EPS_BASIS,
    SIGN_NO_DIRECTIONAL_RESPONSE,
    SIGN_NOT_EVALUABLE,
    SIGN_OPPOSES_DESIRED_CHANGE,
    SIGN_STATES,
    SIGN_SUPPORTS_DESIRED_CHANGE,
    TARGET_MODULATIONS,
    W3_NAMESPACES,
    W3_REQUIRED_ROW_FIELDS,
    ModalityError,
)


# --------------------------------------------------------------------------- #
# 1. The two facts, read separately.
# --------------------------------------------------------------------------- #
def declared_modality(record: Mapping[str, Any], *, arm_key: str) -> str:
    """What the screen DID. Declared by Stage 2, carried verbatim, NEVER defaulted.

    A default here would be the whole defect in miniature: assuming CRISPRi for a row that
    never said so means the compatible-mechanism set is chosen by Stage 3's guess about an
    experiment it did not run. A row that does not declare its modality is REFUSED, and the arm
    yields zero edges — "we never looked" must never become "we looked and found nothing".
    """
    modality = record.get(FIELD_MODALITY)
    if modality in (None, ""):
        raise ModalityError(
            GATE_MODALITY_NOT_DECLARED,
            f"arm {arm_key!r} carries a row with no {FIELD_MODALITY}. Without it there is "
            "nothing to phenocopy and no compatible-mechanism set to derive, and defaulting one "
            "would match drugs against an experiment nobody described")
    if str(modality) not in MODALITY_PERFORMED_ACTION:
        raise ModalityError(
            GATE_UNKNOWN_MODALITY,
            f"arm {arm_key!r} declares {FIELD_MODALITY}={modality!r}, which performs no target "
            f"action Stage 3 knows (declared: {sorted(MODALITY_PERFORMED_ACTION)}). The "
            "compatible-mechanism set FOLLOWS from the modality, so an unknown modality has no "
            "compatible mechanisms — and guessing one would match a drug to the wrong experiment")
    return str(modality)


def phenocopy_class_of(record: Mapping[str, Any], *, arm_key: str) -> str:
    """W3's OWN ``phenocopy_class``, carried VERBATIM. Bound, and deliberately NOT interpreted.

    Stage 3 requires the field (a row without it refuses the arm) and passes it through onto the
    edge for provenance. It does NOT branch on its value, because Stage 3 has not been told that
    vocabulary — and a closed vocabulary invented here would be exactly the fabricated contract
    this lane keeps finding. Stage-3's own per-edge judgment about whether a DRUG phenocopies the
    MODALITY is a separate, derived field (``evidence_relation``), computed from the frozen
    engine and never from this token.
    """
    value = record.get(FIELD_PHENOCOPY_CLASS)
    if value in (None, ""):
        raise ModalityError(
            GATE_PHENOCOPY_CLASS_NOT_DECLARED,
            f"arm {arm_key!r} carries a row with no {FIELD_PHENOCOPY_CLASS}. It is part of the "
            "typed row contract; a row that does not carry it is a row Stage 3 refuses, and the "
            "arm yields zero edges")
    return str(value)


def evaluable_of(record: Mapping[str, Any], *, arm_key: str) -> bool:
    """Stage-2's OWN evaluability. Absent is REFUSED, never read as False.

    ``bool(None)`` is ``False``, so a missing field would silently become "not evaluable" — a
    row nobody assessed, reported as one that was assessed and failed.
    """
    value = record.get("evaluable")
    if not isinstance(value, bool):
        raise ModalityError(
            GATE_EVALUABILITY_NOT_DECLARED,
            f"arm {arm_key!r} carries a row with evaluable={value!r}. Evaluability is Stage-2's "
            "finding, not Stage-3's default: a missing flag read as False would report a row "
            "nobody assessed as one that was assessed and found wanting")
    return value


def observed_sign_state(arm_value: Any, *, evaluable: bool,
                        origin_is_measured: bool, arm_key: str = "") -> str:
    """THE SIGN RULE. Stage-2's own, bound verbatim (Direct disposition / temporal estimand).

    The value arrives ALREADY oriented to its arm's ``desired_change``; a positive value means
    the perturbation moved the program the way THIS arm wants. Stage 3 never re-orients it.

    IT APPLIES ONLY TO A MEASURED LANE, AND THE GUARD IS HERE RATHER THAN AT THE CALL SITE.
    A pathway record is a GENE-SET ENRICHMENT (an enrichment value over a set, with a leading
    edge) — not a per-target knockdown effect. It has no CRISPRi sign to read. Reading one from
    it would take a SET-LEVEL statistic, hand it a sign it never had, and let it support a drug
    direction as though a knockdown had been measured on that gene: guilt by association wearing
    the costume of a measurement. So it is a NAMED REFUSAL, not a branch a caller may forget.
    """
    if not origin_is_measured:
        raise ModalityError(
            GATE_SIGN_READ_FROM_AN_INFERRED_ROW,
            f"arm {arm_key!r} asked for the CRISPRi sign of an INFERRED row (arm_value="
            f"{arm_value!r}). Nobody perturbed this node: a pathway record is a gene-set "
            "enrichment, not a measured per-target knockdown effect, and it carries no sign to "
            "read. A direction is never inherited from set membership")
    if not evaluable or arm_value is None:
        return SIGN_NOT_EVALUABLE
    value = float(arm_value)
    if value > SIGN_EPS:
        return SIGN_SUPPORTS_DESIRED_CHANGE
    if value < -SIGN_EPS:
        return SIGN_OPPOSES_DESIRED_CHANGE
    return SIGN_NO_DIRECTIONAL_RESPONSE


def check_serialized_modulation(record: Mapping[str, Any], sign_state: str, *,
                                modality: str, arm_key: str) -> str:
    """VERIFY the orientation against Stage-2's own token. Never ASSUME it, never obey it.

    Stage 2 derives the modulation from the same signed value Stage 3 re-derives the sign from,
    so the two must agree. If they do not, one of us has the orientation backwards — and a silent
    disagreement here is a whole release of drugs matched to the wrong direction. So the token is
    a CHECK, not an input: Stage 3 classifies from the SIGN it re-derived itself, and refuses the
    row outright if Stage-2's token says something else.

    The expected token is re-derived from :data:`MODULATION_FOR`, because the token's meaning
    depends on the MODALITY: "increase" means the perturbation SUPPORTED the desired change under
    CRISPRa, and OPPOSED it under CRISPRi. A modality-blind token table would be correct for one
    lane and quietly inverted for the other.
    """
    token = record.get(FIELD_MODULATION)
    if token in (None, ""):
        raise ModalityError(
            GATE_UNKNOWN_SERIALIZED_MODULATION,
            f"arm {arm_key!r} carries a row with no {FIELD_MODULATION}. It is part of the typed "
            "row contract, and Stage 3 re-derives the sign in order to CHECK it — with nothing "
            "to check against, an orientation flip upstream would pass unnoticed")
    if str(token) not in TARGET_MODULATIONS:
        raise ModalityError(
            GATE_UNKNOWN_SERIALIZED_MODULATION,
            f"arm {arm_key!r} carries {FIELD_MODULATION}={token!r}, which is not one of the "
            f"typed contract's tokens {list(TARGET_MODULATIONS)}. Reading an unknown term as "
            "'no direction' would make a vocabulary drift look exactly like a target that was "
            "examined and found directionless")
    expected = desired_target_modulation(modality, sign_state)
    if str(token) != expected:
        raise ModalityError(
            GATE_SERIALIZED_MODULATION_DISAGREES_WITH_THE_SIGN,
            f"arm {arm_key!r}: Stage 2 serialized {FIELD_MODULATION}={token!r}, but "
            f"arm_value={record.get(FIELD_ARM_VALUE)!r} with "
            f"evaluable={record.get(FIELD_EVALUABLE)!r} re-derives sign {sign_state!r} under "
            f"Stage-2's OWN rule (eps={SIGN_EPS!r}), which for modality {modality!r} means "
            f"{expected!r}. One of the two has the orientation backwards, and a disagreement "
            "admitted here is an entire release of drugs matched to the wrong direction")
    return str(token)


def desired_target_modulation(modality: str, sign_state: str) -> str:
    """What the OBSERVATION suggests doing to the target. From (modality, SIGN) — never modality
    alone. On an opposing sign it names what would be NEEDED; that is a refusal with a reason,
    not an activator lead."""
    return MODULATION_FOR.get((modality, sign_state), sign_state)


def observed_compatible_action(modality: str, sign_state: str) -> Optional[str]:
    """The target action the DATA supports. ONLY a supporting sign yields one.

    On an opposing sign the answer is None — not the inverse action. The inverse was never
    tested, and returning it here is precisely how an agonist becomes a recommendation.
    """
    if sign_state == SIGN_SUPPORTS_DESIRED_CHANGE:
        return MODALITY_PERFORMED_ACTION[modality]
    return None


def untested_inverse_action(modality: str, sign_state: str) -> Optional[str]:
    """On an OPPOSING sign, the action that WOULD be needed — labelled as untested, never
    ranked, and never a phenocopy of anything."""
    if sign_state == SIGN_OPPOSES_DESIRED_CHANGE:
        return INVERSE_ACTION[MODALITY_PERFORMED_ACTION[modality]]
    return None


def namespace_of(record: Mapping[str, Any], *, arm_key: str) -> str:
    """The row's OWN namespace token, asserted EXACTLY and returned VERBATIM. Never translated.

    PER TARGET ROW, NEVER PER RELEASE, and never guessed from the id's shape.
    """
    declared = record.get(FIELD_NAMESPACE)
    if declared in (None, ""):
        raise ModalityError(
            GATE_NAMESPACE_NOT_DECLARED,
            f"arm {arm_key!r} carries a target with no {FIELD_NAMESPACE}. A namespace-less id "
            "is a name, and names are not identities — the join is by exact typed identity and "
            "never degrades to a symbol match")
    if str(declared) not in W3_NAMESPACES:
        raise ModalityError(
            GATE_UNKNOWN_NAMESPACE,
            f"arm {arm_key!r} declares {FIELD_NAMESPACE}={declared!r}. The typed row contract "
            f"is exactly {list(W3_NAMESPACES)}. This is asserted, not normalised: coercing an "
            "unrecognised token into a known one would let a genuinely different namespace join "
            "a store that never covered it")
    return str(declared)


def check_store_namespace_vocabulary(store_namespaces: Iterable[str]) -> None:
    """THE TWO VOCABULARIES MUST BE ONE. A divergence is SURFACED, never translated away.

    W3 types its rows ``ensembl_gene_id`` / ``gene_symbol``. The admitted universe store types
    its own rows with ITS tokens. If they are not the same strings, the exact-typed join cannot
    be made — and the one thing Stage 3 must not do is quietly map between them, because an
    alias layer would absorb this divergence silently and every test would stay green while the
    two lanes drifted apart.

    So it REFUSES, by name, and the refusal names both vocabularies: one side has to change, and
    a human has to decide which. Fail closed — the arm yields zero edges.
    """
    held = sorted({str(n) for n in store_namespaces})
    if held and set(held) != set(W3_NAMESPACES):
        raise ModalityError(
            GATE_NAMESPACE_VOCABULARY_DIVERGENCE,
            f"the typed row contract names its namespaces {list(W3_NAMESPACES)}, but the "
            f"admitted universe store types its rows {held}. These are two vocabularies for the "
            "same identities, and Stage 3 will not translate between them: an alias layer is "
            "how two admitted artifacts drift apart while both look green. The join is refused "
            "until ONE vocabulary is agreed — either W3 serializes the store's tokens, or the "
            "store is re-extracted under W3's. Zero edges until then")


def check_namespace_against_store(target_id: str, namespace: str, *, arm_key: str,
                                  store_namespaces: Iterable[str]) -> None:
    """The row's DECLARED namespace must be the one the store actually holds this target in.

    If the store holds it under NONE, the target is simply outside the admitted universe — an
    honest absence, dispositioned as such. But if the store holds it under a DIFFERENT one, the
    row has MISTYPED it, and left alone that target would quietly miss the exact-typed join and
    be reported as "not in the admitted universe": a target the store DOES cover, reported as
    one it does not.
    """
    held = {str(n) for n in store_namespaces}
    if held and namespace not in held:
        raise ModalityError(
            GATE_NAMESPACE_MISTYPED,
            f"arm {arm_key!r} types target {target_id!r} as {namespace!r}, but the admitted "
            f"store holds it under {sorted(held)}. A gene SYMBOL declared as an Ensembl id (or "
            "the reverse) does not fail loudly — it misses the typed join and is then reported "
            "as a target outside the universe. A symbol may only ever join a symbol")


# --------------------------------------------------------------------------- #
# 2. The compatible mechanisms, DERIVED from the frozen engine. Never a typed list.
# --------------------------------------------------------------------------- #
def _engine_actions() -> tuple[str, ...]:
    """Every action type the FROZEN engine enumerates. Asked, never restated."""
    return tuple(sorted(dr.ACTION_ABUNDANCE_REDUCTION | dr.ACTION_FUNCTIONAL_INHIBITION
                        | dr.ACTION_FUNCTIONAL_ACTIVATION | dr.ACTION_EXPLICIT_UNKNOWN))


def phenocopying_actions(modality: str) -> tuple[str, ...]:
    """The drug action types that PHENOCOPY what this MODALITY did. Derived by asking the engine.

    Not a hand-typed list of drug words: each action is put through the frozen engine and kept
    only if its intervention effect is one the modality's own action is phenocopied by. Declare
    CRISPRa and this set becomes the activators, with no edit here.
    """
    effects = ACTION_PHENOCOPY_EFFECTS[MODALITY_PERFORMED_ACTION[modality]]
    return tuple(a for a in _engine_actions() if dr.intervention_effect(a)[0] in effects)


def phenocopies(action_type: Optional[str], modality: str) -> bool:
    """Does this sourced mechanism do to the PROTEIN what the modality did to the TRANSCRIPT?

    An INHIBITOR always phenocopies CRISPRi. An AGONIST never does — whatever the sign says.
    """
    effect = dr.intervention_effect(action_type)[0]
    return effect in ACTION_PHENOCOPY_EFFECTS[MODALITY_PERFORMED_ACTION[modality]]


def is_inverse_mechanism(action_type: Optional[str], modality: str) -> bool:
    """Does it do the OPPOSITE of what the modality did? (An agonist, on a CRISPRi arm.)"""
    effect = dr.intervention_effect(action_type)[0]
    inverse = INVERSE_ACTION[MODALITY_PERFORMED_ACTION[modality]]
    return effect in ACTION_PHENOCOPY_EFFECTS[inverse]


def evidence_relation(action_type: Optional[str], modality: str) -> tuple[str, str]:
    """(relation, caveat) for ONE mechanism against ONE modality. Honest, per edge.

    Only a mechanism that ACTUALLY phenocopies the modality wears the phenocopy label. An
    agonist on a CRISPRi arm phenocopies nothing that was tested, so it is labelled the untested
    inverse that it is — a field, not a footnote.
    """
    if phenocopies(action_type, modality):
        return PHENOCOPY_RELATION[modality], PHENOCOPY_CAVEAT
    if is_inverse_mechanism(action_type, modality):
        return RELATION_UNTESTED_INVERSE, INVERSE_CAVEAT
    return RELATION_EFFECT_NOT_ENUMERATED, PHENOCOPY_CAVEAT


# --------------------------------------------------------------------------- #
# 3. The classification. THE SIGN DECIDES; the modality only says what phenocopies what.
# --------------------------------------------------------------------------- #
def classify(*, action_type: Optional[str], modality: str, sign_state: str,
             origin_is_measured: bool) -> dict[str, Any]:
    """Classify ONE sourced mechanism against ONE arm row. Fail-closed.

    An incompatible mechanism is kept as an EXPLICIT non-match: it is emitted, it names its
    reason, and it never ranks. Dropping it would make "this drug does the opposite of what the
    data supports" indistinguishable from "no drug was found".
    """
    effect, effect_reason = dr.intervention_effect(action_type)
    relation, caveat = evidence_relation(action_type, modality)
    phenocopy = phenocopies(action_type, modality)
    inverse = is_inverse_mechanism(action_type, modality)

    if sign_state == SIGN_NOT_EVALUABLE:
        match, status, reason = (MATCH_ARM_NOT_EVALUABLE, wf.UNRESOLVED,
                                 wf.REASON_ARM_NOT_EVALUABLE)
    elif sign_state == SIGN_NO_DIRECTIONAL_RESPONSE:
        match, status, reason = (MATCH_NO_DIRECTIONAL_RESPONSE, wf.UNRESOLVED,
                                 wf.REASON_NO_DIRECTION)
    elif effect == dr.EFFECT_UNKNOWN:
        match, status, reason = (MATCH_EFFECT_UNKNOWN, wf.UNRESOLVED,
                                 wf.REASON_ACTION_UNKNOWN)
    elif sign_state == SIGN_SUPPORTS_DESIRED_CHANGE:
        if phenocopy:
            # The perturbation HELPED, and this drug does to the protein what the perturbation
            # did to the transcript. A PUTATIVE phenocopy — never an equivalence.
            match = MATCH_COMPATIBLE
            status, reason = ((wf.OBSERVED_PERTURBATION, wf.REASON_ACTION_MATCHES_TESTED)
                              if origin_is_measured
                              else (wf.PATHWAY_HYPOTHESIS, wf.REASON_PATHWAY_COMPATIBLE))
        else:
            # The perturbation helped, and this drug runs AGAINST it. Named, kept, never ranked.
            match, status, reason = (MATCH_OPPOSES_OBSERVED_BENEFIT, wf.OPPOSED,
                                     wf.REASON_ACTION_OPPOSES)
    else:                                    # SIGN_OPPOSES_DESIRED_CHANGE
        if phenocopy:
            # *** THE INHIBITOR-OPPOSED FLAG. ***
            # The inhibitor DOES phenocopy the knockdown — and the knockdown moved this arm the
            # WRONG way, so what it phenocopies is the UNDESIRED effect. This is the row the old
            # modality-fixed rule would have ranked as supported evidence.
            match, status, reason = (MATCH_PHENOCOPIES_UNDESIRED, wf.OPPOSED,
                                     wf.REASON_ACTION_OPPOSES)
        elif inverse:
            # *** THE ONE THAT MUST NEVER BE PROMOTED. ***
            # An agonist. It phenocopies NOTHING that was tested; it is the untested inverse of
            # a deleterious result. A labelled hypothesis — never observed support, never a
            # measurement's evidence class, and never a phenocopy.
            match, status, reason = (MATCH_UNTESTED_INVERSE, wf.INVERSE_DIRECTION_HYPOTHESIS,
                                     wf.REASON_INVERSE_ACTIVATION)
        else:
            match, status, reason = (MATCH_EFFECT_UNKNOWN, wf.UNRESOLVED,
                                     wf.REASON_ACTION_UNKNOWN)

    # Observed support requires ALL THREE: a measured origin, a MEASURED status, and a mechanism
    # that actually phenocopies what was done. The third is what the old rule lacked.
    support = (status in wf.MEASURED_EVIDENCE and origin_is_measured and phenocopy
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
        "stage3_evidence_class": wf.evidence_class(status),
    }


def vocabularies() -> dict[str, Any]:
    """The SIGN contract, hashed into the v2 bundle id."""
    return {
        "modality_v2_policy_version": MODALITY_V2_POLICY_VERSION,
        "sign_eps": repr(SIGN_EPS),
        "sign_eps_basis": SIGN_EPS_BASIS,
        "sign_states": list(SIGN_STATES),
        "arm_value_is_pre_oriented_by_stage2": ARM_VALUE_IS_PRE_ORIENTED_BY_STAGE2,
        "w3_required_row_fields": list(W3_REQUIRED_ROW_FIELDS),
        "w3_namespaces": list(W3_NAMESPACES),
        "modality_performed_action": dict(sorted(MODALITY_PERFORMED_ACTION.items())),
        "inverse_action": dict(sorted(INVERSE_ACTION.items())),
        "action_phenocopy_effects": {k: list(v)
                                     for k, v in sorted(ACTION_PHENOCOPY_EFFECTS.items())},
        "phenocopying_actions_by_modality": {
            m: list(phenocopying_actions(m)) for m in sorted(MODALITY_PERFORMED_ACTION)},
        "target_modulations": list(TARGET_MODULATIONS),
        "modulation_for": {f"{m}|{s}": v for (m, s), v in sorted(MODULATION_FOR.items())},
        "match_statuses": list(MATCH_STATUSES),
        "evidence_relations": list(EVIDENCE_RELATIONS),
        "phenocopy_relations": sorted(PHENOCOPY_RELATIONS),
        "evidence_is_equivalence": EVIDENCE_IS_EQUIVALENCE,
        "phenocopy_caveat": PHENOCOPY_CAVEAT,
        "inverse_caveat": INVERSE_CAVEAT,
        "pharmacologic_reversibility_assumed": PHARMACOLOGIC_REVERSIBILITY_ASSUMED,
        # The rule, stated so a reader need not re-derive it from the code.
        "the_modality_says_what_was_tested_the_sign_says_whether_it_helped": True,
        "the_target_modulation_is_never_derived_from_the_modality_alone": True,
        "an_inhibitor_on_an_opposing_row_is_flagged_opposed_never_dropped": True,
        "an_agonist_never_phenocopies_a_knockdown": True,
        "an_agonist_is_never_promoted_to_supported_evidence_by_sign_inversion": True,
        "an_opposing_sign_yields_no_observed_compatible_action": True,
        "a_pathway_enrichment_record_carries_no_crispri_sign": True,
        "the_sign_rule_applies_only_to_measured_lanes": True,
        "no_namespace_or_token_alias_layer_exists": True,
        "a_drug_on_a_protein_is_never_equivalent_to_silencing_a_transcript": True,
    }
