"""Exact ordered gene universe shared by X (perturbations) and y (signature).

Plan §6.3 requires an exact, ordered gene intersection between the perturbation
matrix and the target signature, hashed. Plan §6.2.8 requires excluding the
exact A/B panel + control genes, unresolved duplicates, and genes absent from
the perturbation matrix from the readout / evaluation universe.

Canonical key is the Ensembl id (carried by DE_stats ``var/gene_ids``); the
symbol (``var/gene_name``) is used only to look the gene up in the 396k NTC
expression matrix, whose var index is symbols.
"""
from __future__ import annotations

from typing import Iterable

from direct.hashing import content_hash


def build_universe(de_gene_ids: list[str], de_gene_names: list[str],
                   ntc_symbols: Iterable[str],
                   excluded_ensembl: set[str]) -> dict:
    """Return the ordered readout gene universe and its exclusion accounting.

    A DE gene is retained iff:
      - its Ensembl id is not in ``excluded_ensembl`` (A/B panel + control);
      - its symbol resolves to exactly one 396k NTC column;
      - neither its Ensembl id nor its symbol is duplicated among DE genes
        (unresolved duplicates are excluded, §6.2.8).
    Genes absent from the perturbation matrix cannot appear (the DE var IS the
    perturbation-matrix gene axis).
    """
    ntc_index = {}
    dup_ntc: set[str] = set()
    for j, s in enumerate(ntc_symbols):
        s = str(s)
        if s in ntc_index:
            dup_ntc.add(s)
        else:
            ntc_index[s] = j

    # Count duplicate Ensembl / symbol occurrences in the DE axis.
    ens_counts: dict[str, int] = {}
    sym_counts: dict[str, int] = {}
    for e, s in zip(de_gene_ids, de_gene_names):
        ens_counts[str(e)] = ens_counts.get(str(e), 0) + 1
        sym_counts[str(s)] = sym_counts.get(str(s), 0) + 1

    entries = []
    excl = {"in_excluded_panel_control": 0, "symbol_absent_in_ntc": 0,
            "symbol_ambiguous_in_ntc": 0, "duplicate_ensembl": 0,
            "duplicate_symbol": 0}
    for i, (e, s) in enumerate(zip(de_gene_ids, de_gene_names)):
        e, s = str(e), str(s)
        if e in excluded_ensembl:
            excl["in_excluded_panel_control"] += 1
            continue
        if ens_counts[e] > 1:
            excl["duplicate_ensembl"] += 1
            continue
        if sym_counts[s] > 1:
            excl["duplicate_symbol"] += 1
            continue
        if s in dup_ntc:
            excl["symbol_ambiguous_in_ntc"] += 1
            continue
        if s not in ntc_index:
            excl["symbol_absent_in_ntc"] += 1
            continue
        entries.append({"ensembl": e, "symbol": s,
                        "de_col": i, "ntc_col": ntc_index[s]})

    # Canonical ordering by Ensembl id (deterministic; model is order-invariant).
    entries.sort(key=lambda x: x["ensembl"])
    gene_ids = [x["ensembl"] for x in entries]
    return {
        "entries": entries,
        "gene_ids": gene_ids,
        "symbols": [x["symbol"] for x in entries],
        "de_cols": [x["de_col"] for x in entries],
        "ntc_cols": [x["ntc_col"] for x in entries],
        "n_genes": len(entries),
        "exclusion_counts": excl,
        "universe_sha256": content_hash(gene_ids),
    }


def excluded_panel_control(axis: dict) -> set[str]:
    """Exact A/B panel + control Ensembl ids to exclude (drop nulls)."""
    out: set[str] = set()
    for pole in ("A", "B"):
        for key in ("panel_ensembl", "control_ensembl"):
            for g in axis[pole].get(key, []):
                if g:
                    out.add(str(g))
    return out
