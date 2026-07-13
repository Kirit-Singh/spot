"""Assemble the machine-readable GBM disease-context handoff, keyed by stable gene id.

Three SEPARATE axes per gene (immune / tumor / disease) + a per-direction SUGGESTIVE
compatibility state. No rank, score, or p/q anywhere. The join key is the Ensembl gene id
(never a symbol); a row without one is refused.
"""
from __future__ import annotations

from druglink.gbm_context import build_gbm_context as bg
from druglink.gbm_context import states as st
from druglink.gbm_context import GbmContextError
import pytest


def _arm(ensembl, symbol, desired, program="prog.A", arm_key=None):
    return {"target_ensembl": ensembl, "target_symbol": symbol,
            "desired_change": desired, "program_id": program,
            "arm_key": arm_key or f"{program}:{ensembl}:{desired}", "arm_rank": 3}


def _ot_egfr():
    return {"evaluated": True, "data_version": "26.06",
            "diseases": {"MONDO_0018177": {"name": "glioblastoma",
                         "reported_overall_association_score": 0.6544,
                         "datatype_evidence": {"literature": 0.997}}}}


def _iter_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _iter_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_keys(v)


def test_gene_record_has_three_separate_axes_and_compat():
    rec = bg.build_gene_record("ENSG00000146648", "EGFR",
                               [_arm("ENSG00000146648", "EGFR", "decrease")],
                               ot_result=_ot_egfr(), dep_metrics=None)
    assert set(("immune_axis", "tumor_axis", "disease_axis", "compatibility")) <= set(rec)
    assert rec["immune_axis"]["directions"] == ["decrease"]
    assert rec["tumor_axis"]["state"] == st.NOT_EVALUATED
    assert rec["disease_axis"]["state"] == st.DA_PRESENT
    assert rec["compatibility"]["decrease"]["state"] == st.COMPAT_TUMOR_NOT_EVALUATED
    assert rec["compatibility"]["decrease"]["causal"] is False


def test_dependency_plus_immune_yields_dual_compat():
    rec = bg.build_gene_record("ENSG00000146648", "EGFR",
                               [_arm("ENSG00000146648", "EGFR", "decrease")],
                               ot_result=_ot_egfr(),
                               dep_metrics={"evaluated": True,
                                            "n_gbm_glioma_lines_evaluated": 10,
                                            "n_lines_dependent": 8,
                                            "median_gene_effect": -1.0})
    assert rec["tumor_axis"]["direction"] == st.DEP_DEPENDENCY
    assert rec["compatibility"]["decrease"]["state"] == st.COMPAT_DUAL


def test_handoff_dedupes_gene_across_arms():
    rows = [_arm("ENSG00000146648", "EGFR", "decrease", program="prog.A"),
            _arm("ENSG00000146648", "EGFR", "increase", program="prog.B")]
    h = bg.build_handoff(rows, ot_by_gene={}, dep_handoff=None)
    g = h["genes"]["ENSG00000146648"]
    assert len(g["immune_axis"]["arms"]) == 2
    assert sorted(g["immune_axis"]["directions"]) == ["decrease", "increase"]
    assert set(g["compatibility"]) == {"decrease", "increase"}


def test_handoff_metadata_declares_non_gating_contract():
    h = bg.build_handoff([_arm("ENSG00000146648", "EGFR", "decrease")],
                         ot_by_gene={}, dep_handoff=None)
    assert h["join_key"] == "target_ensembl"
    assert h["classification"] == "descriptive_non_gating"
    assert h["never_alters_ranks"] is True
    assert h["suggestive_only"] is True
    assert h["no_pq_no_overall_rank"] is True


def test_handoff_contains_no_rank_score_or_pq_anywhere():
    rows = [_arm("ENSG00000146648", "EGFR", "decrease")]
    h = bg.build_handoff(rows, ot_by_gene={"ENSG00000146648": _ot_egfr()}, dep_handoff=None)
    keys = set(_iter_keys(h))
    assert not (st.BANNED_PRODUCTION_KEYS & keys), st.BANNED_PRODUCTION_KEYS & keys


def test_row_without_ensembl_is_refused_never_symbol_joined():
    with pytest.raises(GbmContextError):
        bg.build_handoff([{"target_ensembl": None, "target_symbol": "EGFR",
                           "desired_change": "decrease", "program_id": "p",
                           "arm_key": "k"}], ot_by_gene={}, dep_handoff=None)
