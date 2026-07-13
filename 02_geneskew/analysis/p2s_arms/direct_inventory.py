"""THE ADMITTED DIRECT INVENTORY: masks and eligibility, from the bundle's OWN bytes.

Two things here are scientific, not clerical, and an independent real-input attack found both.

MASKS ARE SELECTED BY THE FULL ESTIMATE IDENTITY — NEVER UNIONED ACROSS SCOPES
-----------------------------------------------------------------------------
The bundle's ``masks.parquet`` carries rows for the MAIN estimate and for the guide-slot and
donor-pair estimates. They are different estimates. Taking their union would mask a gene for a
perturbation that had no reason to mask it, and the reconstruction would then be denied
evidence nothing said to withhold — silently, and with a matrix that still looks fine.

So the main-estimate mask is selected on ``estimate_type == "main" AND estimate_id == "main"``,
and the masked gene comes from ``masked_gene_ensembl`` — the readout namespace the arms are
actually computed in.

ELIGIBILITY IS ARM-SPECIFIC
--------------------------
It is not a property of a target. It is ``evaluable`` on the arm
``direct|program|increase|condition`` — the arm the fit is taken on. And because the two sign
arms are one measurement and a sign, their evaluable inventories MUST be identical; if they
are not, something re-derived one of them, and this refuses rather than picking a side.

A MISSING MASK IS A REFUSAL, NEVER AN EMPTY ONE
----------------------------------------------
An eligible target with no mask row would silently get ``mask = {}`` — i.e. NOTHING masked,
which is the most permissive possible mask and the exact opposite of the safe default.
"""
from __future__ import annotations

import os
from typing import Any

import pandas as pd

from . import armref, config
from . import disposition as D


def main_estimate_masks(bundle_dir: str) -> dict[str, Any]:
    """The MAIN-estimate mask rows. Scopes are SELECTED, never unioned."""
    df = pd.read_parquet(os.path.join(bundle_dir, "masks.parquet"))

    if config.MASK_GENE_COLUMN not in df.columns:
        raise D.RefusalError(
            D.REFUSE_BUNDLE_INCOMPLETE,
            f"the bundle's masks.parquet has no {config.MASK_GENE_COLUMN!r} column (it has "
            f"{sorted(df.columns)}). The masked gene must arrive in the READOUT namespace; "
            "this lane will not re-derive it from a symbol")

    n_all = len(df)
    scoped = df
    for col, want in (("estimate_type", config.MASK_MAIN_ESTIMATE_TYPE),
                      ("estimate_id", config.MASK_MAIN_ESTIMATE_ID)):
        if col not in df.columns:
            raise D.RefusalError(
                D.REFUSE_MASK_SCOPE_UNION,
                f"the bundle's masks.parquet has no {col!r} column, so a MAIN-estimate mask "
                "cannot be told apart from a guide-slot or donor-pair one. Unioning them "
                "would mask genes for perturbations that had no reason to mask them")
        scoped = scoped[scoped[col].astype(str) == want]

    if scoped.empty:
        raise D.RefusalError(
            D.REFUSE_MASK_EMPTY,
            f"the admitted bundle ships {n_all} mask row(s) but NONE for the main estimate "
            f"({config.MASK_MAIN_ESTIMATE_TYPE}/{config.MASK_MAIN_ESTIMATE_ID}). An empty "
            "mask is the most permissive mask there is, and it is never a default")

    rows = (scoped[["target_id", config.MASK_GENE_COLUMN]].astype(str)
            .rename(columns={config.MASK_GENE_COLUMN: "gene_id"})
            .drop_duplicates())
    by_target: dict[str, set] = {}
    for r in rows.itertuples(index=False):
        by_target.setdefault(str(r.target_id), set()).add(str(r.gene_id))

    return {"rows": rows.to_dict("records"), "by_target": by_target,
            "n_rows_all_scopes": int(n_all), "n_rows_main": int(len(rows)),
            "scopes_unioned": config.MASK_SCOPES_MAY_BE_UNIONED,
            "estimate_type": config.MASK_MAIN_ESTIMATE_TYPE,
            "estimate_id": config.MASK_MAIN_ESTIMATE_ID,
            "gene_column": config.MASK_GENE_COLUMN}


