"""M2 — the code digest must be reproducible, or it is not an identifier.

The packet cited `5694444e`. Nothing produces it: the recorded recipe gives `a70f327…`
on clean HEAD and `590f6f7…` at the archived commit, and no first-parent commit yields
`5694444e` at all. These tests exist so that never happens again — the digest is computed
by ONE committed script, and running it twice gives the same bytes.
"""
from __future__ import annotations

import json
import os

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
