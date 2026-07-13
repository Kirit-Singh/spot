"""The Stage-3 drug-annotation door: an assessment is not a promotion.

Stage 3 retired its promotion lattice OUTRIGHT — `namespace`, `production_candidate`,
`research_pk_annotation_eligible`, `stage3_eligible`, `stage4_eligible`, `annotation_only` and
the whole `eligibility.py` module are deleted, and `spot.stage03_research_annotation.v1` is no
longer emitted. Stage 4's research adapter was written against that contract and has been
DELETED, not adapted: an adapter that still believed in fields no producer writes is a fiction.

The contract now:

    schema_version           spot.stage03_drug_annotation.v1
    artifact_class           analysis
    stage4_assessment_status queued | not_queued

The bundle these tests run against is a REAL emission of the CURRENT frozen Stage-3 engine
(03_druglink @ e5aa666), built by driving Direct's real screen + the pinned public-bytes
cache through the engine, then re-hashed here. Stage 4 never hand-authors a Stage-3 shape.

    bundle_id                s3_0b119088734643bf
    canonical_content_sha256 0b119088734643bfa6a236ebae0713e4a88a5b043227c1d45c1b3b18a3334853
    document_sha256          ec727aef9682fb61d263367e53adcf52c193a206abb80b79d20a00327ab94ea4
    manifest_sha256          59dcbb99d1552a19ce081d4e2a591a4fd72cb709176614a3377d60b3c55869ac
"""

from __future__ import annotations

import json
import os
import shutil

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from analysis.firewall import Rejection
from analysis.method_config import STAGE4_DIR
from analysis.run_stage4 import main as cli
from analysis.stage3_annotation import (
    ANNOTATION_SCHEMA,
    RETIRED_KEYS,
    STAGE3_CONTRACT_VERSION,
    adapt_annotation_bundle,
    verify_annotation_bundle,
)
from verifier.checks import verify_release

import annotation_evidence as AE

BUNDLE = os.path.join(STAGE4_DIR, "tests", "fixtures", "stage3_annotation",
                      "s3_0b119088734643bf")
METHOD_DIR = os.path.join(STAGE4_DIR, "method")

# The exact bytes Stage 4 builds against, recorded so a silent re-pin is impossible.
PINNED = {
    "bundle_id": "s3_0b119088734643bf",
    "canonical_content_sha256":
        "0b119088734643bfa6a236ebae0713e4a88a5b043227c1d45c1b3b18a3334853",
    "document_sha256":
        "ec727aef9682fb61d263367e53adcf52c193a206abb80b79d20a00327ab94ea4",
    "manifest_sha256":
        "59dcbb99d1552a19ce081d4e2a591a4fd72cb709176614a3377d60b3c55869ac",
}

# The legacy fixture bundle, from the contract before this one.
LEGACY_FIXTURE = os.path.join(STAGE4_DIR, "tests", "fixtures", "stage3",
                              "fx_c5b44dd8bee36b7d")


def _copy(tmp_path) -> str:
    dst = str(tmp_path / "bundle")
    shutil.copytree(BUNDLE, dst)
    return dst


