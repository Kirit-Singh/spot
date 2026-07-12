"""Full synthetic run: no real data, every release invariant asserted.

The fixture writes a structurally faithful miniature of the released artifacts
(categorical obs, ``layers/log_fc``, guide slots WITHOUT sgRNA identity, six
overlapping donor-pair modalities, a smaller donor gene universe) plus an
explicit source-hash-bound contributor manifest. It is NOT a scientific result
and no real ranking is produced.
"""
import json
import os

import pandas as pd
import pytest
from direct import config, disposition, domain, gate, guides, preflight
from direct.run_screen import build_screen
from direct.selection import SelectionError
from fixtures_direct import (
    COMMON_UNIVERSE,
    DONOR_DROPPED_GENE,
    TARGET_GENES,
    UNIVERSE,
    default_specs,
)


@pytest.fixture
def run(synthetic_run):
    args = synthetic_run()
    return build_screen(args), args


def _read(result, name):
    return pd.read_parquet(os.path.join(result["out_dir"], name))


def _json(result, name):
    with open(os.path.join(result["out_dir"], name)) as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# Disposition and ranking.
# --------------------------------------------------------------------------- #
def test_every_source_target_is_disposed_exactly_once(run):
    result, _ = run
    screen = _read(result, "screen.parquet")
    assert len(screen) == 18
    assert screen["target_id"].is_unique
    assert screen["base_qc_state"].notna().all()
    for pole in ("A", "B"):
        assert screen[f"{pole}_state"].notna().all()   # every arm is disposed too
    v = result["verification"]
    assert v["complete_disposition"] is True
    assert v["row_count"] == v["source_target_count"] == 18


def test_each_arm_rank_is_a_nullable_integer_null_where_not_evaluable(run):
    result, _ = run
    screen = _read(result, "screen.parquet")
    for arm in config.ARMS:
        col = config.ARM_RANK_COLUMN[arm]
        evaluable = screen[f"{config.ARM_POLE[arm]}_evaluable"].astype(bool)
        assert str(screen[col].dtype) == "Int64"          # never a NaN float
        assert screen.loc[~evaluable, col].isna().all()
        ranked = screen.loc[evaluable & screen[arm].notna(), col]
        assert sorted(ranked.tolist()) == list(range(1, len(ranked) + 1))
    v = result["verification"]["ranking"]
    assert v["arm_ranks_all_valid"] is True


def test_a_target_failing_base_qc_is_ranked_in_neither_arm(run):
    result, _ = run
    screen = _read(result, "screen.parquet").set_index("target_id")

    # T7 would have the largest away_from_A of all, but it is underpowered on
    # cells -> base QC fails -> BOTH arms are excluded, at any score.
    t7 = screen.loc[TARGET_GENES[7]]
    assert t7["base_qc_state"] == "underpowered_cells"
    assert bool(t7["base_qc_passed"]) is False
    for pole, arm in (("A", config.ARM_A), ("B", config.ARM_B)):
        assert bool(t7[f"{pole}_evaluable"]) is False
        assert t7[f"{pole}_state"] == "excluded_base_qc"
        assert pd.isna(t7[config.ARM_RANK_COLUMN[arm]])
        assert pd.isna(t7[arm])
    v = result["verification"]["ranking"]["per_arm"]
    for arm in config.ARMS:
        assert v[arm]["not_evaluable_with_a_rank"] == []
        assert v[arm]["evaluable_without_a_rank"] == []


def test_unscoreable_targets_carry_their_exact_reason(run):
    result, _ = run
    screen = _read(result, "screen.parquet").set_index("target_id")
    # T3 is absent from the sgRNA library, so the manifest can prove no identity ->
    # ambiguous, and ambiguous stays UNAVAILABLE rather than being rounded to a guess.
    row = screen.loc[TARGET_GENES[3]]
    assert row["mask_unresolved_reason"] == guides.MANIFEST_EVIDENCE_AMBIGUOUS
    assert row["base_qc_state"] == "mask_unresolved"
    for pole, arm in (("A", config.ARM_A), ("B", config.ARM_B)):
        assert pd.isna(row[config.ARM_RANK_COLUMN[arm]])
        assert pd.isna(row[arm])                     # refused, not scored
        assert row[f"{pole}_projection_status"] == "mask_unresolved"


