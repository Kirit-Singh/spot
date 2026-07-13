"""The aggregate run manifest: which lane outputs belong to the SAME Stage-2 run.

Each lane was already content-addressed and verified. What did not exist was anything that
said which of them are the same science — so a screen from one commit could be cited beside
a pathway result from another and nothing would notice. "The per-lane outputs are the
contract" holds right up until somebody has to assemble them, and then it becomes the
reader's problem.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import run_manifest


def _lane_dir(tmp_path, lane, run_id):
    d = os.path.join(str(tmp_path), lane, run_id)
    os.makedirs(d, exist_ok=True)
    for name in run_manifest.LANE_ARTIFACTS[lane]:
        with open(os.path.join(d, name), "w") as fh:
            fh.write(f"{lane}/{run_id}/{name}")
    return d


def _complete(tmp_path):
    inv = []
    for i in range(3):
        inv.append(run_manifest.bind_lane(
            run_manifest.LANE_DIRECT,
            _lane_dir(tmp_path, "direct", f"d{i}"), run_id=f"d{i}"))
    for i in range(6):
        inv.append(run_manifest.bind_lane(
            run_manifest.LANE_TEMPORAL,
            _lane_dir(tmp_path, "temporal", f"t{i}"), run_id=f"t{i}"))
    for i in range(6):
        inv.append(run_manifest.bind_lane(
            run_manifest.LANE_PATHWAY,
            _lane_dir(tmp_path, "pathway", f"p{i}"), run_id=f"p{i}"))
    return inv


class TestItBindsEveryLaneOutput:
    def test_a_complete_run_is_15_invocations(self, tmp_path):
        doc = run_manifest.build(invocations=_complete(tmp_path),
                                 out_path=os.path.join(str(tmp_path), "m.json"))
        assert doc["complete"] is True
        assert doc["n_invocations"] == run_manifest.N_EXPECTED == 15
        assert doc["invocation_counts"] == {"direct": 3, "temporal": 6, "pathway": 6}

    def test_every_artifact_of_every_lane_is_hashed(self, tmp_path):
        doc = run_manifest.build(invocations=_complete(tmp_path),
                                 out_path=os.path.join(str(tmp_path), "m.json"))
        for inv in doc["invocations"]:
            expected = run_manifest.LANE_ARTIFACTS[inv["lane"]]
            assert set(inv["files"]) == set(expected)
            for sha in inv["files"].values():
                assert len(sha) == 64
            assert len(inv["artifact_sha256"]) == 64

    def test_the_manifest_is_content_addressed(self, tmp_path):
        p = os.path.join(str(tmp_path), "m.json")
        doc = run_manifest.build(invocations=_complete(tmp_path), out_path=p)
        with open(p) as fh:
            on_disk = json.load(fh)
        assert on_disk["manifest_sha256"] == doc["manifest_sha256"]
        assert len(doc["manifest_sha256"]) == 64

    def test_it_binds_the_shared_code_identity(self, tmp_path):
        doc = run_manifest.build(invocations=_complete(tmp_path),
                                 out_path=os.path.join(str(tmp_path), "m.json"))
        ci = doc["code_identity"]
        assert set(ci) >= {"commit", "clean_tree", "manifest_sha256",
                           "canonical_digest"}

    def test_it_produces_no_science_and_says_so(self, tmp_path):
        doc = run_manifest.build(invocations=_complete(tmp_path),
                                 out_path=os.path.join(str(tmp_path), "m.json"))
        assert doc["produces_scientific_values"] is False
        assert doc["binds_lane_outputs"] is True


class TestAPartialRunIsVisiblyPartial:
    def test_a_missing_invocation_REFUSES_to_be_called_complete(self, tmp_path):
        inv = _complete(tmp_path)[:-1]          # one pathway invocation short
        with pytest.raises(run_manifest.RunManifestError, match="PARTIAL"):
            run_manifest.build(invocations=inv,
                               out_path=os.path.join(str(tmp_path), "m.json"))

    def test_a_partial_run_MAY_be_manifested_but_is_flagged(self, tmp_path):
        inv = _complete(tmp_path)[:-1]
        doc = run_manifest.build(invocations=inv, allow_partial=True,
                                 out_path=os.path.join(str(tmp_path), "m.json"))
        assert doc["complete"] is False
        assert doc["n_invocations"] == 14

    def test_a_lane_MISSING_AN_ARTIFACT_is_refused(self, tmp_path):
        d = _lane_dir(tmp_path, "direct", "d0")
        os.remove(os.path.join(d, "screen.parquet"))
        with pytest.raises(run_manifest.RunManifestError, match="missing"):
            run_manifest.bind_lane(run_manifest.LANE_DIRECT, d, run_id="d0")


class TestPerturb2StateIsExplicitlyDeferred:
    def test_the_manifest_names_its_state(self, tmp_path):
        doc = run_manifest.build(invocations=_complete(tmp_path),
                                 out_path=os.path.join(str(tmp_path), "m.json"))
        p2s = doc["perturb2state"]
        assert p2s["state"] == "deferred_not_part_of_this_run"
        assert p2s["tier"] == "secondary_method"
        assert p2s["gates_the_run"] is False

    def test_complete_stage2_is_direct_pareto_temporal_pathway(self, tmp_path):
        doc = run_manifest.build(invocations=_complete(tmp_path),
                                 out_path=os.path.join(str(tmp_path), "m.json"))
        assert list(doc["perturb2state"]["complete_stage2_is"]) == [
            "direct", "pareto", "temporal", "pathway"]
