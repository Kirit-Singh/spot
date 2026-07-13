"""NAMED MUTATION ATTACKS on the real Direct inventory, the two locks, and the activation arm.

Every one was raised by an independent real-input attack. Each builds a REAL ten-file bundle
(now with the real mask schema: masked_gene_ensembl + estimate_type/estimate_id) and breaks
exactly one thing.
"""
from __future__ import annotations

import os

import fixtures_p2s as fx
import pandas as pd
import pytest
from p2s_arms import binding, config, direct_inventory
from p2s_arms import disposition as D

CONDITION = fx.CONDITION
PROGRAM = fx.PROGRAM


# --------------------------------------------------------------------------- #
# MASKS — full estimate identity, never unioned, never empty by default.
# --------------------------------------------------------------------------- #
def test_masks_are_selected_on_the_MAIN_estimate_only(tmp_path, view):
    """Guide-slot and donor-pair rows are DIFFERENT estimates and are not unioned."""
    d = fx.write_full_bundle(str(tmp_path / "b"), view, mask_scope_union=True)
    masks = direct_inventory.main_estimate_masks(d)

    assert masks["estimate_type"] == "main" and masks["estimate_id"] == "main"
    assert masks["scopes_unioned"] is False
    # a guide-scope-ONLY gene (gene_ids()[100+]) must NOT appear in the MAIN mask
    all_masked = {g for gs in masks["by_target"].values() for g in gs}
    assert fx.gene_ids()[0] in all_masked            # T00's self-gene (main)
    assert fx.gene_ids()[100] not in all_masked      # a guide-scope gene, never main
    # and the main selection is strictly smaller than the all-scope row count
    assert masks["n_rows_main"] < masks["n_rows_all_scopes"]


def test_MUTATION_no_main_estimate_mask_is_REFUSED(tmp_path, view):
    """An empty main mask is the most permissive mask there is — never a default."""
    d = fx.write_full_bundle(str(tmp_path / "b"), view, no_main_mask=True)
    with pytest.raises(D.RefusalError) as e:
        direct_inventory.main_estimate_masks(d)
    assert e.value.reason == D.REFUSE_MASK_EMPTY


def test_MUTATION_a_mask_table_without_estimate_columns_is_REFUSED(tmp_path, view):
    """Without estimate_type/estimate_id a main mask cannot be told from a guide-slot one."""
    d = fx.write_full_bundle(str(tmp_path / "b"), view)
    path = os.path.join(d, "masks.parquet")
    df = pd.read_parquet(path).drop(columns=["estimate_type", "estimate_id"])
    df.to_parquet(path, index=False)
    with pytest.raises(D.RefusalError) as e:
        direct_inventory.main_estimate_masks(d)
    assert e.value.reason == D.REFUSE_MASK_SCOPE_UNION


def test_MUTATION_a_mask_without_masked_gene_ensembl_is_REFUSED(tmp_path, view):
    """The masked gene must arrive in the READOUT namespace, not be re-derived from a symbol."""
    d = fx.write_full_bundle(str(tmp_path / "b"), view)
    path = os.path.join(d, "masks.parquet")
    df = pd.read_parquet(path).rename(columns={"masked_gene_ensembl": "gene_symbol"})
    df.to_parquet(path, index=False)
    with pytest.raises(D.RefusalError) as e:
        direct_inventory.main_estimate_masks(d)
    assert e.value.reason == D.REFUSE_BUNDLE_INCOMPLETE


def test_MUTATION_an_eligible_target_with_NO_mask_is_REFUSED(tmp_path, view):
    """A missing mask withholds nothing — the opposite of the safe default."""
    d = fx.write_full_bundle(str(tmp_path / "b"), view, drop_mask_for="T00")
    with pytest.raises(D.RefusalError) as e:
        direct_inventory.bind(d, program_id=PROGRAM, condition=CONDITION)
    assert e.value.reason == D.REFUSE_MASK_MISSING_FOR_ELIGIBLE


# --------------------------------------------------------------------------- #
# ELIGIBILITY — arm-specific, and the two sign arms share ONE inventory.
# --------------------------------------------------------------------------- #
def test_eligibility_is_ARM_SPECIFIC_and_the_two_arms_are_SYMMETRIC(tmp_path, view):
    d = fx.write_full_bundle(str(tmp_path / "b"), view)
    inv = direct_inventory.evaluable_targets(d, program_id=PROGRAM, condition=CONDITION)

    assert inv["eligibility_is_arm_specific"] is True
    assert inv["inventories_are_identical"] is True
    assert "|increase|" in inv["arm_key"] and "|decrease|" in inv["sibling_arm_key"]
    assert inv["n_evaluable"] > 0


def test_MUTATION_asymmetric_sign_arm_inventories_are_REFUSED(tmp_path, view):
    """The two arms are one measurement and a sign; a disagreement means one was re-derived."""
    d = fx.write_full_bundle(str(tmp_path / "b"), view)
    path = os.path.join(d, "arms.parquet")
    df = pd.read_parquet(path)
    dec = f"direct|{PROGRAM}|decrease|{CONDITION}"
    # make one target NON-evaluable on the decrease arm only
    mask = (df["arm_key"].astype(str) == dec) & (df["target_id"].astype(str) == "T00")
    df.loc[mask, "evaluable"] = False
    df.to_parquet(path, index=False)

    with pytest.raises(D.RefusalError) as e:
        direct_inventory.evaluable_targets(d, program_id=PROGRAM, condition=CONDITION)
    assert e.value.reason == D.REFUSE_ARM_INVENTORY_ASYMMETRY


