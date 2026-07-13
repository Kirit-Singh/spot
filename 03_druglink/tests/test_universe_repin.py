"""THE VOCABULARY RE-PIN, PROVED ON THE REAL STORE'S BYTES.

Stage 2 (W3) serializes ``ensembl_gene_id`` / ``gene_symbol``. The universe store serialized
``ensembl_gene`` / ``symbol``. The join between them is by EXACT TYPED IDENTITY — the only
honest join, because a symbol match silently re-attributes every edge the first time a gene is
renamed — so exact-token equality refused all 11,522 real Ensembl rows and the lane produced
ZERO edges.

The store was therefore RE-EMITTED under Stage-2's tokens. That is a VOCABULARY re-pin, not a
re-extraction, and this file is the proof of it:

  * the SCIENTIFIC CONTENT HASH — every row with ``target_id_namespace`` projected out — is
    IDENTICAL before and after. This is the load-bearing assertion: it is what demonstrates
    that only the token moved. Nothing else in this file matters if this fails;
  * every count is unchanged: 11,526 rows (11,522 + 4), 2,262 assertions (2,227 + 29 + 6),
    505 targets with drug evidence, 1,923 molecules;
  * the row map is bijective and total, and nothing was reordered;
  * ``store_id`` and the typed-universe hash MUST move — the typed universe hashes
    ``{target_id, target_id_namespace}``, so a token change necessarily moves it. A re-pin
    whose identity did not move did not happen;
  * licences, attribution, provenance and eligibility evidence travel byte-for-byte.

AND THE JOIN, NON-VACUOUSLY:

  * a real ENSG target with a NON-EMPTY edge set joins exactly and returns real ChEMBL edges;
  * a real SYMBOL target RESOLVES in the typed universe and returns ZERO edges with STATED
    MISSINGNESS. Those four targets genuinely carry no drug evidence in ChEMBL. **No symbol
    edge is fabricated to make a test look non-empty.** The join is non-empty at the IDENTITY
    level; the EVIDENCE is legitimately empty, and is stated rather than invented or dropped;
  * an unknown token is a NAMED refusal, never a coercion;
  * the retired-vocabulary store is REFUSED, not silently accepted.

NON-VACUITY: every real-store assertion checks a non-empty count first. A pass over zero rows
proves nothing, which is exactly the failure mode audit blocker B6 describes.
"""
from __future__ import annotations

import json
import os

import pytest

from druglink import universe_repin as rp
from druglink import universe_rows as ur
from druglink import universe_verify as uv
from universe_store_fixture import (
    ADMITTED_STORE_ID,
    ADMITTED_UNIVERSE_SHA,
    ENSG_WITH_EDGES,
    N_AMBIGUOUS,
    N_DRUG_EVIDENCE_TARGETS,
    N_ENSG,
    N_GENERAL,
    N_MOLECULES_GENERAL,
    N_OCCURRENCES,
    N_SYMBOL_ONLY,
    N_TARGETS,
    N_VARIANT,
    SCIENTIFIC_CONTENT_SHA,
    STALE_STORE_DIR,
    STALE_VOCAB_STORE_ID,
    SYMBOL_ONLY,
    needs_stale_store,
    needs_store,
)


@pytest.fixture(scope="module")
def source_rows():
    """The RETIRED-vocabulary store's own rows, read from disk. The re-pin's only input."""
    with open(os.path.join(STALE_STORE_DIR, rp.ROWS_NAME)) as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# 1. THE LOAD-BEARING PROOF: the science did not move.
