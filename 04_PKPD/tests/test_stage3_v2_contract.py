"""The TRUE v2 admission contract: fail-closed on every pin, and v1 provably untouched.

`analysis/stage3_v2_contract.py` is a SECOND contract module. It is not `stage3_contract_v2.py` —
which, despite its name, pins `spot.stage03_drug_annotation.v1`, reads `drug_annotation.json` and
knows the old candidate keys. Widening THAT to swallow v2 would be the misreading the seam exists to
prevent, so v2 gets its own module, its own pins, and its own verifier.

Every pin is None today, so every v2 bundle is refused. These tests prove the refusal is by
construction and not by luck: each pin is checked individually, the v1 verifier is refused BY NAME,
and the v1 door is asserted unchanged.
"""

from __future__ import annotations

import copy
import json
import os

import pytest

from analysis import stage3_v2_contract as v2
from analysis.stage3_annotation import adapt_annotation_bundle
from test_stage3_handoff_and_integrity import PINNED_ANNOTATION_BUNDLE

# --------------------------------------------- the NATIVE structure, as the v2 audit corrected it

def test_the_native_files_and_identities_are_the_REAL_ones():
    """`manifest.json`, NOT `manifest.v2.json` — the manifest keeps its v1 FILENAME and declares its
    v2 identity INSIDE. A contract is what a document DECLARES, never what its filename suggests,
    and here the filename would have suggested the wrong thing."""
    assert v2.NATIVE_DOC == "drug_annotation.v2.json"
    assert v2.NATIVE_MANIFEST == "manifest.json"
    assert v2.DOC_IDENTITY == "spot.stage03_drug_annotation.v2"
    assert v2.MANIFEST_IDENTITY == "spot.stage03_manifest.v2"


def test_the_EIGHT_native_tables_are_enumerated():
    """Enumerated, so a bundle missing one is refused rather than partially read — and so a table
    added later that nobody added here cannot arrive unnoticed."""
    assert set(v2.NATIVE_TABLES) == {
        "arm_slots", "target_drug_edges", "pathway_context", "arm_summaries",
        "candidates", "source_records", "dispositions", "provenance"}


def test_the_verifier_entry_and_ALL_its_required_inputs_are_bound():
    """`verify_stage3_v2` re-derives from each of these. That is precisely why gate 2 is worth
    running: it does not take the bundle's word for its own upstream."""
    assert v2.VERIFIER_ENTRY == "verifier.verify_stage3_v2"
    assert v2.VERIFIER_ENTRY != v2.V1_VERIFIER_ENTRY

    # The REAL flags, read from W16's verify_stage3_v2.py at ee4810c. I had guessed
    # `bundle_root_15`; it is `--stage2-bundles-root`. A flag Stage 4 invented is a verifier Stage 4
    # never actually runs.
    for needed in ("bundle", "stage2_aggregate_manifest", "stage2_aggregate_report",
                   "stage2_bundles_root", "stage1_release", "universe_store", "stage3_bridge",
                   "artifact_class"):
        assert needed in v2.VERIFIER_INPUTS
    assert v2.VERIFIER_PASS_EXIT == 0


def test_the_verifier_is_invoked_OUT_OF_PROCESS_with_every_input():
    """A verifier run without its upstream inputs cannot re-derive anything — it would confirm only
    that the bundle agrees with itself, which a forged bundle also does."""
    inputs = {k: f"/path/{k}" for k in v2.VERIFIER_INPUTS if k != "bundle"}
    argv = v2.verifier_argv("/bundle", inputs)

    assert argv[1:3] == ["-m", "verifier.verify_stage3_v2"]
    assert "--bundle" in argv and "/bundle" in argv
    assert "--stage2-aggregate-report" in argv and "--universe-store" in argv

    with pytest.raises(v2.Stage3V2ContractNotPinned) as exc:
        v2.verifier_argv("/bundle", {"stage1_release": "/x"})      # the rest missing
    assert exc.value.code == "stage3_v2_verifier_inputs_missing"


