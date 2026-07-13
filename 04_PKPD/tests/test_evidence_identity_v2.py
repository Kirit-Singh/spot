"""Evidence identity v2 — a label DOCUMENT is part of the identity of its findings.

The v1 identity is

    {candidate_id}.{label_source}.{finding_type}.{NNN}          # NNN restarts at 0 per call

which carries nothing about WHICH label the finding was read from. Two DailyMed SPLs for one
moiety therefore produce the same ids and the run is refused (`duplicate_id`). It fails closed —
correct — but it means Stage 4 cannot ingest more than one label per moiety at all, and the
source audit requires exactly that: "parse every selected label version; do not select an
arbitrary first hit" (§5.4). Temozolomide carries 20 SPLs on DailyMed.

v2 puts the setid and the label version into the id. It is **opt-in**: v1 is the default and is
preserved BYTE-FOR-BYTE, so every existing scorecard_set_id is unchanged. W8's acquisition path
selects v2; nothing else moves.

The three properties the orchestrator asked to be proved, and that a real multi-label
acquisition depends on:

  * COLLISION      two labels for one moiety no longer collide, and DO under v1;
  * DETERMINISTIC  the same labels in any processing order give the same release identity;
  * BYTE BINDING   each label document is its own SourceRecord, and a finding cannot cite one
                   document's source id while carrying another document's bytes.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from analysis.contracts import ID_PATTERN
from analysis.emit import environment_lock
from analysis.firewall import Rejection
from analysis.ids import derive_scorecard_set_id
from analysis.integrity import check_referential_integrity
from analysis.label_adapters import parse_dailymed_spl
from analysis.method_config import load_method_bundle
from analysis.safety import (
    EVIDENCE_IDENTITY_V1,
    EVIDENCE_IDENTITY_V2,
    safety_rows_from_label,
    source_record_for_label,
)
from fixtures import fixture_bytes, stage4_inputs

METHOD = load_method_bundle()

FLAT = "dailymed_spl_fixture.xml"        # FIXTURIB  / ZZZZZZZZ99, setid …spl001, v7
NESTED = "dailymed_spl_nested_fixture.xml"  # FIXTURIMAB / YYYYYYYY88, setid …spl003, v40


def _parsed(name):
    return parse_dailymed_spl(fixture_bytes(name))


def _rows(name, source_id, scheme, candidate="FIXTURE-002", moiety="FXM-002",
          unii="YYYYYYYY88", moiety_name="FIXTURIMAB"):
    return safety_rows_from_label(
        _parsed(name), candidate, moiety, source_id, "2026-07-13",
        "parse SPL LOINC sections and their nested component/section subsections",
        expected_unii=unii, expected_moiety_name=moiety_name,
        evidence_identity=scheme,
    )


# --------------------------------------------------------------- v1 preserved byte-for-byte

def test_v1_is_the_default_and_is_unchanged():
    """The whole point of Option A: adding v2 must not move a single v1 id."""
    rows = _rows(NESTED, "src.x", EVIDENCE_IDENTITY_V1)
    default = safety_rows_from_label(
        _parsed(NESTED), "FIXTURE-002", "FXM-002", "src.x", "2026-07-13",
        "parse SPL LOINC sections and their nested component/section subsections",
        expected_unii="YYYYYYYY88", expected_moiety_name="FIXTURIMAB")
    assert [r.evidence_id for r in default] == [r.evidence_id for r in rows]
    # the exact v1 shape, unchanged
    assert rows[0].evidence_id == "FIXTURE-002.dailymed_spl.contraindication.000"


# The v1 CONTENT digests, pinned to literals measured before v2 existed (at `6aed6d3`). These
# are the "byte-for-byte" guarantee, and unlike a self-comparison they survive a code change.
V1_EVIDENCE_INPUTS_SHA256 = "8999c5a38c8df8bb85ef2ca16cf5dd6decdddea81f4b48069cb61b680c47c6f5"
# The FIXTURE's source registry, re-pinned: W9's canonical fixtures gained acquisition source
# records, so the registry over the fixture set legitimately grew. This is a fixture pin, not a
# contract pin — the AUTHORITATIVE v1 freeze is the checked-in historical release
# (`test_contract_version_freeze.py`), a real e410d72 artifact rather than a recomputation.
# The line that must never move is the one above: the v1 evidence CONTENT digest.
V1_SOURCE_REGISTRY_SHA256 = "2cf748aa73bae7a5b78b237b5038cfc5df27e11e6ccec3fea91c4f467befae21"


def test_the_v1_evidence_CONTENT_is_byte_for_byte_unchanged():
    """What "preserve v1 byte-for-byte" can and cannot mean — stated exactly, because the
    difference is load-bearing.

    CAN, and is pinned here: every v1 evidence ROW, every v1 evidence ID, and the v1 source
    registry are byte-identical after v2 was added. Adding an opt-in identity scheme moved no
    v1 datum. These digests were measured at `6aed6d3`, before v2 existed.

    CANNOT, and must not: the `scorecard_set_id` itself. It binds `analysis_code_sha256`, so it
    moves whenever the engine's code moves — including for this change. That is the anti-tamper
    property, not a regression: if the id had NOT moved after the scoring code changed, someone
    could alter the engine and keep the old release identity. `test_emit_verify.
    test_altering_the_scoring_code_changes_the_id` exists to force exactly that movement.

    So: v1 DATA is frozen; the v1 release IDENTITY correctly tracks the engine that produced it.
    """
    inputs = stage4_inputs()
    _sid, key = derive_scorecard_set_id(
        inputs.candidate_set, METHOD, inputs.evidence_lanes(), inputs.sources,
        environment_lock()["lock_sha256"], inputs.config)

    assert key["evidence_inputs_sha256"] == V1_EVIDENCE_INPUTS_SHA256, (
        "a v1 evidence row changed. Adding v2 must not move a single v1 datum.")
    assert key["source_registry_sha256"] == V1_SOURCE_REGISTRY_SHA256, (
        "the v1 source registry changed.")


# ------------------------------------------------------------------------------- collision

def test_two_labels_for_one_moiety_COLLIDE_under_v1():
    """The blocker, restated as a test: this is what v2 exists to fix."""
    a = _rows(NESTED, "src.a", EVIDENCE_IDENTITY_V1)
    b = _rows(FLAT, "src.b", EVIDENCE_IDENTITY_V1,
              unii="ZZZZZZZZ99", moiety_name="FIXTURIB")
    assert set(r.evidence_id for r in a) & set(r.evidence_id for r in b), (
        "v1 ids are expected to collide across two labels — if they no longer do, v2 has been "
        "applied by default and v1 reproducibility is broken")


def test_two_labels_for_one_moiety_DO_NOT_collide_under_v2():
    a = _rows(NESTED, "src.a", EVIDENCE_IDENTITY_V2)
    b = _rows(FLAT, "src.b", EVIDENCE_IDENTITY_V2,
              unii="ZZZZZZZZ99", moiety_name="FIXTURIB")
    ids_a, ids_b = [r.evidence_id for r in a], [r.evidence_id for r in b]
    assert not (set(ids_a) & set(ids_b)), "v2 ids still collide across labels"
    assert len(set(ids_a + ids_b)) == len(ids_a) + len(ids_b)


def test_a_v2_id_names_the_document_it_was_read_from():
    r = _rows(NESTED, "src.a", EVIDENCE_IDENTITY_V2)[0]
    assert "ffffffff-0000-4000-8000-fixturespl003" in r.evidence_id, "the setid is not in the id"
    assert ".v40." in r.evidence_id, "the label version is not in the id"
    assert r.evidence_id != "FIXTURE-002.dailymed_spl.contraindication.000"


def test_every_v2_id_is_a_legal_identifier():
    """A setid is a 36-char UUID. The id must still satisfy the contract's ID_PATTERN (<=128)."""
    import re
    for name, unii, mname in ((NESTED, "YYYYYYYY88", "FIXTURIMAB"),
                              (FLAT, "ZZZZZZZZ99", "FIXTURIB")):
        for r in _rows(name, "src.a", EVIDENCE_IDENTITY_V2, unii=unii, moiety_name=mname):
            assert re.match(ID_PATTERN, r.evidence_id), f"illegal v2 id: {r.evidence_id!r}"


