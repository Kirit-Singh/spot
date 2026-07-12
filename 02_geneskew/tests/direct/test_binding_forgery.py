"""RESEALED forgeries: what run_id binds is worthless unless something says what it IS.

Every claim in the run binding is written by the producer and then hashed by the
producer. So ``run_binding_sha256 == sha256(run_binding)`` proves exactly one thing —
that the run hashed what it hashed. It is not a check on the CONTENT, and it never was.

A forger who edits the binding and RESEALS it (recompute the hash, recompute run_id,
rename the output directory) leaves a run that is perfectly self-consistent. Every hash
verifies. And it can be claiming:

  * a different METHOD, at a different version, computing a different formula;
  * an inverted arm formula, so every rank in that arm is upside down;
  * a loosened eligibility threshold, so the screen has rows it did not earn;
  * an evidence domain the manifest was never matched against — or NO domain at all,
    which the old check permitted outright by allowing ``None``;
  * a scope count, or a support-estimate count, that no one ever counted.

The last is the sharpest. Three copies of ``999999`` — in the support contract, in the
run binding, and in the evidence-domain block — agree with each other perfectly, and
with the release not at all. Consistency between two copies of a number written by one
producer is not evidence for the number.

Every test below therefore RESEALS. Each asserts the NAMED check that must fire, and
asserts that ``run_binding_sha256 is the hash of the binding content`` did NOT fire:
if the refusal came from a broken hash, it would prove nothing about the rule under test
and would keep passing if that rule were deleted.
"""
from __future__ import annotations

import json
import os

import pytest
from test_source_replay import run_and_verify

HASH_CHECK = "run_binding_sha256 is the hash of the binding content"
ID_CHECK = "run_id is the binding hash and names the output directory"


def reseal(args, mutate):
    """Forge the binding, then make the run perfectly self-consistent again.

    Recomputes the binding hash with the VERIFIER's own content hash (the independent
    restatement), rewrites run_id, and renames the output directory to match — so the
    run that reaches the verifier is exactly what an honest producer of this (forged)
    binding would have emitted. Returns the new run directory.
    """
    from direct import verify_rules as R

    path = os.path.join(args.out_dir, "provenance.json")
    with open(path) as fh:
        prov = json.load(fh)

    mutate(prov)

    full = R.content_sha256(prov["run_binding"])
    prov["run_binding_sha256"] = full
    prov["run_id"] = full[:16]
    with open(path, "w") as fh:
        json.dump(prov, fh, indent=2, sort_keys=True)

    new_dir = os.path.join(os.path.dirname(args.out_dir.rstrip("/")), full[:16])
    os.rename(args.out_dir, new_dir)
    return new_dir


def failed_checks(args, run_dir=None):
    from direct.verify_run import Report, reconstruct
    rep = Report()
    reconstruct(run_dir or args.out_dir, os.path.dirname(args.selection), rep,
                strict=False)
    return [name for name, _detail in rep.failures]


def attack(synthetic_run, mutate):
    """Build an honest run, forge + reseal it, and report what the verifier refused."""
    args = run_and_verify(synthetic_run())
    run_dir = reseal(args, mutate)
    return failed_checks(args, run_dir)


def assert_resealed(failed, expected_check):
    """The named rule fired, and it was NOT a hash mismatch that did the work."""
    assert expected_check in failed, (
        f"{expected_check!r} did not fire; failures were {failed}")
    assert HASH_CHECK not in failed, (
        "the reseal did not take — the refusal came from a broken binding hash, which "
        "proves nothing about the rule under test")
    assert ID_CHECK not in failed, "the run_id/dir reseal did not take"


def test_the_reseal_itself_is_sound(synthetic_run):
    """A forgery harness that cannot forge would make every test below vacuous.

    Reseal a NO-OP mutation: the run must still verify completely clean. If this fails,
    the harness is breaking something incidental and the 'named check fired' assertions
    downstream would be meaningless.
    """
    failed = attack(synthetic_run, lambda prov: None)
    assert failed == [], f"the no-op reseal broke the run: {failed}"