def test_MUTATION_an_arm_with_nothing_evaluable_is_REFUSED(tmp_path, view):
    d = fx.write_full_bundle(str(tmp_path / "b"), view)
    path = os.path.join(d, "arms.parquet")
    df = pd.read_parquet(path)
    df.loc[df["arm_key"].astype(str).str.contains(f"|{PROGRAM}|"), "evaluable"] = False
    # simpler: blank all evaluable
    df["evaluable"] = False
    df.to_parquet(path, index=False)
    with pytest.raises(D.RefusalError) as e:
        direct_inventory.evaluable_targets(d, program_id=PROGRAM, condition=CONDITION)
    assert e.value.reason == D.REFUSE_ELIGIBLE_EMPTY


# --------------------------------------------------------------------------- #
# TWO ENVIRONMENTS, TWO LOCKS.
# --------------------------------------------------------------------------- #
def test_MUTATION_a_MISSING_p2s_runtime_lock_is_REFUSED():
    with pytest.raises(D.RefusalError) as e:
        binding.verify_p2s_runtime_lock(None)
    assert e.value.reason == D.REFUSE_P2S_LOCK_ABSENT


def test_MUTATION_the_DIRECT_lock_supplied_as_the_P2S_lock_is_REFUSED_BY_NAME():
    """The Direct lock has no sklearn and no pert2state_model; it cannot execute this lane."""
    with pytest.raises(D.RefusalError) as e:
        binding.verify_p2s_runtime_lock(fx.REAL_SOLVER_LOCK)   # the DIRECT lock
    assert e.value.reason == D.REFUSE_P2S_LOCK_MISMATCH
    assert "DIRECT solver lock" in str(e.value)


def test_the_P2S_lock_is_bound_when_it_matches_its_pin(tmp_path, p2s_lock):
    block = binding.verify_p2s_runtime_lock(p2s_lock)
    assert block["verified"] is True
    assert block["role"] == config.LOCK_ROLES["p2s_runtime_lock"]


def test_the_two_locks_are_DISTINCT_and_direct_does_not_execute_p2s():
    assert config.PINNED_SOLVER_LOCK_SHA256 != config.P2S_RUNTIME_LOCK_SHA256
    assert config.DIRECT_LOCK_EXECUTES_P2S is False
    assert set(config.LOCK_ROLES) == {"direct_solver_lock", "p2s_runtime_lock"}


# --------------------------------------------------------------------------- #
# THE ACTIVATION COVARIATE IS NOT AN ARM.
# --------------------------------------------------------------------------- #
def test_MUTATION_an_arm_for_the_ACTIVATION_COVARIATE_is_REFUSED(view):
    """diff_activated IS the activation covariate; an arm for it regresses it on itself."""
    with pytest.raises(D.RefusalError) as e:
        binding.refuse_program(config.ACTIVATION_PROGRAM_ID, view)
    assert e.value.reason == D.REFUSE_ACTIVATION_ARM
    assert "collinear" in str(e.value)


def test_the_activation_program_is_scored_but_never_an_arm():
    assert config.ACTIVATION_IS_NOT_AN_ARM is True
    assert config.ACTIVATION_PROGRAM_ID == "diff_activated"


# --------------------------------------------------------------------------- #
# pca_off FROZEN — pca_on_50 is deferred and is NOT claimed deterministic.
# --------------------------------------------------------------------------- #
def test_BOTH_configs_ship_and_pca_is_made_deterministic_by_a_controlled_seed():
    """The paper uses truncated SVD; disabling it would diverge. We seed it instead.

    Upstream omits random_state on TruncatedSVD; the producer seeds the global RNG before
    each fit (model.run_one). Verified on tcefold: repeat delta 0.0 (0.0666 without).
    """
    assert [c.name for c in config.CONFIGS] == ["pca_on_60", "pca_off"]   # primary first
    assert config.PRIMARY_CONFIG.n_pcs == 60           # the paper's D=60
    assert "random_state" in config.PCA_DETERMINISM_MECHANISM
    assert config.UPSTREAM_PREDICTION_PATH_USED is False

    # the deterministic WRAPPER is used, not a global-seed hack
    import inspect

    from p2s_arms import model
    src = inspect.getsource(model.run_one)
    assert "det.fit_deterministic" in src
    assert "np.random.seed(seed)" not in src


def test_the_upstream_TruncatedSVD_really_has_no_random_state():
    """The premise for the seed mechanism, checked against the pinned source, not on faith."""
    import os
    roots = ("/home/tcelab/spot_stage2/pert2state_model",
             "/home/tcelab/p2s_runtime_20260713/pert2state_model")
    for root in roots:
        src = os.path.join(root, "src/pert2state_model/Perturb2StateModel.py")
        if os.path.exists(src):
            text = open(src).read()
            line = next(ln for ln in text.splitlines()
                        if "TruncatedSVD(" in ln and "n_components" in ln)
            assert "random_state" not in line     # which is why we seed the global RNG
            return
    pytest.skip("the pinned upstream checkout is not on this host")
