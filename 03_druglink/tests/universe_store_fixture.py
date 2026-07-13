"""The REAL admitted universe store, and the hostile rows the gates must refuse.

Shared by :mod:`test_universe_rows` (TARGET identity: the typed universe and the store on
disk) and :mod:`test_universe_edges` (what happens to a source ASSERTION once its target is
admitted) — the same seam ``druglink.universe_rows`` / ``druglink.universe_edges`` draw.

Two kinds of evidence live here, and they are never mixed:

* **The real store**, discovered on disk and never synthesised. If it is not on this host the
  tests SKIP by name — they do not fall back to a fixture and quietly report a pass over zero
  rows, which is exactly the vacuous green that audit blocker B6 describes.
* **A synthetic store**, built by hand for the semantics that need a hostile row the real
  store does not contain. It is constructed directly rather than loaded, precisely because
  ``load_store`` is the GATED path and cannot be fed a forgery — that being the point of it.

The audited counts and hashes below are LITERALS: a pin computed from the thing it pins is
not a pin, so the expected universe hash is written out rather than recomputed from the store
that is supposed to produce it.
"""
from __future__ import annotations

import copy
import json
import os
import shutil

import pytest

from druglink import universe_rows as ur

# The audited store identity, RE-PINNED onto Stage-2's namespace vocabulary. Literals: a pin
# computed from the thing it pins is not a pin.
#
# The store was re-emitted so it serializes the tokens Stage 2 (W3) serializes —
# `ensembl_gene_id` / `gene_symbol` — because exact-token equality against the retired
# `ensembl_gene` / `symbol` refused every real Ensembl row and yielded ZERO edges. The identity
# MOVED (the typed universe hashes the identity PAIR); the SCIENCE did not, and every count
# below is unchanged because of it.
#
#     store_id            bdf41b69… -> 625c921f…
#     typed universe      5fdbaf58… -> 1c19db2b…
#     scientific content  95f81cb1… == 95f81cb1…   (the namespace projected out)
ADMITTED_STORE_ID = "625c921fce2daf60b69fb0ae33570a9f074a0a0042b1717ee2111f81c1160bff"
ADMITTED_UNIVERSE_SHA = "1c19db2b5d666a8f33c715cb634cf111953c7cdd6c23d082e9b375643a3e7cc8"
EMPTY_UNIVERSE_SHA = "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
SCIENTIFIC_CONTENT_SHA = "95f81cb11abf1b39d9345edb182344f0b90b60e08dd7605145b40c08eda391eb"

# The store this one REPLACES. Same science, retired vocabulary. It must REFUSE.
STALE_VOCAB_STORE_ID = "bdf41b69df2be61d3f625aafa0429e643581fe50823698e77e079054c6145160"
STALE_VOCAB_STORE_DIR = "/home/tcelab/.cache/spot-stage3-universe-real/store"

N_TARGETS, N_ENSG, N_SYMBOL_ONLY = 11_526, 11_522, 4
N_GENERAL, N_VARIANT, N_AMBIGUOUS = 2_227, 29, 6
N_OCCURRENCES, N_UNIQUE_MEC = 2_262, 2_258
N_UNDEFINED_MUTATION = 10                       # variant_id == -1
N_DRUG_EVIDENCE_TARGETS = 505
N_MOLECULES_GENERAL = 1_923
SYMBOL_ONLY = ("MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM")
CALMODULIN = ("ENSG00000143933", "ENSG00000160014", "ENSG00000198668")
AMBIGUOUS_MEC_IDS = (6210, 6862)

# A real ENSG target that carries a NON-EMPTY general drug-evidence edge set. Named so the
# typed join is exercised against real ChEMBL assertions and cannot pass vacuously.
ENSG_WITH_EDGES = "ENSG00000003436"


def _find_store() -> str | None:
    """The ADMITTED (re-pinned) store. Never synthesised, and never the retired-vocabulary one.

    Discovery names exactly the store that is admitted. It deliberately does NOT fall back to
    the old `spot-stage3-universe-real` copy: that store's `store_id` is on the REFUSED list, so
    finding it would only turn a clean skip into a confusing refusal — and the one thing that
    must never happen is a run quietly standing on the store whose vocabulary was retired.
    """
    candidates = [os.environ.get("SPOT_STAGE3_UNIVERSE_STORE"),
                  "/home/tcelab/.cache/spot-stage3-universe-w3tokens/store"]
    for path in candidates:
        if path and os.path.exists(os.path.join(path, ur.MANIFEST_NAME)):
            return path
    return None


STORE_DIR = _find_store()
needs_store = pytest.mark.skipif(
    STORE_DIR is None,
    reason="the admitted universe store is not on this host")

STALE_STORE_DIR = (STALE_VOCAB_STORE_DIR
                   if os.path.exists(os.path.join(STALE_VOCAB_STORE_DIR, ur.MANIFEST_NAME))
                   else None)
needs_stale_store = pytest.mark.skipif(
    STALE_STORE_DIR is None,
    reason="the retired-vocabulary store is not on this host")


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
