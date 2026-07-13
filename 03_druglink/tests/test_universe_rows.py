"""The universe-store row reader and the target->drug edge adapter, on the REAL store bytes.

Audit blocker B6: the admitted store verifies, and its 2,227 general drug assertions never
reach candidate generation — while the CLI hands the store an EMPTY typed universe. The
empty list hashes to ``4f53cda1…``; the universe the store was built for hashes to
``5fdbaf58…``. These tests prove the real universe is DERIVED (never copied) and that every
semantic the store paid for holds at the adapter's edge:

  * an empty typed universe is refused, and so is a wrong one;
  * a mutated store row, provenance file or licence is refused by NAME;
  * a symbol join is refused — the join is by exact typed identity or it does not happen;
  * an ambiguous_identity row may not carry a rankable assertion at ANY nesting depth;
  * a variant assertion (including the ``-1`` UNDEFINED MUTATION sentinel) never enters the
    general lane;
  * max_phase may not order anything;
  * the cache carries no Stage-3 direction verdict.

NON-VACUITY: every real-store assertion checks non-empty counts first. A pass over zero rows
proves nothing, and that is exactly the failure mode B6 describes.
"""
from __future__ import annotations

import copy
import glob
import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))

from druglink import universe_rows as ur          # noqa: E402
from druglink import universe_verify as uv        # noqa: E402

# The audited store identity. Literals: a pin computed from the thing it pins is not a pin.
ADMITTED_STORE_ID = "bdf41b69df2be61d3f625aafa0429e643581fe50823698e77e079054c6145160"
ADMITTED_UNIVERSE_SHA = "5fdbaf585a246489a5f2dfcb9450553370d435b1757b2247d972f79be75193af"
EMPTY_UNIVERSE_SHA = "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"

N_TARGETS, N_ENSG, N_SYMBOL_ONLY = 11_526, 11_522, 4
N_GENERAL, N_VARIANT, N_AMBIGUOUS = 2_227, 29, 6
N_OCCURRENCES, N_UNIQUE_MEC = 2_262, 2_258
N_UNDEFINED_MUTATION = 10                       # variant_id == -1
SYMBOL_ONLY = ("MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM")
CALMODULIN = ("ENSG00000143933", "ENSG00000160014", "ENSG00000198668")
AMBIGUOUS_MEC_IDS = (6210, 6862)


def _find_store() -> str | None:
    """The admitted store lives on tcefold; a working copy may be local. Never synthesised."""
    candidates = [os.environ.get("SPOT_STAGE3_UNIVERSE_STORE"),
                  "/home/tcelab/.cache/spot-stage3-universe/store"]
    candidates += sorted(glob.glob("/tmp/claude-*/*/*/scratchpad/w2_admit"))
    for path in candidates:
        if path and os.path.exists(os.path.join(path, ur.MANIFEST_NAME)):
            return path
    return None


STORE_DIR = _find_store()
needs_store = pytest.mark.skipif(
    STORE_DIR is None,
    reason="the admitted universe store is not on this host (it lives on tcefold)")


@pytest.fixture(scope="module")
def store():
    if STORE_DIR is None:
        pytest.skip("no admitted universe store on this host")
    return ur.load_store(STORE_DIR)


@pytest.fixture(scope="module")
def all_edges(store):
    edges = ur.drug_edges_for_targets(
        store, [{"target_id": r["target_id"],
                 "target_id_namespace": r["target_id_namespace"]}
                for r in store.typed_universe])
    assert edges, "non-vacuity: the real store must produce edges"
    return edges


def _copy_store(tmp_path) -> str:
    dest = str(tmp_path / "store")
    shutil.copytree(STORE_DIR, dest)
    return dest


def _rewrite(store_dir: str, name: str, mutate) -> None:
    path = os.path.join(store_dir, name)
    with open(path) as fh:
        doc = json.load(fh)
    with open(path, "w") as fh:
        json.dump(mutate(doc), fh)


