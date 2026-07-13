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
from direct import lane_admission as LA
from direct import selection_projection as P
from direct import stage1_v3 as S1
from direct.hashing import content_hash, file_sha256

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
# A GATE INVENTORY the shape of W10's real one: 107 named gates, including the load-bearing
# ones an admission cannot be without.
GATES = ([f"gate {i}: an independently re-derived invariant" for i in range(104)] +
         ["every artifact's shipped hash matches the BYTES ON DISK — no file moved",
          "every arm's own bytes and counts RE-DERIVE from the shipped parquet rows",
          "every arm key re-derives from (program, desired_change, condition)"])

STAGE1 = {"stage1_scorer_view_canonical_sha256": "5d1d8c36" + "0" * 56,
          "registry_scorer_projection_sha256": "008c1da1" + "0" * 56}


def w10_report(root, condition, bundle_dir, *, gates=None, bound_over=None):
    """W10's FULL report — the real shape, bound to the bundle bytes ON DISK."""
    with open(os.path.join(bundle_dir, "arm_bundle.json")) as fh:
        doc = json.load(fh)
    files = {n: file_sha256(os.path.join(bundle_dir, n))
             for n in sorted(os.listdir(bundle_dir))
             if os.path.isfile(os.path.join(bundle_dir, n))}
    inv = GATES if gates is None else gates
    bound = {
        "arm_bundle_run_id": doc["arm_bundle_run_id"],
        "arm_rows_sha256": doc["arm_rows_sha256"],
        "condition": condition, "lane": "production",
        "solver_lock_sha256": LA.SOLVER_LOCK_SHA256,
        "artifact_sha256": files,
        "recompute_mode": "all",
        "arm_inventory": sorted(({"arm_key": a["arm_key"]} for a in doc["arms"]),
                                key=lambda a: a["arm_key"]),
        **STAGE1,
    }
    bound.update(bound_over or {})
    body = {
        "schema_version": LA.W10_REPORT_SCHEMA,
        "verifier_id": LA.W10_VERIFIER_ID,
        "verifier_code_sha256": LA.W10_VERIFIER_CODE,
        "independent_of_generator": True,
        "gate_inventory": inv,
        "gate_inventory_sha256": content_hash(inv),
        "bound_artifact": bound,
        "n_gates": len(inv), "n_passed": len(inv), "n_failed": 0, "failed_gates": [],
        "verdict": "ADMIT",
    }
    doc_out = dict(body, report_sha256=content_hash(body))
    p = os.path.join(root, LA.W10_REPORT_FILE.format(condition=condition))
    with open(p, "w") as fh:
        json.dump(doc_out, fh, indent=2, sort_keys=True)
    return p


