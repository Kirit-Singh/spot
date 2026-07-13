"""Membership is RE-DERIVED from the store, never taken from the view that claims it.

Every fixture here is GENERIC — `PROG_A` / `PROG_B`, two lanes, two conditions, arbitrary roles. No
Treg, no Th1, no single hard-coded selection: the contract must hold for any question Stage 1 can
pose, and a test that only passes for one biology is a test that pinned the biology instead of the
rule.

The store is GLOBAL over the admitted candidate universe. A selection is a deterministic PROJECTION
of it. So every displayed row makes a claim — "this candidate is on an arm this selection selected"
— and that is exactly the claim a projection cannot be trusted to make about itself.
"""

from __future__ import annotations

import pytest

from analysis.stage3_v2_membership import (
    EXACT_MATCH_RULE,
    STORE_ARM_KEY_COLUMNS,
    MembershipError,
    binding_from_selection_view,
    project,
    rederive,
    verify_view_claim,
)

# Stage 3's real arm-key grammar: lane|program_id|desired_change|condition[|to_condition].
#
# The fixtures are COHERENT by construction: a temporal selection selects two TEMPORAL arms over the
# same ordered endpoints, a direct selection selects two DIRECT arms at one condition. An incoherent
# fixture would be testing a selection Stage 3 cannot emit.
REST, STIM = "Rest", "Stim48hr"

# The two poles of a temporal question, in order. A is away_from_A, B is toward_B — pinned.
TA = f"temporal|PROG_A|decrease|{REST}|{STIM}"     # away from a HIGH pole -> decrease
TB = f"temporal|PROG_B|increase|{REST}|{STIM}"     # toward  a HIGH pole -> increase
# A direct (within-condition) question.
DA = f"direct|PROG_A|decrease|{REST}"
DB = f"direct|PROG_B|increase|{REST}"
# On no selection here.
FOREIGN = f"temporal|PROG_Z|decrease|{REST}|{STIM}"

SLOTS = ("A", "B")
ROLES = ("away_from_A", "toward_B")


def _arm(role: str, arm_key: str, **over) -> dict:
    """A role arm in Stage 3's REAL shape — every field, and the arm_key rebuilds from them."""
    parts = arm_key.split("|")
    if len(parts) < 4:      # a malformed key yields a malformed arm, which is REFUSED downstream
        return {"arm_key": arm_key, "role": role}
    lane, program_id, desired_change, *context = parts
    ctx = ({"from_condition": context[0], "to_condition": context[1]} if len(context) == 2
           else {"condition": context[0]})
    arm = {"arm_key": arm_key, "role": role, "lane": lane, "program_id": program_id,
           "desired_change": desired_change, "context": ctx, "pole": "high"}
    arm.update(over)
    return arm


def _view(*selected: str, mode: str = "temporal_cross_condition",
          conditions: tuple = (REST, STIM), **over) -> dict:
    """A Stage-3 selection view in its ACTUAL emitted shape — every identity field Stage 3 writes.

    `selection` carries `selection_id`, `selection_full_sha256` and `full_contract_content_sha256`
    ALONGSIDE the canonical (biology-only) hash, plus the ordered `conditions`, the per-slot `roles`
    and the `poles`. Stage 4 binds all of them.
    """
    arms = {slot: _arm(role, key) for slot, role, key in zip(SLOTS, ROLES, selected)}
    poles = {}
    for slot, key in zip(SLOTS, selected):
        parts = key.split("|")
        if len(parts) >= 4 and conditions:
            poles[slot] = {"program_id": parts[1], "direction": "high",
                           "condition": conditions[0] if slot == "A" else conditions[-1]}
        elif len(parts) >= 4:      # no conditions declared: the pole states none either
            poles[slot] = {"program_id": parts[1], "direction": "high"}

    view = {
        "schema_version": "spot.stage03_selection_view.v1",
        "view_id": "cdc4d60cc411e6d3",
        "view_content_sha256": "c" * 64,
        "view_method_id": "spot.stage03.selection_view.projection.v1",
        "selection": {
            "selection_id": "sel0000000000001",
            "selection_full_sha256": "5" * 64,
            "full_contract_content_sha256": "f" * 64,
            "canonical_content_sha256": "e" * 64,
            "question_id": "2b46a1c6db331a5c",
            "analysis_mode": mode,
            "conditions": list(conditions),
            "roles": dict(zip(SLOTS, ROLES)),
            "poles": poles,
        },
        "selected_arms": {
            EXACT_MATCH_RULE: True,
            "arm_key_rule_id": "spot.stage02.arm.reusable_key.desired_change.v1",
            "gene_arm_keys": list(selected),
            "arms": arms,
        },
    }
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(view.get(k), dict):
            view[k] = {**view[k], **v}
        else:
            view[k] = v
    return view


def _candidate(cid: str = "CAND_1", **columns) -> dict:
    """A store candidate row. Every typed arm-key column is present — absence is a refusal, and a
    fixture that omits one would be testing a row the store never emits."""
    row = {"candidate_id": cid}
    for col in STORE_ARM_KEY_COLUMNS:
        row[col] = list(columns.pop(col, ()))
    row.update(columns)
    return row


# ------------------------------------------------------------------ the store is the ground truth

def test_membership_is_the_EXACT_intersection_of_store_arm_keys_and_the_selection():
    cand = _candidate(observed_perturbation_arm_keys=[TA, FOREIGN],
                      pathway_hypothesis_arm_keys=[TB])
    m = rederive(cand, binding_from_selection_view(_view(TA, TB)))

    assert m.in_view is True
    assert m.all_arm_keys == (TA, TB), "FOREIGN is in the store but NOT in this selection"
    assert m.arm_keys_by_column["observed_perturbation_arm_keys"] == (TA,)
    assert m.arm_keys_by_column["pathway_hypothesis_arm_keys"] == (TB,)
    # Absence is STATED, never omitted: the column is present and empty.
    assert m.arm_keys_by_column["opposed_arm_keys"] == ()


