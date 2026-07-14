"""W9's optional v2 `organ_system`: extracted from a source, or `unspecified`. Never inferred.

The coordination rule, and the whole of it:

  * a value is admissible ONLY when a public structured source ACTUALLY CARRIES an organ-system
    field, and then it is taken verbatim with the exact section/locator and the raw record
    identity (set ID, version, response SHA-256) that a reviewer can re-check;
  * otherwise the value is `unspecified` / `not_evaluated`. A stated absence.
  * it is NEVER classified from a target name, a gene, a mechanism, a pharmacologic class or a
    drug name. "Anti-CTLA-4, therefore immune system" is a classification, not an observation,
    and it would be indistinguishable in the artifact from a sourced one.

As of this pass NO source in the Stage-4 ledger carries such a field (see `ORGAN_SYSTEM_SPECS`),
so every real extraction returns `unspecified`. The plumbing exists and is tested, so that when a
source-backed field appears it is a spec entry rather than a rewrite — and so that nothing can
quietly start guessing in the meantime.
"""

from __future__ import annotations

import pytest

from analysis.firewall import Rejection
from analysis.organ_system import (
    ORGAN_SYSTEM_SPECS,
    OrganSystemSpec,
    extract_organ_system,
    refuse_inferred_organ_system,
)


class _Label:
    """The shape `dailymed_select.SelectedLabel` presents, reduced to what the extractor reads."""

    def __init__(self, structured=None):
        self.source_record_id = "acq_dailymed_deadbeef"
        self.setid = "ffffffff-0000-4000-8000-fixtureacq01"
        self.label_version = "40"
        self.raw_response_sha256 = "a" * 64
        self.structured = structured or {}


def test_no_ledgered_public_source_currently_carries_an_organ_system_field():
    """The honest state of the world. If this ever stops being true, it is a SPEC entry — a
    reviewed decision naming the source and the locator — not a code change buried in an adapter."""
    assert ORGAN_SYSTEM_SPECS == ()


def test_a_real_label_yields_unspecified_and_says_why():
    evidence = extract_organ_system(_Label(), source_key="dailymed")

    assert evidence.organ_system == "unspecified"
    assert evidence.evidence_state == "not_evaluated"
    assert "does not carry" in evidence.reason or "no" in evidence.reason.lower()


def test_an_unspecified_value_still_binds_the_raw_record_it_was_looked_for_in():
    """W9 must be able to see WHERE we looked and WHAT bytes we looked at, or `unspecified` is
    indistinguishable from `never checked`."""
    evidence = extract_organ_system(_Label(), source_key="dailymed")

    # exactly the names W9's evidence_records.Provenance uses — not new ones
    assert evidence.source_record_id == "acq_dailymed_deadbeef"
    assert evidence.setid == "ffffffff-0000-4000-8000-fixtureacq01"
    assert evidence.label_version == "40"
    assert evidence.raw_response_sha256 == "a" * 64
    assert evidence.source_key == "dailymed"
    assert evidence.value_kind == "none"
    assert evidence.extraction_transform


@pytest.mark.parametrize("hint", [
    "CTLA4", "IL2RA", "anti-CTLA-4 monoclonal antibody", "immune checkpoint inhibitor",
    "T cell", "IPILIMUMAB",
])
def test_organ_system_is_never_classified_from_a_target_mechanism_or_drug_name(hint):
    with pytest.raises(Rejection) as exc:
        refuse_inferred_organ_system(hint)
    assert exc.value.code == "organ_system_inference_refused"


def test_a_source_backed_field_is_taken_verbatim_with_its_exact_locator():
    """The plumbing, proven on a DECLARED spec. When a public source really does carry the field,
    the value is copied — not mapped, not normalised, not re-classified — and the locator travels
    with it."""
    spec = OrganSystemSpec(
        source_key="dailymed",
        field_path=("organ_system_coded", "displayName"),
        section_code="34084-4",
        code_system="2.16.840.1.113883.6.1",
        note="declared for the plumbing test; no live source carries this today",
        value_kind="controlled_value",
    )
    label = _Label(structured={"organ_system_coded": {"displayName": "Nervous system disorders"}})

    evidence = extract_organ_system(label, source_key="dailymed", specs=(spec,))

    assert evidence.organ_system == "Nervous system disorders"   # verbatim
    assert evidence.evidence_state == "observed"
    assert evidence.section_code == "34084-4"
    assert evidence.code_system == "2.16.840.1.113883.6.1"
    assert evidence.locator == "organ_system_coded.displayName"
    assert evidence.value_kind == "controlled_value"
    assert evidence.source_record_id == "acq_dailymed_deadbeef"
    assert evidence.raw_response_sha256 == "a" * 64              # the bytes it came from


def test_a_declared_spec_whose_field_is_absent_still_yields_unspecified_not_a_guess():
    spec = OrganSystemSpec(
        source_key="dailymed", field_path=("organ_system_coded", "displayName"),
        section_code="34084-4", code_system="2.16.840.1.113883.6.1", note="plumbing test")
    evidence = extract_organ_system(_Label(structured={}), source_key="dailymed", specs=(spec,))

    assert evidence.organ_system == "unspecified"
    assert evidence.evidence_state == "not_evaluated"


def test_a_spec_for_another_source_does_not_apply_to_this_one():
    spec = OrganSystemSpec(
        source_key="openfda", field_path=("organ_system_coded",),
        section_code=None, code_system=None, note="plumbing test")
    label = _Label(structured={"organ_system_coded": "Nervous system disorders"})

    evidence = extract_organ_system(label, source_key="dailymed", specs=(spec,))
    assert evidence.organ_system == "unspecified"
