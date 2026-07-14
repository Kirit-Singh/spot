"""Label adapters (pure, cached bytes in) and the safety evidence rules."""

from __future__ import annotations

import pytest

from pydantic import ValidationError

from analysis.evidence_records import (
    EvidenceState,
    GbmScenario,
    InteractionType,
    Provenance,
    SafetyEvidenceRecord,
    SearchManifest,
)
from analysis.label_adapters import (
    EMA_ADAPTER_STATUS,
    SECTION_CODES,
    LabelParseError,
    parse_dailymed_spl,
    parse_ema_product_information,
    parse_openfda_label,
)
from analysis.method_config import load_method_bundle
from analysis.safety import (
    ForbiddenFieldError,
    LabelIdentityError,
    assert_no_forbidden_fields,
    render_evidence_state,
    safety_rows_from_label,
    scenario_matrix,
)
from fixtures import fixture_bytes

METHOD = load_method_bundle()
TAXONOMY = METHOD.safety_taxonomy


# ------------------------------------------------------------------------- adapters

def test_loinc_section_codes_are_the_ones_verified_against_live_spls():
    """Read from real DailyMed responses, not recalled. See method/sources.json.

    34084-4 (adverse reactions) was declared in the taxonomy but missing from the adapter,
    so labelled adverse-reaction material was silently uncollected.
    """
    assert SECTION_CODES == {
        "34066-1": "boxed_warning",
        "34070-3": "contraindication",
        "43685-7": "warning_precaution",
        "34073-7": "labeled_interaction",
        "34084-4": "adverse_reaction",
    }
    mapped = TAXONOMY["label_sections"]["map"]
    assert mapped["boxed_warning"]["loinc"] == "34066-1"
    assert mapped["drug_interactions"]["loinc"] == "34073-7"
    assert TAXONOMY["label_sections"]["code_system"] == "2.16.840.1.113883.6.1"


def test_dailymed_parser_binds_label_identity_and_splits_findings():
    parsed = parse_dailymed_spl(fixture_bytes("dailymed_spl_fixture.xml"))
    assert parsed.label_source == "dailymed_spl"
    assert parsed.setid == "ffffffff-0000-4000-8000-fixturespl001"
    assert parsed.label_version == "7"
    assert parsed.effective_date == "2026-04-01"
    assert parsed.active_moiety_unii == ["ZZZZZZZZ99"]
    assert parsed.raw_sha256 and parsed.raw_bytes > 0

    kinds = [f.finding_type for f in parsed.findings]
    # Two boxed-warning bullets -> two rows, not one wall of text.
    assert kinds.count("boxed_warning") == 2
    assert kinds.count("contraindication") == 1
    assert kinds.count("warning_precaution") == 2
    assert kinds.count("labeled_interaction") == 1
    # Adverse reactions are now collected too (34084-4).
    assert kinds.count("adverse_reaction") == 1
    assert all(f.code_system == "2.16.840.1.113883.6.1" for f in parsed.findings)


def test_parsers_are_pure_and_take_bytes():
    raw = fixture_bytes("dailymed_spl_fixture.xml")
    a, b = parse_dailymed_spl(raw), parse_dailymed_spl(raw)
    assert a == b  # deterministic
    with pytest.raises(LabelParseError):
        parse_dailymed_spl("<document/>")  # a str is not a cached response
    with pytest.raises(LabelParseError):
        parse_dailymed_spl(b"not xml at all")
    with pytest.raises(LabelParseError):
        parse_dailymed_spl(b"<html><body>error page</body></html>")


def test_openfda_parser():
    labels = parse_openfda_label(fixture_bytes("openfda_label_fixture.json"))
    assert len(labels) == 1
    lab = labels[0]
    assert lab.label_source == "openfda_label"
    assert lab.application_number == "BLA999999"
    assert lab.label_version == "3"
    assert lab.effective_date == "2026-03-15"
    kinds = [f.finding_type for f in lab.findings]
    assert kinds.count("boxed_warning") == 1
    assert kinds.count("warning_precaution") == 2
    assert kinds.count("adverse_reaction") == 1
    with pytest.raises(LabelParseError):
        parse_openfda_label(b'{"no_results": true}')


