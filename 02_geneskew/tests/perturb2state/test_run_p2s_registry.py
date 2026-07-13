"""Regression: ``run_p2s.build()`` unpacked ``load_registry`` into the wrong arity.

THE BUG
-------
``direct.io_data.load_registry`` returns a FOUR-key dict. ``run_p2s.build()`` unpacked it
into THREE names::

    programs, reg_sha, reg = io_data.load_registry(args.registry)   # ValueError

That is the FIRST statement of work ``build()`` does, so the entrypoint could not run at all.
``direct.io_data`` was changed under this lane and nothing noticed, because no test ever
called ``build()`` -- the whole orchestrator was untested.

WHAT THESE TESTS PIN
--------------------
Not just "it works now". They pin the CONTRACT that broke: the arity of what
``load_registry`` returns, and WHICH of its two hashes a run is allowed to bind. A test that
only asserted the happy path would go green again the next time ``direct.io_data`` grows a
key -- which is exactly how this got here.
"""
from __future__ import annotations

import hashlib
import json

import pytest
from direct import io_data
from perturb2state import run_p2s

DECLARED_LIE = "d" * 64


def _registry(tmp_path):
    """A registry whose self-declared hash is a LIE, so binding it would be visible."""
    doc = {
        "registry_sha256": DECLARED_LIE,
        "programs": [
            {"program_id": "treg_like", "panel_ensembl": ["ENSG1"],
             "control_ensembl": ["ENSG2"]},
            {"program_id": "th1_like", "panel_ensembl": ["ENSG3"],
             "control_ensembl": ["ENSG4"]},
        ],
    }
    path = tmp_path / "stage01_program_registry.json"
    path.write_text(json.dumps(doc))
    return str(path)


def test_load_registry_returns_FOUR_keys_and_a_3_tuple_unpack_raises(tmp_path):
    """The contract that broke, pinned directly.

    If ``direct.io_data`` ever goes back to three keys -- or grows to five -- this fails
    LOUDLY here rather than silently at the first line of a real run.
    """
    doc = io_data.load_registry(_registry(tmp_path))
    assert set(doc) == {"programs", "file_sha256", "declared_sha256", "raw"}

    with pytest.raises(ValueError, match="too many values to unpack"):
        _programs, _sha, _raw = doc          # the exact line that was shipped


def test_build_loads_the_registry_without_a_ValueError(tmp_path):
    """The regression itself: the load that used to raise before any work happened."""
    programs, reg_sha = run_p2s.load_program_registry(_registry(tmp_path))

    assert set(programs) == {"treg_like", "th1_like"}
    assert programs["treg_like"]["panel_ensembl"] == ["ENSG1"]
    assert isinstance(reg_sha, str) and len(reg_sha) == 64


def test_the_bound_registry_hash_is_DERIVED_never_the_self_declared_one(tmp_path):
    """A file cannot contain its own hash, so a self-declared one proves nothing.

    ``direct.trust``: "a self-declared hash proves nothing and is trivially forged". The
    registry here declares a hash that is a flat lie; the run must bind the hash of the bytes
    on disk, and must not repeat the lie into its own provenance.
    """
    path = _registry(tmp_path)
    _programs, reg_sha = run_p2s.load_program_registry(path)

    expected = hashlib.sha256(open(path, "rb").read()).hexdigest()
    assert reg_sha == expected
    assert reg_sha != DECLARED_LIE

    # ...and the lie really was there to be bound, so this test could actually fail
    assert io_data.load_registry(path)["declared_sha256"] == DECLARED_LIE


def test_the_registry_hash_moves_when_the_registry_moves(tmp_path):
    """A provenance hash that did not follow the bytes would not be provenance."""
    path = _registry(tmp_path)
    _p, before = run_p2s.load_program_registry(path)

    doc = json.loads(open(path).read())
    doc["programs"].append({"program_id": "th17_like", "panel_ensembl": ["ENSG9"]})
    open(path, "w").write(json.dumps(doc))

    programs, after = run_p2s.load_program_registry(path)
    assert after != before
    assert "th17_like" in programs
