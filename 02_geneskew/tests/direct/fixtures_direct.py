"""Fixture builders for the Stage-2 direct lane (Stage-1 trust, selection, specs).

The contributor-evidence bundle — the raw source, its offset proof, the source records,
their derived ids and the manifest that cites them — lives in ``fixtures_evidence``,
because it can only be built in one order and that order is worth stating once.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from fixtures_evidence import (  # noqa: F401  (the one evidence API, re-exported)
    IDENTITY_METHOD,
    MANIFEST_NAME,
    NON_TARGETING_GUIDES,
    NON_TARGETING_TARGET,
    PINNED_REVISION,
    RECORD_TABLE_NAME,
    REGISTRY_NAME,
    REPLAY_REPORT_NAME,
    SOURCE_CLASS,
    SOURCE_NAME,
    Evidence,
    contributing_guides,
    kept_proof,
    link_citations,
    main_ambiguous,
    manifest_doc,
    manifest_rows,
    raw_source_rows,
    source_record_doc,
    source_records,
    write_evidence,
    write_replay_report,
    write_source_file,
)
from fixtures_io import (
    _write_by_donors,
    _write_by_guide,
    _write_main,
    _write_modality,
    _write_obs,
    _write_sgrna,
)
from fixtures_spec import (
    A_PANEL,
    B_PANEL,
    COMMON_UNIVERSE,
    CONDITION,
    CONTROLS,
    DONOR_DROPPED_GENE,
    DONOR_PAIRS,
    DONOR_UNIVERSE,
    DONORS,
    RELEASE_CONDITIONS,
    SYMBOL_TARGETS,
    TARGET_GENES,
    UNIVERSE,
    TargetSpec,
)


def write_stage1_gates(d: str, selectable: bool = True,
                       program_ids=("fx_program_a", "fx_program_b"),
                       conditions=(CONDITION,)) -> tuple[str, str]:
    """A Stage-1 validation + gate spec whose hard gates are RE-DERIVED, not stored.

    ``selectable=False`` reproduces the frozen reality: 0 pairs pass, so nothing
    is production-selectable.

    Selectability is per PROGRAM-CONDITION, so a release that ships three conditions
    carries validation rows for all three: Stage-1 validated each one separately, and a
    gate that could only be re-derived at one of them would refuse the other two.
    """
    gate_spec = {
        "schema_version": "spot.stage01_gate_spec.v1",
        "hard_gates": ["separability", "donor_stability"],
        "thresholds": {
            "separability": {"comparator": "ge", "threshold": 0.70},
            "donor_stability": {"comparator": "ge", "threshold": 0.60},
        },
    }
    passing = {"separability": 0.90, "donor_stability": 0.80}
    failing = {"separability": 0.10, "donor_stability": 0.05}
    values = passing if selectable else failing
    rows = []
    for cond in conditions:
        for pid in program_ids:
            for gate, value in values.items():
                rows.append({"program_id": pid, "condition": cond,
                             "gate_id": gate, "value": value,
                             # a STORED verdict that the loader must ignore entirely
                             "passed": True, "stage2_selectable": True})
    validation = {"schema_version": "spot.stage01_validation.v1", "rows": rows}

    gpath = os.path.join(d, "stage01_gate_spec.json")
    vpath = os.path.join(d, "stage01_validation.json")
    with open(gpath, "w") as fh:
        json.dump(gate_spec, fh, indent=2, sort_keys=True)
    with open(vpath, "w") as fh:
        json.dump(validation, fh, indent=2, sort_keys=True)
    return vpath, gpath


def program_names(prefix: str = "fx_", program_ids=None) -> tuple[str, str]:
    """Program ids are BIOLOGY, not lane state: a real contract carries the frozen
    registry ids (``treg_like``/``th1_like``) with no lane prefix at all."""
    return tuple(program_ids) if program_ids else (f"{prefix}program_a",
                                                   f"{prefix}program_b")


def _write_registry(path: str, extra: dict = None, prefix: str = "fx_",
                    program_ids=None, extra_programs=None) -> str:
    from direct.hashing import file_sha256
    name_a, name_b = program_names(prefix, program_ids)
    # NOTE: no ``production_selectable`` here. The frozen Stage-1 result has ZERO
    # production-selectable pairs, so the synthetic registry must not claim one.
    programs = [
        {"program_id": name_a, "display_label": "Program A",
         "panel_ensembl": A_PANEL, "control_ensembl": CONTROLS,
         "stage2_selectable": True, "primary": True, "base_portable": True},
        {"program_id": name_b, "display_label": "Program B",
         "panel_ensembl": B_PANEL, "control_ensembl": CONTROLS,
         "stage2_selectable": True, "primary": True, "base_portable": True},
    ]
    for p in programs:
        p.update(extra or {})
    # Programs the registry SHIPS but the legacy selection does not name. A v3 contract
    # can then name a DIFFERENT axis than the legacy contract, which is the only way to
    # prove which one a run actually executed (B3).
    programs += list(extra_programs or [])
    reg = {
        "schema_version": "spot.stage01_program_registry.v3",
        "method_version": "stage1-continuous-v3.0.1",
        "programs": programs,
    }
    with open(path, "w") as fh:
        json.dump(reg, fh, indent=2, sort_keys=True)
    from direct.trust import canonical_content_sha256
    return canonical_content_sha256(reg)


def derived_ids(contract: dict) -> dict:
    """Derive the canonical namespaced ids exactly as the lane does."""
    from direct import selection as sel_mod
    from direct.hashing import content_hash
    lane = contract["lane"]
    prefix = sel_mod.LANE_ID_PREFIX.get(lane, "")
    n = sel_mod.ID_LEN
    q = prefix + content_hash({
        "A": {"program_id": contract["A"]["program_id"],
              "direction": contract["A"]["direction"]},
        "B": {"program_id": contract["B"]["program_id"],
              "direction": contract["B"]["direction"]},
        "analysis_condition": contract["analysis_condition"],
    })[:n]
    sid = prefix + content_hash({
        "question_id": q,
        "registry_sha256": contract["hashes"]["registry_sha256"],
        "method_version": contract["hashes"]["method_version"],
        "input_manifest_sha256": contract["hashes"].get("input_manifest_sha256"),
    })[:n]
    return {"question_id": q, "selection_id": sid}


def write_research_bridge(path: str, registry_sha: str, release_hashes: dict,
                          prefix: str = "rq_", program_ids=None,
                          **overrides) -> None:
    """The deterministic Stage-1 research bridge (spot.stage01_selection.v1)."""
    name_a, name_b = program_names(prefix, program_ids)
    contract = {
        "schema_version": "spot.stage01_selection.v1",
        "lane": "research_only",
        "bridge": {"namespace": "research_only", "production_gate_passed": False,
                   "source": "stage01_research_bridge"},
        "A": {"program_id": name_a, "direction": "high"},
        "B": {"program_id": name_b, "direction": "high"},
        "analysis_condition": CONDITION,
        "combination_policy": "deferred_to_stage2",
        "hashes": dict({"registry_sha256": registry_sha,
                        "method_version": "stage1-continuous-v3.0.1",
                        "input_manifest_sha256": "m" * 64,
                        "code_sha256": "c" * 64}, **(release_hashes or {})),
    }
    forged = overrides.pop("ids", None)
    contract.update(overrides)
    # Derive from the FINAL content, so a legitimate override (A/B, condition) still
    # produces a self-consistent contract; an explicit ``ids=`` is a forgery attack
    # and is written verbatim.
    contract["ids"] = forged if forged is not None else derived_ids(contract)
    with open(path, "w") as fh:
        json.dump(contract, fh, indent=2, sort_keys=True)


def write_selection(path: str, registry_sha: str, *,
                    method_version="stage1-continuous-v3.0.1",
                    a_direction="high", b_direction="high",
                    lane="synthetic", prefix="fx_", release_hashes=None,
                    program_ids=None, **overrides) -> None:
    name_a, name_b = program_names(prefix, program_ids)
    contract = {
        "schema_version": "spot.stage01_selection_contract.v1",
        "lane": lane,
        "A": {"program_id": name_a, "direction": a_direction},
        "B": {"program_id": name_b, "direction": b_direction},
        "analysis_condition": CONDITION,
        "combination_policy": "deferred_to_stage2",
        "hashes": {
            "registry_sha256": registry_sha,
            "method_version": method_version,
            "input_manifest_sha256": "m" * 64,
            "code_sha256": "c" * 64,
        },
    }
    if lane == "production":
        # a production contract must bind EXACTLY the verified release
        contract["hashes"].update(release_hashes or {})
    forged = overrides.pop("ids", None)
    drop_lane = overrides.pop("lane_delete", False)
    contract.update(overrides)
    # Derive from the FINAL content, so a legitimate override (A/B, condition) still
    # produces a self-consistent contract; an explicit ``ids=`` is a forgery attack and
    # is written verbatim. Same rule as the research bridge, for the same reason.
    contract["ids"] = forged if forged is not None else derived_ids(contract)
    if drop_lane:
        contract.pop("lane", None)
    with open(path, "w") as fh:
        json.dump(contract, fh, indent=2, sort_keys=True)


def default_specs() -> list[TargetSpec]:
    """Fourteen targets plus the 4 symbol scopes, covering every pooled-main outcome.

    The guide-slot and donor-pair fields still describe what the RELEASE ships — those
    objects exist and are enumerated for accounting — but they are no longer contributor
    evidence for anything: support is explicitly unavailable in this pass, so no spec
    here can make a slot mask, project, replicate, or elevate a tier.
    """
    t = TARGET_GENES
    # donor-pair values are log_fc on the A panel: negative == same direction as
    # a negative main a_effect, i.e. a positive away_from_A.
    all_pairs = {p: -1.0 for p in DONOR_PAIRS}
    return [
        # T0: the manifest proves both contributing guides.
        TargetSpec(t[0], ["g-T0-1", "g-T0-2"], 2.0, a_effect=-1.0, b_effect=1.0,
                   guide_slot_effects={"guide_1": -1.0, "guide_2": -0.8},
                   donor_pair_effects=dict(all_pairs),
                   guide_neighbors={"g-T0-1": [A_PANEL[1]]},
                   manifest_slots={"guide_1": "g-T0-1", "guide_2": "g-T0-2"}),
        # T1: the library holds 2 guides but only 1 contributed. No rule could
        # ever say WHICH; the manifest names it, so the target is scoreable.
        TargetSpec(t[1], ["g-T1-1", "g-T1-2"], 1.0, a_effect=-9.0,
                   guide_slot_effects={"guide_1": -9.0},
                   donor_pair_effects=dict(all_pairs),
                   manifest_main=["g-T1-2"],            # NOT the alphanumeric first
                   manifest_slots={"guide_1": "g-T1-2"}),
        # T2: three library guides, two contributed -> the unused guide must not
        # mask. Only the manifest can say which two.
        TargetSpec(t[2], ["g-T2-1", "g-T2-2", "g-T2-3"], 2.0, a_effect=-2.0,
                   guide_slot_effects={"guide_1": -2.0, "guide_2": -2.0},
                   donor_pair_effects=dict(all_pairs),
                   manifest_main=["g-T2-1", "g-T2-3"],
                   manifest_slots={"guide_1": "g-T2-1", "guide_2": "g-T2-3"}),
        # T3: the release is self-consistent, but the target is absent from the
        # sgRNA library, so the manifest cannot prove an identity -> ambiguous,
        # and ambiguous stays UNAVAILABLE rather than being rounded to a guess.
        TargetSpec(t[3], [], 2.0, a_effect=-3.0,
                   guide_slot_effects={"guide_1": -3.0, "guide_2": -3.0},
                   donor_pair_effects=dict(all_pairs)),
        # T4: two contributing guides, and the release ships only ONE guide slot.
        # The retired slot-contradiction gate refused the whole target for this; it
        # was reading COPIED pooled metadata as an independent witness. The pooled
        # estimate now resolves from the pooled manifest and pooled n_guides alone,
        # so T4 is scored — and a support object can no longer take it down.
        TargetSpec(t[4], ["g-T4-1", "g-T4-2"], 2.0, a_effect=-0.5,
                   guide_slot_effects={"guide_1": -0.5},
                   donor_pair_effects=dict(all_pairs),
                   manifest_slots={"guide_1": "g-T4-1"}),
        # T5: two guides whose SLOT effects disagree in sign. With support
        # unavailable no replication claim is made either way; the pooled fit stands.
        TargetSpec(t[5], ["g-T5-1", "g-T5-2"], 2.0, a_effect=-0.4,
                   guide_slot_effects={"guide_1": -0.4, "guide_2": 0.9},
                   donor_pair_effects=dict(all_pairs),
                   manifest_slots={"guide_1": "g-T5-1", "guide_2": "g-T5-2"}),
        # T6: a genuine single-guide target.
        TargetSpec(t[6], ["g-T6-1"], 1.0, a_effect=-0.3,
                   guide_slot_effects={"guide_1": -0.3},
                   donor_pair_effects={p: -0.3 for p in DONOR_PAIRS[:2]},
                   manifest_slots={"guide_1": "g-T6-1"}),
        # T7: the HIGHEST primary score in the run, but too few cells -> scored,
        # ineligible, and therefore unranked.
        TargetSpec(t[7], ["g-T7-1", "g-T7-2"], 2.0, a_effect=-12.0, n_cells=3.0,
                   guide_slot_effects={"guide_1": -12.0, "guide_2": -12.0},
                   donor_pair_effects=dict(all_pairs),
                   manifest_slots={"guide_1": "g-T7-1", "guide_2": "g-T7-2"}),
        # T8: the pooled fit declares n_guides = 1, the library maps exactly one
        # guide, and the release still ships TWO guide-level DEs. That disagreement
        # is between the pooled fit and a support object's COPIED metadata, and the
        # support object is not a witness: the pooled estimate is scored on its own
        # evidence, and the 6,707 targets this pattern would once have refused stand.
        TargetSpec(t[8], ["g-T8-1"], 1.0, a_effect=-7.0,
                   guide_slot_effects={"guide_1": -7.0, "guide_2": -6.5},
                   guide_slot_n_guides={"guide_1": 1.0, "guide_2": 1.0},
                   donor_pair_effects=dict(all_pairs),
                   manifest_slots={"guide_1": "g-T8-1"}),
        # T9: a genuine MULTI-guide target (3 contributing guides).
        TargetSpec(t[9], ["g-T9-1", "g-T9-2", "g-T9-3"], 3.0, a_effect=-0.6,
                   guide_slot_effects={"guide_1": -0.6, "guide_2": -0.6},
                   donor_pair_effects=dict(all_pairs),
                   manifest_slots={"guide_1": "g-T9-1"}),
        # ---- THE ARBITRARY-CONTRAST ATTACK ----
        # T10 moves strongly AWAY from A but OPPOSES B. T11 barely moves away from
        # A but moves strongly TOWARD B. Under a single "primary" endpoint T10
        # outranked T11 and the B dropdown was decorative. With two arms, T10 must
        # top the away_from_A rank and be LAST (or unranked-negative) in toward_B,
        # while T11 tops toward_B.
        TargetSpec(t[10], ["g-TA-1", "g-TA-2"], 2.0,
                   a_effect=-8.0,          # away_from_A = +8.0 (strong)
                   b_effect=-4.0,          # toward_B    = -4.0 (OPPOSES B)
                   guide_slot_effects={"guide_1": -8.0, "guide_2": -8.0},
                   donor_pair_effects=dict(all_pairs),
                   manifest_slots={"guide_1": "g-TA-1", "guide_2": "g-TA-2"}),
        TargetSpec(t[11], ["g-TB-1", "g-TB-2"], 2.0,
                   a_effect=-0.05,         # away_from_A = +0.05 (weak)
                   b_effect=+9.0,          # toward_B    = +9.0 (strong)
                   guide_slot_effects={"guide_1": -0.05, "guide_2": -0.05},
                   donor_pair_effects=dict(all_pairs),
                   manifest_slots={"guide_1": "g-TB-1", "guide_2": "g-TB-2"}),
        # T12: A-evaluable / B-INELIGIBLE -- its guides mask out the whole B panel,
        # so arm B has no surviving panel gene while arm A is perfectly fine.
        TargetSpec(t[12], ["g-TC-1", "g-TC-2"], 2.0, a_effect=-1.5, b_effect=3.0,
                   guide_slot_effects={"guide_1": -1.5, "guide_2": -1.5},
                   donor_pair_effects=dict(all_pairs),
                   guide_neighbors={"g-TC-1": list(B_PANEL)},
                   manifest_slots={"guide_1": "g-TC-1", "guide_2": "g-TC-2"}),
        # ---- THE 12 SYMBOL-NAMESPACE RELEASE SCOPES ----
        # obs.target_contrast is a gene SYMBOL. Nine of the twelve carry an
        # ENSG-looking release key that belongs to a DIFFERENT gene. All are
        # ontarget_significant=false / low_target_gex=true, all have n_guides=2 and
        # admissible guide reconstruction, and ALL must still be emitted.
        *[TargetSpec(sym, [], 2.0, a_effect=-1.0, b_effect=1.0,
                     ontarget_significant=False, low_target_gex=True,
                     guide_slot_effects={"guide_1": -1.0, "guide_2": -1.0},
                     donor_pair_effects=dict(all_pairs),
                     released_key_prefix=prefix)
          for sym, prefix in SYMBOL_TARGETS.items()],
        # T13: B-evaluable / A-INELIGIBLE -- the mirror image.
        TargetSpec(t[13], ["g-TD-1", "g-TD-2"], 2.0, a_effect=-2.5, b_effect=6.0,
                   guide_slot_effects={"guide_1": -2.5, "guide_2": -2.5},
                   donor_pair_effects=dict(all_pairs),
                   guide_neighbors={"g-TD-1": list(A_PANEL)},
                   manifest_slots={"guide_1": "g-TD-1", "guide_2": "g-TD-2"}),
    ]


def write_stage1_release(d: str, registry: str, validation: str, gate_spec: str,
                         kind: str = "production") -> str:
    """A full immutable Stage-1 bundle: every binding present + pinned.

    ``kind="research"`` omits only the production selectability pointer; every
    measurement binding is still required.
    """
    from direct.hashing import file_sha256
    from direct.trust import canonical_content_sha256

    def artifact(path):
        entry = {"path": os.path.basename(path), "raw_sha256": file_sha256(path)}
        if path.endswith(".json"):
            with open(path) as fh:
                entry["canonical_sha256"] = canonical_content_sha256(json.load(fh))
        return entry

    # the remaining required bindings, as real pinned files
    names = ["input_manifest", "scores", "code", "environment"]
    if kind == "production":
        names.append("selectability_pointer")
    extras = {}
    for name in names:
        p = os.path.join(d, f"stage01_{name}.json")
        with open(p, "w") as fh:
            json.dump({"artifact": name}, fh, indent=2, sort_keys=True)
        extras[name] = artifact(p)

    manifest = {
        "schema_version": "spot.stage01_release_manifest.v1",
        "method_version": "stage1-continuous-v3.0.1",
        "artifacts": dict({"registry": artifact(registry),
                           "validation": artifact(validation),
                           "gate_spec": artifact(gate_spec)}, **extras),
    }
    path = os.path.join(d, f"stage01_{kind}_bundle.json")
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    return path


@dataclass
class RunArgs:
    selection: str
    registry: str
    de_main: str
    by_guide: str
    by_donors: str
    sgrna: str
    out_root: str
    guide_manifest: Optional[str] = None
    source_registry: Optional[str] = None
    stage1_release: Optional[str] = None
    stage1_validation: Optional[str] = None
    stage1_gate_spec: Optional[str] = None
    donor_crosswalk: Optional[str] = None
    env_lock: Optional[str] = None
    lane: str = "synthetic"        # fixtures are synthetic and stay synthetic
    # THE RELEASE GATE. A release-grade lane (production / research_only) may not stand
    # on the pinned replay report, and there is nothing it may present instead: it must
    # re-derive completeness from the raw source in its own invocation. The fixture "raw
    # source" is a few dozen rows, so these lanes run a genuine FRESH strict replay
    # against it — the same code path tcefold runs against the 44 GB object, at a size a
    # unit test can afford.
    #
    # There is deliberately no ``strict_preflight`` field. It carried the path to a
    # "pinned strict-preflight GO artifact", which authenticated nothing and was bound
    # to no evidence; a fixture that can still express the forgery is a fixture that
    # invites a test to re-legitimise it.
    strict_replay: bool = False
    pseudobulk: Optional[str] = None