def test_a_support_object_can_never_take_down_the_pooled_estimate(run):
    """THE RETIRED SLOT-CONTRADICTION GATE, pinned as retired.

    T4 ships two contributing guides and only ONE released guide slot; T8 declares a
    pooled n_guides of 1 while by_guide ships TWO guide-level DEs. The old rule read
    each as the release contradicting itself and refused the whole target — 6,707 of
    33,374 of them. Both disagreements are with a support object's COPIED pooled
    metadata, which is not an independent witness. The pooled fit resolves from its own
    manifest scope and its own n_guides, so both targets are scored.
    """
    result, _ = run
    screen = _read(result, "screen.parquet").set_index("target_id")
    for target in (TARGET_GENES[4], TARGET_GENES[8]):
        row = screen.loc[target]
        assert row["mask_resolved"] if "mask_resolved" in row else True
        assert pd.isna(row["mask_unresolved_reason"]), target
        assert bool(row["A_evaluable"]) is True, target
        assert pd.notna(row["away_from_A"]), target
        assert pd.notna(row["rank_away_from_A"]), target


# --------------------------------------------------------------------------- #
# The contributing-guide contract.
# --------------------------------------------------------------------------- #
def test_identity_comes_from_the_manifest_not_from_the_slot_name(run):
    result, _ = run
    contrib = _read(result, "contributing_guides.parquet")

    # T1's library holds g-T1-1 and g-T1-2; only ONE guide contributed, and the
    # manifest says it was g-T1-2. An alphanumeric slot rule would have said
    # g-T1-1. The lane must follow the manifest.
    t1 = contrib[(contrib["target_id"] == TARGET_GENES[1])
                 & (contrib["estimate_id"] == "main")]
    assert list(t1["guide_id"]) == ["g-T1-2"]
    assert t1.iloc[0]["contributor_source"] == "manifest"

    # The guide SLOT gets no guide at all: support has no contributor evidence in this
    # pass, and a slot name is not evidence of which guide contributed to it.
    t1_slot = contrib[(contrib["target_id"] == TARGET_GENES[1])
                      & (contrib["estimate_id"] == "guide_1")]
    assert t1_slot["guide_id"].isna().all()
    assert (t1_slot["contributor_unresolved_reason"]
            == domain.SUPPORT_UNAVAILABLE).all()

    # T2: three library guides, two contributed -- the manifest names which two,
    # and the unused guide never appears.
    t2 = contrib[(contrib["target_id"] == TARGET_GENES[2])
                 & (contrib["estimate_id"] == "main")]
    assert sorted(t2["guide_id"]) == ["g-T2-1", "g-T2-3"]
    assert "g-T2-2" not in set(contrib["guide_id"].dropna())


def test_an_ambiguous_identity_stays_unavailable(run):
    result, _ = run
    contrib = _read(result, "contributing_guides.parquet")
    t3 = contrib[(contrib["target_id"] == TARGET_GENES[3])
                 & (contrib["estimate_id"] == "main")]
    assert len(t3) == 1
    assert pd.isna(t3.iloc[0]["guide_id"])
    assert t3.iloc[0]["contributor_status"] == "unresolved"
    assert t3.iloc[0]["contributor_unresolved_reason"] == \
        guides.MANIFEST_EVIDENCE_AMBIGUOUS