# --------------------------------------------------------------------------- #
@needs_stale_store
@needs_store
def test_the_SCIENTIFIC_CONTENT_HASH_is_IDENTICAL_across_the_repin(source_rows, store):
    """Every row, with the namespace token PROJECTED OUT, hashes the same on both sides.

    The one assertion this whole exercise stands on. It covers the target ids, the
    dispositions, every drug assertion, every accession, every stated missingness reason — and
    it excludes exactly the one field the re-pin was allowed to touch. If it holds, only the
    vocabulary moved.
    """
    assert len(source_rows) == N_TARGETS, "non-vacuity: the source store is not empty"

    before = rp.scientific_content_sha256(source_rows)
    after = rp.scientific_content_sha256(store.rows)

    assert before == after, (
        "the re-pin changed something other than the namespace token: the scientific content "
        f"hash moved {before[:16]}… -> {after[:16]}…")
    assert after == SCIENTIFIC_CONTENT_SHA
    assert ur.ADMITTED_SCIENTIFIC_CONTENT_SHA256 == SCIENTIFIC_CONTENT_SHA


@needs_stale_store
@needs_store
def test_the_row_map_is_BIJECTIVE_TOTAL_and_UNREORDERED(source_rows, store):
    """No row added, dropped, merged or reordered. The target_id sequence is identical."""
    assert [r["target_id"] for r in source_rows] == [r["target_id"] for r in store.rows]
    assert len(store.rows) == len(source_rows) == N_TARGETS
    assert len({r["target_id"] for r in store.rows}) == N_TARGETS

    # 1:1 and TOTAL, at the typed level: every source identity maps to exactly one new one.
    mapped = {(r["target_id"], rp.REPIN_TOKENS[r["target_id_namespace"]])
              for r in source_rows}
    actual = {(r["target_id"], r["target_id_namespace"]) for r in store.rows}
    assert mapped == actual
    assert len(mapped) == N_TARGETS


@needs_stale_store
@needs_store
def test_every_COUNT_is_UNCHANGED_across_the_repin(source_rows, store):
    """The store's science, recounted from both sets of bytes. Nothing quoted from a memo."""
    def counts(rows):
        general = [a for r in rows for a in (r.get("drugs") or [])]
        variant = [a for r in rows for a in (r.get("variant_specific_assertions") or [])]
        amb = [a for r in rows for a in (r.get("ambiguous_source_assertions") or [])]
        return {
            "rows": len(rows),
            "assertions": len(general) + len(variant) + len(amb),
            "general": len(general), "variant": len(variant), "ambiguous": len(amb),
            "drug_evidence_targets": sum(1 for r in rows if r.get("drugs")),
            "molecules": len({a["molecule_chembl_id"] for a in general}),
            "dispositions": {r["disposition"] for r in rows},
        }

    before, after = counts(source_rows), counts(store.rows)
    assert before == after
    assert after == {
        "rows": N_TARGETS, "assertions": N_OCCURRENCES, "general": N_GENERAL,
        "variant": N_VARIANT, "ambiguous": N_AMBIGUOUS,
        "drug_evidence_targets": N_DRUG_EVIDENCE_TARGETS,
        "molecules": N_MOLECULES_GENERAL,
        "dispositions": {"drug_evidence", "no_drug_evidence", "ambiguous_identity",
                         "unsupported_namespace"},
    }


@needs_stale_store
@needs_store
def test_the_NAMESPACE_SPLIT_is_the_SAME_targets_under_the_NEW_tokens(source_rows, store):
    """11,522 / 4 before, 11,522 / 4 after — and the same four symbols, by name."""
    old_sym = sorted(r["target_id"] for r in source_rows
                     if r["target_id_namespace"] == "symbol")
    new_sym = sorted(r["target_id"] for r in store.rows
                     if r["target_id_namespace"] == ur.NS_SYMBOL)
    assert old_sym == new_sym == sorted(SYMBOL_ONLY)

    assert sum(1 for r in source_rows
               if r["target_id_namespace"] == "ensembl_gene") == N_ENSG
    assert sum(1 for r in store.rows
               if r["target_id_namespace"] == ur.NS_ENSEMBL_GENE) == N_ENSG
    assert len(new_sym) == N_SYMBOL_ONLY


