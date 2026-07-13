"""A staged `spot.stage01_v3_release.v1` — the shape Stage-1 actually ships at 55899ac.

SYNTHETIC. Every gene id, program id and hash below is fixture data; the STRUCTURE is the
real one, copied from `01_programs/analysis/stage2_bridge/release/stage01_v3_release.json`:

  * top-level ``schema`` (not ``schema_version``) and ``components`` (not ``artifacts``);
  * component paths are REPO-RELATIVE (`01_programs/app/data/...`) and resolve under an
    explicitly staged release ROOT — Stage-2 is handed a staged copy, never a path into
    somebody's checkout;
  * ``self_release_sha256`` = sha256 of the canonical release minus that one field;
  * ``selector.admitted_programs`` / ``excluded_nonportable`` / ``conditions``.

THE SEAM THIS FIXTURE EXISTS TO REPRODUCE: the PRIMARY registry carries no ``base_portable``.
Only the executable ``stage2_registry_view`` does. A loader that silently reads the primary
registry would find no portability at all — so the substitution must be REFUSED by name, not
absorbed into a default. `primary_registry()` below therefore strips the key, exactly as the
real `stage01_program_registry_v3.json` does.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from direct.hashing import content_hash, file_sha256
from direct.trust import canonical_content_sha256
from fixtures_spec import A_PANEL, B_PANEL, CONDITION, CONTROLS

RELEASE_SCHEMA = "spot.stage01_v3_release.v1"
VIEW_SCHEMA = "spot.stage01_stage2_registry_view.v1"
METHOD_VERSION = "stage1-continuous-v3.0.1"

# Where the real release puts them. The paths are part of the contract.
REGISTRY_PATH = "01_programs/app/data/stage01_program_registry_v3.json"
VIEW_PATH = "01_programs/app/data/stage01_stage2_registry_view.json"
VALIDATION_PATH = "01_programs/app/data/stage01_validation.json"
GATE_SPEC_PATH = "01_programs/app/data/stage01_gate_spec.json"
UNIVERSE_PATH = "01_programs/analysis/effect_universe_gwcd4i.json"
RELEASE_PATH = "01_programs/analysis/stage2_bridge/release/stage01_v3_release.json"

PROGRAM_A, PROGRAM_B = "fx_program_a", "fx_program_b"
NONPORTABLE = "fx_program_nonportable"


def view_programs() -> list[dict[str, Any]]:
    """The EXECUTABLE scorer view: it declares base_portable, and one program is not."""
    return [
        {"program_id": PROGRAM_A, "score_field": f"{PROGRAM_A}_score", "role": "primary",
         "primary": True, "base_portable": True,
         "panel_ensembl": list(A_PANEL), "control_ensembl": list(CONTROLS)},
        {"program_id": PROGRAM_B, "score_field": f"{PROGRAM_B}_score", "role": "primary",
         "primary": True, "base_portable": True,
         "panel_ensembl": list(B_PANEL), "control_ensembl": list(CONTROLS)},
        # the fixture's Th9: shipped by the release, admitted by nothing
        {"program_id": NONPORTABLE, "score_field": f"{NONPORTABLE}_score",
         "role": "primary", "primary": True, "base_portable": False,
         "panel_ensembl": [], "control_ensembl": list(CONTROLS)},
    ]


def scorer_view_doc() -> dict[str, Any]:
    return {
        "schema_version": VIEW_SCHEMA,
        "method_version": METHOD_VERSION,
        "view_kind": "executable_scorer_projection",
        "effect_universe_id": "fixture : GWCD4i.DE_stats.h5ad",
        "n_programs": len(view_programs()),
        "programs": view_programs(),
    }


def primary_registry_doc() -> dict[str, Any]:
    """The PRIMARY v3 registry. Note what is NOT here: base_portable.

    This is the real seam. The primary registry cannot say which programs may carry a
    reusable arm, so it may never stand in for the executable view.
    """
    programs = []
    for p in view_programs():
        programs.append({k: v for k, v in p.items() if k != "base_portable"})
    return {"schema_version": "spot.stage01_program_registry.v3",
            "method_version": METHOD_VERSION, "programs": programs}


def _component(root: str, rel_path: str, doc: Any, role: str,
               **extra) -> dict[str, Any]:
    path = os.path.join(root, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    return dict({"path": rel_path, "raw_sha256": file_sha256(path),
                 "canonical_content_sha256": canonical_content_sha256(doc),
                 "role": role}, **extra)


def selfhash(release: dict[str, Any]) -> str:
    """Stage-1's own recipe: the canonical release, minus the field it is about to fill."""
    return content_hash({k: v for k, v in release.items()
                         if k != "self_release_sha256"})


