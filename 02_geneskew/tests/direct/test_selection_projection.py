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

STAGE1 = {"stage1_release_raw_sha256": "0c336546" + "0" * 56,
          "stage1_scorer_view_canonical_sha256": "5d1d8c36" + "0" * 56,
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
        # W10's bound artifact carries the SCORER identity; it does not carry the release raw
        # sha — that is the field W4 binds.
        "stage1_scorer_view_canonical_sha256":
            STAGE1["stage1_scorer_view_canonical_sha256"],
        "registry_scorer_projection_sha256": STAGE1["registry_scorer_projection_sha256"],
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
    """A temporal bundle in the NATIVE shape: bundle_key, and every arm binding its ranking."""
    rel = f"{frm}__to__{to}"
    d = os.path.join(root, "temporal", rel)
    os.makedirs(os.path.join(d, "rankings"), exist_ok=True)

    arm_entries = []
    for j, key in enumerate(arms):
        path = f"rankings/arm_{j}.json"
        body = {"arm_key": key,
                "records": [{"target_id": f"ENSG{i:011d}", "arm_value": 1.0 - i / 500.0,
                             "rank": i + 1, "evaluable": True} for i in range(n)]}
        with open(os.path.join(d, path), "w") as fh:
            json.dump(body, fh, indent=2, sort_keys=True)
        arm_entries.append({"arm_key": key,
                            "ranking": {"path": path,
                                        "raw_sha256": file_sha256(os.path.join(d, path)),
                                        "canonical_sha256": content_hash(body)}})

    with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
        json.dump({"schema_version": "spot.stage02_temporal_arm_bundle.v1",
                   "bundle_id": f"T-{frm}-{to}", "bundle_key": rel, "lane": "temporal",
                   "context": {"from_condition": frm, "to_condition": to},
                   "arms": arm_entries}, fh, indent=2, sort_keys=True)

    external_admission(root, "temporal",
                       [{"bundle_id": f"T-{frm}-{to}", "relative_dir": rel,
                         "files": {}, "rankings": {}}])
    return d


# W11 publishes 188 gates. The fixture must hash to the PUBLISHED inventory sha or the pin
# refuses it — so the fixture DECLARES that it is a stand-in and monkeypatches the pin only
# where a stand-in is legitimate. The pin itself is never weakened.
def w11_gates(n=None):
    return [f"w11 gate {i}" for i in range(n or LA.W11_N_GATES)]


@pytest.fixture(autouse=True)
def _w11_standin_pin(monkeypatch):
    """These fixtures are a STAND-IN for W11's real 188-gate inventory.

    The PIN (dc9b6bc1…) is the hash of W11's ACTUAL gate names, which are not on this host. A
    stand-in cannot hash to it — and it must not be able to. So the pin is redirected to the
    stand-in's own hash HERE, explicitly and visibly, rather than the pin being softened in the
    contract. `test_the_PUBLISHED_W11_pin_is_the_real_one` asserts the shipped value is
    untouched, and the REAL-BYTES control (below) runs against the true pin.
    """
    import verify_admission_rules as VR
    h = content_hash(w11_gates())
    for mod in (LA, VR):
        spec = dict(mod.EXTERNAL["temporal"], gate_inventory_sha256=h)
        monkeypatch.setitem(mod.EXTERNAL, "temporal", spec)


def external_admission(root, lane, bundles, *, gates=None, stage1=None, inv_over=None,
                       binds_over=None):
    """The REAL external envelope shape (W11 / W4) + the NATIVE producer inventory.

    THE NATIVE TEMPORAL INVENTORY HAS NO TOP-LEVEL verdict/admitted/self_admitted. It says
    `external_admission.status = pending` and nothing else — "pending is the only honest
    producer state" (temporal/arms/arm_release.py). The committed contract demanded the
    other shape and would have REFUSED the real release.
    """
    spec = LA.EXTERNAL[lane]

    body = {"schema_version": spec["inventory_schema"], "lane": lane,
            "release_id_rule": "sha256(canonical JSON excluding release_id)",
            "n_bundles": len(bundles), "bundles": bundles,
            "external_admission": {"status": "pending",
                                   "required_verifier_id": spec["verifier_id"],
                                   "required_report_schema_version": spec["schema"]}}
    body.update(inv_over or {})
    inv = dict(body, release_id=content_hash(body))
    ip = os.path.join(root, spec["inventory"])
    with open(ip, "w") as fh:
        json.dump(inv, fh, indent=2, sort_keys=True)
    raw = file_sha256(ip)

    s1 = stage1 or STAGE1
    inv_gates = list(spec["gates"]) if gates is None and spec["gates"] else (
        gates if gates is not None else w11_gates())

    if lane == "temporal":
        # W11's REAL fourteen binds keys. Stage-1 raw is NESTED.
        binds = {"bundles": [b["bundle_id"] for b in bundles],
                 "code_identity": "c" * 64, "env_lock_sha256": "e" * 64,
                 "method": "spot.stage02.temporal.method.v1",
                 "native_release_root": "output/temporal",
                 "per_program_projection_sha256": "p" * 64,
                 # DERIVED, exactly as the real verifier derives them
                 "producer_release_canonical_sha256": content_hash(
                     json.loads(open(ip, "rb").read())),
                 "producer_release_file": spec["inventory"],
                 "producer_release_id": inv["release_id"],
                 "producer_release_raw_sha256": raw,
                 "rankings_digest": (LA._rankings_digest(
                     os.path.join(root, "temporal"), inv, content_hash, file_sha256)
                     or "r" * 64),
                 "registry_scorer_projection_sha256":
                     s1["registry_scorer_projection_sha256"],
                 "selector_condition_sequence": ["Rest", "Stim8hr", "Stim48hr"],
                 "stage1_release": {
                     "stage1_release_raw_sha256": s1["stage1_release_raw_sha256"]}}
    else:
        binds = {"producer_release_id": inv["release_id"],
                 "producer_release_raw_sha256": raw, "inventory_raw_sha256": raw,
                 "stage1_release_raw_sha256": s1["stage1_release_raw_sha256"]}
    binds.update(binds_over or {})

    env = {"schema_version": spec["schema"], "verifier_id": spec["verifier_id"],
           "lane": lane, "n_bundles": len(bundles),
           "gate_inventory": inv_gates, "binds": binds,
           "n_failed": 0, "verdict": "ADMIT"}
    for a in spec["asserts"]:
        env[a] = True
    p = os.path.join(root, spec["file"])
    with open(p, "w") as fh:
        json.dump(dict(env, report_id=content_hash(env)), fh, indent=2, sort_keys=True)
    return p


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


class TestAnEmptyVerificationAdmitsNothing:
    """An admission over an EMPTY set looks exactly like one that admits everything."""

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

    def test_an_EMPTY_arm_inventory_RESEALED_is_REFUSED(self, tmp_path):
        """`if keys and arm_key not in keys` — an EMPTY inventory skipped the check and
        ADMITTED. A verification that covered no arms is not a verification of any arm."""
        root, sp, d = self._root(tmp_path)
        w10_report(root, "Rest", d, bound_over={"arm_inventory": []})
        with pytest.raises(P.SelectionProjectionError) as exc:
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root,
                      stage1=STAGE1)
        assert LA.G_EMPTY_INVENTORY in str(exc.value)

    def test_a_PARTIAL_arm_inventory_is_REFUSED(self, tmp_path):
        """A report that covered only some of the arms admits only some of them."""
        root, sp, d = self._root(tmp_path)
        doc = json.load(open(os.path.join(d, "arm_bundle.json")))
        w10_report(root, "Rest", d,
                   bound_over={"arm_inventory": [{"arm_key": doc["arms"][0]["arm_key"]}]})
        with pytest.raises(P.SelectionProjectionError) as exc:
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root,
                      stage1=STAGE1)
        assert LA.G_EMPTY_INVENTORY in str(exc.value)