# --------------------------------------------------------------------------- #
# A synthetic store, for the semantics that need a hostile row rather than the real one.
# Constructed directly: load_store is the GATED path and cannot be fed a forgery, which is
# the point of it.
# --------------------------------------------------------------------------- #
MANIFEST = {
    "store_id": ADMITTED_STORE_ID,
    "releases": {"chembl": {"source_release": "CHEMBL_37", "license": "CC BY-SA 3.0",
                            "attribution": "ChEMBL, EMBL-EBI. CC BY-SA 3.0.",
                            "doi": "10.6019/CHEMBL.database.37", "source_sha256": "aa"},
                 "uniprot": {"source_release": "2026_02", "license": "CC BY 4.0",
                             "attribution": "UniProt Consortium. CC BY 4.0.",
                             "source_sha256": "bb"}},
}


def _assertion(**over):
    a = {"molecule_chembl_id": "CHEMBL25", "target_chembl_id": "CHEMBL1862",
         "pref_name": "ASPIRIN", "molecule_type": "Small molecule", "inchikey": "KEY",
         "source_row_id": 1, "action_type_source": "INHIBITOR",
         "mechanism_of_action": "X inhibitor", "mechanism_refs": ["123"],
         "selectivity_comment": None, "direct_interaction": True,
         "molecular_mechanism": True, "disease_efficacy": True,
         "max_phase_source": "4", "max_phase_canonical": "4E+0",
         "variant_id": None, "variant_specific": False, "general_gene_rankable": True,
         "cross_ref_provenance": {}}
    a.update(over)
    return a


def _synthetic_store(rows):
    typed = ur.derive_typed_universe(rows)
    return ur.AdmittedStore(
        store_dir="/synthetic", manifest=copy.deepcopy(MANIFEST), rows=rows,
        eligibility_evidence={}, source_provenance=[], licences={},
        typed_universe=typed, typed_universe_sha256="synthetic",
        store_binding={}, _index={(r["target_id_namespace"], r["target_id"]): r
                                  for r in rows})


def _row(**over):
    row = {"target_id": "ENSG00000000001", "target_id_namespace": ur.NS_ENSEMBL_GENE,
           "disposition": ur.DISP_DRUG_EVIDENCE, "drugs": [_assertion()],
           "variant_specific_assertions": [], "identity": {"identity_status": "resolved"}}
    row.update(over)
    return row


def _typed(row):
    return {"target_id": row["target_id"],
            "target_id_namespace": row["target_id_namespace"]}


# --------------------------------------------------------------------------- #
# 1. The typed universe is DERIVED, and it is the admitted one.
# --------------------------------------------------------------------------- #
@needs_store
def test_the_typed_universe_derives_the_admitted_hash_from_the_stores_own_rows(store):
    """THE B6 GATE. 11,526 rows in, 5fdbaf58… out — derived, never copied."""
    assert len(store.typed_universe) == N_TARGETS
    assert store.typed_universe_sha256 == ADMITTED_UNIVERSE_SHA
    assert store.typed_universe_sha256 != EMPTY_UNIVERSE_SHA
    assert store.store_id == ADMITTED_STORE_ID
    assert store.store_binding["verified_from_disk"] is True
    # The producer proved the bytes. It did not admit them.
    assert store.store_binding["producer_admits_store"] is False

    ns = [r["target_id_namespace"] for r in store.typed_universe]
    assert ns.count(ur.NS_ENSEMBL_GENE) == N_ENSG
    assert ns.count(ur.NS_SYMBOL) == N_SYMBOL_ONLY

    disp = [r["disposition"] for r in store.typed_universe]
    assert disp.count(ur.DISP_NO_DRUG_EVIDENCE) == 10_931
    assert disp.count(ur.DISP_DRUG_EVIDENCE) == 505
    assert disp.count(ur.DISP_AMBIGUOUS_IDENTITY) == 86
    assert disp.count(ur.DISP_UNSUPPORTED_NAMESPACE) == N_SYMBOL_ONLY


def test_an_empty_typed_universe_is_refused_by_name():
    """The exact defect B6 found: [] hashes to 4f53cda1… and covers nothing."""
    assert uv._typed_universe_hash([]) == EMPTY_UNIVERSE_SHA
    assert EMPTY_UNIVERSE_SHA != ADMITTED_UNIVERSE_SHA

    with pytest.raises(ur.TypedUniverseError) as e1:
        ur.derive_typed_universe([])
    assert e1.value.gate == ur.GATE_EMPTY_TYPED_UNIVERSE

    with pytest.raises(ur.TypedUniverseError) as e2:
        ur.typed_universe_sha256([])
    assert e2.value.gate == ur.GATE_EMPTY_TYPED_UNIVERSE


