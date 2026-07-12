"""The mandatory verified Stage-2 Direct run loader.

There is exactly ONE research input to Stage 3: a Direct **run directory** plus the
raw input root its files were pinned against. A caller-authored lever document is
not an alternative path, not a fallback, and not a degraded mode — the argument
does not exist.

Admission is a refusal machine, in this order:

  1. **File inventory.** The directory must contain exactly the ten Direct release
     files. One extra, stale or missing file is fatal. The expected set is
     RE-DECLARED here rather than imported from the Direct package: a loader that
     imports the producer's own idea of what it produced checks nothing.

  2. **Direct's own standalone verifier.** ``python -m direct.verify_run`` is run as
     a subprocess and must exit 0. That verifier RECONSTRUCTS the run from the raw
     public matrices, the sgRNA library, the contributor manifest and the Stage-1
     artifacts. Source reconstruction — not self-consistency — is the authority, so
     a mutated row whose local self-hashes were all refreshed still fails here.
     A verifier that cannot be located is an abort, never a skip.

  3. **Independent binding.** Stage 3 hashes every file it consumes itself and binds
     those hashes, the Direct run_id / run_binding_sha256 / method, the Stage-1
     selection+release hashes and the verifier-report hash into its own annotation
     ID. Stage 3 never copies a hash the upstream document declared about itself.

  4. **Upstream context, not a gate.** Whatever Stage-1/Stage-2 gate fields the Direct
     run carries are preserved VERBATIM as upstream context. Stage 3 does not read them
     to decide anything: it has no promotion, eligibility or recommendation vocabulary
     left to gate (see :mod:`druglink.workflow`). A failed upstream gate does not
     un-measure a measurement, and Stage 3 never re-labels one.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

from . import artifact_class as ac
from .hashing import content_hash, file_sha256, sha256_hex

# The Direct release inventory, re-declared from the contract (never imported).
EXPECTED_DIRECT_FILES = frozenset({
    "axis.json", "input_manifest.json", "gene_universe.json", "provenance.json",
    "verification.json", "screen.parquet", "masks.parquet",
    "contributing_guides.parquet", "guide_support.parquet", "donor_support.parquet",
})

# Files whose CONTENT Stage 3 actually consumes. Every one is hashed and bound.
CONSUMED_FILES = ("provenance.json", "axis.json", "verification.json",
                  "screen.parquet", "gene_universe.json", "input_manifest.json",
                  "masks.parquet", "contributing_guides.parquet",
                  "guide_support.parquet", "donor_support.parquet")

PROVENANCE_SCHEMA = "spot.stage02_provenance.v3"
VERIFICATION_SCHEMA = "spot.stage02_verification.v3"

# Which Direct lanes each Stage-3 artifact class may consume. `analysis` is generic:
# it reads any real Direct lane. `fixture` reads ONLY a synthetic Direct run — that is
# the whole fixture firewall on the upstream side.
DIRECT_LANES_FOR_CLASS = {
    ac.ANALYSIS: ("research_only", "production"),
    ac.FIXTURE: ("synthetic",),
}

VERIFIER_MODULE = "direct.verify_run"
DIRECT_ANALYSIS_ENV = "SPOT_DIRECT_ANALYSIS"


class DirectRunError(ValueError):
    """The Direct run directory is absent, incomplete, unverified or inadmissible."""


@dataclass(frozen=True)
class DirectRun:
    """An admitted Direct run: verified by Direct, re-hashed by Stage 3."""
    run_dir: str
    run_id: str
    artifact_class: str                    # the STAGE-3 artifact_class that admitted it
    provenance: dict[str, Any]
    axis: dict[str, Any]
    verification: dict[str, Any]
    screen: pd.DataFrame
    file_sha256: dict[str, str]
    verifier: dict[str, Any]
    binding: dict[str, Any]

    @property
    def binding_sha256(self) -> str:
        return content_hash(self.binding)


def resolve_direct_analysis(explicit: Optional[str] = None) -> str:
    """Locate the Direct analysis root that provides ``direct.verify_run``.

    Order: explicit argument, then ``$SPOT_DIRECT_ANALYSIS``, then the sibling
    Direct worktree. Not-found is a hard error: a Stage-3 run that cannot execute
    Direct's verifier must abort, because "verified" would otherwise mean "assumed".
    """
    candidates = [explicit, os.environ.get(DIRECT_ANALYSIS_ENV)]
    # .../<worktree>/03_druglink/analysis/druglink -> the worktree's parent
    here = os.path.dirname(os.path.abspath(__file__))
    worktrees = os.path.normpath(os.path.join(here, "..", "..", "..", ".."))
    candidates.append(os.path.join(worktrees, "spot-stage2-direct",
                                   "02_geneskew", "analysis"))
    for cand in candidates:
        if cand and os.path.isfile(os.path.join(cand, "direct", "verify_run.py")):
            return os.path.abspath(cand)
    raise DirectRunError(
        "cannot locate Direct's standalone verifier (direct/verify_run.py). Stage 3 "
        f"refuses to admit a Direct run it cannot independently verify. Set "
        f"${DIRECT_ANALYSIS_ENV} to the Direct analysis root.")


def run_direct_verifier(run_dir: str, inputs_root: str,
                        direct_analysis: Optional[str] = None) -> dict[str, Any]:
    """Execute Direct's standalone verifier. Non-zero exit aborts Stage 3."""
    analysis = resolve_direct_analysis(direct_analysis)
    argv = [sys.executable, "-m", VERIFIER_MODULE,
            "--run-dir", os.path.abspath(run_dir),
            "--inputs-root", os.path.abspath(inputs_root)]
    env = dict(os.environ)
    env["PYTHONPATH"] = analysis + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(argv, capture_output=True, text=True, env=env, check=False)
    report = proc.stdout + proc.stderr

    n_checks = report.count("[PASS]") + report.count("[FAIL]")
    n_failed = report.count("[FAIL]")
    result = {
        # The command is recorded WITHOUT machine-local paths: the run/input roots
        # are identified by the hashes bound alongside, not by where they sat.
        "verifier_module": VERIFIER_MODULE,
        "verifier_argv": ["python", "-m", VERIFIER_MODULE, "--run-dir", "<run>",
                          "--inputs-root", "<inputs>"],
        "exit_code": proc.returncode,
        "n_checks": n_checks,
        "n_failed": n_failed,
        "report_sha256": sha256_hex(report),
    }
    if proc.returncode != 0:
        raise DirectRunError(
            f"Direct's standalone verifier REFUSED this run (exit {proc.returncode}, "
            f"{n_failed}/{n_checks} checks failed). Stage 3 aborts before any "
            f"acquisition or annotation.\n{report.strip()[-2000:]}")
    if n_checks == 0:
        raise DirectRunError(
            "Direct's verifier exited 0 but reported no checks; refusing to treat an "
            "empty verification as a pass")
    return result


