"""THE REUSABLE-ARM TOPOLOGY: what a complete Stage-2 run IS.

FROZEN AGAINST ``ROUND4_ADDENDUM.md`` sha256
``c477356278c5b7d2842659f5354792c9db7203ee774f8dd70653921124477a9f``.

A complete Stage-2 run is NOT a fixed A/B pair. The release is GENERIC: Stage-2
materialises REUSABLE PER-PROGRAM ARMS, and a pair question is a JOIN of two
independently-admitted arms — never a rerun, never a fused score.

THE ARM KEY IS THE DESIRED CHANGE
---------------------------------
    direct   | program_id | desired_change | condition
    temporal | program_id | desired_change | from_condition | to_condition
    pathway  | program_id | desired_change | condition | gene_set_source

The arm value is ``±delta_program``, and the sign is fixed by the desired change ALONE —
the role and the pole direction decide it only JOINTLY
(``config.ARM_FORMULA`` x ``config.POLE_SIGN``):

    away_from_A(high) -> -delta  DECREASE      toward_B(high) -> +delta  INCREASE
    away_from_A(low)  -> +delta  INCREASE      toward_B(low)  -> -delta  DECREASE

Keying on the POLE DIRECTION would file ``away_from_A(high)`` and ``toward_B(high)`` —
OPPOSITE perturbation directions — into one slot, and split the two arms that are
bit-identical (``away_from_A(high)`` and ``toward_B(low)``) across two. Keying on the ROLE
is worse: a role is a position in somebody's pair, not a property of the arm. Both are
preserved in the selection contract and recorded on the arm as PROVENANCE, never identity.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import config
from .hashing import content_hash, file_sha256

BUNDLE_SCHEMA = "spot.stage02_arm_bundle.v1"

LANE_DIRECT = "direct"
LANE_TEMPORAL = "temporal"
LANE_PATHWAY = "pathway"
LANES = (LANE_DIRECT, LANE_TEMPORAL, LANE_PATHWAY)

INCREASE = "increase"
DECREASE = "decrease"
DESIRED_CHANGES = (INCREASE, DECREASE)

ADMIT = "admit"

BUNDLE_FILES = {
    LANE_DIRECT: {"bundle": "arm_bundle.json", "provenance": "provenance.json",
                  "verification": "verification.json"},
    LANE_TEMPORAL: {"bundle": "arm_bundle.json",
                    "provenance": "temporal_provenance.json",
                    "verification": "temporal_verification.json"},
    LANE_PATHWAY: {"bundle": "arm_bundle.json",
                   "provenance": "pathway_provenance.json",
                   "verification": "pathway_verification.json",
                   "convergence": "convergence.json"},
}

# --------------------------------------------------------------------------- #
# WHAT EVERY BUNDLE MUST BIND ON DISK (pathway audit).
#
# A declared count is not evidence. ``n_hits_in_ranking`` could not be reconstructed by
# anybody, because the pathway provenance bound no ranking and no membership list — so the
# number that decides whether an arm is headline-rankable was, in the end, taken on trust.
#
# Every bundle therefore binds the BYTES its counts are derived from: each arm's ranking
# (target ids + canonical scores + ranks + evaluable flags), and — for pathway — the
# gene-set source membership, the perturbation-target universe, and the masked signatures
# plus the DE-readout universe its convergence stands on. Each is a bundle-relative path
# with a raw AND a canonical hash, so a verifier can open it and recompute.
# --------------------------------------------------------------------------- #
ARM_BINDING = "ranking"                       # every arm, every lane
BUNDLE_BINDINGS = {
    LANE_DIRECT: (),
    LANE_TEMPORAL: (),
    LANE_PATHWAY: ("gene_set_membership", "target_universe", "masked_signatures",
                   "readout_universe"),
}
BINDING_FIELDS = ("path", "raw_sha256", "canonical_sha256")

# --------------------------------------------------------------------------- #
# PAIR-DERIVED VIEWS ARE JOIN-TIME ONLY (frozen clause).
#
# A Pareto tier or a concordance label is a property of a PAIR somebody chose, not of a
# reusable arm. Baked into an arm, it would travel into every future join that reuses the
# arm, carrying an ordering nobody in that join asked for. The UI may derive one at join
# time from the two immutable ranks: off by default, no new score, and it can neither move
# an arm nor rescue an ineligible target. Legacy pair-shaped fields are COMPATIBILITY-ONLY
# and are excluded from the production all-arm manifest.
# --------------------------------------------------------------------------- #
PAIR_DERIVED_KEYS = (
    "pareto", "concordance", "joint_order", "joint_ordering", "combined_score",
    "balanced_skew", "weighted_score", "composite_score", "headline_rank",
)

PAIR_DERIVED_VIEW_POLICY = {
    "pareto_and_concordance": "join_time_display_only",
    "stored_in_reusable_arm_bundles": False,
    "off_by_default": True,
    "introduces_a_new_score": False,
    "can_change_an_arm_value_or_rank": False,
    "can_rescue_an_ineligible_target": False,
    "part_of_release_completeness": False,
    "part_of_stage3_target_admission": False,
    "legacy_pair_fields": "compatibility_only_excluded_from_this_manifest",
}

# The scorer view's own field names. The program set is RE-DERIVED from the portability
# field it names; the list it declares is CHECKED against that, never copied.
SCORER_PROGRAMS = "base_portable_programs"
SCORER_N = "n_base_portable"
SCORER_FIELD = "base_portability_source_field"


class RunManifestError(ValueError):
    """An arm cannot be bound. Refuse; never invent, never back-fill."""


def desired_change_for(role: str, pole_direction: str) -> str:
    """Which way the program is asked to move, for a (role, pole direction) origin.

    DERIVED from the producer's own arm algebra rather than transcribed: a hand-copied
    table would keep agreeing with a producer that no longer computes what it says. The
    VERIFIER holds an INDEPENDENT copy so it can disagree with this.
    """
    if role not in config.ARMS:
        raise RunManifestError(f"unknown arm role {role!r}; expected {list(config.ARMS)}")
    if pole_direction not in config.POLE_SIGN:
        raise RunManifestError(
            f"unknown pole direction {pole_direction!r}; expected "
            f"{sorted(config.POLE_SIGN)}")
    sign = config.POLE_SIGN[pole_direction]
    multiplier = -sign if role == config.ARM_A else sign
    return INCREASE if multiplier > 0 else DECREASE


def role_pole_map() -> dict[str, str]:
    """The full four-entry mapping, as ``"role|pole" -> desired_change``."""
    return {f"{role}|{pole}": desired_change_for(role, pole)
            for role in config.ARMS for pole in sorted(config.POLE_SIGN)}


def pair_derived_hits(obj: Any, path: str = "") -> list[str]:
    """Every key in an arm inventory that stores a pair-derived ordering. Recursive."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(bad in str(k).lower() for bad in PAIR_DERIVED_KEYS):
                hits.append(f"{path}.{k}")
            hits += pair_derived_hits(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            hits += pair_derived_hits(v, f"{path}[{i}]")
    return hits


# --------------------------------------------------------------------------- #
# THE SCORER VIEW: the ONE source of the admitted program set.
# --------------------------------------------------------------------------- #
def load_scorer_view(path: Optional[str]) -> dict[str, Any]:
    """Bind the v3 generic release / scorer view and RE-DERIVE its program set.

    The declared ``base_portable_programs`` list is never believed. The view names the
    field that decides portability; the program set is recomputed from that field over the
    view's own program records, and the declared list and count must agree with the
    recomputation or the view is refused.

    There is no default and no fallback: a run whose admitted program set came from an
    unnamed source cannot be reproduced or contested.
    """
    if not path:
        raise RunManifestError(
            "the aggregate manifest requires --scorer-view: the v3 generic release / "
            "scorer view that names the admitted programs. The legacy "
            "stage01_program_registry.json is NOT this artifact and may not stand in for "
            "it, even while the two happen to agree")
    if not os.path.exists(path):
        raise RunManifestError(f"scorer view not found: {os.path.basename(path)}")
    with open(path) as fh:
        doc = json.load(fh)

    field = doc.get(SCORER_FIELD)
    programs = doc.get("programs")
    if not field or not isinstance(programs, list) or not programs:
        raise RunManifestError(
            f"scorer view must declare {SCORER_FIELD!r} and a non-empty 'programs' list; "
            "a program set that cannot be re-derived cannot be trusted")

    derived = sorted(str(p["program_id"]) for p in programs if p.get(field))
    declared = sorted(str(p) for p in (doc.get(SCORER_PROGRAMS) or []))
    if derived != declared:
        raise RunManifestError(
            f"scorer view: {SCORER_PROGRAMS} declares {declared} but re-deriving from "
            f"{field!r} gives {derived}; the declared list is not believed")
    n_declared = doc.get(SCORER_N)
    if n_declared is not None and int(n_declared) != len(derived):
        raise RunManifestError(
            f"scorer view: {SCORER_N}={n_declared} disagrees with the {len(derived)} "
            "programs re-derived from the portability field")

    return {
        "schema_version": doc.get("schema_version"),
        "method_version": doc.get("method_version"),
        "raw_sha256": file_sha256(path),
        "canonical_sha256": content_hash(doc),
        "base_portability_source_field": str(field),
        "programs": derived,
        "n_programs": len(derived),
        "scorer_projection_sha256": {
            str(p["program_id"]): p.get("method_hash") for p in programs},
        "program_set_rederived_from_the_view": True,
        "legacy_registry_used": False,
    }


# --------------------------------------------------------------------------- #
# THE SLOT ALGEBRA. Cardinalities are DERIVED; not one of them is written down.
# --------------------------------------------------------------------------- #
def ordered_pairs(conditions: list[str]) -> list[tuple[str, str]]:
    conds = sorted(conditions)
    return [(a, b) for a in conds for b in conds if a != b]


def arm_key(lane: str, program: str, desired_change: str,
            context: dict[str, Any]) -> str:
    """The canonical reusable arm key. Role and pole direction are NOT in it."""
    if lane == LANE_DIRECT:
        tail = [str(context["condition"])]
    elif lane == LANE_TEMPORAL:
        tail = [str(context["from_condition"]), str(context["to_condition"])]
    elif lane == LANE_PATHWAY:
        tail = [str(context["condition"]), str(context["gene_set_source"])]
    else:
        raise RunManifestError(f"unknown lane {lane!r}")
    return "|".join([lane, program, desired_change] + tail)


def expected_slots(programs: list[str], conditions: list[str],
                   sources: list[str]) -> dict[str, list[str]]:
    """Every logical arm slot a COMPLETE run must fill, per lane."""
    conds, srcs = sorted(conditions), sorted(sources)
    slots: dict[str, list[str]] = {lane: [] for lane in LANES}
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


def expected_bundles(conditions: list[str], sources: list[str]) -> dict[str, list[str]]:
    """The PHYSICAL all-arm bundles: one per context, each carrying every program arm."""
    conds, srcs = sorted(conditions), sorted(sources)
    return {
        LANE_DIRECT: list(conds),
        LANE_TEMPORAL: [f"{a}->{b}" for a, b in ordered_pairs(conds)],
        LANE_PATHWAY: [f"{c}|{s}" for c in conds for s in srcs],
    }


def selection_capacity(n_programs: int, n_conditions: int) -> dict[str, Any]:
    """How many ordered questions the reusable arms can answer. DERIVED arithmetic.

    A pole STATE is (program, pole direction): 2 per program. WITHIN a condition both
    endpoints of a selection share that condition, so the exactly identical
    (program, pole, condition) tuple is the ONLY refusal — hence ``n x (n-1)``. ACROSS an
    ordered condition pair the endpoints are different conditions, so even the identical
    pole state is a legitimate question ("this program, this pole, from Rest to Stim8hr")
    — hence ``n x n``.
    """
    states = 2 * int(n_programs)
    n_pairs = int(n_conditions) * (int(n_conditions) - 1)
    within = int(n_conditions) * states * (states - 1)
    temporal = n_pairs * states * states
    return {
        "pole_states_per_condition": states,
        "within_condition_selections": within,
        "temporal_selections": temporal,
        "total_valid_ordered_selections": within + temporal,
        "refusal_rule": "only an exactly identical (program, pole, condition) is refused",
    }


# --------------------------------------------------------------------------- #
# THE EXACT PER-LANE CLI INVOCATION CONTRACT.
#
# WHAT produces each bundle, WHAT it writes, and WHERE its row count is supposed to come
# from. No count is written here: a number in this file would be a number nobody measured.
# The SOURCE of the count is named, so a reader can go and check it.
# --------------------------------------------------------------------------- #
CLI_CONTRACTS = {
    LANE_DIRECT: {
        "command": "python -m direct.cli",
        "required_arguments": [
            "--stage1-v3-selection", "--stage1-v3-schema", "--registry", "--de-main",
            "--by-guide", "--by-donors", "--sgrna", "--guide-manifest",
            "--source-registry", "--stage1-release", "--env-lock", "--lane",
            "--out-root"],
        "one_invocation_per": "condition",
        "output_filenames": sorted(set(BUNDLE_FILES[LANE_DIRECT].values()) | {
            "screen.parquet", "masks.parquet", "contributing_guides.parquet",
            "guide_support.parquet", "donor_support.parquet", "axis.json",
            "gene_universe.json", "input_manifest.json"}),
        "expected_row_count_source":
            "one screen row per released pooled-main estimate at the bundle's condition — "
            "verification.json.source_target_count, re-derived by verify_run from the DE "
            "release obs (culture_condition == the bundle's condition)",
        "expected_arm_count_source": "2 x the scorer view's n_base_portable",
        "expected_exit_code": 0,
    },
    LANE_TEMPORAL: {
        "command": "python -m direct.temporal.cli",
        "required_arguments": [
            "--stage1-v3-selection", "--stage1-v3-schema", "--registry", "--de-main",
            "--by-guide", "--by-donors", "--sgrna", "--guide-manifest",
            "--source-registry", "--stage1-release", "--batch-policy", "--out-root"],
        "one_invocation_per": "ordered condition pair",
        "output_filenames": sorted(set(BUNDLE_FILES[LANE_TEMPORAL].values()) | {
            "temporal.parquet", "endpoints.parquet"}),
        "expected_row_count_source":
            "one temporal record per target in the UNION of the two endpoints' released "
            "pooled-main targets — temporal_provenance.json.n_records",
        "expected_arm_count_source": "2 x the scorer view's n_base_portable",
        "expected_exit_code": 0,
    },
    LANE_PATHWAY: {
        "command": "python -m direct.run_pathway",
        "required_arguments": [
            "--stage1-v3-selection", "--stage1-v3-schema", "--registry", "--de-main",
            "--by-guide", "--by-donors", "--sgrna", "--gene-sets", "--guide-manifest",
            "--source-registry", "--stage1-release", "--out-root"],
        "one_invocation_per": "condition x gene-set source",
        "output_filenames": sorted(set(BUNDLE_FILES[LANE_PATHWAY].values()) | {
            "pathway.json"}),
        "expected_row_count_source":
            "one pathway record per gene set in the PINNED bundle — "
            "pathway_provenance.json.run_binding.gene_sets.gene_set_release.n_sets",
        "expected_arm_count_source":
            "2 x the scorer view's n_base_portable, every arm referencing the ONE shared "
            "convergence artifact of this (condition, source)",
        "expected_hit_count_source":
            "RECONSTRUCTED, never declared: n_hits_in_ranking = |gene-set members (target "
            "namespace) INTERSECT the ranked target ids of that arm's bound ranking|, both "
            "read from the bundle's own bound bytes",
        "expected_exit_code": 0,
    },
}
