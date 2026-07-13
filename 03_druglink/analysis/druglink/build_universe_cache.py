"""CLI: build the run-independent universe drug-evidence cache from pinned bulk sources.

Offline, no crawl. Verifies the ChEMBL tarball SHA-256 against the publisher checksum,
extracts the SQLite, derives the typed perturbation-target universe from the pinned DE
object (obs.target_contrast categories: ENSG vs symbol-only), builds the store via the
tested modules, assembles the run-independent manifest, runs the generator-independent
verifier, and records measured metrics (time, peak RSS, disk, counts, hashes).

Raw bulk artifacts and the extracted SQLite stay under the data cache (out of Git); only
compact manifests/reports are meant to be committed.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import sqlite3
import sys
import tarfile
import time

from .hashing import content_hash, file_sha256
from .universe_extract import build_from_sqlite, extraction_query_sha256
from .universe_manifest import build_universe_manifest
from .universe_verify import verify

CHEMBL_PUBLISHER_SHA256 = \
    "33c203740555f96067710cdfc1c3c55d890660e5908ec5cbf5817492c290d281"


def _utc(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def derive_universe(h5ad_path: str) -> list[dict[str, str]]:
    """Typed universe from obs.target_contrast categories (h5py, no full load)."""
    import h5py
    with h5py.File(h5ad_path, "r") as f:
        node = f["obs/target_contrast"]
        cats = node["categories"] if isinstance(node, h5py.Group) else node
        vals = [c.decode() if isinstance(c, bytes) else str(c) for c in cats[:]]
    uni = [{"target_id": v,
            "target_id_namespace": "ensembl_gene" if v.startswith("ENSG") else "symbol"}
           for v in sorted(set(vals))]
    return uni


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite-tar", required=True)
    ap.add_argument("--sqlite-tar-sha256", default=CHEMBL_PUBLISHER_SHA256)
    ap.add_argument("--idmapping", required=True)
    ap.add_argument("--idmapping-sha256", required=True)
    ap.add_argument("--de-obs", required=True)
    ap.add_argument("--extract-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--chembl-release", default="CHEMBL_37")
    ap.add_argument("--uniprot-release", default="2026_02")
    a = ap.parse_args(argv)
    os.makedirs(a.out_dir, exist_ok=True)
    os.makedirs(a.extract_dir, exist_ok=True)
    t0 = time.time()
    metrics: dict = {"started_utc": _utc(t0), "steps": {}}

    # 1. verify the pinned tarball bytes against the publisher checksum (fail-closed)
    ts = time.time()
    chembl_sha = file_sha256(a.sqlite_tar)
    if chembl_sha != a.sqlite_tar_sha256:
        print(f"FAIL: ChEMBL tarball sha256 {chembl_sha} != publisher "
              f"{a.sqlite_tar_sha256}", file=sys.stderr)
        return 2
    uni_sha = file_sha256(a.idmapping)
    if uni_sha != a.idmapping_sha256:
        print(f"FAIL: idmapping sha256 {uni_sha} != {a.idmapping_sha256}",
              file=sys.stderr)
        return 2
    metrics["chembl_source_sha256"] = chembl_sha
    metrics["uniprot_source_sha256"] = uni_sha
    metrics["steps"]["verify_source_bytes_s"] = round(time.time() - ts, 1)

    # 2. extract the SQLite from the tarball (content-addressed extract dir)
    ts = time.time()
    with tarfile.open(a.sqlite_tar, "r:gz") as tf:
        members = [m for m in tf.getmembers() if m.name.endswith(".db")]
        if len(members) != 1:
            print(f"FAIL: expected exactly one .db in tarball, found "
                  f"{[m.name for m in members]}", file=sys.stderr)
            return 2
        tf.extract(members[0], a.extract_dir)
        sqlite_path = os.path.join(a.extract_dir, members[0].name)
    metrics["steps"]["extract_tar_s"] = round(time.time() - ts, 1)
    metrics["sqlite_bytes"] = os.path.getsize(sqlite_path)
    metrics["sqlite_name"] = os.path.basename(sqlite_path)

    # 3. derive the typed universe and build the store
    ts = time.time()
    universe = derive_universe(a.de_obs)
    result = build_from_sqlite(sqlite_path=sqlite_path, idmapping_path=a.idmapping,
                               universe_targets=universe)
    metrics["steps"]["build_store_s"] = round(time.time() - ts, 1)

    rows = result["rows"]
    store_rows_sha = content_hash(rows)
    manifest = build_universe_manifest(
        chembl_release=a.chembl_release, chembl_source_sha256=chembl_sha,
        uniprot_release=a.uniprot_release, uniprot_source_sha256=uni_sha,
        extraction_query_sha256=extraction_query_sha256(),
        universe_targets=universe, coverage=result["coverage"],
        store_rows_sha256=store_rows_sha,
        eligibility_evidence_sha256=result["eligibility_evidence_sha256"])

    vr = verify(store_rows=rows, manifest=manifest, universe_targets=universe)

    # 4. write outputs: full store + eligibility evidence (data-cache), compact
    # manifest+reports (committable). Every file is parse-validated below.
    with open(os.path.join(a.out_dir, "universe_store.rows.json"), "w") as fh:
        json.dump(rows, fh, sort_keys=True)
    with open(os.path.join(a.out_dir, "universe_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    with open(os.path.join(a.out_dir, "target_eligibility_evidence.json"), "w") as fh:
        json.dump(result["eligibility_evidence"], fh, sort_keys=True)
    with open(os.path.join(a.out_dir, "verify_report.json"), "w") as fh:
        json.dump(vr, fh, indent=2, sort_keys=True)

    # parse-validate every emitted JSON (never ship a malformed artifact)
    for name in ("universe_store.rows.json", "universe_manifest.json",
                 "target_eligibility_evidence.json", "verify_report.json"):
        with open(os.path.join(a.out_dir, name)) as fh:
            json.load(fh)

    n_drug = result["coverage"]["n_drug_evidence"]
    n_assertions = sum(len(r["drugs"]) for r in rows)
    metrics.update({
        "finished_utc": _utc(time.time()),
        "wall_clock_s": round(time.time() - t0, 1),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "store_id": manifest["store_id"],
        "manifest_content_sha256": manifest["content_sha256"],
        "store_rows_sha256": store_rows_sha,
        "eligibility_evidence_sha256": result["eligibility_evidence_sha256"],
        "coverage": result["coverage"],
        "eligibility_counts": result["eligibility_evidence"]["counts"],
        "n_drug_evidence_targets": n_drug,
        "n_total_drug_assertions": n_assertions,
        "verify_ok": vr["ok"], "verify_violations": vr["violations"],
    })
    with open(os.path.join(a.out_dir, "extraction_metrics.json"), "w") as fh:
        json.dump(metrics, fh, indent=2, sort_keys=True)
    print(json.dumps({k: metrics[k] for k in (
        "wall_clock_s", "peak_rss_mb", "sqlite_bytes", "store_id",
        "n_drug_evidence_targets", "n_total_drug_assertions", "verify_ok",
        "coverage")}, indent=2))
    return 0 if vr["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
