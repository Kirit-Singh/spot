"""The Stage-2 comparison is DESCRIPTIVE and NON-GATING: it records which control
regulators appear in the eventual Stage-2 output alongside their paper control(s). It never
asserts directional equivalence (the estimands differ) and never changes a rank or gates.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))

import compare_stage2 as cs  # noqa: E402

SPEC = {"controls": [
    {"id": "men1_il10", "kind": "directional", "regulators": ["MEN1"], "cytokine": "IL10",
     "expected_role": "negative_regulator"},
    {"id": "gata3_il13", "kind": "directional", "regulators": ["GATA3"], "cytokine": "IL13",
     "expected_role": "positive_regulator"}]}


def test_overlap_is_descriptive_and_non_gating():
    stage2 = [{"target_symbol": "MEN1", "program_id": "treg",
               "desired_change": "decrease", "condition": "Stim8hr"}]
    r = cs.compare_to_stage2(SPEC, stage2)
    assert r["classification"] == "diagnostic_non_gating"
    assert r["does_not_alter_ranks"] is True
    assert r["does_not_claim_exact_replication"] is True
    men1 = next(o for o in r["overlaps"] if o["regulator"] == "MEN1")
    assert men1["in_stage2"] is True
    assert men1["stage2_appearances"][0]["desired_change"] == "decrease"
    gata3 = next(o for o in r["overlaps"] if o["regulator"] == "GATA3")
    assert gata3["in_stage2"] is False
    assert r["n_in_stage2"] == 1 and r["n_control_regulators"] == 2


def test_records_both_directions_but_asserts_no_equivalence():
    stage2 = [{"target_symbol": "MEN1", "program_id": "treg",
               "desired_change": "increase", "condition": "Stim8hr"}]
    r = cs.compare_to_stage2(SPEC, stage2)
    men1 = next(o for o in r["overlaps"] if o["regulator"] == "MEN1")
    # both are recorded; no field claims they should match
    assert men1["paper_controls"][0]["expected_role"] == "negative_regulator"
    assert men1["stage2_appearances"][0]["desired_change"] == "increase"
    assert "directional_equivalence" not in men1
    assert "concordant" not in men1        # no pass/fail verdict on the overlap


def test_output_has_no_ranking_or_gating_field():
    r = cs.compare_to_stage2(SPEC, [])
    banned = {"rank", "score", "gate", "production_candidate", "priority", "combined_score"}
    assert not (banned & set(r.keys()))
    for o in r["overlaps"]:
        assert not (banned & set(o.keys()))


def test_join_is_on_exact_symbol_or_ensembl_never_partial():
    stage2 = [{"target_ensembl": "ENSG00000133895", "program_id": "treg",
               "desired_change": "decrease"}]   # MEN1 ensembl, no symbol
    spec = {"controls": [{"id": "men1", "regulators": ["MEN1"], "cytokine": "IL10"}]}
    r = cs.compare_to_stage2(spec, stage2, symbol_to_ensembl={"MEN1": "ENSG00000133895"})
    assert next(o for o in r["overlaps"] if o["regulator"] == "MEN1")["in_stage2"] is True