def test_ema_parser_is_declared_but_flagged_unverified():
    lab = parse_ema_product_information(fixture_bytes("ema_smpc_fixture.json"))
    assert lab.label_source == "ema_label"
    assert {f.finding_type for f in lab.findings} == {
        "contraindication", "warning_precaution", "labeled_interaction"
    }
    assert EMA_ADAPTER_STATUS == "shape_declared_unverified_against_live_source"


def test_label_rows_carry_version_section_and_response_hash():
    parsed = parse_dailymed_spl(fixture_bytes("dailymed_spl_fixture.xml"))
    rows = safety_rows_from_label(parsed, "C1", "M1", "src.label", "2026-07-11",
                                  "parse SPL sections", expected_unii="ZZZZZZZZ99")
    assert len(rows) == 7
    for r in rows:
        assert r.evidence_state == EvidenceState.LABEL_SUPPORTED
        assert r.label_identity.setid == parsed.setid
        assert r.label_identity.label_version == "7"
        assert r.label_identity.effective_date == "2026-04-01"
        assert r.label_identity.labeled_section_code in SECTION_CODES
        assert r.provenance.raw_response_sha256 == parsed.raw_sha256
        assert r.finding_text


def test_a_label_for_another_molecule_is_not_evidence_about_this_one():
    """The audit bound six FIXTURIB / UNII ZZZZZZZZ99 findings to active moiety FXM-004."""
    parsed = parse_dailymed_spl(fixture_bytes("dailymed_spl_fixture.xml"))
    with pytest.raises(LabelIdentityError, match="do not.*match|does not match"):
        safety_rows_from_label(parsed, "C4", "FXM-004", "src.label", "2026-07-11", "x",
                               expected_unii="QQQQQQQQ11", expected_moiety_name="SOMETHINGELSE")


def test_label_findings_cannot_be_bound_without_an_identity_to_match_on():
    parsed = parse_dailymed_spl(fixture_bytes("dailymed_spl_fixture.xml"))
    with pytest.raises(LabelIdentityError, match="without an identity to match"):
        safety_rows_from_label(parsed, "C1", "M1", "src.label", "2026-07-11", "x")


def test_ema_rows_cannot_become_label_supported_until_the_shape_is_validated():
    from analysis.label_adapters import EMA_LABEL_SUPPORTED_ALLOWED

    assert EMA_LABEL_SUPPORTED_ALLOWED is False
    lab = parse_ema_product_information(fixture_bytes("ema_smpc_fixture.json"))
    with pytest.raises(LabelIdentityError, match="not validated against a live EMA response"):
        safety_rows_from_label(lab, "C1", "M1", "src.ema", "2026-07-11", "x",
                               expected_moiety_name="fixturib")


def test_no_evidence_found_needs_a_reproducible_search_manifest():
    """A list of source names is not a search. Without the manifest it stays not_evaluated."""
    with pytest.raises(ValidationError, match="requires search_id"):
        SafetyEvidenceRecord(
            evidence_id="E1", candidate_id="C1", active_moiety_id="M1",
            evidence_state=EvidenceState.NO_EVIDENCE_FOUND,
            searched_sources=["dailymed"],
        )


def test_a_search_manifest_backing_a_negative_must_have_returned_nothing():
    with pytest.raises(ValidationError, match="must have returned 0 results"):
        SearchManifest(
            search_id="S1", source="dailymed_spl", endpoint="/spls", query_canonical="q",
            search_scope="all sections", executed_date="2026-07-11", n_results=3,
            provenance=Provenance(source_record_id="src.test", access_date="2026-07-11",
                                  raw_response_sha256="0" * 64, extraction_transform="t"),
        )


