"""The independent verifier for a Direct all-arm bundle: ADMIT the valid, REFUSE the rest.

Every attack here mutates a REAL bundle emitted by the producer and RESEALS whatever the
mutation would obviously break — because a forgery that fails on an arithmetic slip proves
nothing. What must catch these is the re-derivation, not a stale hash.

The M4b case is the load-bearing one: a coherently sign-flipped arm configuration — the one
the pair-bound verifier rejected at 152/153 over a DISPLAY label — must ADMIT here, with no
joint fields anywhere in the artifact.
"""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "analysis", "direct"))

import fixtures_direct as F  # noqa: E402
import verify_arm_bundle as VB  # noqa: E402
import verify_arm_rules as AR  # noqa: E402
import verify_arm_science as S  # noqa: E402
import verify_arm_view as AV  # noqa: E402

# The PRODUCER. The TEST HARNESS drives it to emit a real bundle to attack; the VERIFIER
# never imports it, and gate_independence proves that against the verifier's own source.
from direct import run_arms  # noqa: E402


def flip(spec):
    """Flip EVERY effect together — target, guide-slot AND donor-pair.

    The M4b probe's own construction. Flipping only the target effect would leave the
    guide/donor evidence contradicting it — an internally inconsistent input the lane would
    be RIGHT to refuse, which would prove nothing. Flipping all four keeps the run
    internally consistent: it is simply an arm configuration in which the perturbation
    pushes the other way.
    """
    return dataclasses.replace(
        spec,
        a_effect=-spec.a_effect, b_effect=-spec.b_effect,
        guide_slot_effects={k: -v for k, v in spec.guide_slot_effects.items()},
        donor_pair_effects={k: -v for k, v in spec.donor_pair_effects.items()})


@pytest.fixture
def built(synthetic_run, tmp_path):
    """A real bundle from the producer, plus verifier args pointing at it."""
    def _build(specs=None, **kw):
        args = synthetic_run(specs=specs, **kw)
        args.condition = F.CONDITION
        args.out_root = str(tmp_path / f"arms{len(os.listdir(tmp_path))}")
        res = run_arms.build_bundle(args)
        return res, _verifier_args(res["out_dir"], args)
    return _build


def _verifier_args(bundle_dir, prod, **over):
    argv = [
        "--bundle", bundle_dir,
        "--de-main", prod.de_main,
        "--sgrna", prod.sgrna,
        "--by-guide", prod.by_guide,
        "--by-donors", prod.by_donors,
        "--guide-manifest", prod.guide_manifest,
        "--registry", prod.registry,
        "--condition", prod.condition,
        "--recompute", "all",
    ]
    for flag, attr in (("--source-registry", "source_registry"),
                       ("--target-identity-map", "target_identity_map"),
                       ("--donor-crosswalk", "donor_crosswalk"),
                       ("--strict-replay-source", "strict_replay_source"),
                       ("--pseudobulk", "pseudobulk")):
        value = getattr(prod, attr, None)
        if value:
            argv += [flag, value]
    ns = VB.build_parser().parse_args(argv)
    for k, v in over.items():
        setattr(ns, k, v)
    return ns


def run(args) -> dict:
    return VB.verify(args).doc()


def failures(args) -> set:
    return set(run(args)["failed_gates"])


def failed(args, gate_substring: str) -> bool:
    """The bundle is refused, AND at the gate this attack is supposed to trip.

    The honest producer ADMITS at 71/71, so any failing gate here was caused by the attack —
    there is no inherited gap for a test to coast on.
    """
    doc = run(args)
    return (doc["verdict"] == "REFUSE"
            and any(gate_substring in g for g in doc["failed_gates"]))


