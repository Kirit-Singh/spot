"""Canonical Stage-2 rules, REIMPLEMENTED from the written specification.

This module is part of the standalone verifier and imports NOTHING from the
generator. It is a second, independent expression of the frozen contract, so a bug
in the generator cannot be reproduced by the checker that is meant to catch it.

Every rule below is stated in the frozen spec (config/projection/disposition/
masks/donors/sources docstrings) and is re-derived here from that text.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from typing import Optional

# The mask / donor-split / projection rules are re-exported here so ``R.<rule>`` stays
# the one call site. Imported BY PATH, never as ``direct.verify_project``: the verifier
# is standalone and must not import the generator package.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from verify_project import complementary_splits, guide_mask_genes, program_delta  # noqa: E402,F401

ARM_A, ARM_B = "away_from_A", "toward_B"
ARMS = (ARM_A, ARM_B)
POLE = {ARM_A: "A", ARM_B: "B"}
RANK_COL = {ARM_A: "rank_away_from_A", ARM_B: "rank_toward_B"}

MIN_PANEL = 1
MIN_CONTROL = 10
N_CELLS_MIN = 30
SIGN_EPS = 1e-9
MIN_GUIDES_FOR_REPLICATION = 2

# Combined-objective aliases. A combined score is forbidden under ANY name.
COMBINED_ALIASES = {
    "combination", "combination_score", "combination_state", "combined_score",
    "balanced_score", "balanced_skew", "balanced_a_to_b", "composite_score",
    "total_skew", "overall_score", "aggregate_score", "mean_arm_score",
    "arms_both_positive",
}
HEADLINE_RANK_ALIASES = {"rank", "primary_rank", "rank_primary", "headline_rank",
                         "overall_rank"}
RETIRED = {"toward_b", "contrast_id", "is_eligible", "eligibility_state",
           "desired_target_modulation", "primary_endpoint"}
PQ = {"p_value", "q_value", "padj", "adj_p_value", "fdr", "pvalue", "qvalue"}
FORBIDDEN_COLUMNS = COMBINED_ALIASES | HEADLINE_RANK_ALIASES | RETIRED | PQ

ENSG = re.compile(r"ENSG\d+")


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def content_sha256(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def canonical_num(x) -> Optional[float]:
    """Scores are canonical float64. Non-finite is not a score: it is null."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


# Column contract (allowlist, not just a denylist).
def screen_allowlist() -> set:
    base = {
        "schema_version", "run_id", "released_estimate_id", "target_id",
        "target_id_namespace", "target_symbol", "target_ensembl", "condition",
        "base_qc_state", "base_qc_passed", "base_qc_reasons",
        "mask_resolved", "mask_unresolved_reason", "mask_gene_count",
        "contributing_guide_ids", "contributor_status", "contributor_source",
        "n_cells_target", "n_guides_source", "qc_ontarget_significant",
        "qc_ontarget_effect_size", "qc_low_target_expression", "qc_target_baseMean",
        "source_distal_offtarget_flag", "source_neighboring_gene_KD",
        "effective_donor_n", "crispri_modality", "inference_status",
        "cell_level_support_state", "concordance_class",
        "desired_modulation_agreement",
        # row identity + joint ordering (a tier and a label, never a magnitude)
        "direct_method_version", "direct_config_sha256", "effect_source_sha256",
        "estimate_mask_sha256", "mask_method_version", "pareto_tier",
        "joint_status", "joint_ordering_method_id",
    }
    for arm in ARMS:
        p = POLE[arm]
        base |= {arm, f"{arm}_zscore", RANK_COL[arm]}
        base |= {f"{p}_{s}" for s in (
            "delta", "panel_surviving", "control_surviving", "projection_status",
            "support_status", "evaluable", "state", "reasons", "estimate_available",
            "desired_target_modulation", "guide_replication_state",
            "guide_replication_supported", "n_guide_slots_released",
            "n_guides_mapped", "n_guides_evaluated", "n_guides_concordant",
            "guide_missing_reasons", "n_splits_total", "n_splits_evaluable",
            "n_splits_missing", "n_splits_internally_concordant",
            "n_splits_internally_discordant", "n_splits_agreeing",
            "donor_split_support", "donor_split_denominator", "support_state",
            "evidence_tier")}
    return base


