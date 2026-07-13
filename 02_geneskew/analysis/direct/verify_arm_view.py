"""WHICH programs the release admits — DERIVED from the bound generic v3 release.

INDEPENDENCE RULE (test-enforced): imports nothing from the generator. In particular it
does not import ``scorer_view`` (the producer's derivation) or ``trust`` (the producer's
release loader): a checker that borrowed either would be asking the generator whether the
generator was right.

ROUND4_ADDENDUM (c4773562): "The verifier derives this set from the bound v3 release,
never from a legacy registry path or a copied count."

TWO VIEWS, AND THEY ARE NOT THE SAME OBJECT
-------------------------------------------
``stage1_scorer_view``   the release's own ``spot.stage01_stage2_registry_view.v1`` — the
                         EXECUTABLE scorer projection (panel/control in Ensembl space,
                         and the ``base_portable`` flag). Hash-pinned by the release and
                         re-verified here from its bytes. THE authority on who is admitted.
``stage2_arm_view``      what a Direct bundle embeds and binds: the admitted ids plus the
                         per-program projection those arms were taken under. Re-derived
                         here and compared with the bundle's.

THE RELEASE SHAPE IS PART OF THE CONTRACT
-----------------------------------------
The CURRENT shape is ``spot.stage01_v3_release.v1`` (Stage-1 d9bd4e5 + 55899ac): hash-
pinned ``components`` plus a GENERIC ``selector`` that names no biological pair. The
PRE-GENERIC ``spot.stage01_release_manifest.v1`` hard-coded a pair, and it is refused BY
NAME rather than parsed on a best-effort basis — a verifier that quietly accepted it would
be admitting arms derived from a topology the addendum retired.

The release may DECLARE its admitted set and its desired-change mapping. It may not
OVERRIDE them: both are re-derived here, and a declaration that disagrees is a refusal.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from verify_arm_rules import (
    DESIRED_CHANGE_BY_ROLE_AND_POLE,
    canonical_json,
    content_sha256,
    sha256_file,
    sha256_hex,
)

STAGE1_RELEASE_SCHEMA_V3 = "spot.stage01_v3_release.v1"
STAGE1_RELEASE_SCHEMA_STALE = "spot.stage01_release_manifest.v1"
STAGE1_VIEW_SCHEMA = "spot.stage01_stage2_registry_view.v1"

VIEW_ID = "spot.stage02.admitted_programs.from_bound_v3_scorer_view.v1"
VIEW_RULE = (
    "a program is admitted iff the BOUND v3 release marks it base_portable; the set is "
    "derived from the release's own bytes and never read from a legacy registry or a "
    "copied count")

PORTABLE_KEY = "base_portable"
SCORER_VIEW_COMPONENT = "stage2_registry_view"
SELF_HASH_FIELD = "self_release_sha256"

# A document never attests to itself: these field names are stripped before a canonical
# content hash. (The same three Stage-1 strips.)
SELF_HASH_FIELDS = ("registry_sha256", "self_sha256", "sha256")

REFUSE_STALE_RELEASE_SHAPE = "the_bound_release_is_a_stale_pre_generic_release_shape"
REFUSE_UNKNOWN_RELEASE_SHAPE = "the_bound_release_declares_no_recognised_schema"
REFUSE_VIEW_SHAPE = "the_bound_scorer_view_declares_no_recognised_schema"
REFUSE_PORTABILITY_UNDECLARED = "the_bound_release_does_not_declare_base_portability"
REFUSE_NO_ADMITTED = "the_bound_release_admits_no_base_portable_program"
REFUSE_VIEW_NOT_BOUND = "the_release_does_not_bind_its_scorer_view_canonical_sha256"
REFUSE_VIEW_HASH_MISMATCH = "the_scorer_view_bytes_do_not_match_the_hash_the_release_binds"
REFUSE_COMPONENT_MISSING = "a_required_release_component_is_missing"
REFUSE_COMPONENT_HASH_MISMATCH = "a_release_component_does_not_match_its_pinned_hash"
REFUSE_COMPONENT_PATH_ESCAPES_ROOT = "a_release_component_path_escapes_the_staged_root"
REFUSE_RELEASE_ROOT_NOT_STAGED = "no_staged_release_root_was_given_to_resolve_components"
REFUSE_SELF_HASH_MISMATCH = "the_release_self_hash_does_not_re_derive_from_its_content"
REFUSE_ADMITTED_SET_DISAGREES = "the_declared_admitted_set_disagrees_with_the_derivation"
REFUSE_MAPPING_FORGED = "the_declared_desired_change_mapping_is_not_the_frozen_mapping"


class ScorerViewError(ValueError):
    """The admitted program set cannot be derived. Refuse; never assume a default set."""

    def __init__(self, reason: str, message: str):
        super().__init__(f"[{reason}] {message}")
        self.reason = reason


def _refuse(reason: str, message: str):
    raise ScorerViewError(reason, message)


# --------------------------------------------------------------------------- #
# Canonicalisation, restated (Stage-1's, re-derived — not imported across the seam).
# --------------------------------------------------------------------------- #
def _strip_self_hash(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _strip_self_hash(x) for k, x in v.items()
                if k not in SELF_HASH_FIELDS}
    if isinstance(v, list):
        return [_strip_self_hash(x) for x in v]
    return v


def canonical_content_sha256(doc: Any) -> str:
    """The canonical content hash of a released JSON artifact: self-hash fields stripped
    recursively, then sorted-key compact JSON, then sha256."""
    return content_sha256(_strip_self_hash(doc)) if isinstance(doc, dict) \
        else content_sha256(doc)


def release_self_sha256(doc: dict, field: str = SELF_HASH_FIELD) -> str:
    """The release's self hash: every field EXCEPT the one carrying it."""
    return sha256_hex(canonical_json({k: v for k, v in doc.items() if k != field}))


