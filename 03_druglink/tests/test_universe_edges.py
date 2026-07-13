"""What happens to a source drug ASSERTION once its target is admitted.

The other half of audit blocker B6, on the REAL store's bytes. Target identity — the typed
universe, the store on disk, the typed join — is :mod:`test_universe_rows`; this file starts
where that one ends, at the assertion, and holds the three semantics the store paid for once
already:

  * an **ambiguous_identity row carries no rankable assertion at ANY nesting depth**. The row
    says ``drugs: []`` and is honest — but six source assertions sit one container down, and a
    consumer that flattens reads the ASSERTION, not the row;
  * a **variant assertion never enters the general lane**, including the 10 whose ``variant_id``
    is ``-1``, ChEMBL's UNDEFINED MUTATION sentinel. One that merely OMITS its rankability flag
    is refused too: absence is not permission, and omission is exactly how 29 variant
    assertions reached general-gene ranking;
  * the **cache holds no Stage-3 verdict**. ``action_type`` travels verbatim and ``max_phase``
    is regulatory CONTEXT — it may order nothing, and it is refused as a sort key by name.

Exercised through ``druglink.universe_rows``, which re-exports the edge layer as the single
front door a consumer binds; the behaviour under test lives in ``druglink.universe_edges``.
The real store and the synthetic hostile rows are shared scaffolding: see
:mod:`universe_store_fixture`.

NON-VACUITY: every real-store assertion checks non-empty counts first. A pass over zero edges
proves nothing, and that is exactly the failure mode B6 describes.
"""
from __future__ import annotations

import pytest

from druglink import universe_rows as ur
from druglink import universe_verify as uv
from universe_store_fixture import (
    ADMITTED_STORE_ID,
    ADMITTED_UNIVERSE_SHA,
    AMBIGUOUS_MEC_IDS,
    CALMODULIN,
    N_AMBIGUOUS,
    N_GENERAL,
    N_OCCURRENCES,
    N_UNDEFINED_MUTATION,
    N_UNIQUE_MEC,
    N_VARIANT,
    _assertion,
    _row,
    _synthetic_store,
    _typed,
    needs_store,
)


# --------------------------------------------------------------------------- #
# 4. Ambiguous identity carries no rankable evidence — at ANY depth.
# --------------------------------------------------------------------------- #
@needs_store
def test_the_real_ambiguous_rows_carry_no_rankable_evidence(store, all_edges):
    amb = [e for e in all_edges if e["lane"] == ur.LANE_AMBIGUOUS]
    assert len(amb) == N_AMBIGUOUS
    assert {e["source_row_id"] for e in amb} == set(AMBIGUOUS_MEC_IDS)
    assert {e["target_id"] for e in amb} == set(CALMODULIN)
    assert all(e["general_gene_rankable"] is False for e in amb)
    assert all(e["ambiguity_disposition"] == "ambiguous_identity_nonrankable" for e in amb)
    assert not [e for e in ur.rankable_edges(all_edges)
                if e["target_disposition"] == ur.DISP_AMBIGUOUS_IDENTITY]


def test_an_ambiguous_row_carrying_a_rankable_edge_is_refused():
    row = _row(disposition=ur.DISP_AMBIGUOUS_IDENTITY, drugs=[_assertion()])
    with pytest.raises(ur.DrugEdgeError) as exc:
        ur.drug_edges_for_targets(_synthetic_store([row]), [_typed(row)])
    assert exc.value.gate == ur.GATE_AMBIGUOUS_ROW_HAS_RANKABLE_EVIDENCE