# --------------------------------------------------------------------------- #
# Base QC. Pre-outcome; missing/invalid measurements are NON-EVALUABLE.
# --------------------------------------------------------------------------- #
ENSEMBL_GENE_ID = "ensembl_gene_id"
GENE_SYMBOL = "gene_symbol"
ENSG_EXACT = re.compile(r"^ENSG[0-9]+$")


def target_identity(released_estimate_id, target_contrast, gene_name,
                    identity_map=None):
    """Reimplemented identity rule.

    The released_estimate_id is NEVER parsed. target_ensembl is populated only
    when obs.target_contrast literally IS an Ensembl id, or an explicit map
    supplies one.

    ``released_target_ensembl`` is what the RELEASE itself said — null for every
    gene_symbol scope, whether or not a run-level map later enriched it. The
    contributor evidence describes the released identity, so that is the field a
    manifest row and a source record must agree on.
    """
    target_id = "" if target_contrast is None else str(target_contrast)
    symbol = None if is_null(gene_name) else str(gene_name)
    if ENSG_EXACT.match(target_id):
        return {"released_estimate_id": str(released_estimate_id),
                "target_id": target_id,
                "target_id_namespace": ENSEMBL_GENE_ID,
                "target_symbol": symbol,
                "target_ensembl": target_id,
                "released_target_ensembl": target_id}
    mapped = (identity_map or {}).get(target_id)
    return {"released_estimate_id": str(released_estimate_id),
            "target_id": target_id,
            "target_id_namespace": GENE_SYMBOL,
            "target_symbol": symbol,
            "target_ensembl": mapped if mapped and ENSG_EXACT.match(str(mapped))
                              else None,
            "released_target_ensembl": None}


# --------------------------------------------------------------------------- #
# The generic target-identity contract, REIMPLEMENTED from the written spec.
#
#   ensembl_gene_id => target_id IS an accession, and target_ensembl is that same
#                      accession, exactly (equality, not "looks like one").
#   gene_symbol     => target_id is not an accession, and target_ensembl is NULL.
#   released_estimate_id is provenance only; it is never parsed to fill a target
#   field, not even to phrase a refusal.
# --------------------------------------------------------------------------- #
NAMESPACES = (ENSEMBL_GENE_ID, GENE_SYMBOL)
IDENTITY_FIELDS = ("released_estimate_id", "target_id", "target_id_namespace",
                   "target_symbol", "target_ensembl")
# THE scope identity, everywhere: the estimate AND the whole released identity. A
# reduced key would let a record that agrees about the gene but not about the namespace,
# the symbol or the release key stand in as evidence for a scope it does not describe.
CONTRIB_KEY = ("estimate_type", "estimate_id", "released_estimate_id", "target_id",
               "target_id_namespace", "target_symbol", "target_ensembl",
               "condition", "donor_pair")

DETERMINED = "determined"
AMBIGUOUS = "ambiguous"
EVIDENCE_STATES = (DETERMINED, AMBIGUOUS)


def is_null(v) -> bool:
    return v is None or str(v).strip().lower() in ("", "none", "nan", "null",
                                                   "na", "<na>")


def norm(v) -> Optional[str]:
    return None if is_null(v) else str(v)


def scope_of(row) -> tuple:
    """The FULL released scope identity of a manifest row, record or rebuilt row."""
    return tuple(norm(row.get(f)) for f in CONTRIB_KEY)


def scope_sort_key(scope) -> tuple:
    """Order scopes for reporting without comparing None to str."""
    return tuple("" if x is None else str(x) for x in scope)


