"""Stage-3 test fixtures.

The end-to-end research path is driven by REAL artifacts on both sides:

  * the Direct run is built by Direct's ACTUAL screen and admitted only after Direct's
    OWN standalone verifier reconstructs it from source (no mock, no hand-authored
    Direct document);
  * the acquisition cache is a REAL on-disk cache of REAL pinned public response bytes
    (UniProt 2026_02 + ChEMBL_37), written by the real ``acquire_public`` through a
    transport that serves those pinned bytes and refuses any unpinned URL.

So the engine, the acquisition loader and the independent verifier all run over the
same evidence a real run would see. The perturbation biology is synthetic and the
compounds are whatever the public sources genuinely report — **nothing here is a
scientific finding.**
"""
from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "analysis")))
sys.path.insert(0, _HERE)

import direct_fixture  # noqa: E402
import universe_store_fixture as USF  # noqa: E402
from selection_world import world  # noqa: E402,F401  (the ONE sealed selection-view store)
from stage2_release_fixture import build_release  # noqa: E402


@pytest.fixture(scope="session")
def analysis_root():
    """The importable ``analysis/`` root, for tests that spawn a CLEAN interpreter."""
    return os.path.abspath(os.path.join(_HERE, "..", "analysis"))


@pytest.fixture(scope="session")
def store():
    """The REAL admitted universe store, opened through the GATED path. Never synthesised.

    Shared by the two halves of the store's contract — ``test_universe_rows`` (target
    identity) and ``test_universe_edges`` (assertion lanes) — so the store is proved from its
    own bytes ONCE. If it is not on this host the tests skip: they never fall back to a
    fixture and report a pass over zero rows.
    """
    from druglink import universe_rows as ur
    if USF.STORE_DIR is None:
        pytest.skip("no admitted universe store on this host")
    return ur.load_store(USF.STORE_DIR)


@pytest.fixture(scope="session")
def all_edges(store):
    """Every source drug assertion the store holds, joined by exact typed identity."""
    from druglink import universe_rows as ur
    edges = ur.drug_edges_for_targets(
        store, [{"target_id": r["target_id"],
                 "target_id_namespace": r["target_id_namespace"]}
                for r in store.typed_universe])
    assert edges, "non-vacuity: the real store must produce edges"
    return edges


@pytest.fixture(scope="session")
def direct_run(tmp_path_factory):
    """A real Direct research_only run: rq_ ids, production_gate_passed=false.

    Two targets carry REAL Ensembl ids (CTLA4, IL2RA) so the pinned real public
    responses answer this run. IL2RA is the cross-arm conflict row.
    """
    dest = str(tmp_path_factory.mktemp("direct_rq"))
    built = direct_fixture.build_direct_run(dest, lane="research_only")
    os.environ.setdefault("SPOT_DIRECT_ANALYSIS", built["analysis"])
    return built


# --------------------------------------------------------------------------- #
# UPSTREAM BLOCKER, recorded honestly rather than worked around.
#
# Direct's STANDALONE verifier (`python -m direct.verify_run`) currently CRASHES:
#
#     NameError: name 'SOURCE_CLASSIFICATION_RULE_ID' is not defined
#     02_geneskew/analysis/direct/verify_source.py:412
#
# The constant is defined in verify_classification.py / manifest_schema.py but is not
# imported into verify_source.py. Direct's own suite is green because it never invokes
# verify_run as a subprocess, so the defect is invisible from inside Stage 2.
#
# Stage 3's admission contract IS "Direct's standalone verifier reconstructed this run",
# and a crash IS a verification failure — so the loader refuses, correctly and by
# design. We do NOT add a compatibility exception, we do NOT fall back to an older
# artifact, and we do NOT mock Direct. Every test that needs an admitted Direct run
# SKIPS with this exact reason until Stage 2 fixes the import. Stage 3 owns no part of
# this defect and must not edit Stage 2 to fix it.
# --------------------------------------------------------------------------- #
UPSTREAM_VERIFIER_DEFECT = (
    "BLOCKED ON STAGE 2: Direct's standalone verifier crashes with "
    "NameError: SOURCE_CLASSIFICATION_RULE_ID is not defined "
    "(02_geneskew/analysis/direct/verify_source.py:412 — the constant is defined in "
    "verify_classification.py/manifest_schema.py but never imported there). A crash is "
    "a verification failure, so the Stage-3 loader refuses the run, correctly. Stage 3 "
    "will not mock Direct, will not add a compatibility exception, and will not edit "
    "Stage 2. These tests run again the moment that import is fixed."
)


