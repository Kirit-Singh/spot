"""WHICH RUN THIS IS: a NAMED, VERSIONED, HASH-BOUND topology. Declared before, not inferred after.

THE TRAP THIS EXISTS TO CLOSE
-----------------------------
Reactome is PARKED. The obvious move is to relax the 15-slot completeness check so a run
without Reactome still passes. THAT WOULD BE THE WORST POSSIBLE FIX, because:

    a PARTIAL full run (GO-BP produced, Reactome missing)  ->  3 direct, 6 temporal, 3 pathway
    a COMPLETE GO-BP-only run                              ->  3 direct, 6 temporal, 3 pathway

THEY ARE IDENTICAL IN THE BUNDLES. Nothing you can read off the artifacts distinguishes a run
that was SUPPOSED to produce Reactome and failed, from one that never intended to. A weakened
completeness check would silently admit the first as if it were the second — and the failure it
was hiding is exactly the one nobody would ever look for again.

So the old topology is NOT weakened. It stays exactly as it was, and a partial full run still
refuses. Instead a SECOND, EXPLICIT topology is declared:

    spot.stage02.topology.full.v1     GO-BP + Reactome   3 + 6 + 6 = 15 bundles   (LEGACY)
    spot.stage02.topology.go_bp.v1    GO-BP only         3 + 6 + 3 = 12 bundles   (PRODUCTION)

WHAT MAKES THEM TELLABLE APART
------------------------------
The topology is BOUND INTO THE RUN IDENTITY at preflight, BEFORE any bundle exists, and it is
hashed over its COMPLETE EXPECTED SET — every source, every expected bundle key, every expected
arm slot. Relabelling a finished partial full run as "GO-only" therefore changes the topology
hash, which changes the run identity, and the run refuses. A run cannot decide what it was
trying to be after it finds out what it managed.

ENDPOINT PATHWAYS ARE NOT TEMPORAL PATHWAYS
-------------------------------------------
The GO-BP pathway bundles here are WITHIN-CONDITION (endpoint) enrichments: one per condition.
A temporal GO-BP pathway lane — enrichment over a DIFFERENCE BETWEEN TWO TIMES — is a DIFFERENT
SCIENTIFIC OBJECT with a different estimator, and it does not exist yet. It is declared as a
SEPARATELY TYPED EXTENSION, absent by default, and it may only become required when its producer
exists. Folding it into the pathway count would conflate an endpoint enrichment with a
difference-in-differences enrichment, which is not a bookkeeping error; it is a category error
that would put the wrong number under the wrong question.
"""
from __future__ import annotations

from typing import Any

from .arm_topology import (
    DESIRED_CHANGES,
    LANE_DIRECT,
    LANE_PATHWAY,
    LANE_TEMPORAL,
    RunManifestError,
    arm_key,
    ordered_pairs,
)
from .hashing import content_hash

# --------------------------------------------------------------------------- #
# THE SOURCE VOCABULARY. Exact strings, as the release declares them.
# --------------------------------------------------------------------------- #
SOURCE_GO_BP = "GO-BP"
SOURCE_REACTOME = "Reactome"

# Reactome is PARKED, not deleted. It remains in the FULL topology, which remains valid and
# remains complete-or-refuse. Parking a source is a decision about which run to do next; it is
# not a licence to call an incomplete run complete.
PARKED_SOURCES = (SOURCE_REACTOME,)

# --------------------------------------------------------------------------- #
# THE EXTENSION LANE. Declared, typed, and ABSENT — because its producer does not exist.
# --------------------------------------------------------------------------- #
EXT_TEMPORAL_PATHWAY = "temporal_pathway"

TEMPORAL_PATHWAY_EXTENSION = {
    "extension_id": "spot.stage02.extension.temporal_pathway.v0",
    "status": "not_available",
    "required": False,
    "producer_exists": False,
    "object": "enrichment over a DIFFERENCE BETWEEN TWO CONDITIONS (a DiD)",
    "is_not": "the within-condition endpoint enrichment counted in the pathway lane",
    "why_separately_typed": (
        "an endpoint enrichment and a difference-in-differences enrichment are different "
        "scientific objects with different estimators. Counting them in one lane would put the "
        "wrong number under the wrong question — a category error, not a bookkeeping one"),
    "may_become_required_when": "its producer exists and an independent verifier admits it",
}

