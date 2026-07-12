"""SUPPORT IS UNAVAILABLE, and every artifact must say so honestly.

The by-guide and donor-pair estimates carry no contributor evidence in this pass, so
Stage-2 does not know WHICH guide contributed to which support estimate. Support is
therefore not merely unused — it is INADMISSIBLE, and the difference matters in two
directions that this module pins from both ends:

  * NOTHING a support matrix contains may reach a pooled score, rank, mask or tier.
    Not by projection, not by masking, not by replication, not by a tier elevation. The
    strongest possible statement of that is a SIGN-FLIP: negate every support effect,
    multiply it by a thousand, and every pooled number must come back bit-identical. If
    a single score moved, some code path was reading support as evidence.
  * The artifact may not CLAIM support was evaluated. ``A_support_status='evaluated'``
    asserts that support evidence existed and was assessed; emitted where support was
    unavailable, it turns "we could not ask" into "we asked and found nothing", and
    every downstream reader of the null support columns believes a negative result.

The second was a live defect: the status was computed from arm evaluability alone, so
every evaluable arm in a support-less pass was labelled ``evaluated``.
"""
from __future__ import annotations

import os

import pandas as pd
import pytest
from direct import arms, config, disposition, domain
from direct.run_screen import build_screen
from fixtures_direct import default_specs

TIERS_WITHOUT_SUPPORT = {"not_evaluated", "evaluable_no_directional_signal",
                         "tier3_screen_only"}
ELEVATED_TIERS = {"tier1_guide_and_donor_split", "tier2_guide_replicated"}


def _read(result, name):
    return pd.read_parquet(os.path.join(result["out_dir"], name))


# --------------------------------------------------------------------------- #
# 1. The rule itself: availability is asked BEFORE evaluability.
# --------------------------------------------------------------------------- #
def test_an_evaluable_arm_without_support_is_NOT_evaluated():
    """The defect, isolated: evaluable + no support != 'evaluated'."""
    status = disposition.support_status(arm_evaluable=True, base_passed=True,
                                        support_available=False)
    assert status == domain.SUPPORT_UNAVAILABLE
    assert status != disposition.SUPPORT_STATUS_EVALUATED


def test_an_evaluable_arm_WITH_support_is_evaluated():
    """The honest 'evaluated' still exists — it just has to be earned."""
    assert disposition.support_status(
        arm_evaluable=True, base_passed=True,
        support_available=True) == disposition.SUPPORT_STATUS_EVALUATED


@pytest.mark.parametrize("base_passed,expected", [
    (False, "not_evaluated_base_qc"),
    (True, "not_evaluated_arm"),
])
def test_a_non_evaluable_arm_names_WHICH_gate_stopped_it(base_passed, expected):
    """With support available, the two 'not evaluated' reasons stay distinguishable."""
    assert disposition.support_status(
        arm_evaluable=False, base_passed=base_passed,
        support_available=True) == expected


def test_unavailability_outranks_every_other_reason():
    """No combination of evaluability can produce 'evaluated' with no support."""
    for arm_evaluable in (True, False):
        for base_passed in (True, False):
            assert disposition.support_status(
                arm_evaluable=arm_evaluable, base_passed=base_passed,
                support_available=False) == domain.SUPPORT_UNAVAILABLE


def test_the_emitted_arm_fields_carry_the_unavailable_status(axis):
    """arm_fields is where the lie was emitted; both paths are pinned here."""
    common = dict(pole="A", value=0.5, delta={"delta": 0.5, "status": "ok",
                                              "n_panel_surviving": 3,
                                              "n_control_surviving": 12},
                  base_state="qc_pass_multi_guide", base_passed=True, slots=[],
                  pair_values={}, splits=[], zscore_value=0.4)

    unavailable = arms.arm_fields(**common, support_available=False)
    assert unavailable["A_support_status"] == domain.SUPPORT_UNAVAILABLE
    assert unavailable["A_evaluable"] is True          # the ARM is still evaluable...
    assert unavailable["A_evidence_tier"] == "tier3_screen_only"   # ...but never lifted

    available = arms.arm_fields(**common, support_available=True)
    assert available["A_support_status"] == disposition.SUPPORT_STATUS_EVALUATED


