"""Emit a Stage-3 v2 bundle for the independent verifier to judge. NON-PRODUCTION fixtures.

THE HONEST BUNDLE IS BUILT BY THE REAL PRODUCER
-----------------------------------------------
:func:`build` calls ``druglink.artifacts_v2.emit`` — the shipped writer, over the shipped
tables. It used to call a stand-in producer written beside the verifier, and that is exactly
the defect this lane keeps finding in other people's gates: a verifier that judges a MOCK of
the thing it verifies proves only that two of my own modules agree with each other. The
verifier still restates the contract and imports nothing from ``druglink``; what it now judges
is the artifact a real run would actually ship.

THE ATTACKS FORGE AND RESEAL
----------------------------
An attack cannot go through the real writer — it REFUSES a combined objective, a ranked
pathway edge, an origin swap. So a mutation hook hand-writes the bundle instead (parquet,
document, manifest) and RESEALS every hash, exactly as an attacker who remembers to recompute
them would. A content hash catches nothing from such an attacker; only a reconstruction from
the SOURCES does, which is what the verifier is for.
"""
from __future__ import annotations

import json
import os
import random
from typing import Any

from druglink import artifacts as v1
from druglink import artifacts_v2 as av2
from druglink import bundle_v2 as bv2
from druglink import candidates_v2 as cv2
from druglink import stage2_aggregate as sa
from druglink.hashing import content_hash, file_sha256, without
from v2_fixture import load_fixture_store

CREATED_AT = "2026-07-13T00:00:00+00:00"
DOC_IDENTITY_EXCLUDED = ("bundle_id", "canonical_content_sha256", "document_sha256",
                         "created_at")


def _admit(paths: dict[str, str]) -> sa.AdmittedAggregate:
    return sa.admit_aggregate(manifest_path=paths["manifest"],
                              report_path=paths["report"],
                              bundles_root=paths["bundles_root"],
                              stage1_release_path=paths["stage1_release"])


def tables_of(paths: dict[str, str], store_dir: str, *,
              artifact_class: str = "fixture") -> dict[str, list[dict[str, Any]]]:
    """The seven v2 tables, built by the REAL producer from the sealed inputs."""
    aggregate = _admit(paths)
    store = load_fixture_store(store_dir)
    tables = cv2.build(artifact_class=artifact_class, aggregate=aggregate, store=store)
    tables["provenance"] = bv2.provenance_rows(
        aggregate=aggregate, store=store,
        report=bv2.bind_report(paths["report"], aggregate),
        method=bv2.method_block(store))
    return tables


def build(paths: dict[str, str], store_dir: str, output_root: str, *,
          artifact_class: str = "fixture", permute: bool = False,
          mutate_tables=None, mutate_document=None) -> str:
    """Emit a complete v2 bundle. Honest by default; forged (and RESEALED) on a mutation."""
    aggregate = _admit(paths)
    store = load_fixture_store(store_dir)

    if not (mutate_tables or mutate_document):
        # THE REAL WRITER. Row order is not scientific content — it canonically re-sorts every
        # table — so a permuted build reproduces the identical bundle id, and `permute` needs
        # no special path here.
        return av2.emit(output_root=output_root, artifact_class=artifact_class,
                        aggregate=aggregate, store=store, report_path=paths["report"],
                        created_at=CREATED_AT)["bundle_dir"]

    tables = tables_of(paths, store_dir, artifact_class=artifact_class)
    if permute:
        rng = random.Random(20260713)
        for rows in tables.values():
            rng.shuffle(rows)
    if mutate_tables:
        mutate_tables(tables)

    report = bv2.bind_report(paths["report"], aggregate)
    doc: dict[str, Any] = dict(bv2.canonical_content(
        artifact_class=artifact_class,
        aggregate=bv2.aggregate_binding(aggregate, report),
        universe=bv2.store_binding(store, artifact_class=artifact_class),
        method=bv2.method_block(store),
        table_hashes=av2.table_content_hashes(tables),
        candidates=list(tables.get("candidates", []))))
    doc.update({
        "document_file": bv2.V2_DOC[artifact_class],
        "counts": {f"n_{n}": len(rows) for n, rows in sorted(tables.items())},
        "data_status": ("synthetic_fixture_only" if artifact_class == "fixture"
                        else "admitted_stage2_aggregate_and_universe_store"),
        "inference_status": "not_calibrated",
        "combined_objective_permitted": False,
        "headline_arm_permitted": False,
        "candidate_rank_permitted": False,
        "p_q_fdr_permitted": False,
    })
    if mutate_document:
        mutate_document(doc, tables)
    return _seal(output_root, artifact_class, doc, tables)


