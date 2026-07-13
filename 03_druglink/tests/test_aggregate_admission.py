"""Aggregate admission: TWO artifacts, TWO lanes, or nothing.

Frozen by independent report `a12f7eee`. The producer's release is EVIDENCE; only W11's
envelope is a VERDICT. These hold that line at every place it could quietly give way.

PROVISIONAL: W5 and W11 are both mid-flight, so these run on spec-shaped documents rather
than shipped bytes. The rules are the point — they are what the shipped bytes will be
checked against, and writing them afterwards would let the bytes decide what is true.
"""
from __future__ import annotations

import copy

import pytest

from druglink import aggregate_admission as agg

RAW = "a" * 64
CANON = "b" * 64
PAIRS = ("Rest|Stim8hr", "Rest|Stim48hr", "Stim8hr|Rest",
         "Stim8hr|Stim48hr", "Stim48hr|Rest", "Stim48hr|Stim8hr")


def _release(**over):
    rel = {
        "raw_sha256": RAW,
        "canonical_sha256": CANON,
        "external_verification": {"status": agg.PENDING},
        "bundles": [{"bundle_key": f"temporal|{p}", "raw_sha256": f"{i}" * 64,
                     "canonical_sha256": f"{i}" * 64}
                    for i, p in enumerate(PAIRS)],
        "stage2_inputs": {k: {"sha256": f"{i}" * 64}
                          for i, k in enumerate(agg.STAGE2_INPUT_KEYS)},
    }
    rel.update(over)
    return rel


def _envelope(**over):
    env = {"verifier_id": "spot.stage02.temporal.arm.independent_verifier.v1",
           "verdict": agg.ADMIT,
           "admits": {"raw_sha256": RAW, "canonical_sha256": CANON}}
    env.update(over)
    return env


# --------------------------------------------------------------------------- #
# The happy path, and then every way it could rot.
# --------------------------------------------------------------------------- #
def test_both_artifacts_agreeing_admits_the_release():
    got = agg.admit_release(producer_release=_release(),
                            independent_envelope=_envelope())
    assert got["admission_status"] == "externally_admitted"
    assert got["topology_complete"] is True
    assert got["n_bundles"] == 6
    assert got["n_logical_arms"] == 120
    assert got["producer_raw_sha256"] == RAW
    assert got["verdict"] == agg.ADMIT


# --------------------------------------------------------------------------- #
# The producer never admits itself. This is the whole file.
# --------------------------------------------------------------------------- #
def test_the_producer_release_ALONE_never_admits_anything():
    """It says `pending`. Reading that as `verified` is the bug, in one line."""
    with pytest.raises(agg.SelfAdmissionRefused, match="never admits anything"):
        agg.admit_release(producer_release=_release(), independent_envelope=None)


@pytest.mark.parametrize("claim", sorted(agg.PRODUCER_SELF_CLAIMS))
def test_every_producer_self_check_claim_is_refused_by_name(claim):
    with pytest.raises(agg.SelfAdmissionRefused, match="self-verification claims"):
        agg.check_producer_release(_release(**{claim: True}))


def test_a_producer_that_moved_itself_past_pending_is_refused():
    """W5 does not get to write `admit` in its own external_verification block."""
    bad = _release(external_verification={"status": "admit"})
    with pytest.raises(agg.AggregateAdmissionError, match="does not get to move itself"):
        agg.check_producer_release(bad)


def test_a_release_with_no_external_verification_block_is_refused():
    bad = _release()
    del bad["external_verification"]
    with pytest.raises(agg.AggregateAdmissionError, match="waiting to be verified"):
        agg.check_producer_release(bad)


def test_a_release_that_declares_its_own_topology_complete_is_refused():
    with pytest.raises(agg.SelfAdmissionRefused, match="DECLARES topology_complete"):
        agg.admit_release(producer_release=_release(topology_complete=True),
                          independent_envelope=_envelope())


# --------------------------------------------------------------------------- #
# The envelope must bind THESE bytes.
# --------------------------------------------------------------------------- #
def test_an_envelope_admitting_a_DIFFERENT_release_is_refused():
    stale = _envelope(admits={"raw_sha256": "f" * 64, "canonical_sha256": CANON})
    with pytest.raises(agg.AggregateAdmissionError, match="a DIFFERENT release"):
        agg.admit_release(producer_release=_release(), independent_envelope=stale)


