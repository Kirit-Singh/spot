"""GATE B: the Stage-1 v3 selection contract. Generic — no program is special.

There is no Treg, no Th1 and no Stim48hr anywhere in the gate or in these tests: the
biology arrives through the contract, and the fixture emitter takes it as a parameter.
A gate with a program name in it is a gate that does something different for the next
program, which is the one nobody will check.

THE MOST DANGEROUS THING THIS GATE PREVENTS
-------------------------------------------
Routing a ``temporal_cross_condition`` selection through the within-condition estimator.
They answer different questions — one measures inside a condition, the other compares
across two — and the within-condition formula would happily consume a temporal selection
and return numbers. The numbers would look exactly like an answer. There would be nothing
wrong with them except that they answer a question nobody asked.

So the temporal mode is refused, by name, until Stage-2 actually builds the estimator.
Every other refusal below is typed too: a gate that fails with a sentence is a gate whose
failures cannot be branched on.
"""
from __future__ import annotations

import copy
import json
import os

import fixtures_stage1_contract as S1
import pytest
from direct import stage1_v3 as G
from direct.hashing import content_hash

# The AUTHORITATIVE schema, materialised from git at the pinned Stage-1 commit — never from
# a path on one developer's machine. The old host path held the STALE f4c2 schema, so this
# whole module was green against a schema nobody could audit. See fixtures_stage1_contract.
SCHEMA_PATH = S1.schema_path()

SHA = "a" * 64
TRUST_KEYS = ("validation_raw_sha256", "validation_semantics_raw_sha256",
              "validation_semantics_self_canonical_sha256", "gate_spec_raw_sha256",
              "constituent_main_content_canonical_sha256",
              "constituent_overlay_donor_content_canonical_sha256",
              "marker_diagnostics_content_sha256", "scoring_view_raw_sha256",
              "scoring_view_canonical_sha256")


@pytest.fixture(scope="module")
def schema():
    return G.load_schema(SCHEMA_PATH)


def emit(a="prog_alpha", dir_a="high", b="prog_beta", dir_b="low",
         mode=G.MODE_WITHIN, conditions=None, available=True,
         estimator_status=None, execution_status=None, **over):
    """A schema-valid v3 selection for ANY biology. Nothing here is program-specific."""
    conditions = conditions or (["Rest"] if mode == G.MODE_WITHIN
                                else ["Rest", "Stim48hr"])
    estimator = G.ESTIMATOR_FOR_MODE[mode]
    built = estimator in G.IMPLEMENTED_ESTIMATORS
    if estimator_status is None:
        estimator_status = (G.ESTIMATOR_AVAILABLE if built
                            else G.ESTIMATOR_NOT_IMPLEMENTED)
    if execution_status is None:
        execution_status = G.EXECUTION_READY if built else G.EXECUTION_AWAITING

    def pole(program, direction):
        return {
            "program_id": program, "direction": direction,
            "effect_projection_status": (G.PROJECTION_AVAILABLE if available
                                         else G.PROJECTION_UNAVAILABLE),
            "n_measured": 120,
            "n_panel_in_effect_universe": 30 if available else 1,
            "n_control_in_effect_universe": 40 if available else 2,
            "reason_codes": [] if available else ["panel_below_effect_universe_min"],
        }

    doc = {
        "schema_version": G.SCHEMA_ID,
        "selection_origin": "fixture",
        "execution_status": execution_status,
        "analysis_mode": mode,
        "estimator_id": estimator,
        "estimator_status": estimator_status,
        "selection_id": "0123456789abcdef",
        "selection_full_sha256": SHA,
        "canonical_content": {
            "A": {"program_id": a, "score_field": f"{a}_score", "direction": dir_a},
            "B": {"program_id": b, "score_field": f"{b}_score", "direction": dir_b},
            "analysis_mode": mode,
            "combined_objective": None,
            "poles_separate": True,
            "conditions": list(conditions),
            "dataset_id": "ds1",
            "donor_scope": "all_donor",
            "effect_universe_id": "eu1",
            "registry_scorer_view_sha256": SHA,
            "source_h5ad_sha256": SHA,
            "source_hf_revision": "rev1",
            "stage1_method_version": G.STAGE1_METHOD_VERSION,
        },
        "poles": {"A": pole(a, dir_a), "B": pole(b, dir_b)},
        "trust_bindings": {k: SHA for k in TRUST_KEYS},
        "provenance_bindings": {"primary_registry_v3_raw_sha256": SHA},
        "historical_validation_provenance": {
            "kind": "frozen_lomo_within_condition_validation_v3",
            "selectability_v3_raw_sha256": SHA,
            "active_gate": False},
    }
    doc.update(over)
    # question_id / arms / estimator: REQUIRED by the v3 schema, and the question_id is
    # computed by an INDEPENDENT implementation of Stage-1's published recipe (never by the
    # gate's own derive_question_id — that would prove only that it equals itself). An
    # explicit override in `over` is kept: that is how the forgery paths are written.
    S1.complete(doc)
    return reseal(doc)


