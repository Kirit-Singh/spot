"""Two reductions that used to depend on list order, under ONE scorecard_set_id.

The post-build audit fed the SAME evidence multiset in two orders and got two different
scientific documents behind one cache key, with both verifications passing:

  * DELIVERY — two assignments for one (candidate, context), both requesting
    `local_CNS_target_engagement_required`, one on pharmacology evidence and one on the
    explicitly-rejected `target_biology_only` basis. `resolve_delivery_requirement` compared
    only the requirement VALUES, saw them agree, and took `mine[0]`. Result:
    `local_CNS`/gate=true or `uncertain`/no gate, purely on which came first.
    Reported id `8fc47369784727a8`, two different `scorecards.json` hashes.

  * PROPERTIES — two ClogP rows agreeing on calculator and value but citing different
    sources. `select_properties` took `usable[0]`, so one score carried two possible
    provenance chains. Reported id `7881576feed26d6d`, two different `scorecards.json`
    hashes.

Both reducers are now functions of the SET of rows (`delivery_reduce.py`, `properties.py`).
Byte-identical rows collapse; distinct rows are either all bound (properties, when they
agree on what determines the score) or refused (delivery, always — the basis, the assigner
and the evidence binding are part of the claim, so two distinct assignments conflict even
when the requirement agrees).
"""

from __future__ import annotations

import os

import pyarrow.parquet as pq
import pytest

from analysis.canonical import sha256_file
from analysis.evidence_records import (
    DeliveryAssignment,
    DeliveryBasis,
    DeliveryRequirement,
    PropertyRecord,
)
from analysis.firewall import Rejection
from analysis.ids import derive_scorecard_set_id
from analysis.pipeline import run_pipeline
from provenance_helpers import METHOD, both_verifiers, emit_run, failed

import fixtures as fx


# ------------------------------------------- BLOCKER 1: the delivery reduction is a set

def _competing_assignments():
    def asg(aid, basis, who):
        return DeliveryAssignment(
            assignment_id=aid, candidate_id="FIXTURE-001", context_id="CTX-001A",
            requirement=DeliveryRequirement.LOCAL_CNS,   # the SAME requirement in both
            basis=basis, assigned_by=who, rule_id="explicit_assignment_required",
            rule_version="1.0.0", rationale=f"FIXTURE: {aid}",
            evidence=fx._delivery_evidence(),
        )
    return (asg("DLV-GOOD", DeliveryBasis.MECHANISM_WITH_PHARMACOLOGY_EVIDENCE, "reviewer-01"),
            asg("DLV-BAD", DeliveryBasis.TARGET_BIOLOGY_ONLY, "reviewer-02"))


def _inputs_with(pair):
    inputs = fx.stage4_inputs()
    rest = [a for a in inputs.delivery_assignments if a.assignment_id != "DLV-001A"]
    inputs.delivery_assignments = list(pair) + rest
    return inputs


@pytest.mark.parametrize("order", ["good_first", "bad_first"])
def test_two_distinct_assignments_are_conflicting_in_every_order(order):
    """The reproduced defect: one order gave local_CNS/gate=true, the other uncertain."""
    good, bad = _competing_assignments()
    pair = (good, bad) if order == "good_first" else (bad, good)
    result = run_pipeline(_inputs_with(pair), METHOD)
    d = [x for cr in result.candidates for x in cr.delivery if x.context_id == "CTX-001A"][0]
    assert d.requirement == "delivery_requirement_uncertain"
    assert d.reason_code == "conflicting_assignments"
    assert d.nebpi_primary_gate is None
    assert d.conflicting_assignment_ids == ("DLV-BAD", "DLV-GOOD")


def test_delivery_assignment_order_is_byte_identical(tmp_path):
    """Same id AND same bytes — one cache key can no longer be two documents."""
    good, bad = _competing_assignments()
    seen = {}
    for i, pair in enumerate([(good, bad), (bad, good)]):
        inputs = _inputs_with(pair)
        out_dir, manifest, _r = emit_run(inputs, tmp_path, name=f"o{i}")
        emit_time, standalone = both_verifiers(out_dir, inputs)
        assert emit_time["status"] == "pass", failed(emit_time)
        assert standalone["status"] == "pass", failed(standalone)
        seen[i] = (
            manifest["scorecard_set_id"],
            sha256_file(os.path.join(out_dir, "scorecards.json")),
            sha256_file(os.path.join(out_dir, "delivery_evidence.parquet")),
            sha256_file(os.path.join(out_dir, "delivery_assignments.parquet")),
        )
    assert seen[0] == seen[1], "the reduction is a function of the SET, not the order"


def test_a_changed_assignment_moves_the_run_identity():
    """The basis is part of the claim, so changing it must change the identity."""
    good, _bad = _competing_assignments()
    ids = set()
    for basis in (DeliveryBasis.MECHANISM_WITH_PHARMACOLOGY_EVIDENCE,
                  DeliveryBasis.CLINICAL_EVIDENCE):
        inputs = _inputs_with((DeliveryAssignment(**{**good.model_dump(),
                                                     "basis": basis.value}),))
        sid, _k = derive_scorecard_set_id(inputs.candidate_set, METHOD,
                                          inputs.evidence_lanes(), inputs.sources,
                                          "lock", inputs.config)
        ids.add(sid)
    assert len(ids) == 2, "an assignment's basis must feed the scorecard_set_id"


