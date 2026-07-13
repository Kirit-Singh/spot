"""Four pre-publication repairs, and two gaps they exposed in MY OWN verifier.

1. `n_total_drug_assertions = 2,227` is not a total — it is the general/rankable subtotal.
2. Admission must LOAD AND HASH the 3.5 MB evidence file on disk; a manifest pin proves
   nothing about a file nobody opened.
3. The UniProt `current_release` locator is mutable and must be release-specific.
4. A committed HANDOFF.md leaked `/home/tcelab/...` — and my sweep reported it CLEAN,
   because (a) it only scanned `.json` and (b) `LOCAL_PATH_RE` allowlisted the characters
   that may precede a path, so a markdown code span `` `/home/tcelab/...` `` slipped past.
   An allowlist of delimiters is a guess about how someone will write it.
"""
from __future__ import annotations

import json

import pytest

from verifier import cache_evidence as ce
from verifier import cache_sweep, policy
from verifier import eligibility_evidence as ee
from verifier import source_manifest as sm
from verifier.report import Report


def _failed(rep):
    return [n for n, ok, _ in rep.checks if not ok]


# --------------------------------------------------------------------------- #
# 1. Exact denominators.
# --------------------------------------------------------------------------- #
REAL = {"assertion_counts": {
    "n_total_stored_occurrences": 2262, "n_unique_source_mechanism_rows": 2258,
    "n_general_drug_assertions": 2227, "n_variant_specific_assertions": 29,
    "n_ambiguous_assertion_occurrences": 6, "n_ambiguous_unique_source_rows": 2}}


def test_the_real_denominators_reconcile():
    """2,227 general + 29 variant + 6 ambiguous = 2,262 occurrences."""
    rep = Report()
    ce.check_denominators_are_exact(rep, dict(REAL))
    assert not _failed(rep)
    assert 2227 + 29 + 6 == 2262


def test_a_total_that_is_really_a_subtotal_is_refused():
    """`n_total_drug_assertions: 2227` while 2,262 occurrences exist."""
    import copy
    m = copy.deepcopy(REAL)
    m["n_total_drug_assertions"] = 2227
    rep = Report()
    ce.check_denominators_are_exact(rep, m)
    assert any("only the rankable subset" in n for n in _failed(rep))


@pytest.mark.parametrize("field", ce.REQUIRED_DENOMINATORS)
def test_a_missing_denominator_is_refused(field):
    import copy
    m = copy.deepcopy(REAL)
    del m["assertion_counts"][field]
    rep = Report()
    ce.check_denominators_are_exact(rep, m)
    assert _failed(rep)


def test_denominators_that_do_not_reconcile_are_refused():
    import copy
    m = copy.deepcopy(REAL)
    m["assertion_counts"]["n_ambiguous_assertion_occurrences"] = 0
    rep = Report()
    ce.check_denominators_are_exact(rep, m)
    assert any("RECONCILE" in n for n in _failed(rep))


# --------------------------------------------------------------------------- #
# 2. Admission hashes the bytes ON DISK.
# --------------------------------------------------------------------------- #
def _evidence_file(tmp_path, records, name="target_eligibility_evidence.json"):
    p = tmp_path / name
    p.write_text(json.dumps({"schema": ee.EVIDENCE_SCHEMA, "records": records}))
    return str(p)


def _hash(doc):
    return ee.canonical_content_sha256(doc.get("records") or [])


def test_an_ALTERED_on_disk_file_is_caught_even_though_the_manifest_pin_is_correct(tmp_path):
    """The producer's verifier can hold a correct pin while the file beside it changed."""
    recs = [{"target_chembl_id": "C1", "tax_id": 9606}]
    path = _evidence_file(tmp_path, recs)
    pin = _hash({"records": recs})

    # tamper with the file on disk; the manifest still carries the ORIGINAL pin
    with open(path, "w") as fh:
        json.dump({"schema": ee.EVIDENCE_SCHEMA,
                   "records": [{"target_chembl_id": "C1", "tax_id": 10090}]}, fh)

    rep = Report()
    ee.check_on_disk_evidence_matches_the_pin(
        rep, evidence_path=path,
        manifest={"extraction": {"eligibility_evidence_sha256": pin}},
        content_hash_fn=_hash)
    assert any("ON DISK re-hashes" in n for n in _failed(rep))