@pytest.fixture(scope="session")
def loaded_direct(direct_run):
    """The Direct run, admitted by the Stage-3 loader (Direct's verifier ran)."""
    from druglink import direct_run as dr
    try:
        return dr.load(direct_run["run_dir"], direct_run["inputs_root"],
                       artifact_class="analysis",
                       direct_analysis=direct_run["analysis"])
    except dr.DirectRunError as exc:
        if "NameError" in str(exc) or "SOURCE_CLASSIFICATION_RULE_ID" in str(exc):
            pytest.skip(UPSTREAM_VERIFIER_DEFECT)
        raise


@pytest.fixture(scope="session")
def arm_levers(loaded_direct):
    from druglink import armlever
    return armlever.expand(loaded_direct.screen,
                           direct_run_id=loaded_direct.run_id)


@pytest.fixture(scope="session")
def analysis_cache(tmp_path_factory, loaded_direct):
    """A REAL on-disk acquisition cache of REAL pinned public bytes.

    No socket is opened: the transport serves the pinned responses and raises on any
    URL it was not given. The bytes are genuinely UniProt/ChEMBL, so they are recorded
    honestly as ``acquired_public`` — no fixture is ever relabelled as public.
    """
    import fixture_public_responses as FX
    from druglink import acquire_public as ap

    cache = str(tmp_path_factory.mktemp("stage3_cache"))
    ap.acquire(cache_root=cache, artifact_class="analysis", direct=loaded_direct,
               top_per_arm=25, sources=("uniprot", "chembl"),
               chembl_release="CHEMBL_37",
               transport=FX.FakeTransport(no_match_uniprot=True))
    return cache


@pytest.fixture(scope="session")
def analysis_build(loaded_direct, analysis_cache):
    """A full Stage-3 engine build over the real cache, through the real loader.

    This exercises the acquisition-verification GATE: ``load_manifest`` refuses to
    return an unverified cache, so a build that reaches here has a bound, passing
    acquisition verification.
    """
    from druglink import acquisition, run_stage3

    acquired = acquisition.load_manifest(analysis_cache, "analysis",
                                         direct=loaded_direct)
    return run_stage3.build(artifact_class="analysis", direct=loaded_direct,
                            acquired=acquired)


# --- the REAL Stage-2 aggregate release, built by STAGE-2's OWN producer + verifier --- #
# Not a hand-written document: ``build_release`` drives direct.run_manifest.build and
# direct.verify_run_manifest.verify (see stage2_release_fixture). Stage-2's bundle SCORES are
# synthetic — no science is asserted — but the schema, the self-hash and the ADMISSION are
# real, so the shape cannot drift from the producer without these tests failing.
@pytest.fixture(scope="session")
def honest(tmp_path_factory):
    return build_release(tmp_path_factory.mktemp("s2_aggregate"))


@pytest.fixture(scope="session")
def admitted(honest):
    """The real release, admitted through Stage-2's own admission chain.

    ``artifact_class`` is STAGE-3's declaration about this run (Stage 2 declares none, and
    never did). It stays a fixture here, so the analysis path still refuses it.
    """
    from druglink import stage2_aggregate as sa
    return sa.admit_aggregate(**honest)


# --- the sealed NON-PRODUCTION Stage-3 v2 world (aggregate + store + emitted bundle) --- #
@pytest.fixture(scope="session")
def v2_world(tmp_path_factory):
    """Built ONCE: 15 bundles, 300 arm slots, a universe store, and a v2 bundle emitted
    from both. Every v2 attack breaks exactly one thing in a copy of these honest bytes."""
    from v2_world import build_world
    return build_world(str(tmp_path_factory.mktemp("v2_world")))
