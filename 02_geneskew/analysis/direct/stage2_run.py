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
             "ENV_LOCK", "OUT", "W10_REPORT_DIR",
             # the two EXPLICIT Ensembl-keyed gene-set artifacts. The producer, the aggregate
             # pins and the bundle all bind these SAME real files — never the symbol-keyed cache,
             # never an alias. (<run-root>/geneset-cache-ensembl/{reactome,go_bp}_ensembl.genesets.json)
             "GENESETS_REACTOME", "GENESETS_GO_BP")
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
        self.temporal_verifier = os.environ.get(
            "TEMPORAL_VERIFIER_DIR",
            "/home/tcelab/worktrees/spot-stage2-temporal-verifier/02_geneskew/analysis/verify_temporal_arms")
        self.pathway_verifier = os.environ.get(
            "PATHWAY_VERIFIER_DIR",
            "/home/tcelab/worktrees/spot-stage2-pathway-verifier/02_geneskew/analysis/direct")
        self.p2s_scores = os.environ.get("P2S_SCORES", P2S_SCORES_DEFAULT)
        self.p2s_env_lock = os.environ.get("P2S_ENV_LOCK", "")   # W15's SECOND env lock (P2S runtime)


# ---- run-identity manifest (Phase A) ----------------------------------------------------
def _git_out(d, *a):
    import subprocess
    r = subprocess.run(["git", "-C", d, *a], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


_UNBOUND_V = {"head": "<unbound>", "clean_tree": None, "tree_sha256": "<unbound>"}


def _verifier_binding(path):
    """Bind an EXTERNAL verifier checkout: exact HEAD commit, clean-tree flag, canonical code-tree
    hash (.pyc/__pycache__ excluded). A verifier byte/head change MOVES the run identity. A missing
    or non-git dir binds <unbound> (identity tests decouple from the concurrently-edited real
    worktrees this way); production requires the real checkout and its clean HEAD at invocation."""
    if DRY:
        return {"head": "<head>", "clean_tree": True, "tree_sha256": f"<tree:{os.path.basename(path)}>"}
    if not os.path.isdir(path):
        return dict(_UNBOUND_V)
    head = _git_out(path, "rev-parse", "HEAD")
    if head is None:
        return dict(_UNBOUND_V)
    dirty = _git_out(path, "status", "--porcelain", "--untracked-files=no")
    return {"head": head, "clean_tree": (dirty == ""), "tree_sha256": "tree:" + tree_sha256(path)}


def _require_clean_verifier(cfg, lane, path):
    """At the point a lane's EXTERNAL verifier is INVOKED it must be a REAL checkout at a CLEAN HEAD
    (a dirty or unbound verifier cannot independently admit). Fail closed. DRY is a no-op."""
    if DRY:
        return
    b = _verifier_binding(path)
    if b["clean_tree"] is not True:
        raise SchedulerError(
            f"REFUSED: the {lane} verifier checkout {path} is not a clean pinned HEAD "
            f"(clean_tree={b['clean_tree']}); an admission from a dirty/unbound verifier is not "
            "independent — commit/clean the verifier checkout first")


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
    # bind the REAL explicit Ensembl gene-set artifacts (GENESETS_REACTOME / GENESETS_GO_BP) — the
    # SAME files the producer, the aggregate pins, and the bundle reference. Never sel_dir aliases.
    gene_sets = {}
    for src, gp in (("reactome", cfg.genesets_reactome), ("go_bp", cfg.genesets_go_bp)):
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
            # ALL THREE external verifier implementations, bound by exact HEAD + clean-tree flag +
            # canonical code-tree hash (never a frozen scalar — the head is read LIVE from the
            # checkout). A byte/head change in ANY of them moves this identity, voiding a prior
            # admission on resume.
            "direct": _verifier_binding(cfg.direct_verifier),
            "temporal": _verifier_binding(cfg.temporal_verifier),
            "pathway": _verifier_binding(cfg.pathway_verifier),
            # the W10 NEUTRAL ADAPTER's own code identity (the admitting code inside the Direct
            # verifier); re-derived and checked live in w10_admitted.
            "direct_w10_verifier_id": "spot.stage02.direct.arm_bundle.verifier.v1",
            "direct_w10_verifier_code_sha256": W10_VERIFIER_CODE,
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
    """On resume, BEFORE Phase E: each EXTERNAL verifier checkout (direct/temporal/pathway) must
    still be at its exact bound HEAD + code tree. A swap or byte change is refused (the full-body
    identity compare would already differ; this gives the precise lane). <unbound> pins are skipped
    (decoupled/test)."""
    pins = stored_body.get("verifier_pins", {})
    for lane, path in (("direct", cfg.direct_verifier), ("temporal", cfg.temporal_verifier),
                       ("pathway", cfg.pathway_verifier)):
        want = pins.get(lane)
        if not isinstance(want, dict) or want.get("tree_sha256") in (None, "<unbound>"):
            continue
        got = _verifier_binding(path)
        if got["head"] != want.get("head") or got["tree_sha256"] != want.get("tree_sha256"):
            raise SchedulerError(
                f"RESUME REFUSED: the {lane} verifier checkout changed since preflight "
                "(head/tree moved) — a prior admission from different verifier bytes is void")


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
W10_VERIFIER_CODE = "8290802638898db622a8baf19f233b54b5f6f1c8434f192730aa28f829f8715f"
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


def _completed(cfg, name):
    """Resume gate. ABSENT receipt -> not done, run the phase fresh (False). PRESENT receipt -> it
    MUST re-verify: verify_receipt REFUSES (raises SchedulerError) on a tampered/invalid/stale
    receipt — we let that propagate, never swallow it into a silent rerun/overwrite of native or
    admitted bytes. PRESENT and valid -> done, skip (True). DRY never skips (topology always emits)."""
    if DRY:
        return False
    if not os.path.isfile(_receipt_path(cfg, name)):
        return False                     # absent -> run the phase fresh
    verify_receipt(cfg, name)            # present -> re-verify; a tampered/invalid receipt RAISES here
    return True                          # present AND verified -> skip (no rerun / no overwrite)


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
    if all(_completed(cfg, f"B.direct.{c}") for c in CONDITIONS):
        return   # resume: all Direct bundle receipts verify -> skip (native bytes untouched)
    # ONE authoritative all-conditions run: run_arms --all-conditions derives the condition set from
    # the BOUND Stage-1 release (never a number written here) and produces every condition's
    # content-addressed bundle in a single invocation. Per-condition IMMUTABLE bundle receipts are
    # still bound (the bundles still exist; only the invocation changed) over the ONE shared argv.
    argv = _py("run_arms", "--all-conditions", *bundle_args(cfg),
               "--out-root", os.path.join(cfg.out, "direct"))
    # produce direct:root (the aggregate lane consumes it — nothing produced it before) alongside
    # each per-condition endpoint.
    run("direct:all-conditions", argv,
        produces=[f"direct:{c}" for c in CONDITIONS] + ["direct:root"])   # exact executed command
    for cond in CONDITIONS:
        # bind the IMMUTABLE content-addressed bundle dir, NOT the shared mutable OUT/direct root
        # (so each receipt stays valid as the sibling condition bundles are added). All three
        # receipts share the same all-conditions argv — one run produced all three.
        bdir = direct_bundle_for(cfg, cond)
        _write_receipt(cfg, f"B.direct.{cond}", argv=argv,
                       inputs=[cfg.de, cfg.sgrna, cfg.stage1_release],
                       outputs=[bdir], prereqs=["A.preflight"])


def verify_direct_gate(cfg):
    _phase("C direct/W10 gate (EXTERNAL pinned verifier checkout)")
    if _completed(cfg, "C.direct_admitted"):
        return   # resume: W10 admission verifies -> skip (never re-invoke over admitted bytes)
    _require_clean_verifier(cfg, "direct", cfg.direct_verifier)
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


def verify_direct_release(cfg):
    """Phase C (release level): the pinned EXTERNAL Direct release verifier independently opens and
    re-hashes the NATIVE OUT/direct/direct_release.json (its own direct_release_sha256), requires
    EVERY condition the bound Stage-1 release ships to be admitted in full, and writes its admission
    to the native lane root OUT/direct/direct_release_admission.json (exit 0=ADMIT, 1=REFUSE). The
    scheduler never self-admits; it requires verdict==ADMIT. No manufactured top-level inventory."""
    _phase("C direct RELEASE admission (pinned EXTERNAL verify_direct_release over native OUT/direct)")
    if _completed(cfg, "C.direct_release_admitted"):
        return
    _require_clean_verifier(cfg, "direct", cfg.direct_verifier)
    dv = cfg.direct_verifier
    rel_dir = os.path.join(cfg.out, "direct")                     # native release dir (holds direct_release.json)
    native_release = os.path.join(rel_dir, "direct_release.json")
    admission = os.path.join(rel_dir, "direct_release_admission.json")   # native lane-root admission
    run("direct-release-verify",
        [("python" if DRY else sys.executable), os.path.join(dv, "verify_direct_release.py"),
         "--release", rel_dir,
         "--de-main", cfg.de, "--sgrna", cfg.sgrna, "--by-guide", cfg.guide,
         "--by-donors", cfg.donor, "--guide-manifest", cfg.manifest,
         "--source-registry", cfg.srcreg, "--pseudobulk", cfg.pb,
         "--stage1-v3-release", cfg.stage1_release, "--release-root", cfg.stage1_release_root,
         "--env-lock", cfg.env_lock,
         "--expect-h5ad-sha256", ("<sha256:DE.h5ad>" if DRY else file_sha256(cfg.de)),
         "--recompute", "all", "--report", admission],
        consumes=[f"w10_admission:{c}" for c in CONDITIONS], produces=["direct_release_admission"], cwd=dv)
    if not DRY:
        try:
            adm = json.load(open(admission))
        except Exception as e:
            raise SchedulerError(f"Phase C REFUSED: verify_direct_release wrote no readable admission: {e}")
        if (adm.get("verdict") != "ADMIT"
                or adm.get("verifier_id") != "spot.stage02.direct.release.verifier.v1"):
            raise SchedulerError(
                "Phase C REFUSED: the Direct release was not independently ADMITTED "
                f"(verdict={adm.get('verdict')!r}, verifier_id={adm.get('verifier_id')!r})")
    _write_receipt(cfg, "C.direct_release_admitted", argv=["verify_direct_release"],
                   inputs=[native_release], outputs=[admission], prereqs=["C.direct_admitted"])


def lane_step0(cfg):
    _phase("D step0")
    if _completed(cfg, "D.step0"):
        return
    require_admitted_direct(cfg)
    for cond in CONDITIONS:
        # Step0 reads the native W10 MASK report (--direct-mask-report) + the Direct bundle and
        # internally binds the mask via signature_matrix.w10_anchor. signature_matrix takes NO
        # --stage1-release* flags (not in its CLI); its accepted flags are exactly these.
        run(f"step0:{cond}",
            _py("signature_matrix", "--condition", cond, "--de-main", cfg.de, "--sgrna", cfg.sgrna,
                "--guide-manifest", cfg.manifest, "--source-registry", cfg.srcreg,
                "--direct-bundle", direct_bundle_for(cfg, cond),
                "--direct-mask-report", native_report_path(cfg, cond),
                "--env-lock", cfg.env_lock, "--out-root", cfg.sigroot),
            consumes=[f"direct:{cond}", f"w10_admission:{cond}"], produces=[f"signatures:{cond}"])
    _write_receipt(cfg, "D.step0", argv=["signature_matrix"], inputs=[cfg.de],
                   outputs=[cfg.sigroot], prereqs=["C.direct_admitted"])


def lane_temporal(cfg):
    _phase("D temporal")
    if _completed(cfg, "D.temporal"):
        return
    require_admitted_direct(cfg)
    dargs = []
    for cond in CONDITIONS:
        dargs += ["--direct-bundle", f"{cond}:{direct_bundle_for(cfg, cond)}",
                  "--w10-report", f"{cond}:{native_report_path(cfg, cond)}"]
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
    if _completed(cfg, "D.pathway"):
        return
    require_admitted_direct(cfg)
    for cond in CONDITIONS:
        for src in SOURCES:
            run(f"pathway:{cond}:{src}",
                _py("run_pathway_arms", "--condition", cond, *bundle_args(cfg),
                    "--gene-sets", {"reactome": cfg.genesets_reactome,
                                    "go_bp": cfg.genesets_go_bp}[src],
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


def verify_lanes(cfg):
    """Phase E — the external temporal (W11) + pathway (W4) INDEPENDENT admissions must exist
    before aggregate. Producers write PENDING lane inventories (`release_inventory --lane`); the
    pinned external verifier checkouts admit them; `run_release` requires each admitted. The
    primary aggregate cannot complete without these — and needs NO P2S."""
    _phase("E lane admissions (external temporal/pathway)")
    if _completed(cfg, "E.lane_admissions"):
        return
    _require_clean_verifier(cfg, "temporal", cfg.temporal_verifier)
    _require_clean_verifier(cfg, "pathway", cfg.pathway_verifier)
    if DRY:
        print("=== PHASE E: release_inventory --lane {temporal,pathway} (PENDING) → external "
              "W11/W4 admissions → {temporal,pathway}_arm_external_admission.json")
        for lane in ("temporal", "pathway"):
            print(f"=== REQUIRES {os.path.join(cfg.out, lane + '_arm_external_admission.json')}")
        return
    for lane in ("temporal", "pathway"):
        run(f"inventory:{lane}",
            _py("release_inventory", "--lane", lane, "--bundles-root", cfg.out,
                "--release", cfg.stage1_release, "--release-root", cfg.stage1_release_root,
                "--env-lock", cfg.env_lock),
            produces=[f"{lane}:inventory"])
    outs = []
    for lane in ("temporal", "pathway"):
        adm = os.path.join(cfg.out, f"{lane}_arm_external_admission.json")
        if not os.path.isfile(adm):
            raise SchedulerError(
                f"REFUSED: aggregate requires the external {lane} admission {adm} — run the pinned "
                f"{lane} verifier checkout to admit the {lane} release before aggregate")
        outs.append(adm)
    _write_receipt(cfg, "E.lane_admissions", argv=["phase-e-lane-admissions"], inputs=[],
                   outputs=outs, prereqs=["D.temporal", "D.pathway"])


# The pinned per-lane INDEPENDENT verifier identities, sourced VERBATIM from
# verify_lane_admission.NATIVE (analysis/direct/verify_lane_admission.py lines 57-81 — the module
# the aggregate uses to type each lane native admission). check_external_admission
# (verify_release_envelope.py) and check_preflight (verify_bundle_rules.py) compare an
# admission/preflight verifier_id to expect_verifiers[lane]["verifier_id"]; LA.adapt independently
# enforces the SAME ids. (REPORT_OF is {} in verify_manifest_rules, so schema_version /
# required_gates are never consumed — verifier_id is the only field the gates read.)
LANE_VERIFIER_IDS = {
    "direct": "spot.stage02.direct.release.verifier.v1",
    "temporal": "spot.stage02.temporal.arm.independent_verifier.v1",
    "pathway": "spot.stage02.pathway.arm.independent_verifier.v1",
}


def _gene_set_identity(path):
    """The FULL gene-set identity of ONE Ensembl-keyed artifact, BY CONTENT (never a source name).

    The fields mirror what the native pathway producer binds at method.gene_sets
    (genesets.binding_block) so check_gene_sets can compare them field-by-field: the release
    (id/licence/reference), the identifier namespace, BOTH universes — the DE-readout
    (effect_universe_sha256) and the perturbation-target (target_universe_sha256) — and the
    artifact's own RAW and CANONICAL hashes. Every value is read/derived from the artifact bytes;
    none is fabricated. NOTE: content_hash(artifact) is a whole-file canonical hash and is NOT the
    membership-recipe canonical the geneset-cache provenance pins; the RAW hash matches that pin.
    """
    from .hashing import content_hash, file_sha256
    art = json.load(open(path))
    rel = art.get("release") or {}
    return {
        "gene_set_source": str(rel.get("source")),
        "release_id": rel.get("release_id"),
        "gene_set_license": rel.get("license"),
        "gene_set_license_reference": rel.get("license_reference"),
        "gene_id_namespace": art.get("gene_id_namespace"),
        "effect_universe_sha256": art.get("effect_universe_sha256"),     # DE-readout universe
        "target_universe_sha256": art.get("target_universe_sha256"),     # perturbation-target universe
        "raw_sha256": file_sha256(path),                                 # artifact RAW hash
        "canonical_sha256": content_hash(art),                           # artifact CANONICAL hash
    }


def _expect_pins(cfg):
    """The run_release / verify_run_manifest EXPECT_* pins, materialized to cfg.out/.pins as the
    KINDS the INDEPENDENT verifier consumes (verify_run_manifest.verify):

      --expect-release-sha256   VALUE  compared to content_sha256(load_json(release)) [G_RELEASE_PIN]
      --expect-env-lock-sha256  VALUE  the env-lock FILE sha256 (W.check_supplied_lock)
      --expect-gene-sets        PATH   R.load_json(path) -> {source: identity}; G_SOURCES needs its
                                       keys == release.selector.pathway_sources (R.release_sources),
                                       and check_gene_sets compares each field to the bundle binding
      --expect-verifiers        PATH   R.load_json(path) -> {lane: {"verifier_id": ...}}
      --expected-code-identity  PATH   R.load_json(path) -> code-identity tuple; G_CLEAN needs
                                       clean_tree is True, check_code_identity a shared field

    THE DEFECT this fixes: the three PATH args were returned as HASH VALUES, so verify_run_manifest
    did R.load_json(<hash string>) -> None and every dependent gate failed (rc1). They are FILES
    now. The release VALUE was the run-identity manifest file: sha; the verifier recomputes the
    CANONICAL content hash, so it is corrected. Every value is DERIVED from an authoritative source:
      - release:   hashing.content_hash(load release)   (canonical; == R.content_sha256)
      - env:       the identity-bound env-lock file sha
      - gene_sets: the REAL identity of the two EXPLICIT Ensembl artifacts (GENESETS_REACTOME/
                   GENESETS_GO_BP) keyed by the release own pathway_sources — release/licence/
                   namespace, BOTH universes, and the raw+canonical artifact hashes (NOT source names)
      - verifiers: the pinned lane verifier ids (verify_lane_admission.NATIVE)
      - code:      code_digest.run_binding() — the same tuple run_manifest.build binds
    DRY never reaches here (lane_aggregate uses <id> placeholders).
    """
    from . import code_digest
    from .hashing import content_hash

    m = json.load(open(identity_path(cfg)))

    def raw(v):
        return str(v).split(":", 1)[-1] if v else ""

    # release: the CANONICAL content hash the external verifier recomputes — NOT the file sha the
    # identity manifest records (content_sha256(release) != file_sha256(release_bytes)).
    release = json.load(open(cfg.stage1_release))
    release_sha = content_hash(release)
    env_sha = raw(m.get("env_lock_sha256"))
    sources = [str(x) for x in ((release.get("selector") or {}).get("pathway_sources") or [])]
    if not sources:
        raise SchedulerError(
            "aggregate: the Stage-1 release names no selector.pathway_sources; the gene-set "
            "source universe the pin must cover is unknown")

    # the two EXPLICIT Ensembl-keyed artifacts, indexed by their OWN declared source (so which
    # input is which is decided by the artifact, not by the env var name).
    def _norm(x):
        return str(x).lower().replace("-", "_")
    identities = {}
    for key, path in (("reactome", cfg.genesets_reactome), ("go_bp", cfg.genesets_go_bp)):
        if not path or not os.path.isfile(path):
            raise SchedulerError(
                f"aggregate: the {key} Ensembl gene-set artifact is missing: {path!r} "
                "(set GENESETS_REACTOME / GENESETS_GO_BP to the real artifacts)")
        ident = _gene_set_identity(path)
        identities[_norm(ident["gene_set_source"])] = ident

    # G_SOURCES: the pin keys are the release OWN pathway_sources, in the release form (e.g. GO-BP);
    # each source binds the identity of its Ensembl artifact, with gene_set_source in the release form.
    gene_sets_doc = {}
    for src in sources:
        ident = identities.get(_norm(src))
        if ident is None:
            raise SchedulerError(
                f"aggregate: the release names pathway source {src!r} but neither "
                "GENESETS_REACTOME nor GENESETS_GO_BP provides that Ensembl artifact")
        gene_sets_doc[src] = dict(ident, gene_set_source=src)

    pins_dir = os.path.join(cfg.out, ".pins")
    os.makedirs(pins_dir, exist_ok=True)

    def _write_pin(name, doc):
        path = os.path.join(pins_dir, name)
        with open(path, "w") as fh:
            json.dump(doc, fh, sort_keys=True, indent=2)
        return path

    gene_sets_pin = _write_pin("expected_gene_sets.json", gene_sets_doc)
    verifiers_pin = _write_pin("expected_verifiers.json",
                               {lane: {"verifier_id": vid}
                                for lane, vid in LANE_VERIFIER_IDS.items()})
    code_pin = _write_pin("expected_code_identity.json", code_digest.run_binding())

    pins = {"env": env_sha, "release": release_sha, "gene_sets": gene_sets_pin,
            "verifiers": verifiers_pin, "code": code_pin}
    missing = [k for k, v in pins.items() if not v]
    if missing:
        raise SchedulerError(f"aggregate: EXPECT_* pins not bound in the run identity: {missing}")
    return pins


def lane_aggregate(cfg):
    _phase("F aggregate (run_release --out FILE --verify + separate admission report)")
    if _completed(cfg, "F.aggregate_admission"):
        return
    require_admitted_direct(cfg)
    if not DRY:
        verify_receipt(cfg, "E.lane_admissions")   # aggregate IMPOSSIBLE before Phase E receipts exist
    p = ({"env": "<id>", "release": "<id>", "gene_sets": "<id>", "verifiers": "<id>", "code": "<id>"}
         if DRY else _expect_pins(cfg))
    manifest = os.path.join(cfg.out, "stage2_run_manifest.json")
    report = os.path.join(cfg.out, "stage2_aggregate_verification.json")
    argv = _py("run_release", "--bundles-root", cfg.out, "--release", cfg.stage1_release,
               "--release-root", cfg.stage1_release_root, "--env-lock", cfg.env_lock,
               "--expect-env-lock-sha256", p["env"], "--expect-release-sha256", p["release"],
               "--expect-gene-sets", p["gene_sets"], "--expect-verifiers", p["verifiers"],
               "--expected-code-identity", p["code"],
               "--out", manifest, "--verify-report", report, "--verify")
    run("aggregate:run_release", argv,
        consumes=["direct:root", "temporal:root", "pathway:root"],
        produces=["aggregate:topology_manifest", "aggregate:admission"])
    # aggregate PRODUCER receipt (the manifest) distinct from the independent ADMISSION receipt
    _write_receipt(cfg, "F.aggregate_manifest", argv=argv, inputs=[], outputs=[manifest],
                   prereqs=["C.direct_admitted", "E.lane_admissions"])
    _write_receipt(cfg, "F.aggregate_admission", argv=argv, inputs=[manifest], outputs=[report],
                   prereqs=["F.aggregate_manifest"],
                   extra={"stage3_handoff": {"manifest": manifest, "report": report,
                                             "bundles_root": cfg.out, "stage1_release": cfg.stage1_release}})


def lane_downstream(cfg):
    lane_step0(cfg); lane_temporal(cfg); lane_pathway(cfg)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m direct.stage2_run")
    ap.add_argument("phase", nargs="?", default="all",
                    choices=["preflight", "direct", "verify-direct-gate", "verify-direct-release",
                             "step0", "temporal", "pathway", "verify-lanes", "p2s", "downstream",
                             "aggregate", "all"])
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
    elif args.phase == "verify-direct-release":
        verify_direct_release(cfg)
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
    elif args.phase == "verify-lanes":
        verify_lanes(cfg)          # Phase E, independently resumable
    elif args.phase == "aggregate":
        lane_aggregate(cfg)
    elif args.phase == "all":
        # A -> B -> C -> D -> E -> F, AUTOMATICALLY. No manual command between producer and verifier:
        # Phase C is the pinned EXTERNAL W10 invocation (verify_direct_gate), run inline. Every phase
        # self-skips when its receipt already verifies (deterministic resume; admitted native bytes
        # are never rerun or overwritten). require_admitted_direct / verify_receipt still fail closed.
        phaseA_preflight(cfg)
        lane_direct(cfg)           # Phase B: produce (or skip) the Direct release
        verify_direct_gate(cfg)    # Phase C: AUTO-invoke the pinned EXTERNAL W10 per-bundle verifier
        verify_direct_release(cfg) # Phase C: pinned EXTERNAL release-level admission over native OUT/direct
        lane_downstream(cfg)       # Phase D: step0 -> temporal(--all-pairs) -> pathway
        verify_lanes(cfg)          # Phase E: external temporal(W11)/pathway(W4) lane admissions
        lane_aggregate(cfg)        # Phase F: primary aggregate — NO P2S in the primary chain
        # P2S is a SEPARATE secondary lane (its own env/code/method identity + admission),
        # invoked independently via the `p2s` subcommand AFTER the primary run. Its absence must
        # never make the primary aggregate incomplete or change Direct bytes/ranks.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SchedulerError as e:
        sys.stderr.write(f"{e}\n")
        sys.exit(3)
