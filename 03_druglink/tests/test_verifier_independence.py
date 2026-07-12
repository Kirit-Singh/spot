"""The independent verifier must re-derive the evidence, not re-read the claims.

These are the defects this suite locks shut:

  * the verifier accepted a ``--cache-root`` and never opened it, so a bundle's drug
    evidence was never checked against the bytes it supposedly came from;
  * it trusted ``mechanism_assertions.parquet`` instead of re-parsing the raw UniProt /
    ChEMBL responses, so a fabricated assertion would have passed;
  * it never rebuilt identity / mechanism / candidate tables;
  * a nonexistent cache was silently treated as an empty one;
  * generation would build a bundle on an acquisition nobody had verified.
"""
from __future__ import annotations

import json
import os
import shutil

import pytest

from druglink import acquisition, artifacts
from verifier import rebuild, sources, verify_stage3


def _write(tmp_path, build):
    return artifacts.write_bundle(
        output_root=str(tmp_path / "out"), artifact_class="analysis",
        document=build["document"], doc_id=build["document_id"],
        tables=build["tables"], created_at="2026-07-12T00:00:00+00:00")


def _verify(bundle, direct_run, cache_root):
    return verify_stage3.verify(
        bundle=bundle, cache_root=cache_root, direct_run=direct_run["run_dir"],
        direct_inputs_root=direct_run["inputs_root"], artifact_class="analysis",
        direct_analysis=direct_run["analysis"])


# --------------------------------------------------------------------------- #
# A cache that is not there is not an empty cache.
# --------------------------------------------------------------------------- #
def test_nonexistent_cache_is_rejected(tmp_path, analysis_build, direct_run):
    bundle = _write(tmp_path, analysis_build)

    for missing in (str(tmp_path / "no_such_cache"), "", None):
        rep = _verify(bundle, direct_run, missing)
        assert rep.failures, f"cache_root={missing!r} must be refused"
        names = " ".join(n for n, _d in rep.failures)
        assert "acquisition cache is present and readable" in names
        # And nothing downstream is allowed to silently "pass" on no evidence.
        assert "reconstruct" in names or "raw source bytes" in names

    # An empty directory is not a cache either.
    empty = tmp_path / "empty_cache"
    empty.mkdir()
    rep = _verify(bundle, direct_run, str(empty))
    assert rep.failures

    # Directly, too.
    with pytest.raises(sources.CacheError):
        sources.load_cache(str(tmp_path / "nope"))
    with pytest.raises(sources.CacheError):
        sources.load_cache(None)


# --------------------------------------------------------------------------- #
# The verifier reads and hashes the RAW bytes itself.
# --------------------------------------------------------------------------- #
def test_verifier_reads_and_hashes_the_raw_bytes(tmp_path, analysis_build,
                                                 direct_run, analysis_cache):
    bundle = _write(tmp_path, analysis_build)

    manifest = sources.load_cache(analysis_cache)
    read = sources.read_pages(analysis_cache, manifest)
    assert read["pages"], "the cache must contain acquired pages"
    assert not read["failures"]

    # It really parsed real public bytes, not the bundle's tables.
    records = sources.reparse(read["pages"])
    assert records["gene_map"], "UniProt bytes must yield gene mappings"
    assert records["mechanism"], "ChEMBL bytes must yield mechanisms"
    assert records["target_entity"] and records["molecule"]

    # A tampered cached page is caught by the verifier's own hashing.
    attacked_cache = str(tmp_path / "cache_attacked")
    shutil.copytree(analysis_cache, attacked_cache)
    entry = next(e for e in manifest["entries"]
                 if e.get("acquisition_status") == "acquired_public")
    victim = os.path.join(attacked_cache, entry["raw_file"])
    data = open(victim, "rb").read()
    open(victim, "wb").write(data.replace(b"{", b"{ ", 1))

    rep = _verify(bundle, direct_run, attacked_cache)
    assert rep.failures
    names = " ".join(n for n, _d in rep.failures)
    assert "RAW BYTES" in names


def test_a_fabricated_mechanism_assertion_is_caught(tmp_path, analysis_build,
                                                    direct_run, analysis_cache):
    """An assertion the raw bytes never stated must not survive verification."""
    import pandas as pd

    bundle = _write(tmp_path, analysis_build)
    attacked = str(tmp_path / "fabricated")
    shutil.copytree(bundle, attacked)

    path = os.path.join(attacked, "mechanism_assertions.parquet")
    frame = pd.read_parquet(path)
    forged = frame.iloc[[0]].copy()
    forged["assertion_id"] = "forged0000000000"
    forged["action_type_source"] = "AGONIST"        # never stated by the source
    forged["intervention_effect"] = "functional_activation"
    pd.concat([frame, forged], ignore_index=True).to_parquet(path, index=False)

    import hashlib
    mpath = os.path.join(attacked, "manifest.json")
    manifest = json.loads(open(mpath).read())
    for entry in manifest["files"]:
        if entry["file"] == "mechanism_assertions.parquet":
            entry["file_sha256"] = hashlib.sha256(open(path, "rb").read()).hexdigest()
    with open(mpath, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)

    rep = _verify(attacked, direct_run, analysis_cache)
    assert rep.failures
    names = " ".join(n for n, _d in rep.failures)
    assert "no mechanism assertion exists that the raw bytes do not state" in names


