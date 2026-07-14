"""The CLI's Stage-3 door.

The audit found the door was a wall: `contracts.py` said `stage3_adapter.py` was the only
supported wire path, and the CLI never called it. It parsed `--candidate-set` as Stage 4's
OWN internal model instead, so a real Stage-3 fixture bundle — one that adapts cleanly in
the unit tests — was refused at the command line with `unknown schema_id None`.

The door is now `--stage3-bundle`, and it branches on what Stage 3 actually emitted.
"""

from __future__ import annotations

import json
import os

import pytest

from analysis.evidence_bundle import EVIDENCE_BUNDLE_SCHEMA
from analysis.run_stage4 import RECEIPT_SCHEMA, main
from test_stage3_handoff_and_integrity import COMMITTED_BUNDLES


def receipt_of(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


# ------------------------------------------------------------------ the fixture bundle

def test_the_cli_admits_a_real_stage3_fixture_bundle(tmp_path, capsys):
    """The exact document the old CLI refused with `unknown schema_id None`."""
    rc = main(["--stage3-bundle", COMMITTED_BUNDLES["fixture"],
               "--outputs-root", str(tmp_path)])
    assert rc == 0

    r = receipt_of(capsys)
    assert r["schema_id"] == RECEIPT_SCHEMA
    assert r["stage3"]["schema_version"] == "spot.fixture.stage03_bundle.v1"
    assert r["stage3"]["namespace"] == "fixture"
    assert r["admission"]["admitted_as_candidates"] == 3


def test_a_fixture_bundle_alone_produces_no_scorecard_set(tmp_path, capsys):
    """Structure is exercised; no result is manufactured. Empty lanes are not a finding."""
    rc = main(["--stage3-bundle", COMMITTED_BUNDLES["fixture"],
               "--outputs-root", str(tmp_path)])
    assert rc == 0

    r = receipt_of(capsys)
    assert r["stage4_run"]["scorecards_emitted"] is False
    assert r["stage4_run"]["reason_code"] == "no_evidence_bundle_supplied"
    # Nothing was written at all: not an empty scorecard set, not a stub.
    assert not os.path.exists(tmp_path) or not os.listdir(tmp_path)


def test_the_document_path_works_as_well_as_the_directory(tmp_path, capsys):
    doc = os.path.join(COMMITTED_BUNDLES["fixture"], "fixture_bundle.json")
    assert main(["--stage3-bundle", doc, "--outputs-root", str(tmp_path)]) == 0
    assert receipt_of(capsys)["admission"]["admitted_as_candidates"] == 3


# ------------------------------------------------------------ the research annotation

def test_a_research_annotation_is_inspection_only(tmp_path, capsys):
    """Stage 3's own words: "an ANNOTATION, never a candidate set"."""
    rc = main(["--stage3-bundle", COMMITTED_BUNDLES["research_only"],
               "--outputs-root", str(tmp_path)])
    assert rc == 0

    r = receipt_of(capsys)
    assert r["stage3"]["namespace"] == "research_only"
    assert r["admission"]["admitted_as_candidates"] == 0
    assert r["stage4_run"]["scorecards_emitted"] is False
    assert r["stage4_run"]["reason_code"] == "inspection_only"
    assert "annotation, not a candidate set" in r["admission"]["refusal_reason"]
    assert not os.path.exists(tmp_path) or not os.listdir(tmp_path)


def test_a_research_annotation_yields_no_candidate_and_no_score(tmp_path, capsys):
    """No candidate, no scorecard, no selection — and it can never become production."""
    main(["--stage3-bundle", COMMITTED_BUNDLES["research_only"],
          "--outputs-root", str(tmp_path)])
    r = receipt_of(capsys)
    assert r["stage3"]["stage4_eligible"] is False
    assert r["admission"]["inspected_only"] == 0  # nothing was acquired upstream either
    assert r["stage3"]["source_status"]["n_acquired_public"] == 0


# ------------------------------------------------------------------- the receipt file

def test_the_receipt_can_be_written_for_a_machine(tmp_path, capsys):
    out = tmp_path / "receipt.json"
    main(["--stage3-bundle", COMMITTED_BUNDLES["fixture"], "--receipt-out", str(out),
          "--outputs-root", str(tmp_path / "o")])
    capsys.readouterr()

    with open(out, encoding="utf-8") as fh:
        r = json.load(fh)
    assert r["schema_id"] == RECEIPT_SCHEMA
    assert r["stage3"]["canonical_content_sha256"]
    assert r["stage4_run"]["scorecards_emitted"] is False


# ---------------------------------------------------------------- the evidence bundle

def test_an_empty_evidence_bundle_is_refused(tmp_path, capsys):
    """Ten empty lanes would emit an artifact that reads like a result and contains none."""
    bundle = tmp_path / "evidence.json"
    bundle.write_text(json.dumps({"schema_id": EVIDENCE_BUNDLE_SCHEMA}), encoding="utf-8")

    rc = main(["--stage3-bundle", COMMITTED_BUNDLES["fixture"],
               "--evidence-bundle", str(bundle), "--outputs-root", str(tmp_path / "o")])
    assert rc == 2
    assert "evidence_bundle_empty" in capsys.readouterr().err


def test_an_unknown_evidence_schema_is_refused(tmp_path, capsys):
    bundle = tmp_path / "evidence.json"
    bundle.write_text(json.dumps({"schema_id": "spot.something_else.v1"}), encoding="utf-8")

    rc = main(["--stage3-bundle", COMMITTED_BUNDLES["fixture"],
               "--evidence-bundle", str(bundle), "--outputs-root", str(tmp_path / "o")])
    assert rc == 2
    assert "evidence_bundle_schema_unknown" in capsys.readouterr().err


def test_an_unknown_evidence_lane_is_refused(tmp_path, capsys):
    """Stage 4 will not silently ignore evidence it does not understand."""
    bundle = tmp_path / "evidence.json"
    bundle.write_text(
        json.dumps({"schema_id": EVIDENCE_BUNDLE_SCHEMA, "pharmacogenomics": [{}]}),
        encoding="utf-8")

    rc = main(["--stage3-bundle", COMMITTED_BUNDLES["fixture"],
               "--evidence-bundle", str(bundle), "--outputs-root", str(tmp_path / "o")])
    assert rc == 2
    assert "evidence_bundle_unknown_lane" in capsys.readouterr().err


def test_a_missing_evidence_bundle_is_refused(tmp_path, capsys):
    rc = main(["--stage3-bundle", COMMITTED_BUNDLES["fixture"],
               "--evidence-bundle", str(tmp_path / "nope.json"),
               "--outputs-root", str(tmp_path / "o")])
    assert rc == 2
    assert "evidence_bundle_missing" in capsys.readouterr().err


# -------------------------------------------------------------------- the engine door

def test_the_fixture_engine_path_still_runs_and_is_labelled(tmp_path, capsys):
    rc = main(["--fixtures", "--outputs-root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "verification     : pass" in out
    assert "is_fixture       : True" in out
    assert "This is a FIXTURE run." in out


@pytest.mark.parametrize("argv", [[], ["--fixtures", "--stage3-bundle", "/tmp"]])
def test_exactly_one_door(argv, capsys):
    assert main(argv) == 2
    assert "supply exactly one" in capsys.readouterr().err
