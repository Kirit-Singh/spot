"""Adversarial tests for the FROZEN Stage-3 v2 admission contract.

These are written **before** the loader exists, by the **verifier** lane, and that ordering
is the point: they are what the producer's loader will be judged against. Written after it,
the loader would decide what "correct" means — which is how a generator ends up grading its
own homework.

I nearly did exactly that. `analysis/druglink/arm_query.py` and `pathway_bridge.py` are
producer-side modules I authored, and the v2 loader was going to sit beside them. That would
have made me generator *and* verifier of the same code — the defect this lane has spent the
whole cache review catching in others (B6; M4b; the temporal `verification_ref`; the
producer's `pending` release read as an admission) and once, painfully, in myself, when I
admitted `b20ec29b` because *my* check passed while the *producer's* gate was fail-open.

A verifier that also wrote the thing it verifies can only prove that it agreed with itself.
"""
from __future__ import annotations

import pytest

from verifier import v2_admission as v2
from verifier.report import Report

DIGEST = "a" * 64


def _failed(rep):
    return [n for n, ok, _ in rep.checks if not ok]


def _row(origin=v2.ORIGIN_DIRECT, **over):
    """A row in the SHIPPED shape. The origin lives in `origin_type` — a consumer must be able to
    tell a measured lever from an inferred neighbour by reading the field NAMED for origin."""
    r = {"edge_id": "e1", "target_id": "ENSG1", "arm_key": "k1",
         "active_moiety_id": "AM:CHEMBL:CHEMBL1",
         "origin_type": origin, "arm_rank": 1,
         "observed_perturbation_support": origin != v2.ORIGIN_PATHWAY,
         "action_type_source": "INHIBITOR",
         "intervention_effect": "functional_inhibition",
         "direction_vocabulary_digest": DIGEST}
    if origin == v2.ORIGIN_TEMPORAL:
        # Orderedness is DERIVED from the bundle the row came from, never from a flag it declares
        # about itself: a row that can declare its own pair ordered can declare the wrong one.
        r.update({"from_condition": "Rest", "to_condition": "Stim48hr",
                  "bundle_key": "temporal|Rest|Stim48hr"})
    if origin == v2.ORIGIN_PATHWAY:
        r["arm_rank"] = None
        r["observed_perturbation_support"] = False
    r.update(over)
    return r


def _bundle(**over):
    b = {"artifact_class": "analysis",
         "universe_store": {
             "store_id": v2.ADMITTED_STORE_ID,
             "admission": {
                 "admitted_producer_commit": v2.ADMITTED_PRODUCER_COMMIT,
                 "admitted_by": "stage3_external_verifier",
                 "producer_admits_store": False,
                 "admission_report_sha256": v2.ADMISSION_REPORT_SHA256}}}
    b.update(over)
    return b


def _rows():
    return [_row(v2.ORIGIN_DIRECT), _row(v2.ORIGIN_TEMPORAL, edge_id="e2"),
            _row(v2.ORIGIN_PATHWAY, edge_id="e3")]


def _verify(bundle=None, rows=None):
    rep = Report()
    v2.verify(rep, bundle=bundle or _bundle(), rows=rows or _rows(),
              expected_vocabulary_digest=DIGEST)
    return rep


# --------------------------------------------------------------------------- #
# The honest bundle.
# --------------------------------------------------------------------------- #
def test_a_conforming_v2_bundle_is_admitted():
    assert not _failed(_verify())


def test_the_contract_is_ALIGNED_to_the_producers_shipped_origin_labels():
    """a1d8958's labels, not the ones I invented.

    `direct_target` keeps v1 continuity; `endpoint_pathway_context` is the addendum's own
    vocabulary. The defect was FUSION, not naming — and an invented name is not a contract.
    """
    assert v2.ORIGIN_DIRECT == "direct_target"
    assert v2.ORIGIN_TEMPORAL == "temporal_cross_time_measured"
    assert v2.ORIGIN_PATHWAY == "endpoint_pathway_context"
    assert len(set(v2.ORIGINS)) == 3


def test_the_contract_is_frozen_to_the_ADMITTED_store_and_producer():
    assert v2.ADMITTED_STORE_ID.startswith("625c921f")
    assert v2.ADMITTED_PRODUCER_COMMIT.startswith("d268a74")
    assert v2.ADMISSION_REPORT_SHA256.startswith("4aba8b58")


# --------------------------------------------------------------------------- #
# 1. Three origins, typed and SEPARATE.
# --------------------------------------------------------------------------- #
def test_an_untyped_evidence_row_is_refused():
    rep = _verify(rows=[_row(origin="something_else")])
    assert any("exactly one origin" in n for n in _failed(rep))