def test_a_rankable_assertion_nested_at_ANY_depth_inside_an_ambiguous_row_is_refused():
    """The row says drugs=[]. The assertion two containers down says rankable=true.

    A consumer that flattens reads the ASSERTION, not the row — and flattening is the obvious
    thing to do. So the gate is container-agnostic and depth-agnostic.
    """
    leaked = _assertion(source_row_id=6210, general_gene_rankable=True,
                        ambiguity_disposition="ambiguous_identity_nonrankable")
    row = _row(disposition=ur.DISP_AMBIGUOUS_IDENTITY, drugs=[],
               # deliberately NOT the container the gate knows by name
               provenance={"copies": {"preserved": [leaked]}})
    with pytest.raises(ur.DrugEdgeError) as exc:
        ur.drug_edges_for_targets(_synthetic_store([row]), [_typed(row)])
    assert exc.value.gate == ur.GATE_AMBIGUOUS_ROW_HAS_RANKABLE_EVIDENCE
    assert "6210" in str(exc.value)


# --------------------------------------------------------------------------- #
# 5. Variant assertions never rank a gene. -1 is a MUTATION, not a null.
# --------------------------------------------------------------------------- #
@needs_store
def test_every_real_variant_assertion_is_excluded_from_general_ranking(store, all_edges):
    var = [e for e in all_edges if e["lane"] == ur.LANE_VARIANT]
    assert len(var) == N_VARIANT
    assert all(e["general_gene_rankable"] is False for e in var)
    assert all(e["variant_specific"] is True for e in var)
    assert all(e["variant_disposition"] == "variant_specific_nonrankable" for e in var)

    sentinels = [e for e in var if e["variant_id"] == ur.VARIANT_UNDEFINED_MUTATION]
    assert len(sentinels) == N_UNDEFINED_MUTATION     # -1 is PRESERVED, never nulled
    assert not [e for e in ur.rankable_edges(all_edges)
                if ur.is_variant_assertion(e)]


@pytest.mark.parametrize("variant_id", [ur.VARIANT_UNDEFINED_MUTATION, 617])
def test_a_variant_assertion_in_the_general_lane_is_refused(variant_id):
    """variant_id = -1 is ChEMBL's UNDEFINED MUTATION. Reading it as null makes an unknown
    mutant into a wild-type claim — the worst available interpretation."""
    row = _row(drugs=[_assertion(variant_id=variant_id, variant_specific=True)])
    with pytest.raises(ur.DrugEdgeError) as exc:
        ur.drug_edges_for_targets(_synthetic_store([row]), [_typed(row)])
    assert exc.value.gate == ur.GATE_VARIANT_IN_GENERAL_LANE


def test_a_variant_assertion_that_merely_OMITS_rankability_is_refused():
    """Absence is not permission. The store omits the flag; that is how 29 assertions
    reached general-gene ranking."""
    silent = _assertion(variant_id=617, variant_specific=True)
    silent.pop("general_gene_rankable")
    row = _row(drugs=[], variant_specific_assertions=[silent])
    with pytest.raises(ur.DrugEdgeError) as exc:
        ur.drug_edges_for_targets(_synthetic_store([row]), [_typed(row)])
    assert exc.value.gate == ur.GATE_VARIANT_IN_GENERAL_LANE


# --------------------------------------------------------------------------- #
# 6. max_phase is CONTEXT. The cache holds no Stage-3 verdict.
# --------------------------------------------------------------------------- #
@needs_store
def test_max_phase_may_never_order_or_gate_an_edge(all_edges):
    ranked = ur.rankable_edges(all_edges)
    assert len(ranked) == N_GENERAL                      # non-vacuous
    assert all(e["max_phase_is_context_only"] is True for e in ranked)

    for key in ("max_phase_canonical", "max_phase_source", "max_phase"):
        with pytest.raises(ur.DrugEdgeError) as exc:
            ur.order_edges(ranked, by=[key])
        assert exc.value.gate == ur.GATE_MAX_PHASE_IS_NOT_A_RANK

    ordered = ur.order_edges(ranked, by=["molecule_chembl_id", "source_row_id"])
    assert len(ordered) == N_GENERAL


@needs_store
def test_the_cache_carries_no_stage3_direction_or_ranking_verdict(all_edges):
    """action_type travels VERBATIM; direction is recomputed at build time from the frozen
    Stage-3 vocabulary. A cached verdict outlives the vocabulary that produced it."""
    assert all(e["direction_decided_in_cache"] is False for e in all_edges)
    for e in all_edges:
        assert not (uv.FORBIDDEN_DRUG_KEYS & set(e)), e["edge_id"]
    actions = {e["action_type_source"] for e in all_edges}
    assert "INHIBITOR" in actions                        # non-vacuous, and untranslated
    assert not (actions & {"functional_inhibition", "abundance_reduction", "decrease"})


