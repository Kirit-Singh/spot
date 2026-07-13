"""WHICH RUN THIS IS. Declared before, never inferred after.

THE ONE THAT MATTERS: a PARTIAL full run (GO-BP produced, Reactome missing) and a COMPLETE
GO-BP-only run ship IDENTICAL BUNDLES — 3 direct, 6 temporal, 3 pathway. Nothing you can read
off the artifacts tells them apart. Weakening the 15-slot completeness check would have
silently admitted the first as the second, and the failure it was hiding is exactly the one
nobody would ever look for again.

So the declaration — bound and hashed BEFORE any bundle exists — is the only thing that can
distinguish them, and these tests are about proving it does.
"""
from __future__ import annotations

import os
import sys

import pytest
from direct import run_topology as T

# the verifier's modules load FLAT — as the verifier process loads them, never through the
# producer's package
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "analysis", "direct"))
from direct.arm_topology import LANE_DIRECT, LANE_PATHWAY, LANE_TEMPORAL, RunManifestError

CONDITIONS = ["Rest", "Stim8hr", "Stim48hr"]
PROGRAMS = [f"prog_{i}" for i in range(10)]

FULL = "spot.stage02.topology.full.v1"
GO = "spot.stage02.topology.go_bp.v1"


def _discovered(bound):
    """Exactly the bundles the topology expects — a complete run."""
    return {lane: list(keys) for lane, keys in bound["expected_bundles"].items()}


def _sources(bound):
    return list(bound["pathway_sources"])


class TestTheTwoTopologiesAreDIFFERENTRunsNotOneRelaxed:
    def test_the_GO_topology_is_3_plus_6_plus_3(self):
        b = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)
        assert b["n_expected_bundles"] == {LANE_DIRECT: 3, LANE_TEMPORAL: 6, LANE_PATHWAY: 3}
        assert b["n_expected_bundles_total"] == 12
        assert b["pathway_sources"] == ["GO-BP"]
        assert b["parked_sources"] == ["Reactome"]

    def test_the_LEGACY_full_topology_is_UNCHANGED_at_3_plus_6_plus_6(self):
        """Not weakened. A run declared FULL and missing Reactome still refuses."""
        b = T.binding(FULL, programs=PROGRAMS, conditions=CONDITIONS)
        assert b["n_expected_bundles"] == {LANE_DIRECT: 3, LANE_TEMPORAL: 6, LANE_PATHWAY: 6}
        assert b["n_expected_bundles_total"] == 15
        assert b["pathway_sources"] == ["GO-BP", "Reactome"]
        assert b["parked_sources"] == []           # Reactome is IN this topology

    def test_the_two_topologies_HASH_DIFFERENTLY(self):
        g = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)
        f = T.binding(FULL, programs=PROGRAMS, conditions=CONDITIONS)
        assert g["topology_sha256"] != f["topology_sha256"]

    def test_the_hash_covers_the_COMPLETE_EXPECTED_SET(self):
        """Sources, every expected bundle key, every expected arm slot — so nothing about what
        the run was FOR can change without the hash moving."""
        b = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)
        for field in ("pathway_sources", "expected_bundles", "expected_arm_slots",
                      "conditions", "programs"):
            assert field in b
        # 10 programs x 2 changes x 3 conditions x 1 source
        assert b["n_expected_arm_slots"][LANE_PATHWAY] == 60
        assert b["n_expected_arm_slots"][LANE_DIRECT] == 60
        assert b["n_expected_arm_slots"][LANE_TEMPORAL] == 120

    def test_REACTOME_is_PARKED_not_DELETED(self):
        assert "Reactome" in T.PARKED_SOURCES
        assert "Reactome" in T.TOPOLOGIES[FULL]["pathway_sources"]      # still there
        assert "Reactome" not in T.TOPOLOGIES[GO]["pathway_sources"]


