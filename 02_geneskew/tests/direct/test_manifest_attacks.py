"""Adversarial attacks on the contributor manifest, through the WHOLE run.

The quarantined Claude Science table failed on exactly these shapes: extra donor
scopes, missing released scopes, ``None_None`` guide rows, extra pooled scopes,
unpinned sources. Each must FAIL CLOSED — and none of them may quietly change a
pooled-main score, the eligible set, or a rank.

TWO CLASSES OF ATTACK, and the difference is the point of this release pass:

  * a POOLED-MAIN attack breaks the evidence domain itself, and the run dies;
  * a SUPPORT attack has nowhere to land. By-guide and donor-pair estimates carry no
    contributor evidence here: no mask, no projection, no replication claim, no power
    to elevate an evidence tier. The old lane let a support object's COPIED metadata
    refuse a valid pooled estimate — 6,707 of 33,374 targets. So the strongest thing
    these tests can assert is a NEGATIVE: change the support inputs however you like,
    and every pooled score, rank and evaluability is bit-for-bit identical.
"""
import copy
import os
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from direct import config, domain, guides
from direct.manifest import ManifestError
from direct.run_screen import build_screen

from fixtures_direct import CONDITION, DONOR_PAIRS, TARGET_GENES, default_specs

pytestmark = pytest.mark.filterwarnings("ignore")

ENSG_TARGET = TARGET_GENES[0]


def _screen(result):
    return pd.read_parquet(os.path.join(result["out_dir"], "screen.parquet"))


def _rank_identity(result):
    """BOTH arms' pooled results: evaluability, score and rank, per arm.

    NaN-safe, so a refused score compares equal to a refused score.
    """
    cols = ["target_id"]
    for arm in config.ARMS:
        cols += [arm, config.ARM_RANK_COLUMN[arm],
                 f"{config.ARM_POLE[arm]}_evaluable"]
    df = _screen(result)[cols].sort_values("target_id")

    def cell(v):
        return None if pd.isna(v) else (float(v) if isinstance(v, float) else v)

    return [tuple(cell(r[c]) if c != "target_id" else r[c] for c in cols)
            for _, r in df.iterrows()]


@pytest.fixture
def baseline(synthetic_run):
    return build_screen(synthetic_run())


# --------------------------------------------------------------------------- #
# Hard failures: the manifest does not describe the released POOLED-MAIN universe.
# --------------------------------------------------------------------------- #
def test_an_extra_pooled_scope_fails_closed(synthetic_run):
    def attack(rows):
        # a SELF-CONSISTENT ghost identity, so the refusal is genuinely about the
        # scope not being in the release rather than about a malformed identity
        ghost = dict(rows[0], target_id="ENSG09999999999",
                     target_ensembl="ENSG09999999999",
                     released_estimate_id=f"ENSG09999999999_{CONDITION}",
                     estimate_type="main", estimate_id="main")
        return rows + [ghost]

    with pytest.raises(ManifestError, match="does not contain"):
        build_screen(synthetic_run(manifest_rows_fn=attack))


def test_an_extra_donor_scope_fails_closed(synthetic_run):
    """174,682 extra donor scopes is the shape that quarantined the CS table.

    It no longer fails as "a scope the release does not have" — it fails EARLIER, as a
    row outside the pooled-main evidence domain. That is the stronger refusal: the run
    has no method to check a donor-pair contributor claim at all, so it never reaches
    the question of whether the release ships that scope.
    """
    def attack(rows):
        ghost = dict(rows[0], estimate_type="donor_pair",
                     estimate_id=DONOR_PAIRS[0], donor_pair=DONOR_PAIRS[0])
        return rows + [ghost]

    with pytest.raises(ManifestError, match="pooled-main evidence domain"):
        build_screen(synthetic_run(manifest_rows_fn=attack))


def test_an_extra_guide_slot_scope_fails_closed(synthetic_run):
    def attack(rows):
        ghost = dict(rows[0], estimate_type="guide", estimate_id="guide_1")
        return rows + [ghost]

    with pytest.raises(ManifestError, match="pooled-main evidence domain"):
        build_screen(synthetic_run(manifest_rows_fn=attack))


def test_a_missing_released_scope_fails_closed(synthetic_run):
    """A whole pooled scope dropped. It names nothing, so it appears in no
    completeness iteration — only scope COVERAGE can see it."""
    def attack(rows):
        return [r for r in rows if r["target_id"] != TARGET_GENES[3]]

    with pytest.raises(ManifestError, match="missing .* released"):
        build_screen(synthetic_run(manifest_rows_fn=attack))


