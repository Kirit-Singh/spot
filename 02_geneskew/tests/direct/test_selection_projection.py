"""ONE SELECTION, projected onto the ADMITTED stores. Generic over every axis.

Nothing here is about Treg or Th1. A pole is a (program_id, direction, condition) tuple and no
tuple is special — the tests parametrise over programs, directions, conditions and both
analysis modes, and the REAL 539431d selections are replayed as-is.

Store bytes are fixtures. What is real is the refusal.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
from direct import selection_projection as P
from direct import stage1_v3 as S1
from direct.hashing import content_hash

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "analysis", "direct"))
import verify_selection_projection as V  # noqa: E402
from test_stage1_v3 import SCHEMA_PATH, emit, reseal  # noqa: E402

pytestmark = pytest.mark.skipif(not SCHEMA_PATH, reason="the pinned v3 schema is absent")

SPOT = "/home/tcelab/projects/spot"
PIN = "539431d"
SELDIR = "01_programs/analysis/stage2_bridge/release/selections/"


# --------------------------------------------------------------------------- #
# THE STORES. Immutable fixtures; the receipts they carry are the real shapes.
# --------------------------------------------------------------------------- #
def _direct_store(root, condition, arms, n=150):
    import pandas as pd

    d = os.path.join(root, "direct", condition)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
        json.dump({"schema_version": "spot.stage02_direct_arm_bundle.v1",
                   "arm_bundle_run_id": f"D-{condition}", "condition": condition}, fh)
    rows = []
    for key in arms:
        for i in range(n):
            rows.append({"arm_key": key, "target_id": f"ENSG{i:011d}",
                         "value": 1.0 - i / 1000.0, "rank": i + 1, "evaluable": True,
                         "projection_status": "ok"})
        rows.append({"arm_key": key, "target_id": "UNRANKABLE", "value": None,
                     "rank": None, "evaluable": False,
                     "projection_status": "insufficient_axis_coverage"})
    pd.DataFrame(rows).to_parquet(os.path.join(d, "arms.parquet"))
    with open(os.path.join(root, f"direct_admission_{condition}.json"), "w") as fh:
        json.dump({"binding_schema": "spot.stage02.direct_admission_binding.v1",
                   "native_verdict": "ADMIT", "disposition": "admitted",
                   "condition": condition, "bundle_id": f"D-{condition}"}, fh)
    return d


def _temporal_store(root, frm, to, arms, n=120):
    d = os.path.join(root, "temporal", f"{frm}__{to}")
    os.makedirs(os.path.join(d, "rankings"), exist_ok=True)
    with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
        json.dump({"schema_version": "spot.stage02_temporal_arm_bundle.v1",
                   "bundle_id": f"T-{frm}-{to}", "lane": "temporal",
                   "context": {"from_condition": frm, "to_condition": to}}, fh)
    for j, key in enumerate(arms):
        with open(os.path.join(d, "rankings", f"arm_{j}.json"), "w") as fh:
            json.dump({"arm_key": key,
                       "records": [{"target_id": f"ENSG{i:011d}", "arm_value": 1.0 - i / 500.0,
                                    "rank": i + 1, "evaluable": True} for i in range(n)]}, fh)
    with open(os.path.join(root, "temporal_arm_external_admission.json"), "w") as fh:
        json.dump({"verdict": "ADMIT", "report_id": "t" * 64}, fh)
    return d


def _release(tmp_path, sel_doc, bound):
    """A release that actually contains the arms this selection resolves to."""
    root = str(tmp_path)
    keys = [bound["arms"][r] for r in ("away_from_A", "toward_B")]
    if bound["analysis_mode"] == S1.MODE_TEMPORAL:
        frm, to = bound["conditions"][0], bound["conditions"][-1]
        _temporal_store(root, frm, to, [a["temporal_arm_key"] for a in keys])
        # Direct is present too — the point is that temporal must NOT be answered from it
        for c in (frm, to):
            _direct_store(root, c, [a["direct_arm_key"] for a in keys])
    else:
        _direct_store(root, bound["conditions"][0], [a["direct_arm_key"] for a in keys])
    sp = os.path.join(root, "selection.json")
    with open(sp, "w") as fh:
        json.dump(sel_doc, fh)
    return root, sp


def _project(tmp_path, doc, mode=P.MODE_PRODUCTION):
    bound = S1.validate(doc, S1.load_schema(SCHEMA_PATH))
    root, sp = _release(tmp_path, doc, bound)
    art = P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root, mode=mode,
                    producer_commit="TEST")
    ap = os.path.join(root, P.ARTIFACT)
    with open(ap, "w") as fh:
        json.dump(art, fh, indent=2, sort_keys=True)
    return art, ap, sp, root


# --------------------------------------------------------------------------- #
# GENERIC OVER EVERY AXIS. No program is special.
# --------------------------------------------------------------------------- #
TUPLES = [
    ("prog_alpha", "high", "prog_beta", "low", S1.MODE_WITHIN, ["Rest"]),
    ("prog_beta", "low", "prog_alpha", "high", S1.MODE_WITHIN, ["Stim48hr"]),
    ("prog_alpha", "low", "prog_beta", "high", S1.MODE_TEMPORAL, ["Rest", "Stim8hr"]),
    ("prog_beta", "high", "prog_alpha", "low", S1.MODE_TEMPORAL, ["Stim48hr", "Rest"]),
    # SAME PROGRAM, SAME DIRECTION, DIFFERENT TIMES — a valid Stage-1 output.
    ("prog_alpha", "high", "prog_alpha", "high", S1.MODE_TEMPORAL, ["Rest", "Stim48hr"]),
]


@pytest.mark.parametrize("a,da,b,db,mode,conds", TUPLES)
class TestEveryValidTupleProjects:
    def test_it_projects_and_binds_BOTH_ids(self, tmp_path, a, da, b, db, mode, conds):
        doc = emit(a=a, dir_a=da, b=b, dir_b=db, mode=mode, conditions=conds)
        art, _, _, _ = _project(tmp_path, doc)

        assert art["question_id"] == doc["question_id"]
        assert art["selection_id"] == doc["selection_id"]
        assert art["question_id"] != art["selection_id"]
        assert art["analysis_mode"] == mode

    def test_the_two_arms_stay_SEPARATE_with_their_OWN_ranks(self, tmp_path, a, da, b, db,
                                                             mode, conds):
        doc = emit(a=a, dir_a=da, b=b, dir_b=db, mode=mode, conditions=conds)
        art, _, _, _ = _project(tmp_path, doc)

        away, toward = art["arms"]["away_from_A"], art["arms"]["toward_B"]
        assert away["arm_key"] != toward["arm_key"]
        assert away["rows"] and toward["rows"]
        # each arm carries its OWN rank column; nothing joins them
        assert all("rank" in r and "value" in r for r in away["rows"])
        assert art["combined_objective"] is None
        assert art["joint_rank_emitted"] is False

    def test_the_STORE_that_answered_OWNS_the_mode(self, tmp_path, a, da, b, db, mode, conds):
        doc = emit(a=a, dir_a=da, b=b, dir_b=db, mode=mode, conditions=conds)
        art, ap, sp, root = _project(tmp_path, doc)

        want = "temporal" if mode == S1.MODE_TEMPORAL else "direct"
        assert art["store_lane"] == want
        for arm in art["arms"].values():
            assert arm["lane"] == want
            assert arm["arm_key"].startswith(want + "|")
        assert V.verify(ap, selection_path=sp, bundles_root=root)["verdict"] == "admit"


class TestTheREAL539431dSelections:
    def _real(self, name):
        if not os.path.isdir(os.path.join(SPOT, ".git")):
            pytest.skip("the Stage-1 release tree is not on this host")
        r = subprocess.run(["git", "-C", SPOT, "show", f"{PIN}:{SELDIR}{name}"],
                           capture_output=True)
        if r.returncode != 0:
            pytest.skip(f"{name} is not in this object store")
        return json.loads(r.stdout)

    @pytest.mark.parametrize("name", [
        "stage01_selection_within_Rest.v3.json",
        "stage01_selection_within_Stim48hr.v3.json",
        "stage01_selection_temporal_Rest_Stim48hr.v3.json",
        "stage01_selection_temporal_Stim8hr_Rest.v3.json",
    ])
    def test_a_REAL_selection_projects_onto_the_admitted_stores(self, tmp_path, name):
        doc = self._real(name)
        art, ap, sp, root = _project(tmp_path, doc)

        assert art["question_id"] == doc["question_id"]
        assert art["arms_are_derived_not_declared"] is True
        report = V.verify(ap, selection_path=sp, bundles_root=root)
        assert report["verdict"] == "admit", report["failures"]


class TestTheEstimatorIsNEVERBorrowed:
    def test_a_TEMPORAL_question_is_NOT_answered_from_the_DIRECT_store(self, tmp_path):
        """The Direct store is RIGHT THERE and it has arms with the right programs. It answers
        a different question: 'how does this arm rank targets AT one time'. A temporal arm is a
        DIFFERENCE BETWEEN TWO TIMES. Borrowing one for the other returns numbers about a
        question nobody asked."""
        doc = emit(mode=S1.MODE_TEMPORAL, conditions=["Rest", "Stim48hr"])
        bound = S1.validate(doc, S1.load_schema(SCHEMA_PATH))
        root = str(tmp_path)
        # a full Direct store for BOTH conditions... and NO temporal store at all
        for c in ("Rest", "Stim48hr"):
            _direct_store(root, c, [bound["arms"][r]["direct_arm_key"]
                                    for r in ("away_from_A", "toward_B")])
        sp = os.path.join(root, "selection.json")
        with open(sp, "w") as fh:
            json.dump(doc, fh)

        with pytest.raises(P.SelectionProjectionError) as exc:
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root)
        assert exc.value.gate == P.G_ESTIMATOR_BORROWED


class TestTheFailClosedGates:
    def test_a_MISSING_condition_bundle_is_REFUSED(self, tmp_path):
        doc = emit(conditions=["Rest"])
        bound = S1.validate(doc, S1.load_schema(SCHEMA_PATH))
        root = str(tmp_path)
        _direct_store(root, "Stim8hr", [bound["arms"]["away_from_A"]["direct_arm_key"]])
        sp = os.path.join(root, "selection.json")
        with open(sp, "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(P.SelectionProjectionError) as exc:
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root)
        assert exc.value.gate == P.G_LANE_MISMATCH

    def test_an_UNADMITTED_store_is_REFUSED_in_PRODUCTION(self, tmp_path):
        doc = emit()
        art, _, sp, root = _project(tmp_path, doc)
        os.remove(os.path.join(root, "direct_admission_Rest.json"))
        with pytest.raises(P.SelectionProjectionError) as exc:
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root,
                      mode=P.MODE_PRODUCTION)
        assert exc.value.gate == P.G_LANE_UNADMITTED

    def test_FIXTURE_mode_DECLARES_the_missing_receipt_and_never_claims_admission(
            self, tmp_path):
        doc = emit()
        _, _, sp, root = _project(tmp_path, doc)
        os.remove(os.path.join(root, "direct_admission_Rest.json"))
        art = P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root,
                        mode=P.MODE_FIXTURE)
        adm = art["bindings"]["admissions"]["direct"]
        assert adm["admitted"] is False
        assert adm["not_admitted_because"]
        assert art["mode"] == P.MODE_FIXTURE

    def test_a_REFUSED_store_may_not_ANSWER(self, tmp_path):
        doc = emit()
        _, _, sp, root = _project(tmp_path, doc)
        with open(os.path.join(root, "direct_admission_Rest.json"), "w") as fh:
            json.dump({"native_verdict": "REFUSE", "disposition": "refused"}, fh)
        with pytest.raises(P.SelectionProjectionError) as exc:
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root)
        assert exc.value.gate == P.G_LANE_UNADMITTED

    def test_an_arm_the_STORE_DOES_NOT_HAVE_is_REFUSED(self, tmp_path):
        doc = emit()
        bound = S1.validate(doc, S1.load_schema(SCHEMA_PATH))
        root = str(tmp_path)
        # a Direct bundle for the right condition — carrying only ONE of the two arms
        _direct_store(root, "Rest", [bound["arms"]["away_from_A"]["direct_arm_key"]])
        sp = os.path.join(root, "selection.json")
        with open(sp, "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(P.SelectionProjectionError) as exc:
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root)
        assert exc.value.gate == P.G_ARM_NOT_IN_STORE

    def test_a_FORGED_arm_key_in_the_SELECTION_is_REFUSED_upstream(self, tmp_path):
        """The projection never reads doc["arms"] — and the gate refuses the contract anyway."""
        doc = emit()
        doc["arms"]["away_from_A"]["direct_arm_key"] = "direct|FORGED|increase|Rest"
        reseal(doc)
        root = str(tmp_path)
        sp = os.path.join(root, "selection.json")
        os.makedirs(root, exist_ok=True)
        with open(sp, "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(S1.SelectionV3Error) as exc:
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root)
        assert exc.value.reason == S1.REFUSE_ARM_KEY


class TestTheINDEPENDENTVerifier:
    def _forge(self, tmp_path, mutate, mode=S1.MODE_WITHIN, conds=None):
        doc = emit(mode=mode, conditions=conds or ["Rest"])
        art, ap, sp, root = _project(tmp_path, doc)
        mutate(art)
        art.pop("projection_sha256")
        art["projection_sha256"] = content_hash(art)
        with open(ap, "w") as fh:
            json.dump(art, fh, indent=2, sort_keys=True)
        return V.verify(ap, selection_path=sp, bundles_root=root)

    def test_an_HONEST_projection_is_ADMITTED(self, tmp_path):
        doc = emit()
        _, ap, sp, root = _project(tmp_path, doc)
        rep = V.verify(ap, selection_path=sp, bundles_root=root)
        assert rep["verdict"] == "admit", rep["failures"]

    def test_a_WRONG_selection_id_is_REFUSED(self, tmp_path):
        rep = self._forge(tmp_path, lambda a: a.update({"selection_id": "0" * 16}))
        assert rep["verdict"] == "reject"
        assert any(V.G_IDS in f for f in rep["failures"])

    def test_a_WRONG_question_id_is_REFUSED(self, tmp_path):
        rep = self._forge(tmp_path, lambda a: a.update({"question_id": "0" * 16}))
        assert rep["verdict"] == "reject"
        assert any(V.G_IDS in f for f in rep["failures"])

    def test_a_SWAPPED_arm_key_is_REFUSED(self, tmp_path):
        rep = self._forge(
            tmp_path,
            lambda a: a["arms"]["away_from_A"].update({"arm_key": "direct|x|increase|Rest"}))
        assert rep["verdict"] == "reject"
        assert any(V.G_ARM_KEY in f for f in rep["failures"])

    def test_an_A_B_REVERSAL_is_REFUSED(self, tmp_path):
        """Swapping the arms swaps which program is being moved AWAY FROM and which TOWARD.
        Same two keys, opposite science."""
        def mutate(a):
            a["arms"]["away_from_A"], a["arms"]["toward_B"] = \
                a["arms"]["toward_B"], a["arms"]["away_from_A"]
        rep = self._forge(tmp_path, mutate)
        assert rep["verdict"] == "reject"
        assert any(V.G_ARM_KEY in f for f in rep["failures"])

    def test_a_TAMPERED_row_value_is_REFUSED(self, tmp_path):
        rep = self._forge(
            tmp_path, lambda a: a["arms"]["away_from_A"]["rows"][0].update({"value": 9.9}))
        assert rep["verdict"] == "reject"
        assert any(V.G_ROW_IS_NATIVE in f for f in rep["failures"])

    def test_a_COUNT_that_hides_the_prefix_is_REFUSED(self, tmp_path):
        rep = self._forge(tmp_path,
                          lambda a: a["arms"]["away_from_A"].update({"n_ranked": 100}))
        assert rep["verdict"] == "reject"
        assert any(V.G_COUNTS in f for f in rep["failures"])

    def test_an_UNKNOWN_COLUMN_on_a_served_row_is_REFUSED(self, tmp_path):
        rep = self._forge(
            tmp_path,
            lambda a: a["arms"]["away_from_A"]["rows"][0].update({"mystery_score": 1.0}))
        assert rep["verdict"] == "reject"
        assert any(V.G_UNKNOWN_COLUMN in f for f in rep["failures"])

    @pytest.mark.parametrize("key", ["p_value", "q_value", "fdr", "combined_score",
                                     "balanced_score", "overall_rank", "joint_rank"])
    def test_a_FORBIDDEN_key_ANYWHERE_is_REFUSED(self, tmp_path, key):
        rep = self._forge(
            tmp_path, lambda a, k=key: a["arms"]["away_from_A"]["rows"][0].update({k: 0.01}))
        assert rep["verdict"] == "reject"
        assert any(V.G_FORBIDDEN in f or V.G_UNKNOWN_COLUMN in f for f in rep["failures"])

    def test_the_PRODUCER_ITSELF_refuses_to_emit_a_forbidden_key(self, tmp_path):
        art = {"arms": {"a": {"rows": [{"target_id": "x", "combined_score": 1.0}]}}}
        with pytest.raises(P.SelectionProjectionError) as exc:
            P._forbid(art)
        assert exc.value.gate == P.G_FORBIDDEN

    def test_a_TEMPORAL_artifact_claiming_the_DIRECT_store_is_REFUSED(self, tmp_path):
        rep = self._forge(tmp_path, lambda a: a.update({"store_lane": "direct"}),
                          mode=S1.MODE_TEMPORAL, conds=["Rest", "Stim48hr"])
        assert rep["verdict"] == "reject"
        assert any(V.G_STORE in f for f in rep["failures"])


class TestUIOrderingIsDISPLAYOnly:
    def test_NO_ordering_field_is_IN_the_artifact(self, tmp_path):
        doc = emit()
        art, _, _, _ = _project(tmp_path, doc)
        assert art["ui_ordering_is_display_only_and_not_in_this_artifact"] is True
        blob = json.dumps(art).lower()
        for banned in ("overall_rank", "joint_rank", "combined_score", "display_order"):
            assert f'"{banned}"' not in blob

    def test_the_ordering_is_computed_at_RENDER_time_over_the_two_rank_columns(self, tmp_path):
        doc = emit()
        art, _, _, _ = _project(tmp_path, doc)
        order = P.display_order(art, by="away_from_A")
        assert order[:3] == [r["target_id"] for r in art["arms"]["away_from_A"]["rows"][:3]]
        # ...and asking for the OTHER arm gives the OTHER arm's order. There is no one list.
        assert P.display_order(art, by="toward_B")


class TestTheRECEIPTBindsWhatItWasBuiltFrom:
    def test_it_binds_the_selection_the_stores_and_the_admissions(self, tmp_path):
        doc = emit()
        art, _, _, _ = _project(tmp_path, doc)
        rec = P.receipt(art)
        b = rec["bindings"]

        assert b["selection"]["raw_sha256"] and b["schema"]["raw_sha256"]
        assert b["producer_commit"] == "TEST"
        assert b["admissions"]["direct"]["admitted"] is True
        assert b["admissions"]["direct"]["report_sha256"]
        # the producer admits NOTHING of its own
        assert rec["verdict"] == "pending_independent_verification"
        assert rec["admitted"] is False and rec["self_admitted"] is False
