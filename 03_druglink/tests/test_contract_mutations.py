"""Mutation tests for the rebased contract.

Each of these is an attempt to smuggle a retired or unsound claim back in. Every one
must be REFUSED — and refused structurally, not by a lint that a downstream writer could
forget to run.

  1. the retired promotion/eligibility vocabulary;
  2. a NUMERIC Stage-2 joint field (a combined score wearing a typed name);
  3. wrong-arm pathway inheritance (evidence from one arm supporting a node on the other);
  4. a fixture relabelled as a real analysis.
"""
from __future__ import annotations

import json

import pytest

import fixture_public_responses as FX
import science_fixture
from druglink import (acquisition, artifact_class as ac, joint_context, pathways,
                      science_registry,
                      workflow as wf)

CTLA4 = "ENSG00000163599"
IL2RA = "ENSG00000134460"


def _enrichment():
    """A COMPUTED enrichment: numeric, with the context that makes it reproducible."""
    return {"method_id": "enrich.v1",
            "statistic_name": "hypergeometric_odds_ratio",
            "enrichment_value": 3.7,                 # NUMERIC, not stringified
            "inference_status": "not_calibrated",
            "rounding_rule": "ieee754_float64_no_rounding",
            "gene_set_release": "GO-2026-05",
            "gene_set_sha256": "b" * 64,
            "universe_binding": {"universe_id": "stage2_common_universe",
                                 "universe_sha256": "c" * 64, "n_genes": 18000}}


def _prog(arm):
    """Arm-specific computed evidence, repeating the COMPLETE parent binding inline.

    A node must bind a hash-bound parent enrichment: either a parent_enrichment_ref, or —
    as here — the full gene-set release + universe binding repeated inline. Neither is
    a dangling parent, and a dangling parent is refused.
    """
    return {"method_id": "enrich.v1", "desired_arm": arm,
            "statistic_name": "hypergeometric_odds_ratio",
            "enrichment_value": 3.7,
            "inference_status": "not_calibrated",
            "rounding_rule": "ieee754_float64_no_rounding",
            "gene_set_release": "GO-2026-05",
            "gene_set_sha256": "b" * 64,
            "universe_binding": {"universe_id": "stage2_common_universe",
                                 "universe_sha256": "c" * 64, "n_genes": 18000}}



# --------------------------------------------------------------------------- #
# 1. Retired promotion/eligibility fields.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field", [
    "production_candidate", "production_promotion_eligible",
    "may_write_production_pointer", "production_pointer_written",
    "research_pk_annotation_eligible", "research_direction_evaluable",
    "production_eligible", "stage3_eligible", "stage4_eligible",
    "annotation_only", "production_pointer", "promoted_to_production",
    "current_pointer", "namespace",
])
def test_every_retired_field_is_refused_at_any_depth(field):
    assert field in ac.RETIRED_KEYS

    # Top level.
    with pytest.raises(ac.ArtifactClassError, match="retired"):
        ac.check_no_retired_keys({"artifact_class": "analysis", field: False})

    # Nested in a list, inside a dict — a relabel hides wherever it can.
    with pytest.raises(ac.ArtifactClassError, match="retired"):
        ac.check_no_retired_keys(
            {"candidates": [{"candidate_id": "x", field: False}]})

    # The refusal names the retired vocabulary, so the writer learns WHY.
    with pytest.raises(ac.ArtifactClassError, match="RETIRED"):
        ac.check_no_retired_keys({field: True})


def test_the_retired_vocabulary_is_absent_from_the_verifier_contract():
    """The verifier restates the retired list independently, and refuses it too."""
    from verifier import policy

    assert policy.RETIRED_KEYS == ac.RETIRED_KEYS
    assert policy.retired_keys_in({"a": {"production_candidate": False}})