# --------------------------------------------------------------------------- #
# The Stage-2 arm view: WHO is admitted, and WHAT projection their arms were taken under.
# --------------------------------------------------------------------------- #
def programs_from_doc(doc: dict) -> dict[str, dict]:
    """``{program_id: program}`` from any doc carrying a ``programs`` list.

    The Stage-1 scorer view and a v3 program registry share this shape; the LOADER decides
    which of them is authoritative for the lane, not this function.
    """
    programs = doc.get("programs")
    if not isinstance(programs, list) or not programs:
        _refuse(REFUSE_PORTABILITY_UNDECLARED,
                "the bound document carries no non-empty 'programs' list, so there is no "
                "program set to derive")
    out: dict[str, dict] = {}
    for prog in programs:
        pid = prog.get("program_id")
        if not pid:
            _refuse(REFUSE_PORTABILITY_UNDECLARED,
                    "a program in the bound document has no program_id")
        out[str(pid)] = prog
    return out


def admitted_programs(programs: dict[str, dict]) -> list[str]:
    """The admitted ids, sorted. DERIVED from the release's bytes, never declared."""
    undeclared = sorted(pid for pid, p in programs.items() if PORTABLE_KEY not in p)
    if undeclared:
        _refuse(REFUSE_PORTABILITY_UNDECLARED,
                f"the bound release does not declare {PORTABLE_KEY!r} for "
                f"{undeclared[:5]}. Portability decides whether a program can carry a "
                "reusable arm at all, and a program whose portability is unstated is not "
                "silently treated as portable")
    admitted = sorted(pid for pid, p in programs.items() if bool(p[PORTABLE_KEY]))
    if not admitted:
        _refuse(REFUSE_NO_ADMITTED,
                "the bound release marks no program base_portable, so there is no arm to "
                "compute. An empty bundle that admitted itself would be a release with no "
                "content and a clean bill of health")
    return admitted


