"""DepMap Public 26Q1 dependency bridge for the GBM disease-context layer.

The tumor-cell dependency axis is OWNED by the Stage-2 DepMap lane
(``02_geneskew/analysis/depmap``), whose official-release catalog is fail-closed and
currently EMPTY. This bridge therefore (a) carries the pinned release identity + the
GBM/glioma cell-line inclusion rule as provenance, (b) consumes a per-gene dependency
handoff keyed by stable gene id IF that lane pins one, and (c) otherwise reports
``not_evaluated`` — never inventing a dependency. It refuses a handoff whose release id
does not match the pin, and it never labels an unverified handoff ``official``.
"""
from __future__ import annotations

from druglink.gbm_context import depmap_bridge as db
from druglink.gbm_context import states as st
from druglink.gbm_context import GbmContextError
import pytest


def test_release_identity_is_the_pinned_26q1_facts():
    assert db.DEPMAP_RELEASE_ID == "depmap_public_26q1"
    assert db.DEPMAP_RELEASE_NAME == "DepMap Public 26Q1"
    assert db.DEPMAP_LICENSE == "CC BY 4.0"
    assert "CRISPRGeneDependency.csv" in db.REQUIRED_FILES
    assert db.CELL_LINE_INCLUSION_RULE  # a recorded, non-empty rule


def test_no_handoff_is_not_evaluated_but_records_release_identity():
    assert db.load_dependency_handoff(None) is None
    metrics = db.gene_metrics(None, "ENSG00000146648")
    assert metrics is None
    tumor = st.tumor_dependency_state(metrics)
    assert tumor["state"] == st.NOT_EVALUATED
    prov = db.release_provenance(None)
    assert prov["evaluated"] is False
    assert prov["release_id"] == "depmap_public_26q1"
    assert prov["license"] == "CC BY 4.0"
    assert prov["cell_line_inclusion_rule"]
    assert prov["source_module"] == "02_geneskew/analysis/depmap"


def test_synthetic_handoff_yields_metrics_labeled_synthetic():
    handoff = {"release_id": "depmap_public_26q1", "source_class": "synthetic_fixture",
               "catalog_verified": False,
               "cell_line_inclusion": {"node": "GB", "tree_type": "Lineage"},
               "genes": {"ENSG00000146648": {"n_gbm_glioma_lines_evaluated": 11,
                                             "n_lines_dependent": 7,
                                             "median_gene_effect": -0.91}}}
    loaded = db.load_dependency_handoff(handoff)
    m = db.gene_metrics(loaded, "ENSG00000146648")
    assert m["evaluated"] is True and m["n_lines_dependent"] == 7
    tumor = st.tumor_dependency_state(m)
    assert tumor["direction"] == st.DEP_DEPENDENCY
    prov = db.release_provenance(loaded)
    assert prov["evaluated"] is True and prov["source_class"] == "synthetic_fixture"


def test_official_handoff_wrong_release_is_refused():
    bad = {"release_id": "depmap_public_25q4", "source_class": "official",
           "catalog_verified": True, "genes": {}}
    with pytest.raises(GbmContextError):
        db.load_dependency_handoff(bad)


def test_official_handoff_must_be_catalog_verified():
    unverified = {"release_id": "depmap_public_26q1", "source_class": "official",
                  "catalog_verified": False, "genes": {}}
    with pytest.raises(GbmContextError):
        db.load_dependency_handoff(unverified)


def test_gene_absent_from_handoff_is_not_evaluated():
    handoff = {"release_id": "depmap_public_26q1", "source_class": "synthetic_fixture",
               "catalog_verified": False, "genes": {}}
    loaded = db.load_dependency_handoff(handoff)
    assert db.gene_metrics(loaded, "ENSG00000146648") is None