def test_a_duplicate_scope_and_guide_fails_closed(synthetic_run):
    def attack(rows):
        first = next(r for r in rows if r["guide_id"])
        return rows + [dict(first)]

    with pytest.raises(ManifestError, match="duplicate scope"):
        build_screen(synthetic_run(manifest_rows_fn=attack))


def test_a_none_none_guide_row_fails_closed(synthetic_run):
    """152 invalid None_None rows: a null identity is not an identity."""
    def attack(rows):
        out = copy.deepcopy(rows)
        for r in out:
            if r["target_id"] == ENSG_TARGET and r["evidence_state"] == "determined":
                r["guide_id"] = None          # determined + included, yet null
                break
        return out

    with pytest.raises(ManifestError, match="no guide_id"):
        build_screen(synthetic_run(manifest_rows_fn=attack))


def test_a_null_key_component_fails_closed(synthetic_run):
    def attack(rows):
        out = copy.deepcopy(rows)
        out[0]["released_estimate_id"] = None
        return out

    with pytest.raises(ManifestError, match="null key component"):
        build_screen(synthetic_run(manifest_rows_fn=attack))


def test_conflicting_n_guides_within_one_scope_fails_closed(synthetic_run):
    def attack(rows):
        out = copy.deepcopy(rows)
        mains = [r for r in out if r["target_id"] == ENSG_TARGET]
        mains[0]["n_guides"] = 7
        return out

    with pytest.raises(ManifestError, match="conflicting n_guides"):
        build_screen(synthetic_run(manifest_rows_fn=attack))


def test_a_determined_row_stripped_of_its_proof_fails_closed(synthetic_run):
    """A determined row with no method/source is not a proof. It is not downgraded to
    'ambiguous' — the whole manifest is refused."""
    def attack(rows):
        out = copy.deepcopy(rows)
        for r in out:
            if r["target_id"] == ENSG_TARGET and r["evidence_state"] == "determined":
                r["identity_method"] = None
                r["source_sha256"] = None
        return out

    with pytest.raises(ManifestError, match="must bind"):
        build_screen(synthetic_run(manifest_rows_fn=attack))


@pytest.mark.parametrize("revision", ["main", "latest", "HEAD", "", "master"])
def test_a_mutable_source_revision_fails_closed(synthetic_run, revision):
    sources = [{"name": "assigned_guide.h5ad", "sha256": "a" * 64,
                "revision": revision}]
    with pytest.raises(ManifestError, match="unpinned source|not a pin"):
        build_screen(synthetic_run(manifest_sources=sources))


def test_a_source_without_a_hash_fails_closed(synthetic_run):
    sources = [{"name": "assigned_guide.h5ad", "revision": "abc123",
                "sha256": "not-a-hash"}]
    with pytest.raises(ManifestError, match="no valid sha256"):
        build_screen(synthetic_run(manifest_sources=sources))


def test_no_sources_at_all_fails_closed(synthetic_run):
    with pytest.raises(ManifestError, match="non-empty list"):
        build_screen(synthetic_run(manifest_sources=[]))


# --------------------------------------------------------------------------- #
# A GENUINELY ambiguous scope costs exactly itself.
#
# "Genuinely" is doing real work here. This test used to manufacture the ambiguity by
# REWRITING T5's manifest rows into one ambiguous row while the raw source went on
# holding T5's two kept targeting guides — which is not an ambiguous scope, it is a
# DOWNGRADED one, and it is now refused (see the attack below). The honest way to make a
# scope unprovable is to make the SOURCE unable to prove it, which is what
# ``ambiguous_estimates`` does: the spec emits no contributor rows at all.
# --------------------------------------------------------------------------- #
def _genuinely_ambiguous_specs():
    """The default bundle, with T5 unprovable IN THE RAW SOURCE."""
    specs = []
    for s in default_specs():
        if s.target == TARGET_GENES[5]:
            s = replace(s, ambiguous_estimates=("main",))
        specs.append(s)
    return specs


