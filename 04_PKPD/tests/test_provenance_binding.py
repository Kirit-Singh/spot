"""Every result-affecting row is bound to acquired bytes, or it does not run.

The post-build audit found three lanes that could change a scientific claim while sitting
OUTSIDE the provenance bindings that give the artifact its identity:

  * a `PotencyContextLink` citing `src.DOES_NOT_EXIST` with an invented 64-hex hash turned
    EXP-001A from `not_computable` into `computed` and CTX-001A from no class into
    `insufficiently_permeable` — and BOTH verifiers reported all-pass (176/0 and 169/0);
  * a `DeliveryAssignment` citing the same nonexistent source was accepted as
    `local_CNS_target_engagement_required` with `nebpi_primary_gate=true`;
  * a `SearchManifest` the caller simply authored passed as a sourced negative search, and
    a second, conflicting manifest could be appended under the same `search_id`.

The rule now has no exemptions: a row that cites a source must cite one that EXISTS, was
ACQUIRED, and whose ACQUIRED BYTES HASH TO WHAT THE ROW DECLARES — checked before anything
is classified (`analysis/integrity.py`), and re-derived independently by each verifier.

Permutation invariance of the two order-dependent reducers lives in
`test_reduction_invariance.py`.
"""

from __future__ import annotations

import os

import pyarrow.parquet as pq
import pytest

from analysis.canonical import sha256_file
from analysis.evidence_records import (
    DeliveryAssignment,
    PotencyContextLink,
    SearchManifest,
)
from analysis.firewall import Rejection
from analysis.ids import derive_scorecard_set_id
from analysis.method_config import METHOD_DIR
from analysis.pipeline import run_pipeline
from analysis.verify import verify_output_dir
from provenance_helpers import (
    BOGUS_SHA,
    METHOD,
    both_verifiers,
    emit_run,
    failed,
    potency_out_of_context,
    prov,
    reseal,
)
from verifier.checks import verify_release

import fixtures as fx


# ------------------------------------------- BLOCKER 2: potency-context link provenance

def test_an_unregistered_potency_context_source_is_refused():
    """The reproduced defect: LNK-BOGUS -> src.DOES_NOT_EXIST -> a margin and a class."""
    inputs = potency_out_of_context(fx.stage4_inputs())
    inputs.potency_context_links = [
        PotencyContextLink(link_id="LNK-BOGUS", potency_id="POT-001",
                           tumor_context="GBM_fixture", rationale="invented",
                           provenance=prov("src.DOES_NOT_EXIST", BOGUS_SHA))
    ]
    with pytest.raises(Rejection, match="unbound_source_record"):
        run_pipeline(inputs, METHOD)


def test_a_potency_context_link_whose_hash_does_not_match_its_source_is_refused():
    """A REAL source id with bytes that never produced this row is still a fabrication."""
    inputs = potency_out_of_context(fx.stage4_inputs())
    inputs.potency_context_links = [
        PotencyContextLink(link_id="LNK-HASH", potency_id="POT-001",
                           tumor_context="GBM_fixture", rationale="real id, invented hash",
                           provenance=prov("src.fixture.potency", BOGUS_SHA))
    ]
    with pytest.raises(Rejection, match="source_hash_mismatch"):
        run_pipeline(inputs, METHOD)


def test_without_a_link_the_foreign_context_potency_computes_nothing():
    """The conservative baseline the attack was trying to escape."""
    inputs = potency_out_of_context(fx.stage4_inputs())
    result = run_pipeline(inputs, METHOD)
    margins = {m.measurement_id: mg for cr in result.candidates for m, mg in cr.exposure}
    assert margins["EXP-001A"].status == "not_computable"
    assert margins["EXP-001A"].reason_code == "potency_context_not_relevant"
    classes = {n.context_id: n.nebpi_class for cr in result.candidates for n in cr.nebpi}
    assert classes["CTX-001A"] is None


def test_two_links_for_one_potency_and_context_are_refused():
    """Otherwise the link the margin CITES depends on which row was scanned first."""
    inputs = potency_out_of_context(fx.stage4_inputs())
    p = fx._prov("src.fixture.potency", "read the relevance argument")
    inputs.potency_context_links = [
        PotencyContextLink(link_id="LNK-A", potency_id="POT-001",
                           tumor_context="GBM_fixture", rationale="a", provenance=p),
        PotencyContextLink(link_id="LNK-B", potency_id="POT-001",
                           tumor_context="GBM_fixture", rationale="b", provenance=p),
    ]
    with pytest.raises(Rejection, match="duplicate_potency_context_link"):
        run_pipeline(inputs, METHOD)


