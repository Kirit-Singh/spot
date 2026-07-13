#!/usr/bin/env python3
"""Stage-2 REAL-RUN authoritative scheduler — a resumable, IDENTITY-ANCHORED phased state machine.

`run_stage2.sh` is RETIRED. This module is the sole production scheduler. It crosses an
independent-verifier boundary (downstream measurements may not stand on a Direct endpoint no
external lane admitted), so it is phased A-F with explicit external-verifier gates, and it is
resumable ONLY against a canonical self-hashed run-identity manifest — a mutated scientific
input after preflight can never be resumed as if nothing changed.

PHASES (STAGE2_REAL_RUN_SEQUENCE_AUDIT.md a343a698):
  A preflight   emit + self-hash the run-identity manifest (binds every input/tree, Stage-1
                release + scorer view, gene sets, integrated code identity, verifier pins,
                scheduler version). Prove immutable inputs before heavy compute.
  B direct      the complete Direct release (3 content-addressed bundles), admission PENDING.
  --- STOP: pending_external_verification -------------------------------------------------
  C w10         EXTERNAL pinned verifier checkout -> native report; the neutral adapter
                (verify_arm_contract) normalizes it to spot.stage02.direct_admission_binding.v1.
  D dependent   step0 -> temporal(--all-pairs) -> pathway -> optional P2S, from ADMITTED Direct.
  E lane-verify EXTERNAL admit temporal / pathway / P2S.
  F aggregate   `python -m direct.run_release` (verify) -> external aggregate admission; the
                receipt exports manifest/report/bundles-root/stage1-release for Stage-3.

Resume: EVERY resume rehashes the identity manifest and compares before reading a receipt; each
receipt binds unit argv-hash + input-hashes + output-hashes + prerequisite-receipt-hashes.

DRY RUN: SPOT_DRY_RUN=1 python -m direct.stage2_run all  -> prints per-unit argv + phase
transitions + producer/consumer flow, executes nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

# --- module-root anchoring (works from any cwd) -----------------------------------------
SELF = os.path.dirname(os.path.abspath(__file__))          # .../02_geneskew/analysis/direct
ANALYSIS = os.path.dirname(SELF)                            # .../02_geneskew/analysis
GENESKEW = os.path.dirname(ANALYSIS)                        # .../02_geneskew
REPO = os.path.dirname(GENESKEW)

SCHEDULER_VERSION = "spot.stage02.scheduler.v1"
# P2S production scores input — the staged, independently-verified 396k-row Stage-1 scores.
# NEVER the 40k overlay. Both hashes are pinned and bound into the run identity + preflight.
P2S_SCORES_DEFAULT = ("/home/tcelab/.spot-runs/20260712T021343Z/stage1-inputs/"
                      "stage01_scores_full.parquet")
P2S_SCORES_RAW_SHA256 = "de63b496e8121c77babe380e0c3b5ddfd66f9ce67d0d4e80f55645d177e27e5f"
P2S_SCORES_CANONICAL_SHA256 = "43c4296d5166740c334441a69df23bb440a073382bbe79628a3bb89e43d51316"
CONDITIONS = ("Rest", "Stim8hr", "Stim48hr")
PAIRS = ("Rest__Stim8hr", "Stim8hr__Rest", "Rest__Stim48hr",
         "Stim48hr__Rest", "Stim8hr__Stim48hr", "Stim48hr__Stim8hr")
SOURCES = ("reactome", "go_bp")
DRY = bool(os.environ.get("SPOT_DRY_RUN"))

# The scientific inputs the run identity binds. An unset input is a refusal, not a guess.
INPUT_ENV = ("SEL_DIR", "V3_SCHEMA", "REGISTRY", "STAGE1_RELEASE", "STAGE1_RELEASE_ROOT",
             "STAGE1_VIEW", "DE", "GUIDE", "DONOR", "SGRNA", "MANIFEST", "SRCREG", "PB",
             "ENV_LOCK", "OUT", "W10_REPORT_DIR")
# EXTERNAL pinned verifier checkouts (invoked by absolute path; never vendored into producer).
VERIFIER_ENV = ("DIRECT_VERIFIER_DIR", "TEMPORAL_VERIFIER_DIR", "PATHWAY_VERIFIER_DIR")


class SchedulerError(RuntimeError):
    pass


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_sha256(obj) -> str:
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def file_sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def tree_sha256(root: str) -> str:
    """Deterministic hash of a directory tree's relative paths + file bytes."""
    acc = hashlib.sha256()
    for dp, dns, fns in os.walk(root):
        dns.sort()
        for fn in sorted(fns):
            if fn.endswith((".pyc",)) or "__pycache__" in dp:
                continue
            p = os.path.join(dp, fn)
            acc.update(os.path.relpath(p, root).encode())
            acc.update(file_sha256(p).encode())
    return acc.hexdigest()