def test_both_hashes_must_match_not_just_one():
    """Raw alone misses a re-serialisation; canonical alone lets the file differ."""
    for field in ("raw_sha256", "canonical_sha256"):
        bad = _envelope()
        bad["admits"][field] = "e" * 64
        with pytest.raises(agg.AggregateAdmissionError, match="a DIFFERENT release"):
            agg.admit_release(producer_release=_release(), independent_envelope=bad)


def test_an_envelope_binding_no_bytes_at_all_is_refused():
    with pytest.raises(agg.AggregateAdmissionError, match="opinion about some other"):
        agg.admit_release(producer_release=_release(),
                          independent_envelope=_envelope(admits={}))


def test_a_non_independent_verifier_cannot_admit():
    """The fourth occurrence, refused by name."""
    bad = _envelope(verifier_id="spot.stage02.temporal_arm.verifier.v1")
    with pytest.raises(agg.SelfAdmissionRefused, match="not an INDEPENDENT verifier"):
        agg.admit_release(producer_release=_release(), independent_envelope=bad)


def test_a_reject_verdict_is_not_an_admit():
    with pytest.raises(agg.AggregateAdmissionError, match="not 'admit'"):
        agg.admit_release(producer_release=_release(),
                          independent_envelope=_envelope(verdict="reject"))


# --------------------------------------------------------------------------- #
# The six-bundle inventory. Exact, distinct, addressed.
# --------------------------------------------------------------------------- #
def test_a_partial_inventory_is_never_admissible():
    short = _release()
    short["bundles"] = short["bundles"][:5]
    with pytest.raises(agg.AggregateAdmissionError, match="partial release"):
        agg.check_producer_release(short)


def test_a_duplicate_bundle_cannot_fill_a_missing_slot():
    dup = _release()
    dup["bundles"][5] = copy.deepcopy(dup["bundles"][0])
    with pytest.raises(agg.AggregateAdmissionError, match="six DISTINCT ordered pairs"):
        agg.check_producer_release(dup)


def test_every_bundle_must_be_content_addressed():
    bad = _release()
    del bad["bundles"][2]["canonical_sha256"]
    with pytest.raises(agg.AggregateAdmissionError, match="not content-addressed"):
        agg.check_producer_release(bad)


def test_the_release_itself_must_be_content_addressed():
    bad = _release()
    del bad["canonical_sha256"]
    with pytest.raises(agg.AggregateAdmissionError, match="CONTENT-ADDRESSED"):
        agg.check_producer_release(bad)


# --------------------------------------------------------------------------- #
# stage2_inputs is a FIXED KEYED OBJECT.
# --------------------------------------------------------------------------- #
def test_stage2_inputs_as_a_generic_role_list_is_refused():
    bad = _release(stage2_inputs=[{"role": "de_stats", "sha256": "1" * 64}])
    with pytest.raises(agg.AggregateAdmissionError, match="fixed KEYED OBJECT"):
        agg.check_stage2_inputs(bad)


@pytest.mark.parametrize("key", agg.STAGE2_INPUT_KEYS)
def test_a_missing_stage2_input_is_refused(key):
    bad = _release()
    del bad["stage2_inputs"][key]
    with pytest.raises(agg.AggregateAdmissionError, match="missing"):
        agg.check_stage2_inputs(bad)


def test_an_unknown_stage2_input_key_is_refused():
    bad = _release()
    bad["stage2_inputs"]["mystery_input"] = {"sha256": "9" * 64}
    with pytest.raises(agg.AggregateAdmissionError, match="unknown keys"):
        agg.check_stage2_inputs(bad)


def test_every_stage2_input_must_bind_its_bytes():
    bad = _release()
    bad["stage2_inputs"]["de_stats"] = {"path": "/x/de.h5ad"}      # no sha256
    with pytest.raises(agg.AggregateAdmissionError, match="bind its bytes"):
        agg.check_stage2_inputs(bad)


def test_the_input_key_set_is_fixed_and_not_positional():
    """A list would let two inputs swap places and still validate. A key cannot."""
    assert isinstance(agg.STAGE2_INPUT_KEYS, tuple)
    admitted = agg.admit_release(producer_release=_release(),
                                 independent_envelope=_envelope())
    assert set(admitted["stage2_inputs"]) == set(agg.STAGE2_INPUT_KEYS)
