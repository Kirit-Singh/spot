"""MUTATIONS 1, 2, 4, 5 — the bindings, and what happens when each one is broken.

Every test here builds a REAL Direct arm bundle through ``direct.arm_bundle`` and then
breaks exactly one binding. A secondary lane that survived any of these would be lending its
credit to an artifact nobody stands behind.
"""
from __future__ import annotations

import json
import os

import pandas as pd
import pytest
from direct import scorer_view
from fixtures_p2s import CONDITION, PROGRAM, make_release, write_arm_bundle
from p2s_arms import binding

KEY = f"direct|{PROGRAM}|increase|{CONDITION}"


def test_a_clean_binding_binds(bundle_dir, view, admit_report):
    bound = binding.bind(arm_key=KEY, bundle_dir=bundle_dir, view=view,
                         verifier_report=admit_report)
    assert bound["arm"].arm_key == KEY
    assert bound["base_portable"] is True
    assert bound["scorer_view_sha256"] == view["scorer_view_sha256"]
    assert bound["verifier"]["verdict"] == "admit"
    # the arm slot really came out of the bundle's own manifest
    assert bound["arm_slot"]["arm_key"] == KEY


def test_the_admitted_set_is_DERIVED_from_base_portable_and_excludes_th9(view):
    """Th9 is out because the release says it is not portable — not because a constant says so."""
    assert "th9_like" not in view["admitted_program_ids"]
    assert "th9_like" in view["excluded_program_ids"]
    assert view["n_admitted_programs"] == len(view["admitted_program_ids"])
    assert view["derived_from_legacy_registry"] is False


# --------------------------------------------------------------------------- #
# MUTATION 1 — the arm is not in the bound bundle.
# --------------------------------------------------------------------------- #
def test_MUTATION_arm_absent_from_the_bundle_is_refused(bundle_dir, view, admit_report):
    with pytest.raises(binding.ArmMismatchError) as e:
        binding.bind(arm_key="direct|th1_like|increase|Rest", bundle_dir=bundle_dir,
                     view=view, verifier_report=admit_report)
    assert e.value.reason in ("arm_is_not_in_the_bound_bundle",
                              "arm_condition_is_not_the_bundle_condition")


def test_MUTATION_th9_arm_is_refused_as_not_base_portable(bundle_dir, view, admit_report):
    with pytest.raises(binding.ProgramRefusedError) as e:
        binding.bind(arm_key=f"direct|th9_like|increase|{CONDITION}",
                     bundle_dir=bundle_dir, view=view, verifier_report=admit_report)
    assert e.value.reason == "program_is_not_base_portable"


@pytest.mark.parametrize("pid,reason", [
    ("cd4_ctl_like_actadj", "sensitivity_lane_refused"),
    ("rq_probe", "research_namespace_refused"),
])
def test_MUTATION_sensitivity_and_research_lanes_are_refused(pid, reason, bundle_dir, view,
                                                             admit_report):
    with pytest.raises(binding.ProgramRefusedError) as e:
        binding.bind(arm_key=f"direct|{pid}|increase|{CONDITION}", bundle_dir=bundle_dir,
                     view=view, verifier_report=admit_report)
    assert e.value.reason == reason


# --------------------------------------------------------------------------- #
# MUTATION 2 — the bundle was built against a different scorer view.
# --------------------------------------------------------------------------- #
def test_MUTATION_scorer_view_mismatch_is_refused(tmp_path, admit_report):
    """A bundle built when th1_like was admitted, bound to a release that no longer admits it."""
    built_view = scorer_view.view(make_release())
    bundle = write_arm_bundle(str(tmp_path / "direct"), built_view)

    other_view = scorer_view.view(make_release(portable={"th1_like": False}))
    assert other_view["scorer_view_sha256"] != built_view["scorer_view_sha256"]

    with pytest.raises(binding.ScorerMismatchError) as e:
        binding.bind(arm_key=KEY, bundle_dir=bundle, view=other_view,
                     verifier_report=admit_report)
    assert e.value.reason == "bundle_scorer_view_does_not_match_the_bound_release"


