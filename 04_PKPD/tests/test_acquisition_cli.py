"""The acquisition CLI: an admitted Stage-3 bundle in, a run root out.

What it does NOT do is the point:

  * it acquires no candidate by default — identity acquisition is per-moiety and explicit;
  * it puts nothing on the wire without --allow-network;
  * it writes no ranking, no score and no selection, ever;
  * a name that is not a candidate in the admitted bundle is recorded as a REFERENCE PROBE and
    can never be reported as one.

Offline: the network client is injected. The one live probe lives in test_live_reference_smoke.py
and is skipped unless SPOT_STAGE4_LIVE=1.
"""

from __future__ import annotations

import json
import os

import pytest

from _stage3_forge import PINNED_BUNDLE
from analysis import run_acquire
from analysis.acquire_http import Client, StaticTransport
from test_acquisition_identity import CLOCK, _routes

RANKING_WORDS = ("rank", "score", "recommend", "traffic_light", "best", "top_candidate")


def _client(**over):
    return Client(transport=StaticTransport(_routes(**over), clock=CLOCK), allow_network=True)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _keys(node) -> set[str]:
    """Every field NAME in a document. Prose is not a field — the artifacts say in words that
    they rank nothing, and saying so must not itself trip the scan."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(str(key).lower())
            found |= _keys(value)
    elif isinstance(node, list):
        for item in node:
            found |= _keys(item)
    return found


def test_the_default_run_admits_the_bundle_reuses_stage3_and_acquires_nothing(tmp_path, capsys):
    root = str(tmp_path / "run")
    code = run_acquire.main(["--stage3-bundle", PINNED_BUNDLE, "--run-root", root])
    assert code == 0

    manifest = _read(os.path.join(root, "acquisition_manifest.json"))
    origins = {r["origin"] for r in manifest["records"]}
    assert origins == {"reused_from_stage3"}          # nothing was fetched
    assert not os.path.exists(os.path.join(root, "raw"))  # nothing was cached

    observed = [r for r in manifest["records"] if r["evidence_state"] == "observed"]
    assert {r["source_key"] for r in observed} == {"chembl", "uniprot"}

    # every lane Stage 3 never acquired is a STATED absence
    assert {m["source_key"] for m in manifest["missing"]} >= {"pubchem", "rxnorm"}
    assert all(m["evidence_state"] == "not_evaluated" for m in manifest["missing"])

    out = capsys.readouterr().out
    assert "no drug is ranked" in out.lower()


def test_the_receipt_says_what_was_admitted_and_what_was_not_acquired(tmp_path):
    root = str(tmp_path / "run")
    run_acquire.main(["--stage3-bundle", PINNED_BUNDLE, "--run-root", root])

    receipt = _read(os.path.join(root, "acquisition_receipt.json"))
    assert receipt["stage3"]["bundle_id"] == "s3_0b119088734643bf"
    assert receipt["stage3"]["external_verifier"] == "not_run"   # honest: gate 2 needs Stage-3's build context
    assert receipt["acquisition"]["candidates_acquired"] == 0
    assert receipt["acquisition"]["identities_acquired"] == []
    assert "not_evaluated" in json.dumps(receipt["missing"])
    assert receipt["hard_rules"]


def test_the_run_root_may_not_be_inside_the_git_working_tree(capsys):
    inside = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_should_never_exist")
    code = run_acquire.main(["--stage3-bundle", PINNED_BUNDLE, "--run-root", inside])
    assert code == 2
    assert "run_root_inside_git" in capsys.readouterr().err
    assert not os.path.exists(inside)


def test_identity_acquisition_without_network_permission_is_refused(tmp_path, capsys):
    root = str(tmp_path / "run")
    code = run_acquire.main(
        ["--stage3-bundle", PINNED_BUNDLE, "--run-root", root, "--acquire-identity", "fixturomide"])
    assert code == 2
    assert "network_not_permitted" in capsys.readouterr().err


def test_an_acquired_identity_that_is_not_a_candidate_is_a_reference_probe(tmp_path):
    """TEMODAR/temozolomide is not a Stage-3 candidate — the queued rows are all antibodies. A
    probe is a probe: it can never be reported as a candidate, and nothing about it is ranked."""
    root = str(tmp_path / "run")
    code = run_acquire.main(
        ["--stage3-bundle", PINNED_BUNDLE, "--run-root", root,
         "--acquire-identity", "fixturomide", "--allow-network"],
        client=_client())
    assert code == 0

    receipt = _read(os.path.join(root, "acquisition_receipt.json"))
    probe = receipt["acquisition"]["identities_acquired"][0]
    assert probe["moiety_name"] == "fixturomide"
    assert probe["role"] == "reference_probe"
    assert probe["candidate_id"] is None
    assert probe["identity"]["unii"] == "FIXTURE001"
    assert probe["identity"]["fda_application_number"] == "NDA999901"
    assert receipt["acquisition"]["candidates_acquired"] == 0

    fields = _keys(receipt)
    assert not any(w in f for f in fields for w in RANKING_WORDS)


def test_an_acquired_identity_records_every_response_it_rests_on(tmp_path):
    root = str(tmp_path / "run")
    run_acquire.main(
        ["--stage3-bundle", PINNED_BUNDLE, "--run-root", root,
         "--acquire-identity", "fixturomide", "--allow-network"],
        client=_client())

    manifest = _read(os.path.join(root, "acquisition_manifest.json"))
    fetched = [r for r in manifest["records"] if r["origin"] == "fetched_public"]
    assert {r["source_key"] for r in fetched} == {"pubchem", "rxnorm", "dailymed", "openfda"}
    for rec in fetched:
        assert rec["http_status"] == 200
        assert rec["accessed_at_utc"] == CLOCK
        assert rec["license_or_terms_url"]
        assert rec["adapter_code_sha256"]
        # the bytes are under the run root, addressed by their own hash — and not in Git
        assert os.path.isfile(os.path.join(root, rec["cache_relpath"]))
        assert rec["cache_relpath"].startswith("raw/")


def test_an_identity_conflict_refuses_the_moiety_and_writes_no_identity(tmp_path, capsys):
    root = str(tmp_path / "run")
    code = run_acquire.main(
        ["--stage3-bundle", PINNED_BUNDLE, "--run-root", root,
         "--acquire-identity", "fixturomide", "--allow-network"],
        client=_client(openfda_label="openfda_label_conflicting.json"))
    assert code == 2
    assert "identity_conflict" in capsys.readouterr().err

    # the refusal is not a half-written artifact: no identity was recorded
    receipt_path = os.path.join(root, "acquisition_receipt.json")
    if os.path.exists(receipt_path):
        assert _read(receipt_path)["acquisition"]["identities_acquired"] == []


def test_probing_a_reference_drug_does_not_fill_any_candidates_missing_identity_lane(tmp_path):
    """A probe fetched from PubChem does not make the CANDIDATES' identity lane acquired. The
    absence is per candidate, and it is still absent — clearing it because *something* was
    fetched would be the overclaim this layer exists to prevent."""
    root = str(tmp_path / "run")
    run_acquire.main(
        ["--stage3-bundle", PINNED_BUNDLE, "--run-root", root,
         "--acquire-identity", "fixturomide", "--allow-network"],
        client=_client())

    manifest = _read(os.path.join(root, "acquisition_manifest.json"))
    still_missing = {m["source_key"] for m in manifest["missing"]}
    assert {"pubchem", "rxnorm"} <= still_missing
    assert all(m["evidence_state"] == "not_evaluated" for m in manifest["missing"])


def test_two_identical_runs_produce_the_same_manifest_content_hash(tmp_path):
    """The manifest is content-addressed: same bundle, same responses, same clock -> same hash.
    A reviewer can re-run and compare rather than trust."""
    hashes = []
    for i in range(2):
        root = str(tmp_path / f"run{i}")
        run_acquire.main(
            ["--stage3-bundle", PINNED_BUNDLE, "--run-root", root,
             "--acquire-identity", "fixturomide", "--allow-network"],
            client=_client())
        hashes.append(_read(os.path.join(root, "acquisition_manifest.json"))["content_sha256"])
    assert hashes[0] == hashes[1]


def test_the_manifest_never_carries_a_ranking_field(tmp_path):
    root = str(tmp_path / "run")
    run_acquire.main(["--stage3-bundle", PINNED_BUNDLE, "--run-root", root])
    fields = _keys(_read(os.path.join(root, "acquisition_manifest.json")))
    for word in RANKING_WORDS:
        assert not any(word in f for f in fields)


@pytest.mark.parametrize("source_key", ["chembl", "uniprot"])
def test_the_cli_never_re_queries_a_source_stage3_already_acquired(tmp_path, source_key):
    root = str(tmp_path / "run")
    transport = StaticTransport(_routes(), clock=CLOCK)
    run_acquire.main(
        ["--stage3-bundle", PINNED_BUNDLE, "--run-root", root,
         "--acquire-identity", "fixturomide", "--allow-network"],
        client=Client(transport=transport, allow_network=True))
    assert not any(source_key in url for url in transport.seen)
