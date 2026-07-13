"""Two corrections from the independent source audit.

1. **UniProt -> gene was last-write-wins.** Whichever record parsed last silently became
   the truth, so a drug target's identity depended on the ORDER the public pages arrived
   in. Reverse the pages, get a different answer, with nothing anywhere saying a choice was
   made. Now a conflicting accession is a NAMED REFUSAL.

2. **The target universe is not homogeneous ENSG.** It is 11,522 Ensembl + 4 symbol-only
   (MTRNR2L1/L4/L8, OCLM). The four cannot be reached by an Ensembl-cross-reference
   acquisition route — so they are RETAINED with an explicit `unsupported_namespace`
   disposition and the coverage denominators SPLIT, rather than being quietly dropped to
   make a coverage number look tidy.
"""
from __future__ import annotations

import pytest

from druglink import targets, universe

P16410, P01589 = "P16410", "P01589"
CTLA4, IL2RA = "ENSG00000163599", "ENSG00000134460"


def _gene_map(acc, gene, rid):
    return {"record_kind": "gene_map", "uniprot_id": acc, "target_ensembl": gene,
            "source_record_id": rid}


# --------------------------------------------------------------------------- #
# 1. Identity fails CLOSED on conflict. No tie-break, because none is honest.
# --------------------------------------------------------------------------- #
def test_a_uniprot_accession_mapping_to_two_genes_is_a_named_refusal():
    recs = [_gene_map(P16410, CTLA4, "r1"), _gene_map(P16410, IL2RA, "r2")]
    with pytest.raises(targets.TargetIdentityConflict, match="MORE THAN ONE gene"):
        targets.resolve_uniprot_to_gene(recs)


def test_the_refusal_NAMES_the_accession_the_genes_and_the_records():
    recs = [_gene_map(P16410, CTLA4, "r1"), _gene_map(P16410, IL2RA, "r2")]
    with pytest.raises(targets.TargetIdentityConflict) as exc:
        targets.resolve_uniprot_to_gene(recs)
    msg = str(exc.value)
    assert P16410 in msg and CTLA4 in msg and IL2RA in msg
    assert "r1" in msg and "r2" in msg


def test_ORDER_REVERSAL_cannot_change_the_answer():
    """The bug, stated as a test: under last-write-wins these two disagreed."""
    recs = [_gene_map(P16410, CTLA4, "r1"), _gene_map(P16410, IL2RA, "r2")]
    with pytest.raises(targets.TargetIdentityConflict):
        targets.resolve_uniprot_to_gene(recs)
    with pytest.raises(targets.TargetIdentityConflict):
        targets.resolve_uniprot_to_gene(list(reversed(recs)))


def test_a_clean_map_survives_order_reversal_byte_for_byte():
    recs = [_gene_map(P16410, CTLA4, "r1"), _gene_map(P01589, IL2RA, "r2")]
    assert targets.resolve_uniprot_to_gene(recs) \
        == targets.resolve_uniprot_to_gene(list(reversed(recs)))


def test_MULTIPLICITY_many_accessions_for_ONE_gene_is_fine():
    """Many-to-one is normal biology, not a conflict. Only one-to-many is."""
    recs = [_gene_map(P16410, CTLA4, "r1"), _gene_map("Q5W005", CTLA4, "r2"),
            _gene_map("H0Y5Z0", CTLA4, "r3")]
    got = targets.resolve_uniprot_to_gene(recs)
    assert got == {P16410: CTLA4, "Q5W005": CTLA4, "H0Y5Z0": CTLA4}


def test_a_repeated_IDENTICAL_mapping_is_not_a_conflict():
    recs = [_gene_map(P16410, CTLA4, "r1"), _gene_map(P16410, CTLA4, "r2")]
    assert targets.resolve_uniprot_to_gene(recs) == {P16410: CTLA4}


def test_build_itself_fails_closed_on_a_conflict():
    recs = [_gene_map(P16410, CTLA4, "r1"), _gene_map(P16410, IL2RA, "r2")]
    with pytest.raises(targets.TargetIdentityConflict):
        targets.build(recs)


# --------------------------------------------------------------------------- #
# 2. The universe is 11,522 ENSG + 4 symbol-only.
# --------------------------------------------------------------------------- #
def _lever(tid, ensembl=None, symbol=None):
    return {"target_id": tid, "target_ensembl": ensembl, "target_symbol": symbol}


