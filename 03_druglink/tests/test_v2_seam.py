"""THE v2 SEAM, END TO END, OVER THE REAL ADMITTED UNIVERSE STORE.

The Stage-2 side is a SEALED PLUMBING release. There is NO admitted Stage-2 aggregate on either
host — so none is invented, none is fabricated, and nothing here is presented as a Stage-2
result. What is REAL is the universe STORE: its 11,526 typed targets and its 2,262 VERBATIM
ChEMBL assertions, admitted by an independent verifier and pinned by store_id 625c921f…. The
plumbing arms carry the store's OWN typed identities, so the arm->target join is exercised
against real source assertions rather than invented ones.

NOTHING HERE IS A SCIENTIFIC RESULT. The candidate counts are PLUMBING: they prove the seam
carries evidence end to end and assert nothing biological about any gene or any drug. Every
bundle is emitted as artifact_class="fixture", wears an fx_ id, lands in its own subtree, and
can never reach Stage 4 — and the last test proves that an ANALYSIS run REFUSES, by name,
precisely because no admitted Stage-2 aggregate exists to stand on.
"""
from __future__ import annotations

import os

import pytest

import candidates_v2_fixture as fx
import universe_store_fixture as USF
from druglink import artifacts_v2 as av2
from druglink import stage2_aggregate as sa

CREATED_AT = "2026-07-13T00:00:00+00:00"


# --------------------------------------------------------------------------- #
# THE SEAM, END TO END, OVER THE REAL ADMITTED UNIVERSE STORE.
#
# The Stage-2 side is the SEALED PLUMBING release: there is NO admitted Stage-2 aggregate on
# either host, so none is invented and none is fabricated. What is REAL here is the store — its
# 11,526 typed targets and 2,262 verbatim ChEMBL assertions — and the arms carry the store's
# OWN typed identities, so the join is exercised against real source assertions.
#
# NOTHING BELOW IS A SCIENTIFIC RESULT. The candidate counts are PLUMBING: they prove the seam
# carries evidence end to end, and they assert nothing biological about any gene or any drug.
# The bundle is emitted as artifact_class="fixture", wears an fx_ id, and can never reach
# Stage 4.
# --------------------------------------------------------------------------- #
needs_real_store = pytest.mark.skipif(
    not os.path.isdir(fx.REAL_STORE),
    reason=f"the admitted universe store is not on this host ({fx.REAL_STORE})")


@pytest.fixture(scope="module")
def real_world(tmp_path_factory):
    from druglink import universe_rows as ur
    store = ur.load_store(fx.REAL_STORE)          # the GATED path: pins the admitted store_id
    root = tmp_path_factory.mktemp("real_seam")
    aggregate, paths = fx.admit(root / "release",
                                targets=fx.real_store_targets(store))
    return {"aggregate": aggregate, "store": store, "paths": paths, "root": str(root)}