@needs_stale_store
@needs_store
def test_LICENCES_ATTRIBUTION_and_PROVENANCE_travel_BYTE_FOR_BYTE(store):
    """ChEMBL is CC BY-SA 3.0 and its attribution is REQUIRED. A derived layer that travels
    without its licence is a licence breach, not a missing nicety."""
    for name in rp.CARRIED_VERBATIM:
        old = os.path.join(STALE_STORE_DIR, name)
        new = os.path.join(store.store_dir, name)
        assert os.path.exists(new), f"{name} did not travel"
        with open(old, "rb") as a, open(new, "rb") as b:
            assert a.read() == b.read(), f"{name} is not byte-identical"

    rel = store.releases
    assert rel["chembl"]["license"] == "CC BY-SA 3.0"
    assert rel["chembl"]["source_release"] == "CHEMBL_37"
    assert rel["chembl"]["attribution"]
    assert rel["uniprot"]["license"] == "CC BY 4.0"


# --------------------------------------------------------------------------- #
# 2. THE IDENTITY MUST MOVE. A re-pin whose hashes stayed put did not happen.
# --------------------------------------------------------------------------- #
@needs_store
def test_the_STORE_ID_and_TYPED_UNIVERSE_HASH_BOTH_MOVED(store):
    """The typed universe hashes {target_id, target_id_namespace}: a token change moves it."""
    assert store.store_id == ADMITTED_STORE_ID
    assert store.store_id != STALE_VOCAB_STORE_ID
    assert store.typed_universe_sha256 == ADMITTED_UNIVERSE_SHA
    assert store.typed_universe_sha256 != \
        "5fdbaf585a246489a5f2dfcb9450553370d435b1757b2247d972f79be75193af"
    assert store.manifest["schema_version"] == rp.MANIFEST_SCHEMA_V2


@needs_store
def test_the_store_states_its_own_REPIN_LINEAGE(store):
    """A reader who opens this store must see WHAT changed and WHAT it came from."""
    block = store.manifest["namespace_vocabulary"]
    assert block["vocabulary"] == list(ur.STORE_NAMESPACES)
    assert block["retired_vocabulary"] == list(ur.RETIRED_NAMESPACES)
    assert block["token_map"] == {"ensembl_gene": "ensembl_gene_id", "symbol": "gene_symbol"}
    assert block["repinned_from_store_id"] == STALE_VOCAB_STORE_ID
    assert block["scientific_content_sha256"] == SCIENTIFIC_CONTENT_SHA
    assert block["chembl_was_not_requeried"] is True


# --------------------------------------------------------------------------- #
# 3. THE JOIN, NON-VACUOUSLY, ON THE REAL STORE.
# --------------------------------------------------------------------------- #
@needs_store
def test_an_ENSEMBL_target_joins_exactly_and_returns_REAL_NON_EMPTY_ChEMBL_edges(store):
    """The join the retired vocabulary refused. It must now return real drug evidence."""
    query = {"target_id": ENSG_WITH_EDGES, "target_id_namespace": ur.NS_ENSEMBL_GENE}
    edges = ur.drug_edges_for_targets(store, [query])

    assert edges, (
        f"NON-VACUITY: {ENSG_WITH_EDGES} must return a NON-EMPTY edge set. An empty one here "
        "would mean the typed join is still refusing every Ensembl row")
    assert all(e["target_id"] == ENSG_WITH_EDGES for e in edges)
    assert all(e["target_id_namespace"] == ur.NS_ENSEMBL_GENE for e in edges)

    rankable = ur.rankable_edges(edges)
    assert rankable, "NON-VACUITY: real general-lane ChEMBL assertions"
    for e in rankable:
        assert e["molecule_chembl_id"].startswith("CHEMBL")
        assert e["target_chembl_id"].startswith("CHEMBL")
        assert e["action_type_source"]
        # every edge carries the release it is REOPENABLE in, and the licence it travels under
        binding = e["release_binding"]
        assert binding["chembl_release"] == "CHEMBL_37"
        assert binding["chembl_license"] == "CC BY-SA 3.0"
        assert binding["store_id"] == ADMITTED_STORE_ID
        assert binding["typed_universe_sha256"] == ADMITTED_UNIVERSE_SHA


