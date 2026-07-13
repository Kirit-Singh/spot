"""End-to-end tests for the minimal deterministic verifier CLIs.

`python -m direct.verify_signature_matrix` and `python -m direct.verify_pathway` — argparse,
explicit inputs, a persisted content-addressed report, nonzero exit on any refusal.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest
from direct import verify_pathway
from direct import verify_signature_matrix as V
from test_signature_matrix_forgery import _reseal_binding, shipped  # noqa: F401


# --------------------------------------------------------------------------- #
# verify_signature_matrix CLI
# --------------------------------------------------------------------------- #
def _run_sm(shipped, out, extra=()):  # noqa: F811
    args = shipped["args"]
    return V.main([
        "--signature-matrix-root", shipped["matrix_root"],
        "--bundle", shipped["bundle_dir"],
        "--de-main", args.de_main,
        "--direct-bundle", args.direct_bundle,
        "--direct-mask-report", args.direct_mask_report,
        "--out", out, *extra])


class TestSignatureMatrixCLI:
    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as e:
            V.main(["--help"])
        assert e.value.code == 0
        assert "signature-matrix-root" in capsys.readouterr().out

    def test_honest_bundle_exits_zero_and_persists_a_report(self, shipped, tmp_path):  # noqa: F811
        out = str(tmp_path / "sm_report.json")
        code = _run_sm(shipped, out)
        assert code == 0
        assert os.path.exists(out)
        report = json.load(open(out))
        assert report["verdict"] == "admit" and report["n_failed"] == 0
        assert report["verifier_id"] == "spot.stage02.signature_matrix.verifier.v1"
        # the report is content-addressed and carries no absolute paths
        assert len(report["report_sha256"]) == 64
        assert "/tmp" not in json.dumps({k: v for k, v in report.items()
                                         if k != "report_sha256"})

    def test_the_report_sha_is_deterministic(self, shipped, tmp_path):  # noqa: F811
        a, b = str(tmp_path / "a.json"), str(tmp_path / "b.json")
        _run_sm(shipped, a)
        _run_sm(shipped, b)
        ra, rb = json.load(open(a)), json.load(open(b))
        assert ra["report_sha256"] == rb["report_sha256"]
        # and it is the hash of the report body (excluding the self-reference)
        body = {k: v for k, v in ra.items() if k != "report_sha256"}
        assert hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest() \
            == ra["report_sha256"]

    def test_a_forged_bundle_exits_NONZERO(self, shipped, tmp_path):  # noqa: F811
        # drop the solver lock, reseal the run id: REJECT -> nonzero exit
        prov = json.load(open(os.path.join(shipped["bundle_dir"], V.PROVENANCE_FILE)))
        b = prov["run_binding"]
        b["environment_lock"] = {"name": None, "sha256": None,
                                 "status": "environment_lock_not_supplied"}
        _reseal_binding(shipped, b)
        out = str(tmp_path / "sm_bad.json")
        assert _run_sm(shipped, out) == 1
        assert json.load(open(out))["verdict"] == "reject"

    def test_a_missing_input_crashes_to_a_REJECT_not_a_traceback(self, shipped, tmp_path):  # noqa: F811
        out = str(tmp_path / "sm_missing.json")
        code = V.main(["--signature-matrix-root", "/no/such/dir",
                       "--bundle", "/no/such/bundle",
                       "--de-main", "/no/such.h5ad",
                       "--out", out])
        assert code == 1
        assert json.load(open(out))["verdict"] == "reject"


# --------------------------------------------------------------------------- #
# verify_pathway CLI (the A4 recount verifier)
# --------------------------------------------------------------------------- #
class TestPathwayCLI:
    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as e:
            verify_pathway.main(["--help"])
        assert e.value.code == 0
        assert "out-dir" in capsys.readouterr().out

    def test_a_missing_out_dir_exits_NONZERO(self, tmp_path):
        out = str(tmp_path / "pw.json")
        code = verify_pathway.main(["--out-dir", str(tmp_path / "nope"), "--out", out])
        assert code == 1
        assert json.load(open(out))["verdict"] == "reject"
