"""THE SOLVER-LOCK GATE. Committing the lock file was necessary and NOT sufficient.

The pathway verifier's finding was exactly right: `c1f8e80` added the lock as a FILE, and the
lock hash was nowhere in any bundle or run identity. `runid.env_lock_block` hashed whatever
path it was handed and reported `environment_lock_not_supplied` when handed none — it never
checked the file WAS the lock, and it never refused.

Recording a lock BESIDE a run says which environment the producer HAD.
Binding it INTO the run id says which environment the numbers CAME FROM.
Only the second one survives a swap, and only the second one is a gate.

Three properties, one per lane:
  * a MISSING lock REFUSES at a named gate
  * a SWAPPED lock REFUSES at a named gate — including the STAGE-1 lock, which is the mistake
    somebody will actually make: it is a real, honest, content-addressed solver lock, just for
    a different environment
  * an admitted lock's FULL sha256 is INSIDE the run identity, so the id moves if it changes
"""
from __future__ import annotations

import json
import os

import pytest
from direct import envlock, run_arms, run_pathway_arms
from direct import signature_matrix as sm
from direct.hashing import canonical_json, sha256_hex
from fixtures_pathway import write_gene_sets
from fixtures_spec import TARGET_GENES, UNIVERSE

PINNED = envlock.EXPECTED_SHA256


class TestThePinItself:
    def test_the_pinned_lock_is_the_one_W7_handed_over(self):
        assert PINNED == \
            "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe"

    def test_the_shipped_lock_file_hashes_to_the_pin(self):
        assert envlock.verify(envlock.DEFAULT_PATH)["sha256"] == PINNED

    def test_a_MISSING_lock_is_REFUSED_at_a_named_gate(self):
        with pytest.raises(envlock.EnvLockError) as exc:
            envlock.verify(None)
        assert exc.value.gate == envlock.REFUSE_ABSENT

    def test_a_NONEXISTENT_path_is_REFUSED(self, tmp_path):
        with pytest.raises(envlock.EnvLockError) as exc:
            envlock.verify(str(tmp_path / "nope.txt"))
        assert exc.value.gate == envlock.REFUSE_ABSENT

    def test_a_SWAPPED_lock_is_REFUSED_at_a_named_gate(self, tmp_path):
        other = tmp_path / "stage02_solver_lock.txt"
        other.write_text("# a plausible-looking lock that is not the pinned one\n")
        with pytest.raises(envlock.EnvLockError) as exc:
            envlock.verify(str(other))
        assert exc.value.gate == envlock.REFUSE_MISMATCH

    def test_the_STAGE1_lock_is_REFUSED_and_SAYS_WHY(self, tmp_path):
        # the mistake somebody will actually make: a real, honest, content-addressed solver
        # lock — for a different environment. A hash mismatch alone would not explain it.
        s1 = tmp_path / "stage01_solver_lock.txt"
        s1.write_text("# Stage-1 lock: conda scvi_gpu, python 3.11.15, pyarrow 24.0.0\n")
        with pytest.raises(envlock.EnvLockError) as exc:
            envlock.verify(str(s1))
        assert exc.value.gate == envlock.REFUSE_MISMATCH
        assert "STAGE-1" in str(exc.value)

    def test_a_TRUNCATED_lock_is_REFUSED(self, tmp_path):
        # one byte short of the real thing
        p = tmp_path / "stage02_solver_lock.txt"
        with open(envlock.DEFAULT_PATH, "rb") as fh:
            p.write_bytes(fh.read()[:-1])
        with pytest.raises(envlock.EnvLockError) as exc:
            envlock.verify(str(p))
        assert exc.value.gate == envlock.REFUSE_MISMATCH


class TestTheDIRECTLane:
    """3 of the 15 production invocations."""

    def _args(self, synthetic_run, tmp_path):
        args = synthetic_run()
        args.condition = "StimX"
        args.out_root = str(tmp_path / "d")
        return args

    def test_the_lock_SHA_is_INSIDE_the_run_identity(self, synthetic_run, tmp_path):
        args = self._args(synthetic_run, tmp_path)
        res = run_arms.build_bundle(args)
        with open(os.path.join(res["out_dir"], "provenance.json")) as fh:
            prov = json.load(fh)
        lock = prov["run_binding"]["environment_lock"]
        assert lock["sha256"] == PINNED           # the FULL digest, not a prefix
        assert lock["verified"] is True

        # ...and it is genuinely IN the id, not merely beside it
        full = sha256_hex(canonical_json(prov["run_binding"]))
        assert prov["arm_bundle_run_id"] == full[:16]

    def test_a_MISSING_lock_REFUSES_the_Direct_run(self, synthetic_run, tmp_path):
        args = self._args(synthetic_run, tmp_path)
        args.env_lock = None
        with pytest.raises(envlock.EnvLockError) as exc:
            run_arms.build_bundle(args)
        assert exc.value.gate == envlock.REFUSE_ABSENT

    def test_a_SWAPPED_lock_REFUSES_the_Direct_run(self, synthetic_run, tmp_path):
        args = self._args(synthetic_run, tmp_path)
        swapped = tmp_path / "swapped.txt"
        swapped.write_text("# not the pinned lock\n")
        args.env_lock = str(swapped)
        with pytest.raises(envlock.EnvLockError) as exc:
            run_arms.build_bundle(args)
        assert exc.value.gate == envlock.REFUSE_MISMATCH

    def test_the_lock_MOVES_the_run_id(self, synthetic_run, tmp_path):
        # if it did not, the lock would be recorded but not bound, which is the whole defect
        args = self._args(synthetic_run, tmp_path)
        res = run_arms.build_bundle(args)
        with open(os.path.join(res["out_dir"], "provenance.json")) as fh:
            binding = json.load(fh)["run_binding"]
        other = json.loads(json.dumps(binding))
        other["environment_lock"] = dict(other["environment_lock"], sha256="f" * 64)
        assert sha256_hex(canonical_json(other))[:16] != res["arm_bundle_run_id"]


