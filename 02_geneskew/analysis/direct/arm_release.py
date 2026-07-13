"""THE DIRECT RELEASE: every condition the bound Stage-1 release ships, once each.

BLOCKER 6. `run_arms` emits one condition per invocation. Nothing checked that a Direct
release is Rest + Stim8hr + Stim48hr — so a one-bundle run was indistinguishable from a
finished Direct release, and no verifier could have told them apart because the expectation
existed nowhere.

WHERE THE CONDITIONS COME FROM, AND WHERE THEY DO NOT
-----------------------------------------------------
From `release.selector.conditions` — the BOUND Stage-1 release. Not from a batch policy, not
from the runbook's argv, not from a constant in this repo.

The distinction is not pedantic. A hard-coded three would keep passing after Stage-1 shipped a
fourth condition, and the release would be silently incomplete under a complete-looking name —
the same "copied count" defect that put a 999-slot bundle past every hash it advertised, one
level up. So the expected inventory is a FUNCTION of the release, re-derived on every run.

A missing condition, a duplicated condition and a condition the release never shipped each
refuse at their own named gate.

This producer does NOT admit its own release. The aggregate manifest ships un-admitted, and an
independent verifier replaces the verdict after reading the bundles back off disk.
"""
from __future__ import annotations

import os
from typing import Any

from . import emit, run_arms, scorer_view
from .hashing import canonical_json, content_hash, sha256_hex

SCHEMA = "spot.stage02_direct_release.v1"
RELEASE_ID = "spot.stage02.direct.all_arm_release.v1"
RELEASE_FILE = "direct_release.json"
RELEASE_ID_LEN = 16

CONDITION_RULE = (
    "the physical bundles of a complete Direct release are release.selector.conditions, "
    "derived from the bound Stage-1 release and never from a batch policy")

REFUSE_NO_CONDITIONS = "the_bound_release_declares_no_conditions"
REFUSE_MISSING_CONDITION = "a_condition_the_release_ships_has_no_bundle"
REFUSE_DUPLICATE_CONDITION = "a_condition_was_produced_more_than_once"
REFUSE_UNKNOWN_CONDITION = "a_bundle_names_a_condition_the_release_never_shipped"
REFUSE_TOPOLOGY_MISMATCH = "the_derived_topology_disagrees_with_the_release_declaration"


class DirectReleaseError(ValueError):
    """The Direct release inventory is not the one the bound Stage-1 release implies."""

    def __init__(self, reason: str, message: str):
        super().__init__(f"[{reason}] {message}")
        self.reason = reason


def expected_conditions(release) -> list[str]:
    """The conditions a COMPLETE Direct release consists of. Derived, never declared here."""
    conditions = [str(c) for c in (getattr(release, "conditions", ()) or ())]
    if not conditions:
        raise DirectReleaseError(
            REFUSE_NO_CONDITIONS,
            "the bound Stage-1 release declares no selector conditions, so nothing can say "
            "which physical bundles a complete Direct release consists of. An inventory that "
            "defaulted to three would be a guess wearing a release's name")
    return conditions


def assert_inventory(expected: list[str], produced: list[dict[str, Any]]) -> None:
    """Exactly the release's conditions, each exactly once. Nothing more, nothing less."""
    got = [str(b["condition"]) for b in produced]

    duplicates = sorted({c for c in got if got.count(c) > 1})
    if duplicates:
        raise DirectReleaseError(
            REFUSE_DUPLICATE_CONDITION,
            f"conditions produced more than once: {duplicates}. Two bundles for one condition "
            "are two identities for one measurement, and a reader cannot tell which one the "
            "release means")

    unknown = sorted(set(got) - set(expected))
    if unknown:
        raise DirectReleaseError(
            REFUSE_UNKNOWN_CONDITION,
            f"bundles name conditions the bound release never shipped: {unknown}. The "
            f"release ships {expected}")

    missing = [c for c in expected if c not in got]
    if missing:
        raise DirectReleaseError(
            REFUSE_MISSING_CONDITION,
            f"the bound release ships {expected} but no bundle was produced for {missing}. "
            "An incomplete Direct release must not be indistinguishable from a complete one")