def test_only_the_pooled_estimate_is_masked_and_support_never_borrows_it(run):
    """A support estimate gets NO mask — never the pooled one, never an empty one.

    An empty mask would read as "nothing needed masking". The truth is that this pass
    never knew which guide contributed to a slot, so it masks nothing and says so.
    """
    result, _ = run
    masks = _read(result, "masks.parquet")
    contrib = _read(result, "contributing_guides.parquet")

    # NOTHING but pooled-main is masked. Not an empty mask for a slot -- no mask row
    # for a slot AT ALL, because no support estimate was ever projected.
    assert set(masks["estimate_type"]) == {"main"}
    assert set(masks["estimate_id"]) == {"main"}

    t0 = masks[(masks["target_id"] == TARGET_GENES[0])
               & (masks["estimate_id"] == "main")]
    assert set(t0["masked_gene_ensembl"].dropna())          # the pooled mask is real

    # the support estimates ARE still accounted for -- in the contributor table, with
    # a null guide and an explicit reason. Silently dropping them would read as "the
    # release does not ship them".
    slots = contrib[(contrib["target_id"] == TARGET_GENES[0])
                    & (contrib["estimate_type"] != "main")]
    assert len(slots)
    assert slots["guide_id"].isna().all()
    assert (slots["contributor_unresolved_reason"]
            == domain.SUPPORT_UNAVAILABLE).all()

    # every mask row is keyed by the full estimate identity
    for col in ("estimate_type", "estimate_id", "target_id", "condition",
                "donor_pair"):
        assert col in masks.columns


# --------------------------------------------------------------------------- #
# Guide and donor support.
# --------------------------------------------------------------------------- #
def test_no_target_can_make_a_guide_replication_claim_in_either_direction(run):
    """Support is UNAVAILABLE, which is not the same as support having FAILED.

    T0's two guides agree and T5's disagree, but neither fact is reachable: the slot
    estimates were never projected, so the lane makes no replication claim either way.
    Reporting T5 as 'discordant' would be inventing a negative result out of numbers
    that were never evidence.
    """
    result, _ = run
    screen = _read(result, "screen.parquet").set_index("target_id")

    for target in (TARGET_GENES[0], TARGET_GENES[5], TARGET_GENES[9]):
        row = screen.loc[target]
        for pole in ("A", "B"):
            assert row[f"{pole}_guide_replication_state"] == \
                disposition.REPLICATION_SUPPORT_UNAVAILABLE, target
            assert bool(row[f"{pole}_guide_replication_supported"]) is False
            assert row[f"{pole}_n_guides_mapped"] == 0     # nothing was ever mapped
            assert row[f"{pole}_n_guides_evaluated"] == 0

    # ...and with no support, no arm can be elevated above tier 3.
    evaluable = screen[screen["A_evaluable"].astype(bool)]
    assert set(evaluable["A_evidence_tier"]) <= {"tier3_screen_only",
                                                 "evaluable_no_directional_signal"}


def test_a_multi_guide_target_is_eligible_and_kept_whole(run):
    """eligible_multi_guide is a first-class eligible state, not a dropped row."""
    result, _ = run
    screen = _read(result, "screen.parquet").set_index("target_id")
    t9 = screen.loc[TARGET_GENES[9]]
    assert t9["base_qc_state"] == "qc_pass_multi_guide"
    assert bool(t9["base_qc_passed"]) is True
    assert bool(t9["A_evaluable"]) and bool(t9["B_evaluable"])
    assert pd.notna(t9["rank_away_from_A"]) and pd.notna(t9["rank_toward_B"])
    assert t9["n_guides_source"] == 3

    contract = _json(result, "provenance.json")["stage2_direct_contract"]
    assert "qc_pass_multi_guide" in contract["base_qc_vocabulary"]["pass_states"]


