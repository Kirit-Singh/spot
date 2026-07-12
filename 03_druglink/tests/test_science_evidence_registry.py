"""The Science evidence registry: references RESOLVE, and their bytes RE-HASH.

Before the registry, a Claude Science reference was checked for SHAPE only — an id, 64
hex characters, a known type. Nothing opened the record. A reference to a record that did
not exist, or to bytes that had since changed, passed every check. The hash was
decoration.

These tests attack the binding itself: delete the record, alter the record, alter the raw
bytes, alter the structured bytes, mistype it, and reference it with no registry at all.
Every one must fail CLOSED — a typed refusal, never a warning that passes.

The verifier used here is the INDEPENDENT one (``verifier/science_registry.py``), which
imports nothing from ``druglink``. A verifier that reused the writer's own hashing would
prove only that the writer agreed with itself.
"""
from __future__ import annotations

import json
import os

import pytest
import science_fixture

from druglink import science_registry as sr
from verifier import science_registry as vsr


def _registry(tmp_path):
    root = str(tmp_path / "registry")
    return root, science_fixture.make(root)


def _record_path(root, ref):
    index = sr.load_index(root)
    entry = index["records"][ref["science_evidence_id"]]
    return root, entry


# --------------------------------------------------------------------------- #
# Happy path: it resolves, and every hash is re-derived from bytes on disk.
# --------------------------------------------------------------------------- #
def test_a_referenced_record_resolves_and_its_bytes_rehash(tmp_path):
    root, refs = _registry(tmp_path)

    for ref in refs.values():
        record = sr.resolve(root, ref)
        assert record["science_evidence_id"] == ref["science_evidence_id"]
        assert record["record_type"] == ref["record_type"]
        # The record content-addresses to exactly what the reference binds.
        assert sr.record_sha256(record) == ref["science_evidence_sha256"]
        # Provenance is present: a record nobody can be attributed to is not evidence.
        for field in ("session_id", "model_id", "method_id", "source_chain"):
            assert record["provenance"][field] is not None

    # ...and the INDEPENDENT verifier agrees, from its own implementation.
    assert vsr.verify_refs(root, list(refs.values())) == []


def test_the_independent_verifier_rehashes_rather_than_trusting_the_writer(tmp_path):
    """The verifier's hash must be re-derived, not copied from the record."""
    root, refs = _registry(tmp_path)
    ref = refs["sci_1"]
    _, entry = _record_path(root, ref)

    with open(os.path.join(root, entry["record_file"]), "rb") as fh:
        record = json.loads(fh.read().decode("utf-8"))

    # Two separate implementations, same canonical bytes, same digest.
    assert vsr.record_sha256(record) == sr.record_sha256(record)
    assert vsr.record_sha256(record) == ref["science_evidence_sha256"]
    assert vsr.canonical_bytes(record) == sr.canonical_bytes(record)


# --------------------------------------------------------------------------- #
# Fail closed: missing.
# --------------------------------------------------------------------------- #
def test_a_missing_record_fails_closed(tmp_path):
    root, refs = _registry(tmp_path)

    dangling = {"science_evidence_id": "sci_never_written",
                "science_evidence_sha256": "d" * 64,
                "record_type": "literature_support"}

    with pytest.raises(sr.ScienceRegistryError, match="not in the registry|dangling"):
        sr.resolve(root, dangling)

    fails = vsr.verify_refs(root, [dangling])
    assert fails and "dangling" in fails[0]

    # A reference with NO registry at all is not a binding either.
    with pytest.raises(sr.ScienceRegistryError, match="no science-evidence registry|no "
                                                      "registry was supplied"):
        sr.resolve_all(None, [refs["sci_1"]], where="test")
    assert vsr.verify_refs(None, [refs["sci_1"]])


def test_a_deleted_record_file_fails_closed(tmp_path):
    root, refs = _registry(tmp_path)
    ref = refs["sci_2"]
    _, entry = _record_path(root, ref)
    os.remove(os.path.join(root, entry["record_file"]))

    with pytest.raises(sr.ScienceRegistryError, match="record file is missing"):
        sr.resolve(root, ref)
    assert vsr.verify_refs(root, [ref])


