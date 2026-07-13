"""THE USER'S QUESTION: a verified Stage-1 v3 selection. Re-derived, never read on trust.

Stage-3's scientific store is SELECTION-INDEPENDENT — it holds every arm, every edge, every
candidate, and it re-ranks nothing. This module is the other half of that bargain: it turns the
one question a user actually asked into a typed object, so the store can be PROJECTED onto it.

WHAT A v3 SELECTION IS (``spot.stage01_selection.v3``)
-----------------------------------------------------
An ORDERED PAIR of poles plus an analysis mode::

    A = (program_id, direction)      the pole to move AWAY FROM      role ``away_from_A``
    B = (program_id, direction)      the pole to move TOWARD         role ``toward_B``
    analysis_mode  = within_condition | temporal_cross_condition
    conditions     = [c]             within: exactly ONE condition
                   = [from, to]      temporal: exactly TWO, ORDERED

Each pole sits at its OWN condition: **A at ``conditions[0]``, B at ``conditions[-1]``** (the
same condition within-time; the two ENDPOINTS of the ordered pair across time). That is not
Stage-3's invention — it is what Stage-1's emitter does, and it is why the same program in the
same direction at two DIFFERENT times is a legitimate question rather than a self-comparison.

The pole ``direction`` is ``high|low`` — what Stage-1 was ASKED for. It is NOT a desired change
and it is NOT an arm key: the same pole means OPPOSITE perturbations depending on the role it
plays. That translation happens in :mod:`druglink.arm_selection`, once, and nowhere else.

TWO IDENTITIES. BOTH REQUIRED. THEY MEAN DIFFERENT THINGS
--------------------------------------------------------
Both are RE-DERIVED here from the contract's own content and REQUIRED to match what it declares.
Neither is read on trust: an id nobody recomputes is a label, and a label can be moved onto a
different contract without anything noticing.

``question_id``   WHICH QUESTION IS THIS?  The BIOLOGY-ONLY ordered-question identity — the two
                  poles' ``(program_id, direction, condition)`` and the analysis mode, and NOTHING
                  else. No method, no registry, no source binding. So the SAME biological question
                  keeps ONE ``question_id`` across method / registry / source revisions::

                      question_id = sha256(canonical_json({
                          "A": {"program_id", "direction", "condition": conditions[0]},
                          "B": {"program_id", "direction", "condition": conditions[-1]},
                          "analysis_mode": mode}))[:16]        -> 16 LOWERCASE HEX

                  THE CONDITION IS INSIDE EACH POLE, not a sibling array. Drop it and the same
                  program in the same direction at two different times collapses into one pole
                  compared with itself — and the id would say the two questions were one.

``selection_id``  WHICH RUN OF THAT QUESTION IS THIS?  ``sha256(canonical_json(canonical_content
                  ))[:16]`` — the same biology PLUS the scorer view, the source h5ad and the
                  method version. It is the METHOD/INPUT-BOUND identity, and it moves when the
                  method does. (``selection_full_sha256`` is its full 64-hex form.)

Binding only one would be a silent failure in either direction: with only ``selection_id``, a
method revision looks like a NEW question; with only ``question_id``, a stale run masquerades as
the current one. So both are bound, both are re-derived, and they are never conflated.

``canonical_json`` is compact + sorted-key + ``ensure_ascii`` — byte-identical to ``jq -cS``.
Restated here rather than imported: Stage 1 lives in another lane, and a consumer that borrowed
the producer's hasher could never disagree with it. Verified against Stage-1's own emitted
fixtures (``stage01_selection_temporal_ready_example.json``: question_id ``3203d63970720d4f``,
selection_id ``7a77f6b314b9c0f3``), which ``test_selection_view`` pins.

AN INTERNALLY CONSISTENT CONTRACT IS STILL NOT A VALID ONE
----------------------------------------------------------
A forger with repo access can edit a payload and recompute every id, and the contract then agrees
with itself perfectly. That is why the ids are NOT the last gate: the view additionally requires
the selection to be about the STORE IN HAND (:func:`druglink.selection_view.check_not_stale`). A
resealed selection over the wrong release is internally flawless and scientifically wrong.

WHAT THIS MODULE DOES NOT DO
----------------------------
It does not name a program, a condition, a direction or a time point. There is no Treg here and
no Stim48hr: the biology arrives entirely through the contract. A special case for one program
would be a lane that silently does something different for the next one.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from .stage2_contract import stage2_content_sha256

SELECTION_SCHEMA = "spot.stage01_selection.v3"
SELECTION_ID_LEN = 16
SELECTION_ID_RULE_ID = "spot.stage01.selection_id.sha256_of_canonical_content_first16.v1"
QUESTION_ID_RULE_ID = "spot.stage01.question_id.biology_only_ordered_question.v1"
QUESTION_ID_RULE = (
    "question_id = sha256(canonical_json({A:{program_id,direction,condition:conditions[0]}, "
    "B:{program_id,direction,condition:conditions[-1]}, analysis_mode}))[:16] — the CONDITION "
    "lives INSIDE each pole, never in a sibling array; biology only, no method binding")

# The two analysis modes, and the condition arity each one REQUIRES. The arity is decided by the
# mode, never by the caller: a cross-condition estimate compares exactly two conditions, IN
# ORDER, and a within-condition estimate is made inside exactly one.
MODE_WITHIN = "within_condition"
MODE_TEMPORAL = "temporal_cross_condition"
ANALYSIS_MODES = (MODE_WITHIN, MODE_TEMPORAL)
N_CONDITIONS_FOR_MODE = {MODE_WITHIN: 1, MODE_TEMPORAL: 2}

# The roles a SELECTION assigns. They live HERE, in the question — never in an arm.
ROLE_A = "away_from_A"
ROLE_B = "toward_B"
ROLES = (ROLE_A, ROLE_B)
POLE_FOR_ROLE = {ROLE_A: "A", ROLE_B: "B"}

# The poles Stage-1 offers. `high|low` is what was ASKED for, not what will be perturbed.
POLE_HIGH = "high"
POLE_LOW = "low"
POLES = (POLE_HIGH, POLE_LOW)

EXECUTION_READY = "ready"

# Named gates. Every refusal cites one, so it can be grepped, tested and quoted.
GATE_SELECTION_NOT_ON_DISK = "the_selection_contract_is_not_on_disk"
GATE_SELECTION_UNREADABLE = "the_selection_contract_is_not_readable_json"
GATE_SELECTION_NOT_NATIVE = "the_document_is_not_the_native_stage1_v3_selection_contract"
GATE_SELECTION_ID_NOT_DERIVED = \
    "the_selection_id_does_not_derive_from_its_own_canonical_content"
GATE_QUESTION_ID_MISSING = "the_selection_carries_no_question_id"
GATE_QUESTION_ID_NOT_DERIVED = \
    "the_question_id_does_not_derive_from_the_biology_the_selection_names"
GATE_SELECTION_CONTENT_HASH = "the_contract_hash_does_not_cover_the_contracts_own_content"
GATE_SELECTION_MODE_UNKNOWN = "the_selection_names_an_analysis_mode_stage3_does_not_have"
GATE_SELECTION_CONDITIONS = "the_condition_count_does_not_match_the_analysis_mode"
GATE_SELECTION_BIOLOGY_SPLIT = "the_contract_names_two_different_biologies"
GATE_SELECTION_POLE_UNKNOWN = "a_pole_direction_is_not_one_stage1_offers"
GATE_SELECTION_COMBINED_OBJECTIVE = "stage1_handed_down_a_combined_objective"
GATE_SELECTION_NOT_EXECUTABLE = "the_selection_was_not_executed_by_stage2"


class SelectionError(ValueError):
    """The question is not one Stage 3 can answer. Refuse; never repair, never guess."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _refuse(gate: str, message: str) -> None:
    raise SelectionError(gate, message)


