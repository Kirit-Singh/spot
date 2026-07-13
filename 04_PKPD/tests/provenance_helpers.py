"""Shared scaffolding for the provenance-binding and reduction-invariance regressions.

Kept in one place so both suites drive the SAME two verifiers the same way: the emit-time
verifier (which re-derives the bindings from the input records) and the standalone verifier
(which re-derives them from the emitted tables plus the source catalog). Neither reads the
other's verdict, and neither reads a "bound: true" flag from the generator.
"""

from __future__ import annotations

import json
import os

from analysis.canonical import content_sha256, sha256_file
from analysis.emit import emit
from analysis.evidence_records import PotencyRecord, Provenance
from analysis.method_config import METHOD_DIR, load_method_bundle
from analysis.pipeline import run_pipeline
from analysis.contract_version import ContractVersion
from analysis.tables import write_table
from analysis.verify import verify_output_dir
from verifier.checks import verify_release

METHOD = load_method_bundle()
BOGUS_SHA = "f" * 64


def emit_run(inputs, tmp_path, name="out"):
    """-> (out_dir, manifest, result)."""
    result = run_pipeline(inputs, METHOD)
    out_dir, manifest = emit(inputs, result, METHOD, os.path.join(str(tmp_path), name))
    return out_dir, manifest, result


def both_verifiers(out_dir, inputs=None):
    """-> (emit-time report, standalone report). Two reconstructions, two data sources."""
    standalone = verify_release(out_dir, METHOD_DIR)
    emit_time = verify_output_dir(out_dir, inputs, METHOD if inputs else None)
    return emit_time, standalone


def failed(report):
    return sorted(c["check_id"] for c in report["checks"] if c["status"] == "fail")


def prov(src, sha, transform="test extraction"):
    return Provenance(source_record_id=src, access_date="2026-07-11",
                      raw_response_sha256=sha, extraction_transform=transform)


def potency_out_of_context(inputs):
    """Move POT-001 to a foreign tumour context, so only a link can rescue the margin."""
    inputs.potencies = [
        PotencyRecord(**{**p.model_dump(), "biological_context": "OTHER_TUMOR"})
        if p.potency_id == "POT-001" else p
        for p in inputs.potencies
    ]
    return inputs


def reseal(out_dir, table, rows):
    """Rewrite one parquet and reseal EVERY hash the manifest declares over it.

    A tamper that leaves a stale hash behind is caught by arithmetic, which proves nothing
    about the binding checks. This one is resealed, so ONLY an independent reconstruction of
    the source bindings (or of the reduction) can catch it.
    """
    path = os.path.join(out_dir, f"{table}.parquet")
    desc = write_table(table, rows, path, ContractVersion.V1)

    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    for art in manifest["artifacts"]:
        if art["filename"] == f"{table}.parquet":
            art["content_sha256"] = desc["content_sha256"]
            art["file_sha256"] = desc["file_sha256"]
            art["rows"] = desc["rows"]
    manifest.pop("manifest_content_sha256")
    manifest["manifest_content_sha256"] = content_sha256(manifest)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    assert sha256_file(path) == desc["file_sha256"]