@needs_store
def test_a_universe_that_is_not_the_bound_one_is_refused(store):
    """One target short is a DIFFERENT universe, and the store says so."""
    short = store.typed_universe[:-1]
    assert len(short) == N_TARGETS - 1
    with pytest.raises(ur.TypedUniverseError) as exc:
        ur._check_universe_is_the_admitted_one(short, store.manifest)
    assert exc.value.gate == ur.GATE_TYPED_UNIVERSE_HASH_MISMATCH


@needs_store
def test_a_universe_the_manifest_binds_but_nobody_admitted_is_refused(store):
    """Internal consistency is what a forger has; admission is what a forger lacks."""
    short = store.typed_universe[:-1]
    forged = copy.deepcopy(store.manifest)
    forged["universe_binding"]["universe_targets_sha256"] = ur.typed_universe_sha256(short)
    with pytest.raises(ur.TypedUniverseError) as exc:
        ur._check_universe_is_the_admitted_one(short, forged)
    assert exc.value.gate == ur.GATE_NOT_THE_ADMITTED_UNIVERSE


def test_a_malformed_or_duplicated_universe_row_is_refused():
    with pytest.raises(ur.TypedUniverseError) as e1:
        ur.derive_typed_universe([{"target_id": "ENSG1", "disposition": "no_drug_evidence"}])
    assert e1.value.gate == ur.GATE_MALFORMED_STORE_ROW

    dup = {"target_id": "ENSG1", "target_id_namespace": ur.NS_ENSEMBL_GENE,
           "disposition": ur.DISP_NO_DRUG_EVIDENCE}
    with pytest.raises(ur.TypedUniverseError) as e2:
        ur.derive_typed_universe([dup, dict(dup)])
    assert e2.value.gate == ur.GATE_DUPLICATE_TYPED_IDENTITY


# --------------------------------------------------------------------------- #
# 2. The store is loaded from DISK, and every artifact is re-hashed.
# --------------------------------------------------------------------------- #
@needs_store
def test_a_mutated_store_row_is_refused_even_though_the_manifest_is_untouched(tmp_path):
    d = _copy_store(tmp_path)

    def flip(rows):
        for r in rows:
            if r["disposition"] == ur.DISP_AMBIGUOUS_IDENTITY:
                r["disposition"] = ur.DISP_DRUG_EVIDENCE   # launder an ambiguous target
                return rows
        raise AssertionError("non-vacuity: no ambiguous row to mutate")

    _rewrite(d, ur.ROWS_NAME, flip)
    with pytest.raises(ur.AdmittedStoreError) as exc:
        ur.load_store(d)
    assert exc.value.gate == ur.GATE_ARTIFACT_HASH_DRIFT


@needs_store
def test_a_mutated_provenance_artifact_is_refused(tmp_path):
    d = _copy_store(tmp_path)

    def relabel(prov):
        assert prov, "non-vacuity: the provenance artifact is not empty"
        prov[0]["release"] = "CHEMBL_36"        # claim a release the bytes are not from
        return prov

    _rewrite(d, ur.PROVENANCE_NAME, relabel)
    with pytest.raises(ur.AdmittedStoreError) as exc:
        ur.load_store(d)
    assert exc.value.gate == ur.GATE_ARTIFACT_HASH_DRIFT


@needs_store
def test_a_mutated_eligibility_artifact_is_refused(tmp_path):
    d = _copy_store(tmp_path)

    def promote(doc):
        assert doc["records"], "non-vacuity: eligibility records exist"
        doc["records"][0]["disposition"] = "eligible_human_single_protein"
        return doc

    _rewrite(d, ur.ELIGIBILITY_NAME, promote)
    with pytest.raises(ur.AdmittedStoreError) as exc:
        ur.load_store(d)
    assert exc.value.gate == ur.GATE_ARTIFACT_HASH_DRIFT


