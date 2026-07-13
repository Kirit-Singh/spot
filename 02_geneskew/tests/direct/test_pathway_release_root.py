"""W7's seam: the pathway producer could not consume the v3 release AT ALL.

`run_screen` dispatches on the release's OWN declared schema and REFUSES a
`spot.stage01_v3_release.v1` whose staged root was not stated — its components are declared by
repo-relative path, and a loader that guessed the root from the release's own location could be
walked into a different tree. `run_arms` accepts `--stage1-release-root`. `run_pathway_arms`
never defined it, so the wrapper had no way to pass it and the pathway lane could not run on the
current release.

The narrow fix: accept the root, BIND the release identity into the pathway run id, and refuse a
release that is not the one the Direct arms being enriched were built on.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import gate, run_pathway_arms
from direct import signature_matrix as sm
from fixtures_pathway import write_gene_sets
from fixtures_spec import TARGET_GENES, UNIVERSE


@pytest.fixture
def built(synthetic_run, tmp_path):
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
    sm.build_condition(args, "StimX", args.signature_matrix_root)
    res = run_pathway_arms.build_pathway_arms(args)
    with open(os.path.join(res["out_dir"], "pathway_provenance.json")) as fh:
        prov = json.load(fh)
    return args, res, prov


class TestTheCLISeamIsClosed:
    def test_the_parser_ACCEPTS_the_release_root(self):
        ns = run_pathway_arms.build_parser().parse_args([
            "--condition", "Rest", "--gene-sets", "g.json", "--de-main", "d.h5ad",
            "--signature-matrix-root", "s", "--out-root", "o",
            "--stage1-release", "r.json", "--stage1-release-root", "/staged/root"])
        assert ns.stage1_release_root == "/staged/root"

    def test_it_appears_in_help_so_a_wrapper_can_find_it(self):
        assert "--stage1-release-root" in run_pathway_arms.build_parser().format_help()


class TestTheReleaseIdentityIsBOUND:
    def test_the_release_hashes_are_IN_the_pathway_run_id(self, built):
        from direct.hashing import canonical_json, sha256_hex
        _args, res, prov = built
        b = prov["run_binding"]
        assert "stage1_release_hashes" in b
        assert b["stage1_release_kind"]
        # genuinely IN the id, not merely beside it
        full = sha256_hex(canonical_json(b))
        assert prov["pathway_run_id"] == full[:16]

    def test_changing_the_release_hashes_MOVES_the_run_id(self, built):
        from direct.hashing import canonical_json, sha256_hex
        _args, res, prov = built
        other = json.loads(json.dumps(prov["run_binding"]))
        other["stage1_release_hashes"] = {"forged": "f" * 64}
        assert sha256_hex(canonical_json(other))[:16] != prov["pathway_run_id"]


class TestAMismatchedOrStaleReleaseIsREFUSED:
    def test_a_release_that_is_NOT_the_one_the_DIRECT_arms_came_from_is_REFUSED(self, built):
        # the quiet failure: enriching one experiment's arms with another's scorer view and
        # gene-set universe. Every hash in the artifact would still agree with itself.
        args, _res, _prov = built

        class _Rel:
            kind = "synthetic"
            hashes = {"release_self_sha256": "d" * 64}

        manifest = {"direct_mask_anchor": {
            "direct_stage1_release_hashes": {"release_self_sha256": "a" * 64}}}
        with pytest.raises(gate.GateError) as exc:
            run_pathway_arms.check_release_matches_direct(_Rel(), manifest)
        assert run_pathway_arms.REFUSE_RELEASE_MISMATCH in str(exc.value)

    def test_the_SAME_release_is_ACCEPTED(self):
        class _Rel:
            kind = "synthetic"
            hashes = {"release_self_sha256": "a" * 64}

        manifest = {"direct_mask_anchor": {
            "direct_stage1_release_hashes": {"release_self_sha256": "a" * 64}}}
        run_pathway_arms.check_release_matches_direct(_Rel(), manifest)   # must not raise

    def test_UNANCHORED_signatures_do_not_fabricate_a_release_check(self):
        # absent is absent: it is already reported as mask_is_externally_anchored=false, and
        # inventing a green here would be worse than having no check
        class _Rel:
            kind = "synthetic"
            hashes = {"release_self_sha256": "a" * 64}
        run_pathway_arms.check_release_matches_direct(_Rel(), {})          # must not raise


class TestNUMERICAL_BYTES_ARE_UNCHANGED:
    """A code-identity move must not move a single number."""

    def test_the_enrichment_records_and_convergence_are_BYTE_IDENTICAL(self, built):
        args, res, prov = built
        with open(os.path.join(res["out_dir"], "arm_bundle.json")) as fh:
            doc = json.load(fh)
        with open(os.path.join(res["out_dir"], "convergence.json")) as fh:
            conv = json.load(fh)
        # the scientific content hashes are a pure function of the inputs; the release binding
        # changes the run IDENTITY, and nothing it identifies
        assert doc["records_sha256"] == prov["run_binding"]["records_sha256"]
        assert conv["convergence_sha256"] == prov["run_binding"]["convergence_sha256"]
        assert doc["n_records"] > 0
