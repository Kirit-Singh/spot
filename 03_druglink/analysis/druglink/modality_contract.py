"""THE SIGN RULE. What was TESTED, and whether the test HELPED — two facts, never one.

THE DEFECT THIS MODULE EXISTS TO PREVENT
----------------------------------------
An earlier build of this file mapped the MODALITY straight to a target action::

    MODALITY_TO_MODULATION = {"CRISPRi knockdown": "decrease/inhibit target"}

and argued that "the modulation is FIXED by the modality — inhibit the target in EVERY arm".
It is not, and that rule is a **directional inversion**. It never reads the SIGN, so a gene
whose knockdown moved the program the WRONG way is still matched to inhibitors and ranked as
SUPPORTED evidence — recommending that we inhibit a target the data says inhibition makes
WORSE. It would look rigorous, every hash would verify, and the suite would be green.

So the two facts are kept in SEPARATE fields, and neither is ever converted into the other:

    observed_perturbation_modality   what the screen DID          "CRISPRi_knockdown"
    observed_sign_state              whether doing it HELPED      (from the SIGNED arm_value)

THE RULE, BOUND FROM STAGE 2 — NOT INVENTED HERE
------------------------------------------------
Stage-2 already derives this, twice, and Stage 3 binds their rule rather than writing a third:

  Direct   ``direct/disposition.py::desired_modulation(arm_value, evaluable)``
  temporal ``direct/temporal/arms/arm_estimand.py::target_modulation(arm_value, evaluable)``

Both say the same thing, and the temporal lane says it in words:

    "The perturbation is a CRISPRi KNOCKDOWN. So a POSITIVE arm value (the knockdown moved the
     program in the arm's desired direction) SUGGESTS that INHIBITING the target would support
     that desired change. A NEGATIVE value is OPPOSED: achieving the desired change would
     require ACTIVATING the target — the opposite of a knockdown — and **this screen cannot
     speak to whether a drug could do that, so pharmacologic reversibility is NOT assumed**."

The arm value arrives ALREADY ORIENTED to its own arm's ``desired_change`` — that is Stage-2's
per-arm convention, verified in their bytes, and it is why Stage 3 must NOT re-orient by
``desired_change`` (doing so would apply the orientation twice and flip half the release).

    evaluable is false / arm_value is null   ->  not_evaluable
    |arm_value| <= SIGN_EPS                  ->  no_directional_response
    arm_value  >  SIGN_EPS                   ->  the perturbation SUPPORTS the desired change
    arm_value  < -SIGN_EPS                   ->  the perturbation OPPOSES the desired change

THE TWO SENTENCES THAT GOVERN THE CODE BELOW
--------------------------------------------
**An inhibitor ALWAYS phenocopies CRISPRi — but on a NEGATIVE row it phenocopies the UNDESIRED
effect.** So a negative row does not become an "activate" recommendation. It becomes an
explicit INHIBITOR-OPPOSED flag: the drug is kept, it is named, and it never ranks.

**An agonist NEVER phenocopies CRISPRi.** On a negative row it is only the UNTESTED INVERSE of
a deleterious result — a hypothesis about an experiment nobody ran. It is never promoted to
supported evidence by sign inversion alone, and it never wears a phenocopy label. Presenting it
as a phenocopy would be the worst thing this pipeline could emit, so it is refused BY NAME
(:data:`GATE_NON_PHENOCOPY_IN_SUPPORTED_EVIDENCE`) on the emitted rows — not merely avoided in
the builder.

NOTHING IS HARDCODED TO CRISPRi
-------------------------------
The modality is DECLARED. What each modality DOES to the target
(:data:`MODALITY_PERFORMED_ACTION`) is a small, gated table, and the compatible-mechanism set
FOLLOWS from it by asking the frozen engine (:mod:`druglink.direction`) what each drug action
does. Declare CRISPRa and the phenocopying set becomes the ACTIVATORS, with no edit here.

PHENOCOPY IS NOT EQUIVALENCE
---------------------------
A drug inhibiting a PROTEIN is not CRISPRi silencing a TRANSCRIPT: they differ in modality
(protein vs mRNA), degree (partial occupancy vs knockdown), timing and off-target profile.
Every edge carries its relation and the caveat as FIELDS — Stage 4 reads fields, not docstrings
— and a suggestive signal may SUGGEST but never CONFIRM.
"""
from __future__ import annotations


from . import direction as dr

MODALITY_V2_POLICY_VERSION = "stage3-modality-v2-observed-sign"

