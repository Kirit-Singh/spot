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
    assert "--stage1-release-root" in _block(out, "direct:all-conditions")
    assert "--stage1-release-root" in _block(out, "pathway:Rest:reactome")


def test_topology_direct_all_conditions_pathway_6():
    """Direct is now ONE all-conditions run (was 3 per-condition); pathway stays 6, temporal is one
    all-pairs run over 6 pairs, and the W10 verify/adapter stay per-condition (3 each)."""
    out = _dry()
    assert out.count("=== BEGIN direct:") == 1
    dblk = _block(out, "direct:all-conditions")
    assert "--all-conditions" in dblk and "--stage1-release-root" in dblk
    assert out.count("=== BEGIN pathway:") == 6
    assert len(_tpairs(out)) == 6
    assert out.count("=== BEGIN temporal:all-pairs") == 1
    assert out.count("=== BEGIN w10-verify:") == 3
    assert out.count("=== BEGIN w10-adapter:") == 3


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
        # decouple identity tests from the (concurrently-edited) real verifier worktrees
        "DIRECT_VERIFIER_DIR": str(r / "no_verifier"),
        "TEMPORAL_VERIFIER_DIR": str(r / "no_verifier"),
        "PATHWAY_VERIFIER_DIR": str(r / "no_verifier"),
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


def test_verifier_binding_reads_live_head_not_a_frozen_scalar(monkeypatch):
    """The verifier binding reads the checkout's LIVE 40-hex HEAD + clean-tree flag + .pyc-excluded
    code-tree hash (never a frozen scalar). A missing dir binds <unbound> and never raises."""
    import sys as _sys, os as _os
    import pytest
    _sys.path.insert(0, ANALYSIS)
    from direct import stage2_run as S
    monkeypatch.setattr(S, "DRY", False)
    dv = "/home/tcelab/worktrees/spot-stage2-direct-verifier/02_geneskew/analysis/direct"
    if not _os.path.isdir(dv):
        pytest.skip("direct verifier checkout not present")
    b = S._verifier_binding(dv)
    assert len(b["head"]) == 40 and all(c in "0123456789abcdef" for c in b["head"]), b["head"]
    assert isinstance(b["clean_tree"], bool)
    assert b["tree_sha256"].startswith("tree:")
    assert S._verifier_binding("/no/such/dir")["tree_sha256"] == "<unbound>"   # missing -> unbound, no raise


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


def _producer_opts(modfile):
    import re
    src = open(os.path.join(ANALYSIS, "direct", modfile)).read()
    return set(re.findall(r"""add_argument\(\s*['"](--[a-z0-9-]+)""", src))


_PARSER_VALID = {"direct:": "run_arms.py", "step0:": "signature_matrix.py",
                 "pathway:": "run_pathway_arms.py", "aggregate:": "run_release.py"}


def test_confirmed_lane_blocks_parse_against_producer_argparse():
    """Every --flag a confirmed in-repo lane emits must be an accepted option of that producer's
    argparse. Guards the Step0 seam (signature_matrix takes no --stage1-release*/--direct-w10-report)
    and any future flag drift. External checkouts (w10-verify/adapter, temporal) are out of scope."""
    import re
    out = _dry()
    checked = 0
    for seg in out.split("=== BEGIN ")[1:]:
        label = seg.split("\n", 1)[0].strip()
        prefix = next((p for p in _PARSER_VALID if label.startswith(p)), None)
        if not prefix:
            continue
        body = seg.split("=== END", 1)[0]
        flags = set(re.findall(r"(--[a-z0-9-]+)", body))
        valid = _producer_opts(_PARSER_VALID[prefix])
        unknown = flags - valid
        assert not unknown, f"{label}: flags not in {_PARSER_VALID[prefix]} argparse: {sorted(unknown)}"
        checked += 1
    assert checked >= 4, f"expected >=4 confirmed in-repo lane blocks, saw {checked}"


def test_completed_receipts_skip_on_resume(tmp_path, monkeypatch):
    """Deterministic resume: a phase whose receipt exists AND re-verifies is skipped — its producer
    run() is NOT re-invoked (native/admitted bytes never rerun/overwritten). A mutated bound output
    breaks re-verification, so the phase is no longer 'complete' and would run again."""
    import sys as _sys, json as _j
    _sys.path.insert(0, ANALYSIS)
    from direct import stage2_run as S
    sd = tmp_path / "state"; sd.mkdir()
    idp = sd / "run_identity.json"; idp.write_text(_j.dumps({"run_identity_sha256": "RID"}))
    monkeypatch.setattr(S, "identity_path", lambda cfg: str(idp))
    monkeypatch.setattr(S, "DRY", False)

    inv = tmp_path / "temporal_arm_release.json"; inv.write_text("inv")

    class C:
        state_dir = str(sd)
        out = str(tmp_path)

    S._write_receipt(C, "C.direct_admitted", argv=["x"], inputs=[], outputs=[], prereqs=[])
    S._write_receipt(C, "D.temporal", argv=["run_temporal_arms"], inputs=[],
                     outputs=[str(inv)], prereqs=["C.direct_admitted"])
    assert S._completed(C, "D.temporal") is True

    inv.write_text("MUTATED")                       # bound output changed -> not complete
    assert S._completed(C, "D.temporal") is False
    inv.write_text("inv")                           # restore -> complete again

    calls = []
    monkeypatch.setattr(S, "run", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(S, "require_admitted_direct", lambda cfg: None)
    S.lane_temporal(C)
    assert calls == [], "a completed D.temporal must skip — the producer run() must not be re-invoked"


def test_run_identity_binds_all_three_external_verifiers(monkeypatch):
    """The run identity binds direct/temporal/pathway verifiers each with head/clean_tree/tree_sha256
    (not a frozen scalar), and self-hashes over the whole body — so a change in any verifier moves it."""
    import sys as _sys
    _sys.path.insert(0, ANALYSIS)
    from direct import stage2_run as S
    monkeypatch.setattr(S, "DRY", True)

    class C:
        de = guide = donor = sgrna = manifest = srcreg = pb = v3_schema = registry = env_lock = "/x"
        stage1_release = stage1_release_root = stage1_view = "/x"
        sel_dir = "/x"; lane = "production"; p2s_scores = "/x"; p2s_env_lock = ""
        direct_verifier = "/dv"; temporal_verifier = "/tv"; pathway_verifier = "/pv"

    m = S.build_run_identity(C)
    vp = m["verifier_pins"]
    for lane in ("direct", "temporal", "pathway"):
        assert lane in vp and set(vp[lane]) >= {"head", "clean_tree", "tree_sha256"}, lane
    # no frozen scalar head remains
    assert "direct_verifier_head" not in vp
    body = {k: v for k, v in m.items() if k != "run_identity_sha256"}
    assert m["run_identity_sha256"] == S.content_sha256(body)


def test_phase_C_release_invokes_pinned_verify_direct_release():
    """Phase C invokes the pinned EXTERNAL verify_direct_release over the NATIVE OUT/direct release
    (not a manufactured top-level inventory) and writes the admission to the native lane root."""
    out = _dry()
    blk = _block(out, "direct-release-verify")
    assert "verify_direct_release.py" in blk
    assert "--release" in blk and "--report" in blk
    assert "/o/direct" in blk                       # native release dir, not a top-level copy
    assert "direct_release_admission.json" in blk   # admission at the native lane root
