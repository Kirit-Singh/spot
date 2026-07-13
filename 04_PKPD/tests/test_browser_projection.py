"""The browser projection: nested shape PRESERVED, arm membership carried, any selection filterable.

Two defects, and the second is the dangerous one.

**Arm membership was absent from the release.** Stage 3 knows which arms a candidate sits on; Stage 4
dropped them at the `Stage3Candidate` boundary. So a browser wanting to answer a DIFFERENT selection
had no way to filter — it would need a full rerun, which means re-acquiring public evidence Stage 4
already holds. The store is global and selection-independent precisely so that never happens.

**And the native scorecards are OBJECTS.** `active_moiety`, `compound_ids`, `production_eligible` and
every lane are dicts; `provenance_chain` is a list of dicts. Stringifying them for a UI is not a
formatting choice — it destroys evidence:

    a nested `null` means NOT EVALUATED, and `str(None)` is `"None"` — which is a VALUE
    `{"status": "incomplete", "total": null}` stringified reads as a score
    a lane's missing-value semantics — the whole point of this stage — collapse into prose

So the projection copies the native objects through verbatim, and these tests assert that no leaf
became a string and no null became anything else. Missing stays missing, NESTED.
"""

from __future__ import annotations

import json


from analysis.projection import (
    BROWSER_PROJECTION_SCHEMA,
    build_projection,
)
from analysis.stage3_annotation import adapt_annotation_bundle
from test_stage3_handoff_and_integrity import PINNED_ANNOTATION_BUNDLE

NATIVE = {
    "scorecard_set_id": "abc123",
    "upstream": {"namespace": "research_only"},
    "ordering": {"is_ranking": False},
    "candidates": [{
        "candidate_id": "AM:CHEMBL:CHEMBL1789844",
        # every one of these is an OBJECT, and the nesting carries the meaning
        "active_moiety": {"active_moiety_id": "AM:1", "name": "X", "unii": None},
        "compound_ids": {"chembl_id": "CHEMBL1", "pubchem_cid": None, "rxcui": None},
        "production_eligible": {"eligible": False, "reasons": ["research_only_namespace"]},
        "lanes": {
            "cns_mpo": {"status": "incomplete", "total": None,
                        "components": {"clogp": None, "mw": 0.9}},
            "nebpi": {"nebpi_class": None, "status": "not_classifiable"},
            "exposure": {"measurements": [], "state": "not_evaluated"},
        },
        "provenance_chain": [{"field": "mw", "source_record_id": "acq.1", "transform": "t"}],
        "mechanism": {"kind": "inhibitor"},
        "target": {"symbol": "ABC"},
        "direction_compatibility": "compatible",
    }],
}


def _queued():
    return adapt_annotation_bundle(PINNED_ANNOTATION_BUNDLE).queued


def _view():
    return adapt_annotation_bundle(PINNED_ANNOTATION_BUNDLE).selection_view


