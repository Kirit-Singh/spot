"""Stage-3's ChEMBL and UniProt records are REUSED, not re-acquired.

Stage 3 already put those requests on the wire, hashed the responses, and released them inside
a bundle whose table hashes Stage 4 re-derives at admission. Re-querying them here would
produce a second, unreconciled copy of the same evidence — a different release, a different
day, a different hash — and nothing would say which one a number came from. So:

  * ChEMBL/UniProt are `reuse_only` in the ledger. Asking to fetch one raises.
  * The carried record is Stage 3's, verbatim: its hash, its byte count, its release, its
    licence. Stage 4 re-derives nothing and re-interprets nothing.
  * Stage 3 records the canonical query as a HASH. It is carried as a hash. The query text is
    not reconstructed from it, because it cannot be.
  * A Stage-3 record that claims `acquired_public` without bytes or without a release is
    refused, not defaulted.

The bundle used here is the pinned REAL Stage-3 annotation bundle (ChEMBL_37 / UniProt 2026_02).
"""

from __future__ import annotations

import os

import pandas as pd
import pytest

from _stage3_forge import PINNED_BUNDLE, copy_bundle
from analysis.acquisition import AcquisitionRecord
from analysis.firewall import Rejection
from analysis.public_sources import assert_fetch_permitted, ledger
from analysis.stage3_annotation import adapt_annotation_bundle
from analysis.stage3_reuse import (
    REUSE_TRANSFORM,
    reuse_stage3_sources,
    stage3_missing_lanes,
)

ACCESS_DATE = "2026-07-12"


def _rows() -> list[dict]:
    df = pd.read_parquet(os.path.join(PINNED_BUNDLE, "source_records.parquet"))
    return df.where(pd.notna(df), None).to_dict("records")


def _row(source: str, status: str = "acquired_public") -> dict:
    return next(r for r in _rows()
                if r["source"] == source and r["acquisition_status"] == status)


# ------------------------------------------------------------------ never re-query these


@pytest.mark.parametrize("source_key", ["chembl", "uniprot"])
def test_stage4_refuses_to_re_query_a_source_stage3_already_acquired(source_key):
    with pytest.raises(Rejection) as exc:
        assert_fetch_permitted(source_key)
    assert exc.value.code == "stage3_source_reuse_required"


def test_the_ledger_marks_chembl_and_uniprot_reuse_only():
    for key in ("chembl", "uniprot"):
        assert ledger()["sources"][key]["fetch"] == "reuse_only"


# --------------------------------------------------------------------- carried verbatim


def test_a_chembl_record_is_carried_with_stage3s_own_hash_bytes_and_release():
    row = _row("chembl")
    rec = reuse_stage3_sources([row], access_date=ACCESS_DATE)[0]

    assert rec.origin == "reused_from_stage3"
    assert rec.evidence_state == "observed"
    assert rec.stage3_source_record_id == row["source_record_id"]
    assert rec.raw_sha256 == row["raw_sha256"]           # Stage-3's bytes, Stage-3's hash
    assert rec.raw_bytes == int(row["raw_bytes"])
    assert rec.release_or_last_updated == row["source_release"] == "ChEMBL_37"
    assert rec.license == "CC BY-SA 3.0"
    assert rec.extraction_transform == REUSE_TRANSFORM
    assert rec.access_date == ACCESS_DATE


def test_a_uniprot_record_is_carried_the_same_way():
    row = _row("uniprot")
    rec = reuse_stage3_sources([row], access_date=ACCESS_DATE)[0]
    assert rec.release_or_last_updated == "2026_02"
    assert rec.license == "CC BY 4.0"
    assert rec.raw_sha256 == row["raw_sha256"]


def test_the_terms_url_comes_from_the_ledger_not_from_stage3s_bare_licence_string():
    rec = reuse_stage3_sources([_row("uniprot")], access_date=ACCESS_DATE)[0]
    assert rec.license_or_terms_url == "https://www.uniprot.org/help/license"


def test_stage3s_canonical_query_is_carried_as_a_hash_and_is_never_reconstructed_as_text():
    """Stage 3 stores `query_canonical` as a SHA-256, not as the query. Inventing the text
    from it is impossible, so the record says so instead of guessing."""
    row = _row("chembl")
    rec = reuse_stage3_sources([row], access_date=ACCESS_DATE)[0]
    assert rec.canonical_query_sha256 == row["query_canonical"]
    assert rec.canonical_query is None


