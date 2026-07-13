"""Bridge to the DepMap Public 26Q1 tumor-cell dependency axis.

The dependency computation itself is OWNED by the Stage-2 DepMap lane
(``02_geneskew/analysis/depmap``), whose official-release catalog is fail-closed and
whose bytes are not yet pinned. This module does NOT recompute dependency and does NOT
pin bytes (that is a reviewed change on that lane). It:

  * carries the pinned release IDENTITY and the GBM/glioma cell-line inclusion rule as
    provenance (the facts that lane's ``config.py`` already fixes: release
    ``depmap_public_26q1`` / "DepMap Public 26Q1", the required release files, and the
    Lineage-tree node membership rule);
  * consumes a per-gene dependency HANDOFF (keyed by stable Ensembl gene id) IF that lane
    produces one, refusing a handoff whose release id does not match the pin and never
    labelling an unverified handoff ``official``;
  * otherwise yields ``None`` metrics, so the tumor axis is ``not_evaluated`` — never a
    fabricated dependency.

Licence: DepMap Public 26Q1 is released CC BY 4.0.
"""
from __future__ import annotations

from typing import Any, Optional

from . import GbmContextError

# Pinned release identity — mirrors 02_geneskew/analysis/depmap/config.py. These are
# facts about which release we would consume, not a claim that its bytes are in hand.
DEPMAP_RELEASE_ID = "depmap_public_26q1"
DEPMAP_RELEASE_NAME = "DepMap Public 26Q1"
DEPMAP_LICENSE = "CC BY 4.0"
DEPMAP_LICENSE_URL = "https://depmap.org/portal/data_page/?tab=allData"
DEPMAP_PORTAL = "https://depmap.org/portal/"
DEPMAP_SOURCE_MODULE = "02_geneskew/analysis/depmap"
REQUIRED_FILES = (
    "Model.csv", "SubtypeTree.csv", "SubtypeMatrix.csv",
    "Gene.csv", "CRISPRGeneEffect.csv", "CRISPRGeneDependency.csv")

# The cell-line inclusion rule, recorded verbatim in intent: the GBM/glioma lineage node
# on the DepMap SubtypeTree (TreeType == "Lineage"); a model is in scope iff it is a
# member of the selected node's own subtype column (never a parent's) in SubtypeMatrix.
CELL_LINE_INCLUSION_RULE = (
    "GBM/glioma lineage: models whose membership column (the selected SubtypeTree node's "
    "own DepmapModelType code, TreeType='Lineage') is set in SubtypeMatrix; dependency is "
    "read from CRISPRGeneDependency (probability >= 0.5 => dependent line) and "
    "CRISPRGeneEffect (Chronos). Node selection + verification is owned by "
    "02_geneskew/analysis/depmap (config.ALLOWED_TREE_TYPE='Lineage').")


def load_dependency_handoff(handoff: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Validate and accept a per-gene dependency handoff, or ``None`` when absent.

    An ``official`` handoff must name the pinned release AND be catalog-verified, or it is
    refused. A synthetic-fixture handoff is accepted for exercising the path but never
    wears an official label."""
    if handoff is None:
        return None
    release_id = handoff.get("release_id")
    source_class = handoff.get("source_class")
    if release_id != DEPMAP_RELEASE_ID:
        raise GbmContextError(
            f"DepMap handoff release_id {release_id!r} does not match pinned "
            f"{DEPMAP_RELEASE_ID!r} — refusing to consume a foreign release.")
    if source_class == "official" and not handoff.get("catalog_verified"):
        raise GbmContextError(
            "DepMap handoff claims source_class=official but is not catalog_verified; "
            "an official dependency axis requires the pinned, verified catalog.")
    if source_class not in ("official", "synthetic_fixture"):
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
    """The DepMap release provenance block, evaluated or not."""
    base = {"release_id": DEPMAP_RELEASE_ID, "release_name": DEPMAP_RELEASE_NAME,
            "license": DEPMAP_LICENSE, "license_url": DEPMAP_LICENSE_URL,
            "portal": DEPMAP_PORTAL, "required_files": list(REQUIRED_FILES),
            "cell_line_inclusion_rule": CELL_LINE_INCLUSION_RULE,
            "source_module": DEPMAP_SOURCE_MODULE}
    if not handoff:
        base.update(evaluated=False, source_class=None,
                    reason="depmap_official_catalog_empty_no_dependency_handoff")
        return base
    base.update(evaluated=True, source_class=handoff.get("source_class"),
                catalog_verified=bool(handoff.get("catalog_verified")))
    return base