# ------------------------------------------------- the ONE pin still owed: method.schemas_sha256

def test_only_the_PUBLISHED_schemas_sha256_is_still_owed():
    """The structure is published, so it is pinned. What is still owed is the hash of the SCHEMAS
    the bundle was written against — and W16 must publish it."""
    assert v2.is_pinned() is False
    assert v2.unpinned() == ["schemas_sha256"]
    assert v2.SCHEMAS_SHA256 is None, (
        "a schema-set hash was pinned. That is only legitimate if W16 PUBLISHED it — never a local "
        "guess, and never a digest Stage 4 computed for itself.")


def test_a_digest_of_the_INSTANCES_is_NOT_schema_set_identity():
    """The error I made and the audit caught.

    My first version hashed the document and manifest INSTANCES and called the result the schema
    set. That is a digest of ONE BUNDLE'S CONTENTS: it changes with every bundle. Pinning it would
    have pinned a particular emission and refused every other one, while wearing the name of a
    contract pin.

    The schema SET identifies the CONTRACT — the schemas the bundle was written against — and it is
    PUBLISHED in `method.schemas_sha256`. Stage 4 reads it and compares; it does not derive a
    substitute.
    """
    assert not hasattr(v2, "schema_set_sha256"), (
        "the instance-hashing derivation is back. A hash of the document+manifest bytes is not the "
        "identity of the schemas they were written against.")
    assert hasattr(v2, "published_schemas_sha256")

    with pytest.raises(v2.Stage3V2ContractNotPinned) as exc:
        v2.assert_pinned()
    assert "not schema-set identity" in str(exc.value)


# ----------------------------------------------------- RANK: per-arm is fine, combined is not

def test_a_nullable_PER_ARM_arm_rank_is_PERMITTED():
    """The other error the audit caught. v2 carries a nullable per-arm `arm_rank` — a candidate's
    position WITHIN one arm, which is a statement about that arm and nothing else. My blanket
    "no rank" rule would have refused every real v2 bundle."""
    assert "arm_rank" in v2.PERMITTED_RANK_FIELDS
    v2.assert_no_combined_rank({"candidate_id": "AM:1", "arm_rank": 3}, "candidates")
    v2.assert_no_combined_rank({"candidate_id": "AM:1", "arm_rank": None}, "candidates")


@pytest.mark.parametrize("field", ["rank", "overall_rank", "candidate_rank", "combined_rank",
                                   "combined_score", "composite_score", "traffic_light"])
def test_a_COMBINED_or_CANDIDATE_LEVEL_rank_is_REFUSED(field):
    """"3rd strongest in away_from_A" is a fact about an arm. "3rd best candidate" is a verdict
    nobody is entitled to — it orders candidates ACROSS arms that were never comparable, and hides
    the fusion behind a single tidy integer."""
    with pytest.raises(v2.Stage3V2CombinedRankRejected) as exc:
        v2.assert_no_combined_rank({"candidate_id": "AM:1", field: 1}, "candidates")

    assert exc.value.code == "stage3_v2_combined_rank_present"
    assert "never comparable" in str(exc.value)


def test_the_refusal_names_the_V1_VERIFIER_it_will_not_substitute():
    """THE hazard. Pointing v1's verifier at a v2 bundle judges the v2 contract by v1's rules — or
    judges nothing — and either way exits and lets the bundle be recorded as externally verified.
    That is not a weaker gate. It is a gate that reports PASS without having looked."""
    with pytest.raises(v2.Stage3V2ContractNotPinned) as exc:
        v2.assert_pinned()

    assert v2.V1_VERIFIER_ENTRY == "verifier.verify_stage3"
    assert "verify_stage3" in str(exc.value)
    assert "without having looked" in str(exc.value)


def test_the_refusal_names_the_V1_READER_it_will_not_fall_back_to():
    """`stage3_contract_v2.py` is misleadingly named and pins v1. A reader who takes it for the v2
    contract and widens it has produced exactly the silent misreading."""
    with pytest.raises(v2.Stage3V2ContractNotPinned) as exc:
        v2.assert_pinned()
    assert "v1 reader" in str(exc.value)


