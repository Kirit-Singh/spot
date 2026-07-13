"""The Stage-3 admission door. Two independent gates, and neither one alone.

The Stage-3 owner's rule, quoted from the frozen r7 handoff:

    "The document schema is deliberately `additionalProperties: true`. Validating against
     the JSON Schema alone is not enough. The firewall against a combined/headline objective
     lives in the verifier's recursive banned-key scan + the hash bundle — not in the JSON
     Schema. Stage 4 must run `verifier.verify_stage3` to admit a bundle. A schema-valid
     bundle can still be a refused bundle, and that is by design."

Stage 4 never used `jsonschema.validate` for admission, so there was no schema-only door to
replace. What it *did* have was a hole of the same species: its restatement checked the hash
bundle and the retired promotion keys, but had no combined-objective scan, and admitted a
re-sealed bundle carrying `overall_rank`. That is fixed in `stage3_frozen` + `stage3_contract_v2`.

This module is the door itself. A bundle is admitted only if BOTH gates pass:

  GATE 1 — Stage-4's own restatement (`stage3_contract_v2.verify_annotation_bundle`).
      Imports nothing from Stage 3: re-derives every hash from the bytes, rejects retired
      promotion keys, rejects combined objectives in the document AND in the table columns.
      Runs ALWAYS, on every machine, with no external dependency.

  GATE 2 — Stage-3's own independent verifier (`verifier.verify_stage3`), the owner's
      mandated gate. Run OUT-OF-PROCESS: `python -m verifier.verify_stage3`. A subprocess,
      not an import, so Stage-3's package never enters Stage-4's import graph and cannot
      shadow, monkey-patch or vouch for Stage-4's own hasher. Exit 0 is the only pass.

Why two, when gate 1 already re-derives every hash? Because they fail differently.
`verify_stage3` re-derives Stage 3's output from Direct's `screen.parquet` and the pinned
acquisition cache, and resolves every Claude Science evidence record against the registry —
work Stage 4 has no business restating and could not honestly check. Gate 1 cannot be fooled
by a bug in Stage 3; gate 2 cannot be fooled by a bug in Stage 4. generator != evaluator, in
both directions.

### The honest boundary — and why `not_run` is not a pass

Gate 2 needs Stage-3's BUILD context, not just the bundle: the acquisition cache, the Direct
run, the raw Direct inputs. No real Stage-2 bundle exists yet (Stage 2 is at
READY-FOR-REAL-RUN, code + fixtures only), so that context does not exist to point at, and
gate 2 CANNOT be run against real data today.

That fact is recorded, never rounded off. `external_verifier` is `passed` or `not_run`, it
travels in the admission record, and `require_external_verifier=True` turns `not_run` into a
refusal. The data-bound integration will set that flag. Until then a bundle admitted with
`not_run` is admitted on gate 1 alone, the record says so in those words, and **no
integration-GO may be claimed on it**. A skip that calls itself a pass is the exact failure
this door exists to prevent.

Configured-but-broken is never a skip: if a Stage-3 verifier root IS configured and the
verifier fails, crashes, or cannot be executed, that is a REFUSAL.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

from .firewall import Rejection
from .stage3_contract_v2 import verify_annotation_bundle
from .stage3_frozen import (
    STAGE3_CONTRACT_SHA256,
    STAGE3_FROZEN_COMMIT,
    STAGE3_HANDOFF_SHA256,
    STAGE3_SCHEMA_SET_SHA256,
)

# The Stage-3 build context gate 2 needs. Absent -> gate 2 cannot run (recorded as `not_run`).
# Present but broken -> REFUSAL.
ENV_VERIFIER_ROOT = "SPOT_STAGE3_VERIFIER_ROOT"      # dir holding the `verifier/` package
ENV_CACHE_ROOT = "SPOT_STAGE3_CACHE_ROOT"            # the pinned acquisition cache
ENV_DIRECT_RUN = "SPOT_STAGE3_DIRECT_RUN"            # the verified Stage-2 Direct run
ENV_DIRECT_INPUTS = "SPOT_STAGE3_DIRECT_INPUTS_ROOT"  # raw Direct inputs
ENV_SCIENCE_REGISTRY = "SPOT_STAGE3_SCIENCE_REGISTRY"  # optional evidence registry
ENV_DIRECT_ANALYSIS = "SPOT_STAGE3_DIRECT_ANALYSIS"  # optional Stage-2 Direct analysis root

PASSED = "passed"
NOT_RUN = "not_run"

VERIFIER_TIMEOUT_S = 900


@dataclass(frozen=True)
class Stage3Admission:
    """What Stage 4 admitted, and on whose authority."""

    bundle_dir: str
    bundle_id: str
    document: dict[str, Any]
    tables: dict[str, list[dict[str, Any]]]
    external_verifier: str                     # PASSED | NOT_RUN
    external_verifier_detail: str
    stage3_handoff_sha256: str = STAGE3_HANDOFF_SHA256
    stage3_contract_sha256: str = STAGE3_CONTRACT_SHA256
    stage3_schema_set_sha256: str = STAGE3_SCHEMA_SET_SHA256
    stage3_frozen_commit: str = STAGE3_FROZEN_COMMIT
    gates: tuple[str, ...] = field(default=("stage4_restatement",))

    @property
    def data_bound_integration_ready(self) -> bool:
        """False while gate 2 has not run. Read this before claiming ANY integration-GO."""
        return self.external_verifier == PASSED


def verifier_context() -> dict[str, str] | None:
    """The Stage-3 build context, if it is configured. -> None when gate 2 cannot run.

    All four roots are required together: a half-configured context is a configuration
    error, not a licence to run a weaker verifier.
    """
    required = {
        "verifier_root": os.environ.get(ENV_VERIFIER_ROOT),
        "cache_root": os.environ.get(ENV_CACHE_ROOT),
        "direct_run": os.environ.get(ENV_DIRECT_RUN),
        "direct_inputs_root": os.environ.get(ENV_DIRECT_INPUTS),
    }
    present = {k: v for k, v in required.items() if v}
    if not present:
        return None
    missing = sorted(k for k, v in required.items() if not v)
    if missing:
        raise Rejection(
            "stage3_verifier_context_incomplete",
            f"a partial Stage-3 verifier context is configured (have {sorted(present)}, "
            f"missing {missing}). All four roots are required together — a half-configured "
            "verifier is a configuration error, not grounds to admit on a weaker gate.")
    return {k: str(v) for k, v in required.items()}


def run_external_verifier(bundle_dir: str, ctx: dict[str, str],
                          artifact_class: str) -> tuple[str, str]:
    """GATE 2. Stage-3's own verifier, out-of-process. -> (status, detail). Exit 0 or refuse."""
    root = ctx["verifier_root"]
    if not os.path.isdir(os.path.join(root, "verifier")):
        raise Rejection(
            "stage3_verifier_unavailable",
            f"{ENV_VERIFIER_ROOT}={root!r} holds no `verifier/` package. A configured "
            "verifier that cannot be found is a refusal, never a skip.")

    argv = [
        sys.executable, "-m", "verifier.verify_stage3",
        "--bundle", os.path.abspath(bundle_dir),
        "--cache-root", ctx["cache_root"],
        "--direct-run", ctx["direct_run"],
        "--direct-inputs-root", ctx["direct_inputs_root"],
        "--artifact-class", artifact_class,
    ]
    registry = os.environ.get(ENV_SCIENCE_REGISTRY)
    if registry:
        argv += ["--science-registry", registry]
    # The verifier re-runs Direct's OWN standalone verifier, which lives in the Stage-2 Direct
    # analysis tree. It resolves a default, but a real integration can pin it explicitly.
    direct_analysis = os.environ.get(ENV_DIRECT_ANALYSIS)
    if direct_analysis:
        argv += ["--direct-analysis", direct_analysis]

    # Prepend, never clobber: the verifier's root must win imports, but the real integration
    # may need the inherited PYTHONPATH too (a shared env, a src root). Replacing it outright
    # could turn a runnable verifier into an import crash — fail-closed, but a false NO-GO.
    inherited = os.environ.get("PYTHONPATH", "")
    env = dict(os.environ,
               PYTHONPATH=os.pathsep.join([root, inherited]) if inherited else root)
    try:
        proc = subprocess.run(argv, cwd=root, env=env, capture_output=True,
                              text=True, timeout=VERIFIER_TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Rejection(
            "stage3_verifier_unavailable",
            f"the configured Stage-3 verifier could not be executed ({type(exc).__name__}: "
            f"{exc}). A verifier that cannot run has not passed.") from exc

    if proc.returncode != 0:
        tail = (proc.stdout or proc.stderr or "").strip().splitlines()
        raise Rejection(
            "stage3_external_verifier_refused",
            "verifier.verify_stage3 REFUSED this bundle (exit "
            f"{proc.returncode}). Stage 4 does not admit what Stage 3's own independent "
            "verifier rejects.",
            {"bundle": bundle_dir, "failures": tail[-12:]})

    return PASSED, f"verifier.verify_stage3 exit 0 ({root})"


def admit(bundle_dir: str, *, require_external_verifier: bool = False) -> Stage3Admission:
    """Admit a Stage-3 bundle, or refuse it. Both gates, and neither one alone.

    `require_external_verifier=True` is the DATA-BOUND setting: it refuses a bundle that
    gate 2 has not actually passed. Leave it False only while no real Stage-3 bundle exists,
    and never claim integration-GO on the result.
    """
    # GATE 1 — Stage-4's own restatement. Always. Raises Rejection on any refusal.
    doc, tables = verify_annotation_bundle(bundle_dir)
    gates = ["stage4_restatement"]

    # GATE 2 — Stage-3's own independent verifier.
    ctx = verifier_context()
    if ctx is not None:
        status, detail = run_external_verifier(bundle_dir, ctx, doc["artifact_class"])
        gates.append("verifier.verify_stage3")
    else:
        status = NOT_RUN
        detail = (
            f"no Stage-3 verifier context configured ({ENV_VERIFIER_ROOT}, {ENV_CACHE_ROOT}, "
            f"{ENV_DIRECT_RUN}, {ENV_DIRECT_INPUTS}). verify_stage3 re-derives Stage 3 from "
            "Direct's screen + the acquisition cache, which do not exist until Stage 2 makes "
            "its real run. This bundle is admitted on Stage-4's restatement ALONE — that is "
            "not an integration-GO.")

    if require_external_verifier and status != PASSED:
        raise Rejection(
            "stage3_external_verifier_not_run",
            "a data-bound admission requires verifier.verify_stage3 to have actually passed, "
            f"and it did not run. {detail}")

    return Stage3Admission(
        bundle_dir=bundle_dir,
        bundle_id=doc["bundle_id"],
        document=doc,
        tables=tables,
        external_verifier=status,
        external_verifier_detail=detail,
        gates=tuple(gates),
    )
