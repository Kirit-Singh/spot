"""``temporal_preflight.json`` — the PRODUCER's own self-check. NEVER an admission.

THE TRUST BOUNDARY, WRITTEN DOWN
-------------------------------
A producer may not be the independent witness for code it invoked itself. So the producer's
re-derivation of its own shipped bytes is recorded here as a PREFLIGHT — a
``producer_preflight`` with a status, and nothing more. It carries:

  * NO ``verdict: admit`` — a preflight is not an admission;
  * NOT the independent verifier's identity — it is signed as the producer's own preflight;
  * ``generator_is_not_verifier = false`` — stated plainly, because the generator DID run
    it, and claiming otherwise is the exact self-witnessing this boundary exists to stop;
  * ``status = pending_external_verification`` — the authoritative admission is
    ``temporal_verification.json``, written SEPARATELY by the independent verifier (W11)
    after it reopens these bytes.

It exists for transparency — a reader can see the producer checked its own work and see that
that check is explicitly not the admission — not to satisfy any downstream gate.
"""
from __future__ import annotations

from typing import Any

# The identity of the INDEPENDENT verifier the preflight defers to — a POINTER, so a reader
# knows where the real admission lives, not a claim the producer is that verifier.
from .arm_report import SCHEMA_VERIFICATION, VERIFIER_ID

SCHEMA_PREFLIGHT = "spot.stage02_temporal_arm_producer_preflight.v1"
PREFLIGHT_ID = "spot.stage02.temporal.arm.producer_preflight.v1"
STATUS_PENDING = "pending_external_verification"


def build_preflight(result: dict[str, Any], *, bundle_id: str,
                    arm_bundle_sha256: str) -> dict[str, Any]:
    """The producer's self-check over a ``verify_shipped`` result. A status, never a verdict.

    ``result`` is the producer's own re-derivation. This records WHICH gates it ran and
    whether they passed, binds the bytes it checked, and points at the independent verifier
    for the authoritative admission — without ever calling itself admitted.
    """
    checks = list(result.get("checks") or [])
    failed = [c["gate"] for c in checks if c.get("status") != "pass"]
    return {
        "schema_version": SCHEMA_PREFLIGHT,
        "preflight_id": PREFLIGHT_ID,
        "role": "producer_preflight",
        # a STATUS, not a verdict. Even a clean self-check stays pending until W11 admits.
        "status": STATUS_PENDING,
        "self_check_passed": not failed,
        # the producer ran this; it does not get to declare independence
        "generator_is_not_verifier": False,
        "is_admission": False,
        "n_gates_checked": len(checks),
        "n_failed": len(failed),
        "failed_gates": failed,
        "checks": checks,
        "bundle_id": bundle_id,
        "self_checked": {"arm_bundle_sha256": arm_bundle_sha256},
        # WHERE the authoritative admission will live, and WHO signs it
        "authoritative_verification": {
            "verifier_id": VERIFIER_ID,
            "schema_version": SCHEMA_VERIFICATION,
            "file": "temporal_verification.json",
            "written_by": "independent_verifier",
        },
    }