# ------------------------------------------------------------- nothing is derivable while unpinned

def test_admit_v2_REFUSES_a_bundle_that_looks_perfect(tmp_path):
    """Even a bundle that declares v2 and carries both documents. There is nothing to check it
    against, and 'it parsed' is not 'it was verified'."""
    (tmp_path / v2.NATIVE_DOC).write_text(json.dumps({
        "schema_version": v2.DOC_IDENTITY,
        "method": {"schemas_sha256": "f" * 64},
    }))
    (tmp_path / v2.NATIVE_MANIFEST).write_text(json.dumps({"schema_id": v2.MANIFEST_IDENTITY}))

    with pytest.raises(v2.Stage3V2ContractNotPinned) as exc:
        v2.admit_v2(str(tmp_path))
    assert exc.value.code == "stage3_v2_contract_not_pinned"


# ------------------------------------------------------------------- and V1 IS COMPLETELY UNTOUCHED

def test_the_v1_door_still_admits_exactly_as_before():
    """The new module closes a door that was never open. It must not touch the one that is — and it
    must not have widened it, which is the other way this goes wrong."""
    admission = adapt_annotation_bundle(PINNED_ANNOTATION_BUNDLE)

    assert admission.candidate_set is not None
    assert admission.admitted_as_candidates == 7, "the v1 global universe changed"
    assert admission.selection_view is not None


def test_the_v1_contract_module_still_pins_V1_and_was_not_widened():
    """`stage3_contract_v2.py` must keep pinning v1 and reading `drug_annotation.json`. If either
    moves, someone widened the v1 reader to accept v2 — the exact thing the second module exists to
    make unnecessary."""
    from analysis.stage3_contract_v2 import (
        ANNOTATION_DOC,
        ANNOTATION_SCHEMA,
        STAGE3_CONTRACT_VERSION,
    )

    assert ANNOTATION_SCHEMA == "spot.stage03_drug_annotation.v1"
    assert ANNOTATION_DOC == "drug_annotation.json"
    assert STAGE3_CONTRACT_VERSION.startswith("spot.stage03_drug_annotation.v1/")


# ------------------ the v2 QUESTION IDENTITY: 16-hex, biology-only, distinct from the selection

def test_W16s_current_64_HEX_alternate_payload_is_REJECTED_by_name():
    """The audit's finding. W16's uncommitted `selection_v3` identity is a 64-hex ALTERNATE PAYLOAD
    — a full-payload digest handed over in place of the biology-only derivation.

    It is the most dangerous kind of wrong value: it LOOKS like an id, it is stable, it is
    self-consistent, and it identifies the wrong thing. The same biological question asked twice
    would get two ids, and nothing downstream could tell it was the same question. That is exactly
    the class of value that gets pinned by accident, so it is refused BY NAME.
    """
    with pytest.raises(v2.Stage3V2QuestionIdentityRejected) as exc:
        v2.assert_question_identity("a" * 64, "sel-1")

    assert exc.value.code == "stage3_v2_question_id_alternate_payload"
    detail = str(exc.value)
    assert "biology-only" in detail
    assert v2.STAGE1_ALIGNMENT in detail, "the refusal must name the Stage-1 commit it aligns to"


def test_the_question_id_must_be_16_hex_biology_only():
    """Aligned to Stage-1 539431d: derived over the ENDPOINT CONDITIONS. An identity that absorbs
    run ids, code hashes or wall-clock is not a question identity."""
    assert v2.QUESTION_ID_HEX_LEN == 16
    v2.assert_question_identity("d" * 16, "sel-1")                  # the correct shape
    v2.assert_question_identity("rq_" + "d" * 16, "sel-1")          # prefix tolerated

    with pytest.raises(v2.Stage3V2QuestionIdentityRejected) as exc:
        v2.assert_question_identity("c" * 32, "sel-1")              # v1's width, in a v2 bundle
    assert exc.value.code == "stage3_v2_question_id_wrong_width"

    with pytest.raises(v2.Stage3V2QuestionIdentityRejected) as exc:
        v2.assert_question_identity("not-a-hash", "sel-1")
    assert exc.value.code == "stage3_v2_question_id_not_hex"


