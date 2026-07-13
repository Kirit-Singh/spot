"""Stage-3 (Drugs) Methods & Provenance drawer payload.

Emits the compact machine-readable ``StageMethodsManifest`` the shared header drawer consumes
(_frontend/src/domain/methodsManifest.ts), canonicalised byte-exactly the way the UI recomputes
it (_frontend/src/stage1/canonical.ts):

    json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=True, allow_nan=False)

so W12 can PIN the resulting sha256 in ``STAGE_METHODS_HASHES.drugs`` and the adapter's
fail-closed content gate accepts it. A one-byte mutation of any bound value invalidates it.

RULES HONOURED. Nothing is invented: a genuinely-absent field stays ``None`` and the drawer
renders "unavailable". No editorial prose — limitations are compact factual rows. No combined
/ overall rank. No disease claim beyond what the pinned Open Targets bytes report. The run-
status fields stay null because NO admitted Stage-3 candidate bundle is bound to the page (a
reproduce command may be shown only when it reproduces the admitted bound artifact).

Existing drug-link strings are carried VERBATIM from the current drugs manifest; the one stale
limitation ("Open Targets ... not [wired]") is corrected, because Open Targets disease
association is now wired and DepMap is explicitly not_evaluated.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

# Pinned in stageMethods.ts as SOURCE_TISSUE.drugs and inside the hashed manifest; it must
# match domain stageSourceTissue('Drugs') byte-for-byte or the content gate rejects.
SOURCE_TISSUE_DRUGS = (
    "Biological input is the Stage-2 program/perturbation result from the Marson "
    "primary-human-CD4 dataset; drug evidence comes from separately listed public sources.")

STAGE_LABEL_DRUGS = "Drugs"


def canonical_json(obj: Any) -> str:
    """Byte-exact replica of the UI's canonicalJson (sorted keys, no spaces, ASCII-escaped)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def content_sha256(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def _src(label: str, record_id: str, *, url: Optional[str] = None,
         license: Optional[str] = None, retrieval_utc: Optional[str] = None,
         raw_sha256: Optional[str] = None,
         canonical_sha256: Optional[str] = None) -> dict[str, Any]:
    return {"label": label, "record_id": record_id, "url": url, "license": license,
            "retrieval_utc": retrieval_utc, "raw_sha256": raw_sha256,
            "canonical_sha256": canonical_sha256}


