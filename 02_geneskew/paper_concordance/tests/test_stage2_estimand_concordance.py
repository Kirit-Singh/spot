"""The comparability tiers are the whole point: a verdict is emitted ONLY where the released
estimands actually permit one. IL2/IL10 are in no released program panel, so Stage-2 says
nothing about them; a program delta is never equated to a per-cytokine effect.
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import stage2_estimand_concordance as sc

REGISTRY = [
    {"program_id": "th1_like", "panel_symbols": ["TBX21", "IFNG", "CXCR3"]},
    {"program_id": "th2_like", "panel_symbols": ["GATA3", "IL13", "IL4", "IL5"]},
    {"program_id": "tfh_like", "panel_symbols": ["BCL6", "IL21", "CXCR5"]},
    {"program_id": "treg_like", "panel_symbols": ["FOXP3", "IL2RA", "CTLA4"]},
]


def test_il2_and_il10_are_not_comparable_absent_from_all_panels():
    for cyto in ("IL2", "IL10"):
        c = sc.comparability(cyto, REGISTRY)
        assert c["tier"] == sc.TIER_CYTOKINE_ABSENT
        assert c["programs"] == []


def test_il13_and_il21_are_panel_members_but_not_equivalent():
    c = sc.comparability("IL13", REGISTRY)
    assert c["tier"] == sc.TIER_PROJECTION_NOT_EQUIVALENT
    assert c["programs"] == ["th2_like"]
    assert sc.comparability("IL21", REGISTRY)["programs"] == ["tfh_like"]


def test_broad_effect_has_no_breadth_estimand():
    assert sc.comparability(None, REGISTRY, kind="broad_effect")["tier"] == sc.TIER_NO_BREADTH


def test_verdict_only_on_the_shared_substrate():
    v = sc.substrate_verdict("negative", -4.78)          # GATA3 -> IL13, positive regulator
    assert v["tier"] == sc.TIER_SAME_SUBSTRATE
    assert v["observed_log_fc_sign"] == "negative" and v["concordant"] is True
    assert sc.substrate_verdict("negative", 1.2)["concordant"] is False


def test_projection_observation_never_emits_a_verdict():
    o = sc.projection_observation("th2_like", -0.42, "ok", 4, 120)
    assert o["verdict"] is None                     # descriptive only
    assert o["delta_p_sign"] == "negative"
    assert o["inference"].startswith("none")        # no p/q
    assert "not a per-cytokine effect" in o["note"]


def test_paper_and_our_inference_are_distinguished():
    assert "FDR" in sc.PAPER_INFERENCE
    assert "no p/q" in sc.OUR_INFERENCE
    assert sc.PAPER_MODALITY.startswith("mRNA") and sc.OUR_MODALITY.startswith("mRNA")


def test_read_only_classification():
    assert sc.CLASSIFICATION == "read_only_diagnostic_non_gating"