# --------------------------------------------------------------------------- #
# THE METHOD. Resealable, therefore unverified — until something restates it.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field,forged,check", [
    ("method_id", "spot.stage02.direct.balanced_skew",
     "run_id binds the exact method id"),
    ("method_version", "stage2-direct-v4-combined",
     "run_id binds the exact method version"),
    ("formula_id", "spot.stage02.direct.formula.unmasked.v0",
     "run_id binds the exact formula id"),
    ("effect_layer_primary", "zscore",
     "run_id binds the exact effect layers"),
    ("rank_tie_break", "n_cells_descending",
     "run_id binds the exact rank policy"),
    ("rank_dtype", "float64",
     "run_id binds the exact rank policy"),
])
def test_a_resealed_forged_method_field_is_refused_BY_NAME(synthetic_run, field,
                                                           forged, check):
    """Each of these survived a reseal and was never once compared to anything."""
    def mutate(prov):
        prov["run_binding"]["stage2_method"][field] = forged

    assert_resealed(attack(synthetic_run, mutate), check)


def test_a_resealed_INVERTED_arm_formula_is_refused(synthetic_run):
    """Flip the sign on away_from_A and every rank in that arm inverts.

    The scores and ranks in the emitted table are recomputed by the verifier and would
    still match the EMITTED numbers — the forgery is in what the run says it DID, and
    the run says it did something that produces a different table than the one it
    shipped. Nothing compared the claim to the spec, so nothing noticed.
    """
    def mutate(prov):
        prov["run_binding"]["stage2_method"]["arm_formula"]["away_from_A"] = \
            "sign_A * delta_A"

    assert_resealed(attack(synthetic_run, mutate),
                    "run_id binds BOTH arm formulas, in the right sense")


def test_a_resealed_SWAPPED_arm_rank_column_is_refused(synthetic_run):
    """Each arm's rank belongs to that arm. Swapping the columns swaps the science."""
    def mutate(prov):
        m = prov["run_binding"]["stage2_method"]
        m["arm_rank_column"] = {"away_from_A": "rank_toward_B",
                                "toward_B": "rank_away_from_A"}

    assert_resealed(attack(synthetic_run, mutate),
                    "run_id binds each arm's own rank and evaluable column")


def test_a_resealed_PERMITTED_combined_objective_is_refused(synthetic_run):
    """The single boolean the entire two-arm design exists to hold at False."""
    def mutate(prov):
        prov["run_binding"]["stage2_method"]["combined_objective_permitted"] = True

    assert_resealed(
        attack(synthetic_run, mutate),
        "the bound method FORBIDS a combined objective and a headline arm")


def test_a_resealed_PERMITTED_headline_arm_is_refused(synthetic_run):
    def mutate(prov):
        prov["run_binding"]["stage2_method"]["headline_arm_permitted"] = True

    assert_resealed(
        attack(synthetic_run, mutate),
        "the bound method FORBIDS a combined objective and a headline arm")


def test_an_UNRESTATED_extra_method_field_is_refused(synthetic_run):
    """A field nobody restated is a claim nobody checked. An allowlist, not a denylist."""
    def mutate(prov):
        prov["run_binding"]["stage2_method"]["primary_arm"] = "away_from_A"

    assert_resealed(attack(synthetic_run, mutate),
                    "the bound method block is EXACTLY the restated method")


def test_a_forged_method_in_PROVENANCE_is_refused_even_when_the_BINDING_is_honest(
        synthetic_run):
    """The copy a human reads is held to the same standard as the copy run_id hashes."""
    def mutate(prov):
        prov["method"]["method_version"] = "stage2-direct-v9-better"

    assert_resealed(attack(synthetic_run, mutate),
                    "the method in PROVENANCE is the same method run_id bound")


def test_a_forged_formula_EXPRESSION_is_refused(synthetic_run):
    """The id and the expression must agree; an id is only a pointer to a formula."""
    def mutate(prov):
        prov["method"]["formula_expr"] = "delta_p(X) = mean(P_p) - mean(C_p)"

    assert_resealed(attack(synthetic_run, mutate),
                    "the emitted formula EXPRESSION is the restated formula")


# --------------------------------------------------------------------------- #
# THE ELIGIBILITY / EVIDENCE-TIER POLICY. Numbers that move rows.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field,forged", [
    ("n_cells_min", 1),                    # underpowered targets become evaluable
    ("min_surviving_control", 1),          # a 1-gene control mean is a control mean
    ("min_surviving_panel", 0),
    ("min_guides_for_replication", 1),     # one guide "replicates"
    ("mask_window_kb", 0),                 # neighbours stop being masked
    ("sign_eps", 1.0),                     # every real effect becomes "no direction"
])
def test_a_resealed_LOOSENED_threshold_is_refused_by_name(synthetic_run, field,
                                                          forged):
    """Loosen a threshold, reseal, and the screen grows rows it did not earn."""
    def mutate(prov):
        prov["run_binding"]["stage2_eligibility_policy"][field] = forged

    assert_resealed(attack(synthetic_run, mutate),
                    "run_id binds the exact evaluability thresholds")