# --------------------------------------------------------------------------- #
# The evidence domain, reimplemented: global, all-condition, POOLED-MAIN. Support has
# no contributor evidence: never projected, never masked, never tier-elevating.
# --------------------------------------------------------------------------- #
POOLED_TYPE = "main"
POOLED_ID = "main"
SUPPORT_AVAILABLE = False
SUPPORT_UNAVAILABLE = "unavailable_no_contributor_evidence_in_this_release_pass"
SUPPORT_STATE_UNAVAILABLE = "support_unavailable"
EVIDENCE_DOMAIN_ID = ("spot.stage02.direct.evidence_domain."
                      "pooled_main_all_condition.v1")


def identity_violation(row) -> Optional[str]:
    """The exact reason a row's released target identity is inadmissible, or None."""
    if is_null(row.get("released_estimate_id")):
        return "released_estimate_id_missing"
    if is_null(row.get("target_id")):
        return "target_id_missing"
    if is_null(row.get("target_symbol")):
        return "target_symbol_missing"

    namespace = row.get("target_id_namespace")
    if not isinstance(namespace, str) or namespace not in NAMESPACES:
        return "target_id_namespace_not_in_enum"

    target_id = str(row["target_id"])
    ensembl = row.get("target_ensembl")
    if namespace == ENSEMBL_GENE_ID:
        if not ENSG_EXACT.match(target_id):
            return ("namespace_ensembl_gene_id_but_target_id_is_not_an_"
                    "ensembl_gene_id")
        if is_null(ensembl) or str(ensembl) != target_id:
            return ("namespace_ensembl_gene_id_but_target_ensembl_does_not_equal_"
                    "target_id")
    else:
        if ENSG_EXACT.match(target_id):
            return "namespace_gene_symbol_but_target_id_is_an_ensembl_gene_id"
        if not is_null(ensembl):
            return "namespace_gene_symbol_but_target_ensembl_is_not_null"
    return None


# The manifest's CANONICAL order, reimplemented. Row order is serialisation, not
# science: the same evidence in another order is the same manifest, and must hash
# the same and produce the same run_id.
CANON_VERIFIED = "raw_bytes_match_trusted_pin"


def canonical_row_key(row) -> tuple:
    return (str(row["estimate_type"]), str(row["estimate_id"]),
            str(row["released_estimate_id"]), str(row["target_id"]),
            str(row["target_id_namespace"]), str(row["target_symbol"]),
            "" if is_null(row.get("target_ensembl")) else str(row["target_ensembl"]),
            str(row["condition"]),
            "" if is_null(row.get("donor_pair")) else str(row["donor_pair"]),
            "" if is_null(row.get("guide_id")) else str(row["guide_id"]))


def canonical_manifest_sha256(mdoc) -> str:
    """Re-derive the hash run_id actually bound, from the manifest's content.

    The payload is the WHOLE declared contract, not just the rows:
    ``source_record_table_schema_version`` (WHICH evidence schema the citations resolve
    in — the superseded pair declared one schema over a table that was another) and
    ``evidence_domain`` (the GLOBAL pooled-main universe, not the selected-condition
    one) are both load-bearing. The domain is a property of the contract, not a field
    the producer writes, so it is restated here rather than read from the document — a
    manifest cannot rename its own domain to match a hash.
    """
    sources = sorted(({"name": str(s["name"]),
                       "sha256": str(s["sha256"]).lower(),
                       "revision": str(s["revision"]),
                       "verified": CANON_VERIFIED} for s in mdoc["sources"]),
                     key=lambda s: s["name"])
    return content_sha256({
        "schema_version": str(mdoc["schema_version"]),
        "source_record_table_schema_version":
            str(mdoc["source_record_table_schema_version"]),
        "source_class": str(mdoc["source_class"]),
        "evidence_domain": EVIDENCE_DOMAIN_ID,
        "source_record_table": str(mdoc["source_record_table"]),
        "source_replay_report": str(mdoc["source_replay_report"]),
        "sources": sources,
        "rows": sorted(mdoc["rows"], key=canonical_row_key),
    })


