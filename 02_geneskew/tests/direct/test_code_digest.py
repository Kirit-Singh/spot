"""M2 — the code digest must be reproducible, or it is not an identifier.

The packet cited `5694444e`. Nothing produces it: the recorded recipe gives `a70f327…`
on clean HEAD and `590f6f7…` at the archived commit, and no first-parent commit yields
`5694444e` at all. These tests exist so that never happens again — the digest is computed
by ONE committed script, and running it twice gives the same bytes.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import code_digest


def _tree(tmp_path, files: dict[str, str]) -> str:
    for rel, content in files.items():
        p = os.path.join(str(tmp_path), rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write(content)
    return str(tmp_path)


class TestItIsReproducible:
    def test_running_it_twice_gives_an_identical_digest(self, tmp_path):
        root = _tree(tmp_path, {"a.py": "x = 1\n", "sub/b.json": '{"k": 1}\n'})
        first, second = code_digest.build(root), code_digest.build(root)
        assert first["canonical_digest"] == second["canonical_digest"]
        assert first["manifest_sha256"] == second["manifest_sha256"]
        assert first["files"] == second["files"]

    def test_the_whole_manifest_is_byte_identical_across_runs(self, tmp_path):
        root = _tree(tmp_path, {f"m{i}.py": f"v = {i}\n" for i in range(12)})
        a = code_digest.build(root)
        b = code_digest.build(root)
        strip = lambda d: {k: v for k, v in d.items() if k != "git"}   # noqa: E731
        assert json.dumps(strip(a), sort_keys=True) == \
            json.dumps(strip(b), sort_keys=True)

    def test_it_does_not_depend_on_the_order_the_filesystem_hands_files_back(
            self, tmp_path):
        # the manifest is sorted by path, so the digest is a property of the CONTENT
        root = _tree(tmp_path, {"z.py": "1\n", "a.py": "2\n", "m/q.py": "3\n"})
        doc = code_digest.build(root)
        assert [f["path"] for f in doc["files"]] == sorted(
            f["path"] for f in doc["files"])


class TestItIsSensitiveToWhatItClaimsToPin:
    def test_changing_one_byte_changes_the_digest(self, tmp_path):
        root = _tree(tmp_path, {"a.py": "x = 1\n"})
        before = code_digest.build(root)["canonical_digest"]
        with open(os.path.join(root, "a.py"), "w") as fh:
            fh.write("x = 2\n")
        assert code_digest.build(root)["canonical_digest"] != before

    def test_adding_a_file_changes_the_digest(self, tmp_path):
        root = _tree(tmp_path, {"a.py": "x = 1\n"})
        before = code_digest.build(root)["canonical_digest"]
        with open(os.path.join(root, "b.py"), "w") as fh:
            fh.write("y = 1\n")
        assert code_digest.build(root)["canonical_digest"] != before

    def test_the_manifest_names_every_file_that_went_into_the_digest(self, tmp_path):
        root = _tree(tmp_path, {"a.py": "1\n", "s/b.json": "{}\n", "s/c.py": "2\n"})
        doc = code_digest.build(root)
        assert sorted(f["path"] for f in doc["files"]) == ["a.py", "s/b.json", "s/c.py"]
        assert doc["n_files"] == 3 and doc["n_py"] == 2 and doc["n_json"] == 1


class TestTheIncludeRuleIsExplicit:
    def test_caches_and_vcs_directories_are_excluded(self, tmp_path):
        root = _tree(tmp_path, {
            "a.py": "1\n",
            "__pycache__/a.cpython-312.pyc.py": "junk\n",
            ".pytest_cache/x.json": "{}\n",
        })
        doc = code_digest.build(root)
        assert [f["path"] for f in doc["files"]] == ["a.py"]

    def test_files_that_are_not_py_or_json_are_excluded(self, tmp_path):
        root = _tree(tmp_path, {"a.py": "1\n", "README.md": "# hi\n", "d.txt": "x\n"})
        doc = code_digest.build(root)
        assert [f["path"] for f in doc["files"]] == ["a.py"]

    def test_the_rule_is_stated_not_implied_by_a_file_count(self):
        # "65 py + 3 json" is an OUTCOME of a recipe. Quoting the outcome as the recipe
        # is how the irreproducible digest happened.
        assert "*.py" in code_digest.INCLUDE_RULE
        assert "sorted" in code_digest.INCLUDE_RULE


class TestWhatARunActuallyBinds:
    def test_the_binding_is_the_tuple_never_the_digest_alone(self, tmp_path):
        doc = code_digest.build(_tree(tmp_path, {"a.py": "1\n"}))
        assert set(doc["git"]) == {"commit", "clean_tree", "dirty_paths"}
        for part in ("commit", "clean_tree", "manifest_sha256", "canonical_digest"):
            assert part in doc["binding_rule"]

    def test_a_dirty_tree_is_reported_as_dirty(self):
        # Run against the real repo: whatever the state, it must be REPORTED, because a
        # digest taken from a dirty tree does not identify the commit printed beside it.
        here = os.path.dirname(os.path.dirname(os.path.abspath(code_digest.__file__)))
        doc = code_digest.build(here, repo=os.path.dirname(os.path.dirname(here)))
        assert doc["git"]["clean_tree"] in (True, False)
        if doc["git"]["clean_tree"] is False:
            assert doc["git"]["dirty_paths"]

    def test_the_real_stage2_tree_digests_and_reports_its_manifest(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(code_digest.__file__)))
        doc = code_digest.build(here, repo=os.path.dirname(os.path.dirname(here)))
        assert doc["n_files"] > 0
        assert len(doc["manifest_sha256"]) == 64
        assert len(doc["canonical_digest"]) == code_digest.DIGEST_LEN
        assert len(doc["files"]) == doc["n_files"]

    def test_the_retired_digest_is_not_produced_by_this_script(self):
        # The number the packet cited. It is not reproducible from anything, and the
        # binding must never quote it again.
        here = os.path.dirname(os.path.dirname(os.path.abspath(code_digest.__file__)))
        doc = code_digest.build(here, repo=os.path.dirname(os.path.dirname(here)))
        assert not doc["canonical_digest"].startswith("5694444e")


# --------------------------------------------------------------------------- #
# M2 (re-audit) — the digest was reproducible but NOTHING BOUND IT. A run that does
# not carry the code identity is a run nobody can tie to the code that produced it.
# --------------------------------------------------------------------------- #
class TestTheRunBindingCarriesTheCodeIdentity:
    def test_the_tuple_is_the_binding_not_the_digest_alone(self):
        b = code_digest.run_binding()
        assert set(b) >= {"commit", "clean_tree", "manifest_sha256",
                          "canonical_digest"}
        assert len(b["manifest_sha256"]) == 64
        assert len(b["canonical_digest"]) == code_digest.DIGEST_LEN

    def test_a_release_lane_REFUSES_a_dirty_tree(self, tmp_path):
        # A digest taken over uncommitted bytes does not identify the commit printed
        # beside it. A release-grade run refuses rather than annotating.
        import subprocess
        repo = str(tmp_path)
        subprocess.run(["git", "init", "-q", repo], check=True)
        subprocess.run(["git", "-C", repo, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", repo, "config", "user.name", "t"], check=True)
        with open(os.path.join(repo, "a.py"), "w") as fh:
            fh.write("x = 1\n")
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        subprocess.run(["git", "-C", repo, "commit", "-qm", "init"], check=True)

        clean = code_digest.run_binding(repo, repo, require_clean=True)
        assert clean["clean_tree"] is True

        with open(os.path.join(repo, "a.py"), "w") as fh:
            fh.write("x = 2\n")                      # uncommitted
        with pytest.raises(code_digest.DirtyTreeError) as exc:
            code_digest.run_binding(repo, repo, require_clean=True)
        assert code_digest.DIRTY_TREE_REFUSED in str(exc.value)

        # ...and a NON-release lane records it honestly rather than pretending
        dirty = code_digest.run_binding(repo, repo, require_clean=False)
        assert dirty["clean_tree"] is False

    def test_the_direct_run_binds_it(self, synthetic_run):
        from direct import run_screen
        res = run_screen.build_screen(synthetic_run())
        with open(os.path.join(res["out_dir"], "provenance.json")) as fh:
            prov = json.load(fh)
        ci = prov["run_binding"]["code_identity"]
        assert ci["canonical_digest"] == code_digest.run_binding()["canonical_digest"]
        assert ci["manifest_sha256"] == code_digest.run_binding()["manifest_sha256"]

    def test_the_temporal_run_binds_it(self, temporal_run):
        from direct.temporal import run_temporal
        res = run_temporal.build_temporal(temporal_run())
        with open(os.path.join(res["out_dir"], "temporal_provenance.json")) as fh:
            prov = json.load(fh)
        ci = prov["run_binding"]["code_identity"]
        assert ci["canonical_digest"] == code_digest.run_binding()["canonical_digest"]

    def test_the_run_id_MOVES_when_the_code_identity_moves(self, synthetic_run):
        # The tuple is bound INTO the identity, not merely printed beside it.
        from direct import run_screen, runid
        args = synthetic_run()
        res = run_screen.build_screen(args)
        with open(os.path.join(res["out_dir"], "provenance.json")) as fh:
            binding = json.load(fh)["run_binding"]
        moved = json.loads(json.dumps(binding))
        moved["code_identity"]["canonical_digest"] = "0" * 16
        assert runid.run_id_of(moved)[0] != res["run_id"]

    def test_a_release_BUILD_refuses_a_dirty_tree_through_the_real_path(
            self, synthetic_run, monkeypatch):
        """The gate, through build_screen itself — not just the helper."""
        from direct import run_screen
        args = synthetic_run(lane="production", stage1_selectable=True)
        args.allow_dirty_tree = False           # a real release does not opt out

        # force the "dirty" verdict without touching the developer's actual tree
        monkeypatch.setattr(code_digest, "git_identity", lambda repo: {
            "commit": "d" * 40, "clean_tree": False, "dirty_paths": ["a.py"]})

        with pytest.raises(code_digest.DirtyTreeError):
            run_screen.build_screen(args)

    def test_the_dirty_opt_out_is_RECORDED_and_changes_the_run_id(
            self, synthetic_run, monkeypatch):
        # A dirty release is allowed to exist; it is not allowed to look like a clean one.
        from direct import run_screen
        monkeypatch.setattr(code_digest, "git_identity", lambda repo: {
            "commit": "d" * 40, "clean_tree": False, "dirty_paths": ["a.py"]})
        dirty = run_screen.build_screen(synthetic_run())      # fixture opts out
        with open(os.path.join(dirty["out_dir"], "provenance.json")) as fh:
            ci = json.load(fh)["run_binding"]["code_identity"]
        assert ci["clean_tree"] is False
        assert ci["clean_checkout_required"] is False

        monkeypatch.setattr(code_digest, "git_identity", lambda repo: {
            "commit": "d" * 40, "clean_tree": True, "dirty_paths": []})
        clean = run_screen.build_screen(synthetic_run())
        assert clean["run_id"] != dirty["run_id"]     # the flag is BOUND, not annotated
