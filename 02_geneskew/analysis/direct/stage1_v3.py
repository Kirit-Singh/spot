"""GATE B: the Stage-1 v3 selection contract, validated, routed and bound.

Generic by construction. There is no Treg, no Th1, no Stim48hr and no program id anywhere
in this module: the biology arrives entirely through the contract, and a special case for
one program would be a lane that silently does something different for the next one.

WHAT THIS GATE REFUSES
----------------------
  * a contract that is not exactly ``spot.stage01_selection.v3``, validated against the
    PINNED schema (its raw sha256 is checked before it is used — a schema that can be
    swapped is not a schema);
  * a contract whose own content hash does not cover its own content;
  * a contract that names two different biologies (``canonical_content`` and ``poles``
    disagreeing about a program or a direction);
  * a pole whose effect projection is UNAVAILABLE — with the pole's own typed reason
    codes carried through, never summarised into "failed";
  * ``temporal_cross_condition``, until the temporal estimator exists. It is refused as
    ``awaiting_estimator``, and it is NEVER routed through the within-condition formula.
    That is the single most dangerous thing this gate prevents: the two estimators answer
    different questions, and passing a cross-condition selection through a
    within-condition projection would produce numbers that look exactly like an answer;
  * any Stage-1 combined objective. ``combined_objective`` must be null and
    ``poles_separate`` must be true — a combined score handed down from Stage-1 would
    reintroduce, one stage earlier, the objective this whole lane exists to refuse.

THE SELECTION_ID IS RE-DERIVED, AND IT IS CHECKED (m2)
-----------------------------------------------------
This module used to declare the ``selection_id`` non-derivable — "a citation, not a key" —
and carried it verbatim, unchecked. That was wrong, and an independent audit published the
recipe:

    selection_id = sha256( canonical_json( contract.canonical_content ) )[:16]

where ``canonical_json`` is compact, sorted-key JSON — exactly what ``jq -cS`` emits.
(Verified byte-for-byte against ``jq -cS '.canonical_content' | shasum -a 256`` in
``test_stage1_v3_selection_id``.)

So it IS derivable, it IS derived here, and a contract whose declared ``selection_id``
disagrees with its own canonical content is REFUSED
(``REFUSE_SELECTION_ID``). An id nobody recomputes is a label, and a label can be moved
onto a different contract without anything noticing.

Stage-2 additionally keys its own results on the biology it ACTUALLY READ
(``selection_biology_sha256``), bound into ``stage2_run_id`` — so two different selections
can never share a Stage-2 run id even if a producer somehow reused an id.

THE HISTORICAL GATE IS NOT A GATE
---------------------------------
``historical_validation_provenance.active_gate`` is false, and this module treats it that
way: the frozen selectability artifact is bound as provenance and never consulted to
decide whether anything may run. The retired 0-of-33 production gate is gone, and nothing
here resurrects it.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from . import config, convergence, enrichment, pathway
from .hashing import content_hash, file_sha256

SCHEMA_ID = "spot.stage01_selection.v3"
# The PINNED schema. A schema that can be swapped is not a schema.
SCHEMA_SHA256 = "f4c2c2cc83b739ffba48286e22a7471cb5f83f0ff15e06f2bb377817382ad8e8"

STAGE1_METHOD_VERSION = "stage1-continuous-v3.0.1"

# The frozen enums. EXACT — a value outside them is refused, never coerced.
EXECUTION_READY = "ready"
EXECUTION_REFUSED = "refused"
EXECUTION_AWAITING = "awaiting_estimator"
EXECUTION_STATUSES = (EXECUTION_READY, EXECUTION_REFUSED, EXECUTION_AWAITING)

ESTIMATOR_AVAILABLE = "available"
ESTIMATOR_NOT_IMPLEMENTED = "not_implemented"
ESTIMATOR_STATUSES = (ESTIMATOR_AVAILABLE, ESTIMATOR_NOT_IMPLEMENTED)

MODE_WITHIN = "within_condition"
MODE_TEMPORAL = "temporal_cross_condition"
ANALYSIS_MODES = (MODE_WITHIN, MODE_TEMPORAL)

PROJECTION_AVAILABLE = "available"
PROJECTION_UNAVAILABLE = "unavailable"
PROJECTION_STATUSES = (PROJECTION_AVAILABLE, PROJECTION_UNAVAILABLE)

# WHICH estimator each mode routes to. The temporal one does not exist yet, and this
# table is the only place that decides — so it cannot be quietly bypassed.
ESTIMATOR_WITHIN = "within_condition_v1"
ESTIMATOR_TEMPORAL = "temporal_cross_condition_v1"
ESTIMATOR_FOR_MODE = {MODE_WITHIN: ESTIMATOR_WITHIN, MODE_TEMPORAL: ESTIMATOR_TEMPORAL}

# WHICH estimators Stage-2 has actually built. STAGE-2 DECIDES THIS — a contract cannot
# vote itself an estimator, and this table is the only place that says.
#
# The temporal estimator is a DIFFERENT measurement: it compares ACROSS conditions, and
# routing it through the within-condition formula would return numbers that look exactly
# like an answer. It was therefore refused here until it existed. It NOW EXISTS
# (``direct.temporal``: a population-level difference-in-differences on program
# projections, inference_status=not_calibrated) and it is admitted by a fail-closed
# independent verifier, so it is built, and a temporal selection is READY rather than
# awaiting_estimator.
#
# What each estimator IS, so the bridge can bind the thing it is admitting rather than a
# name: see ``estimator_registry()``.
IMPLEMENTED_ESTIMATORS = (ESTIMATOR_WITHIN, ESTIMATOR_TEMPORAL)

# Typed refusal reasons. Every refusal is one of these; none is a sentence.
REFUSE_SCHEMA = "selection_schema_is_not_v3"
REFUSE_SCHEMA_PIN = "selection_json_schema_is_not_the_pinned_schema"
REFUSE_CONTENT_HASH = "contract_content_hash_does_not_cover_its_own_content"
REFUSE_BIOLOGY_SPLIT = "canonical_content_and_poles_name_different_biology"
REFUSE_COMBINED = "stage1_handed_down_a_combined_objective"
REFUSE_POLE_UNAVAILABLE = "pole_effect_projection_unavailable"
REFUSE_POLE_NOT_IN_UNIVERSE = "pole_program_not_in_the_current_effect_universe"
REFUSE_ESTIMATOR_MISSING = "estimator_not_implemented_in_stage2"
REFUSE_ESTIMATOR_OVERCLAIM = "estimator_declared_available_but_stage2_has_not_built_it"
REFUSE_MODE_ROUTE = "analysis_mode_does_not_match_its_estimator"
REFUSE_STATUS = "execution_status_does_not_follow_from_the_contract"
REFUSE_STAGE1_METHOD = "stage1_method_version_is_not_the_accepted_v3"
REFUSE_HISTORICAL_GATE = "historical_selectability_is_being_used_as_a_live_gate"
REFUSE_CONDITIONS = "condition_count_does_not_match_the_analysis_mode"

REFUSE_SELECTION_ID = "selection_id_does_not_derive_from_its_own_canonical_content"

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


def estimator_registry() -> dict[str, Any]:
    """WHAT Stage-2 has built, and WHAT each estimator is — for the Stage-1 v3 bridge.

    The bridge sets ``estimator_status`` and ``execution_status``, and it must be able to
    bind the METHOD it is admitting, not merely a name. A contract that says "temporal,
    available" while naming no method hash has admitted a word.

    Import-light on purpose: the temporal method hash is resolved lazily, so a caller
    that only wants to know WHICH estimators exist does not pay for the policy artifact.
    """
    reg: dict[str, Any] = {
        ESTIMATOR_WITHIN: {
            "estimator_id": ESTIMATOR_WITHIN,
            "analysis_mode": MODE_WITHIN,
            "n_conditions": 1,
            "status": ESTIMATOR_AVAILABLE,
            "method_id": config.METHOD_ID,
            "method_version": config.METHOD_VERSION,
            "inference_status": config.INFERENCE_STATUS,
        },
        ESTIMATOR_TEMPORAL: {
            "estimator_id": ESTIMATOR_TEMPORAL,
            "analysis_mode": MODE_TEMPORAL,
            # a cross-condition estimate compares exactly two conditions, IN ORDER
            "n_conditions": 2,
            "status": (ESTIMATOR_AVAILABLE if ESTIMATOR_TEMPORAL in
                       IMPLEMENTED_ESTIMATORS else ESTIMATOR_NOT_IMPLEMENTED),
        },
    }
    from .temporal import config as tconfig
    from .temporal import policy as tpolicy
    from .temporal import run_temporal as trun

    reg[ESTIMATOR_TEMPORAL].update({
        "method_id": tconfig.ESTIMATOR_ID,
        "method_version": tconfig.ESTIMATOR_VERSION,
        "estimand_id": tconfig.ESTIMAND_ID,
        "estimand_level": tconfig.ESTIMAND_LEVEL,
        "estimand_is_per_cell_fate": tconfig.ESTIMAND_IS_PER_CELL_FATE,
        "inference_status": tconfig.INFERENCE_STATUS,
        # THE HASH THE BRIDGE BINDS. It covers the temporal method, the within-condition
        # method it differences, the frozen batch policy and both code trees — so a
        # contract admitted against it cannot silently be executed by a different one.
        "method_sha256": trun.temporal_method_sha256(tpolicy.load()),
    })
    return reg


class SelectionV3Error(ValueError):
    """The Stage-1 v3 selection is not usable. Refuse; never repair."""

    def __init__(self, reason: str, message: str):
        super().__init__(f"[{reason}] {message}")
        self.reason = reason


def _refuse(reason: str, message: str) -> None:
    raise SelectionV3Error(reason, message)


def load_schema(path: str) -> dict[str, Any]:
    """The pinned v3 JSON Schema. Its BYTES are checked before it is trusted."""
    actual = file_sha256(path)
    if actual != SCHEMA_SHA256:
        _refuse(REFUSE_SCHEMA_PIN,
                f"the selection schema at {os.path.basename(path)!r} hashes to "
                f"{actual!r}, not the pinned {SCHEMA_SHA256!r}. A schema that can be "
                "swapped validates whatever the swapper wanted it to")
    with open(path) as fh:
        return json.load(fh)


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

    Stage-1's ``selection_id`` derivation is not published in the frozen contract, so
    Stage-2 cannot recompute it and does not pretend to. It keys its own results on this
    instead, so two different selections can never share a stage2_run_id — whatever their
    selection_ids happen to say.
    """
    return content_hash(selection_biology(doc))