def test_a_candidate_on_no_selected_arm_is_OUT_OF_VIEW_not_a_member():
    cand = _candidate(observed_perturbation_arm_keys=[FOREIGN])
    m = rederive(cand, binding_from_selection_view(_view(TA, TB)))
    assert m.in_view is False
    assert m.all_arm_keys == ()


def test_the_v2_columns_are_arm_KEYS_and_the_v1_alias_does_not_silently_match_nothing():
    """The v1 projection read `*_arms`; the v2 store writes `*_arm_keys`. A projection that found
    NEITHER would have matched nothing and shown an EMPTY view rather than failing — a silent,
    total evidence loss that looks exactly like 'no candidate qualified'."""
    v1_shaped = {"candidate_id": "CAND_1", "observed_perturbation_arms": [TA]}  # the old spelling
    with pytest.raises(MembershipError) as exc:
        rederive(v1_shaped, binding_from_selection_view(_view(TA, TB)))
    assert exc.value.code == "stage3_candidate_missing_an_arm_key_column"


# --------------------------------------------------------------- exact equality, never a near-miss

@pytest.mark.parametrize("near_miss", [
    "temporal|PROG_A|decrease|Rest|Stim48hrX",   # the selected key is a strict PREFIX of this
    "temporal|PROG_A|decrease|Rest|Stim48h",     # this one is a strict prefix of the selected
    "temporal|PROG_A|decrease|rest|Stim48hr",    # case
    "temporal|PROG_A|decrease|Rest|Stim48hr ",   # trailing space
])
def test_a_PREFIX_or_near_miss_arm_key_is_NOT_a_member(near_miss):
    """`direct|P|decrease|Rest` is not `direct|P|decrease|Rest48`. Substring logic would place a
    candidate on an arm nobody selected, which is how a drug acquires evidence it does not have."""
    m = rederive(_candidate(observed_perturbation_arm_keys=[near_miss]),
                 binding_from_selection_view(_view(TA, TB)))
    assert m.in_view is False, f"{near_miss!r} matched {TA!r} by something other than equality"


def test_a_DISPLAY_NAME_never_matches_an_arm_key():
    """A preferred_name is not an identity. Matching on it would bind a candidate to an arm by
    coincidence of wording."""
    cand = _candidate(preferred_name="PROG_A", observed_perturbation_arm_keys=[])
    m = rederive(cand, binding_from_selection_view(_view(TA, TB)))
    assert m.in_view is False


def test_a_view_that_does_not_DECLARE_exact_matching_is_refused():
    """Stage 3 states the guarantee itself. Stage 4 will not fall back to its own matching rule for
    a view whose rule is unstated — a rule nobody wrote down is a rule nobody enforced."""
    view = _view(TA, TB)
    view["selected_arms"][EXACT_MATCH_RULE] = False
    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(view)
    assert exc.value.code == "stage3_view_does_not_declare_exact_arm_key_matching"


# ------------------------------------------------------------------- the view's claim is CHECKED

def test_a_view_that_claims_a_FOREIGN_arm_is_refused():
    """The view places the candidate on an arm the STORE never put it on. This is the dangerous
    direction: it ADDS evidence, and it makes a drug look better than its data."""
    cand = _candidate(observed_perturbation_arm_keys=[TA],
                      view_arm_keys_by_origin={"direct_target": [TA, TB]})  # TB is not in the store
    binding = binding_from_selection_view(_view(TA, TB))

    with pytest.raises(MembershipError) as exc:
        verify_view_claim(cand, rederive(cand, binding))
    assert exc.value.code == "stage4_view_claims_membership_the_store_does_not_support"
    assert TB in exc.value.context["foreign_arm_keys"]


def test_a_view_that_DROPS_a_supported_arm_is_refused():
    """The quiet one. The row still renders — just with less evidence than it actually has — and
    nothing about it looks wrong."""
    cand = _candidate(observed_perturbation_arm_keys=[TA],
                      pathway_hypothesis_arm_keys=[TB],
                      view_arm_keys_by_origin={"direct_target": [TA]})  # TB silently omitted
    binding = binding_from_selection_view(_view(TA, TB))

    with pytest.raises(MembershipError) as exc:
        verify_view_claim(cand, rederive(cand, binding))
    assert exc.value.code == "stage4_view_dropped_membership_the_store_does_support"
    assert TB in exc.value.context["dropped_arm_keys"]


def test_a_candidate_that_CONTRADICTS_ITSELF_about_its_arms_is_refused():
    """`arm_keys` restates the typed lists. When they disagree, one was edited and the other was
    not — and Stage 4 will not pick whichever it prefers."""
    cand = _candidate(observed_perturbation_arm_keys=[TA, TB], arm_keys=[TA])
    with pytest.raises(MembershipError) as exc:
        rederive(cand, binding_from_selection_view(_view(TA, TB)))
    assert exc.value.code == "stage3_candidate_contradicts_itself_about_its_arms"


def test_a_selection_view_that_CONTRADICTS_ITSELF_about_its_arms_is_refused():
    """The role arm names an arm absent from the view's own `gene_arm_keys`. Everything else about
    the arm is coherent, so nothing incidental can do the refusing."""
    view = _view(TA, TB)
    view["selected_arms"]["arms"]["A"] = _arm("away_from_A", FOREIGN)
    view["selection"]["poles"]["A"]["program_id"] = "PROG_Z"
    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(view)
    assert exc.value.code == "stage3_selection_contradicts_itself_about_its_arms"


# -------------------------------------------------------------- the binding cannot be swapped

def test_the_membership_hash_MOVES_when_the_selection_moves():
    """Change the question, the mode, a condition, the view, or ONE arm key — the hash moves. That
    is what makes a re-pointed projection detectable rather than merely wrong."""
    cand = _candidate(observed_perturbation_arm_keys=[TA])
    base = rederive(cand, binding_from_selection_view(_view(TA, TB))).membership_sha256()

    # Every swap is COHERENT — a selection Stage 3 could actually emit. An incoherent one would be
    # refused, which proves nothing about the hash.
    swaps = {
        "question": _view(TA, TB, selection={"question_id": "ffffffffffffffff"}),
        "conditions": _view("temporal|PROG_A|decrease|Rest|Stim8hr",
                            "temporal|PROG_B|increase|Rest|Stim8hr",
                            conditions=(REST, "Stim8hr")),
        "mode": _view(DA, DB, mode="direct_within_condition", conditions=(REST,)),
        "view": _view(TA, TB, view_id="v0000000000000002"),
        "selection_hash": _view(TA, TB, selection={"canonical_content_sha256": "f" * 64}),
    }
    for name, view in swaps.items():
        moved = rederive(cand, binding_from_selection_view(view)).membership_sha256()
        assert moved != base, f"the membership hash did NOT move when the {name} changed"


