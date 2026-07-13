"""THE PATHWAY LANE'S OWN external-admission schema — on the NATIVE inventory path.

There is exactly ONE pathway inventory builder: `python -m direct.release_inventory --lane
pathway`, which emits `pathway_arm_release.json` (spot.stage02_pathway_arm_release.v1) and is
validated by W4. The standalone `pathway_release.py` producer was a DUPLICATE of it and has
been removed; these are the checks worth keeping from its test.

What they defend: the pathway lane declared TEMPORAL's external-admission schema. That string
is what decides WHICH CONTRACT a report must satisfy before it may admit a lane — so the
pathway lane was demanding, and the aggregate accepting, a report that declares in its own
schema field that it is about the TEMPORAL lane's bytes.
"""
from __future__ import annotations

from direct import release_inventory as RI
from direct import verify_release_envelope as E
from direct.verify_lane_admission import NATIVE


class TestTheOneNativePathwayInventoryBuilder:
    def test_release_inventory_IS_the_pathway_inventory_builder(self):
        assert RI.INVENTORY_FILE_OF["pathway"] == "pathway_arm_release.json"
        assert RI.SCHEMA_OF["pathway"] == "spot.stage02_pathway_arm_release.v1"

    def test_there_is_no_standalone_pathway_release_producer(self):
        """A second producer for one artifact is a second answer to one question."""
        import importlib
        try:
            importlib.import_module("direct.pathway_release")
        except ModuleNotFoundError:
            return
        raise AssertionError("direct.pathway_release still exists; the only pathway inventory "
                             "builder is `direct.release_inventory --lane pathway`")


class TestEveryLaneDeclaresITSOWNAdmissionSchema:
    def test_every_lane_has_a_DISTINCT_admission_schema(self):
        schemas = E.ADMISSION_SCHEMA_OF
        assert len(set(schemas.values())) == len(schemas)      # no two lanes share one
        assert schemas["pathway"] == "spot.stage02_pathway_arm_external_admission.v1"
        assert schemas["temporal"] == "spot.stage02_temporal_arm_external_admission.v1"

    def test_a_TEMPORAL_report_may_not_admit_the_PATHWAY_lane(self):
        assert E.ADMISSION_SCHEMA_OF["pathway"] != E.ADMISSION_SCHEMA_OF["temporal"]
        assert "temporal" not in E.ADMISSION_SCHEMA_OF["pathway"]

    def test_the_aggregates_lane_adapter_agrees_with_the_envelope(self):
        """If the envelope and the adapter ever disagree about which report admits a lane,
        that lane can never be admitted at all — a failure that looks like a broken verifier."""
        for lane in ("temporal", "pathway"):
            assert NATIVE[lane]["schema_version"] == E.ADMISSION_SCHEMA_OF[lane]