# --------------------------------------------------------------------------- #
# THE TOPOLOGIES. Named, versioned, and each complete-or-refuse in its own terms.
# --------------------------------------------------------------------------- #
TOPOLOGIES: dict[str, dict[str, Any]] = {
    "spot.stage02.topology.full.v1": {
        "topology_id": "spot.stage02.topology.full.v1",
        "label": "full (GO-BP + Reactome)",
        "status": "legacy",
        "pathway_sources": (SOURCE_GO_BP, SOURCE_REACTOME),
        "pathway_scope": "within_condition_endpoint",
        "extensions": {EXT_TEMPORAL_PATHWAY: TEMPORAL_PATHWAY_EXTENSION},
        "note": "UNCHANGED. A run declared under this topology and missing Reactome is "
                "INCOMPLETE and still refuses. That refusal is the point.",
    },
    "spot.stage02.topology.go_bp.v1": {
        "topology_id": "spot.stage02.topology.go_bp.v1",
        "label": "GO-BP only (Reactome parked)",
        "status": "production",
        "pathway_sources": (SOURCE_GO_BP,),
        "pathway_scope": "within_condition_endpoint",
        "extensions": {EXT_TEMPORAL_PATHWAY: TEMPORAL_PATHWAY_EXTENSION},
        "note": "Reactome is PARKED — declared out of scope BEFORE the run, not discovered "
                "missing after it.",
    },
}

DEFAULT_TOPOLOGY = "spot.stage02.topology.go_bp.v1"

# NAMED GATES.
G_UNKNOWN = "the_run_declares_a_topology_nobody_has_defined"
G_INCOMPLETE = "the_run_does_not_fill_every_bundle_its_declared_topology_requires"
G_FOREIGN_SOURCE = "the_run_ships_a_pathway_source_its_declared_topology_does_not_include"
G_RELABELLED = "the_declared_topology_hash_does_not_re_derive_from_the_topology_it_names"
G_EXTENSION_UNDECLARED = "an_extension_lane_is_present_but_the_topology_does_not_declare_it"


def spec(topology_id: str) -> dict[str, Any]:
    t = TOPOLOGIES.get(topology_id)
    if t is None:
        raise RunManifestError(
            f"{G_UNKNOWN}: {topology_id!r} is not a defined topology. The defined ones are "
            f"{sorted(TOPOLOGIES)}. A run that names a topology nobody wrote down is a run "
            "nobody can say is complete")
    return t


def expected_bundles(topology_id: str, conditions: list[str]) -> dict[str, list[str]]:
    """The EXACT physical bundles this topology requires. Derived; never written down."""
    t = spec(topology_id)
    conds = sorted(conditions)
    srcs = sorted(t["pathway_sources"])
    return {
        LANE_DIRECT: list(conds),
        LANE_TEMPORAL: [f"{a}->{b}" for a, b in ordered_pairs(conds)],
        # WITHIN-CONDITION endpoints only. One per (condition x source).
        LANE_PATHWAY: [f"{c}|{s}" for c in conds for s in srcs],
    }


def expected_arm_slots(topology_id: str, programs: list[str],
                       conditions: list[str]) -> dict[str, list[str]]:
    """Every logical arm slot this topology requires, per lane."""
    t = spec(topology_id)
    conds, srcs = sorted(conditions), sorted(t["pathway_sources"])
    slots: dict[str, list[str]] = {LANE_DIRECT: [], LANE_TEMPORAL: [], LANE_PATHWAY: []}
    for program in sorted(programs):
        for dc in DESIRED_CHANGES:
            for cond in conds:
                slots[LANE_DIRECT].append(
                    arm_key(LANE_DIRECT, program, dc, {"condition": cond}))
                for src in srcs:
                    slots[LANE_PATHWAY].append(arm_key(
                        LANE_PATHWAY, program, dc,
                        {"condition": cond, "gene_set_source": src}))
            for frm, to in ordered_pairs(conds):
                slots[LANE_TEMPORAL].append(arm_key(
                    LANE_TEMPORAL, program, dc,
                    {"from_condition": frm, "to_condition": to}))
    return {lane: sorted(v) for lane, v in slots.items()}


def binding(topology_id: str, *, programs: list[str],
            conditions: list[str]) -> dict[str, Any]:
    """WHAT THE RUN IDENTITY BINDS — and it is bound BEFORE any bundle exists.

    The hash is taken over the COMPLETE EXPECTED SET: the sources, every expected bundle key,
    every expected arm slot. So a finished run cannot be relabelled as a different topology:
    the hash moves, the run identity moves, and the run refuses. A run does not get to decide
    what it was trying to be after it finds out what it managed.
    """
    t = spec(topology_id)
    bundles = expected_bundles(topology_id, conditions)
    slots = expected_arm_slots(topology_id, programs, conditions)

    body = {
        "topology_id": t["topology_id"],
        "label": t["label"],
        "status": t["status"],
        # THE EXACT SOURCE LIST. Not "whatever the release happens to ship".
        "pathway_sources": sorted(t["pathway_sources"]),
        "pathway_scope": t["pathway_scope"],
        "parked_sources": [s for s in PARKED_SOURCES
                           if s not in t["pathway_sources"]],
        # ORDER-PRESERVED inputs, so a reordered condition list is a different topology
        "conditions": list(conditions),
        "programs": sorted(programs),
        "expected_bundles": {lane: sorted(v) for lane, v in bundles.items()},
        "n_expected_bundles": {lane: len(v) for lane, v in bundles.items()},
        "n_expected_bundles_total": sum(len(v) for v in bundles.values()),
        "expected_arm_slots": slots,
        "n_expected_arm_slots": {lane: len(v) for lane, v in slots.items()},
        "n_expected_arm_slots_total": sum(len(v) for v in slots.values()),
        # THE EXTENSION: declared, typed, and ABSENT. Never folded into the pathway count.
        "extensions": t["extensions"],
        "extension_lanes_required": [
            k for k, v in t["extensions"].items() if v.get("required")],
    }
    body["topology_sha256"] = content_hash(body)
    return body


