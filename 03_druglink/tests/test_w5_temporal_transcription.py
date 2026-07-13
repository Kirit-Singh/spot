"""The transcribed W5 temporal arm bundle — REAL emitted bytes, not a hand-authored shape.

`tests/fixtures_w5_temporal/` is the byte-for-byte output of W5's committed producer
(`agent/stage2-temporal-arms` @ `cc82599`, 148 tests green), emitted through its own
`arm_emit.emit_bundle`. It was not written by Stage 3. That matters: a fixture Stage 3
authored to match its own expectations would prove only that Stage 3 agrees with itself,
and every earlier memo this lane wrote about the temporal contract (parquet files, absent
unrankable rows) was wrong precisely because it was written from assumption rather than
from bytes.

These tests do two things and stop:

  1. **Pin the transcription.** If the fixture drifts from what W5 shipped, say so — with
     the hash, not a vague failure.
  2. **Prove the JOIN Stage-3 v2 depends on** — arm records → base_records on the immutable
     `base_key`/`target_id`, never on a symbol — and that the identity, modality and
     evidence fields Stage 3 needs are actually present in the shipped bytes.

**Stage-3 v2 is NOT finished here.** The loader is not wired into `run_stage3`, no v2 schema
is finalized, and no Stage-4 re-pin is issued. That waits on **W11 independently admitting
`cc82599`**, after which this fixture is re-verified against the W11-admitted bytes.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "fixtures_w5_temporal")
BUNDLE_DIR = os.path.join(ROOT, "FixRest__to__FixStim48")

W5_COMMIT = "cc82599"
FIXTURE_SET_SHA256 = \
    "d2d7aaaf68cdbf9143b453e568b157a2ccc80ea1d5804876f75cf9383d351ed2"

# The producer's own contract ids, read from the shipped bytes — not restated from code.
BUNDLE_SCHEMA = "spot.stage02_temporal_arm_bundle.v1"
MODALITY = "CRISPRi_knockdown"
MODULATION_RULE = "spot.stage02.temporal.arm.desired_target_modulation.v1"

# W5's closed modulation vocabulary and its Stage-3 meaning.
SUPPORTS_INHIBITION = "supports_target_inhibition"
OPPOSED_NEEDS_ACTIVATION = "opposed_would_require_target_activation"
NO_RESPONSE = "no_directional_response"
NOT_EVALUABLE = "not_evaluable"


@pytest.fixture(scope="module")
def transcription():
    with open(os.path.join(ROOT, "TRANSCRIPTION.json"), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def bundle():
    with open(os.path.join(BUNDLE_DIR, "arm_bundle.json"), encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# 1. The transcription is what W5 shipped.
# --------------------------------------------------------------------------- #
def test_the_fixture_is_byte_identical_to_what_W5_emitted(transcription):
    files = {}
    for dp, _, fs in os.walk(BUNDLE_DIR):
        for f in sorted(fs):
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, BUNDLE_DIR)
            with open(p, "rb") as fh:
                files[rel] = hashlib.sha256(fh.read()).hexdigest()

    assert files == transcription["files"], "the transcribed bytes drifted from W5's"

    h = hashlib.sha256()
    for k in sorted(files):
        h.update(k.encode())
        h.update(b"\0")
        h.update(files[k].encode())
        h.update(b"\n")
    assert h.hexdigest() == FIXTURE_SET_SHA256
    assert transcription["transcribed_from"]["commit"] == W5_COMMIT


def test_the_native_file_set_is_present(transcription):
    """W5's native contract — not the legacy `temporal_arm_*` names, not parquet."""
    names = set(transcription["files"])
    assert "arm_bundle.json" in names
    assert "temporal_provenance.json" in names
    assert "temporal_verification.json" in names
    assert any(n.startswith("rankings/") for n in names)
    assert not [n for n in names if n.endswith(".parquet")], (
        "the temporal contract is JSON; the earlier parquet memo was wrong")


def test_every_ranking_file_is_on_disk_and_matches_its_bound_hash(bundle):
    """The rank stands on bytes, and the bytes are there. (W5 bound these before it
    emitted them; that gap is closed at cc82599 — so verify it, do not assume it.)"""
    for arm in bundle["arms"]:
        binding = arm["ranking"]
        path = os.path.join(BUNDLE_DIR, binding["path"])
        assert os.path.exists(path), f"{binding['path']} is bound but not shipped"
        with open(path, "rb") as fh:
            raw = fh.read()
        assert hashlib.sha256(raw).hexdigest() == binding["raw_sha256"]


# --------------------------------------------------------------------------- #
# 2. The JOIN Stage-3 v2 depends on.
# --------------------------------------------------------------------------- #
def test_every_arm_record_joins_to_a_real_base_record_on_the_IMMUTABLE_key(bundle):
    by_base = {b["base_key"]: b for b in bundle["base_records"]}
    assert by_base, "the bundle ships base_records"

    n = 0
    for arm in bundle["arms"]:
        for rec in arm["records"]:
            base = by_base.get(rec["base_key"])
            assert base is not None, f"dangling base_key {rec['base_key']!r}"
            # target_id travels too, so the join is CHECKABLE rather than trusted.
            assert base["target_id"] == rec["target_id"]
            n += 1
    assert n > 0


def test_the_join_is_never_on_a_symbol(bundle):
    """Symbols are ambiguous and mutable. They are carried for humans, never joined on."""
    arm_record_keys = {k for arm in bundle["arms"] for r in arm["records"] for k in r}
    assert "target_symbol" not in arm_record_keys, (
        "an arm record must not carry a symbol — it would invite a lossy symbol join")
    assert {"base_key", "target_id"} <= arm_record_keys


