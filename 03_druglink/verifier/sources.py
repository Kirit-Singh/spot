"""Independent reader and re-parser of the RAW acquisition bytes.

The verifier does not ask the bundle what the sources said. It opens the cached
response bytes itself, hashes them itself, and re-parses them with parsers written
here from the public API shapes — importing NOTHING from ``druglink.adapters``. A
verifier that reused the generator's parser would bless whatever that parser decided
to do today, including a parser that quietly invented a mapping.

Fail-closed on unknown sources: if the bundle carries a source record produced by an
adapter this module cannot independently re-parse, that is a REFUSAL, not a pass. The
verifier never blesses evidence it cannot re-derive.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import canon

MANIFEST_FILE = "acquisition_manifest.json"
QUEUE_FILE = "target_queue.json"

# The adapters this verifier can independently re-parse. Anything else is a refusal.
REPARSEABLE = ("uniprot_search", "chembl_target", "chembl_mechanism",
               "chembl_molecule", "chembl_status")

RECORDS_KEY = {
    "uniprot_search": "results",
    "chembl_target": "targets",
    "chembl_mechanism": "mechanisms",
    "chembl_molecule": "molecules",
    "chembl_status": None,
}

SINGLE_PROTEIN = "SINGLE PROTEIN"

# ChEMBL max_phase -> development state, restated.
_PHASE = {"4": "approved", "3": "phase_3", "2": "phase_2", "1": "phase_1",
          "0": "preclinical"}


class CacheError(ValueError):
    """The acquisition cache is missing, incomplete, or cannot be re-derived."""


def load_cache(cache_root: Optional[str]) -> dict[str, Any]:
    """Open the cache, or refuse. A nonexistent cache is not an empty cache."""
    if not cache_root:
        raise CacheError("no --cache-root was given; Stage-3 evidence cannot be "
                         "verified without the raw acquisition bytes")
    if not os.path.isdir(cache_root):
        raise CacheError(f"acquisition cache directory does not exist: {cache_root}")
    path = os.path.join(cache_root, MANIFEST_FILE)
    if not os.path.exists(path):
        raise CacheError(f"no {MANIFEST_FILE} in the cache root: {cache_root}")
    with open(path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    if not isinstance(manifest, dict) or "entries" not in manifest:
        raise CacheError(f"{MANIFEST_FILE} is not an acquisition manifest")
    return manifest


def read_pages(cache_root: str, manifest: dict[str, Any]) -> dict[str, Any]:
    """Read and HASH every acquired page. Returns {pages, failures}.

    The bytes on disk are the authority. A manifest entry whose declared hash or byte
    count does not reproduce from the bytes is a failure, not a rounding error.
    """
    pages: list[dict[str, Any]] = []
    failures: list[str] = []

    for entry in manifest["entries"]:
        if entry.get("acquisition_status") != "acquired_public":
            continue
        adapter = entry.get("adapter")
        raw_file = entry.get("raw_file")

        if adapter not in REPARSEABLE:
            failures.append(
                f"{adapter}: no independent re-parser exists; the verifier refuses to "
                "bless evidence it cannot re-derive")
            continue
        if not raw_file or os.path.isabs(raw_file):
            failures.append(f"{adapter}: raw_file is missing or is an absolute path")
            continue

        path = os.path.join(cache_root, raw_file)
        if not os.path.exists(path):
            failures.append(f"{raw_file}: cached bytes are missing")
            continue

        with open(path, "rb") as fh:
            data = fh.read()

        actual = canon.sha256_hex(data)
        if actual != entry.get("raw_sha256"):
            failures.append(
                f"{raw_file}: bytes hash to {actual[:12]}, manifest declared "
                f"{str(entry.get('raw_sha256'))[:12]}")
            continue
        if entry.get("raw_bytes") is not None and len(data) != entry["raw_bytes"]:
            failures.append(
                f"{raw_file}: {len(data)} bytes on disk, manifest declared "
                f"{entry['raw_bytes']}")
            continue

        try:
            body = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            failures.append(f"{raw_file}: not UTF-8 JSON ({exc})")
            continue

        pages.append({"entry": entry, "adapter": adapter, "body": body,
                      "raw_sha256": actual, "raw_bytes": len(data)})

    return {"pages": pages, "failures": failures}


def retrieval_timestamps(manifest: dict[str, Any]) -> list[str]:
    """Every acquired page must carry the moment it was ACTUALLY retrieved."""
    missing: list[str] = []
    for entry in manifest["entries"]:
        if entry.get("acquisition_status") != "acquired_public":
            continue
        record = entry.get("access_record") or {}
        stamp = record.get("retrieved_at")
        if not stamp or not isinstance(stamp, str):
            missing.append(str(entry.get("raw_file")))
        elif record.get("http_status") != 200:
            missing.append(f"{entry.get('raw_file')}: http_status "
                           f"{record.get('http_status')}")
    return missing


# --------------------------------------------------------------------------- #
# Independent parsers. Restated from the public response shapes.
# --------------------------------------------------------------------------- #
def parse_uniprot(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Ensembl GeneId cross-references ONLY. A symbol resemblance maps nothing."""
    out: list[dict[str, Any]] = []
    for rec in body.get("results") or []:
        acc = rec.get("primaryAccession")
        if not acc:
            continue
        genes: set[str] = set()
        for xref in rec.get("uniProtKBCrossReferences") or []:
            if xref.get("database") != "Ensembl":
                continue
            for prop in xref.get("properties") or []:
                if prop.get("key") == "GeneId" and prop.get("value"):
                    genes.add(str(prop["value"]).split(".")[0])
        for ensembl in sorted(genes):
            out.append({"kind": "gene_map", "uniprot_id": acc,
                        "target_ensembl": ensembl})
    return out


