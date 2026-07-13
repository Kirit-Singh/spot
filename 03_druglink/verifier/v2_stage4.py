"""The STAGE-4 READ CONTRACT: what a downstream stage must be able to read, join and reopen.

Imports NOTHING from ``druglink``. Split from :mod:`verifier.v2_checks` at the 500-line gate.

Stage 4 named exactly what it needs out of a v2 bundle, and each of these is checked on the
EMITTED ROWS rather than on the schema:

  * an ADDRESS — every source record names the exact ChEMBL row it came from, so an assertion
    can be reopened at its origin. "ChEMBL says so" is not provenance; "ChEMBL 37, this row" is.
  * a RELEASE, a SOURCE HASH and a LICENCE, bound PER SOURCE and not once per bundle.
  * STATED ABSENCE — every nullable magnitude carries a companion status that says why it is
    absent. A null a consumer coerces becomes a 0, and a 0 sorts.
  * ONE candidate_id, byte-identical in every table that references a candidate. Stage 4 joins
    on it; an id regenerated per table is not an identity.

A column of empty strings satisfies a schema and proves nothing, so every one of these is
asserted NON-EMPTY over a non-empty table.
"""
from __future__ import annotations

from typing import Any

from . import canon
from . import v2_contract as C
from . import v2_tables as T
from .report import Report


def _gate(rep: Report, gate: str, sentence: str, ok: Any, detail: str = "") -> bool:
    return rep.check(f"[{gate}] {sentence}", ok, detail)


def check_stage4_read_contract(rep: Report, *,
                               emitted: dict[str, list[dict[str, Any]]]) -> None:
    """What a DOWNSTREAM stage must be able to read, join on, and reopen.

    A column of empty strings satisfies a schema and proves nothing, so every field a
    consumer depends on is asserted NON-EMPTY on the rows themselves.
    """
    empty: list[str] = []
    for name, columns in T.REQUIRED_NON_EMPTY.items():
        rows = emitted.get(name) or []
        for column in columns:
            n = sum(1 for r in rows if r.get(column) in (None, ""))
            if n:
                empty.append(f"{name}.{column}: {n}/{len(rows)} empty")
    _gate(rep, C.GATE_EMPTY_REQUIRED_COLUMN,
          "every column a downstream stage joins on, reopens or reads is NON-EMPTY on every "
          "row — the candidate identity, the typed origin, the source locator, the release, "
          "the licence and every stated-absence status. A column of empty strings satisfies a "
          "schema and proves nothing",
          not empty, "; ".join(empty[:4]))

    sources = emitted.get("source_records") or []
    unaddressed = [s.get("source_record_id") for s in sources
                   if not str(s.get("source_locator") or "").startswith(
                       f"{C.SOURCE_SCHEME_CHEMBL}:")
                   or f"/{s.get('mec_id')}" not in str(s.get("source_locator") or "")]
    _gate(rep, C.GATE_NO_SOURCE_LOCATOR,
          "every source record carries an ADDRESSABLE locator that names the exact row it "
          "came from (chembl:<release>:drug_mechanism/<mec_id>). A source record that cannot "
          "be reopened at its origin is an assertion with no address, and 'ChEMBL says so' is "
          "not provenance",
          not unaddressed and bool(sources), f"{len(unaddressed)}: {unaddressed[:3]}")

    unreleased = [s.get("source_record_id") for s in sources
                  if not s.get("source_release") or not s.get("source_sha256")
                  or not s.get("source_license")
                  or str(s.get("source_release")) not in str(s.get("source_locator"))]
    _gate(rep, C.GATE_NO_SOURCE_RELEASE,
          "every source record names the exact RELEASE, source SHA-256 and LICENCE it was "
          "drawn from, and its locator resolves inside that release (a release is bound PER "
          "SOURCE, not once per bundle: 'ChEMBL 37, this row' is provenance)",
          not unreleased and bool(sources), f"{len(unreleased)}: {unreleased[:3]}")

    unstated: list[str] = []
    for value_col, status_col, table in T.STATED_ABSENCE:
        for row in emitted.get(table) or []:
            status = row.get(status_col)
            if status not in T.MISSINGNESS_STATES:
                unstated.append(f"{table}.{status_col}={status!r}")
            elif row.get(value_col) in (None, "") and status in (T.STATED, T.RANKED):
                unstated.append(f"{table}.{status_col} claims {status!r} with no value")
            elif value_col == "arm_rank" and row.get(value_col) == 0:
                unstated.append(f"{table}.arm_rank=0 (a null someone coerced)")
    _gate(rep, C.GATE_ABSENCE_NOT_STATED,
          "every ABSENCE is stated explicitly — an unranked target says unranked_by_source, "
          "an inferred node says not_applicable_inferred_origin, a molecule with no max_phase "
          "says not_stated_by_source. Absence is a VALUE, never a missing key: a null a "
          "consumer coerces becomes a 0, and a 0 sorts — which is exactly how an unranked "
          "target reaches first place",
          not unstated, "; ".join(sorted(set(unstated))[:4]))