def test_a_duplicate_link_id_is_refused():
    inputs = potency_out_of_context(fx.stage4_inputs())
    p = fx._prov("src.fixture.potency", "read the relevance argument")
    inputs.potency_context_links = [
        PotencyContextLink(link_id="LNK-1", potency_id="POT-001",
                           tumor_context="GBM_fixture", rationale="a", provenance=p),
        PotencyContextLink(link_id="LNK-1", potency_id="POT-001",
                           tumor_context="OTHER", rationale="b", provenance=p),
    ]
    with pytest.raises(Rejection, match="duplicate link_id"):
        run_pipeline(inputs, METHOD)


def test_a_legitimate_link_is_bound_and_moves_the_run_identity(tmp_path):
    """A sourced link is admissible — and it CHANGES the id, because it changes the result."""
    without = potency_out_of_context(fx.stage4_inputs())
    id_without, _k = derive_scorecard_set_id(
        without.candidate_set, METHOD, without.evidence_lanes(), without.sources,
        "lock", without.config)

    with_link = potency_out_of_context(fx.stage4_inputs())
    with_link.potency_context_links = [
        PotencyContextLink(
            link_id="LNK-OK", potency_id="POT-001", tumor_context="GBM_fixture",
            rationale="FIXTURE: the same target is expressed in both models.",
            provenance=fx._prov("src.fixture.potency", "read the relevance argument"),
        )
    ]
    id_with, _k = derive_scorecard_set_id(
        with_link.candidate_set, METHOD, with_link.evidence_lanes(), with_link.sources,
        "lock", with_link.config)
    assert id_without != id_with, "adding a result-affecting link must move the id"

    out_dir, _m, result = emit_run(with_link, tmp_path)
    margins = {m.measurement_id: mg for cr in result.candidates for m, mg in cr.exposure}
    assert margins["EXP-001A"].status == "computed"
    assert margins["EXP-001A"].potency_context_link_id == "LNK-OK"

    emit_time, standalone = both_verifiers(out_dir, with_link)
    assert emit_time["status"] == "pass", failed(emit_time)
    assert standalone["status"] == "pass", failed(standalone)


# ------------------------------------------- BLOCKER 3: delivery assignment provenance

def test_a_nonexistent_delivery_source_is_refused():
    """The reproduced defect: src.DOES_NOT_EXIST accepted as local_CNS/primary gate."""
    inputs = fx.stage4_inputs()
    inputs.delivery_assignments = [
        DeliveryAssignment(**{**a.model_dump(),
                              "evidence": prov("src.DOES_NOT_EXIST", BOGUS_SHA).model_dump()})
        if a.assignment_id == "DLV-001A" else a
        for a in inputs.delivery_assignments
    ]
    with pytest.raises(Rejection, match="unbound_source_record"):
        run_pipeline(inputs, METHOD)


def test_a_delivery_assignment_whose_hash_does_not_match_its_source_is_refused():
    inputs = fx.stage4_inputs()
    inputs.delivery_assignments = [
        DeliveryAssignment(**{**a.model_dump(),
                              "evidence": prov("src.fixture.delivery", BOGUS_SHA).model_dump()})
        if a.assignment_id == "DLV-001A" else a
        for a in inputs.delivery_assignments
    ]
    with pytest.raises(Rejection, match="source_hash_mismatch"):
        run_pipeline(inputs, METHOD)


def test_an_unevidenced_assignment_is_downgraded_not_refused():
    """"Nobody cited anything" is a legal, honest input — and it never sets the gate."""
    inputs = fx.stage4_inputs()
    inputs.delivery_assignments = [
        DeliveryAssignment(**{**a.model_dump(), "evidence": None})
        if a.assignment_id == "DLV-001A" else a
        for a in inputs.delivery_assignments
    ]
    result = run_pipeline(inputs, METHOD)
    d = [x for cr in result.candidates for x in cr.delivery if x.context_id == "CTX-001A"][0]
    assert d.requirement == "delivery_requirement_uncertain"
    assert d.reason_code == "no_evidence_binding"
    assert d.nebpi_primary_gate is None


# ------------------------------------------- MAJOR 7: negative-search manifests

def test_a_duplicate_search_id_is_refused():
    """The reproduced defect: a second, conflicting manifest under one search_id."""
    inputs = fx.stage4_inputs()
    real = inputs.search_manifests[0]
    forged = SearchManifest(**{
        **real.model_dump(exclude={"provenance"}),
        "endpoint": "/attack/v1/search",
        "query_canonical": "terms=nothing_at_all",
        "provenance": real.provenance.model_dump(),
    })
    inputs.search_manifests = [real, forged]
    with pytest.raises(Rejection, match="duplicate search_id"):
        run_pipeline(inputs, METHOD)