class TestTheEXTERNALEnvelopeIsValidatedNotJustHashed:
    """W11/W4: a report could assert nothing about its independence, run NO gates at all, and
    clear an EMPTY release — and only its hash was checked."""

    def _temporal(self, tmp_path):
        doc = emit(mode=S1.MODE_TEMPORAL, conditions=["Rest", "Stim48hr"])
        art, ap, sp, root = _project(tmp_path, doc)
        return root, sp, art

    def _refused(self, root, sp, marker):
        with pytest.raises(P.SelectionProjectionError) as exc:
            P.project(selection_path=sp, schema_path=SCHEMA_PATH, bundles_root=root,
                      mode=P.MODE_PRODUCTION, stage1=STAGE1)
        assert marker in str(exc.value), str(exc.value)

    def test_an_EMPTY_bundle_list_is_REFUSED(self, tmp_path):
        root, sp, _ = self._temporal(tmp_path)
        external_admission(root, "temporal", [])
        self._refused(root, sp, LA.G_EMPTY_INVENTORY)

    @pytest.mark.parametrize("field", ["generator_is_not_verifier", "fail_closed"])
    def test_BOTH_lanes_must_ASSERT_independence_and_fail_closed(self, tmp_path, field):
        """The REAL W11 envelope carries both (confirmed on admission.json), as W4's does. An
        empty assert set under-checked exactly the two claims a forged envelope would omit."""
        assert field in LA.EXTERNAL["pathway"]["asserts"]
        assert field in LA.EXTERNAL["temporal"]["asserts"]

    def test_an_INVENTED_pending_field_on_the_native_inventory_is_REFUSED(self, tmp_path):
        """The native inventory has NO top-level verdict/admitted/self_admitted. A producer
        that wrote itself one wrote itself an admission."""
        root, sp, _ = self._temporal(tmp_path)
        external_admission(root, "temporal", [{"bundle_id": "T-Rest-Stim48hr"}],
                           inv_over={"verdict": "ADMIT", "admitted": True,
                                     "self_admitted": False})
        self._refused(root, sp, LA.G_PRODUCER_SELF_ADMITTED)

    def test_a_non_PENDING_external_admission_status_is_REFUSED(self, tmp_path):
        root, sp, _ = self._temporal(tmp_path)
        external_admission(root, "temporal", [{"bundle_id": "T-Rest-Stim48hr"}],
                           inv_over={"external_admission": {"status": "admitted"}})
        self._refused(root, sp, LA.G_PRODUCER_SELF_ADMITTED)

    def test_ONE_MISSING_GATE_is_REFUSED(self, tmp_path):
        """187 of 188. The count AND the inventory hash both move."""
        root, sp, _ = self._temporal(tmp_path)
        external_admission(root, "temporal", [{"bundle_id": "T-Rest-Stim48hr"}],
                           gates=w11_gates(LA.W11_N_GATES - 1))
        self._refused(root, sp, LA.G_GATES)

    def test_an_EDITED_RANKING_is_REFUSED(self, tmp_path):
        """The cleared inventory bound every ranking file. Editing one after the fact is
        exactly the mutation an inventory of hashes exists to catch."""
        doc = emit(mode=S1.MODE_TEMPORAL, conditions=["Rest", "Stim48hr"])
        bound = S1.validate(doc, S1.load_schema(SCHEMA_PATH))
        root = str(tmp_path)
        keys = [bound["arms"][r]["temporal_arm_key"] for r in ("away_from_A", "toward_B")]
        d = _temporal_store(root, "Rest", "Stim48hr", keys)
        for c in ("Rest", "Stim48hr"):
            _direct_store(root, c, [bound["arms"][r]["direct_arm_key"]
                                    for r in ("away_from_A", "toward_B")])
        rel = "rankings/arm_0.json"
        external_admission(root, "temporal", [{
            "bundle_id": "T-Rest-Stim48hr",
            "files": {}, "rankings": {rel: {"raw_sha256": file_sha256(
                os.path.join(d, rel))}}}])
        sp = os.path.join(root, "selection.json")
        with open(sp, "w") as fh:
            json.dump(doc, fh)
        # ...and now somebody edits the ranking
        rd = json.load(open(os.path.join(d, rel)))
        rd["records"][0]["arm_value"] = -99.0
        with open(os.path.join(d, rel), "w") as fh:
            json.dump(rd, fh)
        self._refused(root, sp, LA.G_BOUND_BYTES)

    def test_a_STALE_NESTED_stage1_raw_is_REFUSED(self, tmp_path):
        """W11 nests it: binds.stage1_release.stage1_release_raw_sha256 — NOT top-level."""
        root, sp, _ = self._temporal(tmp_path)
        external_admission(
            root, "temporal", [{"bundle_id": "T-Rest-Stim48hr"}],
            binds_over={"stage1_release": {"stage1_release_raw_sha256": "dead" + "0" * 60}})
        self._refused(root, sp, LA.G_STALE_STAGE1)

    def test_a_MISSING_BINDS_KEY_is_REFUSED(self, tmp_path):
        root, sp, _ = self._temporal(tmp_path)
        p = os.path.join(root, "temporal_arm_external_admission.json")
        rep = json.load(open(p))
        del rep["binds"]["rankings_digest"]
        rep["report_id"] = content_hash({k: v for k, v in rep.items() if k != "report_id"})
        with open(p, "w") as fh:
            json.dump(rep, fh)
        self._refused(root, sp, LA.G_BOUND_BYTES)

    def test_a_report_binding_a_STALE_STAGE1_RELEASE_RAW_is_REFUSED(self, tmp_path):
        """The field W4 ACTUALLY binds: binds.stage1_release_raw_sha256."""
        root, sp, _ = self._temporal(tmp_path)
        stale = dict(STAGE1, stage1_release_raw_sha256="dead" + "0" * 60)
        external_admission(root, "temporal", [{"bundle_id": "T-Rest-Stim48hr"}], stage1=stale)
        self._refused(root, sp, LA.G_STALE_STAGE1)

    def test_the_PATHWAY_gate_inventory_must_be_W4s_EXACT_TWELVE(self, tmp_path):
        """W4 runs a named 12-gate inventory (verify_pathway_release @ ef136a9). A report that
        ran a different set of gates is not this verifier's admission."""
        gates = LA.EXTERNAL["pathway"]["gates"]
        assert len(gates) == 12
        assert gates[0] == (
            "the_condition_and_source_universe_comes_from_the_authoritative_stage1_release")
        assert gates[-1] == "the_producer_inventory_binds_the_exact_bytes_that_landed_on_disk"


