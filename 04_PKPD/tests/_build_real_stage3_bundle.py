"""Build a REAL bundle from the CURRENT frozen Stage-3 engine — as a SUBPROCESS.

Run out-of-process (never imported) so the Stage-3 `druglink`/`verifier` packages never enter
the Stage-4 test interpreter, where a `verifier` of the same name already lives. The
cross-worktree test (`test_stage3_cross_worktree`) invokes this with the Stage-3 worktree on
PYTHONPATH, then admits the emitted bundle in-process.

    python tests/_build_real_stage3_bundle.py <stage3_root> <dest_dir>

It reproduces the Stage-3 conftest chain: a real Direct research run (Direct's own screen),
a real on-disk cache of the pinned public bytes (UniProt 2026_02 + ChEMBL_37), the engine
build, and `write_bundle`. It then runs Stage-3's OWN verifier on the result and writes the
four admission roots to `<dest>/roots.json`.

Exit codes are a CONTRACT the caller depends on:
    0  bundle built, Stage-3 verifier passed, roots.json written
    3  UPSTREAM: Direct's standalone verifier is unavailable (a Stage-2 blocker, not ours)
    1  anything else — a real failure the caller must surface, never skip
"""
import json
import os
import sys

UPSTREAM_EXIT = 3


def main() -> int:
    s3_root, dest = sys.argv[1], sys.argv[2]
    for p in (s3_root, os.path.join(s3_root, "analysis"), os.path.join(s3_root, "tests")):
        sys.path.insert(0, p)

    import direct_fixture
    import fixture_public_responses as FX
    from druglink import (acquire_public as ap, acquisition, artifacts,
                          direct_run as dr, run_stage3)
    from verifier import verify_stage3

    os.makedirs(dest, exist_ok=True)

    direct = direct_fixture.build_direct_run(os.path.join(dest, "direct_rq"),
                                             lane="research_only")
    os.environ.setdefault("SPOT_DIRECT_ANALYSIS", direct["analysis"])

    try:
        loaded = dr.load(direct["run_dir"], direct["inputs_root"], artifact_class="analysis",
                         direct_analysis=direct["analysis"])
    except dr.DirectRunError as exc:
        # Direct's standalone verifier crashing is an UPSTREAM Stage-2 defect, recorded
        # honestly by Stage 3 too. It is not a Stage-4 contract failure.
        if "NameError" in str(exc) or "SOURCE_CLASSIFICATION_RULE_ID" in str(exc):
            print(f"UPSTREAM_DIRECT_VERIFIER_DEFECT: {exc}")
            return UPSTREAM_EXIT
        raise

    cache = os.path.join(dest, "stage3_cache")
    ap.acquire(cache_root=cache, artifact_class="analysis", direct=loaded, top_per_arm=25,
               sources=("uniprot", "chembl"), chembl_release="CHEMBL_37",
               transport=FX.FakeTransport(no_match_uniprot=True))

    acquired = acquisition.load_manifest(cache, "analysis", direct=loaded)
    build = run_stage3.build(artifact_class="analysis", direct=loaded, acquired=acquired)

    bundle = artifacts.write_bundle(
        output_root=os.path.join(dest, "out"), artifact_class="analysis",
        document=build["document"], doc_id=build["document_id"], tables=build["tables"],
        created_at="2026-07-12T00:00:00+00:00")

    rep = verify_stage3.verify(bundle=bundle, cache_root=cache, direct_run=direct["run_dir"],
                               direct_inputs_root=direct["inputs_root"],
                               artifact_class="analysis", direct_analysis=direct["analysis"])
    if rep.failures:
        print("STAGE3_VERIFIER_FAILED:\n" + rep.render())
        return 1

    roots = {"bundle": bundle, "cache": cache, "direct_run": direct["run_dir"],
             "direct_inputs": direct["inputs_root"], "direct_analysis": direct["analysis"],
             "n_verifier_checks": len(rep.checks)}
    with open(os.path.join(dest, "roots.json"), "w", encoding="utf-8") as fh:
        json.dump(roots, fh, indent=2)
    print("OK n_checks=%d bundle=%s" % (len(rep.checks), os.path.basename(bundle)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
