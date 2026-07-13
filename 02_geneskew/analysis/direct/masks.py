"""Estimate-specific intended-target / off-target masks.

A mask belongs to ONE estimate (main, one guide slot, or one donor-pair), and is
the union of the mask entries of exactly the guides that contributed to that
estimate — never the pooled library union. If the contributing guides are
unresolved (``guides.py``), the mask is unresolved: no gene set, no score.

``neighboring_gene_KD`` and ``distal_offtarget_flag`` are BOOLEAN obs summaries.
They say a row *has* such an effect, never *which* gene: the gene-list parser
refuses booleans outright so a flag can never become a gene identity.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from . import config
from .guides import Contributors, Estimate, LibraryTarget
from .hashing import content_hash

_ENSG_RE = re.compile(r"ENSG\d+")

INTENDED_TARGET = "intended_target"
NEIGHBOR = "neighbor_within_window"
OFFTARGET_ALIGNMENT = "offtarget_alignment"


def parse_gene_list(raw: Any) -> list[str]:
    """Parse a stringified Ensembl-gene list from the sgRNA library.

    Refuses booleans: the source's off-target *flags* are booleans and must never
    be coerced into a gene identity.
    """
    if raw is None or isinstance(raw, bool):
        return []
    if isinstance(raw, (int, float)):
        return []
    if isinstance(raw, (list, tuple, set)):
        return [g for g in (str(x) for x in raw) if _ENSG_RE.fullmatch(g)]
    s = str(raw)
    if s.strip() in ("", "nan", "[]", "None", "True", "False"):
        return []
    return _ENSG_RE.findall(s)


def _is_missing(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, bool):
        return True          # a boolean is never an identifier
    s = str(v).strip().lower()
    return s in ("", "nan", "none")


def guide_mask_entries(guide_row: dict[str, Any],
                       neighborhood_column: str) -> list[dict]:
    """Mask entries contributed by ONE sgRNA row."""
    guide_id = guide_row.get("sgRNA")
    guide_id = None if _is_missing(guide_id) else str(guide_id)
    row_hash = content_hash({k: (None if _is_missing(v) else str(v))
                             for k, v in sorted(guide_row.items())})
    entries: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(gene: Any, reason: str, distance: Any) -> None:
        if _is_missing(gene):
            return
        gene = str(gene)
        if not _ENSG_RE.fullmatch(gene):
            return
        if (gene, reason) in seen:
            return
        seen.add((gene, reason))
        try:
            dist = None if _is_missing(distance) else float(distance)
        except (TypeError, ValueError):
            dist = None
        entries.append({
            "masked_gene_ensembl": gene,
            "mask_reason": reason,
            "distance": dist,
            "guide_id": guide_id,
            "source_row_hash": row_hash,
        })

    add(guide_row.get("target_gene_id"), INTENDED_TARGET,
        guide_row.get("distance_to_closest_target_tss"))
    for gene in parse_gene_list(guide_row.get(neighborhood_column)):
        add(gene, NEIGHBOR, None)
    if not _is_missing(guide_row.get("other_alignment_chromosome")):
        add(guide_row.get("nearest_nontarget_gene_id"), OFFTARGET_ALIGNMENT,
            guide_row.get("nearest_nontarget_gene_dist"))
    return entries


def build_estimate_mask(est: Estimate, contrib: Contributors,
                        lib: Optional[LibraryTarget],
                        neighborhood_column: str = config.MASK_NEIGHBORHOOD_COLUMN) -> dict:
    """Build the mask of ONE estimate from ONLY its contributing guides.

    Returns ``{"resolved", "reason", "gene_set", "entries", "guide_ids"}``.
    When unresolved, ``gene_set`` is None so no caller can project with a silently
    empty mask.
    """
    if not contrib.resolved or lib is None:
        return {"resolved": False, "reason": contrib.reason, "gene_set": None,
                "entries": [], "guide_ids": []}

    entries: list[dict] = []
    for gid in contrib.guide_ids:
        row = lib.rows.get(gid)
        if row is None:
            return {"resolved": False, "reason": "contributing_guide_row_missing",
                    "gene_set": None, "entries": [], "guide_ids": []}
        entries.extend(guide_mask_entries(row, neighborhood_column))

    # The intended target is always masked, even if a library row omits it: its
    # own repression is QC, never skew evidence.
    if est.target_ensembl is not None and not any(
            e["masked_gene_ensembl"] == est.target_ensembl
            and e["mask_reason"] == INTENDED_TARGET for e in entries):
        if _ENSG_RE.fullmatch(est.target_ensembl):
            entries.append({
                "masked_gene_ensembl": est.target_ensembl,
                "mask_reason": INTENDED_TARGET,
                "distance": None,
                "guide_id": None,
                "source_row_hash": None,
            })

    entries.sort(key=lambda e: (e["masked_gene_ensembl"], e["mask_reason"],
                                str(e["guide_id"])))
    return {
        "resolved": True,
        "reason": None,
        "gene_set": {e["masked_gene_ensembl"] for e in entries},
        "entries": entries,
        "guide_ids": list(contrib.guide_ids),
    }


def estimate_mask_sha256(mask: dict) -> Optional[str]:
    """THIS estimate's mask, as one id: the exact gene SET removed from its projection.

    The run-level ``mask_sha256`` hashes every mask in the run at once, which cannot
    answer the only question a reader of one row actually has: *which genes were removed
    from THIS target's projection*. Without a per-estimate id the screen is not
    self-describing — you must join it back to masks.parquet to find out what was masked,
    and a screen that cannot state its own mask is a screen you have to trust.

    The id is over the GENE SET, not over (gene, reason). Deliberately: the gene set is
    what changes the numbers — it is exactly what is subtracted from the panel and control
    means — whereas the reason is provenance for why a gene is in it. Hashing the reasons
    in would also make the id unverifiable: the standalone verifier reconstructs which
    genes a guide masks, not the label it was filed under, so an id it cannot re-derive is
    an id nothing independent can check. The reasons stay in masks.parquet, where they are
    compared row by row.

    Null on an unresolved mask, never an empty-set hash. An empty mask and an absent one
    are opposite claims — "nothing needed removing" versus "we could not tell what to
    remove" — and giving them the same id would let a projection that refused to run look
    identical to one that ran and masked nothing.
    """
    if not mask["resolved"]:
        return None
    return content_hash(sorted(mask["gene_set"]))


def mask_rows_for_emit(est: Estimate, mask: dict, universe: Iterable[str],
                       run_id: str) -> list[dict]:
    """Emit the mask rows of one estimate, intersected with the gene universe.

    An unresolved estimate emits exactly one row carrying its reason, so every
    estimate is represented in masks.parquet.
    """
    uni = set(universe)
    base = {
        "run_id": run_id,
        "estimate_type": est.estimate_type,
        "estimate_id": est.estimate_id,
        "released_estimate_id": est.released_estimate_id,
        "target_id": est.target_id,
        "target_ensembl": est.target_ensembl,
        "condition": est.condition,
        "donor_pair": est.donor_pair,
    }
    if not mask["resolved"]:
        return [dict(base, guide_id=None, masked_gene_ensembl=None,
                     mask_reason="mask_unresolved", distance=None,
                     in_gene_universe=None, source_row_hash=None,
                     mask_unresolved_reason=mask["reason"])]
    rows = [dict(base,
                 guide_id=e["guide_id"],
                 masked_gene_ensembl=e["masked_gene_ensembl"],
                 mask_reason=e["mask_reason"],
                 distance=e["distance"],
                 in_gene_universe=e["masked_gene_ensembl"] in uni,
                 source_row_hash=e["source_row_hash"],
                 mask_unresolved_reason=None)
            for e in mask["entries"]]
    rows.sort(key=lambda r: (r["estimate_type"], r["estimate_id"],
                             r["target_id"], str(r["masked_gene_ensembl"]),
                             r["mask_reason"], str(r["guide_id"])))
    return rows


# --------------------------------------------------------------------------- #
# THE CANONICAL MASK TABLE — one order, used to serialize AND to hash.
#
# W10's counterexample: the bound mask hash was taken over the rows in the order the producer
# happened to build them (`mask_rows_for_emit` sorts only WITHIN one estimate; the full list is
# a concatenation in target-iteration order), while the shipped `masks.parquet` was written
# through a sort over six of the fourteen identity columns.
#
# Two consequences, and they are the same defect seen from either end:
#
#   * a verifier reading the shipped file could NOT reproduce `mask_sha256` — the one thing
#     binding it exists to permit;
#   * the same rows in a different order gave a DIFFERENT bound hash, so the bundle's identity
#     moved without a single number changing.
#
# The six-column sort was not even a total order: two rows tying on it were left in whatever
# order the producer iterated, so the shipped BYTES were input-order-dependent too.
#
# So there is now ONE canonical table. It is sorted over the FULL identity column tuple, the
# parquet is serialized FROM it, and the hash is taken OF it. A reader of the file can apply
# the same projection and get the bound hash — which is the whole point.
# --------------------------------------------------------------------------- #
MASK_ORDER_RULE_ID = "spot.stage02.direct.mask_row_order.full_identity_columns.v1"
MASK_ORDER_RULE = (
    "mask rows are ordered by the FULL identity column tuple (MASK_ROW_COLUMNS), nulls last "
    "within each column; the shipped parquet is serialized from that exact table and "
    "mask_sha256 is the canonical content hash of that exact table")

# Every column that identifies a mask row. The run id is NOT one of them: it is assigned after
# the mask is known, and a mask that changed when it was named would not be a mask.
MASK_ROW_COLUMNS = (
    "estimate_type", "estimate_id", "released_estimate_id", "target_id",
    "target_ensembl", "condition", "donor_pair", "guide_id",
    "masked_gene_ensembl", "mask_reason", "distance", "in_gene_universe",
    "source_row_hash", "mask_unresolved_reason",
)

RUN_ID_COLUMNS = ("run_id", "arm_bundle_run_id")


def _norm(v: Any) -> Any:
    """The value as a READER of the shipped parquet must see it.

    Parquet round-trips a missing float to NaN and an integer to numpy int64, so hashing the
    in-memory dicts would bind numbers nobody reading the file could reproduce — the same
    "a count nobody can recount" defect this lane has been bitten by before.
    """
    if isinstance(v, (str, bytes)):
        return v.decode() if isinstance(v, bytes) else v
    if hasattr(v, "item"):                       # numpy / pandas scalar -> python primitive
        try:
            v = v.item()
        except (ValueError, AttributeError):
            pass
    if v is None:
        return None
    try:
        if v != v:                               # NaN, and pandas NA
            return None
    except (TypeError, ValueError):
        return None
    if isinstance(v, bool):
        return bool(v)
    if isinstance(v, float):
        return float(v)
    if isinstance(v, int):
        return int(v)
    return str(v)


def _order_key(row: dict[str, Any]) -> tuple:
    """A TOTAL order over the identity columns. Nulls last, and never a tie left to chance."""
    return tuple((row[c] is None, "" if row[c] is None else str(row[c]))
                 for c in MASK_ROW_COLUMNS)


def canonical_mask_rows(rows: Iterable[dict]) -> list[dict]:
    """THE mask table: projected onto the identity columns, normalised, totally ordered."""
    out = [{c: _norm(r.get(c)) for c in MASK_ROW_COLUMNS} for r in rows]
    out.sort(key=_order_key)
    return out


def mask_content_sha256(rows: Iterable[dict]) -> str:
    """The mask's content hash, taken over the canonical table the producer also ships."""
    return content_hash(canonical_mask_rows(rows))