class TestTheVerifierDoesNotSHARETheProducersImplementation:
    def test_the_verifier_does_NOT_import_the_producers_admission_module(self):
        """Calling the producer's admission code to 're-derive' the admission is not a second
        opinion — it is the same opinion twice, and the two could never disagree."""
        import ast
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                "analysis", "direct",
                                "verify_selection_projection.py")).read()
        names = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.ImportFrom):
                names.update(a.name for a in node.names)
                names.add((node.module or "").split(".")[-1])
            elif isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
        assert "lane_admission" not in names
        assert "verify_admission_rules" in names

    def test_a_DELIBERATE_PRODUCER_VERIFIER_DRIFT_is_CAUGHT(self, tmp_path, monkeypatch):
        """Two implementations, on purpose. Move ONE of them and the pair must disagree —
        otherwise the second implementation is decoration."""
        import verify_admission_rules as VR

        doc = emit()
        art, ap, sp, root = _project(tmp_path, doc)
        assert V.verify(ap, selection_path=sp, bundles_root=root)["verdict"] == "admit"

        # the VERIFIER now pins a different W10 code hash than the producer does
        monkeypatch.setattr(VR, "W10_VERIFIER_CODE", "f" * 64)
        rep = V.verify(ap, selection_path=sp, bundles_root=root)
        assert rep["verdict"] == "reject"
        assert any(V.G_UNADMITTED in f for f in rep["failures"])

    def test_the_two_restatements_AGREE_today(self, tmp_path):
        """They must not have drifted by accident either."""
        import verify_admission_rules as VR
        assert VR.W10_VERIFIER_CODE == LA.W10_VERIFIER_CODE
        assert VR.W10_REPORT_SCHEMA == LA.W10_REPORT_SCHEMA
        assert VR.SOLVER_LOCK_SHA256 == LA.SOLVER_LOCK_SHA256
        assert VR.W4_GATES == LA.EXTERNAL["pathway"]["gates"]


