"""THE TYPED LANE-ADMISSION ADAPTER. W10 says ``ADMIT``; the aggregate says ``admitted``.

Two vocabularies, and NEITHER is wrong. W10's independent verifier emits the exact native
token ``"ADMIT"`` (uppercase) in an already-admitted contract; the aggregate's canonical
disposition vocabulary is lowercase. The temptation is to call ``.upper()`` somewhere and
declare the problem solved — and this module exists because that is not a solution, it is a
guess wearing a cast.

WHY A CASE-FOLD IS A BUG, NOT A CONVENIENCE
-------------------------------------------
``str(verdict).upper() == "ADMIT"`` accepts ``admit``, ``Admit``, ``aDmIt`` and any other
spelling a future producer, a hand-edit or a broken serialiser might emit. It cannot tell a
native ``ADMIT`` from a lane that drifted, and it silently ADMITS the drift. The whole point
of a content-addressed admission is that it says exactly one thing; a reader that normalises
the string first has thrown away the only evidence it had.

(This verifier itself did exactly that: ``verify_release_envelope`` compared
``str(doc.get("verdict")).upper()``. It has been removed.)

SO: NO TRANSLITERATION. The native token is compared BYTE FOR BYTE, and it is CARRIED
VERBATIM into the aggregate alongside the aggregate's own disposition. Both are bound into
the manifest's content hash, so a reader can always see what the lane actually said and what
the aggregate made of it — and the mapping between them is explicit, typed, and total:
an unknown native token maps to NOTHING and REFUSES. It never defaults.

W10's contract is NOT changed. This adapter reads it as it is.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

MAPPING_RULE_ID = "spot.stage02.run_manifest.lane_admission_map.v1"

# THE AGGREGATE'S canonical dispositions.
ADMITTED = "admitted"
REFUSED = "refused"

# --------------------------------------------------------------------------- #
# EACH LANE'S NATIVE ADMISSION, EXACTLY AS THAT LANE SHIPS IT.
#
# `admit_token` is BYTE-EXACT. `self_hash_excludes` are the fields the independent verifier
# FILLS IN after the producer shipped un-admitted — they are excluded from the artifact's own
# content hash precisely so that admitting it does not change what it is.
# --------------------------------------------------------------------------- #
NATIVE = {
    "direct": {
        "file": "direct_release.json",
        "schema_version": "spot.stage02_direct_release.v1",
        "verifier_id": "spot.stage02.direct.release.verifier.v1",
        "admit_token": "ADMIT",
        "self_hash_field": "direct_release_sha256",
        "self_hash_excludes": ("direct_release_sha256", "direct_release_run_id",
                               "verdict", "admitted", "self_admitted", "verifier_id"),
    },
    "temporal": {
        "file": "temporal_arm_external_admission.json",
        "schema_version": "spot.stage02_temporal_arm_external_admission.v1",
        "verifier_id": "spot.stage02.temporal.arm.independent_verifier.v1",
        "admit_token": "ADMIT",
        "self_hash_field": "report_id",
        "self_hash_excludes": ("report_id",),
    },
    "pathway": {
        "file": "pathway_arm_external_admission.json",
        "schema_version": "spot.stage02_temporal_arm_external_admission.v1",
        "verifier_id": "spot.stage02.pathway.arm.independent_verifier.v1",
        "admit_token": "ADMIT",
        "self_hash_field": "report_id",
        "self_hash_excludes": ("report_id",),
    },
}

# THE MAPPING. Total over the tokens it knows, and CLOSED: anything else refuses.
NATIVE_TO_DISPOSITION = {"ADMIT": ADMITTED, "REFUSE": REFUSED, "REJECT": REFUSED}


def _canon(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode()).hexdigest()


def _load(path: str) -> Optional[dict]:
    try:
        with open(path) as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def disposition_of(native_verdict: Any) -> Optional[str]:
    """The aggregate's disposition for a NATIVE token. No folding, no defaulting.

    ``"admit"`` is not ``"ADMIT"``. A token this map does not hold returns None, and the
    caller REFUSES — because a verdict nobody can read is not a verdict anybody may act on.
    """
    if not isinstance(native_verdict, str):
        return None
    return NATIVE_TO_DISPOSITION.get(native_verdict)      # EXACT key. Never .upper().


def adapt(root: str, lane: str) -> tuple:
    """Re-open the lane's NATIVE admission and type it. ``(admission_block, problems)``."""
    spec = NATIVE.get(lane)
    if spec is None:
        return None, [f"{lane}: no native admission contract is known for this lane"]

    path = os.path.join(root, spec["file"])
    if not os.path.exists(path):
        return None, [f"[{lane}] no independent admission at {spec['file']}: the producer "
                      "ships un-admitted, and an un-admitted release is not a release"]
    doc = _load(path)
    if doc is None:
        return None, [f"[{lane}] {spec['file']} is not a readable JSON document"]

    bad: list[str] = []
    if doc.get("schema_version") != spec["schema_version"]:
        bad.append(f"[{lane}] schema {doc.get('schema_version')!r} is not "
                   f"{spec['schema_version']!r}")
    if doc.get("verifier_id") != spec["verifier_id"]:
        bad.append(f"[{lane}] admitted by {doc.get('verifier_id')!r}; the native "
                   f"independent verifier is {spec['verifier_id']!r}")

    # THE VERDICT, BYTE FOR BYTE. No case folding: `admit` is not `ADMIT`.
    native = doc.get("verdict")
    disposition = disposition_of(native)
    if native != spec["admit_token"]:
        bad.append(
            f"[{lane}] native verdict is {native!r}; this lane's admission token is "
            f"{spec['admit_token']!r}, byte for byte. A verdict that has to be normalised "
            "before it can be read is a verdict nobody can rely on")
    elif disposition != ADMITTED:
        bad.append(f"[{lane}] native verdict {native!r} does not map to {ADMITTED!r}")

    # THE PRODUCER DID NOT ADMIT ITSELF. `admitted` is the independent verifier's to set.
    if doc.get("admitted") is not True:
        bad.append(f"[{lane}] admitted={doc.get('admitted')!r}; an independent admission "
                   "says so in the field that means it")
    if doc.get("self_admitted") is not False:
        bad.append(f"[{lane}] self_admitted={doc.get('self_admitted')!r} — a release that "
                   "admitted itself was never independently admitted")

    # THE BOUND HASH. Recomputed over the body the verifier did NOT fill in, so admitting an
    # artifact cannot change what that artifact IS.
    field = spec["self_hash_field"]
    claimed = doc.get(field)
    derived = _canon({k: v for k, v in doc.items()
                      if k not in spec["self_hash_excludes"]})
    if claimed != derived:
        bad.append(f"[{lane}] {field} is {str(claimed)[:16]}; its own content hashes to "
                   f"{derived[:16]}")

    block = {
        # VERBATIM. The lane said this, and the aggregate does not rewrite it.
        "native_verdict": native,
        "native_verifier_id": doc.get("verifier_id"),
        "native_schema_version": doc.get("schema_version"),
        "native_self_hash_field": field,
        "native_self_hash": claimed,
        # ...and what the aggregate makes of it, in the aggregate's own vocabulary.
        "aggregate_disposition": disposition,
        "mapping_rule_id": MAPPING_RULE_ID,
        "transliterated": False,
        "admitted": doc.get("admitted"),
        "self_admitted": doc.get("self_admitted"),
    }
    return block, bad
