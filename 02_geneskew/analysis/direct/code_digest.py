"""M2 — THE code digest. One script, one recipe, one reproducible number.

WHY THIS EXISTS
---------------
The packet recorded a Stage-2 code digest of ``5694444e``. It is not reproducible: the
recorded recipe yields ``a70f327…`` on clean HEAD (65 py + 3 json) and ``590f6f7…`` at
the archived ``d5c71c3`` (57 py + 3 json), and no first-parent commit produces
``5694444e`` at all. A digest nobody can recompute is not an identifier — it is a number
that looks like one, and it will be cited as if it were.

So: ONE script, committed, tested, and the only thing anything is allowed to cite.

WHAT IT PRODUCES
----------------
A sorted MANIFEST — every included file's repo-relative path and its sha256 — and an
aggregate DIGEST over that manifest. The manifest is the point: an aggregate digest that
changes tells you *that* something moved, and the per-file list tells you *what*. A
digest without its manifest is unfalsifiable.

WHAT A RUN BINDS
----------------
Not this digest alone. A run's code identity is the tuple:

    (git commit, clean-tree status, manifest sha256, canonical digest)

The digest pins the CONTENT; the commit pins the HISTORY; the clean-tree flag says
whether the two can even be compared. A dirty tree with a matching digest is a
coincidence, not a provenance claim, and ``clean_tree=false`` says so out loud rather
than letting the digest imply a commit it was never taken from.

DETERMINISM
-----------
Path-relative, sorted, byte-hashed, with an explicit include rule and an explicit exclude
rule. No timestamps, no walk order, no machine paths. Run it twice, get the same bytes.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Optional

from .hashing import content_hash, file_sha256

DIGEST_ID = "spot.stage02.code_digest.v1"
DIGEST_LEN = 16

# Compact rule IDs. The rules themselves are stated ONCE, in this module's docstring; a
# served artifact carries the ID, not the paragraph.
INCLUDE_RULE_ID = "spot.stage02.code_digest.include_rule.py_json_sorted_relpath.v1"
BINDING_RULE_ID = (
    "spot.stage02.code_digest.binding_rule.commit_cleantree_manifest_digest.v1")

# WHAT IS IN THE DIGEST. Stated as a rule, not as a count: "65 py + 3 json" is an
# OUTCOME of a recipe, and quoting the outcome as if it were the recipe is how the
# irreproducible number happened in the first place.
INCLUDE_SUFFIXES = (".py", ".json")
EXCLUDE_DIR_NAMES = frozenset({
    "__pycache__", ".pytest_cache", ".git", ".ruff_cache", ".mypy_cache",
    "node_modules", ".ipynb_checkpoints",
})
INCLUDE_RULE = (
    "every *.py and *.json file under the digest root, recursively, excluding "
    f"{sorted(EXCLUDE_DIR_NAMES)}; paths are repo-relative and POSIX-separated; the "
    "manifest is sorted by path; the digest is the canonical content hash of that "
    "manifest")


def _iter_files(root: str) -> list[str]:
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIR_NAMES)
        for name in sorted(filenames):
            if name.endswith(INCLUDE_SUFFIXES):
                out.append(os.path.join(dirpath, name))
    return sorted(out)


def _git(repo: str, *args: str) -> Optional[str]:
    try:
        r = subprocess.run(("git", "-C", repo) + args, capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def git_identity(repo: str) -> dict[str, Any]:
    """The HISTORY half of the binding: which commit, and was the tree clean?

    ``clean_tree=false`` is not a warning to be skimmed past — it means the digest below
    describes bytes that exist on somebody's disk and in no commit, so the commit id
    beside it does NOT identify them.
    """
    commit = _git(repo, "rev-parse", "HEAD")
    status = _git(repo, "status", "--porcelain")
    return {
        "commit": commit,
        "clean_tree": (status == "") if status is not None else None,
        "dirty_paths": sorted(
            line[3:] for line in (status or "").splitlines() if line[3:]),
    }


def build(root: str, repo: Optional[str] = None) -> dict[str, Any]:
    """The manifest, the aggregate digest, and the git identity. Deterministic."""
    root = os.path.abspath(root)
    repo = os.path.abspath(repo or root)

    files = [
        {"path": os.path.relpath(p, repo).replace(os.sep, "/"),
         "sha256": file_sha256(p)}
        for p in _iter_files(root)
    ]
    files.sort(key=lambda f: f["path"])
    manifest_sha256 = content_hash(files)

    return {
        "digest_id": DIGEST_ID,
        "include_rule": INCLUDE_RULE,
        "digest_root": os.path.relpath(root, repo).replace(os.sep, "/"),
        "n_files": len(files),
        "n_py": sum(1 for f in files if f["path"].endswith(".py")),
        "n_json": sum(1 for f in files if f["path"].endswith(".json")),
        # the per-file list IS the evidence. A digest without it cannot be falsified.
        "files": files,
        "manifest_sha256": manifest_sha256,
        "canonical_digest": manifest_sha256[:DIGEST_LEN],
        "git": git_identity(repo),
        # what a run/review must cite. Never the digest alone.
        "binding_rule": (
            "a run binds (git.commit, git.clean_tree, manifest_sha256, "
            "canonical_digest) — never the digest alone, and never a digest recorded "
            "without the manifest that produced it"),
    }


# --------------------------------------------------------------------------- #
# THE RUN BINDING (M2). Every production run carries the code identity TUPLE.
# --------------------------------------------------------------------------- #
DIRTY_TREE_REFUSED = "code_tree_is_dirty_and_the_digest_does_not_identify_the_commit"


class DirtyTreeError(RuntimeError):
    """A release-grade run may not be taken from an uncommitted tree."""


def run_binding(root: Optional[str] = None, repo: Optional[str] = None, *,
                require_clean: bool = False) -> dict[str, Any]:
    """The code-identity TUPLE a run binds: (commit, clean_tree, manifest, digest).

    The digest ALONE is not an identity. It pins the CONTENT; the commit pins the
    HISTORY; ``clean_tree`` says whether the two can even be compared. A dirty tree with a
    matching digest is a coincidence, not a provenance claim.

    ``require_clean`` is the release-grade gate: a production run taken from an
    uncommitted tree is bound to bytes that exist on somebody's disk and in no commit, so
    the commit id beside it identifies nothing. It REFUSES rather than annotating.

    The per-file manifest is deliberately NOT inlined into the binding — it would put
    ~140 hashes into every run id for no extra identity, since ``manifest_sha256`` already
    covers it exactly. It is emitted alongside, so the digest stays falsifiable.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    root = root or os.path.dirname(os.path.dirname(here))       # 02_geneskew/
    repo = repo or os.path.dirname(root)

    doc = build(root, repo)
    git = doc["git"]
    if require_clean and git["clean_tree"] is not True:
        raise DirtyTreeError(
            f"{DIRTY_TREE_REFUSED}: the working tree is dirty "
            f"({len(git['dirty_paths'])} path(s), e.g. {git['dirty_paths'][:3]}). A "
            "release-grade run must be taken from a clean checkout — a digest computed "
            "over uncommitted bytes does not identify the commit printed beside it. "
            "To take a run from a dirty tree anyway, pass --allow-dirty-tree: it is "
            "RECORDED in the run binding and changes the run id, so the artifact says "
            "so out loud")
    # A MACHINE block: ids, hashes, counts and booleans. The rules themselves are stated
    # ONCE, in this module's docstring, and referenced by id — prose re-serialised into
    # every artifact is not provenance, it is noise that drifts.
    return {
        "digest_id": DIGEST_ID,
        "include_rule_id": INCLUDE_RULE_ID,
        "binding_rule_id": BINDING_RULE_ID,
        "digest_root": doc["digest_root"],
        "commit": git["commit"],
        "clean_tree": git["clean_tree"],
        "n_dirty_paths": len(git["dirty_paths"]),
        "manifest_sha256": doc["manifest_sha256"],
        "canonical_digest": doc["canonical_digest"],
        "n_files": doc["n_files"],
        "clean_checkout_required": bool(require_clean),
    }


def main(argv=None) -> int:
    import argparse

    here = os.path.dirname(os.path.abspath(__file__))
    default_root = os.path.dirname(os.path.dirname(here))       # 02_geneskew/
    default_repo = os.path.dirname(default_root)

    ap = argparse.ArgumentParser(description="Reproducible Stage-2 code digest (M2)")
    ap.add_argument("--root", default=default_root,
                    help="directory to digest (default: the Stage-2 tree)")
    ap.add_argument("--repo", default=default_repo,
                    help="repo root, for relative paths + git identity")
    ap.add_argument("--out", default=None, help="write the full manifest here (JSON)")
    args = ap.parse_args(argv)

    doc = build(args.root, args.repo)
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
            fh.write("\n")
    # the summary a human reads; the manifest is what a machine cites
    print(json.dumps({k: v for k, v in doc.items() if k != "files"},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