def test_a_row_bound_to_a_DIFFERENT_selection_is_refused_by_the_projection():
    """A swapped binding can be internally consistent in every field and still answer another
    question."""
    cand = _candidate(observed_perturbation_arm_keys=[TA, DA], arm_keys=[TA, DA])
    # A hash minted under the DIRECT selection, presented under the TEMPORAL one.
    other = rederive(cand, binding_from_selection_view(
        _view(DA, DB, mode="direct_within_condition", conditions=(REST,)))).membership_sha256()
    cand["membership_sha256"] = other

    with pytest.raises(MembershipError) as exc:
        project([cand], _view(TA, TB))
    assert exc.value.code == "stage4_membership_hash_does_not_recompute"


def test_a_view_that_cannot_state_its_own_identity_is_refused():
    view = _view(TA, TB)
    del view["view_content_sha256"]
    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(view)
    assert exc.value.code == "stage3_selection_view_cannot_state_its_identity"


def test_a_selection_that_selected_NOTHING_is_not_a_selection():
    """A selection with no poles is not a question at all. Any of these refusals is correct; what
    matters is that an empty selection never yields a binding."""
    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(_view())
    assert exc.value.code in ("stage3_selection_names_no_role_arms",
                              "stage3_selection_selected_no_arms",
                              "stage3_selection_does_not_state_both_poles")


# ------------------------------------------------------------------------------- the projection

def test_the_projection_FILTERS_and_FLAGS_and_leaves_the_STORE_global():
    """The store is not filtered; this is a projection OF it. Out-of-view candidates are REPORTED,
    not dropped — a row that vanishes and a row that never existed look identical, and only one of
    them is a bug."""
    inside = _candidate("CAND_IN", observed_perturbation_arm_keys=[TA])
    outside = _candidate("CAND_OUT", observed_perturbation_arm_keys=[FOREIGN])

    out = project([inside, outside], _view(TA, TB))

    assert [r["candidate_id"] for r in out["displayed"]] == ["CAND_IN"]
    assert [r["candidate_id"] for r in out["out_of_view"]] == ["CAND_OUT"]
    assert out["counts"] == {"n_displayed": 1, "n_out_of_view": 1}
    assert out["store_is_global_and_was_not_filtered"] is True
    # Every displayed row carries the membership it was displayed UNDER.
    assert out["displayed"][0]["membership_sha256"]


def test_the_projection_is_DETERMINISTIC_and_order_independent():
    a = _candidate("CAND_A", observed_perturbation_arm_keys=[TA])
    b = _candidate("CAND_B", pathway_hypothesis_arm_keys=[TB])
    assert project([a, b], _view(TA, TB)) == project([b, a], _view(TA, TB))


def test_a_candidate_whose_membership_cannot_be_REDERIVED_is_refused_not_displayed():
    """Not shown, not silently dropped — refused, by name."""
    with pytest.raises(MembershipError) as exc:
        project([{"candidate_id": "CAND_1"}], _view(TA, TB))
    assert exc.value.code == "stage3_candidate_missing_an_arm_key_column"

    with pytest.raises(MembershipError) as exc:
        project([_candidate("")], _view(TA, TB))
    assert exc.value.code == "stage3_candidate_without_an_id"


def test_the_contract_is_generic_and_pins_NOTHING_about_the_biology():
    """No program, condition, lane or role is hard-coded anywhere in the module: the same rule must
    hold for any question Stage 1 can pose."""
    import analysis.stage3_v2_membership as m

    from pathlib import Path

    src = Path(m.__file__).read_text(encoding="utf-8").lower()
    for banned in ("treg", "th1", "foxp3", "cd4_ctl_like", "stim48hr", "rest|", "prog_a"):
        assert banned not in src, f"the membership contract hard-codes {banned!r}"


def test_native_v2_admission_stays_CLOSED_and_this_module_opens_nothing():
    """The membership seam is ready for W16's pin. It does not BE the pin."""
    from analysis import stage3_v2_contract, stage3_v2_seam

    assert stage3_v2_seam.STAGE3_V2_SCHEMA_SET_SHA256 is None
    assert stage3_v2_seam.STAGE3_V2_VERIFIER_ENTRY is None
    with pytest.raises(Exception):
        stage3_v2_contract.admit_v2("/nonexistent")


# ================================================= a candidate lives in MANY selections at once

def test_ONE_candidate_shared_across_TWO_selections_gets_TWO_distinct_memberships():
    """The store is GLOBAL: the same candidate is simultaneously a member of every selection whose
    arms it sits on. Its membership is a property of the (candidate, selection) PAIR — never of the
    candidate alone — and the two must not be interchangeable."""
    shared = _candidate("CAND_SHARED",
                        observed_perturbation_arm_keys=[TA],
                        pathway_hypothesis_arm_keys=[DA],
                        arm_keys=[TA, DA])

    temporal = _view(TA, TB)
    direct = _view(DA, DB, mode="direct_within_condition", conditions=(REST,),
                   selection={"selection_id": "sel0000000000002",
                              "selection_full_sha256": "6" * 64,
                              "question_id": "ffffffffffffffff"},
                   view_id="v0000000000000002")

    m1 = rederive(shared, binding_from_selection_view(temporal))
    m2 = rederive(shared, binding_from_selection_view(direct))

    assert m1.in_view and m2.in_view, "the candidate belongs to BOTH selections"
    assert m1.all_arm_keys == (TA,) and m2.all_arm_keys == (DA,), "each sees only ITS OWN arms"
    assert m1.membership_sha256() != m2.membership_sha256(), (
        "one candidate, two selections, ONE hash — the membership would be interchangeable between "
        "questions, which is the swap this hash exists to make detectable")

    # And a hash minted under selection 1 cannot be presented under selection 2.
    swapped = dict(shared, membership_sha256=m1.membership_sha256())
    with pytest.raises(MembershipError) as exc:
        project([swapped], direct)
    assert exc.value.code == "stage4_membership_hash_does_not_recompute"


