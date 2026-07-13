"""The run-manifest contract, REIMPLEMENTED FROM THE WRITTEN SPEC for the verifier.

INDEPENDENCE RULE (test-enforced): nothing here is imported from the generator — not
``run_manifest``, not ``arm_topology``, not ``config``, not ``hashing``, not
``code_digest``. The canonical hash, the desired-change table, the slot algebra and the
forbidden-key firewall are all restated here, so the verifier can DISAGREE with the
producer. A verifier that reused the producer's own functions would agree with it by
construction, whatever those functions happen to compute today.

FROZEN AGAINST ``ROUND4_ADDENDUM.md`` sha256
``c477356278c5b7d2842659f5354792c9db7203ee774f8dd70653921124477a9f``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Optional

LANE_DIRECT, LANE_TEMPORAL, LANE_PATHWAY = "direct", "temporal", "pathway"
LANES = (LANE_DIRECT, LANE_TEMPORAL, LANE_PATHWAY)
INCREASE, DECREASE = "increase", "decrease"
DESIRED_CHANGES = (INCREASE, DECREASE)
ADMIT, REJECT, PASS, FAIL = "admit", "reject", "pass", "fail"

# THE VERIFIER'S OWN COPY of the frozen role x pole -> desired_change table.
#
# away_from_A(high) and toward_B(low) are the SAME desired change (both compute -delta);
# away_from_A(high) and toward_B(high) are OPPOSITE ones (-delta vs +delta). That is
# exactly why the arm key is the DESIRED CHANGE and not the pole direction: keying on the
# pole would merge the two arms that disagree and split the two that are identical.
SPEC_DESIRED_CHANGE = {
    ("away_from_A", "high"): DECREASE,
    ("away_from_A", "low"): INCREASE,
    ("toward_B", "high"): INCREASE,
    ("toward_B", "low"): DECREASE,
}

# W5's REAL physical set (62fbf8b): the temporal bundle ships a PREFLIGHT and NO verifier
# output. A per-bundle "verification" file was this verifier's own invention — the fixtures
# fabricated it, so the suite was green against an artifact set the producer never emits,
# and bind_bundle would have exited 1 on a real W5 directory.
#
# An external admission cannot live in the producer's directory anyway. The preflight is the
# producer's self-check; the ADMISSION is the ONE root envelope.
BUNDLE_FILES = {
    LANE_DIRECT: ("arm_bundle.json", "provenance.json", "verification.json"),
    LANE_TEMPORAL: ("arm_bundle.json", "temporal_provenance.json",
                    "temporal_preflight.json"),
    LANE_PATHWAY: ("arm_bundle.json", "pathway_provenance.json",
                   "pathway_verification.json", "convergence.json"),
}
PROVENANCE_OF = {lane: files[1] for lane, files in BUNDLE_FILES.items()}
# Only these lanes still carry a per-bundle report. Temporal's admission is the root envelope.
REPORT_OF = {LANE_DIRECT: "verification.json",
             LANE_PATHWAY: "pathway_verification.json"}
PREFLIGHT_OF = {LANE_TEMPORAL: "temporal_preflight.json"}
# A file that would be an EXTERNAL admission, sitting in the producer's own directory.
FORBIDDEN_IN_BUNDLE = {LANE_TEMPORAL: "temporal_verification.json"}

# Bindings whose BYTES a pathway count must be reconstructible from.
PATHWAY_BINDINGS = ("gene_set_membership", "target_universe", "masked_signatures",
                    "readout_universe")

# No p, no q, no FDR produced by spot — at any nesting depth, in any bundle.
FORBIDDEN_KEY_RE = re.compile(
    r"(^|_)(p|q)(_?val(ue)?s?)?($|_)|p_?adj|q_?value|fdr|bonferroni|benjamini",
    re.IGNORECASE)

PAIR_DERIVED_KEYS = ("pareto", "concordance", "joint_order", "joint_ordering",
                     "combined_score", "balanced_skew", "weighted_score",
                     "composite_score", "headline_rank")

# Batch commentary stays OUT of the reusable temporal chain (owner rule). The DiD estimand
# is population-level, the arm key already carries the ordered pair, and a batch field
# baked into a reusable arm is commentary travelling into every join that reuses it.
BATCH_KEYS = ("batch", "confound")

# The real schemas. Read from the release's own bytes; never assumed.
RELEASE_SCHEMA = "spot.stage01_v3_release.v1"
VIEW_SCHEMA = "spot.stage01_stage2_registry_view.v1"
VIEW_COMPONENT = "stage2_registry_view"
PORTABLE_KEY = "base_portable"


# --------------------------------------------------------------------------- #
# The verifier's own hashing and readers.
# --------------------------------------------------------------------------- #
# THE CANONICAL PER-PROGRAM PROJECTION RULE (Stage-1 AUTHORITATIVE).
#
#   value = sha256(canonical JSON of the ENTIRE program record, exactly as emitted in
#           stage01_stage2_registry_view.json), over records with base_portable == true.
#
# Canonical JSON: object keys SORTED; ARRAY ORDER PRESERVED. The arrays are the science —
# `panel_ensembl` and `control_ensembl` are the genes the projection is taken over, and
# sorting them would erase a real difference between two views that emitted them in
# different orders. `json.dumps(sort_keys=True)` sorts keys and never touches array order,
# which is exactly the rule; it is asserted by test rather than left as an accident of the
# serialiser.
PROJECTION_RULE_ID = (
    "spot.stage01_stage2_registry_view.program_record.canonical_sha256.v1")


def content_sha256(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                   allow_nan=False).encode("utf-8")).hexdigest()


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: str) -> Optional[Any]:
    """``None`` when the bytes are not a readable JSON document. Never raises."""
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _scan(obj: Any, hit, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if hit(str(k)):
                out.append(f"{path}.{k}")
            out += _scan(v, hit, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            out += _scan(v, hit, f"{path}[{i}]")
    return out


def forbidden_keys(obj: Any) -> list[str]:
    return _scan(obj, lambda k: bool(FORBIDDEN_KEY_RE.search(k)))


def pair_derived_keys(obj: Any) -> list[str]:
    return _scan(obj, lambda k: any(bad in k.lower() for bad in PAIR_DERIVED_KEYS))


def batch_keys(obj: Any) -> list[str]:
    return _scan(obj, lambda k: any(bad in k.lower() for bad in BATCH_KEYS))


# --------------------------------------------------------------------------- #
# The independent expectation.
# --------------------------------------------------------------------------- #
def scorer_programs(view: Optional[dict]) -> tuple[list[str], dict[str, Any]]:
    """RE-DERIVE the admitted program set from ``program.base_portable`` in the view.

    The scorer view (``spot.stage01_stage2_registry_view.v1``) carries ``base_portable``
    per program AND NOTHING ELSE — there is no ``base_portable_programs`` list, no
    ``base_portability_source_field``, no ``view_id`` and no per-program ``method_hash``.
    (An earlier version of this verifier read all four. They do not exist, so it derived an
    empty program set and REJECTED every real release — fail-closed, but blind.)

    The per-program projection id is therefore SPECIFIED, not read: it is the canonical
    hash of the program's whole record. Two releases that admit the same ids but disagree
    about a program's panel, control or coefficients are not the same scorer projection,
    and an arm keyed only on the id could be silently re-attributed between them.
    """
    if not isinstance(view, dict):
        return [], {}
    records = view.get("programs") or []
    # A program whose portability is UNSTATED is not silently treated as portable.
    if any(PORTABLE_KEY not in p for p in records):
        return [], {}
    # THE STAGE-2-PORTABLE SET, and only it. The raw scorer view carries MORE program
    # records than the release admits (th9_like is in the view and is NOT base-portable), so
    # a map derived over the raw entries would carry a program no arm can ever stand on, and
    # would then disagree with W5 and W11 by exactly one key.
    derived = sorted(str(p["program_id"]) for p in records if bool(p[PORTABLE_KEY]))
    projection = {str(p["program_id"]): content_sha256(p)
                  for p in records if bool(p[PORTABLE_KEY])}
    return derived, projection


def resolve_component(release: Optional[dict], name: str,
                      release_root: str) -> Optional[dict]:
    """Load ONE release component from an EXPLICITLY STAGED release root.

    Never a machine default: a component resolved from wherever the process happens to be
    running is a component nobody can point at afterwards. The staged bytes must match the
    raw AND canonical hashes the release pins, or the component is not the one it names.
    """
    comp = ((release or {}).get("components") or {}).get(name)
    if not isinstance(comp, dict) or not comp.get("path") or not release_root:
        return None
    rel = str(comp["path"])
    if os.path.isabs(rel) or ".." in rel.split("/"):
        return None
    path = os.path.join(release_root, rel)
    if not os.path.exists(path):
        return None
    if comp.get("raw_sha256") and file_sha256(path) != comp["raw_sha256"]:
        return None
    doc = load_json(path)
    if doc is None:
        return None
    if comp.get("canonical_content_sha256") and \
            content_sha256(doc) != comp["canonical_content_sha256"]:
        return None
    return doc


def selector_of(release: Optional[dict]) -> dict:
    return (release or {}).get("selector") or {}


def release_conditions(release: Optional[dict]) -> list[str]:
    """The condition universe — from ``release.selector.conditions``, IN ITS ORDER.

    NOT from a batch policy: batch is out of the reusable temporal chain entirely, and a
    confound diagnostic was never the right place to learn which conditions exist. The
    order is the release's (Rest, Stim8hr, Stim48hr — temporal, not alphabetical), and a
    reordered list is a DIFFERENT release: the pinned release hash is what says so.
    """
    return [str(c) for c in (selector_of(release).get("conditions") or [])]


def release_sources(release: Optional[dict]) -> list[str]:
    return [str(s) for s in (selector_of(release).get("pathway_sources") or [])]


def release_admitted(release: Optional[dict]) -> list[str]:
    return sorted(str(p) for p in (selector_of(release).get("admitted_programs") or []))


def ordered_pairs(conds: list[str]) -> list[tuple[str, str]]:
    c = sorted(conds)
    return [(a, b) for a in c for b in c if a != b]


def arm_key(lane: str, program: str, dc: str, ctx: dict) -> str:
    if lane == LANE_DIRECT:
        tail = [str(ctx.get("condition"))]
    elif lane == LANE_TEMPORAL:
        tail = [str(ctx.get("from_condition")), str(ctx.get("to_condition"))]
    else:
        tail = [str(ctx.get("condition")), str(ctx.get("gene_set_source"))]
    return "|".join([lane, program, dc] + tail)


def expected_slots(programs: list[str], conds: list[str],
                   sources: list[str]) -> dict[str, set]:
    """Every logical arm slot a complete run must fill. DERIVED, never declared."""
    out: dict[str, set] = {lane: set() for lane in LANES}
    for p in sorted(programs):
        for dc in DESIRED_CHANGES:
            for c in sorted(conds):
                out[LANE_DIRECT].add(arm_key(LANE_DIRECT, p, dc, {"condition": c}))
                for s in sorted(sources):
                    out[LANE_PATHWAY].add(arm_key(
                        LANE_PATHWAY, p, dc, {"condition": c, "gene_set_source": s}))
            for f, t in ordered_pairs(conds):
                out[LANE_TEMPORAL].add(arm_key(
                    LANE_TEMPORAL, p, dc, {"from_condition": f, "to_condition": t}))
    return out


def selection_capacity(n_programs: int, n_conditions: int) -> dict[str, int]:
    """Restated independently: n(n-1) within a condition, n*n across an ordered pair."""
    states = 2 * int(n_programs)
    pairs = int(n_conditions) * (int(n_conditions) - 1)
    within = int(n_conditions) * states * (states - 1)
    temporal = pairs * states * states
    return {"within_condition_selections": within, "temporal_selections": temporal,
            "total_valid_ordered_selections": within + temporal}


# --------------------------------------------------------------------------- #
# RECONSTRUCTION. A declared count is not evidence.
# --------------------------------------------------------------------------- #
def arm_records(ranking: Any) -> list[dict]:
    """The rows of a bound ranking artifact, whatever the producer calls the list.

    W5's native shape is ``records`` (the same rows nested in ``arm_bundle.json``);
    ``ranked`` is accepted as an alias. A reader that knew only one of them would silently
    see an empty ranking and count zero hits — which looks exactly like a real null result.
    """
    if not isinstance(ranking, dict):
        return []
    rows = ranking.get("records")
    if rows is None:
        rows = ranking.get("ranked")
    return [r for r in (rows or []) if isinstance(r, dict)]


def ranked_target_ids(ranking: Any) -> list[str]:
    """The target ids an arm actually RANKED. RETAINED-ROW semantics (W5).

    Every target is RETAINED in the rows, with ``rank: null`` when it is not rankable. So
    "in the ranking" is not "in the rows": a member that was retained but never ranked is
    NOT a hit, and counting rows instead of ranks would inflate every hit count by exactly
    the targets the arm could not evaluate — the ones least entitled to support a claim.
    """
    return [str(r.get("target_id")) for r in arm_records(ranking)
            if r.get("rank") is not None]


def n_ranked(ranking: Any) -> int:
    return len(ranked_target_ids(ranking))


# THE RANK ARITHMETIC, RE-DERIVED. Counts were never enough: a probe RESEALED a ranking with
# two ranks SWAPPED — every hash recomputed, every count unchanged — and it was ADMITTED,
# because this layer checked how MANY ranks there were, never WHICH target held which.
# Frozen rule: population = evaluable rows with a non-null value; order = value DESCENDING;
# tie-break = target_id ASCENDING; ranks = a contiguous 1..n.
SPEC_RANK_DIRECTION = "descending"
SPEC_RANK_TIE_BREAK = "target_id_ascending"


def rederive_ranks(ranking: Any) -> dict:
    """The ranks the arm's OWN values imply. Independent of the ranks it declared."""
    pop = [r for r in arm_records(ranking)
           if r.get("evaluable") and r.get("arm_value") is not None]
    pop.sort(key=lambda r: (-float(r["arm_value"]), str(r.get("target_id"))))
    return {str(r["target_id"]): i + 1 for i, r in enumerate(pop)}


