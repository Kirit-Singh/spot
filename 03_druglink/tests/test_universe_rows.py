"""The typed universe and the store on disk: TARGET identity, proved from the store's bytes.

Audit blocker B6: the admitted store verifies, every hash in it checks out — and the v2 CLI
hands it an **EMPTY** typed universe. The empty list hashes to ``4f53cda1…``; the universe the
store was built for hashes to ``1c19db2b…``. An empty universe is not "no universe supplied",
it is a **different** universe — one covering nothing. So these tests prove the real
11,526-row universe is DERIVED from the store's own rows (never copied from the manifest),
that the store re-hashes every artifact it loads, and that the join is by exact typed identity
or it does not happen:

  * an empty typed universe is refused, and so is a wrong one, and so is one nobody admitted;
  * a mutated row, provenance file, eligibility record or licence is refused BY NAME;
  * a symbol join is refused — a bare id is a name, and names are not identities;
  * a symbol-only target is RETAINED with its ``unsupported_namespace`` disposition, which
    means "this acquisition route cannot reach it" and never "no drug evidence exists".

What happens to an ASSERTION once its target is admitted — the lanes, the rankability gates,
max_phase — is :mod:`test_universe_edges`, mirroring the ``druglink.universe_rows`` /
``druglink.universe_edges`` split. The real store and the synthetic hostile rows are shared
scaffolding: see :mod:`universe_store_fixture`.

NON-VACUITY: every real-store assertion checks non-empty counts first. A pass over zero rows
proves nothing, and that is exactly the failure mode B6 describes.
"""
from __future__ import annotations

import copy
import os

import pytest

from druglink import universe_rows as ur
from druglink import universe_verify as uv
from universe_store_fixture import (
    ADMITTED_STORE_ID,
    ADMITTED_UNIVERSE_SHA,
    EMPTY_UNIVERSE_SHA,
    N_ENSG,
    N_SYMBOL_ONLY,
    N_TARGETS,
    SYMBOL_ONLY,
    _copy_store,
    _rewrite,
    _row,
    _synthetic_store,
    needs_store,
)


# --------------------------------------------------------------------------- #
# 1. The typed universe is DERIVED, and it is the admitted one.
# --------------------------------------------------------------------------- #
@needs_store
def test_the_typed_universe_derives_the_admitted_hash_from_the_stores_own_rows(store):
    """THE B6 GATE. 11,526 rows in, 1c19db2b… out — derived, never copied."""
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
