"""THE BOUND STAGE-1 v3 RELEASE: the program axis and the condition universe, DERIVED.

WHICH SHAPE, AND WHY THE OTHER ONE IS REFUSED BY NAME
----------------------------------------------------
The CURRENT release is ``spot.stage01_v3_release.v1``: a ``selector`` (what Stage-2 may
use) and ``components`` (the files, each pinned by hash). The LEGACY manifest was
``spot.stage01_release_manifest.v1`` with an ``artifacts`` block. They are different
claims, and a Stage-2 lane that quietly accepted whichever one it found would bind to
whichever happened to be lying around. So the legacy shape is refused BY NAME, at a named
gate, and an ``artifacts`` block appearing beside ``components`` is still the legacy shape.

WHERE THE FILES ARE
-------------------
Against an EXPLICITLY STAGED release root, passed in by the caller. Never a machine
default, never a path baked into this module, and never a path read out of the release
itself: an absolute or upward-escaping component path is refused, because a release that
can point Stage-2 anywhere on the filesystem is not a binding.

THE PROGRAM AXIS IS DERIVED, NOT READ
-------------------------------------
The executable scorer view (``spot.stage01_stage2_registry_view.v1``) carries
``base_portable`` on each program and NOTHING ELSE that names the portable set: there is
no ``base_portable_programs`` list, no ``base_portability_source_field``, no ``view_id``
and no per-program ``method_hash``. So:

    an ADMITTED program is one the view declares ``base_portable = true`` and for which it
    ships a non-empty ``panel_ensembl`` AND ``control_ensembl``

and the COUNT falls out of that. The derived set is then compared with the release's own
``selector.admitted_programs`` — two independent statements of the same fact, and a
disagreement is fatal rather than resolved in favour of either.

A base-portable program with no projectable axis is REFUSED, not skipped: skipping it
leaves a complete-LOOKING bundle with an arm missing from it.

TWO BINDING HASHES, TWO DIFFERENT QUESTIONS
-------------------------------------------
``scorer_view_sha256``        the canonical hash of the WHOLE view. "Is this the same
                              release?" Everything in the view moves it.
``scorer_projection_sha256``  the canonical hash of the ADMITTED PROGRAM AXIS only — each
                              admitted program projected to exactly the fields an arm
                              depends on. "Is this the same program axis?" A change to a
                              non-portable program does not move it, and should not: it
                              cannot change an arm.

A per-program identity, where one is needed, is an independently hashed canonical
PROJECTION RECORD of the program — because the view ships no per-program hash to read.

THE CONDITION UNIVERSE IS THE RELEASE'S, NOT A POLICY FILE'S
------------------------------------------------------------
``selector.conditions`` is the authority. The ordered pairs are DERIVED from it — n
conditions give n*(n-1) ordered pairs — so "six" is a consequence of a three-condition
release and never a constant. This module names no condition and no program: one that did
would confirm the topology it was told to expect instead of the one that shipped.

The list is ORDERED, and the order is CONTENT: it is the time axis. A release that
reordered it would ship the same ordered pairs while telling every reader a different story
about which way time runs, so ``require_conditions`` refuses a reordering against a pinned
universe.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from . import rules
from .canonical import content_hash, file_sha256, sha256_hex

RELEASE_SCHEMA = "spot.stage01_v3_release.v1"
LEGACY_RELEASE_SCHEMA = "spot.stage01_release_manifest.v1"
SCORER_VIEW_SCHEMA = "spot.stage01_stage2_registry_view.v1"

RELEASE_FILENAME = "release.json"
PORTABLE_FLAG = "base_portable"

PROGRAM_PROJECTION_ID = "spot.stage02.temporal.arm.program_projection.v1"
SCORER_PROJECTION_ID = "spot.stage02.temporal.arm.scorer_projection.admitted_axis.v1"

ADMISSION_RULE_ID = "spot.stage02.temporal.arm.program_admission.base_portable.v1"

# THE FROZEN RELEASE'S OWN VALUES, from the authoritative inspection of the Stage-1 v3
# release at 55899ac. They are recorded so a production caller can PIN them — they are not
# applied by default and there is no default: a pin nobody supplied must never silently
# pass, and this repository ships no release to check them against.
FROZEN_SCORER_VIEW_SHA256_PREFIX = "5d1d8c36"
FROZEN_SCORER_PROJECTION_SHA256_PREFIX = "008c1da1"
FROZEN_RELEASE_SELF_SHA256_PREFIX = "125ebfc"

# THE PER-PROGRAM PROJECTION IDENTITY. Specified HERE because the scorer view ships no
# per-program hash to read: each admitted program is projected to exactly the fields an arm
# depends on, hashed, and the sorted list of those hashes is hashed again. Stated as a rule
# so the producer and the verifier compute the SAME number rather than two numbers that
# happen to agree today.
# THE CANONICAL PER-PROGRAM RULE. Stage-1 is authoritative, and this is its rule, restated
# and IMPLEMENTED AGAIN here rather than copied across lanes:
#
#   from the bound stage01_stage2_registry_view, take the records with base_portable = true;
#   for each, the value is SHA-256 of the canonical JSON of the ENTIRE program record
#   EXACTLY as Stage-1 emitted it — object keys canonically sorted, ARRAY ORDER PRESERVED.
#
# The whole record, not a projection of it: a four-field summary would hash the same after
# Stage-1 changed a field the summary never looked at, and the map would keep vouching for a
# program it no longer describes.
#
# ARRAY ORDER IS PRESERVED, NOT SORTED. A panel is an ordered list as Stage-1 emitted it;
# sorting it before hashing would make a reordered panel hash identical to the original, and
# a reordering is a different record.
PER_PROGRAM_PROJECTION_RULE_ID = (
    "spot.stage01_stage2_registry_view.program_record.canonical_sha256.v1")
PER_PROGRAM_PROJECTION_RULE = (
    "sha256(canonical JSON of the ENTIRE program record as emitted in "
    "stage01_stage2_registry_view.json; object keys canonically sorted, array order "
    "preserved), for exactly the records with base_portable=true")

# THE SELECTOR IDENTITY. The condition SEQUENCE, in the order the release declares it — the
# time axis. A sorted condition list is not a sequence, and a lane that kept only the sorted
# one has thrown the arrow of time away and cannot get it back.
SELECTOR_IDENTITY_RULE_ID = (
    "spot.stage02.temporal.arm.selector_identity.ordered_condition_sequence.v1")


class ReleaseRefused(ValueError):
    """The bound release is not the one Stage-2 may read. Refuse; never fall back."""


@dataclass(frozen=True)
class BoundRelease:
    """A proved Stage-1 v3 release. Every field here was DERIVED, not believed."""
    release_root: str
    schema_version: str
    method_version: str
    conditions: tuple[str, ...]
    ordered_pairs: tuple[tuple[str, str], ...]
    admitted_programs: dict[str, dict[str, Any]]
    scorer_view: dict[str, Any]
    scorer_view_programs: dict[str, dict[str, Any]]
    scorer_view_sha256: str
    scorer_view_raw_sha256: str
    scorer_projection_sha256: str
    program_projection_sha256: dict[str, str]
    per_program_projection_sha256: str
    release_self_sha256: str
    component_hashes: dict[str, str]

    @property
    def n_admitted_programs(self) -> int:
        return len(self.admitted_programs)

    @property
    def n_logical_arms(self) -> int:
        """A CONSEQUENCE: programs x desired changes x ordered pairs. Never a constant."""
        return (len(self.admitted_programs) * len(rules.DESIRED_CHANGES)
                * len(self.ordered_pairs))

    def binding_block(self) -> dict[str, Any]:
        """What a downstream lane must bind in order to name THIS release."""
        return {
            "release_schema_version": self.schema_version,
            "release_method_version": self.method_version,
            "conditions": list(self.conditions),
            "n_conditions": len(self.conditions),
            "n_ordered_pairs": len(self.ordered_pairs),
            "programs": sorted(self.admitted_programs),
            "n_programs": len(self.admitted_programs),
            "n_logical_arms": self.n_logical_arms,
            "program_admission_rule_id": ADMISSION_RULE_ID,
            "registry_scorer_view_sha256": self.scorer_view_sha256,
            "scorer_projection_id": SCORER_PROJECTION_ID,
            "scorer_projection_sha256": self.scorer_projection_sha256,
            "per_program_projection_rule_id": PER_PROGRAM_PROJECTION_RULE_ID,
            "per_program_projection_sha256": self.per_program_projection_sha256,
            "selector_identity_rule_id": SELECTOR_IDENTITY_RULE_ID,
            "selector_condition_sequence": list(self.conditions),
            "stage1_release_self_sha256": self.release_self_sha256,
        }


def _refuse(cond: bool, msg: str) -> None:
    if not cond:
        raise ReleaseRefused(msg)


def _resolve(root: str, rel_path: Any, what: str) -> str:
    """Resolve a component path INSIDE the staged root. Absolute or escaping is refused."""
    p = str(rel_path or "")
    _refuse(bool(p), f"component {what!r} declares no path")
    _refuse(not os.path.isabs(p) and not (len(p) > 1 and p[1] == ":"),
            f"component {what!r} declares the absolute path {p!r}. A component path is "
            "relative to the STAGED release root; an absolute one points Stage-2 at a "
            "machine, and a release that can do that is not a binding")
    full = os.path.normpath(os.path.join(root, p))
    _refuse(os.path.commonpath([os.path.abspath(full), root]) == root,
            f"component {what!r} path {p!r} escapes the staged release root")
    _refuse(os.path.exists(full), f"component {what!r} is missing at {p!r}")
    return full


def _load_component(root: str, name: str, entry: Any) -> dict[str, Any]:
    _refuse(isinstance(entry, dict), f"component {name!r} is malformed")
    path = _resolve(root, entry.get("path"), name)
    raw = file_sha256(path)

    declared_raw = str(entry.get("raw_sha256", "") or "").lower()
    if declared_raw:
        _refuse(raw == declared_raw,
                f"component {name!r} raw_sha256 does not match its bytes on disk "
                f"(declared {declared_raw}, independently derived {raw})")

    doc = None
    if path.endswith(".json"):
        with open(path) as fh:
            doc = json.load(fh)
        declared_canon = str(entry.get("canonical_sha256", "") or "").lower()
        derived = content_hash(doc)
        if declared_canon:
            _refuse(derived == declared_canon,
                    f"component {name!r} canonical content does not match its declared "
                    f"canonical_sha256 (declared {declared_canon}, independently derived "
                    f"{derived})")
    return {"name": name, "path": path, "raw_sha256": raw, "doc": doc}


def program_projection(prog: dict[str, Any]) -> dict[str, Any]:
    """THE canonical per-program record: the WHOLE record, exactly as Stage-1 emitted it.

    Not a projection of it. A four-field summary would hash identically after Stage-1
    changed a field the summary never looked at, and the map would go on vouching for a
    program it no longer describes.

    Returned verbatim — the canonical form (keys sorted, ARRAY ORDER PRESERVED) is applied
    by the hash, not by this function. Sorting the panel here would make a reordered panel
    hash the same as the original, and a reordering is a different record.
    """
    return dict(prog)


def scorer_projection(view: dict[str, Any]) -> dict[str, Any]:
    """The ADMITTED PROGRAM AXIS, canonically projected. The thing an arm actually reads."""
    admitted = _derive_admitted(view)
    programs = [program_projection(p) for p in
                (admitted[pid] for pid in sorted(admitted))]
    return {
        "projection_id": SCORER_PROJECTION_ID,
        "portable_flag": PORTABLE_FLAG,
        "programs": programs,
        "n_programs": len(programs),
    }


def _derive_admitted(view: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every base-portable, PROJECTABLE program the view ships. The count is derived."""
    programs = view.get("programs")
    _refuse(isinstance(programs, list) and bool(programs),
            "the scorer view ships no programs; the temporal program axis is DERIVED from "
            "the view, and there is nothing here to derive it from")

    admitted: dict[str, dict[str, Any]] = {}
    unprojectable: list[str] = []
    for prog in programs:
        _refuse(isinstance(prog, dict) and bool(prog.get("program_id")),
                "the scorer view ships a program with no program_id")
        if prog.get(PORTABLE_FLAG) is not True:
            continue                       # not base-portable: not in the base topology
        pid = str(prog["program_id"])
        panel, control = prog.get("panel_ensembl"), prog.get("control_ensembl")
        if not (isinstance(panel, list) and panel and isinstance(control, list)
                and control):
            unprojectable.append(pid)
            continue
        admitted[pid] = prog

    _refuse(not unprojectable,
            f"programs {sorted(unprojectable)} are declared {PORTABLE_FLAG}=true but ship "
            "no projectable panel/control. They are refused, not skipped: a skipped "
            "program leaves a complete-LOOKING bundle with an arm missing from it")
    _refuse(bool(admitted),
            f"no program in the bound release is {PORTABLE_FLAG}=true; a bundle with no "
            "program axis is not a degenerate bundle - it is not a bundle")
    return admitted


