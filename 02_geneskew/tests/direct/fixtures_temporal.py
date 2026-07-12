"""The three-condition fixture the temporal estimator is exercised against.

The programs are REAL frozen registry ids (``diff_naive`` / ``th17_like``), because the
interaction floor and the sparse-panel caution list are keyed by program id: a fixture
using invented program names would exercise the "no measured floor" branch and never the
badge itself.

Arm arithmetic in this fixture (A-panel genes carry ``a_effect``, controls carry 0, both
poles are ``high``):

    delta_A  = mean(A_panel) - mean(controls) = a_effect
    away_from_A = -sign_A * delta_A           = -a_effect
    toward_B    = +sign_B * delta_B           = +b_effect

so a target's ``away_from_A`` DiD across (from -> to) is exactly ``a_from - a_to``, which
is what the tests assert against by hand.
"""
from __future__ import annotations

from dataclasses import replace

from fixtures_spec import TargetSpec

REST, STIM8, STIM48 = "Rest", "Stim8hr", "Stim48hr"
TEMPORAL_CONDITIONS = (REST, STIM8, STIM48)

# The two poles, chosen so BOTH policy branches are live:
#   diff_naive  — interaction_std 0.1568 -> threshold 0.3136, NOT sparse-panel
#   th17_like   — interaction_std 0.4348 -> threshold 0.8695, SPARSE-PANEL caution
PROGRAM_A = "diff_naive"
PROGRAM_B = "th17_like"

# Targets, in the fixture's own Ensembl block (fixtures_spec.TARGET_GENES range).
MOVER = "ENSG00000000200"        # moves hard by 48hr: DiD clears the floor
DRIFTER = "ENSG00000000201"      # moves a little: DiD stays inside the floor
STILL = "ENSG00000000202"        # SYNTHETIC ZERO-SIGNAL control: identical at every condition
B_MOVER = "ENSG00000000203"      # moves on the toward_B arm only


def _remap(spec: TargetSpec, effects: dict[str, tuple[float, float]]) -> TargetSpec:
    """The same target, with a different condition -> effect map. Nothing else moves."""
    return replace(spec, condition_effects=effects)


def permuted_specs() -> list[TargetSpec]:
    """THE CONDITION-LABEL PERMUTATION CONTROL: Rest and Stim48hr trade places.

    Only the LABELS move; every effect vector, every guide, every mask and every QC flag
    is the one it always was. A DiD that is a function of its two labelled endpoints and
    nothing else must therefore come back exactly permuted — the forward estimate on this
    release is the honest release's REVERSE estimate. Anything else means the estimator
    is reading something it was not given.
    """
    out = []
    for spec in temporal_specs():
        effects = {c: spec.effects_at(c) for c in TEMPORAL_CONDITIONS}
        effects[REST], effects[STIM48] = effects[STIM48], effects[REST]
        out.append(_remap(spec, effects))
    return out


def flattened_specs() -> list[TargetSpec]:
    """THE WHOLE-TABLE SYNTHETIC ZERO-SIGNAL CONTROL: no target moves at any condition.

    Every condition gets the target's Rest effect vector, so the release carries no
    temporal signal at all and every DiD on every pair must be exactly 0.0. The batch
    flags, which are a property of the DESIGN and not of the data, must be unchanged.

    THIS IS NOT AN NTC (M5). It is a CONSTRUCTED zero-signal input: it proves the
    estimator invents no movement where the input holds none — a property of the CODE.
    It says nothing about the donor/batch floor of a REAL non-targeting control, because
    a real NTC would carry real donor and batch variation and would NOT come back exactly
    zero. Real-NTC validation is PENDING and is not possible from this effect
    representation: GWCD4i.DE_stats.h5ad ships no NTC target rows at all — NTC is the
    CONTRAST BASELINE every target is measured against, not a row that can be projected.
    """
    return [_remap(spec, {c: spec.effects_at(REST) for c in TEMPORAL_CONDITIONS})
            for spec in temporal_specs()]


def temporal_specs() -> list[TargetSpec]:
    """Four targets whose cross-condition behaviour is known exactly by construction."""
    guides = {"guide_1": -1.0, "guide_2": -1.0}
    return [
        # away_from_A: Rest +1.0, Stim8hr +1.0, Stim48hr +2.0
        #   Rest->Stim8hr  DiD = 0.0   (clean pair, inside the floor)
        #   Rest->Stim48hr DiD = +1.0  (confounded pair, CLEARS the 0.3136 floor)
        TargetSpec(MOVER, ["g-M-1", "g-M-2"], 2.0, a_effect=-1.0, b_effect=0.0,
                   condition_effects={REST: (-1.0, 0.0), STIM8: (-1.0, 0.0),
                                      STIM48: (-2.0, 0.0)},
                   guide_slot_effects=dict(guides),
                   manifest_slots={"guide_1": "g-M-1", "guide_2": "g-M-2"}),
        # away_from_A DiD Rest->Stim48hr = +0.1: real, but INSIDE the floor.
        TargetSpec(DRIFTER, ["g-D-1", "g-D-2"], 2.0, a_effect=-1.0, b_effect=0.0,
                   condition_effects={REST: (-1.0, 0.0), STIM8: (-1.0, 0.0),
                                      STIM48: (-1.1, 0.0)},
                   guide_slot_effects=dict(guides),
                   manifest_slots={"guide_1": "g-D-1", "guide_2": "g-D-2"}),
        # THE SYNTHETIC ZERO-SIGNAL CONTROL (M5). No condition_effects at all, so the
        # effect vector is bit-for-bit the same at every condition and EVERY DiD must be
        # exactly 0.0. It is NOT an NTC: it tests that the CODE invents no movement, not
        # that a real non-targeting control sits inside the donor/batch floor.
        TargetSpec(STILL, ["g-S-1", "g-S-2"], 2.0, a_effect=-0.7, b_effect=0.4,
                   guide_slot_effects=dict(guides),
                   manifest_slots={"guide_1": "g-S-1", "guide_2": "g-S-2"}),
        # toward_B moves (0.2 -> 1.4 by 48hr): DiD = +1.2, which clears th17_like's
        # 0.8695 floor — and th17_like still carries the sparse-panel caution.
        TargetSpec(B_MOVER, ["g-B-1", "g-B-2"], 2.0, a_effect=-0.5, b_effect=0.2,
                   condition_effects={REST: (-0.5, 0.2), STIM8: (-0.5, 0.2),
                                      STIM48: (-0.5, 1.4)},
                   guide_slot_effects=dict(guides),
                   manifest_slots={"guide_1": "g-B-1", "guide_2": "g-B-2"}),
    ]