def validate(doc: dict[str, Any], schema: dict[str, Any],
             effect_universe_programs: Optional[set[str]] = None) -> dict[str, Any]:
    """Every refusal, in order. Returns the routed, bound selection."""
    import jsonschema

    if str(doc.get("schema_version")) != SCHEMA_ID:
        _refuse(REFUSE_SCHEMA,
                f"schema_version must be exactly {SCHEMA_ID!r}, got "
                f"{doc.get('schema_version')!r}; a v2 selection is not a v3 selection "
                "and is never migrated in place")
    try:
        jsonschema.validate(doc, schema)
    except jsonschema.ValidationError as exc:
        _refuse(REFUSE_SCHEMA, f"the selection does not satisfy {SCHEMA_ID}: "
                               f"{exc.message}")

    c = doc["canonical_content"]

    # ---- the contract must hash its own content ----
    payload = {k: v for k, v in doc.items() if k != "full_contract_content_sha256"}
    derived = content_hash(payload)
    if derived != doc["full_contract_content_sha256"]:
        _refuse(REFUSE_CONTENT_HASH,
                f"full_contract_content_sha256 is {doc['full_contract_content_sha256']!r} "
                f"but the contract's own content hashes to {derived!r}. A contract whose "
                "hash does not cover its content has not been bound to anything")

    # ---- the SELECTION_ID must derive from the contract's own canonical content (m2) ----
    # It used to be carried verbatim and unchecked, on the grounds that the rule was not
    # published. The rule IS published. An id nobody recomputes is a label, and a label
    # can be moved onto a different contract without anything noticing.
    declared_id = str(doc["selection_id"])
    derived_id = derive_selection_id(doc)
    if declared_id != derived_id:
        _refuse(REFUSE_SELECTION_ID,
                f"selection_id is {declared_id!r} but the contract's own "
                f"canonical_content derives {derived_id!r} "
                f"(rule: {SELECTION_ID_RULE}). A selection whose id does not follow from "
                "the biology it names could be pointed at a different biology and keep "
                "its name")

    # ---- Stage-1 must be the accepted v3 method ----
    if str(c["stage1_method_version"]) != STAGE1_METHOD_VERSION:
        _refuse(REFUSE_STAGE1_METHOD,
                f"stage1_method_version is {c['stage1_method_version']!r}, expected "
                f"{STAGE1_METHOD_VERSION!r}")

    # ---- NO COMBINED OBJECTIVE, handed down or otherwise ----
    if c.get("combined_objective") is not None or c.get("poles_separate") is not True:
        _refuse(REFUSE_COMBINED,
                f"canonical_content declares combined_objective="
                f"{c.get('combined_objective')!r} / poles_separate="
                f"{c.get('poles_separate')!r}. The poles are an ORDERED PAIR of separate "
                "questions; a combined score handed down from Stage-1 would reintroduce, "
                "one stage earlier, the objective this lane exists to refuse")

    # ---- ONE biology. The two blocks may not disagree about it ----
    for pole in ("A", "B"):
        for field in ("program_id", "direction"):
            if str(c[pole][field]) != str(doc["poles"][pole][field]):
                _refuse(REFUSE_BIOLOGY_SPLIT,
                        f"canonical_content.{pole}.{field}={c[pole][field]!r} but "
                        f"poles.{pole}.{field}={doc['poles'][pole][field]!r}. The "
                        "contract names two different biologies, and whichever one is "
                        "read first decides what gets measured")

    # ---- the CONDITION COUNT is decided by the mode, not by the caller ----
    mode = str(c["analysis_mode"])
    n_cond = len(c["conditions"])
    if mode == MODE_WITHIN and n_cond != 1:
        _refuse(REFUSE_CONDITIONS,
                f"{MODE_WITHIN} names {n_cond} condition(s); a within-condition estimate "
                "is made inside exactly one condition")
    if mode == MODE_TEMPORAL and n_cond != 2:
        _refuse(REFUSE_CONDITIONS,
                f"{MODE_TEMPORAL} names {n_cond} condition(s); a cross-condition "
                "estimate compares exactly two, in order")

    # ---- EVERY POLE, against the CURRENT effect universe ----
    for pole in ("A", "B"):
        p = doc["poles"][pole]
        if str(p["effect_projection_status"]) != PROJECTION_AVAILABLE:
            _refuse(REFUSE_POLE_UNAVAILABLE,
                    f"pole {pole} ({p['program_id']}): effect_projection_status is "
                    f"{p['effect_projection_status']!r} with reason_codes "
                    f"{list(p.get('reason_codes') or [])} "
                    f"(n_panel_in_effect_universe={p['n_panel_in_effect_universe']}, "
                    f"n_control_in_effect_universe={p['n_control_in_effect_universe']}). "
                    "A pole that cannot be projected cannot be measured, and a screen "
                    "that scores it anyway is scoring an axis it does not have")
        if effect_universe_programs is not None \
                and str(p["program_id"]) not in effect_universe_programs:
            _refuse(REFUSE_POLE_NOT_IN_UNIVERSE,
                    f"pole {pole}: program {p['program_id']!r} is not in the current "
                    "effect universe. The contract was minted against a different "
                    "universe than the one this run holds")

    # ---- ROUTING. The temporal estimator does not exist, and is not faked ----
    estimator = str(doc["estimator_id"])
    if ESTIMATOR_FOR_MODE[mode] != estimator:
        _refuse(REFUSE_MODE_ROUTE,
                f"analysis_mode {mode!r} routes to {ESTIMATOR_FOR_MODE[mode]!r}, but the "
                f"contract names estimator_id {estimator!r}")

    declared = str(doc["estimator_status"])
    built = estimator in IMPLEMENTED_ESTIMATORS
    if declared == ESTIMATOR_AVAILABLE and not built:
        _refuse(REFUSE_ESTIMATOR_OVERCLAIM,
                f"the contract declares estimator {estimator!r} available, but Stage-2 "
                f"has built only {list(IMPLEMENTED_ESTIMATORS)}. Stage-2 decides what "
                "Stage-2 has implemented; a contract cannot vote itself an estimator")
    if not built:
        _refuse(REFUSE_ESTIMATOR_MISSING,
                f"estimator {estimator!r} is not implemented in Stage-2. A "
                f"{MODE_TEMPORAL} selection is a DIFFERENT measurement — it compares "
                "across conditions — and it is refused here rather than routed through "
                "the within-condition formula, which would return numbers that look "
                "exactly like an answer")

    # ---- the EXECUTION STATUS must FOLLOW from all of the above ----
    expected = EXECUTION_READY if built else EXECUTION_AWAITING
    if str(doc["execution_status"]) != expected:
        _refuse(REFUSE_STATUS,
                f"execution_status is {doc['execution_status']!r}, but the contract's own "
                f"content implies {expected!r}. A status that does not follow from the "
                "contract was not computed from it")

    # ---- the HISTORICAL gate is never a live gate ----
    if doc["historical_validation_provenance"].get("active_gate") is not False:
        _refuse(REFUSE_HISTORICAL_GATE,
                "historical_validation_provenance.active_gate is not false. The frozen "
                "selectability artifact is PROVENANCE; the retired 0-of-33 production "
                "gate is gone and is not resurrected here")

    return bind(doc)