# --------------------------------------------------------------------------- #
# 2. A real run: the status the release actually ships.
# --------------------------------------------------------------------------- #
def test_no_emitted_row_claims_support_was_evaluated(synthetic_run):
    result = build_screen(synthetic_run())
    screen = _read(result, "screen.parquet")
    for pole in ("A", "B"):
        assert (screen[f"{pole}_support_status"] == domain.SUPPORT_UNAVAILABLE).all()
        assert (screen[f"{pole}_support_status"] != "evaluated").all()


def test_no_arm_is_ever_elevated_above_tier_3(synthetic_run):
    result = build_screen(synthetic_run())
    screen = _read(result, "screen.parquet")
    for pole in ("A", "B"):
        tiers = set(screen[f"{pole}_evidence_tier"])
        assert not (tiers & ELEVATED_TIERS)
        assert tiers <= TIERS_WITHOUT_SUPPORT
        assert not screen[f"{pole}_guide_replication_supported"].astype(bool).any()
        assert not screen[f"{pole}_donor_split_support"].astype(bool).any()


def test_the_support_contract_says_zero_projected_and_zero_masked(synthetic_run):
    result = build_screen(synthetic_run())
    contract = result["support_contract"]
    assert contract["state"] == domain.SUPPORT_STATE_UNAVAILABLE
    assert contract["support_estimates_projected"] == 0
    assert contract["support_masks_built"] == 0
    assert contract["support_may_elevate_evidence_tier"] is False


def test_the_masks_table_holds_no_support_estimate(synthetic_run):
    """A support estimate has no contributor evidence, so it earns no mask gene."""
    result = build_screen(synthetic_run())
    masks = _read(result, "masks.parquet")
    assert set(masks["estimate_type"]) <= {"main"}
    assert set(masks["estimate_id"]) <= {"main"}


# --------------------------------------------------------------------------- #
# 3. THE SIGN-FLIP / MAGNITUDE ATTACK.
#
# If any code path reads a support matrix as evidence, this moves a number.
# --------------------------------------------------------------------------- #
def _hostile_specs(scale: float):
    """Every support effect negated and blown up. The pooled effects are untouched."""
    specs = default_specs()
    for s in specs:
        s.guide_slot_effects = {slot: -v * scale
                                for slot, v in s.guide_slot_effects.items()}
        s.donor_pair_effects = {pair: -v * scale
                                for pair, v in s.donor_pair_effects.items()}
    return specs


POOLED_COLUMNS = (
    list(config.ARMS)
    + list(config.ARM_RANK_COLUMN.values())
    + [f"{p}_{f}" for p in ("A", "B") for f in (
        "delta", "evaluable", "state", "projection_status", "panel_surviving",
        "control_surviving", "evidence_tier", "support_status", "support_state",
        "desired_target_modulation", "guide_replication_state",
        "guide_replication_supported", "donor_split_support")]
    + ["base_qc_state", "base_qc_passed", "mask_resolved", "mask_gene_count",
       "concordance_class", "desired_modulation_agreement"])


@pytest.mark.parametrize("scale", [1.0, 1000.0])
def test_flipping_every_support_effect_changes_no_pooled_number(synthetic_run, scale):
    """Negate and inflate all support; every pooled score, rank and state is identical.

    This is the property the whole pass rests on. Support cannot reach the science,
    so support cannot move the science — and if it ever does, it moves it HERE first.
    """
    honest = build_screen(synthetic_run(default_specs()))
    hostile = build_screen(synthetic_run(_hostile_specs(scale)))

    a = _read(honest, "screen.parquet").sort_values("target_id").reset_index(drop=True)
    b = _read(hostile, "screen.parquet").sort_values("target_id").reset_index(drop=True)

    pd.testing.assert_frame_equal(a[POOLED_COLUMNS], b[POOLED_COLUMNS],
                                  check_dtype=True)


