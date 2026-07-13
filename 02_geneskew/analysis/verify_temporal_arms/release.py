"""THE BOUND STAGE-1 v3 RELEASE — read exactly as Stage-1 ships it.

THE NATIVE BYTES, AND WHY THEY ARE NOT TRANSLATED
-------------------------------------------------
The release is ``stage01_v3_release.json``. It keys its schema under ``schema``. Its component
paths are REPO-RELATIVE, one component is staged outside the repository and bound by hash
alone, and it declares its own id under ``self_release_sha256``.

None of that is negotiable and none of it is aliased. A verifier that accepted a rewritten
copy, or tolerated the old key "just in case", would be verifying something nobody shipped —
and the run that exposed this REJECTED for a missing ``release.json`` while the real release
sat beside it, entirely present. The correct response to native bytes that do not match an
assumption is to fix the assumption.

WHAT IS RE-DERIVED, NOT READ
----------------------------
The release's own id (by its declared rule), every in-repo component's raw and canonical
content hash, the admitted program axis (from ``base_portable`` in the view it binds), the
condition universe and its ORDER, and the scorer identity — the view's canonical hash AND the
registry scorer projection, computed by Stage-1's own rule from the registry the release
binds. Whether the release's declared scorer identity follows from its own registry is exactly
the question, and reading the number it advertises would not answer it.

THE PROGRAM AXIS IS DERIVED, NOT READ
-------------------------------------
An ADMITTED program is one the view declares ``base_portable = true`` and ships a non-empty
panel and control for; the COUNT falls out. That derived set is then compared with the
release's own ``selector.admitted_programs`` — two independent statements of one fact, and a
disagreement is fatal rather than resolved in favour of either.

THE CONDITION UNIVERSE IS THE RELEASE'S
---------------------------------------
``selector.conditions``, and its ORDER is content: it is the time axis. n conditions give
n*(n-1) ordered pairs, so "six" is a consequence of a three-condition release and never a
constant. This module names no condition and no program.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from . import rules
from .canonical import content_hash, file_sha256, sha256_hex
from .stage1_rules import (  # noqa: F401  (re-exported: one import site for a caller)
    ROLE_PROGRAM_REGISTRY,
    ROLE_SCORER_VIEW,
    SCORER_PROJECTION_ID,
    SCORER_PROJECTION_PROV_PROG,
    SCORER_PROJECTION_PROV_TOP,
    SELF_HASH_FIELDS,
    canonical_content_sha256,
    registry_scorer_projection,
)

RELEASE_SCHEMA = "spot.stage01_v3_release.v1"
LEGACY_RELEASE_SCHEMA = "spot.stage01_release_manifest.v1"
SCORER_VIEW_SCHEMA = "spot.stage01_stage2_registry_view.v1"

# The flag the scorer view carries. Named once.
PORTABLE_FLAG = "base_portable"


# THE NATIVE STAGE-1 RELEASE. Its own filename, its own key, its own root convention.
#
# The release declares its schema under ``schema`` — NOT ``schema_version`` — and its
# component paths are REPO-RELATIVE, not relative to the file that names them. Reading it any
# other way is reading a release that does not exist: the correct response to native bytes
# that do not match an assumption is to fix the assumption, never to translate the bytes. An
# alias or a rewritten copy would mean the thing verified is not the thing that shipped.
RELEASE_FILENAME = "stage01_v3_release.json"
SCHEMA_KEY = "schema"
SELF_HASH_FIELD = "self_release_sha256"

# W20's own rule, restated: the canonical hash of the document excluding its own id field.
SELF_HASH_RULE = "sha256(canonical JSON excluding self_release_sha256)"

# The component hash fields the native release actually carries.
COMPONENT_RAW = "raw_sha256"
COMPONENT_CANON = "canonical_content_sha256"

ADMISSION_RULE_ID = "spot.stage02.temporal.arm.program_admission.base_portable.v1"

# THE FROZEN RELEASE'S OWN VALUES. No longer an "authoritative inspection" taken on trust:
# ``TestTheREALStage1Release`` loads the actual release and RE-DERIVES both, so these are now
# measured, not declared. They remain here as the pins a production caller may supply.
FROZEN_SCORER_VIEW_SHA256_PREFIX = "5d1d8c36"
FROZEN_SCORER_PROJECTION_SHA256_PREFIX = "008c1da1"
FROZEN_RELEASE_SELF_SHA256_PREFIX = "2262430"

# THE PER-PROGRAM PROJECTION IDENTITY — Stage-1's rule: the sha256 of the canonical JSON of
# the ENTIRE program record as emitted, keys sorted, ARRAY ORDER PRESERVED, for exactly the
# base_portable records. The whole record, because a summary hashes the same after Stage-1
# changes a field it never looked at; order preserved, because a reordering is a different
# record and sorting first would hide it.
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
    release_path: str
    content_root: str
    self_release_sha256: str
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
    """Resolve a component path INSIDE the content root. Absolute or escaping is refused.

    The native release's component paths are REPO-RELATIVE — they resolve against the content
    root, not against the directory that happens to hold the release file.
    """
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
    """One component. IN-REPO ones are reopened and rehashed; OUT-OF-REPO ones are bound.

    A component staged outside the repository names a ``location`` and its hashes, not a
    path. It is still a BINDING — it just is not a file this verifier can open. What it may
    NOT be is unbound: a component that declares neither a path nor a hash names nothing.
    """
    _refuse(isinstance(entry, dict), f"component {name!r} is malformed")

    if not entry.get("path"):
        staged = str(entry.get("raw_sha256_staged") or entry.get(COMPONENT_RAW) or "")
        canon = str(entry.get(COMPONENT_CANON) or "")
        _refuse(bool(staged or canon),
                f"component {name!r} is staged outside the repository and declares no hash. "
                "A component bound by neither a path nor a hash names nothing at all")
        return {"name": name, "path": None, "raw_sha256": staged or canon,
                "role": entry.get("role"), "in_repo": False, "doc": None}

    path = _resolve(root, entry.get("path"), name)
    raw = file_sha256(path)

    declared_raw = str(entry.get(COMPONENT_RAW, "") or "").lower()
    if declared_raw:
        _refuse(raw == declared_raw,
                f"component {name!r} raw_sha256 does not match its bytes on disk "
                f"(declared {declared_raw}, independently derived {raw})")

    doc = None
    if path.endswith(".json"):
        with open(path) as fh:
            doc = json.load(fh)
        declared_canon = str(entry.get(COMPONENT_CANON, "") or "").lower()
        derived = canonical_content_sha256(doc)
        if declared_canon:
            _refuse(derived == declared_canon,
                    f"component {name!r} canonical content does not match its declared "
                    f"{COMPONENT_CANON} (declared {declared_canon}, independently derived "
                    f"{derived})")
    return {"name": name, "path": path, "raw_sha256": raw, "role": entry.get("role"),
            "in_repo": True, "doc": doc}


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


def _find_content_root(release_path: str, components: dict[str, Any]) -> Optional[str]:
    """WHERE the repo-relative component paths resolve. Discovered, then PROVED.

    The release names its components relative to the repository, so the root is an ancestor
    of the release file. It is not guessed: the first ancestor under which EVERY component
    exists is taken, and if no ancestor resolves all of them the release is refused rather
    than half-loaded.
    """
    # Only the IN-REPO components have a path. One component (the scores parquet) is staged
    # OUT of the repo and is bound by hash alone — it names a ``location``, not a path. It
    # cannot be resolved here and must not be: refusing it would refuse the release, and
    # inventing a path for it would be inventing the very thing the hash exists to pin.
    rels = [str((e or {}).get("path") or "") for e in components.values()
            if (e or {}).get("path")]
    if not rels:
        return None
    here = os.path.dirname(os.path.abspath(release_path))
    while True:
        if all(os.path.exists(os.path.join(here, r)) for r in rels):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def load_release(release_root: str, filename: str = RELEASE_FILENAME,
                 content_root: Optional[str] = None) -> BoundRelease:
    """Load and PROVE the NATIVE Stage-1 v3 release, exactly as Stage-1 ships it.

    ``release_root`` is the directory holding ``stage01_v3_release.json``, or the file itself.
    ``content_root`` is where its REPO-RELATIVE component paths resolve; when omitted it is
    discovered by walking up from the release and PROVED by requiring every component to exist
    under it.
    """
    rr = os.path.abspath(str(release_root))
    path = rr if os.path.isfile(rr) else os.path.join(rr, filename)
    _refuse(os.path.exists(path),
            f"no {filename!r} at {os.path.basename(rr)!r}. The native Stage-1 v3 release is "
            f"{RELEASE_FILENAME!r}; a verifier that looked for another name would report a "
            "missing release for one that is entirely present")

    with open(path, "rb") as fh:
        raw_bytes = fh.read()
    doc = json.loads(raw_bytes)

    # ---- gate: the release SHAPE. The legacy manifest is refused BY NAME. ----
    #
    # ONLY ``schema``. Accepting ``schema_version`` as a fallback would be an ALIAS — a quiet
    # tolerance for a shape Stage-1 does not ship — and the point of reading native bytes is
    # that what gets verified is what got released. A document that keys its schema the old
    # way is not the native release, however similar it looks.
    legacy_key = doc.get("schema_version")
    _refuse(legacy_key is None,
            f"the release keys its schema under 'schema_version'; the native Stage-1 v3 "
            f"release keys it under {SCHEMA_KEY!r}. This is not the release Stage-1 ships, "
            "and this lane does not translate it into one")
    declared = str(doc.get(SCHEMA_KEY) or "")
    _refuse("artifacts" not in doc and declared != LEGACY_RELEASE_SCHEMA,
            f"this is the LEGACY Stage-1 release shape ({LEGACY_RELEASE_SCHEMA!r}, with an "
            f"'artifacts' block). Stage-2 binds the CURRENT release {RELEASE_SCHEMA!r}")
    _refuse(declared == RELEASE_SCHEMA,
            f"release {SCHEMA_KEY!r} must be {RELEASE_SCHEMA!r}, got {declared!r}")

    selector = doc.get("selector")
    _refuse(isinstance(selector, dict), "the release ships no 'selector'")
    components = doc.get("components")
    _refuse(isinstance(components, dict) and bool(components),
            "the release ships no 'components'")

    # ---- THE RELEASE'S OWN IDENTITY, re-derived by its own declared rule ----
    declared_self = str(doc.get(SELF_HASH_FIELD) or "")
    derived_self = content_hash({k: v for k, v in doc.items() if k != SELF_HASH_FIELD})
    _refuse(bool(declared_self),
            f"the release declares no {SELF_HASH_FIELD!r}; a release that cannot name itself "
            "cannot be shown to be the one that was bound")
    _refuse(declared_self == derived_self,
            f"the release's {SELF_HASH_FIELD} is {declared_self[:16]}…, but its own content "
            f"hashes to {derived_self[:16]}… ({SELF_HASH_RULE}). A release whose id does not "
            "follow its content can be edited and keep its name")

    root = os.path.abspath(str(content_root)) if content_root \
        else _find_content_root(path, components)
    _refuse(bool(root),
            "the release's component paths are REPO-RELATIVE and no ancestor of the release "
            "resolves all of them. The content root is proved, never guessed")

    loaded = {name: _load_component(root, name, entry)
              for name, entry in sorted(components.items())}

    views = [c for c in loaded.values()
             if isinstance(c["doc"], dict)
             and str(c["doc"].get("schema_version", "")) == SCORER_VIEW_SCHEMA]
    _refuse(len(views) == 1,
            f"the release must ship exactly one {SCORER_VIEW_SCHEMA!r} component; it ships "
            f"{len(views)}. The view is found BY ITS SCHEMA, because a key name is a label "
            "somebody chose")
    view = views[0]["doc"]

    admitted = _derive_admitted(view)

    # THE SCORER PROJECTION IS STAGE-1'S, AND IT IS RE-DERIVED FROM THE REGISTRY THE RELEASE
    # BINDS — never read off the number the release declares. Whether the release's own
    # registry projects to the hash it advertises is exactly the question.
    registries = [c["doc"] for name, c in loaded.items()
                  if c.get("role") == ROLE_PROGRAM_REGISTRY and isinstance(c["doc"], dict)]
    _refuse(len(registries) == 1,
            f"the release must bind exactly one {ROLE_PROGRAM_REGISTRY!r} component; it binds "
            f"{len(registries)}. The scorer projection is a projection OF the registry, and a "
            "registry found by guessing at its shape is whatever happened to look like one")
    registry = registries[0]
    projection = content_hash(registry_scorer_projection(registry))

    declared_proj = str(doc.get("registry_scorer_projection_sha256") or "")
    _refuse(not declared_proj or declared_proj == projection,
            f"the release declares registry_scorer_projection_sha256 {declared_proj[:16]}…, "
            f"but its own registry projects to {projection[:16]}…. A release whose declared "
            "scorer identity does not follow from its own registry is naming an axis it does "
            "not ship")

    declared_view = str(doc.get("registry_scorer_view_canonical_sha256") or "")
    _refuse(not declared_view or declared_view == content_hash(view),
            f"the release declares registry_scorer_view_canonical_sha256 "
            f"{declared_view[:16]}…, but the view it binds hashes to "
            f"{content_hash(view)[:16]}…")

    declared_admitted = selector.get("admitted_programs")
    _refuse(isinstance(declared_admitted, list) and bool(declared_admitted),
            "selector.admitted_programs is absent; one statement of a fact is not a check")
    _refuse(sorted(admitted) == sorted(str(p) for p in declared_admitted),
            "the program axis DERIVED from base_portable disagrees with the release's own "
            f"selector.admitted_programs: derived {sorted(admitted)}, declared "
            f"{sorted(str(p) for p in declared_admitted)}")

    conditions = selector.get("conditions")
    _refuse(isinstance(conditions, list) and bool(conditions),
            "selector.conditions is absent; the condition universe is the RELEASE's")
    conds = tuple(str(c) for c in conditions)
    try:
        pairs = tuple(rules.ordered_pairs(conds))
    except rules.RuleViolation as exc:
        raise ReleaseRefused(f"selector.conditions: {exc}") from exc

    return BoundRelease(
        release_root=os.path.dirname(path),
        release_path=path,
        content_root=root,
        self_release_sha256=declared_self,
        schema_version=declared,
        method_version=str(doc.get("method_version", "")),
        conditions=conds,
        ordered_pairs=pairs,
        admitted_programs=admitted,
        scorer_view=view,
        scorer_view_programs=dict(admitted),
        scorer_view_sha256=content_hash(view),
        scorer_view_raw_sha256=views[0]["raw_sha256"],
        scorer_projection_sha256=projection,
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
