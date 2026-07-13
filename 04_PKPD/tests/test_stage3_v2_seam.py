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
import shutil

import pytest

from analysis.stage3_annotation import adapt_annotation_bundle
from analysis.stage3_v2_seam import (
    STAGE3_V2_SCHEMA,
    STAGE3_V2_SCHEMA_SET_SHA256,
    Stage3V2NotAdmissible,
    assert_v2_admissible,
    is_v2_bundle,
    seam_status,
)
from test_stage3_handoff_and_integrity import PINNED_ANNOTATION_BUNDLE


def _v2_declaring_bundle(tmp_path):
    """A real v1 bundle, relabelled to DECLARE v2 — the exact shape that must not sneak through.

    Deliberately a bundle whose tables the v1 reader CAN read: if the seam only caught v2 bundles
    that were structurally broken, it would catch nothing that mattered. The whole risk is the v2
    bundle that parses.
    """
    dst = tmp_path / "s3_v2_declaring"
    shutil.copytree(PINNED_ANNOTATION_BUNDLE, dst)

    path = dst / "drug_annotation.json"
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["schema_version"] = STAGE3_V2_SCHEMA
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
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

    assert exc.value.code == "stage3_v2_contract_not_pinned"
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
    for required in ("verify_stage3", "artifact_class", "immutable candidate identifier",
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
