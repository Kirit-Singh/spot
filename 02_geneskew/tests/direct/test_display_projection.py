"""THE SERVED VIEW: a capped prefix that can be PROVEN to be the native rows.

A served view is the only artifact most readers will ever look at. If it can be wrong while
looking right, everything upstream protected bytes nobody reads and left the page unguarded.

Every value here is a FIXTURE. What is real is the refusal.
"""
from __future__ import annotations

import json
import os
import sys

from direct import display_projection as P

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
    with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
        json.dump({"schema_version": "spot.stage02_direct_arm_bundle.v1",
                   "arm_bundle_run_id": "D-1", "condition": "Stim48hr"}, fh)

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
    return root


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