BASE_QC_PRECEDENCE = [
    "unavailable_in_condition", "unresolved_target_identity",
    "mask_unresolved", "missing_qc_measurement",
    "invalid_qc_measurement", "underpowered_cells", "low_target_expression",
    "no_detectable_source_on_target_repression", "qc_pass_single_guide",
    "qc_pass_two_guide", "qc_pass_multi_guide",
]
BASE_QC_PASS = {"qc_pass_single_guide", "qc_pass_two_guide", "qc_pass_multi_guide"}


def base_qc(*, mask_resolved: bool, n_cells, ontarget_significant, low_expression,
            n_guides, target_identity_resolved: bool = True) -> tuple[str, bool]:
    reasons: list[str] = []
    if not target_identity_resolved:
        reasons.append("unresolved_target_identity")
    if not mask_resolved:
        reasons.append("mask_unresolved")

    missing, invalid = [], []
    if n_cells is None:
        missing.append("n_cells")
    else:
        v = canonical_num(n_cells)
        if v is None or v < 0:
            invalid.append("n_cells")
    for name, value in (("ontarget_significant", ontarget_significant),
                        ("low_expression_flag", low_expression)):
        if value is None:
            missing.append(name)
        elif not isinstance(value, bool):
            invalid.append(name)

    if missing:
        reasons.append("missing_qc_measurement")
    if invalid:
        reasons.append("invalid_qc_measurement")

    unusable = set(missing) | set(invalid)
    if "n_cells" not in unusable and float(n_cells) < N_CELLS_MIN:
        reasons.append("underpowered_cells")
    if low_expression is True:
        reasons.append("low_target_expression")
    if ontarget_significant is False:
        reasons.append("no_detectable_source_on_target_repression")

    if n_guides is None:
        reasons.append("mask_unresolved")
    else:
        n = int(n_guides)
        reasons.append("qc_pass_single_guide" if n <= 1
                       else "qc_pass_two_guide" if n == 2 else "qc_pass_multi_guide")

    for state in BASE_QC_PRECEDENCE:
        if state in reasons:
            return state, state in BASE_QC_PASS
    return "mask_unresolved", False


def arm_state(base_state: str, base_passed: bool, projection_status: str) -> tuple:
    if not base_passed:
        return "excluded_base_qc", False
    if projection_status == "mask_unresolved":
        return "mask_unresolved", False
    if projection_status != "ok":
        return "insufficient_axis_coverage", False
    return "evaluable", True


def desired_modulation(value, evaluable: bool) -> str:
    if not evaluable or value is None:
        return "not_evaluated"
    if value > SIGN_EPS:
        return "decrease"
    if value < -SIGN_EPS:
        return "increase"
    return "no_direction_evidence"


def modulation_agreement(a: str, b: str) -> str:
    real = {"decrease", "increase"}
    ar, br = a in real, b in real
    if ar and br:
        return "agree" if a == b else "conflict"
    if ar:
        return "only_away_from_A_evaluated"
    if br:
        return "only_toward_B_evaluated"
    return "neither_arm_evaluated"


def concordance_class(a, b) -> str:
    if a is None and b is None:
        return "not_evaluated"
    if a is None or b is None:
        return "partially_evaluated"
    ap, bp = a > SIGN_EPS, b > SIGN_EPS
    if ap and bp:
        return "concordant_both_arms"
    if ap:
        return "away_from_A_only"
    if bp:
        return "toward_B_only"
    return "discordant_arms"


def sign_of(x) -> Optional[int]:
    if x is None:
        return None
    return 1 if x > SIGN_EPS else (-1 if x < -SIGN_EPS else 0)


