"""The inverse-direction hypothesis: a distinct state, end to end.

Knockdown moved an arm the UNDESIRED way, and a REAL sourced activation/agonism
mechanism exists on the exact single-protein target. That is its own state:

  * ``directional_evidence_status = inverse_direction_hypothesis`` — never folded into
    ``unresolved``, never folded into ``observed_perturbation``;
  * ``observed_perturbation_support = false`` — it is NOT observed gain of function;
  * ``stage3_evidence_class = inverse_direction_hypothesis`` — never a measurement's
    class, and the class is UNORDERED;
  * ``drug_mapping_status = mapped``;
  * ``stage4_assessment_status = queued``, reason ``mapped_inverse_direction_hypothesis``;
  * the exact supporting ARM and MECHANISM are preserved;
  * Direct ranks / arm evidence tiers / Stage-2 Pareto tiers are UNTOUCHED;
  * Claude Science reviews the biological plausibility LATER;
  * if NO real activation mechanism exists, nothing is invented.

The pinned real public sources report no activator for the run's targets, so the
end-to-end coverage below injects an **explicitly fixture-namespaced** ChEMBL agonist
response into a FIXTURE-class cache. It is a contract fixture, never a research finding.
"""
from __future__ import annotations

import json
import os
import shutil

import pytest

from druglink import (acquisition, artifact_class as ac, artifacts, run_stage3,
                      science_review, workflow as wf)
from druglink.direction import ORIGIN_DIRECT_TARGET
from verifier import policy, rebuild, sources, verify_stage3

IL2RA = "ENSG00000134460"          # the cross-arm conflict row: toward_B wants INCREASE
IL2RA_TARGET = "CHEMBL1778"


# --------------------------------------------------------------------------- #
# A fixture-class cache carrying a REAL-SHAPED agonist mechanism.
# --------------------------------------------------------------------------- #
def _agonist_cache(tmp_path, loaded_direct, action="AGONIST"):
    """Copy the analysis cache and add a sourced activation mechanism on IL2RA.

    Written as an `analysis` cache so the engine path is identical; the injected page is
    a real ChEMBL mechanism SHAPE carrying an agonist action. It exists only to exercise
    the contract — no compound here is a scientific finding.
    """
    import hashlib

    import fixture_public_responses as FXP
    from druglink import acquire_public as ap

    cache = str(tmp_path / "agonist_cache")
    os.makedirs(cache, exist_ok=True)
    ap.acquire(cache_root=cache, artifact_class="analysis", direct=loaded_direct,
               top_per_arm=25, sources=("uniprot", "chembl"),
               chembl_release="CHEMBL_37",
               transport=FXP.FakeTransport(no_match_uniprot=True))

    path = os.path.join(cache, acquisition.MANIFEST_FILE)
    manifest = json.loads(open(path).read())

    # Rewrite the IL2RA mechanism page so its action is an ACTIVATION.
    entry = next(e for e in manifest["entries"]
                 if e["adapter"] == "chembl_mechanism"
                 and (e.get("request_context") or {}).get("target_chembl_id")
                 == IL2RA_TARGET)
    raw = os.path.join(cache, entry["raw_file"])
    body = json.loads(open(raw).read())
    assert body["mechanisms"], "the pinned IL2RA page must carry mechanisms"
    for mech in body["mechanisms"]:
        mech["action_type"] = action
    data = json.dumps(body, sort_keys=True).encode()
    open(raw, "wb").write(data)
    entry["raw_sha256"] = hashlib.sha256(data).hexdigest()
    entry["raw_bytes"] = len(data)
    entry["pagination"]["observed_count"] = len(body["mechanisms"])
    # Reseal the manifest's own content hash so the cache is INTERNALLY honest and
    # genuinely passes the offline acquisition verifier. The point of this fixture is to
    # exercise the inverse-direction contract — not to smuggle a broken cache past the
    # gate, which is separately tested and must fail.
    from druglink.acq_manifest import content_sha256
    manifest.pop("content_sha256", None)
    manifest["content_sha256"] = content_sha256(manifest)
    with open(path, "w") as fh:
        fh.write(json.dumps(manifest, indent=2, sort_keys=True))
    return cache


