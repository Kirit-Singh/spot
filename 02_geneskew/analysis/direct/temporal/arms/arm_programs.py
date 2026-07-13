"""WHICH programs a temporal bundle carries — DERIVED from the bound v3 scorer view.

THE COUNT IS A CONSEQUENCE, NEVER AN INPUT
------------------------------------------
The frozen topology says TEN base-portable programs, and Th9 is excluded as non-portable.
That "10" is a FACT ABOUT THE RELEASE, not a constant this module may hold. So the set is
derived, every time, from the programs the bound Stage-1 v3 release actually ships:

    an ADMITTED program is one the bound release declares ``base_portable is True``
    and for which it ships a non-empty ``panel_ensembl`` AND ``control_ensembl``

and the count falls out of that. A module that hard-coded ``PROGRAMS = [...10 ids...]``
would keep returning ten of them after the release dropped one, renamed one, or marked one
non-portable — and every downstream count, every "120 arms" completeness check and every
bundle identity would agree with each other while disagreeing with the science. The only
honest failure here is a LOUD one, so an empty or unprojectable admitted set is refused.

WHAT IS DELIBERATELY *NOT* A CRITERION
--------------------------------------
``base_portable`` is the topology's stated criterion and it is the ONLY one applied. In
particular this module does not additionally gate on the per-condition production
selectability of a program: that gate is a property of a (program, condition) PAIR and it
belongs to the release gate the runner already passes, not to the question "which programs
does this release ship as portable base axes". Silently intersecting the two would shrink
the admitted set below the topology's 10 and make a complete bundle look incomplete.

NO POLE, NO ROLE, NO PAIR
-------------------------
A program is admitted on its own. Nothing here reads a pole (``high|low``), a role
(``away_from_A|toward_B``) or an A/B selection: the bundle is ALL-PROGRAM and
PAIR-AGNOSTIC, and a pair becomes a join over its arms later.
"""
from __future__ import annotations

from typing import Any, Optional

ADMISSION_RULE_ID = "spot.stage02.temporal.arm.program_admission.base_portable.v1"
ADMISSION_RULE = (
    "an admitted program is one the BOUND Stage-1 v3 release declares base_portable=true "
    "and ships a non-empty panel_ensembl and control_ensembl for; the set and its count "
    "are DERIVED from the bound release, never a copied list and never a copied count")

# The flag the scorer view carries. Named once.
PORTABLE_FLAG = "base_portable"


class ProgramAdmissionError(ValueError):
    """The admitted program set is not usable. Refuse; never substitute a default."""


def admitted_programs(release: Any) -> dict[str, dict[str, Any]]:
    """Every base-portable, projectable program the bound release ships, by id.

    Returns ``{program_id: {"program_id", "panel", "control"}}`` — the panel and control
    gene sets the masked projection needs, and NOTHING about a pole or a direction.

    A program that is base-portable but ships no panel or no control is a program that
    cannot be projected. It is REFUSED rather than dropped: dropping it would quietly
    shrink the release below its own topology, and the resulting bundle would be a
    complete-looking artifact with a missing arm.
    """
    programs = getattr(release, "programs", None)
    if not isinstance(programs, dict) or not programs:
        raise ProgramAdmissionError(
            "the bound release ships no programs; a temporal bundle derives its program "
            "axis FROM the release, and there is nothing here to derive it from")

    admitted: dict[str, dict[str, Any]] = {}
    unprojectable: list[str] = []
    for program_id, prog in sorted(programs.items()):
        if prog.get(PORTABLE_FLAG) is not True:
            continue                      # not base-portable: not in the base topology
        panel = prog.get("panel_ensembl")
        control = prog.get("control_ensembl")
        if not (isinstance(panel, list) and panel) or \
                not (isinstance(control, list) and control):
            unprojectable.append(str(program_id))
            continue
        admitted[str(program_id)] = {
            "program_id": str(program_id),
            "panel": [str(g) for g in panel],
            "control": [str(g) for g in control],
        }

    if unprojectable:
        raise ProgramAdmissionError(
            f"programs {sorted(unprojectable)} are declared {PORTABLE_FLAG}=true but ship "
            "no projectable panel/control. They are refused, not skipped: a skipped "
            "program leaves a complete-LOOKING bundle with an arm missing from it")
    if not admitted:
        raise ProgramAdmissionError(
            f"no program in the bound release is declared {PORTABLE_FLAG}=true. The "
            "temporal topology is built on the base-portable programs, and a bundle with "
            "no program axis is not a degenerate bundle - it is not a bundle")
    return admitted