def build_manifest(*, ot_retrieval_utc: str, ot_response_set_canonical_sha256: str
                   ) -> dict[str, Any]:
    """The Drugs-stage drawer manifest: existing drug-link content + the GBM disease-context.

    ``ot_response_set_canonical_sha256`` content-addresses the pinned Open Targets response
    set (the handoff's ``raw_response_artifacts``, each response individually sha256'd), so
    every displayed disease number traces to exact public bytes.
    """
    return {
        "stage_label": STAGE_LABEL_DRUGS,
        "methods": {
            "data_input": (
                "Requires an admitted, re-hashed Stage-2 Direct run mapped to a frozen "
                "offline drug-evidence cache (top-25 targets per arm) from UniProt + ChEMBL; "
                "optional Stage-2 pathway-hypothesis document. GBM disease-context overlay: "
                "the selected Stage-2 arm genes (Ensembl ids) joined to Open Targets 26.06 "
                "disease association; DepMap Public 26Q1 tumor-cell dependency is consumed "
                "only from an official, catalog-verified handoff."),
            "source_tissue": SOURCE_TISSUE_DRUGS,
            "estimand": (
                "Direction-aware target⟷drug link: each Stage-2 screen row becomes exactly "
                "two arm-lever rows; ENSG⟷UniProt⟷ChEMBL SINGLE PROTEIN identity join "
                "(complexes/families refused); action_type carried verbatim and max_phase "
                "carried, never recomputed by spot; no combined / headline / overall score; "
                "direct_target (observed_perturbation) and pathway_node (pathway_hypothesis) "
                "origins are never merged. Offline join, no per-click API. GBM disease-context "
                "(descriptive, non-gating): per gene, joined on Ensembl id and never a symbol, "
                "three SEPARATE axes — immune perturbation direction (Stage-2 arm), "
                "tumor-cell dependency across named GBM/glioma cell lines (DepMap 26Q1), and "
                "disease association to glioblastoma (MONDO_0018177) / glioma (MONDO_0021042) "
                "(Open Targets 26.06) — plus a typed SUGGESTIVE compatibility category; the "
                "axes never fuse into a score and missing evidence stays not_evaluated."),
            "masks_qc": (
                "Frozen identity join: human Ensembl ⟷ UniProt ⟷ ChEMBL at the SINGLE "
                "PROTEIN level only (complexes / families refused); action_type is carried "
                "verbatim and max_phase is carried, never recomputed by spot. Open Targets "
                "acquisition is fail-closed on data-version drift (pinned 26.06) and refuses "
                "target mis-attribution; every disease number binds to its pinned raw response "
                "sha256."),
            "upstream_model": (
                "Required upstream: an admitted Stage-2 Direct run — two independent arms "
                "(away_from_A / toward_B)."),
            "limitations": [
                ("Only UniProt identity + ChEMBL mechanism are wired for target→drug; "
                 "ChEMBL activity, DGIdb, DrugBank and DepMap-PRISM drug sensitivity are not."),
                ("ChEMBL is CC BY-SA 3.0 (ShareAlike): redistributed ChEMBL-derived fields "
                 "inherit attribution and ShareAlike obligations."),
                ("GBM disease-context is descriptive: it never ranks, gates, or alters Stage-2 "
                 "immune-perturbation ranks, and emits no combined or overall score."),
                ("Open Targets association scores are upstream-reported evidence "
                 "(used_for_gating_or_ranking = false); no p/q is emitted, and an association "
                 "is not a causal or therapeutic claim."),
                ("Tumor-cell dependency is not_evaluated: the DepMap Public 26Q1 official "
                 "catalog is empty (0 entries), so no GBM/glioma cell-line coverage is claimed."),
                ("DepMap dependency call is strictly greater than 0.5 on the raw probability "
                 "(never rounded), matching the frozen engine."),
            ],
            "method_id": ("stage3-druglink-v4-workflow-states · schema "
                          "spot.stage03_drug_annotation.v1 · gbm-context "
                          "spot.stage03.gbm_context.v1"),
            # No admitted Stage-3 candidate bundle is bound to this page, so the run identity
            # and a bound-artifact reproduce command remain genuinely unavailable.
            "method_code_sha256": None,
            "environment": None,
            "last_run_utc": None,
            "reproduce_command": None,
        },
        "provenance": {
            "release_revision": None,
            "raw_sha256": None,
            "canonical_sha256": None,
            "generator_status": None,
            "verifier_status": None,
            "cs_notebook_url": None,
            "artifact_paths": [],
            "source_chain": [
                _src("ChEMBL 37", "chembl_37",
                     url=("https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/"
                          "chembl_37/"),
                     license="CC BY-SA 3.0"),
                _src("UniProt 2026_02", "uniprot_2026_02",
                     url="https://www.uniprot.org/release-notes/2026-06-10-release",
                     license="CC BY 4.0"),
                # Wired + traced: canonical_sha256 content-addresses the pinned response set
                # (each raw response individually sha256'd in the run handoff).
                _src("Open Targets Platform 26.06", "open_targets_26_06",
                     url="https://api.platform.opentargets.org/api/v4/graphql",
                     license="CC0 1.0",
                     retrieval_utc=ot_retrieval_utc,
                     canonical_sha256=ot_response_set_canonical_sha256),
                # Declared, NOT retrieved: official catalog empty -> no coverage claimed, so
                # every hash stays null rather than being invented.
                _src("DepMap Public 26Q1", "depmap_public_26q1",
                     url="https://depmap.org/portal/data_page/?tab=allData",
                     license="CC BY 4.0"),
            ],
        },
    }
