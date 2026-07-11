"""Guide-specific intended-target / off-target mask resolution (plan §5.4).

Frozen conservative policy (frozen before inspecting ranks):

  1. resolve contributing guide IDs for a target from the sgRNA library
     (all guides whose target_gene_id == the target Ensembl);
  2. mask the intended target gene;
  3. mask every named gene within the frozen 30-kb neighborhood
     (the library's ``nearby_gene_within_30kb`` column);
  4. mask resolved alternate-alignment / off-target genes;
  5. intersect with the named DE gene universe when emitting.

``neighboring_gene_KD`` and ``distal_offtarget_flag`` are BOOLEAN obs summaries
and are never used as gene identities.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from .hashing import content_hash

_ENSG_RE = re.compile(r"ENSG\d+")


def parse_gene_list(raw: Any) -> list[str]:
    """Parse a stringified gene list.

    The library stores lists either as ``"['ENSG1' 'ENSG2']"`` (numpy repr,
    whitespace separated) or as a plain python list string. Robustly extract
    every Ensembl id.
    """
    if raw is None:
        return []
    s = str(raw)
    if s.strip() in ("", "nan", "[]", "None"):
        return []
    return _ENSG_RE.findall(s)


def _is_missing(v: Any) -> bool:
    if v is None:
        return True
    s = str(v).strip().lower()
    return s in ("", "nan", "none")


def guide_mask_entries(guide_row: dict[str, Any], neighborhood_column: str) -> list[dict]:
    """Return mask entries contributed by a single sgRNA row.

    Each entry: masked_gene_ensembl, reason, distance (nullable), guide id.
    """
    guide_id = guide_row.get("sgRNA")
    row_hash = content_hash({k: (None if _is_missing(v) else str(v))
                             for k, v in sorted(guide_row.items())})
    entries: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(gene: Optional[str], reason: str, distance: Any):
        if _is_missing(gene):
            return
        gene = str(gene)
        if not gene.startswith("ENSG"):
            return
        key = (gene, reason)
        if key in seen:
            return
        seen.add(key)
        dist = None if _is_missing(distance) else float(distance)
        entries.append({
            "masked_gene_ensembl": gene,
            "mask_reason": reason,
            "distance": dist,
            "guide_id": guide_id,
            "source_row_hash": row_hash,
        })

    # 2. intended target
    add(guide_row.get("target_gene_id"), "intended_target",
        guide_row.get("distance_to_closest_target_tss"))
    # 3. named neighbours within the frozen window
    for g in parse_gene_list(guide_row.get(neighborhood_column)):
        add(g, "neighbor_within_30kb", None)
    # 4. resolved off-target alignment
    if not _is_missing(guide_row.get("other_alignment_chromosome")):
        add(guide_row.get("nearest_nontarget_gene_id"), "offtarget_alignment",
            guide_row.get("nearest_nontarget_gene_dist"))
    return entries


def build_target_masks(sgrna_rows_by_target: dict[str, list[dict]],
                       neighborhood_column: str) -> dict[str, dict]:
    """Build a per-target mask by unioning its guides' mask entries.

    Returns target_ensembl -> {
        "gene_set": set[str],            # masked genes (union over guides)
        "entries": list[dict],           # sorted (gene, guide) mask rows
        "guide_ids": list[str],          # contributing guide IDs
    }
    """
    out: dict[str, dict] = {}
    for target, rows in sgrna_rows_by_target.items():
        entries: list[dict] = []
        guide_ids: list[str] = []
        for r in rows:
            gid = r.get("sgRNA")
            if gid is not None and gid not in guide_ids:
                guide_ids.append(str(gid))
            entries.extend(guide_mask_entries(r, neighborhood_column))
        # deterministic sort: gene, then reason, then guide
        entries.sort(key=lambda e: (e["masked_gene_ensembl"], e["mask_reason"],
                                    str(e["guide_id"])))
        out[target] = {
            "gene_set": {e["masked_gene_ensembl"] for e in entries},
            "entries": entries,
            "guide_ids": sorted(guide_ids),
        }
    return out


def fallback_self_mask(target_ensembl: str) -> dict:
    """Minimal mask for a target with no resolvable library guides.

    We still always mask the target's own gene (its Ensembl is known from the
    DE obs), and flag the target as ``unresolved`` upstream.
    """
    entries = [{
        "masked_gene_ensembl": target_ensembl,
        "mask_reason": "intended_target",
        "distance": None,
        "guide_id": None,
        "source_row_hash": None,
    }]
    return {"gene_set": {target_ensembl}, "entries": entries, "guide_ids": []}


def mask_rows_for_emit(target_ensembl: str, condition: str, contrast_id: str,
                       mask: dict, universe: Iterable[str]) -> list[dict]:
    """Intersect a target mask with the gene universe and format emit rows."""
    uni = set(universe)
    rows = []
    for e in mask["entries"]:
        gene = e["masked_gene_ensembl"]
        rows.append({
            "contrast_id": contrast_id,
            "target_ensembl": target_ensembl,
            "condition": condition,
            "guide_id": e["guide_id"],
            "masked_gene_ensembl": gene,
            "mask_reason": e["mask_reason"],
            "distance": e["distance"],
            "in_gene_universe": gene in uni,
            "source_row_hash": e["source_row_hash"],
        })
    rows.sort(key=lambda r: (r["target_ensembl"], r["masked_gene_ensembl"],
                             r["mask_reason"], str(r["guide_id"])))
    return rows
