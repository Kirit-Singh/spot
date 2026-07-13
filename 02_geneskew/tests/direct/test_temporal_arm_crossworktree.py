"""TRULY CROSS-WORKTREE: the PRODUCER'S checkout emits, THIS checkout verifies.

Not two imports in one process, and not a copy of the producer's fixtures living here — the
producer is executed FROM ITS OWN GIT CHECKOUT, at its own committed HEAD, in its own
subprocess, with only that checkout on ``sys.path``. This checkout then reopens the bytes
that landed and decides, in a separate subprocess, through its shipped CLI.

Why the distinction is the whole test: a verifier that re-runs a copy of the producer's
fixtures is verifying its own copy of the thing it is verifying. The two lanes must not be
able to agree because they are running the same code, and the only way to prove that is to
make them different processes reading different checkouts. Both exact commits are bound,
and each half asserts the other's rules never entered its process.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_W11_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_W11_ANALYSIS = os.path.join(_W11_REPO, "02_geneskew", "analysis")

# The PRODUCER's branch. Its LIVE worktree is deliberately NOT used: a working tree is
# somebody else's desk and it changes under you mid-test. What gets verified is a CLEAN
# checkout of the producer's COMMITTED head, materialised below — which is also the only
# thing a code identity can honestly be re-derived against.
_W5_BRANCH = "agent/stage2-temporal-arms"
# The AGGREGATE's branch. It is the READER of the external admission, and therefore it owns
# the filename, the schema, the id rule and the binding set. A producer of an artifact
# nobody can read has not produced it — so the admission is checked with the aggregate's
# OWN code, run from the aggregate's OWN committed checkout.
_W3_BRANCH = "agent/stage2-runmanifest-round4"


def _git(repo: str, *args: str) -> str:
    return subprocess.run(("git", "-C", repo) + args, capture_output=True, text=True,
                          check=True).stdout.strip()


def _producer_commit() -> str:
    """The producer commit THIS verifier was built against — never whatever the branch
    happens to point at when the test runs. The branch moves; a verification does not."""
    return _git(_W11_REPO, "merge-base", "HEAD", _W5_BRANCH)


def _detached(tmp_path_factory, name: str, branch: str):
    path = str(tmp_path_factory.mktemp(name) / "checkout")
    subprocess.run(("git", "-C", _W11_REPO, "worktree", "add", "--detach", path,
                    _git(_W11_REPO, "rev-parse", branch)),
                   capture_output=True, text=True, check=True)
    return path


@pytest.fixture(scope="module")
def aggregate_checkout(tmp_path_factory):
    """A CLEAN, detached checkout of the AGGREGATE's committed head."""
    path = _detached(tmp_path_factory, "w3", _W3_BRANCH)
    yield path
    subprocess.run(("git", "-C", _W11_REPO, "worktree", "remove", "--force", path),
                   capture_output=True, text=True)


# The aggregate's OWN checks, run in the aggregate's OWN process. Nothing of this lane is
# importable there: it is the reader, and it must accept the bytes on their own terms.
AGGREGATE_CHECK = r"""
import json, sys
sys.path.insert(0, {analysis!r})
from direct import verify_release_envelope as V

assert not [m for m in sys.modules if m.startswith("verify_temporal_arms")], \
    "the aggregate process imported the verifier"

root = {root!r}
inv, bad_inv = V.check_inventory(root, {n_bundles!r}, {n_arms!r})
adm, bad_adm = V.check_external_admission(root, inv, {verifier_id!r})
print(json.dumps({{"inventory": bad_inv, "admission": bad_adm}}))
"""


def _aggregate_reads(w3: str, root: str, n_bundles: int = 6, n_arms: int = 120):
    src = AGGREGATE_CHECK.format(
        analysis=os.path.join(w3, "02_geneskew", "analysis"), root=root,
        n_bundles=n_bundles, n_arms=n_arms,
        verifier_id="spot.stage02.temporal.arm.independent_verifier.v1")
    proc = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True,
                          cwd=w3)
    assert proc.returncode == 0, proc.stderr[-1500:]
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def producer_checkout(tmp_path_factory):
    """A CLEAN, detached checkout of the producer's COMMITTED head. Removed afterwards."""
    path = str(tmp_path_factory.mktemp("w5") / "checkout")
    subprocess.run(("git", "-C", _W11_REPO, "worktree", "add", "--detach", path,
                    _producer_commit()), capture_output=True, text=True, check=True)
    yield path
    subprocess.run(("git", "-C", _W11_REPO, "worktree", "remove", "--force", path),
                   capture_output=True, text=True)

