"""Eligibility evidence: replay the verdict, and survive a RESEAL.

The compact cache cannot prove its accepted mappings — the producer applies the six identity
predicates and then discards the fields it applied them to. An "accepted" that nobody can
falsify is not evidence of eligibility; it is a promise about a computation nobody kept the
inputs to.

The resealed attacks below are the point of the whole module. Each one mutates an ACCEPTED
record and **recomputes the content hash**, so the artifact is perfectly, internally
consistent and hashes clean. The hash check passes. Only the REPLAY catches it — because the
contradiction is between a record's own inputs and its own verdict, and no amount of
rehashing can remove that. The only way to hide a mutated taxon is to also flip the verdict
to `rejected`, which is exactly the honest outcome.
"""
from __future__ import annotations

import pytest

from verifier import cache_identity as ci
from verifier import eligibility_evidence as ee
from verifier.report import Report

STORE_ID = "store_abc123"
QUERY_SHA = "q" * 64
SOURCE_SHA = "33c203740555f96067710cdfc1c3c55d890660e5908ec5cbf5817492c290d281"
CODE_SHA = "c" * 64


def _failed(rep):
    return [n for n, ok, _ in rep.checks if not ok]


def _accepted(**over):
    r = {"target_chembl_id": "CHEMBL1778", "accession": "P16410",
         "target_type": "SINGLE PROTEIN", "tax_id": 9606, "species_group_flag": 0,
         "component_type": "PROTEIN", "component_tax_id": 9606, "homologue": 0,
         "n_components_total": 1, "n_components_eligible": 1,
         "verdict": ee.ACCEPTED, "rejection_reason": None}
    r.update(over)
    return r


def _rejected(**over):
    r = _accepted(target_chembl_id="CHEMBL_MOUSE", accession="P_MOUSE", tax_id=10090,
                  verdict=ee.REJECTED, rejection_reason=ci.DISP_NON_HUMAN_TARGET)
    r.update(over)
    return r


def _evidence(records=None, **over):
    records = records if records is not None else [_accepted(), _rejected()]
    ev = {"schema_version": ee.EVIDENCE_SCHEMA, "store_id": STORE_ID,
          "query_sha256": QUERY_SHA, "chembl_release": "CHEMBL_37",
          "source_sha256": SOURCE_SHA, "extractor_code_sha256": CODE_SHA,
          "records": records,
          "content_sha256": ee.canonical_content_sha256(records)}
    ev.update(over)
    return ev


MANIFEST = {"store_id": STORE_ID, "query_sha256": QUERY_SHA,
            "chembl_release": "CHEMBL_37", "source_sha256": SOURCE_SHA,
            "extractor_code_sha256": CODE_SHA}


def _verify(evidence, accessions=None, targets=None):
    rep = Report()
    ee.verify(rep, evidence=evidence, manifest=MANIFEST,
              store_accessions=accessions if accessions is not None
              else {"P16410", "P_MOUSE"},
              store_targets=targets if targets is not None
              else {"CHEMBL1778", "CHEMBL_MOUSE"})
    return rep


# --------------------------------------------------------------------------- #
# The honest artifact.
# --------------------------------------------------------------------------- #
def test_a_complete_honest_evidence_artifact_is_admitted():
    assert not _failed(_verify(_evidence()))


def test_no_evidence_means_NO_ADMISSION():
    rep = _verify(None)
    assert any("sanitized target_eligibility_evidence" in n for n in _failed(rep))


# --------------------------------------------------------------------------- #
# THE RESEALED ATTACKS. Hash clean, replay catches them.
# --------------------------------------------------------------------------- #
RESEAL_MUTATIONS = [
    pytest.param({"tax_id": 10090}, ci.DISP_NON_HUMAN_TARGET, id="mouse_taxon"),
    pytest.param({"component_type": "NUCLEIC ACID"}, ci.DISP_NON_PROTEIN_COMPONENT,
                 id="non_protein_component"),
    pytest.param({"component_tax_id": 10090}, ci.DISP_NON_HUMAN_COMPONENT,
                 id="mouse_component"),
    pytest.param({"homologue": 1}, ci.DISP_HOMOLOGUE, id="homologue_flag"),
    pytest.param({"homologue": 2}, ci.DISP_HOMOLOGUE, id="species_group_representative"),
    pytest.param({"species_group_flag": 1}, ci.DISP_SPECIES_GROUP, id="species_group"),
    pytest.param({"n_components_total": 3}, ci.DISP_COMPONENT_CARDINALITY,
                 id="cardinality_total"),
    pytest.param({"n_components_eligible": 0}, ci.DISP_COMPONENT_CARDINALITY,
                 id="cardinality_eligible"),
    pytest.param({"target_type": "PROTEIN COMPLEX"}, ci.DISP_NOT_SINGLE_PROTEIN,
                 id="not_single_protein"),
]


