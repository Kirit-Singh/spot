"""The Stage-2 -> Stage-3 BRIDGE consumer, attacked.

Every attack here is a COHERENT forgery: the document is edited and then RESEALED, so its own
self-hash recomputes and it is internally consistent. A gate that only checked the self-hash would
admit every single one of them. What kills them is the REBUILD — the bridge is checked against the
admitted native ranking bytes, which the forger does not own.

The one attack that is NOT resealed is the opposite case (``test_altered_bytes_...``): the bytes on
disk are edited AFTER sealing while the caller hands over a pristine dict. It must die too, because
the consumer reads the FILE, never the caller's copy of it.
"""
from __future__ import annotations

import json
import os

import pytest

import native_aggregate_fixture as NAF
from druglink import bridge_join as bj
from druglink import modality_contract as mc
from druglink import stage2_aggregate as sa
from druglink import stage2_bridge as sb


def _paths(tmp_path, **kw):
    return NAF.build(os.path.join(str(tmp_path), "agg"), **kw)


def _admit(paths):
    aggregate = NAF.admit(paths)
    return NAF.admit_bridge(paths, aggregate)


def _refuses(paths, gate):
    with pytest.raises(sa.Stage2BridgeError) as exc:
        _admit(paths)
    assert f"[{gate}]" in str(exc.value), f"expected gate {gate}, got: {exc.value}"
    return str(exc.value)


def _reseal_bridge(path):
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc[NAF.BRIDGE_SELF_HASH_FIELD] = sa.stage2_content_sha256(
        {k: v for k, v in doc.items() if k != NAF.BRIDGE_SELF_HASH_FIELD})
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, sort_keys=True, separators=(",", ":"))


# --- The honest chain. ------------------------------------------------------ #
def test_the_real_shaped_bridge_admits_and_types_the_native_rows(tmp_path):
    paths = _paths(tmp_path)
    aggregate = NAF.admit(paths)

    # The NATIVE record is untyped. This is the fact the whole bridge exists for.
    native = aggregate.arms[0].records[0]
    assert set(native) == {"target_id", "arm_value", "evaluable", "rank"}
    assert "target_id_namespace" not in native and "observed_perturbation_modality" not in native

    bridge = NAF.admit_bridge(paths, aggregate)
    assert bridge.verdict == sa.ADMIT
    assert bridge.verifier_id == sb.BRIDGE_VERIFIER_ID
    assert bridge.counts["n_target_rows"] == 900        # 180 measured arms x 5 targets
    assert bridge.counts["n_pathway_contexts"] == 120

    typed = sa.bind_bridge(aggregate, bridge)
    measured = [a for a in typed.arms if a.lane in sa.MEASURED_LANES][0]
    rec = measured.records[0]
    # ADDED: identity + modality. UNCHANGED: the measurement.
    assert rec["target_id_namespace"] and rec["observed_perturbation_modality"]
    assert rec["arm_value"] == native["arm_value"] and rec["rank"] == native["rank"]

    # The aggregate that was admitted is NOT mutated: a caller still holding it holds the
    # untyped bytes it actually admitted.
    assert "target_id_namespace" not in aggregate.arms[0].records[0]


def test_the_binding_a_bundle_publishes_carries_no_path(tmp_path):
    """An absolute path names a place on one machine, not an artifact — and the REAL bridge's
    bindings are full of them (``/tmp/proto_…``). None may reach a releasable artifact."""
    binding = _admit(_paths(tmp_path)).binding()
    leaks = [f"{k}={v!r}" for k, v in binding.items()
             if isinstance(v, str) and ("/" in v or os.path.isabs(v))]
    assert not leaks, f"the bridge binding leaks a filesystem path: {leaks}"
    assert not [k for k in binding if k == "path" or k.endswith("_path")]