def admitted_conditions(release: Any) -> list[str]:
    """The authoritative condition universe, from the bound v3 ``release.selector.conditions``.

    DERIVED and SORTED, so the universe is order-canonical: reordering the release's own
    condition list cannot change which comparisons are valid. The batch policy is not
    consulted — a confound diagnostic is not an authority on which conditions the release
    ships, and letting it be one was exactly the round-4 defect this removes.
    """
    selector = getattr(release, "selector", None)
    conditions = None
    if selector is not None:
        conditions = (selector.get("conditions") if isinstance(selector, dict)
                      else getattr(selector, "conditions", None))
    if conditions is None and isinstance(release, dict):
        conditions = (release.get("selector") or {}).get("conditions")
    if not conditions:
        raise ProgramAdmissionError(
            "the bound release names no selector.conditions; the temporal condition "
            "universe is derived from the v3 release, never from the batch policy, and a "
            "run whose conditions came from an unnamed source cannot be reproduced")
    derived = sorted({str(c) for c in conditions})
    if len(derived) != len(list(conditions)):
        raise ProgramAdmissionError(
            f"release.selector.conditions {list(conditions)} contains a duplicate; the "
            "condition universe must be a set of distinct conditions")
    return derived


def ordered_pairs(conditions: list[str]) -> list[tuple[str, str]]:
    """Every ordered pair over the condition universe. Sorted; order-canonical."""
    c = sorted({str(x) for x in conditions})
    return [(a, b) for a in c for b in c if a != b]


def require_ordered_pair(conditions: list[str], from_condition: str,
                         to_condition: str) -> None:
    """Refuse an ordered pair the authoritative condition universe does not contain.

    A forged endpoint (a condition the release never named) or a pair missing an endpoint
    is refused BY NAME. Reordering the release's condition list does not change the answer:
    the universe is derived as a sorted set before the pair is checked.
    """
    universe = sorted({str(c) for c in conditions})
    frm, to = str(from_condition), str(to_condition)
    missing = [c for c in (frm, to) if c not in universe]
    if missing:
        raise ProgramAdmissionError(
            f"ordered pair ({frm} -> {to}) names condition(s) {missing} that are not in the "
            f"authoritative universe {universe}. The condition universe is the v3 "
            "release.selector.conditions; a pair outside it was built against a condition "
            "the release does not ship")
    if frm == to:
        raise ProgramAdmissionError(
            f"ordered pair ({frm} -> {to}) compares a condition with itself")


# --------------------------------------------------------------------------- #
# THE STAGE-1 v3 RELEASE BINDING carried on every bundle — hash-bound, non-null.
#
# An arm nobody can attribute to a Stage-1 release is an arm that could have come from
# anywhere. So the bundle binds the release self-hash, the scorer-view raw AND canonical
# hashes, the EXACT declared selector condition sequence (never silently canonical-sorted
# away), the admitted programs, and a per-program projection hash for each. None of these
# may be null in a release-ready bundle — a null identity is the NO-GO the audit found.
# --------------------------------------------------------------------------- #
# The SCALAR overall projection identity (the Stage-2-bound registry_scorer_projection_sha256
# the release publishes) and the 10-key per-program projection MAP are TWO distinct bindings.
# Carry both; collapse neither into the other. W3 verifies the scalar against the release and
# the map's exact key set, and rejects a missing or disagreeing either.
STAGE1_REQUIRED_NONNULL = ("release_self_sha256", "scorer_view_raw_sha256",
                           "scorer_view_canonical_sha256",
                           "registry_scorer_projection_sha256",
                           "effect_universe_sha256", "effect_source_sha256")