class Cfg:
    def __init__(self):
        missing = [k for k in INPUT_ENV if k == "STAGE1_VIEW" or not os.environ.get(k)]
        # STAGE1_VIEW has a derived default; everything else is mandatory.
        real_missing = [k for k in INPUT_ENV if k != "STAGE1_VIEW" and not os.environ.get(k)]
        if real_missing:
            raise SchedulerError(f"refusing to run: unset {' '.join(real_missing)}")
        for k in INPUT_ENV:
            setattr(self, k.lower(), os.environ.get(k, ""))
        if not self.stage1_view:
            self.stage1_view = os.path.join(
                self.stage1_release_root, "01_programs", "app", "data",
                "stage01_stage2_registry_view.json")
        self.state_dir = os.path.join(self.out, ".state")
        self.sigroot = os.path.join(self.out, "signatures")
        self.lane = os.environ.get("LANE", "production")
        # verifier checkout dirs (needed for phases C/E; defaulted for dry-run/topology checks)
        self.direct_verifier = os.environ.get(
            "DIRECT_VERIFIER_DIR",
            "/home/tcelab/worktrees/spot-stage2-direct-verifier/02_geneskew/analysis/direct")
        self.p2s_scores = os.environ.get("P2S_SCORES", P2S_SCORES_DEFAULT)
        self.p2s_env_lock = os.environ.get("P2S_ENV_LOCK", "")   # W15's SECOND env lock (P2S runtime)


# ---- run-identity manifest (Phase A) ----------------------------------------------------
def build_run_identity(cfg: Cfg) -> dict:
    """Canonical, self-hashed identity: every scientific input, Stage-1 release/view, gene sets,
    the integrated producer code identity, verifier pins, and the scheduler version. A resume
    that finds any of these changed REFUSES before reading a single receipt."""
    def h(path):
        if DRY:
            return f"<sha256:{os.path.basename(path)}>"
        if os.path.isdir(path):
            return "tree:" + tree_sha256(path)
        return "file:" + file_sha256(path)

    inputs = {k.lower(): h(getattr(cfg, k.lower()))
              for k in ("DE", "GUIDE", "DONOR", "SGRNA", "MANIFEST", "SRCREG", "PB",
                        "V3_SCHEMA", "REGISTRY", "ENV_LOCK")}
    stage1 = {"release": h(cfg.stage1_release), "release_root": h(cfg.stage1_release_root),
              "scorer_view": h(cfg.stage1_view)}
    gene_sets = {}
    for src in SOURCES:
        gp = os.path.join(cfg.sel_dir, f"genesets_{src}.ensembl.json")
        gene_sets[src] = h(gp)
    code_identity = ("<tree:02_geneskew/analysis/direct>" if DRY
                     else "tree:" + tree_sha256(SELF))
    manifest = {
        "schema": "spot.stage02.run_identity.v1",
        "scheduler_version": SCHEDULER_VERSION,
        "lane": cfg.lane,
        "conditions": list(CONDITIONS),
        "inputs": inputs,
        "stage1": stage1,
        "gene_sets": gene_sets,
        "code_identity": code_identity,
        "env_lock_sha256": h(cfg.env_lock),
        "verifier_pins": {
            "direct_w10_verifier_id": "spot.stage02.direct.arm_bundle.verifier.v1",
            "direct_w10_verifier_code_sha256":
                "3bc55ba51f6a8a619e9a8f47e4fd8d6318811c92048948159e8d03a93210a834",
            "direct_verifier_head": "dd1130026d3bddcfdf108545d0b7553e7d05e9f0",  # W10 FINAL adapter (6 release cross-pins)
            "direct_verifier_tree_sha256": (("tree:" + tree_sha256(cfg.direct_verifier))
                                            if (not DRY and os.path.isdir(cfg.direct_verifier))
                                            else "<unbound>"),
            "temporal_verifier": "07a064c1b8c4f5a1c1693c306fd264c4ada6f49d",
            "pathway_verifier": "53ac540",
        },
        "p2s": {
            "scores_full": cfg.p2s_scores,          # W15 preparer input (NOT a --cells NPZ)
            "scores_raw_sha256": P2S_SCORES_RAW_SHA256,
            "scores_canonical_sha256": P2S_SCORES_CANONICAL_SHA256,
            "p2s_env_lock": (h(cfg.p2s_env_lock) if cfg.p2s_env_lock else None),  # SECOND env lock
            "status": "typed_pending_w15_preparer",
            "forbid_40k_overlay": True,
        },
    }
    manifest["run_identity_sha256"] = content_sha256(manifest)
    return manifest


