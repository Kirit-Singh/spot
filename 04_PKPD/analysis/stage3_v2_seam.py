"""The Stage-3 v2 admission seam — deliberately UNPINNED, and therefore deliberately CLOSED.

W16 is still writing `spot.stage03_drug_annotation.v2`. Stage 4 does not know its fields, and this
module exists to make sure Stage 4 never PRETENDS to.

The failure this prevents is specific and quiet. Stage 4's v1 reader (`stage3_contract_v2.py`,
pinned to `spot.stage03_drug_annotation.v1/2026-07-12-r8`) checks the schema id, then reads the
tables it knows. Hand it a v2 bundle and one of two things happens, both bad:

  * it refuses with a confusing low-level error about a missing column, which reads like a broken
    bundle rather than an unimplemented contract; or worse
  * a v2 bundle that happens to carry the v1 column names is READ AS V1 — its new fields silently
    ignored, its new origin vocabulary silently dropped, its evidence admitted under a contract
    nobody checked it against. Every downstream hash would be self-consistent, and every one would
    be a hash of a misreading.

The second is the reason this file is not just documentation. A contract Stage 4 cannot verify is
not a contract Stage 4 may admit, and "it parsed" is not "it was verified".

WHAT UNBLOCKS IT — exactly two things, from W16:

  1. the final **schema-set sha256** for the v2 contract, and
  2. a real `spot.stage03_drug_annotation.v2` bundle that Stage 3's OWN independent verifier has
     admitted (gate 2), not merely emitted.

Then `STAGE3_V2_SCHEMA_SET_SHA256` below is set in ONE deliberate edit, the v2 adapter is written
against the fields W16 actually published, and the literal chain — acquire -> materialize ->
verify_bundle -> run_stage4 -> verify_stage4 — is run against the real v2 output. Until all of
that, a v2 bundle is refused BY NAME.

**A fixture-only v1 green is not completion.** The chain runs today on the frozen v1 annotation
fixture. That proves the plumbing, not the science.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from .firewall import Rejection

STAGE3_V2_SCHEMA = "spot.stage03_drug_annotation.v2"

# ─── THE PIN ────────────────────────────────────────────────────────────────────────────────
#
# None means UNPINNED, which means CLOSED. This is the single line that changes when W16 reports
# the final hash — deliberately one line, so re-pinning is an act, not an accident.
#
# It is NOT a guess and must never be filled in with a locally computed hash: the whole point of a
# pin is that it was published by the producer and independently verified. A hash Stage 4 computed
# for itself pins nothing.
STAGE3_V2_SCHEMA_SET_SHA256: Optional[str] = None

# What Stage 4 will CHECK once the pin lands. Published here so W16 can build against a stated
# interface instead of guessing what Stage 4 needs — the mirror image of Stage 4 not guessing what
# W16 is writing.
#
# These are requirements on the CONTRACT, not claims about its fields. Stage 4 does not know the
# v2 field names and has not invented any.
STAGE4_REQUIRES_OF_V2 = (
    "schema_version == spot.stage03_drug_annotation.v2, stated in the document",
    "artifact_class == analysis  (a fixture bundle is synthetic and never reaches Stage 4)",
    "a published schema-set sha256 that Stage 4 re-derives from the bundle's own bytes",
    "gate 2: Stage 3's own verifier.verify_stage3 has PASSED out-of-process on this bundle",
    "an immutable candidate identifier per candidate, stable across the whole chain",
    "per-source provenance: locator, license/terms, raw_sha256, and the source's own release",
    "an explicit typed ORIGIN per lever, so a MEASURED and an INFERRED origin are never fused",
    "explicit missingness: a lane Stage 3 did not evaluate says so, rather than arriving empty",
    "NO combined objective, NO p/q value, NO rank — Stage 4 refuses a bundle carrying one",
)


class Stage3V2NotAdmissible(Rejection):
    """A v2 bundle arrived before the v2 contract was pinned. Refused, never guessed at."""


def is_v2_bundle(bundle_dir: str) -> bool:
    """Does this bundle DECLARE the v2 contract? Read the declaration; infer nothing."""
    for name in ("drug_annotation.json", "manifest.json"):
        path = os.path.join(bundle_dir, name)
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        declared = str(doc.get("schema_version") or doc.get("schema_id") or "")
        if declared.startswith(STAGE3_V2_SCHEMA):
            return True
    return False


def assert_v2_admissible(bundle_dir: str, *, schema_set_sha256: Optional[str] = None) -> None:
    """The gate. While the contract is unpinned, a v2 bundle is REFUSED — by name, and loudly.

    This is called at every door BEFORE the v1 reader sees the bundle, so a v2 document can never
    be read under the v1 contract by accident. Being refused for the right reason is a
    prerequisite for being admitted for the right reason.
    """
    if not is_v2_bundle(bundle_dir):
        return

    if STAGE3_V2_SCHEMA_SET_SHA256 is None:
        raise Stage3V2NotAdmissible(
            "stage3_v2_contract_not_pinned",
            f"this bundle declares {STAGE3_V2_SCHEMA}, and Stage 4 has not pinned that contract. "
            "It is NOT read under the v1 contract: a v2 document parsed by a v1 reader would have "
            "its new fields silently ignored and its evidence admitted against a contract nobody "
            "checked it against, and every downstream hash would be a self-consistent hash of a "
            "misreading. W16 must publish the final schema-set sha256 and a bundle its own "
            "verifier has admitted; Stage 4 then re-pins deliberately "
            "(analysis/stage3_v2_seam.py :: STAGE3_V2_SCHEMA_SET_SHA256) and writes the v2 "
            f"adapter against the fields W16 actually published. Stage 4 requires: "
            f"{'; '.join(STAGE4_REQUIRES_OF_V2)}",
        )

    if schema_set_sha256 is None:
        raise Stage3V2NotAdmissible(
            "stage3_v2_schema_set_not_supplied",
            "the v2 contract is pinned, but this bundle supplies no schema-set sha256 to check "
            "the pin against. A pin nothing is compared to is decoration.",
        )

    if schema_set_sha256 != STAGE3_V2_SCHEMA_SET_SHA256:
        raise Stage3V2NotAdmissible(
            "stage3_v2_schema_set_mismatch",
            f"this bundle's schema set hashes to {schema_set_sha256[:16]}…, and Stage 4 is pinned "
            f"to {STAGE3_V2_SCHEMA_SET_SHA256[:16]}…. The contract Stage 4 verified is not the "
            "contract that produced this bundle. Re-pinning is a deliberate act after re-reading "
            "the handoff — never a silent widening to accept whatever arrived.",
        )


def seam_status() -> dict[str, Any]:
    """What an orchestrator (or W1/W16) can read to see exactly where the seam stands."""
    return {
        "stage3_v2_schema": STAGE3_V2_SCHEMA,
        "pinned": STAGE3_V2_SCHEMA_SET_SHA256 is not None,
        "schema_set_sha256": STAGE3_V2_SCHEMA_SET_SHA256,
        "state": ("CLOSED — awaiting W16's final schema-set hash and an externally admitted v2 "
                  "bundle" if STAGE3_V2_SCHEMA_SET_SHA256 is None else "PINNED"),
        "stage4_requires": list(STAGE4_REQUIRES_OF_V2),
        "v1_unaffected": "spot.stage03_drug_annotation.v1/2026-07-12-r8 remains admitted and frozen",
    }