def test_two_labels_under_v2_pass_referential_integrity():
    """The duplicate-id firewall refused this under v1. Under v2 the run is admissible."""
    base = stage4_inputs()
    parsed_n, parsed_f = _parsed(NESTED), _parsed(FLAT)
    src_n = source_record_for_label(parsed_n, source_record_id="src.label.nested",
                                    acquisition_status="synthetic_fixture",
                                    access_date="2026-07-13")
    src_f = source_record_for_label(parsed_f, source_record_id="src.label.flat",
                                    acquisition_status="synthetic_fixture",
                                    access_date="2026-07-13")
    rows = (_rows(NESTED, "src.label.nested", EVIDENCE_IDENTITY_V2)
            + _rows(FLAT, "src.label.flat", EVIDENCE_IDENTITY_V2,
                    unii="ZZZZZZZZ99", moiety_name="FIXTURIB"))
    inputs = replace(base,
                     sources={**base.sources, "src.label.nested": src_n, "src.label.flat": src_f},
                     safety_records=list(base.safety_records) + rows)
    check_referential_integrity(inputs)      # must not raise


# -------------------------------------------------------------------------- deterministic order

def test_the_release_identity_does_not_depend_on_the_order_labels_were_processed():
    """W8 will fetch many labels. Whichever order they come back in, the release must be the
    same artifact — otherwise a re-run of the same acquisition is a different release."""
    base = stage4_inputs()
    parsed_n, parsed_f = _parsed(NESTED), _parsed(FLAT)
    srcs = {
        "src.label.nested": source_record_for_label(
            parsed_n, source_record_id="src.label.nested",
            acquisition_status="synthetic_fixture", access_date="2026-07-13"),
        "src.label.flat": source_record_for_label(
            parsed_f, source_record_id="src.label.flat",
            acquisition_status="synthetic_fixture", access_date="2026-07-13"),
    }
    n = _rows(NESTED, "src.label.nested", EVIDENCE_IDENTITY_V2)
    f = _rows(FLAT, "src.label.flat", EVIDENCE_IDENTITY_V2,
              unii="ZZZZZZZZ99", moiety_name="FIXTURIB")

    def sid_for(order):
        i = replace(base, sources={**base.sources, **srcs},
                    safety_records=list(base.safety_records) + order)
        return derive_scorecard_set_id(i.candidate_set, METHOD, i.evidence_lanes(), i.sources,
                                       environment_lock()["lock_sha256"], i.config)[0]

    assert sid_for(n + f) == sid_for(f + n), (
        "the release identity depends on the order labels were processed in")


