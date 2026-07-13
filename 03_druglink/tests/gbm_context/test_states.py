"""Pure typed-state logic for the Stage-3 v2 GBM disease-context evidence layer.

DESCRIPTIVE, NON-RANKING, NON-GATING. Immune-cell effect and tumor-cell context are
kept on SEPARATE axes; missing evidence is ``not_evaluated`` and is never invented.
No p/q, no score, no rank ever enters an output.
"""
from __future__ import annotations
from druglink.gbm_context import states as st


def test_immune_direction_maps_desired_change_verbatim_tokens():
    assert st.immune_direction("increase") == st.IMMUNE_INCREASE
    assert st.immune_direction("decrease") == st.IMMUNE_DECREASE
    assert st.immune_direction("whatever") == st.IMMUNE_UNKNOWN
    assert st.immune_direction(None) == st.IMMUNE_UNKNOWN


def test_tumor_dependency_not_evaluated_when_no_official_bytes():
    r = st.tumor_dependency_state(None)
    assert r["state"] == st.NOT_EVALUATED
    assert r["direction"] is None and r["coverage"] is None
    # reason is recorded, not blank
    assert r["reason"]


def test_tumor_dependency_direction_and_coverage_from_synthetic_metrics():
    metrics = {"evaluated": True, "n_gbm_glioma_lines_evaluated": 12,
               "n_lines_dependent": 9, "median_gene_effect": -0.87}
    r = st.tumor_dependency_state(metrics, dependency_prob_threshold=0.5)
    assert r["state"] == "evaluated"
    assert r["direction"] == st.DEP_DEPENDENCY
    assert r["coverage"]["n_gbm_glioma_lines_evaluated"] == 12
    assert r["coverage"]["n_lines_dependent"] == 9
    assert r["coverage"]["dependency_prob_threshold"] == 0.5
    # a descriptive median effect may be carried, but never a p/q or rank
    assert r["median_gene_effect"] == -0.87


def test_tumor_dependency_non_dependency_when_zero_dependent_lines():
    metrics = {"evaluated": True, "n_gbm_glioma_lines_evaluated": 10,
               "n_lines_dependent": 0, "median_gene_effect": 0.02}
    r = st.tumor_dependency_state(metrics)
    assert r["direction"] == st.DEP_NON_DEPENDENCY


def test_disease_association_present_carries_datatype_evidence_non_gating():
    ot = {"evaluated": True, "diseases": {
        "MONDO_0018177": {"name": "glioblastoma",
                          "reported_overall_association_score": 0.6544,
                          "datatype_evidence": {"literature": 0.997, "somatic_mutation": 0.857}}}}
    r = st.disease_association_state(ot)
    assert r["state"] == st.DA_PRESENT
    gbm = r["diseases"]["MONDO_0018177"]
    # OT's own score is carried but explicitly flagged not-for-gating/ranking
    assert gbm["reported_overall_association_score"] == 0.6544
    assert gbm["used_for_gating_or_ranking"] is False
    assert gbm["label"] == "open_targets_reported_upstream"


def test_disease_association_not_evaluated_and_absent_are_distinct():
    assert st.disease_association_state(None)["state"] == st.NOT_EVALUATED
    assert st.disease_association_state({"evaluated": True, "diseases": {}})["state"] == st.DA_ABSENT


def test_compatibility_dual_mechanism_is_suggestive_not_causal():
    tumor = st.tumor_dependency_state({"evaluated": True, "n_gbm_glioma_lines_evaluated": 8,
                                       "n_lines_dependent": 6, "median_gene_effect": -1.1})
    c = st.compatibility(st.IMMUNE_DECREASE, tumor)
    assert c["state"] == st.COMPAT_DUAL
    assert c["suggestive"] is True and c["causal"] is False


def test_compatibility_tumor_not_evaluated_stays_separate():
    c = st.compatibility(st.IMMUNE_DECREASE, st.tumor_dependency_state(None))
    assert c["state"] == st.COMPAT_TUMOR_NOT_EVALUATED
    assert c["causal"] is False


def test_compatibility_immune_only_when_no_tumor_dependency():
    tumor = st.tumor_dependency_state({"evaluated": True, "n_gbm_glioma_lines_evaluated": 9,
                                       "n_lines_dependent": 0, "median_gene_effect": 0.1})
    c = st.compatibility(st.IMMUNE_INCREASE, tumor)
    assert c["state"] == st.COMPAT_IMMUNE_ONLY


def test_no_banned_production_key_appears_in_any_state_output():
    tumor = st.tumor_dependency_state({"evaluated": True, "n_gbm_glioma_lines_evaluated": 5,
                                       "n_lines_dependent": 3, "median_gene_effect": -0.6})
    dis = st.disease_association_state({"evaluated": True, "diseases": {
        "MONDO_0018177": {"name": "glioblastoma", "reported_overall_association_score": 0.5,
                          "datatype_evidence": {"literature": 0.5}}}})
    comp = st.compatibility(st.IMMUNE_DECREASE, tumor)
    for blob in (tumor, dis, comp):
        assert not (st.BANNED_PRODUCTION_KEYS & set(blob.keys()))
    assert st.CLASSIFICATION == "descriptive_non_gating"