def test_donor_pairs_are_enumerated_but_carry_no_split_support(run):
    """The six released donor pairs still collapse to three complementary splits, and
    every one of them is emitted — a silently absent estimate would read as "the
    release does not ship it". None of them supports anything: no donor-pair estimate
    was projected, so no split can be evaluable.
    """
    result, _ = run
    donor = _read(result, "donor_support.parquet")
    screen = _read(result, "screen.parquet").set_index("target_id")
    prov = _json(result, "provenance.json")

    contract = prov["donor_contract"]
    assert contract["n_donor_pair_matrices"] == 6
    assert contract["n_splits"] == 3
    assert contract["effective_donor_n"] == 4
    assert contract["donor_tokens"] == ["CE0006864", "CE0008162", "CE0008678",
                                        "CE0010866"]
    # no Stage-1 crosswalk was supplied, so it is declared unavailable, not guessed
    assert contract["stage1_donor_crosswalk"]["status"] == "unavailable"
    # three splits PER ARM, still emitted
    t0_rows = donor[donor["target_id"] == TARGET_GENES[0]]
    assert len(t0_rows) == 3 * len(config.ARMS)
    assert set(t0_rows["arm"]) == set(config.ARMS)
    assert not t0_rows["evaluable"].astype(bool).any()

    for target in (TARGET_GENES[0], TARGET_GENES[6]):
        row = screen.loc[target]
        for pole in ("A", "B"):
            assert (row[f"{pole}_n_splits_total"],
                    row[f"{pole}_n_splits_evaluable"]) == (3, 0), target
            assert row[f"{pole}_n_splits_missing"] == 3
            assert bool(row[f"{pole}_donor_split_support"]) is False
    assert screen.loc[TARGET_GENES[0]]["effective_donor_n"] == 4


# --------------------------------------------------------------------------- #
# The shared gene universe.
# --------------------------------------------------------------------------- #
def test_the_gene_universe_is_the_pooled_object_and_is_not_shrunk_by_support(run):
    """Only main is projected, so the universe is the POOLED object's own gene axis.

    Intersecting with the by-guide / by-donor gene sets would discard pooled genes to
    match matrices no score is ever taken over — a real change to every primary score,
    bought for nothing. The donor object here deliberately ships a SMALLER gene set
    (it drops one control gene); that gene must still survive.
    """
    result, _ = run
    uni = _json(result, "gene_universe.json")
    prov = _json(result, "provenance.json")

    assert uni["gene_ids"] == UNIVERSE
    assert uni["n_genes"] == len(UNIVERSE)
    assert uni["basis"] == "pooled_main_only"
    assert DONOR_DROPPED_GENE in uni["gene_ids"]      # NOT intersected away
    assert set(COMMON_UNIVERSE) < set(uni["gene_ids"])
    assert uni["sha256"] == result["gene_universe_sha256"]
    assert prov["gene_universe_sha256"] == uni["sha256"]
    assert prov["run_binding"]["gene_universe_sha256"] == uni["sha256"]
    assert result["verification"]["gene_universe"][
        "single_universe_for_every_estimate"] is True

    axis = _json(result, "axis.json")
    assert set(axis["A"]["control"]) <= set(uni["gene_ids"])


# --------------------------------------------------------------------------- #
# Release-artifact invariants.
# --------------------------------------------------------------------------- #
def test_no_pq_no_legacy_schema_no_causal_language_no_local_paths(run):
    result, _ = run
    v = result["verification"]
    assert v["no_pq_columns"] is True
    assert v["no_legacy_columns"] is True, v["forbidden_legacy_columns_present"]
    assert v["no_causal_language"] is True, v["causal_language_hits"]
    assert v["no_machine_local_paths"] is True, v["machine_local_path_hits"]
    assert v["inference_status"] == "not_calibrated"

    screen = _read(result, "screen.parquet")
    for banned in ("balanced_skew", "contrast_id", "combination", "rank",
                   "is_eligible"):
        assert banned not in screen.columns
    assert not [c for c in screen.columns
                if c.lower() in {"p_value", "q_value", "padj", "fdr"}]

    manifest = _json(result, "input_manifest.json")
    for entry in manifest["files"]:
        assert "/" not in entry["name"]
        assert len(entry["sha256"]) == 64


