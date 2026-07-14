"""The Stage-4 output contract: seven direction-aware facets, a provenance drawer, no global rank.

What a reader (and the compact UI) must be able to see WITHOUT re-joining the evidence bundle:

    compound identity · target action · potency context · brain exposure
    transporter liability · clinical label/safety · evidence availability

Two of these were missing. The exposure lane cited `potency_id` but not the potency — so a margin's
DENOMINATOR could not be inspected, and a margin whose denominator cannot be inspected is an unbound
ratio. And nothing rolled up what was actually LOOKED AT, so an empty lane was indistinguishable
from a negative result.

`not_evaluated` is a first-class answer here. Absence of an exposure measurement is not evidence of
impermeability, and absence of a labelled finding is not evidence of safety.
"""

from __future__ import annotations

import json
import os

import pytest

from analysis.contract_version import ContractVersion
from analysis.emit import CANDIDATE_FACETS, emit
from analysis.method_config import load_method_bundle
from analysis.pipeline import run_pipeline
from fixtures import stage4_inputs, stage4_inputs_v2


@pytest.fixture(scope="module")
def release(tmp_path_factory):
    out = tmp_path_factory.mktemp("rel")
    i = stage4_inputs()
    method = load_method_bundle()
    path, manifest = emit(i, run_pipeline(i, method), method, str(out))
    with open(os.path.join(path, "scorecards.json"), encoding="utf-8") as fh:
        return {"scorecards": json.load(fh), "manifest": manifest}


# ---------------------------------------------------------------- the seven facets, per candidate

def test_the_seven_facets_are_ENUMERATED_so_a_missing_one_is_noticed():
    """A facet nobody named is a facet nobody notices is missing."""
    assert set(CANDIDATE_FACETS) == {
        "compound_identity", "target_action", "potency_context", "brain_exposure",
        "transporter_liability", "clinical_label_safety", "evidence_availability"}


def test_every_candidate_carries_all_seven(release):
    for c in release["scorecards"]["candidates"]:
        lanes = c["lanes"]
        assert c["active_moiety"] and c["compound_ids"]                    # compound identity
        assert "target" in c and "mechanism" in c                          # target action
        assert c["direction_compatibility"]                                # ...DIRECTION-aware
        assert "potency" in lanes                                          # potency context
        assert {"cns_mpo", "exposure", "nebpi"} <= set(lanes)              # brain exposure
        assert "transporters" in lanes                                     # transporter liability
        assert "safety" in lanes                                           # clinical label/safety
        assert "evidence_availability" in lanes                            # evidence availability


def test_the_POTENCY_facet_makes_a_margins_denominator_INSPECTABLE(release):
    """The exposure lane cited `potency_id` and stopped there. A margin whose denominator cannot be
    inspected is an unbound ratio."""
    lane = release["scorecards"]["candidates"][0]["lanes"]["potency"]

    assert lane["state"] in ("observed", "not_evaluated")
    for row in lane["rows"]:
        # what it IS, not just that it exists
        assert {"potency_id", "metric", "value_source_string", "units",
                "binding_state", "biological_context"} <= set(row)
        # ...and where it came FROM
        assert row["source_record_id"] and row["raw_response_sha256"]


def test_an_ABSENT_potency_states_a_reason_CODE_and_invents_no_value(release):
    """A margin has no denominator, and one is not invented. The reason is a CODE — a free sentence
    in the document would be bound by nothing (the `production_eligible` convention)."""
    for c in release["scorecards"]["candidates"]:
        lane = c["lanes"]["potency"]
        if lane["state"] == "not_evaluated":
            assert lane["rows"] == []
            assert lane["not_evaluated_reason_code"] == "no_potency_acquired"
        else:
            assert lane["not_evaluated_reason_code"] is None


def test_EVIDENCE_AVAILABILITY_says_what_was_looked_at_and_guards_the_reading(release):
    """`not_evaluated` means nobody looked. It is NOT a negative result."""
    avail = release["scorecards"]["candidates"][0]["lanes"]["evidence_availability"]

    for facet in ("potency_context", "brain_exposure", "transporter_liability",
                  "clinical_label_safety", "nebpi_classification"):
        assert avail[facet] in ("observed", "not_evaluated")

    assert avail["guard_code"] == "not_evaluated_is_not_a_negative_result"


