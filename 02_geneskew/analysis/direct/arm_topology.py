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
# THE RANKING ARTIFACT (``rankings/<program>__<desired_change>.json``), per arm.
#
# Shape: ``{"records": [{"target_id", "arm_value", "evaluable", "rank"}, ...]}`` — W5's
# native rows, the same ones nested in ``arm_bundle.json``.
#
# RETAINED-ROW SEMANTICS: every target is RETAINED with ``rank: null`` when it is not
# rankable. So "in the ranking" is NOT "in the rows". A consumer that counted rows instead
# of non-null ranks would inflate every hit count by exactly the targets the arm could not
# evaluate — the ones least entitled to support a claim. ``n_ranked`` is a count of RANKS.
#
# These files are BOUND (path + raw + canonical hash) and the aggregate REFUSES a bundle
# whose bound ranking is absent — it never binds a file that is not there.
ARM_BINDING = "ranking"                       # every arm, every lane
ARM_RANKING_DIR = "rankings"
ARM_RANKING_ROWS = "records"                  # ``ranked`` accepted as an alias
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

# --------------------------------------------------------------------------- #
# THE AUTHORITATIVE STAGE-1 v3 RELEASE. Its real schema, not one we wished for.
#
# An earlier version of this module read `base_portable_programs`,
# `base_portability_source_field` and a per-program `method_hash`. NONE OF THEM EXIST. The
# scorer view (`spot.stage01_stage2_registry_view.v1`) carries `base_portable` PER PROGRAM
# and nothing else, and the release (`spot.stage01_v3_release.v1`) carries `selector` +
# `components`, not `artifacts`. Tests written against invented fields agree with the
# invention, not with the release — so the fields are read from the release's own bytes
# here, and the fixtures stage the REAL release.
#
# The admitted set is DERIVED from `program.base_portable` and then COMPARED to
# `release.selector.admitted_programs`: two independent statements of the same fact, which
# is the only way a disagreement between them can ever surface. Reading the selector alone
# would trust it; deriving alone would never notice it had drifted.
# (Reference: W18's `scorer_view.admitted_programs()` + `cross_check_selector()`.)
# --------------------------------------------------------------------------- #
RELEASE_SCHEMA = "spot.stage01_v3_release.v1"
VIEW_SCHEMA = "spot.stage01_stage2_registry_view.v1"
VIEW_COMPONENT = "stage2_registry_view"
PORTABLE_KEY = "base_portable"

# There is NO per-program hash in the view. If an arm needs a per-program projection id, it
# is SPECIFIED here and derived by hashing the program's canonical record — never read from
# a field that does not exist.
PROJECTION_ID_RULE = "spot.stage02.arm.program_projection_id.canonical_view_record.v1"

# Batch commentary stays OUT of the reusable temporal chain (owner rule). The DiD estimand
# is population-level and the arm key already carries the ordered pair; a batch field in a
# reusable bundle would be commentary travelling into every join that reuses the arm.
BATCH_KEYS = ("batch", "confound")


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


