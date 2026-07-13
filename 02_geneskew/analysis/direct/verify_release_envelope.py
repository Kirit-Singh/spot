"""THE PRODUCER INVENTORY and the EXTERNAL ADMISSION ENVELOPE, verified independently.

Reimplemented from the sealed cross-check ``TEMPORAL_STAGE2_STAGE3_CONTRACT_CROSSCHECK``
(sha256 ``a12f7eee0bcb32c523507f8a92d265fec4b9dfdcfe87fa0cd15431a00e3ca7a2``), sections A
and C. Imports NOTHING from the producer.

WHY THIS EXISTS
---------------
An adversarial probe walked a clean 15-bundle run past the aggregate with ZERO producer
inventories and ZERO external admissions, and it was ADMITTED. The per-bundle
``temporal_verification.json`` looked like an independent report — but the PRODUCER writes
it, and signs it with the independent verifier's id. Every field in it is a field the
producer chose. A file cannot testify that some other process made it.

So the admission of a temporal release rests on TWO artifacts that are NOT the producer's
per-bundle self-check, and the aggregate REQUIRES BOTH:

  1. the PRODUCER INVENTORY (``temporal_arm_release.json``) — immutable, content-addressed,
     naming all six bundles and every byte they stand on. Its ``external_admission.status``
     is ``pending``: that is the ONLY honest producer state, and it may never say ``admit``;

  2. the EXTERNAL ADMISSION ENVELOPE — emitted by the INDEPENDENT verifier alone, after it
     reconstructs all six bundles itself, and BOUND to that exact inventory by
     ``release_id`` and raw hash. An envelope that admits a DIFFERENT release is an
     admission of something else.

A manifest missing either is REJECTED. The producer's preflight, alone, admits nothing.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

# --------------------------------------------------------------------------- #
# THE ONE CANONICAL EXTERNAL-ADMISSION ARTIFACT (W3 <-> W11 reconciliation).
#
# W11 was emitting a root ``temporal_verification.json`` with a 16-hex ``envelope_id`` and
# ``binds.inventory_raw_sha256``. Three problems, and a rename fixes none of them:
#
#   * THE FILENAME COLLIDES. ``temporal_verification.json`` already means "this bundle's
#     verification", inside every bundle. The same name at the root, holding a different
#     schema, is a name that means two things — and a reader that globs for it gets both.
#   * A 16-HEX CONTENT ADDRESS. This id is what makes the admission immutable. Truncating
#     it to 64 bits to look tidy is halving the collision resistance of the one field that
#     stops an admission being swapped, for nothing.
#   * THE WRONG BINDING. ``inventory_raw_sha256`` says which FILE was read.
#     ``producer_release_raw_sha256`` says which RELEASE was admitted. W3 must verify the
#     admission is over the ACTUAL W5 release, so the release identity is REQUIRED; the
#     inventory hash is accepted alongside it and must agree.
# --------------------------------------------------------------------------- #
# PER-LANE root artifacts. Each lane's release is admitted by ITS OWN independent verifier:
# an admission is an admission OF ONE LANE'S RELEASE, and one generic report cannot say
# which lane it admitted.
# EVERY lane: an IMMUTABLE pending inventory + a SEPARATE independent admission report.
# The producer never fills in its own verdict — W10 gates exactly that.
INVENTORY_FILE_OF = {
    "direct": "direct_release.json",
    "temporal": "temporal_arm_release.json",
    "pathway": "pathway_arm_release.json",
}
# Direct's inventory carries W10's own pending markers and its own self-hash field. The
# temporal/pathway inventories use the envelope shape. NEITHER is admitted in place.
SELF_HASH_OF = {
    "direct": ("direct_release_sha256",
               ("direct_release_sha256", "direct_release_run_id", "verdict", "admitted",
                "self_admitted", "verifier_id")),
    "temporal": ("release_id", ("release_id",)),
    "pathway": ("release_id", ("release_id",)),
}
# Lanes whose independent admission is the temporal-style ENVELOPE. Direct's admission is
# W10's own release-verification report, and the TYPED ADAPTER reads it — not this module.
ENVELOPE_LANES = ("temporal", "pathway")
ADMISSION_FILE_OF = {
    "direct": "direct_release_admission.json",
    "temporal": "temporal_arm_external_admission.json",
    "pathway": "pathway_arm_external_admission.json",
}
INVENTORY_FILE = INVENTORY_FILE_OF["temporal"]
ADMISSION_FILE = ADMISSION_FILE_OF["temporal"]
REPORT_ID_FIELD = "report_id"
SHA256_LEN = 64

INVENTORY_SCHEMA_OF = {
    "direct": "spot.stage02_direct_release.v1",
    "temporal": "spot.stage02_temporal_arm_release.v1",
    "pathway": "spot.stage02_pathway_arm_release.v1",
}
INVENTORY_SCHEMA = INVENTORY_SCHEMA_OF["temporal"]

# ONE ADMISSION SCHEMA PER LANE. A single shared constant meant the pathway lane demanded a
# report that declared itself to be about TEMPORAL bytes — and the envelope would have taken
# it.
ADMISSION_SCHEMA_OF = {
    "direct": "spot.stage02_direct_release_verification.v1",
    "temporal": "spot.stage02_temporal_arm_external_admission.v1",
    "pathway": "spot.stage02_pathway_arm_external_admission.v1",
}
ADMISSION_SCHEMA = ADMISSION_SCHEMA_OF["temporal"]      # the legacy default; lanes pass theirs

PENDING = "pending"
PRODUCER_VERDICT_PENDING = "pending_independent_verification"
ADMIT = "ADMIT"

# The producer's honest state, and the only one it may declare.
PRODUCER_STATES = (PENDING,)


def _canon(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode()).hexdigest()


def _raw(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _load(path: str) -> Optional[dict]:
    try:
        with open(path) as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def self_hash(doc: dict, id_field: str) -> str:
    """``sha256(canonical JSON excluding the id field)`` — the rule both artifacts declare."""
    return _canon({k: v for k, v in doc.items() if k != id_field})


def check_inventory(root: str, expect_bundles: int, expect_arms: int,
                    lane: str = "temporal") -> tuple:
    """The PRODUCER INVENTORY: present, self-hashing, byte-true, and only ever PENDING."""
    bad: list[str] = []
    INVENTORY_FILE = INVENTORY_FILE_OF[lane]
    INVENTORY_SCHEMA = INVENTORY_SCHEMA_OF[lane]
    path = os.path.join(root, INVENTORY_FILE)
    if not os.path.exists(path):
        return None, [
            f"no producer inventory at {INVENTORY_FILE}: a run with no inventory has "
            "nothing for an external verifier to have admitted, and the producer's own "
            "per-bundle preflight is not an admission"]

    doc = _load(path)
    if doc is None:
        return None, [f"{INVENTORY_FILE} is not a readable JSON document"]
    if doc.get("schema_version") != INVENTORY_SCHEMA:
        bad.append(f"{INVENTORY_FILE}: schema {doc.get('schema_version')!r} is not "
                   f"{INVENTORY_SCHEMA!r}")

    # CONTENT ADDRESSING: the id follows the content, or the inventory can be edited and
    # keep its name. In an ADMIT_IN_PLACE lane the hash is deliberately BLIND to the four
    # fields the verifier fills in — which is exactly what makes admitting a release
    # identity-preserving rather than a rewrite.
    id_field, excludes = SELF_HASH_OF[lane]
    claimed = doc.get(id_field)
    derived = _canon({k: v for k, v in doc.items() if k not in excludes})
    if claimed != derived:
        bad.append(f"{INVENTORY_FILE}: {id_field} {str(claimed)[:16]} does not follow its "
                   f"own content ({derived[:16]})")

    # THE PRODUCER MAY NOT ADMIT ITS OWN RELEASE.
    #
    # In an ADMIT_IN_PLACE lane the independent verifier fills the admission fields into this
    # same file, so `external_admission.status` is not the carrier — `self_admitted` is, and
    # the typed adapter checks it. Demanding `pending` here would refuse every release W10
    # has ever admitted.
    # THE PRODUCER SHIPS PENDING, IN EVERY LANE, AND STAYS THAT WAY. An inventory carrying
    # a verdict is one somebody EDITED: the independent verifier writes a separate report.
    if lane == "direct":
        if (doc.get("admitted") is not False or doc.get("self_admitted") is not False
                or doc.get("verifier_id") is not None
                or doc.get("verdict") != PRODUCER_VERDICT_PENDING):
            bad.append(f"{INVENTORY_FILE}: the producer's release is not un-admitted "
                       f"(verdict={doc.get('verdict')!r}, admitted={doc.get('admitted')!r})"
                       ". It ships PENDING and immutable; W10 gates exactly that")
    else:
        ext = doc.get("external_admission") or {}
        if ext.get("status") not in PRODUCER_STATES:
            bad.append(f"{INVENTORY_FILE}: external_admission.status is "
                       f"{ext.get('status')!r}; 'pending' is the only honest producer "
                       "state — a producer cannot emit the external verdict on itself")

    # EVERY REFERENCED BYTE. An inventory that named files it never hashed would be an
    # index of nothing.
    bundles = doc.get("bundles") or []
    if len(bundles) != expect_bundles:
        bad.append(f"{INVENTORY_FILE}: names {len(bundles)} bundles; the release topology "
                   f"is {expect_bundles}")
    n_arms = doc.get("n_logical_arms")
    if n_arms is not None and int(n_arms) != expect_arms:
        bad.append(f"{INVENTORY_FILE}: declares {n_arms} logical arms; the topology is "
                   f"{expect_arms}")

    for b in bundles:
        rel_dir = str(b.get("relative_dir") or "")
        for name, entry in sorted((b.get("files") or {}).items()):
            bad += _byte_check(root, rel_dir, name, entry)
        for rel, entry in sorted((b.get("rankings") or {}).items()):
            bad += _byte_check(root, rel_dir, rel, entry)
    return doc, bad


def _byte_check(root: str, rel_dir: str, name: str, entry: Any) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{rel_dir}/{name}: the inventory binds no hashes for it"]
    path = os.path.join(root, rel_dir, name)
    if not os.path.exists(path):
        return [f"{rel_dir}/{name}: named by the inventory, absent from the release"]
    out = []
    if entry.get("raw_sha256") and _raw(path) != entry["raw_sha256"]:
        out.append(f"{rel_dir}/{name}: raw bytes {_raw(path)[:16]} != inventory "
                   f"{str(entry['raw_sha256'])[:16]}")
    doc = _load(path)
    if doc is not None and entry.get("canonical_sha256") \
            and _canon(doc) != entry["canonical_sha256"]:
        out.append(f"{rel_dir}/{name}: canonical content {_canon(doc)[:16]} != inventory "
                   f"{str(entry['canonical_sha256'])[:16]}")
    return out


def check_external_admission(root: str, inventory: Optional[dict],
                             expect_verifier_id: Optional[str],
                             lane: str = "temporal") -> tuple:
    """The EXTERNAL ADMISSION: present, from the pinned verifier, BOUND TO THIS inventory.

    Direct's admission is W10's OWN release-verification report, in W10's own shape; the
    TYPED ADAPTER reads that. Demanding a temporal-style envelope of it would refuse W10.
    """
    if lane not in ENVELOPE_LANES:
        return inventory, []
    bad: list[str] = []
    INVENTORY_FILE = INVENTORY_FILE_OF[lane]
    ADMISSION_FILE = ADMISSION_FILE_OF[lane]
    # THIS LANE'S schema — not temporal's. The function already knew its lane; it just never
    # used it here, so a pathway admission declaring itself `_temporal_` was taken.
    ADMISSION_SCHEMA = ADMISSION_SCHEMA_OF[lane]
    path = os.path.join(root, ADMISSION_FILE)
    if not os.path.exists(path):
        return None, [
            f"no external admission at {ADMISSION_FILE}: the producer's per-bundle report "
            "is a PREFLIGHT, not an admission — it is written by the producer, in the "
            "producer's own directory, and signed with whatever id the producer chose. "
            "Only the independent verifier's envelope admits a release"]

    doc = _load(path)
    if doc is None:
        return None, [f"{ADMISSION_FILE} is not a readable JSON document"]
    if doc.get("schema_version") != ADMISSION_SCHEMA:
        bad.append(f"{ADMISSION_FILE}: schema {doc.get('schema_version')!r} is not "
                   f"{ADMISSION_SCHEMA!r}")

    if doc.get("envelope_id") is not None and doc.get(REPORT_ID_FIELD) is None:
        bad.append(f"{ADMISSION_FILE}: carries a 16-hex 'envelope_id' instead of the "
                   f"canonical '{REPORT_ID_FIELD}'. The content address of an admission is "
                   "what stops it being swapped; it is a full sha256, not a prefix")
    claimed = doc.get(REPORT_ID_FIELD)
    if not isinstance(claimed, str) or len(claimed) != SHA256_LEN:
        bad.append(f"{ADMISSION_FILE}: {REPORT_ID_FIELD} is {str(claimed)[:20]!r} — it "
                   f"must be a full {SHA256_LEN}-hex sha256 of its own canonical content")
    derived = self_hash(doc, REPORT_ID_FIELD)
    if claimed != derived:
        bad.append(f"{ADMISSION_FILE}: {REPORT_ID_FIELD} {str(claimed)[:16]} does not "
                   f"follow its own content ({derived[:16]})")

    if expect_verifier_id and doc.get("verifier_id") != expect_verifier_id:
        bad.append(f"{ADMISSION_FILE}: signed {doc.get('verifier_id')!r}; the pinned "
                   f"independent verifier is {expect_verifier_id!r}")
    # BYTE FOR BYTE. `str(...).upper()` accepted `admit`, `Admit`, `aDmIt` and any other
    # spelling, and could not tell a native ADMIT from a lane that had drifted.
    if doc.get("verdict") != ADMIT:
        bad.append(f"{ADMISSION_FILE}: verdict is {doc.get('verdict')!r}, not {ADMIT!r} "
                   "(exact token; the aggregate does not normalise a lane's verdict)")

    # THE BINDING. An envelope that admits a DIFFERENT release admits something else — and
    # a run that accepted it would be citing an admission it never received.
    binds = doc.get("binds") or {}
    if inventory is not None:
        want_id = inventory.get("release_id")
        if binds.get("producer_release_id") != want_id:
            bad.append(
                f"{ADMISSION_FILE}: it admits release "
                f"{str(binds.get('producer_release_id'))[:16]}; this run's producer "
                f"inventory is {str(want_id)[:16]}. That is an admission of something else")
        want_raw = _raw(os.path.join(root, INVENTORY_FILE))
        # REQUIRED: which RELEASE was admitted. This is what proves the admission is over
        # the actual W5 release and not over some other bytes.
        if binds.get("producer_release_raw_sha256") != want_raw:
            bad.append(
                f"{ADMISSION_FILE}: it binds inventory bytes "
                f"{str(binds.get('producer_release_raw_sha256'))[:16]}; the inventory on "
                f"disk hashes to {want_raw[:16]}")
        # ACCEPTED alongside it, and it must agree — never instead of it.
        alias = binds.get("inventory_raw_sha256")
        if alias is not None and alias != want_raw:
            bad.append(
                f"{ADMISSION_FILE}: binds.inventory_raw_sha256 {str(alias)[:16]} "
                f"disagrees with the inventory on disk ({want_raw[:16]})")
    return doc, bad
