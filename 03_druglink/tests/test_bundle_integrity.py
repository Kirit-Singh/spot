"""End-to-end integrity of the SERIALIZED bundle, plus input-variation attacks.

The other suites test the engine in memory. This one tests what actually lands on
disk — the parquet rows a consumer (and Stage 4) will really read — and then attacks
it: mutate a row, reseal a hash, permute the input, and confirm the INDEPENDENT
verifier refuses or reproduces exactly as the contract requires.
"""
from __future__ import annotations

import json
import os
import shutil

import pandas as pd
import pytest

from druglink import artifacts, run_stage3
from druglink.armlever import ARMS, BANNED_OBJECTIVE_COLUMNS
from verifier import verify_stage3


def _write(tmp_path, build, name="out"):
    return artifacts.write_bundle(
        output_root=str(tmp_path / name), artifact_class="analysis",
        document=build["document"], doc_id=build["document_id"],
        tables=build["tables"], created_at="2026-07-12T00:00:00+00:00")


def _verify(bundle, direct_run, cache_root):
    return verify_stage3.verify(
        bundle=bundle, cache_root=cache_root, direct_run=direct_run["run_dir"],
        direct_inputs_root=direct_run["inputs_root"], artifact_class="analysis",
        direct_analysis=direct_run["analysis"])


# --------------------------------------------------------------------------- #
# The independent verifier passes on an honest bundle.
# --------------------------------------------------------------------------- #
def test_independent_verifier_passes_on_the_emitted_bundle(tmp_path, analysis_build,
                                                           direct_run, analysis_cache):
    bundle = _write(tmp_path, analysis_build)
    rep = _verify(bundle, direct_run, analysis_cache)

    assert not rep.failures, rep.render()
    assert len(rep.checks) >= 30, "the verifier must actually check something"

    # It really did re-run Direct's own standalone verifier, from source.
    names = [n for n, _ok, _d in rep.checks]
    assert any("standalone verifier RECONSTRUCTS" in n for n in names)
    assert any("Direct file hashes to what the bundle bound" in n for n in names)


# --------------------------------------------------------------------------- #
# Two arms survive SERIALIZATION.
# --------------------------------------------------------------------------- #
def test_serialized_rows_keep_both_arms_with_separate_nullable_ranks(tmp_path,
                                                                     analysis_build):
    bundle = _write(tmp_path, analysis_build)

    levers = pd.read_parquet(os.path.join(bundle, "arm_levers.parquet"))
    assert set(levers["desired_arm"]) == set(ARMS)

    # The nullable rank survives the round trip as NULL, never as a float NaN: a
    # consumer that calls int() on NaN crashes, one that coerces it invents a rank.
    assert str(levers["arm_rank"].dtype) == "Int64"
    assert levers["arm_rank"].isna().any(), "some arms are legitimately unranked"

    # Each arm has its OWN rank population; they are not one ranking wearing two names.
    per_arm = {arm: levers[levers["desired_arm"] == arm] for arm in ARMS}
    for arm, rows in per_arm.items():
        ranked = rows["arm_rank"].dropna()
        assert sorted(ranked.tolist()) == list(range(1, len(ranked) + 1)), (
            f"{arm} ranks must be a contiguous 1..n over ITS OWN population")

    # A conflict row really does carry opposite desired modulations, on disk.
    by_target = levers.set_index(["target_id", "desired_arm"])
    conflicts = [t for t in levers["target_id"].unique()
                 if {by_target.loc[(t, "away_from_A"), "arm_desired_target_modulation"],
                     by_target.loc[(t, "toward_B"), "arm_desired_target_modulation"]}
                 == {"decrease", "increase"}]
    assert conflicts, "the serialized rows must preserve a cross-arm conflict"

    # Edges, summaries and candidates all keep the arm.
    edges = pd.read_parquet(os.path.join(bundle, "target_drug_edges.parquet"))
    summaries = pd.read_parquet(
        os.path.join(bundle, "candidate_arm_summaries.parquet"))
    assert set(edges["desired_arm"]) <= set(ARMS)
    assert set(summaries["desired_arm"]) <= set(ARMS)

    # The same moiety+target is present on BOTH arms with DIFFERENT translations.
    pivot = edges.groupby(["active_moiety_id", "target_ensembl"])["desired_arm"].nunique()
    assert (pivot > 1).any(), "a drug must keep an edge on each arm independently"
    split = edges.groupby(["active_moiety_id", "target_ensembl"])[
        "directional_evidence_status"].nunique()
    assert (split > 1).any(), (
        "a drug's evidence status must be allowed to DIFFER between the two arms")


def test_no_combined_objective_column_in_any_serialized_table(tmp_path,
                                                              analysis_build):
    bundle = _write(tmp_path, analysis_build)

    for name in sorted(os.listdir(bundle)):
        if not name.endswith(".parquet"):
            continue
        cols = set(pd.read_parquet(os.path.join(bundle, name)).columns)
        banned = BANNED_OBJECTIVE_COLUMNS.intersection(cols)
        assert not banned, f"{name} carries a combined/headline objective: {banned}"

    doc = json.loads(open(os.path.join(bundle, "drug_annotation.json")).read())
    assert doc["combined_objective_permitted"] is False
    assert doc["headline_arm_permitted"] is False
    assert doc["arms_are_independent"] is True
    assert doc["desired_arms"] == list(ARMS)


