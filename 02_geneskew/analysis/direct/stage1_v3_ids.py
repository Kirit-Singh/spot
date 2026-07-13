"""THE IDENTITIES a Stage-1 v3 contract carries — derived, never read.

Split out of ``stage1_v3`` because identity is one job and the gate is another. Everything
here answers a single question: *given the contract's own bytes, what is this selection?* It
touches no schema, no estimator registry, no release and no run — it takes a contract document
and hashes what the contract says. That is why it can be read, and audited, on its own.

FOUR IDENTITIES, AND THEY ARE NOT INTERCHANGEABLE
-------------------------------------------------
  * ``question_id``  — WHICH BIOLOGICAL QUESTION. The ordered endpoints and the mode, and
    nothing else: no method, no registry, no source. So the same question keeps ONE id across
    method and input revisions. **Stage-2 used to substitute its own biology hash for this and
    never read the contract's field at all** — the id that reached Stage-3 was not the one
    Stage-1 minted, and nothing checked it.
  * ``selection_id`` — WHICH CONTRACT ASKED IT. Hashes ``canonical_content``, which binds the
    scorer view, the source h5ad and the method version. It MOVES when they do; question_id
    does not. That difference is the whole point of having two.
  * ``selection_biology_sha256`` — STAGE-2'S OWN key for the biology it read, so two
    selections can never share a stage2_run_id whatever their contract ids say.
  * ``declared_method_identity`` — WHAT METHOD the contract was admitted against. Stage-1's
    ESTIMAND-IDENTITY hash: bound and preserved through verified bytes, and explicitly NOT
    re-derived here (it is not a code-tree hash and this lane cannot recompute one).

Each derivation is published with a rule id, so a producer that disagrees can be told exactly
which rule it failed rather than being handed a mismatch and left to guess.

Depends only on ``hashing.content_hash``: identity must not be able to change because a
config, a policy or a release moved.
"""
from __future__ import annotations

from typing import Any

from .hashing import content_hash

# --------------------------------------------------------------------------- #
# THE DECLARED METHOD IDENTITY — bound, preserved, and NOT re-derived here.
#
# TWO DIFFERENT HASHES LIVE UNDER THE NAME `method_sha256`, AND CONFLATING THEM IS A BUG:
#
#   1. THE CONTRACT'S (`doc.estimator.method_sha256`). Stage-1's ESTIMAND-IDENTITY hash: the
#      content hash of the estimand block — WHAT is being estimated (a population-level
#      difference-in-differences on program projections, not calibrated). Stage-1 states
#      explicitly that it is NOT a code-tree or batch/confound-policy hash. It is an
#      EXTERNALLY BOUND identity: Stage-1 derived it from the temporal-arms lane, and THIS
#      lane has no way to recompute it.
#
#   2. THIS BRANCH'S (`estimator_registry()[...]['method_sha256']`). An IMPLEMENTATION
#      binding: a hash over the temporal code trees and the frozen batch policy — WHICH CODE
#      would run. A different quantity, answering a different question.
#
# They are not equal and they are not supposed to be. So this module NEVER compares them, and
# it never lets one stand in for the other. Comparing them would fail-closed on the
# authoritative Stage-1 contract — a false refusal, which is exactly as damaging as a false
# admission.
#
# WHAT IS ACTUALLY PROVED HERE, THEN. The declared identity is carried through bytes that ARE
# proved: the contract's own `full_contract_content_sha256` (re-derived), the pinned schema,
# and the admitted Stage-1 release. So a contract cannot be edited in flight to name a
# different method without the content hash failing. What is NOT proved here is that the hash
# corresponds to the code that will run — Stage-2's Direct lane cannot re-derive an estimand
# identity minted in another lane, and it does not pretend to.
#
# THAT RE-DERIVATION IS OWNED BY THE TEMPORAL PRODUCER/VERIFIER (W5/W11). It is named here so
# that the absence of the check is a DECLARED LIMIT with an owner, not a gap a reader has to
# infer from silence. (Same pattern as the release loader's scorer-PROJECTION hash, which is
# likewise bound-as-declared because its derivation rules live in Stage-1.)
# --------------------------------------------------------------------------- #
METHOD_IDENTITY_RULE_ID = (
    "spot.stage02.stage1_v3.declared_method_identity.bound_not_rederived.v1")
