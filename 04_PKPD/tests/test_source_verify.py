"""The method's cited sources must be re-verifiable from any checkout, not just one host.

The registry used to pin one developer's absolute paths. Re-hashing them "verified" that
machine and nothing else; on every other checkout the bytes were simply absent, and the
build said nothing about it.
"""

from __future__ import annotations

import json
import os

from analysis.method_config import load_method_bundle
from analysis.source_verify import CACHE_ROOT_ENV, main, verify_sources

METHOD = load_method_bundle()


def test_no_source_entry_carries_a_machine_local_path():
    """A committed absolute path is not a provenance record."""
    raw = json.dumps(METHOD.sources)
    for marker in ("/home/", "/Users/", "/mnt/", "/tmp/", "C:\\"):
        assert marker not in raw, f"machine-local path {marker!r} in the source registry"


def test_every_hashable_source_has_a_public_locator_and_a_cache_filename():
    for s in METHOD.sources["sources"]:
        if s.get("document_acquired") is False:
            continue
        if s.get("raw_sha256"):
            assert s.get("cache_filename"), s["source_id"]
            assert (s.get("retrieval_url") or s.get("url")), s["source_id"]
        for probe in s.get("probes", []) or []:
            assert probe.get("cache_filename") and probe.get("retrieval_url")


def test_a_clean_checkout_reports_not_cached_rather_than_success(monkeypatch, tmp_path):
    """No bytes here. That is reported explicitly — never as a pass, never as a failure."""
    monkeypatch.delenv(CACHE_ROOT_ENV, raising=False)
    report = verify_sources(cache_root=str(tmp_path))

    assert report["status"] == "pass"       # a missing cache is not a mismatch
    assert report["counts"]["verified"] == 0
    assert report["counts"]["not_cached"] > 0
    assert all(r["status"] in ("not_cached", "not_acquired") for r in report["sources"])


def test_cached_bytes_are_re_hashed_and_verified(tmp_path):
    """Plant bytes that DO hash correctly and the source flips to `verified`."""
    entry = next(s for s in METHOD.sources["sources"]
                 if s["source_id"] == "grossman2026_nebpi")
    # We do not bundle the real document; prove the mechanism on bytes we can construct.
    payload = b"grossman-2026-stand-in"
    import hashlib
    digest = hashlib.sha256(payload).hexdigest()

    sources = json.loads(json.dumps(METHOD.sources))
    for s in sources["sources"]:
        if s["source_id"] == "grossman2026_nebpi":
            s["raw_sha256"] = digest
            # This source declares a CONTENT hash too (the raw bytes carry the PMC BioC
            # retrieval-date envelope and are not stable across re-fetches). The stand-in
            # payload has no envelope, so its content hash is its raw hash.
            s["content_sha256"] = digest
    method_dir = tmp_path / "method"
    method_dir.mkdir()
    with open(method_dir / "sources.json", "w", encoding="utf-8") as fh:
        json.dump(sources, fh)

    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / entry["cache_filename"]).write_bytes(payload)

    report = verify_sources(cache_root=str(cache), method_dir=str(method_dir))
    row = next(r for r in report["sources"] if r["source_id"] == "grossman2026_nebpi")
    assert row["status"] == "verified"
    assert row["recomputed_sha256"] == digest


def test_tampered_cached_bytes_are_a_mismatch_and_a_nonzero_exit(tmp_path, capsys):
    """Bytes that are present and WRONG are the one case that fails the gate."""
    entry = next(s for s in METHOD.sources["sources"]
                 if s["source_id"] == "grossman2026_nebpi")
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / entry["cache_filename"]).write_bytes(b"not the paper")

    report = verify_sources(cache_root=str(cache))
    row = next(r for r in report["sources"] if r["source_id"] == "grossman2026_nebpi")
    assert row["status"] == "MISMATCH"
    assert row["recomputed_sha256"] != row["declared_sha256"]
    assert report["status"] == "fail"

    assert main(["--cache-root", str(cache)]) == 1
    assert "MISMATCH" in capsys.readouterr().out


def test_the_2016_article_is_reported_as_never_acquired(tmp_path):
    """It has no bytes, so it can never be `verified`. It must say so out loud."""
    report = verify_sources(cache_root=str(tmp_path))
    row = next(r for r in report["sources"]
               if r["source_id"] == "wager2016_cnsmpo_desirability")
    assert row["status"] == "not_acquired"
    assert row["declared_sha256"] is None


def test_the_cache_root_can_come_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(CACHE_ROOT_ENV, str(tmp_path))
    assert verify_sources()["cache_root"] == str(tmp_path)
    assert os.environ[CACHE_ROOT_ENV] == str(tmp_path)
