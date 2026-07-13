"""THE SERVED VIEW: a capped prefix that can be PROVEN to be the native rows.

A served view is the only artifact most readers will ever look at. If it can be wrong while
looking right, everything upstream protected bytes nobody reads and left the page unguarded.

Every value here is a FIXTURE. What is real is the refusal.
"""
from __future__ import annotations

import json
import os
import sys

import pytest
from direct import display_projection as P
from direct.hashing import file_sha256

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "analysis", "direct"))
import verify_display_projection as V  # noqa: E402

DARM = "direct|PRG-1|increase|condition=Stim48hr"
PARM = "pathway|PRG-1|increase|condition=Stim48hr"


def _release(tmp_path, n_targets=250, n_unrankable=7, n_sets=120):
    """A Direct bundle with MORE rows than the cap, plus a pathway bundle with more sets."""
    import pandas as pd

    root = str(tmp_path)
    d = os.path.join(root, "direct", "Stim48hr")
    os.makedirs(d, exist_ok=True)

    rows = []
    for i in range(n_targets):
        rows.append({"arm_key": DARM, "program_id": "PRG-1", "desired_change": "increase",
                     "condition": "Stim48hr", "target_id": f"ENSG{i:011d}",
                     # descending value, so native rank 1 is the largest
                     "value": 1.0 - i / 1000.0, "rank": i + 1, "evaluable": True})
    for j in range(n_unrankable):
        # THE ROW THAT SAYS "this arm could not score this target": null value, null rank.
        rows.append({"arm_key": DARM, "program_id": "PRG-1", "desired_change": "increase",
                     "condition": "Stim48hr", "target_id": f"UNRANKABLE{j}",
                     "value": None, "rank": None, "evaluable": False})
    pd.DataFrame(rows).to_parquet(os.path.join(d, "arms.parquet"))
    from direct.hashing import content_hash as _ch
    with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
        json.dump({"schema_version": "spot.stage02_direct_arm_bundle.v1",
                   "arm_bundle_run_id": "D-1", "condition": "Stim48hr",
                   "arm_rows_sha256": _ch(rows),
                   "arms": [{"arm_key": DARM}]}, fh, indent=2, sort_keys=True)
    _w10_report(root, "Stim48hr", d, [DARM])

    p = os.path.join(root, "pathway", "Stim48hr__GO-BP")
    os.makedirs(p, exist_ok=True)
    with open(os.path.join(p, "arm_bundle.json"), "w") as fh:
        json.dump({"schema_version": "spot.stage02_pathway_arm_bundle.v1",
                   "pathway_run_id": "P-1", "condition": "Stim48hr", "source": "GO-BP",
                   "records": [{"pathway_arm_key": PARM, "set_id": f"GO:{i:07d}",
                                "enrichment_value": 2.0 - i / 100.0,
                                "target_source_coverage": 0.75,
                                "global_coverage_disposition": (
                                    "covered" if i % 3 else "under_covered"),
                                "n_leading_edge": 3, "peak_rank": i + 1}
                               for i in range(n_sets)]}, fh)
    _pathway_admission(root)
    return root


def _w10_report(root, condition, bundle_dir, arms):
    """W10's FULL report for a Direct bundle — the display view now REQUIRES it."""
    import sys as _s
    _s.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "..", "analysis", "direct"))
    import verify_admission_rules as AR
    from direct.hashing import content_hash, file_sha256

    gates = ([f"gate {i}: an independently re-derived invariant" for i in range(104)] +
             ["every artifact's shipped hash matches the BYTES ON DISK — no file moved",
              "every arm's own bytes and counts RE-DERIVE from the shipped parquet rows",
              "every arm key re-derives from (program, desired_change, condition)"])
    with open(os.path.join(bundle_dir, "arm_bundle.json")) as fh:
        doc = json.load(fh)
    files = {n: file_sha256(os.path.join(bundle_dir, n))
             for n in sorted(os.listdir(bundle_dir))
             if os.path.isfile(os.path.join(bundle_dir, n))}
    body = {"schema_version": AR.W10_REPORT_SCHEMA, "verifier_id": AR.W10_VERIFIER_ID,
            "verifier_code_sha256": AR.W10_VERIFIER_CODE, "independent_of_generator": True,
            "gate_inventory": gates, "gate_inventory_sha256": content_hash(gates),
            "n_gates": len(gates), "n_passed": len(gates), "n_failed": 0,
            "failed_gates": [], "verdict": "ADMIT",
            "bound_artifact": {
                "arm_bundle_run_id": doc["arm_bundle_run_id"],
                "arm_rows_sha256": doc["arm_rows_sha256"],
                "condition": condition, "solver_lock_sha256": AR.SOLVER_LOCK_SHA256,
                "artifact_sha256": files, "recompute_mode": "all",
                "arm_inventory": [{"arm_key": k} for k in sorted(arms)]}}
    with open(os.path.join(root, AR.W10_REPORT_FILE.format(condition=condition)), "w") as fh:
        json.dump(dict(body, report_sha256=content_hash(body)), fh, indent=2, sort_keys=True)


