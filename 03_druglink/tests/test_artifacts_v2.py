"""Atomic, content-addressed v2 emission — attacked on identity, refusal and vacuity.

NON-PRODUCTION FIXTURES (see :mod:`candidates_v2_fixture`). Every bundle written here is
``artifact_class="fixture"``: it wears an ``fx_`` id, lands in its own subtree, and declares
``stage4_admission_permitted=false``. No biological candidate is invented anywhere.

NON-VACUITY FIRST. Every test below runs over a bundle whose tables are checked to be NON-EMPTY
before anything about them is trusted. A rerun-determinism test over zero rows is a test that
two empty things are equal.

The properties under attack:

  * the same inputs rebuild the SAME bundle id and the SAME table hashes;
  * permuting rows changes NOTHING scientific;
  * the same id with DIFFERENT bytes is REFUSED — two sciences never wear one identifier;
  * a combined/balanced/weighted objective is refused at top level AND nested;
  * a p/q/FDR alias is refused at top level AND nested;
  * an inferred pathway edge carrying a measured rank is refused;
  * paths and timestamps stay OUT of the content address;
  * v1 stays frozen: Stage 4 binds those bytes, and v2 is a NEW schema id, not a widening.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import random

import pytest

import candidates_v2_fixture as fx
from druglink import artifacts_v2 as av2
from druglink import candidates_v2 as cv2
from druglink import direction as dr
from druglink import schemas, stage2_aggregate as sa
from druglink.hashing import contains_local_path, content_hash, without

# The bytes Stage 4 is bound to. A literal: a pin derived from the thing it pins is not a pin.
FROZEN_V1_SHA256 = "361d0833d5cb099155ac6ad87557c728fcd64feba1e2ccbf7938bd2c6f4c9eed"
SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "..", "schemas")

CREATED_AT = "2026-07-13T00:00:00+00:00"


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("v2_world")
    aggregate, paths = fx.admit(root / "release")
    return {"aggregate": aggregate, "store": fx.store(), "paths": paths,
            "root": str(root)}


def _emit(world, out: str, **over):
    kwargs = {"output_root": out, "artifact_class": "fixture",
              "aggregate": world["aggregate"], "store": world["store"],
              "report_path": world["paths"]["report_path"], "created_at": CREATED_AT}
    kwargs.update(over)
    return av2.emit(**kwargs)


@pytest.fixture(scope="module")
def emitted(world, tmp_path_factory):
    out = str(tmp_path_factory.mktemp("v2_bundle"))
    built = _emit(world, out)
    for name in av2.SCIENTIFIC_TABLES:
        assert built["tables"][name], f"non-vacuity: {name} must not be empty"
    return {**built, "output_root": out}


# --------------------------------------------------------------------------- #
# Identity: derived, reproducible, and blind to paths and clocks.
# --------------------------------------------------------------------------- #
class TestTheSameInputsRebuildTheSameBundle:
    def test_twice_identical_gives_the_same_id_and_the_same_table_hashes(
            self, world, emitted, tmp_path):
        again = _emit(world, str(tmp_path / "second_run"))
        assert again["bundle_id"] == emitted["bundle_id"]
        assert (again["document"]["table_hashes"]
                == emitted["document"]["table_hashes"])
        assert (again["document"]["canonical_content_sha256"]
                == emitted["document"]["canonical_content_sha256"])
        assert (again["document"]["document_sha256"]
                == emitted["document"]["document_sha256"])

    def test_a_different_output_path_and_clock_do_not_move_the_id(self, world, tmp_path):
        first = _emit(world, str(tmp_path / "here"), created_at="2020-01-01T00:00:00+00:00")
        second = _emit(world, str(tmp_path / "elsewhere"),
                       created_at="2031-12-31T23:59:59+00:00")
        assert first["bundle_id"] == second["bundle_id"], (
            "paths and timestamps are OUTSIDE scientific content addressing")

    def test_a_rerun_into_the_same_root_with_a_new_clock_is_not_a_collision(
            self, world, tmp_path):
        out = str(tmp_path / "same_root")
        first = _emit(world, out, created_at="2020-01-01T00:00:00+00:00")
        second = _emit(world, out, created_at="2031-12-31T23:59:59+00:00")
        assert first["bundle_dir"] == second["bundle_dir"]

    def test_the_document_leaks_no_machine_local_path(self, emitted):
        assert contains_local_path(emitted["document"]) == []

    def test_the_document_carries_no_clock_at_all(self, emitted):
        assert "created_at" not in emitted["document"], (
            "a clock in the document makes two runs of identical science differ byte for "
            "byte; 'when' belongs in the manifest, outside the content address")
        with open(os.path.join(emitted["bundle_dir"], "manifest.json")) as fh:
            assert json.load(fh)["created_at"] == CREATED_AT

    def test_the_document_bytes_are_a_pure_function_of_the_content(self, world, emitted,
                                                                   tmp_path):
        again = _emit(world, str(tmp_path / "bytes"),
                      created_at="1999-01-01T00:00:00+00:00")
        name = av2.V2_DOC["fixture"]
        first = open(os.path.join(emitted["bundle_dir"], name), "rb").read()
        second = open(os.path.join(again["bundle_dir"], name), "rb").read()
        assert first == second

    def test_the_identity_is_DERIVED_not_declared(self, emitted):
        doc = emitted["document"]
        assert doc["bundle_id"] == "fx_" + doc["canonical_content_sha256"][:16]
        assert content_hash(without(doc, ("document_sha256",))) == doc["document_sha256"]


class TestRowOrderIsNotScientificContent:
    def test_permuting_every_table_does_not_move_a_single_content_hash(self, emitted):
        shuffled = {}
        rng = random.Random(20260713)
        for name, rows in emitted["tables"].items():
            rows = list(rows)
            rng.shuffle(rows)
            shuffled[name] = rows
        assert any(shuffled[n] != emitted["tables"][n] for n in shuffled), (
            "non-vacuity: the permutation must actually reorder something")
        assert (av2.table_content_hashes(shuffled)
                == av2.table_content_hashes(emitted["tables"]))

    def test_a_permuted_build_writes_the_same_bundle_id(self, world, emitted, tmp_path):
        rng = random.Random(7)
        tables = {n: list(rows) for n, rows in emitted["tables"].items()}
        for rows in tables.values():
            rng.shuffle(rows)
        report = av2.bind_report(world["paths"]["report_path"], world["aggregate"])
        doc = av2.build_document(artifact_class="fixture", aggregate=world["aggregate"],
                                 store=world["store"], report=report, tables=tables,
                                 table_hashes=av2.table_content_hashes(tables))
        assert doc["bundle_id"] == emitted["bundle_id"]
        path = av2.write_bundle(output_root=str(tmp_path / "permuted"),
                                artifact_class="fixture", document=doc,
                                doc_id=doc["bundle_id"], tables=tables,
                                created_at=CREATED_AT)
        assert os.path.basename(path) == emitted["bundle_id"]


class TestTheSameIdWithDifferentBytesIsRefused:
    def test_an_existing_bundle_with_different_content_is_REFUSED(self, world, emitted,
                                                                  tmp_path):
        out = str(tmp_path / "collide")
        _emit(world, out)

        tables = copy.deepcopy(emitted["tables"])
        tables["target_drug_edges"] = tables["target_drug_edges"][:-1]          # different science, same id
        doc = copy.deepcopy(emitted["document"])
        with pytest.raises(av2.ArtifactV2Error) as exc:
            av2.write_bundle(output_root=out, artifact_class="fixture", document=doc,
                             doc_id=emitted["bundle_id"], tables=tables,
                             created_at=CREATED_AT)
        assert exc.value.gate == av2.GATE_ID_COLLISION

    def test_the_refused_write_leaves_the_admitted_bundle_and_no_staging_behind(
            self, world, tmp_path):
        out = str(tmp_path / "collide2")
        first = _emit(world, out)
        before = sorted(os.listdir(first["bundle_dir"]))

        tables = copy.deepcopy(first["tables"])
        tables["candidates"] = tables["candidates"][:1]
        with pytest.raises(av2.ArtifactV2Error):
            av2.write_bundle(output_root=out, artifact_class="fixture",
                             document=first["document"], doc_id=first["bundle_id"],
                             tables=tables, created_at=CREATED_AT)
        assert sorted(os.listdir(first["bundle_dir"])) == before
        leftovers = [d for d in os.listdir(os.path.join(out, "fixtures_only"))
                     if d.startswith(".stage3_v2_staging_")]
        assert leftovers == []


# --------------------------------------------------------------------------- #
# The two vocabularies a v2 bundle may never carry — at ANY depth.
# --------------------------------------------------------------------------- #
def _write(world, emitted, tmp_path, *, document, tables):
    return av2.write_bundle(output_root=str(tmp_path / "refuse"), artifact_class="fixture",
                            document=document, doc_id=emitted["bundle_id"], tables=tables,
                            created_at=CREATED_AT)


class TestNoCombinedObjective:
    @pytest.mark.parametrize("field", ["combined_score", "balanced_skew", "weighted_total",
                                       "overall_score", "composite_evidence"])
    def test_a_combined_field_at_TOP_LEVEL_is_REFUSED(self, world, emitted, tmp_path, field):
        doc = copy.deepcopy(emitted["document"])
        doc[field] = "anything at all"
        with pytest.raises(av2.ArtifactV2Error) as exc:
            _write(world, emitted, tmp_path, document=doc, tables=emitted["tables"])
        assert exc.value.gate == av2.GATE_COMBINED_OBJECTIVE

    def test_a_combined_field_NESTED_in_the_method_block_is_REFUSED(self, world, emitted,
                                                                    tmp_path):
        doc = copy.deepcopy(emitted["document"])
        doc["method"]["weighted_objective"] = 1
        with pytest.raises(av2.ArtifactV2Error) as exc:
            _write(world, emitted, tmp_path, document=doc, tables=emitted["tables"])
        assert exc.value.gate == av2.GATE_COMBINED_OBJECTIVE

    def test_a_combined_field_NESTED_in_a_candidate_row_is_REFUSED(self, world, emitted,
                                                                   tmp_path):
        tables = copy.deepcopy(emitted["tables"])
        tables["candidates"][0]["balanced_evidence_score"] = "0.9"
        with pytest.raises(av2.ArtifactV2Error) as exc:
            _write(world, emitted, tmp_path, document=emitted["document"], tables=tables)
        assert exc.value.gate == av2.GATE_COMBINED_OBJECTIVE

    def test_a_combined_field_NESTED_inside_a_candidate_IN_the_document_is_REFUSED(
            self, world, emitted, tmp_path):
        doc = copy.deepcopy(emitted["document"])
        doc["candidates"][0]["combined_objective"] = {"value": "1"}
        with pytest.raises(av2.ArtifactV2Error) as exc:
            _write(world, emitted, tmp_path, document=doc, tables=emitted["tables"])
        assert exc.value.gate == av2.GATE_COMBINED_OBJECTIVE

    def test_the_negative_declarations_are_NOT_mistaken_for_the_thing_they_forbid(
            self, emitted):
        doc = emitted["document"]
        assert doc["combined_objective_permitted"] is False
        assert doc["headline_arm_permitted"] is False
        assert doc["candidate_rank_permitted"] is False
        av2.check_no_combined_objective(doc)        # must not raise on the honest bundle


class TestNoPValueQValueOrFDR:
    @pytest.mark.parametrize("field", ["p_value", "q_value", "fdr", "padj", "pval",
                                       "adjusted_p_value", "fdr_bh"])
    def test_a_significance_alias_at_TOP_LEVEL_is_REFUSED(self, world, emitted, tmp_path,
                                                          field):
        doc = copy.deepcopy(emitted["document"])
        doc[field] = "0.01"
        with pytest.raises(av2.ArtifactV2Error) as exc:
            _write(world, emitted, tmp_path, document=doc, tables=emitted["tables"])
        assert exc.value.gate == av2.GATE_PQ_FDR

    def test_a_significance_alias_NESTED_in_the_method_block_is_REFUSED(self, world, emitted,
                                                                        tmp_path):
        doc = copy.deepcopy(emitted["document"])
        doc["method"]["benjamini_hochberg"] = True
        with pytest.raises(av2.ArtifactV2Error) as exc:
            _write(world, emitted, tmp_path, document=doc, tables=emitted["tables"])
        assert exc.value.gate == av2.GATE_PQ_FDR

    def test_a_significance_alias_NESTED_in_an_edge_row_is_REFUSED(self, world, emitted,
                                                                   tmp_path):
        tables = copy.deepcopy(emitted["tables"])
        tables["target_drug_edges"][0]["q_val"] = "0.049"
        with pytest.raises(av2.ArtifactV2Error) as exc:
            _write(world, emitted, tmp_path, document=emitted["document"], tables=tables)
        assert exc.value.gate == av2.GATE_PQ_FDR

    def test_the_bundle_says_it_is_not_calibrated(self, emitted):
        assert emitted["document"]["inference_status"] == "not_calibrated"
        assert emitted["document"]["p_q_fdr_permitted"] is False
        av2.check_no_pq_fdr(emitted["document"])   # must not raise on the honest bundle


class TestAnInferredEdgeIsRefusedAMeasuredRank:
    def test_a_pathway_origin_edge_carrying_a_rank_is_REFUSED_at_WRITE(self, world, emitted,
                                                                       tmp_path):
        tables = copy.deepcopy(emitted["tables"])
        edge = next(e for e in tables["target_drug_edges"]
                    if e["origin_type"] == dr.ORIGIN_ENDPOINT_PATHWAY)
        edge["arm_rank"] = 1
        with pytest.raises(cv2.CandidatesV2Error) as exc:
            _write(world, emitted, tmp_path, document=emitted["document"], tables=tables)
        assert exc.value.gate == cv2.GATE_INFERRED_ORIGIN_HAS_A_RANK

    def test_an_origin_swapped_edge_is_REFUSED_at_WRITE(self, world, emitted, tmp_path):
        tables = copy.deepcopy(emitted["tables"])
        edge = next(e for e in tables["target_drug_edges"]
                    if e["origin_type"] == dr.ORIGIN_DIRECT_TARGET)
        edge["origin_type"] = dr.ORIGIN_TEMPORAL_CROSS_TIME
        with pytest.raises(cv2.CandidatesV2Error) as exc:
            _write(world, emitted, tmp_path, document=emitted["document"], tables=tables)
        assert exc.value.gate == cv2.GATE_ORIGIN_LANE_DISAGREE


# --------------------------------------------------------------------------- #
# What the bundle id COMMITS to. Move any one of them, and the id must move.
# --------------------------------------------------------------------------- #
class TestTheBundleIdCommitsToEveryUpstreamIdentity:
    def test_the_canonical_content_names_every_binding(self, emitted):
        doc = emitted["document"]
        agg = doc["stage2_aggregate"]
        assert agg["manifest_raw_sha256"] and agg["manifest_canonical_sha256"]
        assert agg["manifest_self_hash"] and agg["stage1_release_sha256"]
        report = agg["independent_report"]
        assert report["raw_sha256"] and report["canonical_sha256"]
        assert "independent" in report["verifier_id"] and report["verdict"] == "admit"
        assert len(agg["lane_artifacts"]) == sa.N_BUNDLES == 15
        assert all(a["raw_sha256"] and a["canonical_sha256"]
                   for a in agg["lane_artifacts"])

        store = doc["universe_store"]
        assert store["store_id"] and store["typed_universe_sha256"]
        assert [a["content_sha256"] for a in store["source_artifacts"]] and all(
            a["content_sha256"] for a in store["source_artifacts"])

        method = doc["method"]
        assert method["direction_vocabulary_digest"] == dr.vocabulary_digest()
        assert method["workflow_vocabulary_digest"]
        assert method["code_tree_sha256"] and method["env_lock_sha256"]
        assert method["schemas_sha256"]
        assert set(doc["table_hashes"]) == set(av2.SCIENTIFIC_TABLES)

    def test_a_moved_lane_artifact_moves_the_bundle_id(self, world, tmp_path):
        def touch_one_bundle(docs):
            key = f"{sa.LANE_DIRECT}|{sa.CONDITIONS[0]}"
            docs[key]["arms"][0]["records"][0]["arm_value"] = 0.123456

        aggregate, paths = fx.admit(tmp_path / "moved", mutate_bundles=touch_one_bundle)
        moved = av2.emit(output_root=str(tmp_path / "out"), artifact_class="fixture",
                         aggregate=aggregate, store=world["store"],
                         report_path=paths["report_path"], created_at=CREATED_AT)
        base = _emit(world, str(tmp_path / "base"))
        assert moved["bundle_id"] != base["bundle_id"]

    def test_a_different_stage2_manifest_moves_the_bundle_id(self, world, tmp_path):
        aggregate, paths = fx.admit(tmp_path / "other_manifest",
                                    generated_at="2026-07-14T00:00:00Z")
        other = av2.emit(output_root=str(tmp_path / "out2"), artifact_class="fixture",
                         aggregate=aggregate, store=world["store"],
                         report_path=paths["report_path"], created_at=CREATED_AT)
        base = _emit(world, str(tmp_path / "base2"))
        assert other["bundle_id"] != base["bundle_id"], (
            "the aggregate manifest's RAW identity is part of the content address")

    def test_a_different_universe_store_moves_the_bundle_id(self, world, tmp_path):
        rows = [r for r in fx.store_rows() if r["target_id"] != fx.TGT_UNSUPPORTED]
        other = _emit(world, str(tmp_path / "out3"), store=fx.store(rows))
        base = _emit(world, str(tmp_path / "base3"))
        assert other["bundle_id"] != base["bundle_id"]

    def test_a_report_that_admits_another_manifest_is_REFUSED(self, world, tmp_path):
        _, other = fx.admit(tmp_path / "unrelated", generated_at="2026-07-15T00:00:00Z")
        with pytest.raises(av2.ArtifactV2Error) as exc:
            _emit(world, str(tmp_path / "out4"), report_path=other["report_path"])
        assert exc.value.gate == av2.GATE_REPORT_BINDS_ANOTHER_MANIFEST


# --------------------------------------------------------------------------- #
# The bundle on disk.
# --------------------------------------------------------------------------- #
class TestTheBundleOnDisk:
    def test_every_table_and_the_document_and_the_manifest_are_there(self, emitted):
        files = set(os.listdir(emitted["bundle_dir"]))
        assert {f"{n}.parquet" for n in av2.SCIENTIFIC_TABLES} <= files
        assert "manifest.json" in files
        assert av2.V2_DOC["fixture"] in files

    def test_the_manifest_inventories_what_was_actually_written(self, emitted):
        with open(os.path.join(emitted["bundle_dir"], "manifest.json")) as fh:
            manifest = json.load(fh)
        assert manifest["schema_version"] == av2.V2_MANIFEST_SCHEMA
        assert manifest["bundle_id"] == emitted["bundle_id"]
        assert manifest["manifest_sha256"] == content_hash(
            without(manifest, ("manifest_sha256", "created_at")))
        for entry in manifest["files"]:
            path = os.path.join(emitted["bundle_dir"], entry["file"])
            assert hashlib.sha256(open(path, "rb").read()).hexdigest() \
                == entry["file_sha256"]

    def test_the_tables_re_read_from_disk_are_the_tables_that_were_hashed(self, emitted):
        for name in av2.SCIENTIFIC_TABLES:
            rows = av2.read_table(
                os.path.join(emitted["bundle_dir"], f"{name}.parquet"), name)
            assert rows, f"non-vacuity: {name} on disk must not be empty"
            assert (av2.table_content_hash(name, rows)
                    == emitted["document"]["table_hashes"][name])

    def test_a_null_rank_survives_the_round_trip_as_NULL_never_as_a_number(self, emitted):
        rows = av2.read_table(
            os.path.join(emitted["bundle_dir"], "target_drug_edges.parquet"),
            "target_drug_edges")
        unranked = [r for r in rows if r["arm_rank"] is None]
        assert unranked, "non-vacuity: the fixture ships an UNRANKED target"
        assert all(r["arm_rank"] is None for r in rows
                   if r["origin_type"] == dr.ORIGIN_ENDPOINT_PATHWAY)

    def test_the_document_validates_against_the_v2_schema(self, emitted):
        schemas.validate(emitted["document"], av2.V2_SCHEMA, context="v2")

    def test_the_v2_schema_is_a_NEW_id_and_not_a_widened_v1(self):
        with open(os.path.join(SCHEMA_DIR, f"{av2.V2_SCHEMA}.json")) as fh:
            doc = json.load(fh)
        assert doc["$id"] == "spot.stage03_drug_annotation.v2"
        assert doc["properties"]["schema_version"]["const"] == av2.V2_SCHEMA
        origins = doc["$defs"]["origin_type"]["enum"]
        assert set(origins) == set(cv2.V2_ORIGINS)
        assert "pathway_node" not in origins, "the v1 origin does not belong in the v2 lane"


class TestTheFixtureFirewall:
    def test_a_fixture_bundle_lands_apart_and_declares_itself(self, emitted):
        assert emitted["bundle_id"].startswith("fx_")
        assert "fixtures_only" in emitted["bundle_dir"]
        assert emitted["document"]["artifact_class"] == "fixture"
        assert emitted["document"]["stage4_admission_permitted"] is False
        assert emitted["document"]["data_status"] == "synthetic_fixture_only"

    def test_a_fixture_aggregate_can_never_be_emitted_as_an_analysis(self, world, tmp_path):
        with pytest.raises(sa.Stage2AggregateError) as exc:
            _emit(world, str(tmp_path / "laundered"), artifact_class="analysis")
        assert sa.GATE_FIXTURE_FIREWALL in str(exc.value)

    def test_an_analysis_must_bind_the_stores_source_artifact_hashes(self, world):
        store = world["store"]
        unpinned = dataclasses.replace(
            store, manifest={k: v for k, v in store.manifest.items() if k != "extraction"})
        with pytest.raises(av2.ArtifactV2Error) as exc:
            av2.store_binding(unpinned, artifact_class="analysis")
        assert exc.value.gate == av2.GATE_STORE_NOT_ADMITTED
        # ... and the same store is fine for a fixture, which is never admitted downstream.
        assert av2.store_binding(unpinned, artifact_class="fixture")["store_id"]


class TestV1StaysFrozen:
    def test_the_v1_contract_bytes_have_not_moved(self):
        path = os.path.join(SCHEMA_DIR, "spot.stage03_drug_annotation.v1.json")
        got = hashlib.sha256(open(path, "rb").read()).hexdigest()
        assert got == FROZEN_V1_SHA256, (
            f"v1 moved: {got} != pinned {FROZEN_V1_SHA256}. Stage 4 binds these bytes; v2 is "
            "a NEW schema id precisely so v1 never has to be widened.")

    def test_the_v2_document_is_not_a_v1_document(self, emitted):
        assert emitted["document"]["schema_version"] == "spot.stage03_drug_annotation.v2"
        assert av2.V2_DOC["fixture"] != "fixture_drug_annotation.json"
