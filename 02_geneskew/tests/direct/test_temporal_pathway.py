"""Fail-closed contract tests for the TEMPORAL PATHWAY enrichment lane.

The honest native fixture ADMITS first; then every attack is refused at its NAMED gate. The
lane is descriptive pathway context over the temporal DiD ranking — no new estimand, no
convergence, no p/q, no combined objective, native temporal arm keys only.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import admission, arm_keys, run_temporal_pathway, stage1_v3
from direct import temporal_pathway as tp
from direct import verify_temporal_pathway as vtp
from direct.hashing import content_hash
from fixtures_pathway import gene_set_doc

PROGRAMS = ["prog_a", "prog_b", "prog_c"]
FROM, TO = "Rest", "Stim8hr"
TARGETS = [f"ENSG{i:011d}" for i in range(1, 25)]     # 24 perturbation targets


def _ranking(program, change):
    key = arm_keys.temporal_arm_key(program, change, FROM, TO)
    sign = 1 if change == "increase" else -1
    ranked = []
    for i, t in enumerate(TARGETS):
        evaluable = i < 22                             # two declined targets
        ranked.append({
            "target_id": t,
            "arm_value": (sign * (len(TARGETS) - i)) if evaluable else None,
            "rank": (i + 1) if evaluable else None,
            "evaluable": evaluable,
            "base_key": f"{program}|{t}",
            "desired_target_modulation": "supports" if evaluable else "not_evaluable"})
    return {"schema_version": tp.INPUT_RANKING_SCHEMA, "arm_key": key, "ranked": ranked}


def _temporal_bundle_dir(tmp_path, *, programs=PROGRAMS, from_c=FROM, to_c=TO,
                         mutate_bundle=None, mutate_ranking=None, name="temporal_bundle"):
    d = os.path.join(str(tmp_path), name)
    os.makedirs(os.path.join(d, "rankings"), exist_ok=True)
    bundle = {
        "schema_version": tp.INPUT_BUNDLE_SCHEMA, "lane": tp.INPUT_LANE,
        "analysis_mode": tp.INPUT_MODE, "from_condition": from_c, "to_condition": to_c,
        "bundle_key": f"{from_c}__to__{to_c}", "bundle_id": "abc123def4567890",
        "program_admission": {"programs": list(programs)},
        "method": {"temporal_method_sha256": "t" * 64,
                   "estimator_id": "temporal_cross_condition_v1",
                   "effect_universe_sha256": "e" * 64},
        "stage1_binding": {"registry_scorer_view_sha256": "s" * 64,
                           "registry_scorer_projection_sha256": "008c1da1" + "0" * 56,
                           "release_self_sha256": "r" * 64},
        "env_lock": {"env_lock_sha256": "2983" + "0" * 60},
    }
    if mutate_bundle:
        bundle = mutate_bundle(bundle)
    with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
        json.dump(bundle, fh)
    for p in programs:
        for c in arm_keys.DESIRED_CHANGES:
            rk = _ranking(p, c)
            if mutate_ranking:
                rk = mutate_ranking(rk, p, c)
            with open(os.path.join(d, "rankings", f"{p}__{c}.json"), "w") as fh:
                json.dump(rk, fh)
    return d


def _gene_sets(tmp_path, mutate=None):
    # the run's perturbation-target universe is EVERY ranked target (all TARGETS); the gene-set
    # bundle must declare that same universe for both roles (this lane binds one universe).
    tsha = content_hash(sorted(TARGETS))
    doc = gene_set_doc(TARGETS, TARGETS[:8], effect_universe_sha256=tsha,
                       target_universe_sha256=tsha)
    if mutate:
        doc = mutate(doc)
    p = os.path.join(str(tmp_path), "genesets.json")
    with open(p, "w") as fh:
        json.dump(doc, fh)
    return p


def _emit(tmp_path, **kw):
    """Produce a temporal pathway bundle on disk; return (out_dir, bundle_dir, gene_sets)."""
    bundle_dir = _temporal_bundle_dir(tmp_path, **kw)
    gs = _gene_sets(tmp_path)
    out = os.path.join(str(tmp_path), "out")
    r = run_temporal_pathway.run(type("A", (), {
        "temporal_bundle_dir": bundle_dir, "gene_sets": gs, "out_root": out,
        "env_lock": None, "allow_dirty_tree": True})())
    return r["out_dir"], bundle_dir, gs


def _verify(out_dir, bundle_dir, gs):
    return vtp.verify(out_dir, temporal_bundle_dir=bundle_dir, gene_sets_path=gs)


# ---------------------------------------------------------------------------- #
# THE HONEST NATIVE FIXTURE ADMITS.
# ---------------------------------------------------------------------------- #
class TestHonestFixtureAdmits:
    def test_the_honest_temporal_pathway_bundle_is_ADMITTED(self, tmp_path):
        rep = _verify(*_emit(tmp_path))
        assert rep["verdict"] == vtp.ADMIT, rep["failed_gates"]
        assert rep["n_failed"] == 0

    def test_exactly_admitted_programs_times_two_arms(self, tmp_path):
        out, *_ = _emit(tmp_path)
        b = json.load(open(os.path.join(out, tp.BUNDLE_FILE)))
        assert b["n_arm_slots"] == len(PROGRAMS) * 2 == b["n_expected_arm_slots"]

    def test_every_record_key_is_the_exact_native_temporal_builder_output(self, tmp_path):
        out, *_ = _emit(tmp_path)
        b = json.load(open(os.path.join(out, tp.BUNDLE_FILE)))
        for rec in b["records"]:
            assert rec["temporal_arm_key"] == arm_keys.temporal_arm_key(
                rec["program_id"], rec["desired_change"], FROM, TO)
            assert rec["temporal_arm_key"].startswith("temporal|")
            assert "__to__" not in rec["temporal_arm_key"]   # dir naming only, never the key

    def test_no_p_q_fdr_or_combined_key_anywhere(self, tmp_path):
        out, *_ = _emit(tmp_path)
        for fname in (tp.BUNDLE_FILE, tp.PROVENANCE_FILE, tp.CONVERGENCE_FILE):
            assert admission.forbidden_keys(json.load(open(os.path.join(out, fname)))) == []

    def test_convergence_is_not_evaluable_with_no_support_or_denominator(self, tmp_path):
        out, *_ = _emit(tmp_path)
        c = json.load(open(os.path.join(out, tp.CONVERGENCE_FILE)))
        assert c["convergence_status"] == "not_evaluable_for_temporal_convergence"
        assert c["supportive_pairs"] == [] and c["denominator"] is None
        assert c["n_intra_set_pairs"] == 0 and c["n_supporting_perturbations"] == 0

    def test_the_bundle_binds_the_temporal_estimator_and_never_recomputes_it(self, tmp_path):
        out, *_ = _emit(tmp_path)
        m = json.load(open(os.path.join(out, tp.BUNDLE_FILE)))["method"]
        assert m["temporal_method_sha256"] == "t" * 64
        assert m["recomputes_temporal_estimand"] is False


# ---------------------------------------------------------------------------- #
# THE ATTACKS — each refused at its NAMED gate.
# ---------------------------------------------------------------------------- #
class TestAttacksAreRefused:
    def _fails(self, rep, gate):
        assert rep["verdict"] == vtp.REJECT
        assert gate in rep["failed_gates"], rep["failed_gates"]

    def test_ATTACK_endpoint_within_condition_bundle_as_temporal_input(self, tmp_path):
        # a within-condition/endpoint bundle declares a different schema+lane -> refused at load
        d = _temporal_bundle_dir(tmp_path, mutate_bundle=lambda b: dict(
            b, schema_version="spot.stage02_pathway_arm_bundle.v1", lane="production",
            analysis_mode="within_condition"))
        with pytest.raises(tp.TemporalPathwayError):
            tp.build_temporal_pathway(bundle_dir=d, gene_sets_path=_gene_sets(tmp_path),
                                      allow_dirty_tree=True)

    def test_ATTACK_swapped_from_to_is_refused(self, tmp_path):
        out, bundle_dir, gs = _emit(tmp_path)
        b = json.load(open(os.path.join(out, tp.BUNDLE_FILE)))
        for rec in b["records"]:                         # swap the pair on every record
            rec["from_condition"], rec["to_condition"] = TO, FROM
        b["records_sha256"] = content_hash(b["records"])
        json.dump(b, open(os.path.join(out, tp.BUNDLE_FILE), "w"))
        self._fails(_verify(out, bundle_dir, gs),
                    "every_record_key_is_the_native_temporal_key_no_reverse_swap_no_foreign_arm")

    def test_ATTACK_wrong_direction_foreign_arm_key_is_refused(self, tmp_path):
        out, bundle_dir, gs = _emit(tmp_path)
        b = json.load(open(os.path.join(out, tp.BUNDLE_FILE)))
        b["records"][0]["temporal_arm_key"] = "direct|prog_a|increase|Rest"   # not temporal
        b["records_sha256"] = content_hash(b["records"])
        json.dump(b, open(os.path.join(out, tp.BUNDLE_FILE), "w"))
        self._fails(_verify(out, bundle_dir, gs),
                    "every_record_key_is_the_native_temporal_key_no_reverse_swap_no_foreign_arm")

    def test_ATTACK_forged_ranking_bytes_are_refused(self, tmp_path):
        out, bundle_dir, gs = _emit(tmp_path)
        # tamper the shipped INPUT ranking bytes AFTER the bundle bound their hash
        rp = os.path.join(bundle_dir, "rankings", f"{PROGRAMS[0]}__increase.json")
        rk = json.load(open(rp))
        rk["ranked"][0]["arm_value"] = 999999.0
        json.dump(rk, open(rp, "w"))
        self._fails(_verify(out, bundle_dir, gs),
                    "every_bound_ranking_hash_rederives_from_the_shipped_ranking_bytes")

    def test_ATTACK_missing_temporal_estimator_identity_is_refused(self, tmp_path):
        out, bundle_dir, gs = _emit(tmp_path)
        prov = json.load(open(os.path.join(out, tp.PROVENANCE_FILE)))
        prov["run_binding"]["temporal_bundle_id"] = None
        json.dump(prov, open(os.path.join(out, tp.PROVENANCE_FILE), "w"))
        b = json.load(open(os.path.join(out, tp.BUNDLE_FILE)))
        b["method"]["temporal_method_sha256"] = None
        json.dump(b, open(os.path.join(out, tp.BUNDLE_FILE), "w"))
        self._fails(_verify(out, bundle_dir, gs), "the_temporal_estimator_identity_is_bound")

    def test_ATTACK_a_temporal_result_claiming_convergent_is_refused(self, tmp_path):
        out, bundle_dir, gs = _emit(tmp_path)
        c = json.load(open(os.path.join(out, tp.CONVERGENCE_FILE)))
        c["convergence_status"] = "convergent"
        c["supportive_pairs"] = [["ENSG00000000001", "ENSG00000000002"]]
        c["n_supporting_perturbations"] = 2
        json.dump(c, open(os.path.join(out, tp.CONVERGENCE_FILE), "w"))
        self._fails(_verify(out, bundle_dir, gs),
                    "convergence_is_not_evaluable_for_temporal_with_no_support")

    def test_ATTACK_a_combined_field_is_refused(self, tmp_path):
        out, bundle_dir, gs = _emit(tmp_path)
        b = json.load(open(os.path.join(out, tp.BUNDLE_FILE)))
        b["records"][0]["combined_objective_value"] = 0.7
        b["records_sha256"] = content_hash(b["records"])
        json.dump(b, open(os.path.join(out, tp.BUNDLE_FILE), "w"))
        self._fails(_verify(out, bundle_dir, gs),
                    "no_forbidden_p_q_fdr_or_combined_key_at_any_depth")

    def test_ATTACK_a_p_q_alias_is_refused(self, tmp_path):
        out, bundle_dir, gs = _emit(tmp_path)
        b = json.load(open(os.path.join(out, tp.BUNDLE_FILE)))
        b["records"][0]["adj_p_value"] = 0.01
        b["records_sha256"] = content_hash(b["records"])
        json.dump(b, open(os.path.join(out, tp.BUNDLE_FILE), "w"))
        self._fails(_verify(out, bundle_dir, gs),
                    "no_forbidden_p_q_fdr_or_combined_key_at_any_depth")

    def test_ATTACK_incomplete_arms_are_refused(self, tmp_path):
        out, bundle_dir, gs = _emit(tmp_path)
        b = json.load(open(os.path.join(out, tp.BUNDLE_FILE)))
        drop = b["records"][0]["temporal_arm_key"]
        b["records"] = [r for r in b["records"] if r["temporal_arm_key"] != drop]
        b["n_arm_slots"] = len(PROGRAMS) * 2 - 1
        b["records_sha256"] = content_hash(b["records"])
        json.dump(b, open(os.path.join(out, tp.BUNDLE_FILE), "w"))
        self._fails(_verify(out, bundle_dir, gs),
                    "the_arm_set_is_complete_admitted_programs_times_two")

    def test_ATTACK_forged_enrichment_value_is_refused(self, tmp_path):
        out, bundle_dir, gs = _emit(tmp_path)
        b = json.load(open(os.path.join(out, tp.BUNDLE_FILE)))
        b["records"][0]["enrichment_value"] = 42.0
        b["records_sha256"] = content_hash(b["records"])
        json.dump(b, open(os.path.join(out, tp.BUNDLE_FILE), "w"))
        self._fails(_verify(out, bundle_dir, gs),
                    "enrichment_rederives_from_the_temporal_ranking_for_every_arm_and_set")


# ---------------------------------------------------------------------------- #
# ROUTING + RELEASE (GO-BP only) + reuse.
# ---------------------------------------------------------------------------- #
class TestRoutingAndRelease:
    def test_temporal_selection_pathway_view_is_awaiting_never_within_condition(self):
        assert stage1_v3.pathway_status_for_mode(stage1_v3.MODE_TEMPORAL) \
            == "awaiting_temporal_pathway_bundle"
        assert stage1_v3.pathway_status_for_mode(stage1_v3.MODE_WITHIN) is None
        # the estimator registry surfaces the awaiting status, never a within-condition bundle
        reg = stage1_v3.estimator_registry()
        assert reg[stage1_v3.ESTIMATOR_TEMPORAL]["pathway_status"] \
            == "awaiting_temporal_pathway_bundle"

    def test_the_routing_constant_matches_the_producer_lane(self):
        assert stage1_v3.PATHWAY_AWAITING_TEMPORAL == tp.AWAITING_TEMPORAL_PATHWAY

    def test_the_release_hook_enumerates_six_GO_BP_invocations_not_twelve(self, tmp_path):
        troot = os.path.join(str(tmp_path), "temporal")
        for pair in ("Rest__to__Stim8hr", "Stim8hr__to__Rest", "Rest__to__Stim48hr",
                     "Stim48hr__to__Rest", "Stim8hr__to__Stim48hr", "Stim48hr__to__Stim8hr"):
            os.makedirs(os.path.join(troot, pair))
        plan = run_temporal_pathway.enumerate_invocations(
            temporal_output_root=troot, gene_sets_by_source={"go_bp": "gs.json"},
            out_root="out")
        assert len(plan) == 6                                  # 6 pairs x GO-BP, never 12
        assert {p["source"] for p in plan} == {"go_bp"}
        assert run_temporal_pathway.EXPECTED_INVOCATIONS == 6
        assert run_temporal_pathway.RELEASE_SOURCES == ("go_bp",)
