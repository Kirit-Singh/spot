"""THE STAGE-2 -> STAGE-3 ROW CONTRACT: what was DONE, what was OBSERVED, what is IMPLIED.

THE INVERSION THIS EXISTS TO MAKE IMPOSSIBLE
--------------------------------------------
The arm key carries ``desired_change=increase|decrease``. That is the direction of the
**PROGRAM**. The perturbation that produced every number in this release is a **CRISPRi
knockdown** — the target was only ever pushed DOWN. If Stage 3 reads the arm's
``desired_change=increase`` as "we want more of this target", it will go looking for
**agonists** when the evidence says *knocking the gene down* raised the program. That is a
180-degree inversion of the pharmacology, and it is one field-name collision away at all
times: the Direct producer's own column allowlist already contains a per-pole
``{pole}_desired_target_modulation``, and a BARE ``desired_target_modulation`` sits in its
FORBIDDEN_LEGACY_COLUMNS. Two things called by one name is how the wrong one gets read.

So this row states all three SEPARATELY, and never lets one be inferred from another:

    observed_perturbation_modality   WHAT WAS DONE.    CRISPRi_knockdown. A constant, taken
                                     from the run's provenance, not from a row.
    program_effect_direction         THE PROGRAM AXIS. increase | decrease. The arm's own
                                     desired_change — a statement about the PROGRAM.
    desired_target_modulation        WHAT IS IMPLIED FOR A DRUG. Re-derived from the ORIENTED
                                     arm value + evaluability, never from the program axis.

THE SIGN RULE (the producer's, not a new one)
---------------------------------------------
The arm value is ORIENTED: positive means the knockdown moved the program in THAT ARM'S OWN
desired direction. So, per ``disposition.desired_modulation`` (Direct) and
``est.target_modulation`` (temporal), which this module re-derives independently:

    value >  +eps   ->  decrease              knockdown moved the program the desired way
                                              => INHIBITION IS OBSERVED-COMPATIBLE. This is
                                              the ONLY class that is a putative CRISPRi
                                              phenocopy, and the only one rankable as
                                              SUPPORTED.
    value <  -eps   ->  increase              knockdown moved the program the WRONG way
                                              => AN INHIBITOR IS OPPOSED by the observation.
                                              "Activate it instead" is an UNTESTED
                                              INVERSE-DIRECTION HYPOTHESIS: no CRISPRa arm
                                              was ever run, nothing was observed to be
                                              phenocopied, and it is NOT supported evidence.
                                              An agonist may never be promoted from a sign
                                              inversion alone.
    |value| <= eps  ->  no_direction_evidence
    not evaluable   ->  not_evaluated

A CRISPRi phenocopy is a PHENOCOPY, never an EQUIVALENCE: an inhibitor is not a knockdown.
Every claim leaving Stage 2 is tagged as such and cannot be un-tagged downstream.

TARGET IDENTITY IS DECLARED, NEVER SNIFFED
------------------------------------------
The perturbed universe is 11,526 targets: 11,522 Ensembl accessions and FOUR bare gene
symbols — MTRNR2L1, MTRNR2L4, MTRNR2L8, OCLM. Three of those four carry an ENSG-looking
RELEASE KEY that belongs to a DIFFERENT GENE (``identity.py``, verified against all 33,983
released dispositions). So a namespace guessed from the shape of a string — "it starts with
ENSG, so it is an Ensembl id" — attaches the wrong gene to a mask and then to a drug.

``target_id_namespace`` is therefore a REQUIRED, DECLARED field, checked against the
release's own target universe. A target whose namespace cannot be resolved from the source
is ``unresolved_target_identity`` and is REFUSED — Stage 3 must refuse it too, and must
never silently drop it, because a dropped row and a row that was never there look identical.
"""
from __future__ import annotations

from typing import Any, Optional