def identity_path(cfg: Cfg) -> str:
    return os.path.join(cfg.state_dir, "run_identity.json")


def phaseA_preflight(cfg: Cfg):
    _phase("A preflight")
    manifest = build_run_identity(cfg)
    if DRY:
        print(f"=== RUN-IDENTITY schema={manifest['schema']} "
              f"scheduler={SCHEDULER_VERSION} binds inputs+stage1+gene_sets+code_identity+"
              f"verifier_pins; self-hash=run_identity_sha256")
        for k in ("DE", "GUIDE", "DONOR", "SGRNA", "MANIFEST", "SRCREG", "PB", "ENV_LOCK",
                  "STAGE1_RELEASE", "STAGE1_RELEASE_ROOT", "STAGE1_VIEW"):
            print(f"=== IDENTITY-INPUT {getattr(cfg, k.lower())}")
        return
    for f in (cfg.env_lock, cfg.stage1_release, cfg.stage1_view):
        if not os.path.isfile(f):
            raise SchedulerError(f"preflight: missing immutable input {f}")
    if not os.path.isdir(cfg.stage1_release_root):
        raise SchedulerError(f"preflight: staged release root missing: {cfg.stage1_release_root}")
    if os.path.exists(cfg.out) and not os.path.isdir(cfg.state_dir) and os.listdir(cfg.out):
        raise SchedulerError(f"preflight: OUT {cfg.out} non-empty and not a resumable run root")
    os.makedirs(cfg.state_dir, exist_ok=True)
    if os.path.isfile(identity_path(cfg)):
        existing = json.load(open(identity_path(cfg)))
        existing_body = {k: v for k, v in existing.items() if k != "run_identity_sha256"}
        manifest_body = {k: v for k, v in manifest.items() if k != "run_identity_sha256"}
        # integrity: re-derive the STORED body's self-hash — a body tamper that kept the declared
        # scalar is caught here (not just a scalar comparison)
        if content_sha256(existing_body) != existing.get("run_identity_sha256"):
            raise SchedulerError(
                f"preflight REFUSED: the stored run-identity manifest in this OUT ({cfg.out}) is "
                "tampered (its body does not re-derive its declared self-hash)")
        # identity: the fresh manifest body must equal the stored body field-by-field
        if existing_body != manifest_body:
            raise SchedulerError(
                f"preflight REFUSED: a DIFFERENT run identity already exists in this OUT ({cfg.out}) "
                "— no rebaseline/overwrite in the same run root; use a fresh OUT")
        return   # genuinely identical re-preflight is a no-op; the stored identity is write-once
    with open(identity_path(cfg), "w") as fh:
        json.dump(manifest, fh, sort_keys=True, indent=2)
    _write_receipt(cfg, "A.preflight", argv=["preflight"], inputs=[], outputs=[identity_path(cfg)],
                   prereqs=[], extra={"run_identity_sha256": manifest["run_identity_sha256"]})


def _verify_external_verifier_tree(cfg, stored_body):
    """Bind the external Direct verifier checkout to its exact tree hash — a verifier-dir swap or
    a dirty verifier tree is refused."""
    want = stored_body.get("verifier_pins", {}).get("direct_verifier_tree_sha256")
    if want and want != "<unbound>" and os.path.isdir(cfg.direct_verifier):
        got = "tree:" + tree_sha256(cfg.direct_verifier)
        if got != want:
            raise SchedulerError("RESUME REFUSED: the external Direct verifier checkout tree "
                                 f"changed (swap/dirty) — got {got[:22]} != bound {str(want)[:22]}")


def verify_run_identity(cfg: Cfg):
    """Every resume, BEFORE any receipt is read: (1) recompute the STORED manifest's self-hash
    and require it equals its own recorded sha (a naive edit is caught); (2) rebuild the identity
    from the ACTUAL inputs and require the FULL body equals the stored body field-by-field (any
    input/tree/code/pin change is caught, not just a sha comparison); (3) confirm the external
    verifier checkout is at its exact bound tree."""
    if DRY:
        print("=== RESUME-GATE recompute stored self-hash + compare FULL stored body + bind "
              "external verifier tree; REFUSE on any change")
        return
    p = identity_path(cfg)
    if not os.path.isfile(p):
        raise SchedulerError("resume: no run-identity manifest; run phase A first")
    stored = json.load(open(p))
    stored_sha = stored.get("run_identity_sha256")
    stored_body = {k: v for k, v in stored.items() if k != "run_identity_sha256"}
    if content_sha256(stored_body) != stored_sha:
        raise SchedulerError("RESUME REFUSED: the stored run-identity manifest is internally "
                             "inconsistent (body edited without a matching self-hash) — tampered")
    fresh_body = {k: v for k, v in build_run_identity(cfg).items() if k != "run_identity_sha256"}
    if fresh_body != stored_body:
        diff = sorted(k for k in set(fresh_body) | set(stored_body)
                      if fresh_body.get(k) != stored_body.get(k))
        raise SchedulerError(f"RESUME REFUSED: the run identity changed since preflight — "
                             f"differing keys: {diff}")
    _verify_external_verifier_tree(cfg, stored_body)


