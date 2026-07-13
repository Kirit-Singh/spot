"""The NATIVE loader for Stage-1's generic release: `spot.stage01_v3_release.v1`.

Stage-1 `55899ac` ships a `schema`, a `selector` and `components`. Direct's legacy loader
(`trust.load_production_release`) accepts only `spot.stage01_release_manifest.v1` with an
`artifacts` map, so it refused the authoritative release on sight — Direct could not consume
the very release it is supposed to be bound to.

Behind that schema refusal sits the seam that actually matters:

    THE PRIMARY v3 REGISTRY DOES NOT CARRY `base_portable`. ONLY THE EXECUTABLE
    STAGE-2 REGISTRY VIEW DOES.

Portability is what decides whether a program can carry a reusable arm at all. A loader that
quietly read the primary registry would find no portability declared anywhere and would have
to invent a default — which is how a bundle ends up shipping arms the release never admitted.
So the view is bound and loaded BY NAME, and the primary registry is REFUSED as a stand-in.

WHAT IS PROVED HERE, FROM BYTES
-------------------------------
  * the release SELF HASH — Stage-1's own recipe: the canonical release minus the one field
    it is about to fill. (A self hash is not a trust anchor on its own — a forger reseals it.
    The anchors are the COMPONENT hashes below; the self hash proves the release document was
    not edited in place, which is a different and still useful claim);
  * every served component's RAW bytes against `raw_sha256`, and every JSON component's
    CANONICAL content against `canonical_content_sha256` — independently derived, never read;
  * the admitted program set, DERIVED here from `program.base_portable` in the view, then
    COMPARED with `selector.admitted_programs`. A disagreement refuses. The selector is a
    cross-check, never the source: a copied list decays the moment the view changes;
  * the scorer view's canonical hash, cross-checked between the component's real bytes, the
    release's `registry_scorer_view_canonical_sha256` and the selector's copy of it. All
    three must agree, and the one that decides is the one derived from bytes.

The scorer PROJECTION hash (`registry_scorer_projection_sha256`, 008c1da1…) is BOUND as
declared. It is a projection of the primary registry through Stage-1's own provenance-strip
rules, which live in Stage-1; Direct does not re-derive it and does not pretend to. It is
anchored by the verified self hash and travels into the bundle identity, so a release that
changed it cannot be swapped in behind a bundle that cited the old one.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from . import config, trust
from .hashing import content_hash, file_sha256

RELEASE_SCHEMA = "spot.stage01_v3_release.v1"
VIEW_SCHEMA = "spot.stage01_stage2_registry_view.v1"
VIEW_KIND = "executable_scorer_projection"

SELF_HASH_FIELD = "self_release_sha256"
SCORER_VIEW_COMPONENT = "stage2_registry_view"
PORTABLE_KEY = "base_portable"

LOADER_ID = "spot.stage02.direct.stage01_v3_release_loader.v1"

# Every one of these must be SERVED under the staged root and must verify. An omitted
# binding is fatal, never advisory — an unbound input is an untrusted input.
REQUIRED_COMPONENTS = ("registry_v3", "validation", "gate_spec",
                       SCORER_VIEW_COMPONENT, "effect_universe")

REFUSE_NOT_V3 = "not_a_stage01_v3_release"
REFUSE_SELF_HASH = "release_self_hash_does_not_cover_its_own_bytes"
REFUSE_COMPONENT_MISSING = "a_required_component_is_not_served_under_the_release_root"
REFUSE_COMPONENT_RAW = "a_component_does_not_match_its_pinned_raw_sha256"
REFUSE_COMPONENT_CANONICAL = "a_component_does_not_match_its_pinned_canonical_sha256"
REFUSE_PATH_ESCAPE = "a_component_path_escapes_the_staged_release_root"
REFUSE_PRIMARY_REGISTRY_SUBSTITUTION = "the_primary_registry_cannot_stand_in_for_the_view"
REFUSE_SCORER_VIEW_MISMATCH = "the_served_scorer_view_is_not_the_one_the_release_declares"
REFUSE_ADMITTED_MISMATCH = "the_selector_disagrees_with_the_view_about_base_portability"
REFUSE_NO_CONDITIONS = "the_release_selector_declares_no_conditions"


class Stage1ReleaseError(ValueError):
    """A Stage-1 v3 binding could not be proved. Refuse; never downgrade."""

    def __init__(self, reason: str, message: str):
        super().__init__(f"[{reason}] {message}")
        self.reason = reason


def _require(cond: bool, reason: str, msg: str) -> None:
    if not cond:
        raise Stage1ReleaseError(reason, msg)


@dataclass(frozen=True)
class Stage1V3Release(trust._Release):
    """The authoritative generic release. `programs` come from the EXECUTABLE VIEW."""

    conditions: tuple = ()
    admitted_programs: tuple = ()
    scorer: dict = field(default_factory=dict)
    # INTEGRATION: the release's OWN selector, exposed verbatim so that
    # `scorer_view.cross_check_selector` — W18's INDEPENDENT re-derivation of the admitted set
    # against the selector — actually fires on this release type. Without it that check reads
    # `selector_present: False` and quietly passes, which is the worst outcome available: a
    # gate that is present, green, and looking at nothing. This loader already refuses a
    # selector disagreement at load time; the two checks are deliberately redundant, and they
    # are derived independently of each other.
    selector: dict = field(default_factory=dict)


def is_v3_release(path: str) -> bool:
    """Cheap shape probe, so a caller can dispatch without catching an exception."""
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return False
    return isinstance(doc, dict) and str(doc.get("schema", "")) == RELEASE_SCHEMA


def self_hash(release: dict[str, Any]) -> str:
    """Stage-1's recipe, re-implemented rather than imported: the canonical release
    document minus the single field it is about to fill."""
    return content_hash({k: v for k, v in release.items() if k != SELF_HASH_FIELD})


def _resolve(root: str, rel_path: str, name: str) -> str:
    """A component path is FIXED BY THE RELEASE and resolved under the staged root.

    The path is repo-relative (`01_programs/app/data/...`). Nothing may point Stage-2
    outside the root it was handed — not an absolute path, not a `..` hop.
    """
    _require(not os.path.isabs(rel_path) and ".." not in rel_path.split("/"),
             REFUSE_PATH_ESCAPE,
             f"component {name!r} path {rel_path!r} must be a release-relative path "
             "under the staged release root")
    return os.path.join(root, rel_path)


def _verify_component(name: str, entry: dict[str, Any], root: str) -> dict[str, Any]:
    """Resolve one component and PROVE its bytes. Raw always; canonical for JSON."""
    rel_path = entry.get("path")
    if not rel_path:
        # DECLARED but not served — the real release's gitignored scores parquet. Its
        # canonical hash is still bound; there are simply no bytes here to check it against,
        # and the release says so out loud rather than leaving a reader to infer it.
        return {"name": name, "path": None, "served": False,
                "raw_sha256": None,
                "canonical_sha256": entry.get("canonical_content_sha256"),
                "doc": None}

    path = _resolve(root, str(rel_path), name)
    _require(os.path.exists(path), REFUSE_COMPONENT_MISSING,
             f"component {name!r} is declared at {rel_path!r} but is not served under the "
             "staged release root")

    raw_declared = str(entry.get("raw_sha256", "")).lower()
    raw = file_sha256(path)
    _require(raw == raw_declared, REFUSE_COMPONENT_RAW,
             f"component {name!r} raw bytes do not match the pinned raw_sha256 "
             f"(declared {raw_declared}, independently derived {raw})")

    doc = None
    canon_declared = str(entry.get("canonical_content_sha256", "")).lower()
    if str(rel_path).endswith(".json"):
        with open(path) as fh:
            doc = json.load(fh)
        derived = trust.canonical_content_sha256(doc)
        _require(derived == canon_declared, REFUSE_COMPONENT_CANONICAL,
                 f"component {name!r} canonical content does not match the pinned "
                 f"canonical_content_sha256 (declared {canon_declared}, independently "
                 f"derived {derived})")
    return {"name": name, "path": str(rel_path), "served": True, "raw_sha256": raw,
            "canonical_sha256": canon_declared, "doc": doc}


def _programs_from_view(view: dict[str, Any]) -> dict[str, dict]:
    """The EXECUTABLE view's programs, and the refusal that keeps the registry out.

    A document that does not declare `base_portable` on its programs is not the scorer view —
    it is (at best) the primary registry, which cannot say which programs may carry a
    reusable arm. Refuse it by name rather than defaulting the answer.
    """
    _require(str(view.get("schema_version", "")) == VIEW_SCHEMA,
             REFUSE_PRIMARY_REGISTRY_SUBSTITUTION,
             f"the component bound as the scorer view declares schema_version "
             f"{view.get('schema_version')!r}, not {VIEW_SCHEMA!r}. The primary registry "
             "cannot stand in for the executable Stage-2 registry view")
    _require(str(view.get("view_kind", "")) == VIEW_KIND,
             REFUSE_PRIMARY_REGISTRY_SUBSTITUTION,
             f"the scorer view declares view_kind {view.get('view_kind')!r}, not "
             f"{VIEW_KIND!r}")

    programs = view.get("programs")
    _require(isinstance(programs, list) and bool(programs),
             REFUSE_PRIMARY_REGISTRY_SUBSTITUTION,
             "the scorer view ships no programs")

    out: dict[str, dict] = {}
    for prog in programs:
        pid = prog.get("program_id")
        _require(bool(pid), REFUSE_PRIMARY_REGISTRY_SUBSTITUTION,
                 "a program in the scorer view has no program_id")
        _require(PORTABLE_KEY in prog, REFUSE_PRIMARY_REGISTRY_SUBSTITUTION,
                 f"program {pid!r} does not declare {PORTABLE_KEY!r}. Only the executable "
                 "Stage-2 registry view declares portability; the primary v3 registry does "
                 "not, and a program whose portability is unstated is never silently "
                 "treated as portable")
        out[str(pid)] = prog
    return out


def _scorer_block(view_doc: dict[str, Any], programs: dict[str, dict],
                  selector: dict[str, Any], view_canonical: str,
                  projection: Optional[str]) -> dict[str, Any]:
    """WHAT the admitted set was derived from — and the selector's claim, cross-checked."""
    derived = sorted(pid for pid, p in programs.items() if bool(p[PORTABLE_KEY]))
    excluded = sorted(pid for pid, p in programs.items() if not bool(p[PORTABLE_KEY]))

    declared = selector.get("admitted_programs")
    _require(isinstance(declared, list), REFUSE_ADMITTED_MISMATCH,
             "the release selector declares no admitted_programs to cross-check against")
    _require(sorted(str(p) for p in declared) == derived, REFUSE_ADMITTED_MISMATCH,
             "the admitted set DERIVED from the view's base_portable flags "
             f"{derived} disagrees with the release selector's admitted_programs "
             f"{sorted(str(p) for p in declared)}. The view's own bytes decide; a selector "
             "that disagrees with them is a release that cannot say which programs it "
             "admits")
    _require(bool(derived), REFUSE_ADMITTED_MISMATCH,
             "the release marks no program base_portable, so there is no arm to compute")

    return {
        "loader_id": LOADER_ID,
        "view_schema_version": str(view_doc.get("schema_version")),
        "view_kind": str(view_doc.get("view_kind")),
        # The release's OWN statement of the arm topology, carried through verbatim. Stage-2
        # derives its topology independently and CROSS-CHECKS against this; it never reads it
        # as the answer. Two derivations that disagree mean the release and the producer do
        # not think they are building the same thing.
        "arm_topology": selector.get("arm_topology") or {},
        "admitted_program_ids": derived,
        "excluded_program_ids": excluded,
        "n_admitted_programs": len(derived),
        "selector_admitted_programs": sorted(str(p) for p in declared),
        "selector_agrees": True,
        "registry_scorer_view_canonical_sha256": view_canonical,
        "registry_scorer_projection_sha256": projection,
        "derived_from_legacy_registry": False,
        "derived_from_primary_registry": False,
    }


