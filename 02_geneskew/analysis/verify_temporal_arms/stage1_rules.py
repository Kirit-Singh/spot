"""STAGE-1'S OWN RULES, implemented again here. Its bytes are authoritative; so are its rules.

A verifier that invents its own definition of a hash the release already declares is not
checking the release — it is checking whether the release agrees with an invention. So both
rules below are Stage-1's, restated:

THE CANONICAL CONTENT HASH
    A DOCUMENT NEVER ATTESTS TO ITSELF. A self-declared hash is trivially forged and proves
    nothing, so those field names are stripped RECURSIVELY before the content hash is taken.
    Hashing them in would mean a document's own claim about its hash changed the hash — and no
    artifact could ever match its own declaration.

THE SCORER PROJECTION
    A projection of the PROGRAM REGISTRY — not of the scorer view — with the fields that do not
    feed scoring removed: top-level provenance, per-program rationale and citations, and
    display-only labels. The display strip is the point of the rule: a cosmetic relabel must
    never move the scorer-core invariant, or every lane pinned to that hash would re-verify for
    a reason that has nothing to do with the science.

    This lane RE-DERIVES it rather than reading the number the release declares. Whether the
    release's own registry projects to the hash it advertises is exactly the question.
"""
from __future__ import annotations

from typing import Any

from .canonical import content_hash

# The release names each component's ROLE. Finding the registry by role is finding it the way
# the release says to; finding it by guessing at its shape is finding whatever happened to
# look like one.
ROLE_PROGRAM_REGISTRY = "program_registry"
ROLE_SCORER_VIEW = "executable_scorer_view"

# THE CANONICAL CONTENT RULE, restated. A DOCUMENT NEVER ATTESTS TO ITSELF: a self-declared
# hash is trivially forged and proves nothing, so these field names are stripped RECURSIVELY
# before the content hash is taken. Hashing them in would mean a document's own claim about
# its hash changed the hash — and no artifact could ever match its own declaration.
SELF_HASH_FIELDS = frozenset({"registry_sha256", "self_sha256", "sha256"})


def _strip_self_hash(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _strip_self_hash(x) for k, x in v.items() if k not in SELF_HASH_FIELDS}
    if isinstance(v, list):
        return [_strip_self_hash(x) for x in v]
    return v


def canonical_content_sha256(doc: Any) -> str:
    """The canonical content hash of a released artifact, self-hash fields stripped."""
    if isinstance(doc, dict):
        return content_hash({k: _strip_self_hash(v) for k, v in doc.items()
                             if k not in SELF_HASH_FIELDS})
    return content_hash(doc)


PROGRAM_PROJECTION_ID = "spot.stage02.temporal.arm.program_projection.v1"
SCORER_PROJECTION_ID = "spot.stage01.registry_scorer_projection.v1"

# STAGE-1'S OWN SCORER PROJECTION, restated and re-derived here.
#
# It is a projection of the PROGRAM REGISTRY, not of the scorer view, and it strips the
# fields that do not feed scoring: top-level provenance, per-program rationale/citations, and
# display-only labels. That last one is the point of the rule — a cosmetic relabel must never
# be able to move the scorer-core invariant, and if it could, every downstream lane pinned to
# that hash would re-verify for a reason that has nothing to do with the science.
#
# This lane RE-DERIVES it rather than reading the number the release declares. The release
# says 008c1da1…; whether that is what its own registry projects to is exactly the question.
SCORER_PROJECTION_PROV_TOP = frozenset({
    "citations_provenance_note", "registry_sha256", "panel_provenance_schema_version",
    "panel_provenance",
})
SCORER_PROJECTION_PROV_PROG = frozenset({
    "selection_rationale", "citations", "citations_verification_status",
    "marker_provenance", "display_label",
})


def _scoring_strip(prog: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in prog.items() if k not in SCORER_PROJECTION_PROV_PROG}
    ap = out.get("activation_predictor")
    if isinstance(ap, dict):
        out["activation_predictor"] = {k: v for k, v in ap.items()
                                       if k != "predictor_provenance"}
    return out


def registry_scorer_projection(registry: dict[str, Any]) -> dict[str, Any]:
    """Stage-1's scoring projection of the program registry. Its rule, implemented again."""
    out = {k: v for k, v in registry.items()
           if k not in SCORER_PROJECTION_PROV_TOP
           and k not in ("programs", "sensitivity_lanes")}
    out["programs"] = [_scoring_strip(p) for p in (registry.get("programs") or [])]
    out["sensitivity_lanes"] = [_scoring_strip(p)
                                for p in (registry.get("sensitivity_lanes") or [])]
    return out