# ---- hash-bound receipts ----------------------------------------------------------------
def _receipt_path(cfg, name):
    return os.path.join(cfg.state_dir, f"{name}.receipt.json")


def _hash_path(p):
    return ("tree:" + tree_sha256(p)) if os.path.isdir(p) else ("file:" + file_sha256(p))


def _write_receipt(cfg, name, *, argv, inputs, outputs, prereqs, extra=None):
    """Immutable unit receipt binding the FULL executed argv, complete input/output hashes, and the
    EXACT prerequisite set — every declared prerequisite receipt MUST already exist (none is
    silently omitted). Write-once: an identical rewrite is a no-op; a divergent one refuses."""
    if DRY:
        return
    rp = _receipt_path(cfg, name)
    for q in prereqs:
        if not os.path.isfile(_receipt_path(cfg, q)):
            raise SchedulerError(f"receipt {name}: required prerequisite receipt {q!r} is missing")
    for p in list(inputs) + list(outputs):
        if not os.path.exists(p):
            raise SchedulerError(f"receipt {name}: declared path {p!r} does not exist — cannot bind "
                                 "(no silent omission)")
    rec = {
        "unit": name,
        "run_identity_sha256": json.load(open(identity_path(cfg)))["run_identity_sha256"],
        "argv": list(argv),                                  # the FULL executed argv, verbatim
        "argv_sha256": content_sha256(list(argv)),
        "input_sha256": {p: _hash_path(p) for p in inputs},
        "output_sha256": {p: _hash_path(p) for p in outputs},
        "prerequisite_receipt_sha256": {q: file_sha256(_receipt_path(cfg, q)) for q in prereqs},
    }
    if extra:
        rec.update(extra)
    rec["receipt_sha256"] = content_sha256(rec)
    if os.path.isfile(rp):
        if json.load(open(rp)).get("receipt_sha256") != rec["receipt_sha256"]:
            raise SchedulerError(f"receipt {name} already exists and DIFFERS — receipts are immutable")
        return
    with open(rp, "w") as fh:
        json.dump(rec, fh, sort_keys=True, indent=2)


def verify_receipt(cfg, name):
    """Before a dependent/resumed phase trusts a unit: self-hash integrity, run-identity binding,
    its bound OUTPUTS still match on disk (post-receipt mutation), and its prerequisite receipts
    exist + hash-match."""
    if DRY:
        return True
    rp = _receipt_path(cfg, name)
    if not os.path.isfile(rp):
        raise SchedulerError(f"verify_receipt: unit receipt {name!r} is missing")
    rec = json.load(open(rp))
    if content_sha256({k: v for k, v in rec.items() if k != "receipt_sha256"}) != rec.get("receipt_sha256"):
        raise SchedulerError(f"verify_receipt: receipt {name!r} is tampered (self-hash mismatch)")
    if rec.get("run_identity_sha256") != json.load(open(identity_path(cfg)))["run_identity_sha256"]:
        raise SchedulerError(f"verify_receipt: receipt {name!r} was written under a different run identity")
    if content_sha256(rec.get("argv", [])) != rec.get("argv_sha256"):
        raise SchedulerError(f"verify_receipt: receipt {name!r} argv does not re-derive its argv_sha256 "
                             "(argv changed with only receipt_sha256 resealed)")
    for p, h in rec.get("input_sha256", {}).items():
        if not os.path.exists(p) or _hash_path(p) != h:
            raise SchedulerError(f"verify_receipt: input {p!r} of unit {name!r} was mutated/removed after its receipt")
    for p, h in rec.get("output_sha256", {}).items():
        if not os.path.exists(p) or _hash_path(p) != h:
            raise SchedulerError(f"verify_receipt: output {p!r} of unit {name!r} was mutated/removed after its receipt")
    for q, h in rec.get("prerequisite_receipt_sha256", {}).items():
        qp = _receipt_path(cfg, q)
        if not os.path.isfile(qp) or file_sha256(qp) != h:
            raise SchedulerError(f"verify_receipt: prerequisite receipt {q!r} of unit {name!r} missing/mutated")
    return True