def _pathway_admission(root):
    """W4's envelope + its PENDING inventory. The view is only 'rebuilt from admitted native
    bytes' once these are LOADED AND VALIDATED — finding a directory is not an admission."""
    import sys as _s
    _s.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "..", "analysis", "direct"))
    import verify_admission_rules as AR
    from direct.hashing import content_hash, file_sha256

    spec = AR.EXTERNAL["pathway"]
    body = {"schema_version": spec["inventory_schema"], "lane": "pathway",
            "n_bundles": 1, "bundles": [{"bundle_id": "P-1"}],
            "external_admission": {"status": "pending"}}
    inv = dict(body, release_id=content_hash(body))
    ip = os.path.join(root, spec["inventory"])
    with open(ip, "w") as fh:
        json.dump(inv, fh, indent=2, sort_keys=True)
    raw = file_sha256(ip)

    env = {"schema_version": spec["schema"], "verifier_id": spec["verifier_id"],
           "lane": "pathway", "generator_is_not_verifier": True, "fail_closed": True,
           "gate_inventory": list(spec["gates"]), "n_failed": 0, "verdict": "ADMIT",
           "binds": {"producer_release_id": inv["release_id"],
                     "producer_release_raw_sha256": raw, "inventory_raw_sha256": raw,
                     "stage1_release_raw_sha256": "0c336546" + "0" * 56}}
    with open(os.path.join(root, spec["file"]), "w") as fh:
        json.dump(dict(env, report_id=content_hash(env)), fh, indent=2, sort_keys=True)


def _project(root):
    out = os.path.join(root, P.PROJECTION_FILE)
    doc = P.write(root, out)
    return doc, out


class TestTheViewIsACAPPEDPREFIXAndSaysSo:
    def test_the_cap_is_FROZEN_and_METHOD_VERSIONED_never_a_UI_knob(self):
        assert P.CAP_OF == {"direct": 100, "temporal": 100, "pathway": 50}
        assert P.CAP_POLICY["configurable_from_the_ui"] is False
        assert P.CAP_POLICY["chosen_before_inspecting_any_value"] is True
        # changing the cap changes the METHOD, and therefore every projection's identity
        assert P.CAP_POLICY["method_version"] == P.METHOD_VERSION

    def test_it_serves_the_first_100_and_COUNTS_the_rest(self, tmp_path):
        root = _release(tmp_path, n_targets=250, n_unrankable=7)
        doc, _ = _project(root)
        arm = doc["arms"][DARM]

        assert arm["n_emitted"] == 100                # the cap
        assert arm["n_ranked"] == 250                 # ...out of every ranked target
        assert arm["n_evaluable"] == 250
        assert arm["n_rows_total"] == 257             # the 7 unrankable are RETAINED, counted
        assert arm["is_a_prefix"] is True             # a reader can see this is a prefix

    def test_the_served_rows_are_the_first_100_IN_NATIVE_RANK_ORDER(self, tmp_path):
        root = _release(tmp_path)
        doc, _ = _project(root)
        rows = doc["arms"][DARM]["rows"]

        assert [r["rank"] for r in rows] == list(range(1, 101))
        assert rows[0]["target_id"] == "ENSG00000000000"
        assert rows[0]["arm_value"] == 1.0            # the NATIVE effect, verbatim

    def test_an_UNRANKABLE_target_is_never_SERVED_but_is_never_LOST(self, tmp_path):
        """It is not a zero and it is not last. It is counted, and it is not evidence."""
        root = _release(tmp_path)
        doc, _ = _project(root)
        arm = doc["arms"][DARM]

        served = {r["target_id"] for r in arm["rows"]}
        assert not any(t.startswith("UNRANKABLE") for t in served)
        assert arm["n_rows_total"] - arm["n_evaluable"] == 7

    def test_NO_NaN_BYTES_reach_the_browser(self, tmp_path):
        root = _release(tmp_path)
        _, out = _project(root)
        raw = open(out).read()
        assert "NaN" not in raw and "Infinity" not in raw


