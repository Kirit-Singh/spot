"""THE METHOD, RESTATED — part of the STANDALONE verifier.

INDEPENDENCE RULE (test-enforced): imports nothing from the generator.

run_id binds the method block and the eligibility policy, so a forger who changes one
of them must reseal the binding hash — and after resealing, a verifier that only
recomputes ``sha256(binding)`` and compares it to ``run_binding_sha256`` finds nothing
wrong. It cannot: it is checking that the run hashed what it hashed. Every field below
survived exactly that way — ``method_id``, ``method_version``, ``formula_id``, the two
arm formulas, the rank policy — because nothing anywhere said what they were SUPPOSED
to be.

So this module says. Every constant here is written out from the spec, not imported: an
expectation imported from ``config`` is not an expectation, it is an echo, and it agrees
with the generator by construction no matter what the generator says today. These are
the fields that decide what the emitted numbers MEAN:

  * WHICH method, at WHICH version, computing WHICH formula. A run that quietly changed
    its projection and kept its method_id is claiming to be a result it is not;
  * the two ARM formulas, and the direction each is scored in. Swap the sign on
    ``away_from_A`` and every rank in that arm inverts while every hash still checks;
  * the RANK policy — population, direction, tie-break, dtype, and what a non-finite
    score becomes. Rank a null as if it were zero and the table gains rows it did not
    earn;
  * the COMBINATION PROHIBITION. This is the one the whole two-arm design exists to
    enforce, and it is a single boolean;
  * the eligibility and evidence-tier thresholds. ``n_cells_min``, the surviving-panel
    and surviving-control minima, the replication minimum, the mask window, the sign
    tolerance: each is a number that moves rows between evaluable and excluded.

A drift in ANY of them is a different scientific result wearing this one's name.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# The method identity, restated.
# --------------------------------------------------------------------------- #
METHOD_ID = "spot.stage02.direct.masked_program_projection"
METHOD_VERSION = "stage2-direct-v5-pooled-main-two-arm"
FORMULA_ID = "spot.stage02.direct.formula.masked_program_delta.v1"
# The bare expression, exactly as an artifact must carry it.
FORMULA_EXPR = "delta_p(X) = mean(P_p \\ M_X) - mean(C_p \\ M_X)"

ARM_A = "away_from_A"
ARM_B = "toward_B"
ARMS = [ARM_A, ARM_B]

# The two arms are scored in OPPOSITE senses of their pole's sign, and that asymmetry is
# the whole biology: move AWAY from A, TOWARD B.
ARM_FORMULA = {ARM_A: "-sign_A * delta_A", ARM_B: "sign_B * delta_B"}
ARM_RANK_COLUMN = {ARM_A: "rank_away_from_A", ARM_B: "rank_toward_B"}
ARM_EVALUABLE_COLUMN = {ARM_A: "A_evaluable", ARM_B: "B_evaluable"}

RANK_POPULATION = "arm_evaluable_and_non_null_canonical_score"
RANK_TIE_BREAK = "target_id_ascending"
RANK_DIRECTION = "descending"
RANK_DTYPE = "Int64"

COMBINED_OBJECTIVE_PERMITTED = False
HEADLINE_ARM_PERMITTED = False

EFFECT_LAYER_PRIMARY = "log_fc"
EFFECT_LAYER_SENSITIVITY = "zscore"

# WHICH mask rule removed the genes, restated. The intended target, its 30-kb
# neighbourhood and every off-target alignment of the CONTRIBUTING guides come out
# before the panel and control means are recomputed.
MASK_METHOD_VERSION = "stage2-direct-mask-v1-contributing-guide-and-offtarget"

# The EXACT method block run_id must have hashed. Exact, not a subset: an extra field is
# a claim nobody restated, and a missing one is a claim that stopped being bound.
EXPECTED_METHOD = {
    "method_id": METHOD_ID,
    "method_version": METHOD_VERSION,
    "formula_id": FORMULA_ID,
    "effect_layer_primary": EFFECT_LAYER_PRIMARY,
    "effect_layer_sensitivity": EFFECT_LAYER_SENSITIVITY,
    "arms": list(ARMS),
    "arm_formula": dict(ARM_FORMULA),
    "arm_rank_column": dict(ARM_RANK_COLUMN),
    "arm_evaluable_column": dict(ARM_EVALUABLE_COLUMN),
    "rank_population": RANK_POPULATION,
    "rank_tie_break": RANK_TIE_BREAK,
    "rank_dtype": RANK_DTYPE,
    "combined_objective_permitted": COMBINED_OBJECTIVE_PERMITTED,
    "headline_arm_permitted": HEADLINE_ARM_PERMITTED,
}

# --------------------------------------------------------------------------- #
# The eligibility + evidence-tier policy, restated.
# --------------------------------------------------------------------------- #
EXPECTED_ELIGIBILITY_POLICY = {
    "policy_id": "spot.stage02.direct.two_arm_eligibility.v1",
    "pre_outcome_base_qc_only": True,
    "arms": list(ARMS),
    "arm_formula": dict(ARM_FORMULA),
    "arm_rank_column": dict(ARM_RANK_COLUMN),
    "combined_objective_permitted": COMBINED_OBJECTIVE_PERMITTED,
    "headline_arm_permitted": HEADLINE_ARM_PERMITTED,
    "rank_population": RANK_POPULATION,
    "rank_tie_break": RANK_TIE_BREAK,
    "rank_direction": RANK_DIRECTION,
    "rank_dtype": RANK_DTYPE,
    "score_representation": "canonical_float64_no_display_rounding",
    "nonfinite_score_rule":
        "nan_and_inf_are_canonicalised_to_null_and_never_ranked",
    "support_requires_arm_evaluable": True,
    "required_base_qc_measurements": ["n_cells", "ontarget_significant",
                                      "low_expression_flag"],
    "base_qc_validity": {"n_cells": "finite_non_negative_number",
                         "ontarget_significant": "boolean",
                         "low_expression_flag": "boolean"},
    "missing_qc_is_non_evaluable": True,
    "arms_are_independent": True,
    "arm_support_is_never_shared": True,
    "min_surviving_panel": 1,
    "min_surviving_control": 10,
    "n_cells_min": 30,
    "min_guides_for_replication": 2,
    "mask_window_kb": 30,
    "mask_neighborhood_column": "nearby_gene_within_30kb",
    "guide_resolution_ladder": ["manifest", "unresolved"],
    "guide_identity_inference_permitted": False,
    "single_guide_targets_never_replicated": True,
    "modulation_conflicts_are_preserved_not_resolved": True,
    "sign_eps": 1e-9,
    "float_decimals": 6,
}


def expected_config_sha256() -> str:
    """The frozen config's id, re-derived from THIS module's restatement.

    Emitted on every screen row. Re-deriving it here means the row's ``direct_config_
    sha256`` is checked against the policy the VERIFIER expects, not against the policy
    the run happened to hash — so a run that loosened a threshold and honestly hashed the
    loosened policy is caught by the row, not merely by the binding.
    """
    import verify_rules as R

    return R.content_sha256({"stage2_method": EXPECTED_METHOD,
                             "stage2_eligibility_policy": EXPECTED_ELIGIBILITY_POLICY})


def _diff(expected: dict, actual) -> list[str]:
    """Which fields disagree. Named, so a failure says WHICH claim moved."""
    if not isinstance(actual, dict):
        return [f"<not an object: {type(actual).__name__}>"]
    bad = [f"{k}={actual.get(k)!r} (expected {v!r})"
           for k, v in expected.items() if actual.get(k) != v]
    bad += [f"{k}=<unrestated extra field>" for k in sorted(set(actual) - set(expected))]
    return bad


def verify_method_identity(prov, binding, rep):
    """The bound method IS the method this verifier was written against.

    Checked field-group by field-group rather than as one equality, so a failure names
    the claim that moved instead of printing two dicts and leaving the reader to diff
    them. The whole-block check runs last and catches anything the named ones did not
    think to ask about — including a field ADDED to the binding, which no expectation
    written in advance can anticipate by name.
    """
    m = binding.get("stage2_method") or {}

    rep.check("run_id binds the exact method id",
              m.get("method_id") == METHOD_ID,
              f"bound {m.get('method_id')!r}, expected {METHOD_ID!r}")
    rep.check("run_id binds the exact method version",
              m.get("method_version") == METHOD_VERSION,
              f"bound {m.get('method_version')!r}, expected {METHOD_VERSION!r}")
    rep.check("run_id binds the exact formula id",
              m.get("formula_id") == FORMULA_ID,
              f"bound {m.get('formula_id')!r}, expected {FORMULA_ID!r}")
    rep.check("run_id binds the exact effect layers",
              m.get("effect_layer_primary") == EFFECT_LAYER_PRIMARY
              and m.get("effect_layer_sensitivity") == EFFECT_LAYER_SENSITIVITY,
              f"primary={m.get('effect_layer_primary')!r} "
              f"sensitivity={m.get('effect_layer_sensitivity')!r}")

    rep.check("run_id binds BOTH arm formulas, in the right sense",
              m.get("arm_formula") == ARM_FORMULA and m.get("arms") == ARMS,
              f"arms={m.get('arms')!r} arm_formula={m.get('arm_formula')!r}; "
              f"expected {ARM_FORMULA!r}")
    rep.check("run_id binds each arm's own rank and evaluable column",
              m.get("arm_rank_column") == ARM_RANK_COLUMN
              and m.get("arm_evaluable_column") == ARM_EVALUABLE_COLUMN,
              f"rank={m.get('arm_rank_column')!r} "
              f"evaluable={m.get('arm_evaluable_column')!r}")
    rep.check("run_id binds the exact rank policy",
              m.get("rank_population") == RANK_POPULATION
              and m.get("rank_tie_break") == RANK_TIE_BREAK
              and m.get("rank_dtype") == RANK_DTYPE,
              f"population={m.get('rank_population')!r} "
              f"tie_break={m.get('rank_tie_break')!r} "
              f"dtype={m.get('rank_dtype')!r}")
    rep.check("the bound method FORBIDS a combined objective and a headline arm",
              m.get("combined_objective_permitted") is False
              and m.get("headline_arm_permitted") is False,
              f"combined={m.get('combined_objective_permitted')!r} "
              f"headline={m.get('headline_arm_permitted')!r}")

    bad = _diff(EXPECTED_METHOD, m)
    rep.check("the bound method block is EXACTLY the restated method", not bad,
              f"{len(bad)} field(s) disagree: {bad[:4]}")

    # ...and the PROVENANCE copy of the method, which is what a human reads, says the
    # same thing. A forged copy is never excused by an honest one: both are written by
    # the same producer.
    pm = prov.get("method") or {}
    rep.check("the method in PROVENANCE is the same method run_id bound",
              pm.get("method_id") == METHOD_ID
              and pm.get("method_version") == METHOD_VERSION
              and pm.get("formula_id") == FORMULA_ID
              and pm.get("arm_formula") == ARM_FORMULA,
              f"provenance says {pm.get('method_id')!r} / "
              f"{pm.get('method_version')!r} / {pm.get('formula_id')!r} / "
              f"{pm.get('arm_formula')!r}")
    rep.check("the emitted formula EXPRESSION is the restated formula",
              pm.get("formula_expr") == FORMULA_EXPR,
              f"provenance carries {pm.get('formula_expr')!r}, expected "
              f"{FORMULA_EXPR!r}")
    rep.check("provenance repeats the combination prohibition",
              pm.get("combined_objective_permitted") is False
              and pm.get("headline_arm_permitted") is False)


def verify_eligibility_policy(binding, rep):
    """The bound policy IS the policy — every threshold that moves a row.

    A policy is not decoration: ``n_cells_min``, the surviving-panel/control minima and
    the sign tolerance each decide whether a target is evaluable, and therefore whether
    it is ranked at all. Loosening one and resealing the binding produces a larger,
    friendlier screen under an unchanged identity.
    """
    p = binding.get("stage2_eligibility_policy") or {}

    rep.check("run_id binds the exact eligibility policy id",
              p.get("policy_id") == EXPECTED_ELIGIBILITY_POLICY["policy_id"],
              f"bound {p.get('policy_id')!r}")
    thresholds = ("min_surviving_panel", "min_surviving_control", "n_cells_min",
                  "min_guides_for_replication", "mask_window_kb", "sign_eps")
    moved = [f"{k}={p.get(k)!r} (expected "
             f"{EXPECTED_ELIGIBILITY_POLICY[k]!r})"
             for k in thresholds if p.get(k) != EXPECTED_ELIGIBILITY_POLICY[k]]
    rep.check("run_id binds the exact evaluability thresholds", not moved,
              f"{len(moved)} threshold(s) moved: {moved}")
    rep.check("the bound policy states base QC is pre-outcome and that a missing "
              "measurement is NOT favourable",
              p.get("pre_outcome_base_qc_only") is True
              and p.get("missing_qc_is_non_evaluable") is True
              and p.get("required_base_qc_measurements")
              == EXPECTED_ELIGIBILITY_POLICY["required_base_qc_measurements"]
              and p.get("base_qc_validity")
              == EXPECTED_ELIGIBILITY_POLICY["base_qc_validity"])
    rep.check("the bound policy keeps the arms independent and never shares support",
              p.get("arms_are_independent") is True
              and p.get("arm_support_is_never_shared") is True
              and p.get("support_requires_arm_evaluable") is True)
    rep.check("the bound policy forbids inferring a guide identity",
              p.get("guide_identity_inference_permitted") is False
              and p.get("guide_resolution_ladder")
              == EXPECTED_ELIGIBILITY_POLICY["guide_resolution_ladder"])
    rep.check("the bound policy states the full rank contract, including direction",
              p.get("rank_direction") == RANK_DIRECTION
              and p.get("rank_population") == RANK_POPULATION
              and p.get("rank_tie_break") == RANK_TIE_BREAK
              and p.get("rank_dtype") == RANK_DTYPE
              and p.get("score_representation")
              == EXPECTED_ELIGIBILITY_POLICY["score_representation"]
              and p.get("nonfinite_score_rule")
              == EXPECTED_ELIGIBILITY_POLICY["nonfinite_score_rule"])

    bad = _diff(EXPECTED_ELIGIBILITY_POLICY, p)
    rep.check("the bound eligibility policy is EXACTLY the restated policy", not bad,
              f"{len(bad)} field(s) disagree: {bad[:4]}")