def test_a_genuinely_ambiguous_pooled_scope_costs_only_that_target(synthetic_run):
    """T5 is unprovable AT SOURCE. It is unscoreable — and NOTHING else moves."""
    specs = _genuinely_ambiguous_specs()
    baseline = build_screen(synthetic_run(specs=default_specs()))
    result = build_screen(synthetic_run(specs=specs))
    screen = _screen(result).set_index("target_id")

    t5 = screen.loc[TARGET_GENES[5]]
    assert t5["mask_unresolved_reason"] == guides.MANIFEST_EVIDENCE_AMBIGUOUS
    assert bool(t5["A_evaluable"]) is False
    assert pd.isna(t5["away_from_A"])

    # Every OTHER target keeps its exact SCORE and evaluability: losing T5's evidence
    # changed nothing about what any other target measured.
    base = _screen(baseline).set_index("target_id")
    others = [t for t in screen.index if t != TARGET_GENES[5]]
    for arm in config.ARMS:
        pole = config.ARM_POLE[arm]
        for t in others:
            assert bool(screen.loc[t, f"{pole}_evaluable"]) == \
                bool(base.loc[t, f"{pole}_evaluable"]), (t, arm)
            a, b = screen.loc[t, arm], base.loc[t, arm]
            assert (pd.isna(a) and pd.isna(b)) or a == b, (t, arm)

        # The ranks are DENSE over the evaluable population, so dropping T5 shifts the
        # integers below it — that is the rank doing its job, not a score moving. What
        # must not change is the ORDER.
        def ordered(df):
            r = df[df[config.ARM_RANK_COLUMN[arm]].notna()]
            r = r.loc[[t for t in r.index if t != TARGET_GENES[5]]]
            return list(r.sort_values(config.ARM_RANK_COLUMN[arm]).index)

        assert ordered(screen) == ordered(base), arm

    # ...and the run is a DIFFERENT run, because its science changed
    assert result["run_id"] != baseline["run_id"]


# --------------------------------------------------------------------------- #
# THE DOWNGRADE. The cheapest evidence deletion there is, and nothing saw it.
#
# Relabel one determined scope's rows as a single ambiguous row. Drop its citations.
# The honest producer then regenerates the record table and the replay report from
# those rows, so EVERY count balances by construction: determined-1, ambiguous+1,
# named unchanged, complete==determined, records==offsets_proven, every hash correct.
# The manifest and the report agree with each other perfectly.
#
# And the raw source still holds that scope's two kept targeting guides, untouched.
#
# The victim loses its mask, its score and its rank. Before the source classification
# rule, the runtime built this screen happily and `verify_run --strict-replay` exited 0
# with 31/31 checks green.
# --------------------------------------------------------------------------- #
def _downgrade(target):
    """Collapse a determined scope to one ambiguous row, citing nothing."""
    def attack(rows):
        out, seen = [], False
        for r in rows:
            if r["target_id"] != target:
                out.append(r)
                continue
            if r["evidence_state"] != "determined" or seen:
                continue
            seen = True
            out.append({k: v for k, v in r.items()
                        if k not in ("identity_method", "source_id",
                                     "source_sha256")}
                       | {"evidence_state": "ambiguous", "guide_id": None,
                          "source_record_id": None})
        return out
    return attack


def test_downgrading_a_determined_scope_to_ambiguous_is_REFUSED(synthetic_run):
    """The source can determine this scope. Calling it unknown deletes evidence."""
    with pytest.raises(ManifestError, match="raw source can DETERMINE") as exc:
        build_screen(synthetic_run(manifest_rows_fn=_downgrade(TARGET_GENES[0])))
    # refused by the SOURCE classification, not by arithmetic and not by a hash
    assert "labelled ambiguous" in str(exc.value)


def test_the_downgrade_is_refused_BEFORE_any_artifact_exists(synthetic_run):
    """A refusal that leaves a screen behind is not a refusal."""
    args = synthetic_run(manifest_rows_fn=_downgrade(TARGET_GENES[0]))
    with pytest.raises(ManifestError):
        build_screen(args)
    assert not os.path.exists(args.out_root)


def test_downgrading_ANY_determined_scope_is_refused(synthetic_run):
    """Not a special case of T0: every determinable scope is protected."""
    for t in (TARGET_GENES[1], TARGET_GENES[2], TARGET_GENES[5]):
        with pytest.raises(ManifestError, match="raw source can DETERMINE"):
            build_screen(synthetic_run(manifest_rows_fn=_downgrade(t)))


