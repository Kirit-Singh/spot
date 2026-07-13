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


def test_warming_caches_every_response_and_verifies_request_source_and_hash(tmp_path):
    receipt = warm(_manifest(tmp_path), str(tmp_path / "run"), client=_client())

    assert receipt["counts"] == {"acquired": 1, "not_found": 0, "error": 0}
    assert receipt["n_responses_cached"] >= 4

    for request in receipt["candidates"][0]["requests"]:
        assert request["http_status"] == 200
        assert request["url"].startswith("https://")
        assert request["raw_sha256"] and request["raw_bytes"]
        assert request["license_or_terms_url"]
        assert request["accessed_at_utc"] == CLOCK
        assert request["cache_relpath"].startswith("raw/")
        # the bytes are really on disk, under their own hash
        assert os.path.isfile(os.path.join(str(tmp_path / "run"), request["cache_relpath"]))

    assert receipt["content_sha256"] and receipt["elapsed_seconds"] >= 0
    assert receipt["transport"]["max_workers"] == 4


def test_a_miss_is_counted_not_fatal_to_the_rest_of_the_queue(tmp_path):
    """One unresolvable molecule must not kill a hundred-candidate warm-up."""
    path = _manifest(tmp_path, records=[
        _record(NAME, "CHEMBL1"),
        _record("nosuchmoleculeexists", "CHEMBL2"),
    ])
    receipt = warm(path, str(tmp_path / "run"), client=_client())

    assert receipt["counts"]["acquired"] == 1
    assert receipt["counts"]["not_found"] + receipt["counts"]["error"] == 1
    assert receipt["n_candidates"] == 2


# ------------------------------------ 3. THE WALL: a prefetch can never enter Stage 4


def test_warming_writes_no_acquisition_manifest_so_materialization_has_nothing_to_read(tmp_path):
    root = str(tmp_path / "run")
    warm(_manifest(tmp_path), root, client=_client())

    assert os.path.isfile(os.path.join(root, "prefetch_receipt.json"))
    assert not os.path.exists(os.path.join(root, "acquisition_manifest.json"))


def test_stage4_materialization_refuses_a_run_root_that_was_only_warmed(tmp_path):
    """FAIL-CLOSED. The materializer reads `acquisition_manifest.json`; a warmed cache has none,
    so a prefetch cannot walk into Stage 4 by itself."""
    from analysis.run_materialize import load_manifest

    root = str(tmp_path / "run")
    warm(_manifest(tmp_path), root, client=_client())

    with pytest.raises(Exception) as exc:      # Rejection or OSError — either way it does not load
        load_manifest(root)
    assert "acquisition_manifest" in str(exc.value) or "manifest" in str(exc.value).lower()


def test_the_prefetch_receipt_is_refused_at_the_stage4_door_if_anyone_hands_it_over(tmp_path):
    """The second wall. Even if a future caller points Stage 4 at the receipt directly, the door
    refuses it by name: it was never bound to an admitted bundle."""
    receipt = warm(_manifest(tmp_path), str(tmp_path / "run"), client=_client())

    with pytest.raises(Rejection) as exc:
        assert_not_prefetch_only(receipt)
    assert exc.value.code == "prefetch_only_artifact_refused"
    assert "admitted" in exc.value.detail


def test_the_receipt_says_in_its_own_fields_that_it_is_not_admissible(tmp_path):
    receipt = warm(_manifest(tmp_path), str(tmp_path / "run"), client=_client())

    assert receipt["prefetch_only"] is True
    assert receipt["stage4_admissible"] is False
    assert receipt["stage3_admission_required"] is False
    assert receipt["stage3_admission_implied"] is False
    assert "never becomes an evidence bundle" in " ".join(receipt["hard_rules"])


# ------------------------------------------------ 4. the payoff: the bytes re-bind, for free


def test_the_warmed_cache_is_replayed_when_the_admitted_bundle_finally_lands(tmp_path):
    """The whole reason to warm: acquisition against the ADMITTED bundle asks the same canonical
    questions, so it is served from cache with ZERO new requests — and the records it builds are
    bound to that bundle, not to the prefetch."""
    from analysis.acquire_cache import RequestCache
    from analysis.acquisition import RunRoot
    from analysis.run_acquire import acquire_identity

    root = str(tmp_path / "run")
    warm(_manifest(tmp_path), root, client=_client())

    # now the "admitted bundle" arrives and acquisition runs over the SAME run root
    transport = StaticTransport(_routes(), clock="2026-07-20T00:00:00Z")
    run_root = RunRoot(root)
    later = Client(transport=transport, allow_network=True, cache=RequestCache(run_root))

    resolved, records = acquire_identity(later, run_root, NAME)

    assert transport.seen == []                      # not one new request: pure cache replay
    assert later.n_reused > 0 and later.n_fetched == 0
    # and the access time is the fetch that REALLY happened, not the replay
    assert all(r.accessed_at_utc == CLOCK for r in records)
    assert resolved["unii"] == "FIXTURE001"
