"""Re-issue the canonical pair under the compiled record-id rule. NO GRANDFATHERING.

The audited Claude Science pair is scientifically sound — its contributor sets, offsets
and row names are the evidence, and none of them are touched here. What is broken is the
KEYING: the emitted ``srec-...`` ids were minted under a rule the table itself does not
declare (``srcrec:sha256:`` + the full digest of a payload INCLUDING the offset and
row-name proof). Under the emitted rule a record's offsets could be swapped for a
different set and every id would still re-derive, so the completeness proof was never
bound to the record that carries it.

This tool re-keys the pair and nothing else:

  * every record id is RECOMPUTED from the record's own full payload (identity + proof);
  * every manifest citation is rewritten to the new id of the record it already cited;
  * schema versions are bumped (records v2, manifest v3) and the table's declared rule
    metadata is written from the COMPILED rule, so the two can never drift again;
  * every other field — guide_id, offsets, row names, n_guides, evidence_state,
    ambiguity reasons — is carried through VERBATIM. No contributor set is re-derived,
    no evidence is invented, nothing is dropped.

Re-keying is not verification. The re-issued pair still has to pass strict replay
against the raw source (``replay.py``) — that is what decides whether the evidence it
carries is true. This only makes the pair say honestly what it is.

THE HASH CYCLE, BROKEN. The manifest pins the replay report; the report must therefore
NOT hash the manifest. It binds the raw source and the source-record table. What binds
the manifest's semantics instead is manifest<->table 1:1 resolution plus the
independently derived scope coverage — both re-derived by the standalone verifier.

So the pair is emitted in two passes:

    1. python -m direct.reissue --old-manifest M1 --old-records T1 --out-dir D
       -> T2 (final) + M2 (draft: no replay-report pin yet)
    2. python -m direct.replay --source-records D/T2 --manifest D/M2 --source PB \
           --source-id GWCD4i.pseudobulk_merged.h5ad --out D/R2
    3. python -m direct.reissue --old-manifest M1 --old-records T1 --out-dir D \
           --replay-report D/R2
       -> T2 (byte-identical) + M2 (final, pinning R2)

Pass 3 does not change the rows, so the verdict R2 reached in pass 2 still describes
them.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

from . import record_id
from .hashing import file_sha256
from .manifest_schema import SCHEMA_VERSION as MANIFEST_SCHEMA
from .manifest_schema import SOURCE_RECORD_TABLE_SCHEMA
from .record_id import RULE_METADATA, RULE_METADATA_KEY
from .sources import SCHEMA_VERSION as RECORDS_SCHEMA

# The re-issue rule, by id. What it MEANS is this module's docstring.
REISSUE_RULE_ID = "spot.stage02.direct.reissue_rule.remint_ids_verbatim_evidence.v1"

RECORDS_OUT = "stage02_source_records.canonical.v2.json"
MANIFEST_OUT = "stage02_contributor_manifest.canonical.v3.json"
REGISTRY_OUT = "source_registry.runtime.json"

# Carried through verbatim; only ``source_record_id`` is re-minted.
REKEYED_FIELD = "source_record_id"


class ReissueError(ValueError):
    """The pair cannot be re-issued faithfully. Refuse; never repair silently."""


def _load(path: str, what: str) -> dict[str, Any]:
    with open(path) as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict):
        raise ReissueError(f"{what} is malformed: {path}")
    return doc


def rekey_records(records: list[dict[str, Any]]) -> tuple[list[dict], dict[str, str]]:
    """Re-mint every record id from its own full payload. Returns (records, old->new).

    Every field except the id is preserved exactly as the producer emitted it.
    """
    out: list[dict[str, Any]] = []
    remap: dict[str, str] = {}
    for i, rec in enumerate(records):
        old = rec.get(REKEYED_FIELD)
        if old is None:
            raise ReissueError(f"source record {i}: no {REKEYED_FIELD} to re-key")
        new = record_id.derive_record_id(rec)          # raises on a malformed proof
        if str(old) in remap and remap[str(old)] != new:
            raise ReissueError(
                f"source record {i}: the old id {old!r} is used by two records that "
                "derive different new ids; the old table was not 1:1 and cannot be "
                "re-keyed unambiguously")
        remap[str(old)] = new
        out.append(dict(rec, **{REKEYED_FIELD: new}))

    minted = {r[REKEYED_FIELD] for r in out}
    if len(minted) != len(out):
        raise ReissueError(
            f"re-issue produced {len(minted)} distinct ids for {len(out)} records: two "
            "records share an identity payload (same estimate, guide AND proof), so "
            "one of them is a duplicate claim")
    return out, remap


def rekey_rows(rows: list[dict[str, Any]],
               remap: dict[str, str]) -> tuple[list[dict], int]:
    """Rewrite every citation to the new id of the record it already cited."""
    out: list[dict[str, Any]] = []
    n_rewritten = 0
    for i, row in enumerate(rows):
        cited = row.get(REKEYED_FIELD)
        if cited is None or str(cited).strip().lower() in ("", "none", "null", "nan"):
            out.append(dict(row))          # an ambiguous row cites nothing. It stays so.
            continue
        new = remap.get(str(cited))
        if new is None:
            raise ReissueError(
                f"contributor manifest row {i}: cites {cited!r}, which is in no source "
                "record. The old pair did not resolve, and a re-key cannot invent the "
                "record it was pointing at")
        out.append(dict(row, **{REKEYED_FIELD: new}))
        n_rewritten += 1
    return out, n_rewritten


def _sources_block(old_sources: list[dict], table_path: str,
                   replay_path: Optional[str]) -> list[dict[str, Any]]:
    """Re-pin the sources: the raw inputs are unchanged; the generated pair is not."""
    table_name, replay_name = RECORDS_OUT, os.path.basename(replay_path or "")
    out: list[dict[str, Any]] = []
    for src in old_sources:
        name = str(src.get("name"))
        if name.startswith("stage02_source_records"):
            continue                       # superseded by the re-issued table
        if name.startswith("stage02_source_replay"):
            continue                       # superseded by the v2 completeness report
        out.append(dict(src))              # raw public sources: unchanged, still pinned

    sha = file_sha256(table_path)
    out.append({"name": table_name, "sha256": sha, "revision": f"sha256:{sha}"})
    if replay_path:
        rsha = file_sha256(replay_path)
        out.append({"name": replay_name, "sha256": rsha,
                    "revision": f"sha256:{rsha}"})
    return sorted(out, key=lambda s: s["name"])


def reissue(old_manifest: str, old_records: str, out_dir: str,
            replay_report: Optional[str] = None,
            old_registry: Optional[str] = None) -> dict[str, Any]:
    old_m = _load(old_manifest, "contributor manifest")
    old_t = _load(old_records, "source-record table")
    records, rows = old_t.get("records"), old_m.get("rows")
    if not isinstance(records, list) or not isinstance(rows, list):
        raise ReissueError("the old pair has no 'records' / 'rows'")

    os.makedirs(out_dir, exist_ok=True)
    new_records, remap = rekey_records(records)
    new_rows, n_rewritten = rekey_rows(rows, remap)

    # ---- the table, under the compiled rule ----
    table = {k: v for k, v in old_t.items()
             if k not in ("schema_version", "records", RULE_METADATA_KEY)}
    table["schema_version"] = RECORDS_SCHEMA
    table[RULE_METADATA_KEY] = RULE_METADATA        # written FROM the compiled rule
    table["record_count"] = len(new_records)
    table["records"] = new_records
    # WHAT was re-issued, as flags and counts. The reasoning (why a truncated id over a
    # payload that omitted the proof is not an identity) is stated once, in this
    # module's docstring and in record_id.py — never re-serialised into the artifact.
    table["reissued_from"] = {
        "source_record_table_sha256": file_sha256(old_records),
        "superseded_schema_version": str(old_t.get("schema_version")),
        "reissue_rule_id": REISSUE_RULE_ID,
        "ids_reminted_from_full_payload": True,
        "contributor_evidence_changed": False,
    }
    table_path = os.path.join(out_dir, RECORDS_OUT)
    _write(table_path, table)

    # ---- the manifest, citing the re-minted ids ----
    manifest = {k: v for k, v in old_m.items()
                if k not in ("schema_version", "rows", "sources",
                             "source_record_table", "source_replay_report",
                             "source_record_table_schema_version")}
    manifest["schema_version"] = MANIFEST_SCHEMA
    manifest["source_record_table"] = RECORDS_OUT
    manifest["source_record_table_schema_version"] = SOURCE_RECORD_TABLE_SCHEMA
    if replay_report:
        manifest["source_replay_report"] = os.path.basename(replay_report)
    manifest["sources"] = _sources_block(old_m.get("sources") or [], table_path,
                                         replay_report)
    manifest["rows"] = new_rows
    manifest["reissued_from"] = {
        "contributor_manifest_sha256": file_sha256(old_manifest),
        "superseded_schema_version": str(old_m.get("schema_version")),
        "reissue_rule_id": REISSUE_RULE_ID,
        "n_citations_rewritten": n_rewritten,
        "only_source_record_id_rewritten": True,
        "guide_identity_changed": False,
        "evidence_state_changed": False,
    }
    manifest_path = os.path.join(out_dir, MANIFEST_OUT)
    _write(manifest_path, manifest)

    # ---- the trusted registry: what a run may pin these by ----
    # The raw public sources keep the PATHS the old registry gave them (they are the
    # same bytes on the same disk); the re-issued generated artifacts point at
    # themselves. The registry is the trust anchor — the manifest may not vouch for its
    # own sources — so it is emitted alongside, never inferred at run time.
    old_paths = {}
    if old_registry:
        entries = _load(old_registry, "source registry").get("sources", {})
        old_paths = {str(k): str(v.get("path", "")) for k, v in entries.items()}

    registry_path = os.path.join(out_dir, REGISTRY_OUT)
    registry = {"sources": {
        s["name"]: {"path": old_paths.get(s["name"], s["name"]),
                    "sha256": s["sha256"], "revision": s["revision"]}
        for s in manifest["sources"]}}
    _write(registry_path, registry)

    return {
        "records": table_path,
        "manifest": manifest_path,
        "registry": registry_path,
        "n_records": len(new_records),
        "n_rows": len(new_rows),
        "n_citations_rewritten": n_rewritten,
        "records_sha256": file_sha256(table_path),
        "manifest_sha256": file_sha256(manifest_path),
        "replay_report_pinned": bool(replay_report),
        "status": "final" if replay_report else "draft_pending_replay_report",
    }


def _write(path: str, doc: dict[str, Any]) -> None:
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Re-issue the canonical contributor pair under the compiled "
                    "record-id rule (no grandfathering of srec- ids)")
    ap.add_argument("--old-manifest", required=True)
    ap.add_argument("--old-records", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--old-registry", default=None,
                    help="the old source registry, for the raw sources' on-disk paths")
    ap.add_argument("--replay-report", default=None,
                    help="the v2 completeness report. Omit on the first pass (the "
                         "report does not exist yet); supply it on the second to pin "
                         "the final manifest.")
    args = ap.parse_args(argv)

    try:
        result = reissue(args.old_manifest, args.old_records, args.out_dir,
                         args.replay_report, args.old_registry)
    except (ReissueError, record_id.RecordIdError) as exc:
        print(f"[FAIL] {exc}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