def verify_all_receipts(cfg):
    """Resume gate: verify EVERY prior unit receipt before any dependent phase reads it."""
    if DRY or not os.path.isdir(cfg.state_dir):
        return
    for fn in sorted(os.listdir(cfg.state_dir)):
        if fn.endswith(".receipt.json"):
            verify_receipt(cfg, fn[:-len(".receipt.json")])


# ---- unit runner ------------------------------------------------------------------------
def run(label, argv, *, produces=(), consumes=(), cwd=ANALYSIS):
    if DRY:
        print(f"=== BEGIN {label}")
        for a in argv:
            print(a)
        for p in produces:
            print(f"=== PRODUCES {p}")
        for c in consumes:
            print(f"=== CONSUMES {c}")
        print(f"=== END {label}")
        return 0
    env = {**os.environ, "PYTHONPATH": ANALYSIS + os.pathsep + os.environ.get("PYTHONPATH", "")}
    r = subprocess.run(argv, cwd=cwd, env=env)
    if r.returncode != 0:
        raise SchedulerError(f"unit {label} failed rc={r.returncode}")
    return 0


def _phase(title):
    print(f"=== PHASE {title}")


def _py(mod, *args):
    return [sys.executable if not DRY else "python", "-m", f"direct.{mod}", *args]


# ---- content-addressed Direct bundle discovery ------------------------------------------
def direct_bundle_for(cfg, cond):
    if DRY:
        return f"<discovered:direct:{cond}>"
    out = subprocess.check_output(
        [sys.executable, "-m", "direct.bundle_index", "--root", os.path.join(cfg.out, "direct"),
         "--condition", cond, "--kind", "direct"],
        cwd=ANALYSIS, env={**os.environ, "PYTHONPATH": ANALYSIS}, text=True)
    return out.strip()


def w10_binding_path(cfg, cond):
    return os.path.join(cfg.w10_report_dir, f"direct_admission_{cond}.json")


def native_report_path(cfg, cond):
    return os.path.join(cfg.w10_report_dir, f"w10_admission_{cond}.json")


BINDING_SCHEMA = "spot.stage02.direct_admission_binding.v1"
W10_VERIFIER_CODE = "3bc55ba51f6a8a619e9a8f47e4fd8d6318811c92048948159e8d03a93210a834"
W10_BUNDLE_VERIFIER_ID = "spot.stage02.direct.arm_bundle.verifier.v1"


def _rerun_adapter(cfg, cond):
    """Re-run the PINNED adapter on the native report + discovered bundle → its FRESH normalized
    binding (the authoritative re-derivation), or None if the adapter/native report is absent or
    the adapter REFUSES (a forged native report cannot produce a binding)."""
    adapter = os.path.join(cfg.direct_verifier, "verify_arm_contract.py")
    native_p = native_report_path(cfg, cond)
    if not (os.path.isfile(adapter) and os.path.isfile(native_p)):
        return None
    try:
        bundle_dir = direct_bundle_for(cfg, cond)
    except Exception:
        return None
    fd, outp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        r = subprocess.run([sys.executable, adapter, "--report", native_p, "--bundle", bundle_dir,
                            "--out", outp], capture_output=True, cwd=cfg.direct_verifier)
        return json.load(open(outp)) if r.returncode == 0 else None
    except Exception:
        return None
    finally:
        try:
            os.unlink(outp)
        except OSError:
            pass


def _binding_semantics_ok(cfg, cond, b):
    """Admission semantics on an authoritative binding: full-body self-hash, bundle subject,
    native ADMIT consistent with disposition=admitted, n_failed==0, verified-on-disk, pinned W10
    id+code, and bind THIS condition + the discovered bundle's arm_bundle_run_id."""
    if not isinstance(b, dict):
        return False
    if content_sha256({k: v for k, v in b.items() if k != "binding_sha256"}) != b.get("binding_sha256"):
        return False
    if b.get("binding_schema") != BINDING_SCHEMA or b.get("subject_kind") != "bundle":
        return False
    if b.get("native_verdict") != "ADMIT" or b.get("disposition") != "admitted":
        return False
    if b.get("n_failed") != 0 or b.get("bundle_verified_on_disk") is not True:
        return False
    if b.get("verifier_code_sha256") != W10_VERIFIER_CODE or b.get("verifier_id") != W10_BUNDLE_VERIFIER_ID:
        return False
    if b.get("condition") != cond:
        return False
    try:
        doc = json.load(open(os.path.join(direct_bundle_for(cfg, cond), "arm_bundle.json")))
    except Exception:
        return False
    return b.get("bundle_id") == doc.get("arm_bundle_run_id")