def reseal(doc, derive_id=True):
    """Seal the contract the way an HONEST producer does.

    The selection_id DERIVES from canonical_content (m2), so it is computed before the
    full-contract hash is taken over the finished document. ``derive_id=False`` keeps a
    caller-supplied id — the forgery path the gate must refuse.
    """
    if derive_id:
        doc["selection_id"] = G.derive_selection_id(doc)
    payload = {k: v for k, v in doc.items() if k != "full_contract_content_sha256"}
    doc["full_contract_content_sha256"] = content_hash(payload)
    return doc


def refusal(doc, schema, **kw):
    with pytest.raises(G.SelectionV3Error) as exc:
        G.validate(doc, schema, **kw)
    return exc.value.reason


# --------------------------------------------------------------------------- #
# 1. THE HONEST CONTRACT ROUTES.
# --------------------------------------------------------------------------- #
def test_a_within_condition_selection_is_READY_and_routes_to_the_direct_estimator(
        schema):
    bound = G.validate(emit(), schema)
    assert bound["execution_status"] == G.EXECUTION_READY
    assert bound["estimator_id"] == G.ESTIMATOR_WITHIN
    assert bound["analysis_mode"] == G.MODE_WITHIN
    assert len(bound["conditions"]) == 1


@pytest.mark.parametrize("a,dir_a,b,dir_b", [
    ("p1", "high", "p2", "low"),
    ("anything", "low", "anything_else", "high"),
    ("x", "high", "y", "high"),
])
def test_the_gate_is_GENERIC_over_any_typed_selection(schema, a, dir_a, b, dir_b):
    """No program is special. The gate never names one."""
    bound = G.validate(emit(a=a, dir_a=dir_a, b=b, dir_b=dir_b), schema)
    assert bound["biology"]["A"] == {"program_id": a, "direction": dir_a}
    assert bound["biology"]["B"] == {"program_id": b, "direction": dir_b}


def _executable_tokens(path):
    """Every identifier and non-docstring string literal. Docstrings are excluded on
    purpose: the module EXPLAINS that it names no program, and that prose is what stops
    the next person adding one."""
    import ast

    tree = ast.parse(open(path).read())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))

    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docstrings:
            out.add(node.value)
    return out


def test_GATE_B_NAMES_NO_PROGRAM_AND_NO_CONDITION():
    """A gate with a program name in it does something different for the next program —
    which is the one nobody will check. Scanned by AST, so the docstring that explains
    the rule does not trip it."""
    tokens = _executable_tokens(G.__file__)
    banned = ("treg", "th1", "Treg", "Th1", "Stim48hr", "Stim8hr", "Rest",
              "tfh", "naive", "memory")
    hits = sorted({b for b in banned for t in tokens if b in t})
    assert not hits, f"Gate B hard-codes a program or condition: {hits}"


