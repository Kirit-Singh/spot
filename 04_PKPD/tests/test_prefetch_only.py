"""Prefetch warms a cache. It can never become evidence, and it never runs unbound.

The two fail-closed properties, proved rather than promised:

  1. **A prefetch artifact cannot enter Stage-4 materialization or admission.** Two independent
     walls: it writes NO acquisition manifest (so the materializer has nothing to read), and
     `assert_not_prefetch_only` refuses the receipt at the door if anyone hands it over anyway.

  2. **It does not run before W16 supplies the bound manifest.** No manifest, an unbound one, or
     one that does not declare itself prefetch-only, is a refusal — before a single byte is
     fetched.

And the reason the whole thing is worth doing: the warmed bytes RE-BIND. The cache is keyed on the
canonical query, so acquisition against the admitted bundle replays it with zero new requests.
"""

from __future__ import annotations

import json
import os

import pytest

from analysis.acquire_http import Client, StaticTransport
from analysis.firewall import Rejection
from analysis.run_prefetch import (
    assert_not_prefetch_only,
    load_prefetch_manifest,
    run_prefetch as warm,
)
from test_acquisition_identity import CLOCK, _routes

NAME = "fixturomide"


def _record(name=NAME, key="CHEMBL999", **over):
    r = {
        "machine_lookup_key": key,
        "machine_lookup_key_kind": "molecule_chembl_id",
        "lookup_key_status": "stated",
        "molecule_pref_name": name,
        "source_locator": f"chembl:CHEMBL_37:drug_mechanism/{key}",
        "source_release": "CHEMBL_37",
    }
    r.update(over)
    return r


def _manifest(tmp_path, records=None, **over) -> str:
    """W16's REAL manifest shape — the same one the live ed29138b document uses."""
    from analysis.prefetch_verify import content_sha256

    doc = {
        "schema_version": "spot.stage03.prefetch_manifest.v1",
        "method_id": "spot.stage03.prefetch_manifest.v1",
        "artifact_class": "prefetch_only",
        "universe_store": "chembl_37_pinned",
        "carries_no_score_or_rank": True,
        "combined_objective_permitted": False,
        "cross_arm_ordering_permitted": False,
        "may_be_admitted_as_a_stage3_analysis": False,
        "created_at": "2026-07-13T00:00:00Z",
        "records": records if records is not None else [_record()],
    }
    doc.update(over)
    doc["counts"] = {"n_prefetch_records": len(doc["records"]),
                     "n_records_with_no_source_locator":
                         sum(1 for r in doc["records"] if not r.get("source_locator"))}
    sha = content_sha256(doc)
    doc["manifest_sha256"] = sha
    doc["manifest_id"] = sha[:16]
    path = str(tmp_path / "prefetch_manifest.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    return path


def _client():
    return Client(transport=StaticTransport(_routes(), clock=CLOCK), allow_network=True)


# --------------------------------------------- 1. it does not run before W16 supplies a manifest


def test_there_is_no_prefetch_without_w16s_manifest(tmp_path):
    with pytest.raises(Rejection) as exc:
        warm(str(tmp_path / "nothing.json"), str(tmp_path / "run"), client=_client())
    assert exc.value.code == "prefetch_manifest_missing"


def test_a_manifest_that_is_not_prefetch_class_is_refused(tmp_path):
    path = _manifest(tmp_path, artifact_class="analysis")
    with pytest.raises(Rejection) as exc:
        load_prefetch_manifest(path)
    assert exc.value.code == "prefetch_manifest_wrong_class"


def test_a_manifest_whose_content_hash_does_not_reproduce_is_refused(tmp_path):
    """The self hash is RE-DERIVED from the bytes. A document that is not what it says it is
    cannot be warmed — this is the check the superseded 353b manifest would have needed."""
    path = _manifest(tmp_path)
    doc = json.load(open(path, encoding="utf-8"))
    doc["records"][0]["molecule_pref_name"] = "SOMETHING ELSE"      # content changed, hash not
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)

    with pytest.raises(Rejection) as exc:
        load_prefetch_manifest(path)
    assert exc.value.code == "prefetch_manifest_content_hash_mismatch"


def test_the_superseded_manifest_is_refused_by_hash(tmp_path):
    """353b7920 declared bindings it did not have. It cannot be consumed by accident."""
    from analysis.prefetch_verify import STALE_MANIFEST_IDS

    assert "353b7920" in STALE_MANIFEST_IDS
    path = _manifest(tmp_path)
    doc = json.load(open(path, encoding="utf-8"))
    doc["manifest_id"] = "353b7920"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)

    with pytest.raises(Rejection) as exc:
        load_prefetch_manifest(path)
    assert exc.value.code == "prefetch_manifest_superseded"