# --------------------------------------------------------------------------- #
# EPSILON. Declared, named, and BOUND FROM UPSTREAM — never a magic number in a compare.
# --------------------------------------------------------------------------- #
# Stage-2 Direct declares the sign tolerance ONCE, in `direct/config.py`, and applies it in
# `disposition.desired_modulation` (`arm_value > SIGN_EPS` / `< -SIGN_EPS`). Stage 3 consumes
# the arm values that rule produced, so it uses that same tolerance: a Stage-3 epsilon of its
# own would draw the zero band in a different place from the lane that computed the numbers,
# and rows in the gap would carry a direction one stage believes and the other denies.
#
# It is NOT retuned here, and it is not a threshold on effect SIZE — it is a guard against
# calling floating-point noise a direction. The temporal lane's own rule compares against exact
# zero; Stage 3's band is a strict SUPERSET of that zero, so where the two differ Stage 3 is
# the more conservative of the pair: it declines a direction the temporal lane would allow, and
# never grants one the temporal lane would refuse.
SIGN_EPS = 1e-9
SIGN_EPS_BASIS = (
    "stage-2 direct config.SIGN_EPS=1e-9, the tolerance the arm values were computed under "
    "(direct/disposition.py::desired_modulation). Bound, not retuned, and not a threshold on "
    "effect size: it is the band within which a float's sign carries no information.")

# --------------------------------------------------------------------------- #
# THE OBSERVED SIGN STATE. Modality-free: it says only what the perturbation DID to the arm.
# --------------------------------------------------------------------------- #
SIGN_NOT_EVALUABLE = "not_evaluable"
SIGN_NO_DIRECTIONAL_RESPONSE = "no_directional_response"
SIGN_SUPPORTS_DESIRED_CHANGE = "perturbation_supports_the_desired_change"
SIGN_OPPOSES_DESIRED_CHANGE = "perturbation_opposes_the_desired_change"
SIGN_STATES = (SIGN_NOT_EVALUABLE, SIGN_NO_DIRECTIONAL_RESPONSE,
               SIGN_SUPPORTS_DESIRED_CHANGE, SIGN_OPPOSES_DESIRED_CHANGE)

# The arm value is ALREADY oriented to its own arm's desired_change by Stage 2. Stage 3 states
# that it verified this rather than assuming it, and never re-orients.
ARM_VALUE_IS_PRE_ORIENTED_BY_STAGE2 = True

# --------------------------------------------------------------------------- #
# THE W3 ROW CONTRACT. ONE typed schema, asserted by EXACT TOKEN. No alias layer.
#
# These are the field names and the token spellings W3 SERIALIZES. They are not normalised, not
# aliased, and not "accepted in either spelling". An alias layer is how two lanes drift apart
# while both look green: it absorbs the divergence silently and nobody ever learns the contract
# broke. An unexpected token is a NAMED REFUSAL — never a coercion, never a best-effort mapping.
# --------------------------------------------------------------------------- #
FIELD_MODALITY = "observed_perturbation_modality"
FIELD_NAMESPACE = "target_id_namespace"
FIELD_MODULATION = "desired_target_modulation"
FIELD_PHENOCOPY_CLASS = "phenocopy_class"
FIELD_ARM_VALUE = "arm_value"
FIELD_EVALUABLE = "evaluable"
# Every typed field W3 must serialize for an arm to yield a single edge. A row missing ANY of
# them refuses the arm; the arm yields ZERO edges. Nothing here is synthesized.
W3_REQUIRED_ROW_FIELDS = (FIELD_MODALITY, FIELD_NAMESPACE, FIELD_MODULATION,
                          FIELD_PHENOCOPY_CLASS, FIELD_EVALUABLE)

# THE MODALITY. Declared by Stage 2, carried VERBATIM, and standing alone.
MODALITY_CRISPRI = "CRISPRi_knockdown"          # UNDERSCORE. W3's exact token.
MODALITY_CRISPRA = "CRISPRa_activation"

# WHAT THE MODALITY DID TO THE TARGET. The one declared table, and the only place a modality is
# translated into an action. It is never derived from the program, and never from the sign.
ACTION_INHIBIT = "inhibit_target"
ACTION_ACTIVATE = "activate_target"
MODALITY_PERFORMED_ACTION = {
    MODALITY_CRISPRI: ACTION_INHIBIT,
    MODALITY_CRISPRA: ACTION_ACTIVATE,
}
INVERSE_ACTION = {ACTION_INHIBIT: ACTION_ACTIVATE, ACTION_ACTIVATE: ACTION_INHIBIT}