@dataclass(frozen=True)
class VerifiedSelection:
    """ONE question, with BOTH identities re-derived from its own content.

    ``question_id``  WHICH QUESTION — biology only, stable across method revisions.
    ``selection_id`` WHICH RUN of it — additionally bound to the method and the inputs.
    """
    selection_id: str
    question_id: str
    analysis_mode: str
    conditions: tuple[str, ...]           # ORDERED. temporal: (from_condition, to_condition)
    poles: dict[str, dict[str, str]]      # {"A": {program_id, direction, condition}, "B": {…}}
    registry_scorer_view_sha256: str
    canonical_content_sha256: str
    full_contract_content_sha256: str
    selection_full_sha256: str
    declared_arms: dict[str, Any]         # Stage-1's OWN arms block, if it emitted one

    @property
    def is_temporal(self) -> bool:
        return self.analysis_mode == MODE_TEMPORAL

    @property
    def from_condition(self) -> str:
        return self.conditions[0]

    @property
    def to_condition(self) -> str:
        return self.conditions[-1]

    def pole(self, role: str) -> dict[str, str]:
        return self.poles[POLE_FOR_ROLE[role]]

    def binding(self) -> dict[str, Any]:
        """What the VIEW binds about the question. Ids and enums only — no paths, no clock."""
        return {
            "selection_schema": SELECTION_SCHEMA,
            # WHICH RUN of the question. Method/input-bound: it moves when the method does.
            "selection_id": self.selection_id,
            "selection_id_rule_id": SELECTION_ID_RULE_ID,
            "selection_full_sha256": self.selection_full_sha256,
            # WHICH QUESTION. Biology only: ONE id per biological question, across every method
            # revision. The two are never conflated — binding only one would let a method bump
            # look like a new question, or a stale run masquerade as the current one.
            "question_id": self.question_id,
            "question_id_rule_id": QUESTION_ID_RULE_ID,
            "analysis_mode": self.analysis_mode,
            "conditions": list(self.conditions),
            # Each pole carries its OWN condition: A at conditions[0], B at conditions[-1].
            "poles": {p: dict(self.poles[p]) for p in ("A", "B")},
            "roles": {"A": ROLE_A, "B": ROLE_B},
            "canonical_content_sha256": self.canonical_content_sha256,
            "full_contract_content_sha256": self.full_contract_content_sha256,
            # The Stage-1 release binding this question was minted against. Stage-1 spells the
            # field `registry_scorer_view_sha256`; the view does not, because Stage-3's structural
            # firewall refuses any key containing `score` at any depth — a rule that exists to
            # stop a pooled objective from ever appearing, and that a Stage-1 identity hash has no
            # business being exempted from. The BYTES are identical; only the label differs.
            "stage1_release_binding_sha256": self.registry_scorer_view_sha256,
            # Said out loud, and bound into the view id: the roles are a property of THIS
            # question, and they were assigned at join time. No arm carries one.
            "roles_are_assigned_at_join_time_never_stored_on_an_arm": True,
            "combined_objective_permitted": False,
        }