def bind(doc: dict[str, Any]) -> dict[str, Any]:
    """What Stage-2 stands on, and what it will hash into its run id."""
    c = doc["canonical_content"]
    return {
        "schema_version": SCHEMA_ID,
        "selection_origin": doc["selection_origin"],
        # RE-DERIVED and CHECKED (m2), not carried on trust. `validate` refuses a contract
        # whose declared id does not follow from its own canonical content.
        "selection_id": doc["selection_id"],
        "selection_id_rederived": derive_selection_id(doc),
        "selection_id_rule_id": SELECTION_ID_RULE_ID,
        "selection_id_rule": SELECTION_ID_RULE,
        "canonical_content_sha256": canonical_content_sha256(doc),
        "selection_full_sha256": doc["selection_full_sha256"],
        "full_contract_content_sha256": doc["full_contract_content_sha256"],
        # ...and the key Stage-2 DOES use: the biology it actually read.
        "selection_biology_sha256": selection_biology_sha256(doc),
        "biology": selection_biology(doc),
        "analysis_mode": c["analysis_mode"],
        "conditions": list(c["conditions"]),
        "estimator_id": doc["estimator_id"],
        "estimator_status": doc["estimator_status"],
        "execution_status": doc["execution_status"],
        "stage1_method_version": c["stage1_method_version"],
        "dataset_id": c["dataset_id"],
        "donor_scope": c["donor_scope"],
        "effect_universe_id": c["effect_universe_id"],
        "registry_scorer_view_sha256": c["registry_scorer_view_sha256"],
        "source_h5ad_sha256": c["source_h5ad_sha256"],
        "source_hf_revision": c["source_hf_revision"],
        "poles": {p: dict(doc["poles"][p]) for p in ("A", "B")},
        "trust_bindings": dict(doc["trust_bindings"]),
        "provenance_bindings": dict(doc["provenance_bindings"]),
        "historical_validation_provenance": dict(
            doc["historical_validation_provenance"]),
        "combined_objective": None,
        "poles_separate": True,
    }