def test_a_caller_authored_negative_search_is_refused():
    """A negative search whose response bytes nobody acquired is not sourced evidence."""
    inputs = fx.stage4_inputs()
    real = inputs.search_manifests[0]
    inputs.search_manifests = [
        SearchManifest(**{**real.model_dump(exclude={"provenance"}),
                          "provenance": prov("src.DOES_NOT_EXIST", BOGUS_SHA).model_dump()})
    ]
    with pytest.raises(Rejection, match="unbound_source_record"):
        run_pipeline(inputs, METHOD)


def test_a_negative_search_bound_to_the_wrong_bytes_is_refused():
    inputs = fx.stage4_inputs()
    real = inputs.search_manifests[0]
    inputs.search_manifests = [
        SearchManifest(**{**real.model_dump(exclude={"provenance"}),
                          "provenance": prov("src.fixture.label.dailymed",
                                             BOGUS_SHA).model_dump()})
    ]
    with pytest.raises(Rejection, match="source_hash_mismatch"):
        run_pipeline(inputs, METHOD)


def test_the_search_manifest_is_bound_into_the_run_identity():
    """Rewriting the query that was run is a different negative search, so a different id."""
    inputs = fx.stage4_inputs()
    real = inputs.search_manifests[0]
    id_a, _k = derive_scorecard_set_id(inputs.candidate_set, METHOD, inputs.evidence_lanes(),
                                       inputs.sources, "lock", inputs.config)
    inputs.search_manifests = [
        SearchManifest(**{**real.model_dump(exclude={"provenance"}),
                          "query_canonical": "terms=something_else",
                          "provenance": real.provenance.model_dump()})
    ]
    id_b, _k = derive_scorecard_set_id(inputs.candidate_set, METHOD, inputs.evidence_lanes(),
                                       inputs.sources, "lock", inputs.config)
    assert id_a != id_b


def test_the_emitted_manifest_carries_its_source_binding(tmp_path):
    out_dir, _m, _r = emit_run(fx.stage4_inputs(), tmp_path)
    rows = pq.read_table(os.path.join(out_dir, "search_manifests.parquet")).to_pylist()
    assert len(rows) == 1
    row = rows[0]
    catalog = {r["source_record_id"]: r for r in
               pq.read_table(os.path.join(out_dir, "source_catalog.parquet")).to_pylist()}
    assert row["source_record_id"] in catalog
    assert row["response_sha256"] == catalog[row["source_record_id"]]["raw_sha256"]


# ------------------- BOTH VERIFIERS, INDEPENDENTLY, ON A RESEALED TAMPER ----------------
# Every tamper below reseals the artifact's own hashes, so arithmetic alone cannot catch it.
# The emit-time verifier re-derives the bindings from the INPUT RECORDS; the standalone
# verifier re-derives them from the EMITTED TABLES plus the source catalog. Neither reads
# the other's verdict, and neither reads a "bound: true" flag from the generator.

def test_the_standalone_verifier_catches_a_resealed_unregistered_link(tmp_path):
    inputs = potency_out_of_context(fx.stage4_inputs())
    inputs.potency_context_links = [
        PotencyContextLink(
            link_id="LNK-OK", potency_id="POT-001", tumor_context="GBM_fixture",
            rationale="FIXTURE: legitimate.",
            provenance=fx._prov("src.fixture.potency", "read the relevance argument"))
    ]
    out_dir, _m, _r = emit_run(inputs, tmp_path)
    assert verify_release(out_dir, METHOD_DIR)["status"] == "pass"

    rows = pq.read_table(os.path.join(out_dir, "potency_context_links.parquet")).to_pylist()
    rows[0]["source_record_id"] = "src.DOES_NOT_EXIST"
    rows[0]["raw_response_sha256"] = BOGUS_SHA
    reseal(out_dir, "potency_context_links", rows)

    report = verify_release(out_dir, METHOD_DIR)
    assert report["status"] == "fail"
    assert "every_evidence_row_is_source_bound" in failed(report)


def test_the_standalone_verifier_catches_a_relaundered_delivery_basis(tmp_path):
    """The `target_biology_only` refusal, rewritten into an acceptable basis in the release."""
    out_dir, _m, _r = emit_run(fx.stage4_inputs(), tmp_path)
    assert verify_release(out_dir, METHOD_DIR)["status"] == "pass"

    rows = pq.read_table(os.path.join(out_dir, "delivery_assignments.parquet")).to_pylist()
    for r in rows:
        if r["assignment_id"] == "DLV-003":
            r["basis"] = "clinical_evidence"
    reseal(out_dir, "delivery_assignments", rows)

    report = verify_release(out_dir, METHOD_DIR)
    assert report["status"] == "fail"
    assert any(c.startswith("delivery_reduction::") for c in failed(report))


