"""WHICH BUILD produced the bytes — RE-DERIVED here, against an externally pinned checkout.

A run is not the witness for its own checkout. The producer RECORDS its code identity —
``(commit, clean_tree, manifest_sha256, canonical_digest)`` — and deliberately does not
declare itself clean. This module re-derives that tuple from a checkout the CALLER pins,
compares it to what the artifact recorded, and decides the FINAL clean-tree status.

THE RECIPE, RE-STATED (the shared Stage-2 code-digest convention, implemented again here)
-----------------------------------------------------------------------------------------
    every *.py and *.json under the digest root, recursively, excluding the build/cache
    directories below; paths are REPO-relative and POSIX-separated; the manifest is the
    sorted list of ``{path, sha256}``; ``manifest_sha256`` is the canonical content hash of
    that manifest, and ``canonical_digest`` is its first 16 hex.

The manifest IS the evidence: an aggregate digest that changes tells you THAT something
moved; the per-file list tells you WHAT. A digest recorded without the manifest that
produced it cannot be falsified.

WHY THE DIGEST ALONE IS NOT AN IDENTITY
---------------------------------------
The digest pins the CONTENT. The commit pins the HISTORY. ``clean_tree`` says whether the
two can even be compared — a dirty tree with a matching digest is a coincidence, not a
provenance claim, because the digest then describes bytes that exist on somebody's disk and
in no commit, and the commit id printed beside it identifies nothing.
"""
from __future__ import annotations

import os
import subprocess
from typing import Any, Optional

from .canonical import content_hash, file_sha256

DIGEST_LEN = 16
INCLUDE_SUFFIXES = (".py", ".json")
EXCLUDE_DIR_NAMES = frozenset({
    "__pycache__", ".pytest_cache", ".git", ".ruff_cache", ".mypy_cache",
    "node_modules", ".ipynb_checkpoints",
})

# The fields the producer records. Re-derived, never believed.
CODE_IDENTITY_KEYS = frozenset({
    "digest_id", "include_rule_id", "binding_rule_id", "digest_root", "commit",
    "clean_tree", "n_dirty_paths", "manifest_sha256", "canonical_digest", "n_files",
    "clean_checkout_required", "env_lock_sha256", "env_lock_name",
})

# THE ENVIRONMENT IS PART OF THE BUILD.
#
# The code digest pins WHAT WAS RUN. It says nothing about WHAT IT WAS RUN WITH: the same
# source, resolved against a different numpy, is a different computation and can produce
# different numbers. A run that binds its code and not its environment has bound half of
# itself, and the half it left out is the half that changes without anybody editing a file.
#
# So the lock's sha256 travels in the build identity, and this lane verifies it against the
# ACTUAL LOCK BYTES the caller supplies — not against the artifact's own word for them.
ENV_LOCK_FIELD = "env_lock_sha256"

# THE AUTHORITATIVE STAGE-2 SOLVER LOCK. One environment across every lane — Direct,
# pathway, temporal and the real run — because "the same computation" means the same
# environment, and two lanes locked to two environments are two computations that agree only
# by luck. This is the frozen/staged lock's sha256, and it is the DEFAULT: a caller who
# supplies some other lock is refused BY NAME rather than quietly verified against it.
FROZEN_STAGE2_ENV_LOCK_SHA256 = (
    "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe")


def check_env_lock(f, recorded: Any, env_lock_path: Optional[str],
                   where: str = "release",
                   expect_sha256: Optional[str] = FROZEN_STAGE2_ENV_LOCK_SHA256) -> None:
    """The env lock, re-hashed from the bytes the CALLER supplied. Fail closed.

    TWO questions, and both must be answered. Is the lock handed to this verifier the
    AUTHORITATIVE Stage-2 lock — the one every other lane is pinned to? And did the release
    actually bind THAT lock? A verifier that only asked the second would happily confirm a
    release against whichever environment somebody handed it.
    """
    if not f.check("the_env_lock_was_supplied_to_the_verifier", bool(env_lock_path),
                   where,
                   "--env-lock was not supplied, so the environment the bundles claim to "
                   "have been built in could not be checked against anything. An unverified "
                   "environment is an unbound input"):
        return
    if not f.check("the_supplied_env_lock_exists",
                   os.path.exists(str(env_lock_path)), where, str(env_lock_path)):
        return

    with open(str(env_lock_path), "rb") as fh:
        want = _sha256_bytes(fh.read())

    if expect_sha256:
        f.check("the_supplied_env_lock_is_the_authoritative_stage2_lock",
                want == str(expect_sha256), where,
                f"the lock supplied to this verifier hashes to {want[:16]}...; the "
                f"authoritative Stage-2 lock is {str(expect_sha256)[:16]}.... Every lane "
                "pins the SAME environment, and verifying against a different one confirms "
                "a computation nobody ran")

    declared = (recorded or {}).get(ENV_LOCK_FIELD)
    if not f.check("the_build_identity_binds_an_env_lock", bool(declared), where,
                   "the bundles record no env_lock_sha256; the same source resolved against "
                   "a different environment is a different computation, and a run that binds "
                   "its code and not its environment has bound half of itself"):
        return
    f.check("the_env_lock_sha256_matches_the_lock_bytes_supplied", declared == want, where,
            f"the bundles bind {str(declared)[:16]}...; the lock supplied to this verifier "
            f"hashes to {want[:16]}.... Either the release was built against a different "
            "environment, or a different lock has been handed to the verifier")