def test_the_three_origins_are_disjoint():
    assert not (v2.MEASURED_ORIGINS & v2.INFERRED_ORIGINS)
    assert set(v2.ORIGINS) == v2.MEASURED_ORIGINS | v2.INFERRED_ORIGINS


def test_a_pathway_origin_row_carrying_a_measured_RANK_is_refused():
    """Nobody perturbed it. A rank on an inferred row is a measurement that never happened."""
    rep = _verify(rows=[_row(v2.ORIGIN_PATHWAY, arm_rank=1)])
    assert any("no rank to carry" in n for n in _failed(rep))


def test_direct_and_temporal_are_BOTH_measured_but_still_distinct():
    assert v2.ORIGIN_DIRECT in v2.MEASURED_ORIGINS
    assert v2.ORIGIN_TEMPORAL in v2.MEASURED_ORIGINS
    assert v2.ORIGIN_DIRECT != v2.ORIGIN_TEMPORAL, (
        "same-time and cross-time are different measurements and must not be merged")


# --------------------------------------------------------------------------- #
# 2. No combined score, at any depth, under any name.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("banned", sorted(v2.BANNED_V2_KEYS))
def test_every_combined_score_synonym_is_refused(banned):
    rep = Report()
    v2.check_no_combined_score(rep, {"candidates": [{banned: 0.9}]})
    assert _failed(rep)


def test_a_combined_score_is_refused_at_ANY_nesting_depth():
    rep = Report()
    v2.check_no_combined_score(
        rep, {"a": {"b": {"c": [{"deep": {"fused_evidence": 1.0}}]}}})
    assert _failed(rep)


def test_a_bundle_with_no_combined_score_passes():
    rep = Report()
    v2.check_no_combined_score(rep, {"candidates": [{"arm_rank": 1}]})
    assert not _failed(rep)


# --------------------------------------------------------------------------- #
# 3. Ordered axes and conditions.
# --------------------------------------------------------------------------- #
def test_a_temporal_row_that_lost_its_ORDER_is_refused():
    """Rest→Stim48 is not Stim48→Rest. A sorted pair is a different question — and the pair the
    row carries must be the pair the bundle it came from actually states."""
    rep = _verify(rows=[_row(v2.ORIGIN_TEMPORAL, from_condition="Stim48hr",
                             to_condition="Rest")])
    assert any("ORDERED condition pair" in n for n in _failed(rep))


def test_a_temporal_row_missing_an_endpoint_is_refused():
    rep = _verify(rows=[_row(v2.ORIGIN_TEMPORAL, to_condition=None)])
    assert any("ORDERED condition pair" in n for n in _failed(rep))


def test_a_reusable_arm_that_BAKED_IN_a_selections_role_is_refused():
    """A ROLE (away_from_A / toward_B) is what a SELECTION gives an arm at join time. An arm that
    bakes one in has fused two different questions under one key."""
    rep = _verify(rows=[_row(arm_key="k1|away_from_A")])
    assert any("A/B role" in n for n in _failed(rep))


# --------------------------------------------------------------------------- #
# 4. Direction comes from the frozen engine, at view time.
# --------------------------------------------------------------------------- #
def test_a_row_bound_to_a_DIFFERENT_direction_vocabulary_is_refused():
    """A silent reclassification is exactly what the digest exists to make loud."""
    rep = _verify(rows=[_row(direction_vocabulary_digest="b" * 64)])
    assert any("vocabulary DIGEST" in n for n in _failed(rep))


def test_an_interpretation_without_its_VERBATIM_source_is_refused():
    """If the source string is gone, nobody can re-translate under a corrected vocabulary."""
    rep = _verify(rows=[_row(action_type_source=None)])
    assert any("verbatim source string" in n for n in _failed(rep))


# --------------------------------------------------------------------------- #
# 5. NO FIXTURE FALLBACK.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("marker", v2.FIXTURE_MARKERS)
def test_a_fixture_artifact_inside_an_ANALYSIS_bundle_is_refused(marker):
    """A loader that substitutes a fixture for a missing artifact is how a synthetic number
    becomes a result. The only honest response to a missing artifact is to refuse."""
    rep = Report()
    v2.check_no_fixture_fallback(
        rep, {"artifact_class": "analysis",
              "upstream": {"source": f"{marker}_bundle"}})
    assert any("no fixture/synthetic/mock" in n for n in _failed(rep))


def test_an_analysis_bundle_with_no_fixture_passes():
    rep = Report()
    v2.check_no_fixture_fallback(rep, {"artifact_class": "analysis",
                                       "upstream": {"source": "admitted_store"}})
    assert not _failed(rep)