def parse_chembl_target(body: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tgt in body.get("targets") or []:
        tid, ttype = tgt.get("target_chembl_id"), tgt.get("target_type")
        if not tid or not ttype:
            continue
        out.append({
            "kind": "target_entity",
            "source_target_id": tid,
            "target_type": ttype,
            "is_single_protein": ttype == SINGLE_PROTEIN,
            "accessions": sorted({c["accession"]
                                  for c in (tgt.get("target_components") or [])
                                  if c.get("accession")}),
        })
    return out


def parse_chembl_mechanism(body: dict[str, Any]) -> list[dict[str, Any]]:
    """The source ``action_type`` is carried VERBATIM. Nothing is normalised here."""
    out: list[dict[str, Any]] = []
    for mech in body.get("mechanisms") or []:
        mol = mech.get("molecule_chembl_id")
        if not mol:
            continue
        out.append({
            "kind": "mechanism",
            "source_row_id": (str(mech["mec_id"])
                              if mech.get("mec_id") is not None else None),
            "source_molecule_id": mol,
            "source_target_id": mech.get("target_chembl_id"),
            "action_type_source": mech.get("action_type"),
            "direct_interaction_flag": mech.get("direct_interaction"),
        })
    return out


def parse_chembl_molecule(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Molecule identity + the SOURCED relations that assign an active moiety."""
    out: list[dict[str, Any]] = []
    for mol in body.get("molecules") or []:
        cid = mol.get("molecule_chembl_id")
        if not cid:
            continue
        hierarchy = mol.get("molecule_hierarchy") or {}
        parent = hierarchy.get("parent_chembl_id")
        active = hierarchy.get("active_chembl_id")
        inchikey = (mol.get("molecule_structures") or {}).get("standard_inchi_key")

        cross_cid = cross_unii = None
        for xref in mol.get("cross_references") or []:
            src, xid = xref.get("xref_src"), xref.get("xref_id")
            if not xid:
                continue
            if src in ("PubChem", "PubChem CID") and cross_cid is None:
                cross_cid = str(xid)
            elif src in ("UNII", "FDA SRS") and cross_unii is None:
                cross_unii = str(xid)

        if mol.get("prodrug") == 1 and active and active != cid:
            form_class, relation, target = "prodrug", "is_prodrug_of", active
        elif mol.get("active_metabolite_of"):
            form_class, relation, target = ("active_metabolite",
                                            "is_active_metabolite_of", cid)
        elif parent and parent != cid:
            form_class, relation, target = "salt", "is_salt_of", (active or parent)
        else:
            form_class, relation, target = "parent", "is_parent_of_self", cid

        state = None
        if mol.get("withdrawn_flag"):
            state = "withdrawn"
        elif mol.get("max_phase") is not None:
            state = _PHASE.get(str(mol["max_phase"]))

        out.append({
            "kind": "molecule",
            "chembl_id": cid,
            "inchikey": inchikey,
            "pubchem_cid": cross_cid,
            "unii": cross_unii,
            "form_class": form_class,
            "relation": relation,
            "relation_target": target,
            "preferred_name": mol.get("pref_name"),
            "development_state": state,
        })
    return out


PARSERS = {
    "uniprot_search": parse_uniprot,
    "chembl_target": parse_chembl_target,
    "chembl_mechanism": parse_chembl_mechanism,
    "chembl_molecule": parse_chembl_molecule,
}


def reparse(pages: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Re-derive every record from the raw bytes, grouped by kind."""
    records: dict[str, list[dict[str, Any]]] = {
        "gene_map": [], "target_entity": [], "mechanism": [], "molecule": []}
    for page in pages:
        parser = PARSERS.get(page["adapter"])
        if parser is None:                       # chembl_status carries no records
            continue
        for rec in parser(page["body"]):
            rec["source_record_sha256"] = page["raw_sha256"]
            records[rec["kind"]].append(rec)
    return records
