"""Gene-universe exclusion + masking tests (plan §6.2.8, §6.3, §6.9)."""
import numpy as np
from perturb2state import pmatrix
from perturb2state import universe as U


def _axis():
    return {
        "A": {"program_id": "treg_like", "direction": "high",
              "panel_ensembl": ["ENSG_AP1", "ENSG_AP2"],
              "control_ensembl": ["ENSG_AC1", None]},
        "B": {"program_id": "th1_like", "direction": "high",
              "panel_ensembl": ["ENSG_BP1"], "control_ensembl": ["ENSG_BC1"]},
    }


def test_excluded_panel_control_drops_nulls():
    excl = U.excluded_panel_control(_axis())
    assert excl == {"ENSG_AP1", "ENSG_AP2", "ENSG_AC1", "ENSG_BP1", "ENSG_BC1"}


def test_excluded_panel_control_cannot_enter_universe():
    de_ids = ["ENSG_AP1", "ENSG_BC1", "ENSG_X", "ENSG_Y"]
    de_syms = ["AP1", "BC1", "X", "Y"]
    ntc = ["AP1", "BC1", "X", "Y", "Z"]
    uni = U.build_universe(de_ids, de_syms, ntc, U.excluded_panel_control(_axis()))
    assert "ENSG_AP1" not in uni["gene_ids"]      # A panel gene excluded
    assert "ENSG_BC1" not in uni["gene_ids"]      # B control gene excluded
    assert uni["gene_ids"] == ["ENSG_X", "ENSG_Y"]
    assert uni["exclusion_counts"]["in_excluded_panel_control"] == 2


def test_gene_order_invariance_of_universe():
    """Universe ordering is canonical (Ensembl-sorted) regardless of DE input order."""
    ntc = ["A", "B", "C"]
    u1 = U.build_universe(["ENSG3", "ENSG1", "ENSG2"], ["C", "A", "B"], ntc, set())
    u2 = U.build_universe(["ENSG1", "ENSG2", "ENSG3"], ["A", "B", "C"], ntc, set())
    assert u1["gene_ids"] == u2["gene_ids"] == ["ENSG1", "ENSG2", "ENSG3"]
    assert u1["universe_sha256"] == u2["universe_sha256"]


def test_symbol_absent_or_ambiguous_excluded():
    de_ids = ["ENSG1", "ENSG2", "ENSG3"]
    de_syms = ["A", "B", "MISSING"]
    ntc = ["A", "B", "B"]                         # B ambiguous, MISSING absent
    uni = U.build_universe(de_ids, de_syms, ntc, set())
    assert uni["gene_ids"] == ["ENSG1"]
    assert uni["exclusion_counts"]["symbol_ambiguous_in_ntc"] == 1
    assert uni["exclusion_counts"]["symbol_absent_in_ntc"] == 1


def test_intended_and_offtarget_masking_zeroes_columns():
    de_ids = ["ENSG1", "ENSG2", "ENSG3", "ENSG4"]
    universe = ["ENSG1", "ENSG2", "ENSG3", "ENSG4"]
    # target T1 effect vector; mask its own gene (ENSG1) + off-target neighbor (ENSG3)
    eff = {"T1": np.array([5.0, 6.0, 7.0, 8.0])}
    mask = {"T1": {"ENSG1", "ENSG3"}}
    X, cov = pmatrix.build_masked_X(eff, de_ids, universe, ["T1"], mask)
    col = X["T1"].to_numpy()
    assert col[0] == 0.0 and col[2] == 0.0        # intended + off-target -> 0
    assert col[1] == 6.0 and col[3] == 8.0        # untouched
    assert cov["T1"]["n_masked_in_universe"] == 2
    assert cov["T1"]["n_retained"] == 2


def test_target_order_invariance_of_X_columns():
    de_ids = ["ENSG1", "ENSG2"]
    universe = ["ENSG1", "ENSG2"]
    eff = {"T1": np.array([1.0, 2.0]), "T2": np.array([3.0, 4.0])}
    X_a, _ = pmatrix.build_masked_X(eff, de_ids, universe, ["T1", "T2"], {})
    X_b, _ = pmatrix.build_masked_X(eff, de_ids, universe, ["T2", "T1"], {})
    # same per-target column content regardless of requested order
    assert np.allclose(X_a["T1"], X_b["T1"]) and np.allclose(X_a["T2"], X_b["T2"])