def scorer_projection(pid: str, prog: dict) -> dict[str, Any]:
    """ONE program's SCORER PROJECTION — the panel and control its arms are taken on.

    THIS is the record the bundle's ``scorer_view_sha256`` is a hash over, so its shape is
    the frozen contract and is reimplemented here exactly: five fields, and the two gene
    sets identified by content rather than by order. Re-sorting a panel is not a different
    scorer and must not look like one; MEMBERSHIP is what moves a number.
    """
    panel = sorted(str(g) for g in (prog.get("panel_ensembl") or []))
    control = sorted(str(g) for g in (prog.get("control_ensembl") or []))
    return {
        "program_id": pid,
        "n_panel": len(panel),
        "n_control": len(control),
        "panel_sha256": content_sha256(panel),
        "control_sha256": content_sha256(control),
    }


def program_projection(pid: str, prog: dict) -> dict[str, Any]:
    """The scorer projection PLUS a per-program id the verifier SPECIFIES and computes.

    The Stage-1 scorer view carries no per-program identifier — no ``method_hash``, no
    projection id — so there is nothing to read and nothing to trust. Rather than read a
    field that does not exist, the record is stated here and hashed from the program's own
    bytes: the id it is admitted under and the exact gene sets it is projected on.

    Deliberately NOT part of ``scorer_view_sha256``: that hash is the producer's frozen
    contract, and a verifier that folded its own extra field into it could never re-derive
    the value it is supposed to be checking. This id travels in the report instead.
    """
    return dict(scorer_projection(pid, prog),
                program_projection_sha256=content_sha256({
                    "program_id": pid,
                    "panel_ensembl": sorted(
                        str(g) for g in (prog.get("panel_ensembl") or [])),
                    "control_ensembl": sorted(
                        str(g) for g in (prog.get("control_ensembl") or [])),
                }))


def stage2_arm_view(programs: dict[str, dict]) -> dict[str, Any]:
    """The admitted set AND what it was derived from — hashable, and bound into identity.

    The panel/control each arm is projected on IS part of the view: two releases that admit
    the same ids but disagree about a panel are not the same scorer view, and a bundle keyed
    only on the ids could be re-attributed from one to the other.
    """
    admitted = admitted_programs(programs)
    # THE hashed detail: the frozen five-field scorer projection, and nothing else. A
    # verifier that added a field of its own here could never re-derive the hash the
    # bundle binds.
    detail = {pid: scorer_projection(pid, programs[pid]) for pid in admitted}
    return {
        "view_id": VIEW_ID,
        "view_rule": VIEW_RULE,
        "admitted_program_ids": admitted,
        "n_admitted_programs": len(admitted),
        "n_release_programs": len(programs),
        "n_excluded_not_base_portable": len(programs) - len(admitted),
        "excluded_program_ids": sorted(set(programs) - set(admitted)),
        "programs": detail,
        # the verifier's own per-program ids — reported, never folded into the hash above
        "program_projections": {pid: program_projection(pid, programs[pid])
                                for pid in admitted},
        "derived_from_legacy_registry": False,
        "scorer_view_sha256": content_sha256(detail),
    }


# --------------------------------------------------------------------------- #
# The CURRENT generic v3 release (Stage-1 d9bd4e5 + 55899ac).
# --------------------------------------------------------------------------- #
def _mapping_from_selector(selector: dict) -> Optional[dict]:
    declared = selector.get("desired_change_mapping")
    return declared if isinstance(declared, dict) else None


def _mapping_key(key: Any) -> str:
    """``role(pole)`` — accepting the ``role|pole`` spelling the arm keys use."""
    k = str(key).strip()
    if "|" in k:
        role, _, pole = k.partition("|")
        return f"{role}({pole})"
    return k


def _check_mapping(selector: dict) -> None:
    """RE-DERIVE the frozen mapping and compare. Never read it and believe it."""
    declared = _mapping_from_selector(selector)
    if declared is None:
        return
    expected = {f"{role}({pole})": change
                for (role, pole), change in DESIRED_CHANGE_BY_ROLE_AND_POLE.items()}
    got = {_mapping_key(k): str(v) for k, v in declared.items()}
    if got != expected:
        _refuse(REFUSE_MAPPING_FORGED,
                f"the release declares {declared!r}; the frozen mapping re-derives to "
                f"{expected!r}. A swapped mapping is a sign error nobody sees")