def test_tables_reconstruct_from_the_raw_bytes(analysis_build, analysis_cache,
                                               arm_levers):
    """Identity, edges and candidates all re-derive from the bytes independently."""
    manifest = sources.load_cache(analysis_cache)
    pages = sources.read_pages(analysis_cache, manifest)["pages"]
    records = sources.reparse(pages)

    forms = rebuild.build_forms(records["molecule"])
    entities = rebuild.build_entities(records["target_entity"], records["gene_map"])
    edges = rebuild.build_edges(mechanisms=records["mechanism"], forms=forms,
                                entities=entities,
                                arm_levers=arm_levers["arm_levers"])
    assert edges, "the raw bytes must imply real edges"

    # A PROTEIN COMPLEX is never turned into one of its component genes.
    complexes = [e for e in entities.values() if not e["is_single_protein"]]
    assert complexes, "the pinned bytes must contain a non-single-protein entity"
    for edge in edges:
        if edge["lane"] != "direct_gene_mechanism":
            assert edge["translation_class"] == "unknown"

    # The independently rebuilt edge set matches what the engine emitted.
    emitted = {(e["desired_arm"], e["target_ensembl"], e["form_id"],
                e["action_type_normalized"])
               for e in analysis_build["tables"]["target_drug_edges"]}
    rebuilt = {(e["desired_arm"], e["target_ensembl"], e["form_id"],
                e["action_type_normalized"]) for e in edges}
    assert emitted == rebuilt

    cands = rebuild.build_candidates(edges, forms)
    assert cands, "candidates must reconstruct from the bytes"


# --------------------------------------------------------------------------- #
# Generation may not stand on an unverified acquisition.
# --------------------------------------------------------------------------- #
def test_generation_requires_a_passing_acquisition_gate(tmp_path, loaded_direct,
                                                        analysis_cache):
    # The honest cache passes, and the verdict is BOUND into the bundle.
    acquired = acquisition.load_manifest(analysis_cache, "analysis",
                                         direct=loaded_direct)
    gate = acquired["acquisition_ref"]["verification"]
    assert gate["all_pass"] is True
    assert gate["n_checks"] > 0 and gate["n_failed"] == 0
    assert gate["report_sha256"]

    # Corrupt the cache: generation must REFUSE, not build on it.
    broken = str(tmp_path / "broken_cache")
    shutil.copytree(analysis_cache, broken)
    manifest = json.loads(
        open(os.path.join(broken, acquisition.MANIFEST_FILE)).read())
    entry = next(e for e in manifest["entries"]
                 if e.get("acquisition_status") == "acquired_public")
    os.remove(os.path.join(broken, entry["raw_file"]))

    with pytest.raises(acquisition.AcquisitionError, match="independent verification"):
        acquisition.load_manifest(broken, "analysis", direct=loaded_direct)


def test_bundle_carries_the_acquisition_gate_and_real_timestamps(analysis_build,
                                                                 analysis_cache):
    doc = analysis_build["document"]
    acq = doc["acquisition"]

    assert acq["verification"]["all_pass"] is True
    assert acq["acquisition_manifest_sha256"]

    # Real runs keep the moment each page was ACTUALLY retrieved.
    manifest = sources.load_cache(analysis_cache)
    assert not sources.retrieval_timestamps(manifest)
    stamps = [e["access_record"]["retrieved_at"] for e in manifest["entries"]
              if e.get("acquisition_status") == "acquired_public"]
    assert stamps and all(s.endswith("Z") for s in stamps)
    # ...and they are excluded from the acquisition IDENTITY, not from the record.
    assert "retrieved_at" not in json.dumps(acq)


def test_verifier_refuses_a_source_it_cannot_reparse():
    """Fail-closed: evidence from an adapter the verifier cannot re-derive is refused."""
    manifest = {"entries": [{
        "acquisition_status": "acquired_public", "adapter": "open_targets_known_drugs",
        "raw_file": "raw/x.json", "raw_sha256": "0" * 64, "raw_bytes": 2,
    }]}
    read = sources.read_pages("/nonexistent", manifest)
    assert read["failures"]
    assert "no independent re-parser" in read["failures"][0]