class TestACompleteRunADMITS:
    def test_a_COMPLETE_GO_run_ADMITS(self):
        b = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)
        assert T.verify(b, discovered=_discovered(b), sources_seen=_sources(b)) == []

    def test_a_COMPLETE_FULL_run_ADMITS(self):
        b = T.binding(FULL, programs=PROGRAMS, conditions=CONDITIONS)
        assert T.verify(b, discovered=_discovered(b), sources_seen=_sources(b)) == []


class TestTheAttacks:
    def test_OMITTING_a_required_GO_bundle_REFUSES(self):
        b = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)
        d = _discovered(b)
        d[LANE_PATHWAY] = d[LANE_PATHWAY][:-1]          # 2 of 3
        bad = T.verify(b, discovered=d, sources_seen=_sources(b))
        assert any(T.G_INCOMPLETE in x for x in bad)
        assert any("unfinished" in x for x in bad)

    def test_INSERTING_REACTOME_under_the_GO_topology_REFUSES(self):
        """Not a bonus. A run that produced a parked source did not do what it declared."""
        b = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)
        d = _discovered(b)
        d[LANE_PATHWAY] = d[LANE_PATHWAY] + ["Rest|Reactome"]
        bad = T.verify(b, discovered=d, sources_seen=["GO-BP", "Reactome"])
        assert any(T.G_FOREIGN_SOURCE in x for x in bad)
        assert any("PARKED" in x for x in bad)

    def test_a_PARTIAL_FULL_run_RELABELLED_as_GO_ONLY_REFUSES(self):
        """THE ONE THAT MATTERS.

        A full run that produced GO-BP and never produced Reactome has EXACTLY the bundles a
        complete GO-only run has. The bundles cannot tell you which it was. Only the
        declaration can — so relabelling it moves the hash, and the run refuses.
        """
        full = T.binding(FULL, programs=PROGRAMS, conditions=CONDITIONS)
        go = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)

        # the bundles a partial FULL run produced ARE the bundles a complete GO run produces
        partial_full_bundles = _discovered(go)
        assert partial_full_bundles[LANE_PATHWAY] == go["expected_bundles"][LANE_PATHWAY]

        # ...so the forger keeps the FULL run's hash and swaps the label to GO
        # ...so the forger takes the FULL run's declaration and swaps its label to GO
        relabelled = dict(full, topology_id=go["topology_id"], label=go["label"])
        bad = T.verify(relabelled, discovered=partial_full_bundles, sources_seen=["GO-BP"])
        assert any(T.G_RELABELLED in x for x in bad)

        # ...and resealing the hash does not help: the BODY still says GO-BP + Reactome
        from direct.hashing import content_hash
        resealed = dict(relabelled)
        resealed.pop("topology_sha256")
        resealed["topology_sha256"] = content_hash(resealed)
        bad = T.verify(resealed, discovered=partial_full_bundles, sources_seen=["GO-BP"])
        assert any(T.G_RELABELLED in x for x in bad)
        assert any("IDENTICAL BUNDLES" in x for x in bad)

    def test_a_PARTIAL_FULL_run_LEFT_LABELLED_FULL_still_REFUSES(self):
        """The legacy topology is NOT weakened: Reactome missing is still incomplete."""
        full = T.binding(FULL, programs=PROGRAMS, conditions=CONDITIONS)
        go = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)
        bad = T.verify(full, discovered=_discovered(go), sources_seen=["GO-BP"])
        assert any(T.G_INCOMPLETE in x for x in bad)

    def test_an_UNKNOWN_topology_REFUSES(self):
        with pytest.raises(RunManifestError, match="not a defined topology"):
            T.binding("spot.stage02.topology.whatever.v9", programs=PROGRAMS,
                      conditions=CONDITIONS)

    def test_a_TAMPERED_source_list_REFUSES(self):
        """Editing the bound source list moves the hash."""
        b = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)
        b["pathway_sources"] = ["GO-BP", "Reactome"]
        bad = T.verify(b, discovered=_discovered(b), sources_seen=["GO-BP"])
        assert any(T.G_RELABELLED in x for x in bad)

    def test_a_REORDERED_condition_list_is_a_DIFFERENT_topology(self):
        a = T.binding(GO, programs=PROGRAMS, conditions=["Rest", "Stim8hr", "Stim48hr"])
        z = T.binding(GO, programs=PROGRAMS, conditions=["Stim48hr", "Stim8hr", "Rest"])
        assert a["topology_sha256"] != z["topology_sha256"]