def test_the_standalone_verifier_catches_an_unbound_delivery_source(tmp_path):
    out_dir, _m, _r = emit_run(fx.stage4_inputs(), tmp_path)
    rows = pq.read_table(os.path.join(out_dir, "delivery_assignments.parquet")).to_pylist()
    for r in rows:
        r["evidence_source_record_id"] = "src.DOES_NOT_EXIST"
        r["evidence_sha256"] = BOGUS_SHA
    reseal(out_dir, "delivery_assignments", rows)

    report = verify_release(out_dir, METHOD_DIR)
    assert report["status"] == "fail"
    assert "every_evidence_row_is_source_bound" in failed(report)


def test_the_standalone_verifier_catches_an_unbound_search_manifest(tmp_path):
    out_dir, _m, _r = emit_run(fx.stage4_inputs(), tmp_path)
    rows = pq.read_table(os.path.join(out_dir, "search_manifests.parquet")).to_pylist()
    rows[0]["source_record_id"] = "src.DOES_NOT_EXIST"
    rows[0]["response_sha256"] = BOGUS_SHA
    reseal(out_dir, "search_manifests", rows)

    report = verify_release(out_dir, METHOD_DIR)
    assert report["status"] == "fail"
    assert "every_evidence_row_is_source_bound" in failed(report)


def test_the_emit_verifier_catches_a_release_that_is_stale_for_its_inputs(tmp_path):
    """A release emitted from one evidence set, re-verified against another, is stale."""
    emitted_from = fx.stage4_inputs()
    out_dir, _m, _r = emit_run(emitted_from, tmp_path)
    assert verify_output_dir(out_dir, emitted_from, METHOD)["status"] == "pass"

    mutated = potency_out_of_context(fx.stage4_inputs())
    mutated.potency_context_links = [
        PotencyContextLink(
            link_id="LNK-OK", potency_id="POT-001", tumor_context="GBM_fixture",
            rationale="FIXTURE: legitimate, but not what this release was built from.",
            provenance=fx._prov("src.fixture.potency", "read the relevance argument"))
    ]
    report = verify_output_dir(out_dir, mutated, METHOD)
    assert report["status"] == "fail"
    marks = failed(report)
    assert "scorecard_set_id_rederived" in marks
    assert "evidence_inputs_sha256_unchanged" in marks
    assert "bound_input_tables_emitted_exactly" in marks


def test_the_emit_verifier_rejects_an_input_row_missing_from_the_release(tmp_path):
    """An assignment the engine consumed but the release does not carry is not verifiable."""
    inputs = fx.stage4_inputs()
    out_dir, _m, _r = emit_run(inputs, tmp_path)

    rows = pq.read_table(os.path.join(out_dir, "delivery_assignments.parquet")).to_pylist()
    reseal(out_dir, "delivery_assignments", rows[1:])   # drop one consumed row

    report = verify_output_dir(out_dir, inputs, METHOD)
    assert report["status"] == "fail"
    assert "bound_input_tables_emitted_exactly" in failed(report)


# ------------------------------------------- the legitimate fixtures still reproduce

def test_the_untouched_fixtures_reproduce_and_both_verifiers_pass(tmp_path):
    inputs = fx.stage4_inputs()
    out_dir, manifest, _r = emit_run(inputs, tmp_path, name="a")

    again = fx.stage4_inputs()
    out_dir_b, manifest_b, _r = emit_run(again, tmp_path, name="b")
    assert manifest["scorecard_set_id"] == manifest_b["scorecard_set_id"]

    for name in os.listdir(out_dir):
        if name.endswith(".parquet"):
            assert sha256_file(os.path.join(out_dir, name)) == \
                   sha256_file(os.path.join(out_dir_b, name)), name

    emit_time, standalone = both_verifiers(out_dir, inputs)
    assert emit_time["status"] == "pass", failed(emit_time)
    assert standalone["status"] == "pass", failed(standalone)
    assert emit_time["n_failed"] == 0 and standalone["n_failed"] == 0


def test_every_bound_input_table_is_in_the_release(tmp_path):
    _out_dir, manifest, _r = emit_run(fx.stage4_inputs(), tmp_path)
    names = {a["filename"] for a in manifest["artifacts"]}
    for table in ("potency_context_links", "delivery_assignments", "search_manifests",
                  "source_catalog", "property_evidence"):
        assert f"{table}.parquet" in names