def assert_declared_topology(release, n_bundles: int, n_logical: int) -> None:
    """Cross-check the DERIVED topology against the release's own declaration, if it makes one.

    Both numbers are derived here (bundles = |conditions|, arms = |conditions| x slots). The
    release's `arm_topology` is an INDEPENDENT statement of the same thing. They must agree —
    and neither is copied from the other, which is the whole point: two derivations that
    disagree mean the release and the producer do not think they are building the same thing.
    """
    topology = (getattr(release, "scorer", {}) or {}).get("arm_topology") or {}
    if not topology:
        return
    declared_bundles = (topology.get("physical_bundles") or {}).get("direct")
    declared_arms = (topology.get("logical_slots") or {}).get("direct")
    for what, declared, derived in (("physical bundles", declared_bundles, n_bundles),
                                    ("logical arms", declared_arms, n_logical)):
        if declared is not None and int(declared) != int(derived):
            raise DirectReleaseError(
                REFUSE_TOPOLOGY_MISMATCH,
                f"the release declares {declared} Direct {what}, but the bound release's own "
                f"conditions and admitted programs imply {derived}")


def build_release(args) -> dict[str, Any]:
    """Build EVERY condition the bound release ships, and bind them into one Direct release.

    The bundles are produced by the ordinary single-condition producer — there is deliberately
    no second implementation, because a bundle built by the aggregate path that could drift
    from a bundle built on its own would make the release a claim about two producers.
    """
    from . import run_screen as rs

    lane = getattr(args, "lane", None) or "production"
    release = rs.load_bundle_release(args, lane)
    conditions = expected_conditions(release)

    bundles: list[dict[str, Any]] = []
    for cond in conditions:
        one = _clone_args(args, cond)
        result = run_arms.build_bundle(one)
        bundles.append({
            "condition": result["condition"],
            "arm_bundle_run_id": result["arm_bundle_run_id"],
            "arm_bundle_run_sha256": result["provenance"]["arm_bundle_run_sha256"],
            "arm_rows_sha256": result["bundle"]["arm_rows_sha256"],
            "n_arm_slots": result["n_arm_slots"],
            "n_expected_arm_slots": result["n_expected_arm_slots"],
            "n_arm_rows": result["n_arm_rows"],
            "out_dir": result["out_dir"],
            # RELATIVE to the release root: a machine-local path is a citation nobody else
            # can follow, and the same science on two hosts must cite the same release.
            "path": os.path.basename(result["out_dir"]),
        })

    assert_inventory(conditions, bundles)

    n_logical = sum(b["n_expected_arm_slots"] for b in bundles)
    assert_declared_topology(release, len(bundles), n_logical)

    body = {
        "schema_version": SCHEMA,
        "direct_release_id": RELEASE_ID,
        "condition_rule": CONDITION_RULE,
        "expected_conditions": conditions,
        "n_physical_bundles": len(bundles),
        "n_logical_arms": n_logical,
        "stage1_release": dict(release.hashes),
        # the SAME view the bundles were built from — one release, one admitted set
        "scorer_view_sha256": scorer_view.view(release)["scorer_view_sha256"],
        "bundles": [{k: v for k, v in b.items() if k != "out_dir"} for b in bundles],
    }
    body["direct_release_sha256"] = content_hash(body)
    release_id = sha256_hex(canonical_json(body))[:RELEASE_ID_LEN]

    doc = dict(body,
               direct_release_run_id=release_id,
               # THE PRODUCER DOES NOT ADMIT ITS OWN RELEASE. An independent verifier reads
               # the three bundles back off disk and replaces this.
               verdict=run_arms.VERDICT_PENDING,
               admitted=False,
               self_admitted=False,
               verifier_id=None)

    out_dir = args.out_root
    os.makedirs(out_dir, exist_ok=True)
    emit.write_json(os.path.join(out_dir, RELEASE_FILE), doc)

    return {"direct_release_run_id": release_id, "out_dir": out_dir,
            "expected_conditions": conditions, "bundles": bundles,
            "n_physical_bundles": len(bundles), "n_logical_arms": n_logical,
            "release": doc}


def _clone_args(args, cond: str):
    """The same args, aimed at one condition. argparse.Namespace or fixture dataclass alike."""
    import copy
    one = copy.copy(args)
    one.condition = cond
    return one