@needs_store
@pytest.mark.parametrize("name", [ur.ROWS_NAME, ur.PROVENANCE_NAME, ur.ELIGIBILITY_NAME,
                                  ur.LICENSE_NAME, ur.ATTRIBUTION_NAME])
def test_a_deleted_artifact_refuses_by_name_rather_than_failing_open(tmp_path, name):
    """An earlier producer shipped the provenance gate's REPORT and returned ok=True."""
    d = _copy_store(tmp_path)
    os.remove(os.path.join(d, name))
    with pytest.raises(ur.AdmittedStoreError) as exc:
        ur.load_store(d)
    assert exc.value.gate == ur.GATE_MISSING_ARTIFACT
    assert name in str(exc.value)


def test_a_store_that_is_not_on_disk_is_refused(tmp_path):
    with pytest.raises(ur.AdmittedStoreError) as exc:
        ur.load_store(str(tmp_path / "nope"))
    assert exc.value.gate == ur.GATE_STORE_NOT_FOUND


# --------------------------------------------------------------------------- #
# 3. The join is TYPED. A symbol join is silent mis-attribution.
# --------------------------------------------------------------------------- #
def test_a_symbol_join_is_refused():
    s = _synthetic_store([_row()])

    with pytest.raises(ur.DrugEdgeError) as e1:            # a bare id is not an identity
        ur.drug_edges_for_targets(s, ["ENSG00000000001"])
    assert e1.value.gate == ur.GATE_UNTYPED_TARGET_QUERY

    with pytest.raises(ur.DrugEdgeError) as e2:            # a symbol is not a typed identity
        ur.drug_edges_for_targets(s, [{"target_id": "CALM1",
                                       "target_id_namespace": "gene_symbol"}])
    assert e2.value.gate == ur.GATE_TARGET_NOT_IN_ADMITTED_UNIVERSE

    with pytest.raises(ur.DrugEdgeError) as e3:            # no namespace at all
        ur.drug_edges_for_targets(s, [{"target_id": "ENSG00000000001"}])
    assert e3.value.gate == ur.GATE_UNTYPED_TARGET_QUERY


@needs_store
def test_the_same_id_may_not_be_joined_across_namespaces(store):
    """MTRNR2L1 exists as a SYMBOL. Asking for it as an ENSG must not answer."""
    with pytest.raises(ur.DrugEdgeError) as exc:
        ur.drug_edges_for_targets(store, [{"target_id": "MTRNR2L1",
                                           "target_id_namespace": ur.NS_ENSEMBL_GENE}])
    assert exc.value.gate == ur.GATE_NAMESPACE_CROSS_JOIN


@needs_store
def test_symbol_only_targets_are_retained_and_answer_with_a_named_disposition(store):
    """Four perturbed genes the acquisition ROUTE cannot reach. Never dropped, never zeroed."""
    kept = [r for r in store.typed_universe
            if r["target_id_namespace"] == ur.NS_SYMBOL]
    assert sorted(r["target_id"] for r in kept) == sorted(SYMBOL_ONLY)
    assert all(r["disposition"] == ur.DISP_UNSUPPORTED_NAMESPACE for r in kept)

    edges = ur.drug_edges_for_targets(
        store, [{"target_id": t, "target_id_namespace": ur.NS_SYMBOL} for t in SYMBOL_ONLY])
    assert edges == []     # no drug evidence was ACQUIRED; none was RULED OUT either
    for t in SYMBOL_ONLY:
        assert store.row_for(t, ur.NS_SYMBOL)["disposition"] == ur.DISP_UNSUPPORTED_NAMESPACE


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


@needs_store
def test_the_store_is_refused_when_its_licence_binding_is_stripped(tmp_path):
    d = _copy_store(tmp_path)

    def strip(manifest):
        manifest["releases"]["chembl"].pop("attribution")
        return manifest

    _rewrite(d, ur.MANIFEST_NAME, strip)
    with pytest.raises(ur.AdmittedStoreError) as exc:
        ur.load_store(d)
    assert exc.value.gate == ur.GATE_LICENSE_BINDING_MISSING
