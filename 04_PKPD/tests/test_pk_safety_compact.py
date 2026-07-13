"""The served PK/safety document: no machine paths, no retired fields, nothing invented.

Every rule here was a defect first. The served JSON leaked the absolute path of the box it was built
on; it carried Stage-3 fields that had been RETIRED because they let an agonist be labelled a CRISPRi
phenocopy while its action opposed the desired direction; and it asserted, of every moiety, that no
measured CNS exposure existed — a claim about the entire literature, which Stage 4 has not read.
"""

from __future__ import annotations

import json

import pytest

from analysis.emit_pk_safety import (
    RETIRED_STAGE3_FIELDS,
    assert_servable,
    canonical_json,
    content_sha256,
    verify_stage3_content_hash,
)
from analysis.pk_safety_compact import CNS_MPO_MISSING_INPUTS, MEASURED_EXPOSURE_FIELDS


def _doc(**over):
    d = {"schema_id": "spot.stage04_pk_safety_compact.v1", "candidates": [], "unacquired": []}
    d.update(over)
    return d


# ------------------------------------------------------ a served document names no machine

@pytest.mark.parametrize("leak", [
    "/home/tcelab/.spot-runs/stage4-prefetch-20260713/prefetch_receipt.json",
    "/Users/someone/data/x.json",
    "/tmp/scratch/y.json",
])
def test_an_ABSOLUTE_MACHINE_PATH_is_REFUSED(leak):
    """A served document that discloses where this machine keeps its files has told the reader
    nothing about the science and something true about the box."""
    with pytest.raises(ValueError, match="machine path"):
        assert_servable(_doc(evidence_source={"path": leak}))


def test_a_public_SOURCE_URL_containing_home_is_NOT_a_machine_path():
    """`https://www.ncbi.nlm.nih.gov/home/about/policies/` is PubChem's terms document — the exact
    licence a reader must be able to open. A path check that blanket-greps for `/home` deletes the
    provenance it exists to protect: 39 of the 41 'leaks' flagged in review were this URL."""
    doc = _doc(candidates=[{"pk_properties": {"molecular_weight": {"provenance": {
        "source_url": "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/1/property/JSON",
        "license_or_terms_url": "https://www.ncbi.nlm.nih.gov/home/about/policies/"}}}}])
    assert_servable(doc)          # must not raise


# --------------------------------------------------- the retired vocabulary may not render

@pytest.mark.parametrize("field", RETIRED_STAGE3_FIELDS)
def test_a_RETIRED_stage3_field_is_REFUSED(field):
    """`direction_compatible` / `observed_sign_state` let an AGONIST be carried as a CRISPRi
    phenocopy while its action OPPOSED the desired direction. A retired field that still renders is
    a retired field still being believed."""
    with pytest.raises(ValueError, match="RETIRED"):
        assert_servable(_doc(candidates=[{"stage3_arms": [{field: True}]}]))


def test_the_CURRENT_vocabulary_is_what_gets_carried():
    doc = _doc(candidates=[{"stage3_arms": [{
        "directional_evidence_status": "opposed",
        "directional_evidence_reason": "action_opposes_desired_direction",
        "observed_perturbation_support": False,
        "mechanism_phenocopies_modality": False}]}])
    assert_servable(doc)


# ----------------------------------------------------------- the hash is Stage 3's, verified

def test_stage3s_SELF_DECLARED_content_hash_is_RECOMPUTED_not_copied():
    """The binding is to the self-declared `content_sha256` — not the raw file hash, which moves on
    a reformat and says nothing about what the document means. And a declared hash Stage 4 has not
    recomputed is a hash it is taking on trust, which is the one thing binding it is meant to avoid.
    """
    body = {"schema_version": "spot.stage03_ui_drugs.v1", "arms": [], "condition": "Rest"}
    honest = dict(body, content_sha256=content_sha256(dict(body)))
    assert verify_stage3_content_hash(honest, "x.json") == honest["content_sha256"]

    with pytest.raises(ValueError, match="does not describe these bytes"):
        verify_stage3_content_hash(dict(body, content_sha256="0" * 64), "x.json")