METHOD_IDENTITY_BINDING = "declared_by_stage1_bound_by_contract_bytes_not_rederived_here"
METHOD_IDENTITY_KIND = "stage1_estimand_identity_hash"
METHOD_IDENTITY_NOT_A = "stage2_implementation_code_tree_hash"
METHOD_IDENTITY_REDERIVATION_OWNER = "spot.stage02.temporal.producer_verifier.W5_W11"
METHOD_IDENTITY_NOT_REDERIVED_BECAUSE = (
    "the contract's estimator.method_sha256 is Stage-1's ESTIMAND-IDENTITY hash, minted in "
    "the temporal-arms lane; it is not a code-tree hash and the Direct lane cannot recompute "
    "it. It is bound through verified contract bytes and preserved downstream. Re-deriving "
    "the IMPLEMENTATION-code binding is the temporal producer/verifier's job (W5/W11), and "
    "comparing it with this branch's code-tree hash would refuse the real contract")

# The method fields a contract may declare. Carried VERBATIM — never invented, never defaulted.
METHOD_IDENTITY_FIELDS = ("method_id", "method_version", "method_sha256", "estimand_id",
                          "estimand_level", "estimand_is_per_cell_fate", "inference_status")


# --------------------------------------------------------------------------- #
# WHAT MAKES TWO AXES THE SAME AXIS.
#
# THIS IS SELECTION METADATA. IT IS NOT AN ARM KEY AND IT IS NOT A CACHE KEY.
#
# A pole is `high|low` — what Stage-1 was ASKED for. A reusable arm is keyed on the
# perturbation's DESIRED CHANGE (`increase|decrease`), because the same pole means opposite
# perturbations depending on the role it plays: away_from_A(high) DECREASES the program,
# toward_B(high) INCREASES it. Keying a cached arm on `high` would therefore fuse two
# opposite perturbations under one key. The arm keys live in ``arms.py``; the pole and the
# role stay here, in the selection, and neither may alter a cached arm's values.
#
# The identity of a pole is the WHOLE tuple: (program_id, pole, condition). Nothing less.
# Two consequences, and the bridge needs both:
#
#   * the same program in the same direction at a DIFFERENT condition is a DIFFERENT axis.
#     The per-condition lane runs one axis at Rest, Stim8hr and Stim48hr, and the temporal
#     estimator exists precisely to compare them — a bridge that collapsed them on
#     program+direction would refuse the runs the lane is built on;
#   * the same program in the same direction at the SAME condition is ONE axis, and a
#     contract naming it for BOTH poles is degenerate: away_from_A and toward_B would be
#     the two opposite arms of a single axis, anti-correlated by construction, and their
#     "convergence" would be an artefact of the contract rather than a finding.
# --------------------------------------------------------------------------- #
POLE_IDENTITY_RULE_ID = "spot.stage01.pole_identity.program_direction_condition.v1"
POLE_IDENTITY_RULE = (
    "a pole is identified by (program_id, direction, condition); only an exactly identical "
    "tuple is the same pole — the same program+direction at another condition is a "
    "different axis")


def pole_identity(program_id: str, direction: str, condition: str) -> str:
    """The identity of ONE pole, at ONE condition."""
    return f"{program_id}|{direction}|{condition}"


def pole_identities(program_id: str, direction: str, conditions) -> list[str]:
    """The identity of one pole at EVERY condition the contract evaluates it at."""
    return [pole_identity(program_id, direction, c) for c in conditions]


def axis_identity(bound: dict[str, Any]) -> list[str]:
    """Every (program, direction, condition) tuple this selection puts on the table."""
    bio = bound["biology"] if "biology" in bound else selection_biology(bound)
    conditions = bound["conditions"]
    return [i for pole in ("A", "B")
            for i in pole_identities(bio[pole]["program_id"], bio[pole]["direction"],
                                     conditions)]

