"""Workflow states replace the retired promotion/eligibility lattice.

Stage 3 had been made to answer questions it has no standing to answer — whether a drug
is a "production candidate", whether it is "promotion eligible", whether a pointer may
be written. Those were programme decisions dressed as scientific results. All of it is
retired, and this suite is what stops it coming back.

  * ``production_candidate`` / ``production_promotion_eligible`` /
    ``may_write_production_pointer`` / ``production_pointer_written`` /
    ``research_pk_annotation_eligible`` / ``namespace`` are REFUSED structurally.
  * The generic ``analysis`` artifact class is the only real one. The FIXTURE firewall
    is strict: a fixture may never be relabelled, and never reaches Stage 4.
  * A Stage-4 assessment is NOT biological promotion and NOT a recommendation.
"""
from __future__ import annotations

import os

import pytest

from druglink import artifact_class as ac, artifacts, workflow as wf


# --------------------------------------------------------------------------- #
# The retired vocabulary is gone, and cannot come back.
# --------------------------------------------------------------------------- #
def test_retired_promotion_fields_are_refused_structurally(analysis_build):
    doc = analysis_build["document"]

    # Not in the document, at any depth.
    assert ac.retired_keys_in(doc) == []
    ac.check_no_retired_keys(doc)

    # Not on any candidate row.
    for cand in analysis_build["tables"]["candidates"]:
        assert ac.retired_keys_in(cand) == []

    # And a writer that tries to add one back is REFUSED — each field, individually.
    for field in ("production_candidate", "production_promotion_eligible",
                  "may_write_production_pointer", "production_pointer_written",
                  "research_pk_annotation_eligible", "namespace",
                  "stage3_eligible", "annotation_only"):
        with pytest.raises(ac.ArtifactClassError, match="retired"):
            ac.check_no_retired_keys({**doc, field: True})

    # Even nested deep inside an otherwise-valid structure.
    with pytest.raises(ac.ArtifactClassError, match="retired"):
        ac.check_no_retired_keys(
            {**doc, "counts": {"per_arm": {"away_from_A": {
                "production_candidate": False}}}})


def test_the_bundle_writer_refuses_a_retired_field(tmp_path, analysis_build):
    poisoned = dict(analysis_build["document"])
    poisoned["production_promotion_eligible"] = False   # even FALSE is refused
    with pytest.raises(ac.ArtifactClassError, match="retired"):
        artifacts.write_bundle(
            output_root=str(tmp_path / "out"), artifact_class="analysis",
            document=poisoned, doc_id=analysis_build["document_id"],
            tables=analysis_build["tables"], created_at="2026-07-12T00:00:00+00:00")


def test_no_promotion_pointer_file_is_ever_written(tmp_path, analysis_build):
    path = artifacts.write_bundle(
        output_root=str(tmp_path / "out"), artifact_class="analysis",
        document=analysis_build["document"], doc_id=analysis_build["document_id"],
        tables=analysis_build["tables"], created_at="2026-07-12T00:00:00+00:00")
    for pointer in ac.RETIRED_POINTER_FILES:
        assert not os.path.exists(os.path.join(path, pointer))
    assert os.path.basename(path).startswith("s3_")


# --------------------------------------------------------------------------- #
# One generic analysis class + a strict fixture firewall.
# --------------------------------------------------------------------------- #
def test_only_two_artifact_classes_exist():
    assert ac.ARTIFACT_CLASSES == ("analysis", "fixture")
    for retired in ("production", "research_only"):
        with pytest.raises(ac.ArtifactClassError, match="retired"):
            ac.require(retired)


def test_the_fixture_firewall_is_strict(analysis_build):
    # A fixture never wears an analysis id, and an analysis never wears a fixture id.
    with pytest.raises(ac.ArtifactClassError):
        ac.check_bundle_id("analysis", "fx_0123456789abcdef")
    with pytest.raises(ac.ArtifactClassError):
        ac.check_bundle_id("fixture", "s3_0123456789abcdef")

    # A fixture may never consume public bytes; an analysis may never consume fixture
    # bytes.
    assert ac.ALLOWED_ACQUISITION["analysis"] == ("acquired_public",)
    assert ac.ALLOWED_ACQUISITION["fixture"] == ("synthetic_fixture",)

    # A fixture NEVER reaches Stage 4, whatever its evidence says.
    assert ac.stage4_queue_permitted("analysis") is True
    assert ac.stage4_queue_permitted("fixture") is False
    status, reason = wf.stage4_assessment(
        artifact_class="fixture", identity_status="resolved",
        active_moiety_id="AM:CHEMBL:CHEMBL1",
        directional_statuses={wf.OBSERVED_PERTURBATION})
    assert status == wf.NOT_QUEUED
    assert reason == wf.REASON_NOT_QUEUED_FIXTURE

    # The document declares the class it really is.
    doc = analysis_build["document"]
    assert doc["artifact_class"] == "analysis"
    with pytest.raises(ac.ArtifactClassError, match="refuses a document"):
        ac.check_document("fixture", doc)