def _direct_store(root, condition, arms, n=150, admit=True):
    import pandas as pd

    d = os.path.join(root, "direct", condition)
    os.makedirs(d, exist_ok=True)
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
    with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
        json.dump({"schema_version": "spot.stage02_direct_arm_bundle.v1",
                   "arm_bundle_run_id": f"D-{condition}", "condition": condition,
                   "arm_rows_sha256": content_hash(rows),
                   "arms": [{"arm_key": k} for k in arms]}, fh, indent=2, sort_keys=True)
    if admit:
        w10_report(root, condition, d)
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
    # THE INVENTORY the independent verifier cleared...
    inv = {"schema_version": "spot.stage02_temporal_arm_release.v1", "lane": "temporal",
           "n_bundles": 1, "bundles": [{"bundle_id": f"T-{frm}-{to}"}]}
    ip = os.path.join(root, "temporal_arm_release.json")
    with open(ip, "w") as fh:
        json.dump(inv, fh, indent=2, sort_keys=True)

    # ...and W11's external admission, BOUND to it by hash. Not a verdict stub.
    body = {"schema_version": "spot.stage02_temporal_arm_external_admission.v1",
            "verifier_id": "spot.stage02.temporal.arm.independent_verifier.v1",
            "verdict": "ADMIT",
            "binds": {"inventory_raw_sha256": file_sha256(ip),
                      "stage1_release_sha256": ""}}
    with open(os.path.join(root, "temporal_arm_external_admission.json"), "w") as fh:
        json.dump(dict(body, report_id=content_hash(body)), fh, indent=2, sort_keys=True)
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
                    producer_commit="TEST", stage1=STAGE1)
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
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root,
                      stage1=STAGE1)
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
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root,
                      stage1=STAGE1)
        assert exc.value.gate == P.G_LANE_MISMATCH

    def test_an_UNADMITTED_store_is_REFUSED_in_PRODUCTION(self, tmp_path):
        doc = emit()
        art, _, sp, root = _project(tmp_path, doc)
        os.remove(os.path.join(root, LA.W10_REPORT_FILE.format(condition="Rest")))
        with pytest.raises(P.SelectionProjectionError) as exc:
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root,
                      mode=P.MODE_PRODUCTION, stage1=STAGE1)
        assert exc.value.gate == P.G_LANE_UNADMITTED

    def test_FIXTURE_mode_DECLARES_the_missing_receipt_and_never_claims_admission(
            self, tmp_path):
        doc = emit()
        _, _, sp, root = _project(tmp_path, doc)
        os.remove(os.path.join(root, LA.W10_REPORT_FILE.format(condition="Rest")))
        art = P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root,
                        mode=P.MODE_FIXTURE, stage1=STAGE1)
        adm = art["bindings"]["admissions"]["direct"]
        assert adm["admitted"] is False
        assert adm["not_admitted_because"]
        assert art["mode"] == P.MODE_FIXTURE

    def test_a_REFUSED_store_may_not_ANSWER(self, tmp_path):
        doc = emit()
        _, _, sp, root = _project(tmp_path, doc)
        d = os.path.join(root, "direct", "Rest")
        rp = w10_report(root, "Rest", d)
        rep = json.load(open(rp))
        rep["verdict"] = "REFUSE"
        rep["n_failed"] = 1
        rep["failed_gates"] = ["something re-derived wrong"]
        rep["report_sha256"] = content_hash(
            {k: v for k, v in rep.items() if k != "report_sha256"})
        with open(rp, "w") as fh:
            json.dump(rep, fh)
        with pytest.raises(P.SelectionProjectionError) as exc:
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root,
                      stage1=STAGE1)
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
        # The ADMISSION refuses first, and more strongly: W10's report never verified that
        # arm, so there is no independent verification of it to lean on at all.
        with pytest.raises(P.SelectionProjectionError) as exc:
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root,
                      stage1=STAGE1)
        assert exc.value.gate in (P.G_ARM_NOT_IN_STORE, P.G_LANE_UNADMITTED)
        assert LA.G_ARM_NOT_VERIFIED in str(exc.value) or "no arm" in str(exc.value)

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
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root,
                      stage1=STAGE1)
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