# --------------------------------------------------------------------------- #
# THE CONTRACT'S ENDPOINTS — and why they are not `axis_identity`.
#
# Two different questions are asked of the same contract, and conflating them is what broke
# this consumer:
#
#   * WHAT WAS ASKED (here). The ordered pair of ENDPOINTS. Pole A sits at conditions[0],
#     pole B at conditions[-1] — for a within-condition selection those are the same
#     condition; for a temporal one they are the FROM and the TO. This is the biological
#     question, and it is what `question_id` hashes.
#   * WHAT MUST BE MEASURED (`axis_identity`). Each pole at EVERY condition it is evaluated
#     at, because a temporal pair is only executable if each pole is selectable at each
#     endpoint it is compared across.
#
# The consumer used to refuse a contract whose two poles shared a (program, direction) —
# full stop, in EVERY mode. But the endpoint disambiguates them: the SAME program in the
# SAME direction at Rest vs Stim48hr is two distinct endpoints and a perfectly good temporal
# question ("does this program's skew move with activation?"), and it is one Stage-1 emits.
# Refusing it meant the consumer rejected valid science that the producer was shipping.
#
# The honest rule is the WHOLE tuple, on BOTH endpoints: refuse only when
# (program, direction, condition) is IDENTICAL on both poles — one axis, named twice, whose
# two arms are anti-correlated by construction.
# --------------------------------------------------------------------------- #
ENDPOINT_RULE_ID = "spot.stage01.endpoint_identity.a_at_first_b_at_last.v1"
ENDPOINT_RULE = (
    "pole A sits at conditions[0] and pole B at conditions[-1]; the two poles are the same "
    "axis only when (program_id, direction, condition) is identical on BOTH endpoints — the "
    "same program+direction at DIFFERENT conditions is a valid temporal question")


def endpoints(doc: dict[str, Any]) -> dict[str, dict[str, str]]:
    """WHAT THE CONTRACT ASKED: the ordered (program, direction, condition) endpoints."""
    c = doc["canonical_content"]
    conds = list(c["conditions"])
    return {
        "A": {"program_id": str(c["A"]["program_id"]),
              "direction": str(c["A"]["direction"]), "condition": str(conds[0])},
        "B": {"program_id": str(c["B"]["program_id"]),
              "direction": str(c["B"]["direction"]), "condition": str(conds[-1])},
    }


# --------------------------------------------------------------------------- #
# THE QUESTION_ID — the contract's OWN biology-only identity, re-derived (not substituted).
#
# This consumer used to SUBSTITUTE its own `selection_biology_sha256` for the contract's
# `question_id`: it never read the field, never re-derived it, and never checked it. So the
# one identifier that says WHICH BIOLOGICAL QUESTION was asked travelled from Stage-1 to
# Stage-3 completely unverified, and a contract could carry any question_id at all — or a
# question_id belonging to a different question — without anything noticing.
#
# The recipe is Stage-1's, published in the contract's own schema and in its producer:
#
#   question_id = sha256(canonical_json({
#       "A": {program_id, direction, condition: conditions[0]},
#       "B": {program_id, direction, condition: conditions[-1]},
#       "analysis_mode": mode}))[:16]
#
# It binds NO method and NO input, so the SAME biological question keeps ONE question_id
# across method / registry / source revisions. That is exactly what makes it different from
# `selection_id`, which hashes `canonical_content` and therefore DOES bind the scorer view,
# the source h5ad and the method version. Both are carried, both are re-derived, and they
# are never allowed to stand in for one another.
# --------------------------------------------------------------------------- #
QUESTION_ID_RULE_ID = "spot.stage01.question_id.sha256_of_ordered_biology_first16.v1"
QUESTION_ID_RULE = (
    "question_id = sha256(canonical_json({A:{program_id,direction,condition:conditions[0]}, "
    "B:{program_id,direction,condition:conditions[-1]}, analysis_mode}))[:16] — biology "
    "only, with NO method or input binding (that is selection_id's job)")
QUESTION_ID_LEN = 16


def question_content(doc: dict[str, Any]) -> dict[str, Any]:
    """The EXACT ordered, biology-only content Stage-1 hashes. Nothing else may enter it."""
    ends = endpoints(doc)
    return {
        "A": ends["A"],
        "B": ends["B"],
        "analysis_mode": str(doc["canonical_content"]["analysis_mode"]),
    }


