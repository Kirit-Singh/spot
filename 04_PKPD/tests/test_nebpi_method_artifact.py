"""The NEBPI method artifact IS the paper, and NEBPI is criteria — not a score.

Source: Grossman et al., "Evaluating 'brain permeability': A critical issue for the development
of therapeutic agents for primary and metastatic brain tumors", Neuro-Oncology 2026,
doi:10.1093/neuonc/noag051, PMC13338342, CC BY 4.0.

Three things are pinned here.

1. **The transcription is not hand-typed.** `analysis/nebpi_source.py` parses Tables 1 and 2 out
   of the cached bytes; `verifier/nebpi_source.py` — a different parser, importing none of it —
   re-reads them and compares the method file cell for cell.

2. **The pin is re-verifiable.** The PMC BioC endpoint stamps the RETRIEVAL DATE into the
   envelope, so the raw bytes of an unchanged paper differ by one byte every day. A registry
   pinning only `raw_sha256` reports MISMATCH on an untouched document daily, which trains a
   reviewer to ignore the one signal meant to stop a tamper. `content_sha256` is stable and IS
   the scientific identity.

3. **NEBPI stays criterion-level.** A criterion nobody evaluated reads `not_evaluated` and can
   never carry a class; a criterion the source gives no Part-II branch can never carry a class
   however strongly it was observed — which is the whole reason CNS-MPO cannot stand in for
   brain exposure.
"""

from __future__ import annotations

import json
import os
import shutil

import pyarrow.parquet as pq
import pytest

from analysis.method_config import METHOD_DIR, load_method_bundle
from analysis.nebpi_source import (
    content_sha256,
    part_i_rows,
    part_ii_rows,
    raw_sha256,
)
from analysis.source_verify import verify_sources
from provenance_helpers import both_verifiers, emit_run, failed
from verifier.criteria import check_criteria, rebuild_criteria
from verifier.nebpi_source import NebpiRereadError, load_source, reread, verify

import fixtures as fx

# The primary-source cache lives OUTSIDE the tree (public-data-only rule): raw article bytes
# are never committed. Point SPOT_SOURCE_CACHE at it; without it these tests skip rather than
# bind one machine's path into the suite.
CACHE = os.environ.get("SPOT_SOURCE_CACHE", "")
METHOD_FILE = os.path.join(METHOD_DIR, "nebpi_grossman2026_v1.json")

# The bytes this method was transcribed from, recorded so a silent re-pin is impossible.
PINNED_CONTENT_SHA = "90ffdf2a07f742f58128bdafeeebedb3d3779640884142783152113fc6473937"
PINNED_RAW_SHA = "8bb0324def170ae1f9aa26e906c8b7327690b8c6eebcd3d3e29f5e5a88b23f47"

SOURCE_AVAILABLE = bool(CACHE) and os.path.exists(os.path.join(CACHE, "PMC13338342.bioc.xml"))
needs_source = pytest.mark.skipif(
    not SOURCE_AVAILABLE,
    reason="the NEBPI primary source is not cached: set SPOT_SOURCE_CACHE to a directory "
           "holding PMC13338342.bioc.xml, re-fetched from the retrieval_url in "
           "method/sources.json")


@pytest.fixture(scope="module")
def raw() -> bytes:
    return load_source(CACHE)