# --------------------------------------------------------------------------- #
# THE FORGED-ADMISSION ATTACKS. Production mode used to be SELF-ATTESTED:
#
#     echo '{"verdict":"ADMIT"}' > direct_admission_Rest.json
#
# ...beside an unadmitted store, and BOTH the producer and the verifier accepted it. The old
# check stored only the file's raw hash and later confirmed the same file still hashed to it —
# which proves the forgery was not edited, and nothing else. An admission that only has to SAY
# "admit" is not an admission; it is a filename.
# --------------------------------------------------------------------------- #
class TestAForgedAdmissionCannotAdmit:
    def _root(self, tmp_path):
        doc = emit()
        bound = S1.validate(doc, S1.load_schema(SCHEMA_PATH))
        root = str(tmp_path)
        keys = [bound["arms"][r]["direct_arm_key"] for r in ("away_from_A", "toward_B")]
        d = _direct_store(root, "Rest", keys)
        sp = os.path.join(root, "selection.json")
        with open(sp, "w") as fh:
            json.dump(doc, fh)
        return root, sp, d

    def _refused(self, root, sp, gate=None):
        with pytest.raises(P.SelectionProjectionError) as exc:
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root,
                      mode=P.MODE_PRODUCTION, stage1=STAGE1)
        assert exc.value.gate == P.G_LANE_UNADMITTED
        if gate:
            assert gate in str(exc.value), str(exc.value)

    def test_the_VALID_W10_report_ADMITS(self, tmp_path):
        """The gate must not refuse a real admission."""
        root, sp, _ = self._root(tmp_path)
        art = P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root,
                        mode=P.MODE_PRODUCTION, stage1=STAGE1)
        adm = art["bindings"]["admissions"]["direct"]
        assert adm["admitted"] is True
        assert adm["recompute_mode"] == "all"
        assert adm["n_failed"] == 0 and adm["n_gates"] >= LA.W10_MIN_GATES
        assert adm["signature_limit"]                      # the limit is NAMED, not hidden
        # NO ABSOLUTE PATHS anywhere in the bindings
        assert "/home/" not in json.dumps(art["bindings"])

    def test_a_ONE_LINE_forged_ADMIT_is_REFUSED(self, tmp_path):
        root, sp, _ = self._root(tmp_path)
        with open(os.path.join(root, LA.W10_REPORT_FILE.format(condition="Rest")), "w") as fh:
            fh.write('{"verdict":"ADMIT"}')
        self._refused(root, sp, LA.G_SHAPE)

    def test_a_GENUINE_report_from_ANOTHER_CONDITION_is_REFUSED(self, tmp_path):
        """A real, whole, internally consistent report — about a different question."""
        root, sp, _ = self._root(tmp_path)
        other = _direct_store(root, "Stim48hr", ["direct|x|increase|Stim48hr"])
        real = json.load(open(w10_report(root, "Stim48hr", other)))
        with open(os.path.join(root, LA.W10_REPORT_FILE.format(condition="Rest")), "w") as fh:
            json.dump(real, fh)                            # renamed / copied, not re-run
        self._refused(root, sp, LA.G_BOUND_SUBJECT)

    def test_an_EDITED_report_with_a_RECOMPUTED_hash_is_REFUSED(self, tmp_path):
        """The forger reseals it. The bound bytes still are not the bytes on disk."""
        root, sp, d = self._root(tmp_path)
        rp = os.path.join(root, LA.W10_REPORT_FILE.format(condition="Rest"))
        rep = json.load(open(rp))
        rep["bound_artifact"]["arm_rows_sha256"] = "9" * 64
        rep["report_sha256"] = content_hash(
            {k: v for k, v in rep.items() if k != "report_sha256"})
        with open(rp, "w") as fh:
            json.dump(rep, fh)
        self._refused(root, sp, LA.G_BOUND_BYTES)

    def test_a_report_whose_BOUND_FILE_BYTES_MOVED_is_REFUSED(self, tmp_path):
        import pandas as pd
        root, sp, d = self._root(tmp_path)
        # the store is edited AFTER it was verified
        pd.DataFrame([{"arm_key": "x", "target_id": "t", "value": 1.0, "rank": 1,
                       "evaluable": True}]).to_parquet(os.path.join(d, "arms.parquet"))
        self._refused(root, sp, LA.G_BOUND_BYTES)

    def test_a_MISSING_GATE_is_REFUSED(self, tmp_path):
        """A report that never checked the bytes on disk did not check the bytes on disk."""
        root, sp, d = self._root(tmp_path)
        thin = [g for g in GATES if "BYTES ON DISK" not in g]
        w10_report(root, "Rest", d, gates=thin)
        self._refused(root, sp, LA.G_GATES)

    def test_a_report_with_ONE_GATE_and_no_failures_is_REFUSED(self, tmp_path):
        root, sp, d = self._root(tmp_path)
        w10_report(root, "Rest", d, gates=["it looked fine to me"])
        self._refused(root, sp, LA.G_GATES)

    @pytest.mark.parametrize("field,value", [
        ("verifier_id", "spot.stage02.some.other.verifier.v1"),
        ("verifier_code_sha256", "b" * 64),
    ])
    def test_a_WRONG_verifier_identity_or_CODE_HASH_is_REFUSED(self, tmp_path, field, value):
        root, sp, _ = self._root(tmp_path)
        rp = os.path.join(root, LA.W10_REPORT_FILE.format(condition="Rest"))
        rep = json.load(open(rp))
        rep[field] = value
        rep["report_sha256"] = content_hash(
            {k: v for k, v in rep.items() if k != "report_sha256"})
        with open(rp, "w") as fh:
            json.dump(rep, fh)
        self._refused(root, sp, LA.G_VERIFIER)

    def test_a_report_that_only_SPOT_CHECKED_is_REFUSED(self, tmp_path):
        root, sp, d = self._root(tmp_path)
        w10_report(root, "Rest", d, bound_over={"recompute_mode": "sample"})
        self._refused(root, sp, LA.G_RECOMPUTE)

    def test_a_report_binding_a_STALE_STAGE1_is_REFUSED(self, tmp_path):
        """It verified a bundle built against a different Stage-1 release. It verified a
        different release."""
        root, sp, d = self._root(tmp_path)
        w10_report(root, "Rest", d,
                   bound_over={"stage1_scorer_view_canonical_sha256": "dead" + "0" * 60})
        self._refused(root, sp, LA.G_STALE_STAGE1)

    def test_a_report_verified_under_ANOTHER_SOLVER_is_REFUSED(self, tmp_path):
        root, sp, d = self._root(tmp_path)
        w10_report(root, "Rest", d, bound_over={"solver_lock_sha256": "b9284e63" + "0" * 56})
        self._refused(root, sp, LA.G_ENV)

    def test_THE_VERIFIER_RE_DERIVES_the_admission_and_does_not_trust_the_index(self,
                                                                               tmp_path):
        """The producer's admission block is an INDEX, not evidence. Forge the store's report
        AFTER the artifact was written and reseal the artifact: the verifier rebuilds the
        admission from the ORIGINAL report and the store bytes, and refuses."""
        root, sp, d = self._root(tmp_path)
        art = P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root,
                        stage1=STAGE1)
        ap = os.path.join(root, P.ARTIFACT)
        with open(ap, "w") as fh:
            json.dump(art, fh, indent=2, sort_keys=True)
        assert V.verify(ap, selection_path=sp, bundles_root=root)["verdict"] == "admit"

        # now replace the real report with a one-line forgery, leaving the artifact untouched
        with open(os.path.join(root, LA.W10_REPORT_FILE.format(condition="Rest")), "w") as fh:
            fh.write('{"verdict":"ADMIT"}')

        rep = V.verify(ap, selection_path=sp, bundles_root=root)
        assert rep["verdict"] == "reject"
        assert any(V.G_UNADMITTED in f for f in rep["failures"])


class TestTheStage1IdentityIsREQUIREDInProduction:
    def test_production_REFUSES_when_the_stage1_identity_is_not_SUPPLIED(self, tmp_path):
        """The quietest fail-open there is: the gate exists, it runs, and it compares nothing.
        Deriving the expected Stage-1 from the selection meant a selection that happened not to
        carry it SKIPPED the check entirely."""
        doc = emit()
        bound = S1.validate(doc, S1.load_schema(SCHEMA_PATH))
        root, sp = _release(tmp_path, doc, bound)
        with pytest.raises(P.SelectionProjectionError) as exc:
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root,
                      mode=P.MODE_PRODUCTION, stage1={})
        assert exc.value.gate == P.G_STAGE1_UNBOUND
