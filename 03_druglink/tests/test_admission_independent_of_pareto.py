"""Stage-3 admission does NOT depend on Pareto tier or cross-arm concordance.

Addendum (sha256 `c477356278c5b7d2…`), final clause: pair-derived **Pareto / concordance
is JOIN-TIME DISPLAY ONLY** — off by default, no new score, and **not part of Stage-3
admission**. Legacy pair fields are compatibility-only.

Stage 3 already treats `joint_status` / `pareto_tier` / `joint_ordering_method_id` and the
cross-arm columns as **pass-through context** (carried byte-identical, never authored). But
"nothing reads them" is a claim about absence, and absence is exactly what a grep cannot
prove — a single `if row["pareto_tier"] == 1:` buried in candidate selection would satisfy
every existing test while silently making a display field load-bearing.

So this proves it the only way absence can be proved: **vary the fields and show the output
does not move.** Drive the real engine twice over the same Direct run — once as Stage 2
released it, once with Pareto/concordance rewritten to adversarial values — and assert the
admitted targets, candidates and edges are IDENTICAL.

If Stage 3 ever starts gating on a tier, these tests fail. That is the point.
"""
from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from druglink import acquisition, armlever, run_stage3

JOINT = ("joint_status", "pareto_tier", "joint_ordering_method_id")
CROSS = armlever.CROSS_ARM_COLUMNS          # concordance_class, desired_modulation_agreement


def _build(direct, cache, screen):
    """Rebuild Stage 3 over a screen we have rewritten, through the REAL engine.

    ``DirectRun`` is a frozen dataclass, so the swap is an explicit ``replace`` — the run
    stays fully admitted (same run_id, same binding, same verified files); only the
    display-context columns move.
    """
    swapped = dataclasses.replace(direct, screen=screen)
    acquired = acquisition.load_manifest(cache, "analysis", direct=swapped)
    return run_stage3.build(artifact_class="analysis", direct=swapped, acquired=acquired)


def _admission_fingerprint(build):
    """WHAT was admitted — not the display context carried alongside it."""
    t = build["tables"]
    targets = sorted({(r["target_id"], r["desired_arm"], r["arm_rank"],
                       r["arm_desired_target_modulation"])
                      for r in t["arm_levers"]})
    cands = sorted(c["candidate_id"] for c in t["candidates"])
    edges = sorted((e["edge_id"], e["target_ensembl"], e["desired_arm"],
                    e["active_moiety_id"], e["origin_type"],
                    e["directional_evidence_status"], e["stage3_evidence_class"],
                    e["observed_perturbation_support"])
                   for e in t["target_drug_edges"])
    queued = sorted((c["candidate_id"], c["stage4_assessment_status"])
                    for c in t["candidates"])
    return {"targets": targets, "candidates": cands, "edges": edges, "queued": queued}


@pytest.fixture(scope="module")
def baseline(loaded_direct, analysis_cache):
    return _admission_fingerprint(
        _build(loaded_direct, analysis_cache, loaded_direct.screen.copy()))


def test_admission_is_identical_when_every_pareto_tier_is_rewritten(
        loaded_direct, analysis_cache, baseline):
    """Collapse every tier to the worst, then to the best. Admission must not move."""
    for tier in (7, 1):
        screen = loaded_direct.screen.copy()
        if "pareto_tier" not in screen.columns:
            pytest.skip("Stage 2 released no pareto_tier for this run")
        screen["pareto_tier"] = pd.array([tier] * len(screen), dtype="Int64")
        got = _admission_fingerprint(_build(loaded_direct, analysis_cache, screen))
        assert got == baseline, (
            f"admission changed when every pareto_tier was set to {tier} — a DISPLAY-ONLY "
            "field is gating Stage-3 admission")


def test_admission_is_identical_when_pareto_tier_is_removed_entirely(
        loaded_direct, analysis_cache, baseline):
    """Pareto is 'off by default'. With the column absent, admission must be unchanged."""
    screen = loaded_direct.screen.copy()
    screen = screen.drop(columns=[c for c in JOINT if c in screen.columns])
    got = _admission_fingerprint(_build(loaded_direct, analysis_cache, screen))
    assert got == baseline, (
        "admission changed when the joint context was absent — Stage 3 cannot require a "
        "field the addendum makes optional and display-only")


def test_admission_is_identical_when_joint_status_is_rewritten(
        loaded_direct, analysis_cache, baseline):
    screen = loaded_direct.screen.copy()
    if "joint_status" not in screen.columns:
        pytest.skip("Stage 2 released no joint_status for this run")
    for value in ("not_evaluable", "opposed", "both_arms"):
        screen["joint_status"] = value
        got = _admission_fingerprint(_build(loaded_direct, analysis_cache, screen))
        assert got == baseline, (
            f"admission changed when joint_status was forced to {value!r} — a "
            "display-only label is gating Stage-3 admission")


def test_admission_is_identical_when_cross_arm_concordance_is_rewritten(
        loaded_direct, analysis_cache, baseline):
    """Concordance is pair-derived and compatibility-only. It must not select targets."""
    screen = loaded_direct.screen.copy()
    present = [c for c in CROSS if c in screen.columns]
    if not present:
        pytest.skip("Stage 2 released no cross-arm concordance columns for this run")
    for col in present:
        screen[col] = "discordant"
    got = _admission_fingerprint(_build(loaded_direct, analysis_cache, screen))
    assert got == baseline, (
        f"admission changed when {present} were forced to 'discordant' — pair-derived "
        "concordance is gating Stage-3 admission")


def test_the_engine_reads_no_joint_or_concordance_field_for_admission(loaded_direct):
    """The static half: no admission module may even name these fields.

    `joint_context.py` is the pass-through carrier and is allowed to name them; nothing
    that decides WHAT is admitted may. A grep cannot prove absence on its own — but paired
    with the mutation tests above, it catches a new reader the moment it is introduced.
    """
    import inspect

    from druglink import candidates, drug_mapping, mechanisms, targets
    forbidden = set(JOINT) | set(CROSS) | {"pareto", "concordance"}
    for mod in (candidates, targets, mechanisms, drug_mapping):
        src = inspect.getsource(mod)
        # strip comments/docstrings: prose may DISCUSS the rule; code may not read it.
        code = "\n".join(ln.split("#", 1)[0] for ln in src.splitlines())
        for name in sorted(forbidden):
            assert name not in code, (
                f"{mod.__name__} references {name!r} in code — Pareto/concordance is "
                "display-only and must never reach an admission decision")