# --------------------------------------------------------------------------- #
# Support (per arm), reimplemented.
# --------------------------------------------------------------------------- #
def guide_replication(arm_value, slots: list[dict], arm: str, base_state: str,
                      arm_evaluable: bool,
                      support_available: bool = SUPPORT_AVAILABLE) -> dict:
    main_sign = sign_of(arm_value)
    mapped = [s for s in slots if s.get("guide_id")]
    distinct = {s["guide_id"] for s in mapped}
    evaluated = {s["guide_id"]: s for s in mapped
                 if s["values"].get(arm) is not None}
    n_eval = len(evaluated)
    signs = [sign_of(s["values"][arm]) for s in evaluated.values()]
    n_conc = 0 if main_sign is None else sum(1 for x in signs if x == main_sign)

    if not arm_evaluable:
        state = "not_evaluated"
    elif not support_available:
        # The guide-slot estimates carry no contributor evidence, so none was
        # projected. The question was never askable — which is NOT the same as the
        # guides having failed to resolve.
        state = SUPPORT_UNAVAILABLE
    elif base_state == "qc_pass_single_guide":
        state = "single_guide_no_replication"
    elif not distinct:
        state = "unavailable_unresolved_guides"
    elif n_eval < MIN_GUIDES_FOR_REPLICATION:
        state = "single_guide_no_replication"
    elif main_sign not in (None, 0) and n_conc == n_eval:
        state = "replicated_concordant"
    else:
        state = "replicated_discordant"
    return {"state": state, "supported": state == "replicated_concordant",
            "n_mapped": len(distinct), "n_evaluated": n_eval,
            "n_concordant": n_conc if n_eval else 0}


def split_support(arm_value, pair_values: dict, splits: list, arm_evaluable: bool,
                  support_available: bool = SUPPORT_AVAILABLE) -> dict:
    main_sign = sign_of(arm_value)
    n_eval = n_int_conc = n_int_disc = n_main = 0
    for half_a, half_b in splits:
        va, vb = pair_values.get(half_a), pair_values.get(half_b)
        if va is None or vb is None:
            continue
        n_eval += 1
        sa, sb = sign_of(va), sign_of(vb)
        if sa == sb and sa != 0:
            n_int_conc += 1
        else:
            n_int_disc += 1
        if main_sign is not None and sa == main_sign and sb == main_sign \
                and main_sign != 0:
            n_main += 1
    total = len(splits)
    supported = (support_available and arm_evaluable and n_eval == total and total > 0
                 and n_main == total and n_int_disc == 0)
    return {"n_total": total, "n_evaluable": n_eval, "n_missing": total - n_eval,
            "n_internally_concordant": n_int_conc,
            "n_internally_discordant": n_int_disc, "n_agreeing": n_main,
            "supported": supported}


def support_status(arm_evaluable: bool, base_passed: bool,
                   support_available: bool = SUPPORT_AVAILABLE) -> str:
    """AVAILABILITY FIRST. 'evaluated' claims support was assessed; with no support
    evidence in the pass there is nothing to assess, however evaluable the arm is."""
    if not support_available:
        return SUPPORT_UNAVAILABLE
    if arm_evaluable:
        return "evaluated"
    return "not_evaluated_base_qc" if not base_passed else "not_evaluated_arm"


def support_state(arm_evaluable: bool, guide_rep: bool, donor: bool) -> str:
    if not arm_evaluable:
        return "not_evaluated"
    return "within_dataset_replicated" if (guide_rep and donor) else "screen_only"


def evidence_tier(arm_evaluable: bool, value, guide_rep: bool, donor: bool,
                  support_available: bool = SUPPORT_AVAILABLE) -> str:
    if not arm_evaluable or value is None:
        return "not_evaluated"
    if value <= SIGN_EPS:
        return "evaluable_no_directional_signal"
    if not support_available:
        # Tiers 1 and 2 are STRUCTURALLY unreachable without support evidence, not
        # merely unreached. An elevation's blast radius is the published ranking.
        return "tier3_screen_only"
    if guide_rep and donor:
        return "tier1_guide_and_donor_split"
    if guide_rep:
        return "tier2_guide_replicated"
    return "tier3_screen_only"


