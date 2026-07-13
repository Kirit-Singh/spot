"""RE-DERIVE the base deltas, the masks, the QC and the denominators from the INPUTS.

INDEPENDENCE RULE (test-enforced): imports nothing from the generator. The masking rule,
the projection formula, the QC ladder and the contributor join are reimplemented from the
frozen spec (``verify_rules`` / ``verify_project``, the standalone verifier's own copies)
— never borrowed from ``arm_bundle``, ``run_arms`` or ``masks``.

WHAT A BASE DELTA IS, restated from the spec:

    delta_p(X) = mean(P_p \\ M_X) - mean(C_p \\ M_X)

taken on the run's gene universe, where ``M_X`` is the estimate-specific mask: the
INTENDED TARGET, its NEIGHBOURS WITHIN 30 kb, and the ALTERNATE-ALIGNMENT OFF-TARGET of
exactly the guides that CONTRIBUTED to X — never the pooled library union. If the
contributing guides cannot be proven from the contributor manifest, the mask is
unresolved and there is no projection: a silently empty mask is a self-fulfilling one.

One base delta per (program, target), and the two arms are its exact sign transforms. So
this module recomputes the BASE, and ``verify_arm_rules`` derives the arms from it — the
same asymmetry the producer has, arrived at independently.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any, Optional

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import verify_rules as R  # noqa: E402

ENSG = re.compile(r"ENSG\d+")

# The mask window and the column it is read from. Restated, not imported.
MASK_NEIGHBORHOOD_COLUMN = "nearby_gene_within_30kb"
MASK_WINDOW_KB = 30
MASK_REASONS = ("intended_target", "neighbor_within_window", "offtarget_alignment")

MASK_UNRESOLVED = "mask_unresolved"
INSUFFICIENT_AXIS_COVERAGE = "insufficient_axis_coverage"
OK = "ok"


def read_pooled_meta(path: str, condition: str):
    """The gene axis and the obs METADATA for one condition. No dense layer is touched.

    Split from the effect read on purpose. The mask of an estimate is a function of its
    metadata and the contributor manifest — not of the effect matrix — so every target's
    mask (and therefore the run's mask identity) can be re-derived without reading a single
    row of a 16 GB object. Only the PROJECTIONS need the dense layer, and in sample mode
    only a few of those are wanted.
    """
    import h5py
    from verify_source import decode, obs_column

    with h5py.File(path, "r") as fh:
        genes = decode(fh["var/gene_ids"][:])
        obs = fh["obs"]
        cond = obs_column(obs, "culture_condition").astype(object)
        sel = np.sort(np.where(cond == condition)[0])
        meta = {k: obs_column(obs, k)[sel] for k in
                ("target_contrast", "target_contrast_gene_name", "n_cells_target",
                 "n_guides", "ontarget_significant", "low_target_gex")}
        idx = obs.attrs.get("_index", "index")
        meta["released_estimate_id"] = np.array(decode(obs[idx][:]),
                                                dtype=object)[sel]
    return genes, meta, sel


def read_effect_rows(path: str, rows: list[int]):
    """The dense ``log_fc`` for EXACTLY the requested obs rows. Nothing else is read."""
    import h5py

    if not rows:
        return {}
    with h5py.File(path, "r") as fh:
        layer = fh["layers/log_fc"]
        return {r: layer[r, :].astype(np.float64) for r in sorted(rows)}


def read_pooled(path: str, condition: str):
    """Gene axis + metadata + the full effect block. Used where every row is wanted."""
    genes, meta, sel = read_pooled_meta(path, condition)
    effects = read_effect_rows(path, list(sel))
    log_fc = np.vstack([effects[r] for r in sel]) if len(sel) else np.zeros((0, 0))
    return genes, meta, log_fc


def read_library(path: str) -> dict[str, dict[str, dict]]:
    """The sgRNA library, indexed by target gene, FOR MASK LOOKUP ONLY.

    It answers "what does guide X mask?" once the manifest has named X. It never answers
    "which guide is behind slot N": neither row order nor sgRNA-name order is an identity.
    A duplicate sgRNA id for a target is recorded, and makes that target unresolved.
    """
    import pandas as pd

    df = pd.read_csv(path, low_memory=False)
    lib: dict[str, dict[str, dict]] = {}
    dupes: dict[str, set] = {}
    for rec in df.to_dict("records"):
        target = str(rec.get("target_gene_id"))
        if target in ("nan", "None", ""):
            continue
        gid = str(rec["sgRNA"])
        rows = lib.setdefault(target, {})
        if gid in rows:
            dupes.setdefault(target, set()).add(gid)
        rows[gid] = rec
    for target in dupes:
        lib[target] = {}          # a duplicate makes every estimate for that target
    return lib                    # unresolved, rather than silently de-duplicated


def _b(v) -> Optional[bool]:
    if v is None or (isinstance(v, float) and v != v):
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    return bool(v)


def _f(v) -> Optional[float]:
    return R.canonical_num(v)


def mask_genes(guide_ids, lib_rows: dict, target_ensembl: Optional[str]) -> set:
    """The mask of ONE estimate: the union over EXACTLY its contributing guides.

    The intended target is always masked, even if a library row omits it — its own
    repression is QC, never skew evidence.
    """
    genes: set = set()
    for gid in guide_ids:
        row = lib_rows.get(gid)
        if row is None:
            return set()          # a contributing guide with no library row: unresolved
        genes |= R.guide_mask_genes(row, target_ensembl or "")
    if target_ensembl and ENSG.fullmatch(target_ensembl):
        genes.add(target_ensembl)
    return genes


def base_row(*, effect_row, panel: list[str], control: list[str], gene_index: dict,
             mask: Optional[set], n_cells, n_guides, ontarget_significant,
             low_target_gex, target_identity_resolved: bool) -> dict[str, Any]:
    """ONE (program, target) base delta, with the QC that gates it. Pre-outcome."""
    delta, status, n_panel, n_control = R.program_delta(
        effect_row, panel, control, gene_index, mask)
    base_state, base_passed = R.base_qc(
        mask_resolved=mask is not None, n_cells=n_cells,
        ontarget_significant=ontarget_significant, low_expression=low_target_gex,
        n_guides=n_guides, target_identity_resolved=target_identity_resolved)
    return {
        "delta": R.canonical_num(delta),
        "projection_status": status,
        "n_panel_surviving": n_panel,
        "n_control_surviving": n_control,
        "base_state": base_state,
        "base_passed": bool(base_passed),
    }


def recompute(*, de_main: str, sgrna: str, condition: str, programs: dict,
              admitted: list[str], contributors: dict, universe: list[str],
              targets: Optional[set] = None) -> dict[str, Any]:
    """Re-derive every admitted program's base delta for the requested targets.

    ``contributors`` maps a released SCOPE to its proven contributing guide ids; a target
    absent from it has no proven guide identity, so its mask is unresolved and nothing is
    scoreable for it — in every program at once.

    ``targets`` restricts the PROJECTIONS to a deterministic subset (the sample mode);
    ``None`` projects them all (the production mode).

    The MASKS are always re-derived for EVERY target, in both modes. They are a function of
    metadata and the contributor manifest, not of the effect matrix, so they cost nothing —
    and the run's mask identity covers every target, so a mask hash re-derived over only a
    sample would be a different number and could never check the one that was bound.
    """
    genes, meta, sel = read_pooled_meta(de_main, condition)
    library = read_library(sgrna)
    gene_index = {g: i for i, g in enumerate(genes)}
    allowed = set(universe)

    # Every program is projected on the SAME genes, restricted to the run's universe. A
    # program projected on genes the universe does not hold would not be comparable to
    # the one beside it, and these arms are meant to be joined.
    panels = {p: [g for g in map(str, programs[p].get("panel_ensembl") or [])
                  if g in allowed] for p in admitted}
    controls = {p: [g for g in map(str, programs[p].get("control_ensembl") or [])
                    if g in allowed] for p in admitted}

    out: dict[str, dict[str, dict]] = {p: {} for p in admitted}
    evidence: dict[str, dict] = {}
    masked: dict[str, Optional[set]] = {}
    row_of: dict[str, int] = {}

    for i, raw_target in enumerate(meta["target_contrast"]):
        ident = R.target_identity(meta["released_estimate_id"][i], raw_target,
                                  meta["target_contrast_gene_name"][i], None)
        target = ident["target_id"]
        row_of[target] = int(sel[i])

        scope = R.scope_of({
            "estimate_type": R.POOLED_TYPE, "estimate_id": R.POOLED_ID,
            "released_estimate_id": ident["released_estimate_id"],
            "target_id": target,
            "target_id_namespace": ident["target_id_namespace"],
            "target_symbol": ident["target_symbol"],
            "target_ensembl": ident["released_target_ensembl"],
            "condition": condition, "donor_pair": None})

        n_guides = R.canonical_num(meta["n_guides"][i])
        n_guides = None if n_guides is None else int(n_guides)
        n_cells = _f(meta["n_cells_target"][i])
        tens = ident["target_ensembl"]

        guide_ids = contributors.get(scope)
        lib_rows = library.get(tens or "", {})
        # THE CONTRIBUTOR DENOMINATOR: the pooled estimate's own declared guide count must
        # equal the number of guides the manifest actually proves for it. A manifest that
        # names fewer guides than the fit used is not evidence for that fit.
        resolved = bool(guide_ids) and tens is not None and bool(lib_rows) \
            and n_guides is not None and len(guide_ids) == n_guides \
            and all(g in lib_rows for g in guide_ids)
        mask = mask_genes(guide_ids or (), lib_rows, tens) if resolved else None
        if mask is not None and not mask:
            mask = None                       # an empty mask is not a resolved one
        masked[target] = mask

        evidence[target] = {
            "scope": scope,
            "n_guides_declared": n_guides,
            "n_guides_proven": len(guide_ids) if guide_ids else 0,
            "contributor_resolved": resolved,
            "mask_resolved": mask is not None,
            "mask_sha256": (None if mask is None
                            else R.content_sha256(sorted(mask))),
            "n_masked_genes": 0 if mask is None else len(mask),
            "qc": {"n_cells": n_cells, "n_guides": n_guides,
                   "ontarget_significant": _b(meta["ontarget_significant"][i]),
                   "low_target_gex": _b(meta["low_target_gex"][i]),
                   "identity_resolved": ident["target_ensembl"] is not None},
        }

    # ...and only NOW the dense read, for exactly the targets whose deltas are wanted.
    projected = sorted(evidence) if targets is None else sorted(
        t for t in evidence if t in targets)
    effects = read_effect_rows(de_main, [row_of[t] for t in projected])

    for target in projected:
        qc = evidence[target]["qc"]
        for pid in admitted:
            out[pid][target] = base_row(
                effect_row=effects[row_of[target]],
                panel=panels[pid], control=controls[pid],
                gene_index=gene_index, mask=masked[target],
                n_cells=qc["n_cells"], n_guides=qc["n_guides"],
                ontarget_significant=qc["ontarget_significant"],
                low_target_gex=qc["low_target_gex"],
                target_identity_resolved=qc["identity_resolved"])

    return {
        "base_by_program": out,
        "evidence_by_target": evidence,
        # the MASK identity covers every target, in both modes — it is what the run bound
        "mask_sha256": R.content_sha256(
            {t: e["mask_sha256"] for t, e in sorted(evidence.items())}),
        "gene_universe_sha256": R.content_sha256(list(genes)),
        "n_targets": len(evidence),
        "n_projected": len(projected),
    }


def contributors_from_manifest(manifest_doc: dict) -> dict[tuple, list[str]]:
    """The PROVEN contributing guides of each pooled-main scope, from the manifest's rows.

    There is no inference path. A row contributes a guide identity only if it is
    DETERMINED (an ambiguous row is never rounded to a guess), PROVEN (it says how the
    identity was established and over which source bytes), and INCLUDED. A duplicate guide
    within a scope makes that scope unresolved rather than being silently de-duplicated —
    the manifest disagreeing with itself is not evidence.
    """
    rows = manifest_doc.get("rows") or []
    by_scope: dict[tuple, list[str]] = {}
    poisoned: set = set()
    for row in rows:
        if str(row.get("estimate_type")) != R.POOLED_TYPE:
            continue                                  # support is outside this domain
        scope = R.scope_of(row)
        if str(row.get("evidence_state")) != R.DETERMINED:
            poisoned.add(scope)
            continue
        proven = (not R.is_null(row.get("identity_method"))
                  and not R.is_null(row.get("source_sha256")))
        if not proven:
            poisoned.add(scope)
            continue
        if row.get("included") in (False, "false", "False", 0):
            continue
        gid = row.get("guide_id")
        if R.is_null(gid):
            poisoned.add(scope)
            continue
        guides = by_scope.setdefault(scope, [])
        if str(gid) in guides:
            poisoned.add(scope)                       # a duplicate citation, not evidence
            continue
        guides.append(str(gid))
    for scope in poisoned:
        by_scope.pop(scope, None)
    return by_scope


def deterministic_sample(target_ids: list[str], size: int) -> set:
    """A SEEDLESS, reproducible sample: an even stride over the sorted target ids.

    Seedless on purpose — a sample drawn from a PRNG is a sample only the drawer can
    reproduce, and a spot-check nobody else can repeat is not a check.
    """
    ordered = sorted(set(map(str, target_ids)))
    if size <= 0 or size >= len(ordered):
        return set(ordered)
    stride = len(ordered) / size
    return {ordered[min(int(i * stride), len(ordered) - 1)] for i in range(size)}
