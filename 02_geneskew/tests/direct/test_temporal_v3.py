"""B3 — a v3 temporal request must EXECUTE the contract it was given.

THE ATTACK (from the targeted re-audit). A valid v3 request naming
``GHOST_A -> GHOST_B``, ``Stim48hr -> Rest`` came back:

    v3_requested_programs  GHOST_A GHOST_B
    emitted_programs       ['diff_naive'] ['th17_like']      <- the LEGACY axes
    requested_order        ['Stim48hr','Rest']
    emitted_pairs          [('Rest','Stim48hr'),('Stim48hr','Rest')]   <- BOTH directions
    run_binding.selection  fx_...  analysis_condition='Rest'  <- the LEGACY selection
    contains_v3_full_hash  False
    verdict                admit

The runner pulled the CONDITIONS out of the v3 contract and executed everything else from
the legacy ``args.selection``: legacy poles, legacy axis, sorted-away direction, both
directions emitted, legacy identity bound. It answered a different question and admitted.

The fixture below makes that visible: the registry ships FOUR programs. The legacy
contract names ``diff_naive``/``th17_like``; the v3 contract names ``GHOST_A``/``GHOST_B``
with DIFFERENT panels. If the run executes the legacy axes, the emitted programs and the
arm values both say so.
"""
from __future__ import annotations

import json
import os

import fixtures_stage1_contract as S1
import pytest
from direct import stage1_v3 as G
from direct.temporal import run_temporal, verify_temporal
from fixtures_spec import A_PANEL, B_PANEL, CONTROLS
from fixtures_temporal import (
    PROGRAM_A,
    PROGRAM_B,
    REST,
    STIM48,
    TEMPORAL_CONDITIONS,
    temporal_specs,
)

# The AUTHORITATIVE schema, from git at the pinned Stage-1 commit — not from a host path
# that happened to hold the STALE pre-repair schema. See fixtures_stage1_contract.
SCHEMA_PATH = S1.schema_path()
SHA = "a" * 64

# The GHOST axes: programs the registry ships and the LEGACY contract never names.
# Their panels are SWAPPED relative to the legacy pair, so an arm value scored on the
# wrong axis is not merely mislabelled — it is a different number.
GHOST_A = "GHOST_A"
GHOST_B = "GHOST_B"
GHOST_PROGRAMS = [
    {"program_id": GHOST_A, "display_label": "Ghost A",
     "panel_ensembl": B_PANEL, "control_ensembl": CONTROLS,
     "stage2_selectable": True, "primary": True, "base_portable": True},
    {"program_id": GHOST_B, "display_label": "Ghost B",
     "panel_ensembl": A_PANEL, "control_ensembl": CONTROLS,
     "stage2_selectable": True, "primary": True, "base_portable": True},
]

TRUST_KEYS = ("validation_raw_sha256", "validation_semantics_raw_sha256",
              "validation_semantics_self_canonical_sha256", "gate_spec_raw_sha256",
              "constituent_main_content_canonical_sha256",
              "constituent_overlay_donor_content_canonical_sha256",
              "marker_diagnostics_content_sha256", "scoring_view_raw_sha256",
              "scoring_view_canonical_sha256")


def _reseal(doc, derive_id=True):
    """Seal the contract the way an HONEST producer does.

    The selection_id DERIVES from canonical_content (m2), so it is computed here before
    the full-contract hash is taken over the finished document. ``derive_id=False`` leaves
    a caller-supplied id in place — that is the forgery path, and the gate refuses it.
    """
    from direct.hashing import content_hash
    if derive_id:
        doc["selection_id"] = G.derive_selection_id(doc)
    payload = {k: v for k, v in doc.items() if k != "full_contract_content_sha256"}
    doc["full_contract_content_sha256"] = content_hash(payload)
    return doc