def _verify_component(name: str, entry: Any, release_root: str) -> dict[str, Any]:
    """Resolve ONE component against the EXPLICITLY STAGED release root and prove its bytes.

    The root is passed in, never inferred from the verifier's own location or from a
    machine default: a component resolved against wherever-the-checker-happens-to-live is
    a component nobody pinned. The pinned path is repo-relative and may not escape the
    root — a release cannot point the verifier at a file outside the tree it staged.
    """
    if not isinstance(entry, dict) or not entry.get("path"):
        _refuse(REFUSE_COMPONENT_MISSING,
                f"release component {name!r} is missing or carries no path")
    rel = str(entry["path"])
    if os.path.isabs(rel) or ".." in rel.replace("\\", "/").split("/"):
        _refuse(REFUSE_COMPONENT_PATH_ESCAPES_ROOT,
                f"release component {name!r} pins {rel!r}, which is absolute or escapes "
                "the staged release root")
    root = os.path.abspath(release_root)
    path = os.path.abspath(os.path.join(root, rel))
    if os.path.commonpath([root, path]) != root:
        _refuse(REFUSE_COMPONENT_PATH_ESCAPES_ROOT,
                f"release component {name!r} resolves outside the staged root {root!r}")
    if not os.path.exists(path):
        _refuse(REFUSE_COMPONENT_MISSING,
                f"release component {name!r} is not on disk at its pinned path {rel!r} "
                f"under the staged release root {root!r}")

    raw = sha256_file(path)
    declared_raw = str(entry.get("raw_sha256", "")).lower()
    if declared_raw and raw != declared_raw:
        _refuse(REFUSE_COMPONENT_HASH_MISMATCH,
                f"release component {name!r}: raw bytes do not match the pinned "
                f"raw_sha256 (declared {declared_raw}, actual {raw})")

    doc = None
    if path.endswith(".json"):
        with open(path) as fh:
            doc = json.load(fh)
        declared_canon = str(entry.get("canonical_content_sha256", "")).lower()
        actual_canon = canonical_content_sha256(doc)
        if declared_canon and actual_canon != declared_canon:
            _refuse(REFUSE_COMPONENT_HASH_MISMATCH,
                    f"release component {name!r}: canonical content does not match the "
                    f"pinned canonical_content_sha256 (declared {declared_canon}, actual "
                    f"{actual_canon})")
    return {"path": path, "raw_sha256": raw, "doc": doc}


