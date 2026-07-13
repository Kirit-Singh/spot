"""NATIVE-SHAPE DISCOVERY on REAL producer bytes. The acceptance gate for the fix.

An independent replay caught the aggregate keying discovery on a fictional top-level ``lane``
that the REAL Direct and pathway producers never write, so on real bytes discovery found
``direct=[]``, ``temporal=['temporal']``, ``pathway=[]`` — nothing — while the hand-built
generic-shape fixtures masked it. These tests build the REAL bundles from the ACTUAL producer
entrypoints (``arm_release.build_release`` / ``run_temporal_arms`` emit / ``run_pathway_arms``)
and require native discovery to find EXACTLY 3 Direct + 6 temporal + 6 pathway, while a
generic / unrecognised shape refuses.
"""
from __future__ import annotations

import json
import os

import fixtures_temporal_arms as FX
import fixtures_v3_release as V3
import pytest
from direct import arm_release, run_pathway_arms, run_release
from direct import bundle_normalize as BN
from direct import run_screen as rs
from direct import signature_matrix as sm
from direct import universe as uni
from direct.temporal.arms import arm_emit
from fixtures_pathway import write_gene_sets
from fixtures_spec import TARGET_GENES, UNIVERSE

CONDITIONS = ("Rest", "Stim8hr", "Stim48hr")
SOURCES = ("reactome", "go_bp")
# The two REAL pinned sources carry ENFORCED licences + references (and go_bp a dated
# release). The default fixture release_id ("fixture-2026-07-01") satisfies the date gate.
LICENSE = {
    "reactome": ("CC0-1.0", "https://reactome.org/license"),
    "go_bp": ("CC-BY-4.0", "http://geneontology.org/docs/go-citation-policy/"),
}


def _real_direct(tmp_path, synthetic_run, root) -> list[str]:
    args = synthetic_run(conditions=CONDITIONS)
    rel_root = str(tmp_path / "d_release")
    args.stage1_release = V3.stage_release(rel_root, conditions=CONDITIONS)
    args.stage1_release_root = rel_root
    args.out_root = os.path.join(root, "direct")
    arm_release.build_release(args)
    return [os.path.join(args.out_root, d) for d in os.listdir(args.out_root)
            if os.path.isdir(os.path.join(args.out_root, d))]


def _real_temporal(root) -> dict:
    return arm_emit.emit_release(FX.build_all(), os.path.join(root, "temporal"),
                                 expect_n_bundles=6)


def _real_pathway(tmp_path, synthetic_run, root) -> list[str]:
    args = synthetic_run(conditions=CONDITIONS)
    # BUNDLE-SCOPED prepare (per condition), exactly as build_pathway_arms does — the
    # selection-scoped rs.prepare binds the single default condition and is not this path.
    ctx = rs.prepare_bundle(args, cond=CONDITIONS[0])
    tu = uni.target_universe(ctx["identities_by_condition"])
    sig_root = str(tmp_path / "signatures")
    for cond in CONDITIONS:
        sm.build_condition(args, cond, sig_root)
    out_root = os.path.join(root, "pathway")
    dirs = []
    for i, src in enumerate(SOURCES):
        gs_dir = str(tmp_path / f"genesets_{src}")
        os.makedirs(gs_dir, exist_ok=True)
        lic, ref = LICENSE[src]
        gs = write_gene_sets(
            gs_dir, UNIVERSE, list(TARGET_GENES), ctx["gene_universe"]["sha256"],
            target_universe_sha256=tu["sha256"],
            mutate=lambda d, s=src, l=lic, r=ref: {
                **d, "release": {**d["release"], "source": s, "license": l,
                                 "license_reference": r}})
        for cond in CONDITIONS:
            args.gene_sets = gs
            args.condition = cond
            args.out_root = out_root
            args.signature_matrix_root = sig_root
            res = run_pathway_arms.build_pathway_arms(args)
            dirs.append(res["out_dir"])
    return dirs


@pytest.fixture
def real_run(tmp_path, synthetic_run):
    """15 REAL bundles under ONE root: 3 Direct + 6 temporal + 6 pathway."""
    root = str(tmp_path / "bundles")
    os.makedirs(root, exist_ok=True)
    direct = _real_direct(tmp_path, synthetic_run, root)
    _real_temporal(root)
    pathway = _real_pathway(tmp_path, synthetic_run, root)
    return {"root": root, "direct": direct, "pathway": pathway}


class TestDiscoveryFindsExactlyThreeSixSixOnRealBytes:
    def test_native_discovery_is_3_6_6(self, real_run):
        root = real_run["root"]
        assert len(run_release.discover(root, "direct")) == 3
        assert len(run_release.discover(root, "temporal")) == 6
        assert len(run_release.discover(root, "pathway")) == 6

    def test_the_OLD_top_level_lane_keying_would_have_found_NOTHING(self, real_run):
        # the exact bug: real Direct/pathway bundles carry no top-level ``lane``
        root = real_run["root"]
        by_old = {"direct": 0, "temporal": 0, "pathway": 0}
        for base, _dirs, files in os.walk(root):
            if "arm_bundle.json" not in files:
                continue
            doc = json.load(open(os.path.join(base, "arm_bundle.json")))
            lane = doc.get("lane")            # the retired keying
            if lane in by_old:
                by_old[lane] += 1
        assert by_old["direct"] == 0
        assert by_old["pathway"] == 0
        assert by_old["temporal"] == 6       # only temporal writes a top-level lane

    def test_every_real_bundle_normalizes_to_its_native_identity(self, real_run):
        root = real_run["root"]
        for d in run_release.discover(root, "direct"):
            n = BN.normalize(json.load(open(os.path.join(d, "arm_bundle.json"))))
            assert n["lane"] == "direct" and n["bundle_id"] and "condition" in n["context"]
            assert all(k.startswith("direct|") for k in n["arm_keys"])
        for d in run_release.discover(root, "pathway"):
            n = BN.normalize(json.load(open(os.path.join(d, "arm_bundle.json"))))
            assert n["lane"] == "pathway" and n["bundle_id"]
            assert set(n["context"]) == {"condition", "gene_set_source"}
            assert all(k.startswith("pathway|") for k in n["arm_keys"])


class TestAGenericOrUnrecognisedShapeRefuses:
    def test_a_bundle_with_no_native_schema_is_NOT_discovered(self, real_run, tmp_path):
        # a directory whose arm_bundle.json is not a native producer bundle is not a lane
        junk = os.path.join(real_run["root"], "junk_bundle")
        os.makedirs(junk, exist_ok=True)
        with open(os.path.join(junk, "arm_bundle.json"), "w") as fh:
            json.dump({"schema_version": "not.a.real.bundle", "lane": "direct"}, fh)
        assert junk not in run_release.discover(real_run["root"], "direct")

    def test_classify_lane_refuses_unknown_and_a_direct_shape_missing_its_id(self):
        assert BN.classify_lane({"schema_version": "bogus"}) is None
        assert BN.classify_lane({}) is None
        with pytest.raises(BN.BundleShapeError) as exc:
            BN.normalize({"schema_version": BN.DIRECT_SCHEMA, "condition": "Rest",
                          "arms": []})            # native Direct shape, no arm_bundle_run_id
        assert exc.value.reason == BN.REFUSE_MISSING_IDENTITY