class TestItIsSELECTIONINDEPENDENTAndCarriesNoCombinedOrder:
    def test_it_carries_NO_selection_and_NO_analysis_mode(self, tmp_path):
        root = _release(tmp_path)
        doc, _ = _project(root)
        assert doc["selection_independent"] is True
        assert doc["selection_id"] is None
        # analysis_mode belongs to a PER-SELECTION projection, never to the all-arm view
        assert doc["analysis_mode"] is None

    def test_it_emits_NO_combined_or_pair_ranking(self, tmp_path):
        root = _release(tmp_path)
        doc, out = _project(root)
        assert doc["combined_objective"] is None
        assert doc["cross_arm_score_or_order"] is None
        blob = open(out).read().lower()
        for banned in ("combined_score", "balanced_score", "pair_rank", "headline_rank",
                       "p_value", "q_value", "fdr"):
            assert f'"{banned}"' not in blob

    def test_the_NATIVE_artifacts_remain_the_authoritative_ones(self, tmp_path):
        root = _release(tmp_path)
        doc, _ = _project(root)
        assert doc["authoritative_artifacts_are_the_native_ones"] is True
        # ...and the view BINDS them, so a reader can go and get them
        assert doc["bindings"]["native_bundles"]["direct/Stim48hr"]["files"]["arms.parquet"]


class TestPathwayHasNoNATIVEGeneSetRankAndTheViewSaysSo:
    """The native record carries `peak_rank` (where the peak sat in the TARGET ranking) and an
    enrichment_value. It carries NO rank of gene sets against each other. Ordering them by
    enrichment_value here would make THIS MODULE the author of the headline result."""

    def test_the_pathway_rows_are_an_ORDER_and_declare_they_are_NOT_a_RANKING(self, tmp_path):
        root = _release(tmp_path, n_sets=120)
        doc, _ = _project(root)
        arm = doc["arms"][PARM]

        assert arm["rows_are_ranked"] is False
        assert arm["row_order"] == "native_producer_emission_order"
        assert "enrichment_value" in arm["why_not_ranked"]
        # ...and the prefix really is the producer's own order, not a re-sort by effect size
        assert [r["set_id"] for r in arm["rows"]] == [f"GO:{i:07d}" for i in range(50)]

    def test_the_coverage_counts_are_over_EVERY_set_not_just_the_prefix(self, tmp_path):
        root = _release(tmp_path, n_sets=120)
        doc, _ = _project(root)
        arm = doc["arms"][PARM]

        assert arm["n_sets_total"] == 120
        assert arm["n_emitted"] == 50
        assert sum(arm["coverage_disposition_counts"].values()) == 120     # ALL of them
        assert arm["n_with_coverage"] == 120