# --------------------------------------------------------------------------- #
# Fail closed: altered.
# --------------------------------------------------------------------------- #
def test_an_altered_record_fails_closed(tmp_path):
    """Change the record, and it is no longer the record that was cited."""
    root, refs = _registry(tmp_path)
    ref = refs["sci_1"]
    _, entry = _record_path(root, ref)
    path = os.path.join(root, entry["record_file"])

    with open(path, "rb") as fh:
        record = json.loads(fh.read().decode("utf-8"))
    record["provenance"]["model_id"] = "some-other-model"   # re-attribute the claim
    with open(path, "wb") as fh:
        fh.write(sr.canonical_bytes(record))

    with pytest.raises(sr.ScienceRegistryError, match="was ALTERED"):
        sr.resolve(root, ref)

    fails = vsr.verify_refs(root, [ref])
    assert fails and "ALTERED" in fails[0]


def test_altered_raw_bytes_fail_closed(tmp_path):
    """The record can be untouched and still be lying about what Science said."""
    root, refs = _registry(tmp_path)
    ref = refs["sci_3"]
    _, entry = _record_path(root, ref)

    with open(os.path.join(root, entry["raw_file"]), "wb") as fh:
        fh.write(b"a completely different claim, quietly substituted")

    with pytest.raises(sr.ScienceRegistryError, match="raw bytes were ALTERED"):
        sr.resolve(root, ref)

    fails = vsr.verify_refs(root, [ref])
    assert fails and "raw bytes ALTERED" in fails[0]


def test_altered_structured_bytes_fail_closed(tmp_path):
    root, refs = _registry(tmp_path)
    ref = refs["sci_2"]
    _, entry = _record_path(root, ref)

    with open(os.path.join(root, entry["structured_file"]), "wb") as fh:
        fh.write(sr.canonical_bytes({"claim": "reversed", "confidence": "certain"}))

    with pytest.raises(sr.ScienceRegistryError, match="structured bytes were ALTERED"):
        sr.resolve(root, ref)
    assert vsr.verify_refs(root, [ref])


def test_a_record_type_mismatch_fails_closed(tmp_path):
    """A contradiction cannot be cited as literature support."""
    root, refs = _registry(tmp_path)
    mistyped = dict(refs["sci_3"], record_type="literature_support")

    with pytest.raises(sr.ScienceRegistryError, match="ALTERED|record_type"):
        sr.resolve(root, mistyped)
    assert vsr.verify_refs(root, [mistyped])


def test_the_record_type_enum_is_closed(tmp_path):
    root, refs = _registry(tmp_path)
    junk = dict(refs["sci_1"], record_type="peer_reviewed_truth")

    with pytest.raises(sr.ScienceRegistryError, match="CLOSED enum"):
        sr.check_ref("test", junk)
    assert vsr.verify_refs(root, [junk])


# --------------------------------------------------------------------------- #
# A reference is a TYPED TRIPLE. Never an id alone, never an embedded blob.
# --------------------------------------------------------------------------- #
def test_a_reference_is_a_typed_triple_never_an_id_alone(tmp_path):
    root, refs = _registry(tmp_path)

    for missing in sr.REF_FIELDS:
        partial = {k: v for k, v in refs["sci_1"].items() if k != missing}
        with pytest.raises(sr.ScienceRegistryError, match=f"missing {missing!r}"):
            sr.check_ref("test", partial)
        assert vsr.verify_refs(root, [partial])

    # An interpretation is REFERENCED, never embedded as a free-form object or string.
    # A bare object is refused for what it lacks; a non-object for what it is.
    for embedded in ("CTLA4 is clearly central", 42, None):
        with pytest.raises(sr.ScienceRegistryError, match="typed record"):
            sr.check_ref("test", embedded)
    with pytest.raises(sr.ScienceRegistryError, match="missing"):
        sr.check_ref("test", {"note": "central"})


def test_a_registry_with_no_index_is_a_refusal_not_an_empty_registry(tmp_path):
    empty = str(tmp_path / "nothing")
    os.makedirs(empty, exist_ok=True)

    with pytest.raises(sr.ScienceRegistryError, match="no registry.json"):
        sr.load_index(empty)
    with pytest.raises(vsr.RegistryVerifyError, match="no registry.json"):
        vsr.load_index(empty)


def test_the_bundle_registry_block_carries_no_local_paths(tmp_path):
    root, _refs = _registry(tmp_path)
    block = sr.registry_ref(root)

    assert block["science_registry"] == "provided"
    assert block["n_records"] == 4
    assert len(block["science_registry_sha256"]) == 64
    # Nothing that leaks where this machine keeps its files.
    assert str(tmp_path) not in json.dumps(block)
    assert sr.registry_ref(None)["science_registry"] == "not_provided"