# --------------------------------------------------------------------------- #
# WHAT WAS DONE. The one perturbation behind every number in this release.
# `config.CRISPRI_MODALITY` in the Direct producer; pinned here and PIN-TESTED against it,
# so a producer that changed its modality could not quietly disagree with this contract.
# --------------------------------------------------------------------------- #
OBSERVED_PERTURBATION_MODALITY = "CRISPRi_knockdown"

# ...and what that perturbation does TO THE TARGET. A knockdown only ever pushes the target
# DOWN. This is a property of the ASSAY, so it is a constant on every row — it is NOT the
# implied drug direction, and the two must never be collapsed into one field.
PERTURBATION_TARGET_EFFECT = "target_transcript_reduced"

# The claim a drug match may carry. NEVER "equivalence": an inhibitor is not a knockdown.
PHENOCOPY_CLAIM = "putative_crispri_phenocopy"

# --------------------------------------------------------------------------- #
# THE PROGRAM AXIS. The arm's own `desired_change`. A statement about the PROGRAM.
# --------------------------------------------------------------------------- #
PROGRAM_INCREASE = "increase"
PROGRAM_DECREASE = "decrease"
PROGRAM_EFFECT_DIRECTIONS = (PROGRAM_INCREASE, PROGRAM_DECREASE)

# --------------------------------------------------------------------------- #
# THE IMPLIED DRUG DIRECTION. The producers' own MOD_* tokens (disposition.py), byte for
# byte — a fifth vocabulary for the same four states would be a fifth chance to mismap them.
# --------------------------------------------------------------------------- #
MOD_DECREASE = "decrease"
MOD_INCREASE = "increase"
MOD_NO_DIRECTION = "no_direction_evidence"
MOD_NOT_EVALUATED = "not_evaluated"
MODULATIONS = (MOD_DECREASE, MOD_INCREASE, MOD_NO_DIRECTION, MOD_NOT_EVALUATED)

# `config.SIGN_EPS`. Below this there is no sign, and therefore no direction evidence.
SIGN_EPS = 1e-9

# --------------------------------------------------------------------------- #
# WHAT STAGE 3 IS ALLOWED TO DO WITH EACH. This is the whole point of the row.
# --------------------------------------------------------------------------- #
INHIBITION_COMPATIBLE = "inhibition_observed_compatible"
INHIBITOR_OPPOSED = "inhibitor_opposed"
NO_DIRECTIONAL_RESPONSE = "no_directional_response"
NOT_EVALUABLE = "not_evaluable"

PHENOCOPY_CLASS_OF = {
    MOD_DECREASE: INHIBITION_COMPATIBLE,
    MOD_INCREASE: INHIBITOR_OPPOSED,
    MOD_NO_DIRECTION: NO_DIRECTIONAL_RESPONSE,
    MOD_NOT_EVALUATED: NOT_EVALUABLE,
}

# The ONE class an inhibitory / downregulating mechanism may be matched to, and the ONE class
# that may be ranked as supported. Everything else is carried, labelled, and not acted on.
STAGE3_MATCHING_POLICY = {
    "policy_id": "spot.stage02.stage3_row.crispri_phenocopy_matching.v1",
    "observed_perturbation_modality": OBSERVED_PERTURBATION_MODALITY,
    "claim_strength": PHENOCOPY_CLAIM,
    "claim_is_equivalence": False,
    "inhibitory_or_downregulating_mechanisms_may_match": [INHIBITION_COMPATIBLE],
    "rankable_as_supported": [INHIBITION_COMPATIBLE],
    "must_flag_opposition": [INHIBITOR_OPPOSED],
    # The load-bearing refusal. There was no CRISPRa arm; nothing observed an activation.
    "agonist_promotion_from_sign_inversion": False,
    "agonist_promotion_rule": (
        "a negative arm value OPPOSES an inhibitor; it does not SUPPORT an agonist. "
        "Activation is an untested inverse-direction hypothesis — no CRISPRa arm was run, so "
        "there is no observation for an agonist to phenocopy, and it may never be ranked as "
        "supported evidence on the strength of a sign inversion alone"),
    "unresolved_namespace": "refuse_never_silently_drop",
}

