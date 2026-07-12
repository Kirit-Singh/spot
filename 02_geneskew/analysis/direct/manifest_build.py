"""B5 — BUILD the contributor manifest from the pinned source. Generator, not verifier.

WHY THIS EXISTS
---------------
The only materialized manifest was produced by an external process and is STALE: it
labels 6 of the 33,983 released pooled-main scopes ``ambiguous`` — ENSG00000137265 and
ENSG00000196535, at each of the three conditions — when the source in fact keeps
targeting guides for every one of them. ``preflight.py`` correctly refuses it
(``SCOPE_DOWNGRADED``: a source-determinable scope labelled ambiguous), so no run can
start from it, and there was no way to make one that could.

WHY THOSE SIX WERE WRONG
------------------------
Both genes carry TWO symbol aliases in the guide library — IRF4/MUM1 and MYO18A/TIAF1 —
so their guides arrive under two different symbol families (``IRF4-1, IRF4-2, MUM1-1,
MUM1-2``) while naming ONE Ensembl target. A generator that resolved contributors by
SYMBOL saw two families for one scope and called it ambiguous. Resolved by the thing the
release actually keys on — ``(perturbed_gene_id, culture_condition)`` — the contributor
set is not ambiguous at all: it is every kept TARGETING guide for that scope. There was
never a missing fact here, only a resolution done in the wrong namespace.

THE RULE, IN ONE LINE
---------------------
A scope's contributors are exactly the guides the SOURCE kept for the DE fit, of type
``targeting``, for that (target, condition). ``replay.source_provable_guides`` is the one
authority on that set, and it is the same function the strict-replay gate re-derives from
the raw rows to check this manifest. Nothing here consults the released by-guide slots, a
prior manifest, or a guide's NAME.

THE ORDER IS THE CONTRACT
-------------------------
The evidence can only be built in one direction, because the record id is a hash of the
completeness proof:

    raw source -> the kept offsets + row names it holds
               -> source records carrying that proof
               -> the record ids DERIVED from it
               -> the manifest citations that name those ids

Nothing here runs backwards. A manifest row cannot mint its own citation: its payload
does not hold the offset proof, and the proof is what the id is a hash of.

This module GENERATES. ``preflight``/``replay`` VERIFY, independently, against the same
raw source — and they are what decides whether what this wrote is admissible.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any, Optional

from . import domain, identity, io_data, manifest_schema, record_id, replay, sources
from .hashing import file_sha256

MANIFEST_NAME = "stage02_contributor_manifest.canonical.v3.json"
RECORD_TABLE_NAME = "stage02_source_records.canonical.v2.json"
REPLAY_REPORT_NAME = "stage02_source_replay.json"
REGISTRY_NAME = "source_registry.json"

DE_SOURCE_NAME = "GWCD4i.DE_stats.h5ad"
PB_SOURCE_NAME = "GWCD4i.pseudobulk_merged.h5ad"

IDENTITY_METHOD = "released_per_guide_identity_column"
SOURCE_CLASS = manifest_schema.SOURCE_CLASS_MARSON

BUILDER_ID = "spot.stage02.direct.manifest_builder.v1"
RESOLUTION_RULE = (
    "a pooled-main scope's contributors are exactly the guides the source kept for the "
    "DE fit (keep_for_DE) with guide_type == targeting, for that "
    "(perturbed_gene_id, culture_condition). Resolution is by the released ENSEMBL "
    "target id, never by guide NAME: a gene with two symbol aliases (IRF4/MUM1, "
    "MYO18A/TIAF1) has one contributor set, not an ambiguity")


def _rows_and_records(by_condition: dict[str, dict], provable: dict[tuple, set],
                      offsets: dict[tuple, list], row_names: dict[tuple, list],
                      pb_sha: str) -> tuple[list[dict], list[dict]]:
    """Manifest rows and their source records, in the ONE order the id rule permits."""
    rows: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []

    for condition in sorted(by_condition):
        for target_id in sorted(by_condition[condition]):
            ident = by_condition[condition][target_id]
            base = {
                "estimate_type": domain.POOLED_MAIN_TYPE,
                "estimate_id": domain.POOLED_MAIN_ID,
                "released_estimate_id": ident.released_estimate_id,
                "target_id": ident.target_id,
                "target_id_namespace": ident.target_id_namespace,
                "target_symbol": ident.target_symbol,
                "target_ensembl": ident.released_target_ensembl,
                "condition": condition,
                "donor_pair": None,
                "included": True,
            }
            kept = sorted(provable.get((str(target_id), str(condition))) or set())
            if not kept:
                # GENUINELY ambiguous: the source kept no targeting guide for this
                # scope. Emitted, never guessed. (For the pinned release this branch is
                # empty — every released scope is determinable — and it stays here so a
                # future release that is not gets the honest answer instead of a forged
                # one.)
                rows.append(dict(base, guide_id=None,
                                 evidence_state=manifest_schema.AMBIGUOUS,
                                 source_record_id=None))
                continue

            for guide in kept:
                key = (str(target_id), str(condition), guide)
                rec = {
                    **{k: base[k] for k in sources.ESTIMATE_KEY},
                    "guide_id": guide,
                    "identity_method": IDENTITY_METHOD,
                    "source_id": PB_SOURCE_NAME,
                    "source_sha256": pb_sha,
                    # THE COMPLETE PROOF: every kept raw row for this contributor, in
                    # source order, with the names the source gives them.
                    "pseudobulk_source_offsets": list(offsets[key]),
                    "pseudobulk_source_rows": list(row_names[key]),
                    "source_row_index": offsets[key][0],
                }
                # only NOW is the id derivable: it is a hash of the proof above
                rec["source_record_id"] = record_id.derive_record_id(rec)
                records.append(rec)
                rows.append(dict(base, guide_id=guide,
                                 evidence_state=manifest_schema.DETERMINED,
                                 identity_method=IDENTITY_METHOD,
                                 source_id=PB_SOURCE_NAME, source_sha256=pb_sha,
                                 source_record_id=rec["source_record_id"]))

    # the table's bytes must not depend on the order the manifest happened to list rows
    records.sort(key=lambda r: r["source_record_id"])
    return rows, records


def _dump(path: str, doc: Any) -> str:
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def build(*, de_main: str, pseudobulk: str, out_dir: str,
          target_identity_map: Optional[str] = None) -> dict[str, Any]:
    """Write a fresh, complete contributor manifest + record table + replay report."""
    os.makedirs(out_dir, exist_ok=True)
    created_at = _dt.datetime.now(_dt.timezone.utc).isoformat()

    # ---- the RELEASED evidence domain: every pooled-main scope, all conditions ----
    idmap = identity.load_identity_map(target_identity_map)
    raw = io_data.load_main_identity_universe(de_main)
    by_condition = {
        c: {t: identity.resolve(r["released_estimate_id"], r["target_id"],
                                r["target_symbol"], idmap)
            for t, r in targets.items()}
        for c, targets in raw.items()}
    n_scopes = len(domain.global_pooled_main_scopes(by_condition))

    # ---- the SOURCE's own evidence. obs only; no dense layer is touched. ----
    cols = replay.read_evidence(pseudobulk)
    _complete, offsets, row_names, _types = replay.derive_from_source(cols)
    provable = replay.source_provable_guides(cols)

    pb_sha, de_sha = file_sha256(pseudobulk), file_sha256(de_main)
    rows, records = _rows_and_records(by_condition, provable, offsets, row_names, pb_sha)

    n_determined = sum(1 for r in rows
                       if r["evidence_state"] == manifest_schema.DETERMINED)
    n_ambiguous = sum(1 for r in rows
                      if r["evidence_state"] == manifest_schema.AMBIGUOUS)
    scopes_determined = len({(r["target_id"], r["condition"]) for r in rows
                             if r["evidence_state"] == manifest_schema.DETERMINED})
    scopes_ambiguous = len({(r["target_id"], r["condition"]) for r in rows
                            if r["evidence_state"] == manifest_schema.AMBIGUOUS})

    table_path = _dump(os.path.join(out_dir, RECORD_TABLE_NAME), {
        "schema_version": sources.SCHEMA_VERSION,
        record_id.RULE_METADATA_KEY: json.loads(json.dumps(record_id.RULE_METADATA)),
        "records": records,
    })
    manifest_path = os.path.join(out_dir, MANIFEST_NAME)

    def manifest_doc(source_list: list[dict]) -> dict[str, Any]:
        return {
            "schema_version": manifest_schema.SCHEMA_VERSION,
            "source_record_table_schema_version":
                manifest_schema.SOURCE_RECORD_TABLE_SCHEMA,
            "identity_method": IDENTITY_METHOD,
            "source_class": SOURCE_CLASS,
            "source_record_table": RECORD_TABLE_NAME,
            "source_replay_report": REPLAY_REPORT_NAME,
            "builder_id": BUILDER_ID,
            "resolution_rule": RESOLUTION_RULE,
            "generated_at": created_at,
            "counts": {
                "n_released_pooled_main_scopes": n_scopes,
                "n_scopes_determined": scopes_determined,
                "n_scopes_ambiguous": scopes_ambiguous,
                "n_rows": len(rows),
                "n_rows_determined": n_determined,
                "n_rows_ambiguous": n_ambiguous,
                "n_source_records": len(records),
            },
            "sources": source_list,
            "rows": rows,
        }

    # pass 1: the rows, so the replay has a manifest to prove completeness against
    _dump(manifest_path, manifest_doc([]))
    report = replay.build_report(table_path=table_path, manifest_path=manifest_path,
                                 source_path=pseudobulk, source_id=PB_SOURCE_NAME)
    replay_path = _dump(os.path.join(out_dir, REPLAY_REPORT_NAME), report)

    pins = {
        PB_SOURCE_NAME: {"path": os.path.abspath(pseudobulk), "sha256": pb_sha,
                         "revision": f"sha256:{pb_sha}",
                         "role": "per_guide_membership_evidence"},
        DE_SOURCE_NAME: {"path": os.path.abspath(de_main), "sha256": de_sha,
                         "revision": f"sha256:{de_sha}",
                         "role": "release_identity_universe"},
        RECORD_TABLE_NAME: {"path": RECORD_TABLE_NAME,
                            "sha256": file_sha256(table_path),
                            "revision": f"sha256:{file_sha256(table_path)}"},
        REPLAY_REPORT_NAME: {"path": REPLAY_REPORT_NAME,
                             "sha256": file_sha256(replay_path),
                             "revision": f"sha256:{file_sha256(replay_path)}"},
    }
    registry_path = _dump(os.path.join(out_dir, REGISTRY_NAME), {"sources": pins})
    source_list = [{"name": n, "sha256": p["sha256"], "revision": p["revision"]}
                   for n, p in sorted(pins.items())]

    # pass 2: the same rows, now with every source pinned
    _dump(manifest_path, manifest_doc(source_list))

    return {
        "builder_id": BUILDER_ID,
        "manifest_path": manifest_path,
        "record_table_path": table_path,
        "replay_report_path": replay_path,
        "source_registry_path": registry_path,
        "manifest_sha256": file_sha256(manifest_path),
        "n_released_pooled_main_scopes": n_scopes,
        "n_scopes_determined": scopes_determined,
        "n_scopes_ambiguous": scopes_ambiguous,
        "n_rows": len(rows),
        "n_source_records": len(records),
        # the replay report's OWN field names — read, never guessed. A key that does not
        # exist must not come back as a quiet None: that is a missing statistic wearing
        # the clothes of a measured one.
        "replay_verdict": report["verdict"],
        "replay_completeness_verdict": report["completeness_verdict"],
        "replay_n_records_offset_proven": report["n_records_offset_proven"],
        "replay_n_scopes_complete": report["n_scopes_complete"],
        "replay_n_scopes_downgraded": report["n_scopes_downgraded"],
        "replay_n_scopes_overclaimed": report["n_scopes_overclaimed"],
        "replay_n_failed": report["n_failed"],
        "sources": source_list,
    }


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Build the Stage-2 contributor manifest from the pinned source")
    ap.add_argument("--de-main", required=True)
    ap.add_argument("--pseudobulk", required=True)
    ap.add_argument("--target-identity-map", default=None)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)

    result = build(de_main=args.de_main, pseudobulk=args.pseudobulk,
                   out_dir=args.out_dir,
                   target_identity_map=args.target_identity_map)
    print(json.dumps(result, indent=2, sort_keys=True))
    # a manifest that does not cover every released scope is not a manifest
    return 0 if result["n_scopes_ambiguous"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