def check_ranks(ranking: Any, arm_key: str) -> list[str]:
    """Every declared rank must be the rank that arm's own values produce."""
    want = rederive_ranks(ranking)
    got = {str(r.get("target_id")): r.get("rank") for r in arm_records(ranking)
           if r.get("rank") is not None}
    if got == want:
        return []
    wrong = sorted(t for t in set(want) | set(got) if want.get(t) != got.get(t))
    return [f"{arm_key}: {len(wrong)} target(s) do not hold the rank their own arm value "
            f"implies (e.g. {wrong[:3]}: declared "
            f"{[got.get(t) for t in wrong[:3]]}, re-derived {[want.get(t) for t in wrong[:3]]})"]


# --------------------------------------------------------------------------- #
# KEYED PROVENANCE. ``stage2_inputs[].role`` is forbidden.
#
# The probe RESEALED a role/value list and it was ADMITTED, because a generic
# label/value mini-language is not exact-allowlistable: anything can be smuggled through a
# field called "role", and "role" is reserved for join-time selection metadata. The inputs
# are a FIXED OBJECT whose keys name them directly.
# --------------------------------------------------------------------------- #
KEYED_STAGE2_INPUTS = ("direct_method_version", "direct_config_sha256",
                       "effect_source_sha256")
FORBIDDEN_PROVENANCE_KEYS = ("role", "pole", "pair_selection", "fate")