class TestTheTemporalPathwayExtensionIsSEPARATELYTyped:
    """An endpoint enrichment and a difference-in-differences enrichment are different
    scientific objects. Counting them in one lane would put the wrong number under the wrong
    question."""

    def test_it_is_DECLARED_ABSENT_and_NOT_required(self):
        b = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)
        ext = b["extensions"][T.EXT_TEMPORAL_PATHWAY]
        assert ext["status"] == "not_available"
        assert ext["required"] is False
        assert ext["producer_exists"] is False
        assert b["extension_lanes_required"] == []

    def test_it_is_NOT_folded_into_the_pathway_count(self):
        b = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)
        # 3 within-condition endpoint bundles. NOT 3 + 6 temporal-pathway bundles.
        assert b["n_expected_bundles"][LANE_PATHWAY] == 3
        assert b["pathway_scope"] == "within_condition_endpoint"

    def test_an_UNDECLARED_temporal_pathway_bundle_REFUSES(self):
        b = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)
        d = _discovered(b)
        d[T.EXT_TEMPORAL_PATHWAY] = ["Rest->Stim48hr|GO-BP"]
        bad = T.verify(b, discovered=d, sources_seen=_sources(b))
        assert any(T.G_EXTENSION_UNDECLARED in x for x in bad)
        assert any("category error" in x for x in bad)


class TestStage3DerivesFromTheManifestAndNeverHardcodes15:
    def test_the_binding_carries_EVERYTHING_stage3_needs(self):
        """Stage-3 reads the expected keys and sources FROM THE ADMITTED MANIFEST. It must
        never carry a 15 of its own."""
        b = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)
        assert b["expected_bundles"] and b["expected_arm_slots"]
        assert b["pathway_sources"] and b["n_expected_bundles_total"] == 12
        assert b["topology_id"] and b["topology_sha256"]

    def test_the_expected_TOTAL_moves_with_the_TOPOLOGY_not_a_constant(self):
        assert T.binding(GO, programs=PROGRAMS,
                         conditions=CONDITIONS)["n_expected_bundles_total"] == 12
        assert T.binding(FULL, programs=PROGRAMS,
                         conditions=CONDITIONS)["n_expected_bundles_total"] == 15
        # ...and with the conditions, too. Nothing here is a literal.
        assert T.binding(GO, programs=PROGRAMS,
                         conditions=["Rest", "Stim48hr"])["n_expected_bundles_total"] == 2 + 2 + 2


# --------------------------------------------------------------------------- #
# WIRED: the topology is bound into the RUN IDENTITY at preflight and into the MANIFEST,
# and the VERIFIER re-derives it on load through its OWN restatement.
# --------------------------------------------------------------------------- #
class TestItIsBOUNDIntoTheRunIdentityAndTheManifest:
    def test_the_SCHEDULER_declares_the_GO_topology_and_binds_it_into_the_run_identity(self):
        from direct import stage2_run as S
        assert S.RUN_TOPOLOGY_ID == GO
        # ...and it RUNS only what it declared: Reactome is parked, not invoked
        assert S.SOURCES == ("go_bp",)

    def test_the_scheduler_SOURCES_are_DERIVED_from_the_topology_not_a_literal(self):
        from direct import stage2_run as S
        assert S.SOURCES == T.file_keys(S.RUN_TOPOLOGY_ID)
        assert T.file_keys(FULL) == ("go_bp", "reactome")     # the legacy one is unchanged

    def test_the_MANIFEST_binds_the_topology_and_NARROWS_the_sources(self):
        """The exact source list comes from the TOPOLOGY, not from whatever the release ships."""
        from direct.hashing import content_hash
        b = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)
        assert b["pathway_sources"] == ["GO-BP"]
        assert b["topology_sha256"] == content_hash(
            {k: v for k, v in b.items() if k != "topology_sha256"})