def test_the_canonicalization_is_STAGE_3s_rule_ensure_ascii_TRUE():
    """Verified against W16's final files: their declared hash reproduces under ensure_ascii=True
    and NOT under False, which is what Stage 4 was using. Two rules for one hash means each side
    verifies its own idea of the bytes."""
    obj = {"units": "Å²"}
    assert canonical_json(obj) == '{"units":"\\u00c5\\u00b2"}'


def test_the_documents_OWN_content_hash_recomputes():
    doc = _doc(selection="rest")
    doc["content_sha256"] = content_sha256(doc)
    assert content_sha256(doc) == doc["content_sha256"]


# ------------------------------------------------ absence is stated, never claimed too broadly

def test_the_brain_basis_is_what_WE_EXTRACTED_not_a_claim_about_the_LITERATURE():
    """"No source reports a measured Kp,uu for this moiety" is an assertion about everything ever
    published, which Stage 4 has not read. What is true is narrower and checkable: no such value was
    extracted from the sources cached in THIS run."""
    from analysis.pk_safety_compact import _brain_penetrance

    block = _brain_penetrance({})
    assert block["assessment"] == "unknown"
    assert block["assessment_state"] == "not_evaluated"
    assert block["basis"] == "not_extracted_not_available_in_current_sources"
    assert "NOT a claim that no such measurement exists" in block["reason"]

    for field in MEASURED_EXPOSURE_FIELDS:
        cell = block["measured_exposure"][field]
        assert cell["value"] is None
        assert cell["state"] == "not_evaluated"
        assert cell["reason"] == "not_extracted_from_the_sources_cached_in_this_run"


def test_the_proxies_are_never_an_assessment():
    """A molecule can satisfy every physicochemical proxy and never reach the brain."""
    from analysis.pk_safety_compact import _brain_penetrance

    pk = {"molecular_weight": {"value": 415.4, "units": "g/mol", "provenance": {"source_url": "u"}},
          "xlogp": {"value": 3.7, "units": None, "provenance": {"source_url": "u"}}}
    block = _brain_penetrance(pk)

    assert block["physicochemical_proxies"]["molecular_weight"]["value"] == 415.4
    assert block["assessment"] == "unknown", "proxies must never produce a favorable assessment"
    assert block["assessment_is_not_derived_from_proxies"] is True
    assert block["proxies_are_suggestive_never_confirmatory"] is True


def test_CNS_MPO_names_the_inputs_it_is_MISSING():
    """A composite from four of six inputs is not CNS-MPO with two fields missing — it is a
    different score wearing CNS-MPO's name, and it would read as a brain-penetrance result."""
    assert set(CNS_MPO_MISSING_INPUTS) == {"clogd_7_4", "pka_most_basic"}


# --------------------------------------------------------------------- the real served files

REST = "/home/tcelab/.spot-runs/stage4-ui-dev-20260713/stage04_pk_safety_rest.json"


@pytest.mark.skipif(not __import__("os").path.exists(REST), reason="the served file is not here")
def test_the_REAL_served_document_passes_every_gate():
    with open(REST, encoding="utf-8") as fh:
        doc = json.load(fh)

    assert_servable(doc)          # zero machine paths, zero retired fields
    assert content_sha256(doc) == doc["content_sha256"]
    assert doc["stage3_source"]["content_sha256"] == \
        "40546baccb1f1a2b46971fa962dc3ad7527a9df94721daec6d1d9117834a7701"
    assert doc["stage3_source"]["content_sha256_recomputed_by_stage4"] is True

    # A phenocopy claim only where the mechanism actually phenocopies the observed modality.
    for row in doc["candidates"] + doc["unacquired"]:
        for arm in row.get("stage3_arms") or []:
            if arm.get("evidence_relation") == "putative_crispri_phenocopy":
                assert arm.get("mechanism_phenocopies_modality") is True

    for row in doc["candidates"]:
        assert row["brain_penetrance"]["assessment"] == "unknown"
        assert row["cns_mpo"]["state"] == "not_evaluated"
