"""Masks, donor splits and the program projection — REIMPLEMENTED from the spec.

Part of the standalone verifier: imports nothing from the generator. The thresholds and
the ENSG shape are restated here from the frozen spec rather than imported, on purpose —
a constant the checker borrows from the thing it is checking is a constant nobody
checked.
"""
from __future__ import annotations

import re
from typing import Optional

import numpy as np

MIN_PANEL = 1
MIN_CONTROL = 10
ENSG = re.compile(r"ENSG\d+")


def guide_mask_genes(lib_row: dict, target: str) -> set:
    """Intended target + named neighbours + resolved alternate-alignment off-target.
    A boolean flag is never a gene identity."""
    genes = set()
    tgt = lib_row.get("target_gene_id")
    if isinstance(tgt, str) and ENSG.fullmatch(tgt):
        genes.add(tgt)
    if ENSG.fullmatch(target):
        genes.add(target)
    nb = lib_row.get("nearby_gene_within_30kb")
    if isinstance(nb, str):
        genes.update(ENSG.findall(nb))
    alt = lib_row.get("other_alignment_chromosome")
    off = lib_row.get("nearest_nontarget_gene_id")
    if isinstance(alt, str) and alt.strip() not in ("", "nan") \
            and isinstance(off, str) and ENSG.fullmatch(off):
        genes.add(off)
    return genes


def complementary_splits(pair_ids: list[str]) -> list[tuple[str, str]]:
    members = {p: frozenset(p.split("_")) for p in pair_ids}
    donors = frozenset(d for m in members.values() for d in m)
    by_set = {s: p for p, s in members.items()}
    out, seen = [], set()
    for pair in sorted(pair_ids):
        if pair in seen:
            continue
        mate = by_set.get(donors - members[pair])
        if mate is None or mate == pair:
            seen.add(pair)
            continue
        seen.update({pair, mate})
        out.append(tuple(sorted((pair, mate))))
    return sorted(out)


def program_delta(effect_row, panel: list[str], control: list[str], index: dict,
                  mask: Optional[set]):
    """Returns (delta, status, n_panel_surviving, n_control_surviving).

    An unresolved mask yields NO counts: there is nothing to have survived.
    """
    if mask is None:
        return None, "mask_unresolved", None, None
    pc = [index[g] for g in panel if g in index and g not in mask]
    cc = [index[g] for g in control if g in index and g not in mask]
    if len(pc) < MIN_PANEL or len(cc) < MIN_CONTROL:
        return None, "insufficient_axis_coverage", len(pc), len(cc)
    mean_p = float(np.mean(effect_row[pc]))
    mean_c = float(np.mean(effect_row[cc]))
    return mean_p - mean_c, "ok", len(pc), len(cc)