def check_keyed_provenance(prov: Any, bundle_id: str) -> list[str]:
    """``stage2_inputs`` is a fixed keyed object, and carries no selection vocabulary."""
    bad: list[str] = []
    rb = (prov or {}).get("run_binding") or {}
    inputs = rb.get("stage2_inputs")
    if isinstance(inputs, list):
        bad.append(f"{bundle_id}: stage2_inputs is a role/value LIST. It must be a fixed "
                   "keyed object — a generic label/value mini-language is not "
                   "exact-allowlistable, and 'role' is reserved for join-time selection "
                   "metadata")
    elif not isinstance(inputs, dict) or not inputs:
        bad.append(f"{bundle_id}: stage2_inputs is absent or not a keyed object")
    else:
        unknown = sorted(k for k in inputs if k not in KEYED_STAGE2_INPUTS)
        if unknown:
            bad.append(f"{bundle_id}: stage2_inputs carries unallowlisted key(s) {unknown}")
        # A KEY WITH A NULL VALUE IS NOT A BINDING. The canonical object must be complete:
        # W5 defaulted every one of these to None and validated none of them.
        missing = sorted(k for k in KEYED_STAGE2_INPUTS if not inputs.get(k))
        if missing:
            bad.append(f"{bundle_id}: stage2_inputs is missing or NULL for {missing} — a "
                       "keyed object whose values are null binds nothing")
    hits = _scan(prov, lambda k: k.lower() in FORBIDDEN_PROVENANCE_KEYS)
    if hits:
        bad.append(f"{bundle_id}: provenance carries selection vocabulary {hits[:4]}")
    return bad