# --------------------------------------------------------------------------- #
# 2. Stage-2 joint context: TYPED. pareto_tier IS numeric — and that is correct.
# --------------------------------------------------------------------------- #
def test_pareto_tier_is_a_positive_integer_and_is_accepted():
    """A Pareto tier is a rank-like TIER LABEL, not a hidden combined score."""
    for tier in (1, 2, 7):
        assert joint_context.from_screen_row({"pareto_tier": tier})[
            "pareto_tier"] == tier

    # Null means NOT JOINTLY EVALUABLE. That is a fact, not a zero.
    assert joint_context.from_screen_row({"pareto_tier": None})["pareto_tier"] is None

    # It starts at 1: 0 and negatives are not tiers.
    for bad in (0, -1):
        with pytest.raises(joint_context.JointContextError, match="must start at 1"):
            joint_context.from_screen_row({"pareto_tier": bad})

    # A float or a string is not a Pareto tier.
    for bad in (2.5, "tier_1", True):
        with pytest.raises(joint_context.JointContextError,
                           match="positive integer"):
            joint_context.from_screen_row({"pareto_tier": bad})


def test_joint_status_is_a_closed_enum_and_method_id_is_a_string():
    for value in joint_context.JOINT_STATUS_VALUES:
        assert joint_context.from_screen_row({"joint_status": value})[
            "joint_status"] == value

    with pytest.raises(joint_context.JointContextError, match="closed enum"):
        joint_context.from_screen_row({"joint_status": "pareto_optimal"})

    assert joint_context.from_screen_row(
        {"joint_ordering_method_id": "spot.stage02.joint.v1"}
    )["joint_ordering_method_id"] == "spot.stage02.joint.v1"
    with pytest.raises(joint_context.JointContextError, match="must be a string"):
        joint_context.from_screen_row({"joint_ordering_method_id": 7})


def test_typed_joint_context_is_republished_but_never_directional():
    block = joint_context.from_provenance({
        "stage2_joint_ordering": {"joint_status": "both_arms",
                                  "pareto_tier": 1,
                                  "joint_ordering_method_id": "m1"}})
    assert block["stage2_joint_context"] == "provided"
    assert block["pareto_tier"] == 1
    assert block["used_to_infer_drug_direction"] is False
    assert block["used_to_rank_or_filter_arms"] is False
    assert block["rewritten_by_stage3"] is False

    # Absent is `not_provided` — never a favourable default, never invented.
    absent = joint_context.from_provenance({})
    assert absent["pareto_tier"] == joint_context.NOT_PROVIDED
    assert absent["stage2_joint_context"] == joint_context.NOT_PROVIDED

    # STRUCTURAL: the direction engine has no parameter through which joint context
    # could reach it. This is what makes "never used for direction" enforceable rather
    # than merely promised.
    import inspect

    from druglink import direction
    params = set(inspect.signature(direction.translate).parameters)
    assert not (params & {"joint_status", "pareto_tier", "joint_ordering_method_id",
                          "joint_context", "pareto"})
    assert params == {"desired_modulation", "effect", "arm_evaluable",
                      "target_entity_is_single_protein", "action_conflict",
                      "origin_type"}


def test_numeric_combined_objectives_are_still_refused():
    """A numeric TIER is fine. A numeric weighted SUM of the arms is not."""
    from druglink.armlever import BANNED_OBJECTIVE_COLUMNS

    for banned in ("combined_score", "balanced_skew", "balanced_a_to_b",
                   "total_skew", "overall_rank", "rank", "headline_rank",
                   "mean_arm_score", "aggregate_score", "composite_score"):
        assert banned in BANNED_OBJECTIVE_COLUMNS
    # ...while the TYPED joint fields are context and are NOT banned.
    for typed in ("joint_status", "pareto_tier", "joint_ordering_method_id"):
        assert typed not in BANNED_OBJECTIVE_COLUMNS


def test_stage3_never_alters_direct_ranks_or_pareto_tiers(analysis_build,
                                                          loaded_direct):
    """Direct's ranks are upstream facts. Stage 3 republishes; it never rewrites."""
    import pandas as pd

    screen = loaded_direct.screen
    levers = analysis_build["tables"]["arm_levers"]
    by_key = {(r["target_id"], r["desired_arm"]): r for r in levers}

    for row in screen.to_dict("records"):
        for arm, col in (("away_from_A", "rank_away_from_A"),
                         ("toward_B", "rank_toward_B")):
            want = row[col]
            got = by_key[(row["target_id"], arm)]["arm_rank"]
            assert got == (None if pd.isna(want) else int(want))

    doc = analysis_build["document"]
    assert doc["stage3_never_alters_direct_ranks_or_stage2_pareto_tiers"] is True
    assert doc["stage2_joint_context"]["rewritten_by_stage3"] is False

    # An inverse-direction hypothesis carries Direct's rank VERBATIM — it never
    # promotes, demotes or invents one.
    for cand in analysis_build["tables"]["candidates"]:
        for support in cand["inverse_direction_support"]:
            gene, arm = support["target_ensembl"], support["desired_arm"]
            src = next(r for r in levers
                       if r["target_ensembl"] == gene and r["desired_arm"] == arm)
            assert support["arm_rank"] == src["arm_rank"]
            assert support["arm_evidence_tier"] == src["arm_evidence_tier"]