def test_an_intact_on_disk_file_passes(tmp_path):
    recs = [{"target_chembl_id": "C1", "tax_id": 9606}]
    path = _evidence_file(tmp_path, recs)
    rep = Report()
    got = ee.check_on_disk_evidence_matches_the_pin(
        rep, evidence_path=path,
        manifest={"extraction": {
            "eligibility_evidence_sha256": _hash({"records": recs})}},
        content_hash_fn=_hash)
    assert not _failed(rep) and got is not None


def test_a_MISSING_evidence_file_is_refused(tmp_path):
    rep = Report()
    ee.check_on_disk_evidence_matches_the_pin(
        rep, evidence_path=str(tmp_path / "nope.json"),
        manifest={"extraction": {"eligibility_evidence_sha256": "a" * 64}},
        content_hash_fn=_hash)
    assert any("ON DISK" in n for n in _failed(rep))


# --------------------------------------------------------------------------- #
# 3. The mutable UniProt locator.
# --------------------------------------------------------------------------- #
def test_the_uniprot_current_release_locator_is_declared_MUTABLE():
    assert sm.UNIPROT["url_is_mutable"] is True
    assert "mutable" in sm.UNIPROT["url_mutability_note"]


def test_an_undeclared_mutable_locator_is_refused():
    rep = Report()
    sm.check_mutable_urls_are_declared(
        rep, [{"source": "uniprot", "url_is_mutable": False}])
    assert _failed(rep)


# --------------------------------------------------------------------------- #
# 4. The path leak my own sweep missed. TWICE.
# --------------------------------------------------------------------------- #
def test_a_BACKTICKED_path_is_caught():
    """The real HANDOFF.md line. My allowlist of preceding characters had no backtick, so
    a markdown code span sailed through and my sweep reported the file clean."""
    line = ("## Data artifacts (out-of-Git; tcefold data cache "
            "`/home/tcelab/.cache/spot-stage3-universe/`)")
    assert policy.LOCAL_PATH_RE.search(line), "a backticked path is still a path"


@pytest.mark.parametrize("wrapper", ["`{}`", "[{}]", "({})", "<{}>", '"{}"', "{}", ",{}"])
def test_a_path_is_caught_however_it_is_delimited(wrapper):
    assert policy.LOCAL_PATH_RE.search(wrapper.format("/home/tcelab/x"))


def test_a_path_INSIDE_a_longer_path_is_not_a_false_positive():
    assert not policy.LOCAL_PATH_RE.search("relative/home/dir/file")


def test_the_sweep_scans_MARKDOWN_not_just_json(tmp_path):
    """A JSON-only scan misses a committed HANDOFF.md. The leak does not care about the
    extension it was written under, so neither does the scan."""
    (tmp_path / "HANDOFF.md").write_text(
        "## Data artifacts (tcefold cache `/home/tcelab/.cache/spot-stage3-universe/`)")
    (tmp_path / "ok.json").write_text('{"clean": true}')

    rep = Report()
    cache_sweep.check_no_machine_paths_in_ANY_public_text(rep, str(tmp_path))
    failed = _failed(rep)
    assert failed
    detail = next(d for n, ok, d in rep.checks if not ok)
    assert "HANDOFF.md:1" in detail


def test_markdown_is_in_the_public_suffix_set():
    assert ".md" in cache_sweep.PUBLIC_SUFFIXES
    assert ".json" in cache_sweep.PUBLIC_SUFFIXES


def test_a_clean_public_tree_passes(tmp_path):
    (tmp_path / "HANDOFF.md").write_text("## Data artifacts (out-of-Git data cache)")
    rep = Report()
    cache_sweep.check_no_machine_paths_in_ANY_public_text(rep, str(tmp_path))
    assert not _failed(rep)