def test_MUTATION_a_different_PANEL_is_a_different_scorer_view(tmp_path, admit_report):
    """Same program ids, different panels. Not the same view — and not the same arms."""
    built_view = scorer_view.view(make_release())
    bundle = write_arm_bundle(str(tmp_path / "direct"), built_view)

    repanelled = scorer_view.view(make_release(panels={PROGRAM: ["ENSG99999999"]}))
    with pytest.raises(binding.ScorerMismatchError):
        binding.bind(arm_key=KEY, bundle_dir=bundle, view=repanelled,
                     verifier_report=admit_report)


# --------------------------------------------------------------------------- #
# MUTATION 4 — a program with no surviving panel.
# --------------------------------------------------------------------------- #
def test_MUTATION_missing_panel_refuses_the_arm_and_never_returns_zeros(tmp_path,
                                                                        admit_report):
    """MISSING STAYS MISSING. A zero is a measurement; an absence is not."""
    empty = scorer_view.view(make_release(panels={PROGRAM: []}))
    bundle = write_arm_bundle(str(tmp_path / "direct"), empty)

    with pytest.raises(binding.PanelMissingError) as e:
        binding.bind(arm_key=KEY, bundle_dir=bundle, view=empty,
                     verifier_report=admit_report)
    assert e.value.reason == "program_has_no_surviving_panel"
    assert "table of zeros" in str(e.value)


# --------------------------------------------------------------------------- #
# MUTATION 5 — an ALTERED RANK in the shipped arm rows.
# --------------------------------------------------------------------------- #
def test_MUTATION_an_altered_rank_is_caught_by_the_recomputed_row_hash(tmp_path, view,
                                                                       admit_report):
    """The rank is inside the hashed projection, so an edited one cannot pass."""
    bundle = write_arm_bundle(str(tmp_path / "direct"), view, tamper_rank=True)

    with pytest.raises(binding.AlteredRankError) as e:
        binding.bind(arm_key=KEY, bundle_dir=bundle, view=view,
                     verifier_report=admit_report)
    assert e.value.reason == "arm_rows_do_not_hash_to_the_bundle_claim"


def test_MUTATION_an_altered_VALUE_is_caught_too(tmp_path, view, admit_report):
    bundle = write_arm_bundle(str(tmp_path / "direct"), view)
    rows_path = os.path.join(bundle, "arms.parquet")
    df = pd.read_parquet(rows_path)
    df.loc[0, "value"] = float(df.loc[0, "value"] or 0.0) + 1.0
    df.to_parquet(rows_path, index=False)

    with pytest.raises(binding.AlteredRankError):
        binding.bind(arm_key=KEY, bundle_dir=bundle, view=view,
                     verifier_report=admit_report)


# --------------------------------------------------------------------------- #
# The bundle's own verifier must have ADMITTED it.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("verdict", ["reject", "", "pending"])
def test_a_bundle_its_own_verifier_did_not_admit_is_refused(verdict, bundle_dir, view):
    with pytest.raises(binding.VerifierRejectedError) as e:
        binding.bind(arm_key=KEY, bundle_dir=bundle_dir, view=view,
                     verifier_report={"verdict": verdict})
    assert e.value.reason == "bundle_was_not_admitted_by_its_verifier"


def test_an_incomplete_bundle_is_refused(tmp_path, view, admit_report):
    d = tmp_path / "direct" / "deadbeef"
    d.mkdir(parents=True)
    (d / "arm_bundle.json").write_text(json.dumps({"condition": CONDITION}))
    with pytest.raises(binding.BindingError) as e:
        binding.bind(arm_key=KEY, bundle_dir=str(d), view=view,
                     verifier_report=admit_report)
    assert e.value.reason == "bundle_is_incomplete"
