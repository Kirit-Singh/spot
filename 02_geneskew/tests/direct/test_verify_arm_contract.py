"""THE NEUTRAL ADMISSION ADAPTER — one seam over the immutable native W10 report.

Two kinds of test here:

  * envelope validation with a synthetic real-shaped report — every required binding is
    mandatory, the self-hash is re-derived, the verdict is byte-exact, a self-admission and a
    wrong-checker report refuse;
  * a REAL end-to-end cross-contract test — a REAL Direct bundle from the producer, a REAL
    W10 report from the real verifier, normalized on disk; then every mutation (bundle byte,
    mask table, verdict, self-hash, env, condition) refuses at a NAMED gate.

The native report is never mutated in place: the producer's report is the sole source, and
this adapter reads it as it is.
"""
from __future__ import annotations

import json
import os
import shutil
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "analysis", "direct"))
sys.path.insert(0, os.path.join(_ROOT, "tests", "direct"))

import verify_arm_contract as C  # noqa: E402
import verify_arm_rules as AR  # noqa: E402

LOCK = os.path.join(_ROOT, "analysis", "stage02_solver_lock.txt")


def _seal(report: dict) -> dict:
    body = {k: v for k, v in report.items() if k != "report_sha256"}
    report["report_sha256"] = AR.content_sha256(body)
    return report


def _synthetic_report() -> dict:
    """A schema-complete native bundle report — the shape the real verifier emits."""
    inv = ["g1", "g2"]
    return _seal({
        "schema_version": C.SCHEMA_BUNDLE,
        "verifier_id": C.W10_VERIFIER_ID_BUNDLE,
        "verifier_code_sha256": "3bc55ba5" + "0" * 56,
        "spec_sha256": C.W10_SPEC_SHA256,
        "independent_of_generator": True,
        "gate_inventory": inv,
        "gate_inventory_sha256": AR.content_sha256(inv),
        "gates": [{"gate": "g1", "passed": True}, {"gate": "g2", "passed": True}],
        "n_gates": 2, "n_passed": 2, "n_failed": 0, "failed_gates": [],
        "verdict": "ADMIT",
        "bound_artifact": {
            "arm_bundle_run_id": "1ea4013bae69998a",
            "condition": "StimX", "lane": "synthetic",
            "arm_rows_sha256": "66fc" + "0" * 60,
            "scorer_view_sha256": "3a2a" + "0" * 60,
            "stage1_scorer_view_canonical_sha256": "5d1d" + "0" * 60,
            "registry_scorer_projection_sha256": "008c" + "0" * 60,
            "solver_lock_sha256": C.PINNED_SOLVER_LOCK_SHA256,
            "solver_lock_pinned_sha256": C.PINNED_SOLVER_LOCK_SHA256,
            "artifact_sha256": {"arm_bundle.json": "ab" * 32},
        },
    })


