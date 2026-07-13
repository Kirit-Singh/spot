"""Final admission criterion — sealed re-audit `1f6008c2`, corrected by the primary source.

I recommended REPLACING the mutable UniProt `current_release` locator with an immutable
2026_02 archive. Checked against the publisher: **no such archive exists.**
`previous_releases/` stops at `release-2026_01`, and `current_release/relnotes.txt` reads
"UniProt Release 2026_02". So `current_release/` is where 2026_02 actually lives, and my
recommendation would have asked W2 to point at a URL that does not exist.

**A locator honest about being mutable beats a locator that is stable and wrong.**

So the criterion is not "replace the URL" — it is: keep the truthful locator, BIND the
publisher metadata that proves which release those bytes came from, and REOPEN AND HASH the
provenance file at admission. A manifest that pins a provenance hash while nobody ever opens
the file has pinned nothing — the same defect the audit found for the eligibility artifact,
one file over.
"""
from __future__ import annotations

import json

import pytest

from verifier import source_manifest as sm
from verifier.report import Report


def _failed(rep):
    return [n for n, ok, _ in rep.checks if not ok]


def _hash(doc):
    import hashlib
    return hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


UNIPROT = {
    "name": "uniprot_idmapping", "release": "2026_02", "release_date": "10-Jun-2026",
    "publisher_md5": "7ef6a677d4db949397c3b352c466e499", "size_bytes": 37842957,
    "acquired_sha256": "0741a549" + "0" * 56,
    "accessed_at_utc": "2026-07-13T06:29:16Z",
    "release_metadata_url": "https://ftp.uniprot.org/.../RELEASE.metalink",
    "relnotes_url": "https://ftp.uniprot.org/.../relnotes.txt",
    "current_release_is_mutable_note": "current_release path is mutable; bytes pinned",
}
CHEMBL = {
    "name": "chembl_sqlite", "release": "CHEMBL_37",
    "publisher_sha256": "33c20374" + "0" * 56,
    "acquired_sha256": "33c20374" + "0" * 56,
    "accessed_at_utc": "2026-07-13T06:29:16Z",
    "release_metadata_url": "https://ftp.ebi.ac.uk/.../checksums.txt",
    "doi": "10.6019/CHEMBL.database.37",
}


def _store(tmp_path, prov=None):
    prov = prov if prov is not None else [CHEMBL, UNIPROT]
    (tmp_path / sm.PROVENANCE_FILENAME).write_text(json.dumps(prov))
    manifest = {"extraction": {"public_source_provenance_sha256": _hash(prov)}}
    return str(tmp_path), manifest, prov


# --------------------------------------------------------------------------- #
# The provenance file is REOPENED and HASHED at admission.
# --------------------------------------------------------------------------- #
def test_the_provenance_file_is_reopened_and_hashed(tmp_path):
    root, manifest, _ = _store(tmp_path)
    rep = Report()
    sm.check_provenance_is_reopened_and_hashed(
        rep, store_root=root, manifest=manifest, content_hash_fn=_hash)
    assert not _failed(rep)


def test_a_SWAPPED_provenance_file_is_caught_at_a_NAMED_gate(tmp_path):
    """The audit's failure scenario: swap the file, leave the manifest untouched.

    Nothing else in the store changes. Only reopening the file finds it.
    """
    root, manifest, _ = _store(tmp_path)
    swapped = [CHEMBL, {**UNIPROT, "release": "2026_03",
                        "acquired_sha256": "deadbeef" + "0" * 56}]
    (tmp_path / sm.PROVENANCE_FILENAME).write_text(json.dumps(swapped))

    rep = Report()
    sm.check_provenance_is_reopened_and_hashed(
        rep, store_root=root, manifest=manifest, content_hash_fn=_hash)
    failed = _failed(rep)
    assert failed
    assert sm.GATE_PROVENANCE_DRIFT in failed[0]


def test_a_manifest_that_pins_but_never_opens_has_pinned_NOTHING(tmp_path):
    """One byte altered on disk; the manifest pin is still 'correct'."""
    root, manifest, prov = _store(tmp_path)
    tampered = json.loads(json.dumps(prov))
    tampered[1]["size_bytes"] = 1
    (tmp_path / sm.PROVENANCE_FILENAME).write_text(json.dumps(tampered))

    rep = Report()
    sm.check_provenance_is_reopened_and_hashed(
        rep, store_root=root, manifest=manifest, content_hash_fn=_hash)
    assert _failed(rep)


def test_a_missing_provenance_file_is_refused(tmp_path):
    rep = Report()
    sm.check_provenance_is_reopened_and_hashed(
        rep, store_root=str(tmp_path), manifest={"extraction": {}},
        content_hash_fn=_hash)
    assert _failed(rep)


# --------------------------------------------------------------------------- #
# The publisher metadata proves the release, because the URL cannot.
# --------------------------------------------------------------------------- #
def test_bound_release_metadata_passes():
    rep = Report()
    sm.check_release_metadata_is_bound(rep, [CHEMBL, UNIPROT])
    assert not _failed(rep)


@pytest.mark.parametrize("field", sm.REQUIRED_RELEASE_METADATA["uniprot"])
def test_a_missing_uniprot_release_field_is_refused(field):
    bad = {k: v for k, v in UNIPROT.items() if k != field}
    rep = Report()
    sm.check_release_metadata_is_bound(rep, [CHEMBL, bad])
    assert _failed(rep)


@pytest.mark.parametrize("field", sm.REQUIRED_RELEASE_METADATA["chembl"])
def test_a_missing_chembl_release_field_is_refused(field):
    bad = {k: v for k, v in CHEMBL.items() if k != field}
    rep = Report()
    sm.check_release_metadata_is_bound(rep, [bad, UNIPROT])
    assert _failed(rep)


def test_the_uniprot_locator_must_declare_its_mutability():
    bare = {k: v for k, v in UNIPROT.items()
            if k != "current_release_is_mutable_note"}
    rep = Report()
    sm.check_release_metadata_is_bound(rep, [CHEMBL, bare])
    assert any("honest about being mutable" in n for n in _failed(rep))


def test_no_immutable_2026_02_archive_exists():
    """Verified against the publisher: previous_releases stops at release-2026_01, and
    current_release/relnotes.txt reads 'UniProt Release 2026_02'.

    Demanding an immutable URL would be demanding a fabricated one.
    """
    assert sm.UNIPROT_IMMUTABLE_ARCHIVE_EXISTS is False