# --------------------------------------------------------------------------- #
# THE REPAIRED PRODUCER (W14, 41d9a9d). It ADMITS — 71/71 gates, no exception.
#
# Audit blockers 1-6 are closed against it: the pair selection is gone from the identity, the
# contributor manifest / mask / source registry / target-identity map are all bound, the
# evidence SHIPS, the producer no longer admits itself, and `mask_sha256` is now taken over
# the canonical table the bundle actually ships — so a reader of masks.parquet can reproduce
# the number bound beside it, which is the whole reason for binding it.
#
# There is no PRODUCER_GAPS baseline any more, and that is the point: it was pinned, not
# waived, and it came out when the producer earned it.
# --------------------------------------------------------------------------- #
class TestTheRepairedProducerAdmits:
    def test_the_repaired_producer_ADMITS(self, built):
        _, args = built()
        doc = run(args)
        assert doc["verdict"] == "ADMIT", doc["failed_gates"]
        assert doc["n_failed"] == 0

    def test_it_ran_a_non_vacuous_number_of_gates(self, built):
        _, args = built()
        doc = run(args)
        assert doc["n_gates"] >= 60 and doc["n_passed"] == doc["n_gates"]

    def test_the_MASK_hash_re_derives_from_the_shipped_masks_parquet(self, built):
        # W10's counterexample, now closed. The mask is a SET of facts: the same rows in any
        # order must give the same canonical table and the same hash, or the bundle's identity
        # would move without a single value changing.
        res, args = built()
        rows = pd.read_parquet(
            os.path.join(res["out_dir"], "masks.parquet")).to_dict("records")
        bound = res["provenance"]["run_binding"]["mask_sha256"]
        assert AR.content_sha256(S._canonical_mask_rows(rows)) == bound
        assert AR.content_sha256(S._canonical_mask_rows(list(reversed(rows)))) == bound

    def test_the_audit_blockers_are_CLOSED(self, built):
        _, args = built()
        assert failures(args) == set()

    def test_the_producer_does_NOT_admit_its_own_output(self, built):
        res, args = built()
        verification = json.load(open(os.path.join(res["out_dir"], "verification.json")))
        assert verification["admitted"] is False
        assert verification["self_admitted"] is False
        assert verification["verifier_id"] is None
        assert "PRODUCER did not admit its own output" in " ".join(
            run(args)["gate_inventory"])

    def test_the_report_is_TYPED_and_bound_to_this_exact_artifact(self, built):
        res, args = built()
        doc = run(args)
        assert doc["verifier_id"] == VB.VERIFIER_ID
        assert doc["spec_sha256"] == VB.SPEC_SHA256
        assert len(doc["verifier_code_sha256"]) == 64
        assert len(doc["gate_inventory_sha256"]) == 64
        bound = doc["bound_artifact"]
        assert bound["arm_bundle_run_id"] == res["arm_bundle_run_id"]
        assert bound["arm_rows_sha256"] == res["bundle"]["arm_rows_sha256"]
        assert set(bound["artifact_sha256"]) == VB.EXPECTED_FILES
        assert len(bound["arm_inventory"]) == res["n_expected_arm_slots"]

    def test_the_report_is_CONTENT_ADDRESSED_so_the_run_manifest_can_bind_it(self, built):
        _, args = built()
        doc = run(args)
        body = {k: v for k, v in doc.items() if k != "report_sha256"}
        assert doc["report_sha256"] == AR.content_sha256(body)

    def test_a_FLIPPED_verdict_does_not_survive_the_report_hash(self, built):
        _, args = built()
        doc = run(args)
        forged = dict(doc, verdict="REFUSE", n_failed=9, failed_gates=["x"])
        body = {k: v for k, v in forged.items() if k != "report_sha256"}
        assert AR.content_sha256(body) != forged["report_sha256"]

    def test_production_mode_recomputes_EVERY_target(self, built):
        _, args = built()
        bound = run(args)["bound_artifact"]
        assert bound["n_targets_recomputed"] == bound["n_targets_in_bundle"]

    def test_the_sample_mode_is_deterministic_and_seedless(self, built):
        _, args = built()
        args.recompute, args.sample_size = "sample", 5
        a, b = run(args)["bound_artifact"], run(args)["bound_artifact"]
        assert a["n_targets_recomputed"] == b["n_targets_recomputed"] == 5
        assert run(args)["verdict"] == "ADMIT"


class TestAuditBlocker5IsClosedTheIdentityNoLongerNamesAPair:
    def test_the_SAME_measurement_asked_for_two_pairs_is_now_ONE_bundle(
            self, synthetic_run, tmp_path):
        # The audit's BLOCKER 5, re-run against the repaired producer. Identical rows used
        # to come back under two ids because an UNUSED pair file was hashed into the
        # identity. Now the pair is not an input at all, so the id cannot move with it.
        a = synthetic_run()
        a.condition, a.out_root = F.CONDITION, str(tmp_path / "a")
        b = synthetic_run(direction_a="low")     # a DIFFERENT pair question
        b.condition, b.out_root = F.CONDITION, str(tmp_path / "b")
        ra, rb = run_arms.build_bundle(a), run_arms.build_bundle(b)

        assert ra["bundle"]["arm_rows_sha256"] == rb["bundle"]["arm_rows_sha256"], \
            "the fixture did not hold the measurement constant"
        assert ra["arm_bundle_run_id"] == rb["arm_bundle_run_id"], (
            "the same measurement still produces two bundle ids — the arms inside cannot "
            "be reused")

    def test_no_pair_scoped_input_is_hashed_into_the_identity(self, built):
        res, _ = built()
        names = [i["name"] for i in
                 res["provenance"]["run_binding"]["stage2_inputs"]]
        assert not [n for n in names
                    if any(f in n.lower() for f in ("selection", "contrast", "pair"))]

    def test_the_verifier_PASSES_the_pair_gate_on_the_repaired_producer(self, built):
        _, args = built()
        assert not any("binds NO pair selection" in g
                       for g in run(args)["failed_gates"])