def test_provenance_carries_the_top_level_identifiers_and_the_contract(run):
    result, _ = run
    prov = _json(result, "provenance.json")

    for key in ("run_id", "question_id", "selection_id", "analysis_condition",
                "mask_sha256", "gene_universe_sha256"):
        assert prov[key], f"provenance is missing top-level {key}"
    assert prov["run_id"] == result["run_id"]
    assert prov["mask_sha256"] == result["mask_sha256"]

    contract = prov["stage2_direct_contract"]
    assert contract["run_key"] == "run_id"          # never the biology-only id
    assert contract["screen"]["no_balanced_skew"] is True
    assert contract["screen"]["no_headline_rank"] is True
    assert contract["screen"]["rank_dtype"].startswith("Int64")
    # the estimate key is the WHOLE released identity, not the gene alone: a scope
    # cannot be claimed by accession while its namespace or symbol says otherwise
    assert contract["estimate_key"] == list(domain.SCOPE_KEY_FIELDS)

    binding = prov["run_binding"]
    assert binding["stage1"]["validation_sha256"] is None      # still pending
    assert prov["selection_contract"]["stage1_validation_status"] == \
        "pending_stage1_v3_validation"

    gm = binding["guide_manifest"]
    assert gm["status"] == "bound"
    # The BINDING carries the manifest's SEMANTICS, never its byte formatting: row
    # order and indentation are not science, so the raw file hash must not be able to
    # move run_id. What run_id binds is the canonical hash.
    assert "manifest_sha256" not in gm
    assert len(gm["canonical_sha256"]) == 64
    assert all(len(s["sha256"]) == 64 for s in gm["sources"])

    # ...and the raw bytes are still RETAINED, as audit provenance only.
    audit = prov["guide_contract"]["contributor_manifest"]
    assert len(audit["manifest_sha256"]) == 64
    assert audit["canonical_sha256"] == gm["canonical_sha256"]
    assert prov["guide_contract"]["identity_inference_permitted"] is False


# --------------------------------------------------------------------------- #
# Fail-closed default: no manifest, no identity, NO RESULT AT ALL.
#
# A screen built with no contributor manifest is a complete table of nulls with a
# run_id, a provenance block and a verification record attached. That artifact says
# "we looked and found nothing", when the truth is "we were never shown the
# evidence" — so it is not written. The refusal is the result.
# --------------------------------------------------------------------------- #
def test_without_a_contributor_manifest_the_build_refuses(synthetic_run):
    args = synthetic_run(manifest=False)
    with pytest.raises(gate.GateError) as exc:
        build_screen(args)
    assert "contributor_manifest_resolves" in str(exc.value)


def test_a_refused_run_writes_no_result_artifact(synthetic_run):
    """Zero artifacts — not an empty screen, not a run directory, nothing."""
    args = synthetic_run(manifest=False)
    with pytest.raises(gate.GateError):
        build_screen(args)
    assert not os.path.exists(args.out_root) or os.listdir(args.out_root) == []


def test_the_refusal_is_the_same_gate_a_preflight_would_have_applied(synthetic_run):
    """The build cannot be weaker than --preflight-only over identical inputs."""
    args = synthetic_run(manifest=False)
    report = preflight.run(args)
    assert report["verdict"] == preflight.NO_GO
    assert [f["check"] for f in report["failures"]] == ["contributor_manifest_resolves"]
    assert report["result_artifacts_written"] == 0

    with pytest.raises(gate.GateError) as exc:
        build_screen(args)
    assert exc.value.report["failures"] == report["failures"]


# --------------------------------------------------------------------------- #
# run_id.
# --------------------------------------------------------------------------- #
def test_run_id_is_stable_across_reruns_but_moves_with_the_science(synthetic_run):
    first = build_screen(synthetic_run())
    second = build_screen(synthetic_run())
    assert first["run_id"] == second["run_id"]          # timestamps do not enter it
    assert first["mask_sha256"] == second["mask_sha256"]

    # a scientific input changed: one target lost a contributing guide
    specs = default_specs()
    specs[0].n_guides = 1.0
    specs[0].manifest_main = ["g-T0-1"]
    specs[0].guide_slot_effects = {"guide_1": -1.0}
    specs[0].manifest_slots = {"guide_1": "g-T0-1"}
    changed = build_screen(synthetic_run(specs))
    assert changed["run_id"] != first["run_id"]

    # results are keyed by run_id, never by the biology-only question_id
    assert os.path.basename(first["out_dir"]) == first["run_id"]


def test_a_stale_v2_selection_is_rejected(synthetic_run):
    args = synthetic_run(method_version="stage1-continuous-v2")
    with pytest.raises(SelectionError, match="stale Stage-1 selection"):
        build_screen(args)