# --------------------------------------------------------------------------- #
# 3. Wrong-arm pathway inheritance.
# --------------------------------------------------------------------------- #
def _pathway_doc(direct, node):
    return {
        "schema_version": pathways.PATHWAY_SCHEMA,
        "artifact_class": "analysis",
        "direct_run_id": direct.run_id,
        "direct_run_binding_sha256": direct.binding_sha256,
        "pathways": [{
            "pathway_id": "GO:0042110", "pathway_source": "GO",
            "pathway_source_release": "2026-05",
            "pathway_source_sha256": "a" * 64,
            "computed_enrichment": _enrichment(),
            "nodes": [node],
        }],
    }


def _node(*, arm, evidence_arm, modulation="decrease", cite_arm=None):
    return {
        "target_ensembl": CTLA4,
        "desired_arm": arm,
        "desired_target_modulation": modulation,
        "evidence_status": "computed_enrichment_member",
        "programmatic_evidence": _prog(evidence_arm),
        "contributing_perturbations": [
            {"target_ensembl": IL2RA,
             "desired_arm": cite_arm or arm}],
    }


def test_pathway_evidence_computed_on_the_other_arm_is_refused(loaded_direct):
    """Evidence enriched on one arm can NEVER support a node on the other."""
    bad = _pathway_doc(loaded_direct,
                       _node(arm="away_from_A", evidence_arm="toward_B"))
    with pytest.raises(pathways.PathwayError, match="ARM-SPECIFIC"):
        pathways.admit(bad, artifact_class="analysis", direct=loaded_direct)

    # The matching arm is accepted.
    good = _pathway_doc(loaded_direct,
                        _node(arm="away_from_A", evidence_arm="away_from_A"))
    admitted = pathways.admit(good, artifact_class="analysis", direct=loaded_direct)
    assert admitted["levers"][0]["programmatic_evidence_method_id"] == "enrich.v1"


def test_a_contributing_perturbation_from_the_other_arm_is_not_evidence(loaded_direct):
    """A perturbation measured on the other arm does not support this node."""
    doc = _pathway_doc(loaded_direct,
                       _node(arm="away_from_A", evidence_arm="away_from_A",
                             cite_arm="toward_B"))
    admitted = pathways.admit(doc, artifact_class="analysis", direct=loaded_direct)

    lever = admitted["levers"][0]
    assert lever["contributing_perturbations"] == []
    # With no valid citation the node is barred from every drug edge, and says so.
    assert lever["gene_target_drug_edge_permitted"] is False
    assert any(d["state"] == "no_contributing_perturbation"
               for d in admitted["dispositions"])


def test_a_node_requires_programmatic_evidence_not_a_claude_science_reading(
        loaded_direct):
    """Interpretation is provenance. It can never stand in for computed enrichment."""
    node = _node(arm="away_from_A", evidence_arm="away_from_A")
    del node["programmatic_evidence"]
    # An embedded free-form interpretation is not a computation and cannot stand in.
    node["science_evidence_refs"] = [
        {"science_evidence_id": "sci_001", "science_evidence_sha256": "d" * 64,
         "record_type": "mechanistic_rationale"}]

    with pytest.raises(pathways.PathwayError, match="Claude Science reading is "
                                                     "provenance, not enrichment"):
        pathways.admit(_pathway_doc(loaded_direct, node),
                       artifact_class="analysis", direct=loaded_direct)


def test_a_pathway_must_pin_its_release_and_hash(loaded_direct):
    """A pathway term's MEMBERSHIP changes between releases."""
    doc = _pathway_doc(loaded_direct,
                       _node(arm="away_from_A", evidence_arm="away_from_A"))
    del doc["pathways"][0]["pathway_source_sha256"]
    with pytest.raises(pathways.PathwayError, match="not reproducible"):
        pathways.admit(doc, artifact_class="analysis", direct=loaded_direct)


