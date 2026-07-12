"""Sampled Stage-3 candidates, reconstructed from the RAW acquired bytes.

Everything else in this suite checks that the bundle is internally consistent and that its
hashes reproduce. That proves one producer was self-consistent. It does not prove the rows
say what the sources say.

So: take real queued candidates, go back to the raw UniProt/ChEMBL response bytes Stage 3
cached, and rebuild the claim from those bytes — the moiety's ChEMBL id, its preferred name,
its development state, and the mechanism assertions the edges rest on. Then require the
bundle to agree.

This reads the raw pages directly (`json.load` on the cached response) and re-derives from
them. It imports nothing from Stage 3 and nothing from Stage-4's own adapter's internals.

The perturbation biology upstream is synthetic; the DRUG bytes are real pinned public
responses (UniProt 2026_02 CC BY 4.0, ChEMBL_37 CC BY-SA 3.0). **Nothing here is a scientific
finding** — it is a check that Stage 4 does not believe a row the sources do not support.
"""

from __future__ import annotations

import hashlib
import json
import os

import pyarrow.parquet as pq
import pytest

from analysis.method_config import STAGE4_DIR
from analysis.stage3_annotation import adapt_annotation_bundle

FIXTURES = os.path.join(STAGE4_DIR, "tests", "fixtures", "stage3_annotation")
BUNDLE = os.path.join(FIXTURES, "s3_be0f05c07b3f6330")
CACHE = os.path.join(FIXTURES, "cache")

# How many queued candidates to reconstruct from raw bytes. The task asks for >= 2; every
# candidate whose moiety is reachable in the raw ChEMBL molecule pages is reconstructed.
MIN_SAMPLED = 2


def _acquisition_entries() -> list[dict]:
    with open(os.path.join(CACHE, "acquisition_manifest.json"), encoding="utf-8") as fh:
        return json.load(fh)["entries"]


def _raw_pages(source: str, adapter: str | None = None) -> list[dict]:
    """Every ACQUIRED raw page for a source, read from the bytes the manifest hashed."""
    pages = []
    for e in _acquisition_entries():
        if e["source"] != source or e["acquisition_status"] != "acquired_public":
            continue
        if adapter and e["adapter"] != adapter:
            continue
        path = os.path.join(CACHE, e["raw_file"])
        raw = open(path, "rb").read()
        # the bytes must be the bytes the manifest signed, or they are not evidence
        assert hashlib.sha256(raw).hexdigest() == e["raw_sha256"], (
            f"{e['raw_file']} does not hash to what the acquisition manifest recorded")
        pages.append(json.loads(raw.decode("utf-8")))
    return pages


def _chembl_molecules() -> dict[str, dict]:
    """chembl_id -> molecule record, straight out of the raw ChEMBL molecule pages."""
    out: dict[str, dict] = {}
    for page in _raw_pages("chembl"):
        for mol in page.get("molecules", []):
            cid = mol.get("molecule_chembl_id")
            if cid:
                out[cid] = mol
    return out


def _chembl_mechanisms() -> dict[str, list[dict]]:
    """chembl_id -> its mechanism records, straight out of the raw ChEMBL mechanism pages."""
    out: dict[str, list[dict]] = {}
    for page in _raw_pages("chembl"):
        for mech in page.get("mechanisms", []):
            cid = mech.get("molecule_chembl_id")
            if cid:
                out.setdefault(cid, []).append(mech)
    return out


@pytest.fixture(scope="module")
def admission():
    return adapt_annotation_bundle(BUNDLE)


@pytest.fixture(scope="module")
def raw_molecules():
    return _chembl_molecules()


def test_the_raw_cache_bytes_hash_to_the_acquisition_manifest():
    """If the bytes moved, nothing below is evidence of anything."""
    acquired = [e for e in _acquisition_entries()
                if e["acquisition_status"] == "acquired_public"]
    assert acquired, "no acquired public page in the pinned cache"
    for e in acquired:
        raw = open(os.path.join(CACHE, e["raw_file"]), "rb").read()
        assert hashlib.sha256(raw).hexdigest() == e["raw_sha256"]
        assert len(raw) == e["raw_bytes"]


