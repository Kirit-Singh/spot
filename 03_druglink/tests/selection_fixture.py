"""Sealed Stage-1 v3 SELECTION contracts, in STAGE-1's OWN emitted shape.

GENERIC — the biology is a parameter, never a constant. There is no Treg here, no Th1 and no
Stim48hr: every contract is built from programs and conditions the CALLER passes in (in practice,
whatever the admitted release happens to hold), so a test that passed only for one favoured pair
could not be written with this fixture even by accident.

THE SHAPE IS STAGE-1's, NOT ONE STAGE 3 INVENTED
------------------------------------------------
Transcribed from ``01_programs/analysis/stage2_bridge/emit_selection_contract.py`` at
``539431d`` — including the fields a reconstruction would quietly leave out and thereby fail to
test: ``score_field`` inside each pole of ``canonical_content``, the ``question_id``, the
``selection_full_sha256``, and Stage-1's OWN ``arms`` block carrying the arm keys it believes the
question names. Stage 3 re-derives those keys independently and refuses a disagreement, so the
block has to be here or that gate is never exercised.

``test_selection_view`` additionally pins this fixture's derivations against STAGE-1's REAL
BYTES (``stage01_selection_temporal_ready_example.json``: ``question_id 3203d63970720d4f``,
``selection_id 7a77f6b314b9c0f3``). A fixture checked only against itself proves only that its
author agreed with themselves.

THE IDENTITIES
--------------
    selection_id = sha256(canonical_json(canonical_content))[:16]              method/input-bound
    question_id  = sha256(canonical_json({A:{program_id,direction,condition:conditions[0]},
                                          B:{program_id,direction,condition:conditions[-1]},
                                          analysis_mode}))[:16]                biology-only
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from druglink.stage2_contract import stage2_content_sha256

SCHEMA = "spot.stage01_selection.v3"
STAGE1_METHOD_VERSION = "stage1-continuous-v3.0.1"

# Stage-1's frozen role x pole -> desired_change map, restated so the fixture can emit the `arms`
# block Stage-1 emits — and therefore so Stage-3's cross-check has something to disagree with.
DESIRED_CHANGE = {("away_from_A", "high"): "decrease", ("away_from_A", "low"): "increase",
                  ("toward_B", "high"): "increase", ("toward_B", "low"): "decrease"}


def canonical_content(*, a_program: str, a_direction: str, b_program: str, b_direction: str,
                      analysis_mode: str, conditions: Sequence[str],
                      registry_view_sha256: str) -> dict[str, Any]:
    """The SCIENTIFIC content only — no timestamps, no labels, no paths. Stage-1's exact keys."""
    return {
        "A": {"program_id": a_program, "score_field": f"{a_program}_score",
              "direction": a_direction},
        "B": {"program_id": b_program, "score_field": f"{b_program}_score",
              "direction": b_direction},
        "analysis_mode": analysis_mode,
        "combined_objective": None,
        "conditions": list(conditions),
        "dataset_id": "FIXTURE_DATASET",
        "donor_scope": "all",
        "effect_universe_id": "FIXTURE_EFFECT_UNIVERSE",
        "poles_separate": True,
        "registry_scorer_view_sha256": registry_view_sha256,
        "source_h5ad_sha256": "0" * 64,
        "source_hf_revision": "fixture",
        "stage1_method_version": STAGE1_METHOD_VERSION,
    }


def question_content(content: dict[str, Any]) -> dict[str, Any]:
    """THE BIOLOGY, with the CONDITION INSIDE EACH POLE. A at the first, B at the last."""
    conditions = list(content["conditions"])
    return {
        "A": {"program_id": content["A"]["program_id"],
              "direction": content["A"]["direction"], "condition": conditions[0]},
        "B": {"program_id": content["B"]["program_id"],
              "direction": content["B"]["direction"], "condition": conditions[-1]},
        "analysis_mode": content["analysis_mode"],
    }


def _arm_ref(role: str, program: str, direction: str, condition: str,
             conditions: Sequence[str]) -> dict[str, Any]:
    """Stage-1's OWN arm reference: the keys IT believes this pole names, at ITS OWN condition."""
    change = DESIRED_CHANGE[(role, direction)]
    return {
        "role": role, "program_id": program, "pole_direction": direction,
        "desired_change": change, "condition": condition,
        "direct_arm_key": f"direct|{program}|{change}|{condition}",
        "pathway_arm_key_base": f"pathway|{program}|{change}|{condition}",
        "temporal_arm_key": (f"temporal|{program}|{change}|{conditions[0]}|{conditions[-1]}"
                             if len(conditions) == 2 else None),
    }


def selection(*, a_program: str, a_direction: str, b_program: str, b_direction: str,
              analysis_mode: str, conditions: Sequence[str], registry_view_sha256: str,
              execution_status: str = "ready", with_arms: bool = True,
              mutate: Optional[Any] = None, reseal: bool = True) -> dict[str, Any]:
    """A complete, self-consistent ``spot.stage01_selection.v3`` contract, Stage-1's shape."""
    content = canonical_content(
        a_program=a_program, a_direction=a_direction, b_program=b_program,
        b_direction=b_direction, analysis_mode=analysis_mode, conditions=conditions,
        registry_view_sha256=registry_view_sha256)
    conds = list(conditions)
    doc: dict[str, Any] = {
        "schema_version": SCHEMA,
        "selection_origin": "fixture",
        "execution_status": execution_status,
        "analysis_mode": analysis_mode,
        "estimator_id": ("within_condition_v1" if analysis_mode == "within_condition"
                         else "temporal_cross_condition_v1"),
        "estimator_status": "available",
        "selection_id": stage2_content_sha256(content)[:16],
        "selection_full_sha256": stage2_content_sha256(content),
        "question_id": stage2_content_sha256(question_content(content))[:16],
        "canonical_content": content,
        "poles": {
            "A": {"program_id": a_program, "direction": a_direction,
                  "effect_projection_status": "available"},
            "B": {"program_id": b_program, "direction": b_direction,
                  "effect_projection_status": "available"},
        },
        "historical_validation_provenance": {"active_gate": False},
    }
    if with_arms:
        # Each arm sits at its OWN pole condition: away_from_A at conditions[0], toward_B at
        # conditions[-1] (the same one within-time; the later timepoint across time).
        doc["arms"] = {
            "away_from_A": _arm_ref("away_from_A", a_program, a_direction, conds[0], conds),
            "toward_B": _arm_ref("toward_B", b_program, b_direction, conds[-1], conds),
        }
    if mutate:
        mutate(doc)
    if reseal:
        # RE-SEAL EVERY ID, exactly as a forger with repo access would. A gate that only catches
        # a careless edit catches nothing: the ids must ALSO bind the store the view is over.
        content = doc["canonical_content"]
        doc["selection_id"] = stage2_content_sha256(content)[:16]
        doc["selection_full_sha256"] = stage2_content_sha256(content)
        doc["question_id"] = stage2_content_sha256(question_content(content))[:16]
        doc["full_contract_content_sha256"] = stage2_content_sha256(
            {k: v for k, v in doc.items() if k != "full_contract_content_sha256"})
    else:
        doc.setdefault("full_contract_content_sha256", "0" * 64)
    return doc