# --------------------------------------------------------------------------- #
# Envelope validation (synthetic report, no disk).
# --------------------------------------------------------------------------- #
class TestTheEnvelopeValidates:
    def test_a_complete_report_validates_and_normalizes(self):
        b = C.normalize(_synthetic_report())
        assert b["binding_schema"] == C.BINDING_SCHEMA
        assert b["native_verdict"] == "ADMIT"
        assert b["disposition"] == "admitted"
        assert b["bundle_verified_on_disk"] is False
        assert b["binding_sha256"] == AR.content_sha256(
            {k: v for k, v in b.items() if k != "binding_sha256"})

    def test_the_disposition_is_byte_exact(self):
        assert C.disposition(_synthetic_report()) == "admitted"
        r = _synthetic_report()
        r["verdict"] = "REFUSE"
        r["n_failed"], r["failed_gates"] = 1, ["g2"]
        _seal(r)
        assert C.disposition(r) == "refused"

    @pytest.mark.parametrize("field", C.REQUIRED_TOP)
    def test_a_missing_top_field_refuses(self, field):
        # deliberately NOT resealed: a missing required field is caught before the self-hash,
        # and report_sha256 is itself required
        r = _synthetic_report()
        del r[field]
        with pytest.raises(C.ContractError):
            C.validate_report(r)

    @pytest.mark.parametrize("field", C.REQUIRED_BUNDLE_PROVENANCE)
    def test_a_missing_provenance_binding_refuses(self, field):
        r = _synthetic_report()
        del r["bound_artifact"][field]
        _seal(r)
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason in (C.REFUSE_MISSING_PROVENANCE, C.REFUSE_WRONG_ENV)

    def test_a_broken_self_hash_refuses(self):
        r = _synthetic_report()
        r["n_gates"] = 999                    # edit the body, do NOT reseal
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_SELF_HASH

    def test_an_unknown_verdict_is_not_folded(self):
        for tok in ("admit", "Admit", "aDmIt", "yes"):
            r = _synthetic_report()
            r["verdict"] = tok
            _seal(r)
            with pytest.raises(C.ContractError) as exc:
                C.validate_report(r)
            assert exc.value.reason == C.REFUSE_UNKNOWN_VERDICT, tok

    def test_an_admit_with_failed_gates_refuses(self):
        r = _synthetic_report()
        r["n_failed"], r["failed_gates"] = 2, ["g1", "g2"]
        _seal(r)
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_ADMIT_WITH_FAILURES

    def test_a_self_admission_slot_refuses(self):
        r = _synthetic_report()
        r["verifier_id"] = None
        r["verdict"] = "pending_independent_verification"
        _seal(r)
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_SELF_ADMITTED

    def test_a_report_not_independent_refuses(self):
        r = _synthetic_report()
        r["independent_of_generator"] = False
        _seal(r)
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_NOT_INDEPENDENT

    def test_a_report_from_another_checker_refuses(self):
        r = _synthetic_report()
        r["verifier_id"] = "some.other.checker.v1"
        _seal(r)
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_WRONG_VERIFIER

    def test_spec_drift_refuses(self):
        r = _synthetic_report()
        r["spec_sha256"] = "0" * 64
        _seal(r)
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_SPEC_DRIFT

    def test_the_env_lock_must_be_the_pin(self):
        r = _synthetic_report()
        r["bound_artifact"]["solver_lock_sha256"] = "b928" + "0" * 60
        _seal(r)
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_WRONG_ENV

    def test_the_two_byte_admit_stub_refuses(self):
        with pytest.raises(C.ContractError):
            C.validate_report({"verdict": "ADMIT"})

    def test_the_schema_file_matches_the_binding(self):
        schema = json.load(open(C.SCHEMA_PATH))
        assert schema["properties"]["binding_schema"]["const"] == C.BINDING_SCHEMA
        b = C.normalize(_synthetic_report())
        for f in schema["required"]:
            assert f in b, f


# --------------------------------------------------------------------------- #
# The REAL end-to-end cross-contract test (a real bundle + real W10 report).
# --------------------------------------------------------------------------- #
@pytest.fixture
def real(synthetic_run, tmp_path):
    """A REAL Direct bundle + a REAL W10 report, and a re-usable copy factory."""
    import fixtures_direct as F
    import verify_arm_bundle as VB
    from direct import run_arms

    prod = synthetic_run()
    prod.condition, prod.env_lock = F.CONDITION, LOCK
    prod.out_root = str(tmp_path / "arms")
    res = run_arms.build_bundle(prod)
    bundle = res["out_dir"]

    argv = ["--bundle", bundle, "--de-main", prod.de_main, "--sgrna", prod.sgrna,
            "--by-guide", prod.by_guide, "--by-donors", prod.by_donors,
            "--guide-manifest", prod.guide_manifest, "--registry", prod.registry,
            "--condition", prod.condition, "--recompute", "all", "--env-lock", LOCK]
    for flag, attr in (("--source-registry", "source_registry"),
                       ("--pseudobulk", "pseudobulk")):
        v = getattr(prod, attr, None)
        if v:
            argv += [flag, v]
    report = VB.verify(VB.build_parser().parse_args(argv)).doc()
    report_path = str(tmp_path / "w10_report.json")
    with open(report_path, "w") as fh:
        json.dump(report, fh, sort_keys=True)

    counter = {"n": 0}

    def copy_bundle():
        counter["n"] += 1
        dst = str(tmp_path / f"copy{counter['n']}")
        shutil.copytree(bundle, dst)
        return dst

    return report, report_path, bundle, copy_bundle


def _refuses(report_path, bundle_dir, reason):
    try:
        C.load_and_normalize(report_path, bundle_dir)
    except C.ContractError as exc:
        return exc.reason == reason, exc.reason
    return False, "NORMALIZED — not refused"