def _leaves(node, path="$"):
    """Every leaf, with its path — so a stringified object cannot hide inside a nested structure."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _leaves(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _leaves(v, f"{path}[{i}]")
    else:
        yield path, node


# ------------------------------------------------------ the nested shape survives, verbatim

def test_the_native_OBJECTS_are_copied_through_and_NEVER_stringified():
    """THE test. A dict that arrives as a dict must leave as a dict."""
    doc = build_projection(NATIVE, _queued())
    row = doc["candidates"][0]

    for field in ("active_moiety", "compound_ids", "production_eligible", "lanes", "mechanism",
                  "target"):
        assert isinstance(row[field], dict), (
            f"{field} was flattened into {type(row[field]).__name__}. Stringifying an object "
            "destroys its missing-value semantics.")
    assert isinstance(row["provenance_chain"], list)
    assert isinstance(row["provenance_chain"][0], dict)

    # and it is the SAME object, not a lossy re-render
    assert row["lanes"] == NATIVE["candidates"][0]["lanes"]
    assert row["production_eligible"] == {"eligible": False,
                                          "reasons": ["research_only_namespace"]}


def test_a_nested_NULL_stays_NULL_and_never_becomes_the_string_None():
    """`str(None)` is `"None"` — which is a VALUE. A not-evaluated field that renders as the text
    "None" has been converted from an absence into a presence, and a reader cannot tell."""
    doc = build_projection(NATIVE, _queued())
    row = doc["candidates"][0]

    assert row["lanes"]["cns_mpo"]["total"] is None
    assert row["lanes"]["cns_mpo"]["components"]["clogp"] is None
    assert row["lanes"]["nebpi"]["nebpi_class"] is None
    assert row["compound_ids"]["pubchem_cid"] is None
    assert row["active_moiety"]["unii"] is None

    # nothing anywhere in the document became the string "None"/"null"/"nan"
    for path, leaf in _leaves(doc):
        if isinstance(leaf, str):
            assert leaf.strip().lower() not in ("none", "null", "nan", "n/a"), (
                f"{path} carries {leaf!r} — a missing value that was rendered into a string. "
                "Missing must stay missing.")


def test_CNS_MPO_stays_incomplete_in_the_projection():
    """The engine says incomplete with a null total. The browser must receive exactly that, not a
    number and not a dash."""
    row = build_projection(NATIVE, _queued())["candidates"][0]
    assert row["lanes"]["cns_mpo"]["status"] == "incomplete"
    assert row["lanes"]["cns_mpo"]["total"] is None


# --------------------------------- arm membership: any selection, filterable, without a rerun

def test_every_candidate_carries_its_STAGE3_ARM_MEMBERSHIP():
    """Absent from the release before this. Without it, answering a different selection means a
    full rerun — re-acquiring public evidence Stage 4 already holds."""
    doc = build_projection(NATIVE, _queued())
    membership = doc["candidates"][0]["stage3_arm_membership"]

    assert membership["arms"] == ["away_from_A"]
    # the four claims are kept APART: an observed knockdown direction and a proposed
    # inverse-direction hypothesis are not the same evidence.
    for col in ("observed_perturbation_arms", "inverse_direction_hypothesis_arms",
                "pathway_hypothesis_arms", "opposed_arms"):
        assert col in membership


def test_the_projection_is_the_GLOBAL_store_not_a_singleton_selection():
    """The expensive part of Stage 4 — acquiring public evidence — is selection-INDEPENDENT. The
    store holds the whole admitted universe so a second question is a filter, not a second run."""
    doc = build_projection(NATIVE, _queued(), _view())

    assert doc["store_is_selection_independent"] is True
    assert doc["schema_id"] == BROWSER_PROJECTION_SCHEMA
    assert len(doc["candidates"]) == len(NATIVE["candidates"]), (
        "the projection dropped candidates: it is a store, not a filtered view")


def test_the_active_view_is_FLAGGED_never_enforced():
    """A convenience, not a gate. The candidate stays in the store either way — the next selection
    may be exactly about it."""
    doc = build_projection(NATIVE, _queued(), _view())

    assert doc["active_selection_view"]["question_id"]
    row = doc["candidates"][0]
    assert row["in_active_view"] is True          # away_from_A ∈ {away_from_A, toward_B}
    assert row["candidate_id"] in doc["active_view_candidate_ids"]

    # without a view the store is still complete, just unflagged
    plain = build_projection(NATIVE, _queued())
    assert "in_active_view" not in plain["candidates"][0]
    assert len(plain["candidates"]) == 1


def test_the_projection_carries_NO_ranking():
    doc = build_projection(NATIVE, _queued(), _view())
    assert doc["is_ranking"] is False

    blob = json.dumps(doc).lower()
    for banned in ("overall_rank", "combined_score", "traffic_light", "p_value", "safety_score"):
        assert banned not in blob, f"the browser projection carries {banned!r}"
