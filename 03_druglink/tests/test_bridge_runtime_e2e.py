"""END TO END: admitted bytes -> BRIDGE -> v2 bundle -> selection view -> membership receipt.

This is the test the whole lane exists for. It drives the REAL producer chain — the same admission
gates, the same bridge consumer, the same emitter, the same membership verifier production runs —
and requires an actual content-addressed bundle, a SELECTION-BOUND view with rows in it, and a
membership receipt whose verdict is ``admit`` and whose two named ids differ.

WHY THE HAPPY PATH DOES NOT GO THROUGH THE CLI. The CLI additionally opens the UNIVERSE STORE via
``universe_rows.load_store``, which is PINNED to the exact ``store_id`` an independent verifier
admitted. A synthetic store can never satisfy that, and that is the entire point of it — so the
sealed store is loaded the way the rest of this suite loads it, and the CLI's store firewall is
asserted SEPARATELY (``test_the_cli_refuses_a_synthetic_store``) rather than weakened to get a
green tick. The CLI's own happy path is exercised the moment a real admitted store and a real
admitted Stage-2 release are both present; until then this is the honest boundary.

The release is sealed and NON-PRODUCTION (``artifact_class: fixture``, ``FIXTURE_*`` everywhere), so
nothing here is a scientific finding. What is real is the MECHANISM.
"""
from __future__ import annotations

import json
import os

import pytest

import native_aggregate_fixture as NAF
import selection_fixture as SF
from v2_fixture import load_fixture_store, write_store
from druglink import artifacts_v2 as av2
from druglink import bundle_v2 as bv2
from druglink import candidates_v2 as cv2
from druglink import membership_receipt as mr
from druglink import run_stage3
from druglink import selection_v3 as s3
from druglink import selection_view as sv
from druglink import stage2_aggregate as sa
from druglink import view_contract as vc


def _run(root, paths, store_dir, *, selection=None, artifact_class="fixture"):
    argv = ["--v2", "--artifact-class", artifact_class,
            "--stage2-manifest", paths["manifest"],
            "--stage2-report", paths["report"],
            "--bundles-root", paths["bundles_root"],
            "--stage1-release", paths["stage1_release"],
            "--universe-store", store_dir,
            "--stage2-bridge", paths["bridge"],
            "--stage2-bridge-report", paths["bridge_report"],
            "--stage2-bridge-receipt", paths["receipt"],
            "--output-root", os.path.join(str(root), "out")]
    if selection:
        argv += ["--selection", selection]
    return run_stage3.main(argv)


