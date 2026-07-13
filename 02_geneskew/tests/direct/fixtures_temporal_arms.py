"""SYNTHETIC FIXTURES for the reusable temporal arm producer. FIXTURE DATA ONLY.

=============================================================================
EVERY NUMBER IN THIS MODULE IS INVENTED. It is constructed to exercise the
arithmetic, the refusals and the determinism of the producer. It is NOT
measured, it is NOT derived from GWCD4i or any other dataset, and NO
BIOLOGICAL CLAIM MAY BE READ OUT OF IT. The program ids below are spelled
FIXTURE_* precisely so that a number from this module can never be mistaken
for a statement about treg_like, th1_like or anything else real.
=============================================================================

The fixture release ships TEN base-portable programs plus ONE non-portable one, so the
producer's admitted set has to be DERIVED (and the non-portable one has to be left out) —
a fixture with exactly ten portable programs would let a hard-coded ``10`` pass.
"""
from __future__ import annotations

import numpy as np
from direct.temporal.arms import arm_bundle

# --------------------------------------------------------------------------- #
# The synthetic gene space. Twelve genes; panels and controls are disjoint.
# --------------------------------------------------------------------------- #
# The control set must clear the direct lane's real minimum (MIN_SURVIVING_CONTROL = 10),
# or every projection comes back `insufficient_axis_coverage` and the fixture would be
# testing the refusal path while looking like it tested the arithmetic.
GENES = [f"ENSG{i:011d}" for i in range(24)]
GENE_INDEX = {g: i for i, g in enumerate(GENES)}
PANEL_POOL = GENES[:10]
CONTROLS = GENES[10:]          # 14 controls

N_PORTABLE = 10
PORTABLE_IDS = [f"FIXTURE_PROG_{i:02d}" for i in range(N_PORTABLE)]
NON_PORTABLE_ID = "FIXTURE_PROG_NONPORTABLE"   # stands in for the excluded Th9

CONDITIONS = ("FixRest", "FixStim8", "FixStim48")

# The 6 ORDERED pairs over 3 conditions. Derived, not typed out.
ORDERED_PAIRS = [(a, b) for a in CONDITIONS for b in CONDITIONS if a != b]


def _panel(i: int) -> list[str]:
    """A 3-gene panel per program, rotating through the panel pool. Distinct per program."""
    n = len(PANEL_POOL)
    return [PANEL_POOL[(i + k) % n] for k in range(3)]


def programs_registry() -> dict[str, dict]:
    """The FIXTURE Stage-1 scorer view: 10 base-portable + 1 explicitly non-portable."""
    # FIXTURE program RECORDS, mirroring the shape the producer hashes whole (the real
    # stage01_stage2_registry_view.json record carries more fields; the producer derives the
    # per-program projection id from the ENTIRE record, whatever its fields are).
    reg = {
        pid: {"program_id": pid, "panel_ensembl": _panel(i), "control_ensembl": CONTROLS,
              "base_portable": True, "primary": True, "stage2_selectable": True,
              "coefficients": [round(0.1 * (i + 1) * (k + 1), 4) for k in range(3)]}
        for i, pid in enumerate(PORTABLE_IDS)
    }
    reg[NON_PORTABLE_ID] = {
        "program_id": NON_PORTABLE_ID, "panel_ensembl": _panel(0),
        "control_ensembl": CONTROLS,
        # NOT base-portable. The producer must derive it OUT of the admitted set.
        "base_portable": False, "primary": True, "stage2_selectable": True,
    }
    return reg


class _Selector:
    """The v3 release selector the producer reads for the condition universe. Fixture only."""

    def __init__(self, conditions):
        self.conditions = list(conditions)


class FixtureRelease:
    """The minimal duck-typed release the producer reads: ``.programs`` + ``.selector``."""

    def __init__(self, programs: dict[str, dict] | None = None, conditions=None):
        self.programs = programs_registry() if programs is None else programs
        self.selector = _Selector(CONDITIONS if conditions is None else conditions)


def admitted():
    from direct.temporal.arms import arm_programs
    return arm_programs.admitted_programs(FixtureRelease())


def condition_universe(release=None):
    from direct.temporal.arms import arm_programs
    return arm_programs.admitted_conditions(FixtureRelease() if release is None else release)


def stage1(release=None):
    """The FIXTURE Stage-1 v3 release metadata. Every hash is INVENTED, clearly-marked
    fixture data — never a measurement — but complete (non-null) so the release is GO.

    Deliberately does NOT supply per_program_projection_sha256: the producer DERIVES that
    map from the Stage-1 records itself. (A supplied map is only admissible if it matches.)
    """
    return {
        "release_self_sha256": "b" * 64,                   # FIXTURE v3 release self-hash
        "scorer_view_raw_sha256": "a" * 64,                # FIXTURE scorer view raw
        "scorer_view_canonical_sha256": "a" * 64,          # == scorer_view_sha256 below
        # (a) the SCALAR overall projection identity — DISTINCT from the per-program map.
        # FIXTURE value; the real frozen production identity is 008c1da1… (W3/W11 pin that).
        "registry_scorer_projection_sha256": "c0" * 32,
        # the DECLARED selector sequence — carried verbatim, NOT canonical-sorted away
        "selector_condition_sequence": list(CONDITIONS),
    }


