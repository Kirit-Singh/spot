"""Independent source-catalog binding: does every result-affecting row rest on real bytes?

Reconstructed from the RELEASE alone — the parquet tables plus `source_catalog` — and
importing nothing from `analysis/`. The engine has its own binding pass over its own input
records (`analysis/integrity.py`); this one re-derives the same bindings from the emitted
tables and must reach the same verdict independently. Neither reads the other's answer.

The audit's finding: `potency_context_links`, `delivery_assignments` and `search_manifests`
were consumed as evidence but never bound to the source registry. A link citing
`src.DOES_NOT_EXIST` with an invented 64-hex hash turned a margin from `not_computable`
into `computed` and an NEBPI class from `None` into `insufficiently_permeable`, and both
verifiers reported all-pass. So the rule here is uniform and has no exemptions:

    a row that cites a source must cite a source that EXISTS, was ACQUIRED, and whose
    ACQUIRED BYTES HASH TO WHAT THE ROW DECLARES.

A half-binding (an id with no hash, or a hash with no id) is malformed, not lenient: it is
the shape a fabricated citation takes.
"""

from __future__ import annotations

from typing import Any, Optional

# table -> (row id column, source id column, response hash column, binding is optional)
#
# An OPTIONAL binding may be absent entirely (both columns null) and the row is still
# legal — an unevidenced delivery assignment is downgraded to uncertain, and a
# `no_evidence_found` safety row's state is a claim about a SEARCH, not about a document.
# It may never be HALF present, and when it IS present it is checked exactly as strictly.
BOUND_TABLES: tuple[tuple[str, str, str, str, bool], ...] = (
    ("property_evidence", "property_record_id", "source_record_id", "raw_response_sha256", False),
    ("potency_evidence", "potency_id", "source_record_id", "raw_response_sha256", False),
    ("potency_context_links", "link_id", "source_record_id", "raw_response_sha256", False),
    ("transporter_evidence", "observation_id", "source_record_id", "raw_response_sha256", False),
    ("exposure_evidence", "measurement_id", "source_record_id", "raw_response_sha256", False),
    ("nebpi_observations", "observation_id", "source_record_id", "raw_response_sha256", False),
    ("search_manifests", "search_id", "source_record_id", "response_sha256", False),
    ("delivery_assignments", "assignment_id", "evidence_source_record_id", "evidence_sha256", True),
    ("safety_evidence", "evidence_id", "source_record_id", "raw_response_sha256", True),
)

# A source with no bytes behind it is not a source. `synthetic_fixture` HAS bytes (the
# cached fixture response is hashed for real) and is legal evidence for a fixture run; it
# is `production_eligibility` that refuses to promote it, not this check.
UNACQUIRED = "not_acquired"


def _catalog(tables: dict[str, list[dict]]) -> dict[str, dict]:
    return {r["source_record_id"]: r for r in tables.get("source_catalog", [])}


def binding_failures(tables: dict[str, list[dict]]) -> dict[str, list[str]]:
    """-> {table: [why each bad row is bad]}. Empty means every row rests on real bytes."""
    catalog = _catalog(tables)
    out: dict[str, list[str]] = {}

    for table, id_col, src_col, hash_col, optional in BOUND_TABLES:
        problems: list[str] = []
        for row in tables.get(table, []):
            rid = row.get(id_col)
            src = row.get(src_col)
            sha = row.get(hash_col)

            if src is None and sha is None:
                if not optional:
                    problems.append(f"{rid}: no source binding, and this row requires one")
                continue
            if src is None or sha is None:
                problems.append(
                    f"{rid}: half a source binding ({src_col}={src!r}, {hash_col}={sha!r}). "
                    "An id without bytes, or bytes without an id, cites nothing."
                )
                continue

            rec = catalog.get(src)
            if rec is None:
                problems.append(
                    f"{rid}: cites source {src!r}, which is not in source_catalog. There is no "
                    "record of it ever being acquired."
                )
                continue
            if rec.get("acquisition_status") == UNACQUIRED:
                problems.append(
                    f"{rid}: cites source {src!r}, which was never acquired. No bytes behind "
                    "it, so no evidence behind the row."
                )
                continue
            if rec.get("raw_sha256") != sha:
                problems.append(
                    f"{rid}: declares {hash_col}={sha!r}, but source {src!r} hashes to "
                    f"{rec.get('raw_sha256')!r}. The row was not taken from those bytes."
                )
        if problems:
            out[table] = sorted(problems)
    return out


def duplicate_row_ids(tables: dict[str, list[dict]]) -> dict[str, list[str]]:
    """-> {table: [ids that appear more than once]}. A row id is supplied exactly once."""
    out: dict[str, list[str]] = {}
    for table, id_col, _s, _h, _o in BOUND_TABLES:
        seen: set[str] = set()
        dupes: set[str] = set()
        for row in tables.get(table, []):
            rid = row.get(id_col)
            if rid is None:
                continue
            (dupes if rid in seen else seen).add(rid)
        if dupes:
            out[table] = sorted(dupes)
    return out


def unique_potency_context_links(tables: dict[str, list[dict]]) -> list[str]:
    """-> [(potency, tumour context) pairs claimed by more than one link].

    Two links relating one potency to one tumour context would make the link the margin
    cites depend on which row was scanned first.
    """
    seen: dict[tuple[str, str], str] = {}
    clashes: list[str] = []
    for row in sorted(tables.get("potency_context_links", []),
                      key=lambda r: str(r.get("link_id"))):
        pair = (str(row.get("potency_id")), str(row.get("tumor_context")))
        if pair in seen:
            clashes.append(f"{seen[pair]} and {row.get('link_id')} both relate {pair[0]} "
                           f"to {pair[1]}")
        else:
            seen[pair] = str(row.get("link_id"))
    return sorted(clashes)


def negative_searches_are_manifested(tables: dict[str, list[dict]]) -> list[str]:
    """Every `no_evidence_found` safety row names a manifest that is actually in the release.

    Without the manifest, "we looked and found nothing" is indistinguishable from "nobody
    looked", and the manifest is what makes the negative reproducible.
    """
    manifests = {r["search_id"] for r in tables.get("search_manifests", [])}
    bad: list[str] = []
    for row in tables.get("safety_evidence", []):
        if row.get("evidence_state") != "no_evidence_found":
            continue
        sid: Optional[Any] = row.get("search_id")
        if not sid:
            bad.append(f"{row.get('evidence_id')}: claims no_evidence_found with no search_id")
        elif sid not in manifests:
            bad.append(f"{row.get('evidence_id')}: names search {sid!r}, which has no manifest "
                       "in this release")
    return sorted(bad)


def empty_searches_are_empty(tables: dict[str, list[dict]]) -> list[str]:
    """A manifest backing a negative result returned zero rows. Anything else is not a negative."""
    return sorted(
        f"{r.get('search_id')}: n_results={r.get('n_results')}"
        for r in tables.get("search_manifests", [])
        if r.get("n_results") != 0
    )