def test_label_supported_row_cannot_exist_without_a_label_and_a_source():
    with pytest.raises(ValidationError, match="label_supported requires"):
        SafetyEvidenceRecord(
            evidence_id="E1", candidate_id="C1", active_moiety_id="M1",
            evidence_state=EvidenceState.LABEL_SUPPORTED, finding_type="contraindication",
            finding_text="remembered from somewhere",
        )


# ------------------------------------------------------------------ evidence states

def test_the_five_evidence_states_are_the_only_ones():
    assert {s.value for s in EvidenceState} == set(TAXONOMY["evidence_states"]["allowed"])


@pytest.mark.parametrize("state", [s.value for s in EvidenceState])
def test_no_evidence_state_ever_renders_as_safe(state):
    assert render_evidence_state(state)["renders_as_safe"] is False


def test_no_evidence_found_is_a_statement_about_the_search():
    r = render_evidence_state("no_evidence_found")
    assert "NOT a finding of safety" in r["display_text"]
    assert "Absence of evidence is not evidence of absence" in r["display_text"]
    # And it cannot even be recorded without naming what was searched.
    with pytest.raises(ValidationError, match="requires searched_sources"):
        SafetyEvidenceRecord(
            evidence_id="E1", candidate_id="C1", active_moiety_id="M1",
            evidence_state=EvidenceState.NO_EVIDENCE_FOUND,
        )


def test_not_evaluated_is_distinct_from_no_evidence_found():
    """Nobody looked, versus we looked and found nothing. Different claims."""
    not_evaluated = render_evidence_state("not_evaluated")["display_text"]
    no_evidence = render_evidence_state("no_evidence_found")["display_text"]
    assert not_evaluated != no_evidence
    assert "Not searched" in not_evaluated
    assert "were searched" in no_evidence


def test_faers_is_signal_only_and_not_accepted_in_this_pass():
    assert TAXONOMY["faers_policy"]["accepted"] is False
    assert TAXONOMY["faers_policy"]["if_ever_accepted"]["evidence_state"] == "signal_only"
    cannot = TAXONOMY["faers_policy"]["if_ever_accepted"]["cannot_establish"]
    assert {"incidence", "causality", "safety", "contraindication"} <= set(cannot)


# --------------------------------------------------------------- scenarios & lanes

def test_scenarios_and_interaction_types_stay_separate():
    assert {s.value for s in GbmScenario} == {
        "temozolomide", "radiation", "corticosteroid_exposure",
        "antiseizure_therapy", "perioperative_setting",
    }
    assert {i.value for i in InteractionType} == {
        "pk_interaction", "overlapping_toxicity", "marrow_effects", "infection_liability",
        "immune_activation_autoimmunity", "bleeding", "qt_cardiac", "mechanistic_antagonism",
    }

    cells = scenario_matrix("C1", [])
    assert len(cells) == 5 * 8  # every cell is its own lane, never merged
    assert all(c["evidence_state"] == "not_evaluated" for c in cells)
    assert all(c["renders_as_safe"] is False for c in cells)


def test_an_empty_cell_is_not_evaluated_not_no_evidence_found():
    """Nobody looked is not the same as we looked and found nothing."""
    cells = scenario_matrix("C1", [])
    assert {c["evidence_state"] for c in cells} == {"not_evaluated"}


def test_forbidden_fields_are_rejected_anywhere_in_an_artifact():
    forbidden = METHOD.forbidden_fields
    assert "traffic_light" in forbidden and "safety_score" in forbidden

    assert_no_forbidden_fields({"lanes": {"safety": {"rows": []}}}, forbidden)
    with pytest.raises(ForbiddenFieldError, match="traffic_light"):
        assert_no_forbidden_fields({"candidates": [{"traffic_light": "green"}]}, forbidden)
    with pytest.raises(ForbiddenFieldError):
        assert_no_forbidden_fields({"a": {"b": [{"composite_score": 0.9}]}}, forbidden)