def _sha256_bytes(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _iter_files(root: str) -> list[str]:
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIR_NAMES)
        for name in sorted(filenames):
            if name.endswith(INCLUDE_SUFFIXES):
                out.append(os.path.join(dirpath, name))
    return sorted(out)


def manifest(root: str, repo: str) -> list[dict[str, str]]:
    """The sorted, repo-relative per-file manifest. The evidence a digest stands on."""
    files = [{"path": os.path.relpath(p, repo).replace(os.sep, "/"),
              "sha256": file_sha256(p)}
             for p in _iter_files(os.path.abspath(root))]
    files.sort(key=lambda f: f["path"])
    return files


def _git(repo: str, *args: str) -> Optional[str]:
    try:
        r = subprocess.run(("git", "-C", repo) + args, capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def git_state(repo: str) -> dict[str, Any]:
    """WHICH commit, and was the tree clean? Re-derived from the checkout, not read."""
    commit = _git(repo, "rev-parse", "HEAD")
    status = _git(repo, "status", "--porcelain")
    dirty = [ln for ln in (status or "").splitlines() if ln.strip()]
    return {
        "commit": commit,
        "clean_tree": (status is not None and not dirty) if commit else None,
        "n_dirty_paths": len(dirty),
    }


def rederive(digest_root: str, repo: str) -> dict[str, Any]:
    """The code-identity tuple, computed HERE from a checkout the caller pinned."""
    files = manifest(digest_root, repo)
    m = content_hash(files)
    state = git_state(repo)
    return {
        "digest_root": os.path.relpath(os.path.abspath(digest_root),
                                       os.path.abspath(repo)).replace(os.sep, "/"),
        "n_files": len(files),
        "manifest_sha256": m,
        "canonical_digest": m[:DIGEST_LEN],
        **state,
    }


def check(f, recorded: Any, *, digest_root: str, repo: str, where: str = "release",
          require_clean: bool = True) -> None:
    """Re-derive the code identity and decide the FINAL clean-tree status.

    The producer records its tree state and does not declare itself clean. THIS is where
    clean is decided, against the pinned checkout — a release-grade artifact taken from a
    dirty tree is bound to bytes that exist in no commit, and the commit id beside it
    identifies nothing.
    """
    if not f.check("the_bundle_records_a_code_identity", isinstance(recorded, dict)
                   and bool(recorded), where,
                   "a bundle that does not say WHICH BUILD produced it cannot be "
                   "reproduced, and a method hash is not a build"):
        return

    got = rederive(digest_root, repo)
    f.check("code_identity_rederives_from_the_pinned_checkout",
            recorded.get("manifest_sha256") == got["manifest_sha256"]
            and recorded.get("canonical_digest") == got["canonical_digest"], where,
            f"recorded manifest {str(recorded.get('manifest_sha256'))[:16]}..., the pinned "
            f"checkout hashes to {got['manifest_sha256'][:16]}... over {got['n_files']} "
            "files. The bytes that were verified are not the bytes that were built")
    f.check("code_identity_names_the_commit_of_the_pinned_checkout",
            recorded.get("commit") == got["commit"], where,
            f"recorded {recorded.get('commit')}, pinned checkout is at {got['commit']}")
    # THE FINAL CLEAN-TREE DECISION. Made here, by the lane that did not do the building.
    # ``require_clean=False`` exists ONLY for the in-process fixture suite, whose producer
    # runs from the verifier's own working tree and is therefore dirty BY CONSTRUCTION while
    # this lane is being developed. The real decision is proved in the cross-worktree test,
    # against the producer's committed, clean checkout — where it is not optional.
    if not require_clean:
        return
    f.check("the_pinned_producer_checkout_is_clean", got["clean_tree"] is True, where,
            f"the producer checkout has {got['n_dirty_paths']} uncommitted path(s). A "
            "release-grade artifact from a dirty tree is bound to bytes that exist in no "
            "commit, so the commit id recorded beside it identifies nothing")
