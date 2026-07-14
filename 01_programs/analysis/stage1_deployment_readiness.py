#!/usr/bin/env python3
"""Derive Stage-1 app/overlay deployment readiness from VERIFIED served-artifact integrity + overlay
fidelity — NEVER from the historical 0/33 LOMO/selectability result.

Policy (authorized repair): the served continuous-score display bundle (v3 registry + UMAP overlay +
summary) is deployment-ready iff its SERVED BYTES match the independently-verified release identity AND
the overlay faithfully equals the full computation (overlay==full, proven by the D-compute recovery
receipt). The frozen within-condition 0/33 selectability outcome is descriptive historical validation
metadata: it is NOT an input here and never blocks displaying continuous scores or generic Stage-2
selection. The overlay REPRESENTATIVENESS gate (composition/distributions/correlations) is likewise a
separate descriptive visualization-quality signal, not a deployment input.

`derive_deployment_readiness` is a PURE function over already-read hashes + the recovery receipt, so it is
unit-testable with no filesystem: a missing or hash-mismatched overlay fails closed, while a 0/33
selectability result (absent from the signature) can never gate it.
"""
from __future__ import annotations

# Frozen v3 display-release identity — the independently-verified served-artifact hashes. Sourced from
# stage2_bridge/release/stage01_v3_release.json (registry raw; overlay coordinates + scores content) and
# the D-compute recovery receipt stage01_v3_recovery_verification.json (scores content, overlay==full).
# The overlay raw sha is the release-frozen served-overlay byte identity. Integrity = SERVED bytes recompute
# to these; a swapped/tampered/missing artifact cannot match and fails closed.
V3_DISPLAY_EXPECTED = {
    "stage01_program_registry_v3.json": {
        "raw_sha256": "bcb536d06d373ab8f2c8e33d73096bd2dc66a62f23a2124a733c1c361c38e664",
    },
    "stage01_umap_overlay_v3.json": {
        "raw_sha256": "1fe05f33112c12af970ab5269ad64b1e0211f09143c991c2be982493c002366b",
        "scores_canonical_content_sha256": "43c4296d5166740c334441a69df23bb440a073382bbe79628a3bb89e43d51316",
        "coordinates_sha256": "c3d3a0a752614470693a0148ba37a45cf20aba290a6e54b4f7fa0bc468a6605b",
    },
    "stage01_summary_v3.json": {
        "raw_sha256": "5e4153bdfa83cc0e77cd2980db024675006124b521b18de4fa970a8ff8bd2b13",
    },
}

REGISTRY = "stage01_program_registry_v3.json"
OVERLAY = "stage01_umap_overlay_v3.json"
SUMMARY = "stage01_summary_v3.json"


def _match(got, want):
    return got is not None and want is not None and got == want


def derive_deployment_readiness(served: dict, receipt: dict | None, expected: dict = V3_DISPLAY_EXPECTED) -> dict:
    """Derive app/overlay deployment readiness. DECOUPLED from selectability (0/33) — it is not a param.

    served: {
      'stage01_program_registry_v3.json': {'present': bool, 'raw_sha256': str|None},
      'stage01_umap_overlay_v3.json':      {'present': bool, 'raw_sha256': str|None,
          'scores_canonical_content_sha256': str|None, 'coordinates_sha256': str|None},
      'stage01_summary_v3.json':           {'present': bool, 'raw_sha256': str|None},
    }
    receipt: parsed stage01_v3_recovery_verification.json (or None).

    Returns a dict of typed booleans + reason_codes. app_deployment_ready is True IFF every served display
    artifact's bytes match the frozen release identity AND the overlay is proven overlay==full.
    """
    integrity_reasons: list[str] = []
    fidelity_reasons: list[str] = []

    def art(name):
        return served.get(name) or {"present": False}

    # ── served-artifact integrity: SERVED bytes recompute to the frozen release identity ──
    reg, ovl, summ = art(REGISTRY), art(OVERLAY), art(SUMMARY)
    if not reg.get("present"):
        integrity_reasons.append("registry_v3_missing")
    elif not _match(reg.get("raw_sha256"), expected[REGISTRY]["raw_sha256"]):
        integrity_reasons.append("registry_v3_raw_sha_mismatch")

    if not ovl.get("present"):
        integrity_reasons.append("overlay_missing")
    else:
        if not _match(ovl.get("raw_sha256"), expected[OVERLAY]["raw_sha256"]):
            integrity_reasons.append("overlay_raw_sha_mismatch")
        if not _match(ovl.get("scores_canonical_content_sha256"), expected[OVERLAY]["scores_canonical_content_sha256"]):
            integrity_reasons.append("overlay_scores_content_sha_mismatch")
        if not _match(ovl.get("coordinates_sha256"), expected[OVERLAY]["coordinates_sha256"]):
            integrity_reasons.append("overlay_coordinates_sha_mismatch")

    if not summ.get("present"):
        integrity_reasons.append("summary_v3_missing")
    elif not _match(summ.get("raw_sha256"), expected[SUMMARY]["raw_sha256"]):
        integrity_reasons.append("summary_v3_raw_sha_mismatch")

    overlay_integrity_ok = not any(r.startswith("overlay_") for r in integrity_reasons)
    served_artifact_integrity_ok = len(integrity_reasons) == 0

    # ── overlay-release fidelity: the served overlay faithfully equals the full computation ──
    r = receipt or {}
    checks = r.get("checks", {}) if isinstance(r, dict) else {}
    if not r.get("all_pass") is True:
        fidelity_reasons.append("recovery_receipt_not_all_pass")
    oef = checks.get("overlay_equals_full", {}) if isinstance(checks, dict) else {}
    if not (oef.get("overlay_eq_full_all_fields") is True and oef.get("mismatches") == 0
            and oef.get("barcodes_all_present") is True):
        fidelity_reasons.append("overlay_equals_full_unproven")
    scc = checks.get("scores_canonical_content_sha256", {}) if isinstance(checks, dict) else {}
    if scc.get("match") is not True:
        fidelity_reasons.append("scores_canonical_content_unverified")

    overlay_release_fidelity_ok = len(fidelity_reasons) == 0
    overlay_release_ok = bool(overlay_integrity_ok and overlay_release_fidelity_ok)
    app_deployment_ready = bool(served_artifact_integrity_ok and overlay_release_fidelity_ok)

    return {
        "served_artifact_integrity_ok": served_artifact_integrity_ok,
        "overlay_release_fidelity_ok": overlay_release_fidelity_ok,
        "overlay_release_ok": overlay_release_ok,
        "app_deployment_ready": app_deployment_ready,
        "integrity_reason_codes": integrity_reasons,
        "fidelity_reason_codes": fidelity_reasons,
        "derivation": ("app_deployment_ready = served_artifact_integrity_ok AND overlay_release_fidelity_ok; "
                       "DECOUPLED from the frozen historical within-condition selectability outcome (never an input)."),
    }
