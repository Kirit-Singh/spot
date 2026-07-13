"""MUTATION 7 — upstream version drift. The pin is checked, never echoed.

A constant in a config file is a claim ABOUT the software; it is not the software. Every
test here hands ``identity`` an OBSERVATION and asks whether it refuses — which is the only
way to tell a pin that is checked from a pin that is printed.
"""
from __future__ import annotations

import pytest
from p2s_arms import config, upstream

# The tree hash is MANDATORY now, and it defaults to the pin — an optional integrity check is
# an integrity check nobody passes. So a "good" observation must carry the REAL pinned tree.
GOOD = {
    "commit": config.UPSTREAM_COMMIT,
    "dirty": False,
    "version": config.UPSTREAM_VERSION,
    "tree_sha256": config.UPSTREAM_TREE_SHA256,
    "_source_root": "/somewhere",
}


def test_the_pinned_software_is_admitted():
    ident = upstream.identity(GOOD)
    assert ident["upstream_commit"] == config.UPSTREAM_COMMIT
    assert ident["upstream_license"] == "MIT"
    assert ident["resolved_at_runtime"] is True


def test_MUTATION_a_drifted_COMMIT_is_refused():
    with pytest.raises(upstream.UpstreamDriftError) as e:
        upstream.identity(dict(GOOD, commit="0" * 40))
    assert e.value.reason == "upstream_commit_drift"


def test_MUTATION_a_drifted_VERSION_is_refused():
    with pytest.raises(upstream.UpstreamDriftError) as e:
        upstream.identity(dict(GOOD, version="9.9.9"))
    assert e.value.reason == "upstream_version_drift"


def test_MUTATION_an_EDITED_FILE_under_the_pinned_commit_is_caught_by_the_TREE_HASH():
    """The commit id cannot detect this. The bytes can.

    This is the whole reason a tree hash exists beside a commit: an edited working file
    leaves the commit id untouched, so a run pinned only on the commit would ratify software
    nobody committed.
    """
    with pytest.raises(upstream.UpstreamDriftError) as e:
        upstream.identity(dict(GOOD, tree_sha256="b" * 64))     # pin applies by DEFAULT
    assert e.value.reason == "upstream_tree_content_drift"
    assert "BYTES DO NOT" in str(e.value)


def test_the_TREE_PIN_is_MANDATORY_not_opt_in():
    """An optional integrity check is an integrity check nobody passes."""
    assert config.UPSTREAM_TREE_SHA256.startswith("623b24ff")
    with pytest.raises(upstream.UpstreamDriftError):
        upstream.identity(dict(GOOD, tree_sha256=None))          # no explicit expect_ arg


def test_MUTATION_a_DIRTY_upstream_checkout_is_refused():
    with pytest.raises(upstream.UpstreamDriftError) as e:
        upstream.identity(dict(GOOD, dirty=True))
    assert e.value.reason == "upstream_tree_is_dirty"


def test_NO_machine_local_path_is_emitted():
    """The path is how the software was found, not what it is."""
    ident = upstream.identity(GOOD)
    assert ident["machine_path_emitted"] is False
    blob = repr(ident)
    for token in ("/home/", "/Users/", "/somewhere", "_source_root"):
        assert token not in blob


def test_the_tree_hash_is_deterministic_and_sees_an_edit(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("y = 2\n")

    first = upstream.tree_sha256(str(tmp_path))
    assert first == upstream.tree_sha256(str(tmp_path))

    (tmp_path / "sub" / "b.py").write_text("y = 3\n")
    assert upstream.tree_sha256(str(tmp_path)) != first


def test_the_tree_hash_ignores_caches_but_not_source(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    base = upstream.tree_sha256(str(tmp_path))

    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "a.pyc").write_bytes(b"\x00\x01")
    assert upstream.tree_sha256(str(tmp_path)) == base


def test_the_REAL_pinned_checkout_matches_the_pin():
    """Smoke: the software actually installed here is the software this lane pinned.

    Skipped where the upstream package is not importable — the real run is on tcefold, and
    a lane that could not be unit-tested off it would be a lane nobody could develop.
    """
    pytest.importorskip("pert2state_model",
                        reason="the pinned upstream package is not installed on this host")
    obs = upstream.probe()
    assert obs["commit"] == config.UPSTREAM_COMMIT
    assert upstream.identity(obs)["upstream_commit"] == config.UPSTREAM_COMMIT
