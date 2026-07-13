"""Captured-argv, invalid-transition, and identity-resume tests for the authoritative Python
scheduler `direct.stage2_run`. `run_stage2.sh` is retired; these supersede the shell tests.

W10 adapter-binding consumer rewires (Step0/temporal) + the detached same-report cross-contract
test are added once W10's repaired adapter lands; these tests cover the scheduler CORE:
identity-anchored resume, phase transitions, parser-valid confirmed lanes, run_release aggregate.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

MOD = "direct.stage2_run"
ANALYSIS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "analysis"))

DUMMY = {
    "SEL_DIR": "/d", "V3_SCHEMA": "/d", "REGISTRY": "/d", "STAGE1_RELEASE": "/d",
    "STAGE1_RELEASE_ROOT": "/root", "DE": "/de", "GUIDE": "/g", "DONOR": "/dn", "SGRNA": "/s",
    "MANIFEST": "/m", "SRCREG": "/sr", "PB": "/pb", "ENV_LOCK": "/el", "OUT": "/o",
    "W10_REPORT_DIR": "/w", "PYTHONPATH": ANALYSIS,
}


def _run(args, env_extra, cwd="/tmp"):
    env = {**os.environ, **DUMMY, **env_extra}
    return subprocess.run([sys.executable, "-m", MOD, *args], env=env, cwd=cwd,
                          capture_output=True, text=True)


def _dry(args=("all",)):
    return _run(args, {"SPOT_DRY_RUN": "1"}).stdout


def _block(out, begin_label):
    return out.split(f"=== BEGIN {begin_label}", 1)[1].split("=== END", 1)[0]


def _tpairs(out):
    return [l for l in out.splitlines()
            if l.startswith("=== PRODUCES temporal:") and "root" not in l]


def test_module_compiles_and_runs_from_arbitrary_cwd():
    out = _dry()
    assert "=== PHASE A preflight" in out and "=== PHASE F aggregate" in out


def test_phase_A_emits_the_run_identity_manifest():
    out = _dry()
    assert "=== RUN-IDENTITY schema=spot.stage02.run_identity.v1" in out
    assert "code_identity" in out and "verifier_pins" in out


def test_no_retired_temporal_cli():
    assert "temporal.cli" not in _dry()


def test_temporal_is_one_all_pairs_over_admitted_endpoints():
    out = _dry()
    assert "direct.temporal.arms.run_temporal_arms" in out and "--all-pairs" in out
    assert out.count("=== BEGIN temporal:all-pairs") == 1
    assert len(_tpairs(out)) == 6
    tblk = _block(out, "temporal:all-pairs")
    assert "--direct-bundle" in tblk and "--w10-report" in tblk


def test_native_loaders_get_the_staged_release_root():
    out = _dry()
    assert "--stage1-release-root" in _block(out, "direct:Rest")
    assert "--stage1-release-root" in _block(out, "pathway:Rest:reactome")


def test_topology_is_exactly_3_6_6():
    out = _dry()
    assert out.count("=== BEGIN direct:") == 3
    assert len(_tpairs(out)) == 6
    assert out.count("=== BEGIN pathway:") == 6


def test_phase_C_invokes_external_verifier_and_adapter():
    out = _dry()
    assert out.count("=== BEGIN w10-verify:") == 3      # native report from pinned checkout
    assert out.count("=== BEGIN w10-adapter:") == 3      # neutral adapter -> binding
    assert "verify_arm_bundle.py" in out and "verify_arm_contract.py" in out


def test_aggregate_uses_run_release_not_wildcard_run_manifest():
    out = _dry()
    assert "direct.run_release" in out
    agg = _block(out, "aggregate:run_release")
    assert "--verify" in agg and "--bundles-root" in agg and "--expected-code-identity" in agg


def _real_run_dir(tmp_path):
    r = tmp_path / "run"
    (r / "root" / "01_programs" / "app" / "data").mkdir(parents=True)
    for f in ("de", "guide", "donor", "sgrna", "manifest", "srcreg", "pb", "el"):
        (r / f).write_text(f"orig-{f}")
    (r / "root" / "rel.json").write_text("rel")
    (r / "root" / "01_programs" / "app" / "data" / "stage01_stage2_registry_view.json").write_text("view")
    (r / "genesets_reactome.ensembl.json").write_text("gr")
    (r / "genesets_go_bp.ensembl.json").write_text("gg")
    return r


def _env_for(r):
    return {
        "SEL_DIR": str(r), "V3_SCHEMA": str(r / "de"), "REGISTRY": str(r / "de"),
        "STAGE1_RELEASE": str(r / "root" / "rel.json"), "STAGE1_RELEASE_ROOT": str(r / "root"),
        "DE": str(r / "de"), "GUIDE": str(r / "guide"), "DONOR": str(r / "donor"),
        "SGRNA": str(r / "sgrna"), "MANIFEST": str(r / "manifest"), "SRCREG": str(r / "srcreg"),
        "PB": str(r / "pb"), "ENV_LOCK": str(r / "el"), "OUT": str(r / "out"),
        "W10_REPORT_DIR": str(r / "w"),
        # decouple identity tests from the (concurrently-edited) real verifier worktree
        "DIRECT_VERIFIER_DIR": str(r / "no_verifier"),
    }


def test_invalid_transition_downstream_before_admission_refuses(tmp_path):
    r = _real_run_dir(tmp_path); env = _env_for(r)
    assert _run(["preflight"], env).returncode == 0
    res = _run(["downstream"], env)
    assert res.returncode == 3
    assert "REFUSED" in res.stderr and "RESUME REFUSED" not in res.stderr  # admission, not identity


def test_identity_resume_refuses_after_input_mutation(tmp_path):
    r = _real_run_dir(tmp_path); env = _env_for(r)
    assert _run(["preflight"], env).returncode == 0
    (r / "de").write_text("orig-de\nMUTATED")   # a scientific input changes after preflight
    res = _run(["downstream"], env)
    assert res.returncode == 3
    assert "RESUME REFUSED" in res.stderr        # fail-open CLOSED


def test_identity_resume_passes_when_unchanged(tmp_path):
    r = _real_run_dir(tmp_path); env = _env_for(r)
    assert _run(["preflight"], env).returncode == 0
    res = _run(["temporal"], env)   # unchanged -> identity passes -> refuses on admission only
    assert res.returncode == 3
    assert "RESUME REFUSED" not in res.stderr


def test_identity_resume_refuses_a_tampered_stored_manifest(tmp_path):
    import json
    r = _real_run_dir(tmp_path); env = _env_for(r)
    assert _run(["preflight"], env).returncode == 0
    mp = r / "out" / ".state" / "run_identity.json"
    m = json.loads(mp.read_text())
    m["lane"] = "tampered"               # edit the body WITHOUT recomputing the self-hash
    mp.write_text(json.dumps(m))
    res = _run(["temporal"], env)
    assert res.returncode == 3
    assert "RESUME REFUSED" in res.stderr and "tampered" in res.stderr


def test_preflight_refuses_rebaseline_in_same_run_root(tmp_path):
    r = _real_run_dir(tmp_path); env = _env_for(r)
    assert _run(["preflight"], env).returncode == 0
    (r / "de").write_text("orig-de\nMUTATED")   # a different identity in the SAME OUT
    res = _run(["preflight"], env)
    assert res.returncode == 3
    assert "no rebaseline" in res.stderr.lower() or "different run identity" in res.stderr.lower()


def test_receipt_hardening(tmp_path, monkeypatch):
    """Receipts bind the FULL argv, refuse a missing prerequisite, and verify_receipt refuses a
    post-receipt output mutation."""
    import sys as _sys, json as _j
    import pytest
    _sys.path.insert(0, ANALYSIS)
    from direct import stage2_run as S
    sd = tmp_path / "state"; sd.mkdir()
    idp = sd / "run_identity.json"
    idp.write_text(_j.dumps({"run_identity_sha256": "RID"}))
    monkeypatch.setattr(S, "identity_path", lambda cfg: str(idp))
    monkeypatch.setattr(S, "DRY", False)

    class C:
        state_dir = str(sd)

    out = tmp_path / "out.txt"; out.write_text("original")
    S._write_receipt(C, "U1", argv=["python", "-m", "direct.run_arms", "--condition", "Rest"],
                     inputs=[], outputs=[str(out)], prereqs=[])
    rec = _j.loads((sd / "U1.receipt.json").read_text())
    assert rec["argv"] == ["python", "-m", "direct.run_arms", "--condition", "Rest"]   # FULL argv
    assert S.verify_receipt(C, "U1") is True

    out.write_text("MUTATED")                      # post-receipt output mutation
    with pytest.raises(S.SchedulerError):
        S.verify_receipt(C, "U1")

    with pytest.raises(S.SchedulerError):          # missing prerequisite is never silently omitted
        S._write_receipt(C, "U2", argv=["x"], inputs=[], outputs=[], prereqs=["NOPE"])

    with pytest.raises(S.SchedulerError):          # missing declared INPUT -> refuse, not omit
        S._write_receipt(C, "U3", argv=["x"], inputs=[str(tmp_path / "ghost_in")], outputs=[], prereqs=[])
    with pytest.raises(S.SchedulerError):          # missing declared OUTPUT -> refuse, not omit
        S._write_receipt(C, "U4", argv=["x"], inputs=[], outputs=[str(tmp_path / "ghost_out")], prereqs=[])

    # three-condition shared-root evolution: bind an IMMUTABLE bundle dir; adding a SIBLING to the
    # shared parent must NOT invalidate the receipt (this is the Direct per-condition fix)
    root = tmp_path / "direct"; root.mkdir()
    b_rest = root / "bundle_rest"; b_rest.mkdir(); (b_rest / "arms.parquet").write_text("rest")
    S._write_receipt(C, "B.direct.Rest", argv=["python", "-m", "direct.run_arms", "--condition", "Rest"],
                     inputs=[], outputs=[str(b_rest)], prereqs=[])
    (root / "bundle_stim8").mkdir(); (root / "bundle_stim8" / "arms.parquet").write_text("stim8")
    assert S.verify_receipt(C, "B.direct.Rest") is True     # Rest receipt stays valid after Stim8 added

    # (input mutation) verify_receipt re-hashes INPUTS -> mutating a bound input after the receipt refuses
    inp = tmp_path / "bound_input.txt"; inp.write_text("orig")
    S._write_receipt(C, "U5", argv=["python", "-m", "x"], inputs=[str(inp)], outputs=[], prereqs=[])
    assert S.verify_receipt(C, "U5") is True
    inp.write_text("MUTATED")
    with pytest.raises(S.SchedulerError):
        S.verify_receipt(C, "U5")

    # (argv reseal) changing argv + resealing ONLY receipt_sha256 -> argv_sha256 no longer re-derives
    S._write_receipt(C, "U6", argv=["python", "-m", "direct.run_arms"], inputs=[], outputs=[], prereqs=[])
    rp = sd / "U6.receipt.json"; rec6 = _j.loads(rp.read_text())
    rec6["argv"] = ["python", "-m", "direct.TAMPERED"]      # change argv, keep the old argv_sha256
    rec6["receipt_sha256"] = S.content_sha256({k: v for k, v in rec6.items() if k != "receipt_sha256"})
    rp.write_text(_j.dumps(rec6))
    with pytest.raises(S.SchedulerError):
        S.verify_receipt(C, "U6")


def test_verifier_head_pin_is_a_40char_hex_sha(monkeypatch):
    import sys as _sys
    _sys.path.insert(0, ANALYSIS)
    from direct import stage2_run as S
    monkeypatch.setattr(S, "DRY", True)
    for k, v in DUMMY.items():
        monkeypatch.setenv(k, v)
    head = S.build_run_identity(S.Cfg())["verifier_pins"]["direct_verifier_head"]
    assert len(head) == 40 and all(c in "0123456789abcdef" for c in head), head


def test_preflight_refuses_over_a_tampered_stored_body(tmp_path):
    """Explicit re-preflight over a body-tampered stored manifest (declared scalar kept) must
    REFUSE — phaseA re-derives the stored self-hash, not just a scalar compare."""
    import json
    r = _real_run_dir(tmp_path); env = _env_for(r)
    assert _run(["preflight"], env).returncode == 0
    mp = r / "out" / ".state" / "run_identity.json"
    m = json.loads(mp.read_text())
    m["lane"] = "tampered"              # edit the body but KEEP the declared run_identity_sha256
    mp.write_text(json.dumps(m))
    res = _run(["preflight"], env)
    assert res.returncode == 3
    assert "tampered" in res.stderr.lower()


def test_w10_admitted_no_fallback_and_rejects_forgeries(tmp_path, monkeypatch):
    """Production has NO offline fallback: a missing/refusing adapter, or any fresh≠stored
    difference, is False. Offline tests MOCK an authoritative adapter success. Covers: no-adapter
    refusal, acceptance, forged CACHED binding, and post-bundle mutation."""
    import sys as _sys, json as _j
    _sys.path.insert(0, ANALYSIS)
    from direct import stage2_run as S
    d = tmp_path / "w"; d.mkdir()
    bundle = tmp_path / "bundle"; bundle.mkdir()
    (bundle / "arm_bundle.json").write_text(_j.dumps({"arm_bundle_run_id": "BUN1"}))
    monkeypatch.setattr(S, "direct_bundle_for", lambda cfg, cond: str(bundle))

    class C:
        w10_report_dir = str(d)
        direct_verifier = str(tmp_path / "no_verifier")

    def sealed(b):
        b["binding_sha256"] = S.content_sha256({k: v for k, v in b.items() if k != "binding_sha256"})
        return b

    def valid():
        return sealed({"binding_schema": S.BINDING_SCHEMA, "subject_kind": "bundle",
                       "native_verdict": "ADMIT", "disposition": "admitted", "n_failed": 0,
                       "bundle_verified_on_disk": True, "verifier_id": S.W10_BUNDLE_VERIFIER_ID,
                       "verifier_code_sha256": S.W10_VERIFIER_CODE, "condition": "Rest",
                       "bundle_id": "BUN1", "arm_rows_sha256": "a", "mask_sha256": "m"})

    def store(obj):
        (d / "direct_admission_Rest.json").write_text(_j.dumps(obj))

    # (1) NO FALLBACK: adapter unavailable/refuses -> False even for a perfectly valid stored binding
    store(valid()); monkeypatch.setattr(S, "_rerun_adapter", lambda cfg, cond: None)
    assert S.w10_admitted(C, "Rest") is False

    # (2) adapter SUCCEEDS + fresh == stored valid ADMIT -> True
    vb = valid(); store(vb); monkeypatch.setattr(S, "_rerun_adapter", lambda cfg, cond: dict(vb))
    assert S.w10_admitted(C, "Rest") is True

    # (3) forged CACHED binding (REFUSE+admitted) but fresh authoritative differs -> False
    store(sealed({**valid(), "native_verdict": "REFUSE"}))
    monkeypatch.setattr(S, "_rerun_adapter", lambda cfg, cond: dict(vb))
    assert S.w10_admitted(C, "Rest") is False

    # (4) post-bundle mutation: fresh re-derivation differs from the stored binding -> False
    store(vb); mut = sealed({**valid(), "arm_rows_sha256": "MUTATED"})
    monkeypatch.setattr(S, "_rerun_adapter", lambda cfg, cond: dict(mut))
    assert S.w10_admitted(C, "Rest") is False

    # (5) adapter succeeds but the native verdict is REFUSE (fresh==stored, both refused) -> False
    rf = sealed({**valid(), "native_verdict": "REFUSE", "disposition": "refused"})
    store(rf); monkeypatch.setattr(S, "_rerun_adapter", lambda cfg, cond: dict(rf))
    assert S.w10_admitted(C, "Rest") is False