# Emitted from the PRODUCER's checkout ONLY. Nothing of the verifier is importable there.
EMIT = r'''
import os, sys
sys.path.insert(0, {analysis!r})
sys.path.insert(0, {tests!r})
import fixtures_temporal_arms as P
from direct.temporal.arms import arm_direct_source as src
from direct.temporal.arms import arm_emit, arm_env

assert not [m for m in sys.modules if m.startswith("verify_temporal_arms")], \
    "the producer process imported the verifier"

out = {out!r}
os.makedirs(out, exist_ok=True)
stage1 = {stage1!r}
direct = {direct!r}
w10 = {w10!r}
admitted = P.admitted()
loaded = {{c: src.load_direct_bundle(direct[c], expect_condition=c, w10_report=w10[c])
          for c in P.CONDITIONS}}
lock = arm_env.env_lock_block({lock!r})
bundles = [P.build(a, b, scorer_view_sha256={view_sha!r}, stage1=stage1,
                   from_endpoints=src.endpoints(loaded[a], admitted),
                   to_endpoints=src.endpoints(loaded[b], admitted),
                   endpoint_source=src.source_binding(loaded[a], loaded[b]),
                   env_lock=lock)
           for a, b in P.ORDERED_PAIRS]
arm_emit.emit_release(bundles, out, expect_n_bundles=len(P.ORDERED_PAIRS))
print("EMITTED")
'''


def _emit_from_producer_checkout(w5: str, out_dir: str, view_sha: str, stage1,
                                 direct, w10, lock) -> None:
    geneskew = os.path.join(w5, "02_geneskew")
    src = EMIT.format(analysis=os.path.join(geneskew, "analysis"),
                      tests=os.path.join(geneskew, "tests", "direct"),
                      out=out_dir, view_sha=view_sha, stage1=stage1,
                      direct=direct, w10=w10, lock=lock)
    proc = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True,
                          cwd=w5)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "EMITTED" in proc.stdout


def _verify_from_this_checkout(w5: str, release_root: str, bundle_root: str, *extra,
                               env_lock: str = None, direct=None, w10=None):
    env = dict(os.environ, PYTHONPATH=_W11_ANALYSIS)
    # the detached replay uses the AUTHORITATIVE Stage-2 lock (2983d140…) and the frozen
    # default pin — the same lock bytes Direct, pathway and the real run are pinned to
    lock = ["--env-lock", env_lock] if env_lock else []
    for cond, path in (direct or {}).items():
        lock += ["--direct-bundle", f"{cond}:{path}"]
    for cond, path in (w10 or {}).items():
        lock += ["--w10-report", f"{cond}:{path}"]
    proc = subprocess.run(
        [sys.executable, "-m", "verify_temporal_arms.cli",
         "--stage1-release-root", release_root, "--bundle-root", bundle_root,
         "--producer-checkout", w5, *lock, *extra],
        capture_output=True, text=True, env=env, cwd=_W11_REPO)
    return proc.returncode, json.loads(proc.stdout)


def _stage(w5, tmp_path):
    """Emit from the producer's checkout. The bytes are its own; nothing is repaired."""
    sys.path.insert(0, _HERE)
    import fixtures_arm_verifier as FX
    from verify_temporal_arms import release as R

    release_root = FX.stage_release(os.path.join(str(tmp_path), "stage1"))
    bundle_root = os.path.join(str(tmp_path), "temporal")
    bound = R.load_release(release_root)
    stage1 = {
        "release_self_sha256": bound.release_self_sha256,
        "scorer_view_raw_sha256": bound.scorer_view_raw_sha256,
        "scorer_view_canonical_sha256": bound.scorer_view_sha256,
        "selector_condition_sequence": list(bound.conditions),
        "per_program_projection_sha256": dict(bound.program_projection_sha256),
        "registry_scorer_projection_sha256": bound.scorer_projection_sha256,
    }
    direct, w10 = FX.stage_direct_bundles(os.path.join(str(tmp_path), "direct"))
    lock = FX.stage_env_lock(os.path.join(str(tmp_path), "env"))
    _emit_from_producer_checkout(w5, bundle_root, bound.scorer_view_sha256, stage1,
                                 direct, w10, lock)
    return release_root, bundle_root, lock, direct, w10


