"""Stage-3's source records, carried into Stage 4 verbatim.

Stage 3 acquired its ChEMBL and UniProt responses, hashed them, and released them inside a
bundle whose table hashes Stage 4 re-derives at admission (`stage3_admission.admit`, both
gates). Those records are therefore already public evidence with bytes behind them.

Stage 4 does two things with them, and nothing else:

  * carries them VERBATIM — hash, byte count, release, licence, endpoint. It does not re-query
    them (the ledger marks both sources `reuse_only`, and `assert_fetch_permitted` raises), and
    it does not re-derive or re-interpret any field. A second copy acquired on a different day
    from a different release would be a second, unreconciled provenance for the same number.
  * refuses what it cannot account for — an `acquired_public` row with no bytes or no release
    is incomplete, not defaultable; an unrecognised acquisition status is a refusal, not a
    guess.

Stage 3 stores the canonical query as a SHA-256, not as text. It is carried as a SHA-256. The
query string is not reconstructed from a hash, and no field pretends otherwise.

What Stage 3 planned but never acquired (its `not_acquired` PubChem/RxNorm/LINCS rows) becomes
a STATED ABSENCE — `not_evaluated` — which is exactly the lane the Stage-4 acquisition adapters
then fill from public sources.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from .acquisition import (
    AcquisitionRecord,
    MissingEvidence,
    SourceType,
    as_source_type,
    code_sha256,
    new_record_id,
)
from .firewall import Rejection
from .public_sources import ledger
from .stage3_contract_v2 import ACQUISITION_STATUSES

REUSE_TRANSFORM = "stage3_reuse.carry_verbatim:v1"

# What an `acquired_public` Stage-3 record must show before Stage 4 will treat it as bytes.
REQUIRED_WHEN_ACQUIRED = ("raw_sha256", "raw_bytes", "source_release")

# Stage-3 sources that map onto a lane Stage 4 would otherwise have to acquire itself.
LANE_OF_SOURCE = {
    "chembl": "mechanism_and_potency",
    "uniprot": "target_identity",
    "pubchem": "identity_and_descriptors",
    "rxnorm": "identity_crosswalk",
    "lincs": "transcriptional_support",
    "open_targets": "mechanism_and_potency",
    "gbm_atlas": "disease_context",
}


def _clean(value: Any) -> Any:
    """Parquet gives NaN for an absent number and NaN is not 'no value' — it is a float."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _int(value: Any) -> Optional[int]:
    v = _clean(value)
    return int(v) if v is not None else None


def _str(value: Any) -> Optional[str]:
    v = _clean(value)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _source_type(source_key: str) -> SourceType:
    entry = ledger()["sources"].get(source_key)
    return as_source_type(str(entry["source_type"])) if entry else "public_database"


def _terms(source_key: str, stage3_license: Optional[str]) -> tuple[Optional[str], Optional[str], str]:
    """(licence, terms URL, licence status).

    The LICENCE is Stage 3's own declaration, carried verbatim. The TERMS URL comes from the
    Stage-4 ledger when Stage 4 has recorded terms for that source — and is left empty, with a
    status that says so, when it has not. A terms URL is never invented for a source Stage 4
    has not reviewed.
    """
    entry = ledger()["sources"].get(source_key)
    if entry is None:
        return (stage3_license, None,
                "carried_from_stage3_terms_not_reviewed_by_stage4")
    return (stage3_license or str(entry["license"]),
            str(entry["license_or_terms_url"]),
            str(entry["license_status"]))


