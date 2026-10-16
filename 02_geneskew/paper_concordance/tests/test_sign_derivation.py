"""Deterministic sign-control re-derivation over an abstract DE accessor (no h5py needed).

Paper sign convention (Zhu/Dann 2025, p9): the readout is the cytokine's log2FC on
regulator KNOCKDOWN. negative regulator => KD raises cytokine => log_fc > 0; positive
regulator => KD lowers cytokine => log_fc < 0. This lane is NON-RANKING and NON-GATING;
upstream FDR is a provenance diagnostic only.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))

import sign_derivation as sd  # noqa: E402


def _observe(table):
    def observe(regulator, cytokine, condition):
        v = table.get((regulator, cytokine, condition))
        if v is None:
            return {"present": False}
        return {"present": True, "log_fc": v[0], "adj_p": v[1]}
    return observe


CONDS = ["Rest", "Stim8hr", "Stim48hr"]


def test_negative_regulator_expects_positive_log_fc():
    ctrl = {"id": "men1_il10", "kind": "directional", "regulators": ["MEN1"],
            "cytokine": "IL10", "expected_role": "negative_regulator",
            "expected_log_fc_sign": "positive"}
    obs = _observe({("MEN1", "IL10", "Stim8hr"): (4.42, 2e-5),
                    ("MEN1", "IL10", "Rest"): (-0.26, 0.99)})
    r = sd.derive_control(ctrl, observe=obs, conditions=CONDS)
    assert r["outcome"]["concordant_significant"] is True
    stim = next(o for o in r["observations"] if o["condition"] == "Stim8hr")
    assert stim["observed_sign"] == "positive" and stim["concordant"] is True
    assert stim["provenance_diagnostics"]["significant_at_5pct"] is True


def test_positive_regulator_expects_negative_log_fc():
    ctrl = {"id": "gata3_il13", "kind": "directional", "regulators": ["GATA3"],
            "cytokine": "IL13", "expected_role": "positive_regulator",
            "expected_log_fc_sign": "negative"}
    obs = _observe({("GATA3", "IL13", "Stim8hr"): (-4.78, 4.5e-18)})
    r = sd.derive_control(ctrl, observe=obs, conditions=CONDS)
    assert r["outcome"]["concordant_significant"] is True


def test_divergent_control_requires_both_signs_concordant():
    ctrl = {"id": "nfkb2", "kind": "directional", "regulators": ["NFKB2"],
            "divergent": [{"cytokine": "IL10", "expected_role": "positive_regulator",
                           "expected_log_fc_sign": "negative"},
                          {"cytokine": "IL21", "expected_role": "negative_regulator",
                           "expected_log_fc_sign": "positive"}]}
    good = _observe({("NFKB2", "IL10", "Stim8hr"): (-2.17, 0.04),
                     ("NFKB2", "IL21", "Stim8hr"): (1.75, 0.028)})
    assert sd.derive_control(ctrl, observe=good, conditions=["Stim8hr"])[
        "outcome"]["concordant_significant"] is True
    bad = _observe({("NFKB2", "IL10", "Stim8hr"): (2.0, 0.04),      # IL10 wrong sign
                    ("NFKB2", "IL21", "Stim8hr"): (1.75, 0.028)})
    assert sd.derive_control(ctrl, observe=bad, conditions=["Stim8hr"])[
        "outcome"]["concordant_significant"] is False


def test_upstream_adj_p_confined_to_provenance_diagnostics():
    ctrl = {"id": "men1_il10", "kind": "directional", "regulators": ["MEN1"],
            "cytokine": "IL10", "expected_role": "negative_regulator",
            "expected_log_fc_sign": "positive"}
    r = sd.derive_control(ctrl, observe=_observe(
        {("MEN1", "IL10", "Stim8hr"): (4.42, 2e-5)}), conditions=["Stim8hr"])
    o = r["observations"][0]
    assert "adj_p_value" not in o and "p_value" not in o          # never top-level
    assert o["provenance_diagnostics"]["label"] == "authors_reported_upstream"
    assert o["provenance_diagnostics"]["used_for_gating_or_ranking"] is False


def test_absent_gene_is_recorded_not_invented():
    ctrl = {"id": "x", "kind": "directional", "regulators": ["NOPE"], "cytokine": "IL10",
            "expected_role": "negative_regulator", "expected_log_fc_sign": "positive"}
    r = sd.derive_control(ctrl, observe=_observe({}), conditions=["Stim8hr"])
    assert r["observations"][0]["present"] is False
    assert r["outcome"]["concordant_significant"] is False


def test_broad_effect_control_counts_significant_cytokines():
    ctrl = {"id": "broad", "kind": "broad_effect", "regulators": ["MED24"]}
    table = {("MED24", c, "Stim8hr"): (-2.0, 1e-4)
             for c in ["IL2", "IL10", "TNF", "IL16", "IL21"]}
    r = sd.derive_broad_control(ctrl, observe=_observe(table), conditions=["Stim8hr"],
                                cytokine_panel=["IL2", "IL10", "TNF", "IL16", "IL21", "IL4"],
                                broad_min_cytokines=3)
    assert r["per_regulator"]["MED24"]["max_n_significant_cytokines"] == 5
    assert r["outcome"]["broad"] is True


def test_derive_all_wires_the_spec_cytokine_panel_to_broad_controls():
    # regression: derive_all must pass the spec's named cytokine panel to broad controls,
    # not an empty list (a key-name mismatch silently made every broad count 0).
    spec = {"spec_id": "x", "conditions": ["Stim8hr"],
            "cytokine_panel_paper_named": ["IL10", "IFNG", "IL13"],
            "broad_min_cytokines": 2,
            "controls": [{"id": "broad", "kind": "broad_effect", "regulators": ["MED24"]}]}
    table = {("MED24", c, "Stim8hr"): (-2.0, 1e-4) for c in ["IL10", "IFNG", "IL13"]}
    r = sd.derive_all(spec, observe=_observe(table))
    broad = r["results"][0]
    assert broad["per_regulator"]["MED24"]["max_n_significant_cytokines"] == 3
    assert broad["outcome"]["broad"] is True


def test_output_carries_no_ranking_or_gating_field():
    ctrl = {"id": "men1_il10", "kind": "directional", "regulators": ["MEN1"],
            "cytokine": "IL10", "expected_role": "negative_regulator",
            "expected_log_fc_sign": "positive"}
    r = sd.derive_control(ctrl, observe=_observe(
        {("MEN1", "IL10", "Stim8hr"): (4.42, 2e-5)}), conditions=["Stim8hr"])
    assert not (sd.BANNED_PRODUCTION_KEYS & set(r.keys()))
    assert r["classification"] == "diagnostic_non_gating"
