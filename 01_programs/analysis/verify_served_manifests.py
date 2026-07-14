#!/usr/bin/env python3
"""Served-manifest consistency verifier (release-state contradiction gate).

A packaging audit found a Stage-1 release-state CONTRADICTION: the Stage-1 gate manifest
(stage01_release_manifest.json) declares the app/overlay NOT ready (app_deployment_ready=false,
overlay_release_ok=false), while a served deployment manifest (app/release_manifest.json) declares the
same app DEPLOYED (a `release` id serving built page/assets). A served release cannot simultaneously be
"deployed" and "gated-not-ready".

This verifier reads the deployment state each served manifest DECLARES and refuses a contradictory pair.
It is decoupled from the retired 0-of-33 production gate: the frozen within-condition validation is a
HISTORICAL outcome (active_gate:false) and never a deployment-state input.

generator != verifier: this file re-derives the deployment signal directly from the manifests; it never
trusts a self-declared "consistent" flag.
"""
from __future__ import annotations

import json
import os
import sys


def declared_deployed(manifest: dict):
    """The deployment state a served manifest DECLARES, or None if it carries no deployment signal.

    - a Stage-1 GATE manifest (``release_gates`` / ``release_statuses``): deployed iff
      ``app_deployment_ready`` is true AND ``overlay_release_ok`` is not false.
    - a DEPLOYMENT manifest: a ``release`` id that serves built Stage-1 app files (class ``built``).
    """
    for key in ("release_gates", "release_statuses"):
        g = manifest.get(key)
        if isinstance(g, dict) and "app_deployment_ready" in g:
            return bool(g.get("app_deployment_ready")) and (g.get("overlay_release_ok") is not False)
    if manifest.get("release") and isinstance(manifest.get("files"), list):
        if any(isinstance(f, dict) and f.get("class") == "built" for f in manifest["files"]):
            return True
    return None


def contradictory_served_manifests(m1: dict, m2: dict):
    """Return a reason string if two served manifests disagree on the deployment state, else None."""
    d1, d2 = declared_deployed(m1), declared_deployed(m2)
    if d1 is not None and d2 is not None and d1 != d2:
        return (f"served-manifest deployment-state contradiction: manifest-1 declares deployed={d1}, "
                f"manifest-2 declares deployed={d2} — a served release cannot be both deployed and "
                f"gated-not-ready. Reconcile the gate and the deployment manifest before release.")
    return None


def check_paths(*paths: str):
    """Load each manifest path (skipping absent ones) and pairwise-check for a deployment contradiction.
    Returns (ok, reasons)."""
    loaded = [(p, json.load(open(p))) for p in paths if os.path.exists(p)]
    reasons = []
    for i in range(len(loaded)):
        for j in range(i + 1, len(loaded)):
            r = contradictory_served_manifests(loaded[i][1], loaded[j][1])
            if r:
                reasons.append(f"{os.path.basename(loaded[i][0])} vs {os.path.basename(loaded[j][0])}: {r}")
    return (len(reasons) == 0), reasons


if __name__ == "__main__":
    # default: cross-check the served Stage-1 gate manifest against the deployment manifest, if present
    HERE = os.path.dirname(os.path.abspath(__file__))
    APP = os.path.join(HERE, "..", "app")
    default = [os.path.join(APP, "data", "stage01_release_manifest.json"),
               os.path.join(APP, "data", "stage01_current.json"),
               os.path.join(APP, "release_manifest.json")]
    args = sys.argv[1:] or default
    ok, reasons = check_paths(*args)
    print("SERVED-MANIFEST CONSISTENCY:", "OK" if ok else "CONTRADICTION")
    for r in reasons:
        print("  -", r)
    sys.exit(0 if ok else 1)