@pytest.mark.parametrize("mutation,expected_reason", RESEAL_MUTATIONS)
def test_a_RESEALED_mutation_of_an_accepted_record_is_caught_by_the_REPLAY(
        mutation, expected_reason):
    """Mutate an accepted record, recompute the content hash, ship it. Perfectly consistent
    bytes that say the wrong thing — and the replay contradicts the verdict anyway."""
    records = [_accepted(**mutation), _rejected()]
    resealed = _evidence(records=records)          # content_sha256 RECOMPUTED

    rep = _verify(resealed)
    failed = _failed(rep)

    # the hash is clean — the reseal worked
    assert not any("content_sha256 recomputes" in n for n in failed), (
        "the attacker resealed correctly; the hash must NOT be what catches this")
    # ...and the replay still catches it
    assert any("REPLAYS from its own predicate inputs" in n for n in failed)

    derived, reason = ee.replay(records[0])
    assert derived == ee.REJECTED
    assert reason == expected_reason


def test_the_replay_failure_NAMES_the_contradiction():
    resealed = _evidence(records=[_accepted(tax_id=10090), _rejected()])
    rep = _verify(resealed)
    detail = next(d for n, ok, d in rep.checks if not ok and "REPLAYS" in n)
    assert "producer says 'accepted', replay says 'rejected'" in detail
    assert ci.DISP_NON_HUMAN_TARGET in detail


def test_the_ONLY_way_to_hide_a_mutation_is_to_tell_the_truth():
    """Flip the verdict to rejected as well, and it passes — because that is honest."""
    honest = _evidence(records=[
        _accepted(tax_id=10090, verdict=ee.REJECTED,
                  rejection_reason=ci.DISP_NON_HUMAN_TARGET),
        _rejected()])
    assert not _failed(_verify(honest))


# --------------------------------------------------------------------------- #
# The hash still catches a LAZY tamper (one who forgot to reseal).
# --------------------------------------------------------------------------- #
def test_an_UNSEALED_mutation_is_caught_by_the_content_hash():
    ev = _evidence()
    ev["records"][0]["tax_id"] = 10090          # mutate AFTER hashing
    rep = _verify(ev)
    failed = _failed(rep)
    assert any("content_sha256 recomputes" in n for n in failed)
    assert any("REPLAYS" in n for n in failed)      # ...and the replay, too


def test_both_defences_ship_because_they_catch_different_attackers():
    """Hash: the bytes are the ones that were judged. Replay: the judgement was right."""
    ev = _evidence()
    assert ee.canonical_content_sha256(ev["records"]) == ev["content_sha256"]
    for r in ev["records"]:
        assert ee.replay(r)[0] == r["verdict"]


# --------------------------------------------------------------------------- #
# Coverage — accepted AND rejected.
# --------------------------------------------------------------------------- #
def test_an_uncovered_store_accession_is_refused():
    rep = _verify(_evidence(), accessions={"P16410", "P_MOUSE", "P_UNCOVERED"})
    assert any("every accession in the store" in n for n in _failed(rep))


def test_an_uncovered_store_target_is_refused():
    rep = _verify(_evidence(), targets={"CHEMBL1778", "CHEMBL_MOUSE", "CHEMBL_GHOST"})
    assert any("every ChEMBL target in the store" in n for n in _failed(rep))


def test_a_producer_that_DROPPED_its_rejections_is_refused():
    """'No rejections' from a store holding mouse targets is a missing gate, not a clean
    bill of health."""
    rep = _verify(_evidence(records=[_accepted()]),
                  accessions={"P16410"}, targets={"CHEMBL1778"})
    assert any("covers REJECTED mappings too" in n for n in _failed(rep))


def test_a_rejection_must_NAME_a_known_disposition():
    rep = _verify(_evidence(records=[
        _accepted(), _rejected(rejection_reason="because")]))
    assert any("names a known disposition" in n for n in _failed(rep))


def test_an_unknown_verdict_is_refused():
    rep = _verify(_evidence(records=[_accepted(verdict="probably"), _rejected()]))
    assert any("exactly 'accepted' or 'rejected'" in n for n in _failed(rep))


# --------------------------------------------------------------------------- #
# Bindings + sanitization.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field", ["store_id", "query_sha256", "chembl_release",
                                   "source_sha256", "extractor_code_sha256"])
def test_evidence_bound_to_a_DIFFERENT_store_or_extraction_is_refused(field):
    rep = _verify(_evidence(**{field: "other"}))
    assert any("SAME" in n for n in _failed(rep))


@pytest.mark.parametrize("binding", ee.REQUIRED_BINDINGS)
def test_a_missing_binding_is_refused(binding):
    ev = _evidence()
    ev[binding] = None
    rep = _verify(ev)
    assert _failed(rep)


def test_a_local_path_in_the_evidence_is_refused():
    rep = _verify(_evidence(
        extraction_note="/home/tcelab/.cache/spot-stage3-universe/chembl_37.db"))
    assert any("machine-local path" in n for n in _failed(rep))


def test_the_replay_uses_the_SAME_constants_as_the_identity_gate():
    """The two must not drift apart: one gate, two call sites."""
    assert ci.HUMAN_TAX_ID == 9606
    assert ci.HOMOLOGUE_EXACT == 0
    assert ci.SINGLE_PROTEIN == "SINGLE PROTEIN"
    assert ci.COMPONENT_PROTEIN == "PROTEIN"


def test_a_record_missing_a_predicate_input_replays_as_rejected():
    """A cache too coarse to prove eligibility is not eligible."""
    thin = _accepted()
    del thin["homologue"]
    derived, reason = ee.replay(thin)
    assert derived == ee.REJECTED and ci.DISP_CACHE_TOO_COARSE in reason