def test_the_FULL_selection_identity_is_bound_not_just_the_canonical_biology_hash():
    """Two selections can pose the SAME biological question under different run/endpoint contracts.
    The canonical hash is deliberately biology-only, so binding to it alone cannot tell a re-run
    under a changed contract from the original."""
    cand = _candidate(observed_perturbation_arm_keys=[TA])
    base = rederive(cand, binding_from_selection_view(_view(TA, TB))).membership_sha256()

    for field, value in (("selection_id", "sel0000000000009"),
                         ("selection_full_sha256", "9" * 64),
                         ("full_contract_content_sha256", "8" * 64)):
        moved = rederive(cand, binding_from_selection_view(
            _view(TA, TB, selection={field: value}))).membership_sha256()
        assert moved != base, f"the membership hash did NOT move when {field} changed"


def test_a_view_missing_its_full_run_identity_is_refused():
    for field in ("selection_id", "selection_full_sha256", "full_contract_content_sha256"):
        view = _view(TA, TB)
        del view["selection"][field]
        with pytest.raises(MembershipError) as exc:
            binding_from_selection_view(view)
        assert exc.value.code == "stage3_selection_view_cannot_state_its_identity"


# ============================================ a STORE row and an emitted VIEW row are different

def test_an_emitted_VIEW_row_that_states_NO_membership_claim_is_REFUSED():
    """Stating which selected arms the candidate sits on is the entire job of a view row. One that
    states nothing cannot be checked against the store — and treating a missing claim as 'nothing to
    check' lets an emitted view escape the only check there is on it."""
    from analysis.stage3_v2_membership import VIEW_ROW

    row = _candidate("CAND_1", observed_perturbation_arm_keys=[TA])  # no view_arm_keys_by_origin
    with pytest.raises(MembershipError) as exc:
        project([row], _view(TA, TB), VIEW_ROW)
    assert exc.value.code == "stage4_view_row_states_no_membership_claim"


def test_a_global_STORE_row_legitimately_makes_no_claim():
    """The same bytes, read as what they are. Stage 4 computes the intersection itself."""
    from analysis.stage3_v2_membership import STORE_ROW

    row = _candidate("CAND_1", observed_perturbation_arm_keys=[TA])
    out = project([row], _view(TA, TB), STORE_ROW)
    assert out["counts"]["n_displayed"] == 1
    assert out["row_kind"] == "store"


# ================================================== arm_keys IS the union — exactly, both ways

def test_an_arm_supported_by_NO_evidence_class_is_refused():
    """Measured on the real bundle: `arm_keys == union(typed)` for 19/19 candidates. A key in the
    union that no typed class supports means either corruption or a SIXTH evidence class — and a
    class Stage 4 does not know about is one it would carry uncounted and unhashed."""
    cand = _candidate(observed_perturbation_arm_keys=[TA], arm_keys=[TA, TB])  # TB in no class
    with pytest.raises(MembershipError) as exc:
        rederive(cand, binding_from_selection_view(_view(TA, TB)))
    assert exc.value.code == "stage3_candidate_arm_is_supported_by_no_evidence_class"


# ============================================ the parquet encoding: a string is NOT a list

def test_a_JSON_STRING_arm_key_column_decodes_and_does_NOT_iterate_as_CHARACTERS():
    """Stage 3 writes these columns as JSON STRINGS in parquet. Iterating one yields CHARACTERS, and
    the selected key ',' appears in every serialized list — so a naive `for k in value` matched ALL
    19 real candidates against a selection of two arms. 100% membership, no error raised."""
    import json as _json

    cand = _candidate(observed_perturbation_arm_keys=[])
    cand["observed_perturbation_arm_keys"] = _json.dumps([TA])   # the REAL parquet encoding
    cand["arm_keys"] = _json.dumps([TA])

    m = rederive(cand, binding_from_selection_view(_view(TA, TB)))
    assert m.all_arm_keys == (TA,), "the JSON-string column did not decode to the arm key"

    # And a one-character 'arm key' — the character a naive `for k in string` would have produced —
    # cannot even FORM a selection: it has no lane, no program, no desired change, no context.
    with pytest.raises(MembershipError):
        binding_from_selection_view(_view(",", TB))


def test_a_BARE_string_arm_key_column_is_REFUSED_never_iterated():
    cand = _candidate(observed_perturbation_arm_keys=[])
    cand["observed_perturbation_arm_keys"] = TA     # a bare key, not a JSON list
    with pytest.raises(MembershipError) as exc:
        rederive(cand, binding_from_selection_view(_view(TA, TB)))
    assert exc.value.code == "stage3_arm_key_column_is_not_a_list"


# ================================================================== the gate has a real CALLER

def test_the_membership_gate_is_WIRED_INTO_the_browser_projection_not_left_uncalled():
    """A gate with no caller is a gate that never runs."""
    inside = _candidate("CAND_IN", observed_perturbation_arm_keys=[TA], arm_keys=[TA])
    outside = _candidate("CAND_OUT", observed_perturbation_arm_keys=[FOREIGN], arm_keys=[FOREIGN])
    scorecards = {"scorecard_set_id": "sc1",
                  "candidates": [{"candidate_id": "CAND_IN"}, {"candidate_id": "CAND_OUT"}]}

    doc = _proj(scorecards, [inside, outside], _view(TA, TB))

    rows = {c["candidate_id"]: c for c in doc["candidates"]}
    assert rows["CAND_IN"]["in_active_view"] is True
    assert rows["CAND_OUT"]["in_active_view"] is False
    # The displayed row carries the membership it was displayed UNDER.
    assert rows["CAND_IN"]["stage3_v2_membership"]["membership_sha256"]
    # The out-of-view row EXISTS in Stage 3 — it is simply on none of the selected arms. It still
    # carries its (empty) membership: "out of view" is a stated result, not an absence.
    out = rows["CAND_OUT"]["stage3_v2_membership"]
    assert out["membership_sha256"]
    assert all(not v for v in out["arm_keys_by_column"].values())
    # HONEST COUNTS. These rows came from the selection VIEW — already filtered by Stage 3. Claiming
    # "global store, not filtered" would be a claim about bytes Stage 4 never loaded.
    assert doc["source_is_selection_view"] is True
    assert doc["store_is_global_and_was_not_filtered"] is False
    assert doc["stage3_v2_selection"]["selection_id"] == "sel0000000000001"