def stage1_binding_block(stage1: dict[str, Any], admitted: dict[str, dict[str, Any]], *,
                         effect_universe_sha256: Any,
                         effect_source_sha256: Any) -> dict[str, Any]:
    """The v3 release / scorer / program / condition identity, from the bound inputs.

    Built from what the producer actually read — never a fabricated value. The declared
    selector sequence is carried verbatim; the per-program projection hash is carried for
    every admitted program.
    """
    stage1 = stage1 or {}
    programs = sorted(admitted)
    seq = [str(c) for c in (stage1.get("selector_condition_sequence") or [])]
    per = stage1.get("per_program_projection_sha256") or {}
    return {
        # the canonical scorer-view hash, under the name the independent verifier reads
        # (``registry_scorer_view_sha256``) AND the raw/canonical pair, so both consumers
        # find it; they are the SAME canonical hash and the gate holds them equal.
        "registry_scorer_view_sha256": stage1.get("scorer_view_canonical_sha256"),
        "release_self_sha256": stage1.get("release_self_sha256"),
        "scorer_view_raw_sha256": stage1.get("scorer_view_raw_sha256"),
        "scorer_view_canonical_sha256": stage1.get("scorer_view_canonical_sha256"),
        # (a) the SCALAR Stage-2-bound overall projection identity the release publishes —
        # checked by W3 against the release's registry_scorer_projection_sha256;
        "registry_scorer_projection_sha256":
            stage1.get("registry_scorer_projection_sha256"),
        "selector_condition_sequence": seq,
        "n_conditions": len(seq),
        "admitted_programs": programs,
        "n_programs": len(programs),
        # (b) the INDEPENDENTLY recomputed 10-key per-program projection MAP — distinct from
        # the scalar above, keyed EXACTLY on the admitted programs, never collapsed into it.
        "per_program_projection_sha256": {p: per.get(p) for p in programs},
        "effect_universe_sha256": effect_universe_sha256,
        "effect_source_sha256": effect_source_sha256,
        "programs_derived_from": "bound_stage1_v3_scorer_view",
    }


def stage1_binding_nulls(block: dict[str, Any]) -> list[str]:
    """Every REQUIRED stage-1 field that is still null/absent, or a map with the wrong keys.

    Empty means release-ready. The SCALAR projection identity and the per-program MAP are
    both required (and distinct); the map must be keyed EXACTLY on the admitted programs.
    """
    block = block or {}
    missing = [f for f in STAGE1_REQUIRED_NONNULL if not block.get(f)]
    if not block.get("selector_condition_sequence"):
        missing.append("selector_condition_sequence")
    proj = block.get("per_program_projection_sha256") or {}
    if not proj or any(v is None for v in proj.values()):
        missing.append("per_program_projection_sha256")
    elif sorted(proj) != sorted(block.get("admitted_programs") or []):
        # the map must cover EXACTLY the admitted programs — no missing, no extra key
        missing.append("per_program_projection_sha256_key_set")
    return missing


def require_program(admitted: dict[str, dict[str, Any]], program_id: str) -> None:
    """Refuse a program the bound release did not admit. Never guess a near match."""
    if str(program_id) not in admitted:
        raise ProgramAdmissionError(
            f"program {program_id!r} is not in the admitted base-portable set "
            f"{sorted(admitted)}. It is refused rather than resolved to something similar: "
            "a program substituted for the one that was asked for would answer a different "
            "question under the requested program's name")


def admission_block(admitted: dict[str, dict[str, Any]],
                    scorer_view_sha256: Optional[str]) -> dict[str, Any]:
    """HOW this program axis was derived — bound into the bundle, so it is checkable."""
    return {
        "program_admission_rule_id": ADMISSION_RULE_ID,
        "program_admission_rule": ADMISSION_RULE,
        "programs_derived_from": "bound_stage1_v3_scorer_view",
        "programs_copied_from_a_list": False,
        "program_count_is_derived": True,
        "registry_scorer_view_sha256": scorer_view_sha256,
        "programs": sorted(admitted),
        "n_programs": len(admitted),
    }
