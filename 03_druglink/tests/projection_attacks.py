"""THE ATTACKS ON A SEALED PROJECTION, in one place — so both suites run the SAME attack.

The seal suite (:mod:`test_selection_view_projection_seal`) asks what the CONTRACT refuses with
the bytes alone. The store suite (:mod:`test_selection_view_projection_store`) asks what only a
verifier HOLDING THE STORE can refuse. They must attack the same view in the same way, or the
boundary between them is a story rather than a result.
"""
from __future__ import annotations

import copy

from druglink import view_projection as vp
from druglink.hashing import content_hash

from selection_world import TEMPORAL, WITHIN, _conditions, _programs, _verified, _view

# `pathway_context` is EMPTY BY POLICY — the pathway lane is not admitted, because a gene-set
# enrichment record never sources a drug edge. Its attack is therefore an INSERTED row: bytes
# nobody sealed, which is the same refusal from the other side.
EMPTY_BY_POLICY = "pathway_context"

# A benign, NON-KEY column per projected table: enough to move the table's content hash, never
# the row's own identity. A mutation that changed an id would be caught by something else and
# would prove nothing about the seal.
MUTATED_COLUMN = {
    "arm_slots": "arm_context_sha256",          # the reviewer's own column
    "target_drug_edges": "arm_rank",
    "arm_summaries": "n_edges",
    "candidates": "identity_status",
    "source_records": "identity_status",
    "dispositions": "reason",
}


def sel(world):
    programs, conditions = _programs(world), _conditions(world)
    return _verified(world, a=programs[0], b=programs[1], mode=WITHIN,
                     conditions=[conditions[0]])


def other_sel(world):
    """A DIFFERENT question over the SAME store — the store is reusable, which is the point."""
    programs, conditions = _programs(world), _conditions(world)
    return _verified(world, a=programs[2], b=programs[3], mode=TEMPORAL,
                     conditions=[conditions[0], conditions[2]])


def honest(world) -> dict:
    return _view(world, sel(world))


def mutate(view: dict) -> dict:
    """A deep, independent copy. The attacker edits THIS, AFTER the view was sealed."""
    return copy.deepcopy(view)


def reseal(view: dict, bundle_dir: str) -> dict:
    """What a forger who UNDERSTOOD the contract check would do: re-seal over the mutated rows,
    re-stamp both receipts, and re-address the document. Every hash agrees again.

    This is why the contract check is not the whole gate. A document can always be made to agree
    with ITSELF; it cannot be made to agree with bytes it does not control.
    """
    seal = vp.seal(view_rows={n: view["tables"][n] for n in vp.SEALED_TABLES},
                   arm_evidence=view["arm_evidence"], bundle_dir=bundle_dir)
    view["projection"] = seal
    view["store"]["projection_sha256"] = seal["projection_sha256"]
    view["admission"]["projection_sha256"] = seal["projection_sha256"]
    view.pop("view_id", None)
    view.pop("view_content_sha256", None)
    content = content_hash(view)
    view["view_id"] = content[:16]
    view["view_content_sha256"] = content
    return view
