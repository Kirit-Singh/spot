"""The cache sweep — the two defects that quarantined W2's real extracted cache.

`/home/tcelab/.cache/spot-stage3-universe`: three source provenance files malformed from
unescaped quoted ETags, and containing local paths. Both are refused here, and the
malformed-JSON one is refused in the specific way that matters — as a FAILURE, not a skip.
"""
from __future__ import annotations

import json
import os

import pytest

from verifier import cache_sweep as cs
from verifier.report import Report


def _failed(rep):
    return [n for n, ok, _ in rep.checks if not ok]


def _write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


@pytest.fixture
def clean_cache(tmp_path):
    root = str(tmp_path / "cache")
    _write(root, "source_manifest.json", json.dumps({
        "source": "chembl", "release": "CHEMBL_37",
        "url": "https://ftp.ebi.ac.uk/pub/databases/chembl/",
        "etag": "33c20374abc", "bytes": 5_764_252_857}))
    _write(root, "universe/universe.json", json.dumps({"n_targets": 11526}))
    return root


# --------------------------------------------------------------------------- #
# The malformed-JSON defect. It must FAIL, not be skipped.
# --------------------------------------------------------------------------- #
def test_an_unescaped_quoted_etag_makes_the_file_UNPARSEABLE_and_that_FAILS(tmp_path):
    """The exact bug: the server sends ETag: "abc", written raw it is not JSON."""
    root = str(tmp_path / "cache")
    _write(root, "provenance/chembl.json",
           '{"source": "chembl", "etag": ""33c20374abc""}')

    rep = Report()
    cs.sweep(rep, root)
    failures = _failed(rep)
    assert any("EVERY json artifact" in n for n in failures)


def test_the_refusal_NAMES_the_file_and_diagnoses_the_etag(tmp_path):
    root = str(tmp_path / "cache")
    _write(root, "provenance/uniprot.json",
           '{"source": "uniprot", "etag": ""7ef6a677""}')

    rep = Report()
    cs.sweep(rep, root)
    detail = next(d for n, ok, d in rep.checks
                  if not ok and "EVERY json artifact" in n)
    assert "provenance/uniprot.json" in detail
    assert "UNESCAPED QUOTED ETag" in detail


def test_a_malformed_file_is_NOT_silently_skipped(tmp_path):
    """`try: json.load except: continue` would report green here. That is the trap:
    'every file I could read was fine' is not a statement about the cache."""
    root = str(tmp_path / "cache")
    _write(root, "good.json", json.dumps({"ok": True}))
    _write(root, "bad.json", '{"etag": ""x""}')

    parsed, failures = cs.parse_all_json(root)
    assert "good.json" in parsed          # the readable one parsed
    assert failures                       # ...and the unreadable one is REPORTED
    rep = Report()
    cs.sweep(rep, root)
    assert _failed(rep), "a cache with one unparseable file is not green"


def test_a_clean_cache_parses(clean_cache):
    rep = Report()
    parsed = cs.sweep(rep, clean_cache)
    assert not _failed(rep)
    assert set(parsed) == {"source_manifest.json", "universe/universe.json"}


# --------------------------------------------------------------------------- #
# Machine-local paths.
# --------------------------------------------------------------------------- #
def test_a_local_path_in_a_provenance_file_is_refused(tmp_path):
    root = str(tmp_path / "cache")
    _write(root, "provenance/chembl.json", json.dumps({
        "source": "chembl",
        "extracted_from": "/home/tcelab/.cache/spot-stage3-universe/chembl_37.db"}))

    rep = Report()
    cs.sweep(rep, root)
    assert any("machine-local path" in n for n in _failed(rep))


def test_the_leak_is_reported_with_its_json_path(tmp_path):
    root = str(tmp_path / "cache")
    _write(root, "p.json", json.dumps({"a": {"b": ["/home/tcelab/secret/x.db"]}}))
    rep = Report()
    cs.sweep(rep, root)
    detail = next(d for n, ok, d in rep.checks if not ok and "machine-local" in n)
    assert "p.json" in detail and ".a.b[0]" in detail


@pytest.mark.parametrize("leak", [
    "/home/tcelab/x", "/Users/kiritsingh/y", "/mnt/tcenas/datasets/z", "/tmp/scratch/w"])
def test_every_machine_path_shape_is_caught(tmp_path, leak):
    root = str(tmp_path / "cache")
    _write(root, "p.json", json.dumps({"path": leak}))
    rep = Report()
    cs.sweep(rep, root)
    assert any("machine-local path" in n for n in _failed(rep))


def test_a_public_url_is_not_a_leak(clean_cache):
    rep = Report()
    cs.sweep(rep, clean_cache)
    assert not any("machine-local" in n for n in _failed(rep))


# --------------------------------------------------------------------------- #
# Tokens.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("token", [
    "ghp_abcdefghijklmnopqrstuvwxyz01",
    "AKIAIOSFODNN7EXAMPLE",
    "sk-abcdefghijklmnopqrstuvwxyz012345",
    "xoxb-1234567890-abcdefghij",
])
def test_a_credential_in_a_public_artifact_is_refused(tmp_path, token):
    root = str(tmp_path / "cache")
    _write(root, "p.json", json.dumps({"note": token}))
    rep = Report()
    cs.sweep(rep, root)
    assert any("token, key or authorization" in n for n in _failed(rep))


def test_an_authorization_header_is_refused(tmp_path):
    root = str(tmp_path / "cache")
    _write(root, "p.json", json.dumps({"headers": {"h": "Authorization: Bearer abc123xyz"}}))
    rep = Report()
    cs.sweep(rep, root)
    assert any("token, key or authorization" in n for n in _failed(rep))


def test_a_clean_cache_carries_no_tokens(clean_cache):
    rep = Report()
    cs.sweep(rep, clean_cache)
    assert not any("token" in n for n in _failed(rep))


# --------------------------------------------------------------------------- #
# ETag storage — the defect refused at its source.
# --------------------------------------------------------------------------- #
def test_a_quoted_etag_stored_as_a_string_is_still_refused(tmp_path):
    """Even when it happens to parse, a quote-wrapped ETag is the same bug one step later."""
    root = str(tmp_path / "cache")
    _write(root, "p.json", json.dumps({"etag": '"33c20374abc"'}))
    rep = Report()
    cs.sweep(rep, root)
    assert any("ETag is stored as a clean string" in n for n in _failed(rep))


def test_a_clean_etag_passes(clean_cache):
    rep = Report()
    cs.sweep(rep, clean_cache)
    assert not any("ETag" in n for n in _failed(rep))


# --------------------------------------------------------------------------- #
# The sweep runs BEFORE content checks.
# --------------------------------------------------------------------------- #
def test_a_missing_cache_root_is_refused(tmp_path):
    rep = Report()
    got = cs.sweep(rep, str(tmp_path / "nope"))
    assert got is None
    assert _failed(rep)


def test_the_real_quarantined_cache_is_refused_if_present():
    """If W2's cache is still on disk in its quarantined state, this says so."""
    root = "/home/tcelab/.cache/spot-stage3-universe"
    if not os.path.isdir(root):
        pytest.skip("W2's cache is not on this host (expected: it is quarantined)")
    rep = Report()
    cs.sweep(rep, root)
    # Not asserting failure — W2 may have regenerated it. Asserting the sweep RAN.
    assert rep.checks, "the sweep must actually inspect the real cache when it exists"
