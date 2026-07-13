"""The Stage-3 v2 seam: closed until W16 pins it, and closed for the RIGHT reason.

W16 is still writing `spot.stage03_drug_annotation.v2`. Stage 4 does not know its fields, and these
tests exist to prove Stage 4 never pretends to.

The danger is not that a v2 bundle fails to load. It is that it LOADS. A v2 document whose column
names happen to overlap v1's would be read by the v1 reader, its new fields silently ignored, its
new origin vocabulary silently dropped, and its evidence admitted against a contract nobody checked
it against. Every downstream hash would then be self-consistent — and every one would be a hash of
a misreading. "It parsed" is not "it was verified".

So a v2 bundle is refused BY NAME, at every door, before the v1 reader sees a byte.
"""

from __future__ import annotations

import json
import os
import shutil

import pytest

from analysis.stage3_annotation import adapt_annotation_bundle
from analysis.stage3_v2_seam import (
    STAGE3_V2_SCHEMA,
    v2_documents,
    STAGE3_V2_SCHEMA_SET_SHA256,
    Stage3V2NotAdmissible,
    assert_v2_admissible,
    is_v2_bundle,
    seam_status,
)
from test_stage3_handoff_and_integrity import PINNED_ANNOTATION_BUNDLE


# W16's ACTUAL emission filename. The seam's first version scanned only `drug_annotation.json` and
# `manifest.json`, so a real v2 bundle was INVISIBLE to it — and this test suite passed anyway,
# because it built the v2 bundle using the V1 filename. The test constructed the adversary in the
# seam's own image. Both are fixed, and this constant is why.
W16_V2_DOC = "drug_annotation.v2.json"