def _read_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _check_inventory(run_dir: str) -> None:
    if not os.path.isdir(run_dir):
        raise DirectRunError(f"Direct run directory does not exist: {run_dir}")
    present = {f for f in os.listdir(run_dir) if not f.startswith(".")}
    extra = sorted(present - EXPECTED_DIRECT_FILES)
    missing = sorted(EXPECTED_DIRECT_FILES - present)
    if extra or missing:
        raise DirectRunError(
            f"Direct run file inventory is not exact: extra={extra} missing={missing}")


def _check_screen_contract(screen: pd.DataFrame, verification: dict[str, Any]) -> None:
    """The two arms must arrive as two independent, nullable-ranked populations."""
    from .armlever import ARMS, ARM_RANK_COLUMN, BANNED_OBJECTIVE_COLUMNS

    banned = sorted(BANNED_OBJECTIVE_COLUMNS.intersection(screen.columns))
    if banned:
        raise DirectRunError(
            f"screen.parquet carries a combined/headline objective column: {banned}")
    for arm in ARMS:
        if arm not in screen.columns:
            raise DirectRunError(f"screen.parquet has no {arm!r} arm value column")
        rank_col = ARM_RANK_COLUMN[arm]
        if rank_col not in screen.columns:
            raise DirectRunError(f"screen.parquet has no {rank_col!r} column")
        dtype = str(screen[rank_col].dtype)
        if dtype != "Int64":
            raise DirectRunError(
                f"{rank_col} must be nullable Int64 (a NaN float rank invents a rank "
                f"for a target that has none); got {dtype}")

    declared = verification.get("row_count")
    if declared != len(screen):
        raise DirectRunError(
            f"verification.json row_count={declared} but screen.parquet has "
            f"{len(screen)} rows")
    if verification.get("complete_disposition") is not True:
        raise DirectRunError(
            "Direct did not emit a complete disposition; Stage 3 refuses a screen "
            "that silently dropped source targets")


def _check_artifact_class(artifact_class: str, provenance: dict[str, Any]) -> None:
    """The fixture firewall, on the upstream side. That is the only gate left.

    Stage 3 does not read Direct's Stage-1 gate fields to decide anything — it has no
    promotion or eligibility vocabulary to gate. It carries them as context.
    """
    permitted = DIRECT_LANES_FOR_CLASS[artifact_class]
    declared = provenance.get("namespace")
    if declared not in permitted:
        raise DirectRunError(
            f"the {artifact_class} artifact class refuses a Direct run in lane "
            f"{declared!r}; it may consume {list(permitted)}. A fixture may never "
            "consume a real Direct run, and an analysis may never consume a synthetic "
            "one.")