class TestTheINDEPENDENTVerifierPROVESTheRowsAreNative:
    def test_an_HONEST_projection_is_ADMITTED(self, tmp_path):
        root = _release(tmp_path)
        _, out = _project(root)
        report = V.verify(out, bundles_root=root)
        assert report["verdict"] == "admit", report["failures"]
        assert report["rebuilt_from_admitted_native_bytes"] is True

    def _forge(self, tmp_path, mutate):
        root = _release(tmp_path)
        doc, out = _project(root)
        mutate(doc)
        doc.pop("projection_sha256")
        doc["projection_sha256"] = P._canon(doc)      # RESEALED: it agrees with itself
        with open(out, "w") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
        return V.verify(out, bundles_root=root)

    def test_a_SWAPPED_ROW_at_a_valid_rank_is_REFUSED(self, tmp_path):
        """The forged row is plausible and sits at a plausible rank. It is not the native row
        at that rank, and that is the only question worth asking."""
        def mutate(doc):
            doc["arms"][DARM]["rows"][0]["target_id"] = "ENSG00000000249"   # a REAL target...
        report = self._forge(tmp_path, mutate)                              # ...at rank 1

        assert report["verdict"] == "reject"
        assert any(V.G_ROW_IS_NATIVE in f for f in report["failures"])

    def test_a_TAMPERED_EFFECT_VALUE_is_REFUSED(self, tmp_path):
        report = self._forge(tmp_path,
                             lambda d: d["arms"][DARM]["rows"][0].update({"arm_value": 9.9}))
        assert report["verdict"] == "reject"
        assert any(V.G_ROW_IS_NATIVE in f for f in report["failures"])

    def test_a_REORDERED_prefix_is_REFUSED(self, tmp_path):
        report = self._forge(tmp_path,
                             lambda d: d["arms"][DARM]["rows"].reverse())
        assert report["verdict"] == "reject"
        assert any(V.G_PREFIX in f for f in report["failures"])

    def test_a_CHERRY_PICKED_prefix_is_REFUSED(self, tmp_path):
        """Not the first 100 in native rank order — a chosen 100. That is an editorial act."""
        def mutate(doc):
            rows = doc["arms"][DARM]["rows"]
            rows[50] = {"target_id": "ENSG00000000200", "rank": 201, "arm_value": 0.8}
        report = self._forge(tmp_path, mutate)
        assert report["verdict"] == "reject"
        assert any(V.G_ROW_IS_NATIVE in f or V.G_PREFIX in f for f in report["failures"])

    def test_SERVING_AN_UNRANKABLE_TARGET_as_evidence_is_REFUSED(self, tmp_path):
        def mutate(doc):
            doc["arms"][DARM]["rows"][0] = {"target_id": "UNRANKABLE0", "rank": 1,
                                            "arm_value": 0.0}
        report = self._forge(tmp_path, mutate)
        assert report["verdict"] == "reject"
        assert any(V.G_UNRANKED_EMITTED in f or V.G_ROW_IS_NATIVE in f
                   for f in report["failures"])

    def test_a_COUNT_that_hides_the_prefix_is_REFUSED(self, tmp_path):
        """If n_ranked reads as 100, then 100 rows read as THE ANSWER."""
        report = self._forge(tmp_path,
                             lambda d: d["arms"][DARM].update({"n_ranked": 100}))
        assert report["verdict"] == "reject"
        assert any(V.G_COUNTS in f for f in report["failures"])

    def test_a_RAISED_CAP_is_REFUSED(self, tmp_path):
        report = self._forge(tmp_path,
                             lambda d: d["cap_policy"].update({"caps": {"direct": 5000}}))
        assert report["verdict"] == "reject"
        assert any(V.G_CAP in f for f in report["failures"])

    def test_a_UI_CONFIGURABLE_CAP_is_REFUSED(self, tmp_path):
        report = self._forge(
            tmp_path, lambda d: d["cap_policy"].update({"configurable_from_the_ui": True}))
        assert report["verdict"] == "reject"
        assert any("could change what a reader believes" in f for f in report["failures"])

    def test_a_SELECTION_smuggled_into_the_all_arm_view_is_REFUSED(self, tmp_path):
        report = self._forge(tmp_path,
                             lambda d: d.update({"analysis_mode": "within_condition"}))
        assert report["verdict"] == "reject"
        assert any(V.G_SELECTION in f for f in report["failures"])

    def test_a_COMBINED_RANKING_smuggled_into_the_view_is_REFUSED(self, tmp_path):
        report = self._forge(
            tmp_path, lambda d: d["arms"][DARM]["rows"][0].update({"combined_score": 1.0}))
        assert report["verdict"] == "reject"
        assert any(V.G_CROSS_ARM in f for f in report["failures"])

    def test_MUTATING_THE_NATIVE_BYTES_after_the_view_was_built_is_REFUSED(self, tmp_path):
        import pandas as pd
        root = _release(tmp_path)
        _, out = _project(root)
        # somebody edits the authoritative artifact afterwards
        d = os.path.join(root, "direct", "Stim48hr")
        df = pd.read_parquet(os.path.join(d, "arms.parquet"))
        df.loc[0, "value"] = -99.0
        df.to_parquet(os.path.join(d, "arms.parquet"))

        report = V.verify(out, bundles_root=root)
        assert report["verdict"] == "reject"
        assert any(V.G_SOURCE_BYTES in f for f in report["failures"])

    def test_a_FORGED_pathway_row_is_REFUSED(self, tmp_path):
        report = self._forge(
            tmp_path,
            lambda d: d["arms"][PARM]["rows"][0].update({"enrichment_value": 99.0}))
        assert report["verdict"] == "reject"
        assert any(V.G_ROW_IS_NATIVE in f for f in report["failures"])

    def test_a_pathway_view_CLAIMING_ITS_ROWS_ARE_RANKED_is_REFUSED(self, tmp_path):
        report = self._forge(tmp_path,
                             lambda d: d["arms"][PARM].update({"rows_are_ranked": True}))
        assert report["verdict"] == "reject"
        assert any(V.G_PREFIX in f for f in report["failures"])


class TestTheCapsAgreeAcrossTheSeam:
    def test_the_verifier_RESTATES_the_cap_and_has_not_DRIFTED(self):
        """It restates rather than imports: a verifier that reads the producer's cap agrees
        with it by construction and could never catch it moving."""
        assert V.CAP_OF == P.CAP_OF
        assert V.CAP_POLICY_ID == P.CAP_POLICY_ID
        assert V.METHOD_VERSION == P.METHOD_VERSION


