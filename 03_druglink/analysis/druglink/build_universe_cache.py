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
import shutil
import sys
import tarfile
import time

from .hashing import contains_local_path, content_hash, file_sha256
from .universe_extract import build_from_sqlite, extraction_query_sha256
from .universe_manifest import build_universe_manifest
from .universe_verify import verify_from_disk

CHEMBL_PUBLISHER_SHA256 = \
    "33c203740555f96067710cdfc1c3c55d890660e5908ec5cbf5817492c290d281"
UNIPROT_PUBLISHER_MD5 = "7ef6a677d4db949397c3b352c466e499"


def _file_sha256(path):
    return file_sha256(path) if os.path.exists(path) else None


def _public_source_provenance(chembl_sha, chembl_size, uni_sha, uni_size,
                              chembl_release, uniprot_release, accessed, raw_dir):
    """Sanitized, content-bound public provenance (no machine path). The URL stays the
    real (mutable) ``current_release`` locator — UniProt has not yet archived 2026_02 to
    previous_releases — but the RELEASE.metalink + relnotes + checksum BYTES are hashed
    and bound, so the release=2026_02 association and the publisher checksum are proven
    without depending on the mutable path. Bound into the manifest + store_id."""
    chembl_checksums_sha = _file_sha256(os.path.join(raw_dir, "chembl_37.checksums.txt"))
    uni_metalink_sha = _file_sha256(
        os.path.join(raw_dir, "uniprot_2026_02.by_organism.RELEASE.metalink"))
    uni_relnotes_sha = _file_sha256(os.path.join(raw_dir, "uniprot_2026_02.relnotes.txt"))
    return [
        {"name": "chembl_sqlite", "basename": "chembl_37_sqlite.tar.gz",
         "url": ("https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/"
                 "chembl_37/chembl_37_sqlite.tar.gz"),
         "release": chembl_release, "doi": "10.6019/CHEMBL.database.37",
         "release_metadata_url": ("https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/"
                                  "releases/chembl_37/checksums.txt"),
         "release_metadata_sha256": chembl_checksums_sha,
         "release_metadata_packaged_as": "CHEMBL_checksums.txt",
         "size_bytes": chembl_size, "acquired_sha256": chembl_sha,
         "publisher_sha256": CHEMBL_PUBLISHER_SHA256,
         "last_modified": "Fri, 29 May 2026 06:35:28 GMT",
         "accessed_at_utc": accessed, "license": "CC BY-SA 3.0",
         "required_attribution": ("preserve ChEMBL IDs; display release; cite Mendez 2019 "
                                  "DOI 10.1093/nar/gky1075")},
        {"name": "uniprot_idmapping", "basename": "HUMAN_9606_idmapping.dat.gz",
         "url": ("https://ftp.uniprot.org/pub/databases/uniprot/current_release/"
                 "knowledgebase/idmapping/by_organism/HUMAN_9606_idmapping.dat.gz"),
         "release": uniprot_release, "release_date": "10-Jun-2026",
         "release_metadata_url": ("https://ftp.uniprot.org/pub/databases/uniprot/"
                                  "current_release/knowledgebase/idmapping/by_organism/"
                                  "RELEASE.metalink"),
         "release_metadata_sha256": uni_metalink_sha,
         "release_metadata_packaged_as": "UNIPROT_2026_02.by_organism.RELEASE.metalink",
         "relnotes_url": ("https://ftp.uniprot.org/pub/databases/uniprot/current_release/"
                          "relnotes.txt"),
         "relnotes_sha256": uni_relnotes_sha,
         "relnotes_packaged_as": "UNIPROT_2026_02.relnotes.txt",
         "metalink_attested_md5": UNIPROT_PUBLISHER_MD5,
         "locator_note": (
             "current_release path is mutable and UniProt has NOT archived 2026_02 to "
             "previous_releases yet (latest archived: 2026_01); the release=2026_02 "
             "association is proven by the bound relnotes bytes and the RELEASE.metalink "
             "which attests this file's MD5; bytes are pinned by publisher MD5 + acquired "
             "SHA-256. Add previous_releases/release-2026_02/ once UniProt archives it."),
         "size_bytes": uni_size, "acquired_sha256": uni_sha,
         "publisher_md5": UNIPROT_PUBLISHER_MD5,
         "last_modified": "Wed, 10 Jun 2026 20:00:00 GMT",
         "accessed_at_utc": accessed, "license": "CC BY 4.0"},
    ]


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
    accessed = "2026-07-13T06:29:16Z..2026-07-13T07:08:12Z"
    raw_dir = os.path.dirname(os.path.abspath(a.sqlite_tar))
    public_prov = _public_source_provenance(
        chembl_sha, os.path.getsize(a.sqlite_tar), uni_sha,
        os.path.getsize(a.idmapping), a.chembl_release, a.uniprot_release, accessed,
        raw_dir)
    public_prov_sha = content_hash(public_prov)

    manifest = build_universe_manifest(
        chembl_release=a.chembl_release, chembl_source_sha256=chembl_sha,
        uniprot_release=a.uniprot_release, uniprot_source_sha256=uni_sha,
        extraction_query_sha256=extraction_query_sha256(),
        universe_targets=universe, coverage=result["coverage"],
        store_rows_sha256=store_rows_sha,
        eligibility_evidence_sha256=result["eligibility_evidence_sha256"],
        public_source_provenance_sha256=public_prov_sha)

    # 4. write outputs: data-cache (store rows + eligibility) + committable compact reports
    with open(os.path.join(a.out_dir, "universe_store.rows.json"), "w") as fh:
        json.dump(rows, fh, sort_keys=True)
    with open(os.path.join(a.out_dir, "universe_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    with open(os.path.join(a.out_dir, "target_eligibility_evidence.json"), "w") as fh:
        json.dump(result["eligibility_evidence"], fh, sort_keys=True)
    with open(os.path.join(a.out_dir, "source_provenance.public.json"), "w") as fh:
        json.dump(public_prov, fh, indent=2, sort_keys=True)
    # mixed-license release gate + release-metadata provenance: package the permitted
    # notices and the release-metadata bytes (checksums, metalink, relnotes) alongside data
    for src, dst in [
            ("chembl_37_LICENSE", "CHEMBL_LICENSE"),
            ("chembl_37.REQUIRED.ATTRIBUTION", "CHEMBL_REQUIRED_ATTRIBUTION"),
            ("chembl_37.checksums.txt", "CHEMBL_checksums.txt"),
            ("uniprot_2026_02.by_organism.RELEASE.metalink",
             "UNIPROT_2026_02.by_organism.RELEASE.metalink"),
            ("uniprot_2026_02.relnotes.txt", "UNIPROT_2026_02.relnotes.txt")]:
        if os.path.exists(os.path.join(raw_dir, src)):
            shutil.copyfile(os.path.join(raw_dir, src), os.path.join(a.out_dir, dst))

    # DISK-level admission: verify against the ACTUAL written store rows + eligibility
    vr = verify_from_disk(store_dir=a.out_dir, manifest=manifest,
                          universe_targets=universe)
    with open(os.path.join(a.out_dir, "verify_report.json"), "w") as fh:
        json.dump(vr, fh, indent=2, sort_keys=True)

    # parse-validate every publishable JSON + assert no machine path leaks
    for name in ("universe_store.rows.json", "universe_manifest.json",
                 "target_eligibility_evidence.json", "source_provenance.public.json",
                 "verify_report.json"):
        with open(os.path.join(a.out_dir, name)) as fh:
            obj = json.load(fh)
        leak = contains_local_path(obj)
        if leak:
            print(f"FAIL: machine path in {name}: {leak[:2]}", file=sys.stderr)
            return 4

    # exact assertion denominators (n_general is the rankable set, NOT a total)
    def _all(r):
        return ((r.get("drugs") or []) + (r.get("variant_specific_assertions") or [])
                + (r.get("ambiguous_source_assertions") or []))
    n_general = sum(len(r.get("drugs") or []) for r in rows)
    n_variant = sum(len(r.get("variant_specific_assertions") or []) for r in rows)
    n_amb = sum(len(r.get("ambiguous_source_assertions") or []) for r in rows)
    uniq_mec = {x.get("source_row_id") for r in rows for x in _all(r)}
    amb_uniq = {x.get("source_row_id") for r in rows
                for x in (r.get("ambiguous_source_assertions") or [])}
    metrics.update({
        "finished_utc": _utc(time.time()),
        "wall_clock_s": round(time.time() - t0, 1),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "store_id": manifest["store_id"],
        "manifest_content_sha256": manifest["content_sha256"],
        "store_rows_sha256": store_rows_sha,
        "eligibility_evidence_sha256": result["eligibility_evidence_sha256"],
        "public_source_provenance_sha256": public_prov_sha,
        "coverage": result["coverage"],
        "eligibility_counts": result["eligibility_evidence"]["counts"],
        "n_drug_evidence_targets": result["coverage"]["n_drug_evidence"],
        "assertion_counts": {
            "n_general_drug_assertions": n_general,
            "n_variant_specific_assertions": n_variant,
            "n_ambiguous_assertion_occurrences": n_amb,
            "n_ambiguous_unique_source_rows": len(amb_uniq),
            "n_unique_source_mechanism_rows": len(uniq_mec),
            "n_total_stored_occurrences": n_general + n_variant + n_amb,
        },
        "verify_ok": vr["ok"], "verify_violations": vr["violations"],
    })
    with open(os.path.join(a.out_dir, "extraction_metrics.json"), "w") as fh:
        json.dump(metrics, fh, indent=2, sort_keys=True)
    print(json.dumps({k: metrics[k] for k in (
        "wall_clock_s", "store_id", "n_drug_evidence_targets", "assertion_counts",
        "verify_ok", "coverage")}, indent=2))
    return 0 if vr["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