# --- Identity, and the separate verifier's admission. ----------------------- #
def test_altered_bridge_bytes_with_a_clean_caller_dict(tmp_path):
    """The consumer reads the FILE. A pristine dict handed alongside altered bytes admits the
    altered bytes, or nothing."""
    paths = _paths(tmp_path)
    with open(paths["bridge"], encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["target_rows"][0]["arm_value"] = 99.0          # edited AFTER sealing; NOT resealed
    with open(paths["bridge"], "w", encoding="utf-8") as fh:
        json.dump(doc, fh, sort_keys=True, separators=(",", ":"))
    _refuses(paths, sb.GATE_BRIDGE_SELF_HASH)


def test_a_coherently_resealed_bridge_that_restates_a_measurement(tmp_path):
    """The forger reseals, so the self-hash recomputes. It still dies: the NATIVE ranking says
    otherwise, and those bytes are not the forger's to edit."""
    def forge(bridge):
        bridge["target_rows"][0]["arm_value"] = 99.0
    _refuses(_paths(tmp_path, mutate_bridge=forge), sb.GATE_BRIDGE_CHANGED_A_NATIVE_VALUE)


def test_a_bridge_that_admits_itself(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b.update(self_admitted=True)),
             sb.GATE_BRIDGE_SELF_ADMITTED)


def test_a_bridge_that_binds_nothing(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b["bindings"].pop("aggregate")),
             sb.GATE_BRIDGE_BINDS_NOTHING)


def test_a_bridge_that_is_not_the_native_schema(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b.update(schema_version="spot.made.up.v1")),
             sb.GATE_BRIDGE_NOT_NATIVE)


def test_a_bridge_with_no_evidence(tmp_path):
    """A clean report over an EMPTY handoff is the most dangerous artifact of all."""
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b.update(target_rows=[])),
             sb.GATE_BRIDGE_ZERO_EVIDENCE)


def test_a_missing_bridge(tmp_path):
    paths = _paths(tmp_path)
    os.remove(paths["bridge"])
    _refuses(paths, sb.GATE_BRIDGE_NOT_ON_DISK)


def test_the_bridge_and_its_report_are_the_same_file(tmp_path):
    paths = _paths(tmp_path)
    paths["bridge_report"] = paths["bridge"]
    _refuses(paths, sb.GATE_BRIDGE_SELF_ADMISSION)


# --- The SEPARATE report. --------------------------------------------------- #
def test_a_report_that_did_not_admit(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge_report=lambda r: r.update(verdict="refuse")),
             sb.GATE_BRIDGE_NOT_ADMITTED)


def test_a_report_with_a_failed_gate_but_an_admit_verdict(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge_report=lambda r: r.update(n_failed=1)),
             sb.GATE_BRIDGE_NOT_ADMITTED)


def test_a_report_that_only_read_the_rows_it_did_not_rebuild_them(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge_report=lambda r: r.update(
        reconstructs_from_admitted_native_bytes=False)), sb.GATE_BRIDGE_NOT_ADMITTED)


def test_generator_is_verifier(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge_report=lambda r: r.update(
        generator_is_not_verifier=False)), sb.GATE_BRIDGE_REPORT_NOT_INDEPENDENT)


def test_a_forged_verifier_name(tmp_path):
    """A friendly-sounding id is not a binding. The verifier is PINNED."""
    _refuses(_paths(tmp_path, mutate_bridge_report=lambda r: r.update(
        verifier_id="totally.independent.verifier.v1")), sb.GATE_BRIDGE_REPORT_NOT_INDEPENDENT)


def test_a_report_that_judged_other_bytes(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge_report=lambda r: r["judged_bridge"].update(
        raw_sha256="0" * 64)), sb.GATE_REPORT_JUDGED_OTHER_BYTES)


# --- THE RECEIPT: the join. ------------------------------------------------- #
def test_a_receipt_that_binds_another_bridge(tmp_path):
    _refuses(_paths(tmp_path, mutate_receipt=lambda r: r["bridge"].update(raw_sha256="0" * 64)),
             sb.GATE_RECEIPT_BINDS_ANOTHER_BRIDGE)


def test_a_receipt_that_binds_another_report(tmp_path):
    _refuses(_paths(tmp_path, mutate_receipt=lambda r: r["bridge_report"].update(
        canonical_sha256="0" * 64)), sb.GATE_RECEIPT_BINDS_ANOTHER_REPORT)