# --------------------------------------------------------------------------- #
# 2. TEMPORAL IS REFUSED. It is NEVER routed through the within-condition formula.
# --------------------------------------------------------------------------- #
# B3: the estimator now EXISTS. The gate's job flips from "refuse until it is built" to
# "admit it, and only under the identity it actually has". Both states are asserted: the
# REFUSED path is exercised by simulating an absent estimator, so the guard that stopped
# a temporal selection being routed through the within-condition formula is still proven.
def test_a_temporal_selection_is_READY_now_that_the_estimator_EXISTS(schema):
    """The estimator is built (``direct.temporal``) and independently verified, so a
    temporal contract is executable rather than parked."""
    bound = G.validate(emit(mode=G.MODE_TEMPORAL), schema)
    assert bound["execution_status"] == G.EXECUTION_READY
    assert bound["estimator_status"] == G.ESTIMATOR_AVAILABLE
    assert bound["estimator_id"] == G.ESTIMATOR_TEMPORAL
    assert bound["analysis_mode"] == G.MODE_TEMPORAL
    assert len(bound["conditions"]) == 2          # an ordered PAIR


def test_a_temporal_selection_is_REFUSED_when_the_estimator_is_ABSENT(schema,
                                                                      monkeypatch):
    """The guard that mattered, still proven.

    If the temporal estimator were not built, the within-condition formula would happily
    consume a temporal selection and return numbers — and the numbers would look exactly
    like an answer. Simulate its absence and the gate must still refuse.
    """
    monkeypatch.setattr(G, "IMPLEMENTED_ESTIMATORS", (G.ESTIMATOR_WITHIN,))
    doc = emit(mode=G.MODE_TEMPORAL, estimator_status=G.ESTIMATOR_NOT_IMPLEMENTED,
               execution_status=G.EXECUTION_AWAITING)
    assert refusal(doc, schema) == G.REFUSE_ESTIMATOR_MISSING


def test_an_estimator_STAGE2_HAS_NOT_BUILT_cannot_vote_itself_available(schema,
                                                                        monkeypatch):
    """Stage-2 decides what Stage-2 has implemented. A contract cannot vote itself
    an estimator — asserted with the estimator simulated absent."""
    monkeypatch.setattr(G, "IMPLEMENTED_ESTIMATORS", (G.ESTIMATOR_WITHIN,))
    doc = emit(mode=G.MODE_TEMPORAL,
               estimator_status=G.ESTIMATOR_AVAILABLE,
               execution_status=G.EXECUTION_READY)
    assert refusal(doc, schema) == G.REFUSE_ESTIMATOR_OVERCLAIM


def test_the_execution_status_must_still_FOLLOW_from_the_contract(schema):
    """The estimator exists, so `awaiting_estimator` no longer follows from anything."""
    doc = emit(mode=G.MODE_TEMPORAL, estimator_status=G.ESTIMATOR_AVAILABLE,
               execution_status=G.EXECUTION_AWAITING)
    assert refusal(doc, schema) == G.REFUSE_STATUS


def test_a_temporal_selection_cannot_borrow_the_within_condition_estimator(schema):
    """Refused TWICE OVER — and the second layer is the one that matters.

    The repaired f810 schema carries the rule itself ("a temporal mode may never borrow the
    within-condition estimator"), so the pinned schema now refuses this before the gate's own
    routing check is reached.
    """
    doc = reseal(emit(mode=G.MODE_TEMPORAL, estimator_id=G.ESTIMATOR_WITHIN))
    assert refusal(doc, schema) == G.REFUSE_SCHEMA


def test_the_GATE_refuses_the_borrowed_estimator_even_WITHOUT_the_schema():
    """Defence in depth: the gate does not delegate this to the schema.

    Validated against a PERMISSIVE schema, so the pinned schema's allOf rule cannot fire and
    the gate's OWN routing check is the only thing left to catch it. If this were not
    checked, a loosened schema would silently take the protection away — and routing a
    cross-condition selection through the within-condition formula returns numbers that look
    exactly like an answer.
    """
    doc = reseal(emit(mode=G.MODE_TEMPORAL, estimator_id=G.ESTIMATOR_WITHIN))
    with pytest.raises(G.SelectionV3Error) as exc:
        G.validate(doc, {})
    assert exc.value.reason == G.REFUSE_MODE_ROUTE