def test_the_wired_projection_REFUSES_a_foreign_membership_claim():
    """The gate must actually fire through the consumer, not merely exist beside it."""
    forged = _candidate("CAND_IN", observed_perturbation_arm_keys=[TA], arm_keys=[TA],
                        view_arm_keys_by_origin={"direct_target": [TA, TB]})
    scorecards = {"scorecard_set_id": "sc1", "candidates": [{"candidate_id": "CAND_IN"}]}

    with pytest.raises(MembershipError) as exc:
        _proj(scorecards, [forged], _view(TA, TB))
    assert exc.value.code == "stage4_view_claims_membership_the_store_does_not_support"


# ===================================== ORDER AND ROLE: the swaps a SET of arm keys cannot see
#
# `selected_arm_keys` is a frozenset. Swap which arm is A and which is B, or swap the roles, and the
# set is bit-for-bit identical — yet the question inverts. These are the attacks that a membership
# hash over a set would pass with a straight face.

def test_swapping_the_ARMS_between_slots_MOVES_the_membership_hash():
    """A/B swap. Same two arm keys, same set, OPPOSITE question: it now searches for drugs that push
    toward the program the question wanted to move AWAY from."""
    cand = _candidate(observed_perturbation_arm_keys=[TA], arm_keys=[TA])
    honest = _view(TA, TB)
    base = rederive(cand, binding_from_selection_view(honest)).membership_sha256()

    # The arms change slots. Each slot keeps its own role and pole, so the view stays COHERENT —
    # and the selected-key SET is unchanged.
    swapped = _view(TA, TB)
    swapped["selected_arms"]["arms"] = {
        "A": _arm("away_from_A", "temporal|PROG_B|decrease|Rest|Stim48hr"),
        "B": _arm("toward_B", "temporal|PROG_A|increase|Rest|Stim48hr"),
    }
    swapped["selected_arms"]["gene_arm_keys"] = [
        "temporal|PROG_B|decrease|Rest|Stim48hr", "temporal|PROG_A|increase|Rest|Stim48hr"]
    swapped["selection"]["poles"] = {
        "A": {"program_id": "PROG_B", "direction": "high", "condition": REST},
        "B": {"program_id": "PROG_A", "direction": "high", "condition": STIM},
    }
    moved = rederive(cand, binding_from_selection_view(swapped)).membership_sha256()
    assert moved != base, "the programs swapped poles and the membership hash did not move"


def test_swapping_the_ROLES_between_slots_is_REFUSED():
    """Role swap. `A` is `away_from_A` and `B` is `toward_B` — pinned. If A ever carried `toward_B`,
    every downstream reading would be inverted and every hash would still agree."""
    view = _view(TA, TB)
    view["selected_arms"]["arms"]["A"]["role"] = "toward_B"
    view["selected_arms"]["arms"]["B"]["role"] = "away_from_A"
    view["selection"]["roles"] = {"A": "toward_B", "B": "away_from_A"}

    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(view)
    assert exc.value.code == "stage3_role_is_not_the_role_of_its_slot"


def test_REVERSING_the_temporal_endpoints_is_REFUSED():
    """`Rest -> Stim48hr` and `Stim48hr -> Rest` contain the SAME two conditions and describe
    OPPOSITE directions of time. A set-membership check on conditions accepts the reversal."""
    reversed_key = f"temporal|PROG_A|decrease|{STIM}|{REST}"
    view = _view(TA, TB)
    view["selected_arms"]["arms"]["A"] = _arm("away_from_A", reversed_key)
    view["selected_arms"]["gene_arm_keys"] = [reversed_key, TB]

    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(view)
    assert exc.value.code == "stage3_role_arm_context_is_not_the_selection_ordered_conditions"


def test_SWAPPING_which_pole_sits_at_which_CONDITION_is_REFUSED():
    """A sits at the first declared condition and B at the last. Swapping them swaps the question
    without changing a single arm key."""
    view = _view(TA, TB)
    view["selection"]["poles"]["A"]["condition"] = STIM   # A belongs at REST
    view["selection"]["poles"]["B"]["condition"] = REST

    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(view)
    assert exc.value.code == "stage3_pole_condition_is_not_its_ordered_condition"


def test_a_pole_DIRECTION_that_disagrees_with_the_arm_is_REFUSED():
    """High and low are opposite ends of the program, and Stage 3 states the direction twice."""
    view = _view(TA, TB)
    view["selection"]["poles"]["A"]["direction"] = "low"   # the arm says the pole is high

    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(view)
    assert exc.value.code == "stage3_selection_contradicts_itself_about_a_pole_direction"


def test_a_DESIRED_CHANGE_that_does_not_follow_from_role_and_pole_is_REFUSED():
    """THE SIGN OF THE WHOLE SEARCH. `away_from_A` on a HIGH pole means the program must DECREASE.
    A row claiming `increase` points Stage 4 at drugs that push the program the way the question
    wanted to AVOID — and every hash in the chain still agrees."""
    wrong = f"temporal|PROG_A|increase|{REST}|{STIM}"      # away from a HIGH pole must be decrease
    view = _view(TA, TB)
    view["selected_arms"]["arms"]["A"] = _arm("away_from_A", wrong)
    view["selected_arms"]["gene_arm_keys"] = [wrong, TB]

    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(view)
    assert exc.value.code == "stage3_desired_change_does_not_follow_from_role_and_pole"


