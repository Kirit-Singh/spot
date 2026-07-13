"""THE INVOCATION CONTRACT for the aggregate verifier, and the ZERO-COMPUTE DRY RUN.

W7 consumes this. Split out of ``verify_run_manifest`` for size; imports nothing from the
producer.
"""
from __future__ import annotations

import os
from typing import Any

VERIFIER_ID = "spot.stage02.run_manifest.verifier.v1"

# --------------------------------------------------------------------------- #
# THE INVOCATION CONTRACT (W7 consumes this) + the ZERO-COMPUTE DRY RUN.
#
# The production wrapper omitted --release and --release-root, and tried to bind ONE generic
# verifier report across Direct, temporal and pathway. Neither is possible: the release is
# what DEFINES the expected topology, and an external admission is an admission OF ONE LANE'S
# RELEASE — a single report cannot say which lane it admitted.
#
# So every input is REQUIRED and EXPLICIT. There are no defaults and no guessed paths: a path
# the verifier inferred is a path nobody agreed to, and it is exactly how a run ends up
# admitted against the wrong release root.
# --------------------------------------------------------------------------- #
REQUIRED_INPUTS = (
    ("manifest", "the aggregate run manifest under test"),
    ("bundles_root", "the root the bundles were emitted under"),
    ("release", "the authoritative Stage-1 v3 release"),
    ("release_root", "the directory the release is STAGED in"),
    ("expect_release_sha256", "the independently pinned canonical release hash"),
    ("expect_gene_sets", "the pinned gene-set source identities"),
    ("expect_verifiers", "the pinned per-lane verifier ids + gate inventories"),
    ("expected_code_identity", "the independently pinned build"),
    ("release_inventory_root", "the content-addressed root: inventory + external admission"),
    ("env_lock", "the committed Stage-2 environment lock"),
    ("expect_env_lock_sha256",
     "the independently pinned sha256 of the AUTHORITATIVE Stage-2 solver lock"),
)

# The lock every lane must bind. Supplied as an input, never hardcoded into a gate — but
# named here so an invocation that pins the wrong one is visible in the contract W7 reads.
AUTHORITATIVE_LOCK_NOTE = (
    "every lane (Direct, temporal, pathway) binds the SAME authoritative solver lock; a "
    "lane that bound a different one was solved in a different environment and is a "
    "different run")


def invocation_contract() -> dict[str, Any]:
    """WHAT W7 must pass. Machine-readable; no path is ever inferred."""
    return {
        "command": "python -m direct.verify_run_manifest",
        "verifier_id": VERIFIER_ID,
        "required_arguments": [f"--{name.replace('_', '-')}" for name, _ in
                               REQUIRED_INPUTS],
        "argument_meanings": {f"--{n.replace('_', '-')}": why
                              for n, why in REQUIRED_INPUTS},
        "authoritative_env_lock": AUTHORITATIVE_LOCK_NOTE,
        "implicit_paths_permitted": False,
        "one_generic_report_across_lanes_permitted": False,
        "external_admission_is_per_lane_release": True,
        "dry_run": {"flag": "--dry-run", "reads_bundles": False,
                    "exit_0_iff": "every required input is present and readable"},
        "expected_exit_codes": {"0": "ADMIT", "1": "REJECT or missing input"},
    }


def dry_run(args) -> dict[str, Any]:
    """Resolve every required input. Read NO bundle. Compute NOTHING."""
    missing, unreadable = [], []
    for name, _why in REQUIRED_INPUTS:
        value = getattr(args, name, None)
        if not value:
            missing.append(f"--{name.replace('_', '-')}")
            continue
        if name in ("expect_release_sha256", "expect_env_lock_sha256"):
            continue
        if not os.path.exists(value):
            unreadable.append(f"--{name.replace('_', '-')}={value}")
    return {
        "mode": "dry_run",
        "reads_bundles": False,
        "contract": invocation_contract(),
        "missing_arguments": missing,
        "unreadable_paths": unreadable,
        "ready": not missing and not unreadable,
    }