@pytest.mark.parametrize("scale", [1.0, 1000.0])
def test_flipping_every_support_effect_changes_no_mask(synthetic_run, scale):
    """The mask hash is bound into run_id. A support-driven mask would change it."""
    honest = build_screen(synthetic_run(default_specs()))
    hostile = build_screen(synthetic_run(_hostile_specs(scale)))
    assert honest["mask_sha256"] == hostile["mask_sha256"]

    ma = _read(honest, "masks.parquet").sort_values(
        ["target_id", "masked_gene_ensembl"]).reset_index(drop=True)
    mb = _read(hostile, "masks.parquet").sort_values(
        ["target_id", "masked_gene_ensembl"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(ma.drop(columns=["run_id"]),
                                  mb.drop(columns=["run_id"]))


def test_the_support_tables_still_ENUMERATE_every_released_estimate(synthetic_run):
    """Refusing to score support is not the same as pretending it does not exist.

    A silently absent row reads as "the release does not ship this estimate". Every
    released support estimate is emitted, with a null value and a named reason.
    """
    result = build_screen(synthetic_run())
    guide = _read(result, "guide_support.parquet")
    donor = _read(result, "donor_support.parquet")

    assert len(guide) > 0 and len(donor) > 0
    assert guide["value"].isna().all()               # never projected
    assert not guide["evaluated"].astype(bool).any()
    assert donor["half_a_value"].isna().all()
    assert donor["half_b_value"].isna().all()
    assert not donor["evaluable"].astype(bool).any()
    assert (donor["missing_reason"] == domain.SUPPORT_UNAVAILABLE).all()


def test_a_guide_slot_never_acquires_a_guide_identity(synthetic_run):
    """A slot NAME is not evidence of which guide contributed to it."""
    result = build_screen(synthetic_run())
    guide = _read(result, "guide_support.parquet")
    assert guide["guide_id"].isna().all()

    contrib = _read(result, "contributing_guides.parquet")
    support = contrib[contrib["estimate_type"] != "main"]
    assert len(support) > 0                          # enumerated...
    assert support["guide_id"].isna().all()          # ...and never identified


# --------------------------------------------------------------------------- #
# 4. THE STANDALONE VERIFIER HOLDS NO SUPPORT MATRIX.
#
# Leaving the effect vectors loaded-but-unused is not the same as not loading them. As
# long as the verifier has the numbers in its hands, projecting them is one line away —
# and the checker would then be certifying a claim the run is forbidden to make. So the
# support reader is METADATA ONLY, and that is enforced two ways: structurally (no code
# path opens a support layer) and behaviourally (the verifier's verdict does not move
# when every support matrix is negated and inflated).
# --------------------------------------------------------------------------- #
def test_the_verifier_has_no_support_LAYER_read_anywhere_in_its_source():
    """Structural: the only dense read the verifier may make is the POOLED estimate."""
    import ast

    from direct import trust
    here = os.path.dirname(os.path.abspath(trust.__file__))

    for mod in ("verify_run.py", "verify_tables.py", "verify_source.py",
                "verify_evidence.py", "verify_rules.py", "verify_binding.py"):
        src = open(os.path.join(here, mod)).read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            # any subscript whose literal names a modality layer: f["mod/..."]["layers"]
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                v = node.value
                if "mod/" in v and "layer" in v:
                    raise AssertionError(
                        f"{mod} opens a SUPPORT layer ({v!r}); support carries no "
                        "contributor evidence and its matrices must never be read")
        # the pooled layer is the ONE legitimate dense read, and only verify_run makes it
        if mod != "verify_run.py":
            assert "layers/log_fc" not in src, (
                f"{mod} reads a dense layer; only verify_run reads the pooled estimate")


def test_the_verifier_support_reader_returns_identity_ONLY(synthetic_run):
    """No 'effect', no gene axis, no n_guides — nothing a projection could consume."""
    from direct.verify_run import Report, read_support_identities

    args = synthetic_run()
    rep = Report()
    mods = read_support_identities(args.by_guide, "StimX", rep)
    assert mods, "the fixture ships guide modalities"
    for _mod_id, block in mods.items():
        assert set(block) == {"by_target"}
        for _target, entry in block["by_target"].items():
            assert set(entry) == {"released_estimate_id"}
    assert rep.failures == []


@pytest.mark.parametrize("scale", [1.0, 1000.0])
def test_the_verifier_verdict_is_unmoved_by_hostile_support_matrices(synthetic_run,
                                                                    scale):
    """Behavioural: negate and inflate every support effect; the verifier still passes.

    If any verifier path read a support matrix, the reconstruction it compares against
    the run would change and the verdict would flip.
    """
    from test_source_replay import run_and_verify, verify

    args = run_and_verify(synthetic_run(_hostile_specs(scale)))
    assert verify(args, strict=False) == 0