# --------------------------------------------------------------------------- #
# 4. Fixture relabelling.
# --------------------------------------------------------------------------- #
def test_a_fixture_cannot_be_relabelled_as_an_analysis(tmp_path):
    """Synthetic bytes wearing an `acquired_public` label are caught, not trusted."""
    import hashlib
    import os
    import shutil

    from druglink import acquire_public as ap

    cache = str(tmp_path / "cache")
    os.makedirs(cache, exist_ok=True)
    direct = FX.direct_double([FX.CTLA4, FX.IL2RA])
    ap.acquire(cache_root=cache, artifact_class="analysis", direct=direct,
               top_per_arm=25, sources=("uniprot", "chembl"),
               chembl_release="CHEMBL_37", transport=FX.FakeTransport())

    attacked = str(tmp_path / "attacked")
    shutil.copytree(cache, attacked)
    path = os.path.join(attacked, acquisition.MANIFEST_FILE)
    manifest = json.loads(open(path).read())

    entry = next(e for e in manifest["entries"]
                 if e["adapter"] == "chembl_mechanism"
                 and e["acquisition_status"] == "acquired_public")
    forged = FX.synthetic_chembl_mechanism(stamped=True)
    raw = os.path.join(attacked, entry["raw_file"])
    open(raw, "wb").write(forged)
    # Reseal so the manifest is internally consistent — the relabel must still fail.
    entry["raw_sha256"] = hashlib.sha256(forged).hexdigest()
    entry["raw_bytes"] = len(forged)
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)

    # The loader refuses it outright...
    with pytest.raises(acquisition.AcquisitionError):
        acquisition.load_manifest(attacked, "analysis", direct=direct, verify=False)

    # ...and so does the independent acquisition verifier.
    from druglink import verify_acquisition as va
    rep = va.verify(attacked, run_dir=None, inputs_root=None,
                    artifact_class="analysis", direct=direct)
    assert rep.failed
    assert any("fixture" in name for name, _ok, _d in rep.failed)


def test_an_analysis_may_not_consume_fixture_bytes_and_vice_versa():
    assert ac.ALLOWED_ACQUISITION["analysis"] == ("acquired_public",)
    assert ac.ALLOWED_ACQUISITION["fixture"] == ("synthetic_fixture",)
    # A fixture never reaches Stage 4, no matter how good its evidence looks.
    assert wf.stage4_assessment(
        artifact_class="fixture", identity_status="resolved",
        active_moiety_id="AM:CHEMBL:CHEMBL1",
        directional_statuses={wf.OBSERVED_PERTURBATION}
    ) == (wf.NOT_QUEUED, wf.REASON_NOT_QUEUED_FIXTURE)


# --------------------------------------------------------------------------- #
# 5. Computed enrichment is NUMERIC; Claude Science is REFERENCED, never embedded.
# --------------------------------------------------------------------------- #
def test_enrichment_value_must_be_numeric_with_its_full_context(loaded_direct):
    """A computed statistic is a number. Stringifying it destroys it."""
    node = _node(arm="away_from_A", evidence_arm="away_from_A")

    # Numeric is required — a stringified statistic is refused.
    bad = _pathway_doc(loaded_direct, node)
    bad["pathways"][0]["computed_enrichment"]["enrichment_value"] = "3.7"
    with pytest.raises(pathways.PathwayError, match="must be NUMERIC"):
        pathways.admit(bad, artifact_class="analysis", direct=loaded_direct)

    # ...and a bare number is not enough: it needs WHAT it is, HOW it was computed, the
    # rounding rule, the gene set and the universe it was computed against.
    for field, match in (("statistic_name", "statistic_name"),
                         ("rounding_rule", "rounding_rule"),
                         ("gene_set_sha256", "gene_set_release"),
                         ("universe_binding", "universe")):
        doc = _pathway_doc(loaded_direct, node)
        doc["pathways"][0]["computed_enrichment"].pop(field)
        with pytest.raises(pathways.PathwayError, match=match):
            pathways.admit(doc, artifact_class="analysis", direct=loaded_direct)


