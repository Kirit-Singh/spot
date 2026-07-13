"""The acquisition -> evidence-bundle materializer, and every way it could lie.

The E2E audit's finding: `run_acquire` wrote an acquisition manifest, `run_stage4` consumed an
evidence bundle, and NOTHING turned one into the other. There was no production path from acquired
public bytes to a scorecard set — so every green run in this repo was scoring a fixture, and no
amount of downstream rigour could have told you that.

These tests build a real acquisition (real DailyMed SPL bytes, real PubChem-shaped JSON, cached
under a run root OUTSIDE the tree, hashed) and drive the materializer over it. The bytes are
labelled test bytes, but the RECORDS claim `fetched_public` and the materializer treats them as
it would treat a live response — which is the only way to test the path that matters.

The attacks are the point. A materializer that fabricates is worse than no materializer: it makes
an unsourced number look acquired.
"""

from __future__ import annotations

import json
import os

import pytest

from analysis.acquisition import AcquisitionManifest, AcquisitionRecord, RunRoot
from analysis.canonical import sha256_bytes
from analysis.contract_version import ContractVersion
from analysis.evidence_bundle import load_evidence_bundle
from analysis.firewall import Rejection
from analysis.materialize import MaterializationError, materialize
from analysis.run_stage4 import adapt, load_stage3_bundle
from fixtures import fixture_bytes
from test_stage3_handoff_and_integrity import (
    COMMITTED_BUNDLES,
    PINNED_ANNOTATION_BUNDLE,
)
from verifier.verify_bundle import verify_bundle

SPL = "dailymed_spl_nested_fixture.xml"
ADAPTER_SHA = "a" * 64

PUBCHEM_JSON = json.dumps({
    "PropertyTable": {"Properties": [{
        "CID": 5394,
        "MolecularWeight": "194.15",
        "TPSA": "106.0",
        "HBondDonorCount": 1,
        "XLogP": "-0.6",
        "InChIKey": "YYYYYYYY88AA-BBBBBBBBBB-N",
    }]}
}).encode()


def _admission():
    return adapt(*load_stage3_bundle(COMMITTED_BUNDLES["fixture"]))


def _annotation_admission():
    """The door `run_acquire` and `run_materialize` actually use — Stage 3's drug-annotation
    bundle, admitted through both gates."""
    from analysis.stage3_annotation import adapt_annotation_bundle

    return adapt_annotation_bundle(PINNED_ANNOTATION_BUNDLE)


def _spl_for(moiety_name: str, unii: str = "SYNTHUNII01") -> bytes:
    """The nested SPL fixture, retargeted to the moiety actually under test.

    The label must BE the candidate's label. Binding a label for one molecule to a different
    candidate is refused by the identity firewall (`LabelIdentityError`) — see
    `test_a_label_for_a_DIFFERENT_molecule_is_refused` below, which is the important half.
    """
    raw = fixture_bytes(SPL).decode()
    return (raw.replace("FIXTURIMAB", moiety_name)
               .replace("YYYYYYYY88", unii)
               .encode())


def _record(run_root, *, key, raw, stable_id, source_type, transform, origin="fetched_public",
            state="observed", candidate_id=None):
    relpath, digest = run_root.store(raw, source_key=key)
    return AcquisitionRecord(
        acquisition_record_id=f"acq.{key}.{stable_id}",
        source_key=key,
        source_name=f"{key} response",
        source_type=source_type,
        origin=origin,
        stable_record_id=stable_id,
        url=f"https://example.invalid/{key}/{stable_id}",
        canonical_query=f"GET /{key}/{stable_id}",
        canonical_query_sha256=sha256_bytes(f"GET /{key}/{stable_id}".encode()),
        accessed_at_utc="2026-07-13T00:00:00Z",
        access_date="2026-07-13",
        http_status=200,
        raw_media_type="application/json",
        release_or_last_updated="2026-07-01",
        license="no blanket licence verified",
        license_or_terms_url="https://dailymed.nlm.nih.gov/dailymed/",
        raw_bytes=len(raw),
        raw_sha256=digest,
        cache_relpath=relpath,
        extraction_transform=transform,
        adapter_code_sha256=ADAPTER_SHA,
        review_status="unreviewed",
        evidence_state=state,
        stage3_source_record_id=candidate_id,
    )


