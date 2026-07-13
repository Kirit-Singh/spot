"""Stability — a SINGLE primary estimand, with SEPARATELY TYPED sensitivity families.

TWO THINGS THIS MODULE REFUSES TO DO
------------------------------------
  * **pool families.** The PRIMARY P2S coefficient is exactly one fit — ``all_donor`` +
    author ``zscore`` + the seeded ``pca_on_60`` SVD. ``log_fc``, ``pca_off`` and each
    leave-one-donor-out fit are SEPARATELY TYPED SENSITIVITIES. Taking a median across all of
    them would blend different estimands and let a sensitivity move the number a reader sees
    as "the" coefficient. So the primary magnitude and sign come from the primary fit ALONE;
  * **invent a support threshold.** Under the seeded SVD the coefficient backprojection is
    DENSE (~3923/3926 nonzero), so a ``selection_frequency`` on ``coefficient != 0`` would
    mark almost everything "selected". There is NO discrete ``p2s_supported`` flag and NO
    rank. The lane emits the CONTINUOUS primary coefficient, its sign, and the cross-family
    sign CONCORDANCE with denominators; a magnitude threshold is the consumer's, prospective.

The sign is still meaningful: a negative primary coefficient is OPPOSED — the inverse of the
measured knockdown. Cross-family sign concordance is DESCRIPTIVE and carries its denominator;
it never overrides the primary sign.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from . import config

LODO_PREFIX = "lodo_"

LODO_SEMANTICS = ("agreement among OVERLAPPING leave-one-donor-out fits; they share most of "
                  "their cells and are not independent replicates")


def _sign(coefficient: Optional[float]) -> str:
    """The ONE rule: round to the coefficient precision, then sign from the rounded value."""
    if coefficient is None:
        return config.SIGN_ZERO
    rounded = round(float(coefficient), config.COEFFICIENT_DECIMALS)
    if rounded == 0.0:
        return config.SIGN_ZERO
    return config.SIGN_SUPPORTIVE if rounded > 0 else config.SIGN_OPPOSED


def _is_primary(r: dict[str, Any]) -> bool:
    return (str(r["donor_scope"]) == config.PRIMARY_SCOPE
            and str(r["effect_layer"]) == config.PRIMARY_LAYER
            and str(r["model_config"]) == config.PRIMARY_MODEL_CONFIG)


def _family(r: dict[str, Any]) -> Optional[str]:
    """Which SENSITIVITY family a non-primary fit belongs to. Typed, never pooled."""
    scope, layer, cfg = (str(r["donor_scope"]), str(r["effect_layer"]),
                         str(r["model_config"]))
    if scope.startswith(LODO_PREFIX) and layer == config.PRIMARY_LAYER \
            and cfg == config.PRIMARY_MODEL_CONFIG:
        return "donor_lodo"
    if scope == config.PRIMARY_SCOPE and cfg == config.PRIMARY_MODEL_CONFIG \
            and layer == "log_fc":
        return "effect_layer_log_fc"
    if scope == config.PRIMARY_SCOPE and layer == config.PRIMARY_LAYER \
            and cfg == "pca_off":
        return "model_config_pca_off"
    return None                              # any other grid cell is not a named family


def compute(coef_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per (arm_key, target_id): the PRIMARY coefficient + typed sensitivity concordance."""
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in coef_rows:
        by_key.setdefault((str(r["arm_key"]), str(r["target_id"])), []).append(r)

    out: list[dict[str, Any]] = []
    for (arm_key, target_id), rows in sorted(by_key.items()):
        first = rows[0]

        primary = next((r for r in rows if _is_primary(r)), None)
        primary_coef = round(float(primary["coefficient"]), 6) if primary else None
        primary_sign = _sign(primary_coef)

        # sensitivity families, TYPED and kept apart. Each carries its own sign; none feeds
        # the primary. Concordance is the fraction agreeing with the primary sign, WITH its
        # denominator — descriptive only.
        fam_rows: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            fam = _family(r)
            if fam:
                fam_rows.setdefault(fam, []).append(r)

        lodo = fam_rows.get("donor_lodo", [])
        log_fc = fam_rows.get("effect_layer_log_fc", [])
        pca_off = fam_rows.get("model_config_pca_off", [])

        # cross-family sign concordance vs the primary (single value per family where the
        # family is one fit; LODO is summarised over its fits). Denominators shipped.
        def _concord(fam_list):
            if primary_sign == config.SIGN_ZERO or not fam_list:
                return None, len(fam_list)
            agree = sum(1 for r in fam_list
                        if _sign(round(float(r["coefficient"]), 6)) == primary_sign)
            return round(agree / len(fam_list), 6), len(fam_list)

        lodo_conc, n_lodo = _concord(lodo)
        logfc_conc, n_logfc = _concord(log_fc)
        pcaoff_conc, n_pcaoff = _concord(pca_off)

        out.append({
            "arm_key": arm_key,
            "program_id": str(first["program_id"]),
            "desired_change": str(first["desired_change"]),
            "condition": str(first["condition"]),
            "target_id": target_id,
            "n_runs": len(rows),
            # THE PRIMARY — from the primary fit ALONE. Continuous; no threshold.
            "primary_coefficient": primary_coef,
            "primary_abs_coefficient": round(abs(primary_coef), 6)
            if primary_coef is not None else None,
            "primary_sign": primary_sign,
            "opposed": primary_sign == config.SIGN_OPPOSED,
            "primary_available": primary is not None,
            # SENSITIVITY families — each typed, each with its own denominator, never pooled.
            "sens_log_fc_sign_concordance": logfc_conc,
            "n_log_fc": n_logfc,
            "sens_pca_off_sign_concordance": pcaoff_conc,
            "n_pca_off": n_pcaoff,
            "lodo_sign_concordance": lodo_conc,
            "n_lodo": n_lodo,
        })
    return out


def method_block() -> dict[str, Any]:
    """The support method, as one hashable object. Primary/sensitivity separated; continuous."""
    return {
        "primary_estimand": {
            "donor_scope": config.PRIMARY_SCOPE,
            "effect_layer": config.PRIMARY_LAYER,
            "model_config": config.PRIMARY_MODEL_CONFIG,
        },
        "sensitivity_families": dict(config.SENSITIVITY_FAMILIES),
        "families_are_pooled_into_primary": False,
        "support_is_continuous": config.SUPPORT_IS_CONTINUOUS,
        "support_is_discrete_flag": config.SUPPORT_IS_DISCRETE_FLAG,
        "support_threshold_defined_here": False,
        "dense_backprojection_note": config.DENSE_BACKPROJECTION_NOTE,
        "sign_values": [config.SIGN_SUPPORTIVE, config.SIGN_OPPOSED, config.SIGN_ZERO],
        "lodo_semantics": LODO_SEMANTICS,
        "lodo_fits_are_independent_replicates": False,
        "rank_column_emitted": config.RANK_COLUMN_EMITTED,
        "opposed_contributors_are_kept_opposed": True,
    }
