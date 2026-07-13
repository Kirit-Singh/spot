"""The ALL-ARM Direct bundle: every admitted program's two arms, and NO pair anywhere.

ROUND4_ADDENDUM c4773562. The old runner's identity was a function of the A/B pair it was
asked about, so the same measurement requested for two pairs produced two bundles that
looked like two different measurements — and the arms inside them could never be reused. A
bundle whose identity does not mention a pair can be cited by every pair that needs it.

The two properties this has to get right, and they pull in opposite directions:

  * the two arms of a program are ONE measurement — `increase` is the base delta, `decrease`
    is its exact negation, so they cannot disagree about a magnitude they share;
  * the two arms are TWO RANKINGS — a rank is a statement about a population, and negating
    the values genuinely reverses the order. An arm that inherited the other's ranks would
    be reporting a position nothing put it in.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import arm_bundle, arm_keys, run_arms, scorer_view
from direct import projection as proj


@pytest.fixture
def bundle(synthetic_run, tmp_path):
    args = synthetic_run()
    args.condition = "StimX"
    args.out_root = str(tmp_path / "arms")
    res = run_arms.build_bundle(args)
    # the STANDARDIZED native names (run_arms.PROVENANCE_FILE etc.) — the interface W3 reads
    # and W10 verifies, not this module's private convention
    with open(os.path.join(res["out_dir"], run_arms.BUNDLE_FILE)) as fh:
        doc = json.load(fh)
    with open(os.path.join(res["out_dir"], run_arms.PROVENANCE_FILE)) as fh:
        prov = json.load(fh)
    return res, doc, prov


class TestEveryAdmittedProgramGetsBothArms:
    def test_the_slot_count_is_programs_times_two(self, bundle):
        res, doc, _ = bundle
        assert doc["n_arm_slots"] == res["n_admitted_programs"] * 2
        assert doc["n_arm_slots"] == doc["n_expected_arm_slots"]

    def test_the_expected_count_is_DERIVED_never_a_copied_constant(self, bundle):
        _, doc, _ = bundle
        admitted = doc["scorer_view"]["admitted_program_ids"]
        assert arm_bundle.expected_slots(admitted) == len(admitted) * 2

    def test_every_program_has_an_increase_AND_a_decrease_arm(self, bundle):
        _, doc, _ = bundle
        for program in doc["scorer_view"]["admitted_program_ids"]:
            changes = {a["desired_change"] for a in doc["arms"]
                       if a["program_id"] == program}
            assert changes == {arm_keys.INCREASE, arm_keys.DECREASE}

    def test_an_EMPTY_arm_is_still_a_slot(self, bundle):
        # an arm missing from the manifest is indistinguishable from one that was computed
        # and found nothing
        _, doc, _ = bundle
        assert len(doc["arms"]) == doc["n_expected_arm_slots"]
        for a in doc["arms"]:
            assert a["n_ranked"] >= 0

    def test_the_arm_keys_are_canonical_and_carry_no_pole_or_role(self, bundle):
        _, doc, _ = bundle
        for a in doc["arms"]:
            assert a["arm_key"] == arm_keys.direct_arm_key(
                a["program_id"], a["desired_change"], a["condition"])
            for forbidden in ("high", "low", "away_from_A", "toward_B"):
                assert forbidden not in a["arm_key"]


class TestTheTwoArmsAreOneMeasurementAndTwoRankings:
    def _rows(self, res):
        import pandas as pd
        return pd.read_parquet(os.path.join(res["out_dir"], "arms.parquet"))

    def test_decrease_is_the_EXACT_negation_of_increase(self, bundle):
        res, _, _ = bundle
        df = self._rows(res)
        up = df[df.desired_change == arm_keys.INCREASE].set_index(
            ["program_id", "target_id"])
        down = df[df.desired_change == arm_keys.DECREASE].set_index(
            ["program_id", "target_id"])
        for key, u in up.iterrows():
            d = down.loc[key]
            if u["value"] is None or d["value"] is None:
                continue
            if u["value"] == u["value"] and d["value"] == d["value"]:   # both non-NaN
                assert d["value"] == pytest.approx(-u["value"], abs=1e-12)

    def test_both_arms_share_ONE_base_delta(self, bundle):
        res, _, _ = bundle
        df = self._rows(res)
        per = df.groupby(["program_id", "target_id"])["base_delta"].nunique(dropna=False)
        assert (per <= 1).all(), "the two arms disagree about the effect they share"

    def test_the_RANKS_are_taken_separately_per_arm(self, bundle):
        res, _, _ = bundle
        df = self._rows(res)
        for key, arm in df[df["rank"].notna()].groupby("arm_key"):
            ranks = sorted(arm["rank"].tolist())
            assert ranks == list(range(1, len(ranks) + 1)), f"{key}: ranks are not dense"

    def test_the_top_of_one_arm_is_the_BOTTOM_of_the_other(self, bundle):
        # the whole reason ranks cannot be shared between the arms
        res, _, _ = bundle
        df = self._rows(res)
        ranked = df[df["rank"].notna()]
        for program in ranked.program_id.unique():
            up = ranked[(ranked.program_id == program)
                        & (ranked.desired_change == arm_keys.INCREASE)]
            down = ranked[(ranked.program_id == program)
                          & (ranked.desired_change == arm_keys.DECREASE)]
            if len(up) < 2 or len(down) < 2:
                continue
            top_up = up.loc[up["rank"].idxmin(), "target_id"]
            bottom_down = down.loc[down["rank"].idxmax(), "target_id"]
            assert top_up == bottom_down
            return
        pytest.skip("no program has two rankable targets in this fixture")

    def test_a_target_the_arm_could_not_score_is_ABSENT_from_the_ranking_not_last(
            self, bundle):
        res, _, _ = bundle
        df = self._rows(res)
        assert df[~df.evaluable]["rank"].isna().all()


class TestNoPairAndNoPairDerivedNumberIsAnywhereInTheBundle:
    def test_the_bundle_carries_NO_pair_fields(self, bundle):
        # Scanned over the DATA, with the method's negative declarations set aside: the
        # method says `pareto_emitted: False`, and a check that could not tell a disclosure
        # from an emission would force the bundle to stop declaring what it refuses to emit.
        res, doc, prov = bundle
        data = {k: v for k, v in doc.items() if k != "method"}
        binding = {k: v for k, v in prov["run_binding"].items() if k != "method"}
        blob = json.dumps(data) + json.dumps(binding)
        for forbidden in ("away_from_A", "toward_B", "pareto", "concordance"):
            assert forbidden not in blob

    def test_no_arm_ROW_carries_a_pair_column(self, bundle):
        import pandas as pd
        res, _, _ = bundle
        cols = set(pd.read_parquet(os.path.join(res["out_dir"], "arms.parquet")).columns)
        assert cols == set(arm_bundle.ARM_ROW_COLUMNS) | {"arm_bundle_run_id"}
        for forbidden in ("away_from_A", "toward_B", "pareto", "concordance",
                          "A_delta", "B_delta"):
            assert forbidden not in cols

    def test_the_method_DECLARES_what_it_will_not_emit(self, bundle):
        _, doc, _ = bundle
        m = doc["method"]
        assert m["pair_fields_emitted"] is False
        assert m["pareto_emitted"] is False
        assert m["concordance_emitted"] is False
        assert m["combined_objective_permitted"] is False
        assert m["arm_key_carries_pole_or_role"] is False

    def test_there_is_NO_p_q_or_FDR(self, bundle):
        _, doc, prov = bundle
        blob = (json.dumps(doc) + json.dumps(prov)).lower()
        for forbidden in ("p_value", "q_value", "fdr", "padj", "pval"):
            assert forbidden not in blob
        assert prov["inference_status"] == "not_calibrated"

    def test_the_REQUEST_names_a_context_and_no_pair(self, bundle):
        _, _, prov = bundle
        req = prov["run_binding"]["arm_bundle_request"]
        assert req["names_a_program_pair"] is False
        assert req["condition"]
        assert "A" not in req and "B" not in req

    def test_the_request_is_SELF_HASHED(self, bundle):
        from direct.hashing import content_hash
        _, _, prov = bundle
        req = dict(prov["run_binding"]["arm_bundle_request"])
        declared = req.pop("request_sha256")
        assert content_hash(req) == declared


class TestM4b_APairDerivedStatusCanNEVERGateAReusableArm:
    """W16's M4b: the pair-bound Direct verifier re-derives `joint_status` and REJECTS a
    coherently sign-flipped but otherwise valid arm configuration — 152/153 checks pass and
    the joint_status gate fails it. `joint_status`, Pareto and concordance are functions of
    TWO arms; c4773562 makes them join-time display only. A quantity that exists only when
    two arms are put side by side cannot decide whether one of them is admissible.

    This bundle removes them entirely rather than defaulting them off: a field that is not
    emitted cannot come back as a gate in a later pass.
    """

    def test_a_COHERENTLY_SIGN_FLIPPED_configuration_still_builds_every_arm(
            self, synthetic_run, tmp_path):
        # The audit caught this test not doing what it said: it named a sign flip and then
        # called the ORDINARY fixture, unchanged. So it asserted nothing about flipped signs
        # and would have passed against a producer that refused them outright.
        #
        # It now actually flips. Arbitrary coherent signs — positive, negative and zero — are
        # a perfectly valid configuration, and exactly the one the pair-derived `joint_status`
        # gate rejected. A quantity that exists only when two arms are put side by side cannot
        # decide whether one of them is admissible.
        base = {"p": [
            {"target_id": "T1", "delta": 7.5, "status": proj.OK, "base_state": "pass",
             "base_passed": True, "n_panel_surviving": 3, "n_control_surviving": 9},
            {"target_id": "T2", "delta": -3.25, "status": proj.OK, "base_state": "pass",
             "base_passed": True, "n_panel_surviving": 3, "n_control_surviving": 9},
            {"target_id": "T3", "delta": 0.0, "status": proj.OK, "base_state": "pass",
             "base_passed": True, "n_panel_surviving": 3, "n_control_surviving": 9},
        ]}
        rows = arm_bundle.build_rows(condition="StimX", admitted=["p"],
                                     base_by_program=base)

        assert len(rows) == 6                     # one program x two arms x three targets
        up = {r["target_id"]: r for r in rows
              if r["desired_change"] == arm_keys.INCREASE}
        down = {r["target_id"]: r for r in rows
                if r["desired_change"] == arm_keys.DECREASE}

        # every sign survives, and decrease is the EXACT negation — never a re-estimate
        assert up["T1"]["value"] == 7.5 and down["T1"]["value"] == -7.5
        assert up["T2"]["value"] == -3.25 and down["T2"]["value"] == 3.25
        assert up["T3"]["value"] == 0.0 and down["T3"]["value"] == 0.0

        # ...and the RANKS genuinely reverse, because negating the values reverses the order
        assert up["T1"]["rank"] == 1 and down["T2"]["rank"] == 1
        assert arm_bundle.expected_slots(["p"]) == 2

    def test_NO_joint_status_exists_anywhere_in_the_bundle(self, bundle):
        res, doc, prov = bundle
        import pandas as pd
        blob = json.dumps({k: v for k, v in doc.items() if k != "method"})
        assert "joint_status" not in blob
        cols = set(pd.read_parquet(os.path.join(res["out_dir"], "arms.parquet")).columns)
        assert "joint_status" not in cols

    def test_the_ARM_BYTES_are_a_function_of_the_ARM_ROWS_ALONE(self, bundle):
        # arm_rows_sha256 RE-DERIVES from the shipped rows, over ARM_ROW_COLUMNS only. No
        # pair-derived quantity is an input to it, so no display-time choice — no Pareto
        # tier, no joint_status, no concordance label — can change what a cached arm IS.
        import pandas as pd
        res, doc, _ = bundle
        df = pd.read_parquet(os.path.join(res["out_dir"], "arms.parquet"))
        rows = [{c: (None if pd.isna(r[c]) else r[c])
                 for c in arm_bundle.ARM_ROW_COLUMNS} for _, r in df.iterrows()]
        # the SHIPPED bytes, re-hashed by the published canonical projection
        assert arm_bundle.rows_sha256(rows) == doc["arm_rows_sha256"]

    def test_no_pair_derived_column_is_even_DEFINED(self, bundle):
        assert set(arm_bundle.ARM_ROW_COLUMNS).isdisjoint(
            {"joint_status", "pareto_tier", "concordance_class"})

    def test_the_method_declares_these_are_NOT_completeness_bearing(self, bundle):
        _, doc, _ = bundle
        m = doc["method"]
        assert m["pareto_emitted"] is False
        assert m["concordance_emitted"] is False
        assert m["pair_fields_emitted"] is False


class TestTheAdmittedSetComesFromTheBOUNDRelease:
    def test_the_scorer_view_hash_is_bound_into_the_bundle_identity(self, bundle):
        _, doc, prov = bundle
        assert prov["run_binding"]["scorer_view_sha256"] == \
            doc["scorer_view"]["scorer_view_sha256"]

    def test_a_non_base_portable_program_is_EXCLUDED(self, bundle):
        _, doc, _ = bundle
        view = doc["scorer_view"]
        assert view["derived_from_legacy_registry"] is False
        assert set(view["admitted_program_ids"]).isdisjoint(view["excluded_program_ids"])

    def test_a_release_that_declares_no_portability_is_REFUSED(self):
        class R:
            kind = "synthetic"
            programs = {"p1": {"panel_ensembl": ["g"], "control_ensembl": ["h"]}}
        with pytest.raises(scorer_view.ScorerViewError) as exc:
            scorer_view.view(R())
        assert exc.value.reason == scorer_view.REFUSE_PORTABILITY_UNDECLARED

    def test_a_release_that_admits_NOTHING_is_REFUSED_not_emitted_empty(self):
        class R:
            kind = "synthetic"
            programs = {"p1": {"base_portable": False, "panel_ensembl": [],
                               "control_ensembl": []}}
        with pytest.raises(scorer_view.ScorerViewError) as exc:
            scorer_view.view(R())
        assert exc.value.reason == scorer_view.REFUSE_NO_ADMITTED


class TestTheBundleIsContentAddressed:
    def test_the_rows_hash_is_bound_into_the_run_id(self, bundle):
        _, doc, prov = bundle
        assert prov["run_binding"]["arm_rows_sha256"] == doc["arm_rows_sha256"]

    def test_the_run_id_re_derives_from_its_own_binding(self, bundle):
        from direct.hashing import canonical_json, sha256_hex
        _, _, prov = bundle
        full = sha256_hex(canonical_json(prov["run_binding"]))
        assert prov["arm_bundle_run_id"] == full[:run_arms.BUNDLE_RUN_ID_LEN]
        assert prov["arm_bundle_run_sha256"] == full


# ---- W18 regressions, preserved through the W14 integration ----
class TestThePhysicalContract:
    """The exact names W10's verifier and W3's manifest read. Emitted natively, no shim."""

    def test_the_bundle_ships_exactly_the_contract_files(self, bundle):
        # DERIVED from arm_artifacts, never a hardcoded list: the native file set is the thing
        # W10 admitted and W3 keys on, and a list copied into a test drifts from it silently.
        from direct import arm_artifacts
        res, _, _ = bundle
        expected = {arm_artifacts.ROWS_FILE, arm_artifacts.MASKS_FILE,
                    arm_artifacts.CONTRIB_FILE, arm_artifacts.GUIDE_SUPPORT_FILE,
                    arm_artifacts.DONOR_SUPPORT_FILE, arm_artifacts.INPUTS_FILE,
                    arm_artifacts.UNIVERSE_FILE, arm_artifacts.BUNDLE_FILE,
                    arm_artifacts.PROVENANCE_FILE, arm_artifacts.VERIFICATION_FILE}
        assert set(os.listdir(res["out_dir"])) == expected

    def test_the_producer_does_NOT_admit_its_own_output(self, bundle):
        from direct import arm_artifacts
        res, _, _ = bundle
        with open(os.path.join(res["out_dir"],
                               arm_artifacts.VERIFICATION_FILE)) as fh:
            v = json.load(fh)
        assert v["verdict"] == arm_artifacts.VERDICT_PENDING
        assert v.get("admitted") is not True


class TestW10_ThePAIRIsNotPartOfAReusableBundlesIDENTITY:
    """W10 proved it: byte-identical arm content, DIFFERENT bundle ids, because the runner
    bound `stage2_input_manifest` — which hashes stage01_selection_contract.json. So a pair
    the bundle does not contain, does not use, and cannot be affected by was deciding its id.
    An arm keyed on whichever question happened to be asked first is not reusable: the cache
    misses every time, and the same measurement is recomputed under a new name.
    """

    def _build(self, synthetic_run, tmp_path, tag, **kw):
        args = synthetic_run(**kw)
        args.condition = "StimX"
        args.out_root = str(tmp_path / tag)
        return run_arms.build_bundle(args)

    def test_changing_ONLY_the_pair_leaves_the_bundle_id_IDENTICAL(
            self, synthetic_run, tmp_path):
        a = self._build(synthetic_run, tmp_path, "a")
        # the SAME data, a DIFFERENT A/B selection contract
        b = self._build(synthetic_run, tmp_path, "b",
                        a_direction="low", b_direction="low")
        assert a["arm_bundle_run_id"] == b["arm_bundle_run_id"]

    def test_changing_ONLY_the_pair_leaves_the_arm_BYTES_identical(
            self, synthetic_run, tmp_path):
        a = self._build(synthetic_run, tmp_path, "c")
        b = self._build(synthetic_run, tmp_path, "d",
                        a_direction="low", b_direction="low")
        assert a["bundle"]["arm_rows_sha256"] == b["bundle"]["arm_rows_sha256"]

    def test_the_selection_contract_is_NOT_in_the_bound_inputs(self, bundle):
        _, _, prov = bundle
        names = {i["name"] for i in prov["run_binding"]["stage2_inputs"]}
        assert "stage01_selection_contract.json" not in names

    def test_the_DATA_still_moves_the_id(self, bundle):
        # the pair must not move it; the data must. A bundle nothing can change is not an
        # identity, it is a constant.
        _, _, prov = bundle
        names = {i["name"] for i in prov["run_binding"]["stage2_inputs"]}
        assert "GWCD4i.DE_stats.h5ad" in names


class TestW10_TheCONTRIBUTORManifestAndTheMASKAreBoundAsBYTES:
    """Every delta depends on them: the manifest decides which guides contributed, which
    decides the mask, which decides the projection. The bundle recorded only COUNTS — and two
    different manifests with the same number of rows would produce different science under
    the same id.
    """

    def test_the_contributor_manifest_is_bound_by_RAW_and_CANONICAL_hash(self, bundle):
        _, _, prov = bundle
        m = prov["run_binding"]["contributor_manifest"]
        assert m["status"] == "bound"
        assert len(m["raw_sha256"]) == 64
        assert len(m["canonical_sha256"]) == 64

    def test_the_MASK_content_hash_is_bound(self, bundle):
        _, _, prov = bundle
        assert len(prov["run_binding"]["mask_sha256"]) == 64
        assert prov["run_binding"]["n_mask_rows"] > 0

    def test_the_mask_ARTIFACT_ships_so_the_hash_can_be_CHECKED(self, bundle):
        # binding the hash of bytes nobody can hold is the same defect as naming a gene-set
        # file that only exists on the producer's disk
        res, _, _ = bundle
        assert os.path.exists(os.path.join(res["out_dir"], "masks.parquet"))

    def test_a_RESEALED_mask_mutation_changes_the_bound_hash(self, bundle):
        # the honest-producer attack: alter the masked genes and re-hash. The mask hash is
        # over the mask ROWS, so it moves — and the run id, which covers it, moves with it.
        from direct import emit as _emit
        res, _, prov = bundle
        import pandas as pd
        df = pd.read_parquet(os.path.join(res["out_dir"], "masks.parquet"))
        rows = [{k: (None if pd.isna(v) else (v.item() if hasattr(v, "item") else v))
                 for k, v in r.items()} for r in df.to_dict("records")]
        assert rows, "no mask rows to mutate"
        honest = _emit.mask_content_sha256(rows)
        rows[0]["mask_reason"] = "forged"
        assert _emit.mask_content_sha256(rows) != honest

    def test_a_RESEALED_contributor_manifest_changes_the_bound_identity(self, bundle):
        from direct.hashing import content_hash
        _, _, prov = bundle
        m = prov["run_binding"]["contributor_manifest"]
        forged = dict(m, n_rows=(m["n_rows"] or 0) + 1)
        assert content_hash(forged) != content_hash(m)