# --------------------------------------------------------------------------- #
# B3 — THE ONE VERIFIED TYPED V3 OBJECT.
#
# The temporal runner used to reach into a v3 contract, pull out its CONDITIONS, and then
# execute everything else from the LEGACY `args.selection`: legacy poles, legacy axis,
# legacy analysis_condition, legacy run binding. A valid v3 request for
# `GHOST_A -> GHOST_B, Stim48hr -> Rest` therefore came back with the `diff_naive` /
# `th17_like` axes, BOTH directions, and no trace of the v3 contract in its identity — and
# it still ADMITTED. It answered a different question and called it an answer.
#
# So there is now exactly ONE object, produced by the FULL v3 gate, and it carries the
# biology, the ORDER and the identity together. Nothing downstream may take one of those
# from the contract and the others from somewhere else.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class V3Selection:
    """A validated v3 contract, in the shape the Stage-2 lanes consume.

    Duck-compatible with ``selection.Selection`` on the fields the run binding reads, so a
    v3 run is not a second code path through emit/provenance — it is the same path with a
    contract that actually says what was asked for.
    """
    a: Any                       # selection.Pole
    b: Any                       # selection.Pole
    lane: str
    analysis_mode: str
    conditions: tuple[str, ...]  # ORDERED. For temporal: (from_condition, to_condition).
    analysis_condition: str      # the FROM endpoint; a within-condition run's one condition
    question_id: str
    selection_id: str
    registry_sha256: str
    stage1_method_version: str
    contract_sha256: str         # the v3 FULL-CONTRACT content hash
    selection_biology_sha256: str
    estimator_id: str
    execution_status: str
    bound: dict[str, Any]        # the whole validated v3 bind()
    raw: dict[str, Any]

    # the legacy Selection carries these; a v3 contract binds its Stage-1 trust
    # differently (trust_bindings / provenance_bindings), so they are explicitly absent
    # rather than silently faked
    stage1_input_manifest_sha256: Optional[str] = None
    stage1_code_sha256: Optional[str] = None
    stage1_validation_sha256: Optional[str] = None

    @property
    def from_condition(self) -> str:
        return self.conditions[0]

    @property
    def to_condition(self) -> str:
        return self.conditions[-1]

    @property
    def is_temporal(self) -> bool:
        return self.analysis_mode == MODE_TEMPORAL