def test_the_relation_is_carried_at_v2_where_the_COLUMN_exists(tmp_path):
    """`relation` distinguishes a point estimate (`=`) from an assay that ran out of range — and only
    an equality is a magnitude anything may be divided by. It is a v2 column: emitting it at v1 would
    put a value in the document that no emitted table binds."""
    i = stage4_inputs_v2()
    method = load_method_bundle(version=ContractVersion.V2)
    path, _ = emit(i, run_pipeline(i, method), method, str(tmp_path))

    with open(os.path.join(path, "scorecards.json"), encoding="utf-8") as fh:
        rows = json.load(fh)["candidates"][0]["lanes"]["potency"]["rows"]
    if rows:
        assert "relation" in rows[0]


# --------------------------------------------------------------------- NO global combined rank

def test_the_output_carries_NO_global_combined_rank(release):
    """A per-arm rank is a statement about one arm. A candidate-level rank orders candidates across
    arms that were never comparable, and hides the fusion behind one tidy integer."""
    blob = json.dumps(release["scorecards"]).lower()
    for banned in ("overall_rank", "candidate_rank", "combined_rank", "combined_score",
                   "composite_score", "overall_score", "traffic_light", "p_value"):
        assert banned not in blob, f"the output carries {banned!r}"

    assert release["scorecards"]["ordering"]["is_ranking"] is False


# ------------------------------------------------- the Methods & provenance drawer, and licensing

def test_the_manifest_feeds_the_METHODS_AND_PROVENANCE_DRAWER(release):
    """Everything the drawer needs, assembled here rather than left for a UI to reconstruct — a
    drawer that has to guess is a drawer that guesses wrong."""
    m = release["manifest"]

    assert m["method_file_sha256"] and m["analysis_code_sha256"]       # method / code hash
    assert m["environment"]["lock_sha256"]                             # env lock
    assert m["reproduce"]["command"], "no rerun command"               # rerun command
    assert "verify_stage4" in " ".join(m["reproduce"]["command"])
    assert m["created_at"]                                             # rerun time
    assert m["reproduce"]["scorecard_set_id_excludes_the_clock"] is True


@pytest.fixture(scope="module")
def materialized(tmp_path_factory):
    """The REAL chain: only a materialized bundle carries `acquired_public` sources. The engine's
    own fixtures are synthetic, and a synthetic source has no licence to assert."""
    from analysis.acquisition import RunRoot
    from analysis.materialize import materialize
    from analysis.run_acquire import run as acquire
    from analysis.run_materialize import load_manifest
    from analysis.stage3_annotation import adapt_annotation_bundle

    root = tmp_path_factory.mktemp("chain")
    run_root = str(root / "rr")
    bundle_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "fixtures", "stage3_annotation", "s3_0b119088734643bf")

    acquire(bundle_dir, run_root, names=[], allow_network=False, setid=None,
            require_external_verifier=False)
    admission = adapt_annotation_bundle(bundle_dir)
    doc = materialize(admission, load_manifest(run_root), RunRoot(run_root))

    path = str(root / "evidence.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return doc


def test_every_public_source_carries_EXACT_machine_readable_terms(materialized):
    """Locator, licence, release and hash — structured fields, not prose a UI has to parse."""
    public = [s for s in materialized["sources"].values()
              if s.get("acquisition_status") == "acquired_public"]
    assert public, "this test is vacuous with no public source"

    for s in public:
        assert s["url"], "a public source must carry its locator"
        assert s["license"], "a public source must carry its licence, machine-readably"
        assert s["raw_sha256"], "a public source must carry the hash of its bytes"
        assert s["release_version"], "a public source must carry the source's own release"


def test_NO_source_fabricates_an_ACCESS_DATE(materialized):
    """`1970-01-01` was reaching the release's source registry — which is precisely what the
    provenance drawer displays. An epoch placeholder is not a missing value: it is a fabricated
    provenance claim that reads as a real access date.

    A time nobody stated is ABSENT. `SourceRecord.access_date` is Optional so it can be.
    """
    for sid, s in materialized["sources"].items():
        date = str(s.get("access_date") or "")
        assert not date.startswith("1970-"), (
            f"{sid[:12]} claims access_date={date!r} — the epoch is not a date, it is an invented "
            "one.")