def stage_release(root: str, *, conditions=(CONDITION,),
                  admitted: Optional[list[str]] = None,
                  view_doc: Optional[dict] = None,
                  view_path: str = VIEW_PATH,
                  validation: Optional[dict] = None,
                  gate_spec: Optional[dict] = None,
                  reseal: bool = True) -> str:
    """Write a complete staged v3 release under ``root``; return the release JSON path.

    ``reseal`` re-derives ``self_release_sha256`` over the final body. Set it False to model
    a release whose declared self hash no longer covers its own bytes.
    """
    from fixtures_direct import write_stage1_gates

    view = scorer_view_doc() if view_doc is None else view_doc
    if validation is None or gate_spec is None:
        tmp = os.path.join(root, "_gates")
        os.makedirs(tmp, exist_ok=True)
        v_path, g_path = write_stage1_gates(
            tmp, program_ids=(PROGRAM_A, PROGRAM_B), conditions=tuple(conditions))
        with open(v_path) as fh:
            validation = json.load(fh)
        with open(g_path) as fh:
            gate_spec = json.load(fh)

    universe = {"schema_version": "spot.stage01_effect_universe.v1",
                "effect_universe_id": "fixture : GWCD4i.DE_stats.h5ad",
                "n_symbols": len(set(A_PANEL) | set(B_PANEL) | set(CONTROLS))}

    components = {
        "registry_v3": _component(root, REGISTRY_PATH, primary_registry_doc(),
                                  "program_registry"),
        "validation": _component(root, VALIDATION_PATH, validation, "frozen_validation"),
        "gate_spec": _component(root, GATE_SPEC_PATH, gate_spec,
                                "pre_registered_gate_spec"),
        "stage2_registry_view": _component(root, view_path, view, "executable_scorer_view"),
        "effect_universe": _component(root, UNIVERSE_PATH, universe,
                                      "effect_universe_target_space"),
        # a component the release DECLARES but does not serve — the real release's
        # gitignored scores parquet. It has no path, and the loader must not trip on that.
        "scores_parquet": {"role": "continuous_program_scores",
                           "canonical_content_sha256": content_hash({"fixture": "scores"}),
                           "location": "release_staging_not_served"},
    }
    view_canonical = components["stage2_registry_view"]["canonical_content_sha256"]
    derived = sorted(p["program_id"] for p in view["programs"]
                     if p.get("base_portable"))
    excluded = sorted(p["program_id"] for p in view["programs"]
                      if not p.get("base_portable"))

    release = {
        "schema": RELEASE_SCHEMA,
        "method_version": METHOD_VERSION,
        "stage1_registry_sha256": components["registry_v3"]["canonical_content_sha256"],
        "registry_scorer_projection_sha256": content_hash(primary_registry_doc()),
        "registry_scorer_view_canonical_sha256": view_canonical,
        "effect_universe_id": "fixture : GWCD4i.DE_stats.h5ad",
        "source_h5ad_sha256": content_hash({"fixture": "h5ad"}),
        "selector": {
            "kind": "generic_continuous_program_selector",
            "program_set_source": "v3_scorer_view",
            "registry_scorer_view_canonical_sha256": view_canonical,
            "admitted_programs": derived if admitted is None else list(admitted),
            "excluded_nonportable": excluded,
            "directions": ["high", "low"],
            "conditions": list(conditions),
            "modes": ["within_condition", "temporal_cross_condition"],
        },
        "components": components,
    }
    release["self_release_sha256"] = (selfhash(release) if reseal
                                      else "0" * 64)

    path = os.path.join(root, RELEASE_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(release, fh, indent=2, sort_keys=True)
    return path


def rewrite(release_path: str, mutate, *, reseal: bool = True) -> str:
    """Mutate a staged release in place. ``reseal`` decides whether it re-attests to itself.

    An attacker who edits a release and re-derives its self hash is the INTERESTING case:
    the document is internally consistent and only the component bytes can refuse it.
    """
    with open(release_path) as fh:
        release = json.load(fh)
    mutate(release)
    release.pop("self_release_sha256", None)
    release["self_release_sha256"] = (selfhash(release) if reseal else "0" * 64)
    with open(release_path, "w") as fh:
        json.dump(release, fh, indent=2, sort_keys=True)
    return release_path