@pytest.fixture(scope="module")
def inverse_build(tmp_path_factory, loaded_direct):
    tmp_path = tmp_path_factory.mktemp("inverse")
    cache = _agonist_cache(tmp_path, loaded_direct)
    # The gate runs for real: a bundle can only be built on a cache that passed
    # independent offline verification.
    acquired = acquisition.load_manifest(cache, "analysis", direct=loaded_direct)
    build = run_stage3.build(artifact_class="analysis", direct=loaded_direct,
                             acquired=acquired)
    return {"cache": cache, "build": build, "tmp_path": tmp_path}


# --------------------------------------------------------------------------- #
# End to end.
# --------------------------------------------------------------------------- #
def test_end_to_end_emits_a_distinct_inverse_direction_hypothesis(inverse_build):
    build = inverse_build["build"]
    edges = [e for e in build["tables"]["target_drug_edges"]
             if e["target_ensembl"] == IL2RA and e["desired_arm"] == "toward_B"
             and e["lane"] == "direct_gene_mechanism"]
    assert edges, "IL2RA/toward_B must carry direct-gene edges"

    inverse = [e for e in edges
               if e["directional_evidence_status"]
               == wf.INVERSE_DIRECTION_HYPOTHESIS]
    assert inverse, "an activation on the undesired-direction arm must be an INVERSE " \
                    "DIRECTION HYPOTHESIS"

    for edge in inverse:
        # Distinct: not unresolved, not observed.
        assert edge["directional_evidence_status"] != wf.UNRESOLVED
        assert edge["directional_evidence_status"] != wf.OBSERVED_PERTURBATION
        assert edge["directional_evidence_reason"] == wf.REASON_INVERSE_ACTIVATION
        # Never observed gain of function.
        assert edge["observed_perturbation_support"] is False
        # Never a measurement's evidence class.
        assert edge["stage3_evidence_class"] == wf.CLASS_INVERSE
        assert edge["stage3_evidence_class"] != wf.CLASS_MEASURED
        # It is a REAL activation on the arm that wanted an increase.
        assert edge["intervention_effect"] == "functional_activation"
        assert edge["arm_desired_target_modulation"] == "increase"
        assert edge["origin_type"] == ORIGIN_DIRECT_TARGET
        # The exact supporting arm and mechanism are preserved.
        assert edge["desired_arm"] == "toward_B"
        assert edge["action_type_sources"]
        assert edge["assertion_ids"]

    # The arm's counts report it separately from everything else.
    per_arm = build["counts"]["per_arm"]["toward_B"][ORIGIN_DIRECT_TARGET]
    assert per_arm["n_inverse_direction_hypothesis"] > 0
    assert per_arm["n_observed_perturbation"] == 0


def test_the_candidate_is_mapped_and_queued_with_the_right_reason(inverse_build):
    build = inverse_build["build"]

    cand = next(c for c in build["tables"]["candidates"]
                if "toward_B" in c["inverse_direction_hypothesis_arms"])

    # drug_mapping_status = mapped
    mapping = [m for m in build["tables"]["drug_mapping"]
               if m["target_ensembl"] == IL2RA and m["desired_arm"] == "toward_B"]
    assert mapping and mapping[0]["drug_mapping_status"] == wf.MAPPED

    # stage4_assessment_status = queued, reason = mapped_inverse_direction_hypothesis
    assert cand["stage4_assessment_status"] == wf.QUEUED
    assert cand["stage4_assessment_reason"] == "mapped_inverse_direction_hypothesis"
    assert cand["stage4_assessment_reason"] == wf.REASON_QUEUED_INVERSE

    # NOT observed support, and NOT a measurement's evidence class.
    assert "toward_B" not in cand["observed_perturbation_arms"]
    assert wf.CLASS_INVERSE in cand["stage3_evidence_classes"]

    # Claude Science reviews plausibility LATER.
    assert cand["disease_context_review_status"] == science_review.PENDING
    assert build["counts"]["disease_context_review"]["pending"] > 0

    # The exact supporting arm + mechanism are preserved on the candidate.
    support = cand["inverse_direction_support"]
    assert support
    for row in support:
        assert row["desired_arm"] == "toward_B"
        assert row["target_ensembl"] == IL2RA
        assert row["intervention_effect"] == "functional_activation"
        assert row["action_type_sources"] and row["assertion_ids"]


