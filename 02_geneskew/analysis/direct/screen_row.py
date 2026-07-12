"""One complete disposition record per SOURCE target.

Carries BASE QC once, then each arm's own score, evaluability, support, direction and
tier. There is no combined score and no headline rank.

Support is UNAVAILABLE in this pass (``domain.py``): the by-guide and donor-pair
estimates carry no contributor evidence, so they were never projected. Every arm is
therefore built with ``support_available=False`` — no replication claim, no donor-split
claim, and no path above tier 3.
"""
from __future__ import annotations

from typing import Any

from . import arms, config, disposition, emit
from . import projection as proj
from .hashing import round_float


def _f(v):
    import numpy as np
    if v is None:
        return None
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(fv) else fv


def _b(v):
    return None if v is None else bool(v)


def screen_row(*, ident, i, meta, cond, mask, contrib, deltas, zdeltas, scores,
                zscores, base_state, base_passed, base_reasons, slots, pair_values,
                splits, n_guides) -> dict[str, Any]:
    """One complete disposition record per SOURCE target.

    Carries BASE QC once, then each arm's own score, evaluability, support,
    direction and tier. There is no combined score and no headline rank.
    """
    row = {
        "schema_version": emit.SCHEMA_SCREEN,
        "run_id": None,                     # filled once the run is named
        # --- target identity, honestly named ---
        "released_estimate_id": ident.released_estimate_id,   # exact obs.index
        "target_id": ident.target_id,                          # exact target_contrast
        "target_id_namespace": ident.target_id_namespace,
        "target_symbol": ident.target_symbol,
        "target_ensembl": ident.target_ensembl,                # nullable
        "condition": cond,
        # --- base QC (pre-outcome; a function of NEITHER arm) ---
        "base_qc_state": base_state,
        "base_qc_passed": base_passed,
        "base_qc_reasons": ";".join(base_reasons),
        # --- contributing-guide contract ---
        "mask_resolved": mask["resolved"],
        "mask_unresolved_reason": mask["reason"],
        "mask_gene_count": (None if not mask["resolved"] else len(mask["gene_set"])),
        "contributing_guide_ids": ";".join(contrib.guide_ids),
        "contributor_status": contrib.status,
        "contributor_source": contrib.source,
        # --- source QC (kept separate from the Stage-2 projection) ---
        "n_cells_target": round_float(_f(meta["n_cells_target"][i])),
        "n_guides_source": (None if n_guides is None else int(n_guides)),
        "qc_ontarget_significant": _b(meta["ontarget_significant"][i]),
        "qc_ontarget_effect_size": round_float(_f(meta["ontarget_effect_size"][i])),
        "qc_low_target_expression": _b(meta["low_target_gex"][i]),
        "qc_target_baseMean": round_float(_f(meta["target_baseMean"][i])),
        "source_distal_offtarget_flag": _b(meta["distal_offtarget_flag"][i]),
        "source_neighboring_gene_KD": _b(meta["neighboring_gene_KD"][i]),
        "effective_donor_n": splits["n_donors"],
        "crispri_modality": config.CRISPRI_MODALITY,
        "inference_status": config.INFERENCE_STATUS,
        "cell_level_support_state": "screen_only",   # cell-level lane deferred
    }

    # --- the two arms, built by the SAME code path, sharing nothing ---
    for pole in ("A", "B"):
        arm = arms.arm_of_pole(pole)
        row.update(arms.arm_fields(
            pole=pole, value=scores[arm], delta=deltas[pole],
            base_state=base_state, base_passed=base_passed, slots=slots,
            pair_values=pair_values, splits=splits["splits"],
            zscore_value=zscores[arm],
            # support has no contributor evidence in this pass: no replication claim,
            # no donor-split claim, and no path above tier 3
            support_available=False))

    # --- descriptive only: never ranks, never gates, raw values stay alongside ---
    row["concordance_class"] = proj.concordance_class(
        {a: row[a] for a in config.ARMS}, config.SIGN_EPS)
    row["desired_modulation_agreement"] = disposition.modulation_agreement(
        row["A_desired_target_modulation"], row["B_desired_target_modulation"])
    return row