def test_a_resealed_policy_that_PERMITS_guide_identity_inference_is_refused(
        synthetic_run):
    """The whole guide-identity contract, as one boolean."""
    def mutate(prov):
        p = prov["run_binding"]["stage2_eligibility_policy"]
        p["guide_identity_inference_permitted"] = True

    assert_resealed(attack(synthetic_run, mutate),
                    "the bound policy forbids inferring a guide identity")


def test_a_resealed_policy_that_SHARES_support_between_arms_is_refused(synthetic_run):
    def mutate(prov):
        p = prov["run_binding"]["stage2_eligibility_policy"]
        p["arm_support_is_never_shared"] = False

    assert_resealed(
        attack(synthetic_run, mutate),
        "the bound policy keeps the arms independent and never shares support")


def test_a_resealed_policy_that_makes_a_MISSING_measurement_favourable_is_refused(
        synthetic_run):
    """A missing QC measurement is not a passing QC measurement."""
    def mutate(prov):
        p = prov["run_binding"]["stage2_eligibility_policy"]
        p["missing_qc_is_non_evaluable"] = False

    assert_resealed(
        attack(synthetic_run, mutate),
        "the bound policy states base QC is pre-outcome and that a missing "
        "measurement is NOT favourable")


def test_a_resealed_policy_that_INVERTS_the_rank_direction_is_refused(synthetic_run):
    """Ascending ranks put the least-moved target at rank 1."""
    def mutate(prov):
        p = prov["run_binding"]["stage2_eligibility_policy"]
        p["rank_direction"] = "ascending"

    assert_resealed(
        attack(synthetic_run, mutate),
        "the bound policy states the full rank contract, including direction")


def test_a_resealed_policy_with_a_forged_POLICY_ID_is_refused(synthetic_run):
    def mutate(prov):
        p = prov["run_binding"]["stage2_eligibility_policy"]
        p["policy_id"] = "spot.stage02.direct.two_arm_eligibility.v2"

    assert_resealed(attack(synthetic_run, mutate),
                    "run_id binds the exact eligibility policy id")


def test_a_DROPPED_policy_field_is_refused(synthetic_run):
    """A claim that stops being bound is a claim that stopped being made."""
    def mutate(prov):
        prov["run_binding"]["stage2_eligibility_policy"].pop("sign_eps")

    assert_resealed(attack(synthetic_run, mutate),
                    "the bound eligibility policy is EXACTLY the restated policy")


# --------------------------------------------------------------------------- #
# THE EVIDENCE DOMAIN: no copy may be missing, and no count may be invented.
# --------------------------------------------------------------------------- #
def test_a_bound_manifest_with_NO_evidence_domain_is_refused(synthetic_run):
    """The cheapest forgery there was: DELETE the field.

    The old rule was ``gm_domain in (None, EVIDENCE_DOMAIN_ID)``. A manifest that
    declared no domain at all sailed through the check whose entire job was to pin the
    domain — absence was in the allowed set. A manifest that names no domain has not
    been matched against one.
    """
    def mutate(prov):
        prov["run_binding"]["guide_manifest"].pop("evidence_domain")

    assert_resealed(
        attack(synthetic_run, mutate),
        "the bound MANIFEST declares the frozen evidence domain, explicitly")


def test_a_bound_manifest_declaring_a_DIFFERENT_domain_is_refused(synthetic_run):
    def mutate(prov):
        prov["run_binding"]["guide_manifest"]["evidence_domain"] = \
            "spot.stage02.direct.evidence_domain.selected_condition_all_estimates.v1"

    assert_resealed(
        attack(synthetic_run, mutate),
        "the bound MANIFEST declares the frozen evidence domain, explicitly")


def test_a_forged_manifest_SCOPE_COUNT_is_caught_by_the_raw_release(synthetic_run):
    """Every copy of the count is checked against the RAW DE obs, not against a sibling."""
    def mutate(prov):
        prov["run_binding"]["guide_manifest"]["n_scopes"] = 999999

    assert_resealed(
        attack(synthetic_run, mutate),
        "the scope count in the bound manifest IS the count the raw DE release ships")


