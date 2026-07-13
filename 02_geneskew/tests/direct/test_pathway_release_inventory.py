"""BLOCKER 7 (pathway): a real producer for the pathway ROOT INVENTORY.

The aggregate verifier demanded a per-lane producer inventory ``pathway_arm_release.json``
(schema ``spot.stage02_pathway_arm_release.v1``) that NOTHING in the integration tree wrote.
This is that producer. Its inventory is the exact contract ``verify_release_envelope``
consumes: content-addressed, byte-true, and PENDING — the producer never admits itself.

The bundles are FIXTURES (``fixtures_run_manifest``); the topology (3 conditions x 2 sources)
is real, and so is the consistency check against the verifier module that reads the inventory.
"""
from __future__ import annotations

import json
import os

import fixtures_run_manifest as F
import pytest
from direct import verify_release_envelope as E
from direct import pathway_release as PR


def _six(tmp_path):
    """Six real-shaped pathway bundles: the full 3-condition x 2-source grid, once each."""
    staged = F.stage_release(tmp_path)
    root = os.path.join(str(tmp_path), "bundles")
    conds, sources = staged["conditions"], staged["sources"]
    dirs = [F.build_bundle(root, "pathway", {"condition": c, "gene_set_source": s}, staged)
            for c in conds for s in sources]
    return root, dirs, staged, list(conds), list(sources)


def _expect_arms(dirs):
    return sum(len(json.load(open(os.path.join(d, "arm_bundle.json")))["arms"])
               for d in dirs)


class TestTheCanonicalNameAndSchemaAgreeWithTheVerifier:
    def test_the_filename_and_schema_are_the_ONES_the_aggregate_reads(self):
        assert PR.RELEASE_FILENAME == E.INVENTORY_FILE_OF["pathway"]
        assert PR.SCHEMA_RELEASE == E.INVENTORY_SCHEMA_OF["pathway"]


class TestTheCompleteGridProducesAContentAddressedPendingInventory:
    def test_six_bundles_are_bound_into_ONE_pending_inventory(self, tmp_path):
        root, dirs, _staged, conds, sources = _six(tmp_path)
        doc = PR.build_release(dirs, root, conditions=conds, sources=sources)

        assert doc["schema_version"] == "spot.stage02_pathway_arm_release.v1"
        assert doc["lane"] == "pathway"
        assert doc["n_bundles"] == 6
        assert doc["topology"]["expected_n_bundles"] == 6
        assert len({b["bundle_id"] for b in doc["bundles"]}) == 6
        # the ONLY honest producer state
        assert doc["external_admission"]["status"] == "pending"
        assert doc["external_admission"]["required_verifier_id"] == (
            "spot.stage02.pathway.arm.independent_verifier.v1")

    def test_the_release_id_FOLLOWS_the_content(self, tmp_path):
        root, dirs, _staged, conds, sources = _six(tmp_path)
        doc = PR.build_release(dirs, root, conditions=conds, sources=sources)
        derived = E.self_hash(doc, "release_id")
        assert doc["release_id"] == derived
        # ...and editing the inventory breaks the address
        tampered = dict(doc, n_bundles=99)
        assert E.self_hash(tampered, "release_id") != doc["release_id"]

    def test_the_inventory_is_written_at_the_release_root(self, tmp_path):
        root, dirs, _staged, conds, sources = _six(tmp_path)
        PR.build_release(dirs, root, conditions=conds, sources=sources)
        path = os.path.join(root, "pathway_arm_release.json")
        assert os.path.exists(path)
        # no machine-local path leaks into the portable inventory
        assert "/tmp/" not in open(path).read()