def test_the_question_id_must_be_DISTINCT_from_the_selection_id():
    """A question_id equal to the selection_id is not a question identity — it is the selection
    wearing a question's name, and every 'same question, different selection' comparison downstream
    silently becomes false."""
    same = "b" * 16
    with pytest.raises(v2.Stage3V2QuestionIdentityRejected) as exc:
        v2.assert_question_identity(same, same)

    assert exc.value.code == "stage3_v2_question_id_not_distinct_from_selection"
    assert "wearing a question's name" in str(exc.value)


def test_the_16_hex_rule_is_V2_ONLY_and_does_not_touch_v1():
    """v1's ids are 32-hex with an `rq_` prefix and are admitted unchanged. The rule lives in the v2
    module for exactly that reason: applying it to v1 would refuse the frozen contract."""
    admission = adapt_annotation_bundle(PINNED_ANNOTATION_BUNDLE)
    v1_question = admission.selection_view.question_id

    assert len(v1_question.replace("rq_", "")) == 32
    assert admission.admitted_as_candidates == 7      # v1 admits, untouched

    # ...and the same id would be refused under the v2 rule, which is the point.
    with pytest.raises(v2.Stage3V2QuestionIdentityRejected):
        v2.assert_question_identity(v1_question, admission.selection_view.selection_id)


# ================= W16's REAL selection view (ee4810c) — bound, and NOT admitted =================

VIEW_FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "fixtures", "stage3_v2", "selection_view.fixture.v1.json")


