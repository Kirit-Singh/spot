"""THE TOPOLOGY CONTRACT, RESTATED FOR THE VERIFIER. It does not import the producer.

The whole point of this check is that the producer might compute the WRONG expected set. A
verifier that imported ``run_topology`` and called it would derive the expected set exactly the
way the producer did, agree with it by construction, and be unable to catch it — the check would
run, pass, and mean nothing. (My audit probe caught me doing precisely this.)

So the two topologies and the slot algebra are re-stated here, independently, and a drift
between this module and ``run_topology`` is a FINDING rather than a silent agreement.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

# RE-STATED. If these ever disagree with the producer's, that disagreement is the finding.
SOURCE_GO_BP = "GO-BP"
SOURCE_REACTOME = "Reactome"
PARKED_SOURCES = (SOURCE_REACTOME,)

DESIRED_CHANGES = ("increase", "decrease")

TOPOLOGY_SOURCES = {
    "spot.stage02.topology.full.v1": (SOURCE_GO_BP, SOURCE_REACTOME),
    "spot.stage02.topology.go_bp.v1": (SOURCE_GO_BP,),
}

G_UNKNOWN = "the_run_declares_a_topology_nobody_has_defined"
G_INCOMPLETE = "the_run_does_not_fill_every_bundle_its_declared_topology_requires"
G_FOREIGN_SOURCE = "the_run_ships_a_pathway_source_its_declared_topology_does_not_include"
G_RELABELLED = "the_declared_topology_hash_does_not_re_derive_from_the_topology_it_names"
G_ABSENT = "a_production_manifest_declares_no_run_topology"


def _canon(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def _ordered_pairs(conditions):
    c = sorted(conditions)
    return [(a, b) for a in c for b in c if a != b]


def expected_bundles(topology_id: str, conditions) -> dict:
    """The EXACT bundles this topology requires — derived here, not read from the producer."""
    srcs = sorted(TOPOLOGY_SOURCES[topology_id])
    conds = sorted(conditions)
    return {
        "direct": list(conds),
        "temporal": [f"{a}->{b}" for a, b in _ordered_pairs(conds)],
        # WITHIN-CONDITION endpoints. A temporal-pathway (DiD) bundle is a different object.
        "pathway": [f"{c}|{s}" for c in conds for s in srcs],
    }


def verify(bound: dict, *, discovered: dict, sources_seen: list,
           require_declared: bool = False) -> list:
    """Hold the run to the topology it DECLARED."""
    if not bound:
        return ([f"{G_ABSENT}: this manifest declares no run_topology. An INCOMPLETE FULL RUN "
                 "and a COMPLETE GO-ONLY RUN SHIP IDENTICAL BUNDLES, so a run that did not say "
                 "which run it was cannot be said to be complete"]
                if require_declared else [])

    bad: list[str] = []
    tid = str(bound.get("topology_id"))
    if tid not in TOPOLOGY_SOURCES:
        return [f"{G_UNKNOWN}: {tid!r} is not a defined topology"]

    # (1) THE SELF-HASH, over the WHOLE body — no bound field can be edited without moving it.
    declared = bound.get("topology_sha256")
    derived = _canon({k: v for k, v in bound.items() if k != "topology_sha256"})
    if declared != derived:
        return [f"{G_RELABELLED}: the bound topology says {str(declared)[:16]}; its own body "
                f"hashes to {derived[:16]}. A field was edited after the run was launched"]

    # (2) THE SOURCE LIST IS THIS TOPOLOGY'S — re-derived, never read.
    want_sources = sorted(TOPOLOGY_SOURCES[tid])
    if sorted(bound.get("pathway_sources") or []) != want_sources:
        bad.append(
            f"{G_RELABELLED}: the run declares {tid!r} but binds sources "
            f"{bound.get('pathway_sources')}; that topology's exact list is {want_sources}. "
            "An INCOMPLETE FULL RUN and a COMPLETE GO-ONLY RUN SHIP IDENTICAL BUNDLES, and the "
            "declaration is the only thing that can tell them apart")
        return bad

    # (3) THE EXPECTED BUNDLES, re-derived from the topology it names.
    want = expected_bundles(tid, bound.get("conditions") or [])
    if bound.get("expected_bundles") != want:
        bad.append(f"{G_RELABELLED}: the bound expected_bundles are not the ones {tid!r} "
                   "requires over these conditions")
        return bad

    for lane, expected in want.items():
        got = sorted(discovered.get(lane) or [])
        missing = sorted(set(expected) - set(got))
        extra = sorted(set(got) - set(expected))
        if missing:
            bad.append(f"{G_INCOMPLETE}: [{lane}] {len(missing)} required bundle(s) absent: "
                       f"{missing[:4]}. A run that is short is not a smaller release; it is an "
                       "unfinished one")
        if extra:
            bad.append(f"{G_INCOMPLETE}: [{lane}] {len(extra)} unexpected bundle(s): "
                       f"{extra[:4]}")

    foreign = sorted({str(s) for s in sources_seen if s and s != "None"} - set(want_sources))
    if foreign:
        parked = [s for s in foreign if s in PARKED_SOURCES]
        bad.append(
            f"{G_FOREIGN_SOURCE}: the run ships pathway source(s) {foreign} under {tid!r}, "
            f"whose exact list is {want_sources}."
            + (f" {parked} is PARKED: a run that produced it anyway did not do what it "
               "declared." if parked else ""))
    return bad