def test_OVERCLAIMING_a_genuinely_ambiguous_scope_is_REFUSED(synthetic_run):
    """The mirror lie: name a guide for a scope the source cannot prove at all."""
    specs = _genuinely_ambiguous_specs()          # T5 has NO rows in the raw source

    def attack(rows):
        out = []
        for r in rows:
            if r["target_id"] == TARGET_GENES[5]:
                out.append(dict(r, evidence_state="determined",
                                guide_id="g-T5-1",
                                identity_method="released_per_guide_identity_column"))
            else:
                out.append(r)
        return out

    with pytest.raises(ManifestError):
        build_screen(synthetic_run(specs=specs, manifest_rows_fn=attack))


# --------------------------------------------------------------------------- #
# SUPPORT HAS NOWHERE TO LAND.
# --------------------------------------------------------------------------- #
def test_support_is_unavailable_and_says_so(baseline):
    """Not silently absent — explicitly unavailable, with a named reason."""
    contract = baseline["support_contract"]
    assert contract["state"] == domain.SUPPORT_STATE_UNAVAILABLE
    assert contract["reason"] == domain.SUPPORT_UNAVAILABLE
    assert contract["guide_support_available"] is False
    assert contract["donor_support_available"] is False
    assert contract["support_may_elevate_evidence_tier"] is False
    assert contract["support_masks_built"] == 0
    assert contract["support_estimates_projected"] == 0
    # the released support estimates are still COUNTED, not dropped
    assert contract["n_support_estimates_observed"] > 0


def test_changing_the_support_effects_cannot_move_a_single_pooled_score(
        synthetic_run, baseline):
    """THE invariant. Rewrite every guide-slot and donor-pair effect in the release —
    flip their signs, blow up their magnitudes — and re-run.

    If any pooled score, rank or evaluability moves, a support object is reaching the
    primary result through some path, which is precisely the bug this pass removes.
    """
    specs = default_specs()
    for s in specs:
        s.guide_slot_effects = {k: -v * 17.0 for k, v in s.guide_slot_effects.items()}
        s.donor_pair_effects = {k: -v * 23.0 for k, v in s.donor_pair_effects.items()}

    perturbed = build_screen(synthetic_run(specs))
    assert _rank_identity(perturbed) == _rank_identity(baseline)
    # the pooled masks are identical too: no support object contributed a gene
    assert perturbed["mask_sha256"] == baseline["mask_sha256"]


def test_removing_support_estimates_entirely_cannot_move_a_pooled_score(
        synthetic_run, baseline):
    """The release could have shipped no by-guide slots for a target at all."""
    specs = default_specs()
    for s in specs:
        s.guide_slot_effects = {}
        s.guide_slot_n_guides = {}

    stripped = build_screen(synthetic_run(specs))
    assert _rank_identity(stripped) == _rank_identity(baseline)
    assert stripped["mask_sha256"] == baseline["mask_sha256"]


def test_no_target_in_any_arm_is_elevated_above_tier_three(baseline):
    """Tiers 1 and 2 are STRUCTURALLY unreachable while support is unavailable."""
    screen = _screen(baseline)
    for arm in config.ARMS:
        pole = config.ARM_POLE[arm]
        tiers = set(screen[f"{pole}_evidence_tier"])
        assert not {"tier1_guide_and_donor_split", "tier2_guide_replicated"} & tiers
        assert not screen[f"{pole}_guide_replication_supported"].astype(bool).any()
        assert not screen[f"{pole}_donor_split_support"].astype(bool).any()


def test_a_support_estimate_never_acquires_a_mask(baseline):
    """No mask row exists for any non-pooled estimate. Not an empty one — none."""
    masks = pd.read_parquet(os.path.join(baseline["out_dir"], "masks.parquet"))
    assert set(masks["estimate_type"]) == {"main"}
    assert set(masks["estimate_id"]) == {"main"}


def test_every_support_estimate_is_still_accounted_for(baseline):
    """A silently absent estimate reads as 'the release does not ship it'."""
    contrib = pd.read_parquet(
        os.path.join(baseline["out_dir"], "contributing_guides.parquet"))
    support = contrib[contrib["estimate_type"] != "main"]
    assert len(support)
    assert set(support["estimate_type"]) == {"guide", "donor_pair"}
    assert support["guide_id"].isna().all()          # never guessed from a slot name
    assert (support["contributor_unresolved_reason"]
            == domain.SUPPORT_UNAVAILABLE).all()

    guide_support = pd.read_parquet(
        os.path.join(baseline["out_dir"], "guide_support.parquet"))
    assert len(guide_support)
    assert not guide_support["evaluated"].astype(bool).any()   # never projected
    assert guide_support["value"].isna().all()
    assert guide_support["guide_id"].isna().all()