def test_an_assertion_carrying_a_precomputed_direction_is_refused():
    row = _row(drugs=[_assertion(direction="decrease")])
    with pytest.raises(ur.DrugEdgeError) as exc:
        ur.drug_edges_for_targets(_synthetic_store([row]), [_typed(row)])
    assert exc.value.gate == ur.GATE_CACHE_CARRIES_A_DIRECTION_VERDICT


def test_an_assertion_without_its_source_identity_is_refused():
    row = _row(drugs=[_assertion(source_row_id=None)])
    with pytest.raises(ur.DrugEdgeError) as exc:
        ur.drug_edges_for_targets(_synthetic_store([row]), [_typed(row)])
    assert exc.value.gate == ur.GATE_MISSING_SOURCE_IDENTITY


# --------------------------------------------------------------------------- #
# 7. The adapter's accounting reconciles, and preserves the source verbatim.
# --------------------------------------------------------------------------- #
@needs_store
def test_the_edge_denominators_reconcile_with_the_stores_own_counts(store, all_edges):
    lanes = [e["lane"] for e in all_edges]
    assert lanes.count(ur.LANE_GENERAL) == N_GENERAL
    assert lanes.count(ur.LANE_VARIANT) == N_VARIANT
    assert lanes.count(ur.LANE_AMBIGUOUS) == N_AMBIGUOUS
    assert len(all_edges) == N_OCCURRENCES == N_GENERAL + N_VARIANT + N_AMBIGUOUS
    assert len({e["source_row_id"] for e in all_edges}) == N_UNIQUE_MEC

    cov = store.manifest["coverage"]
    assert cov["n_general_drug_assertions"] == N_GENERAL
    assert cov["n_variant_specific_assertions"] == N_VARIANT
    assert len({e["target_id"] for e in ur.rankable_edges(all_edges)}) == cov["n_drug_evidence"]


@needs_store
def test_every_source_field_survives_verbatim(store, all_edges):
    """The bytes that leave the adapter are the bytes ChEMBL wrote."""
    by_mec = {(e["target_id"], e["source_row_id"]): e for e in all_edges}
    checked = 0
    for row in store.rows:
        for container in ("drugs", "variant_specific_assertions",
                          "ambiguous_source_assertions"):
            for a in (row.get(container) or []):
                e = by_mec[(row["target_id"], a["source_row_id"])]
                for k in ("molecule_chembl_id", "target_chembl_id", "pref_name",
                          "molecule_type", "inchikey", "action_type_source",
                          "mechanism_of_action", "mechanism_refs", "selectivity_comment",
                          "direct_interaction", "molecular_mechanism", "disease_efficacy",
                          "max_phase_source", "max_phase_canonical", "variant_id",
                          "variant_specific", "cross_ref_provenance"):
                    assert k in a, f"{a['source_row_id']}: the source lost {k}"
                    assert e[k] == a[k], f"{a['source_row_id']}: {k} did not survive"
                checked += 1
    assert checked == N_OCCURRENCES


@needs_store
def test_every_edge_binds_its_release_licence_and_attribution(all_edges):
    for e in all_edges[:50] + all_edges[-50:]:
        b = e["release_binding"]
        assert b["store_id"] == ADMITTED_STORE_ID
        assert b["typed_universe_sha256"] == ADMITTED_UNIVERSE_SHA
        assert b["chembl_release"] == "CHEMBL_37"
        assert b["chembl_license"] == "CC BY-SA 3.0"
        assert b["uniprot_license"] == "CC BY 4.0"
        assert "REQUIRED.ATTRIBUTION" in b["chembl_required_attribution"]
        assert b["chembl_doi"] and b["chembl_source_sha256"]