def test_the_desired_change_is_DERIVED_for_every_role_and_pole_combination():
    """All four combinations, from Stage 3's own semantics — not one hard-coded case."""
    from analysis.selection_roles import DESIRED_CHANGE

    assert DESIRED_CHANGE == {
        ("toward", "high"): "increase", ("toward", "low"): "decrease",
        ("away", "high"): "decrease", ("away", "low"): "increase",
    }


def test_an_arm_whose_KEY_does_not_REBUILD_from_its_own_fields_is_REFUSED():
    """Stage 4 matches on the key and displays the fields. If they disagree it would be doing both
    to different arms."""
    view = _view(TA, TB)
    view["selected_arms"]["arms"]["A"]["program_id"] = "PROG_OTHER"   # key still says PROG_A

    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(view)
    assert exc.value.code == "stage3_role_arm_key_does_not_reproduce_from_its_fields"


def test_an_arm_whose_CONTEXT_ARITY_does_not_match_the_MODE_is_REFUSED():
    """A within-condition arm is measured AT a condition; a cross-condition arm BETWEEN two."""
    view = _view(DA, DB, mode="temporal_cross_condition", conditions=(REST, STIM))
    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(view)
    assert exc.value.code == "stage3_role_arm_context_does_not_match_the_analysis_mode"


def test_an_UNKNOWN_analysis_mode_is_refused_never_guessed():
    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(_view(TA, TB, mode="something_new"))
    assert exc.value.code == "stage3_unknown_analysis_mode"


# ================================ the JOIN: duplicates collapse silently, foreigners walk through

# W16's authoritative map, inverted: an arm's evidence STATE decides its ONE typed column.
STATE_FOR_COLUMN = {
    "observed_perturbation_arm_keys": "observed_perturbation",
    "inverse_direction_hypothesis_arm_keys": "inverse_direction_hypothesis",
    "pathway_hypothesis_arm_keys": "pathway_hypothesis",
    "opposed_arm_keys": "opposed",
    "unresolved_arm_keys": "unresolved",
}


def _summaries(*rows) -> list:
    """`arm_summaries`: the AUTHORITATIVE per-arm evidence state. One arm, one state, one column."""
    return [{"candidate_id": cid, "arm_key": arm, "arm_evidence_state": STATE_FOR_COLUMN[column]}
            for cid, arm, column in rows]


def _sc(*ids: str) -> dict:
    return {"scorecard_set_id": "sc1", "candidates": [{"candidate_id": i} for i in ids]}


# W16's ACTUAL receipt schema — `spot.stage03_membership_receipt.v1`. Stage 4 consumes it; it does
# not coin one. The receipt is SEALED ON DISK over a real view, because a dict the caller passes in
# is a proof the caller wrote for itself.
def _receipt(view_path="selection_view.json", **over) -> dict:
    from analysis.stage3_receipt import (MEMBERSHIP_RULE_ID, MEMBERSHIP_SCHEMA,
                                         MEMBERSHIP_VERIFIER_ID, RECEIPT_SCHEMA)

    r = {"schema_version": RECEIPT_SCHEMA, "verdict": "admit", "artifact_class": "fixture",
         "generator_id": "spot.stage03.selection_view.producer.v1",
         "verifier_id": MEMBERSHIP_VERIFIER_ID, "generator_is_not_verifier": True,
         "producer_tree_is_clean": True, "code_commit": "a50a28af85b2191d",
         "membership": {"schema": MEMBERSHIP_SCHEMA, "rule_id": MEMBERSHIP_RULE_ID,
                        "verifier_id": MEMBERSHIP_VERIFIER_ID,
                        "vocabulary_digest_in_force": "07f460f6" * 8, "retired_ids": []},
         "store": {"table_hashes": {"candidates": "1" * 64, "arm_summaries": "2" * 64},
                   "corroborating_tables": ["candidates", "arm_summaries"],
                   "corroborating_tables_uncovered": [],
                   "selection_view_vocabulary_digest": "07f460f6" * 8},
         "view": {"path": view_path}}
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(r.get(k), dict):
            r[k] = {**r[k], **v}
        else:
            r[k] = v
    return r


def _seal(bundle, view_doc, receipt) -> str:
    """Write the view and the receipt to a bundle dir and seal the receipt over the view's REAL
    hashes — exactly as W16's producer does."""
    import hashlib
    import json as _json
    import os

    from analysis.stage3_receipt import SELF_HASH_FIELD, canonical_sha256

    os.makedirs(bundle, exist_ok=True)
    rel = receipt["view"]["path"]
    vp = os.path.join(bundle, rel)
    raw = _json.dumps(view_doc).encode()
    with open(vp, "wb") as fh:
        fh.write(raw)

    content = canonical_sha256(
        {k: v for k, v in view_doc.items() if k not in ("view_id", "view_content_sha256")})
    receipt["view"] = {"path": rel, "raw_sha256": hashlib.sha256(raw).hexdigest(),
                       "canonical_sha256": canonical_sha256(view_doc),
                       "view_content_sha256": content, "view_id": content[:16]}
    body = {k: v for k, v in receipt.items() if k != SELF_HASH_FIELD}
    receipt[SELF_HASH_FIELD] = canonical_sha256(body)

    rp = os.path.join(bundle, "receipt.json")
    with open(rp, "w", encoding="utf-8") as fh:
        _json.dump(receipt, fh)
    return rp


def _bundled(view, store, summaries=None, receipt=None):
    """A hash-bound bundle: the view CARRIES the corroborating tables, the way W16 ships them.

    -> (bundle_dir, receipt_path, SEALED VIEW). The sealed view is what the caller must hand back:
    Stage 4 projects the receipt-bound bytes and refuses any copy that differs.
    """
    import tempfile

    doc = dict(view)
    doc["tables"] = {"candidates": list(store),
                     "arm_summaries": list(summaries if summaries is not None else
                                           _default_summaries(store))}
    bundle = tempfile.mkdtemp()
    return bundle, _seal(bundle, doc, receipt or _receipt()), doc


def _default_summaries(store):
    """Every published arm sits in exactly one typed column, and the summary says which."""
    out = []
    for c in store:
        for column, state in STATE_FOR_COLUMN.items():
            for k in (c.get(column) or []):
                out.append({"candidate_id": c["candidate_id"], "arm_key": k,
                            "arm_evidence_state": state})
    return out


