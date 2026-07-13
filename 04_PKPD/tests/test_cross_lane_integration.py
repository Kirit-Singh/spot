"""CROSS-LANE INTEGRATION GATE — owned by the integration verifier, not by W8 or W9.

The Stage-4 build is split:

    W8  agent/stage4-acquisition-core   public acquisition core (fetch, manifest, selection)
    W9  agent/stage4-pk-schema          typed PK / potency / exposure schema

Both branch from `e410d72`. Each lane has its own tests for its own code. These tests are
different: they hold the SEAM that neither lane owns, and that a green lane-local suite
would not catch —

    admitted Stage-3 bundle -> acquisition manifest -> rich evidence contract
        -> current NEBPI/safety engine -> INDEPENDENT verifier

They pass today on `e410d72`, so they are a real baseline and not aspirational. They are the
gate a lane's commit must keep green before it is cherry-picked.

What is deliberately NOT here (already covered, and duplicating it would be noise):
`test_emit_verify` owns scorecard_set_id derivation/stability, artifact emission, mutation
detection and the composite-score firewall. These tests own only what is between the lanes.
"""

from __future__ import annotations

import os
from dataclasses import replace

import pyarrow.parquet as pq
import pytest

from analysis.emit import emit
from analysis.evidence_bundle import LANE_MODELS, load_evidence_bundle
from analysis.label_adapters import parse_dailymed_spl
from analysis.method_config import load_method_bundle
from analysis.pipeline import run_pipeline
from analysis.safety import safety_rows_from_label
from fixtures import fixture_bytes, stage4_inputs
from verifier.checks import verify_release

METHOD = load_method_bundle()
METHOD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "method")

# The nested SPL is a DailyMed label for FIXTURIMAB (UNII YYYYYYYY88) — the molecule the
# openFDA fixture describes. A real molecule carries records in both sources, so the binding is
# honest and the identity guard proves it from the bytes.
NESTED_SPL = "dailymed_spl_nested_fixture.xml"
FIXTURE_CANDIDATE = "FIXTURE-002"
FIXTURE_MOIETY = "FXM-002"


# A second label is a SECOND SOURCE: its own record id and its own bytes. The provenance
# firewall enforces this — a row citing the flat SPL's source id while carrying the nested
# SPL's hash is refused (`source_hash_mismatch`), and it should be.
NESTED_SOURCE_ID = "src.fixture.label.dailymed.nested"


def _nested_source_record():
    from analysis.canonical import sha256_bytes
    from analysis.contracts import SourceRecord

    raw = fixture_bytes(NESTED_SPL)
    return SourceRecord(
        source_record_id=NESTED_SOURCE_ID,
        source_type="fixture",
        source_name=f"FIXTURE label response ({NESTED_SPL}) — nested subsections",
        acquisition_status="synthetic_fixture",
        access_date="2026-07-13",
        raw_sha256=sha256_bytes(raw),
        raw_bytes=len(raw),
    )


def _nested_safety_rows(candidate_id=FIXTURE_CANDIDATE, moiety_id=FIXTURE_MOIETY):
    """Real rows, from the real recursive parser. Not hand-authored."""
    spl = parse_dailymed_spl(fixture_bytes(NESTED_SPL))
    return safety_rows_from_label(
        spl, candidate_id, moiety_id, NESTED_SOURCE_ID,
        "2026-07-13",
        "parse SPL LOINC sections and their nested component/section subsections",
        expected_unii="YYYYYYYY88", expected_moiety_name="FIXTURIMAB",
    )


def _inputs_with_nested_label():
    base = stage4_inputs()
    return replace(
        base,
        sources={**base.sources, NESTED_SOURCE_ID: _nested_source_record()},
        safety_records=list(base.safety_records) + _nested_safety_rows(),
    )


def _emit_with_nested_label(tmp_path):
    """Drive the WHOLE chain with a label whose warnings are nested. -> the release dir."""
    inputs = _inputs_with_nested_label()
    result = run_pipeline(inputs, METHOD)
    out, _manifest = emit(inputs, result, METHOD, str(tmp_path))
    return out


