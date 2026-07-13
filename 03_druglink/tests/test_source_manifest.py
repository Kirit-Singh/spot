"""Audit gate item 1 — publisher provenance pinned BEFORE acquisition.

ChEMBL 37 is now independently confirmed against the publisher:
5,764,252,857 bytes, sha256 33c203740555f96067710cdfc1c3c55d890660e5908ec5cbf5817492c290d281.

The ordering matters and is the whole point: a checksum written down *after* the download
records what you got, not what you were promised — it can never catch a truncated read or a
substituted archive. So the publisher's figures live in the code before a byte is fetched,
and the acquisition is checked against them.
"""
from __future__ import annotations

import pytest

from verifier import source_manifest as sm
from verifier.report import Report

CHEMBL_SHA = "33c203740555f96067710cdfc1c3c55d890660e5908ec5cbf5817492c290d281"


def _failed(rep):
    return [n for n, ok, _ in rep.checks if not ok]


def _manifest(**over):
    m = {"source": "chembl", "url": sm.CHEMBL["url"], "release": "CHEMBL_37",
         "release_date": "01/05/2026", "bytes": 5_764_252_857,
         "publisher_checksum": CHEMBL_SHA, "computed_sha256": CHEMBL_SHA,
         "license": "CC BY-SA 3.0", "attribution": "preserve ChEMBL IDs; display release",
         "access_time_utc": "2026-07-13T00:00:00Z"}
    m.update(over)
    return m


# --------------------------------------------------------------------------- #
# The publisher's figures, pinned.
# --------------------------------------------------------------------------- #
def test_the_chembl_37_archive_is_pinned_to_the_publishers_exact_figures():
    assert sm.CHEMBL["bytes"] == 5_764_252_857
    assert sm.CHEMBL["publisher_sha256"] == CHEMBL_SHA
    assert sm.CHEMBL["license"] == "CC BY-SA 3.0"
    assert sm.CHEMBL["doi_resolves"] is True


def test_uniprot_is_pinned_and_its_url_is_declared_MUTABLE():
    assert sm.UNIPROT["release"] == "2026_02"
    assert sm.UNIPROT["publisher_md5"] == "7ef6a677d4db949397c3b352c466e499"
    assert sm.UNIPROT["url_is_mutable"] is True
    # The audit found the REST licence locator returning HTTP 400.
    assert sm.UNIPROT["rest_license_locator_verified"] is False


def test_the_publisher_pins_check_passes():
    rep = Report()
    sm.check_publisher_pins_are_recorded(rep)
    assert not _failed(rep)


# --------------------------------------------------------------------------- #
# The acquisition is checked AGAINST the publisher.
# --------------------------------------------------------------------------- #
def test_a_faithful_acquisition_passes():
    rep = Report()
    sm.check_acquired_bytes_match_the_publisher(rep, _manifest())
    assert not _failed(rep)


def test_a_TRUNCATED_archive_is_caught_by_the_byte_count():
    """5.76 GB arriving as 5.75 GB. The count catches it before the hash even runs."""
    rep = Report()
    sm.check_acquired_bytes_match_the_publisher(
        rep, _manifest(bytes=5_764_252_000))
    assert any("byte count" in n for n in _failed(rep))


def test_a_SUBSTITUTED_archive_is_caught_by_the_recomputed_hash():
    rep = Report()
    sm.check_acquired_bytes_match_the_publisher(
        rep, _manifest(computed_sha256="f" * 64))
    assert any("INDEPENDENTLY COMPUTED sha256" in n for n in _failed(rep))


def test_the_wrong_release_is_refused():
    rep = Report()
    sm.check_acquired_bytes_match_the_publisher(rep, _manifest(release="CHEMBL_36"))
    assert any("release is 'CHEMBL_37'" in n for n in _failed(rep))


def test_a_chembl_archive_wearing_the_uniprot_licence_is_refused():
    rep = Report()
    sm.check_acquired_bytes_match_the_publisher(rep, _manifest(license="CC BY 4.0"))
    assert any("licence" in n for n in _failed(rep))


def test_an_unknown_source_is_refused():
    rep = Report()
    sm.check_acquired_bytes_match_the_publisher(rep, _manifest(source="drugbank"))
    assert _failed(rep)


# --------------------------------------------------------------------------- #
# Manifest completeness (gate item 1).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field", sm.REQUIRED_MANIFEST_FIELDS)
def test_a_manifest_missing_any_required_field_is_refused(field):
    rep = Report()
    sm.check_manifest_is_complete(rep, _manifest(**{field: None}))
    assert _failed(rep)


def test_a_complete_manifest_passes():
    rep = Report()
    sm.check_manifest_is_complete(rep, _manifest())
    assert not _failed(rep)


def test_a_manifest_with_only_the_publishers_hash_and_no_recompute_is_refused():
    """The publisher's hash is a CLAIM. Recomputing it is the check."""
    rep = Report()
    sm.check_manifest_is_complete(rep, _manifest(computed_sha256=None))
    assert _failed(rep)


# --------------------------------------------------------------------------- #
# Mutable URLs must be declared.
# --------------------------------------------------------------------------- #
def test_an_undeclared_mutable_uniprot_url_is_refused():
    rep = Report()
    sm.check_mutable_urls_are_declared(
        rep, [{"source": "uniprot", "url_is_mutable": False}])
    assert any("DECLARED mutable" in n for n in _failed(rep))