def _v2_declaring_bundle(tmp_path, *, doc_name: str = W16_V2_DOC, keep_v1_doc: bool = False):
    """A real v1 bundle, relabelled to DECLARE v2 — the exact shape that must not sneak through.

    Deliberately a bundle whose tables the v1 reader CAN read: if the seam only caught v2 bundles
    that were structurally broken, it would catch nothing that mattered. The whole risk is the v2
    bundle that parses.

    `doc_name` defaults to what W16 really emits, NOT to what v1 emits.
    """
    dst = tmp_path / f"s3_v2_{doc_name}"
    shutil.copytree(PINNED_ANNOTATION_BUNDLE, dst)

    v1_doc = dst / "drug_annotation.json"
    with open(v1_doc, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["schema_version"] = STAGE3_V2_SCHEMA

    with open(dst / doc_name, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
    if doc_name != "drug_annotation.json" and not keep_v1_doc:
        v1_doc.unlink()
    return str(dst)


# ------------------------------------------------------------------------ the seam is CLOSED

def test_the_v2_contract_is_deliberately_UNPINNED():
    """None means unpinned means closed. If this ever fails, someone pinned the contract — which is
    fine, but it must be a deliberate act taken after W16 published the hash, never a local guess:
    a hash Stage 4 computed for itself pins nothing."""
    assert STAGE3_V2_SCHEMA_SET_SHA256 is None, (
        "the v2 schema set is pinned. That is only legitimate if W16 PUBLISHED this hash and an "
        "independently admitted v2 bundle exists; it must never be a locally computed value.")

    status = seam_status()
    assert status["pinned"] is False
    assert "CLOSED" in status["state"]
    assert status["v1_unaffected"].startswith("spot.stage03_drug_annotation.v1")


def test_a_v2_bundle_is_REFUSED_and_never_read_under_the_v1_contract(tmp_path):
    """THE test. Not "v2 fails to parse" — v2 must not be PARSED AT ALL.

    This bundle's tables are perfectly readable by the v1 reader. That is the point: the failure
    mode being prevented is the one where a v2 document loads cleanly and is admitted against a
    contract nobody checked it against.
    """
    bundle = _v2_declaring_bundle(tmp_path)

    with pytest.raises(Stage3V2NotAdmissible) as exc:
        adapt_annotation_bundle(bundle)

    assert exc.value.code == "stage3_v2_external_verifier_not_declared"
    detail = str(exc.value)
    assert "not read under the v1 contract" in detail.lower(), (
        "the refusal must say WHY it refuses rather than parse-and-hope")
    assert "W16" in detail, "the refusal must name what would unblock it"


def test_the_refusal_PUBLISHES_what_stage4_requires_of_v2(tmp_path):
    """The mirror image of Stage 4 not guessing W16's fields: W16 should not have to guess Stage
    4's requirements. The refusal states them."""
    bundle = _v2_declaring_bundle(tmp_path)

    with pytest.raises(Stage3V2NotAdmissible) as exc:
        assert_v2_admissible(bundle)

    detail = str(exc.value)
    for required in ("verify_stage3", "immutable candidate identifier",
                     "explicit missingness", "NO combined objective"):
        assert required.lower() in detail.lower(), f"the seam does not state that it requires {required!r}"


def test_v2_is_detected_from_the_DECLARATION_never_inferred(tmp_path):
    """Read what the bundle says it is. A contract is not guessed from the shape of its tables."""
    assert is_v2_bundle(_v2_declaring_bundle(tmp_path)) is True
    assert is_v2_bundle(PINNED_ANNOTATION_BUNDLE) is False
    assert is_v2_bundle(str(tmp_path / "does_not_exist")) is False


# ------------------------------------------------------------- and v1 is completely unaffected

def test_the_FROZEN_v1_bundle_still_admits_exactly_as_before():
    """The seam closes a door that was never open. It must not touch the one that is."""
    admission = adapt_annotation_bundle(PINNED_ANNOTATION_BUNDLE)
    assert admission.candidate_set is not None
    assert admission.candidate_set.candidates, "the frozen v1 bundle stopped admitting candidates"


def test_every_door_is_covered_by_the_seam(tmp_path):
    """`adapt_annotation_bundle` is the single choke point run_acquire, run_materialize and
    run_stage4's annotation door all pass through. One gate, no door left unguarded — a seam with a
    gap is not a seam."""
    import inspect

    from analysis import run_acquire, run_materialize, run_stage4

    for module in (run_acquire, run_materialize, run_stage4):
        src = inspect.getsource(module)
        assert "adapt_annotation_bundle" in src or "admit(" in src, (
            f"{module.__name__} reaches Stage 3 by some path that does not cross the seam")

    # ...and the choke point itself calls the gate.
    from analysis import stage3_annotation
    assert "assert_v2_admissible" in inspect.getsource(stage3_annotation.adapt_annotation_bundle)


# ------------------- the blindness: the seam only saw the adversary it had imagined

def test_the_seam_SEES_W16s_ACTUAL_FILENAME_not_only_v1s(tmp_path):
    """THE hold's finding, and the sharpest lesson in this file.

    The seam scanned `drug_annotation.json` and `manifest.json` — the names V1 emits. W16 emits
    `drug_annotation.v2.json`. So a real v2 bundle was invisible to the seam and fell straight
    through to the v1 reader: exactly the misreading the seam was built to prevent.

    And this suite passed, because it built its v2 bundle using the v1 FILENAME. A test that
    constructs the adversary in the seam's own image proves only that the seam is self-consistent.
    Discovery is now by DECLARATION, at any filename.
    """
    bundle = _v2_declaring_bundle(tmp_path, doc_name=W16_V2_DOC)
    assert not os.path.exists(os.path.join(bundle, "drug_annotation.json")), (
        "this test is vacuous if the v1 filename is still present")

    assert is_v2_bundle(bundle) is True, (
        "the seam is blind to W16's real emission filename; a real v2 bundle would reach the v1 "
        "reader")
    assert v2_documents(bundle) == {W16_V2_DOC: STAGE3_V2_SCHEMA}

    with pytest.raises(Stage3V2NotAdmissible):
        adapt_annotation_bundle(bundle)


@pytest.mark.parametrize("doc_name", ["drug_annotation.v2.json", "drug_annotation.json",
                                      "annotation.json", "stage03_drug_annotation_v2.json"])
def test_v2_is_caught_under_ANY_filename(tmp_path, doc_name):
    """Whatever W16 calls it. A contract is what a document DECLARES, never where it lives."""
    bundle = _v2_declaring_bundle(tmp_path, doc_name=doc_name)
    with pytest.raises(Stage3V2NotAdmissible):
        adapt_annotation_bundle(bundle)


def test_a_v2_bundle_that_ALSO_carries_a_v1_document_is_still_refused(tmp_path):
    """The nastiest shape: a bundle the v1 reader would happily read, with a v2 document sitting
    beside it. Any v2 declaration anywhere refuses the whole bundle — Stage 4 does not get to pick
    the document it prefers."""
    bundle = _v2_declaring_bundle(tmp_path, doc_name=W16_V2_DOC, keep_v1_doc=True)
    assert os.path.exists(os.path.join(bundle, "drug_annotation.json"))

    with pytest.raises(Stage3V2NotAdmissible) as exc:
        adapt_annotation_bundle(bundle)
    assert exc.value.code == "stage3_v2_external_verifier_not_declared"


# --------------------------------- v1's verifier may never sit in judgement on a v2 bundle

def test_the_V1_EXTERNAL_VERIFIER_is_never_run_against_a_v2_bundle(tmp_path):
    """`stage3_admission` shells out to `python -m verifier.verify_stage3` — the V1 verifier.

    Pointed at a v2 bundle it would judge the v2 contract by v1's rules, or judge nothing, and
    either way exit and let the bundle be recorded as externally verified. That is not a weaker
    gate. It is a gate that reports PASS without having looked, which is the worst possible
    outcome: the operator believes gate 2 ran.

    So the v2 verifier entry point is UNDECLARED, and the bundle is refused before admission is
    even attempted.
    """
    from analysis.stage3_v2_seam import STAGE3_V2_VERIFIER_ENTRY

    assert STAGE3_V2_VERIFIER_ENTRY is None, (
        "a v2 verifier entry point is declared. That is only legitimate if W16 PUBLISHED it; it "
        "must never default to verifier.verify_stage3, which is v1's.")

    bundle = _v2_declaring_bundle(tmp_path)
    with pytest.raises(Stage3V2NotAdmissible) as exc:
        adapt_annotation_bundle(bundle, require_external_verifier=True)

    assert exc.value.code == "stage3_v2_external_verifier_not_declared"
    assert "verify_stage3" in str(exc.value), "the refusal must name the verifier it refuses to use"


def test_the_seam_requires_a_REAL_stage2_aggregate_not_an_invented_envelope():
    """W16 currently expects an invented Stage-2 aggregate envelope. A Stage-3 bundle standing on a
    synthetic Stage-2 shape carries synthetic numbers into Stage 4 under a real bundle's name — and
    every hash downstream would be a self-consistent hash of a fiction. Stage 4 states the
    requirement rather than discovering it after the fact."""
    requires = " ".join(seam_status()["stage4_requires"]).lower()
    assert "run_release" in requires
    assert "invented aggregate envelope" in requires


# ---------------------------- the exact Stage-2 upstream contract W16 must actually consume

def test_the_stage2_upstream_contract_is_recorded_EXACTLY_as_published():
    """Verbatim, not paraphrased. W16 currently expects an INVENTED Stage-2 aggregate envelope; a
    Stage-3 bundle standing on a synthetic Stage-2 shape carries synthetic numbers into Stage 4
    under a real bundle's name, and every hash downstream is a self-consistent hash of a fiction."""
    from analysis.stage3_v2_seam import STAGE2_UPSTREAM_CONTRACT as C

    assert C["manifest_schema"] == "spot.stage02_run_manifest.v3_topology_only"
    assert set(C["manifest_carries"]) == {"bundles[]", "stage1_v3_release"}
    assert C["external_report_schema"] == "spot.stage02_run_manifest_verification.v1"

    r = C["external_report_requires"]
    assert r["verdict"] == "admit"
    assert r["n_failed"] == 0
    assert r["manifest_hashes_equal"] is True
    assert r["topology"] is r["release"] is r["admission"] is True

    # The producer may not be its own judge. This is what gate 2 IS.
    assert r["generator_is_not_verifier"] is True


def test_stage4_does_NOT_assert_v1_concepts_onto_the_v2_contract():
    """`artifact_class` and an `admits` block are v1 concepts. The v2 upstream contract does not
    carry them, and an earlier version of this seam REQUIRED artifact_class — which is precisely
    the guessing this module exists to prevent. Stage 4 does not get to invent the other side's
    fields, not even the ones it is used to."""
    from analysis.stage3_v2_seam import STAGE2_UPSTREAM_CONTRACT, STAGE4_REQUIRES_OF_V2

    assert set(STAGE2_UPSTREAM_CONTRACT["absent_by_design"]) == {"artifact_class", "admits block"}

    requires = " ".join(STAGE4_REQUIRES_OF_V2).lower()
    assert "artifact_class" not in requires, (
        "the seam requires `artifact_class` of a v2 bundle. That is a v1 field; the v2 contract "
        "does not have one, and asserting it would refuse every real v2 bundle for a field its "
        "producer never agreed to emit.")


def test_every_pin_blocker_is_NAMED_and_actionable():
    """"The seam is closed" must never collapse into a vague "not ready yet" that nobody can act
    on. Each blocker names who closes it and what it costs to leave open."""
    from analysis.stage3_v2_seam import V2_PIN_BLOCKERS

    joined = " ".join(V2_PIN_BLOCKERS)
    assert "drug_annotation.v2.json" in joined, "the filename mismatch is not named"
    assert "underscore" in joined, "the fixture's underscore variant is not named"
    assert "schema-set sha256" in joined
    assert "verifier.verify_stage3" in joined, "the wrong-verifier hazard is not named"
    assert "DISP_NON_RANKABLE_ASSERTION" in joined, "the stale fixture constant is not named"
    assert len(V2_PIN_BLOCKERS) == 4


# ------------------------- the handoff to W16 must never drift from what the code enforces

def test_the_W16_handoff_agrees_with_the_SEAM_and_claims_no_readiness():
    """A handoff that says something the code does not enforce is worse than no handoff: W16 builds
    against the document, and the document is the thing nobody re-runs.

    So the doc is checked against the seam constants, and — the part that matters — it is checked
    for NOT claiming readiness. 24 green seam tests prove the door is shut. They prove nothing about
    whether Stage 4 can READ a v2 bundle, because no real one exists to read.
    """
    import os as _os

    from analysis.stage3_v2_seam import (
        STAGE2_UPSTREAM_CONTRACT,
        STAGE3_V2_SCHEMA,
        V2_PIN_BLOCKERS,
    )

    path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                         "HANDOFF_STAGE3_V2.md")
    import re as _re

    with open(path, encoding="utf-8") as fh:
        # Whitespace-normalised: a phrase must not escape this check merely by falling across a
        # line wrap. The check is on what the handoff SAYS, not on how it happens to be typeset.
        doc = _re.sub(r"\s+", " ", fh.read())

    # every blocker the code names, the handoff names
    assert "drug_annotation.v2.json" in doc
    assert "underscore" in doc
    assert "schema-set sha256" in doc
    assert "verify_stage3" in doc, "the wrong-verifier hazard must be spelled out to W16"
    assert "DISP_NON_RANKABLE_ASSERTION" in doc
    assert len(V2_PIN_BLOCKERS) == 4

    # the exact upstream contract, not a paraphrase
    assert STAGE2_UPSTREAM_CONTRACT["manifest_schema"] in doc
    assert STAGE2_UPSTREAM_CONTRACT["external_report_schema"] in doc
    assert "generator_is_not_verifier" in doc
    assert STAGE3_V2_SCHEMA in doc

    # ...and the v1 concept that must NOT be demanded of v2
    assert "no `artifact_class`, no `admits` block" in doc

    # THE honest line: a closed door is not a working reader.
    assert "is not readiness" in doc
    assert "A skip is not a pass" in doc
