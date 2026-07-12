"""Sources come from a trusted acquisition manifest -- never from self-labelling.

A cached response is a pair: raw bytes on disk, plus a manifest entry that the
network-permitted acquisition step (:mod:`druglink.acquire_public`) wrote -- URL,
release, endpoint, query, license, HTTP access record, pagination, byte hash.
Nothing else may declare a response "public": a payload envelope that calls itself
``public_cached_response`` is exactly what an attacker (or a careless fixture)
would write.

This module is the offline LOADER used by the Stage-3 run. It re-checks what it
can before handing a single byte to an adapter:

  * the raw bytes hash to what the manifest declared, and are as long as declared;
  * an ``acquired_public`` entry carries an access record, a license, a release and
    its place in a pagination chain;
  * ``acquired_public`` bytes are not FIXTURE bytes wearing a public label -- a
    synthetic payload is stamped, and a real response states its own totals and
    pagination, so a relabelled fixture fails both ways;
  * when a verified Direct run is supplied, the cache's FROZEN TARGET QUEUE was
    derived from THAT run. A cache built against a different Direct run is refused
    outright: its bytes answer a different question.

``source_record_id`` hashes the whole LOCATOR, so two entries with byte-identical
payloads fetched from different endpoints or queries cannot collide.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import artifact_class as ac
from .adapters import ADAPTERS, adapter_for
from .hashing import content_hash, file_sha256, sha256_hex
from .schemas import ACQUISITION, SchemaError, validate

MANIFEST_FILE = "acquisition_manifest.json"
QUEUE_FILE = "target_queue.json"

# A synthetic payload MUST stamp itself. Public bytes that carry a fixture stamp
# are a relabel, not data.
FIXTURE_MARKERS = ("_spot_fixture", "spot_fixture_namespace", "synthetic_fixture")

# The array a real response from each endpoint carries. A body that cannot state
# its own records cannot be a page of that endpoint.
RECORDS_KEY = {
    "uniprot_search": "results",
    "chembl_target": "targets",
    "chembl_mechanism": "mechanisms",
    "chembl_molecule": "molecules",
    "chembl_activity": "activities",
}

DEFERRED_SOURCES = ("open_targets", "pubchem", "rxnorm", "lincs", "depmap")


class AcquisitionError(ValueError):
    """The acquisition manifest is malformed, mislabelled, or its bytes disagree."""


def _locator(entry: dict[str, Any], adapter, artifact_class: str) -> dict[str, Any]:
    return {
        "artifact_class": artifact_class,
        "source": entry["source"],
        "adapter": adapter.name,
        "adapter_version": adapter.version,
        "adapter_status": adapter.status,
        "source_release": entry["source_release"],
        "source_endpoint": entry["source_endpoint"],
        "retrieval_url": entry.get("retrieval_url"),
        "query_canonical": content_hash(entry["query"]),
        "license": entry["license"],
        "acquisition_status": entry["acquisition_status"],
        "raw_sha256": entry.get("raw_sha256"),
    }


def _refuse_fixture_bytes(i: int, entry: dict[str, Any], data: bytes) -> None:
    """An acquired_public entry whose bytes are a synthetic fixture is a relabel."""
    text = data.decode("utf-8", errors="replace")
    for marker in FIXTURE_MARKERS:
        if marker in text:
            raise AcquisitionError(
                f"entry[{i}]: bytes labelled acquired_public carry the fixture "
                f"marker {marker!r} ({entry['source']} {entry['source_endpoint']}); "
                "a fixture cannot be relabelled as a public response")

    key = RECORDS_KEY.get(entry["adapter"])
    if key is None:
        return
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AcquisitionError(f"entry[{i}]: acquired_public bytes are not JSON: {exc}")
    if not isinstance(body, dict) or not isinstance(body.get(key), list):
        raise AcquisitionError(
            f"entry[{i}]: acquired_public {entry['adapter']} bytes carry no {key!r} "
            "array; this is not a response from that endpoint")

    pagination = entry.get("pagination") or {}
    observed = len(body[key])
    if pagination and pagination.get("observed_count") != observed:
        raise AcquisitionError(
            f"entry[{i}]: declared observed_count="
            f"{pagination.get('observed_count')} but the bytes carry {observed} "
            f"{key}")
    if entry["source"] == "chembl" and not isinstance(body.get("page_meta"), dict):
        raise AcquisitionError(
            f"entry[{i}]: a real ChEMBL response states its own page_meta; these "
            "bytes do not")


def _check_public_record(i: int, entry: dict[str, Any]) -> None:
    if not entry.get("access_record"):
        raise AcquisitionError(
            f"entry[{i}]: acquired_public requires an access_record "
            "(retrieval time + HTTP status)")
    status = (entry["access_record"] or {}).get("http_status")
    if status != 200:
        raise AcquisitionError(
            f"entry[{i}]: acquired_public with HTTP status {status!r}; only a 200 "
            "response is a response")
    if not entry.get("pagination"):
        raise AcquisitionError(
            f"entry[{i}]: acquired_public requires a pagination record (its place "
            "in the chain); a page that cannot state its own position may be a "
            "silently truncated result")
    if not (entry.get("license") or "").strip():
        raise AcquisitionError(f"entry[{i}]: acquired_public requires a license")
    if not (entry.get("attribution") or "").strip():
        raise AcquisitionError(
            f"entry[{i}]: acquired_public requires an attribution string "
            f"({entry['license']} is an attribution license)")


def load_queue(cache_root: str) -> Optional[dict[str, Any]]:
    path = os.path.join(cache_root, QUEUE_FILE)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _check_frozen_queue(cache_root: str, manifest: dict[str, Any], direct) -> None:
    """The cache must answer THIS Direct run's question, not another one's."""
    binding = manifest.get("acquisition_binding") or {}
    queue = load_queue(cache_root)
    if not binding or queue is None:
        raise AcquisitionError(
            "this cache carries no frozen target queue, so it cannot be shown to "
            "have been derived from the admitted Direct run")
    if queue.get("acquisition_id") != manifest.get("acquisition_id"):
        raise AcquisitionError(
            "the frozen target queue and the manifest disagree about the "
            "acquisition_id")
    if content_hash(queue["target_queue"]) != binding.get("target_queue_sha256"):
        raise AcquisitionError(
            "the frozen target queue does not hash to the manifest's declared "
            "target_queue_sha256")
    if binding.get("direct_run_id") != direct.run_id:
        raise AcquisitionError(
            f"this cache was frozen against Direct run "
            f"{binding.get('direct_run_id')!r}, but the run admitted "
            f"{direct.run_id!r}; its bytes answer a different question")
    if content_hash(binding.get("direct_binding") or {}) != direct.binding_sha256:
        raise AcquisitionError(
            "the cache's Direct binding does not match the Direct run this Stage-3 "
            "run independently hashed")


def acquisition_ref(manifest: dict[str, Any], counts: dict[str, int],
                    artifact_class: str,
                    verification: dict[str, Any] | None = None) -> dict[str, Any]:
    """The canonical block the Stage-3 bundle ID binds to. No timestamps, no paths."""
    binding = manifest.get("acquisition_binding") or {}
    policy = binding.get("policy") or {}
    releases = manifest.get("releases") or {}
    mcounts = manifest.get("counts") or {}
    return {
        "acquisition_id": manifest.get("acquisition_id"),
        "acquisition_manifest_sha256": manifest.get("content_sha256"),
        "acquisition_policy_version": policy.get("acquisition_policy_version"),
        "artifact_class": artifact_class,
        "direct_run_id": binding.get("direct_run_id"),
        "direct_binding_sha256": binding.get("direct_binding_sha256"),
        "top_per_arm": policy.get("top_per_arm"),
        "frozen_target_queue_sha256": binding.get("target_queue_sha256"),
        "n_query_targets": mcounts.get("n_query_targets"),
        "n_query_genes": mcounts.get("n_query_genes"),
        "per_arm_target_counts": dict(sorted((binding.get("per_arm_counts")
                                              or {}).items())),
        "sources": sorted(policy.get("sources") or []),
        "source_releases": {k: v.get("source_release")
                            for k, v in sorted(releases.items())},
        "licenses": {k: v.get("license") for k, v in sorted(releases.items())},
        "n_pages": mcounts.get("n_pages"),
        "n_request_groups": mcounts.get("n_request_groups"),
        "n_acquired_public": counts["n_acquired_public"],
        "n_not_acquired": counts["n_not_acquired"],
        "n_synthetic_fixture": counts["n_synthetic_fixture"],
        "deferred_sources": {s: "not_evaluated" for s in DEFERRED_SOURCES},
        "chembl_activity_potency_state": (
            "acquired" if policy.get("activity_acquired") else "not_evaluated"),
        "adaptive_expansion_permitted": bool(policy.get(
            "adaptive_expansion_permitted", False)),
        # Proof that the raw bytes were independently re-derived BEFORE this bundle
        # was built. The Stage-3 verifier re-checks that this gate is present and
        # passing, so a bundle can never stand on unverified evidence.
        "verification": dict(sorted((verification or {}).items())),
    }


def verification_gate(cache_root: str, artifact_class: str, *,
                      direct: Any = None) -> dict[str, Any]:
    """Run the OFFLINE acquisition verifier and REFUSE unless it all-passes.

    Generation may not stand on an unverified cache. The verdict is returned so it can
    be bound into the Stage-3 bundle: a bundle therefore carries proof that its
    evidence was independently re-derived from the raw bytes BEFORE it was built, and
    the Stage-3 verifier re-checks that this gate is present and passing.
    """
    from . import verify_acquisition          # local: verify_acquisition imports us

    rep = verify_acquisition.verify(cache_root, run_dir=None, inputs_root=None,
                                    artifact_class=artifact_class, direct=direct)
    verdict = {
        "verifier": "druglink.verify_acquisition",
        "n_checks": len(rep.rows),
        "n_failed": len(rep.failed),
        "all_pass": not rep.failed,
        "report_sha256": sha256_hex(rep.render()),
    }
    if rep.failed:
        failed = "; ".join(name for name, _ok, _detail in rep.failed[:5])
        raise AcquisitionError(
            f"the acquisition cache did NOT pass independent verification "
            f"({len(rep.failed)}/{len(rep.rows)} checks failed): {failed}. "
            "Stage 3 refuses to build a bundle on unverified evidence.")
    return verdict


def load_manifest(cache_root: str, artifact_class: str, *, direct: Any = None,
                  verify: bool = True) -> dict[str, Any]:
    """Return {manifest, source_records, raw, dispositions, counts, acquisition_ref}.

    ``direct`` is an admitted :class:`druglink.direct_run.DirectRun`. When it is
    given, the cache must prove it was frozen against that exact run.

    ``verify=True`` (the default, and the only value any real run uses) runs the
    offline acquisition verifier first and refuses an unverified cache. It is a
    parameter solely so the acquisition verifier's OWN tests can load a deliberately
    corrupted cache in order to prove that it is caught.
    """
    ac.require(artifact_class)
    path = os.path.join(cache_root, MANIFEST_FILE)
    if not os.path.exists(path):
        raise AcquisitionError(f"no acquisition manifest in cache root ({MANIFEST_FILE})")
    with open(path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    gate = (verification_gate(cache_root, artifact_class, direct=direct) if verify
            else {"verifier": "druglink.verify_acquisition", "all_pass": False,
                  "n_checks": 0, "n_failed": 0, "report_sha256": None,
                  "skipped": "verification was explicitly skipped; this cache may "
                             "not be used to build a bundle"})

    try:
        validate(manifest, ACQUISITION, context="acquisition_manifest")
    except SchemaError as exc:
        raise AcquisitionError(str(exc)) from exc

    if manifest["artifact_class"] != artifact_class:
        raise AcquisitionError(
            f"{artifact_class} run refuses an acquisition manifest declaring "
            f"artifact_class={manifest['artifact_class']!r}")

    source_records: list[dict[str, Any]] = []
    raw: dict[str, Any] = {}
    dispositions: list[dict[str, Any]] = []
    counts = {"n_acquired_public": 0, "n_not_acquired": 0, "n_synthetic_fixture": 0}
    seen: set[str] = set()

    for i, entry in enumerate(manifest["entries"]):
        status = entry["acquisition_status"]
        adapter = adapter_for(entry["adapter"])
        if adapter is None:
            raise AcquisitionError(f"entry[{i}]: unknown adapter {entry['adapter']!r}")
        if adapter.source != entry["source"]:
            raise AcquisitionError(
                f"entry[{i}]: adapter {adapter.name} does not serve source "
                f"{entry['source']!r}")

        if status not in ac.ALLOWED_ACQUISITION[artifact_class] and status != "not_acquired":
            raise AcquisitionError(
                f"{artifact_class} refuses a source with acquisition_status={status!r} "
                f"({entry['source']} {entry['source_endpoint']})")
        if status == "synthetic_fixture" and artifact_class != ac.FIXTURE:
            raise AcquisitionError(
                f"{artifact_class} refuses a synthetic fixture source")
        if status == "acquired_public":
            _check_public_record(i, entry)
        if status == "synthetic_fixture" and entry.get("access_record"):
            raise AcquisitionError(
                f"entry[{i}]: a synthetic fixture must not carry an access record")

        rec = {
            "source_record_id": "",
            "artifact_class": artifact_class,
            "source": entry["source"],
            "adapter": adapter.name,
            "adapter_version": adapter.version,
            "adapter_status": adapter.status,
            "source_release": entry["source_release"],
            "source_endpoint": entry["source_endpoint"],
            "retrieval_url": entry.get("retrieval_url"),
            "query_canonical": content_hash(entry["query"]),
            "license": entry["license"],
            "attribution": entry.get("attribution"),
            "acquisition_status": status,
            "raw_sha256": entry.get("raw_sha256"),
            "raw_bytes": entry.get("raw_bytes"),
            "raw_media_type": entry.get("raw_media_type"),
            "access_record_sha256": (content_hash(entry["access_record"])
                                     if entry.get("access_record") else None),
            "parse_status": None,
            "parse_detail": None,
        }

        if status == "not_acquired":
            counts["n_not_acquired"] += 1
            rec["parse_status"] = "not_acquired"
            rec["parse_detail"] = entry.get("not_acquired_reason") or "not acquired"
        else:
            counts["n_acquired_public" if status == "acquired_public"
                   else "n_synthetic_fixture"] += 1
            raw_file = entry.get("raw_file")
            if not raw_file or not entry.get("raw_sha256"):
                raise AcquisitionError(
                    f"entry[{i}]: {status} requires raw_file + raw_sha256")
            if os.path.isabs(raw_file) or ".." in raw_file.split("/"):
                raise AcquisitionError(
                    f"entry[{i}]: raw_file must be a relative in-cache path, not "
                    f"{raw_file!r}")
            raw_path = os.path.join(cache_root, raw_file)
            if not os.path.exists(raw_path):
                raise AcquisitionError(f"entry[{i}]: raw file missing: {raw_file}")
            actual = file_sha256(raw_path)
            if actual != entry["raw_sha256"]:
                raise AcquisitionError(
                    f"entry[{i}]: raw bytes do not match the manifest hash for "
                    f"{raw_file}: declared {entry['raw_sha256']}, actual {actual}")
            with open(raw_path, "rb") as fh:
                data = fh.read()
            if entry.get("raw_bytes") is not None and len(data) != entry["raw_bytes"]:
                raise AcquisitionError(f"entry[{i}]: raw_bytes length mismatch")
            if status == "acquired_public":
                _refuse_fixture_bytes(i, entry, data)

        rec["source_record_id"] = sha256_hex(
            content_hash(_locator(entry, adapter, artifact_class)))
        if rec["source_record_id"] in seen:
            raise AcquisitionError(
                f"entry[{i}]: duplicate source locator (same source, adapter, "
                "release, endpoint, url, query and bytes)")
        seen.add(rec["source_record_id"])

        if status != "not_acquired":
            raw[rec["source_record_id"]] = {"bytes": data, "entry": entry,
                                            "adapter": adapter}
        else:
            dispositions.append({
                "subject_kind": "source_record",
                "subject_id": rec["source_record_id"],
                "state": "not_acquired",
                "reason": "source_not_acquired",
                "detail": (f"{entry['source']} {entry['source_endpoint']}: "
                           f"{entry.get('not_acquired_reason')}"),
                "source_record_id": rec["source_record_id"],
            })
        source_records.append(rec)

    if direct is not None:
        _check_frozen_queue(cache_root, manifest, direct)

    return {"manifest": manifest, "source_records": source_records, "raw": raw,
            "dispositions": dispositions, "counts": counts,
            "acquisition_ref": acquisition_ref(manifest, counts, artifact_class,
                                               verification=gate)}


def adapters_manifest() -> dict[str, Any]:
    """The adapter registry, hashed into every run ID."""
    return {name: {"version": a.version, "status": a.status, "source": a.source,
                   "endpoints": list(a.endpoints)}
            for name, a in sorted(ADAPTERS.items())}
