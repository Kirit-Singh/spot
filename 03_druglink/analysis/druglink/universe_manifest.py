"""The RUN-INDEPENDENT universe manifest.

Unlike :mod:`druglink.acq_manifest` (bound to one ``direct_run_id`` and its per-arm
queue), this manifest is bound to the SOURCE RELEASES and the typed perturbation-target
universe — nothing about any selection. A per-run view (``universe_store.view_for_queue``)
is a downstream selection over the store; it never re-binds the store to a run.

Licenses are packaged SEPARATELY: ChEMBL-derived evidence is CC BY-SA 3.0 (ShareAlike,
with REQUIRED.ATTRIBUTION — preserve ChEMBL IDs and display the release), UniProt-derived
identity is CC BY 4.0. The cache DATA is not the code's MIT license.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

from .hashing import content_hash

UNIVERSE_MANIFEST_SCHEMA = "spot.stage03_universe_manifest.v1"

CHEMBL_LICENSE = "CC BY-SA 3.0"
CHEMBL_ATTRIBUTION = (
    "ChEMBL (https://www.ebi.ac.uk/chembl/), EMBL-EBI. Data licensed CC BY-SA 3.0. "
    "REQUIRED.ATTRIBUTION: preserve ChEMBL IDs and clearly display the ChEMBL release. "
    "Cite Mendez D. et al., Nucleic Acids Res. 2019;47(D1):D930-D940, "
    "DOI 10.1093/nar/gky1075.")
CHEMBL_DOI = "10.6019/CHEMBL.database.37"
UNIPROT_LICENSE = "CC BY 4.0"
UNIPROT_ATTRIBUTION = (
    "The UniProt Consortium. UniProtKB (https://www.uniprot.org). "
    "Database content licensed CC BY 4.0.")

# Excluded from the content identity (record, not identity) — nothing else.
_TIMESTAMP_KEYS = ("created_at",)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def universe_targets_sha256(universe_targets: list[dict[str, str]]) -> str:
    """Hash of the TYPED universe: every target as {target_id, target_id_namespace},
    canonically sorted. All 11,526 targets (incl. the 4 symbol-only) are hashed rows."""
    typed = sorted(
        ({"target_id": t["target_id"],
          "target_id_namespace": t["target_id_namespace"]} for t in universe_targets),
        key=lambda r: (r["target_id_namespace"], r["target_id"]))
    return content_hash(typed)


def content_sha256(manifest: dict[str, Any]) -> str:
    """Canonical identity with retrieval timestamps and the self-hash excluded."""
    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items()
                    if k not in _TIMESTAMP_KEYS and k != "content_sha256"}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node
    return content_hash(strip(manifest))


def build_universe_manifest(
    *,
    chembl_release: str, chembl_source_sha256: str,
    uniprot_release: str, uniprot_source_sha256: str,
    extraction_query_sha256: str,
    universe_targets: list[dict[str, str]],
    coverage: dict[str, Any],
    store_rows_sha256: str,
    eligibility_evidence_sha256: str | None = None,
    public_source_provenance_sha256: str | None = None,
) -> dict[str, Any]:
    n_ensg = sum(1 for t in universe_targets
                 if t["target_id_namespace"] == "ensembl_gene")
    n_symbol = len(universe_targets) - n_ensg
    uni_sha = universe_targets_sha256(universe_targets)

    manifest = {
        "schema_version": UNIVERSE_MANIFEST_SCHEMA,
        "run_independent": True,
        "created_at": _now(),
        "releases": {
            "chembl": {
                "source_release": chembl_release,
                "source_sha256": chembl_source_sha256,
                "license": CHEMBL_LICENSE, "attribution": CHEMBL_ATTRIBUTION,
                "doi": CHEMBL_DOI, "derived_layer": "chembl_drug_evidence",
            },
            "uniprot": {
                "source_release": uniprot_release,
                "source_sha256": uniprot_source_sha256,
                "license": UNIPROT_LICENSE, "attribution": UNIPROT_ATTRIBUTION,
                "derived_layer": "uniprot_identity",
            },
        },
        "license_packaging": {
            "chembl_derived_layer_license": CHEMBL_LICENSE,
            "uniprot_derived_layer_license": UNIPROT_LICENSE,
            "cache_data_is_not_code_mit_license": True,
            "sharealike_scope_is_a_release_compliance_question": True,
        },
        "universe_binding": {
            "typed_universe": True,
            "n_targets_total": len(universe_targets),
            "n_ensg": n_ensg,
            "n_symbol_only": n_symbol,
            "universe_targets_sha256": uni_sha,
        },
        "coverage": coverage,
        "extraction": {"extraction_query_sha256": extraction_query_sha256,
                       "store_rows_sha256": store_rows_sha256,
                       "eligibility_evidence_sha256": eligibility_evidence_sha256,
                       "public_source_provenance_sha256": public_source_provenance_sha256},
        # store_id binds the TYPED universe + both source releases + method + the
        # eligibility evidence + the sanitized public source provenance.
        "store_id": content_hash({
            "extraction_query_sha256": extraction_query_sha256,
            "chembl_source_sha256": chembl_source_sha256,
            "uniprot_source_sha256": uniprot_source_sha256,
            "universe_targets_sha256": uni_sha,
            "store_rows_sha256": store_rows_sha256,
            "eligibility_evidence_sha256": eligibility_evidence_sha256,
            "public_source_provenance_sha256": public_source_provenance_sha256,
        }),
    }
    manifest["content_sha256"] = content_sha256(manifest)
    return manifest