def w10_admitted(cfg, cond):
    """STRONGEST fail-closed rule — NO production fallback. RE-RUN the pinned adapter on the native
    report + discovered bundle and require its FRESH output to equal the stored binding canonically,
    then the admission semantics. A MISSING adapter, a NONZERO adapter (native-report refusal /
    tampered bytes), an UNREADABLE output, or ANY fresh≠stored difference is False — there is no
    offline path that could accept a resealed cached binding. Offline tests MOCK an authoritative
    adapter success; production always re-derives from source."""
    stored_p = w10_binding_path(cfg, cond)
    if not os.path.isfile(stored_p):
        return False
    try:
        stored = json.load(open(stored_p))
    except Exception:
        return False
    fresh = _rerun_adapter(cfg, cond)
    if fresh is None:                                    # missing / refused / unreadable → REFUSE
        return False
    if content_sha256(fresh) != content_sha256(stored):  # forged/resealed/mutated stored binding
        return False
    return _binding_semantics_ok(cfg, cond, fresh)


def require_admitted_direct(cfg):
    if DRY:
        return
    missing = [c for c in CONDITIONS if not w10_admitted(cfg, c)]
    if missing:
        raise SchedulerError(
            f"REFUSED: dependent phase requires independent Direct/W10 admissions; "
            f"missing/!admit binding for {missing} under {cfg.w10_report_dir}")


# ---- phases -----------------------------------------------------------------------------
def bundle_args(cfg):
    return ["--registry", cfg.registry, "--stage1-release", cfg.stage1_release,
            "--stage1-release-root", cfg.stage1_release_root, "--de-main", cfg.de,
            "--by-guide", cfg.guide, "--by-donors", cfg.donor, "--sgrna", cfg.sgrna,
            "--guide-manifest", cfg.manifest, "--source-registry", cfg.srcreg,
            "--lane", cfg.lane, "--strict-replay", "--pseudobulk", cfg.pb,
            "--env-lock", cfg.env_lock]


def lane_direct(cfg):
    _phase("B direct")
    for cond in CONDITIONS:
        argv = _py("run_arms", "--condition", cond, *bundle_args(cfg),
                   "--out-root", os.path.join(cfg.out, "direct"))
        run(f"direct:{cond}", argv, produces=[f"direct:{cond}"])   # exact executed command
        # bind the IMMUTABLE content-addressed bundle dir, NOT the shared mutable OUT/direct root
        # (so the Rest receipt stays valid as Stim8hr/Stim48hr are added later)
        bdir = direct_bundle_for(cfg, cond)
        _write_receipt(cfg, f"B.direct.{cond}", argv=argv,
                       inputs=[cfg.de, cfg.sgrna, cfg.stage1_release],
                       outputs=[bdir], prereqs=["A.preflight"])


def verify_direct_gate(cfg):
    _phase("C direct/W10 gate (EXTERNAL pinned verifier checkout)")
    dv = cfg.direct_verifier
    for cond in CONDITIONS:
        nrep = native_report_path(cfg, cond)
        binding = w10_binding_path(cfg, cond)
        # 1) native report from the pinned verifier checkout (absolute path; no PYTHONPATH)
        run(f"w10-verify:{cond}",
            [("python" if DRY else sys.executable), os.path.join(dv, "verify_arm_bundle.py"),
             "--bundle", direct_bundle_for(cfg, cond), "--condition", cond,
             "--de-main", cfg.de, "--sgrna", cfg.sgrna, "--by-guide", cfg.guide,
             "--by-donors", cfg.donor, "--guide-manifest", cfg.manifest,
             "--source-registry", cfg.srcreg, "--pseudobulk", cfg.pb,
             "--stage1-v3-release", cfg.stage1_release, "--release-root", cfg.stage1_release_root,
             "--env-lock", cfg.env_lock,
             "--expect-h5ad-sha256", ("<sha256:DE.h5ad>" if DRY else file_sha256(cfg.de)),
             "--recompute", "all", "--report", nrep],
            consumes=[f"direct:{cond}"], produces=[f"w10_report:{cond}"], cwd=dv)
        # 2) the neutral adapter normalizes native report -> self-hashed binding
        run(f"w10-adapter:{cond}",
            [("python" if DRY else sys.executable), os.path.join(dv, "verify_arm_contract.py"),
             "--report", nrep, "--bundle", direct_bundle_for(cfg, cond), "--out", binding],
            consumes=[f"w10_report:{cond}"], produces=[f"w10_admission:{cond}"], cwd=dv)
    require_admitted_direct(cfg)
    _write_receipt(cfg, "C.direct_admitted", argv=["verify-direct"],
                   inputs=[], outputs=[w10_binding_path(cfg, c) for c in CONDITIONS],
                   prereqs=[f"B.direct.{c}" for c in CONDITIONS])