_KIND_FOR_LANE = {
    config.LANE_PRODUCTION: "production",
    config.LANE_RESEARCH: "research",
}


def load(release_path: str, *, root: str, lane: str) -> Stage1V3Release:
    """Load and PROVE the authoritative Stage-1 generic release.

    ``root`` is the EXPLICIT staged release root that component paths resolve under. It is a
    required argument and never inferred from the release's own location: the release is
    handed to Stage-2 as a staged copy, and a loader that guessed its root could be walked
    into a different tree by a relative path.
    """
    _require(os.path.exists(release_path), REFUSE_NOT_V3,
             f"Stage-1 v3 release not found: {os.path.basename(release_path)}")
    with open(release_path) as fh:
        try:
            release = json.load(fh)
        except ValueError as exc:
            raise Stage1ReleaseError(REFUSE_NOT_V3,
                                     f"Stage-1 v3 release is not JSON: {exc}") from exc

    _require(isinstance(release, dict)
             and str(release.get("schema", "")) == RELEASE_SCHEMA,
             REFUSE_NOT_V3,
             f"Stage-1 v3 release: 'schema' must be {RELEASE_SCHEMA!r} (got "
             f"{release.get('schema')!r}). A legacy release manifest, or a bare registry, "
             "is not a generic release and may not be loaded as one")

    declared_self = str(release.get(SELF_HASH_FIELD, "")).lower()
    derived_self = self_hash(release)
    _require(declared_self == derived_self, REFUSE_SELF_HASH,
             f"the release's {SELF_HASH_FIELD} does not cover its own bytes (declared "
             f"{declared_self}, independently derived {derived_self})")

    components = release.get("components") or {}
    missing = [c for c in REQUIRED_COMPONENTS if c not in components]
    _require(not missing, REFUSE_COMPONENT_MISSING,
             f"Stage-1 v3 release: required components omitted: {missing}. An omitted "
             "binding is fatal, never advisory.")

    # EVERY declared component is verified, not just the ones Direct reads: a release whose
    # unread components had drifted would still be a release nobody could reproduce.
    verified = {name: _verify_component(name, entry, root)
                for name, entry in sorted(components.items())}

    view_entry = verified[SCORER_VIEW_COMPONENT]
    _require(view_entry["doc"] is not None, REFUSE_PRIMARY_REGISTRY_SUBSTITUTION,
             "the scorer-view component must be a served JSON document")
    view_doc = view_entry["doc"]
    programs = _programs_from_view(view_doc)

    # The view's canonical hash, DERIVED from its bytes, must be what the release advertises
    # in both places it advertises it. A bundle binds this hash; if the release could
    # advertise one view and ship another, the bundle could be re-attributed to a program set
    # it never scored.
    view_canonical = view_entry["canonical_sha256"]
    for where, declared in (
            ("registry_scorer_view_canonical_sha256",
             release.get("registry_scorer_view_canonical_sha256")),
            ("selector.registry_scorer_view_canonical_sha256",
             (release.get("selector") or {}).get(
                 "registry_scorer_view_canonical_sha256"))):
        if declared is None:
            continue
        _require(str(declared).lower() == view_canonical, REFUSE_SCORER_VIEW_MISMATCH,
                 f"the release advertises {where} = {declared}, but the scorer view it "
                 f"actually ships canonicalises to {view_canonical}")

    selector = release.get("selector") or {}
    conditions = [str(c) for c in (selector.get("conditions") or [])]
    _require(bool(conditions), REFUSE_NO_CONDITIONS,
             "the release selector declares no conditions, so nothing can say which "
             "physical bundles a complete Direct release consists of")

    projection = release.get("registry_scorer_projection_sha256")
    scorer = _scorer_block(view_doc, programs, selector, view_canonical,
                           None if projection is None else str(projection))

    # ---- the Stage-1 hard gates, and what this loader honestly does NOT claim ----
    #
    # The v3 validation is NOT the legacy gate shape. It has no (program, condition, gate_id,
    # value) rows to re-derive a verdict from: it stores `stage1_selectable_by_condition`
    # per condition, and — by the gate spec's own pre-registered principle — keeps
    # `stage2_base_portability` SEPARATE from Stage-1 measurement validity.
    #
    # So this loader does not pretend to re-derive Stage-1's per-condition selectability. It
    # would have to read a stored boolean to do it, and a stored verdict is exactly what
    # Stage-2 refuses to believe. `selectable_pairs` is therefore EMPTY — fail-closed. Any
    # PAIR path that asks this release whether a (program, condition) is production-selectable
    # gets False, which is the safe answer and, against the frozen Stage-1 (0/33 selectable),
    # also the true one.
    #
    # What an ARM's admission actually turns on is `base_portable`, and that IS derived here,
    # from the view's own bytes. The all-arm producer consults nothing else — it has no pair.
    # The validation and gate spec are still BOUND by verified hash, so a release that
    # changed either cannot be swapped in behind a bundle that cited it.
    selectable: frozenset = frozenset()
    evidence = {
        "release_schema": RELEASE_SCHEMA,
        "rule_id": config.SELECTABILITY_RULE_ID,
        "stored_boolean_read": False,
        "stage1_selectability_rederived_by_stage2": False,
        "stage1_selectability_not_rederived_because":
            "the v3 validation stores per-condition selectability rather than the "
            "(program, condition, gate_id, value) rows a verdict can be recomputed from; "
            "Stage-2 will not substitute a stored boolean for a derivation",
        "n_production_selectable": 0,
        "arm_admission_rule": "base_portable, derived from the executable scorer view",
        "validation_canonical_sha256": verified["validation"]["canonical_sha256"],
        "gate_spec_canonical_sha256": verified["gate_spec"]["canonical_sha256"],
        "confers_production_eligibility": (lane == config.LANE_PRODUCTION),
        "confers_stage3_eligibility": (lane == config.LANE_PRODUCTION),
    }

    hashes: dict[str, Any] = {
        "release_schema": RELEASE_SCHEMA,
        "release_raw_sha256": file_sha256(release_path),
        "release_self_sha256": derived_self,
        "method_version": str(release.get("method_version", "")),
        "registry_scorer_view_canonical_sha256": view_canonical,
        "registry_scorer_projection_sha256": scorer["registry_scorer_projection_sha256"],
        # INTEGRATION: the un-prefixed names `scorer_view.view()` reaches for when it emits the
        # release's own scorer hashes. Same two values, published under the names the consumer
        # asks by, so the view reports them instead of silently emitting null.
        "scorer_view_canonical_sha256": view_canonical,
        "scorer_projection_sha256": scorer["registry_scorer_projection_sha256"],
        "stage1_registry_sha256": release.get("stage1_registry_sha256"),
        "effect_universe_id": release.get("effect_universe_id"),
        "source_h5ad_sha256": release.get("source_h5ad_sha256"),
        "source_hf_revision": release.get("source_hf_revision"),
        "scores_canonical_content_sha256":
            release.get("scores_canonical_content_sha256"),
        "coordinates_sha256": release.get("coordinates_sha256"),
    }
    for name, v in verified.items():
        if v["raw_sha256"]:
            hashes[f"{name}_raw_sha256"] = v["raw_sha256"]
        if v["canonical_sha256"]:
            hashes[f"{name}_canonical_sha256"] = v["canonical_sha256"]

    method_version = str(release.get("method_version", ""))
    _require(bool(method_version), REFUSE_NOT_V3,
             "Stage-1 v3 release: method_version is a required binding")

    return Stage1V3Release(
        kind=_KIND_FOR_LANE.get(lane, "fixture"),
        method_version=method_version,
        programs=programs,
        hashes=hashes,
        selectable_pairs=selectable,
        gate_evidence=evidence,
        conditions=tuple(conditions),
        admitted_programs=tuple(scorer["admitted_program_ids"]),
        scorer=scorer,
        selector=dict(selector),
    )