def evaluable_targets(bundle_dir: str, *, program_id: str, condition: str) -> dict[str, Any]:
    """The targets EVALUABLE on this program's arm. Arm-specific, and symmetric by proof."""
    arms = pd.read_parquet(os.path.join(bundle_dir, "arms.parquet"))
    inc, dec = armref.both_arms(program_id, condition)

    def inventory(arm_key: str) -> list[str]:
        sub = arms[arms["arm_key"].astype(str) == arm_key]
        ev = sub[sub["evaluable"].astype(bool)]
        return sorted(ev["target_id"].astype(str).unique().tolist())

    inc_targets = inventory(inc.arm_key)
    dec_targets = inventory(dec.arm_key)

    if not inc_targets:
        raise D.RefusalError(
            D.REFUSE_ELIGIBLE_EMPTY,
            f"the admitted bundle ships no EVALUABLE target on {inc.arm_key!r}. Eligibility "
            "is a property of the ARM, not of the target, and an arm with nothing evaluable "
            "has no perturbation matrix to reconstruct from")

    # The two arms are ONE measurement and a sign. Their evaluable inventories must therefore
    # be identical — if they are not, one of them was re-derived, and picking a side would be
    # choosing which of two disagreeing answers to believe.
    if inc_targets != dec_targets:
        only_inc = sorted(set(inc_targets) - set(dec_targets))[:3]
        only_dec = sorted(set(dec_targets) - set(inc_targets))[:3]
        raise D.RefusalError(
            D.REFUSE_ARM_INVENTORY_ASYMMETRY,
            f"the two sign arms of {program_id!r} at {condition!r} do not share one evaluable "
            f"inventory ({len(inc_targets)} vs {len(dec_targets)}; only-increase={only_inc}, "
            f"only-decrease={only_dec}). They are one measurement and a sign; a disagreement "
            "here means something re-derived one of them")

    states = (arms[arms["arm_key"].astype(str) == inc.arm_key]
              .set_index("target_id")["base_state"].astype(str).to_dict())
    return {
        "targets": inc_targets,
        "n_evaluable": len(inc_targets),
        "arm_key": inc.arm_key,
        "sibling_arm_key": dec.arm_key,
        "inventories_are_identical": True,
        "eligibility_is_arm_specific": True,
        "base_state_by_target": {t: states.get(t) for t in inc_targets},
        "qc_pass_states_seen": sorted({states.get(t) for t in inc_targets if states.get(t)}),
    }


def bind(bundle_dir: str, *, program_id: str, condition: str) -> dict[str, Any]:
    """Masks + arm-specific eligibility, cross-checked. A gap between them is a refusal."""
    masks = main_estimate_masks(bundle_dir)
    elig = evaluable_targets(bundle_dir, program_id=program_id, condition=condition)

    # EVERY eligible target must carry a mask. A target with no mask row would otherwise get
    # the empty mask — nothing withheld at all, the most permissive setting there is.
    unmasked = [t for t in elig["targets"] if t not in masks["by_target"]]
    if unmasked:
        raise D.RefusalError(
            D.REFUSE_MASK_MISSING_FOR_ELIGIBLE,
            f"{len(unmasked)} evaluable target(s) on {elig['arm_key']!r} have NO main-estimate "
            f"mask in the admitted bundle (e.g. {unmasked[:3]}). A missing mask is not an "
            "empty mask: it would withhold nothing, which is the most permissive mask there "
            "is and the exact opposite of the safe default")

    return {"masks": masks, "eligible": elig,
            "targets": elig["targets"], "mask_by_target": masks["by_target"]}