def check_candidate_identity(rep: Report, *, doc: dict[str, Any],
                             emitted: dict[str, list[dict[str, Any]]]) -> None:
    """ONE candidate_id, byte-identical everywhere. Stage 4 joins on it."""
    known = {str(c["candidate_id"]) for c in (emitted.get("candidates") or [])}
    dangling: list[str] = []
    unstable: list[str] = []
    for name in ("target_drug_edges", "arm_summaries", "source_records"):
        for row in emitted.get(name) or []:
            if row.get("candidate_id") != row.get("active_moiety_id"):
                unstable.append(f"{name}: {row.get('candidate_id')!r} != "
                                f"{row.get('active_moiety_id')!r}")
            if name != "source_records" and str(row.get("candidate_id")) not in known:
                dangling.append(f"{name}: {row.get('candidate_id')!r}")
    for row in emitted.get("dispositions") or []:
        if row.get("subject_kind") == "candidate" \
                and str(row.get("subject_id")) not in known:
            dangling.append(f"dispositions: {row.get('subject_id')!r}")

    _gate(rep, C.GATE_CANDIDATE_ID_NOT_STABLE,
          "ONE candidate_id, byte-identical in every table that references a candidate — "
          "edges, arm summaries, source records, dispositions — and it IS the active-moiety "
          "id. Stage 4 joins on it: an id regenerated per table is not an identity, it is a "
          "coincidence that holds until two tables disagree and silently join the wrong rows",
          not unstable and not dangling,
          "; ".join((unstable + dangling)[:4]))

    in_doc = [str(c.get("candidate_id")) for c in (doc.get("candidates") or [])]
    _gate(rep, C.GATE_CANDIDATE_ID_NOT_STABLE,
          "the DOCUMENT's candidate ids are exactly the candidates table's ids (the manifest "
          "and the tables must name the same candidates, or a consumer reading one and "
          "joining the other silently drops rows)",
          sorted(in_doc) == sorted(known),
          f"document {len(in_doc)} vs table {len(known)}")


def check_provenance(rep: Report, *, emitted: dict[str, list[dict[str, Any]]],
                     aggregate: dict[str, Any], store: dict[str, Any],
                     doc: dict[str, Any], digest: str) -> None:
    """The provenance rows ARE the artifacts this verifier independently re-admitted.

    Not rebuilt row-for-row: the code-tree and vocabulary digests it carries are properties of
    the PRODUCER's tree, and a verifier that recomputed them would be re-running the producer.
    So every row that names an UPSTREAM artifact is compared against what this verifier read
    off the disk itself, every row recomputes its OWN id, and the direction vocabulary is the
    one this verifier restated.
    """
    rows = emitted.get("provenance") or []
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_kind.setdefault(str(row.get("kind")), []).append(row)

    forged = [r.get("provenance_id") for r in rows
              if canon.short({k: r.get(k) for k in T.PROVENANCE_COLUMNS
                              if k != "provenance_id"}) != r.get("provenance_id")]
    _gate(rep, C.GATE_PROVENANCE_BINDING,
          "every provenance row recomputes its OWN id from its own content (a row that cannot "
          "prove who it is cannot bind anything)",
          not forged and bool(rows), f"{len(forged)} forged: {forged[:3]}")

    drift: list[str] = []
    manifest_rows = by_kind.get("stage2_aggregate_manifest") or []
    if len(manifest_rows) != 1 or \
            manifest_rows[0].get("raw_sha256") != aggregate["manifest_raw_sha256"] or \
            manifest_rows[0].get("canonical_sha256") != aggregate[
                "manifest_canonical_sha256"]:
        drift.append("stage2_aggregate_manifest")

    report_rows = by_kind.get("stage2_independent_report") or []
    if len(report_rows) != 1 or \
            report_rows[0].get("raw_sha256") != aggregate["report_raw_sha256"] or \
            report_rows[0].get("verdict") != aggregate["aggregate_verdict"]:
        drift.append("stage2_independent_report")

    release_rows = by_kind.get("stage1_release") or []
    if len(release_rows) != 1 or \
            release_rows[0].get("raw_sha256") != aggregate["stage1_release_sha256"]:
        drift.append("stage1_release")

    lanes = {str(r.get("subject")): r.get("raw_sha256")
             for r in by_kind.get("stage2_lane_artifact") or []}
    if lanes != {b["bundle_key"]: b["raw_sha256"] for b in aggregate["bundles"]}:
        drift.append(f"stage2_lane_artifact ({len(lanes)} of {C.N_BUNDLES})")

    store_rows = by_kind.get("universe_store") or []
    if len(store_rows) != 1 or store_rows[0].get("subject") != store["store_id"] or \
            store_rows[0].get("canonical_sha256") != store["typed_universe_sha256"]:
        drift.append("universe_store")

    pins = {str(r.get("subject")): r.get("canonical_sha256")
            for r in by_kind.get("universe_store_artifact") or []}
    extraction = store["manifest"].get("extraction") or {}
    if pins != {name: extraction.get(pin) for name, pin in C.STORE_ARTIFACT_PINS.items()}:
        drift.append("universe_store_artifact")

    vocab = {str(r.get("subject")): r.get("canonical_sha256")
             for r in by_kind.get("vocabulary") or []}
    if vocab.get("direction") != digest:
        drift.append("vocabulary.direction")

    _gate(rep, C.GATE_PROVENANCE_BINDING,
          "the provenance table enumerates EXACTLY the artifacts this verifier re-admitted "
          f"from disk — the Stage-2 manifest, the separate independent report, the Stage-1 "
          f"release, all {C.N_BUNDLES} lane artifacts, the universe store and its "
          "content-pinned artifacts — and the direction vocabulary is the one this verifier "
          "restated. A binding a reader cannot enumerate is a binding a reader cannot check",
          not drift, str(drift[:4]))

    method = doc.get("method") or {}
    code = {str(r.get("subject")): r.get("canonical_sha256")
            for r in by_kind.get("code_identity") or []}
    _gate(rep, C.GATE_PROVENANCE_BINDING,
          "the provenance table binds the code tree, the schema set and the environment lock "
          "the document declares (they identify the producer, and a bundle that cannot name "
          "what built it cannot be rebuilt)",
          code.get("code_tree") == method.get("code_tree_sha256")
          and code.get("schema_set") == method.get("schemas_sha256")
          and code.get("env_lock") == method.get("env_lock_sha256")
          and all(code.values()),
          str(sorted(code)))
