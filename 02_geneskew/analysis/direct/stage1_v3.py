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

THE SELECTION_ID IS A CITATION, NOT A KEY
-----------------------------------------
The frozen contract states that ``selection_id`` is a 16-hex biological id, invariant
over the scoring-view hash. It does NOT publish the rule that derives it, so Stage-2
cannot recompute it and does not pretend to: it is carried verbatim as provenance.

What Stage-2 keys its own results on is the biology it ACTUALLY READ — re-derived here as
``selection_biology_sha256`` and bound into ``stage2_run_id``. So two different selections
can never share a Stage-2 run id, whatever their selection_ids say. See
``STAGE1_SELECTION_ID_NOT_REDERIVABLE`` for the exact boundary this leaves.

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

# WHICH estimators Stage-2 has actually built. The temporal estimator is a DIFFERENT
# measurement — it compares across conditions — and until it exists and is verified, a
# temporal selection is refused rather than routed through the within-condition formula.
IMPLEMENTED_ESTIMATORS = (ESTIMATOR_WITHIN,)

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

# The boundary this gate cannot cross, stated once, as an id.
STAGE1_SELECTION_ID_NOT_REDERIVABLE = (
    "spot.stage02.gate_b.selection_id_is_a_citation_not_a_recomputable_key.v1")


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
        # carried VERBATIM as provenance. Stage-2 cannot recompute it and does not key on
        # it — see STAGE1_SELECTION_ID_NOT_REDERIVABLE.
        "selection_id": doc["selection_id"],
        "selection_full_sha256": doc["selection_full_sha256"],
        "full_contract_content_sha256": doc["full_contract_content_sha256"],
        "selection_id_rule_id": STAGE1_SELECTION_ID_NOT_REDERIVABLE,
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