# --------------------------------------------------------------------------- #
# TARGET IDENTITY. `identity.py`'s enum, byte for byte.
# --------------------------------------------------------------------------- #
ENSEMBL_GENE_ID = "ensembl_gene_id"
GENE_SYMBOL = "gene_symbol"
NAMESPACES = (ENSEMBL_GENE_ID, GENE_SYMBOL)
UNRESOLVED_IDENTITY = "unresolved_target_identity"

# The four targets that are NOT Ensembl accessions, from the release itself. Held here as a
# DOCUMENTED EXPECTATION for the pin test — never as the source a row's namespace is read
# from. The source manifest is the source; this is how we notice if it ever stops being.
KNOWN_SYMBOL_TARGETS = ("MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM")
EXPECTED_UNIVERSE = {"n_targets": 11526, "n_ensembl": 11522, "n_symbol": 4}

# --------------------------------------------------------------------------- #
# THE THREE NATIVE RANKING-ROW SHAPES. Three lanes, three names for the value.
#
# Direct writes `value`, temporal writes `arm_value`, pathway writes `score`. Reading any one
# of those names on all three lanes finds the number on ONE lane and None on the other two —
# and a None arm value derives `not_evaluated`, which is a silent, plausible, wrong answer.
# Pathway's rankings carry NO `evaluable` field at all: only ranked targets are present, so
# evaluability is true BY CONSTRUCTION there, and is asserted rather than read.
# --------------------------------------------------------------------------- #
NATIVE_ROW = {
    "direct": {"value_field": "value", "evaluable_field": "evaluable",
               "modulation_field": None, "rows_are_ranked_only": False},
    "temporal": {"value_field": "arm_value", "evaluable_field": "evaluable",
                 # temporal ALREADY ships this, and its own verifier already re-derives it.
                 "modulation_field": "desired_target_modulation",
                 "rows_are_ranked_only": False},
    "pathway": {"value_field": "score", "evaluable_field": None,
                "modulation_field": None, "rows_are_ranked_only": True},
}

ROW_SCHEMA = "spot.stage02_stage3_row.v1"
ROW_RULE_ID = "spot.stage02.stage3_row.direction_and_namespace.v1"

REQUIRED_ROW_FIELDS = (
    "schema_version", "arm_key", "program_id", "target_id", "target_id_namespace",
    "observed_perturbation_modality", "perturbation_target_effect",
    "program_effect_direction", "desired_target_modulation", "phenocopy_class",
    "arm_value", "evaluable", "rank",
)


class RowContractError(ValueError):
    """A row cannot be handed to Stage 3. Refuse; never repair, and never drop."""


# --------------------------------------------------------------------------- #
# THE RE-DERIVATIONS. Pure, and the only place a direction is ever decided.
# --------------------------------------------------------------------------- #
def desired_target_modulation(arm_value: Optional[float], *, evaluable: bool) -> str:
    """The drug direction IMPLIED by ONE arm value, under CRISPRi knockdown.

    From the ORIENTED value and evaluability ONLY. It never sees the program direction —
    that is exactly the input whose influence would produce the inversion.
    """
    if not evaluable or arm_value is None:
        return MOD_NOT_EVALUATED
    value = float(arm_value)
    if value > SIGN_EPS:
        return MOD_DECREASE          # knockdown moved the program the desired way
    if value < -SIGN_EPS:
        return MOD_INCREASE          # ...and this is NOT an agonist recommendation
    return MOD_NO_DIRECTION


def phenocopy_class(modulation: str) -> str:
    """What Stage 3 may DO with this row. Total over the enum; never defaults."""
    if modulation not in PHENOCOPY_CLASS_OF:
        raise RowContractError(
            f"modulation {modulation!r} is not one of {list(MODULATIONS)}; a direction "
            "nobody can read is not a direction anybody may prescribe against")
    return PHENOCOPY_CLASS_OF[modulation]