# --------------------------------------------------------------------------- #
# THE REAL W11 BYTES. Not on this host at the time of writing — and that is REPORTED, not
# papered over. This control runs against the TRUE published pin the moment they appear.
# --------------------------------------------------------------------------- #
W11_INVENTORY = ("/home/tcelab/.spot-runs/temporal-candidate-20260713T174955Z/output/"
                 "temporal/temporal_arm_release.json")
W11_ADMISSION = ("/home/tcelab/.spot-audits/temporal-repair-b7de295-independent/results/"
                 "admission.json")
W11_INVENTORY_RAW = "0a4929aad0ab5e47f862b041d4d8c7de018b20774786ea77a859de14f6161617"
W11_RELEASE_ID = "6aaa04a2003b5f0961b26b263ef25b9b9cb9ed7cc20d059bf5c80fc355c73f51"
W11_REPORT_ID = "15e02e764ee04b79822b2740a464ba05df46dd8b3dc169c4088171668f72633a"


class TestTheREALW11Bytes:
    """No stand-in. The actual immutable files, against the actual published pin."""

    @pytest.fixture(autouse=True)
    def _no_standin(self, monkeypatch):
        """Undo the module-wide stand-in pin: this class uses the REAL one."""
        import verify_admission_rules as VR
        for mod in (LA, VR):
            monkeypatch.setitem(mod.EXTERNAL, "temporal",
                                dict(mod.EXTERNAL["temporal"],
                                     gate_inventory_sha256=LA.W11_GATE_INVENTORY_SHA256))

    def _real(self):
        missing = [p for p in (W11_INVENTORY, W11_ADMISSION) if not os.path.exists(p)]
        if missing:
            pytest.skip("THE REAL W11 BYTES ARE NOT ON THIS HOST: " + "; ".join(missing) +
                        ". This control CANNOT be executed here and the temporal branch is "
                        "therefore NOT proven end-to-end against real bytes. It is not "
                        "passing — it is skipped, and the skip says so.")
        return json.load(open(W11_INVENTORY)), json.load(open(W11_ADMISSION))

    def test_the_PUBLISHED_W11_pin_is_the_real_one(self):
        """The pin itself is asserted here, unpatched, whether or not the bytes are present."""
        assert LA.W11_N_GATES == 188
        assert LA.W11_GATE_INVENTORY_SHA256 == (
            "dc9b6bc14ba56c28efcc4bcabbca456fe49d0e816cba036546f85d98ee27ba97")
        assert len(LA.W11_BINDS_KEYS) == 14
        assert "inventory_raw_sha256" not in LA.W11_BINDS_KEYS      # W11 does NOT bind it
        assert "stage1_release" in LA.W11_BINDS_KEYS                # ...it NESTS Stage-1 there

    def test_the_REAL_inventory_hashes_and_re_derives(self):
        inv, _ = self._real()
        assert file_sha256(W11_INVENTORY) == W11_INVENTORY_RAW
        assert inv["release_id"] == W11_RELEASE_ID
        assert inv["release_id"] == content_hash(
            {k: v for k, v in inv.items() if k != "release_id"})
        # the NATIVE shape: pending, and no top-level verdict at all
        assert inv["external_admission"]["status"] == "pending"
        for invented in ("verdict", "admitted", "self_admitted", "verifier_id"):
            assert invented not in inv

    def test_the_REAL_admission_hashes_and_carries_the_188_gate_inventory(self):
        _, adm = self._real()
        assert adm["schema_version"] == "spot.stage02_temporal_arm_external_admission.v1"
        assert adm["report_id"] == W11_REPORT_ID
        assert adm["report_id"] == content_hash(
            {k: v for k, v in adm.items() if k != "report_id"})
        assert len(adm["gate_inventory"]) == 188
        assert content_hash(adm["gate_inventory"]) == LA.W11_GATE_INVENTORY_SHA256
        assert set(adm["binds"]) >= LA.W11_BINDS_KEYS
        assert adm["binds"]["producer_release_id"] == W11_RELEASE_ID
        assert adm["binds"]["producer_release_raw_sha256"] == W11_INVENTORY_RAW
        assert adm["binds"]["stage1_release"]["stage1_release_raw_sha256"]

    def _staged(self, tmp_path):
        """The REAL inventory + the REAL admission, at the names the contract reads."""
        import shutil
        inv, adm = self._real()
        root = str(tmp_path)
        shutil.copyfile(W11_INVENTORY, os.path.join(root, "temporal_arm_release.json"))
        shutil.copyfile(W11_ADMISSION,
                        os.path.join(root, "temporal_arm_external_admission.json"))
        return root, inv, adm

    def _real_root(self, tmp_path):
        """The REAL inventory + REAL admission + the REAL bundle directories, byte for byte."""
        import shutil
        inv, adm = self._real()
        base = os.path.dirname(W11_INVENTORY)
        missing = [b["relative_dir"] for b in inv["bundles"]
                   if not os.path.isdir(os.path.join(base, b["relative_dir"]))]
        if missing:
            pytest.skip(f"the real bundle directories are not on this host: {missing}")

        root = str(tmp_path)
        shutil.copyfile(W11_INVENTORY, os.path.join(root, "temporal_arm_release.json"))
        shutil.copyfile(W11_ADMISSION,
                        os.path.join(root, "temporal_arm_external_admission.json"))
        for b in inv["bundles"]:
            shutil.copytree(os.path.join(base, b["relative_dir"]),
                            os.path.join(root, "temporal", b["relative_dir"]))
        s1 = dict(STAGE1, stage1_release_raw_sha256=(
            adm["binds"]["stage1_release"]["stage1_release_raw_sha256"]))
        return root, inv, adm, s1

    def test_END_TO_END_the_REAL_W11_admission_ADMITS_the_REAL_bundles(self, tmp_path):
        """THE CONTROL. Real inventory, real 188-gate admission, real bundle bytes, real pin.

        Every leg: schema, verifier id, report_id self-hash, verdict, the 188-gate inventory
        against the PUBLISHED hash, the 14 binds keys, producer_release_id/_raw against the
        inventory ON DISK, release_id re-derivation, the native PENDING state, the NESTED
        Stage-1 raw, the non-empty bundle list, and EVERY bundle file and EVERY ranking
        re-hashed against the bytes.
        """
        root, inv, _adm, s1 = self._real_root(tmp_path)

        for entry in inv["bundles"]:
            bd = os.path.join(root, "temporal", entry["relative_dir"])
            out = LA.bind_external(root, "temporal", bundle_dir=bd, stage1=s1)
            assert out["admitted"] is True
            assert out["n_gates"] == 188
            assert out["n_bundles"] == 6
            assert out["bound_bundle_id"] == entry["bundle_id"]

    def test_the_VERIFIER_ADMITS_the_REAL_bytes_INDEPENDENTLY(self, tmp_path):
        """generator != verifier, on real bytes: the independent restatement admits too."""
        import verify_admission_rules as VR
        root, inv, _adm, s1 = self._real_root(tmp_path)
        bd = os.path.join(root, "temporal", inv["bundles"][0]["relative_dir"])
        out = VR.check_external(root, "temporal", bundle_dir=bd, stage1=s1)
        assert out["admitted"] is True and out["n_gates"] == 188

    def test_an_EDITED_RANKING_in_the_REAL_release_is_REFUSED(self, tmp_path):
        """The real inventory bound every ranking file. Edit one and it refuses."""
        root, inv, _adm, s1 = self._real_root(tmp_path)
        entry = inv["bundles"][0]
        bd = os.path.join(root, "temporal", entry["relative_dir"])
        rel = sorted(entry["rankings"])[0]
        target = os.path.join(bd, rel)
        os.chmod(target, 0o644)                  # the source is immutable; the COPY is ours
        with open(target, "a") as fh:
            fh.write("\n")                       # ONE byte
        with pytest.raises(LA.AdmissionError) as exc:
            LA.bind_external(root, "temporal", bundle_dir=bd, stage1=s1)
        assert exc.value.gate == LA.G_BOUND_BYTES
        # The RANKINGS DIGEST catches it release-wide, BEFORE the per-file check — a stronger
        # refusal: one edited byte in one ranking moves a digest taken over all 120 of them.
        assert "rankings_digest" in str(exc.value) or rel in str(exc.value)

    def test_the_REAL_envelope_ASSERTS_independence_AND_fail_closed(self):
        """It DOES carry both. An empty assert set under-checked exactly the two claims a
        forged envelope would omit."""
        _inv, adm = self._real()
        assert adm["generator_is_not_verifier"] is True
        assert adm["fail_closed"] is True
        assert LA.EXTERNAL["temporal"]["asserts"] == (
            "generator_is_not_verifier", "fail_closed")

    @pytest.mark.parametrize("field", ["generator_is_not_verifier", "fail_closed"])
    def test_DROPPING_an_assert_from_the_REAL_envelope_is_REFUSED(self, tmp_path, field):
        root, inv, adm, s1 = self._real_root(tmp_path)
        forged = dict(adm)
        forged[field] = False
        forged.pop("report_id")
        forged["report_id"] = content_hash(forged)              # resealed
        with open(os.path.join(root, "temporal_arm_external_admission.json"), "w") as fh:
            json.dump(forged, fh)
        bd = os.path.join(root, "temporal", inv["bundles"][0]["relative_dir"])
        with pytest.raises(LA.AdmissionError) as exc:
            LA.bind_external(root, "temporal", bundle_dir=bd, stage1=s1)
        assert exc.value.gate == LA.G_VERIFIER
        assert field in str(exc.value)

    def test_the_CANONICAL_binding_is_RE_DERIVED_from_the_real_inventory(self, tmp_path):
        """producer_release_canonical_sha256 = content_hash(json.loads(raw bytes)). It was
        accepted on PRESENCE — a check that compares nothing."""
        _inv, adm = self._real()
        with open(W11_INVENTORY, "rb") as fh:
            iraw = fh.read()
        assert adm["binds"]["producer_release_canonical_sha256"] == content_hash(
            json.loads(iraw))

    def test_a_FORGED_CANONICAL_binding_is_REFUSED(self, tmp_path):
        root, inv, adm, s1 = self._real_root(tmp_path)
        forged = dict(adm)
        forged["binds"] = dict(adm["binds"],
                               producer_release_canonical_sha256="dead" + "0" * 60)
        forged.pop("report_id")
        forged["report_id"] = content_hash(forged)
        with open(os.path.join(root, "temporal_arm_external_admission.json"), "w") as fh:
            json.dump(forged, fh)
        bd = os.path.join(root, "temporal", inv["bundles"][0]["relative_dir"])
        with pytest.raises(LA.AdmissionError) as exc:
            LA.bind_external(root, "temporal", bundle_dir=bd, stage1=s1)
        assert exc.value.gate == LA.G_BOUND_BYTES
        assert "producer_release_canonical_sha256" in str(exc.value)

    def test_the_RANKINGS_DIGEST_is_RE_DERIVED_over_all_120_rankings(self, tmp_path):
        """One row per ARM RANKING across every bundle — {bundle_key, arm_key, path,
        raw_sha256, canonical_sha256} — sorted, with raw/canonical RECOMPUTED FROM DISK."""
        root, inv, adm, _s1 = self._real_root(tmp_path)
        native = os.path.join(root, "temporal")
        got = LA._rankings_digest(native, inv, content_hash, file_sha256)
        assert got == adm["binds"]["rankings_digest"]
        # 6 bundles x 20 arms
        rows = sum(len(json.load(open(os.path.join(native, b["relative_dir"],
                                                   "arm_bundle.json")))["arms"])
                   for b in inv["bundles"])
        assert rows == 120

    def test_a_FORGED_RANKINGS_DIGEST_is_REFUSED(self, tmp_path):
        root, inv, adm, s1 = self._real_root(tmp_path)
        forged = dict(adm)
        forged["binds"] = dict(adm["binds"], rankings_digest="beef" + "0" * 60)
        forged.pop("report_id")
        forged["report_id"] = content_hash(forged)
        with open(os.path.join(root, "temporal_arm_external_admission.json"), "w") as fh:
            json.dump(forged, fh)
        bd = os.path.join(root, "temporal", inv["bundles"][0]["relative_dir"])
        with pytest.raises(LA.AdmissionError) as exc:
            LA.bind_external(root, "temporal", bundle_dir=bd, stage1=s1)
        assert exc.value.gate == LA.G_BOUND_BYTES
        assert "rankings_digest" in str(exc.value)

    def test_the_VERIFIER_re_derives_BOTH_digests_INDEPENDENTLY(self, tmp_path):
        import verify_admission_rules as VR
        root, inv, adm, _s1 = self._real_root(tmp_path)
        native = os.path.join(root, "temporal")
        assert VR._rankings_digest(native, inv, VR.canon, VR.raw) == \
            adm["binds"]["rankings_digest"]
        with open(W11_INVENTORY, "rb") as fh:
            assert VR.canon(json.loads(fh.read())) == \
                adm["binds"]["producer_release_canonical_sha256"]

    def test_a_PRODUCER_VERIFIER_DRIFT_is_CAUGHT_on_the_REAL_bytes(self, tmp_path,
                                                                   monkeypatch):
        """Move the VERIFIER'S pin off the published one: the pair must disagree."""
        import verify_admission_rules as VR
        root, inv, _adm, s1 = self._real_root(tmp_path)
        bd = os.path.join(root, "temporal", inv["bundles"][0]["relative_dir"])
        assert LA.bind_external(root, "temporal", bundle_dir=bd, stage1=s1)["admitted"]

        monkeypatch.setitem(VR.EXTERNAL, "temporal",
                            dict(VR.EXTERNAL["temporal"], gate_inventory_sha256="f" * 64))
        with pytest.raises(VR.AdmissionError) as exc:
            VR.check_external(root, "temporal", bundle_dir=bd, stage1=s1)
        assert exc.value.gate == VR.G_GATES

    def test_the_VERIFIER_reaches_the_SAME_point_on_the_REAL_bytes(self, tmp_path):
        """generator != verifier, on real bytes: the independent restatement agrees."""
        import verify_admission_rules as VR
        root, inv, adm = self._staged(tmp_path)
        entry = inv["bundles"][0]
        bd = os.path.join(root, "temporal", str(entry["relative_dir"]))
        os.makedirs(bd, exist_ok=True)
        with open(os.path.join(bd, "arm_bundle.json"), "w") as fh:
            json.dump({"schema_version": "spot.stage02_temporal_arm_bundle.v1",
                       "bundle_id": entry["bundle_id"], "lane": "temporal",
                       "context": {"from_condition": entry["from_condition"],
                                   "to_condition": entry["to_condition"]}}, fh)
        s1 = dict(STAGE1, stage1_release_raw_sha256=(
            adm["binds"]["stage1_release"]["stage1_release_raw_sha256"]))

        with pytest.raises(VR.AdmissionError) as exc:
            VR.check_external(root, "temporal", bundle_dir=bd, stage1=s1)
        assert exc.value.gate == VR.G_BOUND_BYTES

    def test_a_STALE_NESTED_stage1_is_REFUSED_ON_THE_REAL_ADMISSION(self, tmp_path):
        """The real envelope, against a Stage-1 it was not built on."""
        root, _inv, _adm = self._staged(tmp_path)
        bd = os.path.join(root, "temporal", "x")
        os.makedirs(bd, exist_ok=True)
        with open(os.path.join(bd, "arm_bundle.json"), "w") as fh:
            json.dump({"schema_version": "spot.stage02_temporal_arm_bundle.v1",
                       "bundle_id": "x", "lane": "temporal",
                       "context": {"from_condition": "Rest", "to_condition": "Stim48hr"}}, fh)
        with pytest.raises(LA.AdmissionError) as exc:
            LA.bind_external(root, "temporal", bundle_dir=bd,
                             stage1=dict(STAGE1,
                                         stage1_release_raw_sha256="dead" + "0" * 60))
        assert exc.value.gate == LA.G_STALE_STAGE1

    def test_ONE_MISSING_GATE_is_REFUSED_ON_THE_REAL_ADMISSION(self, tmp_path):
        """Drop one of W11's 188 real gate names and reseal: the PUBLISHED pin refuses it."""
        root, _inv, adm = self._staged(tmp_path)
        forged = dict(adm)
        forged["gate_inventory"] = adm["gate_inventory"][:-1]           # 187
        forged.pop("report_id")
        forged["report_id"] = content_hash(forged)                      # resealed
        with open(os.path.join(root, "temporal_arm_external_admission.json"), "w") as fh:
            json.dump(forged, fh)

        bd = os.path.join(root, "temporal", "x")
        os.makedirs(bd, exist_ok=True)
        with open(os.path.join(bd, "arm_bundle.json"), "w") as fh:
            json.dump({"bundle_id": "x"}, fh)
        with pytest.raises(LA.AdmissionError) as exc:
            LA.bind_external(root, "temporal", bundle_dir=bd, stage1=STAGE1)
        assert exc.value.gate == LA.G_GATES
        assert "188" in str(exc.value)

    def test_THE_BUNDLE_BYTE_LEG_IS_UNPROVEN_and_says_so(self):
        """The 6 bundle directories were NOT copied. This leg of the contract — every bundle
        file and EVERY RANKING re-hashed against the bytes on disk — is therefore NOT proven on
        real bytes, and production must not proceed on temporal until it is."""
        base = os.path.dirname(W11_INVENTORY)
        inv = json.load(open(W11_INVENTORY)) if os.path.exists(W11_INVENTORY) else {"bundles": []}
        missing = [b["relative_dir"] for b in inv.get("bundles", [])
                   if not os.path.isdir(os.path.join(base, b["relative_dir"]))]
        if not missing:
            # the bytes landed: prove the leg for real, against the inventory's own hashes
            for b in inv["bundles"]:
                d = os.path.join(base, b["relative_dir"])
                for group in ("files", "rankings"):
                    for name, e in (b.get(group) or {}).items():
                        assert file_sha256(os.path.join(d, name)) == e["raw_sha256"], name
            return

        # The CODE is fail-closed here regardless: bind_external re-hashes every bundle file
        # and every ranking, so temporal CANNOT be admitted in production without these bytes.
        # This marker exists so the gap cannot be forgotten — it is not a silent skip.
        pytest.skip(
            "PRODUCTION GATE (temporal): the 6 bundle directories named by the real inventory "
            f"are NOT on this host: {missing}. The per-bundle / per-ranking byte-binding leg of "
            "the W11 contract cannot be exercised, so the temporal lane is NOT proven "
            "end-to-end on real bytes. Production is fail-closed without them (bind_external "
            "re-hashes each one). Copy output/temporal/<relative_dir>/ from tcefold to close it.")