class TestTheRealCrossContractBindingAdmitsAndMutationsRefuse:
    def test_a_real_report_and_bundle_NORMALIZE_and_ADMIT_on_disk(self, real):
        report, report_path, bundle, _ = real
        assert report["verdict"] == "ADMIT", report["failed_gates"]
        b = C.load_and_normalize(report_path, bundle)
        assert b["disposition"] == "admitted"
        assert b["bundle_verified_on_disk"] is True
        # the mask was RE-DERIVED from masks.parquet, not copied from the report
        assert b["mask_sha256"] and len(b["mask_sha256"]) == 64
        # every shipped file was re-hashed from disk
        assert set(b["direct_bundle_sha256"]) == set(
            report["bound_artifact"]["artifact_sha256"])
        assert b["binding_sha256"] == AR.content_sha256(
            {k: v for k, v in b.items() if k != "binding_sha256"})

    def test_the_binding_is_PER_RUN_content_addressed(self, real):
        # temporal anchors its DiD on these; two runs must not share a binding id
        report, report_path, bundle, _ = real
        b = C.load_and_normalize(report_path, bundle)
        assert b["source_report_sha256"] == report["report_sha256"]

    def test_a_MUTATED_bundle_byte_refuses(self, real):
        report, report_path, _, copy_bundle = real
        dst = copy_bundle()
        with open(os.path.join(dst, "arms.parquet"), "ab") as fh:
            fh.write(b"\0")
        ok, got = _refuses(report_path, dst, C.REFUSE_BUNDLE_BYTES)
        assert ok, got

    def test_a_MUTATED_mask_table_refuses_at_the_BYTES_gate(self, real):
        # the simple case: editing masks.parquet moves its bytes, caught before the mask
        report, report_path, _, copy_bundle = real
        import pandas as pd
        dst = copy_bundle()
        mp = os.path.join(dst, "masks.parquet")
        pd.read_parquet(mp).iloc[1:].to_parquet(mp, index=False)
        ok, got = _refuses(report_path, dst, C.REFUSE_BUNDLE_BYTES)
        assert ok, got

    def test_a_RESEALED_mask_swap_refuses_at_the_MASK_gate(self, real, tmp_path):
        # the sharp case: edit masks.parquet AND update the report's artifact_sha256 for it
        # AND honestly reseal, so the bytes gate PASSES. The bundle's own provenance.json
        # still binds the ORIGINAL mask, and the re-derivation no longer matches it.
        import pandas as pd
        report, _, _, copy_bundle = real
        dst = copy_bundle()
        mp = os.path.join(dst, "masks.parquet")
        pd.read_parquet(mp).iloc[1:].to_parquet(mp, index=False)
        forged = json.loads(json.dumps(report))
        forged["bound_artifact"]["artifact_sha256"]["masks.parquet"] = AR.sha256_file(mp)
        body = {k: v for k, v in forged.items() if k != "report_sha256"}
        forged["report_sha256"] = AR.content_sha256(body)
        fp = str(tmp_path / "mask_forged.json")
        with open(fp, "w") as fh:
            json.dump(forged, fh)
        ok, got = _refuses(fp, dst, C.REFUSE_MASK)
        assert ok, got

    def test_a_RESELAED_report_flipping_REFUSE_to_ADMIT_refuses(self, real):
        # take the real report, force a failed gate, honestly reseal -> ADMIT-with-failures
        report, _, bundle, _ = real
        forged = dict(report, verdict="ADMIT", n_failed=1, failed_gates=["x"])
        body = {k: v for k, v in forged.items() if k != "report_sha256"}
        forged["report_sha256"] = AR.content_sha256(body)
        p = os.path.join(bundle, "..", "forged.json")
        with open(p, "w") as fh:
            json.dump(forged, fh)
        ok, got = _refuses(p, bundle, C.REFUSE_ADMIT_WITH_FAILURES)
        assert ok, got

    def test_a_TAMPERED_report_self_hash_refuses(self, real):
        report, _, bundle, _ = real
        tampered = dict(report, n_gates=999)      # not resealed
        p = os.path.join(bundle, "..", "tampered.json")
        with open(p, "w") as fh:
            json.dump(tampered, fh)
        ok, got = _refuses(p, bundle, C.REFUSE_SELF_HASH)
        assert ok, got

    def test_a_report_for_ANOTHER_BUNDLE_refuses(self, real, synthetic_run, tmp_path):
        # a real ADMIT report, pointed at a different real bundle
        report, report_path, _, _ = real
        import fixtures_direct as F
        from direct import run_arms
        other = synthetic_run(direction_a="low")
        other.condition, other.env_lock = F.CONDITION, LOCK
        other.out_root = str(tmp_path / "other")
        other_bundle = run_arms.build_bundle(other)["out_dir"]
        ok, got = _refuses(report_path, other_bundle, C.REFUSE_BUNDLE_BYTES)
        assert ok, got