def _acquisition(tmp_path, *, records=None, missing=None, annotation=False):
    run_root = RunRoot(str(tmp_path / "runroot"))
    admission = _annotation_admission() if annotation else _admission()
    cid = admission.candidate_set.candidates[0].candidate_id

    if records is None:
        records = [
            _record(run_root, key="pubchem.property", raw=PUBCHEM_JSON, stable_id="5394",
                    source_type="public_api", transform="PubChem PUG REST property table",
                    candidate_id=cid),
            _record(run_root, key="dailymed.spl",
                    raw=_spl_for(admission.candidate_set.candidates[0].active_moiety
                                 .active_moiety_name),
                    stable_id="setid-1", source_type="regulatory_label",
                    transform="parse SPL LOINC sections and nested subsections",
                    candidate_id=cid),
        ]
    else:
        records = records(run_root, cid)

    manifest = AcquisitionManifest(
        schema_id="spot.stage04_acquisition_manifest.v1",
        run_id="acqrun-0001",
        stage3_binding={"stage3_document_id": "fx_c5b44dd8bee36b7d"},
        source_ledger_sha256="b" * 64,
        records=records,
        missing=list(missing or []),
    )
    run_root.write_manifest(manifest)      # the verifier reads it from the run root, as it would
    return admission, manifest, run_root


def _materialize(tmp_path, **kw):
    admission, manifest, run_root = _acquisition(tmp_path, **kw)
    doc = materialize(admission, manifest, run_root, ContractVersion.V2)
    return doc, run_root


