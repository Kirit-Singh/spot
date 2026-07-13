"""A null is never dressed as a key.

The first prefetch manifest emitted `source_locator: null` and `source_release: null` on ALL 455
rows — because those field names did not exist on the store's edges and `.get()` returned None —
while the handoff to W8 claimed every row carried "the exact public-source lookup key". W8 was one
step from fetching against 455 nulls.

Nothing crashed. Nothing failed a schema. The manifest was content-addressed, deterministic and
internally consistent, and it was WRONG in exactly the way that is hardest to see: a field that is
absent, presented as a field that is present.

These tests hold the line. Every one checks a VALUE, not a key: a test asserting the key exists
would have passed on the broken manifest.
"""
from __future__ import annotations

import os

import pytest

from druglink import prefetch_manifest as pm
from druglink import universe_rows as ur

STORE = "/home/tcelab/.spot-runs/stage3-universe-20260713/store_w3tokens"
PROJECTION = ("/home/tcelab/.spot-runs/w3-mixed-handoff-0f38de5/OUT/"
              "stage2_display_projection.json")

needs_inputs = pytest.mark.skipif(
    not (os.path.isdir(STORE) and os.path.exists(PROJECTION)),
    reason="the admitted store and W3's display projection are not on this host")


@pytest.fixture(scope="module")
def manifest():
    store = ur.load_store(STORE)
    return pm.build(projection_path=PROJECTION, store=store,
                    created_at="2026-07-13T00:00:00Z")


@needs_inputs
def test_the_manifest_is_non_vacuous(manifest):
    """Every assertion below is worthless over an empty record set."""
    assert manifest["counts"]["n_prefetch_records"] > 0
    assert manifest["records"]


@needs_inputs
@pytest.mark.parametrize("field", [
    "target_id", "target_id_namespace", "molecule_chembl_id", "molecule_pref_name",
    "machine_lookup_key", "source_release", "mec_id", "action_type_source",
])
def test_no_record_carries_a_NULL_in_a_field_the_handoff_promises(manifest, field):
    """THE DEFECT, AS A TEST. Check the VALUE — a key-existence test passed on the broken one."""
    nulls = [r for r in manifest["records"] if r.get(field) in (None, "")]
    assert not nulls, (
        f"{len(nulls)}/{len(manifest['records'])} records carry a null {field}. A null presented "
        "as a value is the defect this file exists to prevent: W8 would fetch against nothing.")


@needs_inputs
def test_a_STATED_lookup_key_is_actually_stated(manifest):
    """`lookup_key_status` must not lie. A row claiming `stated` with a null locator is exactly
    the original bug wearing a status field."""
    liars = [r for r in manifest["records"]
             if r["lookup_key_status"] == pm.LOOKUP_KEY_STATED and not r["source_locator"]]
    assert not liars, f"{len(liars)} record(s) claim a stated lookup key and carry none"


@needs_inputs
def test_a_locator_names_the_release_and_the_row_it_came_from(manifest):
    """`chembl:<release>:drug_mechanism/<mec_id>` — reopenable at its origin. 'ChEMBL says so' is
    not provenance; 'ChEMBL 37, this row' is."""
    for r in manifest["records"]:
        if r["lookup_key_status"] != pm.LOOKUP_KEY_STATED:
            continue
        loc = r["source_locator"]
        assert loc.startswith("chembl:"), loc
        assert str(r["source_release"]) in loc, (loc, r["source_release"])
        assert str(r["mec_id"]) in loc, (loc, r["mec_id"])


@needs_inputs
def test_absence_is_phrased_as_a_fact_about_THIS_STORE(manifest):
    """"No qualifying drug evidence in the bound store" — never "has no drug". The second states a
    fact about the WORLD when we only have a fact about ChEMBL 37's rankable lane, and a reader who
    believes it stops looking."""
    said = manifest["absence_means"].lower()
    assert "bound store" in said
    assert "not 'this target has no drug'" in said or "has no drug" in said
    assert manifest["counts"]["n_targets_with_no_qualifying_drug_evidence_in_the_bound_store"] >= 0


@needs_inputs
def test_it_carries_no_score_no_rank_and_no_cross_arm_order(manifest):
    assert manifest["carries_no_score_or_rank"] is True
    assert manifest["combined_objective_permitted"] is False
    assert manifest["cross_arm_ordering_permitted"] is False
    banned = {"score", "rank", "combined", "priority", "weight"}
    for r in manifest["records"]:
        assert not (banned & {k.lower() for k in r}), (
            "a prefetch record acquired an ordering field; a work list that sorts is a ranking "
            "wearing a work-list's clothes")


@needs_inputs
def test_it_cannot_be_admitted_as_a_stage3_analysis(manifest):
    from druglink import artifact_class as ac
    assert manifest["artifact_class"] == pm.ARTIFACT_CLASS == "prefetch_only"
    assert manifest["may_be_admitted_as_a_stage3_analysis"] is False
    with pytest.raises(ac.ArtifactClassError):
        ac.require(manifest["artifact_class"])          # a type error, not a convention


@needs_inputs
def test_identity_is_resolved_by_the_store_never_by_the_shape_of_an_id(manifest):
    """The universe holds Ensembl ids AND gene symbols. A shape guess types most rows right and
    mistypes the rest — and a mistyped row fails the join by silently finding no drug."""
    for r in manifest["records"]:
        assert r["target_id_namespace"] in ("ensembl_gene_id", "gene_symbol")
    assert manifest["counts"]["n_ambiguous_identity"] == 0


@needs_inputs
def test_the_projection_and_store_are_bound_by_recomputed_hashes(manifest):
    b = manifest["stage2_display_projection"]
    assert len(b["raw_sha256"]) == 64
    assert len(b["projection_self_sha256"]) == 64      # RECOMPUTED, not read
    assert manifest["universe_store"]["store_id"] == (
        "625c921fce2daf60b69fb0ae33570a9f074a0a0042b1717ee2111f81c1160bff")


@needs_inputs
def test_the_manifest_is_deterministic(manifest):
    store = ur.load_store(STORE)
    again = pm.build(projection_path=PROJECTION, store=store,
                     created_at="2026-07-13T00:00:00Z")
    assert again["manifest_sha256"] == manifest["manifest_sha256"]