LEVERS = [
    _lever(CTLA4, ensembl=CTLA4, symbol="CTLA4"),
    _lever(IL2RA, ensembl=IL2RA, symbol="IL2RA"),
    *[_lever(s, ensembl=None, symbol=s) for s in universe.SYMBOL_ONLY_TARGETS],
]


def test_the_audited_universe_is_not_homogeneous_ensembl():
    assert universe.N_ENSEMBL == 11_522
    assert universe.N_SYMBOL_ONLY == 4
    assert universe.N_UNIVERSE == 11_526
    assert universe.SYMBOL_ONLY_TARGETS == ("MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM")


def test_the_four_symbol_only_targets_are_RETAINED_not_dropped():
    parts = universe.split(LEVERS)
    assert parts["n_symbol_only"] == 4
    assert parts["n_ensembl"] == 2
    assert parts["n_total"] == 6, "every released target survives the split"
    assert set(parts["symbol_only_targets"]) == set(universe.SYMBOL_ONLY_TARGETS)
    assert parts["universe_is_homogeneous_ensembl"] is False


def test_each_symbol_only_target_carries_an_explicit_unsupported_namespace_disposition():
    disps = universe.dispositions(LEVERS)
    assert len(disps) == 4
    for d in disps:
        assert d["state"] == universe.UNSUPPORTED_NAMESPACE
        assert d["acquisition_route_can_reach_it"] is False
        # The load-bearing one: a route limit is NOT an absence of drug evidence.
        assert d["means_no_drug_evidence_exists"] is False
        assert "NOT an absence of drug evidence" in d["reason"]


def test_no_ensembl_target_gets_an_unsupported_namespace_disposition():
    subjects = {d["subject_id"] for d in universe.dispositions(LEVERS)}
    assert CTLA4 not in subjects and IL2RA not in subjects


# --------------------------------------------------------------------------- #
# Coverage denominators SPLIT.
# --------------------------------------------------------------------------- #
def test_coverage_denominators_split_by_namespace():
    cov = universe.coverage(LEVERS, acquired_target_ids={CTLA4})
    ens = cov["by_namespace"][universe.NS_ENSEMBL]
    sym = cov["by_namespace"][universe.NS_SYMBOL_ONLY]

    assert ens["denominator"] == 2 and ens["acquired"] == 1
    assert ens["coverage"] == 0.5
    assert ens["route_can_reach"] is True

    assert sym["denominator"] == 4, "the four are in the accounting, not vanished"
    assert sym["route_can_reach"] is False
    assert sym["disposition"] == universe.UNSUPPORTED_NAMESPACE


def test_symbol_only_coverage_is_NULL_not_zero():
    """0.0 would say 'we looked and found nothing'. We never looked — we cannot."""
    sym = universe.coverage(LEVERS, acquired_target_ids={CTLA4})[
        "by_namespace"][universe.NS_SYMBOL_ONLY]
    assert sym["coverage"] is None
    assert sym["coverage"] != 0.0


def test_a_single_blended_coverage_number_is_refused():
    cov = universe.coverage(LEVERS, acquired_target_ids={CTLA4})
    assert cov["blended_coverage_permitted"] is False
    assert "true of neither population" in cov["blended_coverage_reason"]


def test_dropping_the_four_would_have_reported_100_percent():
    """The exact defect. Ensembl-only accounting calls this complete; it is 1 of 6."""
    cov = universe.coverage(LEVERS, acquired_target_ids={CTLA4, IL2RA})
    assert cov["by_namespace"][universe.NS_ENSEMBL]["coverage"] == 1.0
    assert cov["n_total_targets"] == 6, (
        "the ENSEMBL population is fully covered, but four targets were never reachable — "
        "and the total says so")


def test_acquiring_a_symbol_only_target_is_impossible_and_refused():
    with pytest.raises(universe.UniverseError, match="had no id for"):
        universe.coverage(LEVERS, acquired_target_ids={"MTRNR2L1"})


# --------------------------------------------------------------------------- #
# Drift against the audit is loud.
# --------------------------------------------------------------------------- #
def test_a_universe_that_drifts_from_the_audited_split_is_refused():
    with pytest.raises(universe.UniverseError, match="need a human"):
        universe.check_against_audit({"n_ensembl": 11_526, "n_symbol_only": 0})


def test_the_audited_split_itself_passes():
    universe.check_against_audit({"n_ensembl": universe.N_ENSEMBL,
                                  "n_symbol_only": universe.N_SYMBOL_ONLY})