# --------------------------------------------------------------------------- #
# THE W10 CODE PIN. RE-DERIVED, never copied.
#
# I inherited 8290802638… and it REFUSED THREE GENUINE, GREEN W10 REPORTS. A gate that refuses
# real evidence is not a strict gate, it is a broken one — and the failure mode is nastier than
# a fail-open, because it looks like rigour. The reports were never the problem; the constant
# was. So the pin is now RE-DERIVED from the checkout that actually wrote them.
# --------------------------------------------------------------------------- #
W10_PRODUCER_ROOT = ("/home/tcelab/worktrees/spot-stage2-w10-producer-root/"
                     "02_geneskew/analysis/direct")


class TestTheW10CodePinIsRE_DERIVED:
    def test_the_pin_RE_DERIVES_from_the_canonical_W10_checkout(self):
        """Not copied from a doc. Computed, from the tree that wrote the reports."""
        if not os.path.isdir(W10_PRODUCER_ROOT):
            pytest.skip("the W10 producer-root checkout is not on this host")
        import subprocess
        out = subprocess.run(
            [sys.executable, "-c",
             "import sys;sys.path.insert(0,'.');import verify_arm_report as R;"
             "print(R.verifier_code_sha256())"],
            cwd=W10_PRODUCER_ROOT, capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == LA.W10_VERIFIER_CODE

    def test_the_STALE_pin_is_NAMED_and_is_NOT_the_pin(self):
        import verify_admission_rules as VR
        stale = "8290802638898db622a8baf19f233b54b5f6f1c8434f192730aa28f829f8715f"
        assert LA.W10_VERIFIER_CODE_PREVIOUS == stale
        assert LA.W10_VERIFIER_CODE != stale
        assert LA.W10_VERIFIER_CODE == (
            "943d32bd5317bbc84d2705a39f98de024f10548d1995cd6bc42ed56fb9efc174")
        assert VR.W10_VERIFIER_CODE == LA.W10_VERIFIER_CODE      # both sides re-pinned

    def test_a_report_bound_to_the_STALE_pin_is_REFUSED(self, tmp_path):
        """The pre-producer-code-root build is not the current verifier."""
        doc = emit()
        bound = S1.validate(doc, S1.load_schema(SCHEMA_PATH))
        root = str(tmp_path)
        keys = [bound["arms"][r]["direct_arm_key"] for r in ("away_from_A", "toward_B")]
        d = _direct_store(root, "Rest", keys)
        rp = os.path.join(root, LA.W10_REPORT_FILE.format(condition="Rest"))
        rep = json.load(open(rp))
        rep["verifier_code_sha256"] = LA.W10_VERIFIER_CODE_PREVIOUS
        rep["report_sha256"] = content_hash(
            {k: v for k, v in rep.items() if k != "report_sha256"})
        with open(rp, "w") as fh:
            json.dump(rep, fh)

        with pytest.raises(LA.AdmissionError) as exc:
            LA.bind_direct(root, condition="Rest", bundle_dir=d,
                           arm_key=keys[0], stage1={})
        assert exc.value.gate == LA.G_VERIFIER

    def test_the_REAL_admitted_W10_reports_carry_the_CANONICAL_pin(self):
        """The three real reports, unedited, bind 943d32bd… — the current verifier."""
        base = "/home/tcelab/.spot-audits/w3-ui-integration-real-direct"
        if not os.path.isdir(base):
            pytest.skip("the real Direct audit bundles are not on this host")
        for c in ("Rest", "Stim8hr", "Stim48hr"):
            rep = json.load(open(os.path.join(base, f"w10_admission_{c}.json")))
            assert rep["verifier_code_sha256"] == LA.W10_VERIFIER_CODE
            assert rep["verdict"] == "ADMIT" and rep["n_failed"] == 0

    def test_ALL_W10_pin_consumers_AGREE_on_the_canonical_hash(self):
        """Every consumer of the W10 code pin, in one place.

        The pin lived in THREE places and they DISAGREED: lane_admission and
        verify_admission_rules were re-pinned to 943d…, while the SCHEDULER'S RUNTIME BINDING
        (`stage2_run`) still carried 8290… — so the same three genuine reports would have been
        admitted by the projection and REFUSED by the run. A pin that is true in one module and
        false in another is not a pin; it is a disagreement waiting to be discovered in
        production.
        """
        import verify_admission_rules as VR
        from direct import stage2_run as S2

        canonical = "943d32bd5317bbc84d2705a39f98de024f10548d1995cd6bc42ed56fb9efc174"
        stale = "8290802638898db622a8baf19f233b54b5f6f1c8434f192730aa28f829f8715f"

        consumers = {
            "lane_admission": LA.W10_VERIFIER_CODE,
            "verify_admission_rules": VR.W10_VERIFIER_CODE,
            "stage2_run": S2.W10_VERIFIER_CODE,
        }
        for name, got in consumers.items():
            assert got == canonical, f"{name} pins {got[:12]}, not the canonical {canonical[:12]}"
            assert got != stale, f"{name} still pins the PREVIOUS pre-producer-code-root hash"

    def test_the_RUN_IDENTITY_binds_the_canonical_pin_and_the_matching_head(self):
        """The head must name the SAME TREE the code hash re-derives from."""
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                "analysis", "direct", "stage2_run.py")).read()
        assert "943d32bd5317bbc84d2705a39f98de024f10548d1995cd6bc42ed56fb9efc174" in src
        assert "f6da8047a61411aa5374d6281fe6672979573af5" in src        # producer-root head
        # 2c3031e hashes to the PREVIOUS pin and must not be the bound head any more
        assert '"direct_verifier_head": "2c3031e' not in src
