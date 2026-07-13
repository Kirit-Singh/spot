"""THE PRODUCTION COMMAND: a release is exactly its lanes, and only what was admitted.

`run_release` discovers bundles, builds the per-lane inventories (Direct 3, temporal 6,
pathway 6), assembles the aggregate manifest, and hands it to the SEPARATE verifier. It
launches no compute.

Every bundle here is a FIXTURE. What is real is the refusal.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil

import fixtures_run_manifest as F
import pytest
from direct import release_inventory as RI
from direct import run_release
from direct.arm_topology import RunManifestError


class _Args:
    """The exact invocation W7 issues. No path is inferred."""

    def __init__(self, run, tmp_path, **kw):
        self.bundles_root = run["root"]
        self.release = run["release_path"]
        self.release_root = run["release_root"]
        self.env_lock = run["env_lock"]
        self.expect_env_lock_sha256 = F.env_lock_sha256(run)
        self.expect_release_sha256 = run["expect_release_sha256"]
        self.expect_gene_sets = run["pinned_gene_sets"]
        self.expect_verifiers = run["pinned_verifiers"]
        self.expected_code_identity = run["expected_code_identity"]
        self.producer_commit = "fc9bdcd"
        self.verifier_commit = "99eaa81"
        self.out = os.path.join(str(tmp_path), "release_manifest.json")
        self.verify = False
        for k, v in kw.items():
            setattr(self, k, v)


class TestTheReleaseIsExactlyItsLanes:
    def test_the_lane_counts_are_3_and_6_and_6(self, tmp_path):
        run = F.complete_run(tmp_path)
        doc = run_release.assemble(_Args(run, tmp_path))
        inv = doc["release_assembly"]["lane_inventories"]

        assert inv["direct"]["n_bundles"] == 3
        assert inv["temporal"]["n_bundles"] == 6
        assert inv["pathway"]["n_bundles"] == 6
        assert doc["n_bundles"] == 15
        assert doc["n_bound_arm_slots"] == 300

    def test_the_expected_count_is_DERIVED_not_declared(self):
        # 3 conditions, 2 sources: direct 3, temporal 3x2=6 ordered pairs, pathway 3x2=6
        assert RI.expected_bundle_count("direct", 3, 2) == 3
        assert RI.expected_bundle_count("temporal", 3, 2) == 6
        assert RI.expected_bundle_count("pathway", 3, 2) == 6
        # ...and it moves with the release, because nothing here is hard-coded
        assert RI.expected_bundle_count("temporal", 4, 2) == 12

    def test_it_LAUNCHES_NO_COMPUTE(self, tmp_path):
        run = F.complete_run(tmp_path)
        doc = run_release.assemble(_Args(run, tmp_path))
        assert doc["release_assembly"]["launched_compute"] is False

    def test_P2S_is_indexed_BESIDE_the_release_never_inside_it(self, tmp_path):
        run = F.complete_run(tmp_path)
        doc = run_release.assemble(_Args(run, tmp_path))
        p2s = doc["release_assembly"]["perturb2state"]

        assert p2s["tier"] == "secondary_method"
        assert p2s["gates_the_release"] is False
        # a secondary method that could move a primary ranking would not be secondary
        assert p2s["may_change_a_direct_arm_value_or_rank"] is False
        assert p2s["indexed_beside_the_release_never_inside_it"] is True
        # and it is NOT one of the release's bundles
        assert all(b["lane"] != "perturb2state" for b in doc["bundles"])

    def test_the_release_binds_producer_verifier_stage1_lock_and_counts(self, tmp_path):
        run = F.complete_run(tmp_path)
        doc = run_release.assemble(_Args(run, tmp_path))
        a = doc["release_assembly"]

        assert a["producer_commit"] == "fc9bdcd"
        assert a["verifier_commit"] == "99eaa81"
        assert a["solver_lock_sha256"] == F.env_lock_sha256(run)
        assert doc["stage1_v3_release"]["release_canonical_sha256"]
        assert doc["n_expected_arm_slots"] == 300

    def test_no_p_no_q_no_fixed_pair_no_combined_objective(self, tmp_path):
        run = F.complete_run(tmp_path)
        doc = run_release.assemble(_Args(run, tmp_path))
        printed = json.dumps(doc, default=str).lower()

        assert doc["combined_objective"] is None
        assert doc["cross_arm_score_or_order"] is None
        assert doc["combined_objective_permitted"] is False
        assert doc["emits_p_q_or_fdr"] is False
        for banned in ('"p_value"', '"q_value"', '"fdr"', '"balanced_skew"'):
            assert banned not in printed


class TestOnlyADMITTEDBytesEnterARelease:
    def test_an_UNADMITTED_lane_may_not_be_RELEASED(self, tmp_path):
        run = F.complete_run(tmp_path)
        F.write_native_admission(run, "direct", verdict="REFUSE", admitted=False)

        with pytest.raises(RunManifestError, match="NOT independently admitted"):
            run_release.assemble(_Args(run, tmp_path))

    def test_a_MISSING_lane_admission_may_not_be_RELEASED(self, tmp_path):
        run = F.complete_run(tmp_path)
        os.remove(os.path.join(run["root"], "temporal_arm_external_admission.json"))

        with pytest.raises(RunManifestError, match="NOT independently admitted"):
            run_release.assemble(_Args(run, tmp_path))

    def test_a_SELF_ADMITTED_lane_may_not_be_RELEASED(self, tmp_path):
        run = F.complete_run(tmp_path)
        F.write_native_admission(run, "direct", self_admitted=True)

        with pytest.raises(RunManifestError, match="NOT independently admitted"):
            run_release.assemble(_Args(run, tmp_path))


class TestTheFourAssemblyAttacks:
    def test_MISSING_a_bundle_is_REFUSED(self, tmp_path):
        run = F.complete_run(tmp_path)
        shutil.rmtree(run["temporal"][0])          # 5 ordered pairs, not 6
        run["temporal"] = run["temporal"][1:]
        F.seal_release(run)

        with pytest.raises(RunManifestError, match="exactly 6"):
            run_release.assemble(_Args(run, tmp_path))

    def test_a_DUPLICATE_bundle_is_REFUSED(self, tmp_path):
        run = F.complete_run(tmp_path)
        # a copy of an existing bundle, in a new directory: the count is right and the
        # bundle_id is not
        shutil.copytree(run["direct"][0],
                        os.path.join(os.path.dirname(run["direct"][0]), "COPY-of-Rest"))
        F.seal_release(run)

        with pytest.raises(RunManifestError, match="exactly 3|more than once"):
            run_release.assemble(_Args(run, tmp_path))

    def test_a_STALE_bundle_from_an_earlier_run_is_REFUSED(self, tmp_path):
        run = F.complete_run(tmp_path)
        stale = os.path.join(os.path.dirname(run["pathway"][0]), "STALE-earlier-run")
        shutil.copytree(run["pathway"][0], stale)
        # it is a REAL bundle — it is simply not part of THIS release
        F.seal_release(run)

        with pytest.raises(RunManifestError, match="exactly 6|more than once"):
            run_release.assemble(_Args(run, tmp_path))

    def test_a_SWAPPED_LANE_bundle_is_REFUSED(self, tmp_path):
        """A temporal bundle relabelled `direct`: the counts still look right."""
        run = F.complete_run(tmp_path)
        d = run["temporal"][0]
        inv = json.load(open(os.path.join(d, "arm_bundle.json")))
        inv["lane"] = "direct"                     # now discovered as a 4th Direct bundle
        with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
            json.dump(inv, fh, indent=2, sort_keys=True)
        F.seal_release(run)

        with pytest.raises(RunManifestError, match="exactly 3|exactly 6"):
            run_release.assemble(_Args(run, tmp_path))


class TestTheProducerShipsPENDINGAndStaysThatWay:
    """The correction. W10 does NOT fill in `direct_release.json` — it GATES that nobody did.

    I had modelled Direct as "admitted in place": the verifier writing verdict/admitted/
    self_admitted/verifier_id into the producer's own file. That was wrong, and wrong in the
    dangerous direction — an aggregate that TOLERATED an admitted producer file would have
    been tolerating a file somebody had EDITED. The admission is a SEPARATE report.
    """

    def test_the_producer_release_is_PENDING_and_the_admission_is_SEPARATE(self, tmp_path):
        run = F.complete_run(tmp_path)
        prod = json.load(open(os.path.join(run["root"], "direct_release.json")))

        assert prod["verdict"] == "pending_independent_verification"
        assert prod["admitted"] is False
        assert prod["self_admitted"] is False
        assert prod["verifier_id"] is None

        # ...and the admission is a DIFFERENT artifact, which BINDS it
        adm = json.load(open(os.path.join(run["root"],
                                          "direct_release_admission.json")))
        assert adm["schema_version"] == "spot.stage02_direct_release_verification.v1"
        assert adm["verdict"] == "ADMIT"                    # native, uppercase
        assert (adm["bound_artifact"]["direct_release_sha256"]
                == prod["direct_release_sha256"])

    def test_an_ADMITTED_producer_file_is_REFUSED(self, tmp_path):
        # exactly what my earlier model would have waved through
        run = F.complete_run(tmp_path)
        path = os.path.join(run["root"], "direct_release.json")
        prod = json.load(open(path))
        prod.update({"verdict": "ADMIT", "admitted": True,
                     "verifier_id": "spot.stage02.direct.release.verifier.v1"})
        with open(path, "w") as fh:
            json.dump(prod, fh, indent=2, sort_keys=True)

        with pytest.raises(RunManifestError, match="NOT independently admitted"):
            run_release.assemble(_Args(run, tmp_path))

    def test_an_admission_bound_to_ANOTHER_release_is_REFUSED(self, tmp_path):
        run = F.complete_run(tmp_path)
        path = os.path.join(run["root"], "direct_release_admission.json")
        adm = json.load(open(path))
        adm["bound_artifact"]["direct_release_sha256"] = "9" * 64
        adm["report_sha256"] = F._canon(
            {k: v for k, v in adm.items() if k != "report_sha256"})
        with open(path, "w") as fh:
            json.dump(adm, fh, indent=2, sort_keys=True)

        with pytest.raises(RunManifestError, match="NOT independently admitted"):
            run_release.assemble(_Args(run, tmp_path))


class TestTheCapturedCLI:
    def test_the_CLI_REFUSES_without_every_explicit_input(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf), pytest.raises(SystemExit):
            run_release.main(["--bundles-root", "r"])
        err = buf.getvalue()
        for flag in ("--release", "--release-root", "--env-lock", "--out"):
            assert flag in err, flag

    def test_the_CLI_ASSEMBLES_and_then_hands_off_to_the_SEPARATE_verifier(
            self, tmp_path):
        run = F.complete_run(tmp_path)
        out = os.path.join(str(tmp_path), "m.json")
        argv = [
            "--bundles-root", run["root"],
            "--release", run["release_path"],
            "--release-root", run["release_root"],
            "--env-lock", run["env_lock"],
            "--expect-env-lock-sha256", F.env_lock_sha256(run),
            "--expect-release-sha256", run["expect_release_sha256"],
            "--expect-gene-sets", run["pinned_gene_sets"],
            "--expect-verifiers", run["pinned_verifiers"],
            "--expected-code-identity", run["expected_code_identity"],
            "--producer-commit", "fc9bdcd", "--verifier-commit", "99eaa81",
            "--out", out, "--verify",
        ]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = run_release.main(argv)
        printed = buf.getvalue()

        assert rc == 0, printed
        assert os.path.exists(out)
        # the exit code is the VERIFIER's: this command does not certify its own output
        assert '"aggregate_verdict": "admit"' in printed
        assert '"n_failed": 0' in printed

    def test_the_CLI_EXITS_NONZERO_when_the_separate_verifier_REFUSES(self, tmp_path):
        run = F.complete_run(tmp_path)
        out = os.path.join(str(tmp_path), "m.json")
        # admitted lanes, complete topology... and a bundle built by a different method
        F.seal_release(run)
        path = os.path.join(run["temporal"][0], "temporal_provenance.json")
        doc = json.load(open(path))
        doc["run_binding"]["temporal_method_sha256"] = "f" * 64
        with open(path, "w") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
        F.seal_release(run)

        argv = [
            "--bundles-root", run["root"], "--release", run["release_path"],
            "--release-root", run["release_root"], "--env-lock", run["env_lock"],
            "--expect-env-lock-sha256", F.env_lock_sha256(run),
            "--expect-release-sha256", run["expect_release_sha256"],
            "--expect-gene-sets", run["pinned_gene_sets"],
            "--expect-verifiers", run["pinned_verifiers"],
            "--expected-code-identity", run["expected_code_identity"],
            "--out", out, "--verify",
        ]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = run_release.main(argv)

        assert rc == 1
        assert '"aggregate_verdict": "reject"' in buf.getvalue()
