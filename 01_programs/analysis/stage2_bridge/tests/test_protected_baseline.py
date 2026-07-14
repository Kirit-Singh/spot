"""Protected-baseline hardening (external review S1-M1 + S1-M2).

S1-M1: the Stage-2 scorer VIEW (what selection_id binds) is now frozen + independently rebuilt in
check_protected(); a view mutation that omits a gene/coefficient moves the canonical hash even though the
source registry and numerical artifacts are untouched.
S1-M2: a Tier-2 display field reinserted into the Tier-1 registry is rejected by a NAMED failure, and the
protected checker now runs inside the reproduce path + the normal test suite.
"""
import copy
import json
import os

import build_registry_view as rv
import protected_hashes as ph

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYSIS = os.path.dirname(HERE)
DATA = os.path.join(os.path.dirname(ANALYSIS), "app", "data")

VIEW_CANON = "5d1d8c362ee55dba048c8b5d6718cffe4525acbcda230d503f4899433c052a0c"
VIEW_RAW = "d37c19273435ff09d1705de4f64f9f185dcf4192a2bad5259cbd15d39e24915f"


def test_clean_tree_passes():
    assert ph.check_protected() == []


def test_baseline_binds_the_stage2_view():
    base = ph.load_baseline()
    assert base["stage2_view_canonical_sha256"] == VIEW_CANON
    assert base["raw_sha256"]["stage2_registry_view"] == VIEW_RAW


def test_view_gene_omission_moves_or_aborts(monkeypatch):
    """S1-M1 failure scenario: omit one measured panel gene from the view builder. It is caught EITHER by the
    count-consistency assert firing (build aborts) OR by the rebuilt canonical diverging from frozen 5d1d8c36
    — either way the Stage-2 selection binding cannot silently change."""
    reg, eu, val = rv.load_sources()
    reg2 = copy.deepcopy(reg)
    prim = next(p for p in reg2["programs"] if p.get("role") == "primary")
    prim["panel_genes_measured"] = prim["panel_genes_measured"][1:]     # omit one panel gene
    monkeypatch.setattr(rv, "load_sources", lambda: (reg2, eu, val))
    try:
        moved = rv.build_and_hash()[2] != VIEW_CANON
    except AssertionError:
        moved = True                                                    # _assert_counts_match_frozen fired
    assert moved


def test_view_coefficient_change_moves_canonical(monkeypatch):
    reg, eu, val = rv.load_sources()
    reg2 = copy.deepcopy(reg)
    prim = next(p for p in reg2["programs"] if p.get("role") == "primary")
    prim["coefficients"] = dict(prim["coefficients"])
    prim["coefficients"]["panel_coef"] = 0.5                            # tamper a coefficient
    monkeypatch.setattr(rv, "load_sources", lambda: (reg2, eu, val))
    assert rv.build_and_hash()[2] != VIEW_CANON


def test_clean_registry_has_no_tier2_leak():
    reg = json.load(open(os.path.join(DATA, "stage01_program_registry_v3.json")))
    assert ph.tier2_leak(reg) == []


def test_tier2_display_field_reinsert_detected():
    """S1-M2 failure scenario: a fully resealed display_label reinserted into a Tier-1 program is caught by
    the NAMED tier2_field_in_tier1_registry failure (independent of the raw-sha reseal)."""
    reg = json.load(open(os.path.join(DATA, "stage01_program_registry_v3.json")))
    reg["programs"][0]["display_label"] = "INJECTED TIER-2 LABEL"
    leaked = ph.tier2_leak(reg)
    assert reg["programs"][0]["program_id"] in leaked