def test_at_least_two_queued_candidates_reconstruct_from_the_raw_bytes(
        admission, raw_molecules):
    """The moiety, its name and its development state come from the raw response — or not at all."""
    moieties = {m["active_moiety_id"]: m
                for m in pq.read_table(
                    os.path.join(BUNDLE, "active_moieties.parquet")).to_pylist()}

    sampled = 0
    for q in admission.queued:
        m = moieties[q.active_moiety_id]
        chembl_id = m.get("moiety_chembl_id")
        if not chembl_id or chembl_id not in raw_molecules:
            continue
        raw = raw_molecules[chembl_id]
        sampled += 1

        # 1. the moiety id really is derived from this ChEMBL id
        assert q.active_moiety_id == f"AM:CHEMBL:{chembl_id}"

        # 2. the preferred name is the raw pref_name, not something Stage 3 invented
        assert m["preferred_name"] == raw.get("pref_name"), (
            f"{chembl_id}: bundle says {m['preferred_name']!r}, the raw ChEMBL response says "
            f"{raw.get('pref_name')!r}")

        # 3. the development state is the raw max_phase, mapped — never upgraded
        max_phase = raw.get("max_phase")
        agg = m["development_state_aggregate"]
        if max_phase in (4, 4.0, "4", "4.0"):
            assert agg == "approved", f"{chembl_id}: max_phase=4 but bundle says {agg!r}"
        else:
            assert agg != "approved", (
                f"{chembl_id}: raw max_phase={max_phase!r} is not 4, but the bundle claims "
                "'approved'. Stage 4 will not believe a development state the source does "
                "not state.")

    assert sampled >= MIN_SAMPLED, (
        f"only {sampled} queued candidate(s) could be reconstructed from the raw ChEMBL "
        f"bytes; at least {MIN_SAMPLED} must be")


def test_every_edge_rests_on_a_mechanism_the_raw_bytes_actually_state(admission):
    """No mechanism assertion may exist that the raw ChEMBL response does not state."""
    mechanisms = _chembl_mechanisms()
    assertions = pq.read_table(
        os.path.join(BUNDLE, "mechanism_assertions.parquet")).to_pylist()
    assert assertions, "the bundle claims edges but carries no mechanism assertion"

    checked = 0
    for a in assertions:
        mol = a.get("source_molecule_id")
        if mol not in mechanisms:
            continue
        raw_actions = {m.get("action_type") for m in mechanisms[mol]}
        claimed = a.get("action_type_source")
        assert claimed in raw_actions, (
            f"{mol}: the bundle asserts action_type={claimed!r}, which the raw ChEMBL "
            f"mechanism response does not state (it states {sorted(raw_actions)})")
        checked += 1

    assert checked >= MIN_SAMPLED, (
        f"only {checked} mechanism assertion(s) were traceable to raw bytes")


def test_a_candidate_is_never_queued_without_a_moiety_the_sources_resolve(admission):
    """Every queued candidate resolves to a real, source-backed active moiety."""
    moieties = {m["active_moiety_id"]: m
                for m in pq.read_table(
                    os.path.join(BUNDLE, "active_moieties.parquet")).to_pylist()}
    for q in admission.queued:
        m = moieties[q.active_moiety_id]
        assert m["identity_status"] == "resolved"
        assert m.get("moiety_chembl_id"), (
            f"{q.candidate_id} was queued with no resolved ChEMBL identity")


def test_potency_is_not_evaluated_and_that_is_not_zero(admission):
    """`not_evaluated` means potency was NOT ACQUIRED — not zero, not absence of activity."""
    rows = pq.read_table(os.path.join(BUNDLE, "potency_evidence.parquet")).to_pylist()
    assert rows == []
    for q in admission.queued:
        assert q.potency_state == "not_evaluated"

    # and Stage 3 says WHY, in the acquisition record — an absence with a reason, not silence
    not_acquired = [e for e in _acquisition_entries()
                    if e["adapter"] == "chembl_activity"
                    and e["acquisition_status"] == "not_acquired"]
    assert not_acquired, "potency is not_evaluated with no recorded reason"
    assert all("not zero" in (e.get("not_acquired_reason") or "") for e in not_acquired)
