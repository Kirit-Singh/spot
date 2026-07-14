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
    3  UPSTREAM precondition not met — a Stage-2 state, not a Stage-3/Stage-4 contract break:
         * Direct's standalone verifier is unavailable (the known NameError blocker), OR
         * the Stage-2 Direct worktree is DIRTY, so Direct refuses a release-grade run
           (a sibling lane mid-edit; the committed fixture already proves gate-1 admission)
    1  anything else — a real failure the caller must surface, never skip
"""
import json
import os
import subprocess
import sys

UPSTREAM_EXIT = 3

# The Stage-2 Direct worktree, resolved exactly as Stage-3's direct_fixture resolves it.
#
# `$SPOT_DIRECT_WT`, else the sibling worktree next to this one. A hard-coded absolute default
# binds one developer's checkout into a tracked helper and points at nothing anywhere else —
# and a path that silently resolves to nothing turns this proof into a permanent skip.
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # .../<worktree>/04_PKPD
_SIBLING = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "spot-stage2-direct")
STAGE2_WT = os.environ.get("SPOT_DIRECT_WT") or _SIBLING


def stage2_tree_is_dirty() -> str | None:
    """-> a short description of the dirt, or None if the Stage-2 tree is clean/absent.

    A dirty upstream tree cannot produce a release-grade, reproducible Direct run: Direct's
    own `code_digest` binds the code identity into the run, and uncommitted bytes do not
    identify a commit. So this is a PRECONDITION, checked up front and deterministically, not
    a failure to race on: when a sibling lane is mid-edit on Stage 2, the end-to-end proof
    cannot run, and the committed fixture carries gate-1 in the meantime.
    """
    try:
        out = subprocess.run(["git", "-C", STAGE2_WT, "status", "--porcelain"],
                             capture_output=True, text=True, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    return f"{len(lines)} uncommitted path(s), e.g. {lines[:3]}" if lines else None

# Signatures of an UPSTREAM Stage-2 precondition, recognised by message so this file imports
# nothing from Direct. A dirty upstream tree is a transient state of a worktree Stage 4 does
# not own; Direct correctly refuses a release-grade run from uncommitted bytes.
_UPSTREAM_MARKERS = ("NameError", "SOURCE_CLASSIFICATION_RULE_ID",
                     "DirtyTreeError", "code_tree_is_dirty", "working tree is dirty")


def _is_upstream(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}"
    return any(m in text for m in _UPSTREAM_MARKERS)


def main() -> int:
    s3_root, dest = sys.argv[1], sys.argv[2]

    # PRECONDITION, checked first and deterministically: a clean Stage-2 Direct tree. A sibling
    # lane editing Stage 2 would make the build's code identity non-reproducible and race the
    # re-verify. Skip up front rather than emit a bundle nothing can reproduce.
    dirt = stage2_tree_is_dirty()
    if dirt:
        print(f"UPSTREAM_STAGE2_PRECONDITION: Stage-2 Direct worktree is dirty ({dirt})")
        return UPSTREAM_EXIT

    for p in (s3_root, os.path.join(s3_root, "analysis"), os.path.join(s3_root, "tests")):
        sys.path.insert(0, p)

    import direct_fixture
    import fixture_public_responses as FX
    from druglink import (acquire_public as ap, acquisition, artifacts,
                          direct_run as dr, run_stage3)
    from verifier import verify_stage3

    os.makedirs(dest, exist_ok=True)

    # Building the Direct run and admitting it both touch the Stage-2 worktree. Either can hit
    # an UPSTREAM precondition (dirty tree, or Direct's verifier defect) — a Stage-2 state, not
    # a Stage-3/Stage-4 contract break. Classified as exit 3 so the caller skips with a reason
    # rather than reporting a cross-stage failure that is not there.
    try:
        direct = direct_fixture.build_direct_run(os.path.join(dest, "direct_rq"),
                                                 lane="research_only")
        os.environ.setdefault("SPOT_DIRECT_ANALYSIS", direct["analysis"])
        loaded = dr.load(direct["run_dir"], direct["inputs_root"], artifact_class="analysis",
                         direct_analysis=direct["analysis"])
    except Exception as exc:  # noqa: BLE001 — re-raised unless it is a known upstream state
        if _is_upstream(exc):
            print(f"UPSTREAM_STAGE2_PRECONDITION: {type(exc).__name__}: {exc}")
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
        # If the tree went dirty DURING the build, the verify failure is that race, not a
        # Stage-3/Stage-4 defect — classify it upstream. Otherwise it is a real failure.
        dirt = stage2_tree_is_dirty()
        if dirt:
            print(f"UPSTREAM_STAGE2_PRECONDITION: Stage-2 tree went dirty mid-build ({dirt})")
            return UPSTREAM_EXIT
        print("STAGE3_VERIFIER_FAILED:\n" + rep.render())
        return 1

    roots = {"bundle": bundle, "cache": cache, "direct_run": direct["run_dir"],
             "direct_inputs": direct["inputs_root"], "direct_analysis": direct["analysis"],
             "stage2_wt": STAGE2_WT, "n_verifier_checks": len(rep.checks)}
    with open(os.path.join(dest, "roots.json"), "w", encoding="utf-8") as fh:
        json.dump(roots, fh, indent=2)
    print("OK n_checks=%d bundle=%s" % (len(rep.checks), os.path.basename(bundle)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
