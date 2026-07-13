"""END TO END, THROUGH THE REAL CLI: admitted bytes -> bridge -> v2 bundle -> view -> receipt.

This is the test the whole lane exists for. It runs ``run_stage3 --v2`` over a real-shaped Stage-2
release + its bridge + the admitted universe store, and requires an actual content-addressed
bundle, a SELECTION-BOUND view with rows in it, and a membership receipt whose verdict is ``admit``
and whose two named ids differ.

The release is sealed and NON-PRODUCTION (``artifact_class: fixture``, ``FIXTURE_*`` everywhere), so
nothing here is a scientific finding. What is real is the MECHANISM: the same admission gates, the
same bridge consumer, the same emitter, the same membership verifier that production runs.
"""
from __future__ import annotations

import json
import os

import pytest

import native_aggregate_fixture as NAF
import selection_fixture as SF
from v2_fixture import write_store
from druglink import membership_receipt as mr
from druglink import run_stage3
from druglink import stage2_aggregate as sa


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
    root = tmp_path_factory.mktemp("bridge_e2e")
    paths = NAF.build(os.path.join(str(root), "agg"))
    store_dir = write_store(os.path.join(str(root), "store"))
    aggregate = NAF.admit(paths)
    return {"root": str(root), "paths": paths, "store_dir": store_dir,
            "aggregate": aggregate,
            "selection": _selection_file(str(root), paths, aggregate)}


def _bundle_dir(chain):
    out = os.path.join(chain["root"], "out")
    for base, dirs, files in os.walk(out):
        if "manifest.json" in files:
            return base
    raise AssertionError(f"no bundle was written under {out}")


def test_the_cli_consumes_the_bridge_and_emits_a_real_v2_bundle(chain):
    assert _run(chain["root"], chain["paths"], chain["store_dir"],
                selection=chain["selection"]) == 0

    bundle_dir = _bundle_dir(chain)
    with open(os.path.join(bundle_dir, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)

    # THE EDGES ARE REAL. Without the bridge there is no namespace and no modality, and the
    # builder refuses an untyped record by name — so a nonempty edge table IS the proof the
    # bridge was consumed.
    edges = [f for f in manifest["files"] if f["file"] == "target_drug_edges.parquet"][0]
    assert edges["n_rows"] > 0, "no drug edges: the bridge was not consumed"
    assert manifest["combined_objective_permitted"] is False
    assert manifest["p_q_fdr_permitted"] is False


def test_the_bundle_names_the_bridge_it_stands_on(chain):
    _run(chain["root"], chain["paths"], chain["store_dir"], selection=chain["selection"])
    import pandas as pd
    prov = pd.read_parquet(os.path.join(_bundle_dir(chain), "provenance.parquet"))
    kinds = set(prov["kind"])
    assert {"stage2_stage3_bridge", "stage2_stage3_bridge_report",
            "stage2_stage3_receipt"} <= kinds, (
        "a bundle whose typed identities all came from the bridge must NAME it")

    aggregate = chain["aggregate"]
    bridge = NAF.admit_bridge(chain["paths"], aggregate)
    row = prov[prov["kind"] == "stage2_stage3_bridge"].iloc[0]
    assert row["raw_sha256"] == bridge.bridge_raw_sha256
    # No machine-local path anywhere in a releasable table.
    assert not [c for c in prov.astype(str).values.ravel() if str(c).startswith("/")]


def test_the_membership_receipt_is_emitted_and_reverifies_from_its_own_bytes(chain):
    _run(chain["root"], chain["paths"], chain["store_dir"], selection=chain["selection"])
    bundle_dir = _bundle_dir(chain)

    with open(os.path.join(bundle_dir, "membership_receipt.json"), encoding="utf-8") as fh:
        receipt = json.load(fh)

    assert receipt["schema_version"] == mr.RECEIPT_SCHEMA == \
        "spot.stage03_membership_receipt.v1"
    assert receipt["verdict"] == mr.ADMIT
    # TWO NAMED IDS, REQUIRED TO DIFFER. A producer that verifies its own output has not been
    # verified, and a boolean is a thing a producer can simply write.
    assert receipt["generator_id"] != receipt["verifier_id"]
    assert receipt["store"]["corroborating_tables_uncovered"] == []
    # The view ref is BUNDLE-RELATIVE.
    assert not os.path.isabs(receipt["view"]["path"])

    # Re-derived from the bytes on disk, by the shipped verifier.
    mr.verify(receipt, bundle_dir=bundle_dir)


def test_the_view_is_selection_bound_and_carries_rows(chain):
    _run(chain["root"], chain["paths"], chain["store_dir"], selection=chain["selection"])
    with open(os.path.join(_bundle_dir(chain), "selection_view.json"), encoding="utf-8") as fh:
        view = json.load(fh)

    assert view["selection"]["poles"]["A"] != view["selection"]["poles"]["B"]
    assert len(view["selected_arms"]["gene_arm_keys"]) > 0
    # A view that surfaced no candidate would prove the projection ran, not that it works.
    assert len(view["tables"]["target_drug_edges"]) > 0
    assert len(view["tables"]["candidates"]) > 0


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
