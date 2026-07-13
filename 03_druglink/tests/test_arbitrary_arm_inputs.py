"""Stage 3 accepts ARBITRARY arm content — the biology is not the contract.

The two arm SLOTS (`away_from_A`, `toward_B`) are the generic contract: A and B are poles
a Stage-1 selection defines, not a fixed biology. Treg-like → Th1-like is one instance.

What must therefore be arbitrary is the CONTENT of those slots: any targets, any ranks,
any desired modulations, an arm that carries nothing, a target set for which no drug
evidence exists at all. Stage 3 must admit and process every such run without special-
casing the fixture it happens to be tested on — and without inventing anything to fill a
gap.

Each case below drives Direct's REAL screen with a different arm configuration, admits it
through Direct's own standalone verifier, and runs the real Stage-3 engine over it.
"""
from __future__ import annotations

import dataclasses
import os

import direct_fixture as DF
from druglink import acquire_public, acquisition, armlever, run_stage3
from druglink import direct_run as dr


def _direct_roots():
    a, f = DF.direct_roots()
    import sys
    for p in (a, f):
        if p not in sys.path:
            sys.path.insert(0, p)
    import fixtures_direct as F
    return F


def _run(tmp_path, name, specs):
    """Build + admit a Direct run with this arm configuration, then build Stage 3."""
    import fixture_public_responses as FX

    built = DF.build_direct_run(os.path.join(str(tmp_path), name), lane="research_only",
                                specs=specs)
    direct = dr.load(built["run_dir"], built["inputs_root"], artifact_class="analysis",
                     direct_analysis=built["analysis"])
    cache = os.path.join(str(tmp_path), f"{name}_cache")
    acquire_public.acquire(cache_root=cache, artifact_class="analysis", direct=direct,
                           top_per_arm=25, sources=("uniprot", "chembl"),
                           chembl_release="CHEMBL_37",
                           transport=FX.FakeTransport(no_match_uniprot=True))
    acquired = acquisition.load_manifest(cache, "analysis", direct=direct)
    build = run_stage3.build(artifact_class="analysis", direct=direct, acquired=acquired)
    return direct, build


def _base_specs():
    F = _direct_roots()
    d = F.default_specs()
    return [dataclasses.replace(d[1], target=DF.CTLA4),
            dataclasses.replace(d[10], target=DF.IL2RA)]


# --------------------------------------------------------------------------- #
# Both arms carrying real, opposed direction evidence.
# --------------------------------------------------------------------------- #
def test_both_arms_with_opposed_directions_are_accepted(tmp_path):
    direct, build = _run(tmp_path, "opposed", _base_specs())
    screen = direct.screen

    assert len(screen) == 2
    # The two arms are independent and BOTH survive: one target is opposed across them.
    assert set(build["tables"]["arm_levers"][0]) >= {"desired_arm", "arm_rank"}
    arms = {r["desired_arm"] for r in build["tables"]["arm_levers"]}
    assert arms == set(armlever.ARMS), f"both arm slots must be expanded, got {arms}"
    assert build["tables"]["candidates"], "real drug evidence must reach candidates"


# --------------------------------------------------------------------------- #
# One arm carries nothing. The other still works; nothing is invented to fill it.
# --------------------------------------------------------------------------- #
def test_a_single_arm_run_is_accepted_and_the_empty_arm_is_not_invented(tmp_path):
    specs = [dataclasses.replace(s, b_effect=0.0) for s in _base_specs()]
    direct, build = _run(tmp_path, "single_arm", specs)

    b_mod = set(direct.screen["B_desired_target_modulation"].dropna().unique())
    assert b_mod == {"no_direction_evidence"}, (
        "the B arm carries no direction evidence in this run")

    levers = build["tables"]["arm_levers"]
    # BOTH slots are still expanded — an arm with no evidence is EMITTED as having none,
    # never dropped and never back-filled with a direction Stage 2 did not state.
    assert {r["desired_arm"] for r in levers} == set(armlever.ARMS)
    b_rows = [r for r in levers if r["desired_arm"] == armlever.ARM_B]
    assert b_rows, "the empty arm is still represented, not silently dropped"
    for r in b_rows:
        assert r["arm_desired_target_modulation"] in (None, "no_direction_evidence"), (
            "Stage 3 invented a direction for an arm Stage 2 left without evidence")

    # And the A arm is entirely unaffected by B being empty.
    a_rows = [r for r in levers if r["desired_arm"] == armlever.ARM_A]
    assert any(r["arm_rank"] is not None for r in a_rows), (
        "the populated arm must still rank independently of the empty one")


# --------------------------------------------------------------------------- #
# Targets with NO drug evidence at all. Zero candidates is a valid result.
# --------------------------------------------------------------------------- #
def test_a_run_whose_targets_have_no_drug_evidence_is_accepted_with_zero_candidates(
        tmp_path):
    """Direct's synthetic ENSG000000002xx targets genuinely have no UniProt entry.

    Stage 3 must admit the run, emit the arms, and report ZERO candidates — not fail,
    and not manufacture a drug to have something to say.
    """
    F = _direct_roots()
    d = F.default_specs()
    specs = [d[1], d[10]]                     # left as synthetic ids: no real gene at all
    direct, build = _run(tmp_path, "no_drugs", specs)

    assert len(direct.screen) == 2
    assert {r["desired_arm"] for r in build["tables"]["arm_levers"]} == set(armlever.ARMS)
    assert build["tables"]["candidates"] == [], (
        "no public drug evidence exists for these targets; zero candidates is the only "
        "honest result")
    assert build["tables"]["target_drug_edges"] == []