def derive_selection_id(doc: dict[str, Any]) -> str:
    """RE-DERIVED: sha256(canonical_json(canonical_content))[:16]. The METHOD-BOUND identity."""
    return stage2_content_sha256(doc["canonical_content"])[:SELECTION_ID_LEN]


def derive_selection_full_sha256(doc: dict[str, Any]) -> str:
    """The full 64-hex form of the same hash."""
    return stage2_content_sha256(doc["canonical_content"])


def derive_contract_hash(doc: dict[str, Any]) -> str:
    """The contract's hash over its OWN content, excluding only the field that holds it."""
    return stage2_content_sha256(
        {k: v for k, v in doc.items() if k != "full_contract_content_sha256"})


def question_content(doc: dict[str, Any]) -> dict[str, Any]:
    """The BIOLOGY, and only the biology — with the CONDITION INSIDE EACH POLE.

    A at ``conditions[0]``, B at ``conditions[-1]``. That is what makes "the same program, in the
    same direction, at two different times" a real question with a real identity, instead of one
    pole compared with itself. A sibling ``conditions`` array here would let the two poles look
    identical and hash to the same id.
    """
    c = doc["canonical_content"]
    conditions = list(c["conditions"])
    return {
        "A": {"program_id": c["A"]["program_id"], "direction": c["A"]["direction"],
              "condition": conditions[0]},
        "B": {"program_id": c["B"]["program_id"], "direction": c["B"]["direction"],
              "condition": conditions[-1]},
        "analysis_mode": c["analysis_mode"],
    }


def derive_question_id(doc: dict[str, Any]) -> str:
    """Stage-1's published rule, RE-DERIVED. 16 lowercase hex — never the 64-hex form."""
    return stage2_content_sha256(question_content(doc))[:SELECTION_ID_LEN]