class TestM4bACoherentSignFlipIsNotRefusedByAnyDisplayLogic:
    def test_a_COHERENTLY_SIGN_FLIPPED_configuration_adds_NO_failure(self, built):
        """The pair-bound verifier refused this at 152/153 over a re-derived `joint_status`
        — a DISPLAY label — while every measurement, rank, hash and reconstruction was
        valid. Here the flipped configuration fails EXACTLY the producer's binding gaps and
        nothing else: no display field, no science gate and no rank rule refuses it."""
        _, args = built(specs=[flip(s) for s in F.default_specs()])
        assert failures(args) == set()

    def test_the_flipped_bundle_carries_NO_joint_field_at_all(self, built):
        res, _ = built(specs=[flip(s) for s in F.default_specs()])
        blob = json.dumps(json.load(open(
            os.path.join(res["out_dir"], "arm_bundle.json"))))
        blob += json.dumps(json.load(open(
            os.path.join(res["out_dir"], VB.PROVENANCE_FILE))))
        for absent in ("joint_status", "pareto_tier", "concordance_class"):
            assert absent not in blob

    def test_NO_display_field_could_have_gated_the_verdict(self, built):
        # the M4b property, stated as a fact about the BYTES rather than as a promise about
        # the checker: a display field cannot decide anything here, because a display field
        # cannot BE here.
        res, args = built()
        doc = run(args)
        for name in ("arm_bundle.json", VB.PROVENANCE_FILE):
            assert AR.forbidden_hits(
                json.load(open(os.path.join(res["out_dir"], name)))) == []
        assert "no display-only field is available to gate admission" in \
            doc["gate_inventory"]
        assert "no display-only field is available to gate admission" not in \
            doc["failed_gates"]