@pytest.fixture(scope="module")
def method() -> dict:
    with open(METHOD_FILE, encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------- 1. the independent re-read

@needs_source
def test_every_encoded_criterion_matches_the_source_cell_for_cell():
    """The whole point. A hand-typed table is a claim about a paper; this checks the claim."""
    bad = verify(METHOD_FILE, CACHE)
    assert bad == [], "the method file does not say what the paper says:\n  " + "\n  ".join(bad)


@needs_source
def test_table_1_has_exactly_eight_criteria_and_the_method_knows_it(raw, method):
    rows = part_i_rows(raw)
    assert len(rows) == 8
    assert method["part_i_criteria_count_in_source"] == 8

    in_table = [c for c in method["part_i_criteria"] if c["in_part_i_table"]]
    assert len(in_table) == 8
    assert [c["source_verbatim"] for c in in_table] == [r["criterion_verbatim"] for r in rows]
    assert [c["importance"] for c in in_table] == [r["importance_verbatim"] for r in rows]


@needs_source
def test_the_ninth_criterion_is_declared_as_not_being_in_table_1(method):
    """`radiographic_response_in_neb` is a Part-II branch that Table 1 does not list.

    It is modelled as its own criterion with importance=null rather than folded into
    `pd_in_neb` (a different measurement) or `response_in_enhancing_lesions` (ENHANCING, not
    non-enhancing — a different criterion entirely).
    """
    ninth = [c for c in method["part_i_criteria"] if not c["in_part_i_table"]]
    assert len(ninth) == 1
    c = ninth[0]
    assert c["criterion_id"] == "radiographic_response_in_neb"
    assert c["importance"] is None
    assert c["source_verbatim"] is None
    assert "one of the eight rows of Table 1" in c["not_in_part_i_table"]
    assert c["can_satisfy_part_ii_branch"] is True


@needs_source
def test_a_tampered_criterion_letter_is_caught_by_the_re_read(raw, method, tmp_path):
    """The re-read is not decorative: change one importance letter and it fails."""
    tampered = raw.replace(b"Physical characteristics of drug\tA",
                           b"Physical characteristics of drug\tB", 1)
    assert tampered != raw
    bad = reread(method, tampered)
    assert any("physical_characteristics" in b and "importance" in b for b in bad), bad


@needs_source
def test_a_tampered_class_definition_is_caught_by_the_re_read(raw, method):
    """`No relevant PD in NEB` -> `Relevant PD in NEB` inverts the science. It must fail."""
    tampered = raw.replace(b"andNo relevant PD in NEB", b"andRelevant PD in NEB")
    assert tampered != raw
    bad = reread(method, tampered)
    assert any("source_quote does not match Table 2" in b for b in bad), bad


@needs_source
def test_the_re_read_refuses_a_document_that_is_not_the_paper():
    with pytest.raises(NebpiRereadError):
        reread({"source_binding": {}}, b"<collection><document></document></collection>")


# ------------------------------------------- 2. the pin is re-verifiable

@needs_source
def test_the_raw_hash_is_a_snapshot_and_the_content_hash_is_the_identity(raw):
    assert raw_sha256(raw) == PINNED_RAW_SHA
    assert content_sha256(raw) == PINNED_CONTENT_SHA


@needs_source
def test_a_re_fetched_document_verifies_even_though_its_raw_bytes_differ(raw, tmp_path):
    """The exact defect: the API stamps its retrieval date into the envelope.

    Simulated here rather than hitting the network, byte for byte: the ONLY difference between
    a re-fetch and the pinned file is the <date> element. Verified against the live endpoint on
    2026-07-12 — live raw_sha256 0862ac39..., identical content_sha256, identical table cells.
    """
    refetched = raw.replace(b"<date>20260711</date>", b"<date>20260712</date>", 1)
    assert refetched != raw, "the pinned file must carry the retrieval-date envelope"
    assert raw_sha256(refetched) != PINNED_RAW_SHA      # the raw hash moves...
    assert content_sha256(refetched) == PINNED_CONTENT_SHA   # ...the article does not
    assert part_i_rows(refetched) == part_i_rows(raw)
    assert part_ii_rows(refetched) == part_ii_rows(raw)

    shutil.copy(os.path.join(CACHE, "PMC13338342.bioc.xml"),
                tmp_path / "PMC13338342.bioc.xml")
    (tmp_path / "PMC13338342.bioc.xml").write_bytes(refetched)
    report = verify_sources(cache_root=str(tmp_path))
    row = next(r for r in report["sources"] if r["source_id"] == "grossman2026_nebpi")
    assert row["status"] == "verified", row
    assert "retrieval-date envelope" in row["note"]


@needs_source
def test_a_real_edit_to_the_article_still_fails_source_verification(raw, tmp_path):
    tampered = raw.replace(b"Little to no drug in NEB", b"Plenty of drug in NEB", 1)
    assert tampered != raw
    (tmp_path / "PMC13338342.bioc.xml").write_bytes(tampered)
    report = verify_sources(cache_root=str(tmp_path))
    row = next(r for r in report["sources"] if r["source_id"] == "grossman2026_nebpi")
    assert row["status"] == "MISMATCH"
    assert report["status"] == "fail"


def test_the_registry_no_longer_claims_the_raw_bytes_are_stable():
    with open(os.path.join(METHOD_DIR, "sources.json"), encoding="utf-8") as fh:
        reg = json.load(fh)
    s = next(x for x in reg["sources"] if x["source_id"] == "grossman2026_nebpi")
    assert s["content_sha256"] == PINNED_CONTENT_SHA
    assert "raw_bytes_volatile_daily" in s["volatility"]
    assert "retrieval" in s["content_hash_rule"].lower()


# --------------------------------------- 3. NEBPI is criterion-level, not a score

def test_the_release_carries_a_criterion_level_table(tmp_path):
    out_dir, _m, _r = emit_run(fx.stage4_inputs(), tmp_path)
    rows = pq.read_table(os.path.join(out_dir, "nebpi_criteria.parquet")).to_pylist()
    assert rows, "NEBPI must be reported criterion by criterion, not as a class alone"

    method = load_method_bundle()
    n_criteria = len(method.nebpi["part_i_criteria"])
    contexts = {(r["candidate_id"], r["context_id"]) for r in rows}
    assert len(rows) == n_criteria * len(contexts), (
        "every criterion appears for every context — a criterion nobody evaluated is still a "
        "row, not a silence")


def test_a_criterion_with_no_evidence_reads_not_evaluated_and_carries_nothing(tmp_path):
    """Absent evidence is never favourable evidence."""
    out_dir, _m, _r = emit_run(fx.stage4_inputs(), tmp_path)
    rows = pq.read_table(os.path.join(out_dir, "nebpi_criteria.parquet")).to_pylist()

    unevaluated = [r for r in rows if r["n_observations"] == 0]
    assert unevaluated, "the fixture must exercise at least one unevaluated criterion"
    for r in unevaluated:
        assert r["status"] in ("not_evaluated", "pk_not_evaluated"), r
        assert r["carried_the_assigned_class"] is False
        assert r["observation_ids"] == []


def test_cns_mpo_alone_never_satisfies_an_nebpi_branch(tmp_path):
    """`physical_characteristics` is graded A in Table 1 and appears in NO Table-2 definition.

    So a compound can have every physicochemical descriptor the CNS-MPO score wants, be
    `observed_present` on this criterion, and still carry no permeability class. That is the
    whole reason a design-space score is not brain exposure.
    """
    out_dir, _m, _r = emit_run(fx.stage4_inputs(), tmp_path)
    rows = pq.read_table(os.path.join(out_dir, "nebpi_criteria.parquet")).to_pylist()

    physchem = [r for r in rows if r["criterion_id"] == "physical_characteristics"]
    assert physchem
    for r in physchem:
        assert r["can_satisfy_part_ii_branch"] is False
        assert r["carried_the_assigned_class"] is False
        assert r["evidence_lane_consumed"] == "property_evidence"

    observed = [r for r in physchem if r["status"] == "observed_present"]
    assert observed, "the fixture must have at least one OBSERVED physical-characteristics row"
    for r in observed:
        assert r["carried_the_assigned_class"] is False, (
            "an observed physicochemical criterion carried a permeability class — CNS-MPO has "
            "become brain exposure, which is the exact failure this method exists to prevent")


def test_csf_can_never_stand_in_for_non_enhancing_brain(tmp_path):
    """CSF is graded C and has no Part-II branch. The blood-CSF barrier is not the BBB."""
    out_dir, _m, _r = emit_run(fx.stage4_inputs(), tmp_path)
    rows = pq.read_table(os.path.join(out_dir, "nebpi_criteria.parquet")).to_pylist()
    for r in [x for x in rows if x["criterion_id"] == "csf_drug_levels"]:
        assert r["importance"] == "C"
        assert r["can_satisfy_part_ii_branch"] is False
        assert r["carried_the_assigned_class"] is False


def test_only_the_three_branch_criteria_can_carry_a_class(tmp_path):
    out_dir, _m, _r = emit_run(fx.stage4_inputs(), tmp_path)
    rows = pq.read_table(os.path.join(out_dir, "nebpi_criteria.parquet")).to_pylist()
    can = {r["criterion_id"] for r in rows if r["can_satisfy_part_ii_branch"]}
    assert can == {"pk_in_neb", "pd_in_neb", "radiographic_response_in_neb"}
    for r in rows:
        if r["carried_the_assigned_class"]:
            assert r["criterion_id"] in can


def test_the_independent_verifier_rebuilds_the_criterion_table(tmp_path):
    """generator != verifier: rebuilt from the observations + the method, not read back."""
    inputs = fx.stage4_inputs()
    out_dir, _m, _r = emit_run(inputs, tmp_path)
    emit_time, standalone = both_verifiers(out_dir, inputs)
    assert standalone["status"] == "pass", failed(standalone)
    assert emit_time["status"] == "pass", failed(emit_time)
    assert any(c["check_id"] == "nebpi_criteria_reconstructed"
               for c in standalone["checks"])


def test_a_tampered_criterion_row_is_caught_by_the_verifier(tmp_path):
    """Flip an unevaluated criterion to 'carried the class' and the rebuild disagrees."""
    from verifier.reconstruct import load_method, load_tables

    inputs = fx.stage4_inputs()
    out_dir, _m, _r = emit_run(inputs, tmp_path)
    tables = load_tables(out_dir)
    method = load_method(os.path.join(os.path.dirname(METHOD_DIR), "method"))

    assert check_criteria(tables, method) == []

    victim = next(r for r in tables["nebpi_criteria"]
                  if r["criterion_id"] == "physical_characteristics")
    victim["carried_the_assigned_class"] = True
    problems = check_criteria(tables, method)
    assert problems
    assert any("carries no Part-II branch" in p for p in problems), problems


def test_the_rebuild_covers_every_criterion_in_every_context(tmp_path):
    from verifier.reconstruct import load_method, load_tables

    out_dir, _m, _r = emit_run(fx.stage4_inputs(), tmp_path)
    tables = load_tables(out_dir)
    method = load_method(os.path.join(os.path.dirname(METHOD_DIR), "method"))
    want = rebuild_criteria(tables, method)
    assert len(want) == len(tables["nebpi_criteria"])