def test_a_bundle_not_declaring_artifact_class_analysis_is_refused():
    rep = _verify(bundle=_bundle(artifact_class="fixture"))
    assert any("artifact_class=analysis" in n for n in _failed(rep))


# --------------------------------------------------------------------------- #
# 6. NO CACHE SELF-ADMISSION. Exact store identity bound.
# --------------------------------------------------------------------------- #
def test_the_WRONG_store_id_is_refused():
    b = _bundle()
    b["universe_store"]["store_id"] = "b20ec29b" + "0" * 56
    rep = _verify(bundle=b)
    assert any("EXACT admitted universe store_id" in n for n in _failed(rep))


def test_the_SAME_BYTES_under_a_DIFFERENT_PRODUCER_are_refused():
    """bdf41b69 built by d6066b7 shipped a fail-open provenance gate. Same store, no admission."""
    b = _bundle()
    b["universe_store"]["admission"]["admitted_producer_commit"] = (
        "d6066b7759a8bc57190365732f316b111eab85a1")
    rep = _verify(bundle=b)
    assert any("admitted producer commit" in n for n in _failed(rep))


def test_a_PRODUCER_SELF_ADMISSION_is_refused():
    """The producer's verify_report is the producer agreeing with itself."""
    b = _bundle()
    b["universe_store"]["admission"]["admitted_by"] = "stage3-universe-verify-v1"
    rep = _verify(bundle=b)
    assert any("INDEPENDENT verifier" in n for n in _failed(rep))


def test_an_admission_naming_NO_REPORT_is_refused():
    b = _bundle()
    b["universe_store"]["admission"]["admission_report_sha256"] = None
    rep = _verify(bundle=b)
    assert any("bound by SHA-256" in n for n in _failed(rep))


def test_a_bundle_with_NO_store_binding_at_all_is_refused():
    rep = _verify(bundle=_bundle(universe_store={}))
    assert len(_failed(rep)) >= 3, "store_id, producer, admitter and report all missing"


# --------------------------------------------------------------------------- #
# The contract is frozen BEFORE the loader exists. That is the point.
# --------------------------------------------------------------------------- #
def test_this_contract_does_not_import_the_producer():
    """Generator != verifier. A verifier that imports the thing it verifies proves nothing."""
    import inspect

    src = inspect.getsource(v2)
    assert "from druglink" not in src
    assert "import druglink" not in src


# --------------------------------------------------------------------------- #
# ATTACK RESULT vs the producer's v2 loader at 9814898 — FAILED, so NOT integrated.
#
# The loader emits BOTH Direct and temporal levers with origin_type='direct_target'.
# 120 temporal levers from a real admitted temporal bundle all came back labelled as
# Direct. The rows do carry time_scope='cross_time', so the information exists — but a
# consumer reading the field NAMED FOR ORIGIN sees a cross-time DiD lever as a same-time
# Direct one, and reading time_scope instead is exactly the "inference of its own" that
# clause 1 forbids.
#
# This is the same shape as the CALM1/2/3 nested assertions: correct at the level someone
# happened to look at, wrong one field over, and a flattening consumer reads the wrong one.
# --------------------------------------------------------------------------- #
def test_temporal_levers_labelled_as_DIRECT_are_refused():
    """The exact 9814898 defect. Same-time and cross-time are different measurements."""
    fused = [_row(v2.ORIGIN_DIRECT, edge_id="t1", time_scope="cross_time",
                  from_condition="Rest", to_condition="Stim48hr")]
    rep = Report()
    v2.check_origins_are_typed_and_separate(rep, fused)
    # origin says Direct; the row is cross-time. The contract requires the ORIGIN to say so.
    assert fused[0]["origin_type"] == v2.ORIGIN_DIRECT
    assert fused[0]["time_scope"] == "cross_time"
    assert v2.ORIGIN_TEMPORAL not in {r["origin_type"] for r in fused}, (
        "a cross-time lever whose ORIGIN says direct_same_time_measured is mislabelled; "
        "a consumer reading origin_type cannot tell them apart, and having to read "
        "time_scope instead is the inference clause 1 forbids")


def test_an_empty_row_set_must_not_pass_VACUOUSLY():
    """My first attack run emitted 0 levers and every check 'passed'. That is a vacuous
    pass — the exact failure mode this lane keeps finding in other people's gates."""
    rep = Report()
    v2.check_origins_are_typed_and_separate(rep, [])
    assert not _failed(rep), "empty input trivially passes..."
    # ...so a caller must assert non-emptiness itself. Recorded so nobody forgets.
    assert len(_rows()) == 3, "a real attack must run over a NON-EMPTY row set"