class TestTheProducerInventoryPASSESTheVerifierThatReadsIt:
    """The whole point of the reconciliation: producer and verifier agree, byte for byte."""

    def test_check_inventory_accepts_the_producers_own_output(self, tmp_path):
        root, dirs, _staged, conds, sources = _six(tmp_path)
        PR.build_release(dirs, root, conditions=conds, sources=sources)
        inv, problems = E.check_inventory(root, expect_bundles=6,
                                          expect_arms=_expect_arms(dirs), lane="pathway")
        assert problems == [], problems
        assert inv is not None

    def test_a_TAMPERED_bundle_byte_is_caught_by_the_verifier(self, tmp_path):
        root, dirs, _staged, conds, sources = _six(tmp_path)
        PR.build_release(dirs, root, conditions=conds, sources=sources)
        # replace a bound file's bytes AFTER the inventory hashed them
        victim = os.path.join(dirs[0], "convergence.json")
        with open(victim, "w") as fh:
            json.dump({"tampered": True}, fh)
        _inv, problems = E.check_inventory(root, expect_bundles=6,
                                           expect_arms=_expect_arms(dirs), lane="pathway")
        assert problems, "the verifier must catch a byte that moved under a bound name"


class TestAnIncompleteOrDuplicatedGridIsREFUSED:
    def test_a_MISSING_cell_5_of_6_is_refused(self, tmp_path):
        root, dirs, _staged, conds, sources = _six(tmp_path)
        with pytest.raises(PR.PathwayReleaseError) as exc:
            PR.build_release(dirs[:-1], root, conditions=conds, sources=sources)
        assert exc.value.reason == PR.REFUSE_MISSING_CELL

    def test_a_DUPLICATE_cell_is_refused(self, tmp_path):
        root, dirs, _staged, conds, sources = _six(tmp_path)
        with pytest.raises(PR.PathwayReleaseError) as exc:
            PR.build_release(dirs + [dirs[0]], root, conditions=conds, sources=sources)
        assert exc.value.reason == PR.REFUSE_DUPLICATE_CELL

    def test_a_source_the_release_never_shipped_is_refused(self, tmp_path):
        root, dirs, _staged, conds, _sources = _six(tmp_path)
        with pytest.raises(PR.PathwayReleaseError) as exc:
            # the release only ships the two real sources; nominate one it did not
            PR.build_release(dirs, root, conditions=conds, sources=["ONLY-ONE-SOURCE"])
        assert exc.value.reason == PR.REFUSE_UNKNOWN_CELL

    def test_ZERO_bundles_is_not_a_release(self, tmp_path):
        with pytest.raises(PR.PathwayReleaseError) as exc:
            PR.build_release([], str(tmp_path))
        assert exc.value.reason == PR.REFUSE_NO_BUNDLES


class TestThePathwayLaneDeclaresITSOWNAdmissionSchema:
    """It declared TEMPORAL's — and that string is what decides which contract a report must
    satisfy. A pathway release demanding a temporal report would be admitted by a report that
    says, in its own schema field, that it is about a different lane's bytes."""

    def test_the_required_report_schema_is_the_PATHWAY_one(self):
        from direct import pathway_release
        assert (pathway_release.REQUIRED_REPORT_SCHEMA
                == "spot.stage02_pathway_arm_external_admission.v1")
        assert "temporal" not in pathway_release.REQUIRED_REPORT_SCHEMA

    def test_every_lane_has_a_DISTINCT_admission_schema(self):
        from direct import verify_release_envelope as E
        schemas = E.ADMISSION_SCHEMA_OF
        assert len(set(schemas.values())) == len(schemas)     # no two lanes share one
        assert schemas["pathway"] == "spot.stage02_pathway_arm_external_admission.v1"
        assert schemas["temporal"] == "spot.stage02_temporal_arm_external_admission.v1"

    def test_the_lane_ADAPTER_and_the_PRODUCER_agree(self):
        """The producer says which report it requires; the aggregate says which it accepts.
        If those two strings ever differ, the lane can never be admitted at all."""
        from direct import pathway_release
        from direct.verify_lane_admission import NATIVE
        assert (NATIVE["pathway"]["schema_version"]
                == pathway_release.REQUIRED_REPORT_SCHEMA)

    def test_a_TEMPORAL_report_may_not_admit_the_PATHWAY_lane(self):
        from direct import verify_release_envelope as E
        assert E.ADMISSION_SCHEMA_OF["pathway"] != E.ADMISSION_SCHEMA_OF["temporal"]
