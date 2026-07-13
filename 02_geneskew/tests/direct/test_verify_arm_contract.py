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
    """A schema-complete, PIN-VALID native bundle report — the shape the real verifier emits.

    Carries the real pinned code sha and the real security-critical gate names, so it is a
    valid baseline the envelope tests mutate ONE field away from.
    """
    inv = list(C.REQUIRED_GATES[C.W10_VERIFIER_ID_BUNDLE])
    return _seal({
        "schema_version": C.SCHEMA_BUNDLE,
        "verifier_id": C.W10_VERIFIER_ID_BUNDLE,
        "verifier_code_sha256": C.W10_VERIFIER_CODE_SHA256,
        "spec_sha256": C.W10_SPEC_SHA256,
        "independent_of_generator": True,
        "gate_inventory": inv,
        "gate_inventory_sha256": AR.content_sha256(inv),
        "gates": [{"gate": g, "passed": True} for g in inv],
        "n_gates": len(inv), "n_passed": len(inv), "n_failed": 0, "failed_gates": [],
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
        r["gates"][-1]["passed"] = False              # a real gate actually failed
        failed = r["gates"][-1]["gate"]
        r["n_passed"], r["n_failed"] = r["n_gates"] - 1, 1
        r["failed_gates"] = [failed]
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


class TestTheAdversarialFailOpenCasesAreClosed:
    """Every case the adversarial review reproduced on e4cf8b9, each now refused by name.

    The theme: a report can be made INTERNALLY CONSISTENT — self-hash valid, inventory hash
    valid — and still be a fraud. Only a pin the report does not get a vote on, and a check of
    the counts against the list they summarise, refuse these.
    """

    def _real_gate_report(self):
        """A synthetic report carrying the REAL bundle gate inventory + the real code sha."""
        r = _synthetic_report()
        r["verifier_code_sha256"] = C.W10_VERIFIER_CODE_SHA256
        # the real security-critical gate names must be present
        inv = list(C.REQUIRED_GATES[C.W10_VERIFIER_ID_BUNDLE])
        r["gate_inventory"] = inv
        r["gate_inventory_sha256"] = AR.content_sha256(inv)
        r["gates"] = [{"gate": g, "passed": True} for g in inv]
        r["n_gates"], r["n_passed"], r["n_failed"], r["failed_gates"] = \
            len(inv), len(inv), 0, []
        return _seal(r)

    def test_the_real_gate_report_validates(self):
        C.validate_report(self._real_gate_report())     # baseline: it passes honestly

    def test_A_a_ZEROED_verifier_code_sha_resealed_REFUSES(self):
        r = self._real_gate_report()
        r["verifier_code_sha256"] = "0" * 64
        _seal(r)
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_WRONG_CODE

    def test_A_a_weakened_fork_keeping_the_id_but_wrong_code_REFUSES(self):
        r = self._real_gate_report()
        r["verifier_code_sha256"] = "dead" + "0" * 60
        _seal(r)
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_WRONG_CODE

    def test_B_an_EMPTY_gate_inventory_with_n_gates_0_REFUSES(self):
        r = self._real_gate_report()
        r["gate_inventory"], r["gates"] = [], []
        r["gate_inventory_sha256"] = AR.content_sha256([])
        r["n_gates"] = r["n_passed"] = r["n_failed"] = 0
        r["failed_gates"] = []
        _seal(r)
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_GATE_MISSING

    def test_B_a_resealed_deletion_of_the_MASK_gate_REFUSES(self):
        r = self._real_gate_report()
        mask = next(g for g in r["gate_inventory"] if "MASK's identity" in g)
        r["gate_inventory"] = [g for g in r["gate_inventory"] if g != mask]
        r["gates"] = [g for g in r["gates"] if g["gate"] != mask]
        r["gate_inventory_sha256"] = AR.content_sha256(r["gate_inventory"])
        r["n_gates"] = r["n_passed"] = len(r["gate_inventory"])
        _seal(r)                                       # honestly resealed, counts consistent
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_GATE_MISSING

    def test_C_inflated_n_gates_and_n_passed_999_REFUSES(self):
        r = self._real_gate_report()
        r["n_gates"] = 999
        r["n_passed"] = 999
        _seal(r)
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_GATE_COUNTS

    def test_C_padded_n_passed_alone_REFUSES(self):
        r = self._real_gate_report()
        r["n_passed"] = r["n_gates"] + 5
        _seal(r)
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_GATE_COUNTS

    def test_C_a_gate_list_that_is_not_the_inventory_REFUSES(self):
        r = self._real_gate_report()
        r["gates"][0]["gate"] = "a different name"     # list disagrees with inventory
        _seal(r)
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_GATE_COUNTS

    def test_a_report_that_matches_NO_known_profile_still_needs_the_critical_gates(self):
        # a synthetic report selects the lenient fixture profile; deleting a CRITICAL gate
        # still refuses (the subset floor), even though the fixture profile is not exact
        r = _synthetic_report()
        mask = next(g for g in r["gate_inventory"] if "MASK's identity" in g)
        r["gate_inventory"] = [g for g in r["gate_inventory"] if g != mask]
        r["gates"] = [g for g in r["gates"] if g["gate"] != mask]
        r["gate_inventory_sha256"] = AR.content_sha256(r["gate_inventory"])
        r["n_gates"] = r["n_passed"] = len(r["gate_inventory"])
        _seal(r)
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_GATE_MISSING

    def test_the_pinned_code_sha_RE_DERIVES_from_W10s_own_recipe(self):
        # the pin is version-locked; a test re-derives it so a stale pin fails loudly rather
        # than silently refusing W10's own current reports
        import verify_arm_report as R
        assert C.W10_VERIFIER_CODE_SHA256 == R.verifier_code_sha256()

    def test_a_REAL_release_binding_normalizes_and_satisfies_its_own_schema(
            self, synthetic_run, tmp_path):
        # the exact review case: a release binding's arm_rows_sha256 is legitimately null,
        # and the binding must still be schema-valid. Built from a REAL release report so it
        # carries the exact 26-gate release profile (release is always production-grade).
        import fixtures_v3_release as V3
        import verify_direct_release as VR
        from direct import arm_release
        conds = ("Rest", "Stim8hr", "Stim48hr")
        prod = synthetic_run(conditions=conds)
        root = str(tmp_path / "root")
        s1 = V3.stage_release(root, conditions=conds)
        prod.stage1_release, prod.stage1_release_root, prod.env_lock = s1, root, LOCK
        prod.out_root = str(tmp_path / "rel")
        arm_release.build_release(prod)
        report_path = str(tmp_path / "release_report.json")
        argv = ["--release", prod.out_root, "--de-main", prod.de_main, "--sgrna", prod.sgrna,
                "--by-guide", prod.by_guide, "--by-donors", prod.by_donors,
                "--guide-manifest", prod.guide_manifest, "--registry", prod.registry,
                "--stage1-v3-release", s1, "--release-root", root, "--recompute", "all",
                "--env-lock", LOCK, "--report", report_path]
        if prod.source_registry:
            argv += ["--source-registry", prod.source_registry]
        if getattr(prod, "pseudobulk", None):
            argv += ["--pseudobulk", prod.pseudobulk]
        rc = VR.main(argv)                       # writes the CANONICAL release report
        assert rc == 0
        report = json.load(open(report_path))    # release schema + release verifier_id
        assert report["schema_version"] == C.SCHEMA_RELEASE
        # normalize WITH the release directory so the adapter re-derives the W3 cross-pins
        b = C.load_and_normalize(report_path, prod.out_root)
        assert b["subject_kind"] == "release"
        assert b["arm_rows_sha256"] is None
        # the W3 cross-pins for the aggregate manifest Direct lane
        assert isinstance(b["direct_bundle_ids"], list) and len(b["direct_bundle_ids"]) == 3
        assert all(b["direct_bundle_ids"])
        assert b["code_identity"] and b["release_canonical_sha256"]
        assert b["scorer_view_sha256"]
        assert b["w10_report"] == report_path and b["w10_report_raw_sha256"]
        C.validate_binding(b)                    # explicitly: the binding is schema-valid


@pytest.fixture
def real(synthetic_run, tmp_path):
    """A REAL Direct bundle + a REAL W10 report (fixture lane), and a bundle-copy factory."""
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
    return False, "NORMALIZED (not refused)"


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



# --------------------------------------------------------------------------- #
# EXECUTION-COMPLETENESS: the production profile is EXACT — any gate deletion refuses.
# --------------------------------------------------------------------------- #
def _stage_v3(prod, root):
    import verify_arm_view as AV
    os.makedirs(root, exist_ok=True)
    reg = json.load(open(prod.registry))
    view = {"schema_version": AV.STAGE1_VIEW_SCHEMA,
            "method_version": "stage1-continuous-v3.0.1",
            "view_kind": "executable_scorer_projection",
            "n_programs": len(reg["programs"]), "programs": reg["programs"]}
    vp = os.path.join(root, "stage01_stage2_registry_view.json")
    json.dump(view, open(vp, "w"), indent=1)
    canon = AV.canonical_content_sha256(view)
    rel = {"schema": AV.STAGE1_RELEASE_SCHEMA_V3, "method_version": "stage1-continuous-v3.0.1",
           "registry_scorer_view_canonical_sha256": canon,
           "registry_scorer_projection_sha256": "f" * 64,
           "selector": {"kind": "generic_continuous_program_selector",
                        "program_set_source": "v3_scorer_view",
                        "registry_scorer_view_canonical_sha256": canon,
                        "admitted_programs": sorted(p["program_id"] for p in reg["programs"]
                                                    if p.get("base_portable")),
                        "conditions": ["Rest", "Stim8hr", "Stim48hr"],
                        "desired_change_mapping": {
                            "away_from_A(high)": "decrease", "away_from_A(low)": "increase",
                            "toward_B(high)": "increase", "toward_B(low)": "decrease"}},
           "components": {"stage2_registry_view": {
               "path": "stage01_stage2_registry_view.json", "raw_sha256": AR.sha256_file(vp),
               "canonical_content_sha256": canon, "role": "executable_scorer_view"}}}
    rel["self_release_sha256"] = AV.release_self_sha256(rel)
    p = os.path.join(root, "stage01_v3_release.json")
    json.dump(rel, open(p, "w"), indent=1)
    return p


@pytest.fixture
def production_report(synthetic_run, tmp_path):
    """A native report carrying the full PRODUCTION gate inventory (stage1 release bound,
    H5AD pinned, recompute all). Built on a synthetic bundle — the gate NAMES are
    flag-determined and data/lane-independent — then relabelled to the production lane so it
    selects the exact production profile."""
    import fixtures_direct as F
    import verify_arm_bundle as VB
    from direct import run_arms
    prod = synthetic_run()
    prod.condition, prod.env_lock = F.CONDITION, LOCK
    prod.out_root = str(tmp_path / "arms")
    res = run_arms.build_bundle(prod)
    root = str(tmp_path / "root")
    s1 = _stage_v3(prod, root)
    argv = ["--bundle", res["out_dir"], "--de-main", prod.de_main, "--sgrna", prod.sgrna,
            "--by-guide", prod.by_guide, "--by-donors", prod.by_donors,
            "--guide-manifest", prod.guide_manifest, "--registry", prod.registry,
            "--condition", prod.condition, "--recompute", "all", "--env-lock", LOCK,
            "--stage1-v3-release", s1, "--release-root", root,
            "--expect-h5ad-sha256", AR.sha256_file(prod.de_main)]
    if prod.source_registry:
        argv += ["--source-registry", prod.source_registry]
    if getattr(prod, "pseudobulk", None):
        argv += ["--pseudobulk", prod.pseudobulk]
    report = VB.verify(VB.build_parser().parse_args(argv)).doc()
    # relabel to the production lane so the profile selector picks the exact production profile
    report["bound_artifact"]["lane"] = "production"
    return _seal(report)


class TestTheProductionProfileIsExact:
    def test_the_production_report_matches_the_pinned_profile(self, production_report):
        # baseline: the full production inventory validates against the exact profile
        C.validate_report(production_report)
        assert production_report["n_gates"] == \
            C.GATE_PROFILES[C.PROFILE_BUNDLE_PRODUCTION]["n_gates"]
        assert production_report["gate_inventory_sha256"] == \
            C.GATE_PROFILES[C.PROFILE_BUNDLE_PRODUCTION]["gate_inventory_sha256"]

    def test_deleting_a_NON_CRITICAL_production_gate_and_resealing_REFUSES(
            self, production_report):
        # the residual the review flagged: a gate NOT in the critical subset, honestly
        # deleted and resealed, used to pass. The exact profile refuses it.
        r = production_report
        noncritical = next(
            g for g in r["gate_inventory"]
            if "no p, q or FDR" in g or "columns are exactly the allowlisted" in g)
        assert not any(sub in noncritical for sub in
                       C.REQUIRED_GATES[C.W10_VERIFIER_ID_BUNDLE]), \
            "picked a gate that IS in the critical subset — choose a non-critical one"
        r["gate_inventory"] = [g for g in r["gate_inventory"] if g != noncritical]
        r["gates"] = [g for g in r["gates"] if g["gate"] != noncritical]
        r["gate_inventory_sha256"] = AR.content_sha256(r["gate_inventory"])
        r["n_gates"] = r["n_passed"] = len(r["gate_inventory"])
        _seal(r)
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_GATE_PROFILE

    def test_a_production_report_missing_the_H5AD_PIN_gate_REFUSES(self, production_report):
        # a production admission that did not pin the H5AD is not the production invocation
        r = production_report
        h5 = next(g for g in r["gate_inventory"] if "PINNED object" in g)
        r["gate_inventory"] = [g for g in r["gate_inventory"] if g != h5]
        r["gates"] = [g for g in r["gates"] if g["gate"] != h5]
        r["gate_inventory_sha256"] = AR.content_sha256(r["gate_inventory"])
        r["n_gates"] = r["n_passed"] = len(r["gate_inventory"])
        _seal(r)
        with pytest.raises(C.ContractError) as exc:
            C.validate_report(r)
        assert exc.value.reason == C.REFUSE_GATE_PROFILE

    def test_the_pinned_production_profile_hash_RE_DERIVES(self, production_report):
        # the profile is version-locked; re-deriving it from a real production-flags run means
        # a deliberate gate change in W10 fails HERE (refresh the profile) rather than
        # silently refusing W10's own production reports
        assert AR.content_sha256(production_report["gate_inventory"]) == \
            C.GATE_PROFILES[C.PROFILE_BUNDLE_PRODUCTION]["gate_inventory_sha256"]
        assert production_report["n_gates"] == 80


class TestTheEmittedBindingValidatesAgainstThePublishedSchemaFile:
    """The coordinator's explicit re-verification: the normalized binding must validate
    against schemas/stage02_direct_admission_binding.schema.json with a REAL jsonschema
    validator — not only the adapter's own validate_binding — for BOTH subject_kinds. A
    release binding whose arm_rows_sha256 is legitimately null must still be schema-valid.
    """

    def test_a_real_BUNDLE_binding_validates_against_the_schema_FILE(self, real):
        import jsonschema
        _, report_path, bundle, _ = real
        binding = C.load_and_normalize(report_path, bundle)
        assert binding["subject_kind"] == "bundle"
        jsonschema.validate(binding, json.load(open(C.SCHEMA_PATH)))

    def test_a_real_RELEASE_binding_validates_against_the_schema_FILE(
            self, synthetic_run, tmp_path):
        import fixtures_v3_release as V3
        import jsonschema
        import verify_direct_release as VR
        from direct import arm_release
        conds = ("Rest", "Stim8hr", "Stim48hr")
        prod = synthetic_run(conditions=conds)
        root = str(tmp_path / "root")
        stage1 = V3.stage_release(root, conditions=conds)
        prod.stage1_release, prod.stage1_release_root = stage1, root
        prod.env_lock, prod.out_root = LOCK, str(tmp_path / "rel")
        res = arm_release.build_release(prod)
        argv = ["--release", res["out_dir"], "--de-main", prod.de_main,
                "--sgrna", prod.sgrna, "--by-guide", prod.by_guide,
                "--by-donors", prod.by_donors, "--guide-manifest", prod.guide_manifest,
                "--registry", prod.registry, "--stage1-v3-release", stage1,
                "--release-root", root, "--recompute", "all", "--env-lock", LOCK]
        for flag, attr in (("--source-registry", "source_registry"),
                           ("--pseudobulk", "pseudobulk")):
            v = getattr(prod, attr, None)
            if v:
                argv += [flag, v]
        rel_path = str(tmp_path / "release_verification.json")
        assert VR.main(argv + ["--report", rel_path]) == 0
        binding = C.load_and_normalize(rel_path, res["out_dir"])   # release dir via --bundle
        assert binding["subject_kind"] == "release"
        assert binding["arm_rows_sha256"] is None      # legitimate for a release subject
        # the W3 cross-pins present and well-formed
        assert len(binding["direct_bundle_ids"]) == 3 and all(binding["direct_bundle_ids"])
        assert binding["code_identity"] and binding["scorer_view_sha256"]
        assert binding["release_canonical_sha256"] and binding["w10_report_raw_sha256"]
        jsonschema.validate(binding, json.load(open(C.SCHEMA_PATH)))

    def test_a_release_whose_bundles_disagree_on_code_identity_REFUSES(
            self, synthetic_run, tmp_path):
        import fixtures_v3_release as V3
        import verify_direct_release as VR
        from direct import arm_release
        conds = ("Rest", "Stim8hr", "Stim48hr")
        prod = synthetic_run(conditions=conds)
        root = str(tmp_path / "root")
        stage1 = V3.stage_release(root, conditions=conds)
        prod.stage1_release, prod.stage1_release_root = stage1, root
        prod.env_lock, prod.out_root = LOCK, str(tmp_path / "rel")
        res = arm_release.build_release(prod)
        argv = ["--release", res["out_dir"], "--de-main", prod.de_main,
                "--sgrna", prod.sgrna, "--by-guide", prod.by_guide,
                "--by-donors", prod.by_donors, "--guide-manifest", prod.guide_manifest,
                "--registry", prod.registry, "--stage1-v3-release", stage1,
                "--release-root", root, "--recompute", "all", "--env-lock", LOCK]
        for flag, attr in (("--source-registry", "source_registry"),
                           ("--pseudobulk", "pseudobulk")):
            v = getattr(prod, attr, None)
            if v:
                argv += [flag, v]
        rel_path = str(tmp_path / "release_verification.json")
        assert VR.main(argv + ["--report", rel_path]) == 0
        # corrupt ONE bundle's provenance code identity on disk -> the 3 no longer agree
        reldoc = json.load(open(os.path.join(res["out_dir"], "direct_release.json")))
        bdir = os.path.join(res["out_dir"], reldoc["bundles"][0]["path"])
        pp = os.path.join(bdir, "provenance.json")
        prov = json.load(open(pp))
        prov["run_binding"]["code_identity"]["canonical_digest"] = "deadbeef" * 2
        with open(pp, "w") as fh:
            json.dump(prov, fh)
        with pytest.raises(C.ContractError) as exc:
            C.load_and_normalize(rel_path, res["out_dir"])
        assert exc.value.reason == C.REFUSE_CODE_IDENTITY_DISAGREES