def reuse_stage3_source(row: dict[str, Any], *, access_date: str) -> AcquisitionRecord:
    """One Stage-3 source record -> one Stage-4 acquisition record. Nothing re-derived."""
    source_key = str(row.get("source") or "unknown")
    status = _str(row.get("acquisition_status"))
    stage3_id = str(row["source_record_id"])

    if status not in ACQUISITION_STATUSES:
        raise Rejection(
            "stage3_unknown_acquisition_status",
            f"Stage-3 source record {stage3_id!r} declares acquisition_status={status!r}, which "
            f"Stage 4 does not recognise. Known: {list(ACQUISITION_STATUSES)}. Stage 4 refuses "
            "rather than guessing whether bytes exist behind a row.")

    licence, terms_url, licence_status = _terms(source_key, _str(row.get("license")))
    adapter = f"{row.get('adapter')}@{row.get('adapter_version')}"
    common: dict[str, Any] = {
        "acquisition_record_id": new_record_id("acq_s3", source_key, stage3_id),
        "source_key": source_key,
        "source_name": f"Stage-3 {source_key} ({adapter})",
        "stage3_source_record_id": stage3_id,
        "stable_record_id": stage3_id,
        "url": _str(row.get("retrieval_url")) or _str(row.get("source_endpoint")),
        # Stage 3 hashes its canonical query rather than storing it. Carried as a hash.
        "canonical_query_sha256": _str(row.get("query_canonical")),
        "access_date": access_date,
        "release_or_last_updated": _str(row.get("source_release")),
        "license": licence,
        "license_or_terms_url": terms_url,
        "license_status": licence_status,
        "raw_media_type": _str(row.get("raw_media_type")),
        "extraction_transform": REUSE_TRANSFORM,
        "adapter_code_sha256": adapter_code_sha256(),
    }

    if status == "acquired_public":
        missing = [f for f in REQUIRED_WHEN_ACQUIRED if _clean(row.get(f)) in (None, "")]
        if missing:
            raise Rejection(
                "stage3_source_record_incomplete",
                f"Stage-3 source record {stage3_id!r} ({source_key}) claims acquired_public but "
                f"is missing {sorted(missing)}. Stage 4 carries such a record VERBATIM or not at "
                "all — it does not supply a hash, a byte count or a release that Stage 3 never "
                "recorded.")
        return AcquisitionRecord(
            **common,
            source_type=_source_type(source_key),
            origin="reused_from_stage3",
            raw_sha256=_str(row["raw_sha256"]),
            raw_bytes=_int(row["raw_bytes"]),
            # Stage-4's gate 1 re-derived the table hash these bytes are bound by; no human has
            # re-read the response itself.
            review_status="machine_verified",
            evidence_state="observed",
            note=f"carried verbatim from the admitted Stage-3 bundle (parse_status="
                 f"{_str(row.get('parse_status'))})",
        )

    if status == "synthetic_fixture":
        raw_sha = _str(row.get("raw_sha256"))
        if not raw_sha:
            raise Rejection(
                "stage3_source_record_incomplete",
                f"Stage-3 fixture record {stage3_id!r} carries no raw_sha256; a fixture still "
                "hashes the exact bytes it parsed")
        return AcquisitionRecord(
            **common,
            source_type="fixture",
            origin="synthetic_fixture",
            raw_sha256=raw_sha,
            raw_bytes=_int(row.get("raw_bytes")),
            review_status="not_applicable",
            evidence_state="not_applicable",
            note="Stage-3 synthetic fixture, carried without upgrade. Not evidence about any "
                 "drug.",
        )

    # not_acquired: Stage 3 planned the request and never made it. There are no bytes, so there
    # is no observation — and no hash is invented to stand in for one.
    return AcquisitionRecord(
        **common,
        source_type=_source_type(source_key),
        origin="reused_from_stage3",
        review_status="not_applicable",
        evidence_state="not_evaluated",
        note=f"Stage 3 recorded this source as not_acquired: "
             f"{_str(row.get('parse_detail')) or 'no acquisition step ran'}. There are no bytes "
             "behind it, so there is no evidence behind it.",
    )


def reuse_stage3_sources(rows: list[dict[str, Any]], *, access_date: str) -> list[AcquisitionRecord]:
    return [reuse_stage3_source(r, access_date=access_date) for r in rows]


def stage3_missing_lanes(rows: list[dict[str, Any]]) -> list[MissingEvidence]:
    """What Stage 3 planned and never acquired, stated as an absence — one entry per source."""
    seen: dict[str, MissingEvidence] = {}
    for row in rows:
        if _str(row.get("acquisition_status")) != "not_acquired":
            continue
        source_key = str(row.get("source") or "unknown")
        if source_key in seen:
            continue
        seen[source_key] = MissingEvidence(
            lane=LANE_OF_SOURCE.get(source_key, "unclassified"),
            evidence_state="not_evaluated",
            source_key=source_key,
            reason=(
                f"Stage 3 declared a {source_key} source record and never acquired it "
                f"({_str(row.get('parse_detail')) or 'no acquisition step ran'}). Stage 4 does "
                "not infer the response it would have returned."),
        )
    return [seen[k] for k in sorted(seen)]


def adapter_code_sha256() -> str:
    """The hash of THIS module's source — the code that did the carrying."""
    return code_sha256(__file__)
