"""The producer BINDS the admitted universe store. It never admits it.

Frozen v2 admission contract, rule 6: *the universe store is admitted by an INDEPENDENT
verifier and bound by its exact ``store_id``; the producer's own verdict is never the
admission.* (That contract lives in the verifier lane. This test does not import it — the
producer must stand on its own bytes, or the "independent" check is the same process twice.)

So the producer pins the ONE store an independent verifier admitted:

    store_id  625c921fce2daf60b69fb0ae33570a9f074a0a0042b1717ee2111f81c1160bff
    producer  d268a74f339d346609951e73810ab26e2e654d86

and REFUSES anything else — including a store whose internal hashes are all perfectly
self-consistent. Self-consistency is what a forger has; admission is what a forger lacks.

It also refuses, BY NAME and with its reason, the store this one replaces
(``bdf41b69…``): same science, RETIRED namespace vocabulary. That store types its rows
``ensembl_gene`` / ``symbol`` while Stage 2 serializes ``ensembl_gene_id`` / ``gene_symbol``,
so the exact-typed join refuses every Ensembl row in it and the lane yields zero edges. A
stale binding must not be reintroducible by accident.

Two refusals matter especially, because an earlier producer (d6066b7) shipped the provenance
gate's REPORT rather than the gate, and `verify_from_disk` still returned ok=True on a DELETED
provenance file. It was refused for exactly that, with the same store bytes:

  * a DELETED provenance artifact must refuse BY NAME, not fail open;
  * a MUTATED provenance artifact must refuse at its hash, even though the manifest is
    untouched.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))

from druglink import admitted_universe as au   # noqa: E402
from druglink import universe_verify as uv     # noqa: E402
from druglink.hashing import content_hash      # noqa: E402

# The exact identities an INDEPENDENT verifier admitted. Asserted as literals: a pin that is
# computed from the thing it pins is not a pin.
ADMITTED_STORE_ID = \
    "625c921fce2daf60b69fb0ae33570a9f074a0a0042b1717ee2111f81c1160bff"
ADMITTED_PRODUCER_COMMIT = "d268a74f339d346609951e73810ab26e2e654d86"
STALE_VOCAB_STORE_ID = \
    "bdf41b69df2be61d3f625aafa0429e643581fe50823698e77e079054c6145160"

# The canonical vocabulary, spelled out rather than imported: this file must be able to say
# what the tokens ARE without asking the module it is testing.
NS_ENSEMBL_GENE = "ensembl_gene_id"

TARGETS = [{"target_id": "ENSG1", "target_id_namespace": NS_ENSEMBL_GENE},
           {"target_id": "ENSG2", "target_id_namespace": NS_ENSEMBL_GENE}]


def _store(tmp_path, *, mutate_provenance=False, delete_provenance=False,
           namespace=NS_ENSEMBL_GENE, store_id=None):
    """A SYNTHETIC store whose internal hashes are all self-consistent — and which is still
    not the admitted store, because it is not the one anybody admitted."""
    d = str(tmp_path / "store")
    os.makedirs(d, exist_ok=True)

    # The REAL row shape the store verifier recomputes coverage over. No drug rows: the drug
    # payload is not what these tests are about, and a fixture that fights the real gate on
    # unrelated fields would be testing the fixture.
    rows = [{"target_id": "ENSG1", "target_id_namespace": namespace,
             "disposition": "no_drug_evidence", "drugs": [],
             "variant_specific_assertions": []},
            {"target_id": "ENSG2", "target_id_namespace": namespace,
             "disposition": "no_drug_evidence", "drugs": [],
             "variant_specific_assertions": []}]
    elig = {"records": [], "counts": {"n_total": 0, "n_eligible": 0}}
    prov = {"source": "fixture", "note": "synthetic; not the admitted store"}

    ext = {
        "extraction_query_sha256": content_hash({"q": "fixture"}),
        "store_rows_sha256": content_hash(rows),
        "eligibility_evidence_sha256": content_hash(elig),
        "public_source_provenance_sha256": content_hash(prov),
    }
    # The universe the store BINDS is derived from its own rows, so the fixture stays
    # self-consistent whatever namespace it is built in.
    targets = [{"target_id": r["target_id"],
                "target_id_namespace": r["target_id_namespace"]} for r in rows]
    ub = {"universe_targets_sha256": uv._typed_universe_hash(targets)}
    rel = {"chembl": {"source_sha256": content_hash({"c": 1}),
                      "license": "CC BY-SA 3.0"},
           "uniprot": {"source_sha256": content_hash({"u": 1}),
                       "license": "CC BY 4.0"}}
    manifest = {"extraction": ext, "universe_binding": ub, "releases": rel,
                "coverage": uv._recompute_coverage(rows)}
    manifest["store_id"] = store_id or uv.store_identity(manifest)
    manifest["content_sha256"] = uv._manifest_identity(manifest)

    if mutate_provenance:
        prov = dict(prov, note="TAMPERED — the manifest still says otherwise")

    json.dump(rows, open(os.path.join(d, "universe_store.rows.json"), "w"), sort_keys=True)
    json.dump(manifest, open(os.path.join(d, "universe_manifest.json"), "w"),
              indent=2, sort_keys=True)
    json.dump(elig, open(os.path.join(d, "target_eligibility_evidence.json"), "w"),
              sort_keys=True)
    if not delete_provenance:
        json.dump(prov, open(os.path.join(d, "source_provenance.public.json"), "w"),
                  sort_keys=True)
    return d


class TestThePinIsTheMechanism:
    def test_the_producer_pins_the_EXACT_admitted_identities(self):
        assert au.ADMITTED_STORE_ID == ADMITTED_STORE_ID
        assert au.ADMITTED_PRODUCER_COMMIT == ADMITTED_PRODUCER_COMMIT

    def test_a_SELF_CONSISTENT_but_UNADMITTED_store_is_REFUSED(self, tmp_path):
        # every internal hash verifies. It is still not the store anybody admitted, and
        # self-consistency is precisely what a forged store also has.
        store = _store(tmp_path)
        with pytest.raises(au.AdmittedUniverseError) as exc:
            au.bind(store_dir=store, universe_targets=TARGETS)
        assert exc.value.reason == au.REFUSE_NOT_THE_ADMITTED_STORE


class TestTheRetiredVocabularyStoreIsRefused:
    """The store this one replaces holds the SAME science and the WRONG tokens.

    It types its rows ``ensembl_gene`` / ``symbol``; Stage 2 serializes ``ensembl_gene_id`` /
    ``gene_symbol``. Exact-token equality — the only honest typed join — then refuses every
    Ensembl row in it, and the lane produces zero edges while every hash inside it verifies.
    Its science was carried forward byte-for-byte into the admitted store, so there is no
    reason to reach for it again — and the refusal says so rather than leaving a bare mismatch.
    """

    def test_the_STALE_store_id_is_on_the_REFUSED_list_with_its_reason(self):
        assert STALE_VOCAB_STORE_ID in au.REFUSED_STORES
        reason = au.REFUSED_STORES[STALE_VOCAB_STORE_ID]
        assert "ensembl_gene_id" in reason and "gene_symbol" in reason
        assert STALE_VOCAB_STORE_ID != au.ADMITTED_STORE_ID

    def test_a_store_carrying_the_STALE_store_id_REFUSES_BY_NAME(self, tmp_path):
        store = _store(tmp_path, store_id=STALE_VOCAB_STORE_ID)
        with pytest.raises(au.AdmittedUniverseError) as exc:
            au.bind(store_dir=store, universe_targets=TARGETS)
        assert exc.value.reason == au.REFUSE_REFUSED_STORE
        assert "RETIRED NAMESPACE VOCABULARY" in str(exc.value)

    def test_a_store_still_speaking_the_RETIRED_TOKENS_does_not_verify(self, tmp_path):
        """Not silently accepted, and not coerced: the token is refused at the store verifier.

        This is the alias layer's absence, made testable. A translation map would have let this
        store through and every test would still be green.
        """
        store = _store(tmp_path, namespace="ensembl_gene")
        targets = [{"target_id": t["target_id"], "target_id_namespace": "ensembl_gene"}
                   for t in TARGETS]
        with pytest.raises(au.AdmittedUniverseError) as exc:
            au.bind(store_dir=store, universe_targets=targets)
        assert exc.value.reason == au.REFUSE_STORE_DID_NOT_VERIFY
        assert "unknown_namespace_token:ENSG1:ensembl_gene" in str(exc.value)

    def test_an_UNKNOWN_token_is_a_NAMED_refusal_never_a_coercion(self, tmp_path):
        store = _store(tmp_path, namespace="entrez_gene_id")
        targets = [{"target_id": t["target_id"], "target_id_namespace": "entrez_gene_id"}
                   for t in TARGETS]
        with pytest.raises(au.AdmittedUniverseError) as exc:
            au.bind(store_dir=store, universe_targets=targets)
        assert exc.value.reason == au.REFUSE_STORE_DID_NOT_VERIFY
        assert "unknown_namespace_token:ENSG1:entrez_gene_id" in str(exc.value)

    def test_the_producer_does_NOT_admit_the_store_it_binds(self, tmp_path):
        store = _store(tmp_path)
        try:
            au.bind(store_dir=store, universe_targets=TARGETS)
        except au.AdmittedUniverseError:
            pass
        # whatever happens, there is no code path on which the producer issues an admission
        assert au.PRODUCER_ADMITS_STORE is False


class TestTheProvenanceGateIsNotFailOpen:
    """d6066b7 shipped the gate's REPORT rather than the gate: verify_from_disk still returned
    ok=True on a deleted provenance. Same store bytes as d268a74, and refused anyway."""

    def test_a_DELETED_provenance_artifact_REFUSES_BY_NAME(self, tmp_path):
        store = _store(tmp_path, delete_provenance=True)
        with pytest.raises(au.AdmittedUniverseError) as exc:
            au.bind(store_dir=store, universe_targets=TARGETS)
        assert exc.value.reason == au.REFUSE_STORE_DID_NOT_VERIFY
        assert "missing_artifact:source_provenance.public.json" in str(exc.value)

    def test_a_MUTATED_provenance_artifact_REFUSES_AT_ITS_HASH(self, tmp_path):
        # the manifest is untouched; only the artifact on disk moved
        store = _store(tmp_path, mutate_provenance=True)
        with pytest.raises(au.AdmittedUniverseError) as exc:
            au.bind(store_dir=store, universe_targets=TARGETS)
        assert exc.value.reason == au.REFUSE_STORE_DID_NOT_VERIFY
        assert "provenance" in str(exc.value)

    def test_a_MISSING_store_directory_REFUSES(self, tmp_path):
        with pytest.raises(au.AdmittedUniverseError) as exc:
            au.bind(store_dir=str(tmp_path / "nope"), universe_targets=TARGETS)
        assert exc.value.reason == au.REFUSE_STORE_NOT_FOUND

    def test_a_universe_the_store_was_NOT_built_against_REFUSES(self, tmp_path):
        # the store binds the typed universe it was extracted for. Serving it a different
        # universe would answer questions about targets it never covered.
        store = _store(tmp_path)
        other = [{"target_id": "ENSG9", "target_id_namespace": "ensembl"}]
        with pytest.raises(au.AdmittedUniverseError) as exc:
            au.bind(store_dir=store, universe_targets=other)
        assert exc.value.reason == au.REFUSE_STORE_DID_NOT_VERIFY
        assert "universe_targets_hash_mismatch" in str(exc.value)


class TestTheBindingBlockSaysWhatItIs:
    def test_the_block_declares_the_producer_is_not_the_admitter(self):
        block = au.binding_block(store_id=ADMITTED_STORE_ID,
                                 verify={"ok": True, "violations": [],
                                         "verify_policy_version": "x"})
        assert block["store_id"] == ADMITTED_STORE_ID
        assert block["admitted_producer_commit"] == ADMITTED_PRODUCER_COMMIT
        assert block["producer_admits_store"] is False
        assert block["admitted_by"] == "independent_verifier"