# --------------------------------------------------------- cross-source byte binding

def test_each_label_document_is_its_own_source_record_bound_to_its_own_bytes():
    parsed_n, parsed_f = _parsed(NESTED), _parsed(FLAT)
    src_n = source_record_for_label(parsed_n, source_record_id="src.label.nested",
                                    acquisition_status="synthetic_fixture",
                                    access_date="2026-07-13")
    src_f = source_record_for_label(parsed_f, source_record_id="src.label.flat",
                                    acquisition_status="synthetic_fixture",
                                    access_date="2026-07-13")
    # bytes come from the PARSED document, never hand-passed
    assert src_n.raw_sha256 == parsed_n.raw_sha256 != parsed_f.raw_sha256 == src_f.raw_sha256
    assert src_n.raw_bytes == parsed_n.raw_bytes
    assert src_n.record_id == parsed_n.setid
    assert "40" in (src_n.release_version or ""), "the label version is not recorded on the source"


def test_a_finding_cannot_cite_one_document_while_carrying_anothers_bytes():
    """CROSS-SOURCE BYTE BINDING. A row from the nested SPL that cites the FLAT SPL's source
    record is refused: the raw hash it carries is not that source's bytes. This is what stops a
    multi-label acquisition from silently attributing one label's warnings to another."""
    base = stage4_inputs()
    parsed_f = _parsed(FLAT)
    src_f = source_record_for_label(parsed_f, source_record_id="src.label.flat",
                                    acquisition_status="synthetic_fixture",
                                    access_date="2026-07-13")
    # nested-SPL findings, but citing the FLAT document's source record
    mis = _rows(NESTED, "src.label.flat", EVIDENCE_IDENTITY_V2)
    inputs = replace(base, sources={**base.sources, "src.label.flat": src_f},
                     safety_records=list(base.safety_records) + mis)
    with pytest.raises(Rejection) as exc:
        check_referential_integrity(inputs)
    assert exc.value.code == "source_hash_mismatch"


def test_a_finding_citing_a_source_that_was_never_acquired_is_refused():
    base = stage4_inputs()
    orphan = _rows(NESTED, "src.label.never-fetched", EVIDENCE_IDENTITY_V2)
    inputs = replace(base, safety_records=list(base.safety_records) + orphan)
    with pytest.raises(Rejection):
        check_referential_integrity(inputs)