def test_the_IDENTITY_split_preserves_the_PUBLIC_SURFACE():
    """The derivations live in ``stage1_v3_ids``; they are named through ``stage1_v3``.

    Every lane, every runner and every test reaches the identities through this module. An
    identity that quietly changed its import path would be an identity that changed — so the
    re-export is a CONTRACT, and it is asserted rather than assumed. Each name must resolve,
    and resolve to the SAME object: a shadowing copy would drift from the original in silence.
    """
    from direct import stage1_v3_ids as I

    names = [n for n in vars(I)
             if not n.startswith("_") and n not in ("annotations", "Any", "content_hash")]
    assert len(names) >= 29, "the identity module lost a public name"
    for n in names:
        assert hasattr(G, n), f"stage1_v3 no longer re-exports {n!r}"
        assert getattr(G, n) is getattr(I, n), f"{n!r} is a COPY, not the derivation"

    # the derivations themselves, reachable by their original names
    for fn in ("derive_question_id", "derive_selection_id", "endpoints", "pole_identity",
               "declared_method_identity", "selection_biology_sha256"):
        assert callable(getattr(G, fn))


def test_the_identity_module_depends_on_NOTHING_that_could_move_an_id():
    """Identity must not be able to change because a config, a policy or a release moved."""
    import ast
    import os

    src = os.path.join(os.path.dirname(G.__file__), "stage1_v3_ids.py")
    with open(src) as fh:
        tree = ast.parse(fh.read())
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imported <= {"__future__", "typing", "hashing"}, imported
    # ...and nothing plain-imported either: no config, no policy, no release, no os/json.
    assert not [a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
                for a in n.names]


def test_the_temporal_estimator_IS_in_the_implemented_set():
    assert G.ESTIMATOR_TEMPORAL in G.IMPLEMENTED_ESTIMATORS
    assert G.IMPLEMENTED_ESTIMATORS == (G.ESTIMATOR_WITHIN, G.ESTIMATOR_TEMPORAL)


def test_the_registry_binds_the_METHOD_not_merely_the_name():
    """A contract that says 'temporal, available' while naming no method hash has
    admitted a word. The bridge binds what it is admitting."""
    reg = G.estimator_registry()
    t = reg[G.ESTIMATOR_TEMPORAL]
    assert t["status"] == G.ESTIMATOR_AVAILABLE
    assert t["analysis_mode"] == G.MODE_TEMPORAL
    assert t["n_conditions"] == 2
    assert len(t["method_sha256"]) == 64
    assert t["inference_status"] == "not_calibrated"
    assert t["estimand_is_per_cell_fate"] is False
    # ...and the within-condition estimator is still there, unchanged
    assert reg[G.ESTIMATOR_WITHIN]["status"] == G.ESTIMATOR_AVAILABLE
    assert reg[G.ESTIMATOR_WITHIN]["n_conditions"] == 1


@pytest.mark.parametrize("mode,n", [(G.MODE_WITHIN, 2), (G.MODE_TEMPORAL, 1)])
def test_the_condition_count_must_match_the_mode(schema, mode, n):
    doc = emit(mode=mode, conditions=["Rest", "Stim8hr"][:n])
    assert refusal(doc, schema) == G.REFUSE_CONDITIONS


# --------------------------------------------------------------------------- #
# 3. POLES. Unavailable is refused, with the pole's OWN typed reasons.
# --------------------------------------------------------------------------- #
def test_an_UNAVAILABLE_pole_is_refused_with_its_typed_reason_codes(schema):
    with pytest.raises(G.SelectionV3Error) as exc:
        G.validate(emit(available=False), schema)
    assert exc.value.reason == G.REFUSE_POLE_UNAVAILABLE
    # the pole's own reason codes survive into the refusal, never summarised into "failed"
    assert "panel_below_effect_universe_min" in str(exc.value)
    assert "n_panel_in_effect_universe=1" in str(exc.value)


def test_RELABELLING_an_unavailable_pole_as_available_is_caught(schema):
    """The counts still say it is not projectable. The label says it is."""
    doc = emit(available=False)
    for p in ("A", "B"):
        doc["poles"][p]["effect_projection_status"] = G.PROJECTION_AVAILABLE
    doc = reseal(doc)

    # it now passes the pole gate — and dies on the EFFECT UNIVERSE, which is the
    # independent witness: the program is simply not projectable in it.
    assert refusal(doc, schema,
                   effect_universe_programs=set()) == G.REFUSE_POLE_NOT_IN_UNIVERSE