def test_it_does_not_alter_direct_ranks_or_pareto_tiers(inverse_build, loaded_direct):
    """Direct's ranks and tiers are upstream facts. The hypothesis changes none."""
    import pandas as pd

    build = inverse_build["build"]
    screen = loaded_direct.screen
    row = next(r for r in screen.to_dict("records") if r["target_id"] == IL2RA)

    edges = [e for e in build["tables"]["target_drug_edges"]
             if e["target_ensembl"] == IL2RA and e["desired_arm"] == "toward_B"
             and e["directional_evidence_status"]
             == wf.INVERSE_DIRECTION_HYPOTHESIS]
    want_rank = row["rank_toward_B"]
    for edge in edges:
        assert edge["arm_rank"] == (None if pd.isna(want_rank) else int(want_rank))
        assert edge["arm_evidence_tier"] == row["B_evidence_tier"]

    doc = build["document"]
    assert doc["stage3_never_alters_direct_ranks_or_stage2_pareto_tiers"] is True
    assert doc["evidence_classes_are_unordered"] is True
    assert doc["stage2_joint_context"]["rewritten_by_stage3"] is False


def test_no_activation_mechanism_means_no_inverse_hypothesis(analysis_build):
    """The REAL public sources report no activator — so none is invented."""
    edges = analysis_build["tables"]["target_drug_edges"]
    inverse = [e for e in edges
               if e["directional_evidence_status"]
               == wf.INVERSE_DIRECTION_HYPOTHESIS]
    assert inverse == [], "no activator is sourced, so no inverse hypothesis may exist"

    # IL2RA/toward_B has only inhibitors: they are OPPOSED, not converted.
    il2ra = [e for e in edges if e["target_ensembl"] == IL2RA
             and e["desired_arm"] == "toward_B"
             and e["lane"] == "direct_gene_mechanism"]
    assert il2ra
    assert all(e["directional_evidence_status"] in (wf.OPPOSED, wf.UNRESOLVED)
               for e in il2ra)

    # And nothing is queued on an inverse basis.
    for cand in analysis_build["tables"]["candidates"]:
        assert cand["inverse_direction_hypothesis_arms"] == []
        assert cand["stage4_assessment_reason"] != wf.REASON_QUEUED_INVERSE
        assert cand["disease_context_review_status"] == science_review.NOT_REQUIRED


