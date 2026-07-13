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

import json

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

    for needed in ("bundle", "stage2_aggregate_manifest", "stage2_aggregate_report",
                   "bundle_root_15", "stage1_release", "universe_store", "stage3_bridge",
                   "artifact_class"):
        assert needed in v2.VERIFIER_INPUTS


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