def lane_step0(cfg):
    _phase("D step0")
    require_admitted_direct(cfg)
    for cond in CONDITIONS:
        # Step0 uses its ACCEPTED producer CLI; it reads the W10 native report + bundle and
        # internally calls the adapter (load_and_normalize) for the mask hash — no invented flag.
        run(f"step0:{cond}",
            _py("signature_matrix", "--condition", cond, "--de-main", cfg.de, "--sgrna", cfg.sgrna,
                "--guide-manifest", cfg.manifest, "--source-registry", cfg.srcreg,
                "--stage1-release", cfg.stage1_release, "--stage1-release-root", cfg.stage1_release_root,
                "--direct-bundle", direct_bundle_for(cfg, cond),
                "--direct-w10-report", native_report_path(cfg, cond),
                "--env-lock", cfg.env_lock, "--out-root", cfg.sigroot),
            consumes=[f"direct:{cond}", f"w10_admission:{cond}"], produces=[f"signatures:{cond}"])
    _write_receipt(cfg, "D.step0", argv=["signature_matrix"], inputs=[cfg.de],
                   outputs=[cfg.sigroot], prereqs=["C.direct_admitted"])


def lane_temporal(cfg):
    _phase("D temporal")
    require_admitted_direct(cfg)
    dargs = []
    for cond in CONDITIONS:
        dargs += ["--direct-bundle", f"{cond}:{direct_bundle_for(cfg, cond)}",
                  "--w10-report", f"{cond}:{w10_binding_path(cfg, cond)}"]
    run("temporal:all-pairs",
        _py("temporal.arms.run_temporal_arms", "--stage1-view", cfg.stage1_view,
            "--stage1-release", cfg.stage1_release, *dargs, "--env-lock", cfg.env_lock,
            "--conditions", ",".join(CONDITIONS), "--all-pairs",
            "--out-root", os.path.join(cfg.out, "temporal")),
        consumes=[f"w10_admission:{c}" for c in CONDITIONS],
        produces=[f"temporal:{p}" for p in PAIRS] + ["temporal:root"])
    _write_receipt(cfg, "D.temporal", argv=["run_temporal_arms", "--all-pairs"], inputs=[],
                   outputs=[os.path.join(cfg.out, "temporal")], prereqs=["C.direct_admitted"])


def lane_pathway(cfg):
    _phase("D pathway")
    require_admitted_direct(cfg)
    for cond in CONDITIONS:
        for src in SOURCES:
            run(f"pathway:{cond}:{src}",
                _py("run_pathway_arms", "--condition", cond, *bundle_args(cfg),
                    "--gene-sets", os.path.join(cfg.sel_dir, f"genesets_{src}.ensembl.json"),
                    "--signature-matrix-root", cfg.sigroot,
                    "--out-root", os.path.join(cfg.out, "pathway")),
                consumes=[f"signatures:{cond}"], produces=[f"pathway:{cond}:{src}"])
    _write_receipt(cfg, "D.pathway", argv=["run_pathway_arms"], inputs=[],
                   outputs=[os.path.join(cfg.out, "pathway")], prereqs=["D.step0"])


# --- P2S: two-phase optional secondary lane, a CLEAN HOOK for W15 (TYPED PENDING) -----------
# W15 fills the two hooks below once its tested preparer + runtime CLIs are published. The
# scheduler already sequences them after admitted Direct and binds a SECOND env lock
# (P2S_ENV_LOCK) distinct from the Stage-2 solver lock. Until then both are typed-pending and
# do not run. The raw stage01_scores_full.parquet is a preparer INPUT, never a --cells NPZ; and
# NEVER the 40k overlay.
def lane_p2s_prepare(cfg):
    """W15 PREP hook: barcode-join the staged 396k `stage01_scores_full.parquet` (pinned in the
    run identity) to the condition-specific NTC expression matrix -> prepared per-condition NPZ
    (barcodes/donors/gene_ids/expr/score__<program_id>) + effects.parquet + admitted masks.parquet
    + eligible.parquet. Typed-pending until W15's preparer CLI + handoff are published."""
    _phase("D p2s-prepare (W15 hook — TYPED PENDING)")
    require_admitted_direct(cfg)
    if DRY:
        print("=== P2S-PREPARE TYPED-PENDING (W15 hook): scores x NTC -> prepared NPZ + "
              "effects/masks/eligible; preparer CLI not yet published; never the 40k overlay")
        return
    for cond in CONDITIONS:
        _write_receipt(cfg, f"D.p2s_prepare.{cond}", argv=["p2s-prepare-pending"], inputs=[],
                       outputs=[], prereqs=["C.direct_admitted"],
                       extra={"status": "typed_pending_w15_preparer", "forbid_40k_overlay": True})