def load_release(release_root: str, filename: str = RELEASE_FILENAME) -> BoundRelease:
    """Load and PROVE the bound Stage-1 v3 release from an EXPLICITLY STAGED root."""
    root = os.path.abspath(str(release_root))
    _refuse(os.path.isdir(root),
            f"the staged release root {os.path.basename(root)!r} is not a directory. The "
            "root is passed in, never defaulted: a verifier that guessed one would bind to "
            "whatever release happened to be on the machine that ran it")
    path = os.path.join(root, filename)
    _refuse(os.path.exists(path), f"no {filename!r} in the staged release root")
    with open(path) as fh:
        doc = json.load(fh)

    # ---- gate: the release SHAPE. The legacy manifest is refused BY NAME. ----
    declared = str(doc.get("schema_version", ""))
    _refuse("artifacts" not in doc and declared != LEGACY_RELEASE_SCHEMA,
            f"this is the LEGACY Stage-1 release shape ({LEGACY_RELEASE_SCHEMA!r}, with an "
            f"'artifacts' block). Stage-2 binds the CURRENT release {RELEASE_SCHEMA!r} "
            "(selector + components); the two are different claims and accepting whichever "
            "one is present would bind to whichever one happened to be lying around")
    _refuse(declared == RELEASE_SCHEMA,
            f"release schema_version must be {RELEASE_SCHEMA!r}, got {declared!r}")

    selector = doc.get("selector")
    _refuse(isinstance(selector, dict), "the release ships no 'selector'")
    components = doc.get("components")
    _refuse(isinstance(components, dict) and bool(components),
            "the release ships no 'components'")

    loaded = {name: _load_component(root, name, entry)
              for name, entry in sorted(components.items())}

    # ---- gate: the scorer view is found by its OWN schema, not by a key name ----
    views = [c for c in loaded.values()
             if isinstance(c["doc"], dict)
             and str(c["doc"].get("schema_version", "")) == SCORER_VIEW_SCHEMA]
    _refuse(len(views) == 1,
            f"the release must ship exactly one {SCORER_VIEW_SCHEMA!r} component; it ships "
            f"{len(views)}. The view is found BY ITS SCHEMA, because a key name is a label "
            "somebody chose and two views would mean picking one")
    view = views[0]["doc"]

    admitted = _derive_admitted(view)

    # ---- gate: the DERIVED axis must equal the release's OWN selector ----
    declared_admitted = selector.get("admitted_programs")
    _refuse(isinstance(declared_admitted, list) and bool(declared_admitted),
            "selector.admitted_programs is absent; the derived program axis has nothing to "
            "be checked against, and one statement of a fact is not a check")
    _refuse(sorted(admitted) == sorted(str(p) for p in declared_admitted),
            "the program axis DERIVED from base_portable disagrees with the release's own "
            f"selector.admitted_programs: derived {sorted(admitted)}, declared "
            f"{sorted(str(p) for p in declared_admitted)}. Two independent statements of "
            "the same fact disagree; neither is preferred and the release is refused")

    # ---- gate: the condition universe, from the release ----
    conditions = selector.get("conditions")
    _refuse(isinstance(conditions, list) and bool(conditions),
            "selector.conditions is absent; the condition universe is the RELEASE's, and a "
            "temporal lane that took it from a policy file would compute a time axis the "
            "release never released")
    conds = tuple(str(c) for c in conditions)
    try:
        pairs = tuple(rules.ordered_pairs(conds))
    except rules.RuleViolation as exc:
        raise ReleaseRefused(f"selector.conditions: {exc}") from exc

    return BoundRelease(
        release_root=root,
        schema_version=declared,
        method_version=str(doc.get("method_version", "")),
        conditions=conds,
        ordered_pairs=pairs,
        admitted_programs=admitted,
        scorer_view=view,
        scorer_view_programs=dict(admitted),
        scorer_view_sha256=content_hash(view),
        scorer_view_raw_sha256=views[0]["raw_sha256"],
        scorer_projection_sha256=content_hash(scorer_projection(view)),
        program_projection_sha256={pid: content_hash(program_projection(prog))
                                   for pid, prog in admitted.items()},
        per_program_projection_sha256=content_hash(
            [{"program_id": pid, "projection_sha256": content_hash(program_projection(prog))}
             for pid, prog in sorted(admitted.items())]),
        release_self_sha256=file_sha256(path),
        component_hashes={name: c["raw_sha256"] for name, c in loaded.items()},
    )