@needs_store
def test_the_WHOLE_admitted_universe_joins_and_yields_the_2262_source_assertions(store):
    """Not one target: ALL 11,526 — the count the retired vocabulary drove to zero."""
    edges = ur.drug_edges_for_targets(
        store, [{"target_id": r["target_id"],
                 "target_id_namespace": r["target_id_namespace"]}
                for r in store.typed_universe])
    assert len(edges) == N_OCCURRENCES
    assert len(ur.rankable_edges(edges)) == N_GENERAL
    assert len({e["molecule_chembl_id"] for e in ur.rankable_edges(edges)}) \
        == N_MOLECULES_GENERAL


@needs_store
@pytest.mark.parametrize("symbol", SYMBOL_ONLY)
def test_a_SYMBOL_target_RESOLVES_and_states_its_missingness_without_inventing_an_edge(
        store, symbol):
    """The identity RESOLVES; the EVIDENCE is legitimately empty, and is STATED.

    MTRNR2L1/L4/L8 and OCLM genuinely carry no drug evidence in ChEMBL. Stage-3's acquisition
    route resolves targets by UniProt Ensembl cross-reference, so the ROUTE cannot reach them
    either. Both facts are true, and neither is an absence of drug evidence anybody RULED OUT.

    So the resolution is asserted NON-EMPTY — the target is in the admitted universe, under
    `gene_symbol`, with a named disposition — and the edge set is asserted EMPTY. Fabricating a
    symbol edge to make this test "non-empty" would be inventing the exact finding the store
    exists to keep honest.
    """
    query = {"target_id": symbol, "target_id_namespace": ur.NS_SYMBOL}

    # THE IDENTITY RESOLVES. Non-empty, and that is what "the join works" means here.
    row = store.row_for(symbol, ur.NS_SYMBOL)
    assert row is not None, "NON-VACUITY: the target must RESOLVE in the typed universe"
    assert row["target_id"] == symbol
    assert row["target_id_namespace"] == ur.NS_SYMBOL
    assert row["disposition"] == ur.DISP_UNSUPPORTED_NAMESPACE
    assert any(t["target_id"] == symbol and t["target_id_namespace"] == ur.NS_SYMBOL
               for t in store.typed_universe)

    # THE MISSINGNESS IS STATED, in the store's OWN words — quoted, never paraphrased into
    # something tidier. `symbol_only_target_no_ensembl_xref_join` says precisely why: the
    # acquisition ROUTE resolves targets by UniProt Ensembl cross-reference, and this target
    # has none. That is not "ChEMBL says there is no drug"; it is "this route never asked".
    assert row["no_evidence_reason"] == "symbol_only_target_no_ensembl_xref_join"

    # THE EVIDENCE IS EMPTY, and it is STATED. Never invented, never silently dropped.
    assert ur.drug_edges_for_targets(store, [query]) == []
    assert not row["drugs"]
    assert not row.get("variant_specific_assertions")
    assert not row.get("ambiguous_source_assertions")


@needs_store
def test_a_gene_symbol_may_only_join_a_gene_symbol(store):
    """Cross-namespace joins stay REFUSED. A symbol asked for as an Ensembl id must not answer."""
    with pytest.raises(ur.DrugEdgeError) as exc:
        ur.drug_edges_for_targets(
            store, [{"target_id": "MTRNR2L1",
                     "target_id_namespace": ur.NS_ENSEMBL_GENE}])
    assert exc.value.gate == ur.GATE_NAMESPACE_CROSS_JOIN

    with pytest.raises(ur.DrugEdgeError) as exc2:
        ur.drug_edges_for_targets(
            store, [{"target_id": ENSG_WITH_EDGES,
                     "target_id_namespace": ur.NS_SYMBOL}])
    assert exc2.value.gate == ur.GATE_NAMESPACE_CROSS_JOIN