def _seal(output_root: str, artifact_class: str, doc: dict[str, Any],
          tables: dict[str, list[dict[str, Any]]]) -> str:
    """Write the forged bundle and RESEAL every hash, as an attacker who reseals would."""
    content_sha = content_hash(without(doc, DOC_IDENTITY_EXCLUDED))
    doc["bundle_id"] = ("fx_" if artifact_class == "fixture" else "s3_") + content_sha[:16]
    doc["canonical_content_sha256"] = content_sha
    doc["document_sha256"] = content_hash(without(doc, ("document_sha256",)))

    target = v1.bundle_dir(output_root, artifact_class, doc["bundle_id"])
    os.makedirs(target, exist_ok=True)

    files = []
    for name in av2.SCIENTIFIC_TABLES:
        rows = tables.get(name, [])
        fname = f"{name}.parquet"
        av2._frame(name, rows).to_parquet(os.path.join(target, fname), index=False)
        files.append({"file": fname, "n_rows": len(rows),
                      "content_sha256": av2.table_content_hash(name, rows),
                      "file_sha256": file_sha256(os.path.join(target, fname))})

    doc_name = str(doc.get("document_file") or bv2.V2_DOC[artifact_class])
    _write_json(os.path.join(target, doc_name), doc)
    files.append({"file": doc_name, "n_rows": len(doc.get("candidates") or []),
                  "content_sha256": content_sha,
                  "file_sha256": file_sha256(os.path.join(target, doc_name))})

    manifest = {
        "schema_version": bv2.V2_MANIFEST_SCHEMA, "artifact_class": artifact_class,
        "bundle_id": doc["bundle_id"], "document_file": doc_name,
        "document_sha256": doc["document_sha256"],
        "canonical_content_sha256": content_sha,
        "stage2_aggregate": doc["stage2_aggregate"],
        "universe_store": doc["universe_store"], "method": doc["method"],
        "origin_types": doc["origin_types"], "data_status": doc["data_status"],
        "inference_status": doc["inference_status"],
        "combined_objective_permitted": False, "headline_arm_permitted": False,
        "p_q_fdr_permitted": False, "deferred_lanes": doc["deferred_lanes"],
        "table_hashes": doc["table_hashes"], "counts": doc["counts"],
        "files": sorted(files, key=lambda f: f["file"]), "created_at": CREATED_AT,
    }
    manifest["manifest_sha256"] = content_hash(
        without(manifest, ("manifest_sha256", "created_at")))
    _write_json(os.path.join(target, "manifest.json"), manifest)
    return target


def _write_json(path: str, doc: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True, ensure_ascii=True)
        fh.write("\n")


def reseal_file_hashes(bundle: str) -> str:
    """Re-hash the FILES after an attacker edited a parquet in place.

    A content hash catches nothing from an attacker who remembers to recompute it — so the
    attacks reseal, and the verifier has to catch them on the SOURCES instead.
    """
    path = os.path.join(bundle, "manifest.json")
    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    for entry in manifest["files"]:
        entry["file_sha256"] = file_sha256(os.path.join(bundle, entry["file"]))
    manifest["manifest_sha256"] = content_hash(
        without(manifest, ("manifest_sha256", "created_at")))
    _write_json(path, manifest)
    return bundle
