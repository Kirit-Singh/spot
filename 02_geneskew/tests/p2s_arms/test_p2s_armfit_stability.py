"""MUTATIONS 3 and 8 — opposed contributors, and determinism. Plus the sign-transform law.

The scientific claim this lane rests on is that the two arms of a program are ONE
measurement and a sign. If that is not exactly true, a reader comparing the arms is reading
a difference that nothing measured.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fixtures_p2s import CONDITION, CONTRIBUTOR, OPPONENT, PROGRAM, gene_ids, linear_fit, target_ids
from p2s_arms import armfit, config, model, stability

INC = f"direct|{PROGRAM}|increase|{CONDITION}"
DEC = f"direct|{PROGRAM}|decrease|{CONDITION}"


@pytest.fixture
def planted():
    """X whose T00 column reconstructs the signature and whose T01 column OPPOSES it."""
    rng = np.random.default_rng(5)
    genes, targets = gene_ids(120), target_ids()
    direction = np.zeros(len(genes))
    direction[:30] = 1.0

    cols = {}
    for t in targets:
        v = rng.normal(0, 0.3, size=len(genes))
        if t == CONTRIBUTOR:
            v = v + 2.0 * direction
        elif t == OPPONENT:
            v = v - 2.0 * direction
        cols[t] = v
    x = pd.DataFrame(cols, index=pd.Index(genes, name="gene_id"), columns=targets)
    return x, direction


def fit_both(planted, seed=config.RANDOM_STATE):
    x, direction = planted
    return armfit.fit_program(program_id=PROGRAM, condition=CONDITION,
                              base_signature=direction, x=x, cfg=config.CONFIGS[0],
                              layer="zscore", scope="all_donor", fit=linear_fit, seed=seed)


# --------------------------------------------------------------------------- #
# The sign-transform law: ONE measurement, TWO arms.
# --------------------------------------------------------------------------- #
def test_the_two_arms_are_EXACT_negations_of_each_other(planted):
    rows = fit_both(planted)["coefficients"]
    inc = {r["target_id"]: r["coefficient"] for r in rows if r["arm_key"] == INC}
    dec = {r["target_id"]: r["coefficient"] for r in rows if r["arm_key"] == DEC}

    assert set(inc) == set(dec)
    for t in inc:
        assert inc[t] == -dec[t] or (inc[t] == 0.0 and dec[t] == 0.0)


def test_a_zero_negates_to_positive_zero_never_minus_zero():
    """A sign on a zero is a distinction the data does not make — and it prints differently."""
    out = armfit.negate([0.0, 2.0, -3.0], "decrease")
    assert out == [0.0, -2.0, 3.0]
    assert not np.signbit(out[0])


def test_the_reconstruction_metrics_are_identical_on_both_arms(planted):
    """They are sign-invariant: reconstructing -y from -b fits exactly as well."""
    recon = fit_both(planted)["reconstruction"]
    by_arm = {r["arm_key"]: r["reconstruction_gene_cv_test_r2_mean"] for r in recon}
    assert by_arm[INC] == by_arm[DEC]
    assert all(r["metrics_are_sign_invariant"] is True for r in recon)


def test_the_cv_is_labelled_gene_cv_and_never_donor_or_external(planted):
    for r in fit_both(planted)["reconstruction"]:
        assert r["cv_label"] == "reconstruction_gene_cv"
        assert "donor" not in r["cv_label"] and "external" not in r["cv_label"]


# --------------------------------------------------------------------------- #
# MUTATION 3 — the opposed contributor. Kept opposed; never converted; never dropped.
# --------------------------------------------------------------------------- #
def test_MUTATION_a_negative_contributor_gets_a_NEGATIVE_coefficient(planted):
    rows = fit_both(planted)["coefficients"]
    inc = {r["target_id"]: r["coefficient"] for r in rows if r["arm_key"] == INC}
    assert inc[CONTRIBUTOR] > 0, "the planted contributor must reconstruct the signature"
    assert inc[OPPONENT] < 0, "the planted opponent uses the INVERSE of the knockdown"


def test_MUTATION_an_opposed_contributor_is_reported_opposed_and_never_as_support(planted):
    rows = fit_both(planted)["coefficients"]
    support = {(r["arm_key"], r["target_id"]): r for r in stability.compute(rows)}

    opponent = support[(INC, OPPONENT)]
    assert opponent["support_status"] == config.OPPOSED
    assert opponent["opposed"] is True
    assert opponent["negative_frequency"] >= config.SUPPORT_SIGN_DOMINANCE

    contributor = support[(INC, CONTRIBUTOR)]
    assert contributor["support_status"] == config.SUPPORTED
    assert contributor["opposed"] is False


def test_MUTATION_the_opposed_status_FLIPS_with_the_arm(planted):
    """Under the sign transform, what supports `increase` opposes `decrease`. Both are stated."""
    rows = fit_both(planted)["coefficients"]
    support = {(r["arm_key"], r["target_id"]): r for r in stability.compute(rows)}

    assert support[(INC, CONTRIBUTOR)]["support_status"] == config.SUPPORTED
    assert support[(DEC, CONTRIBUTOR)]["support_status"] == config.OPPOSED
    assert support[(INC, OPPONENT)]["support_status"] == config.OPPOSED
    assert support[(DEC, OPPONENT)]["support_status"] == config.SUPPORTED


def test_a_positive_constraint_that_would_erase_opposed_contributors_is_REFUSED():
    with pytest.raises(model.ModelError) as e:
        model.validate_positive(True)
    assert e.value.reason == "positive_constraint_would_erase_opposed_contributors"


# --------------------------------------------------------------------------- #
# MUTATION 8 — determinism.
# --------------------------------------------------------------------------- #
def test_MUTATION_two_runs_at_seed_42_are_byte_identical(planted):
    a = fit_both(planted, seed=42)["coefficients"]
    b = fit_both(planted, seed=42)["coefficients"]
    assert [r["coefficient"] for r in a] == [r["coefficient"] for r in b]


def test_MUTATION_a_changed_seed_changes_the_numbers_so_it_cannot_pass_unnoticed(planted):
    a = fit_both(planted, seed=42)["coefficients"]
    b = fit_both(planted, seed=1)["coefficients"]
    assert [r["coefficient"] for r in a] != [r["coefficient"] for r in b]


# --------------------------------------------------------------------------- #
# The l1 grid, validated rather than assumed.
# --------------------------------------------------------------------------- #
def test_the_pinned_l1_grid_is_valid():
    assert model.validate_l1_grid(config.L1_RATIO_GRID) == tuple(config.L1_RATIO_GRID)
    assert all(0.0 <= v <= 1.0 for v in config.L1_RATIO_GRID)


@pytest.mark.parametrize("bad", [[-0.1], [1.5], [0.5, 2.0], [float("nan")]])
def test_an_l1_ratio_outside_0_1_is_REFUSED_not_clipped(bad):
    with pytest.raises(model.ModelError) as e:
        model.validate_l1_grid(bad)
    assert e.value.reason == "l1_ratio_out_of_range"


def test_an_empty_l1_grid_is_refused():
    with pytest.raises(model.ModelError) as e:
        model.validate_l1_grid([])
    assert e.value.reason == "empty_l1_grid"


# --------------------------------------------------------------------------- #
# Counting rules: a zero never disappears, and no-evidence is never perfect agreement.
# --------------------------------------------------------------------------- #
def test_a_zero_coefficient_stays_in_the_denominator():
    rows = [
        {"arm_key": INC, "program_id": PROGRAM, "desired_change": "increase",
         "condition": CONDITION, "target_id": "T00", "coefficient": c,
         "nonzero": c != 0, "sign": int(np.sign(c)), "effect_layer": "zscore",
         "model_config": "pca_off", "donor_scope": s}
        for c, s in [(1.0, "all_donor"), (0.0, "lodo_D1"), (0.0, "lodo_D2"),
                     (0.0, "lodo_D3")]
    ]
    got = stability.compute(rows)[0]
    assert got["n_runs"] == 4                       # the DENOMINATOR ships with the number
    assert got["n_selected_runs"] == 1
    assert got["selection_frequency"] == 0.25
    assert got["support_status"] == config.WEAK     # 1-of-4 is not robustness


def test_no_evidence_is_reported_as_None_never_as_perfect_agreement():
    assert stability._sign_agreement([0, 0, 0]) is None
    assert stability._sign_agreement([1, 1, 1]) == 1.0
    assert stability._sign_agreement([1, -1]) == 0.5


def test_lodo_fits_are_never_called_independent_replicates():
    block = stability.method_block()
    assert block["lodo_fits_are_independent_replicates"] is False
    assert "not independent replicates" in block["lodo_semantics"]
    assert block["rank_column_emitted"] is False