# --------------------------------------------------------------------------- #
# Independent verifier reconstruction.
# --------------------------------------------------------------------------- #
def test_the_verifier_reconstructs_the_inverse_state_from_the_raw_bytes(
        inverse_build, direct_run):
    tmp_path = inverse_build["tmp_path"]
    build = inverse_build["build"]
    cache = inverse_build["cache"]

    bundle = artifacts.write_bundle(
        output_root=str(tmp_path / "out"), artifact_class="analysis",
        document=build["document"], doc_id=build["document_id"],
        tables=build["tables"], created_at="2026-07-12T00:00:00+00:00")

    rep = verify_stage3.verify(
        bundle=bundle, cache_root=cache, direct_run=direct_run["run_dir"],
        direct_inputs_root=direct_run["inputs_root"], artifact_class="analysis",
        direct_analysis=direct_run["analysis"])
    assert not rep.failures, rep.render()

    names = [n for n, _ok, _d in rep.checks]
    assert any("inverse-direction hypothesis is a REAL sourced activation" in n
               for n in names)
    assert any("PENDING a Claude Science disease-context review" in n for n in names)

    # The verifier's OWN restatement independently derives the same state from bytes.
    manifest = sources.load_cache(cache)
    pages = sources.read_pages(cache, manifest)["pages"]
    records = sources.reparse(pages)
    forms = rebuild.build_forms(records["molecule"])
    entities = rebuild.build_entities(records["target_entity"], records["gene_map"])
    edges = rebuild.build_edges(mechanisms=records["mechanism"], forms=forms,
                                entities=entities,
                                arm_levers=build["tables"]["arm_levers"])
    rebuilt = [e for e in edges
               if e["directional_evidence_status"]
               == policy.INVERSE_DIRECTION_HYPOTHESIS]
    assert rebuilt, "the verifier must re-derive the inverse state from the RAW bytes"
    for edge in rebuilt:
        assert edge["observed_perturbation_support"] is False
        assert edge["stage3_evidence_class"] == policy.CLASS_INVERSE


def test_promoting_an_inverse_hypothesis_to_observed_support_is_refused(
        inverse_build, direct_run):
    """Relabelling the hypothesis as a measurement is caught by reconstruction."""
    import hashlib

    import pandas as pd

    tmp_path = inverse_build["tmp_path"]
    build = inverse_build["build"]
    cache = inverse_build["cache"]

    bundle = artifacts.write_bundle(
        output_root=str(tmp_path / "out2"), artifact_class="analysis",
        document=build["document"], doc_id=build["document_id"],
        tables=build["tables"], created_at="2026-07-12T00:00:00+00:00")
    attacked = str(tmp_path / "attacked")
    shutil.copytree(bundle, attacked)

    path = os.path.join(attacked, "target_drug_edges.parquet")
    edges = pd.read_parquet(path)
    idx = edges.index[edges["directional_evidence_status"]
                      == wf.INVERSE_DIRECTION_HYPOTHESIS]
    assert len(idx)
    edges.loc[idx[0], "directional_evidence_status"] = wf.OBSERVED_PERTURBATION
    edges.loc[idx[0], "observed_perturbation_support"] = True
    edges.loc[idx[0], "stage3_evidence_class"] = wf.CLASS_MEASURED
    edges.to_parquet(path, index=False)

    mpath = os.path.join(attacked, "manifest.json")
    manifest = json.loads(open(mpath).read())
    for entry in manifest["files"]:
        if entry["file"] == "target_drug_edges.parquet":
            entry["file_sha256"] = hashlib.sha256(open(path, "rb").read()).hexdigest()
    with open(mpath, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)

    rep = verify_stage3.verify(
        bundle=attacked, cache_root=cache, direct_run=direct_run["run_dir"],
        direct_inputs_root=direct_run["inputs_root"], artifact_class="analysis",
        direct_analysis=direct_run["analysis"])
    assert rep.failures
    names = " ".join(n for n, _d in rep.failures)
    assert "re-derives" in names or "evidence class" in names


# --------------------------------------------------------------------------- #
# The retired vocabulary stays retired.
# --------------------------------------------------------------------------- #
def test_the_inverse_state_introduces_no_retired_field(inverse_build):
    build = inverse_build["build"]

    ac.check_no_retired_keys(build["document"])
    assert ac.retired_keys_in(build["document"]) == []

    for cand in build["tables"]["candidates"]:
        assert ac.retired_keys_in(cand) == []
        # Queuing an inverse hypothesis confers NO promotion. There is no field for one.
        assert "production_candidate" not in cand
        assert "production_promotion_eligible" not in cand
        assert "research_pk_annotation_eligible" not in cand

    for edge in build["tables"]["target_drug_edges"]:
        assert ac.retired_keys_in(edge) == []

    # A Stage-4 assessment is not promotion and not a recommendation — including here.
    note = build["document"]["stage4_assessment_note"]
    assert "not biological promotion" in note and "not a recommendation" in note