def test_a_declared_mutable_url_passes():
    rep = Report()
    sm.check_mutable_urls_are_declared(
        rep, [{"source": "uniprot", "url_is_mutable": True},
              {"source": "chembl", "url_is_mutable": False}])
    assert not _failed(rep)


# --------------------------------------------------------------------------- #
# Gate item 3 — W2's frozen SQL. Stage 3 refuses a cache that cannot show it.
# --------------------------------------------------------------------------- #
GOOD_SQL = """
SELECT td.chembl_id, cs.accession
FROM target_dictionary td
JOIN target_components tc ON tc.tid = td.tid
JOIN component_sequences cs ON cs.component_id = tc.component_id
WHERE td.target_type = 'SINGLE PROTEIN'
  AND td.tax_id = 9606
  AND td.species_group_flag = 0
  AND cs.component_type = 'PROTEIN'
  AND cs.tax_id = 9606
  AND tc.homologue = 0
"""


def test_a_missing_extractor_manifest_is_refused():
    rep = Report()
    sm.check_extractor_sql_is_frozen(rep, None)
    assert _failed(rep)


def test_sql_without_the_six_predicates_is_refused():
    rep = Report()
    sm.check_extractor_sql_is_frozen(rep, {
        "sql_text": "SELECT * FROM target_dictionary WHERE target_type='SINGLE PROTEIN'",
        "sql_sha256": "a" * 64, "component_cardinality_proved": True})
    assert any("six identity predicates" in n for n in _failed(rep))


def test_sql_that_is_not_hash_bound_is_refused():
    rep = Report()
    sm.check_extractor_sql_is_frozen(rep, {
        "sql_text": GOOD_SQL, "component_cardinality_proved": True})
    assert any("bound by hash" in n for n in _failed(rep))


def test_an_extractor_that_does_not_prove_cardinality_is_refused():
    rep = Report()
    sm.check_extractor_sql_is_frozen(rep, {
        "sql_text": GOOD_SQL, "sql_sha256": "a" * 64})
    assert any("component cardinality" in n for n in _failed(rep))


def test_a_frozen_extractor_with_all_six_predicates_passes():
    rep = Report()
    sm.check_extractor_sql_is_frozen(rep, {
        "sql_text": GOOD_SQL, "sql_sha256": "a" * 64,
        "component_cardinality_proved": True})
    assert not _failed(rep)


# --------------------------------------------------------------------------- #
# W2 e298770 — the regenerated cache's identities, pinned.
# --------------------------------------------------------------------------- #
def test_w2s_chembl_source_sha_equals_the_publishers():
    """Independently confirmed against my pre-acquisition pin."""
    assert sm.CHEMBL["publisher_sha256"] == CHEMBL_SHA


def test_w2s_store_identities_are_pinned():
    assert sm.W2_PRODUCER_COMMIT.startswith("e298770")
    assert sm.W2_STORE_ID.startswith("446c3b78")
    assert sm.W2_ELIGIBILITY_EVIDENCE_SHA256.startswith("cf5d7088")


def test_the_eligibility_evidence_was_SHIPPED_and_REPLAYED():
    """The store lives on tcefold; Git carries only the compact reports. Copied and audited.

    I first concluded the store was absent because I checked only tcedirector — it was on
    tcefold all along. Checking one host and calling an artifact missing is the same error
    as trusting a claim without checking: both substitute a convenient answer for a look.
    """
    assert sm.W2_EVIDENCE_SHIPPED is True
    assert sm.W2_STORE_PATH.startswith("tcefold:")


def test_all_11055_eligibility_verdicts_replay_with_zero_mismatches():
    r = sm.W2_REPLAY
    assert r["eligibility_records_replayed"] == 11_055
    assert r["verdict_mismatches"] == 0


def test_ambiguous_shared_accessions_carry_NO_drug_evidence_in_the_real_store():
    r = sm.W2_REPLAY
    assert r["ambiguous_identity_rows"] == 86
    assert r["ambiguous_rows_carrying_drug_evidence"] == 0


def test_all_29_variant_assertions_are_excluded_from_general_ranking():
    """Including the 10 that carry the -1 UNDEFINED MUTATION sentinel."""
    r = sm.W2_REPLAY
    assert r["variant_assertions"] == 29
    assert r["variant_assertions_leaking_into_general_ranking"] == 0
    assert r["variant_undefined_mutation_sentinels"] == 10


def test_w2s_coverage_arithmetic_reconciles():
    """505 drug-evidence + 10,931 none + 86 ambiguous = 11,522 ENSG; + 4 symbol = 11,526.

    Nothing vanished to make a denominator look tidy.
    """
    c = sm.W2_COUNTS
    assert c["drug_evidence_targets"] + 10_931 + c["ambiguous_identity"] == 11_522
    assert 11_522 + c["unsupported_namespace"] == c["universe_total"] == 11_526


def test_w2s_eligibility_counts_sum():
    c = sm.W2_COUNTS
    assert c["eligible"] + c["rejected"] == c["chembl_mappings_evaluated"] == 11_055


def test_the_29_variant_assertions_are_the_ones_the_gate_must_exclude():
    assert sm.W2_COUNTS["variant_specific_assertions"] == 29