def test_a_pole_absent_from_the_CURRENT_effect_universe_is_refused(schema):
    """The contract was minted against a different universe than this run holds."""
    doc = emit(a="ghost_program")
    assert refusal(doc, schema, effect_universe_programs={"prog_beta"}) \
        == G.REFUSE_POLE_NOT_IN_UNIVERSE


def test_both_poles_are_validated_not_just_the_first(schema):
    doc = emit()
    doc["poles"]["B"]["effect_projection_status"] = G.PROJECTION_UNAVAILABLE
    doc = reseal(doc)
    with pytest.raises(G.SelectionV3Error) as exc:
        G.validate(doc, schema)
    assert exc.value.reason == G.REFUSE_POLE_UNAVAILABLE
    assert "pole B" in str(exc.value)


# --------------------------------------------------------------------------- #
# 4. THE BIOLOGY. A changed A/B/direction/condition cannot ride a stale id.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mutate", [
    lambda d: d["canonical_content"]["A"].update({"program_id": "OTHER"}),
    lambda d: d["canonical_content"]["B"].update({"program_id": "OTHER"}),
    lambda d: d["canonical_content"]["A"].update({"direction": "low"}),
    lambda d: d["canonical_content"]["B"].update({"direction": "high"}),
    lambda d: d["canonical_content"].update({"conditions": ["Stim8hr"]}),
])
def test_changing_the_biology_WITHOUT_updating_the_contract_hash_is_refused(schema,
                                                                            mutate):
    """The contract's own content hash covers its own content, so a silent edit fails."""
    doc = emit()
    mutate(doc)                                   # NOT resealed — the id is now stale
    assert refusal(doc, schema) == G.REFUSE_CONTENT_HASH


@pytest.mark.parametrize("pole,field,value", [
    ("A", "program_id", "OTHER"), ("B", "program_id", "OTHER"),
    ("A", "direction", "low"), ("B", "direction", "high"),
])
def test_a_contract_that_names_TWO_BIOLOGIES_is_refused(schema, pole, field, value):
    """Mutate canonical_content and reseal the hash honestly — ``poles`` still disagrees.

    Whichever block is read first decides what gets measured, and the two blocks would
    then be measuring different things under one id.
    """
    doc = emit()
    doc["canonical_content"][pole][field] = value
    doc = reseal(doc)
    assert refusal(doc, schema) == G.REFUSE_BIOLOGY_SPLIT


def test_stage2_keys_on_the_BIOLOGY_it_read_not_on_the_selection_id(schema):
    """Stage-2 keys on the biology it ACTUALLY READ, so two different selections can never
    share a stage2_run_id — whatever their selection_ids say.

    The selection_id is now re-derived and enforced (m2), so two different biologies get
    two different ids anyway. This is the DEFENCE IN DEPTH behind that: even if a producer
    somehow reused an id, the Stage-2 run id would still separate them, because it is
    keyed on the biology and not on the label.
    """
    one = G.validate(emit(a="p1"), schema)
    two = G.validate(emit(a="p2"), schema)
    # m2: the ids now DERIVE, so different biology => different id
    assert one["selection_id"] != two["selection_id"]
    assert one["selection_id"] == G.derive_selection_id(emit(a="p1"))
    assert one["selection_biology_sha256"] != two["selection_biology_sha256"]

    # ...and the run id does not depend on the id at all: forge them equal and it still
    # separates the two selections.
    two_forged = dict(two, selection_id=one["selection_id"])
    assert G.stage2_run_id(G.stage2_run_binding(
        one, effect_universe_sha256="e" * 64,
        perturbation_source_hashes={"de": "d" * 64},
        direct_config_sha256="c" * 64)) != G.stage2_run_id(G.stage2_run_binding(
            two_forged, effect_universe_sha256="e" * 64,
            perturbation_source_hashes={"de": "d" * 64},
            direct_config_sha256="c" * 64))

    def run_id(sel):
        return G.stage2_run_id(G.stage2_run_binding(
            sel, effect_universe_sha256="e" * 64,
            perturbation_source_hashes={"de": "d" * 64},
            direct_config_sha256="c" * 64))

    assert run_id(one) != run_id(two)      # ...and the results cannot collide
    # m2: the binding now publishes the DERIVATION rule, not the retired
    # "non-recomputable citation" claim.
    assert one["selection_id_rule_id"] == G.SELECTION_ID_RULE_ID
    assert one["selection_id_rederived"] == one["selection_id"]


