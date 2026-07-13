"""WHAT THE BUNDLE SHIPS: the native file set, the artifact manifest, and the empty verdict.

These names are the INTERFACE — what W3 reads and what an independent verifier reads back off
disk — not an implementation detail of the producer that happens to write them. They live in
one module so that "the file set" is a thing with a definition, rather than a list of string
literals scattered through a build function.

`verification.json` is written as a PLACEHOLDER and nothing else. A generator that admits its
own output is not a gate; it is the same process asserting twice.
"""
from __future__ import annotations

import os
from typing import Any

from .hashing import file_sha256

SCHEMA_VERIFICATION = "spot.stage02_arm_bundle_verification.v1"

ROWS_FILE = "arms.parquet"
MASKS_FILE = "masks.parquet"
CONTRIB_FILE = "contributing_guides.parquet"
GUIDE_SUPPORT_FILE = "guide_support.parquet"
DONOR_SUPPORT_FILE = "donor_support.parquet"
INPUTS_FILE = "input_manifest.json"
UNIVERSE_FILE = "gene_universe.json"
BUNDLE_FILE = "arm_bundle.json"
PROVENANCE_FILE = "provenance.json"
VERIFICATION_FILE = "verification.json"

VERDICT_PENDING = "pending_independent_verification"

# Everything an independent verifier is expected to read back off disk.
VERIFIED_PATHS = (BUNDLE_FILE, PROVENANCE_FILE, ROWS_FILE, MASKS_FILE, CONTRIB_FILE,
                  GUIDE_SUPPORT_FILE, DONOR_SUPPORT_FILE, INPUTS_FILE, UNIVERSE_FILE)


def artifact_manifest(out_dir: str) -> list[dict[str, Any]]:
    """Every file this bundle shipped, by RELATIVE name and raw hash.

    Relative, always: a machine-local path in an artifact is a citation nobody else can
    follow, and it would make the same science produced on two hosts cite two different
    bundles. `verification.json` is excluded — it is the one file the producer does not own.
    """
    return sorted(
        [{"name": name, "size_bytes": os.path.getsize(os.path.join(out_dir, name)),
          "raw_sha256": file_sha256(os.path.join(out_dir, name))}
         for name in os.listdir(out_dir) if name != VERIFICATION_FILE],
        key=lambda e: e["name"])


def verification_placeholder(bundle_run_id: str, doc: dict[str, Any],
                             produced_by: str) -> dict[str, Any]:
    """NOT a verdict. The slot an INDEPENDENT verifier fills, and the producer never does.

    It ships un-admitted, names no verifier, and states the files a verifier must read back
    off disk. Whoever replaces it must be code that did not produce these bytes.
    """
    return {
        "schema_version": SCHEMA_VERIFICATION,
        "arm_bundle_run_id": bundle_run_id,
        "verifier_id": None,
        "verdict": VERDICT_PENDING,
        "admitted": False,
        "self_admitted": False,
        # W18's explicit declarations, kept: an artifact with no verification file at all is
        # indistinguishable from one whose verifier never ran, and a downstream reader would
        # have to guess which. These say it out loud.
        "generator_is_not_verifier": True,
        "fail_closed": True,
        "produced_by": produced_by,
        "verified_paths": list(VERIFIED_PATHS),
        # what a verifier is expected to re-derive, stated by the producer as a CLAIM — never
        # as evidence that it holds
        "arm_rows_sha256": doc["arm_rows_sha256"],
        "n_expected_arm_slots": doc["n_expected_arm_slots"],
        "n_arm_slots": doc["n_arm_slots"],
        "n_arm_rows": doc["n_arm_rows"],
    }