class TestTheVERIFIERReDerivesOnLoad:
    """Through its OWN restatement — a verifier that imported the producer's topology would
    derive the expected set exactly as the producer did and could never catch it wrong."""

    def _manifest(self, bound, bundles):
        return {"run_topology": bound, "bundles": bundles}

    def _bundles(self, conditions, sources):
        out = []
        for c in conditions:
            out.append({"lane": "direct", "context": {"condition": c}})
            for s in sources:
                out.append({"lane": "pathway",
                            "context": {"condition": c, "gene_set_source": s}})
        for a in sorted(conditions):
            for z in sorted(conditions):
                if a != z:
                    out.append({"lane": "temporal",
                                "context": {"from_condition": a, "to_condition": z}})
        return out

    def test_a_COMPLETE_GO_run_ADMITS(self):
        import verify_topology_rules as VT
        b = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)
        m = self._manifest(b, self._bundles(CONDITIONS, ["GO-BP"]))
        from direct.verify_run_manifest import check_run_topology
        assert check_run_topology(m) == []
        assert VT.TOPOLOGY_SOURCES[GO] == ("GO-BP",)

    def test_ONE_MISSING_GO_bundle_REFUSES(self):
        from direct.verify_run_manifest import check_run_topology
        b = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)
        bundles = [x for x in self._bundles(CONDITIONS, ["GO-BP"])
                   if not (x["lane"] == "pathway"
                           and x["context"]["condition"] == "Rest")]
        bad = check_run_topology(self._manifest(b, bundles))
        assert any("does_not_fill_every_bundle" in x for x in bad)

    def test_INSERTING_REACTOME_under_the_GO_topology_REFUSES(self):
        from direct.verify_run_manifest import check_run_topology
        b = T.binding(GO, programs=PROGRAMS, conditions=CONDITIONS)
        bundles = self._bundles(CONDITIONS, ["GO-BP"]) + [
            {"lane": "pathway", "context": {"condition": "Rest",
                                            "gene_set_source": "Reactome"}}]
        bad = check_run_topology(self._manifest(b, bundles))
        assert any("pathway_source_its_declared_topology_does_not_include" in x for x in bad)
        assert any("PARKED" in x for x in bad)

    def test_a_PARTIAL_FULL_run_RELABELLED_as_GO_ONLY_REFUSES_on_HASH(self):
        """THE ONE THAT MATTERS. Identical bundles; only the declaration differs."""
        from direct.hashing import content_hash
        from direct.verify_run_manifest import check_run_topology

        full = T.binding(FULL, programs=PROGRAMS, conditions=CONDITIONS)
        bundles = self._bundles(CONDITIONS, ["GO-BP"])       # a partial FULL run's bundles

        # left labelled FULL -> INCOMPLETE (the legacy check is not weakened)
        bad = check_run_topology(self._manifest(full, bundles))
        assert any("does_not_fill_every_bundle" in x for x in bad)

        # relabelled GO-only, resealed -> the BODY still says GO-BP + Reactome
        relabelled = dict(full, topology_id=GO)
        relabelled.pop("topology_sha256")
        relabelled["topology_sha256"] = content_hash(relabelled)
        bad = check_run_topology(self._manifest(relabelled, bundles))
        assert any("does_not_re_derive_from_the_topology_it_names" in x for x in bad)
        assert any("IDENTICAL BUNDLES" in x for x in bad)

    def test_a_manifest_declaring_NO_topology_refuses_in_PRODUCTION(self):
        from direct.verify_run_manifest import check_run_topology
        m = self._manifest(None, [])
        assert check_run_topology(m) == []                    # legacy path: tolerated
        bad = check_run_topology(m, require_declared=True)    # production: refused
        assert any("declares_no_run_topology" in x for x in bad)