def v3_contract(a=GHOST_A, b=GHOST_B, conditions=(STIM48, REST),
                mode=G.MODE_TEMPORAL, **over):
    """A schema-valid, gate-valid v3 temporal selection naming the GHOST axes."""
    def pole(program, direction):
        return {"program_id": program, "direction": direction,
                "effect_projection_status": G.PROJECTION_AVAILABLE,
                "n_measured": 120, "n_panel_in_effect_universe": 30,
                "n_control_in_effect_universe": 40, "reason_codes": []}

    doc = {
        "schema_version": G.SCHEMA_ID,
        "selection_origin": "fixture",
        "execution_status": G.EXECUTION_READY,
        "analysis_mode": mode,
        "estimator_id": G.ESTIMATOR_FOR_MODE[mode],
        "estimator_status": G.ESTIMATOR_AVAILABLE,
        "selection_id": "0123456789abcdef",
        "selection_full_sha256": SHA,
        "canonical_content": {
            "A": {"program_id": a, "score_field": f"{a}_score", "direction": "high"},
            "B": {"program_id": b, "score_field": f"{b}_score", "direction": "high"},
            "analysis_mode": mode,
            "combined_objective": None,
            "poles_separate": True,
            "conditions": list(conditions),
            "dataset_id": "ds1", "donor_scope": "all_donor", "effect_universe_id": "eu1",
            "registry_scorer_view_sha256": SHA, "source_h5ad_sha256": SHA,
            "source_hf_revision": "rev1",
            "stage1_method_version": G.STAGE1_METHOD_VERSION,
        },
        "poles": {"A": pole(a, "high"), "B": pole(b, "high")},
        "trust_bindings": {k: SHA for k in TRUST_KEYS},
        "provenance_bindings": {"primary_registry_v3_raw_sha256": SHA},
        "historical_validation_provenance": {
            "kind": "frozen_lomo_within_condition_validation_v3",
            "selectability_v3_raw_sha256": SHA, "active_gate": False},
    }
    doc.update(over)
    # question_id / arms / estimator: required by the f810 schema. The question_id is built
    # by an INDEPENDENT implementation of Stage-1's recipe, never by the gate under test.
    S1.complete(doc)
    return _reseal(doc)


@pytest.fixture
def ghost_run(synthetic_run, tmp_path):
    """A run whose LEGACY contract names diff_naive/th17_like and whose V3 contract names
    GHOST_A/GHOST_B. Whichever axis comes out is the one that actually executed."""
    def _build(contract=None, **kw):
        args = synthetic_run(
            temporal_specs(), conditions=TEMPORAL_CONDITIONS,
            program_ids=(PROGRAM_A, PROGRAM_B), program_prefix="",
            analysis_condition=REST,                    # the LEGACY condition
            extra_programs=GHOST_PROGRAMS, **kw)
        path = os.path.join(os.path.dirname(args.de_main), "v3_selection.json")
        with open(path, "w") as fh:
            json.dump(contract if contract is not None else v3_contract(), fh)
        args.stage1_v3_selection = path
        args.stage1_v3_schema = SCHEMA_PATH
        return args
    return _build


@pytest.fixture
def built(ghost_run):
    args = ghost_run()
    res = run_temporal.build_temporal(args)
    import pandas as pd
    df = pd.read_parquet(os.path.join(res["out_dir"], "temporal.parquet"))
    with open(os.path.join(res["out_dir"], "temporal_provenance.json")) as fh:
        prov = json.load(fh)
    return res, df, prov


pytestmark = pytest.mark.skipif(
    not os.path.exists(SCHEMA_PATH), reason="the pinned v3 schema is not present")