def as_selection(bound: dict[str, Any], doc: dict[str, Any],
                 lane: str) -> V3Selection:
    """The validated v3 contract, as the ONE object the lanes execute."""
    from .selection import Pole

    poles = bound["poles"]
    conditions = tuple(bound["conditions"])
    return V3Selection(
        a=Pole(program_id=str(poles["A"]["program_id"]),
               direction=str(poles["A"]["direction"])),
        b=Pole(program_id=str(poles["B"]["program_id"]),
               direction=str(poles["B"]["direction"])),
        lane=lane,
        analysis_mode=str(bound["analysis_mode"]),
        conditions=conditions,
        analysis_condition=conditions[0],
        question_id=str(bound["selection_biology_sha256"]),
        selection_id=str(bound["selection_id"]),
        registry_sha256=str(bound["registry_scorer_view_sha256"]),
        stage1_method_version=str(bound["stage1_method_version"]),
        contract_sha256=str(bound["full_contract_content_sha256"]),
        selection_biology_sha256=str(bound["selection_biology_sha256"]),
        estimator_id=str(bound["estimator_id"]),
        execution_status=str(bound["execution_status"]),
        bound=bound,
        raw=doc,
    )


def reverify_full_contract_hash(doc: dict[str, Any]) -> str:
    """Recompute the v3 full-contract hash from the contract's OWN content, and prove it.

    ``validate`` already checks this at load. It is re-checked HERE, at the point the run
    identity binds it, because a hash that is verified once and then carried around as a
    string is a string — and the run binding is exactly where a swapped one would land.
    """
    payload = {k: v for k, v in doc.items() if k != "full_contract_content_sha256"}
    derived = content_hash(payload)
    declared = str(doc.get("full_contract_content_sha256"))
    if derived != declared:
        _refuse(REFUSE_CONTENT_HASH,
                f"full_contract_content_sha256 is {declared!r} but the contract's own "
                f"content hashes to {derived!r}")
    return derived