def load_v3_release(path: str, release_root: Optional[str] = None) -> dict[str, Any]:
    """Load, PROVE and DERIVE from the current generic v3 release. Fail-closed.

    ``release_root`` is the EXPLICITLY STAGED root the components' repo-relative paths are
    resolved against. It is not defaulted to a machine location; when it is omitted the
    release's own directory is used, which is correct only for a self-contained staging
    directory and is refused the moment a component points anywhere else.
    """
    if not os.path.exists(path):
        _refuse(REFUSE_COMPONENT_MISSING, f"Stage-1 v3 release not found: {path}")
    with open(path) as fh:
        release = json.load(fh)

    schema = str(release.get("schema") or release.get("schema_version") or "")
    if schema == STAGE1_RELEASE_SCHEMA_STALE:
        _refuse(REFUSE_STALE_RELEASE_SHAPE,
                f"the bound release declares {schema!r}. That is the PRE-GENERIC shape: "
                "it hard-coded a biological pair, and its arms are keyed on a topology "
                f"the addendum retired. The current shape is "
                f"{STAGE1_RELEASE_SCHEMA_V3!r}")
    if schema != STAGE1_RELEASE_SCHEMA_V3:
        _refuse(REFUSE_UNKNOWN_RELEASE_SHAPE,
                f"the bound release declares schema {schema!r}; this verifier consumes "
                f"{STAGE1_RELEASE_SCHEMA_V3!r} and refuses rather than guessing at an "
                "unknown shape")

    if SELF_HASH_FIELD in release:
        declared = str(release[SELF_HASH_FIELD])
        actual = release_self_sha256(release)
        if declared != actual:
            _refuse(REFUSE_SELF_HASH_MISMATCH,
                    f"the release self hash does not re-derive from its content "
                    f"(declared {declared}, actual {actual})")

    bound_view_sha = str(release.get("registry_scorer_view_canonical_sha256") or "")
    if not bound_view_sha:
        _refuse(REFUSE_VIEW_NOT_BOUND,
                "the release does not bind registry_scorer_view_canonical_sha256, so "
                "nothing says WHICH scorer view its admitted programs came from")

    components = release.get("components") or {}
    if SCORER_VIEW_COMPONENT not in components:
        _refuse(REFUSE_COMPONENT_MISSING,
                f"the release has no {SCORER_VIEW_COMPONENT!r} component; the admitted "
                "set is derived from the scorer view and there is no substitute for it")

    root = release_root or os.path.dirname(os.path.abspath(path))
    if not root:
        _refuse(REFUSE_RELEASE_ROOT_NOT_STAGED,
                "no staged release root was given; component paths are repo-relative and "
                "may not be resolved against a machine default")
    verified = {name: _verify_component(name, entry, root)
                for name, entry in components.items()}

    view_doc = verified[SCORER_VIEW_COMPONENT]["doc"]
    if not isinstance(view_doc, dict):
        _refuse(REFUSE_COMPONENT_MISSING,
                f"the {SCORER_VIEW_COMPONENT!r} component is not a JSON document")
    view_schema = str(view_doc.get("schema_version") or "")
    if view_schema != STAGE1_VIEW_SCHEMA:
        _refuse(REFUSE_VIEW_SHAPE,
                f"the bound scorer view declares schema {view_schema!r}; this verifier "
                f"consumes {STAGE1_VIEW_SCHEMA!r} and refuses rather than guessing at an "
                "unknown shape")

    # THE binding: the view's own canonical content must be the hash the release names.
    actual_view_sha = canonical_content_sha256(view_doc)
    if actual_view_sha != bound_view_sha:
        _refuse(REFUSE_VIEW_HASH_MISMATCH,
                f"the scorer view's canonical content is {actual_view_sha}, but the "
                f"release binds {bound_view_sha}. A bundle built from this view could be "
                "re-attributed to a different program set")

    selector = release.get("selector") or {}
    _check_mapping(selector)

    view = stage2_arm_view(programs_from_doc(view_doc))
    admitted = view["admitted_program_ids"]

    declared_admitted = selector.get("admitted_programs")
    if isinstance(declared_admitted, list) and sorted(
            str(p) for p in declared_admitted) != admitted:
        _refuse(REFUSE_ADMITTED_SET_DISAGREES,
                f"the release DECLARES {sorted(str(p) for p in declared_admitted)!r} but "
                f"its scorer view DERIVES {admitted!r}. A declared list may accompany the "
                "derivation; it may not override it")

    return {
        "release_path": os.path.abspath(path),
        "release_root": os.path.abspath(root),
        "release_schema": schema,
        "release_raw_sha256": sha256_file(path),
        "release_self_sha256": release.get(SELF_HASH_FIELD),
        "method_version": str(release.get("method_version", "")),
        # RE-DERIVED from the view's own bytes.
        "stage1_scorer_view_canonical_sha256": actual_view_sha,
        # BOUND, not recomputed: the scorer PROJECTION hash is taken over the primary
        # registry by Stage-1's own projection rule. The verifier pins the value the
        # release declares and requires the bundle to have bound the same one; it does not
        # claim to have re-derived a hash whose recipe lives in another stage.
        "registry_scorer_projection_sha256": release.get(
            "registry_scorer_projection_sha256"),
        "stage1_scorer_view_doc": view_doc,
        "components": {n: {"path": v["path"], "raw_sha256": v["raw_sha256"]}
                       for n, v in verified.items()},
        "programs": programs_from_doc(view_doc),
        "stage2_arm_view": view,
        "admitted_program_ids": admitted,
        "n_admitted_programs": len(admitted),
        "selector": selector,
    }