def verify(bound: dict[str, Any], *, discovered: dict[str, list[str]],
           sources_seen: list[str]) -> list[str]:
    """Hold a run to the topology it DECLARED. Complete, exact, or refused.

    ``discovered`` is lane -> the bundle keys actually on disk.
    ``sources_seen`` is every gene-set source the pathway bundles actually carry.
    """
    bad: list[str] = []
    topology_id = str(bound.get("topology_id"))

    # (1) THE DECLARATION RE-DERIVES. This is what stops a partial FULL run being relabelled
    # GO-only after the fact: its expected set — and therefore its hash — is different.
    try:
        want = binding(topology_id, programs=list(bound.get("programs") or []),
                       conditions=list(bound.get("conditions") or []))
    except RunManifestError as exc:
        return [str(exc)]
    # (1a) THE DECLARATION HASHES TO ITSELF. Re-derived over the WHOLE body, so no bound field
    # can be edited without moving the hash. (Re-deriving only from topology_id + programs +
    # conditions left every OTHER field unchecked — the source list could be rewritten in place
    # and the hash would not budge. A selective re-derivation is a selective check.)
    declared = bound.get("topology_sha256")
    self_derived = content_hash({k: v for k, v in bound.items() if k != "topology_sha256"})
    if declared != self_derived:
        bad.append(
            f"{G_RELABELLED}: the bound topology says {str(declared)[:16]} but its own body "
            f"hashes to {self_derived[:16]}. A field was edited after the run was launched")
        return bad

    # (1b) ...and the body IS the canonical topology, field for field. Nothing extra, nothing
    # missing, nothing changed.
    got_body = {k: v for k, v in bound.items() if k != "topology_sha256"}
    want_body = {k: v for k, v in want.items() if k != "topology_sha256"}
    if got_body != want_body:
        diff = sorted({k for k in set(got_body) | set(want_body)
                       if got_body.get(k) != want_body.get(k)})
        bad.append(
            f"{G_RELABELLED}: this run declares topology {topology_id!r}, but its bound body "
            f"differs from that topology at {diff}. A run cannot be relabelled as a topology it "
            "was not launched under — an INCOMPLETE FULL RUN and a COMPLETE GO-ONLY RUN SHIP "
            "IDENTICAL BUNDLES, and the declaration is the only thing that can tell them apart")
        return bad

    # (2) EVERY REQUIRED BUNDLE. Omission refuses — it is not a smaller run, it is a broken one.
    for lane, expected in want["expected_bundles"].items():
        got = sorted(discovered.get(lane) or [])
        missing = sorted(set(expected) - set(got))
        extra = sorted(set(got) - set(expected))
        if missing:
            bad.append(
                f"{G_INCOMPLETE}: [{lane}] the declared topology requires {len(expected)} "
                f"bundle(s) and {len(missing)} are absent: {missing[:4]}. A run that is short "
                "is not a smaller release; it is an unfinished one")
        if extra:
            bad.append(f"{G_INCOMPLETE}: [{lane}] {len(extra)} bundle(s) this topology does not "
                       f"expect: {extra[:4]}")

    # (3) THE EXACT SOURCE LIST. A parked source appearing under a topology that excludes it is
    # not a bonus — it is a run that did something other than what it declared.
    allowed = set(want["pathway_sources"])
    foreign = sorted({str(s) for s in sources_seen} - allowed)
    if foreign:
        parked = [s for s in foreign if s in PARKED_SOURCES]
        bad.append(
            f"{G_FOREIGN_SOURCE}: the run ships pathway source(s) {foreign} under topology "
            f"{topology_id!r}, whose exact source list is {sorted(allowed)}."
            + (f" {parked} is PARKED: it is out of scope for this topology, and a run that "
               "produced it anyway did not do what it said it would."
               if parked else ""))

    # (4) NO UNDECLARED EXTENSION. A temporal-pathway bundle appearing here would be a DiD
    # enrichment counted as an endpoint enrichment.
    for name, ext in (want.get("extensions") or {}).items():
        if discovered.get(name) and not ext.get("required"):
            bad.append(
                f"{G_EXTENSION_UNDECLARED}: {name!r} bundles are present, but this topology "
                f"declares that extension {ext.get('status')!r} and NOT required. "
                f"{ext.get('why_separately_typed')}")
    return bad