# ------------------------------------------------ SEAM A: e410d72 survives the whole chain

def test_nested_warning_provenance_reaches_the_emitted_release(tmp_path):
    """THE cross-lane lock.

    `e410d72` fixed a parser that silently dropped every nested warning. Nothing, however,
    drives a nested label all the way to the emitted artifact — the pipeline fixture uses the
    FLAT SPL. So W8 could rewrite acquisition, or W9 could reshape the evidence contract, drop
    the subsection provenance on the floor, and every existing test would stay green.

    This asserts the six nested warnings reach `safety_evidence.parquet` WITH the subsection
    they were read from. If a lane breaks it, it breaks here.
    """
    out = _emit_with_nested_label(tmp_path)
    rows = pq.read_table(os.path.join(out, "safety_evidence.parquet")).to_pylist()

    nested = [r for r in rows if r.get("setid") == "ffffffff-0000-4000-8000-fixturespl003"]
    assert nested, "the nested label contributed no evidence to the release at all"

    warnings = [r for r in nested if r["finding_type"] == "warning_precaution"]
    titles = {r["labeled_subsection_name"] for r in warnings}
    for n in ("5.1", "5.2", "5.3", "5.4", "5.5", "5.6"):
        assert any(t and t.startswith(n) for t in titles), (
            f"warning {n} did not survive the chain into the release: {sorted(titles)}")

    for w in warnings:
        # the safety TYPE stays the ancestor LOINC section...
        assert w["labeled_section_code"] == "43685-7"
        # ...and the row can still name the subsection it was actually read from
        assert w["labeled_subsection_code"] == "42229-5"
        assert w["labeled_subsection_name"]

    # the <excerpt> Highlights restatement must never have become evidence
    assert not any("HIGHLIGHTS RESTATEMENT" in (r.get("finding_text") or "") for r in rows)


def test_the_independent_verifier_admits_the_release_built_from_a_nested_label(tmp_path):
    """The chain ends at the INDEPENDENT verifier, not at the engine's own say-so."""
    out = _emit_with_nested_label(tmp_path)
    report = verify_release(out, METHOD_DIR)
    assert report["status"] == "pass", report


def test_a_nested_finding_is_not_double_counted_in_the_release(tmp_path):
    """5.6 repeats 5.1's sentence verbatim, as real labels do. The release must carry it once —
    emitting twice double-counts a labeled claim, and dropping it at random is irreproducible."""
    out = _emit_with_nested_label(tmp_path)
    rows = pq.read_table(os.path.join(out, "safety_evidence.parquet")).to_pylist()
    nested = [r for r in rows if r.get("setid") == "ffffffff-0000-4000-8000-fixturespl003"]
    keys = [(r["finding_type"], r["finding_text"]) for r in nested]
    assert len(keys) == len(set(keys)), "a nested finding was double-counted in the release"


# ---------- SEAM B: BLOCKER for W8 — one moiety cannot carry two labels (evidence_id collides)

def test_two_labels_for_one_moiety_currently_COLLIDE_on_evidence_id():
    """A BLOCKING cross-lane finding, pinned in code so it cannot be forgotten.

    `analysis/safety.py:117` derives
        evidence_id = f"{candidate_id}.{label_source}.{finding_type}.{i:03d}"
    with `i` restarting at 0 on every call. The label's own identity (setid, version) is NOT in
    the id. So two DailyMed SPLs for the SAME moiety produce the same ids and the run is
    REFUSED by the duplicate-id firewall.

    It fails CLOSED, which is the right instinct — but it means Stage 4 cannot ingest more than
    one label per moiety at all, and the audit's own sequence requires exactly that:
    "parse every selected label version; do not select an arbitrary first hit" (§5.4). Real
    drugs carry many SPLs (temozolomide: 20 on DailyMed).

    W8 (acquisition/selection) will hit this on its first multi-label fetch. The fix — putting
    the setid/version into the evidence_id — CHANGES v1 evidence ids and therefore every
    scorecard_set_id, so it is a deliberate contract decision for the orchestrator, not
    something a lane may do quietly. This test asserts TODAY's behaviour; when the id scheme
    changes it must be updated on purpose, with the reproducibility cost stated.
    """
    from analysis.firewall import Rejection
    from analysis.integrity import check_referential_integrity

    base = _inputs_with_nested_label()
    # Two DailyMed labels for the same moiety — exactly what label discovery produces. (Here the
    # same parsed SPL twice; two DIFFERENT setids collide identically, because the setid is not
    # part of the id.)
    doubled = replace(base, safety_records=list(base.safety_records) + _nested_safety_rows())
    with pytest.raises(Rejection) as exc:
        check_referential_integrity(doubled)
    assert exc.value.code == "duplicate_id"
    assert "evidence_id" in str(exc.value)