def is_supported(row: dict[str, Any]) -> bool:
    """SUPPORTED = an inhibitor phenocopies what was actually observed. Nothing else is."""
    return row.get("phenocopy_class") == INHIBITION_COMPATIBLE


def build_row(*, lane: str, native: dict[str, Any], arm_key: str, program_id: str,
              program_effect_direction: str, namespace_of: dict[str, str],
              context: dict[str, Any]) -> dict[str, Any]:
    """ONE Stage-2 -> Stage-3 row, from ONE native ranking row.

    ``namespace_of`` is the release's own target universe: target_id -> namespace. It is the
    ONLY source of a namespace. A target that is not in it is REFUSED, never sniffed.
    """
    spec = NATIVE_ROW.get(lane)
    if spec is None:
        raise RowContractError(f"{lane!r} is not a lane with a known native row shape")
    if program_effect_direction not in PROGRAM_EFFECT_DIRECTIONS:
        raise RowContractError(
            f"program_effect_direction {program_effect_direction!r} is not one of "
            f"{list(PROGRAM_EFFECT_DIRECTIONS)}")

    target_id = native.get("target_id")
    if target_id is None:
        raise RowContractError(f"[{lane}] a ranking row with no target_id")

    # THE NAMESPACE. Declared by the source, never inferred from the string's shape: three of
    # the four symbol targets carry an ENSG-looking release key belonging to a DIFFERENT gene.
    namespace = namespace_of.get(str(target_id))
    if namespace is None:
        raise RowContractError(
            f"[{lane}] {target_id}: {UNRESOLVED_IDENTITY} — this target is not in the "
            "release's target universe, so its namespace cannot be resolved. It is REFUSED, "
            "not guessed from the shape of its id and not silently dropped")
    if namespace not in NAMESPACES:
        raise RowContractError(
            f"[{lane}] {target_id}: namespace {namespace!r} is not one of {list(NAMESPACES)}")

    value = native.get(spec["value_field"])
    # Pathway ranks only what it could rank, so an unranked row cannot appear there at all.
    evaluable = (True if spec["evaluable_field"] is None
                 else bool(native.get(spec["evaluable_field"])))

    modulation = desired_target_modulation(value, evaluable=evaluable)

    # If the lane already ships a modulation, it must AGREE with the re-derivation. A lane
    # that says one thing while its own number says another is the bug this row exists for.
    shipped = native.get(spec["modulation_field"]) if spec["modulation_field"] else None
    if shipped is not None and shipped != modulation:
        raise RowContractError(
            f"[{lane}] {target_id}: the bundle ships desired_target_modulation={shipped!r}, "
            f"but its own arm value {value!r} re-derives {modulation!r}")

    return {
        "schema_version": ROW_SCHEMA,
        "rule_id": ROW_RULE_ID,
        "lane": lane,
        "arm_key": arm_key,
        "program_id": program_id,
        "context": dict(context),
        # WHO the target is — declared, and carrying its namespace with it
        "target_id": str(target_id),
        "target_id_namespace": namespace,
        # WHAT WAS DONE (the assay), kept separate from everything it implies
        "observed_perturbation_modality": OBSERVED_PERTURBATION_MODALITY,
        "perturbation_target_effect": PERTURBATION_TARGET_EFFECT,
        # THE PROGRAM AXIS — a statement about the program, not about the target
        "program_effect_direction": program_effect_direction,
        # ...and WHAT IS IMPLIED FOR A DRUG, re-derived from the oriented value alone
        "desired_target_modulation": modulation,
        "phenocopy_class": phenocopy_class(modulation),
        "phenocopy_claim": PHENOCOPY_CLAIM,
        "claim_is_equivalence": False,
        # the signed evidence itself, and whether it could be ranked at all
        "arm_value": value,
        "evaluable": evaluable,
        "rank": native.get("rank"),
    }
