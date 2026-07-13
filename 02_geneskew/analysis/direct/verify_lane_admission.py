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

# The producer's honest state, in every lane. It never fills in its own verdict.
PRODUCER_PENDING = "pending_independent_verification"

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
# --------------------------------------------------------------------------- #
# THE DIRECT LANE'S REAL ADMISSION — W1's FLAT, PER-CONDITION BINDING.
#
# I had invented a single `direct_release_admission.json` carrying a nested
# ``binds { w10_report, w10_report_raw_sha256, code_identity(dict), direct_bundle_ids[] }``.
# NO SUCH FILE IS EVER WRITTEN. W1's adapter (`verify_arm_contract`) normalizes W10's native
# report into ONE BINDING PER CONDITION — `direct_admission_<condition>.json` — and every
# field on it is FLAT:
#
#   binding_schema           spot.stage02.direct_admission_binding.v1
#   binding_sha256           sha256 over the body EXCLUDING binding_sha256
#   subject_kind             "bundle"        (it admits a BUNDLE, not a release doc)
#   condition                the bundle's condition
#   bundle_id                == that bundle's arm_bundle_run_id
#   native_verdict           "ADMIT"         (byte-exact)
#   disposition              "admitted"
#   n_failed                 0
#   bundle_verified_on_disk  true
#   verifier_id              spot.stage02.direct.arm_bundle.verifier.v1
#   verifier_code_sha256     the PINNED W10 checkout
#   code_identity            a STRING, not a dict
#
# A lane admitted CONDITION BY CONDITION is admitted only when EVERY condition is: a Direct
# release missing one condition's binding is not a smaller release, it is an unadmitted one.
# --------------------------------------------------------------------------- #
DIRECT_BINDING_PREFIX = "direct_admission_"
DIRECT_BINDING_SCHEMA = "spot.stage02.direct_admission_binding.v1"
DIRECT_VERIFIER_ID = "spot.stage02.direct.arm_bundle.verifier.v1"
DIRECT_SELF_HASH_FIELD = "binding_sha256"
DIRECT_SUBJECT_KIND = "bundle"
DIRECT_BUNDLE_SCHEMA = "spot.stage02_direct_arm_bundle.v1"