# ------------------------------- SEAM C: W9 must not break a v1 bundle (forward-compat gate)

def test_a_v1_evidence_bundle_stays_loadable(tmp_path):
    """W9 is reshaping the PK/potency/exposure contract. A richer schema is welcome; a schema
    that REFUSES the bundles v1 already produces is a reproducibility break, not an upgrade.

    Every lane the contract declares must still accept a v1-shaped row. If W9 needs a new
    REQUIRED field, that is a deliberate contract break and must arrive with a migration —
    this test is where that conversation starts, rather than a silent failure in a real run.
    """
    import json

    base = stage4_inputs()
    bundle = {"schema_id": "spot.stage04_evidence_bundle.v1",
              "sources": {k: json.loads(v.model_dump_json()) for k, v in base.sources.items()}}
    for lane in LANE_MODELS:
        rows = getattr(base, lane, None)
        bundle[lane] = [json.loads(r.model_dump_json()) for r in (rows or [])]

    path = str(tmp_path / "v1_bundle.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, sort_keys=True)

    loaded = load_evidence_bundle(path)          # the frozen door, unmodified
    assert loaded["properties"], "a v1 evidence bundle no longer loads — reproducibility broke"
    assert loaded["safety_records"]


# ---------------------------------- SEAM C: neither lane may fabricate what it cannot acquire

def test_an_unacquirable_lane_stays_empty_and_is_never_inferred(tmp_path):
    """The audit's standing verdict: there is no production acquisition adapter for any PK
    lane. W8/W9 must make those lanes ACQUIRABLE, never FILLED. A candidate with no observation
    is never rendered safe, permeable, or NEBPI-classified — absence of evidence is not a
    result, and this is the gate that says so in code.
    """
    base = stage4_inputs()
    stripped = replace(base, properties=[], potencies=[], exposures=[], transporters=[],
                       nebpi_observations=[], delivery_assignments=[], potency_context_links=[])
    result = run_pipeline(stripped, METHOD)
    out, _ = emit(stripped, result, METHOD, str(tmp_path))

    # the engine still emits an honest artifact set, and the INDEPENDENT verifier admits it...
    assert verify_release(out, METHOD_DIR)["status"] == "pass"

    # ...but nothing in it claims permeability, safety, or a NEBPI class it never measured.
    decisions = pq.read_table(os.path.join(out, "nebpi_decisions.parquet")).to_pylist()
    for d in decisions:
        assert d.get("nebpi_class") in (None, "not_classifiable"), (
            f"a NEBPI class was manufactured from zero evidence: {d.get('nebpi_class')!r}")
        assert not d.get("nebpi_primary_gate"), "an unmeasured candidate passed the primary gate"


def test_the_release_never_carries_a_composite_or_traffic_light_for_a_nested_label(tmp_path):
    """The firewall is not lane-local: a new acquisition path must not smuggle a rolled-up
    score in with richer evidence."""
    out = _emit_with_nested_label(tmp_path)
    banned = ("overall_score", "composite_score", "traffic_light", "safety_score",
              "risk_score", "combined_score", "overall_rank")
    for name in os.listdir(out):
        if not name.endswith(".parquet"):
            continue
        cols = set(pq.read_schema(os.path.join(out, name)).names)
        assert not (cols & set(banned)), f"{name} carries a composite objective: {cols & set(banned)}"