def derive_question_id(doc: dict[str, Any]) -> str:
    """Re-derive the question_id from the biology the contract names. Never read it."""
    return content_hash(question_content(doc))[:QUESTION_ID_LEN]


# THE RULE, published (m2). It was previously declared non-derivable and carried
# unchecked; an independent audit published the recipe and it is now enforced.
SELECTION_ID_RULE_ID = (
    "spot.stage01.selection_id.sha256_of_canonical_content_first16.v1")
SELECTION_ID_RULE = (
    "selection_id = sha256(canonical_json(contract.canonical_content))[:16], where "
    "canonical_json is compact sorted-key JSON — byte-identical to `jq -cS "
    "'.canonical_content' | shasum -a 256`")
SELECTION_ID_LEN = 16

# Retired. Kept as a NAMED retraction so a reader who meets the old id in an archived
# artifact learns it was withdrawn, rather than concluding the check never existed.
STAGE1_SELECTION_ID_NOT_REDERIVABLE = (
    "RETIRED:spot.stage02.gate_b.selection_id_is_a_citation_not_a_recomputable_key.v1"
    " — superseded by " + SELECTION_ID_RULE_ID + "; the id IS derivable and is now "
    "re-derived and enforced")


def derive_selection_id(doc: dict[str, Any]) -> str:
    """Re-derive the selection_id from the contract's OWN canonical content."""
    return content_hash(doc["canonical_content"])[:SELECTION_ID_LEN]


def canonical_content_sha256(doc: dict[str, Any]) -> str:
    """The full 64-hex hash the selection_id is the first 16 of."""
    return content_hash(doc["canonical_content"])


def declared_method_identity(doc: dict[str, Any]) -> dict[str, Any]:
    """WHAT METHOD the contract says it was admitted against — carried verbatim, and LABELLED.

    Every field is the contract's own. Nothing here is derived, defaulted or repaired; the
    block additionally says, in machine-readable form, WHAT KIND of hash this is, that
    Stage-2 did not re-derive it, and WHO owns the re-derivation — so a downstream reader can
    never mistake it for a locally proved implementation binding.
    """
    est = doc.get("estimator") or {}
    identity = {f: est[f] for f in METHOD_IDENTITY_FIELDS if f in est}
    identity.update({
        "declared": bool(identity),
        "binding": METHOD_IDENTITY_BINDING,
        "rule_id": METHOD_IDENTITY_RULE_ID,
        "identity_kind": METHOD_IDENTITY_KIND,
        "is_not": METHOD_IDENTITY_NOT_A,
        "rederived_by_stage2_direct": False,
        "not_rederived_because": METHOD_IDENTITY_NOT_REDERIVED_BECAUSE,
        "rederivation_owner": METHOD_IDENTITY_REDERIVATION_OWNER,
        # anchored by bytes that ARE proved: the contract hashes its own content, and the
        # schema and the Stage-1 release it arrived in are both pinned.
        "anchored_by": ["full_contract_content_sha256", "selection_schema_sha256",
                        "admitted_stage1_v3_release"],
    })
    return identity


def selection_biology(doc: dict[str, Any]) -> dict[str, Any]:
    """The BIOLOGY of a selection, as Stage-2 reads it. Generic: no program is special."""
    c = doc["canonical_content"]
    return {
        "A": {"program_id": c["A"]["program_id"], "direction": c["A"]["direction"]},
        "B": {"program_id": c["B"]["program_id"], "direction": c["B"]["direction"]},
        "analysis_mode": c["analysis_mode"],
        "conditions": list(c["conditions"]),
    }


def selection_biology_sha256(doc: dict[str, Any]) -> str:
    """Stage-2's OWN key for the biology it actually read.

    This is a THIRD hash, and it is not a substitute for either contract id. Stage-1's
    ``selection_id`` AND ``question_id`` are both re-derived and enforced above; this one is
    Stage-2's own, so that two different selections can never share a stage2_run_id whatever
    their contract ids happen to say. It once stood in for ``question_id`` — which meant the
    contract's own question identity was never checked and never travelled. It does not any
    more; the three are carried side by side and none may impersonate another.
    """
    return content_hash(selection_biology(doc))