# A sentinel: `None`/`{}` are MEANINGFUL here (the "no receipt" attacks). A falsy default would
# silently supply the very receipt those tests check the absence of.
_DEFAULT = object()


def _proj(scorecards, store, view, summaries=None, receipt=_DEFAULT, **kw):
    """Seal a real on-disk bundle (view + receipt) and project through the real consumer."""
    from analysis.projection import build_v2_projection

    bundle, receipt_path, sealed = _bundled(view, store, summaries,
                                            None if receipt is _DEFAULT else receipt)
    return build_v2_projection(scorecards, store, sealed,
                               stage3_receipt_path=receipt_path,
                               stage3_bundle_dir=bundle, **kw)


def test_a_DUPLICATE_stage3_candidate_id_is_REFUSED_before_the_join():
    """A dict join keeps the LAST row and silently discards the rest. Two different candidates
    sharing an id means one is displayed carrying the other's evidence — and no count looks wrong."""
    dupes = [_candidate("CAND_1", observed_perturbation_arm_keys=[TA], arm_keys=[TA]),
             _candidate("CAND_1", observed_perturbation_arm_keys=[TB], arm_keys=[TB])]
    with pytest.raises(MembershipError) as exc:
        _proj(_sc("CAND_1"), dupes, _view(TA, TB))
    assert exc.value.code == "stage3_candidate_ids_are_not_unique"


def test_a_DUPLICATE_stage4_scorecard_id_is_REFUSED():
    store = [_candidate("CAND_1", observed_perturbation_arm_keys=[TA], arm_keys=[TA])]
    with pytest.raises(MembershipError) as exc:
        _proj(_sc("CAND_1", "CAND_1"), store, _view(TA, TB))
    assert exc.value.code == "stage4_scorecard_candidate_ids_are_not_unique"


def test_a_FOREIGN_stage4_scorecard_candidate_is_REFUSED_not_shown_as_out_of_view():
    """A candidate Stage 4 scored that Stage 3 never admitted is not 'out of view' — it is evidence
    about a drug that entered the pipeline from somewhere else. A `.get()` returning None would have
    rendered it as merely out of view."""
    store = [_candidate("CAND_1", observed_perturbation_arm_keys=[TA], arm_keys=[TA])]
    with pytest.raises(MembershipError) as exc:
        _proj(_sc("CAND_1", "CAND_GHOST"), store, _view(TA, TB))
    assert exc.value.code == "stage4_scorecard_candidate_is_not_in_the_admitted_stage3_universe"
    assert "CAND_GHOST" in exc.value.context["foreign_candidate_ids"]


def test_OUT_OF_VIEW_is_permitted_ONLY_for_a_candidate_that_EXISTS_in_stage3():
    """The legitimate case, alongside the refusal above: the candidate IS admitted, and simply sits
    on none of the selected arms."""
    store = [_candidate("CAND_1", observed_perturbation_arm_keys=[TA], arm_keys=[TA]),
             _candidate("CAND_2", observed_perturbation_arm_keys=[FOREIGN], arm_keys=[FOREIGN])]
    doc = _proj(_sc("CAND_1", "CAND_2"), store, _view(TA, TB))

    rows = {c["candidate_id"]: c for c in doc["candidates"]}
    assert rows["CAND_1"]["in_active_view"] is True
    assert rows["CAND_2"]["in_active_view"] is False


def test_a_candidate_with_NO_ID_cannot_be_joined_to_anything():
    store = [_candidate("", observed_perturbation_arm_keys=[TA], arm_keys=[TA])]
    with pytest.raises(MembershipError) as exc:
        _proj(_sc("CAND_1"), store, _view(TA, TB))
    assert exc.value.code == "stage3_candidate_ids_are_not_unique"


def test_the_emitted_COUNTS_reconcile_exactly():
    """displayed + out_of_view == the input. Counted, not assumed: a row that is neither has
    vanished, and a vanished row is indistinguishable from one that never existed."""
    store = [_candidate("CAND_1", observed_perturbation_arm_keys=[TA], arm_keys=[TA]),
             _candidate("CAND_2", observed_perturbation_arm_keys=[FOREIGN], arm_keys=[FOREIGN]),
             _candidate("CAND_3", observed_perturbation_arm_keys=[TB], arm_keys=[TB])]
    doc = _proj(_sc("CAND_1", "CAND_2", "CAND_3"), store, _view(TA, TB))

    c = doc["counts"]
    assert c["n_stage3_view_candidates"] == 3
    assert "n_stage3_admitted" not in c, (
        "the rows came from a selection-filtered VIEW; calling them the admitted global store is a "
        "claim about bytes Stage 4 never loaded")
    assert c["n_stage4_scorecards"] == 3
    assert c["n_displayed"] + c["n_out_of_view"] == c["n_stage4_scorecards"]
    assert c["n_displayed"] == 2 and c["n_out_of_view"] == 1
    assert len(doc["candidates"]) == 3


# ========================== THE MISSING-FIELD BYPASS: a check you can delete is not a check
#
# Reversed endpoints and role swaps were refused — but only because the fields they compare were
# PRESENT. Delete the field and the comparison never runs. Each deletion below removed one whole
# side of the question while leaving every surviving field internally consistent, and the binding
# was ADMITTED.

@pytest.mark.parametrize("block", ["selected_arms.arms", "selection.roles", "selection.poles"])
def test_DELETING_the_B_POLE_from_any_block_is_REFUSED(block):
    """A selection missing one pole still validates on the pole it kept: same role, same program,
    same direction, same condition. It has silently become a different question — one with nothing
    to contrast against."""
    view = _view(TA, TB)
    outer, inner = block.split(".")
    del view[outer][inner]["B"]

    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(view)
    assert exc.value.code == "stage3_selection_does_not_state_both_poles"


