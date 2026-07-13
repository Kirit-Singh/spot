"""The upstream model pin — RESOLVED AT RUNTIME, never echoed.

A constant in a config file is a claim about the software; it is not the software. A run
that printed ``commit = 2c2e3095…`` from its own config would say exactly the same thing
whether or not that commit was the one that produced the numbers — which makes the pin
decorative. So this module goes and looks:

  * the resolved module's source path (used, then DISCARDED — never emitted);
  * that source tree's git commit;
  * the installed package version;
  * a content hash over the tree's own bytes;
  * the environment lock.

and REFUSES on any mismatch.

The content hash is the one that cannot be talked around. A commit id is metadata a working
tree can contradict — an edited file leaves the commit id untouched — so the bytes are
hashed too, and a tree that has been edited under a pinned commit fails on the tree hash
even though it passes on the commit.

NO MACHINE-LOCAL PATHS ARE EMITTED. The path is how the software was found, not what it is.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from typing import Any, Optional

from . import config

VERIFIER_ID = "spot.stage02.p2s_arms.upstream_pin.v1"

INCLUDE_SUFFIXES = (".py", ".toml")
EXCLUDE_DIR_NAMES = frozenset({
    "__pycache__", ".git", ".pytest_cache", ".ruff_cache", ".mypy_cache", "build", "dist",
})


class UpstreamDriftError(RuntimeError):
    """The upstream model is not the pinned one. Refuse; never run against a drifted model."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def _git(repo: str, *args: str) -> Optional[str]:
    try:
        r = subprocess.run(("git", "-C", repo) + args, capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def tree_sha256(root: str) -> str:
    """A content hash over the upstream source tree. Sorted, path-relative, byte-hashed.

    Catches the case a commit id cannot: a file EDITED under a pinned commit. The commit
    still reads as pinned; the bytes do not.
    """
    entries: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIR_NAMES)
        for name in sorted(filenames):
            if not name.endswith(INCLUDE_SUFFIXES):
                continue
            path = os.path.join(dirpath, name)
            h = hashlib.sha256()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            entries.append((rel, h.hexdigest()))
    entries.sort()
    agg = hashlib.sha256()
    for rel, digest in entries:
        agg.update(f"{rel}\0{digest}\n".encode())
    return agg.hexdigest()


def probe() -> dict[str, Any]:
    """Look at the software that is actually installed. Raises if it is not importable."""
    try:
        import pert2state_model as m
    except ImportError as e:
        raise UpstreamDriftError(
            "upstream_model_not_importable",
            f"the pinned upstream model {config.UPSTREAM_REPOSITORY} is not importable "
            f"({e}); there is no fallback estimator") from e

    pkg_dir = os.path.dirname(os.path.abspath(m.__file__))
    # the checkout root: the package dir, or its parent when installed from a src layout
    repo = pkg_dir
    for _ in range(3):
        if os.path.isdir(os.path.join(repo, ".git")):
            break
        parent = os.path.dirname(repo)
        if parent == repo:
            break
        repo = parent

    return {
        "commit": _git(repo, "rev-parse", "HEAD"),
        "dirty": (_git(repo, "status", "--porcelain") or "") != "",
        "version": str(getattr(m, "__version__", "") or ""),
        "tree_sha256": tree_sha256(pkg_dir),
        # deliberately NOT emitted downstream — see ``identity``
        "_source_root": repo,
    }


def identity(observed: Optional[dict[str, Any]] = None, *,
             expect_tree_sha256: Optional[str] = None) -> dict[str, Any]:
    """Verify the observed software against the pin, and return the EMITTABLE identity.

    ``expect_tree_sha256`` is optional: it is pinned once the tree hash has been recorded
    from a verified checkout. Until then the commit and the version carry the pin, and the
    observed tree hash is RECORDED so it can be pinned — recorded, not asserted.
    """
    obs = observed if observed is not None else probe()

    commit = obs.get("commit")
    if commit != config.UPSTREAM_COMMIT:
        raise UpstreamDriftError(
            "upstream_commit_drift",
            f"the upstream model is at commit {commit!r}, not the pinned "
            f"{config.UPSTREAM_COMMIT!r}. The pin is the model — a run against a different "
            "commit produces numbers this lane cannot account for, so it is refused rather "
            "than annotated")

    version = obs.get("version")
    if config.UPSTREAM_VERSION and version and version != config.UPSTREAM_VERSION:
        raise UpstreamDriftError(
            "upstream_version_drift",
            f"the upstream package reports version {version!r}, not the pinned "
            f"{config.UPSTREAM_VERSION!r}")

    if obs.get("dirty"):
        raise UpstreamDriftError(
            "upstream_tree_is_dirty",
            "the upstream checkout has uncommitted changes, so the commit id beside it does "
            "not identify the bytes that would run")

    observed_tree = obs.get("tree_sha256")
    if expect_tree_sha256 and observed_tree != expect_tree_sha256:
        raise UpstreamDriftError(
            "upstream_tree_content_drift",
            f"the upstream source tree hashes to {observed_tree!r}, not the pinned "
            f"{expect_tree_sha256!r}. The commit matches and the BYTES DO NOT — a file has "
            "been edited under the pinned commit, which is exactly what a commit id cannot "
            "detect")

    # NO machine-local path. The path is how the software was found, not what it is.
    return {
        "verifier_id": VERIFIER_ID,
        "upstream_repository": config.UPSTREAM_REPOSITORY,
        "upstream_commit": config.UPSTREAM_COMMIT,
        "upstream_version": config.UPSTREAM_VERSION,
        "upstream_license": config.UPSTREAM_LICENSE,
        "upstream_tree_sha256": observed_tree,
        "upstream_tree_sha256_pinned": bool(expect_tree_sha256),
        "resolved_at_runtime": True,
        "machine_path_emitted": False,
        "provenance": config.UPSTREAM_PROVENANCE,
    }
