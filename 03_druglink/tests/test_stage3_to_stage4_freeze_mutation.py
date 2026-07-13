"""The Stage-3 -> Stage-4 freeze must BITE, not merely be declared.

Stage 4 binds the Stage-3 schema set by SHA. During the v2 producer integration I widened the
`origin_type` enum in the drug-annotation schemas so the engine's three typed origins would
validate — and Stage-4's live-pin guard caught the working tree mid-edit:

    observed  c64264ca…      <- the widened enum (UNCOMMITTED, and reverted)
    pinned    e3a44c01…      <- the frozen fixture, which is what this head ships

That was the freeze doing its job. The change was reverted: a v1 bundle contains only v1
origins, so the frozen document still says so, and the v2 vocabulary lives in the v2 lane
(`direction.v2_origin_vocabulary`) until a v2 bundle actually ships.

These tests exist so the next person cannot make that edit quietly. A byte pin that nobody
attacks is a pin nobody has checked.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))

from druglink import direction as d          # noqa: E402

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "..", "schemas")
FIXTURE_SCHEMA = "spot.fixture.stage03_drug_annotation.v1.json"

# The bytes Stage 4 is bound to. A literal, because a pin derived from the thing it pins is
# not a pin.
PINNED_FIXTURE_SHA256 = \
    "e3a44c01e2129ebdb0c58e309ffa343f0a404d768e6b656543b8c9a5e3b23ce9"



def _sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


class TestTheShippedFixtureIsTheBytesStage4Pinned:
    def test_the_fixture_schema_is_EXACTLY_the_pinned_bytes(self):
        got = _sha256(os.path.join(SCHEMA_DIR, FIXTURE_SCHEMA))
        assert got == PINNED_FIXTURE_SHA256, (
            f"the fixture schema moved: {got[:8]}… != pinned {PINNED_FIXTURE_SHA256[:8]}…. "
            "Stage 4 binds these bytes; do not re-pin to make this pass.")


class TestWideningTheOriginEnumIsCAUGHT:
    """The exact mutation the live-pin guard saw. It must be detectable, not silent."""

    def test_widening_the_origin_enum_MOVES_the_bytes_and_is_caught(self, tmp_path):
        src = os.path.join(SCHEMA_DIR, FIXTURE_SCHEMA)
        dst = str(tmp_path / FIXTURE_SCHEMA)
        shutil.copyfile(src, dst)

        doc = json.load(open(dst))
        widened = [0]

        def walk(o):
            if isinstance(o, dict):
                if isinstance(o.get("enum"), list) and set(o["enum"]) == {
                        "direct_target", "pathway_node"}:
                    o["enum"] = ["direct_target", "temporal_cross_time_measured",
                                 "endpoint_pathway_context", "pathway_node"]
                    widened[0] += 1
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(doc)
        assert widened[0] > 0, "the fixture no longer carries the origin enum to mutate"

        json.dump(doc, open(dst, "w"), indent=2, sort_keys=False)
        open(dst, "a").write("\n")

        mutated = _sha256(dst)
        assert mutated != PINNED_FIXTURE_SHA256, (
            "widening the origin enum did NOT move the bytes — the freeze would not catch it")
        # The exact digest is NOT pinned here. The guard's observation (c64264ca…) came from my
        # working tree with the enum AND its descriptions rewritten; pinning the hash of an
        # edit that no longer exists would be a brittle test of a deleted thing. What must hold
        # forever is the property below: touch this enum and the freeze moves.


class TestTheV2VocabularyNeverLeaksIntoTheFrozenDocument:
    """The root cause. The engine learned two new origins; the frozen v1 document must not."""

    def test_the_frozen_bundle_vocabulary_lists_ONLY_the_v1_origins(self):
        assert d.vocabularies()["origin_types"] == list(d.V1_ORIGIN_TYPES)

    def test_no_v2_origin_string_appears_in_the_frozen_vocabulary(self):
        blob = json.dumps(d.vocabularies())
        assert d.ORIGIN_TEMPORAL_CROSS_TIME not in blob
        assert d.ORIGIN_ENDPOINT_PATHWAY not in blob

    def test_the_bundle_document_builder_uses_the_v1_pair(self):
        # bundle.py writes origin_types straight into the document Stage 4 reads
        src = open(os.path.join(os.path.dirname(__file__), "..", "analysis", "druglink",
                                "bundle.py")).read()
        assert "list(V1_ORIGIN_TYPES)" in src
        assert "list(ORIGIN_TYPES)" not in src, (
            "bundle.py is writing the ENGINE's full origin set into the frozen document")

    def test_the_v2_vocabulary_is_still_available_to_the_v2_lane(self):
        # kept out of the frozen doc, NOT thrown away
        v2v = d.v2_origin_vocabulary()
        assert set(v2v["origin_types"]) == {
            d.ORIGIN_DIRECT_TARGET, d.ORIGIN_TEMPORAL_CROSS_TIME,
            d.ORIGIN_ENDPOINT_PATHWAY}
        assert v2v["combined_objective_permitted"] is False


class TestTheEngineStillResolvesWhatTheDocumentDoesNotAdvertise:
    @pytest.mark.parametrize("origin,expected_support", [
        ("direct_target", True),
        ("temporal_cross_time_measured", True),
        ("endpoint_pathway_context", False),
    ])
    def test_scientific_field_compatibility_is_unchanged_for_v1_consumers(
            self, origin, expected_support):
        # Stage 4 reads directional_evidence_status + observed_perturbation_support. Their
        # MEANING is untouched: observed support still requires a measured origin in a
        # measured status, and an inferred node still never carries it.
        out = d.translate(desired_modulation=d.MOD_DECREASE,
                          effect=d.FUNCTIONAL_INHIBITION, arm_evaluable=True,
                          target_entity_is_single_protein=True, origin_type=origin)
        assert out["observed_perturbation_support"] is expected_support