def test_a_receipt_over_another_aggregate(tmp_path):
    """A bridge over a release nobody cleared looks exactly like one over a release that was."""
    _refuses(_paths(tmp_path, mutate_receipt=lambda r: r["aggregate"]["manifest"].update(
        raw_sha256="0" * 64)), sb.GATE_RECEIPT_BINDS_ANOTHER_AGGREGATE)


def test_a_receipt_edited_after_it_was_addressed(tmp_path):
    paths = _paths(tmp_path)
    with open(paths["receipt"], encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["aggregate_is_immutable"] = False            # edited; self-hash NOT recomputed
    with open(paths["receipt"], "w", encoding="utf-8") as fh:
        json.dump(doc, fh, sort_keys=True, separators=(",", ":"))
    _refuses(paths, sb.GATE_RECEIPT_SELF_HASH)


def test_a_receipt_that_is_not_the_native_schema(tmp_path):
    _refuses(_paths(tmp_path, mutate_receipt=lambda r: r.update(schema_version="spot.nope.v1")),
             sb.GATE_RECEIPT_NOT_NATIVE)


# --- THE ROWS: rebuilt from bytes the forger does not own. ------------------- #
def test_a_dropped_row(tmp_path):
    """A dropped row and a row that never existed look identical, and the dropped one is the one
    nobody checks."""
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b["target_rows"].pop(0)),
             sb.GATE_BRIDGE_DROPPED_A_ROW)


def test_an_orphan_row_the_native_bytes_never_produced(tmp_path):
    def forge(bridge):
        row = dict(bridge["target_rows"][0], target_id="FIXTURE_TGT_INVENTED")
        bridge["target_rows"].append(row)
    _refuses(_paths(tmp_path, mutate_bridge=forge), sb.GATE_BRIDGE_ORPHAN_ROW)


def test_two_rows_claiming_one_identity(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b["target_rows"].append(
        dict(b["target_rows"][0]))), sb.GATE_BRIDGE_DUPLICATE_ROW)


def test_a_row_missing_a_typed_column(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b["target_rows"][0].pop(
        "target_id_namespace")), sb.GATE_BRIDGE_ROW_INCOMPLETE)


def test_a_direction_the_native_value_does_not_imply(tmp_path):
    """The bridge's direction token is a CHECK, never an input. Flip it and the sign re-derived
    from the NATIVE arm_value refuses it."""
    def forge(bridge):
        row = bridge["target_rows"][0]
        row["desired_target_modulation"] = "increase"
        row["phenocopy_class"] = "inhibitor_opposed"
    _refuses(_paths(tmp_path, mutate_bridge=forge),
             mc.GATE_SERIALIZED_MODULATION_DISAGREES_WITH_THE_SIGN)


def test_a_rank_the_native_ranking_does_not_state(tmp_path):
    """The RETAINED rank:null row is the one most likely to be quietly given a rank."""
    def forge(bridge):
        row = [r for r in bridge["target_rows"] if r["rank"] is None][0]
        row["rank"] = 1
    _refuses(_paths(tmp_path, mutate_bridge=forge), sb.GATE_BRIDGE_CHANGED_A_NATIVE_VALUE)


# --- THE PATHWAY FIREWALL: context annotates, and never promotes. ----------- #
def test_a_pathway_arm_shipping_a_target_row(tmp_path):
    """THE orphan-pathway-drug attack: a gene-set arm ships a target row, so a set membership
    would source a drug edge no measurement supports."""
    def forge(bridge):
        pathway_arm = bridge["pathway_contexts"][0]["arm_key"]
        row = dict(bridge["target_rows"][0], lane="pathway", arm_key=pathway_arm)
        bridge["target_rows"].append(row)
    _refuses(_paths(tmp_path, mutate_bridge=forge), sb.GATE_PATHWAY_LANE_CARRIES_TARGET_ROWS)


def test_a_pathway_context_smuggling_a_target_evidence_field(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b["pathway_contexts"][0].update(
        arm_value=0.9)), sb.GATE_CTX_CARRIES_TARGET_EVIDENCE)


