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
import glob
import json
import os
import shutil

import pytest

from druglink import universe_rows as ur

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