class TestTheSTEP0AndPATHWAYLanes:
    """Step 0 (shared matrix) + 6 of the 15 production invocations."""

    def _pathway_args(self, synthetic_run, tmp_path):
        from direct import run_screen as rs
        from direct import universe as uni
        args = synthetic_run()
        ctx = rs.prepare(args)
        tu = uni.target_universe(ctx["identities_by_condition"])
        args.gene_sets = write_gene_sets(
            os.path.dirname(args.de_main), UNIVERSE, list(TARGET_GENES),
            ctx["gene_universe"]["sha256"], target_universe_sha256=tu["sha256"])
        args.condition = "StimX"
        args.out_root = str(tmp_path / "pw")
        args.signature_matrix_root = str(tmp_path / "sig")
        return args

    def test_STEP0_binds_the_lock_and_REFUSES_without_it(self, synthetic_run, tmp_path):
        args = self._pathway_args(synthetic_run, tmp_path)
        m = sm.build_condition(args, "StimX", args.signature_matrix_root)
        assert m["environment_lock"]["sha256"] == PINNED

        args.env_lock = None
        with pytest.raises(envlock.EnvLockError) as exc:
            sm.build_condition(args, "StimX", str(tmp_path / "sig2"))
        assert exc.value.gate == envlock.REFUSE_ABSENT

    def test_the_PATHWAY_bundle_binds_the_lock_INSIDE_its_run_id(self, synthetic_run,
                                                                 tmp_path):
        args = self._pathway_args(synthetic_run, tmp_path)
        sm.build_condition(args, "StimX", args.signature_matrix_root)
        res = run_pathway_arms.build_pathway_arms(args)
        with open(os.path.join(res["out_dir"], "pathway_provenance.json")) as fh:
            prov = json.load(fh)
        assert prov["run_binding"]["environment_lock"]["sha256"] == PINNED
        full = sha256_hex(canonical_json(prov["run_binding"]))
        assert prov["pathway_run_id"] == full[:16]

    def test_a_MISSING_lock_REFUSES_the_PATHWAY_run(self, synthetic_run, tmp_path):
        args = self._pathway_args(synthetic_run, tmp_path)
        sm.build_condition(args, "StimX", args.signature_matrix_root)
        args.env_lock = None
        with pytest.raises(envlock.EnvLockError) as exc:
            run_pathway_arms.build_pathway_arms(args)
        assert exc.value.gate == envlock.REFUSE_ABSENT

    def test_a_SWAPPED_lock_REFUSES_the_PATHWAY_run(self, synthetic_run, tmp_path):
        args = self._pathway_args(synthetic_run, tmp_path)
        sm.build_condition(args, "StimX", args.signature_matrix_root)
        swapped = tmp_path / "swapped.txt"
        swapped.write_text("# not the pinned lock\n")
        args.env_lock = str(swapped)
        with pytest.raises(envlock.EnvLockError) as exc:
            run_pathway_arms.build_pathway_arms(args)
        assert exc.value.gate == envlock.REFUSE_MISMATCH


class TestEveryProductionEntryPointACCEPTSTheFlag:
    @pytest.mark.parametrize("module", [
        "direct.run_arms",            # 3 Direct invocations
        "direct.run_pathway_arms",    # 6 pathway invocations
        "direct.signature_matrix",    # Step 0
        "direct.cli",
        "direct.run_pathway",
        # the PRODUCTION temporal lane. `direct.temporal.cli` — the retired flat lane — no
        # longer exists in this tree, and a gate that named it was checking a module nobody
        # can run: `--help` returned nothing, and "no flags found" is not "flag missing".
        "direct.temporal.arms.run_temporal_arms",
    ])
    def test_it_defines_env_lock(self, module):
        import subprocess
        import sys
        here = os.path.dirname(os.path.abspath(__file__))
        analysis = os.path.join(os.path.dirname(os.path.dirname(here)), "analysis")
        out = subprocess.run([sys.executable, "-m", module, "--help"],
                             cwd=analysis, capture_output=True, text=True).stdout
        assert "--env-lock" in out, f"{module} does not accept --env-lock"