def require_conditions(bound: BoundRelease, expected) -> None:
    """The release's condition universe must be EXACTLY the pinned one, IN ORDER.

    Order is content: the condition list IS the time axis. A release that reordered it
    would ship the same ordered pairs while telling every reader a different story about
    which way time runs.
    """
    got, want = list(bound.conditions), [str(c) for c in expected]
    _refuse(sorted(got) == sorted(want),
            f"the release's conditions {got} do not match the pinned universe {want}; a "
            "forged or missing condition is refused, never reconciled")
    _refuse(got == want,
            f"the release's conditions {got} are the pinned set in a different ORDER than "
            f"{want}. The order is the time axis, and reordering it is a different claim")


def require_scorer_binding(bound: BoundRelease, *, view_prefix: Optional[str] = None,
                           projection_prefix: Optional[str] = None) -> None:
    """Check the caller's PINNED scorer-view / scorer-projection prefixes. No default."""
    if view_prefix:
        got = bound.scorer_view_sha256
        _refuse(got.startswith(str(view_prefix).lower()),
                f"scorer_view canonical hash {got[:16]}... does not match the pinned "
                f"prefix {view_prefix!r}; this is a different Stage-1 release")
    if projection_prefix:
        got = bound.scorer_projection_sha256
        _refuse(got.startswith(str(projection_prefix).lower()),
                f"scorer_projection hash {got[:16]}... does not match the pinned prefix "
                f"{projection_prefix!r}; this is a different program axis")


def raw_sha256(data: bytes) -> str:
    return sha256_hex(data)