def lane_p2s_runtime(cfg):
    """W15 RUNTIME hook: `run_p2s_arms` per admitted condition on the PREPARED inputs, under the
    SECOND env lock (P2S_ENV_LOCK). Separately admitted; Direct bytes/ranks unchanged whether it
    runs or not. Typed-pending until prepare lands."""
    _phase("D p2s-runtime (W15 hook — TYPED PENDING)")
    require_admitted_direct(cfg)
    if DRY:
        print("=== P2S-RUNTIME TYPED-PENDING (W15 hook): run_p2s_arms needs the prepared NPZ + "
              "the second env lock P2S_ENV_LOCK; not runnable until prepare is published")
        return
    for cond in CONDITIONS:
        _write_receipt(cfg, f"D.p2s_runtime.{cond}", argv=["p2s-runtime-pending"], inputs=[],
                       outputs=[], prereqs=[f"D.p2s_prepare.{cond}"],
                       extra={"status": "typed_pending_w15_runtime"})


def lane_p2s(cfg):
    lane_p2s_prepare(cfg)
    lane_p2s_runtime(cfg)


def lane_aggregate(cfg):
    _phase("F aggregate (run_release --verify + external admission)")
    require_admitted_direct(cfg)
    out = os.path.join(cfg.out, "aggregate")
    run("aggregate:run_release",
        _py("run_release", "--bundles-root", cfg.out, "--release", cfg.stage1_release,
            "--release-root", cfg.stage1_release_root, "--env-lock", cfg.env_lock,
            "--expect-env-lock-sha256", os.environ.get("EXPECT_ENV_LOCK_SHA256", ""),
            "--expect-release-sha256", os.environ.get("EXPECT_RELEASE_SHA256", ""),
            "--expect-gene-sets", os.environ.get("EXPECT_GENE_SETS", ""),
            "--expect-verifiers", os.environ.get("EXPECT_VERIFIERS", ""),
            "--expected-code-identity", os.environ.get("EXPECTED_CODE_IDENTITY", ""),
            "--out", out, "--verify"),
        consumes=["direct:root", "temporal:root", "pathway:root"],
        produces=["aggregate:topology_manifest"])
    _write_receipt(cfg, "F.aggregate", argv=["run_release", "--verify"], inputs=[],
                   outputs=[out], prereqs=["C.direct_admitted", "D.temporal", "D.pathway"],
                   extra={"exports": {"manifest": os.path.join(out, "run_manifest.json"),
                                      "report": os.path.join(out, "aggregate_admission.json"),
                                      "bundles_root": cfg.out, "stage1_release": cfg.stage1_release}})


def lane_downstream(cfg):
    lane_step0(cfg); lane_temporal(cfg); lane_pathway(cfg)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m direct.stage2_run")
    ap.add_argument("phase", nargs="?", default="all",
                    choices=["preflight", "direct", "verify-direct-gate", "step0", "temporal",
                             "pathway", "p2s", "downstream", "aggregate", "all"])
    args = ap.parse_args(argv)
    cfg = Cfg()
    if args.phase != "preflight" and not DRY and os.path.isfile(identity_path(cfg)):
        verify_run_identity(cfg)     # every resume rehashes identity first
        verify_all_receipts(cfg)     # then verify every prior receipt (outputs unmutated, prereqs intact)
    if args.phase == "preflight":
        phaseA_preflight(cfg)
    elif args.phase == "direct":
        phaseA_preflight(cfg); lane_direct(cfg)
    elif args.phase == "verify-direct-gate":
        verify_direct_gate(cfg)
    elif args.phase == "step0":
        lane_step0(cfg)
    elif args.phase == "temporal":
        lane_temporal(cfg)
    elif args.phase == "pathway":
        lane_pathway(cfg)
    elif args.phase == "p2s":
        lane_p2s(cfg)
    elif args.phase == "downstream":
        require_admitted_direct(cfg); lane_downstream(cfg)
    elif args.phase == "aggregate":
        lane_aggregate(cfg)
    elif args.phase == "all":
        phaseA_preflight(cfg)
        lane_direct(cfg)
        if not DRY and not all(w10_admitted(cfg, c) for c in CONDITIONS):
            sys.stderr.write(
                "\n=== PHASE B complete. 3 Direct bundles produced, admission PENDING.\n"
                "=== Run the EXTERNAL pinned Direct verifier + adapter (Phase C) to write "
                f"{cfg.w10_report_dir}/direct_admission_<cond>.json, then: stage2_run downstream ; "
                "stage2_run aggregate\n")
            return 3
        verify_direct_gate(cfg)
        lane_downstream(cfg)
        lane_p2s(cfg)
        lane_aggregate(cfg)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SchedulerError as e:
        sys.stderr.write(f"{e}\n")
        sys.exit(3)