# --------------------------------------------------------------------------- #
# 5. NO COMBINED STAGE-1 SCORE MAY BE HANDED DOWN.
# --------------------------------------------------------------------------- #
def test_a_combined_stage1_objective_is_refused(schema):
    doc = emit()
    doc["canonical_content"]["combined_objective"] = {"balanced_a_to_b": 0.5}
    doc = reseal(doc)
    # the frozen schema types it as null, so it dies there; and if the schema were ever
    # relaxed, the gate refuses it by name anyway
    reason = refusal(doc, schema)
    assert reason in (G.REFUSE_SCHEMA, G.REFUSE_COMBINED)


def test_poles_separate_FALSE_is_refused(schema):
    doc = emit()
    doc["canonical_content"]["poles_separate"] = False
    doc = reseal(doc)
    assert refusal(doc, schema) in (G.REFUSE_SCHEMA, G.REFUSE_COMBINED)


# --------------------------------------------------------------------------- #
# 6. THE SCHEMA AND THE HASHES ARE PINNED.
# --------------------------------------------------------------------------- #
def test_the_pinned_schema_is_the_one_stage1_froze():
    from direct.hashing import file_sha256
    assert file_sha256(SCHEMA_PATH) == G.SCHEMA_SHA256


def test_a_SWAPPED_schema_is_refused(tmp_path):
    """A schema that can be swapped validates whatever the swapper wanted it to."""
    with open(SCHEMA_PATH) as fh:
        s = json.load(fh)
    s["additionalProperties"] = True                 # a friendlier schema
    p = os.path.join(str(tmp_path), "swapped.schema.json")
    with open(p, "w") as fh:
        json.dump(s, fh)

    with pytest.raises(G.SelectionV3Error) as exc:
        G.load_schema(p)
    assert exc.value.reason == G.REFUSE_SCHEMA_PIN


@pytest.mark.parametrize("key", ["registry_scorer_view_sha256", "source_h5ad_sha256"])
def test_a_changed_bound_hash_changes_the_contract_and_must_be_resealed(schema, key):
    doc = emit()
    doc["canonical_content"][key] = "b" * 64
    assert refusal(doc, schema) == G.REFUSE_CONTENT_HASH   # not resealed -> caught


def test_a_changed_registry_hash_changes_the_STAGE2_RUN_ID(schema):
    """Resealed honestly, it is a different scientific input and must be a different run."""
    base = G.validate(emit(), schema)
    doc = emit()
    doc["canonical_content"]["registry_scorer_view_sha256"] = "b" * 64
    other = G.validate(reseal(doc), schema)

    def run_id(sel, eu="e" * 64):
        return G.stage2_run_id(G.stage2_run_binding(
            sel, effect_universe_sha256=eu,
            perturbation_source_hashes={"de": "d" * 64},
            direct_config_sha256="c" * 64))

    # the registry hash is bound into the SELECTION, which is bound into the run
    assert base["registry_scorer_view_sha256"] != other["registry_scorer_view_sha256"]
    # ...and a changed EFFECT UNIVERSE changes the run id directly
    assert run_id(base) != run_id(base, eu="f" * 64)


def test_a_missing_trust_binding_is_refused_by_the_schema(schema):
    doc = emit()
    doc["trust_bindings"].pop("gate_spec_raw_sha256")
    assert refusal(reseal(doc), schema) == G.REFUSE_SCHEMA


# --------------------------------------------------------------------------- #
# 7. A v2 SELECTION IS NOT A v3 SELECTION.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("old", ["spot.stage01_selection.v2",
                                 "spot.stage01_selection_contract.v1",
                                 "spot.stage01_current.v2"])
def test_replaying_a_v2_selection_or_current_record_is_refused(schema, old):
    doc = emit()
    doc["schema_version"] = old
    assert refusal(reseal(doc), schema) == G.REFUSE_SCHEMA


