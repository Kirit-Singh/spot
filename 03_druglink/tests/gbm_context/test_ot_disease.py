"""Open Targets disease-association acquisition/parse for the GBM disease-context layer.

Transport is a PARAMETER, so every test serves the REAL pinned response bytes
(``PINNED_OT_EGFR.json``, captured from api.platform.opentargets.org, Data 26.06) and
never opens a socket. The parser refuses target mis-attribution and fails closed on a
drifted OT data version. OT's own scores are carried, never used to gate or rank.
"""
from __future__ import annotations
import hashlib
import json
import os

from druglink.gbm_context import ot_disease as ot
from druglink.gbm_context import GbmContextError
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PINNED = os.path.join(_HERE, "fixtures", "PINNED_OT_EGFR.json")
_PINNED_SHA = "0ac55a97bb9a14a95b9fe9f2469063021d3b14cd815766c2aa334ddc0e0dd6df"


def _pinned_bytes():
    with open(_PINNED, "rb") as fh:
        return fh.read()


def _fake_transport(status, raw):
    def transport(url, data, headers):
        assert url == ot.OT_ENDPOINT
        return status, raw
    return transport


def test_pinned_fixture_is_byte_identical():
    assert hashlib.sha256(_pinned_bytes()).hexdigest() == _PINNED_SHA


def test_parse_real_egfr_association_datatypes():
    obj = json.loads(_pinned_bytes())
    r = ot.parse_association(obj, "ENSG00000146648")
    assert r["evaluated"] is True
    assert r["data_version"] == "26.06"
    gbm = r["diseases"]["MONDO_0018177"]
    assert gbm["name"] == "glioblastoma"
    assert round(gbm["reported_overall_association_score"], 3) == 0.654
    # the descriptive evidence is the OT datatype breakdown, verbatim
    assert "literature" in gbm["datatype_evidence"]
    assert "somatic_mutation" in gbm["datatype_evidence"]
    assert "MONDO_0021042" in r["diseases"]  # glioma too


def test_fetch_gene_with_pinned_transport_records_provenance():
    r = ot.fetch_gene("ENSG00000146648", transport=_fake_transport(200, _pinned_bytes()))
    assert r["evaluated"] is True
    assert r["raw_sha256"] == _PINNED_SHA
    assert r["http_status"] == 200
    assert r["endpoint"] == ot.OT_ENDPOINT
    assert r["diseases"]["MONDO_0018177"]["name"] == "glioblastoma"


def test_http_error_is_not_evaluated_never_invented():
    r = ot.fetch_gene("ENSG00000146648", transport=_fake_transport(503, b""))
    assert r["evaluated"] is False
    assert r["reason"] == "http_503"
    assert r["diseases"] == {}


def test_data_version_drift_fails_closed():
    obj = json.loads(_pinned_bytes())
    obj["data"]["meta"]["dataVersion"] = {"year": "99", "month": "99"}
    with pytest.raises(GbmContextError):
        ot.verify_data_version(obj)


def test_target_id_mismatch_is_refused_not_misattributed():
    obj = json.loads(_pinned_bytes())
    with pytest.raises(GbmContextError):
        ot.parse_association(obj, "ENSG00000000000")  # not EGFR's id


def test_absent_target_is_evaluated_but_no_association():
    obj = {"data": {"meta": {"dataVersion": {"year": "26", "month": "06"},
                             "apiVersion": {"x": "26", "y": "6", "z": "3"}},
                    "target": None}}
    r = ot.parse_association(obj, "ENSG00000146648")
    assert r["evaluated"] is True and r["diseases"] == {}


def test_gql_errors_payload_is_refused():
    with pytest.raises(GbmContextError):
        ot.fetch_gene("ENSG00000146648",
                      transport=_fake_transport(200, b'{"errors":[{"message":"bad"}]}'))