# --------------------------------------------------------------------------- #
# The attacks. Each RESEALS what it breaks; the re-derivation must still catch it.
# --------------------------------------------------------------------------- #
def _reseal(bundle_dir, doc=None, prov=None, rows=None):
    """Rewrite the artifacts, recomputing every hash a forger could recompute.

    Including the SHIPPED ARTIFACT MANIFEST: a forger who edited a file and left its own
    hash behind would be caught by arithmetic, and that would prove nothing about the
    verifier. Everything the producer can recompute, this recomputes.
    """
    dpath = os.path.join(bundle_dir, "arm_bundle.json")
    ppath = os.path.join(bundle_dir, VB.PROVENANCE_FILE)
    rpath = os.path.join(bundle_dir, "arms.parquet")
    doc = doc if doc is not None else json.load(open(dpath))
    prov = prov if prov is not None else json.load(open(ppath))
    if rows is not None:
        pd.DataFrame(rows).to_parquet(rpath, index=False)
    with open(dpath, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    prov["artifacts"] = [
        {"name": e["name"],
         "size_bytes": os.path.getsize(os.path.join(bundle_dir, e["name"])),
         "raw_sha256": AR.sha256_file(os.path.join(bundle_dir, e["name"]))}
        for e in prov.get("artifacts", [])]
    with open(ppath, "w") as fh:
        json.dump(prov, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _rows_of(bundle_dir):
    return pd.read_parquet(os.path.join(bundle_dir, "arms.parquet")).to_dict("records")


def _fully_reseal(bundle_dir, rows):
    """The STRONGEST forgery: rewrite the rows, then recompute every hash the producer
    would have — the per-arm bytes, the rows hash, the binding, the run id and the shipped
    artifact manifest — so nothing is left inconsistent. Only an independent RE-DERIVATION
    from the DE data can refuse this."""
    doc = json.load(open(os.path.join(bundle_dir, "arm_bundle.json")))
    prov = json.load(open(os.path.join(bundle_dir, VB.PROVENANCE_FILE)))
    canon = [{c: r[c] for c in AR.ARM_ROW_COLUMNS} for r in rows]
    by_arm = {}
    for r in canon:
        by_arm.setdefault(r["arm_key"], []).append(r)
    for a in doc["arms"]:
        a["arm_rows_sha256"] = AR.arm_rows_sha256(by_arm.get(a["arm_key"], []))
    doc["arm_rows_sha256"] = AR.rows_sha256(canon)
    prov["run_binding"]["arm_rows_sha256"] = doc["arm_rows_sha256"]
    full = AR.sha256_hex(AR.canonical_json(prov["run_binding"]))
    prov["arm_bundle_run_sha256"] = full
    prov["arm_bundle_run_id"] = full[:VB.BUNDLE_RUN_ID_LEN]
    for r in rows:
        r["arm_bundle_run_id"] = prov["arm_bundle_run_id"]
    _reseal(bundle_dir, doc, prov, rows)


class TestTheIndependentAuditsExactAttacks:
    """DIRECT_ALL_ARM_INDEPENDENT_AUDIT.md (sha 1690df56…), BLOCKER 3.

    Every one of these left `run_hash_valid` and `parquet_rows_hash_valid` TRUE against the
    unverified producer — the advertised hashes stayed valid while the artifact lied. Each
    must now fail at a NAMED gate, and at a gate the attack itself trips: inheriting a
    producer binding gap it did not cause would not be catching it.
    """

    def test_AUDIT_forged_count_declared_999_slots_while_20_arms_remained(self, built):
        res, args = built()
        doc = json.load(open(os.path.join(res["out_dir"], "arm_bundle.json")))
        doc["n_arm_slots"] = 999
        doc["n_expected_arm_slots"] = 999
        _reseal(res["out_dir"], doc=doc)
        assert failed(args, "DERIVED from the admitted set, not copied")

    def test_AUDIT_missing_arm(self, built):
        res, args = built()
        doc = json.load(open(os.path.join(res["out_dir"], "arm_bundle.json")))
        doc["arms"].pop()
        _reseal(res["out_dir"], doc=doc)
        assert failed(args, "EXACTLY the expected arm keys")

    def test_AUDIT_duplicate_arm(self, built):
        res, args = built()
        doc = json.load(open(os.path.join(res["out_dir"], "arm_bundle.json")))
        doc["arms"].append(dict(doc["arms"][0]))
        _reseal(res["out_dir"], doc=doc)
        assert failed(args, "DUPLICATED")

    def test_AUDIT_scorer_hash_mismatch_zeroed_in_the_bundle(self, built):
        res, args = built()
        doc = json.load(open(os.path.join(res["out_dir"], "arm_bundle.json")))
        doc["scorer_view"]["scorer_view_sha256"] = "0" * 64
        _reseal(res["out_dir"], doc=doc)
        assert failed(args, "scorer view hash RE-DERIVES")

    def test_AUDIT_pair_field_insertion_as_a_16th_parquet_column(self, built):
        # the audit's sharpest one: this needed NO reseal — the canonical row hash and the
        # run id both stayed valid, because the projection simply ignored the extra column
        res, args = built()
        rows = _rows_of(res["out_dir"])
        for r in rows:
            r["joint_status"] = "opposed"
        pd.DataFrame(rows).to_parquet(
            os.path.join(res["out_dir"], "arms.parquet"), index=False)
        assert failed(args, "pair-derived or display-only column")

    def test_AUDIT_swapped_desired_change_mapping_FULLY_RESEALED(self, built):
        res, args = built()
        rows = _rows_of(res["out_dir"])
        for r in rows:
            other = (AR.DECREASE if r["desired_change"] == AR.INCREASE else AR.INCREASE)
            r["desired_change"] = other
            r["arm_key"] = AR.direct_arm_key(r["program_id"], other, r["condition"])
        _fully_reseal(res["out_dir"], rows)
        assert failed(args, "EXACT sign transform")

    def test_AUDIT_scientific_value_tamper_FULLY_RESEALED(self, built):
        res, args = built()
        rows = _rows_of(res["out_dir"])
        target = next(r for r in rows if r["value"] == r["value"])
        target["value"] = target["value"] + 1.0
        target["base_delta"] = target["base_delta"] + 1.0
        # re-rank so even the rank rule is internally consistent
        _fully_reseal(res["out_dir"], rows)
        assert failed(args, "base delta RE-DERIVES")


class TestForgedProgramSetsAndMappings:
    def test_a_COPIED_program_set_that_the_release_does_not_admit_is_REFUSED(self, built):
        res, args = built()
        doc = json.load(open(os.path.join(res["out_dir"], "arm_bundle.json")))
        doc["scorer_view"]["admitted_program_ids"].append("fx_invented_program")
        _reseal(res["out_dir"], doc=doc)
        assert failed(args, "admitted set EQUALS the independently derived set")

    def test_a_FORGED_scorer_view_hash_is_REFUSED(self, built):
        res, args = built()
        doc = json.load(open(os.path.join(res["out_dir"], "arm_bundle.json")))
        doc["scorer_view"]["scorer_view_sha256"] = "0" * 64
        _reseal(res["out_dir"], doc=doc)
        assert failed(args, "scorer view hash RE-DERIVES")

    def test_a_SWAPPED_desired_change_mapping_is_REFUSED(self, built):
        # relabel every arm's desired_change: increase <-> decrease, keys and all. The
        # VALUES then contradict the sign transform the key demands.
        res, args = built()
        rows = _rows_of(res["out_dir"])
        for r in rows:
            other = (AR.DECREASE if r["desired_change"] == AR.INCREASE
                     else AR.INCREASE)
            r["desired_change"] = other
            r["arm_key"] = AR.direct_arm_key(r["program_id"], other, r["condition"])
        _fully_reseal(res["out_dir"], rows)
        assert failed(args, "EXACT sign transform")

    def test_a_SIGN_FLIP_on_one_arm_alone_is_REFUSED(self, built):
        # negate one arm's values without touching its base delta: the two arms would now
        # disagree about a magnitude they share
        res, args = built()
        rows = _rows_of(res["out_dir"])
        for r in rows:
            if r["desired_change"] == AR.INCREASE and r["value"] == r["value"]:
                r["value"] = -r["value"]
        _fully_reseal(res["out_dir"], rows)
        assert failed(args, "EXACT sign transform")

    def test_a_POLE_KEYED_arm_is_REFUSED(self, built):
        res, args = built()
        doc = json.load(open(os.path.join(res["out_dir"], "arm_bundle.json")))
        doc["arms"][0]["arm_key"] = "direct|fx_progA|high|StimX"
        _reseal(res["out_dir"], doc=doc)
        assert failed(args, "keyed on a POLE or a ROLE")


class TestRankAndTieMutations:
    def test_a_MUTATED_rank_is_REFUSED(self, built):
        res, args = built()
        rows = _rows_of(res["out_dir"])
        ranked = [r for r in rows if r["rank"] == r["rank"]]
        assert ranked, "fixture has no ranked row"
        ranked[0]["rank"] = ranked[0]["rank"] + 100
        _fully_reseal(res["out_dir"], rows)
        assert failed(args, "rank RE-DERIVES per arm")

    def test_a_REVERSED_ranking_is_REFUSED(self, built):
        res, args = built()
        rows = _rows_of(res["out_dir"])
        key = rows[0]["arm_key"]
        arm = [r for r in rows if r["arm_key"] == key and r["rank"] == r["rank"]]
        n = len(arm)
        for r in arm:
            r["rank"] = n + 1 - r["rank"]        # still dense 1..n — only the ORDER lies
        if n < 2:
            pytest.skip("arm has fewer than two ranked targets")
        _fully_reseal(res["out_dir"], rows)
        assert failed(args, "rank RE-DERIVES per arm")

    def test_a_BROKEN_TIE_taken_the_wrong_way_is_REFUSED(self, built):
        # two targets with identical values: the tie breaks on target_id ASCENDING
        res, args = built()
        rows = _rows_of(res["out_dir"])
        key = rows[0]["arm_key"]
        arm = sorted([r for r in rows if r["arm_key"] == key
                      and r["rank"] == r["rank"]], key=lambda r: r["rank"])
        if len(arm) < 2:
            pytest.skip("arm has fewer than two ranked targets")
        arm[1]["value"] = arm[0]["value"]        # force an exact tie...
        arm[0]["rank"], arm[1]["rank"] = arm[1]["rank"], arm[0]["rank"]   # ...broken wrong
        _fully_reseal(res["out_dir"], rows)
        assert failed(args, "rank RE-DERIVES per arm")

    def test_a_NON_EVALUABLE_target_given_a_rank_is_REFUSED(self, built):
        res, args = built()
        rows = _rows_of(res["out_dir"])
        unranked = [r for r in rows if not r["evaluable"]]
        if not unranked:
            pytest.skip("fixture has no non-evaluable row")
        unranked[0]["rank"] = 99
        _fully_reseal(res["out_dir"], rows)
        assert failed(args, "ABSENT from the ranking")


class TestMissingDuplicateAndExtraArms:
    def test_a_MISSING_arm_is_REFUSED(self, built):
        res, args = built()
        doc = json.load(open(os.path.join(res["out_dir"], "arm_bundle.json")))
        dropped = doc["arms"].pop()
        doc["n_arm_slots"] = len(doc["arms"])
        rows = [r for r in _rows_of(res["out_dir"])
                if r["arm_key"] != dropped["arm_key"]]
        doc["n_arm_rows"] = len(rows)
        _reseal(res["out_dir"], doc=doc, rows=rows)
        _fully_reseal(res["out_dir"], rows)
        assert failed(args, "EXACTLY the expected arm keys")

    def test_a_DUPLICATED_arm_is_REFUSED(self, built):
        res, args = built()
        doc = json.load(open(os.path.join(res["out_dir"], "arm_bundle.json")))
        doc["arms"].append(dict(doc["arms"][0]))
        doc["n_arm_slots"] = len(doc["arms"])
        _reseal(res["out_dir"], doc=doc)
        assert failed(args, "DUPLICATED")

    def test_an_EXTRA_arm_the_release_does_not_admit_is_REFUSED(self, built):
        res, args = built()
        doc = json.load(open(os.path.join(res["out_dir"], "arm_bundle.json")))
        doc["arms"].append(dict(doc["arms"][0],
                                arm_key="direct|fx_ghost|increase|StimX",
                                program_id="fx_ghost"))
        doc["n_arm_slots"] = len(doc["arms"])
        _reseal(res["out_dir"], doc=doc)
        assert failed(args, "EXACTLY the expected arm keys")


class TestResealedArtifactsAndIdentity:
    def test_an_ALTERED_parquet_value_is_REFUSED_even_fully_RESEALED(self, built):
        # the strongest forgery: every hash the producer computes is recomputed, so nothing
        # is internally inconsistent. Only the independent recomputation from the DE data
        # can refuse it.
        res, args = built()
        rows = _rows_of(res["out_dir"])
        target = next(r for r in rows if r["value"] == r["value"])
        target["value"] = target["value"] + 1.0
        target["base_delta"] = target["base_delta"] + 1.0
        _fully_reseal(res["out_dir"], rows)
        assert failed(args, "base delta RE-DERIVES")

    def test_an_ALTERED_parquet_that_is_NOT_resealed_is_REFUSED_on_the_bytes(self, built):
        res, args = built()
        rows = _rows_of(res["out_dir"])
        rows[0]["value"] = 12345.0
        pd.DataFrame(rows).to_parquet(
            os.path.join(res["out_dir"], "arms.parquet"), index=False)
        assert failed(args, "arm_rows_sha256 RE-DERIVES")

    def test_a_RUN_ID_that_does_not_re_derive_is_REFUSED(self, built):
        res, args = built()
        prov = json.load(open(os.path.join(res["out_dir"],
                                           VB.PROVENANCE_FILE)))
        prov["arm_bundle_run_id"] = "deadbeefdeadbeef"
        _reseal(res["out_dir"], prov=prov)
        assert failed(args, "run id RE-DERIVES")

    def test_a_TAMPERED_binding_that_reseals_the_run_id_is_still_REFUSED(self, built):
        # reseal the id so it DOES re-derive — the binding now describes a different run
        res, args = built()
        prov = json.load(open(os.path.join(res["out_dir"],
                                           VB.PROVENANCE_FILE)))
        prov["run_binding"]["arm_rows_sha256"] = "0" * 64
        full = AR.sha256_hex(AR.canonical_json(prov["run_binding"]))
        prov["arm_bundle_run_sha256"] = full
        prov["arm_bundle_run_id"] = full[:VB.BUNDLE_RUN_ID_LEN]
        _reseal(res["out_dir"], prov=prov)
        assert failed(args, "arm bytes are BOUND into the run identity")

    def test_a_FORGED_request_hash_is_REFUSED(self, built):
        res, args = built()
        prov = json.load(open(os.path.join(res["out_dir"],
                                           VB.PROVENANCE_FILE)))
        prov["run_binding"]["arm_bundle_request"]["condition"] = "SomewhereElse"
        _reseal(res["out_dir"], prov=prov)
        assert failed(args, "SELF-HASHED")

    def test_an_ARBITRARY_verdict_admit_STUB_is_REFUSED(self, built):
        # the artifact replaced wholesale by a file that simply asserts it is fine
        res, args = built()
        for name in VB.EXPECTED_FILES:
            path = os.path.join(res["out_dir"], name)
            if path.endswith(".json"):
                with open(path, "w") as fh:
                    json.dump({"verdict": "admit"}, fh)
        # a file that simply asserts it is fine authenticates nothing
        assert run(args)["verdict"] == "REFUSE"

    def test_a_MISSING_artifact_is_REFUSED(self, built):
        res, args = built()
        os.remove(os.path.join(res["out_dir"], "arms.parquet"))
        assert failed(args, "file inventory")

    def test_an_EXTRA_file_in_the_bundle_is_REFUSED(self, built):
        res, args = built()
        with open(os.path.join(res["out_dir"], "sneaky.json"), "w") as fh:
            json.dump({"pareto_tier": 1}, fh)
        assert failed(args, "file inventory")


class TestInputAndCodeIdentityMismatches:
    def test_a_MUTATED_H5AD_is_REFUSED(self, built, tmp_path):
        res, args = built()
        copy = str(tmp_path / "tampered.h5ad")
        shutil.copy(args.de_main, copy)
        with open(copy, "ab") as fh:
            fh.write(b"\0")
        args.de_main = copy
        assert failed(args, "BYTES match the hash the run pinned")

    def test_a_WRONG_pinned_H5AD_sha_is_REFUSED(self, built):
        _, args = built()
        args.expect_h5ad_sha256 = "0" * 64
        assert failed(args, "PINNED object")

    def test_a_MUTATED_sgRNA_library_is_REFUSED(self, built, tmp_path):
        res, args = built()
        copy = str(tmp_path / "tampered.csv")
        shutil.copy(args.sgrna, copy)
        with open(copy, "a") as fh:
            fh.write("\n")
        args.sgrna = copy
        assert failed(args, "BYTES match the hash the run pinned")

    def test_a_MUTATED_contributor_manifest_is_REFUSED(self, built, tmp_path):
        # drop a guide citation: the mask shrinks, so every base delta moves
        res, args = built()
        doc = json.load(open(args.guide_manifest))
        doc["rows"] = [r for r in doc["rows"]
                       if not (r["estimate_type"] == "main"
                               and r["guide_id"] == doc["rows"][0]["guide_id"])]
        copy = str(tmp_path / "tampered.manifest.json")
        with open(copy, "w") as fh:
            json.dump(doc, fh)
        args.guide_manifest = copy
        assert failed(args, "base delta RE-DERIVES")

    def test_a_FORGED_code_digest_is_REFUSED(self, built):
        res, args = built()
        prov = json.load(open(os.path.join(res["out_dir"],
                                           VB.PROVENANCE_FILE)))
        prov["run_binding"]["code_identity"]["manifest_sha256"] = "0" * 64
        _reseal(res["out_dir"], prov=prov)
        assert failed(args, "code manifest hash RE-DERIVES")

    def test_a_FORGED_gene_universe_hash_is_REFUSED(self, built):
        res, args = built()
        prov = json.load(open(os.path.join(res["out_dir"],
                                           VB.PROVENANCE_FILE)))
        prov["run_binding"]["gene_universe_sha256"] = "0" * 64
        _reseal(res["out_dir"], prov=prov)
        assert failed(args, "effect-gene universe RE-DERIVES")

    def test_a_WRONG_condition_is_REFUSED(self, built):
        _, args = built()
        args.condition = "NotTheContext"
        assert failed(args, "ONE context")


class TestDisplayOnlyFieldsAreForbiddenNotDefaultedOff:
    def test_an_INSERTED_pair_field_is_REFUSED(self, built):
        res, args = built()
        doc = json.load(open(os.path.join(res["out_dir"], "arm_bundle.json")))
        doc["arms"][0]["joint_status"] = "opposed"
        _reseal(res["out_dir"], doc=doc)
        assert failed(args, "no pair / Pareto / concordance")

    def test_an_INSERTED_pareto_tier_COLUMN_is_REFUSED(self, built):
        res, args = built()
        rows = _rows_of(res["out_dir"])
        for r in rows:
            r["pareto_tier"] = 1
        pd.DataFrame(rows).to_parquet(
            os.path.join(res["out_dir"], "arms.parquet"), index=False)
        assert failed(args, "pair-derived or display-only column")

    def test_an_INSERTED_q_value_is_REFUSED(self, built):
        res, args = built()
        prov = json.load(open(os.path.join(res["out_dir"],
                                           VB.PROVENANCE_FILE)))
        prov["run_binding"]["method"]["q_value_threshold"] = 0.05
        _reseal(res["out_dir"], prov=prov)
        assert failed(args, "no pair / Pareto / concordance")

    def test_a_NEGATIVE_DECLARATION_flipped_true_is_REFUSED(self, built):
        res, args = built()
        doc = json.load(open(os.path.join(res["out_dir"], "arm_bundle.json")))
        doc["method"]["pareto_emitted"] = True
        _reseal(res["out_dir"], doc=doc)
        assert failed(args, "no pair / Pareto / concordance")


class TestTheCurrentGenericV3ReleaseIsWhatTheVerifierConsumes:
    """The SHIPPED integration: the admitted set comes from the bound generic v3 release
    (`spot.stage01_v3_release.v1`, Stage-1 d9bd4e5+55899ac), not from a registry path.

    The release here is CLEARLY SYNTHETIC — it wraps the fixture's own programs in the real
    release/scorer-view SHAPE, so what is exercised is the shape, not invented biology.
    """

    def _stage_v3_release(self, prod, root):
        """Wrap the fixture's programs in a real-shaped v3 release + scorer view."""
        os.makedirs(root, exist_ok=True)
        registry = json.load(open(prod.registry))
        view = {
            "schema_version": AV.STAGE1_VIEW_SCHEMA,
            "method_version": "stage1-continuous-v3.0.1",
            "view_kind": "executable_scorer_projection",
            "effect_universe_id": "fx_effect_universe",
            "n_programs": len(registry["programs"]),
            "programs": registry["programs"],
        }
        view_path = os.path.join(root, "stage01_stage2_registry_view.json")
        with open(view_path, "w") as fh:
            json.dump(view, fh, indent=1)
        canon = AV.canonical_content_sha256(view)
        release = {
            "schema": AV.STAGE1_RELEASE_SCHEMA_V3,
            "method_version": "stage1-continuous-v3.0.1",
            "registry_scorer_view_canonical_sha256": canon,
            "registry_scorer_projection_sha256": "f" * 64,
            "selector": {
                "kind": "generic_continuous_program_selector",
                "program_set_source": "v3_scorer_view",
                "registry_scorer_view_canonical_sha256": canon,
                "admitted_programs": sorted(
                    p["program_id"] for p in registry["programs"]
                    if p.get("base_portable")),
                "desired_change_mapping": {
                    "away_from_A(high)": "decrease", "away_from_A(low)": "increase",
                    "toward_B(high)": "increase", "toward_B(low)": "decrease"},
            },
            "components": {
                "stage2_registry_view": {
                    "path": "stage01_stage2_registry_view.json",
                    "raw_sha256": AR.sha256_file(view_path),
                    "canonical_content_sha256": canon,
                    "role": "executable_scorer_view",
                },
            },
        }
        release["self_release_sha256"] = AV.release_self_sha256(release)
        path = os.path.join(root, "stage01_v3_release.json")
        with open(path, "w") as fh:
            json.dump(release, fh, indent=1)
        return path

    def test_the_bundle_ADMITS_against_the_bound_generic_v3_release(self, synthetic_run,
                                                                    tmp_path):
        prod = synthetic_run()
        prod.condition, prod.out_root = F.CONDITION, str(tmp_path / "arms")
        res = run_arms.build_bundle(prod)
        root = str(tmp_path / "release")
        args = _verifier_args(res["out_dir"], prod,
                              stage1_v3_release=self._stage_v3_release(prod, root),
                              release_root=root)
        doc = run(args)
        assert doc["verdict"] == "ADMIT", doc["failed_gates"]
        assert doc["bound_artifact"]["stage1_scorer_view_canonical_sha256"]
        assert doc["bound_artifact"]["registry_scorer_projection_sha256"] == "f" * 64

    def test_a_STALE_pre_generic_release_shape_REFUSES_through_the_verifier(
            self, synthetic_run, tmp_path):
        prod = synthetic_run()
        prod.condition, prod.out_root = F.CONDITION, str(tmp_path / "arms")
        res = run_arms.build_bundle(prod)
        root = str(tmp_path / "release")
        os.makedirs(root)
        stale = os.path.join(root, "old_release.json")
        with open(stale, "w") as fh:
            json.dump({"schema_version": AV.STAGE1_RELEASE_SCHEMA_STALE,
                       "artifacts": {"registry": {"path": "r.json"}}}, fh)
        args = _verifier_args(res["out_dir"], prod, stage1_v3_release=stale,
                              release_root=root)
        assert failed(args, "loads and proves its own components")

    def test_a_RESEALED_release_naming_a_DIFFERENT_program_set_REFUSES(
            self, synthetic_run, tmp_path):
        # drop a program from the release's scorer view and reseal everything the release
        # can reseal. The bundle's own arms then answer to a set the release does not admit.
        prod = synthetic_run()
        prod.condition, prod.out_root = F.CONDITION, str(tmp_path / "arms")
        res = run_arms.build_bundle(prod)
        root = str(tmp_path / "release")
        path = self._stage_v3_release(prod, root)

        view_path = os.path.join(root, "stage01_stage2_registry_view.json")
        view = json.load(open(view_path))
        view["programs"][0]["base_portable"] = False
        with open(view_path, "w") as fh:
            json.dump(view, fh, indent=1)
        canon = AV.canonical_content_sha256(view)
        rel = json.load(open(path))
        rel["registry_scorer_view_canonical_sha256"] = canon
        rel["selector"]["registry_scorer_view_canonical_sha256"] = canon
        rel["selector"]["admitted_programs"] = sorted(
            p["program_id"] for p in view["programs"] if p.get("base_portable"))
        rel["components"]["stage2_registry_view"].update(
            raw_sha256=AR.sha256_file(view_path), canonical_content_sha256=canon)
        rel["self_release_sha256"] = AV.release_self_sha256(rel)
        with open(path, "w") as fh:
            json.dump(rel, fh, indent=1)

        args = _verifier_args(res["out_dir"], prod, stage1_v3_release=path,
                             release_root=root)
        assert failed(args, "admitted set EQUALS the independently derived set")