class TestTheGhostAttack:
    """The report's exact request: GHOST_A -> GHOST_B, Stim48hr -> Rest."""

    def test_it_executes_the_V3_axes_not_the_legacy_ones(self, built):
        _, df, _ = built
        assert sorted(df["A_program_id"].unique()) == [GHOST_A]
        assert sorted(df["B_program_id"].unique()) == [GHOST_B]
        # the legacy programs are nowhere in the emitted artifact
        assert PROGRAM_A not in set(df["A_program_id"]) | set(df["B_program_id"])
        assert PROGRAM_B not in set(df["A_program_id"]) | set(df["B_program_id"])

    def test_it_emits_ONLY_the_requested_direction(self, built):
        _, df, _ = built
        pairs = set(zip(df["from_condition"], df["to_condition"]))
        assert pairs == {(STIM48, REST)}
        # the reverse direction is NOT emitted: nobody asked for it
        assert (REST, STIM48) not in pairs

    def test_the_run_binding_carries_the_V3_FULL_CONTRACT_HASH(self, built):
        _, _, prov = built
        v3 = prov["run_binding"]["stage1_v3"]
        assert v3 is not None
        assert len(v3["full_contract_content_sha256"]) == 64
        # ...and that it RE-DERIVES from the contract's own content is the next test

    def test_the_bound_hash_RE_DERIVES_from_the_contract_content(self, ghost_run):
        args = ghost_run()
        with open(args.stage1_v3_selection) as fh:
            doc = json.load(fh)
        expect = G.reverify_full_contract_hash(doc)

        res = run_temporal.build_temporal(args)
        with open(os.path.join(res["out_dir"], "temporal_provenance.json")) as fh:
            prov = json.load(fh)
        assert prov["run_binding"]["stage1_v3"][
            "full_contract_content_sha256"] == expect

    def test_the_binding_names_the_requested_order_and_the_requested_poles(self, built):
        _, _, prov = built
        v3 = prov["run_binding"]["stage1_v3"]
        assert v3["from_condition"] == STIM48
        assert v3["to_condition"] == REST
        assert v3["poles"]["A"]["program_id"] == GHOST_A
        assert v3["poles"]["B"]["program_id"] == GHOST_B
        assert v3["analysis_mode"] == G.MODE_TEMPORAL
        assert prov["run_binding"]["analysis_mode"] == G.MODE_TEMPORAL

    def test_the_artifact_still_ADMITS(self, built):
        res, _, _ = built
        assert res["verification"]["verdict"] == verify_temporal.ADMIT
        assert res["n_comparisons"] == 1

    def test_the_arm_values_are_scored_on_the_GHOST_panels(self, built):
        # GHOST_A's panel is the LEGACY B panel and vice versa, so an arm value computed
        # on the wrong axis is a different NUMBER, not just a different label. The
        # B_MOVER target moves on the legacy B panel; under GHOST_A (= that panel) the
        # movement must appear on the AWAY arm instead.
        _, df, _ = built
        from fixtures_temporal import B_MOVER
        r = df[df.target_id == B_MOVER].iloc[0]
        # Stim48hr -> Rest on the GHOST_A arm (legacy B panel): b went 0.2 -> 1.4 by 48h,
        # so from(Stim48)=1.4, to(Rest)=0.2 under sign_A=+1 => away = -delta => the DiD is
        # non-zero and reverses the legacy sign convention.
        assert r["away_from_A_temporal_did"] != 0.0


class TestTheContractIsObeyedWholly:
    def test_an_explicit_conditions_override_beside_a_v3_contract_is_REFUSED(
            self, ghost_run):
        args = ghost_run()
        with pytest.raises(ValueError, match="already names the comparison"):
            run_temporal.build_temporal(args, conditions=[REST, STIM48])

    def test_a_WITHIN_condition_v3_contract_is_refused_by_the_temporal_runner(
            self, ghost_run):
        args = ghost_run(contract=v3_contract(mode=G.MODE_WITHIN, conditions=(REST,)))
        with pytest.raises(G.SelectionV3Error) as exc:
            run_temporal.build_temporal(args)
        assert exc.value.reason == G.REFUSE_MODE_ROUTE

    def test_a_v3_contract_naming_a_program_the_registry_lacks_is_REFUSED(self,
                                                                          ghost_run):
        from direct.selection import SelectionError
        args = ghost_run(contract=v3_contract(a="NOT_IN_THE_REGISTRY"))
        with pytest.raises(SelectionError, match="not in the bound Stage-1 registry"):
            run_temporal.build_temporal(args)

    def test_a_v3_contract_without_its_pinned_schema_is_REFUSED(self, ghost_run):
        args = ghost_run()
        args.stage1_v3_schema = None
        with pytest.raises(ValueError, match="PINNED schema"):
            run_temporal.build_temporal(args)

    def test_a_tampered_contract_hash_is_REFUSED(self, ghost_run):
        doc = v3_contract()
        doc["canonical_content"]["conditions"] = [REST, STIM48]   # flip, do NOT reseal
        args = ghost_run(contract=doc)
        with pytest.raises(G.SelectionV3Error):
            run_temporal.build_temporal(args)


class TestTheLegacyPathStillWorks:
    def test_without_a_v3_contract_every_ordered_pair_is_still_computed(self,
                                                                        temporal_run):
        res = run_temporal.build_temporal(temporal_run())
        assert res["n_comparisons"] == 6
        assert res["verification"]["verdict"] == verify_temporal.ADMIT