def _selection_file(root, paths, aggregate):
    release = paths["manifest_doc"]["stage1_v3_release"]
    programs = list(aggregate.program_ids)
    doc = SF.selection(
        a_program=programs[0], a_direction="high",
        b_program=programs[1], b_direction="high",
        analysis_mode="within_condition", conditions=[release["conditions"][0]],
        registry_view_sha256=release["registry_scorer_view_canonical_sha256"])
    path = os.path.join(str(root), "selection.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return path


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    """The REAL chain, end to end: admit -> bridge -> join -> emit -> project -> receipt."""
    root = str(tmp_path_factory.mktemp("bridge_e2e"))
    paths = NAF.build(os.path.join(root, "agg"))
    store_dir = write_store(os.path.join(root, "store"))
    store = load_fixture_store(store_dir)

    native = NAF.admit(paths)
    bridge = NAF.admit_bridge(paths, native)
    aggregate = sa.bind_bridge(native, bridge)          # THE JOIN

    tables = cv2.build(artifact_class="fixture", aggregate=aggregate, store=store)
    report = bv2.bind_report(paths["report"], aggregate)
    tables["provenance"] = bv2.provenance_rows(
        aggregate=aggregate, store=store, report=report, method=bv2.method_block(store),
        bridge=bridge)
    document = bv2.build_document(
        artifact_class="fixture", aggregate=aggregate, store=store, report=report,
        table_hashes=av2.table_content_hashes(tables), tables=tables)
    bundle_dir = av2.write_bundle(
        output_root=os.path.join(root, "bundle"), artifact_class="fixture", document=document,
        doc_id=document["bundle_id"], tables=tables, created_at="2026-07-13T00:00:00Z")

    selection = s3.verify(json.load(open(_selection_file(root, paths, aggregate))))
    view = sv.materialize(
        selection=selection, aggregate=aggregate, document=document, tables=tables,
        manifest=paths["manifest_doc"], bundle_dir=bundle_dir,
        admission=sv.admit_receipt(paths["receipt"], aggregate=aggregate,
                                   report_path=paths["report"]))
    vc.validate(dict(view))

    view_path = os.path.join(bundle_dir, "selection_view.json")
    with open(view_path, "w", encoding="utf-8") as fh:
        json.dump(view, fh, sort_keys=True, separators=(",", ":"))
    receipt = mr.emit(view_path=view_path, bundle_dir=bundle_dir)
    mr.write(receipt, os.path.join(bundle_dir, "membership_receipt.json"))

    return {"root": root, "paths": paths, "store_dir": store_dir, "aggregate": aggregate,
            "bridge": bridge, "tables": tables, "document": document,
            "bundle_dir": bundle_dir, "view": view, "receipt": receipt}


def test_the_bridge_makes_the_edges_exist_at_all(chain):
    """THE POINT OF THE LANE. The builder refuses an untyped record BY NAME, so before the bridge
    there was nothing to build from. A nonempty edge table IS the proof it was consumed."""
    tables = chain["tables"]
    assert len(tables["target_drug_edges"]) > 0, "no drug edges: the bridge was not consumed"
    assert len(tables["candidates"]) > 0
    assert len(tables["arm_slots"]) == 300               # every slot, including the empty ones

    # Every edge traces to a MEASURED arm. Pathway sourced none of them.
    assert {e["origin_type"] for e in tables["target_drug_edges"]} <= {
        "direct_target", "temporal_cross_time_measured"}


def test_the_bundle_names_the_bridge_it_stands_on(chain):
    import pandas as pd
    prov = pd.read_parquet(os.path.join(chain["bundle_dir"], "provenance.parquet"))
    kinds = set(prov["kind"])
    assert {"stage2_stage3_bridge", "stage2_stage3_bridge_report",
            "stage2_stage3_receipt"} <= kinds, (
        "a bundle whose typed identities all came from the bridge must NAME it")

    row = prov[prov["kind"] == "stage2_stage3_bridge"].iloc[0]
    assert row["raw_sha256"] == chain["bridge"].bridge_raw_sha256
    # No machine-local path anywhere in a releasable table.
    assert not [c for c in prov.astype(str).values.ravel() if str(c).startswith("/")]


def test_the_membership_receipt_is_emitted_and_reverifies_from_its_own_bytes(chain):
    receipt, bundle_dir = chain["receipt"], chain["bundle_dir"]

    assert receipt["schema_version"] == mr.RECEIPT_SCHEMA == \
        "spot.stage03_membership_receipt.v1"
    assert receipt["verdict"] == mr.ADMIT
    # TWO NAMED IDS, REQUIRED TO DIFFER. A producer that verifies its own output has not been
    # verified, and a boolean is a thing a producer could simply write.
    assert receipt["generator_id"] != receipt["verifier_id"]
    assert receipt["store"]["corroborating_tables_uncovered"] == []
    # The view ref is BUNDLE-RELATIVE. An absolute path names a place on one machine.
    assert not os.path.isabs(receipt["view"]["path"])

    # Re-derived from the BYTES on disk, by the shipped verifier.
    mr.verify(receipt, bundle_dir=bundle_dir)


def test_the_view_is_selection_bound_and_carries_rows(chain):
    view = chain["view"]
    assert view["selection"]["poles"]["A"] != view["selection"]["poles"]["B"]
    assert len(view["selected_arms"]["gene_arm_keys"]) > 0
    # A view that surfaced no candidate would prove the projection ran, not that it works.
    assert len(view["tables"]["target_drug_edges"]) > 0
    assert len(view["tables"]["candidates"]) > 0


def test_the_cli_refuses_a_synthetic_store(chain):
    """The universe-store gate is PINNED to the store an independent verifier admitted. A store
    that is perfectly self-consistent with a universe nobody admitted is what a forgery is."""
    code = _run(chain["root"] + "_cli", chain["paths"], chain["store_dir"])
    assert code == 3


# --- FAIL CLOSED, BEFORE ANY DIRECTORY IS CREATED. -------------------------- #
@pytest.mark.parametrize("kill", ["bridge", "bridge_report", "receipt"])
def test_a_missing_bridge_artifact_writes_no_bundle(tmp_path, kill):
    paths = NAF.build(os.path.join(str(tmp_path), "agg"))
    store_dir = write_store(os.path.join(str(tmp_path), "store"))
    os.remove(paths[kill])
    assert _run(tmp_path, paths, store_dir) == 3
    assert not os.path.exists(os.path.join(str(tmp_path), "out")), \
        "a refused run created an output directory"


def test_an_altered_bridge_writes_no_bundle(tmp_path):
    """The forgery the whole module exists to stop: a re-measured number wearing an admitted
    release's hashes."""
    def forge(bridge):
        bridge["target_rows"][0]["arm_value"] = 99.0
    paths = NAF.build(os.path.join(str(tmp_path), "agg"), mutate_bridge=forge)
    store_dir = write_store(os.path.join(str(tmp_path), "store"))
    assert _run(tmp_path, paths, store_dir) == 3
    assert not os.path.exists(os.path.join(str(tmp_path), "out"))


def test_an_untyped_aggregate_cannot_reach_the_edge_builder(tmp_path):
    """The regression this lane is named for: BEFORE the bridge, the native rows carry no
    namespace and no modality, and a bundle built from them would be built from nothing."""
    from druglink import candidates_v2 as cv2
    from v2_fixture import load_fixture_store
    paths = NAF.build(os.path.join(str(tmp_path), "agg"))
    store = load_fixture_store(write_store(os.path.join(str(tmp_path), "store")))
    native = NAF.admit(paths)                     # NOT bridged
    with pytest.raises(Exception) as exc:
        cv2.build(artifact_class="fixture", aggregate=native, store=store)
    assert "namespace" in str(exc.value).lower()

    # ...and WITH the bridge it builds.
    typed = sa.bind_bridge(native, NAF.admit_bridge(paths, native))
    tables = cv2.build(artifact_class="fixture", aggregate=typed, store=store)
    assert len(tables["target_drug_edges"]) > 0
