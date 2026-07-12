"""The Stage-3 contract is FROZEN. These tests make that enforceable, not declarative.

Stage 4 (window 6) rebases onto this branch and binds to
``spot.stage03_drug_annotation.v1``. A freeze that lives only in a handoff document is a
promise nobody can check: the schema bytes could drift and the first thing to notice would
be a Stage-4 integration failure, far from the edit that caused it.

So the frozen hashes are PINNED here. Editing a frozen schema now fails THIS test, in THIS
lane, with a message that says what to do about it — which is the whole point of a freeze.

Unfreezing is allowed. It is just not allowed to happen SILENTLY: bump the schema id, hand
Stage 4 the new hash, and update the pin deliberately.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_DIR = os.path.abspath(os.path.join(_HERE, "..", "schemas"))

# The generic contract Stage 4 consumes, and the digest of the whole schema set.
# Re-hashed at the r7 freeze; see the round's HANDOFF.md §5.
FROZEN_CONTRACT = "spot.stage03_drug_annotation.v1"
FROZEN_CONTRACT_SHA256 = \
    "361d0833d5cb099155ac6ad87557c728fcd64feba1e2ccbf7938bd2c6f4c9eed"
FROZEN_SCHEMA_SET_SHA256 = \
    "5b42a64c8aca0fd279ba1440cb956ce034246f542362a6a8b470d27ca2f11b82"

_UNFREEZE = (
    "\n\nThe Stage-3 contract is FROZEN and Stage 4 binds to these bytes. If this change "
    "is intended: bump the schema $id, re-hash, hand the new hash to the Stage-4 owner "
    "(window 6), and update the pin in this file — in that order. Do not just update the "
    "pin to make this pass; that silently breaks the consumer this freeze exists to "
    "protect."
)

# The vocabulary the contract retired. It is refused structurally elsewhere; here we hold
# the frozen BYTES to never quietly reintroduce it.
RETIRED = (
    "production_candidate", "production_promotion_eligible",
    "may_write_production_pointer", "production_pointer_written",
    "research_pk_annotation_eligible", "spot.stage03_research_annotation.v1",
)


def _sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _schema_set_sha256() -> str:
    """Sorted name + per-file hash, so a RENAME or a DELETION moves the digest too."""
    h = hashlib.sha256()
    for name in sorted(n for n in os.listdir(SCHEMA_DIR) if n.endswith(".json")):
        h.update(name.encode())
        h.update(b"\0")
        h.update(_sha256(os.path.join(SCHEMA_DIR, name)).encode())
        h.update(b"\n")
    return h.hexdigest()


def test_the_generic_stage4_contract_is_byte_frozen():
    path = os.path.join(SCHEMA_DIR, f"{FROZEN_CONTRACT}.json")
    got = _sha256(path)
    assert got == FROZEN_CONTRACT_SHA256, (
        f"{FROZEN_CONTRACT} changed: {got} != pinned {FROZEN_CONTRACT_SHA256}" + _UNFREEZE)


def test_the_whole_schema_set_is_byte_frozen():
    """Catches what a single-file pin cannot: a renamed, deleted or ADDED schema."""
    got = _schema_set_sha256()
    assert got == FROZEN_SCHEMA_SET_SHA256, (
        f"the schemas/ set changed: {got} != pinned {FROZEN_SCHEMA_SET_SHA256}" + _UNFREEZE)


def test_the_frozen_contract_still_declares_its_own_id():
    """A hash pin proves the bytes; this proves the bytes still say what we handed over."""
    with open(os.path.join(SCHEMA_DIR, f"{FROZEN_CONTRACT}.json")) as fh:
        doc = json.load(fh)
    assert doc["$id"] == FROZEN_CONTRACT
    assert doc["properties"]["schema_version"]["const"] == FROZEN_CONTRACT
    assert doc["properties"]["artifact_class"]["const"] == "analysis"


@pytest.mark.parametrize("term", RETIRED)
def test_no_frozen_schema_reintroduces_retired_vocabulary(term):
    for name in sorted(os.listdir(SCHEMA_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(SCHEMA_DIR, name)) as fh:
            body = fh.read()
        # The drug-annotation contract NAMES the retired terms in its description, to say
        # they are refused. That is the contract speaking, not a field being offered.
        doc = json.loads(body)
        offered = json.dumps({k: v for k, v in doc.items() if k != "description"})
        assert term not in offered, (
            f"{name} reintroduces retired vocabulary {term!r} outside its description")
