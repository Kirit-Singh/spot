"""End-to-end run of the GBM disease-context layer through an injected transport.

The transport is a PARAMETER serving the REAL pinned EGFR bytes, so the run exercises the
full path (arms -> OT association -> handoff + provenance) without a socket. A separate
network-gated smoke (test_smoke_open_targets_live) proves egress on demand.
"""
from __future__ import annotations
import json
import os

from druglink.gbm_context import run_gbm_context as rg
from druglink.gbm_context import states as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_PINNED = os.path.join(_HERE, "fixtures", "PINNED_OT_EGFR.json")
_CODE = os.path.join(_HERE, "..", "..", "analysis", "druglink", "gbm_context")


def _code_paths():
    return [os.path.join(_CODE, f) for f in os.listdir(_CODE) if f.endswith(".py")]


def _egfr_bytes():
    with open(_PINNED, "rb") as fh:
        return fh.read()


def _dispatch_transport():
    """Serve pinned EGFR bytes for EGFR; a valid 'target: null' payload for anything else."""
    null_payload = json.dumps({"data": {
        "meta": {"dataVersion": {"year": "26", "month": "06"},
                 "apiVersion": {"x": "26", "y": "6", "z": "3"}},
        "target": None}}).encode()

    def transport(url, data, headers):
        ens = json.loads(data)["variables"]["ensemblId"]
        return (200, _egfr_bytes()) if ens == "ENSG00000146648" else (200, null_payload)
    return transport


_ARMS = [
    {"target_ensembl": "ENSG00000146648", "target_symbol": "EGFR",
     "desired_change": "decrease", "program_id": "prog.A", "arm_key": "a1"},
    {"target_ensembl": "ENSG00000049768", "target_symbol": "FOXP3",
     "desired_change": "increase", "program_id": "prog.B", "arm_key": "a2"},
]


def test_run_builds_handoff_over_pinned_transport(tmp_path):
    out = tmp_path / "handoff.json"
    h = rg.run(arms=_ARMS, out_path=str(out), transport=_dispatch_transport(),
               depmap_handoff=None, now_utc="2026-07-13T12:00:00Z",
               code_paths=_code_paths())
    assert out.exists()
    disk = json.loads(out.read_text())
    assert disk["n_genes"] == 2
    egfr = disk["genes"]["ENSG00000146648"]
    assert egfr["disease_axis"]["state"] == st.DA_PRESENT
    assert egfr["disease_axis"]["diseases"]["MONDO_0018177"]["used_for_gating_or_ranking"] is False
    assert egfr["tumor_axis"]["state"] == st.NOT_EVALUATED
    assert egfr["compatibility"]["decrease"]["state"] == st.COMPAT_TUMOR_NOT_EVALUATED
    # FOXP3 had no GBM/glioma association in the null payload -> honest absent
    foxp3 = disk["genes"]["ENSG00000049768"]
    assert foxp3["disease_axis"]["state"] == st.DA_ABSENT
    rp = disk["run_provenance"]
    assert rp["run_timestamp_utc"] == "2026-07-13T12:00:00Z"
    assert len(rp["code_sha256"]) == 64
    assert rp["populated_vs_missing"]["tumor_dependency_depmap"] == "not_evaluated"
    assert rp["populated_vs_missing"]["disease_association_open_targets"] == "populated"


def test_run_without_transport_leaves_disease_not_evaluated(tmp_path):
    out = tmp_path / "h2.json"
    h = rg.run(arms=_ARMS, out_path=str(out), transport=None, live=False,
               depmap_handoff=None, now_utc="2026-07-13T12:00:00Z",
               code_paths=_code_paths())
    for ens in ("ENSG00000146648", "ENSG00000049768"):
        assert h["genes"][ens]["disease_axis"]["state"] == st.NOT_EVALUATED
    assert h["run_provenance"]["populated_vs_missing"][
        "disease_association_open_targets"] == "not_evaluated"