# --------------------------------------------------------------------------- #
# THE RECEIPT MUST NAME THE PROJECTION IT JUDGED.
#
# It carried a verifier id, booleans, n_arms, failures and a verdict — and NOTHING that
# identified the bytes. So a UI could take an ALTERED projection (one arm_value
# 1.6758342617 -> 125.1318342617, declared projection_sha256 left alone) and pair it with the
# ORIGINAL receipt, and both parsed: the only thing tying them together was n_arms, which the
# mutation does not change. A verdict about bytes nobody named is not a verdict about these
# bytes.
# --------------------------------------------------------------------------- #
class TestTheRECEIPTBindsTheEXACTProjection:
    def _receipt(self, root, out):
        return V.verify(out, bundles_root=root)

    def test_the_receipt_BINDS_raw_canonical_and_self_hashes(self, tmp_path):
        root = _release(tmp_path)
        _, out = _project(root)
        rec = self._receipt(root, out)
        subj = rec["subject"]

        import hashlib
        assert subj["projection_raw_sha256"] == hashlib.sha256(
            open(out, "rb").read()).hexdigest()
        assert subj["projection_canonical_sha256"]
        assert subj["projection_self_sha256_declared"] == \
            subj["projection_self_sha256_recomputed"]
        assert subj["self_hash_agrees"] is True
        assert subj["projection_file"] == P.PROJECTION_FILE      # a NAME, not a path

    def test_THE_UI_MUTATION_an_altered_arm_value_with_the_ORIGINAL_receipt_is_CAUGHT(
            self, tmp_path):
        """THE REPRODUCED DEFECT. Alter one arm_value, keep the declared projection_sha256,
        keep the original receipt. n_arms is unchanged — and that was the only binding."""
        root = _release(tmp_path)
        doc, out = _project(root)
        original = self._receipt(root, out)
        assert original["verdict"] == "admit"

        # THE EXACT CHANGE: edit the arm_value THAT EXISTS. (An earlier version of this test
        # set `["value"]`, which ADDS a field the row does not have — that is a different
        # mutation, caught by a different gate, and it did not reproduce the defect at all.)
        row = doc["arms"][DARM]["rows"][0]
        assert "arm_value" in row and "value" not in row
        before = row["arm_value"]
        row["arm_value"] = 125.1318342617                        # SAME SHAPE, new number
        # v2 rows also carry target_symbol (display metadata). The mutation adds and removes
        # nothing — it is the same shape, one different number.
        assert set(row) == {"target_id", "target_symbol", "rank", "arm_value"}
        with open(out, "w") as fh:                               # declared hash left ALONE
            json.dump(doc, fh, indent=2, sort_keys=True)
        assert doc["arms"][DARM]["rows"][0]["arm_value"] != before

        # THE UI'S CHECK: the original receipt's SUBJECT HASH no longer names these bytes.
        import hashlib
        now = hashlib.sha256(open(out, "rb").read()).hexdigest()
        assert original["subject"]["projection_raw_sha256"] != now
        assert original["n_arms"] == len(doc["arms"])            # n_arms is UNCHANGED —
        #                                                          it was the ONLY binding

        # ...and re-verifying the altered file refuses outright
        rep = self._receipt(root, out)
        assert rep["verdict"] == "reject"
        assert any(V.G_SELF_HASH in f or V.G_ROW_IS_NATIVE in f for f in rep["failures"])
        # the FRESH receipt names the NEW bytes, so a UI can always tell the two apart
        assert rep["subject"]["projection_raw_sha256"] == now

    def test_a_SWAPPED_receipt_from_another_projection_does_not_name_these_bytes(self,
                                                                                 tmp_path):
        root_a = _release(tmp_path / "a")
        _, out_a = _project(root_a)
        rec_a = self._receipt(root_a, out_a)

        root_b = _release(tmp_path / "b", n_targets=200)          # a DIFFERENT release
        _, out_b = _project(root_b)
        rec_b = self._receipt(root_b, out_b)

        assert rec_a["subject"]["projection_raw_sha256"] != \
            rec_b["subject"]["projection_raw_sha256"]
        # a UI holding receipt A and projection B can SEE they do not match
        import hashlib
        assert rec_a["subject"]["projection_raw_sha256"] != hashlib.sha256(
            open(out_b, "rb").read()).hexdigest()

    def test_a_STALE_receipt_over_re_projected_bytes_does_not_match(self, tmp_path):
        import pandas as pd
        root = _release(tmp_path)
        _, out = _project(root)
        stale = self._receipt(root, out)

        d = os.path.join(root, "direct", "Stim48hr")
        df = pd.read_parquet(os.path.join(d, "arms.parquet"))
        df.loc[0, "value"] = 0.999
        df.to_parquet(os.path.join(d, "arms.parquet"))
        _, out2 = _project(root)                                  # re-projected

        fresh = self._receipt(root, out2)
        assert stale["subject"]["projection_raw_sha256"] != \
            fresh["subject"]["projection_raw_sha256"]