@pytest.mark.parametrize("block", ["selected_arms.arms", "selection.roles", "selection.poles"])
def test_an_EXTRA_slot_beyond_A_and_B_is_REFUSED(block):
    """A question has exactly two poles."""
    view = _view(TA, TB)
    outer, inner = block.split(".")
    view[outer][inner]["C"] = view[outer][inner]["A"]

    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(view)
    assert exc.value.code == "stage3_selection_does_not_state_both_poles"


def test_an_EMPTY_conditions_list_is_REFUSED_it_TURNS_OFF_every_ordered_check():
    """`conditions: []` did not FAIL the ordered checks — it disabled them, because each one is a
    comparison against a list that is no longer there. A guard you can switch off by deleting its
    input is not a guard."""
    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(_view(TA, TB, conditions=()))
    assert exc.value.code == "stage3_selection_states_no_conditions"


def test_the_CONDITION_COUNT_must_match_the_analysis_mode():
    """A cross-condition question is asked BETWEEN two conditions, in order."""
    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(_view(TA, TB, conditions=(REST,)))
    assert exc.value.code == "stage3_selection_conditions_do_not_match_the_analysis_mode"


def test_a_CROSS_CONDITION_selection_cannot_contrast_a_condition_with_ITSELF():
    """Between one endpoint and itself there is no change to measure."""
    same = f"temporal|PROG_A|decrease|{REST}|{REST}"
    other = f"temporal|PROG_B|increase|{REST}|{REST}"
    with pytest.raises(MembershipError) as exc:
        binding_from_selection_view(_view(same, other, conditions=(REST, REST)))
    assert exc.value.code == "stage3_cross_condition_endpoints_are_the_same_condition"


# ============ TYPED MEMBERSHIP: exactly ONE column, derived from the arm's evidence STATE
#
# The first version asked each column "is your count positive?" So an arm listed in BOTH
# `observed_perturbation_arm_keys` AND `opposed_arm_keys`, whose summary reported
# n_observed_perturbation=1 and n_opposed=1, satisfied both questions and was ADMITTED as two
# corroborated placements. It is ONE arm. Asking "is this column plausible?" five times can never
# establish that exactly one is right.

def test_an_arm_in_TWO_typed_columns_is_REFUSED_even_when_both_look_supported():
    """THE STOP-GATE. Same active arm in observed AND opposed. The union is unchanged, every
    set-based check passes — and the drug is read as the strongest class it appears in."""
    from analysis.typed_membership import assert_typed_placement

    both = _candidate("CAND_1", observed_perturbation_arm_keys=[TA], opposed_arm_keys=[TA],
                      arm_keys=[TA])
    summaries = _summaries(("CAND_1", TA, "observed_perturbation_arm_keys"))

    with pytest.raises(MembershipError) as exc:
        assert_typed_placement(both, summaries)
    assert exc.value.code == "stage3_typed_arm_is_in_more_than_one_evidence_class"
    assert exc.value.context["also_in"] == ["opposed_arm_keys"]


def test_a_CONFLICTING_arm_maps_to_NO_column_and_is_REFUSED_never_skipped():
    """Stage 3 PRESERVES the contradiction (`observed` AND `opposed` -> `conflicting`). There is no
    column that honestly holds 'the sources disagree', so Stage 4 refuses rather than skipping —
    skipping is how the contradiction got displayed in the first place."""
    from analysis.typed_membership import assert_typed_placement

    cand = _candidate("CAND_1", observed_perturbation_arm_keys=[TA], arm_keys=[TA])
    summaries = [{"candidate_id": "CAND_1", "arm_key": TA, "arm_evidence_state": "conflicting"}]

    with pytest.raises(MembershipError) as exc:
        assert_typed_placement(cand, summaries)
    assert exc.value.code == "stage3_arm_evidence_state_has_no_typed_column"
    assert exc.value.context["state"] == "conflicting"


def test_an_arm_MOVED_to_a_column_its_STATE_does_not_map_to_is_REFUSED():
    """Promotion: the evidence is `opposed`, the candidate publishes it as `observed`."""
    from analysis.typed_membership import assert_typed_placement

    promoted = _candidate("CAND_1", observed_perturbation_arm_keys=[TA], arm_keys=[TA])
    summaries = _summaries(("CAND_1", TA, "opposed_arm_keys"))     # the state says OPPOSED

    with pytest.raises(MembershipError) as exc:
        assert_typed_placement(promoted, summaries)
    assert exc.value.code == "stage3_typed_arm_is_not_in_the_column_its_state_maps_to"
    assert exc.value.context["expected"] == "opposed_arm_keys"


def test_the_state_to_column_map_is_W16s_and_covers_every_evidence_class():
    from analysis.typed_membership import COLUMN_FOR_STATE, STATES_WITH_NO_TYPED_COLUMN

    assert COLUMN_FOR_STATE == {
        "observed_perturbation": "observed_perturbation_arm_keys",
        "inverse_direction_hypothesis": "inverse_direction_hypothesis_arm_keys",
        "pathway_hypothesis": "pathway_hypothesis_arm_keys",
        "opposed": "opposed_arm_keys",
        "unresolved": "unresolved_arm_keys",
    }
    assert "conflicting" in STATES_WITH_NO_TYPED_COLUMN


def test_a_typed_arm_with_NO_arm_summary_is_REFUSED():
    from analysis.typed_membership import assert_typed_placement

    cand = _candidate("CAND_1", observed_perturbation_arm_keys=[TA], arm_keys=[TA])
    with pytest.raises(MembershipError) as exc:
        assert_typed_placement(cand, _summaries(("CAND_1", TB, "observed_perturbation_arm_keys")))
    assert exc.value.code == "stage3_typed_arm_has_no_arm_summary"


def test_an_HONEST_candidate_with_ONE_column_per_arm_is_ADMITTED():
    """The gates must be passable. One arm, one state, one column."""
    from analysis.typed_membership import assert_typed_placement

    cand = _candidate("CAND_1", observed_perturbation_arm_keys=[TA], opposed_arm_keys=[TB],
                      arm_keys=[TA, TB])
    summaries = _summaries(("CAND_1", TA, "observed_perturbation_arm_keys"),
                           ("CAND_1", TB, "opposed_arm_keys"))
    assert assert_typed_placement(cand, summaries)["typed_arm_placements_checked"] == 2