def test_emitted_artifacts_leak_no_machine_local_path(tmp_path, analysis_build):
    bundle = _write(tmp_path, analysis_build)
    for name in ("drug_annotation.json", "manifest.json"):
        text = open(os.path.join(bundle, name)).read()
        for leak in ("/home/", "/Users/", "/mnt/", "/tmp/", "/private/var/"):
            assert leak not in text, f"{name} leaks a machine-local path: {leak}"


# --------------------------------------------------------------------------- #
# Input variation: permutation reproduces, mutation is refused.
# --------------------------------------------------------------------------- #
def test_permuted_direct_rows_reproduce_the_same_bundle_id(loaded_direct,
                                                           analysis_build,
                                                           analysis_cache):
    import copy

    from druglink import acquisition

    permuted = copy.copy(loaded_direct)
    object.__setattr__(permuted, "screen",
                       loaded_direct.screen.iloc[::-1].reset_index(drop=True))

    acquired = acquisition.load_manifest(analysis_cache, "analysis",
                                         direct=loaded_direct)
    again = run_stage3.build(artifact_class="analysis", direct=permuted,
                             acquired=acquired)

    assert again["document_id"] == analysis_build["document_id"]
    assert (again["document"]["canonical_content_sha256"]
            == analysis_build["document"]["canonical_content_sha256"])
    assert (again["document"]["table_hashes"]
            == analysis_build["document"]["table_hashes"])


def test_mutated_parquet_row_is_refused_by_the_verifier(tmp_path, analysis_build,
                                                        direct_run, analysis_cache):
    bundle = _write(tmp_path, analysis_build)
    attacked = str(tmp_path / "attacked")
    shutil.copytree(bundle, attacked)

    # Promote an OPPOSED edge (a real antagonist on the arm that wants an INCREASE)
    # into observed loss-of-function support, and reseal the manifest's file digest so
    # the bundle agrees with itself.
    path = os.path.join(attacked, "target_drug_edges.parquet")
    edges = pd.read_parquet(path)
    idx = edges.index[edges["directional_evidence_status"] == "opposed"]
    assert len(idx), "the run must contain an opposed edge to attack"
    edges.loc[idx[0], "directional_evidence_status"] = "observed_perturbation"
    edges.loc[idx[0], "observed_perturbation_support"] = True
    edges.to_parquet(path, index=False)

    import hashlib
    mpath = os.path.join(attacked, "manifest.json")
    manifest = json.loads(open(mpath).read())
    for entry in manifest["files"]:
        if entry["file"] == "target_drug_edges.parquet":
            entry["file_sha256"] = hashlib.sha256(open(path, "rb").read()).hexdigest()
    with open(mpath, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)

    rep = _verify(attacked, direct_run, analysis_cache)
    assert rep.failures, "a resealed row mutation must still be refused"
    names = " ".join(n for n, _d in rep.failures)
    # It is caught by RECONSTRUCTION from the raw source bytes, not by a self-hash.
    assert "re-derives" in names or "raw bytes" in names


def test_mutated_upstream_hash_is_refused_by_the_verifier(tmp_path, analysis_build,
                                                          direct_run, analysis_cache):
    bundle = _write(tmp_path, analysis_build)
    attacked = str(tmp_path / "attacked_upstream")
    shutil.copytree(bundle, attacked)

    dpath = os.path.join(attacked, "drug_annotation.json")
    doc = json.loads(open(dpath).read())
    # Repoint the bundle at a Direct file hash it did not consume.
    doc["upstream"]["direct_file_sha256"]["screen.parquet"] = "0" * 64
    with open(dpath, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)

    rep = _verify(attacked, direct_run, analysis_cache)
    assert rep.failures
    names = " ".join(n for n, _d in rep.failures)
    assert "Direct file hashes to what the bundle bound" in names


def test_a_retired_promotion_field_is_refused_by_the_verifier(tmp_path, analysis_build,
                                                              direct_run,
                                                              analysis_cache):
    """Smuggling the retired promotion vocabulary back in is caught by the verifier."""
    bundle = _write(tmp_path, analysis_build)
    attacked = str(tmp_path / "attacked_promo")
    shutil.copytree(bundle, attacked)

    dpath = os.path.join(attacked, "drug_annotation.json")
    doc = json.loads(open(dpath).read())
    doc["production_promotion_eligible"] = True
    doc["production_pointer_written"] = True
    with open(dpath, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)

    rep = _verify(attacked, direct_run, analysis_cache)
    assert rep.failures
    names = " ".join(n for n, _d in rep.failures)
    assert "retired promotion/eligibility field" in names


def test_rewriting_the_bundle_is_idempotent_but_never_silently_overwritten(
        tmp_path, analysis_build):
    first = _write(tmp_path, analysis_build)
    again = _write(tmp_path, analysis_build)          # identical content: accepted
    assert first == again

    # A DIFFERENT bundle claiming the same ID is refused rather than overwritten.
    tampered = dict(analysis_build["document"])
    tampered["inference_status"] = "calibrated"
    with pytest.raises(artifacts.ArtifactError, match="different content"):
        artifacts.write_bundle(
            output_root=str(tmp_path / "out"), artifact_class="analysis",
            document=tampered, doc_id=analysis_build["document_id"],
            tables=analysis_build["tables"],
            created_at="2026-07-12T00:00:00+00:00")