class TestREBUILTFromAdmittedIsEARNEDNotDeclared:
    def test_it_binds_the_ADMITTED_LANE_INPUTS(self, tmp_path):
        root = _release(tmp_path)
        _, out = _project(root)
        rec = V.verify(out, bundles_root=root)

        assert rec["rebuilt_from_admitted_native_bytes"] is True
        # EVERY source lane, not just one: Direct's W10 report AND pathway's W4 envelope.
        pw = rec["admitted_inputs"]["pathway"]
        assert pw["report_id"] and pw["bound_inventory_sha256"]
        assert pw["n_gates"] == 12                               # W4's exact inventory

        dr = rec["admitted_inputs"]["direct:Stim48hr"]
        assert dr["recompute_mode"] == "all"
        assert dr["n_gates"] >= 50 and dr["n_arms_verified"] == 1

    def test_a_MISSING_lane_admission_makes_it_FALSE_and_REFUSES(self, tmp_path):
        """It used to be a hard-coded True: it meant 'a directory was found'."""
        root = _release(tmp_path)
        _, out = _project(root)
        os.remove(os.path.join(root, "pathway_arm_external_admission.json"))

        rec = V.verify(out, bundles_root=root)
        assert rec["rebuilt_from_admitted_native_bytes"] is False
        assert rec["verdict"] == "reject"
        assert any(V.G_ADMITTED_INPUTS in f for f in rec["failures"])

    def test_an_admission_binding_ANOTHER_inventory_is_REFUSED(self, tmp_path):
        from direct.hashing import content_hash
        root = _release(tmp_path)
        _, out = _project(root)
        p = os.path.join(root, "pathway_arm_external_admission.json")
        rep = json.load(open(p))
        rep["binds"]["producer_release_raw_sha256"] = "dead" + "0" * 60
        rep["report_id"] = content_hash({k: v for k, v in rep.items() if k != "report_id"})
        with open(p, "w") as fh:
            json.dump(rep, fh)

        rec = V.verify(out, bundles_root=root)
        assert rec["rebuilt_from_admitted_native_bytes"] is False
        assert rec["verdict"] == "reject"
        assert any(V.G_ADMITTED_INPUTS in f for f in rec["failures"])


class TestEVERYSourceLaneMustBeAdmitted:
    """A MIXED projection may not lean on one lane's admission for another lane's rows."""

    def test_a_MISSING_DIRECT_admission_REFUSES_even_though_pathway_is_admitted(self,
                                                                                tmp_path):
        """Skipping past Direct meant a mixed view could claim
        `rebuilt_from_admitted_native_bytes` on the TEMPORAL/PATHWAY admission alone, while its
        Direct rows rested on nothing."""
        import verify_admission_rules as AR
        root = _release(tmp_path)
        _, out = _project(root)
        assert V.verify(out, bundles_root=root)["verdict"] == "admit"

        os.remove(os.path.join(root, AR.W10_REPORT_FILE.format(condition="Stim48hr")))
        rec = V.verify(out, bundles_root=root)

        assert rec["rebuilt_from_admitted_native_bytes"] is False
        assert rec["verdict"] == "reject"
        assert any(V.G_ADMITTED_INPUTS in f and "direct" in f for f in rec["failures"])
        # ...and the PATHWAY admission is still fine — it just cannot cover Direct
        assert "pathway" in rec["admitted_inputs"]

    def test_a_FORGED_DIRECT_report_REFUSES(self, tmp_path):
        import verify_admission_rules as AR
        root = _release(tmp_path)
        _, out = _project(root)
        p = os.path.join(root, AR.W10_REPORT_FILE.format(condition="Stim48hr"))
        with open(p, "w") as fh:
            fh.write('{"verdict":"ADMIT"}')

        rec = V.verify(out, bundles_root=root)
        assert rec["rebuilt_from_admitted_native_bytes"] is False
        assert rec["verdict"] == "reject"

    def test_EVERY_source_lane_appears_in_admitted_inputs(self, tmp_path):
        root = _release(tmp_path)
        doc, out = _project(root)
        rec = V.verify(out, bundles_root=root)

        lanes = {b["lane"] for b in doc["bindings"]["native_bundles"].values()}
        assert lanes == {"direct", "pathway"}
        keys = set(rec["admitted_inputs"])
        assert "pathway" in keys
        assert any(k.startswith("direct:") for k in keys)


# --------------------------------------------------------------------------- #
# THE SYMBOL IS DISPLAY METADATA — looked up in a frozen, bound artifact, never guessed.
# --------------------------------------------------------------------------- #
CROSSWALK = "effect_universe_gwcd4i.json"