def _doc(b: str) -> dict:
    with open(os.path.join(b, "drug_annotation.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _write_doc(b: str, doc: dict) -> None:
    with open(os.path.join(b, "drug_annotation.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True, ensure_ascii=True)
        fh.write("\n")


def _rewrite(b: str, table: str, rows: list[dict]) -> None:
    path = os.path.join(b, f"{table}.parquet")
    schema = pq.read_schema(path)
    arrays = [pa.array([r.get(n) for r in rows], type=f.type)
              for n, f in zip(schema.names, schema)]
    pq.write_table(pa.Table.from_arrays(arrays, schema=schema), path)


def _evidence(tmp_path, admission, n=2) -> str:
    cids = [c.candidate_id for c in admission.candidate_set.candidates]
    moiety = {c.candidate_id: c.active_moiety.active_moiety_id
              for c in admission.candidate_set.candidates}
    return AE.write(str(tmp_path / "evidence.json"), cids, moiety, n_with_evidence=n)


# ------------------------------------------------------- the pinned bytes, re-hashed

def test_the_pinned_stage3_bundle_hashes_to_what_stage4_recorded():
    """A silent re-pin is impossible: the hashes are asserted, not just consumed."""
    a = adapt_annotation_bundle(BUNDLE)
    assert a.bundle_id == PINNED["bundle_id"]
    assert a.canonical_content_sha256 == PINNED["canonical_content_sha256"]
    assert a.document_sha256 == PINNED["document_sha256"]
    assert a.manifest_sha256 == PINNED["manifest_sha256"]
    assert a.schema_version == ANNOTATION_SCHEMA
    assert a.artifact_class == "analysis"
    assert a.data_status == "acquired_public_responses"


def test_the_contract_version_is_pinned():
    assert STAGE3_CONTRACT_VERSION.startswith("spot.stage03_drug_annotation.v1/")


# --------------------------------------------------------- POSITIVE: queued rows only

def test_only_queued_rows_are_admitted():
    a = adapt_annotation_bundle(BUNDLE)
    assert a.n_candidates_in_bundle == 10
    assert a.admitted_as_candidates == 7
    assert a.not_queued == 3

    doc = _doc(BUNDLE)
    want = {c["candidate_id"] for c in doc["candidates"]
            if c["stage4_assessment_status"] == "queued"}
    got = {q.candidate_id for q in a.queued}
    assert got == want, "exactly the rows Stage 3 queued, and no others"

    # rows Stage 3 did NOT queue stay visible with their reason — never silently dropped
    assert len(a.not_queued_reasons) == 3
    assert all(v for v in a.not_queued_reasons.values())


def test_both_arms_are_carried_separately_and_no_rank_is_invented():
    """away_from_A and toward_B are independent hypotheses, per origin_type."""
    a = adapt_annotation_bundle(BUNDLE)
    for q in a.queued:
        cells = {(x.desired_arm, x.origin_type) for x in q.arm_evidence_states}
        assert cells == {
            ("away_from_A", "direct_target"), ("away_from_A", "pathway_node"),
            ("toward_B", "direct_target"), ("toward_B", "pathway_node"),
        }, "one cell per (desired_arm, origin_type) — four, never collapsed"

    # Stage 4 invents no combined direction in ANY field: doing so would silently privilege
    # whichever arm was listed first, which IS the cross-arm objective Stage 3 forbids.
    for c in a.candidate_set.candidates:
        assert c.direction_compatibility.value == "unknown"
        assert c.program_direction == "unspecified"
        assert c.drug_effect_direction == "unspecified"


def test_a_pathway_node_result_is_never_reported_as_a_measured_one():
    a = adapt_annotation_bundle(BUNDLE)
    for q in a.queued:
        measured = {x.desired_arm for x in q.arm_evidence_states
                    if x.origin_type == "direct_target"
                    and x.arm_evidence_state == "observed_perturbation"}
        assert set(q.observed_perturbation_arms) <= measured, (
            "observed_perturbation_arms must come from direct_target cells only")
        # nothing in this bundle is a pathway hypothesis, and none is invented
        assert q.pathway_hypothesis_arms == []


def test_an_inverse_hypothesis_is_never_observed_gain_of_function():
    a = adapt_annotation_bundle(BUNDLE)
    for q in a.queued:
        # the real pinned sources report no activator, so Stage 3 emits zero inverse
        # hypotheses — and Stage 4 invents none.
        assert q.inverse_direction_hypothesis_arms == []
        assert q.inverse_direction_support == []
        # an inverse arm may never also be an observed arm
        assert not (set(q.inverse_direction_hypothesis_arms)
                    & set(q.observed_perturbation_arms))
        # the evidence class is an UNORDERED label set, never a tier
        assert "inverse_direction_hypothesis" not in q.stage3_evidence_classes


def test_disease_context_review_is_carried_not_assumed():
    """A COMPLETABLE review, carried verbatim. `pending` is not reviewed; `insufficient` is
    not a soft yes. Stage 4 reports Stage 3's recorded result and invents none of it."""
    a = adapt_annotation_bundle(BUNDLE)
    for q in a.queued:
        r = q.disease_context_review
        assert r.status in ("pending", "completed", "not_required")
        # a result is only ever set on a COMPLETED review; otherwise it is None
        if r.status == "completed":
            assert r.result in ("supportive", "contradictory", "mixed", "insufficient")
        else:
            assert r.result is None
        # every carried evidence ref is a typed triple, never a blob
        for ref in r.evidence_refs:
            assert set(ref) == {"science_evidence_id", "science_evidence_sha256", "record_type"}


def test_science_evidence_refs_are_carried_as_typed_references():
    """Typed pointers, never dereferenced or embedded. The pathway lane is unfed here."""
    a = adapt_annotation_bundle(BUNDLE)
    for q in a.queued:
        for ref in q.science_evidence_refs:
            assert set(ref) == {"science_evidence_id", "science_evidence_sha256",
                                "record_type"}
    # pathway lane not evaluated -> zero refs, and none is invented
    assert all(q.science_evidence_refs == [] for q in a.queued)


def test_an_untyped_science_evidence_ref_is_refused(tmp_path):
    """A free-form object or string in place of a typed reference is refused."""
    b = _copy(tmp_path)
    rows = pq.read_table(os.path.join(b, "pathway_nodes.parquet")).to_pylist()
    assert rows == []
    from analysis.stage3_annotation import _science_refs
    with pytest.raises(Rejection) as exc:
        _science_refs({"pathway_nodes": [{"science_evidence_ids": ["a bare string"]}]})
    assert exc.value.code == "stage3_science_ref_untyped"


# --------------------------------------------------------------- END TO END: scorecards

def test_the_assessment_emits_scorecards_and_the_verifier_reconstructs_them(tmp_path):
    a = adapt_annotation_bundle(BUNDLE)
    ev = _evidence(tmp_path, a)
    out = str(tmp_path / "out")
    assert cli(["--stage3-annotation-bundle", BUNDLE, "--evidence-bundle", ev,
                "--outputs-root", out]) == 0

    release = os.path.join(out, os.listdir(out)[0])
    with open(os.path.join(release, "scorecards.json"), encoding="utf-8") as fh:
        sc = json.load(fh)
    assert len(sc["candidates"]) == 7
    for c in sc["candidates"]:
        assert c["production_eligible"]["eligible"] is False

    assert verify_release(release, METHOD_DIR)["status"] == "pass"


def test_a_production_pointer_is_refused_nonzero(tmp_path):
    a = adapt_annotation_bundle(BUNDLE)
    ev = _evidence(tmp_path, a)
    out = str(tmp_path / "out")
    assert cli(["--stage3-annotation-bundle", BUNDLE, "--evidence-bundle", ev,
                "--outputs-root", out, "--write-production-pointer"]) == 3
    release = os.path.join(out, os.listdir(out)[0])
    for name in os.listdir(release):
        assert "pointer" not in name.lower()


def test_a_candidate_with_no_evidence_is_never_safe_or_permeable(tmp_path):
    """Missing evidence stays missing. It is not safety, and it is not permeability."""
    a = adapt_annotation_bundle(BUNDLE)
    ev = _evidence(tmp_path, a, n=2)     # only 2 of the 7 carry observations
    out = str(tmp_path / "out")
    cli(["--stage3-annotation-bundle", BUNDLE, "--evidence-bundle", ev,
         "--outputs-root", out])
    release = os.path.join(out, os.listdir(out)[0])
    with open(os.path.join(release, "scorecards.json"), encoding="utf-8") as fh:
        sc = json.load(fh)

    scored = [c for c in sc["candidates"] if c["lanes"]["nebpi"]]
    bare = [c for c in sc["candidates"] if not c["lanes"]["nebpi"]]
    assert len(scored) == 2 and len(bare) == 5

    for c in bare:
        assert c["lanes"]["safety"]["rows"] == []
        assert c["lanes"]["exposure"] == []
        assert c["lanes"]["cns_mpo"]["status"] == "incomplete"
        assert c["lanes"]["cns_mpo"]["total_published"] is None

    for c in scored:
        for n in c["lanes"]["nebpi"]:
            # derived from a measured concentration vs the MEC, never from CNS-MPO
            assert n["nebpi_class"] == "insufficiently_permeable"


def test_an_incomplete_cns_mpo_never_satisfies_an_nebpi_branch(tmp_path):
    a = adapt_annotation_bundle(BUNDLE)
    ev = _evidence(tmp_path, a)
    out = str(tmp_path / "out")
    cli(["--stage3-annotation-bundle", BUNDLE, "--evidence-bundle", ev,
         "--outputs-root", out])
    release = os.path.join(out, os.listdir(out)[0])
    with open(os.path.join(release, "scorecards.json"), encoding="utf-8") as fh:
        sc = json.load(fh)
    for c in sc["candidates"]:
        mpo = c["lanes"]["cns_mpo"]
        assert mpo["status"] == "incomplete" and mpo["total_published"] is None
        assert "not measured brain permeability" in mpo["interpretation_guard"]
        for n in c["lanes"]["nebpi"]:
            satisfied = [b["branch_id"] for b in n["branch_proof"] if b["satisfied"]]
            assert all("cns_mpo" not in b for b in satisfied)


# --------------------------------------------------- NEGATIVE: the retired vocabulary

@pytest.mark.parametrize("key", sorted(RETIRED_KEYS))
def test_every_retired_key_is_refused_at_any_depth(key, tmp_path):
    """Even set to `false`. The point of a relabel attack is to ADD the field."""
    b = _copy(tmp_path)
    doc = _doc(b)
    doc["upstream"][key] = False
    _write_doc(b, doc)
    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(b)
    assert exc.value.code in ("stage3_retired_key_present", "stage3_document_hash_mismatch")


def test_the_retired_schema_is_refused_by_name(tmp_path):
    b = _copy(tmp_path)
    doc = _doc(b)
    doc["schema_version"] = "spot.stage03_research_annotation.v1"
    _write_doc(b, doc)
    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(b)
    assert exc.value.code == "stage3_schema_unsupported"


def test_a_fixture_artifact_class_never_reaches_stage4(tmp_path):
    b = _copy(tmp_path)
    doc = _doc(b)
    doc["artifact_class"] = "fixture"
    _write_doc(b, doc)
    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(b)
    assert exc.value.code in ("stage3_artifact_class_refused",
                              "stage3_document_hash_mismatch")


# ------------------------------------------------------------- NEGATIVE: tampering

def test_a_tampered_table_row_is_refused(tmp_path):
    b = _copy(tmp_path)
    rows = pq.read_table(os.path.join(b, "candidates.parquet")).to_pylist()
    rows[0]["stage4_assessment_status"] = "queued"
    rows[-1]["stage4_assessment_status"] = "queued"   # promote a not_queued row
    _rewrite(b, "candidates", rows)
    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(b)
    assert exc.value.code in ("stage3_table_content_hash_mismatch",
                              "stage3_file_hash_mismatch")


def test_a_tampered_document_is_refused(tmp_path):
    b = _copy(tmp_path)
    doc = _doc(b)
    doc["candidates"][0]["stage4_assessment_reason"] = "TAMPERED"
    _write_doc(b, doc)
    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(b)
    assert exc.value.code == "stage3_document_hash_mismatch"


def test_a_resealed_document_still_fails_its_canonical_content(tmp_path):
    """Reseal document_sha256 too: the bundle_id it commits to no longer derives."""
    from analysis.stage3_contract import content_hash

    b = _copy(tmp_path)
    doc = _doc(b)
    doc["candidates"][0]["stage4_assessment_reason"] = "TAMPERED"
    doc["document_sha256"] = content_hash(
        {k: v for k, v in doc.items() if k != "document_sha256"})
    _write_doc(b, doc)
    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(b)
    assert exc.value.code == "stage3_canonical_content_mismatch"


def test_a_production_pointer_file_in_the_bundle_is_refused(tmp_path):
    b = _copy(tmp_path)
    with open(os.path.join(b, "current.json"), "w", encoding="utf-8") as fh:
        json.dump({"promoted": True}, fh)
    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(b)
    assert exc.value.code == "stage3_carries_a_production_pointer"


def test_a_missing_table_is_refused(tmp_path):
    b = _copy(tmp_path)
    os.remove(os.path.join(b, "drug_forms.parquet"))
    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(b)
    assert exc.value.code in ("stage3_table_missing", "stage3_bundle_incomplete")


def test_a_legacy_fixture_bundle_is_refused_at_the_annotation_door():
    """The previous contract's fixture bundle is not a drug annotation."""
    if not os.path.isdir(LEGACY_FIXTURE):
        return
    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(LEGACY_FIXTURE)
    assert exc.value.code.startswith("stage3_")