def test_a_record_missing_its_source_bindings_is_refused(tmp_path):
    """THE EXACT DEFECT of the superseded manifest: null locator/release/name in every row."""
    path = _manifest(tmp_path, records=[_record(source_locator=None)])
    with pytest.raises(Rejection) as exc:
        load_prefetch_manifest(path)
    assert exc.value.code in ("prefetch_manifest_records_incomplete",
                             "prefetch_manifest_count_mismatch")


def test_a_manifest_that_overclaims_is_refused(tmp_path):
    path = _manifest(tmp_path, may_be_admitted_as_a_stage3_analysis=True)
    with pytest.raises(Rejection) as exc:
        load_prefetch_manifest(path)
    assert exc.value.code == "prefetch_manifest_overclaims"


def test_an_empty_manifest_is_refused(tmp_path):
    with pytest.raises(Rejection) as exc:
        load_prefetch_manifest(_manifest(tmp_path, records=[]))
    assert exc.value.code == "prefetch_manifest_empty"


# ------------------------------------------------- 2. it warms the cache and verifies every byte


class _Klaxon:
    """Any request at all is a failure while the run is held."""

    clock = CLOCK

    def __call__(self, url: str, timeout: int):
        raise AssertionError(f"THE WIRE WAS TOUCHED WHILE HELD: {url!r}")


def test_warming_is_held_until_the_adapters_pass_the_source_totals_through(tmp_path):
    """THE INTEGRATION GATE. It is not enough for AcquisitionRecord to HAVE the fields — the real
    adapter constructors must pass selection_disposition / pin / match_total_reported /
    records_returned / result_set_complete through `record_from_response`, from the response the
    source actually sent. Until they do, a receipt could not state how many records each source
    claimed to have, and stamping a `1` because one row came back would be a fabricated total.

    So the run refuses, and it refuses BEFORE THE WIRE.
    """
    from analysis.acquire_http import Client

    with pytest.raises(Rejection) as exc:
        warm(_manifest(tmp_path), str(tmp_path / "run"),
             client=Client(transport=_Klaxon(), allow_network=True))

    assert exc.value.code == "source_totals_not_bound"
    assert "NO REQUEST IS MADE" in exc.value.detail
    # not one byte was fetched, and no run root was even created
    assert not os.path.exists(str(tmp_path / "run" / "raw"))


class _Rec:
    """A fetched record, shaped as the adapter would hand it over."""

    origin = "fetched_public"
    acquisition_record_id = "acq_x"

    def __init__(self, source_key, canonical_query, **over):
        self.source_key = source_key
        self.canonical_query = canonical_query
        self.selection_disposition = "unique"
        self.selection_pin = None
        self.match_total_reported = None
        self.records_returned = 1
        self.result_set_complete = None
        for k, v in over.items():
            setattr(self, k, v)


# --- SEARCH / LIST endpoints: the source reports a total, so it is MANDATORY ---------------

def test_a_search_endpoint_that_drops_the_source_total_is_refused():
    """openFDA reports meta.results.total. An adapter that does not pass it through leaves a
    truncated page indistinguishable from a complete one — the limit=1 defect, returning."""
    from analysis.source_totals import assert_totals_bound

    with pytest.raises(Rejection) as exc:
        assert_totals_bound([_Rec("openfda", 'drug/label.json?limit=25&search=x',
                                  match_total_reported=None)])
    assert exc.value.code == "source_total_missing_on_search"


def test_a_search_endpoint_whose_completeness_contradicts_its_own_total_is_refused():
    from analysis.source_totals import assert_totals_bound

    with pytest.raises(Rejection) as exc:
        assert_totals_bound([_Rec("openfda", "drug/drugsfda.json?limit=25&search=x",
                                  match_total_reported=7, records_returned=1,
                                  result_set_complete=True)])      # 7 != 1
    assert exc.value.code == "source_totals_inconsistent"


def test_a_search_endpoint_that_reports_its_total_honestly_passes():
    from analysis.source_totals import assert_totals_bound

    assert_totals_bound([_Rec("dailymed", "spls.json?drug_name=x&pagesize=100",
                              match_total_reported=20, records_returned=20,
                              result_set_complete=True)])


# --- DIRECT / identity endpoints: the source reports NO total. Null is the honest answer. ----

@pytest.mark.parametrize("source_key,query", [
    ("pubchem", "compound/name/temozolomide/cids/JSON"),
    ("pubchem", "compound/cid/5394/property/InChIKey/JSON"),
    ("rxnorm", "rxcui.json?name=temozolomide&search=0"),
    ("dailymed", "spls/046a9011-3911-4d3f-a15f-fbb56d5aad56.xml"),
])
def test_a_direct_endpoint_may_honestly_report_no_total(source_key, query):
    """These endpoints return the document or the whole list. There is no match total, so null is
    correct — and the gate must NOT refuse an honest absence."""
    from analysis.source_totals import assert_totals_bound

    assert_totals_bound([_Rec(source_key, query, match_total_reported=None,
                              result_set_complete=None)])