def _require_content(doc: Any) -> dict[str, Any]:
    if not isinstance(doc, dict) or doc.get("schema_version") != SELECTION_SCHEMA:
        _refuse(GATE_SELECTION_NOT_NATIVE,
                f"the selection declares schema_version="
                f"{(doc or {}).get('schema_version') if isinstance(doc, dict) else None!r}; "
                f"Stage 3 consumes exactly {SELECTION_SCHEMA!r}. A v1 or v2 selection is not a "
                "v3 selection and is never migrated in place — the older contracts do not carry "
                "an analysis_mode, so a cross-time question could not even be expressed in one.")
    for field in ("canonical_content", "poles", "selection_id",
                  "full_contract_content_sha256"):
        if field not in doc:
            _refuse(GATE_SELECTION_NOT_NATIVE,
                    f"the selection carries no {field!r}. A missing field is a refusal, never a "
                    "default: a question with no content hash has been bound to nothing.")
    return doc["canonical_content"]


def verify(doc: dict[str, Any]) -> VerifiedSelection:
    """Every refusal, in order. Returns the ONE typed object the materializer consumes."""
    content = _require_content(doc)

    derived_id = derive_selection_id(doc)
    if str(doc["selection_id"]) != derived_id:
        _refuse(GATE_SELECTION_ID_NOT_DERIVED,
                f"the selection declares selection_id={str(doc['selection_id'])!r} but its own "
                f"canonical_content derives {derived_id!r}. An id nobody recomputes is a label, "
                "and a label can be moved onto a different contract without anything noticing — "
                "the view would then answer one question under the identity of another.")

    # THE BIOLOGY-ONLY IDENTITY. Required, and re-derived — never read.
    if "question_id" not in doc:
        _refuse(GATE_QUESTION_ID_MISSING,
                "the selection carries no question_id. It is the BIOLOGY-ONLY ordered-question "
                "identity, and it is what tells a consumer WHICH QUESTION this is, independently "
                "of which method run answered it. Without it, a method revision is "
                "indistinguishable from a new question.")
    derived_question = derive_question_id(doc)
    if str(doc["question_id"]) != derived_question:
        _refuse(GATE_QUESTION_ID_NOT_DERIVED,
                f"the selection declares question_id={str(doc['question_id'])!r} but the biology "
                f"it names derives {derived_question!r} "
                f"(rule: {QUESTION_ID_RULE}). The condition lives INSIDE each pole — A at the "
                "first condition, B at the last — so a question_id that dropped it would collapse "
                "'the same program, same direction, at two different times' into one pole "
                "compared with itself, and hand two different questions one id.")

    derived_hash = derive_contract_hash(doc)
    if str(doc["full_contract_content_sha256"]) != derived_hash:
        _refuse(GATE_SELECTION_CONTENT_HASH,
                f"full_contract_content_sha256 is "
                f"{str(doc['full_contract_content_sha256'])[:16]}… but the contract's own content "
                f"hashes to {derived_hash[:16]}…. A contract whose hash does not cover its "
                "content has not been bound to anything.")

    mode = str(content.get("analysis_mode"))
    if mode not in ANALYSIS_MODES:
        _refuse(GATE_SELECTION_MODE_UNKNOWN,
                f"the selection names analysis_mode={mode!r}; Stage 3 projects exactly "
                f"{list(ANALYSIS_MODES)}. The two modes read DIFFERENT arms — a within-condition "
                "question reads same-time Direct arms, a cross-time question reads the temporal "
                "DiD arms — and their numbers look alike, so an unknown mode is refused rather "
                "than routed to whichever happens to be first.")

    conditions = tuple(str(c) for c in (content.get("conditions") or ()))
    want = N_CONDITIONS_FOR_MODE[mode]
    if len(conditions) != want:
        _refuse(GATE_SELECTION_CONDITIONS,
                f"a {mode} selection names {len(conditions)} condition(s) {list(conditions)}; it "
                f"is exactly {want}. The arity is decided by the MODE, not by the caller: a "
                "cross-condition estimate compares exactly two conditions, IN ORDER, and "
                "reversing them changes the sign of the difference.")

    if content.get("combined_objective") is not None \
            or content.get("poles_separate") is not True:
        _refuse(GATE_SELECTION_COMBINED_OBJECTIVE,
                f"the selection declares combined_objective="
                f"{content.get('combined_objective')!r} / poles_separate="
                f"{content.get('poles_separate')!r}. The two poles are an ORDERED PAIR of "
                "SEPARATE questions. A combined score handed down from Stage 1 would reintroduce, "
                "one stage earlier, the pooled objective this whole store exists to refuse.")

    poles: dict[str, dict[str, str]] = {}
    for pole, condition in (("A", conditions[0]), ("B", conditions[-1])):
        block = doc["poles"].get(pole) or {}
        for field in ("program_id", "direction"):
            if str(content[pole][field]) != str(block.get(field)):
                _refuse(GATE_SELECTION_BIOLOGY_SPLIT,
                        f"canonical_content.{pole}.{field}={content[pole][field]!r} but "
                        f"poles.{pole}.{field}={block.get(field)!r}. The contract names two "
                        "different biologies, and whichever one is read first decides which "
                        "arms get projected.")
        direction = str(content[pole]["direction"])
        if direction not in POLES:
            _refuse(GATE_SELECTION_POLE_UNKNOWN,
                    f"pole {pole} names direction {direction!r}; Stage-1's poles are exactly "
                    f"{list(POLES)}. A pole is not a desired change and is never coerced into "
                    "one — the same pole is an increase in one role and a decrease in the other.")
        # THE POLE'S OWN CONDITION. A at the first, B at the last — the same one within-time, the
        # two ENDPOINTS across time. It is part of the pole's identity, not a sibling fact.
        poles[pole] = {"program_id": str(content[pole]["program_id"]), "direction": direction,
                       "condition": str(condition)}

    status = str(doc.get("execution_status") or "")
    if status != EXECUTION_READY:
        _refuse(GATE_SELECTION_NOT_EXECUTABLE,
                f"the selection declares execution_status={status!r}, not {EXECUTION_READY!r}. "
                "Stage 3 projects the store onto a question STAGE 2 ACTUALLY RAN. A selection "
                "Stage 2 refused or is still awaiting an estimator for has no arms behind it, "
                "and a view over it would be an empty answer wearing a real question's id.")

    return VerifiedSelection(
        selection_id=str(doc["selection_id"]),
        question_id=derived_question,
        analysis_mode=mode,
        conditions=conditions,
        poles=poles,
        registry_scorer_view_sha256=str(content.get("registry_scorer_view_sha256") or ""),
        canonical_content_sha256=stage2_content_sha256(content),
        full_contract_content_sha256=derived_hash,
        selection_full_sha256=derive_selection_full_sha256(doc),
        # Stage-1 EMITS its own `arms` block with the exact arm keys it believes this question
        # names. Stage 3 derives them INDEPENDENTLY and then requires the two to agree
        # (`arm_selection.check_declared_arms`). Two lanes computing the same key with different
        # hands is the only way either of them can be wrong out loud.
        declared_arms=dict(doc.get("arms") or {}),
    )