# --------------------------------------------------------------------------- #
# Synthetic effect vectors. Deterministic, invented, and NOT a measurement.
# --------------------------------------------------------------------------- #
TARGETS = [f"FIXTURE_TGT_{i:02d}" for i in range(6)]


def effect_row(target_i: int, condition: str) -> np.ndarray:
    """A deterministic synthetic effect vector. Invented; carries no biology."""
    base = np.arange(len(GENES), dtype=float) * 0.01
    shift = {"FixRest": 0.0, "FixStim8": 0.5, "FixStim48": 1.25}[condition]
    return base + 0.1 * target_i + shift * np.sin(np.arange(len(GENES)) + target_i)


def endpoint(target_i: int, condition: str, *, mask=frozenset(), **overrides
             ) -> arm_bundle.TargetEndpoint:
    """One synthetic (target, condition) endpoint with a COMPLETE program axis."""
    from direct.temporal.arms import arm_estimand as est

    target_id = TARGETS[target_i]
    progs = overrides.pop("programs", None) or admitted()
    deltas = est.project_programs(effect_row(target_i, condition), progs, GENE_INDEX,
                                  set(mask))
    fields = dict(
        target_id=target_id,
        program_delta=deltas,
        target_symbol=f"SYM{target_i}",
        target_ensembl=f"ENSGT{target_i:011d}",
        target_id_namespace="fixture",
        released_estimate_id=f"{target_id}|{condition}",
        base_qc_passed=True,
        base_qc_state="base_qc_passed",
        base_qc_reasons="",
        qc_ontarget_significant=True,
        qc_ontarget_effect_size=-1.5 - 0.1 * target_i,
        qc_target_baseMean=100.0 + target_i,
        qc_low_target_expression=False,
        mask_resolved=True,
        estimate_mask_sha256=f"{target_i:064x}",
        mask_gene_count=len(mask),
        mask_unresolved_reason=None,
        n_guide_slots_released=4,
        n_guides_mapped=4,
        n_guides_evaluated=0,
        n_splits_total=3,
        n_splits_evaluable=0,
        donor_split_denominator=0,
        effective_donor_n=4,
        n_cells_target=200 + target_i,
    )
    fields.update(overrides)
    return arm_bundle.TargetEndpoint(**fields)


def endpoints(condition: str, n: int = len(TARGETS), **kw):
    return [endpoint(i, condition, **kw) for i in range(n)]


def method():
    """A FIXTURE method block. The hashes are invented placeholders."""
    return arm_bundle.method_block(
        temporal_method_sha256="f" * 64,
        direct_method_version="fixture-direct-v0",
        direct_config_sha256="e" * 64,
        effect_source_sha256="d" * 64,
        effect_universe_sha256="c" * 64,
    )


_UNSET = object()
_CODE_IDENTITY = None


def code_identity():
    """The REAL shared code-digest tuple of this checkout, computed ONCE and cached.

    Not a fabricated constant — it is the actual ``code_digest.run_binding`` over the
    Stage-2 tree. Cached so every fixture bundle in a run shares one build identity (the
    honest answer: they were all built by the same code) and the whole-tree hash is paid
    once, not per bundle.
    """
    global _CODE_IDENTITY
    if _CODE_IDENTITY is None:
        _CODE_IDENTITY = arm_bundle.code_identity()
    return _CODE_IDENTITY


def build(from_condition="FixRest", to_condition="FixStim48", **kw):
    """One synthetic bundle for one ordered pair.

    An explicitly-supplied ``[]`` must REACH the producer: a truthiness fallback would
    silently substitute the default endpoints, and the empty-condition refusal would go
    untested while appearing to be tested.
    """
    progs = kw.pop("admitted", _UNSET)
    frm = kw.pop("from_endpoints", _UNSET)
    to = kw.pop("to_endpoints", _UNSET)
    meth = kw.pop("method", _UNSET)
    conds = kw.pop("conditions", _UNSET)
    code = kw.pop("code", _UNSET)
    s1 = kw.pop("stage1", _UNSET)
    return arm_bundle.build_bundle(
        from_condition=from_condition, to_condition=to_condition,
        admitted=admitted() if progs is _UNSET else progs,
        from_endpoints=endpoints(from_condition) if frm is _UNSET else frm,
        to_endpoints=endpoints(to_condition) if to is _UNSET else to,
        method=method() if meth is _UNSET else meth,
        conditions=list(CONDITIONS) if conds is _UNSET else conds,
        scorer_view_sha256=kw.pop("scorer_view_sha256", "a" * 64),
        stage1=stage1() if s1 is _UNSET else s1,
        code=code_identity() if code is _UNSET else code,
        **kw)


def build_all():
    """All 6 ordered-pair bundles — the fixture stand-in for the 120-arm release."""
    return [build(a, b) for a, b in ORDERED_PAIRS]