@needs_real_store
class TestTheSeamOverTheRealAdmittedStore:
    def test_the_store_RECOMPUTES_the_admitted_universe_from_its_own_bytes(self, real_world):
        """Every number is re-derived from the store's rows — never quoted from a document."""
        store = real_world["store"]
        assert store.store_id == USF.ADMITTED_STORE_ID
        assert store.typed_universe_sha256 == USF.ADMITTED_UNIVERSE_SHA

        counts = fx.universe_counts(store)
        assert counts["n_typed_targets"] == 11_526
        assert counts["n_source_assertions"] == 2_262
        assert counts["n_rankable_assertions"] == 2_227
        assert counts["n_variant_non_rankable"] == 29
        assert counts["n_ambiguous_non_rankable"] == 6
        assert counts["n_targets_with_drug_evidence"] == 505
        assert counts["n_molecules"] == 1_923

    def test_the_emitted_bundle_is_NON_EMPTY_and_stands_on_REAL_source_assertions(
            self, real_world, tmp_path):
        built = av2.emit(output_root=str(tmp_path / "out"), artifact_class="fixture",
                         aggregate=real_world["aggregate"], store=real_world["store"],
                         report_path=real_world["paths"]["report_path"],
                         created_at=CREATED_AT)
        tables = built["tables"]
        assert len(tables["arm_slots"]) == sa.N_ARM_SLOTS == 300
        assert tables["target_drug_edges"], "a vacuous bundle would prove nothing"
        assert tables["candidates"] and tables["source_records"]

        # The edges stand on REAL ChEMBL rows, each addressable in a REAL release.
        edge = tables["target_drug_edges"][0]
        assert edge["source_locator"].startswith("chembl:CHEMBL_37:drug_mechanism/")
        assert edge["source_release"] == "CHEMBL_37"

        record = tables["source_records"][0]
        assert record["source_license"] == "CC BY-SA 3.0"
        assert record["source_sha256"] and record["source_required_attribution"]

        # The NON-rankable lanes travelled with the result rather than being dropped.
        lanes = {r["assertion_lane"] for r in tables["source_records"]}
        assert "variant_specific_non_rankable" in lanes
        assert "ambiguous_identity_non_rankable" in lanes
        assert not any(e["assertion_lane"] != "general_gene_rankable"
                       for e in tables["target_drug_edges"]), "only the general lane ranks"

        # A target the admitted store does NOT cover is NAMED, never silently absent.
        states = {d["state"] for d in tables["dispositions"]}
        assert "target_not_in_admitted_typed_universe" in states
        assert "target_carries_no_source_drug_assertion" in states
        assert "target_namespace_unreachable_by_this_acquisition_route" in states

    def test_building_TWICE_into_DIFFERENT_roots_is_byte_identical(self, real_world,
                                                                   tmp_path):
        """The same science reproduces the same bundle: the id AND every table hash."""
        def emit(where, clock):
            return av2.emit(output_root=str(tmp_path / where), artifact_class="fixture",
                            aggregate=real_world["aggregate"], store=real_world["store"],
                            report_path=real_world["paths"]["report_path"],
                            created_at=clock)

        first = emit("root_a", "2020-01-01T00:00:00+00:00")
        second = emit("root_b", "2031-12-31T23:59:59+00:00")

        assert first["bundle_id"] == second["bundle_id"]
        assert (first["document"]["table_hashes"]
                == second["document"]["table_hashes"])
        assert set(first["document"]["table_hashes"]) == set(av2.SCIENTIFIC_TABLES)
        # ...and the DOCUMENT BYTES are identical too: different roots, different clocks.
        name = av2.V2_DOC["fixture"]
        a = open(os.path.join(first["bundle_dir"], name), "rb").read()
        b = open(os.path.join(second["bundle_dir"], name), "rb").read()
        assert a == b

    def test_the_INDEPENDENT_verifier_admits_the_emitted_bundle(self, real_world, tmp_path):
        """The generator does not get to mark its own work."""
        from verifier import verify_stage3_v2 as V

        built = av2.emit(output_root=str(tmp_path / "verified"), artifact_class="fixture",
                         aggregate=real_world["aggregate"], store=real_world["store"],
                         report_path=real_world["paths"]["report_path"],
                         created_at=CREATED_AT)
        paths = real_world["paths"]
        rep = V.verify(bundle=built["bundle_dir"],
                       stage2_aggregate_manifest=paths["manifest_path"],
                       stage2_aggregate_report=paths["report_path"],
                       stage2_bundles_root=paths["bundles_root"],
                       stage1_release=paths["stage1_release_path"],
                       universe_store=fx.REAL_STORE, artifact_class="fixture")
        assert not rep.failures, [n for n, _ in rep.failures]
        assert len(rep.checks) > 50

    def test_an_ANALYSIS_run_REFUSES_at_the_fixture_firewall(self, real_world, tmp_path):
        """THE HEADLINE. The store is real and admitted; the Stage-2 aggregate is a FIXTURE,
        because no admitted Stage-2 aggregate exists. So there is no real analysis to run, and
        the seam says so BY NAME rather than emitting a bundle full of plumbing numbers."""
        with pytest.raises(sa.Stage2AggregateError) as exc:
            av2.emit(output_root=str(tmp_path / "refused"), artifact_class="analysis",
                     aggregate=real_world["aggregate"], store=real_world["store"],
                     report_path=real_world["paths"]["report_path"],
                     created_at=CREATED_AT)
        assert sa.GATE_FIXTURE_FIREWALL in str(exc.value)
        assert not os.path.exists(str(tmp_path / "refused")), "nothing was written"