def bind_axis(sel: V3Selection, release) -> dict[str, Any]:
    """The A/B axis, built from THE V3 CONTRACT'S OWN POLES. Never from a legacy one.

    Same registry lookup, same panel/control extraction and the same independently
    derived selectability the within-condition binder applies — but keyed on the programs
    the v3 contract actually named. This is what makes ``GHOST_A -> GHOST_B`` come back as
    GHOST_A and GHOST_B rather than as whatever the legacy contract happened to say.

    For a TEMPORAL selection the gate is evaluated at BOTH endpoints: a pair is only
    executable if each pole is selectable at each condition it is being compared across.
    """
    from . import config as _cfg
    from .selection import SelectionError

    out: dict[str, Any] = {
        "release_kind": release.kind,
        "registry_hash_binding": "independently_derived_canonical_content",
        "gate_evidence": release.gate_evidence,
        "may_confer_stage3_eligibility": release.may_confer_stage3_eligibility,
        "analysis_mode": sel.analysis_mode,
        "conditions": list(sel.conditions),
    }
    selectability: dict[str, Any] = {}
    for key, pole in (("A", sel.a), ("B", sel.b)):
        prog = release.programs.get(pole.program_id)
        if prog is None:
            raise SelectionError(
                f"v3 selection: program {pole.program_id!r} ({key}) is not in the bound "
                "Stage-1 registry. The contract names an axis the release does not ship, "
                "and a run that substituted a different one would answer a different "
                "question")
        per_condition = {}
        for cond in sel.conditions:
            per_condition[cond] = (pole.program_id, cond) in release.selectable_pairs
        selectability[key] = {
            "program_conditions": [f"{pole.program_id}|{c}" for c in sel.conditions],
            "selectable_derived_by_condition": per_condition,
            "rule_id": _cfg.SELECTABILITY_RULE_ID,
            "stored_boolean_read": False,
        }
        panel = prog.get("panel_ensembl")
        control = prog.get("control_ensembl")
        if not (isinstance(panel, list) and panel):
            raise SelectionError(
                f"registry program {pole.program_id!r}: panel_ensembl missing")
        if not (isinstance(control, list) and control):
            raise SelectionError(
                f"registry program {pole.program_id!r}: control_ensembl missing")
        out[key] = {
            "program_id": pole.program_id,
            "direction": pole.direction,
            "sign": pole.sign,
            "panel": [str(g) for g in panel],
            "control": [str(g) for g in control],
        }
    out["selectability"] = selectability
    out["namespace"] = ("production" if release.kind == "production"
                        else _cfg.RESEARCH_NAMESPACE if release.kind == "research"
                        else "synthetic")
    out["production_eligible"] = (release.kind == "production")
    out["stage3_eligible"] = (release.kind == "production")
    out["may_write_production_pointer"] = release.may_write_production_pointer
    out["production_gate_passed"] = bool(release.selectable_pairs)
    return out