def test_a_not_acquired_record_carries_no_bytes_and_is_not_an_observation():
    row = _row("pubchem", status="not_acquired")
    rec = reuse_stage3_sources([row], access_date=ACCESS_DATE)[0]
    assert rec.evidence_state == "not_evaluated"
    assert rec.raw_sha256 is None and rec.raw_bytes is None
    assert "not_acquired" in (rec.note or "") or "never" in (rec.note or "")


def test_the_lanes_stage3_never_acquired_are_listed_as_stated_absences():
    missing = stage3_missing_lanes(_rows())
    lanes = {m.source_key for m in missing}
    assert {"pubchem", "rxnorm"} <= lanes          # Stage 3 planned them, never fetched them
    assert all(m.evidence_state == "not_evaluated" for m in missing)


# ---------------------------------------------------------------------------- refusals


def test_an_acquired_public_stage3_record_without_bytes_is_refused_not_defaulted():
    row = dict(_row("chembl"), raw_sha256=None, raw_bytes=None)
    with pytest.raises(Rejection) as exc:
        reuse_stage3_sources([row], access_date=ACCESS_DATE)
    assert exc.value.code == "stage3_source_record_incomplete"
    assert "raw_sha256" in exc.value.detail


def test_an_acquired_public_stage3_record_without_a_release_is_refused():
    """FAIL-CLOSED (release): a curated database record with no release cannot be re-found."""
    row = dict(_row("chembl"), source_release=None)
    with pytest.raises(Rejection) as exc:
        reuse_stage3_sources([row], access_date=ACCESS_DATE)
    assert exc.value.code == "stage3_source_record_incomplete"
    assert "source_release" in exc.value.detail


def test_an_unknown_acquisition_status_is_refused_rather_than_guessed():
    row = dict(_row("chembl"), acquisition_status="probably_fine")
    with pytest.raises(Rejection) as exc:
        reuse_stage3_sources([row], access_date=ACCESS_DATE)
    assert exc.value.code == "stage3_unknown_acquisition_status"


def test_a_synthetic_stage3_record_stays_synthetic_and_is_never_upgraded():
    row = dict(_row("chembl"), acquisition_status="synthetic_fixture")
    rec = reuse_stage3_sources([row], access_date=ACCESS_DATE)[0]
    assert rec.origin == "synthetic_fixture"
    assert rec.evidence_state == "not_applicable"


# ------------------------------------------------------------ end to end, the real bundle


def test_the_real_admitted_bundle_yields_its_chembl_and_uniprot_records_unchanged():
    admission = adapt_annotation_bundle(PINNED_BUNDLE)
    rows = _rows()
    records = reuse_stage3_sources(rows, access_date=ACCESS_DATE)

    by_id = {r.acquisition_record_id: r for r in records}
    assert len(by_id) == len(rows)                      # one carried record per Stage-3 row

    observed = [r for r in records if r.evidence_state == "observed"]
    assert {r.source_key for r in observed} == {"chembl", "uniprot"}

    # every carried hash is byte-identical to the admitted bundle's own
    admitted = {s.source_record_id: s for s in admission.source_records.values()}
    for rec in observed:
        assert rec.raw_sha256 == admitted[rec.stage3_source_record_id].raw_sha256


def test_a_mutated_source_record_never_reaches_the_reuse_translation(tmp_path):
    """FAIL-CLOSED (hash): the admission gate re-derives the source_records table hash from the
    rows, so a tampered hash is refused BEFORE anything is carried into Stage 4."""
    bundle = copy_bundle(tmp_path)
    path = os.path.join(bundle, "source_records.parquet")
    df = pd.read_parquet(path)
    df.loc[df["source"] == "chembl", "raw_sha256"] = "9" * 64
    df.to_parquet(path, index=False)

    with pytest.raises(Rejection) as exc:
        adapt_annotation_bundle(bundle)
    assert "hash" in exc.value.code or "hash" in exc.value.detail.lower()


def test_a_carried_record_translates_into_the_source_contract_as_acquired_public():
    from analysis.acquisition import to_source_record

    rec = reuse_stage3_sources([_row("chembl")], access_date=ACCESS_DATE)[0]
    src = to_source_record(rec)
    assert src.acquisition_status.value == "acquired_public"
    assert src.release_version == "ChEMBL_37"
    assert isinstance(rec, AcquisitionRecord)