NATIVE = {
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
        # THE PATHWAY LANE'S OWN schema. It said `_temporal_` — and this field is what decides
        # which contract a report must satisfy, so the pathway lane was accepting a report
        # that declared itself to be about the temporal lane's bytes.
        "schema_version": "spot.stage02_pathway_arm_external_admission.v1",
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


def adapt_direct(root: str) -> tuple:
    """The Direct lane: W1's FLAT, PER-CONDITION bindings. Every condition, or none.

    W10 admits a BUNDLE at a time, and W1's adapter normalizes each of those native reports
    into one flat `direct_admission_<condition>.json`. So the LANE is admitted only when every
    condition it shipped is — a Direct release missing one condition's binding is not a smaller
    release, it is an unadmitted one.
    """
    import glob

    paths = sorted(glob.glob(os.path.join(root, f"{DIRECT_BINDING_PREFIX}*.json")))
    if not paths:
        return None, [f"[direct] no {DIRECT_BINDING_PREFIX}<condition>.json binding. W1's "
                      "adapter normalizes each of W10's native bundle reports into one flat "
                      "binding per condition; an un-admitted lane is not a release"]

    # WHICH conditions the release actually shipped, from the bundles themselves.
    shipped: dict[str, str] = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if "arm_bundle.json" not in files:
            continue
        try:
            with open(os.path.join(base, "arm_bundle.json")) as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        # the lane, by the bundle's OWN SCHEMA — restated here, never imported: this is a
        # VERIFIER, and a verifier that imports the producer's normalizer agrees with it by
        # construction and could never catch it mis-identifying a lane.
        if doc.get("schema_version") == DIRECT_BUNDLE_SCHEMA:
            shipped[str(doc.get("condition"))] = str(doc.get("arm_bundle_run_id"))

    bad: list[str] = []
    bindings: dict[str, Any] = {}
    for path in paths:
        b = _load(path)
        name = os.path.basename(path)
        if b is None:
            bad.append(f"[direct] {name} is not a readable JSON document")
            continue
        cond = str(b.get("condition"))

        # THE FLAT CONTRACT, field by field. Nothing nested, and `code_identity` is a STRING.
        if b.get("binding_schema") != DIRECT_BINDING_SCHEMA:
            bad.append(f"[direct] {name}: binding_schema {b.get('binding_schema')!r} is not "
                       f"{DIRECT_BINDING_SCHEMA!r}")
        if b.get("subject_kind") != DIRECT_SUBJECT_KIND:
            bad.append(f"[direct] {name}: subject_kind {b.get('subject_kind')!r} — this "
                       "binding admits a BUNDLE, not a release document")
        if b.get("verifier_id") != DIRECT_VERIFIER_ID:
            bad.append(f"[direct] {name}: admitted by {b.get('verifier_id')!r}")
        if b.get("native_verdict") != "ADMIT":
            bad.append(f"[direct] {name}: native verdict {b.get('native_verdict')!r} is not "
                       "the exact token 'ADMIT'")
        if b.get("disposition") != ADMITTED:
            bad.append(f"[direct] {name}: disposition {b.get('disposition')!r}")
        if b.get("n_failed") != 0:
            bad.append(f"[direct] {name}: n_failed={b.get('n_failed')!r}")
        if b.get("bundle_verified_on_disk") is not True:
            bad.append(f"[direct] {name}: the bundle was not verified ON DISK; a report about "
                       "bytes nobody opened is not an admission")
        if not isinstance(b.get("code_identity"), str):
            bad.append(f"[direct] {name}: code_identity is "
                       f"{type(b.get('code_identity')).__name__}, not a string")
        if b.get("self_admitted") is True:
            bad.append(f"[direct] {name}: self_admitted — a bundle that admitted itself was "
                       "never independently admitted")

        # THE SELF-HASH, over the body EXCLUDING it.
        derived = _canon({k: v for k, v in b.items() if k != DIRECT_SELF_HASH_FIELD})
        if b.get(DIRECT_SELF_HASH_FIELD) != derived:
            bad.append(f"[direct] {name}: {DIRECT_SELF_HASH_FIELD} is "
                       f"{str(b.get(DIRECT_SELF_HASH_FIELD))[:16]}; its own content hashes to "
                       f"{derived[:16]}")

        # ...and it must admit a bundle THIS RELEASE ACTUALLY SHIPPED.
        want = shipped.get(cond)
        if want is None:
            bad.append(f"[direct] {name}: admits condition {cond!r}, which this release ships "
                       "no Direct bundle for")
        elif b.get("bundle_id") != want:
            bad.append(f"[direct] {name}: admits bundle {b.get('bundle_id')!r}; the {cond!r} "
                       f"bundle in this release is {want!r}. An admission of another bundle is "
                       "an admission of something else")
        bindings[cond] = b

    # EVERY CONDITION, OR THE LANE IS NOT ADMITTED.
    missing = sorted(set(shipped) - set(bindings))
    if missing:
        bad.append(f"[direct] condition(s) {missing} shipped a bundle and carry NO admission "
                   "binding. A lane admitted condition by condition is admitted only when "
                   "every condition is")

    block = {
        "native_verdict": "ADMIT",
        "native_verifier_id": DIRECT_VERIFIER_ID,
        "native_schema_version": DIRECT_BINDING_SCHEMA,
        "native_self_hash_field": DIRECT_SELF_HASH_FIELD,
        "native_self_hash": {c: b.get(DIRECT_SELF_HASH_FIELD)
                             for c, b in sorted(bindings.items())},
        "aggregate_disposition": ADMITTED if not bad else REFUSED,
        "mapping_rule_id": MAPPING_RULE_ID,
        "transliterated": False,
        "admitted": not bad,
        "self_admitted": False,
        "per_condition": {c: {"bundle_id": b.get("bundle_id"),
                              "code_identity": b.get("code_identity"),
                              "verifier_code_sha256": b.get("verifier_code_sha256")}
                          for c, b in sorted(bindings.items())},
        "producer_release": {},
    }
    return block, bad


def adapt(root: str, lane: str) -> tuple:
    """Re-open the lane's NATIVE admission and type it. ``(admission_block, problems)``."""
    if lane == "direct":
        return adapt_direct(root)

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

    # WHERE THE REPORT CARRIES THEM, the affirmative fields must say so.
    if "admitted" in doc and doc.get("admitted") is not True:
        bad.append(f"[{lane}] admitted={doc.get('admitted')!r}; an independent admission "
                   "says so in the field that means it")
    if "self_admitted" in doc and doc.get("self_admitted") is not False:
        bad.append(f"[{lane}] self_admitted={doc.get('self_admitted')!r} — a release that "
                   "admitted itself was never independently admitted")

    # THE PRODUCER'S RELEASE MUST STILL BE UN-ADMITTED, and this report must be an admission
    # OF IT. The producer never fills its own verdict in — W10 gates exactly that — so an
    # aggregate that found an admitted producer file has found one somebody edited.
    producer_state: dict[str, Any] = {}
    binds = spec.get("binds_producer")
    if binds:
        ppath = os.path.join(root, binds["file"])
        prod = _load(ppath)
        if prod is None:
            bad.append(f"[{lane}] the producer release {binds['file']} is absent or "
                       "unreadable; there is nothing for this report to be about")
        else:
            producer_state = {
                "verdict": prod.get("verdict"),
                "admitted": prod.get("admitted"),
                "self_admitted": prod.get("self_admitted"),
                "verifier_id": prod.get("verifier_id"),
            }
            if (prod.get("admitted") is not False
                    or prod.get("self_admitted") is not False
                    or prod.get("verifier_id") is not None
                    or prod.get("verdict") != PRODUCER_PENDING):
                bad.append(
                    f"[{lane}] the producer's {binds['file']} is not un-admitted "
                    f"(verdict={prod.get('verdict')!r}, admitted={prod.get('admitted')!r}, "
                    f"self_admitted={prod.get('self_admitted')!r}). The producer ships "
                    "PENDING and immutable; a verdict in it is one somebody wrote there")

            want = prod.get(binds["producer_hash_field"])
            got: Any = doc
            for key in binds["report_hash_path"]:
                got = (got or {}).get(key) if isinstance(got, dict) else None
            if got != want:
                bad.append(
                    f"[{lane}] this report admits release {str(got)[:16]}; the producer's "
                    f"release is {str(want)[:16]}. An admission that names another artifact "
                    "is an admission of something else")

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
        # the producer's release, as it still stands: PENDING, and never self-admitted
        "producer_release": producer_state,
    }
    return block, bad