def _crosswalk(root, forward=None):
    """The frozen Stage-1 artifact: symbol -> ensembl."""
    doc = {"symbol_to_ensembl": forward if forward is not None else {
               "POGLUT3": "ENSG00000000000", "SEC61B": "ENSG00000000001",
               "MED12": "ENSG00000000002"},
           "provenance": {"dataset": "GWCD4i", "role": "effect_universe",
                          "host_path": "/should/never/be/serialized"}}
    p = os.path.join(root, CROSSWALK)
    with open(p, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
    return p


_NO_CW = object()


def _project_cw(root, cw=_NO_CW):
    """cw=None means NO crosswalk at all (the unlabelled control)."""
    out = os.path.join(root, P.PROJECTION_FILE)
    path = os.path.join(root, CROSSWALK) if cw is _NO_CW else (cw or "")
    doc = P.write(root, out, crosswalk_path=path)
    return doc, out


class TestTheSymbolIsLookedUpNeverGuessed:
    def test_every_mapped_row_carries_the_EXACT_symbol(self, tmp_path):
        root = _release(tmp_path)
        _crosswalk(root)
        doc, _ = _project_cw(root)
        rows = {r["target_id"]: r["target_symbol"] for r in doc["arms"][DARM]["rows"]}
        assert rows["ENSG00000000000"] == "POGLUT3"
        assert rows["ENSG00000000002"] == "MED12"

    def test_an_UNMAPPED_target_is_an_EXPLICIT_NULL_not_its_own_id(self, tmp_path):
        """An ENSG printed where a reader expects a gene name is a lie a plot tells quietly."""
        root = _release(tmp_path)
        _crosswalk(root)
        doc, _ = _project_cw(root)
        unmapped = [r for r in doc["arms"][DARM]["rows"]
                    if r["target_id"] not in ("ENSG00000000000", "ENSG00000000001",
                                              "ENSG00000000002")]
        assert unmapped, "the fixture must contain targets the crosswalk does not cover"
        for r in unmapped:
            assert r["target_symbol"] is None
            assert r["target_symbol"] != r["target_id"]

    def test_an_AMBIGUOUS_inversion_is_DROPPED_not_picked(self, tmp_path):
        """Two symbols naming one id: that id has no single public label."""
        root = _release(tmp_path)
        _crosswalk(root, forward={"AAA": "ENSG00000000000", "BBB": "ENSG00000000000",
                                  "SEC61B": "ENSG00000000001"})
        doc, _ = _project_cw(root)
        rows = {r["target_id"]: r["target_symbol"] for r in doc["arms"][DARM]["rows"]}
        assert rows["ENSG00000000000"] is None          # the collision is UNLABELLED
        assert rows["ENSG00000000001"] == "SEC61B"
        b = doc["bindings"]["symbol_crosswalk"]
        assert b["n_ambiguous_dropped"] == 1
        assert b["n_one_to_one"] == 1

    def test_the_crosswalk_is_BOUND_by_raw_AND_canonical_hash(self, tmp_path):
        root = _release(tmp_path)
        p = _crosswalk(root)
        doc, _ = _project_cw(root)
        b = doc["bindings"]["symbol_crosswalk"]
        assert b["raw_sha256"] == file_sha256(p)
        assert b["canonical_sha256"]
        assert b["crosswalk_id"] == "spot.stage01.effect_universe_gwcd4i.symbol_to_ensembl.v1"
        assert b["symbol_namespace"] == "hgnc_symbol"
        assert b["coverage_universe"] == "de_readout"
        # NO HOST PATH is serialized — a binding that carried it would bind a machine
        assert "host_path" not in json.dumps(b)
        assert b["path"] == CROSSWALK                    # a NAME, not a path

    def test_the_VALUES_RANKS_and_PREFIX_are_UNCHANGED_by_labelling(self, tmp_path):
        """A label is not a result. v1 and v2 must be byte-identical in the science."""
        root = _release(tmp_path)
        plain, _ = _project_cw(root, cw=None)             # NO crosswalk at all
        _crosswalk(root)
        labelled, _ = _project_cw(root)

        a, b = plain["arms"][DARM], labelled["arms"][DARM]
        assert a["n_emitted"] == b["n_emitted"] == 100
        assert a["n_ranked"] == b["n_ranked"]
        assert a["cap"] == b["cap"]
        for ra, rb in zip(a["rows"], b["rows"]):
            assert ra["target_id"] == rb["target_id"]
            assert ra["rank"] == rb["rank"]
            assert ra["arm_value"] == rb["arm_value"]    # the SCIENCE is untouched

    def test_TEMPORAL_rows_get_symbols_too(self, tmp_path):
        root = str(tmp_path)
        os.makedirs(root, exist_ok=True)
        _crosswalk(root)
        # a temporal bundle whose targets are in the crosswalk
        d = os.path.join(root, "temporal", "Rest__to__Stim48hr")
        os.makedirs(os.path.join(d, "rankings"), exist_ok=True)
        key = "temporal|p|increase|Rest|Stim48hr"
        with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
            json.dump({"schema_version": "spot.stage02_temporal_arm_bundle.v1",
                       "bundle_id": "T-1", "lane": "temporal",
                       "context": {"from_condition": "Rest", "to_condition": "Stim48hr"}}, fh)
        with open(os.path.join(d, "rankings", "a.json"), "w") as fh:
            json.dump({"arm_key": key, "records": [
                {"target_id": "ENSG00000000000", "arm_value": 1.0, "rank": 1,
                 "evaluable": True}]}, fh)
        doc = P.project(root, crosswalk_path=os.path.join(root, CROSSWALK))
        assert doc["arms"][key]["rows"][0]["target_symbol"] == "POGLUT3"


class TestTheVerifierPROVESEverySymbol:
    def _forge(self, tmp_path, mutate):
        root = _release(tmp_path)
        _crosswalk(root)
        doc, out = _project_cw(root)
        mutate(doc, root)
        doc.pop("projection_sha256")
        doc["projection_sha256"] = P._canon(doc)
        with open(out, "w") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
        return V.verify(out, bundles_root=root)

    def test_an_HONEST_labelled_projection_is_ADMITTED(self, tmp_path):
        root = _release(tmp_path)
        _crosswalk(root)
        _, out = _project_cw(root)
        rep = V.verify(out, bundles_root=root)
        assert rep["verdict"] == "admit", rep["failures"]

    def test_a_SWAPPED_symbol_is_REFUSED(self, tmp_path):
        rep = self._forge(
            tmp_path,
            lambda d, r: d["arms"][DARM]["rows"][0].update({"target_symbol": "MED12"}))
        assert rep["verdict"] == "reject"
        assert any(V.G_SYMBOL in f for f in rep["failures"])

    def test_LABELLING_an_UNMAPPED_target_is_REFUSED(self, tmp_path):
        def mutate(d, r):
            row = next(x for x in d["arms"][DARM]["rows"] if x["target_symbol"] is None)
            row["target_symbol"] = "PLAUSIBLE1"
        rep = self._forge(tmp_path, mutate)
        assert rep["verdict"] == "reject"
        assert any("EXPLICIT null" in f for f in rep["failures"])

    def test_a_STALE_CROSSWALK_on_disk_is_REFUSED(self, tmp_path):
        """The projection was labelled from different bytes than the ones now bound."""
        def mutate(d, r):
            _crosswalk(r, forward={"WRONG": "ENSG00000000000"})   # the file changes
        rep = self._forge(tmp_path, mutate)
        assert rep["verdict"] == "reject"
        assert any(V.G_CROSSWALK in f for f in rep["failures"])

    def test_a_MUTATED_crosswalk_HASH_is_REFUSED(self, tmp_path):
        rep = self._forge(
            tmp_path,
            lambda d, r: d["bindings"]["symbol_crosswalk"].update(
                {"raw_sha256": "dead" + "0" * 60}))
        assert rep["verdict"] == "reject"
        assert any(V.G_CROSSWALK in f for f in rep["failures"])

    def test_a_symbol_with_NO_CROSSWALK_BOUND_is_REFUSED(self, tmp_path):
        """Silence is not permission."""
        rep = self._forge(
            tmp_path,
            lambda d, r: d["bindings"].update({"symbol_crosswalk": None}))
        assert rep["verdict"] == "reject"
        assert any(V.G_CROSSWALK in f for f in rep["failures"])

    def test_a_FORGED_ambiguity_count_is_REFUSED(self, tmp_path):
        rep = self._forge(
            tmp_path,
            lambda d, r: d["bindings"]["symbol_crosswalk"].update(
                {"n_ambiguous_dropped": 99}))
        assert rep["verdict"] == "reject"
        assert any(V.G_AMBIGUOUS in f for f in rep["failures"])

    @pytest.mark.parametrize("field", ["p_value", "q_value", "fdr", "se", "std_error",
                                       "significance"])
    def test_NO_inferential_or_precision_field_may_reach_a_ROW(self, tmp_path, field):
        """A standard error would be a new statistic, and a plot showing one would assert a
        precision nobody computed."""
        rep = self._forge(
            tmp_path,
            lambda d, r, f=field: d["arms"][DARM]["rows"][0].update({f: 0.01}))
        assert rep["verdict"] == "reject"
        assert any(V.G_UNKNOWN_ROW_FIELD in f or V.G_CROSS_ARM in f for f in rep["failures"])