def _write(tmp_path, doc):
    path = str(tmp_path / "evidence_bundle.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
    return path


# ----------------------------------------------------------------- it produces a REAL bundle

def test_the_materialized_bundle_LOADS_through_the_frozen_evidence_door(tmp_path):
    """The whole point: what comes out is what `run_stage4 --evidence-bundle` consumes. If this
    fails, the bridge does not connect and the pipeline still has a hole in the middle."""
    doc, _ = _materialize(tmp_path)
    loaded = load_evidence_bundle(_write(tmp_path, doc))

    assert loaded["contract_version"] is ContractVersion.V2
    assert loaded["safety_records"], "the DailyMed label contributed no labelled finding"
    assert loaded["properties"], "PubChem contributed no property"
    assert loaded["source_acquisition"], "the bundle stands on no acquisition record"


def test_the_label_findings_reach_the_bundle_with_the_subsection_they_were_read_from(tmp_path):
    """Nested warnings survive the whole chain — the parser fix, into the materialized bundle."""
    doc, _ = _materialize(tmp_path)
    warnings = [r for r in doc["safety_records"] if r["finding_type"] == "warning_precaution"]
    assert warnings

    titles = {(r.get("label_identity") or {}).get("labeled_subsection_name") for r in warnings}
    for n in ("5.1", "5.2", "5.6"):
        assert any(t and t.startswith(n) for t in titles), f"warning {n} was dropped: {titles}"
    assert not any("HIGHLIGHTS RESTATEMENT" in (r.get("finding_text") or "")
                   for r in doc["safety_records"]), "the Highlights excerpt became evidence"


def test_it_is_DETERMINISTIC(tmp_path):
    """Same manifest, same bytes -> byte-identical bundle. A materializer whose output depends on
    dict order cannot be re-derived by anyone, so nothing downstream of it can be checked."""
    a, _ = _materialize(tmp_path / "a")
    b, _ = _materialize(tmp_path / "b")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# --------------------------------------------------- what it REFUSES to invent (the whole job)

def test_CNS_MPO_stays_incomplete_rather_than_being_finished_with_a_substitute(tmp_path):
    """PubChem has no ClogD(7.4) and no most-basic pKa. Wager's method is defined against specific
    calculators, so XLogP3 is NOT ClogP. The bundle carries what was sourced, names the calculator,
    and leaves CNS-MPO incomplete — which is the honest answer, not a failure."""
    doc, _ = _materialize(tmp_path)
    props = {p["property_id"] for p in doc["properties"]}

    assert props, "PubChem sourced nothing at all"
    for absent in ("clogd_74", "pka_most_basic", "logD7.4", "most_basic_pKa"):
        assert absent not in props, f"{absent} was materialized from a source that does not have it"

    for row in doc["properties"]:
        assert row["calculator_id"].startswith("pubchem::"), (
            "a property row does not name the calculator that produced it")
        assert row["determination"] == "predicted", (
            "a COMPUTED PubChem descriptor was dressed up as an experimental measurement")
        # `accepted` is the CALCULATOR POLICY's decision, made in the engine. The materializer
        # must not pre-accept a descriptor into a CNS-MPO slot the method says it cannot fill.
        assert "accepted" not in row, (
            "the materializer decided acceptance itself, bypassing the calculator policy")


@pytest.mark.parametrize("lane", ["exposures", "transporters", "nebpi_observations",
                                  "fraction_unbound", "potency_context_links"])
def test_no_lane_a_public_source_cannot_supply_is_ever_populated(tmp_path, lane):
    """THE firewall. There is no public adapter for a brain concentration, an efflux ratio, an
    NEBPI observation or an fu. Absence of an exposure measurement is not evidence of
    impermeability, and a materializer that fills these in has fabricated a PK claim."""
    doc, _ = _materialize(tmp_path)
    assert doc[lane] == [], f"{lane} was populated from an acquisition that cannot supply it"


def test_every_empty_lane_is_STATED_not_evaluated_with_a_reason(tmp_path):
    """Silence reads as "nothing was wrong". It must read as "nobody looked"."""
    doc, _ = _materialize(tmp_path)
    stated = {s["lane"]: s for s in doc["config"]["not_evaluated"]}

    for lane in ("exposures", "transporters", "nebpi_observations", "fraction_unbound"):
        assert lane in stated, f"{lane} is empty and says nothing about why"
        assert stated[lane]["evidence_state"] == "not_evaluated"
        assert len(stated[lane]["reason"]) > 20, "a reason that explains nothing is not a reason"

    assert "impermea" in stated["exposures"]["reason"].lower(), (
        "the exposure absence must say, in writing, that it is NOT evidence of impermeability")


def test_the_stated_absences_are_hashed_into_the_release_identity(tmp_path):
    """`config` feeds `scorecard_set_id`. So an absence is part of what identifies the release —
    quietly dropping a lane cannot leave the id unchanged."""
    doc, _ = _materialize(tmp_path)
    assert doc["config"]["not_evaluated"], "no absence was stated at all"
    assert doc["config"]["acquisition_manifest_sha256"]
    assert doc["config"]["acquisition_run_id"] == "acqrun-0001"


def test_organ_system_is_source_backed_or_unspecified_never_inferred(tmp_path):
    """`ORGAN_SYSTEM_SPECS` is empty: no source in the ledger states an organ system in a coded
    field. So every row must say `unspecified`. A hepatic warning does not make it `hepatic`."""
    doc, _ = _materialize(tmp_path)
    systems = {(r.get("organ_system_evidence") or {}).get("organ_system")
               for r in doc["safety_records"]}
    assert systems == {"unspecified"}, f"an organ system was inferred from label wording: {systems}"


def test_a_label_for_a_DIFFERENT_molecule_is_refused(tmp_path):
    """The identity firewall. A DailyMed label for FIXTURIMAB may not become safety evidence for
    a candidate that is not FIXTURIMAB — that is how a real safety finding gets attached to the
    wrong drug, and it is refused by name rather than bound on a hopeful match."""
    from analysis.safety import LabelIdentityError

    def _wrong_molecule(run_root, cid):
        return [_record(run_root, key="dailymed.spl", raw=fixture_bytes(SPL),
                        stable_id="setid-1", source_type="regulatory_label",
                        transform="parse SPL", candidate_id=cid)]

    with pytest.raises(LabelIdentityError):
        _materialize(tmp_path, records=_wrong_molecule)


def test_a_FIXTURE_may_never_be_laundered_into_a_materialized_bundle(tmp_path):
    """A materialized bundle is made of bytes a reviewer can fetch again."""
    def _fixture_records(run_root, cid):
        # `synthetic_fixture` + `observed` is refused by the AcquisitionRecord contract itself
        # ("a synthetic fixture is not an observation of anything"), so the only way to smuggle a
        # fixture into a manifest at all is as a non-observation. The materializer refuses that
        # too: a bundle is made of bytes somebody can fetch again.
        return [_record(run_root, key="pubchem.property", raw=PUBCHEM_JSON, stable_id="5394",
                        source_type="public_api", transform="PubChem property table",
                        origin="synthetic_fixture", state="not_applicable", candidate_id=cid)]

    with pytest.raises(MaterializationError) as exc:
        _materialize(tmp_path, records=_fixture_records)
    assert exc.value.code == "fixture_evidence_in_materialized_bundle"


def test_a_record_that_was_never_OBSERVED_contributes_no_evidence(tmp_path):
    """`not_evaluated` means nobody looked. It is provenance, never data."""
    def _unobserved(run_root, cid):
        return [_record(run_root, key="pubchem.property", raw=PUBCHEM_JSON, stable_id="5394",
                        source_type="public_api", transform="PubChem property table",
                        state="not_evaluated", candidate_id=cid)]

    # `not_evaluated` with bytes is refused by the record contract itself — which is the point:
    # a hash behind "nobody looked" would be a fiction.
    with pytest.raises(Exception):
        _materialize(tmp_path, records=_unobserved)


# ------------------------------------------------------- the INDEPENDENT verifier, and mutation

def test_the_independent_verifier_admits_a_real_materialized_bundle(tmp_path):
    doc, run_root = _materialize(tmp_path)
    report = verify_bundle(_write(tmp_path, doc), run_root.root)
    failed = [c for c in report["checks"] if c["status"] == "fail"]
    assert report["status"] == "pass", f"a real materialized bundle does not verify: {failed}"


def test_a_FABRICATED_exposure_is_REFUSED_by_the_independent_verifier(tmp_path):
    """The attack that matters: a brain concentration nobody measured, spliced into a bundle that
    is otherwise perfectly real. Every hash still reproduces — only the firewall can catch it."""
    doc, run_root = _materialize(tmp_path)
    doc["exposures"] = [{
        "measurement_id": "EXP-FAKE", "candidate_id": "AM:INCHIKEY:SYNTHAAAAAAAAA-BBBBBBBBBB-N",
        "matrix": "brain_tissue_non_enhancing", "concentration_source_string": "1.2",
        "concentration_units": "uM", "detection_status": "detected",
    }]
    report = verify_bundle(_write(tmp_path, doc), run_root.root)

    assert report["status"] == "fail"
    assert any(c["check_id"] == "no_brain_exposure_or_safety_inferred_from_missing_data"
               and c["status"] == "fail" for c in report["checks"]), (
        "a manufactured brain exposure passed the independent bundle verifier")


def test_a_row_whose_HASH_does_not_reproduce_from_the_cache_is_REFUSED(tmp_path):
    """A row may only rest on bytes that are actually in the run root, and that actually hash to
    what the row claims. Otherwise the provenance chain is decorative."""
    doc, run_root = _materialize(tmp_path)
    doc["safety_records"][0]["provenance"]["raw_response_sha256"] = "c" * 64
    report = verify_bundle(_write(tmp_path, doc), run_root.root)

    assert report["status"] == "fail"
    assert any(c["check_id"] == "every_row_hash_matches_the_cached_bytes"
               and c["status"] == "fail" for c in report["checks"])


def test_a_row_citing_a_source_the_ACQUISITION_NEVER_MADE_is_REFUSED(tmp_path):
    doc, run_root = _materialize(tmp_path)
    doc["properties"][0]["provenance"]["source_record_id"] = "acq.invented.never_fetched"
    report = verify_bundle(_write(tmp_path, doc), run_root.root)

    assert report["status"] == "fail"
    assert any(c["check_id"] == "every_cited_source_was_acquired"
               and c["status"] == "fail" for c in report["checks"])


def test_SILENTLY_dropping_a_stated_absence_is_REFUSED(tmp_path):
    """Deleting the `not_evaluated` entry leaves an empty lane that reads as "nothing was wrong".
    `unbound_prose` cannot catch a deletion, and neither can a hash. This can."""
    doc, run_root = _materialize(tmp_path)
    doc["config"]["not_evaluated"] = [
        s for s in doc["config"]["not_evaluated"] if s["lane"] != "exposures"]
    report = verify_bundle(_write(tmp_path, doc), run_root.root)

    assert report["status"] == "fail"
    assert any(c["check_id"] == "every_absent_lane_is_stated_not_evaluated"
               and c["status"] == "fail" for c in report["checks"])


def test_an_INFERRED_organ_system_is_REFUSED_by_the_independent_verifier(tmp_path):
    """The row says `hepatic` because a warning mentioned the liver. No source states it in a
    coded field, so no source backs it — and a safety burden attributed to an organ nobody named
    is exactly the inference this stage refuses to make."""
    doc, run_root = _materialize(tmp_path)
    doc["safety_records"][0]["organ_system_evidence"]["organ_system"] = "hepatic"
    report = verify_bundle(_write(tmp_path, doc), run_root.root)

    assert report["status"] == "fail"
    assert any(c["check_id"] == "no_inferred_organ_system" and c["status"] == "fail"
               for c in report["checks"]), "an inferred organ system passed the bundle verifier"


# ------------------------------------------------------ THE CHAIN: acquisition -> scorecard set

def test_the_materialized_bundle_DRIVES_run_stage4_end_to_end(tmp_path):
    """The whole reason this module exists.

    acquisition manifest + cached bytes -> materializer -> evidence bundle -> run_stage4 ->
    scorecard set -> INDEPENDENT verifier. Before the materializer there was no path from an
    acquired byte to a scorecard set at all, so no E2E claim was available to anyone.
    """
    import os as _os

    from analysis.run_stage4 import main
    from verifier.checks import verify_release

    doc, _run_root = _materialize(tmp_path)
    bundle = _write(tmp_path, doc)
    out_root = tmp_path / "out"

    rc = main(["--stage3-bundle", COMMITTED_BUNDLES["fixture"],
               "--evidence-bundle", bundle, "--outputs-root", str(out_root)])
    assert rc == 0, "the materialized bundle did not drive a real Stage-4 run"

    releases = list(out_root.rglob("manifest.json"))
    assert len(releases) == 1, f"expected one release, got {releases}"
    release = str(releases[0].parent)

    method_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                               "method")
    report = verify_release(release, method_dir)
    failed = [(c["check_id"], c["detail"]) for c in report["checks"] if c["status"] == "fail"]
    assert report["status"] == "pass", f"the release from a materialized bundle does not verify: {failed}"