# The drug intervention effects that PHENOCOPY each action, expressed in the FROZEN engine's own
# effect vocabulary so no drug word is restated here.
ACTION_PHENOCOPY_EFFECTS = {
    ACTION_INHIBIT: (dr.ABUNDANCE_REDUCTION, dr.FUNCTIONAL_INHIBITION),
    ACTION_ACTIVATE: (dr.FUNCTIONAL_ACTIVATION,),
}

# --------------------------------------------------------------------------- #
# THE DESIRED TARGET MODULATION. W3's four tokens — EXACTLY these, and no others.
#
# They name a direction ON THE TARGET, and are therefore modality-INDEPENDENT: "decrease" says
# lowering this target is what the data supports, whatever experiment established that. So the
# same four tokens serve CRISPRa without inventing a second vocabulary — only the SIGN->TOKEN
# mapping turns on the modality, which is exactly the fact the modality is allowed to decide.
# --------------------------------------------------------------------------- #
MOD_DECREASE = "decrease"
MOD_INCREASE = "increase"
MOD_NO_DIRECTION = "no_direction_evidence"
MOD_NOT_EVALUATED = "not_evaluated"
TARGET_MODULATIONS = (MOD_DECREASE, MOD_INCREASE, MOD_NO_DIRECTION, MOD_NOT_EVALUATED)

# (modality, sign) -> the token. The MODALITY says which target action was performed; the SIGN
# says whether performing it helped. Only both together name a direction.
#
#   CRISPRi (it LOWERED the target):  helped -> "decrease"   harmed -> "increase"
#   CRISPRa (it RAISED the target):   helped -> "increase"   harmed -> "decrease"
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

# *** WHAT ``increase`` IS, AND WHAT IT IS NOT. ***
#
# On a CRISPRi arm, "increase" says: to get the desired program change you would have to RAISE
# this target — the OPPOSITE of the knockdown that was actually performed. It is a statement
# about an experiment NOBODY RAN. It is the single field most likely to be misread as "match
# agonists", and it must not be. The screen cannot say a drug could raise anything, so
# pharmacologic reversibility is NOT assumed, and an "increase" row NEVER licenses supported
# agonism — it licenses an explicitly-labelled, non-rankable inverse hypothesis and nothing more.
PHARMACOLOGIC_REVERSIBILITY_ASSUMED = False

# NOTE: there is deliberately NO second token->sign map. The token's meaning is MODALITY-
# DEPENDENT — "increase" means the perturbation SUPPORTED the arm under CRISPRa and OPPOSED it
# under CRISPRi — so a modality-blind map would be right for one lane and silently inverted for
# the other. The check below re-derives the expected token from MODULATION_FOR instead: ONE map,
# which cannot disagree with itself.

# --------------------------------------------------------------------------- #
# PHENOCOPY, NOT EQUIVALENCE — and only where a phenocopy actually exists.
# --------------------------------------------------------------------------- #
PHENOCOPY_RELATION = {
    MODALITY_CRISPRI: "putative_crispri_phenocopy",
    MODALITY_CRISPRA: "putative_crispra_phenocopy",
}
PHENOCOPY_RELATIONS = frozenset(PHENOCOPY_RELATION.values())

# A mechanism that does NOT phenocopy the declared modality gets an HONEST relation, never the
# phenocopy label. An agonist on a CRISPRi arm phenocopies nothing that was tested — calling it
# a "putative_crispri_phenocopy" would assert exactly the equivalence this lane refuses.
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

# --------------------------------------------------------------------------- #
# How ONE sourced mechanism stands to the arm. Every non-match is EXPLICIT and carries a reason.
# --------------------------------------------------------------------------- #
MATCH_COMPATIBLE = "phenocopies_the_perturbation_that_helped"
MATCH_PHENOCOPIES_UNDESIRED = "phenocopies_the_perturbation_that_harmed"   # INHIBITOR-OPPOSED
MATCH_UNTESTED_INVERSE = "untested_inverse_direction_never_supported"
MATCH_OPPOSES_OBSERVED_BENEFIT = "runs_against_the_perturbation_that_helped"
MATCH_EFFECT_UNKNOWN = "mechanism_effect_unknown"
MATCH_NO_DIRECTIONAL_RESPONSE = "arm_shows_no_directional_response"
MATCH_ARM_NOT_EVALUABLE = "arm_not_evaluable"
MATCH_STATUSES = (MATCH_COMPATIBLE, MATCH_PHENOCOPIES_UNDESIRED, MATCH_UNTESTED_INVERSE,
                  MATCH_OPPOSES_OBSERVED_BENEFIT, MATCH_EFFECT_UNKNOWN,
                  MATCH_NO_DIRECTIONAL_RESPONSE, MATCH_ARM_NOT_EVALUABLE)