def test_a_retired_v2_field_cannot_be_smuggled_in(schema):
    """global_stage2_selectable / production_stage2_ready / 0-of-33 are RETIRED."""
    for retired in ("global_stage2_selectable", "production_stage2_ready",
                    "n_selectable_program_conditions", "research_only"):
        doc = emit()
        doc[retired] = True
        assert refusal(reseal(doc), schema) == G.REFUSE_SCHEMA


# --------------------------------------------------------------------------- #
# 8. THE HISTORICAL GATE IS NOT A GATE.
# --------------------------------------------------------------------------- #
def test_the_historical_selectability_may_never_become_a_live_gate(schema):
    doc = emit()
    doc["historical_validation_provenance"]["active_gate"] = True
    doc = reseal(doc)
    assert refusal(doc, schema) in (G.REFUSE_SCHEMA, G.REFUSE_HISTORICAL_GATE)


def test_the_honest_contract_binds_it_as_PROVENANCE_only(schema):
    bound = G.validate(emit(), schema)
    assert bound["historical_validation_provenance"]["active_gate"] is False


# --------------------------------------------------------------------------- #
# 9. THE IDENTIFIER HIERARCHY: selection_id -> stage2_run_id.
# --------------------------------------------------------------------------- #
def _binding(sel, **over):
    kw = dict(effect_universe_sha256="e" * 64,
              perturbation_source_hashes={"de_main": "d" * 64, "by_guide": "g" * 64},
              direct_config_sha256="c" * 64)
    kw.update(over)
    return G.stage2_run_binding(sel, **kw)


def test_the_run_id_binds_every_method_that_could_change_the_numbers(schema):
    sel = G.validate(emit(), schema)
    b = _binding(sel)
    for field in ("selection_id", "selection_biology_sha256", "analysis_mode",
                  "estimator_id", "direct_method_version", "direct_config_sha256",
                  "effect_universe_sha256", "perturbation_source_hashes",
                  "mask_method_version", "pathway_method_version"):
        assert field in b, field
    assert len(G.stage2_run_id(b)) == 16


@pytest.mark.parametrize("field,value", [
    ("effect_universe_sha256", "f" * 64),
    ("direct_config_sha256", "0" * 64),
])
def test_a_changed_method_or_input_is_a_DIFFERENT_run(schema, field, value):
    """The same selection screened differently is a different RESULT — and one that
    shared its key would silently overwrite the other."""
    sel = G.validate(emit(), schema)
    base = G.stage2_run_id(_binding(sel))
    assert G.stage2_run_id(_binding(sel, **{field: value})) != base


def test_a_changed_perturbation_source_is_a_different_run(schema):
    sel = G.validate(emit(), schema)
    base = G.stage2_run_id(_binding(sel))
    other = G.stage2_run_id(_binding(
        sel, perturbation_source_hashes={"de_main": "9" * 64, "by_guide": "g" * 64}))
    assert other != base


def test_the_run_binding_is_invariant_to_source_hash_ORDER(schema):
    sel = G.validate(emit(), schema)
    a = _binding(sel, perturbation_source_hashes={"a": "1" * 64, "b": "2" * 64})
    b = _binding(sel, perturbation_source_hashes={"b": "2" * 64, "a": "1" * 64})
    assert G.stage2_run_id(a) == G.stage2_run_id(b)


def test_two_runs_of_the_SAME_science_share_a_run_id(schema):
    sel = G.validate(emit(), schema)
    assert G.stage2_run_id(_binding(sel)) == G.stage2_run_id(_binding(
        copy.deepcopy(sel)))