def test_a_pathway_context_that_does_not_deny_being_a_target_row(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b["pathway_contexts"][0].update(
        may_be_matched_to_a_drug_as_a_target=True)), sb.GATE_CTX_CARRIES_TARGET_EVIDENCE)


def test_a_pathway_context_with_an_unknown_field(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b["pathway_contexts"][0].update(
        promoted_candidate="CHEMBL999")), sb.GATE_CTX_UNKNOWN_FIELD)


def test_a_pathway_context_for_an_arm_nobody_ran(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b["pathway_contexts"][0].update(
        arm_key="pathway|GHOST_PROG|increase|Rest|GO-BP")), sb.GATE_CTX_ORPHAN_ARM)


def test_a_pathway_context_naming_an_absolute_artifact_path(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b["pathway_contexts"][0].update(
        source_artifact={"path": "/etc/passwd", "raw_sha256": "0" * 64})),
        sb.GATE_ABSOLUTE_ARTIFACT_REF)


def test_a_pathway_context_traversing_out_of_the_bundle(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b["pathway_contexts"][0].update(
        source_artifact={"path": "../../secrets.json", "raw_sha256": "0" * 64})),
        sb.GATE_ABSOLUTE_ARTIFACT_REF)


def test_the_join_refuses_to_type_a_pathway_arm(tmp_path):
    """Belt and braces: even if a bridge row somehow reached a pathway arm, the JOIN refuses to
    let a gene set acquire a typed target record."""
    paths = _paths(tmp_path)
    aggregate = NAF.admit(paths)
    bridge = NAF.admit_bridge(paths, aggregate)
    pathway = [a for a in aggregate.arms if a.lane == sa.LANE_PATHWAY][0]
    # forge a typed row onto a pathway arm, behind the admission gate's back
    tid = str(pathway.records[0].get("target_id"))
    object.__setattr__(pathway, "records",
                       ({"target_id": "FIXTURE_TGT_00", "arm_value": 0.1,
                         "evaluable": True, "rank": 1},))
    bridge.rows[(sa.LANE_PATHWAY, pathway.arm_key, "FIXTURE_TGT_00")] = {
        "target_id_namespace": "ensembl_gene_id",
        "observed_perturbation_modality": "CRISPRi_knockdown"}
    with pytest.raises(sa.Stage2BridgeError) as exc:
        sa.bind_bridge(aggregate, bridge)
    assert f"[{bj.GATE_PATHWAY_ARM_WAS_TYPED}]" in str(exc.value)
    assert tid is not None


def test_a_measured_record_with_no_typed_bridge_row(tmp_path):
    """Without the bridge row a target has no identity to join on — and a namespace GUESSED from
    the shape of an id attaches the wrong gene to a drug."""
    paths = _paths(tmp_path)
    aggregate = NAF.admit(paths)
    bridge = NAF.admit_bridge(paths, aggregate)
    bridge.rows.clear()
    with pytest.raises(sa.Stage2BridgeError) as exc:
        sa.bind_bridge(aggregate, bridge)
    assert f"[{bj.GATE_ARM_IDENTITY_UNRESOLVED}]" in str(exc.value)


# --- The two vocabularies that may never cross the bridge. ------------------ #
def test_a_combined_objective_at_the_top_level(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b.update(combined_score=0.9)),
             sb.GATE_COMBINED_OBJECTIVE)


def test_a_combined_objective_nested_deep(tmp_path):
    """The whole point of reviving a combined objective is that it arrives NESTED, in a later
    writer."""
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b["target_rows"][0].update(
        overall_rank=1)), sb.GATE_COMBINED_OBJECTIVE)


def test_a_q_value_at_the_top_level(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b.update(q_value=0.01)), sb.GATE_PQ_FDR)


def test_an_fdr_nested_in_a_row(tmp_path):
    _refuses(_paths(tmp_path, mutate_bridge=lambda b: b["target_rows"][0].update(fdr=0.05)),
             sb.GATE_PQ_FDR)
