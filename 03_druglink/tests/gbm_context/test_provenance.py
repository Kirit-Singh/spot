"""Provenance for the GBM disease-context layer: pinned sources + licenses, the honest
tissue/organ-axis record, a deterministic code hash, env, and the rerun command.
"""
from __future__ import annotations
import os

from druglink.gbm_context import provenance as pv


def test_sources_pin_open_targets_and_depmap_with_licenses():
    ot = pv.SOURCES["open_targets"]
    assert ot["data_version"] == "26.06"
    assert ot["license"] == "CC0 1.0"
    assert ot["endpoint"].startswith("https://api.platform.opentargets.org")
    assert ot["glioblastoma_id"] == "MONDO_0018177"
    assert ot["glioma_id"] == "MONDO_0021042"
    dm = pv.SOURCES["depmap"]
    assert dm["release_id"] == "depmap_public_26q1"
    assert dm["license"] == "CC BY 4.0"


def test_tissue_axis_states_no_immune_tissue_axis_but_records_contexts():
    ta = pv.TISSUE_ORGAN_AXIS
    assert ta["immune_assay_tissue_organ_axis_present"] is False
    assert "CD4" in ta["immune_assay_rationale"]
    # tumor + disease contexts are named, not an organ-expression gradient
    assert "cell line" in ta["tumor_context"].lower()
    assert ta["disease_context"]


def test_code_hash_is_deterministic_and_content_sensitive(tmp_path):
    a = tmp_path / "a.py"; a.write_text("x = 1\n")
    b = tmp_path / "b.py"; b.write_text("y = 2\n")
    h1 = pv.code_hash([str(a), str(b)])
    h2 = pv.code_hash([str(b), str(a)])   # order-independent
    assert h1 == h2 and len(h1) == 64
    a.write_text("x = 9\n")
    assert pv.code_hash([str(a), str(b)]) != h1


def test_run_provenance_has_required_fields():
    rp = pv.run_provenance(run_timestamp_utc="2026-07-13T00:00:00Z",
                           code_sha256="deadbeef", n_genes=3,
                           ot_evaluated=True, depmap_evaluated=False)
    for k in ("run_timestamp_utc", "code_sha256", "env", "rerun_command",
              "sources", "tissue_organ_axis", "populated_vs_missing"):
        assert k in rp
    assert rp["populated_vs_missing"]["disease_association_open_targets"] == "populated"
    assert rp["populated_vs_missing"]["tumor_dependency_depmap"] == "not_evaluated"