# --------------------------------------------------------------------------- #
# Stage-4 assessment: a look, not a verdict.
# --------------------------------------------------------------------------- #
def test_stage4_assessment_is_not_promotion_or_recommendation(analysis_build):
    doc = analysis_build["document"]

    assert doc["stage4_assessment_statuses"] == ["queued", "not_queued"]
    assert "not biological promotion" in doc["stage4_assessment_note"]
    assert "not a recommendation" in doc["stage4_assessment_note"]

    queued = [c for c in analysis_build["tables"]["candidates"]
              if c["stage4_assessment_status"] == wf.QUEUED]
    assert queued, "a resolved, direction-compatible candidate must be queued"
    for cand in queued:
        assert cand["stage4_assessment_reason"] in (
            wf.REASON_QUEUED_OBSERVED, wf.REASON_QUEUED_PATHWAY)
        # Queuing confers NOTHING else. There is no promotion field to confer.
        assert ac.retired_keys_in(cand) == []

    # Candidates not queued stay visible, with a compact reason.
    not_queued = {c["candidate_id"] for c in analysis_build["tables"]["candidates"]
                  if c["stage4_assessment_status"] == wf.NOT_QUEUED}
    disposed = {d["subject_id"] for d in analysis_build["tables"]["dispositions"]
                if d["state"] == wf.NOT_QUEUED}
    assert not_queued <= disposed
    for cand in analysis_build["tables"]["candidates"]:
        assert cand["stage4_assessment_reason"] in wf.STAGE4_REASONS


def test_stage4_queue_requires_identity_and_direction_compatible_evidence():
    resolved = dict(artifact_class="analysis", identity_status="resolved",
                    active_moiety_id="AM:CHEMBL:CHEMBL1")

    assert wf.stage4_assessment(
        **resolved, directional_statuses={wf.OBSERVED_PERTURBATION}
    ) == (wf.QUEUED, wf.REASON_QUEUED_OBSERVED)
    assert wf.stage4_assessment(
        **resolved, directional_statuses={wf.PATHWAY_HYPOTHESIS}
    ) == (wf.QUEUED, wf.REASON_QUEUED_PATHWAY)

    # Opposed-only / unresolved-only is not direction-compatible.
    assert wf.stage4_assessment(
        **resolved, directional_statuses={wf.OPPOSED, wf.UNRESOLVED}
    ) == (wf.NOT_QUEUED, wf.REASON_NOT_QUEUED_NO_EVIDENCE)

    # An unresolved / ambiguous / multi-ingredient identity cannot be assessed.
    assert wf.stage4_assessment(
        artifact_class="analysis", identity_status="resolved",
        active_moiety_id="AM:UNRESOLVED:deadbeef",
        directional_statuses={wf.OBSERVED_PERTURBATION}
    )[1] == wf.REASON_NOT_QUEUED_IDENTITY
    assert wf.stage4_assessment(
        artifact_class="analysis", identity_status="ambiguous",
        active_moiety_id="AM:CHEMBL:CHEMBL1",
        directional_statuses={wf.OBSERVED_PERTURBATION}
    )[1] == wf.REASON_NOT_QUEUED_AMBIGUOUS
    assert wf.stage4_assessment(
        artifact_class="analysis", identity_status="multi_ingredient",
        active_moiety_id="AM:CHEMBL:CHEMBL1",
        directional_statuses={wf.OBSERVED_PERTURBATION}
    )[1] == wf.REASON_NOT_QUEUED_MULTI


# --------------------------------------------------------------------------- #
# drug_mapping_status: mapped | unmapped | refused
# --------------------------------------------------------------------------- #
def test_drug_mapping_status_distinguishes_refused_from_unmapped(analysis_build):
    rows = analysis_build["tables"]["drug_mapping"]
    assert rows
    assert {r["drug_mapping_status"] for r in rows} <= set(wf.DRUG_MAPPING_STATUSES)

    # A symbol is not an accession.
    assert wf.drug_mapping_status(
        has_accession=False, n_single_protein_entities=0, n_non_gene_entities=0
    ) == (wf.UNMAPPED, wf.REASON_NO_ACCESSION)

    # Nothing matched at all.
    assert wf.drug_mapping_status(
        has_accession=True, n_single_protein_entities=0, n_non_gene_entities=0
    ) == (wf.UNMAPPED, wf.REASON_NO_SOURCE_MAPPING)

    # Entities matched, but every one was a complex/family. That is a REFUSAL — a
    # different fact from "nothing matched", and it must not hide behind an absence.
    assert wf.drug_mapping_status(
        has_accession=True, n_single_protein_entities=0, n_non_gene_entities=3
    ) == (wf.REFUSED, wf.REASON_ONLY_NON_GENE_ENTITY)

    assert wf.drug_mapping_status(
        has_accession=True, n_single_protein_entities=1, n_non_gene_entities=2
    )[0] == wf.MAPPED

    # The real run maps something, and every unmapped/refused row is disposed.
    counts = analysis_build["counts"]["drug_mapping"]
    assert counts[wf.MAPPED] > 0
    disposed = {d["subject_id"] for d in analysis_build["tables"]["dispositions"]
                if d["subject_kind"] == "drug_mapping"}
    for row in rows:
        if row["drug_mapping_status"] != wf.MAPPED:
            key = (f"{row['target_ensembl']}:{row['desired_arm']}:"
                   f"{row['origin_type']}")
            assert key in disposed