def test_base_records_carry_the_identity_and_evidence_stage3_needs(bundle):
    base = bundle["base_records"][0]
    for field in ("base_key", "program_id", "target_id", "target_symbol",
                  "target_ensembl", "target_id_namespace", "temporal_status",
                  "evaluable", "base_delta", "perturbation_modality"):
        assert field in base, f"base_record is missing {field!r}"

    # released_estimate_id + QC tier, per endpoint.
    for end in ("from", "to"):
        assert f"{end}_released_estimate_id" in base
        assert f"{end}_base_qc_state" in base

    assert base["perturbation_modality"] == MODALITY


def test_identity_is_normalised_not_duplicated(bundle):
    """Identity lives in base_records ONCE. Duplicating it per arm is 20 chances to drift."""
    arm_keys_seen = {k for arm in bundle["arms"] for r in arm["records"] for k in r}
    for identity in ("target_symbol", "target_ensembl", "target_id_namespace"):
        assert identity not in arm_keys_seen


# --------------------------------------------------------------------------- #
# 3. Modality + orientation, bound in the SHIPPED BYTES (not read from W5's code).
# --------------------------------------------------------------------------- #
def test_the_modality_and_modulation_rule_are_bound_in_the_bytes(bundle):
    pert = bundle["perturbation"]
    assert pert["perturbation_modality"] == MODALITY
    assert pert["modulation_rule_id"] == MODULATION_RULE
    assert set(pert["modulations"]) == {NOT_EVALUABLE, SUPPORTS_INHIBITION,
                                        OPPOSED_NEEDS_ACTIVATION, NO_RESPONSE}


def test_the_orientation_is_the_one_stage3_requires(bundle):
    """positive -> inhibition · negative -> opposed/activation-needed · null -> not_evaluable.

    Re-derived here from the arm VALUES in the shipped bytes, so this is a check on the
    producer's orientation and not a restatement of its label.
    """
    seen = set()
    for arm in bundle["arms"]:
        for r in arm["records"]:
            mod, val, evaluable = (r["desired_target_modulation"], r["arm_value"],
                                   r["evaluable"])
            seen.add(mod)
            if not evaluable or val is None:
                assert mod == NOT_EVALUABLE
            elif val > 0:
                assert mod == SUPPORTS_INHIBITION, (
                    "a knockdown that moved the program the DESIRED way supports "
                    "INHIBITING the target")
            elif val < 0:
                assert mod == OPPOSED_NEEDS_ACTIVATION, (
                    "a negative response is OPPOSED — achieving the desired change would "
                    "need ACTIVATION, which this screen cannot speak to")
            else:
                assert mod == NO_RESPONSE
    assert seen <= {NOT_EVALUABLE, SUPPORTS_INHIBITION, OPPOSED_NEEDS_ACTIVATION,
                    NO_RESPONSE}


def test_pharmacologic_reversibility_is_explicitly_DISCLAIMED_in_the_bytes(bundle):
    """`opposed` says what would be NEEDED, never that a drug could do it.

    W5 does not merely avoid the claim — it ships the DENIAL, so a consumer can verify the
    prohibition instead of inferring it from an absence. (My first draft of this test hunted
    for the substring "reversib" and failed on `pharmacologic_reversibility_assumed: false`
    — the honest declaration read as the thing it forbids. Assert the field, not the word.)
    """
    pert = bundle["perturbation"]
    assert pert["pharmacologic_reversibility_assumed"] is False
    assert pert["is_suggestive_not_confirmatory"] is True

    # The orientation map, stated in the bytes rather than left to a consumer to guess.
    assert pert["positive_response_to_knockdown"] == SUPPORTS_INHIBITION
    assert pert["negative_response_to_knockdown"] == OPPOSED_NEEDS_ACTIVATION
    assert pert["null_or_unresolved_response"] == NOT_EVALUABLE

    # And nothing anywhere claims an activator is actually available.
    blob = json.dumps(bundle).lower()
    for claim in ("activator_available", "druggable_activation", "can_be_activated"):
        assert claim not in blob


def test_the_bundle_computes_no_p_or_q(bundle):
    est = bundle["estimand"]
    assert est["inference_status"] == "not_calibrated"
    blob = json.dumps(bundle).lower()
    for banned in ("\"p_value\"", "\"q_value\"", "\"fdr\"", "\"padj\""):
        assert banned not in blob


# --------------------------------------------------------------------------- #
# 4. Retained rows, and the shape of the contract.
# --------------------------------------------------------------------------- #
def test_unrankable_targets_are_RETAINED_with_a_null_rank(bundle):
    """The correction that mattered most: an unranked target is a STATE, not an absence."""
    for arm in bundle["arms"]:
        assert len(arm["records"]) == arm["n_targets"]
        ranked = [r for r in arm["records"] if r["rank"] is not None]
        assert len(ranked) == arm["n_ranked"]
        # every target survives, ranked or not
        assert arm["n_targets"] >= arm["n_ranked"]


def test_the_bundle_declares_the_contract_facts_stage3_relies_on(bundle):
    assert bundle["schema_version"] == BUNDLE_SCHEMA
    assert bundle["analysis_mode"] == "temporal_cross_condition"
    assert bundle["lane"] == "temporal"
    assert bundle["bundle_is_pair_agnostic"] is True
    assert bundle["bundle_carries_role_or_pole"] is False, (
        "an arm is keyed on desired_change; a pole/role in the bundle would fuse two "
        "opposite perturbations under one key")
    assert bundle["context"]["from_condition"] and bundle["context"]["to_condition"]