def load(run_dir: str, inputs_root: str, *, artifact_class: str,
         direct_analysis: Optional[str] = None) -> DirectRun:
    """Admit a Direct run directory, or refuse. There is no other research input."""
    ac.require(artifact_class)
    _check_inventory(run_dir)

    # Direct's verifier runs BEFORE anything is parsed or trusted.
    verifier = run_direct_verifier(run_dir, inputs_root, direct_analysis)

    # Stage 3 hashes what it consumes. It does not copy a declared hash.
    hashes = {name: file_sha256(os.path.join(run_dir, name))
              for name in sorted(CONSUMED_FILES)}

    provenance = _read_json(os.path.join(run_dir, "provenance.json"))
    axis = _read_json(os.path.join(run_dir, "axis.json"))
    verification = _read_json(os.path.join(run_dir, "verification.json"))

    if provenance.get("schema_version") != PROVENANCE_SCHEMA:
        raise DirectRunError(
            f"Direct provenance schema_version={provenance.get('schema_version')!r}; "
            f"Stage 3 consumes {PROVENANCE_SCHEMA!r}")
    if verification.get("schema_version") != VERIFICATION_SCHEMA:
        raise DirectRunError(
            f"Direct verification schema_version="
            f"{verification.get('schema_version')!r}; Stage 3 consumes "
            f"{VERIFICATION_SCHEMA!r}")

    run_id = str(provenance.get("run_id") or "")
    if run_id != os.path.basename(os.path.abspath(run_dir).rstrip("/")):
        raise DirectRunError(
            f"Direct run_id {run_id!r} does not name its own directory")
    if run_id != str(verification.get("run_id")):
        raise DirectRunError("provenance and verification disagree about run_id")

    _check_artifact_class(artifact_class, provenance)

    screen = pd.read_parquet(os.path.join(run_dir, "screen.parquet"))
    _check_screen_contract(screen, verification)

    binding = _binding(provenance=provenance, verification=verification,
                       hashes=hashes, verifier=verifier, artifact_class=artifact_class)
    return DirectRun(run_dir=os.path.abspath(run_dir), run_id=run_id,
                     artifact_class=artifact_class, provenance=provenance, axis=axis,
                     verification=verification, screen=screen, file_sha256=hashes,
                     verifier=verifier, binding=binding)


def _binding(*, provenance: dict[str, Any], verification: dict[str, Any],
             hashes: dict[str, str], verifier: dict[str, Any],
             artifact_class: str) -> dict[str, Any]:
    """Everything about the upstream that the Stage-3 annotation ID commits to.

    Any change to a Direct file, its run identity, its Stage-1 provenance, or the
    verifier's verdict changes this content and therefore the Stage-3 ID.
    """
    run_binding = provenance.get("run_binding") or {}
    stage1_release = run_binding.get("stage1_release") or {}
    selection = provenance.get("selection_contract") or {}
    return {
        "stage3_artifact_class": artifact_class,
        "direct_run_id": provenance["run_id"],
        "direct_run_binding_sha256": provenance["run_binding_sha256"],
        "direct_lane_declared": provenance["namespace"],
        "direct_question_id": provenance["question_id"],
        "direct_selection_id": provenance["selection_id"],
        "direct_analysis_condition": provenance["analysis_condition"],
        "direct_mask_sha256": provenance["mask_sha256"],
        "direct_gene_universe_sha256": provenance["gene_universe_sha256"],
        "direct_lane": run_binding.get("lane"),
        "direct_stage2_method": run_binding.get("stage2_method"),
        "direct_file_sha256": dict(sorted(hashes.items())),
        "direct_verifier": dict(sorted(verifier.items())),
        "direct_row_count": verification["row_count"],
        "direct_source_target_count": verification["source_target_count"],
        "stage1_selection": {
            "selection_id": selection.get("selection_id"),
            "question_id": selection.get("question_id"),
            "contract_sha256": selection.get("contract_sha256"),
            "stage1_method_version": selection.get("stage1_method_version"),
            "stage1_validation_sha256": selection.get("stage1_validation_sha256"),
            "stage1_validation_status": selection.get("stage1_validation_status"),
        },
        "stage1_release": {
            "kind": stage1_release.get("kind"),
            "method_version": stage1_release.get("method_version"),
            "hashes": stage1_release.get("hashes"),
            "n_production_selectable": stage1_release.get("n_production_selectable"),
        },
        # Upstream gate fields, preserved VERBATIM as context. Stage 3 reads none of
        # them to decide anything: a failed upstream gate does not un-measure a
        # measurement, and Stage 3 has no promotion vocabulary left to gate. They are
        # carried under neutral names so the retired keys cannot re-enter a bundle.
        "upstream_gate_context": {
            "direct_lane": provenance.get("namespace"),
            "stage1_gate_passed": provenance.get("production_gate_passed"),
            "stage1_n_selectable": (
                (run_binding.get("stage1_release") or {}).get(
                    "n_production_selectable")),
            "note": "upstream context only; Stage 3 does not gate on it",
        },
    }


def upstream_gate_context(direct: DirectRun) -> dict[str, Any]:
    return dict(direct.binding["upstream_gate_context"])
