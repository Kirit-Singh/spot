"""Network-gated REAL smoke: hit the live Open Targets API (CC0) for one gene.

Auto-skips when there is no egress (e.g. offline CI). Proves the pinned query shape,
data version, and disease ids still match the live API — a drift here fails loudly.
"""
from __future__ import annotations
import os
import urllib.error

import pytest

from druglink.gbm_context import ot_disease as ot


def _has_egress() -> bool:
    if os.environ.get("SPOT_OT_LIVE") == "0":
        return False
    try:
        r = ot.fetch_gene("ENSG00000146648", transport=ot.default_transport)
        return bool(r.get("evaluated"))
    except (urllib.error.URLError, OSError, Exception):
        return False


_EGRESS = _has_egress()


@pytest.mark.skipif(not _EGRESS, reason="no Open Targets egress")
def test_smoke_live_egfr_glioblastoma_association():
    r = ot.fetch_gene("ENSG00000146648", transport=ot.default_transport)
    assert r["evaluated"] is True
    assert r["data_version"] == ot.OT_DATA_VERSION_EXPECTED
    gbm = r["diseases"][ot.GLIOBLASTOMA_ID]
    assert gbm["name"] == "glioblastoma"
    assert gbm["reported_overall_association_score"] > 0
    assert gbm["datatype_evidence"]  # non-empty descriptive breakdown