def test_the_end_to_end_release_classifies_NOTHING_it_did_not_measure(tmp_path):
    """And the answer it gives is the honest one. A public acquisition supplies no brain exposure,
    so no candidate is NEBPI-classified and none is called permeable or safe. This is the result,
    and it is not a failure — it is what the evidence supports."""
    import os as _os

    import pyarrow.parquet as pq

    from analysis.run_stage4 import main

    doc, _run_root = _materialize(tmp_path)
    out_root = tmp_path / "out"
    assert main(["--stage3-bundle", COMMITTED_BUNDLES["fixture"],
                 "--evidence-bundle", _write(tmp_path, doc),
                 "--outputs-root", str(out_root)]) == 0

    release = str(next(out_root.rglob("manifest.json")).parent)
    decisions = pq.read_table(_os.path.join(release, "nebpi_decisions.parquet")).to_pylist()

    for d in decisions:
        assert d.get("nebpi_class") in (None, "not_classifiable"), (
            f"a NEBPI class was manufactured from an acquisition that measured no exposure: "
            f"{d.get('nebpi_class')!r}")
        assert not d.get("nebpi_primary_gate"), "an unmeasured candidate passed the primary gate"


# ------------------------------------------------------------------------------------ the CLI

def test_the_CLI_writes_a_bundle_and_reports_what_it_could_not_reach(tmp_path, capsys):
    """`python -m analysis.run_materialize --stage3-bundle <dir> --run-root <R> --out <B>`"""
    from analysis.run_materialize import main

    _admission_, manifest, run_root = _acquisition(tmp_path, annotation=True)
    out = str(tmp_path / "bundle.json")

    rc = main(["--stage3-bundle", PINNED_ANNOTATION_BUNDLE,
               "--run-root", run_root.root, "--out", out])
    assert rc == 0
    assert os.path.exists(out)

    receipt = json.loads(capsys.readouterr().out)
    assert receipt["schema_id"] == "spot.stage04_evidence_bundle.v2"
    assert receipt["lanes_with_evidence"]["safety_records"] > 0
    # the CLI SAYS what it could not reach -- a reader never has to infer an absence
    assert "exposures" in receipt["not_evaluated"]
    assert "nebpi_observations" in receipt["not_evaluated"]


def test_the_CLI_REFUSES_when_no_acquisition_ever_ran(tmp_path, capsys):
    """A bundle can only be materialized from an acquisition that actually happened."""
    from analysis.run_materialize import main

    empty = tmp_path / "empty"
    empty.mkdir()
    rc = main(["--stage3-bundle", PINNED_ANNOTATION_BUNDLE,
               "--run-root", str(empty), "--out", str(tmp_path / "b.json")])

    assert rc == 2
    assert "acquisition_manifest_missing" in capsys.readouterr().err


def test_a_TAMPERED_acquisition_manifest_is_REFUSED(tmp_path):
    """Swap a record's hash after the acquisition ran and the manifest no longer describes the
    bytes on disk. Materializing it would mint an evidence bundle that LOOKS acquired."""
    from analysis.run_materialize import load_manifest

    _a, _m, run_root = _acquisition(tmp_path)
    path = os.path.join(run_root.root, "acquisition_manifest.json")
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["records"][0]["raw_sha256"] = "e" * 64          # content changes, content_sha256 does not
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)

    with pytest.raises(Rejection) as exc:
        load_manifest(run_root.root)
    assert exc.value.code == "acquisition_manifest_tampered"
