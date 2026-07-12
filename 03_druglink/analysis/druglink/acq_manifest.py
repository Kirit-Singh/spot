"""The acquisition manifest: what was asked, what came back, and under what licence.

Split out of :mod:`druglink.acquire_public` to keep both modules small and to give
the source identities (endpoint, licence, attribution) one home. Nothing here opens
a socket; it assembles and content-addresses the record of an acquisition that has
already happened.
"""
from __future__ import annotations

from typing import Any, Optional

from . import http_public as hp
from .hashing import content_hash

MANIFEST_SCHEMA = "spot.stage03_acquisition_manifest.v1"

# --------------------------------------------------------------------------- #
# Source identities. Carried on EVERY page, not just once in a header.
# --------------------------------------------------------------------------- #
UNIPROT_SEARCH = hp.UNIPROT_ORIGIN + "/uniprotkb/search"
UNIPROT_ENDPOINT = "/uniprotkb/search"
UNIPROT_FIELDS = "accession,reviewed,organism_name,organism_id,xref_ensembl"
UNIPROT_PAGE_SIZE = "500"
UNIPROT_LICENSE = "CC BY 4.0"
UNIPROT_ATTRIBUTION = (
    "The UniProt Consortium. UniProtKB (https://www.uniprot.org). "
    "Database content is licensed under CC BY 4.0.")

CHEMBL_DATA = hp.CHEMBL_ORIGIN + "/chembl/api/data"
CHEMBL_LIMIT = "1000"
CHEMBL_LICENSE = "CC BY-SA 3.0"
CHEMBL_ATTRIBUTION = (
    "ChEMBL (https://www.ebi.ac.uk/chembl/), EMBL-EBI. "
    "Data are licensed under CC BY-SA 3.0.")

# Excluded from the content hash, and ONLY these: when a page was retrieved, and the
# per-response caching/cursor headers. Both stay verbatim in the entry — they are
# excluded from the IDENTITY of the acquisition, not from the RECORD of it.
TIMESTAMP_KEYS = ("created_at", "retrieved_at", "access_record", "response_headers")


def content_sha256(manifest: dict[str, Any]) -> str:
    """Canonical hash with retrieval timestamps and volatile headers excluded.

    Re-running the same frozen acquisition against an unchanged release reproduces
    this hash exactly. (A UniProt query large enough to paginate would carry a
    server-issued cursor in its successor URL; the bounded queries here return one
    page per gene, so no cursor enters the hash.)
    """
    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items()
                    if k not in TIMESTAMP_KEYS and k != "content_sha256"}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    return content_hash(strip(manifest))


def build_manifest(*, artifact_class: str, frozen: dict[str, Any],
                   entries: list[dict[str, Any]], groups: list[dict[str, Any]],
                   uniprot_release: tuple[Optional[str], Optional[str]],
                   chembl_release: Optional[dict[str, Any]],
                   gene_map: dict[str, list[str]], accessions: list[str],
                   target_ids: list[str]) -> dict[str, Any]:
    """Assemble the manifest and bind it to the frozen question it answered."""
    acquired = [e for e in entries if e["acquisition_status"] == "acquired_public"]

    releases: dict[str, Any] = {}
    if uniprot_release[0]:
        releases["uniprot"] = {
            "source_release": uniprot_release[0],
            "source_release_date": uniprot_release[1],
            # The release is what the RESPONSE said, never what a document claimed.
            "read_from": "X-UniProt-Release response header",
            "license": UNIPROT_LICENSE, "attribution": UNIPROT_ATTRIBUTION,
        }
    if chembl_release:
        releases["chembl"] = chembl_release

    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "artifact_class": artifact_class,
        "manifest_id": f"acq_{frozen['acquisition_id']}",
        "acquisition_run_id": frozen["acquisition_id"],
        "acquisition_id": frozen["acquisition_id"],
        "created_at": hp.now_utc(),
        "acquisition_binding": {
            "policy": frozen["policy"],
            "direct_run_id": frozen["direct_binding"]["direct_run_id"],
            "direct_binding_sha256": content_hash(frozen["direct_binding"]),
            "direct_binding": frozen["direct_binding"],
            "target_queue": frozen["target_queue"],
            "target_queue_sha256": frozen["target_queue_sha256"],
            "query_genes": frozen["query_genes"],
            "per_arm_counts": frozen["per_arm_counts"],
        },
        "request_groups": sorted(groups, key=lambda g: (g["kind"],
                                                        g["request_group_id"])),
        "releases": releases,
        "counts": {
            "n_query_targets": len(frozen["target_queue"]),
            "n_query_genes": len(frozen["query_genes"]),
            "n_pages": len(acquired),
            "n_request_groups": len(groups),
            "n_uniprot_accessions": len(accessions),
            "n_single_protein_targets": len(target_ids),
            "n_acquired_public": len(acquired),
            "n_not_acquired": len(entries) - len(acquired),
        },
        "derived": {
            "gene_to_accessions": {g: list(a) for g, a in sorted(gene_map.items())},
            "uniprot_accessions": accessions,
            "chembl_single_protein_targets": target_ids,
        },
        "entries": sorted(entries, key=lambda e: (e["source"], e["adapter"],
                                                  e.get("request_group_id") or "",
                                                  e.get("page_index") or 0)),
    }
    manifest["content_sha256"] = content_sha256(manifest)
    return manifest