# --------------------------------------------------------------------------- #
# THE NAMESPACE. PER ROW, NEVER PER RELEASE — and asserted by EXACT TOKEN.
#
# The admitted universe is HETEROGENEOUS: 11,522 Ensembl gene ids and 4 gene SYMBOLS (recounted
# from the store's own bytes, never quoted from a memo). One release-level token stamped across
# every row would type those four symbols as Ensembl ids — a SILENT MISTYPING of target
# identity. A release-level default is not a safer inference than a string-shape guess; it is
# the same guess, made once and applied everywhere. So the token is read from the ROW.
#
# THERE IS NO TRANSLATION MAP HERE, DELIBERATELY. The retired one folded `ensembl_gene_id` into
# `ensembl_gene`, which is exactly the alias layer that lets two vocabularies drift apart while
# every test stays green. W3's tokens ARE the vocabulary, end to end — including in the join
# against the universe store.
# --------------------------------------------------------------------------- #
W3_NS_ENSEMBL_GENE_ID = "ensembl_gene_id"
W3_NS_GENE_SYMBOL = "gene_symbol"
W3_NAMESPACES = (W3_NS_ENSEMBL_GENE_ID, W3_NS_GENE_SYMBOL)

# --------------------------------------------------------------------------- #
# Named gates. Every refusal cites one, so it can be grepped, tested and quoted.
# --------------------------------------------------------------------------- #
GATE_MODALITY_NOT_DECLARED = "stage2_declared_no_observed_perturbation_modality_for_this_row"
GATE_UNKNOWN_MODALITY = "the_declared_perturbation_modality_performs_no_known_target_action"
GATE_EVALUABILITY_NOT_DECLARED = "stage2_declared_no_evaluability_for_this_row"
GATE_NAMESPACE_NOT_DECLARED = "stage2_declared_no_target_id_namespace_for_this_row"
GATE_UNKNOWN_NAMESPACE = "the_declared_target_id_namespace_is_not_a_typed_contract_namespace"
GATE_NAMESPACE_VOCABULARY_DIVERGENCE = \
    "the_row_contract_and_the_universe_store_name_their_namespaces_differently"
GATE_NAMESPACE_MISTYPED = "a_target_is_typed_in_a_namespace_the_store_does_not_hold_it_in"
GATE_PHENOCOPY_CLASS_NOT_DECLARED = "stage2_declared_no_phenocopy_class_for_this_row"
GATE_NO_EVIDENCE_RELATION = "an_edge_does_not_declare_its_relation_to_the_perturbation"
GATE_CLAIMS_EQUIVALENCE = "an_edge_claims_the_drug_is_EQUIVALENT_to_the_perturbation"
GATE_SIGN_READ_FROM_AN_INFERRED_ROW = \
    "a_crispri_sign_was_read_from_a_pathway_enrichment_row_that_has_none"
GATE_INFERRED_ORIGIN_PRODUCED_A_DRUG_EDGE = \
    "a_pathway_enrichment_record_produced_a_measured_drug_direction"
GATE_HIT_COUNT_COUNTED_ROWS_NOT_RANKS = "a_hit_count_counted_rows_not_ranks"

# THE ONES THAT GUARD THE SIGN. These are the defect, named.
GATE_MODULATION_DERIVED_FROM_MODALITY_ALONE = \
    "the_target_modulation_was_derived_from_the_modality_without_the_observed_sign"
GATE_NON_PHENOCOPY_IN_SUPPORTED_EVIDENCE = \
    "a_mechanism_that_does_not_phenocopy_the_declared_modality_reached_supported_evidence"
GATE_SUPPORTED_ON_A_NON_SUPPORTING_SIGN = \
    "an_edge_claims_observed_support_on_a_row_whose_sign_does_not_support_the_desired_change"
GATE_SERIALIZED_MODULATION_DISAGREES_WITH_THE_SIGN = \
    "stage2s_own_modulation_token_disagrees_with_the_sign_of_the_value_it_was_derived_from"
GATE_UNKNOWN_SERIALIZED_MODULATION = \
    "the_row_carries_a_modulation_token_from_neither_stage2_lane_vocabulary"


class ModalityError(ValueError):
    """A named, fail-closed refusal. The arm produces ZERO edges."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"[{gate}] {message}")
        self.gate = gate