def test_p_and_q_are_refused_while_the_method_is_not_calibrated(loaded_direct):
    """No calibrated null exists, and a p-value without one is not a p-value."""
    for field in ("p_value", "q_value"):
        doc = _pathway_doc(loaded_direct,
                           _node(arm="away_from_A", evidence_arm="away_from_A"))
        doc["pathways"][0]["computed_enrichment"][field] = 0.001
        with pytest.raises(pathways.PathwayError, match="not_calibrated"):
            pathways.admit(doc, artifact_class="analysis", direct=loaded_direct)

    # inference_status must actually say not_calibrated.
    doc = _pathway_doc(loaded_direct,
                       _node(arm="away_from_A", evidence_arm="away_from_A"))
    doc["pathways"][0]["computed_enrichment"]["inference_status"] = "calibrated"
    with pytest.raises(pathways.PathwayError, match="independently justified"):
        pathways.admit(doc, artifact_class="analysis", direct=loaded_direct)


def test_claude_science_is_referenced_by_typed_id_and_hash_never_embedded(
        loaded_direct, tmp_path):
    """An interpretation is not a computation, and an un-hashed blob is unverifiable."""
    node = _node(arm="away_from_A", evidence_arm="away_from_A")

    # A free-form string or object is NOT a science evidence reference.
    for junk in ("this gene is clearly central", {"note": "central"}, 42):
        doc = _pathway_doc(loaded_direct, node)
        doc["pathways"][0]["science_evidence_refs"] = junk
        with pytest.raises((pathways.PathwayError,
                            science_registry.ScienceRegistryError),
                           match="TYPED references|typed record"):
            pathways.admit(doc, artifact_class="analysis", direct=loaded_direct)

    # A reference missing its id / hash / type cannot be verified or attributed.
    for missing in ("science_evidence_id", "science_evidence_sha256", "record_type"):
        ref = {"science_evidence_id": "sci_1", "science_evidence_sha256": "d" * 64,
               "record_type": "literature_support"}
        ref.pop(missing)
        doc = _pathway_doc(loaded_direct, node)
        doc["pathways"][0]["science_evidence_refs"] = [ref]
        with pytest.raises((pathways.PathwayError,
                            science_registry.ScienceRegistryError),
                           match="content-hashed|missing"):
            pathways.admit(doc, artifact_class="analysis", direct=loaded_direct)

    # A well-formed typed reference is accepted — but ONLY if it actually resolves. A
    # reference whose record is not in the registry is dangling, and a dangling reference
    # is refused, not carried.
    doc = _pathway_doc(loaded_direct, node)
    doc["pathways"][0]["science_evidence_refs"] = [
        {"science_evidence_id": "sci_1", "science_evidence_sha256": "d" * 64,
         "record_type": "mechanistic_rationale"}]
    with pytest.raises(science_registry.ScienceRegistryError,
                       match="no registry was supplied|not in the registry"):
        pathways.admit(doc, artifact_class="analysis", direct=loaded_direct)
    # ...and with a registry it resolves, the FULL typed triple is carried through —
    # never the id alone. An id without its hash is not a binding.
    refs = science_fixture.make(str(tmp_path / "registry"))
    doc = _pathway_doc(loaded_direct, node)
    doc["pathways"][0]["science_evidence_refs"] = [refs["sci_1"]]
    admitted = pathways.admit(doc, artifact_class="analysis", direct=loaded_direct,
                              science_registry_root=str(tmp_path / "registry"))
    carried = admitted["pathways"][0]["science_evidence_refs"]
    assert carried == [refs["sci_1"]]
    assert carried[0]["science_evidence_sha256"] and carried[0]["record_type"]


def test_evidence_status_is_a_closed_enum(loaded_direct):
    node = _node(arm="away_from_A", evidence_arm="away_from_A")
    node["evidence_status"] = "it_felt_related"
    with pytest.raises(pathways.PathwayError, match="CLOSED enum"):
        pathways.admit(_pathway_doc(loaded_direct, node),
                       artifact_class="analysis", direct=loaded_direct)
    for ok in pathways.EVIDENCE_STATUSES:
        node["evidence_status"] = ok
        pathways.admit(_pathway_doc(loaded_direct, node),
                       artifact_class="analysis", direct=loaded_direct)