class TestTheProducerAndTheVerifierRunFromDifferentCheckouts:

    def test_producer_emits_and_this_checkout_admits_and_signs(
            self, producer_checkout, tmp_path):
        release_root, bundle_root, lock, direct, w10 = _stage(
            producer_checkout, tmp_path)
        code, report = _verify_from_this_checkout(
            producer_checkout, release_root, bundle_root, "--sign", env_lock=lock,
            direct=direct, w10=w10)

        assert code == 0, report["failures"]
        assert report["verdict"] == "ADMIT"
        assert report["counts"]["n_bundles"] == 6
        assert report["counts"]["n_logical_arms"] == 120
        assert report["n_base_deltas_rederived"] == 360
        assert report["producer_self_report_trusted"] is False

        # ONE envelope, at the RELEASE ROOT, signed by THIS lane...
        assert report["external_verification_envelope"] == \
            "temporal_arm_external_admission.json"
        with open(os.path.join(bundle_root, "temporal_arm_external_admission.json")) as fh:
            env = json.load(fh)
        assert env["verifier_id"] == "spot.stage02.temporal.arm.independent_verifier.v1"
        assert env["verdict"] == "ADMIT"
        assert env["generator_is_not_verifier"] is True
        assert env["binds"]["producer_release_id"]
        assert env["binds"]["producer_release_raw_sha256"]
        assert env["report_id"] and len(env["report_id"]) == 64
        assert len(env["binds"]["bundles"]) == 6
        assert env["gate_inventory"]

        # ...and the producer's own directories are exactly as it left them.
        for d in sorted(os.listdir(bundle_root)):
            if os.path.isdir(os.path.join(bundle_root, d)):
                assert not os.path.exists(
                    os.path.join(bundle_root, d, "temporal_arm_external_admission.json"))

    def test_the_admission_binds_the_producers_exact_commit(
            self, producer_checkout, tmp_path):
        """The verdict names WHICH build it admitted, and that build is RE-DERIVED from the
        pinned checkout — not read out of the artifact that is being judged."""
        release_root, bundle_root, lock, direct, w10 = _stage(
            producer_checkout, tmp_path)
        code, _ = _verify_from_this_checkout(
            producer_checkout, release_root, bundle_root, "--sign", env_lock=lock,
            direct=direct, w10=w10)
        assert code == 0

        with open(os.path.join(bundle_root, "temporal_arm_external_admission.json")) as fh:
            env = json.load(fh)
        assert env["binds"]["code_identity"]["commit"] == _producer_commit()
        assert env["binds"]["code_identity"]["clean_tree"] is True
        assert "code_identity_rederives_from_the_pinned_checkout" in env["gate_inventory"]
        assert "the_pinned_producer_checkout_is_clean" in env["gate_inventory"]

    def test_a_missing_producer_inventory_fails(self, producer_checkout, tmp_path):
        """The root inventory is MANDATORY: without it there is nothing to verify AGAINST,
        only a directory to look at."""
        release_root, bundle_root, lock, direct, w10 = _stage(
            producer_checkout, tmp_path)
        os.remove(os.path.join(bundle_root, "temporal_arm_release.json"))

        code, report = _verify_from_this_checkout(
            producer_checkout, release_root, bundle_root, env_lock=lock,
            direct=direct, w10=w10)
        assert code == 1
        assert "the_producer_release_inventory_is_on_disk" in \
            {x["gate"] for x in report["failures"]}

    def test_a_mutated_producer_inventory_fails(self, producer_checkout, tmp_path):
        """The inventory is content-addressed over its own bytes."""
        release_root, bundle_root, lock, direct, w10 = _stage(
            producer_checkout, tmp_path)
        path = os.path.join(bundle_root, "temporal_arm_release.json")
        with open(path) as fh:
            inv = json.load(fh)
        inv["n_logical_arms"] = 119
        with open(path, "w") as fh:
            json.dump(inv, fh, sort_keys=True, separators=(",", ":"))

        code, report = _verify_from_this_checkout(
            producer_checkout, release_root, bundle_root, env_lock=lock,
            direct=direct, w10=w10)
        assert code == 1
        assert "the_inventory_release_id_covers_its_own_content" in \
            {x["gate"] for x in report["failures"]}

    def test_a_verdict_file_planted_in_a_producer_bundle_dir_fails(
            self, producer_checkout, tmp_path):
        """Six per-bundle verdicts are not an external admission — they are the producer's
        directories, and the external verdict lives once, at the root."""
        release_root, bundle_root, lock, direct, w10 = _stage(
            producer_checkout, tmp_path)
        for d in sorted(os.listdir(bundle_root)):
            p = os.path.join(bundle_root, d)
            if os.path.isdir(p):
                with open(os.path.join(p, "temporal_verification.json"), "w") as fh:
                    json.dump({"verdict": "ADMIT"}, fh)

        code, report = _verify_from_this_checkout(
            producer_checkout, release_root, bundle_root, env_lock=lock,
            direct=direct, w10=w10)
        assert code == 1
        assert "no_verdict_file_inside_a_producer_bundle_directory" in \
            {x["gate"] for x in report["failures"]}

    def test_the_envelope_binds_the_ranking_bytes_a_consumer_must_recheck(
            self, producer_checkout, tmp_path):
        """W3 must be able to refuse a RESEALED rank-swap. It can only do that against a
        binding the producer did not write: this lane's envelope records the hash of every
        ranking file it actually reopened and RE-RANKED."""
        release_root, bundle_root, lock, direct, w10 = _stage(
            producer_checkout, tmp_path)
        code, _ = _verify_from_this_checkout(
            producer_checkout, release_root, bundle_root, "--sign", env_lock=lock,
            direct=direct, w10=w10)
        assert code == 0
        with open(os.path.join(bundle_root, "temporal_arm_external_admission.json")) as fh:
            env = json.load(fh)

        assert env["binds"]["rankings_digest"]
        rankings = env["binds"]["bundles"][0]["rankings"]
        assert len(rankings) == 20                      # every arm of the bundle
        # the recorded hash IS the byte on disk, so a consumer can recompute it
        d = os.path.join(bundle_root, env["binds"]["bundles"][0]["dir"])
        for binding in rankings.values():
            with open(os.path.join(d, binding["path"]), "rb") as fh:
                raw = fh.read()
            assert binding["raw_sha256"] == hashlib.sha256(raw).hexdigest()

    def test_a_resealed_rank_swap_is_refused_and_moves_the_envelope_binding(
            self, producer_checkout, tmp_path):
        """Swap two ranks inside a ranking file and reseal the producer's inventory around
        it. The producer's own artifacts all agree; the arm's bound hash does not."""
        release_root, bundle_root, lock, direct, w10 = _stage(
            producer_checkout, tmp_path)
        d = os.path.join(bundle_root, sorted(
            x for x in os.listdir(bundle_root)
            if os.path.isdir(os.path.join(bundle_root, x)))[0])
        rpath = os.path.join(d, sorted(
            os.path.join("rankings", r) for r in os.listdir(os.path.join(d, "rankings")))[0])
        with open(rpath) as fh:
            ranking = json.load(fh)
        ranked = [r for r in ranking["ranked"] if r["rank"] is not None]
        ranked[0]["rank"], ranked[1]["rank"] = ranked[1]["rank"], ranked[0]["rank"]
        with open(rpath, "w") as fh:
            json.dump(ranking, fh, sort_keys=True, separators=(",", ":"))

        code, report = _verify_from_this_checkout(
            producer_checkout, release_root, bundle_root, env_lock=lock,
            direct=direct, w10=w10)
        assert code == 1
        assert "the_ranking_file_raw_sha256_matches_the_bytes_on_disk" in \
            {x["gate"] for x in report["failures"]}

    def test_the_AGGREGATE_reads_and_accepts_what_this_lane_signed(
            self, producer_checkout, aggregate_checkout, tmp_path):
        """THE CONTRACT, END TO END, ACROSS THREE CHECKOUTS: the producer emits, this lane
        admits, and the AGGREGATE — reading with its own code, in its own process — accepts
        the inventory AND the external admission. One filename, one schema, one binding set."""
        release_root, bundle_root, lock, direct, w10 = _stage(
            producer_checkout, tmp_path)
        code, _ = _verify_from_this_checkout(
            producer_checkout, release_root, bundle_root, "--sign", env_lock=lock,
            direct=direct, w10=w10)
        assert code == 0

        result = _aggregate_reads(aggregate_checkout, bundle_root)
        assert result["inventory"] == [], result["inventory"]
        assert result["admission"] == [], result["admission"]

    def test_the_aggregate_refuses_an_admission_over_a_DIFFERENT_release(
            self, producer_checkout, aggregate_checkout, tmp_path):
        """An envelope that admits a different release is an admission of something else."""
        release_root, bundle_root, lock, direct, w10 = _stage(
            producer_checkout, tmp_path)
        code, _ = _verify_from_this_checkout(
            producer_checkout, release_root, bundle_root, "--sign", env_lock=lock,
            direct=direct, w10=w10)
        assert code == 0

        path = os.path.join(bundle_root, "temporal_arm_external_admission.json")
        with open(path) as fh:
            env = json.load(fh)
        env["binds"]["producer_release_id"] = "0" * 64
        env.pop("report_id")
        env["report_id"] = hashlib.sha256(
            json.dumps(env, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True).encode()).hexdigest()
        with open(path, "w") as fh:
            json.dump(env, fh, sort_keys=True, separators=(",", ":"))

        result = _aggregate_reads(aggregate_checkout, bundle_root)
        assert result["admission"], "the aggregate accepted an admission of another release"

    def test_the_aggregate_refuses_a_release_with_no_external_admission(
            self, producer_checkout, aggregate_checkout, tmp_path):
        """The producer's per-bundle preflight admits nothing."""
        release_root, bundle_root, lock, direct, w10 = _stage(
            producer_checkout, tmp_path)
        result = _aggregate_reads(aggregate_checkout, bundle_root)
        assert result["inventory"] == [], result["inventory"]
        assert result["admission"], "the aggregate admitted a release nobody verified"

    def test_the_FULL_PRODUCTION_CLI_admits_and_leaves_producer_bytes_untouched(
            self, producer_checkout, tmp_path):
        """THE PRODUCTION INVOCATION, exactly as an aggregate runs it — every flag, through
        the shipped parser, in its own process.

        And the thing an aggregate has to be able to trust: the verifier REOPENS the
        producer's root inventory and WRITES ONE file beside it, and it changes NOTHING the
        producer wrote. Proved by hashing every producer byte before and after."""
        import hashlib

        sys.path.insert(0, _HERE)
        import fixtures_arm_verifier as FX

        release_root, bundle_root, lock, direct, w10 = _stage(producer_checkout, tmp_path)

        def snapshot():
            out = {}
            for dirpath, _, names in os.walk(bundle_root):
                for n in sorted(names):
                    fp = os.path.join(dirpath, n)
                    rel = os.path.relpath(fp, bundle_root)
                    with open(fp, "rb") as fh:
                        out[rel] = hashlib.sha256(fh.read()).hexdigest()
            return out

        before = snapshot()
        # the producer's MANDATORY root inventory is there to be reopened
        assert "temporal_arm_release.json" in before
        assert "temporal_arm_external_admission.json" not in before

        env = dict(os.environ, PYTHONPATH=_W11_ANALYSIS)
        argv = [sys.executable, "-m", "verify_temporal_arms.cli",
                "--stage1-release-root", release_root,
                "--bundle-root", bundle_root,
                "--producer-checkout", producer_checkout,
                "--env-lock", lock,
                "--expect-conditions", *FX.CONDITIONS,
                "--sign"]
        for cond, path in direct.items():
            argv += ["--direct-bundle", f"{cond}:{path}"]
        for cond, path in w10.items():
            argv += ["--w10-report", f"{cond}:{path}"]

        proc = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=_W11_REPO)
        assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-800:]
        report = json.loads(proc.stdout)
        assert report["verdict"] == "ADMIT"

        after = snapshot()

        # ONE new file, at the RELEASE ROOT, and it is ours
        added = sorted(set(after) - set(before))
        assert added == ["temporal_arm_external_admission.json"], added

        # EVERY producer byte is exactly as the producer left it
        changed = sorted(k for k in before if after[k] != before[k])
        assert changed == [], f"the verifier rewrote producer bytes: {changed}"

        with open(os.path.join(bundle_root,
                               "temporal_arm_external_admission.json")) as fh:
            envelope = json.load(fh)
        assert envelope["schema_version"] == \
            "spot.stage02_temporal_arm_external_admission.v1"
        assert envelope["verifier_id"] == \
            "spot.stage02.temporal.arm.independent_verifier.v1"
        assert envelope["verdict"] == "ADMIT"
        assert len(envelope["report_id"]) == 64
        assert envelope["binds"]["producer_release_id"]
        assert envelope["binds"]["env_lock_sha256"] == FX.env_lock_sha256()

    def test_the_admission_can_be_FILED_AT_THE_AGGREGATE_ROOT_leaving_the_native_root_intact(
            self, producer_checkout, tmp_path):
        """THE AGGREGATE'S SHAPE: read OUT/temporal (the producer's native root), write the
        receipt at OUT/. The verifier still reads the native inventory and still writes
        NOTHING into the producer's root — the path is not the binding, and the admission
        still names the exact release it admits."""
        import hashlib

        sys.path.insert(0, _HERE)

        release_root, bundle_root, lock, direct, w10 = _stage(producer_checkout, tmp_path)

        # the aggregate root is the PARENT of the producer's native temporal root
        agg_root = os.path.dirname(os.path.abspath(bundle_root))
        admission = os.path.join(agg_root, "temporal_arm_external_admission.json")

        def snapshot():
            out = {}
            for dirpath, _, names in os.walk(bundle_root):
                for n in sorted(names):
                    fp = os.path.join(dirpath, n)
                    with open(fp, "rb") as fh:
                        out[os.path.relpath(fp, bundle_root)] = \
                            hashlib.sha256(fh.read()).hexdigest()
            return out

        before = snapshot()
        assert "temporal_arm_release.json" in before      # the native inventory is READ

        env = dict(os.environ, PYTHONPATH=_W11_ANALYSIS)
        argv = [sys.executable, "-m", "verify_temporal_arms.cli",
                "--stage1-release-root", release_root,
                "--bundle-root", bundle_root,                 # the NATIVE producer root
                "--admission-out", admission,                 # ...the AGGREGATE's root
                "--producer-checkout", producer_checkout,
                "--env-lock", lock, "--sign"]
        for cond, path in direct.items():
            argv += ["--direct-bundle", f"{cond}:{path}"]
        for cond, path in w10.items():
            argv += ["--w10-report", f"{cond}:{path}"]

        proc = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=_W11_REPO)
        assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-500:]
        assert json.loads(proc.stdout)["verdict"] == "ADMIT"

        # the receipt is at the AGGREGATE root...
        assert os.path.exists(admission)
        # ...the producer's native root is BIT-IDENTICAL, and gained nothing
        after = snapshot()
        assert after == before, "the verifier touched the producer's native root"
        assert "temporal_arm_external_admission.json" not in after

        # ...and the receipt still names the exact release it admits, from over there
        with open(admission) as fh:
            envelope = json.load(fh)
        with open(os.path.join(bundle_root, "temporal_arm_release.json"), "rb") as fh:
            inv_raw = fh.read()
        assert envelope["binds"]["producer_release_raw_sha256"] == \
            hashlib.sha256(inv_raw).hexdigest()
        assert envelope["binds"]["producer_release_id"] == json.loads(inv_raw)["release_id"]

    def test_a_REJECT_is_a_nonzero_exit_code_from_the_production_cli(
            self, producer_checkout, tmp_path):
        """A rejected release is an exit code, not a log line an aggregate has to read."""
        sys.path.insert(0, _HERE)
        import fixtures_arm_verifier as FX

        release_root, bundle_root, lock, direct, w10 = _stage(producer_checkout, tmp_path)
        env = dict(os.environ, PYTHONPATH=_W11_ANALYSIS)
        proc = subprocess.run(
            [sys.executable, "-m", "verify_temporal_arms.cli",
             "--stage1-release-root", release_root, "--bundle-root", bundle_root,
             "--producer-checkout", producer_checkout, "--env-lock", lock,
             # the time axis, reversed: a different claim about which way time runs
             "--expect-conditions", *reversed(FX.CONDITIONS)],
            capture_output=True, text=True, env=env, cwd=_W11_REPO)
        assert proc.returncode == 1
        report = json.loads(proc.stdout)
        assert report["verdict"] == "REJECT"
        assert "release_conditions_match_the_pinned_universe" in \
            {x["gate"] for x in report["failures"]}

    def test_the_integration_CONTRACT_is_emitted_as_bytes_and_cannot_drift(self):
        """An aggregate BINDS this instead of transcribing it. A contract copied by hand is
        a contract that drifts, and the drift is invisible until a release is admitted
        against the wrong thing — so every field here is asserted against the constants the
        verifier actually runs on, not against a copy of them."""
        from verify_temporal_arms import direct_source, schema, verify

        env = dict(os.environ, PYTHONPATH=_W11_ANALYSIS)
        proc = subprocess.run(
            [sys.executable, "-m", "verify_temporal_arms.cli", "--print-contract"],
            capture_output=True, text=True, env=env, cwd=_W11_REPO)
        assert proc.returncode == 0, proc.stderr[-500:]
        c = json.loads(proc.stdout)

        assert c["verifier_id"] == verify.VERIFIER_ID
        # what it READS: the producer-native inventory, and nothing generic
        assert c["reads"]["producer_inventory_file"] == schema.INVENTORY_FILENAME
        assert c["reads"]["producer_inventory_schema"] == schema.SCHEMA_INVENTORY
        assert c["reads"]["producer_inventory_is_mandatory"] is True
        assert c["reads"]["generic_or_copied_inventory_accepted"] is False
        # what it WRITES: one file, beside it, and nothing of the producer's
        assert c["writes"]["external_admission_file"] == schema.ENVELOPE_FILENAME
        assert c["writes"]["external_admission_schema"] == schema.SCHEMA_ENVELOPE
        assert c["writes"]["producer_bytes_modified"] is False
        assert c["writes"]["producer_root_written_into"] is False
        assert c["writes"]["override_flag"] == "--admission-out FILE"
        assert c["writes"]["path_is_not_the_binding"] is True
        # what --w10-report must SAY
        req = c["w10_admission_document"]["required_fields"]
        assert req["admitted"] is True and req["self_admitted"] is False
        assert direct_source.PENDING_VERDICT in req["verdict"]
        assert c["w10_admission_document"]["must_not_be"]["path"].endswith(
            direct_source.VERIFICATION_FILE)
        assert c["exit_codes"] == {"0": "ADMIT", "1": "REJECT"}

    def test_the_print_flags_need_no_release_but_everything_else_does(self):
        """A missing root is an ERROR, not a default: a verifier that guessed one would bind
        to whatever release happened to be on the machine that ran it."""
        env = dict(os.environ, PYTHONPATH=_W11_ANALYSIS)
        bad = subprocess.run(
            [sys.executable, "-m", "verify_temporal_arms.cli", "--sign"],
            capture_output=True, text=True, env=env, cwd=_W11_REPO)
        assert bad.returncode != 0
        assert "--stage1-release-root" in bad.stderr and "--bundle-root" in bad.stderr

    def test_neither_process_imports_the_others_rules(self):
        """Asserted in the process that actually ran, not by reading the source."""
        env = dict(os.environ, PYTHONPATH=_W11_ANALYSIS)
        out = subprocess.run(
            [sys.executable, "-c",
             "import sys, verify_temporal_arms.verify; "
             "print([m for m in sys.modules if m.startswith('direct')])"],
            capture_output=True, text=True, env=env, cwd=_W11_REPO, check=True).stdout
        assert out.strip() == "[]", f"the verifier pulled in the producer: {out}"