def test_a_forged_manifest_scope_count_in_the_DOMAIN_BLOCK_is_caught(synthetic_run):
    """The domain block carries its own copy of the manifest's scope count."""
    def mutate(prov):
        prov["run_binding"]["stage2_evidence_domain"]["manifest_n_scopes"] = 999999
        prov["evidence_domain"]["manifest_n_scopes"] = 999999

    failed = attack(synthetic_run, mutate)
    assert ("the scope count in the run binding's manifest scope count IS the count "
            "the raw DE release ships") in failed
    assert ("the scope count in provenance's manifest scope count IS the count the "
            "raw DE release ships") in failed
    assert HASH_CHECK not in failed


# --------------------------------------------------------------------------- #
# THE SUPPORT CONTRACT: mutually consistent counts nobody counted.
# --------------------------------------------------------------------------- #
def _forge_support_counts(prov, n):
    """Set EVERY copy of every observed-support count to the same lie.

    This is the point of the attack: the forgery is internally perfect. The contract
    agrees with the binding, the binding agrees with the domain block, and every hash
    verifies. Only the release disagrees, and nothing was asking it.
    """
    for block in (prov["support_contract"],
                  prov["run_binding"]["stage2_support_contract"]):
        block["n_support_estimates_observed"] = n
        block["n_guide_estimates_observed"] = n
        block["n_donor_pair_estimates_observed"] = n
    for block in (prov["evidence_domain"],
                  prov["run_binding"]["stage2_evidence_domain"]):
        block["n_support_estimates_observed"] = n


def test_mutually_consistent_FORGED_support_counts_are_refused(synthetic_run):
    """999,999 guide estimates, 999,999 donor estimates, and every copy agrees."""
    failed = attack(synthetic_run, lambda prov: _forge_support_counts(prov, 999999))

    assert HASH_CHECK not in failed
    for where in ("the support contract", "the run binding"):
        assert (f"{where} counts the guide support estimates the release actually "
                "ships") in failed
        assert (f"{where} counts the donor-pair support estimates the release "
                "actually ships") in failed
        assert (f"{where} counts the support estimates the release actually ships"
                ) in failed
    assert ("the observed support-estimate count in the run binding IS the count the "
            "release ships") in failed
    assert ("the observed support-estimate count in provenance IS the count the "
            "release ships") in failed


def test_a_forged_support_MODALITY_LIST_is_refused(synthetic_run):
    """Naming modalities the release does not ship is the same lie as counting them."""
    def mutate(prov):
        for block in (prov["support_contract"],
                      prov["run_binding"]["stage2_support_contract"]):
            block["guide_modalities_observed"] = ["guide_1", "guide_2", "guide_3"]

    failed = attack(synthetic_run, mutate)
    assert HASH_CHECK not in failed
    for where in ("the support contract", "the run binding"):
        assert (f"{where} names the support modalities the release actually ships"
                ) in failed


def test_an_UNDERCOUNTED_support_total_is_refused_too(synthetic_run):
    """Not only inflation: silently dropping released support estimates also lies."""
    def mutate(prov):
        for block in (prov["support_contract"],
                      prov["run_binding"]["stage2_support_contract"]):
            block["n_support_estimates_observed"] -= 1

    failed = attack(synthetic_run, mutate)
    assert HASH_CHECK not in failed
    assert ("the support contract counts the support estimates the release actually "
            "ships") in failed


# --------------------------------------------------------------------------- #
# THE RETIRED PINNED GATE, if a run ever emitted one again.
# --------------------------------------------------------------------------- #
def test_a_run_presenting_the_RETIRED_pinned_gate_is_refused_by_name(synthetic_run):
    """The generator cannot produce this. The verifier must still refuse to read it."""
    def mutate(prov):
        prov["run_binding"]["stage2_release_gate"] = {
            "gate_id": "spot.stage02.direct.release_gate.v1",
            "lane": "production", "strict_replay_required": True,
            "state": "pinned_strict_preflight_go", "strict_replay_ran": False,
            "strict_preflight_sha256": "a" * 64,
        }
        prov["run_binding"]["lane"] = "production"

    failed = attack(synthetic_run, mutate)
    assert "the run does not stand on the RETIRED pinned-preflight gate" in failed
    assert HASH_CHECK not in failed
