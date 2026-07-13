"""Shared v3 TEMPORAL selection-contract fixtures for the Stage-1 v3 test suite.

This module builds a schema-valid, gate-valid v3 temporal selection naming the GHOST axes
(``GHOST_A -> GHOST_B``) — the fixtures ``test_cli_v3``, ``test_stage1_v3_selection_id``,
``test_preflight_v3_parity`` and ``test_v3_axis_identity`` import ``SCHEMA_PATH``,
``v3_contract`` and ``_reseal`` from here.

It ONCE also drove the flat temporal RUNNER (``run_temporal``/``verify_temporal``) to prove
the runner executed the v3 contract rather than the legacy selection. That runner was retired
in the GATE-7 cleanup, so those runner-level tests are gone; the v3-contract validation they
depended on is covered directly against ``stage1_v3`` in ``test_stage1_v3`` /
``test_stage1_v3_selection_id``. The GHOST axes and the sealed-contract builder remain here
because the rest of the v3 suite is built on them.
"""
from __future__ import annotations

import json
import os

import fixtures_stage1_contract as S1
import pytest
from direct import stage1_v3 as G
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