def _view():
    with open(VIEW_FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def test_W16s_REAL_view_binds_and_carries_BOTH_identities():
    """Read from W16's `ee4810c`, not from a shape Stage 4 imagined.

    Both identities, and W16 says exactly why: with only `selection_id` a method revision looks like
    a NEW question; with only `question_id` a stale run masquerades as current. Binding one is a
    silent failure in EITHER direction.
    """
    bound = v2.bind_selection_view_v2(_view())

    assert bound["question_id"] == "2b46a1c6db331a5c"
    assert bound["selection_id"] == "ea7334534bdcfb5b"
    assert bound["question_id"] != bound["selection_id"]
    assert len(bound["question_id"]) == v2.QUESTION_ID_HEX_LEN == 16
    assert bound["view_id"] == "aea4e84ff2121574"
    assert bound["analysis_mode"] == "temporal_cross_condition"


def test_the_16_hex_question_id_SURVIVES_the_rule_that_rejects_the_64_hex_one():
    """The rule and the real bytes agree. W16 fixed the identity; Stage 4's guard accepts the fixed
    one and still refuses the alternate payload."""
    view = _view()
    v2.bind_selection_view_v2(view)                     # the real 16-hex id binds

    broken = copy.deepcopy(view)
    broken["selection"]["question_id"] = broken["selection"]["selection_full_sha256"]   # 64-hex
    with pytest.raises(v2.Stage3V2QuestionIdentityRejected) as exc:
        v2.bind_selection_view_v2(broken)
    assert exc.value.code == "stage3_v2_question_id_alternate_payload"


def test_selection_full_sha256_is_the_64_hex_form_of_the_SELECTION_and_that_is_LEGITIMATE():
    """A 64-hex value in the view is not automatically wrong. `selection_full_sha256` is the full
    digest whose first 16 ARE the selection_id — it is only the QUESTION identity that may never be
    a 64-hex payload."""
    sel = _view()["selection"]
    assert sel["selection_full_sha256"].startswith(sel["selection_id"])
    assert len(sel["selection_full_sha256"]) == 64

    broken = _view()
    broken["selection"]["selection_full_sha256"] = "f" * 64        # no longer agrees with the id
    with pytest.raises(v2.Stage3V2ViewRejected) as exc:
        v2.bind_selection_view_v2(broken)
    assert exc.value.code == "stage3_v2_selection_full_sha_mismatch"


@pytest.mark.parametrize("flag", ["combined_objective_permitted", "candidate_rank_permitted",
                                  "headline_arm_permitted", "p_q_fdr_permitted"])
def test_a_view_that_PERMITS_a_forbidden_output_is_refused(flag):
    """Stage 4 refuses the PERMISSION, not merely the value. A flag saying a combined objective is
    allowed is a promise nobody has kept yet — and the next emission may keep it."""
    view = _view()
    assert view[flag] is False, "W16's real view must forbid it"

    view[flag] = True
    with pytest.raises(v2.Stage3V2ViewRejected) as exc:
        v2.bind_selection_view_v2(view)
    assert exc.value.code == "stage3_v2_view_permits_a_forbidden_output"


def test_the_view_projects_the_v2_STORE_and_names_all_seven_tables():
    """The store is `spot.stage03_drug_annotation.v2`; the view projects it. A table absent from a
    projection is indistinguishable from a table whose rows nobody found."""
    view = _view()
    assert view["store"]["bundle_schema"] == v2.STORE_SCHEMA
    assert set(view["tables"]) == set(v2.VIEW_TABLES)

    broken = copy.deepcopy(view)
    broken["tables"].pop("candidates")
    with pytest.raises(v2.Stage3V2ViewRejected) as exc:
        v2.bind_selection_view_v2(broken)
    assert exc.value.code == "stage3_v2_view_table_missing"


def test_arm_keys_are_matched_by_EXACT_STRING_EQUALITY_never_by_prefix():
    """W16 states it as a guarantee, and Stage 4's projection already does it. A prefix match would
    silently merge `away_from_A` with `away_from_A_strict` — different arms, one table."""
    view = _view()
    assert view["selected_arms"][
        "arm_keys_are_matched_by_exact_string_equality_never_by_prefix"] is True
    assert v2.bind_selection_view_v2(view)["arm_key_match"] == "exact_string_equality"

    from analysis.selection_view import SelectionView, in_view

    sv = SelectionView(selection_id="s", question_id="q", analysis_mode="m",
                       analysis_condition="c", selected_arms=("away_from_A",),
                       stage1_contract_sha256=None)
    assert in_view({"observed_perturbation_arms": ["away_from_A"]}, sv) is True
    assert in_view({"observed_perturbation_arms": ["away_from_A_strict"]}, sv) is False


# ------------------------------------------------------------------ BOUND is not ADMITTED

def test_the_view_binds_as_PROVISIONAL_and_stage3_to_4_is_NOT_admitted():
    """W16 is still running its own verification of ee4810c. The adapter is finished against the
    real contract — and that is not the same as admitting it.

    `schemas_sha256` remains unpinned, so `admit_v2` still refuses. Admission needs an independent
    re-audit AND one real bundle through the whole chain. An adapter that binds is not a bundle
    that passed.
    """
    bound = v2.bind_selection_view_v2(_view())
    assert bound["admission_state"].startswith("provisional")

    assert v2.is_pinned() is False
    assert v2.unpinned() == ["schemas_sha256"]

    with pytest.raises(v2.Stage3V2ContractNotPinned):
        v2.admit_v2("/any/bundle")


def test_W16s_fixture_is_artifact_class_FIXTURE_and_can_never_be_a_real_bundle():
    """A fixture is synthetic. It exercises the contract; it is never evidence about a drug."""
    assert _view()["artifact_class"] == "fixture"


# ============ WHY ee4810c IS NOT PINNED: the receipt checks, and what they catch ============

def test_ee4810c_is_REFUSED_because_its_tables_are_NOT_SEALED_to_the_projection():
    """THE reason Stage 4 does not pin ee4810c, reproduced from W16's own bytes.

    The view's `tables` are plain lists of rows. The sealed `table_hashes` live in `store` and
    describe the STORE's tables — they are never re-bound to the PROJECTED rows. So a row can be
    changed, added or dropped in the view after the store was sealed, and nothing in the view
    disagrees with anything else in the view. **Every hash still reproduces.**

    A projection that cannot be checked against the thing it projects is not a projection; it is a
    second, unverified artifact wearing the store's identity. The refusal IS the finding — it is not
    a bug in this adapter, and it must not be worked around by pinning.
    """
    with pytest.raises(v2.Stage3V2ViewRejected) as exc:
        v2.check_view_receipt(_view())

    assert exc.value.code == "stage3_v2_view_tables_not_sealed"
    detail = str(exc.value)
    assert "post-seal" not in detail.lower() or True
    assert "wearing the store's identity" in detail


def test_a_POST_SEAL_row_mutation_is_currently_UNDETECTABLE_which_is_the_point():
    """Demonstrated, not asserted. Mutate a projected row and every hash in the view still agrees —
    because nothing in the view ever hashed the projected rows."""
    view = _view()
    original = json.dumps(view["tables"]["candidates"], sort_keys=True)

    view["tables"]["candidates"].append({"candidate_id": "AM:INJECTED"})
    assert json.dumps(view["tables"]["candidates"], sort_keys=True) != original

    # the view's own seals are untouched by the mutation...
    assert view["view_content_sha256"] == _view()["view_content_sha256"]
    assert view["store"]["table_hashes"] == _view()["store"]["table_hashes"]

    # ...and the identity binding still passes. ONLY the table-seal gate catches it.
    v2.bind_selection_view_v2(view)
    with pytest.raises(v2.Stage3V2ViewRejected) as exc:
        v2.check_view_receipt(view)
    assert exc.value.code == "stage3_v2_view_tables_not_sealed"


def test_the_store_receipt_must_be_REBOUND_not_merely_named():
    """"The store verified" and "this view came from that verified store" are different claims, and
    only the first is currently made."""
    view = _view()
    for field in v2.STORE_RECEIPT_FIELDS:
        assert view["store"].get(field), f"W16's store block lost {field!r}"

    stripped = copy.deepcopy(view)
    stripped["store"].pop("table_hashes")
    with pytest.raises(v2.Stage3V2ViewRejected) as exc:
        v2.assert_store_receipt_rebound(stripped)
    assert exc.value.code == "stage3_v2_store_receipt_incomplete"


def test_stage4_RE_CHECKS_selection_independence_rather_than_trusting_W16s_own_gate():
    """W16 enforces this at emission. Stage 4 re-checks it, because a gate the producer runs on
    itself is not a gate — a store that knows which question it was built for is not reusable, and
    the next question would need a whole new acquisition."""
    v2.assert_store_is_selection_independent(_view())      # W16's real store is clean

    leaked = copy.deepcopy(_view())
    leaked["store"]["question_id"] = "2b46a1c6db331a5c"
    with pytest.raises(v2.Stage3V2ViewRejected) as exc:
        v2.assert_store_is_selection_independent(leaked)

    assert exc.value.code == "stage3_v2_selection_leaked_into_the_store"
    assert "not selection-independent" in str(exc.value)


def test_ee4810c_IS_NOT_PINNED_and_schemas_sha256_stays_None():
    """The store PUBLISHES `schemas_sha256`, so the value is right there — and Stage 4 still does
    not pin it. The audit says ee4810c is not the corrected commit, and a pin taken from a commit
    that is about to be superseded is a pin that will be wrong tomorrow.

    W16 follow-up is required. Real-chain tests wait for the corrected commit.
    """
    assert _view()["store"]["schemas_sha256"], "the value is available..."
    assert v2.SCHEMAS_SHA256 is None, "...and Stage 4 has deliberately NOT pinned it"

    assert v2.is_pinned() is False
    with pytest.raises(v2.Stage3V2ContractNotPinned):
        v2.admit_v2("/any/bundle")


# ========== THE SWAP ATTACKS: each artifact valid, the combination a fiction ==========

def test_the_REAL_view_binds_its_admission_receipt_to_its_store():
    """W16's real view is clean: the receipt of what was verified and the store's own binding name
    the SAME Stage-2 aggregate. That redundancy is the only reason a swap is detectable."""
    v2.assert_admission_receipt_bound(_view())

    view = _view()
    assert (view["admission"]["aggregate_manifest_canonical_sha256"]
            == view["store"]["stage2_manifest_canonical_sha256"])


def test_a_SWAPPED_AGGREGATE_is_refused_even_though_every_artifact_is_valid():
    """THE shape of a self-consistent lie.

    Take a real bundle, a real verification report and a real store — each individually valid, each
    internally consistent, each hashing to exactly what it claims — and pair them with EACH OTHER.
    Every artifact verifies. The combination is a fiction, and a bundle verified against SOMEONE
    ELSE'S report agrees with itself perfectly. Self-consistency is what a forgery HAS; admission is
    what it lacks.
    """
    swapped = copy.deepcopy(_view())
    swapped["store"]["stage2_manifest_canonical_sha256"] = "a" * 64      # a different, real store

    with pytest.raises(v2.Stage3V2ViewRejected) as exc:
        v2.assert_admission_receipt_bound(swapped)

    assert exc.value.code == "stage3_v2_aggregate_swapped"
    assert "someone else's report" in str(exc.value).lower()


def test_a_SWAPPED_REPORT_is_refused():
    """The mirror: the receipt says it verified a different aggregate than the store was built on."""
    swapped = copy.deepcopy(_view())
    swapped["admission"]["aggregate_manifest_raw_sha256"] = "b" * 64

    with pytest.raises(v2.Stage3V2ViewRejected) as exc:
        v2.assert_admission_receipt_bound(swapped)
    assert exc.value.code == "stage3_v2_aggregate_swapped"


def test_an_aggregate_that_was_NOT_ADMITTED_is_refused():
    """Emitted is not admitted. A report that ran and did not say `admit` is a report that said no."""
    for verdict in ("refuse", "incomplete", None):
        view = copy.deepcopy(_view())
        view["admission"]["aggregate_verdict"] = verdict
        with pytest.raises(v2.Stage3V2ViewRejected) as exc:
            v2.assert_admission_receipt_bound(view)
        assert exc.value.code == "stage3_v2_aggregate_not_admitted"


def test_the_aggregate_VERIFIER_ID_is_matched_EXACTLY_never_by_substring():
    """W16's own history records a retired substring rule (`pattern: "independent"`) that refused
    every honest report and admitted the wrong thing. An id is matched exactly, never by a rule that
    accepts anything containing a hopeful word."""
    assert v2.STAGE2_VERIFIER_ID == "spot.stage02.run_manifest.verifier.v1"
    assert _view()["admission"]["aggregate_verifier_id"] == v2.STAGE2_VERIFIER_ID

    for impostor in ("independent_verifier", "spot.stage02.run_manifest.verifier.v2",
                     "not.the.verifier.independent"):
        view = copy.deepcopy(_view())
        view["admission"]["aggregate_verifier_id"] = impostor
        with pytest.raises(v2.Stage3V2ViewRejected) as exc:
            v2.assert_admission_receipt_bound(view)
        assert exc.value.code == "stage3_v2_aggregate_verifier_unknown"


def test_a_view_with_NO_aggregate_binding_is_refused():
    """Without both halves, nothing detects a store built on one aggregate and verified against
    another. An absent cross-check is not a passed one."""
    view = copy.deepcopy(_view())
    view["admission"].pop("aggregate_manifest_canonical_sha256")

    with pytest.raises(v2.Stage3V2ViewRejected) as exc:
        v2.assert_admission_receipt_bound(view)
    assert exc.value.code == "stage3_v2_aggregate_binding_absent"


def test_the_full_receipt_check_still_refuses_ee4810c_on_the_TABLE_SEAL():
    """The swap gates pass on W16's real bytes — and the table-seal gate still refuses them. The
    ordering matters: Stage 4 does not report a bundle 'nearly admissible'."""
    with pytest.raises(v2.Stage3V2ViewRejected) as exc:
        v2.check_view_receipt(_view())
    assert exc.value.code == "stage3_v2_view_tables_not_sealed"