def members_by_set(membership: Any) -> dict[str, set]:
    """Gene-set membership in the TARGET namespace, from the bound membership bytes."""
    if not isinstance(membership, dict):
        return {}
    return {str(sid): {str(g) for g in (s.get("genes_target") or [])}
            for sid, s in (membership.get("sets") or {}).items()}


def reconstruct_hits(membership: Any, ranking: Any) -> dict[str, int]:
    """n_hits_in_ranking, RECOMPUTED per set from the bytes the bundle bound.

    This is the number that decides whether an arm is headline-rankable. Before the
    bundle contract bound the ranking and the membership list, nobody could recompute it
    — so it was, in the end, taken on trust.
    """
    ranked = set(ranked_target_ids(ranking))
    return {sid: len(genes & ranked)
            for sid, genes in members_by_set(membership).items()}


def find_bundle_dir(root: str, name: str) -> Optional[str]:
    for base, dirs, _files in os.walk(root):
        for d in dirs:
            if d == name:
                return os.path.join(base, d)
    return None


class Report:
    """Every gate is recorded, passed or failed. A crash IS a verification failure."""

    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def gate(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append({"gate": name, "status": PASS if ok else FAIL,
                            "detail": "" if ok else detail})
        return bool(ok)

    @property
    def failed(self) -> list[str]:
        return [c["gate"] for c in self.checks if c["status"] == FAIL]

    def doc(self, verifier_id: str, schema_version: str, **extra: Any) -> dict[str, Any]:
        return {
            "schema_version": schema_version,
            "verifier_id": verifier_id,
            "generator_is_not_verifier": True,
            "fail_closed": True,
            "checks": self.checks,
            "n_failed": len(self.failed),
            "failed_gates": self.failed,
            "verdict": ADMIT if not self.failed else REJECT,
            **extra,
        }