# --------------------------------------------------------------------------- #
# 4. NO ALIAS LAYER. The retired tokens are refused, not translated.
# --------------------------------------------------------------------------- #
def test_the_LOADER_speaks_ONLY_the_canonical_tokens():
    assert ur.STORE_NAMESPACES == ("ensembl_gene_id", "gene_symbol")
    assert uv.STORE_NAMESPACES == ("ensembl_gene_id", "gene_symbol")
    assert ur.NS_ENSEMBL_GENE == "ensembl_gene_id"
    assert ur.NS_SYMBOL == "gene_symbol"
    # The retired tokens exist ONLY as a refusal vocabulary, never as accepted inputs.
    assert ur.RETIRED_NAMESPACES == ("ensembl_gene", "symbol")
    assert not set(ur.RETIRED_NAMESPACES) & set(ur.STORE_NAMESPACES)


@pytest.mark.parametrize("token", ["ensembl_gene", "symbol", "entrez_gene_id", "hgnc", ""])
def test_a_NON_CANONICAL_namespace_token_is_a_NAMED_REFUSAL_never_a_coercion(token):
    """The alias layer's absence, made testable.

    A translation map would map `ensembl_gene` -> `ensembl_gene_id` here and every test would
    stay green while the two lanes drifted apart. There is no such map: the token is refused.
    """
    rows = [{"target_id": "ENSG00000003436", "target_id_namespace": token,
             "disposition": ur.DISP_NO_DRUG_EVIDENCE, "drugs": []}]
    with pytest.raises(ur.TypedUniverseError) as exc:
        ur.derive_typed_universe(rows)
    # An empty token cannot be a namespace at all; a non-empty unknown one names the gate.
    assert exc.value.gate in (ur.GATE_UNKNOWN_NAMESPACE_TOKEN, ur.GATE_MALFORMED_STORE_ROW)
    if token:
        assert exc.value.gate == ur.GATE_UNKNOWN_NAMESPACE_TOKEN


@needs_stale_store
def test_the_RETIRED_VOCABULARY_STORE_ON_DISK_IS_REFUSED_not_silently_accepted():
    """The real stale store, loaded through the real gated path. It must not open.

    Every hash inside it still verifies — that is exactly the point. It is refused on its
    VOCABULARY, by name, and never quietly translated into the admitted one.
    """
    with pytest.raises(ur.UniverseRowsError) as exc:
        ur.load_store(STALE_STORE_DIR)
    assert exc.value.gate == ur.GATE_UNKNOWN_NAMESPACE_TOKEN
    assert "ensembl_gene" in str(exc.value)
    # and it is still on disk, untouched: the admitted bytes are never mutated
    assert os.path.exists(os.path.join(STALE_STORE_DIR, rp.MANIFEST_NAME))


# --------------------------------------------------------------------------- #
# 5. The re-pin tool's own gates.
# --------------------------------------------------------------------------- #
def test_the_scientific_content_hash_EXCLUDES_the_token_and_NOTHING_ELSE():
    """Change the token: the hash holds. Change any other field: it moves."""
    row = {"target_id": "ENSG1", "target_id_namespace": "ensembl_gene",
           "disposition": "drug_evidence",
           "drugs": [{"molecule_chembl_id": "CHEMBL25", "source_row_id": 1}]}
    base = rp.scientific_content_sha256([row])

    assert rp.scientific_content_sha256(
        [{**row, "target_id_namespace": "ensembl_gene_id"}]) == base
    assert rp.scientific_content_sha256(
        [{**row, "target_id_namespace": "anything_at_all"}]) == base

    # everything else is INSIDE the hash — including target_id, which the re-pin may not touch
    assert rp.scientific_content_sha256([{**row, "target_id": "ENSG2"}]) != base
    assert rp.scientific_content_sha256([{**row, "disposition": "no_drug_evidence"}]) != base
    assert rp.scientific_content_sha256([{**row, "drugs": []}]) != base