def test_a_byte_identical_duplicate_assignment_is_refused():
    """An id supplied twice is a malformed evidence set, agreeing or not."""
    inputs = fx.stage4_inputs()
    dup = [a for a in inputs.delivery_assignments if a.assignment_id == "DLV-001A"][0]
    inputs.delivery_assignments = list(inputs.delivery_assignments) + [dup]
    with pytest.raises(Rejection, match="duplicate assignment_id"):
        run_pipeline(inputs, METHOD)


def test_a_conflicting_duplicate_assignment_id_is_refused():
    """Same id, different content: two records claiming to be one."""
    inputs = fx.stage4_inputs()
    orig = [a for a in inputs.delivery_assignments if a.assignment_id == "DLV-001A"][0]
    clash = DeliveryAssignment(**{**orig.model_dump(),
                                  "basis": DeliveryBasis.CLINICAL_EVIDENCE.value,
                                  "rationale": "a different claim under the same id"})
    inputs.delivery_assignments = list(inputs.delivery_assignments) + [clash]
    with pytest.raises(Rejection, match="duplicate assignment_id"):
        run_pipeline(inputs, METHOD)


# ------------------------------------------- MAJOR 4: agreeing property rows

def _agreeing_clogp_pair():
    """Two ClogP rows, same calculator and value, different method and different source."""
    base = [p for p in fx.properties()
            if p.candidate_id == "FIXTURE-001" and p.property_id == "clogp"][0]
    alt = PropertyRecord(**{
        **base.model_dump(),
        "property_record_id": "PRP-FIXTURE-001-clogp-biobyte-2",
        "method": "BioByte CLOGP (v4.3 batch)",
        "provenance": fx._prov("src.fixture.props.acd",
                               "read clogp for FXM-001 from the cached acd response"
                               ).model_dump(),
    })
    return base, alt


def _inputs_with_props(pair):
    inputs = fx.stage4_inputs()
    rest = [p for p in inputs.properties
            if not (p.candidate_id == "FIXTURE-001" and p.property_id == "clogp")]
    inputs.properties = list(pair) + rest
    return inputs


@pytest.mark.parametrize("order", ["orig_first", "alt_first"])
def test_agreeing_property_rows_bind_their_whole_evidence_set(order):
    """The reproduced defect: usable[0] won, so one id carried two provenance chains."""
    base, alt = _agreeing_clogp_pair()
    pair = (base, alt) if order == "orig_first" else (alt, base)
    result = run_pipeline(_inputs_with_props(pair), METHOD)
    mpo = [cr.cns_mpo for cr in result.candidates if cr.candidate_id == "FIXTURE-001"][0]

    # The score is well defined (both rows agree on calculator + value)...
    assert mpo.components["clogp"] == 1.0
    # ...and EVERY row behind it is named. No row is silently chosen or dropped.
    sources = sorted(p["source_record_id"] for p in mpo.input_provenance
                     if p["property_id"] == "clogp")
    assert sources == ["src.fixture.props.acd", "src.fixture.props.biobyte"]
    records = sorted(p["property_record_id"] for p in mpo.input_provenance
                     if p["property_id"] == "clogp")
    assert records == ["PRP-FIXTURE-001-clogp-biobyte-2",
                       "PRP-FIXTURE-001-clogp-biobyte_clogp"]


def test_agreeing_property_row_order_is_byte_identical(tmp_path):
    base, alt = _agreeing_clogp_pair()
    seen = {}
    for i, pair in enumerate([(base, alt), (alt, base)]):
        inputs = _inputs_with_props(pair)
        out_dir, manifest, _r = emit_run(inputs, tmp_path, name=f"p{i}")
        emit_time, standalone = both_verifiers(out_dir, inputs)
        assert emit_time["status"] == "pass", failed(emit_time)
        assert standalone["status"] == "pass", failed(standalone)
        seen[i] = (manifest["scorecard_set_id"],
                   sha256_file(os.path.join(out_dir, "scorecards.json")),
                   sha256_file(os.path.join(out_dir, "property_evidence.parquet")))
    assert seen[0] == seen[1]


def test_both_agreeing_rows_are_emitted_as_accepted(tmp_path):
    base, alt = _agreeing_clogp_pair()
    out_dir, _m, _r = emit_run(_inputs_with_props((base, alt)), tmp_path)
    rows = pq.read_table(os.path.join(out_dir, "property_evidence.parquet")).to_pylist()
    clogp = [r for r in rows if r["candidate_id"] == "FIXTURE-001"
             and r["property_id"] == "clogp"]
    assert len(clogp) == 2
    assert all(r["accepted"] for r in clogp)
    assert all(r["component_score_t0"] == 1.0 for r in clogp)


def test_disagreeing_property_rows_are_still_ambiguous():
    """Corroboration is not conflict: a different VALUE is refused, exactly as before."""
    base, alt = _agreeing_clogp_pair()
    disagreeing = PropertyRecord(**{**alt.model_dump(), "value_source_string": "3.9"})
    result = run_pipeline(_inputs_with_props((base, disagreeing)), METHOD)
    mpo = [cr.cns_mpo for cr in result.candidates if cr.candidate_id == "FIXTURE-001"][0]
    assert mpo.status == "incomplete"
    assert mpo.components["clogp"] is None
    assert "ambiguous_multiple_sources" in {m.reason_code for m in mpo.missing_inputs}


def test_a_duplicate_property_record_id_is_refused():
    base, _alt = _agreeing_clogp_pair()
    twin = PropertyRecord(**{**base.model_dump(), "method": "a different method"})
    with pytest.raises(Rejection, match="duplicate property_record_id"):
        run_pipeline(_inputs_with_props((base, twin)), METHOD)
