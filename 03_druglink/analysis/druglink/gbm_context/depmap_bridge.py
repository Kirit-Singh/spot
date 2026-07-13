"""Bridge to the DepMap Public 26Q1 tumor-cell dependency axis.

The dependency computation is OWNED by the Stage-2 DepMap lane
(``02_geneskew/analysis/depmap``), whose official-release catalog is fail-closed and
currently EMPTY. This module does NOT recompute dependency and does NOT pin bytes. It:

  * fixes the canonical dependency-call rule to MATCH the frozen engine EXACTLY — DepMap
    calls a line dependent iff its dependency probability is STRICTLY greater than 0.5
    (``config.DEPENDENCY_PROB_THRESHOLD=0.5``, ``DEPENDENCY_PROB_STRICT=True``); rounding
    first would flip 0.5000004 to non-dependent, so the raw value is compared strictly;
  * carries the pinned release identity + the GBM/glioma cell-line inclusion rule;
  * consumes a per-gene dependency HANDOFF (keyed by Ensembl id) IF that lane produces one,
    but REFUSES any ``official`` handoff while the official catalog is empty — no coverage
    is claimed until the official 26Q1 catalog is populated;
  * otherwise yields ``None`` metrics, so the tumor axis is ``not_evaluated``.

Licence: DepMap Public 26Q1 is released CC BY 4.0.
"""
from __future__ import annotations

from typing import Any, Optional

from . import GbmContextError

DEPMAP_RELEASE_ID = "depmap_public_26q1"
DEPMAP_RELEASE_NAME = "DepMap Public 26Q1"
DEPMAP_LICENSE = "CC BY 4.0"
DEPMAP_LICENSE_URL = "https://depmap.org/portal/data_page/?tab=allData"
DEPMAP_PORTAL = "https://depmap.org/portal/"
DEPMAP_SOURCE_MODULE = "02_geneskew/analysis/depmap"
REQUIRED_FILES = (
    "Model.csv", "SubtypeTree.csv", "SubtypeMatrix.csv",
    "Gene.csv", "CRISPRGeneEffect.csv", "CRISPRGeneDependency.csv")

# The official-release catalog (02_geneskew/analysis/depmap/official_catalog.json) is EMPTY.
# Until it is populated by that lane's reviewed change, NO official coverage may be claimed.
DEPMAP_OFFICIAL_CATALOG_POPULATED = False

# Frozen-engine dependency-call rule, mirrored EXACTLY from
# 02_geneskew/analysis/depmap/config.py (DEPENDENCY_PROB_THRESHOLD=0.5, STRICT=True).
DEPENDENCY_PROB_THRESHOLD = 0.5
DEPENDENCY_PROB_STRICT = True
DEPENDENCY_PROB_COMPARATOR = ">" if DEPENDENCY_PROB_STRICT else ">="

CELL_LINE_INCLUSION_RULE = (
    "GBM/glioma lineage: models whose membership column (the selected SubtypeTree node's "
    "own DepmapModelType code, TreeType='Lineage') is set in SubtypeMatrix; a line is "
    "called dependent iff its CRISPRGeneDependency probability is STRICTLY greater than 0.5 "
    "(raw value, not rounded); gene effect is read from CRISPRGeneEffect (Chronos). Node "
    "selection + verification is owned by 02_geneskew/analysis/depmap.")


def is_dependent_line(dependency_probability: Optional[float]) -> Optional[bool]:
    """The frozen DepMap dependency call: strictly greater than 0.5, on the RAW probability
    (never rounded). ``None`` (unassayed) stays ``None`` — never counted as non-dependent."""
    if dependency_probability is None:
        return None
    if DEPENDENCY_PROB_STRICT:
        return bool(dependency_probability > DEPENDENCY_PROB_THRESHOLD)
    return bool(dependency_probability >= DEPENDENCY_PROB_THRESHOLD)


def load_dependency_handoff(handoff: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Validate and accept a per-gene dependency handoff, or ``None`` when absent.

    An ``official`` handoff is REFUSED while the official catalog is empty — coverage is not
    claimed until the official 26Q1 catalog is populated. A synthetic-fixture handoff is
    accepted for exercising the path but never wears an official label."""
    if handoff is None:
        return None
    release_id = handoff.get("release_id")
    source_class = handoff.get("source_class")
    if release_id != DEPMAP_RELEASE_ID:
        raise GbmContextError(
            f"DepMap handoff release_id {release_id!r} does not match pinned "
            f"{DEPMAP_RELEASE_ID!r} — refusing to consume a foreign release.")
    if source_class == "official":
        if not DEPMAP_OFFICIAL_CATALOG_POPULATED:
            raise GbmContextError(
                "DepMap official catalog is EMPTY; refusing an 'official' dependency "
                "handoff. No tumor-cell coverage may be claimed until the official 26Q1 "
                "catalog is populated by 02_geneskew/analysis/depmap.")
        if not handoff.get("catalog_verified"):
            raise GbmContextError(
                "DepMap handoff claims source_class=official but is not catalog_verified.")
    elif source_class != "synthetic_fixture":
        raise GbmContextError(
            f"DepMap handoff has unknown source_class {source_class!r}.")
    return handoff


def gene_metrics(handoff: Optional[dict[str, Any]], ensembl_id: str
                 ) -> Optional[dict[str, Any]]:
    """Per-gene dependency metrics for ``ensembl_id``, or ``None`` when not evaluated."""
    if not handoff:
        return None
    rec = (handoff.get("genes") or {}).get(ensembl_id)
    if rec is None:
        return None
    return {"evaluated": True,
            "n_gbm_glioma_lines_evaluated": rec["n_gbm_glioma_lines_evaluated"],
            "n_lines_dependent": rec["n_lines_dependent"],
            "median_gene_effect": rec.get("median_gene_effect"),
            "source_class": handoff.get("source_class")}


def release_provenance(handoff: Optional[dict[str, Any]]) -> dict[str, Any]:
    """The DepMap release provenance block, evaluated or not. Records explicitly whether the
    official catalog is populated and whether any coverage is claimed."""
    base = {"release_id": DEPMAP_RELEASE_ID, "release_name": DEPMAP_RELEASE_NAME,
            "license": DEPMAP_LICENSE, "license_url": DEPMAP_LICENSE_URL,
            "portal": DEPMAP_PORTAL, "required_files": list(REQUIRED_FILES),
            "cell_line_inclusion_rule": CELL_LINE_INCLUSION_RULE,
            "dependency_prob_threshold": DEPENDENCY_PROB_THRESHOLD,
            "dependency_prob_comparator": DEPENDENCY_PROB_COMPARATOR,
            "official_catalog_populated": DEPMAP_OFFICIAL_CATALOG_POPULATED,
            "source_module": DEPMAP_SOURCE_MODULE}
    if not handoff:
        base.update(evaluated=False, coverage_claimed=False, source_class=None,
                    reason="depmap_official_catalog_empty_no_dependency_handoff")
        return base
    sc = handoff.get("source_class")
    base.update(evaluated=True, source_class=sc,
                catalog_verified=bool(handoff.get("catalog_verified")),
                coverage_claimed=(sc == "official"))
    return base