def load_selection(args, expect_mode: Optional[str] = None):
    """THE ONE VERIFIED TYPED V3 OBJECT, for ANY lane. ``None`` when none was supplied.

    B3. Direct and Pathway used to consume only the LEGACY single-condition contract shape,
    so a v3 object failed their loaders outright — a real v3 selection could not drive them
    at all. They now take the same typed object the temporal lane does, through the same
    full gate, and the axis is built from ITS poles.

    ``expect_mode`` refuses a contract for a different analysis mode BY NAME. The two
    estimators answer different questions and their numbers look alike, so a
    within-condition runner must never silently execute a cross-condition selection or the
    other way round.
    """
    path = getattr(args, "stage1_v3_selection", None)
    schema = getattr(args, "stage1_v3_schema", None)
    if not path:
        return None
    if not schema:
        raise SelectionV3Error(
            REFUSE_SCHEMA_PIN,
            "--stage1-v3-selection requires --stage1-v3-schema: the contract is validated "
            "against the PINNED schema, and a contract checked against no schema has been "
            "checked against nothing")
    with open(path) as fh:
        doc = json.load(fh)
    bound = validate(doc, load_schema(schema))
    if expect_mode is not None and bound["analysis_mode"] != expect_mode:
        raise SelectionV3Error(
            REFUSE_MODE_ROUTE,
            f"this runner executes {expect_mode!r}, but the v3 selection declares "
            f"analysis_mode {bound['analysis_mode']!r}. The two estimators answer "
            "different questions and their numbers look alike, so the wrong one is never "
            "silently executed")
    lane = getattr(args, "lane", None) or "production"
    return as_selection(bound, doc, lane)


def load(path: str, schema_path: str,
         effect_universe_programs: Optional[set[str]] = None) -> dict[str, Any]:
    with open(path) as fh:
        doc = json.load(fh)
    return validate(doc, load_schema(schema_path), effect_universe_programs)


# --------------------------------------------------------------------------- #
# THE IDENTIFIER HIERARCHY: selection_id -> stage2_run_id.
#
# A Stage-2 result is NOT keyed by the Stage-1 selection. The same selection, screened
# with a different method, a different config, a different effect universe, a different
# perturbation source, a different mask rule or a different pathway method, is a
# DIFFERENT RESULT — and one that shared its key would silently overwrite the other.
# --------------------------------------------------------------------------- #
def stage2_run_binding(selection: dict[str, Any], *,
                       effect_universe_sha256: str,
                       perturbation_source_hashes: dict[str, str],
                       direct_config_sha256: str) -> dict[str, Any]:
    """Everything a Stage-2 run id must bind. Method-aware by construction."""
    return {
        "selection_id": selection["selection_id"],
        "selection_biology_sha256": selection["selection_biology_sha256"],
        "analysis_mode": selection["analysis_mode"],
        "estimator_id": selection["estimator_id"],
        "conditions": list(selection["conditions"]),
        "direct_method_version": config.METHOD_VERSION,
        "direct_config_sha256": direct_config_sha256,
        "effect_universe_sha256": effect_universe_sha256,
        "perturbation_source_hashes": dict(sorted(perturbation_source_hashes.items())),
        "mask_method_version": config.MASK_METHOD_VERSION,
        "pathway_method_version": pathway.SCHEMA_VERSION,
        "enrichment_method_id": enrichment.METHOD_ID,
        "convergence_method_id": convergence.METHOD_ID,
    }


def stage2_run_id(binding: dict[str, Any]) -> str:
    """16 hex over the whole binding. A changed method is a changed run."""
    return content_hash(binding)[:16]