@pytest.mark.parametrize("source_key,query", [
    ("pubchem", "compound/name/temozolomide/cids/JSON"),
    ("rxnorm", "rxcui.json?name=x&search=0"),
])
def test_stamping_total_1_on_an_endpoint_that_reports_none_is_refused(source_key, query):
    """THE FORBIDDEN MOVE. A `1` that merely echoes the single row that arrived is
    indistinguishable in the artifact from a total the source actually stated."""
    from analysis.source_totals import assert_totals_bound

    with pytest.raises(Rejection) as exc:
        assert_totals_bound([_Rec(source_key, query, match_total_reported=1, records_returned=1,
                                  result_set_complete=True)])
    assert exc.value.code == "source_total_invented"
    assert "fabricated" in exc.value.detail or "invented" in exc.value.detail.lower()


def test_a_direct_endpoint_may_not_assert_completeness_it_cannot_derive():
    from analysis.source_totals import assert_totals_bound

    with pytest.raises(Rejection) as exc:
        assert_totals_bound([_Rec("pubchem", "compound/cid/1/property/InChIKey/JSON",
                                  match_total_reported=None, result_set_complete=True)])
    assert exc.value.code == "source_total_invented"


def test_the_selection_proof_and_the_returned_count_are_always_required():
    """However the endpoint behaves, we always know HOW we selected and HOW MANY rows we parsed."""
    from analysis.source_totals import assert_totals_bound

    with pytest.raises(Rejection) as exc:
        assert_totals_bound([_Rec("pubchem", "compound/cid/1/property/X/JSON",
                                  selection_disposition=None)])
    assert exc.value.code == "source_totals_not_bound"


# ------------------------------------ 3. THE WALL: a prefetch can never enter Stage 4


def test_a_prefetch_artifact_is_refused_at_the_stage4_door(tmp_path):
    """The second wall, independent of the first. Even if a caller points Stage 4 at a prefetch
    receipt directly, the door refuses it BY NAME: it was never bound to an admitted bundle."""
    receipt = {"prefetch_only": True, "stage4_admissible": False}

    with pytest.raises(Rejection) as exc:
        assert_not_prefetch_only(receipt)
    assert exc.value.code == "prefetch_only_artifact_refused"
    assert "admitted" in exc.value.detail


def test_stage4_materialization_cannot_read_a_run_root_that_holds_only_a_cache(tmp_path):
    """FAIL-CLOSED. The materializer reads `acquisition_manifest.json`. Warming never writes one,
    so a warmed cache cannot walk into Stage 4 by itself."""
    from analysis.acquisition import RunRoot
    from analysis.run_materialize import load_manifest

    root = str(tmp_path / "run")
    RunRoot(root)                                   # a run root with a cache but no manifest

    with pytest.raises(Exception) as exc:
        load_manifest(root)
    assert "manifest" in str(exc.value).lower()


# ------------------------------------------------ 4. the payoff: the bytes re-bind, for free


def test_cached_bytes_replay_and_re_bind_with_zero_new_requests(tmp_path):
    """The payoff that makes warming worth doing at all: the cache is keyed on the CANONICAL
    QUERY, so a later acquisition asks the same questions and is served from cache — and the
    records it builds are bound to THAT run, with the access time of the fetch that really
    happened, never re-stamped."""
    from analysis.acquire_cache import RequestCache
    from analysis.acquisition import RunRoot
    from analysis.run_acquire import acquire_identity

    root = str(tmp_path / "run")
    run_root = RunRoot(root)
    cache = RequestCache(run_root)

    first = Client(transport=StaticTransport(_routes(), clock=CLOCK), allow_network=True,
                   cache=cache)
    acquire_identity(first, run_root, NAME)
    assert first.n_fetched > 0

    # "the admitted bundle lands" — same questions, a later clock, a fresh client
    transport = StaticTransport(_routes(), clock="2026-07-20T00:00:00Z")
    later = Client(transport=transport, allow_network=True, cache=RequestCache(RunRoot(root)))
    resolved, records = acquire_identity(later, run_root, NAME)

    assert transport.seen == []                      # not one new request: pure cache replay
    assert later.n_reused > 0 and later.n_fetched == 0
    assert all(r.accessed_at_utc == CLOCK for r in records)   # the REAL fetch time, not the replay
    assert resolved["unii"] == "FIXTURE001"
