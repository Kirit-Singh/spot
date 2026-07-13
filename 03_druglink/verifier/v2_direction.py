"""The FROZEN Stage-3 direction + workflow vocabulary, RESTATED for the verifier.

Imports NOTHING from ``druglink``. Split out of :mod:`verifier.v2_contract` at the 500-line
gate — the same seam the producer draws between ``direction``/``workflow`` (what the evidence
IS) and the artifact contract (what the bundle must LOOK like).

The digest is recomputed from THIS restatement and never read off the bundle, so a silent
reclassification is loud: move an action type between sets and the digest moves with it,
instead of a drug quietly starting to rank.
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any, Optional

from . import policy
from . import v2_admission as v2

ANALYSIS = "analysis"


class VerifierContractError(ValueError):
    """A value has no representation the restated contract can address."""


# --------------------------------------------------------------------------- #
# The FROZEN direction vocabulary, restated. The digest is recomputed from THIS
# restatement — never read off the bundle — so a silent reclassification is loud.
# --------------------------------------------------------------------------- #
DIRECTION_POLICY_VERSION = "stage3-direction-v4-workflow-states"

ABUNDANCE_REDUCTION = policy.ABUNDANCE_REDUCTION
FUNCTIONAL_INHIBITION = policy.FUNCTIONAL_INHIBITION
FUNCTIONAL_ACTIVATION = policy.FUNCTIONAL_ACTIVATION
EFFECT_UNKNOWN = policy.EFFECT_UNKNOWN
INTERVENTION_EFFECTS = (ABUNDANCE_REDUCTION, FUNCTIONAL_INHIBITION,
                        FUNCTIONAL_ACTIVATION, EFFECT_UNKNOWN)

ACTION_ABUNDANCE_REDUCTION = policy.ACTION_ABUNDANCE_REDUCTION
ACTION_FUNCTIONAL_INHIBITION = policy.ACTION_FUNCTIONAL_INHIBITION
ACTION_FUNCTIONAL_ACTIVATION = policy.ACTION_FUNCTIONAL_ACTIVATION
# UPREGULATOR and STABILISER plausibly raise abundance, but the closed vocabulary has no
# abundance-increase term: calling them activation would assert a signalling effect the
# source never stated. They stay unknown, deliberately.
ACTION_EXPLICIT_UNKNOWN = frozenset({
    "BINDER", "BINDING AGENT", "MODULATOR", "ALLOSTERIC MODULATOR", "PARTIAL AGONIST",
    "SUBSTRATE", "OTHER", "UNKNOWN", "CROSS-LINKING AGENT", "HYDROLYTIC ENZYME",
    "SEQUESTERING AGENT", "DISRUPTING AGENT", "CHELATING AGENT", "RELEASING AGENT",
    "STABILISER", "STABILIZER", "UPREGULATOR", "OXIDATIVE ENZYME",
    "PROTEOLYTIC ENZYME"})
_DUAL_RE = re.compile(r"[/&+]| AND |,")

MOD_DECREASE = policy.MOD_DECREASE
MOD_INCREASE = policy.MOD_INCREASE
MOD_NO_DIRECTION = policy.MOD_NO_DIRECTION
MOD_NOT_EVALUATED = "not_evaluated"

REASON_NON_RANKABLE_LANE = "assertion_lane_is_not_general_gene_rankable"


def direction_vocabulary_digest() -> str:
    """A content address for the CLOSED direction vocabulary itself.

    Recomputed from this module's restatement. If someone adds an action type to a set,
    moves one between sets, or edits the policy version, the digest moves and the change is
    visible — instead of being inferred from a drug that quietly started ranking.
    """
    payload = json.dumps({
        "policy_version": DIRECTION_POLICY_VERSION,
        "abundance_reduction": sorted(ACTION_ABUNDANCE_REDUCTION),
        "functional_inhibition": sorted(ACTION_FUNCTIONAL_INHIBITION),
        "functional_activation": sorted(ACTION_FUNCTIONAL_ACTIVATION),
        "explicit_unknown": sorted(ACTION_EXPLICIT_UNKNOWN),
        "intervention_effects": list(INTERVENTION_EFFECTS),
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def intervention_effect(action_type: Optional[str]) -> tuple[str, str]:
    """(effect, reason), re-derived from the VERBATIM source action. Fail-closed.

    An INHIBITOR is NOT an abundance reduction: an antagonist can shut down signalling
    without changing abundance at all. Activation is NEVER inferred from inhibition.
    """
    norm = policy.normalize_action(action_type)
    tag = norm.lower().replace(" ", "_")
    if norm in ACTION_ABUNDANCE_REDUCTION:
        return ABUNDANCE_REDUCTION, f"action_{tag}_lowers_target_abundance"
    if norm in ACTION_FUNCTIONAL_INHIBITION:
        return FUNCTIONAL_INHIBITION, (
            f"action_{tag}_reduces_target_function_not_target_level")
    if norm in ACTION_FUNCTIONAL_ACTIVATION:
        return FUNCTIONAL_ACTIVATION, (
            f"action_{tag}_increases_target_function_not_target_level")
    if norm in ACTION_EXPLICIT_UNKNOWN:
        return EFFECT_UNKNOWN, f"action_{tag}_has_no_enumerated_intervention_effect"
    if _DUAL_RE.search(norm):
        return EFFECT_UNKNOWN, "mixed_or_compound_action_type_not_translatable"
    return EFFECT_UNKNOWN, "unrecognised_action_type_fails_closed"


# THE RETIRED RULE IS GONE, DELIBERATELY.
#
# What stood here was ``translate(modulation, effect, …)``: a classifier that took the
# producer's SERIALIZED modulation as an INPUT and decided the edge from it. It is retired for
# two reasons, either of which alone is fatal.
#
#   1. It READ the producer's answer. A verifier whose classification is a function of the
#      token the producer wrote can only prove the producer agreed with itself.
#   2. The token it read is not what decides a direction. The direction comes from the SIGN of
#      the measured ``arm_value`` against the DECLARED modality, and the two must be
#      cross-checked. That rule is restated, independently, in :mod:`verifier.v2_sign`, which
#      RE-DERIVES the sign and then REQUIRES the producer's token to equal it.
#
# ``MODULATION_TO_DESIRED`` — the modality->modulation collapse that mapped "CRISPRi" straight
# to "inhibit the target in EVERY arm" — is retired with it. It never read the sign, so a gene
# whose knockdown moved the program the WRONG way was still matched to inhibitors and filed as
# supported evidence.


def summary_state(statuses: set[str]) -> str:
    """One (candidate, arm, origin) state. A CONTRADICTION is preserved, never resolved by
    preferring the favourable source."""
    if not statuses:
        return "not_annotated"
    if policy.OBSERVED_PERTURBATION in statuses and policy.OPPOSED in statuses:
        return "conflicting"
    for state in (policy.OBSERVED_PERTURBATION, policy.OPPOSED,
                  policy.INVERSE_DIRECTION_HYPOTHESIS, policy.PATHWAY_HYPOTHESIS):
        if state in statuses:
            return state
    return policy.UNRESOLVED


def stage4_assessment(*, artifact_class: str, identity_status: str, active_moiety_id: str,
                      directional_statuses: set[str]) -> tuple[str, str]:
    """Is Stage 4 asked to LOOK at this candidate? Queuing is not endorsement.

    A FIXTURE is never queued, whatever its evidence — that is the firewall, restated.
    """
    if artifact_class != ANALYSIS:
        return policy.NOT_QUEUED, "fixture_artifact_class_never_reaches_stage4"
    if active_moiety_id.startswith("AM:UNRESOLVED:") or identity_status == "unresolved":
        return policy.NOT_QUEUED, "active_moiety_identity_unresolved"
    if identity_status == "ambiguous":
        return policy.NOT_QUEUED, "active_moiety_identity_ambiguous"
    if identity_status == "multi_ingredient":
        return policy.NOT_QUEUED, "active_moiety_multi_ingredient"
    if policy.OBSERVED_PERTURBATION in directional_statuses:
        return policy.QUEUED, "direction_compatible_observed_perturbation"
    if policy.INVERSE_DIRECTION_HYPOTHESIS in directional_statuses:
        return policy.QUEUED, policy.REASON_QUEUED_INVERSE
    if policy.PATHWAY_HYPOTHESIS in directional_statuses:
        return policy.QUEUED, "direction_compatible_pathway_hypothesis"
    return policy.NOT_QUEUED, "no_direction_compatible_evidence"


# --------------------------------------------------------------------------- #
# ONE canonical numeric representation. Restated from the frozen rule.
#
# A float64 is rendered by its SHORTEST ROUND-TRIP decimal (repr, which is exact), then
# normalised to a canonical exponential decimal. NO ROUNDING, EVER: 4.0e-7 and 4.9e-7 stay
# distinct strings and therefore distinct hashes. A unit-agnostic rounding rule would collapse
# them, and a hash that collapses two different magnitudes is not a content address.
# --------------------------------------------------------------------------- #
def canonical_number(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        raise VerifierContractError(f"not a number: {value!r}")
    if isinstance(value, float):
        return format(Decimal(repr(value)).normalize(), "E")
    return format(Decimal(str(value).strip()).normalize(), "E")


def value_strings(value: Any) -> tuple[Optional[str], Optional[str]]:
    """The arm value as an exact SOURCE string plus its canonical decimal. Never a float."""
    if value is None or isinstance(value, bool):
        return None, None
    return (repr(value) if isinstance(value, float) else str(value),
            canonical_number(value))


# --------------------------------------------------------------------------- #
# Banned vocabularies. Refused by NAME, at any depth, so a friendly synonym does not
# launder the claim.
# --------------------------------------------------------------------------- #
OBJECTIVE_KEYS = frozenset(policy.BANNED_KEYS | v2.BANNED_V2_KEYS | {
    "combined_objective", "balanced_objective", "balanced_evidence",
    "weighted_score", "weighted_rank", "weighted_evidence", "weighted_objective"})
OBJECTIVE_PREFIXES = ("combined_", "balanced_", "weighted_", "fused_", "merged_",
                      "composite_", "consensus_")

# The document must be able to STATE that it carries no combined objective. These are the
# only names that may say so, they are exhaustively listed, and the schema gate requires
# each to be exactly False — a declaration that could be True would be the objective.
OBJECTIVE_DECLARATIONS = frozenset({"combined_objective_permitted",
                                    "headline_arm_permitted",
                                    "candidate_rank_permitted"})

# The one name that may SAY the bundle carries no p/q/FDR. It is the denial, not the thing —
# and the schema gate requires it to be exactly False, so a declaration that could be True
# would itself be the statistic.
INFERENCE_DECLARATIONS = frozenset({"p_q_fdr_permitted"})

# Stage 3 reports no significance. A p/q/FDR field is a statistic this stage never
# computed, wearing the authority of one that was.
STAT_KEY_RE = re.compile(
    r"(?:^|_)(?:p|q)(?:[_-]?val(?:ue)?s?)?$"
    r"|(?:^|_)(?:p|q)[_-]?adj(?:usted)?(?:[_-]?val(?:ue)?s?)?$"
    r"|(?:^|_)adj(?:usted)?[_-]?(?:p|q)(?:[_-]?val(?:ue)?s?)?$"
    r"|fdr|bonferroni|benjamini|holm[_-]?bonferroni",
    re.IGNORECASE)


def is_objective_key(name: Any) -> bool:
    if not isinstance(name, str) or name.lower() in OBJECTIVE_DECLARATIONS:
        return False
    low = name.lower()
    return low in OBJECTIVE_KEYS or low.startswith(OBJECTIVE_PREFIXES)


def is_stat_key(name: Any) -> bool:
    if not isinstance(name, str) or name.lower() in INFERENCE_DECLARATIONS:
        return False
    return bool(STAT_KEY_RE.search(name))


def walk_keys(obj: Any, path: str = "$"):
    """Every (path, key) in the document, at ANY depth and in ANY container."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield f"{path}.{key}", key
            yield from walk_keys(value, f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for i, value in enumerate(obj):
            yield from walk_keys(value, f"{path}[{i}]")


def objective_keys_in(obj: Any) -> list[str]:
    return [p for p, k in walk_keys(obj) if is_objective_key(k)]


def true_objective_declarations(obj: Any) -> list[str]:
    """A declaration that says the objective IS permitted IS the objective."""
    hits: list[str] = []

    def walk(node: Any, path: str = "$") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and key.lower() in OBJECTIVE_DECLARATIONS \
                        and value is not False:
                    hits.append(f"{path}.{key}={value!r}")
                walk(value, f"{path}.{key}")
        elif isinstance(node, (list, tuple)):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]")

    walk(obj)
    return hits


def stat_keys_in(obj: Any) -> list[str]:
    return [p for p, k in walk_keys(obj) if is_stat_key(k)]