def load(path: str) -> VerifiedSelection:
    """The verified question, from disk. There is no default selection and no fallback."""
    if not os.path.isfile(path):
        _refuse(GATE_SELECTION_NOT_ON_DISK,
                f"no Stage-1 v3 selection at {path!r}. Stage 3 does not have a default question: "
                "a view with no selection behind it would be one arbitrary pair's answer wearing "
                "the authority of the whole store.")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except json.JSONDecodeError as exc:
        _refuse(GATE_SELECTION_UNREADABLE,
                f"the selection at {path!r} is not readable JSON: {exc}")
    return verify(doc)


def vocabularies() -> dict[str, Any]:
    """The selection vocabulary, hashed into the view's method block."""
    return {
        "selection_schema": SELECTION_SCHEMA,
        "analysis_modes": list(ANALYSIS_MODES),
        "n_conditions_for_mode": dict(sorted(N_CONDITIONS_FOR_MODE.items())),
        "roles": list(ROLES),
        "poles": list(POLES),
        "selection_id_rule_id": SELECTION_ID_RULE_ID,
        "question_id_rule_id": QUESTION_ID_RULE_ID,
        "question_id_rule": QUESTION_ID_RULE,
        "both_identities_are_required_and_are_never_conflated": True,
        "selection_id_is_re_derived_never_read": True,
        "question_id_is_re_derived_never_read": True,
        "the_condition_lives_inside_each_pole": True,
        "pole_A_is_at_the_first_condition_and_pole_B_at_the_last": True,
        "a_pole_is_not_a_desired_change": True,
        "combined_objective_permitted": False,
    }
