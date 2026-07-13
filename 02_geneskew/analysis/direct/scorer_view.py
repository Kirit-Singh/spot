"""WHICH programs the release admits — derived from the BOUND v3 scorer view, never counted.

ROUND4_ADDENDUM (c4773562): "The verifier derives this set from the bound v3 release, never
from a legacy registry path or a copied count."

So the admitted set is not a number written down anywhere. It is DERIVED, here, from the
bound release's own program entries: a program is admitted iff the release marks it
BASE-PORTABLE. Th9 is excluded because the release says it is not portable — not because a
constant somewhere says "10".

Two failure modes this closes:

  * a COPIED COUNT. "10 programs" in a doc, a manifest or a test is a claim that decays the
    moment the release changes. A bundle that shipped 9 arms while something asserted 10
    would be caught only if the 10 were re-derived. So nothing here hard-codes 10, and the
    expected slot count is a FUNCTION of the admitted set;
  * a LEGACY REGISTRY. `stage01_program_registry.json` is not the scorer view and may not
    stand in for it: it can name programs the frozen release never admitted, and a bundle
    built from it would carry arms the release cannot account for.

The view is hashed, and that hash is bound into the bundle identity — so a bundle cannot be
re-attributed to a different program set after the fact.
"""
from __future__ import annotations

from typing import Any

from .hashing import content_hash

VIEW_ID = "spot.stage02.admitted_programs.from_bound_v3_scorer_view.v1"
VIEW_RULE = (
    "a program is admitted iff the BOUND v3 release marks it base_portable; the set is "
    "derived from the release's own bytes and never read from a legacy registry or a "
    "copied count")

PORTABLE_KEY = "base_portable"

REFUSE_NO_ADMITTED = "the_bound_release_admits_no_base_portable_program"
REFUSE_PORTABILITY_UNDECLARED = "the_bound_release_does_not_declare_base_portability"


class ScorerViewError(ValueError):
    """The admitted program set cannot be derived. Refuse; never assume a default set."""

    def __init__(self, reason: str, message: str):
        super().__init__(f"[{reason}] {message}")
        self.reason = reason


def admitted_programs(release) -> list[str]:
    """The admitted program ids, sorted. Derived from the release, not declared."""
    programs = dict(release.programs)
    undeclared = [pid for pid, p in programs.items() if PORTABLE_KEY not in p]
    if undeclared:
        raise ScorerViewError(
            REFUSE_PORTABILITY_UNDECLARED,
            f"the bound release does not declare {PORTABLE_KEY!r} for "
            f"{sorted(undeclared)[:5]}. Portability is what decides whether a program can "
            "carry a reusable arm at all, and a program whose portability is unstated is "
            "not silently treated as portable")
    admitted = sorted(pid for pid, p in programs.items() if bool(p[PORTABLE_KEY]))
    if not admitted:
        raise ScorerViewError(
            REFUSE_NO_ADMITTED,
            "the bound release marks no program base_portable, so there is no arm to "
            "compute. An empty bundle that admitted itself would be a release with no "
            "content and a clean bill of health")
    return admitted


def view(release) -> dict[str, Any]:
    """The admitted set AND what it was derived from — hashable, and bound into identity."""
    admitted = admitted_programs(release)
    programs = release.programs
    # The panel/control each arm is projected on IS part of the view: two releases that
    # admit the same program ids but disagree about its panel are not the same scorer view,
    # and a bundle keyed only on the ids could be re-attributed from one to the other.
    detail = {
        pid: {
            "program_id": pid,
            "n_panel": len(programs[pid].get("panel_ensembl") or []),
            "n_control": len(programs[pid].get("control_ensembl") or []),
            "panel_sha256": content_hash(
                sorted(str(g) for g in (programs[pid].get("panel_ensembl") or []))),
            "control_sha256": content_hash(
                sorted(str(g) for g in (programs[pid].get("control_ensembl") or []))),
        }
        for pid in admitted
    }
    return {
        "view_id": VIEW_ID,
        "view_rule": VIEW_RULE,
        "release_kind": release.kind,
        "admitted_program_ids": admitted,
        "n_admitted_programs": len(admitted),
        "n_release_programs": len(programs),
        "n_excluded_not_base_portable": len(programs) - len(admitted),
        "excluded_program_ids": sorted(set(programs) - set(admitted)),
        "programs": detail,
        "derived_from_legacy_registry": False,
        "scorer_view_sha256": content_hash(detail),
    }