# --------------------------------------------------------------------------- #
# THE ARMS ARE DERIVED, NEVER TRUSTED.
#
# `doc["arms"]` was read by nobody and checked by nothing: forge every arm key, reseal
# `full_contract_content_sha256`, and the gate ADMITTED it — while the BoundSelection dropped
# `arms` entirely, so the forgery travelled downstream as the only copy anyone had. The content
# hash proves the bytes were not changed IN TRANSIT. It says nothing about whether they were
# right when they were written.
# --------------------------------------------------------------------------- #
class TestTheArmsAreDERIVEDFromTheBiology:
    def test_a_REAL_539431d_selection_still_ADMITS(self, schema):
        """The gate must not refuse the authoritative contract."""
        import fixtures_stage1_contract as S1
        doc = S1.producer_fixture("temporal_ready")
        bound = G.validate(doc, schema)
        assert bound["arms_are_derived_not_declared"] is True
        assert set(bound["arms"]) == {"away_from_A", "toward_B"}

    def test_the_DERIVED_arms_are_BOUND_into_the_selection(self, schema):
        bound = G.validate(emit(), schema)
        away = bound["arms"]["away_from_A"]
        # keyed on the CHANGE, minted by the SAME module the producers mint with
        assert away["direct_arm_key"].startswith("direct|")
        assert away["desired_change"] in ("increase", "decrease")

    def test_a_TEMPORAL_selection_derives_an_ORDERED_pair_key(self, schema):
        bound = G.validate(
            emit(mode=G.MODE_TEMPORAL, conditions=["Rest", "Stim48hr"]), schema)
        t = bound["arms"]["away_from_A"]["temporal_arm_key"]
        assert t.startswith("temporal|") and t.endswith("|Rest|Stim48hr")
        # A at the FIRST condition, B at the LAST — the ordered pair, never a set
        assert bound["arms"]["away_from_A"]["condition"] == "Rest"
        assert bound["arms"]["toward_B"]["condition"] == "Stim48hr"

    def test_a_WITHIN_selection_derives_NO_temporal_key(self, schema):
        bound = G.validate(emit(), schema)
        assert "temporal_arm_key" not in bound["arms"]["away_from_A"]

    @pytest.mark.parametrize("role,field,forged", [
        ("away_from_A", "direct_arm_key", "direct|FORGED|increase|Rest"),
        ("toward_B", "direct_arm_key", "direct|OTHER|decrease|Stim48hr"),
        ("away_from_A", "pathway_arm_key_base", "pathway|FORGED|increase|Rest"),
    ])
    def test_a_FORGED_arm_key_is_REFUSED_even_when_RESEALED(self, schema, role, field,
                                                            forged):
        """THE PROBE. Forge the key, recompute the full-contract hash: it still refuses."""
        doc = emit()
        doc["arms"][role][field] = forged
        reseal(doc)
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        assert exc.value.reason == G.REFUSE_ARM_KEY

    def test_a_FORGED_TEMPORAL_arm_key_is_REFUSED_even_when_RESEALED(self, schema):
        doc = emit(mode=G.MODE_TEMPORAL, conditions=["Rest", "Stim48hr"])
        doc["arms"]["away_from_A"]["temporal_arm_key"] = "temporal|FORGED|increase|Rest|Rest"
        reseal(doc)
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        assert exc.value.reason == G.REFUSE_ARM_KEY

    def test_a_FORGED_desired_change_is_REFUSED(self, schema):
        """The change is the arm's IDENTITY. Flipping it points at the opposite arm."""
        doc = emit()
        doc["arms"]["away_from_A"]["desired_change"] = "increase"
        reseal(doc)
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        assert exc.value.reason == G.REFUSE_ARM_FIELD

    def test_an_OMITTED_arm_is_REFUSED(self, schema):
        """Half a comparison."""
        doc = emit()
        del doc["arms"]["toward_B"]
        reseal(doc)
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        assert exc.value.reason in (G.REFUSE_SCHEMA, G.REFUSE_ARM_ROLES)

    def test_an_EXTRA_arm_is_REFUSED(self, schema):
        """An arm nobody asked for. The SCHEMA refuses it first — an earlier gate, and a
        stronger one; the roles gate stands behind it for anything the schema would admit."""
        doc = emit()
        doc["arms"]["third_arm"] = dict(doc["arms"]["away_from_A"], role="third_arm")
        reseal(doc)
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        assert exc.value.reason in (G.REFUSE_SCHEMA, G.REFUSE_ARM_ROLES)

    def test_ARMS_MISSING_ENTIRELY_is_REFUSED(self, schema):
        doc = emit()
        doc["arms"] = {}
        reseal(doc)
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        assert exc.value.reason in (G.REFUSE_SCHEMA, G.REFUSE_ARMS_MISSING)