def key_hits(obj: Any, keys: tuple, path: str = "") -> list[str]:
    """Every key anywhere in a document whose name contains one of ``keys``. Recursive."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(bad in str(k).lower() for bad in keys):
                hits.append(f"{path}.{k}")
            hits += key_hits(v, keys, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            hits += key_hits(v, keys, f"{path}[{i}]")
    return hits


def pair_derived_hits(obj: Any, path: str = "") -> list[str]:
    """Every key in an arm inventory that stores a pair-derived ordering."""
    return key_hits(obj, PAIR_DERIVED_KEYS, path)


# --------------------------------------------------------------------------- #
# THE AUTHORITATIVE RELEASE: the ONE source of the programs, the conditions and the
# gene-set sources.
# --------------------------------------------------------------------------- #
def program_projection_sha256(record: dict[str, Any]) -> str:
    """The per-program projection id, SPECIFIED because the view does not carry one.

    Two releases that admit the same program ids but disagree about that program's panel,
    control or coefficients are NOT the same scorer projection, and an arm keyed only on
    the id could be silently re-attributed from one to the other. So the id is the
    canonical hash of the program's whole record in the view.
    """
    return content_hash(record)


def _component(release: dict[str, Any], name: str, release_root: str) -> dict[str, Any]:
    """Resolve ONE release component against an EXPLICITLY STAGED release root.

    Never a machine default: a component resolved from wherever the process happens to be
    running is a component nobody can point at afterwards.
    """
    comp = (release.get("components") or {}).get(name)
    if not isinstance(comp, dict) or not comp.get("path"):
        raise RunManifestError(
            f"the release declares no {name!r} component; it cannot be resolved")
    rel = str(comp["path"])
    if os.path.isabs(rel) or ".." in rel.split("/"):
        raise RunManifestError(
            f"release component {name!r} path {rel!r} must be release-root-relative")
    path = os.path.join(release_root, rel)
    if not os.path.exists(path):
        raise RunManifestError(
            f"release component {name!r} is not staged at {rel!r} under the release root; "
            "stage the release explicitly rather than resolving it from a machine default")

    raw = file_sha256(path)
    if comp.get("raw_sha256") and raw != comp["raw_sha256"]:
        raise RunManifestError(
            f"release component {name!r}: the staged bytes hash to {raw[:16]}, but the "
            f"release pins {str(comp['raw_sha256'])[:16]}")
    with open(path) as fh:
        doc = json.load(fh)
    canon = content_hash(doc)
    if comp.get("canonical_content_sha256") and canon != comp["canonical_content_sha256"]:
        raise RunManifestError(
            f"release component {name!r}: canonical content hashes to {canon[:16]}, but "
            f"the release pins {str(comp['canonical_content_sha256'])[:16]}")
    return {"doc": doc, "path": rel, "raw_sha256": raw, "canonical_sha256": canon}


def load_release(release_path: Optional[str],
                 release_root: Optional[str]) -> dict[str, Any]:
    """Bind the authoritative Stage-1 v3 release and DERIVE the whole topology from it.

    The admitted program set is derived from ``program.base_portable`` in the scorer view
    and then CHECKED against ``release.selector.admitted_programs``. The conditions and the
    pathway sources come from the selector. Nothing is taken from a legacy registry, and no
    count is copied.
    """
    if not release_path or not release_root:
        raise RunManifestError(
            "the aggregate manifest requires --release AND --release-root: the "
            "authoritative Stage-1 v3 release, and the directory it is STAGED in. The "
            "legacy stage01_program_registry.json is not this artifact and may not stand "
            "in for it")
    if not os.path.exists(release_path):
        raise RunManifestError(f"release not found: {os.path.basename(release_path)}")
    with open(release_path) as fh:
        release = json.load(fh)
    if release.get("schema") != RELEASE_SCHEMA:
        raise RunManifestError(
            f"release schema is {release.get('schema')!r}; expected {RELEASE_SCHEMA!r}")

    view_comp = _component(release, VIEW_COMPONENT, release_root)
    view = view_comp["doc"]
    if view.get("schema_version") != VIEW_SCHEMA:
        raise RunManifestError(
            f"scorer view schema is {view.get('schema_version')!r}; expected "
            f"{VIEW_SCHEMA!r}")
    # The release publishes the view's canonical hash; the staged bytes must BE that view.
    pinned_view = release.get("registry_scorer_view_canonical_sha256")
    if pinned_view and view_comp["canonical_sha256"] != pinned_view:
        raise RunManifestError(
            f"the staged scorer view canonically hashes to "
            f"{view_comp['canonical_sha256'][:16]}, but the release binds "
            f"{str(pinned_view)[:16]}")

    records = view.get("programs")
    if not isinstance(records, list) or not records:
        raise RunManifestError("the scorer view carries no programs")
    undeclared = [str(p.get("program_id")) for p in records if PORTABLE_KEY not in p]
    if undeclared:
        raise RunManifestError(
            f"the scorer view does not declare {PORTABLE_KEY!r} for {sorted(undeclared)}; "
            "a program whose portability is unstated is not silently treated as portable")

    derived = sorted(str(p["program_id"]) for p in records if bool(p[PORTABLE_KEY]))
    if not derived:
        raise RunManifestError(
            "the release marks no program base_portable, so there is no arm to compute")

    selector = release.get("selector") or {}
    declared = sorted(str(p) for p in (selector.get("admitted_programs") or []))
    if declared and declared != derived:
        raise RunManifestError(
            f"base_portable derives {derived}, but the release selector declares "
            f"{declared}. One of them is wrong about what this release admits, and a run "
            "that picked either without checking would not know which")

    conditions = [str(c) for c in (selector.get("conditions") or [])]
    sources = [str(s) for s in (selector.get("pathway_sources") or [])]
    if not conditions or not sources:
        raise RunManifestError(
            "the release selector must name its conditions and its pathway sources; the "
            "condition universe is NOT taken from a batch policy and NOT from the manifest")

    return {
        "release_schema": release.get("schema"),
        "release_canonical_sha256": content_hash(release),
        "release_raw_sha256": file_sha256(release_path),
        "method_version": release.get("method_version"),
        # bound WHOLE, as the release publishes them — never a per-program field that does
        # not exist
        "registry_scorer_view_canonical_sha256": view_comp["canonical_sha256"],
        "registry_scorer_projection_sha256": release.get(
            "registry_scorer_projection_sha256"),
        "scorer_view_raw_sha256": view_comp["raw_sha256"],
        "scorer_view_path": view_comp["path"],
        "programs": derived,
        "n_programs": len(derived),
        "admitted_set_rederived_from_base_portable": True,
        "derived_agrees_with_selector": bool(declared),
        # the per-program id is SPECIFIED and computed, not read
        "program_projection_id_rule": PROJECTION_ID_RULE,
        "program_projection_sha256": {
            str(p["program_id"]): program_projection_sha256(p)
            for p in records if bool(p[PORTABLE_KEY])},
        # ORDER PRESERVED: the release states its conditions in temporal order, and a
        # reordered list is a different release
        "conditions": conditions,
        "gene_set_sources": sources,
        "condition_universe_source": "release.selector.conditions",
        "batch_policy_is_not_an_authority_here": True,
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
        "expected_arm_count_source":
            "2 x the admitted set derived from program.base_portable in the release's "
            "scorer view (cross-checked against release.selector.admitted_programs)",
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
        "expected_arm_count_source":
            "2 x the admitted set derived from program.base_portable in the release's "
            "scorer view (cross-checked against release.selector.admitted_programs)",
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
            "2 x the admitted set derived from program.base_portable, every arm "
            "referencing the ONE shared convergence artifact of this (condition, source)",
        "expected_hit_count_source":
            "RECONSTRUCTED, never declared: n_hits_in_ranking = |gene-set members (target "
            "namespace) INTERSECT the ranked target ids of that arm's bound ranking|, both "
            "read from the bundle's own bound bytes",
        "expected_exit_code": 0,
    },
}
