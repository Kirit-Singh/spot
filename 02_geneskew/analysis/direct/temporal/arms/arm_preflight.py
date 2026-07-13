"""``temporal_preflight.json`` — the PRODUCER's own self-check. NEVER an independent ADMIT.

THE TRUST BOUNDARY, WRITTEN DOWN (sealed cross-check a12f7eee, §A)
----------------------------------------------------------------
A producer may not be the independent witness for code it invoked itself. So the producer's
re-derivation of its own shipped bytes is recorded here as a PRODUCER PREFLIGHT, and its
identity says so:

  * ``schema_version = spot.stage02_temporal_arm_preflight.v1``;
  * ``verifier_id = spot.stage02.temporal.arm.producer_preflight.v1`` — the PRODUCER's own
    id, never W11's independent-verifier id;
  * ``status`` is ``pass`` or ``fail`` — NOT an ``admit``, and not a "pending" verdict;
  * ``generator_is_not_verifier = false`` — stated plainly, because the generator DID run
    it, and claiming otherwise is the exact self-witnessing this boundary exists to stop;
  * ``binds`` records the bundle, provenance and ranking hashes it self-checked.

There is deliberately NO ``role`` key: that word is reserved (selection metadata / provenance
input naming), and a generic ``role`` has no place in a positive self-report. The
authoritative admission is the INDEPENDENT verifier's (W11's), emitted separately; this file
only shows the producer checked its own work, and shows that that check is not the admission.
"""
from __future__ import annotations

from typing import Any

# The identity of the INDEPENDENT verifier the preflight defers to — a POINTER, so a reader
# knows where the real admission lives, not a claim the producer is that verifier.
from .arm_report import EXTERNAL_ADMISSION_SCHEMA, VERIFIER_ID

SCHEMA_PREFLIGHT = "spot.stage02_temporal_arm_preflight.v1"
PREFLIGHT_VERIFIER_ID = "spot.stage02.temporal.arm.producer_preflight.v1"
STATUS_PASS = "pass"
STATUS_FAIL = "fail"


def _ranking_binds(bundle: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Each arm's ranking hash, by arm key — the bytes the self-check stood on."""
    return {a["arm_key"]: dict(a["ranking"]) for a in bundle.get("arms", [])}


def build_preflight(result: dict[str, Any], *, bundle: dict[str, Any],
                    arm_bundle_sha256: str, provenance_sha256: str) -> dict[str, Any]:
    """The producer's self-check over a ``verify_shipped`` result. A status, never a verdict.

    Binds the bundle, provenance and ranking hashes it checked, records WHICH gates ran and
    whether they passed as ``status = pass|fail``, and points at the INDEPENDENT external
    admission for the authoritative verdict — without ever calling itself admitted.
    """
    checks = list(result.get("checks") or [])
    failed = [c["gate"] for c in checks if c.get("status") != "pass"]
    return {
        "schema_version": SCHEMA_PREFLIGHT,
        "verifier_id": PREFLIGHT_VERIFIER_ID,
        # a STATUS, pass|fail — never an admit, never a pending verdict.
        "status": STATUS_PASS if not failed else STATUS_FAIL,
        # the producer ran this; it does not get to declare independence
        "generator_is_not_verifier": False,
        "is_admission": False,
        "n_gates_checked": len(checks),
        "n_failed": len(failed),
        "failed_gates": failed,
        "checks": checks,
        "bundle_id": bundle["bundle_id"],
        # BINDS the bytes it self-checked: bundle, provenance and every ranking hash
        "binds": {
            "arm_bundle_sha256": arm_bundle_sha256,
            "provenance_sha256": provenance_sha256,
            "rankings": _ranking_binds(bundle),
        },
        # WHERE the authoritative admission will live, and WHO signs it (the independent
        # verifier's root envelope — NOT a per-bundle producer report)
        "external_admission_requirement": {
            "required_verifier_id": VERIFIER_ID,
            "required_report_schema_version": EXTERNAL_ADMISSION_SCHEMA,
            "scope": "root_release",
        },
    }