def test_the_hash_REFUSES_a_target_id_that_is_ambiguous_once_the_token_is_removed():
    """With the namespace projected out, target_id must carry the identity alone."""
    rows = [{"target_id": "X", "target_id_namespace": "ensembl_gene", "disposition": "a"},
            {"target_id": "X", "target_id_namespace": "symbol", "disposition": "b"}]
    with pytest.raises(rp.RepinError) as exc:
        rp.scientific_content_sha256(rows)
    assert exc.value.gate == rp.GATE_AMBIGUOUS_PROJECTED_IDENTITY


def test_the_repin_REFUSES_a_row_whose_token_it_does_not_know():
    with pytest.raises(rp.RepinError) as exc:
        rp.repin_rows([{"target_id": "ENSG1", "target_id_namespace": "entrez_gene_id"}])
    assert exc.value.gate == rp.GATE_UNKNOWN_NAMESPACE_TOKEN


@needs_store
def test_the_repin_REFUSES_to_re_pin_an_ALREADY_CANONICAL_store(store, tmp_path):
    """A no-op re-pin would mint a new identity for nothing."""
    with pytest.raises(rp.RepinError) as exc:
        rp.emit(src_dir=store.store_dir, dest_dir=str(tmp_path / "out"),
                created_at="2026-07-13T12:00:00Z")
    assert exc.value.gate == rp.GATE_ALREADY_CANONICAL


@needs_stale_store
def test_the_repin_REFUSES_to_write_over_the_store_it_reads():
    """The admitted bytes are never mutated in place."""
    with pytest.raises(rp.RepinError) as exc:
        rp.emit(src_dir=STALE_STORE_DIR, dest_dir=STALE_STORE_DIR,
                created_at="2026-07-13T12:00:00Z")
    assert exc.value.gate == rp.GATE_SOURCE_NOT_ON_DISK


@needs_stale_store
def test_the_repin_is_DETERMINISTIC_and_reproduces_the_ADMITTED_identity(tmp_path):
    """Re-run the re-pin from the stale store's bytes: it must land on the admitted store_id.

    This is the whole re-pin, reproduced end to end from the only input it is allowed to have —
    and it lands, byte for byte, on the identity the loader pins. A pin that only its own
    author can reproduce is not a pin.
    """
    dest = str(tmp_path / "repinned")
    proof = rp.emit(src_dir=STALE_STORE_DIR, dest_dir=dest,
                    created_at="2026-07-13T12:00:00Z")

    assert proof["identity"]["repinned_store_id"] == ADMITTED_STORE_ID
    assert proof["identity"]["repinned_typed_universe_sha256"] == ADMITTED_UNIVERSE_SHA
    assert proof["identity"]["source_store_id"] == STALE_VOCAB_STORE_ID
    assert proof["scientific_content_hash"]["identical"] is True
    assert proof["scientific_content_hash"]["source"] == SCIENTIFIC_CONTENT_SHA
    assert proof["scientific_content_hash"]["repinned"] == SCIENTIFIC_CONTENT_SHA
    assert proof["verification_from_disk"]["ok"] is True
    assert proof["verification_from_disk"]["violations"] == []
    assert proof["row_bijection"] == {
        "n_rows_source": N_TARGETS, "n_rows_repinned": N_TARGETS,
        "target_id_sequence_identical": True, "total": True, "bijective": True,
        "rows_added": 0, "rows_dropped": 0, "rows_merged": 0, "rows_reordered": 0}
    assert proof["stated_missingness"]["n_symbol_target_drug_edges"] == 0
    assert proof["stated_missingness"]["symbol_targets"] == sorted(SYMBOL_ONLY)

    # and the re-emitted store opens through the REAL gated path, with the admitted pins
    reloaded = ur.load_store(dest)
    assert reloaded.store_id == ADMITTED_STORE_ID
    assert reloaded.typed_universe_sha256 == ADMITTED_UNIVERSE_SHA
    assert len(reloaded.rows) == N_TARGETS
