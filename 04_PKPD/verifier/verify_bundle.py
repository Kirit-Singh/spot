"""Independently verify a MATERIALIZED evidence bundle against the bytes it claims to rest on.

The generator is `analysis/materialize.py`. This is not it, and imports nothing from `analysis/`:
a verifier that trusts the generator's idea of what it produced is not a check, it is a mirror.

What it re-derives, from the run root and the bundle alone:

  1. every row's `raw_response_sha256` is the sha256 of bytes that ARE in the cache;
  2. every source the bundle cites is one the acquisition manifest actually acquired;
  3. no lane holds evidence the acquisition never observed (the emitted rows outnumbering the
     observed responses is the signature of fabrication);
  4. every empty lane is STATED `not_evaluated` with a reason — silence is not absence;
  5. nothing claims a brain exposure, an NEBPI class or a safety verdict that no acquired byte
     supports;
  6. no `organ_system` beyond what a source backs.

Exit: 0 verified · 1 REFUSED.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

BUNDLE_SCHEMAS = ("spot.stage04_evidence_bundle.v1", "spot.stage04_evidence_bundle.v2")
MANIFEST_FILE = "acquisition_manifest.json"

# Lanes that a PUBLIC acquisition cannot populate. A row here did not come from an acquired byte,
# so it came from somewhere else -- and there is nowhere else it may legitimately come from.
UNACQUIRABLE_LANES = ("exposures", "transporters", "nebpi_observations", "fraction_unbound",
                      "potency_context_links")

# `organ_system` is source-backed or `unspecified`. There are no other legal values, because
# ORGAN_SYSTEM_SPECS is empty: no source in the ledger states an organ system in a coded field.
LEGAL_ORGAN_SYSTEMS = ("unspecified",)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check(out: list[dict[str, Any]], cid: str, ok: bool, detail: str) -> None:
    out.append({"check_id": cid, "status": "pass" if ok else "fail", "detail": detail})


def verify_bundle(bundle_path: str, run_root: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    with open(bundle_path, encoding="utf-8") as fh:
        bundle = json.load(fh)
    with open(os.path.join(run_root, MANIFEST_FILE), encoding="utf-8") as fh:
        manifest = json.load(fh)

    _check(checks, "bundle_schema_known", bundle.get("schema_id") in BUNDLE_SCHEMAS,
           f"schema_id={bundle.get('schema_id')!r}")

    records = {r["acquisition_record_id"]: r for r in manifest.get("records", [])}
    observed = {rid for rid, r in records.items() if r.get("evidence_state") == "observed"}

    # 1 + 2 -- every cited source is an acquired one, and its bytes re-derive.
    #
    # WHO FETCHED IT decides what can be checked, and pretending otherwise is how this whole class
    # of defect started. A response STAGE 4 fetched is cached under the run root and must re-hash
    # from those bytes. A response STAGE 3 fetched is NOT in Stage 4's cache -- Stage 4 carries the
    # hash, not the bytes -- so re-deriving it here is impossible, and a check that cannot run must
    # not report `pass`. What IS checkable is that the row agrees with the acquisition manifest,
    # and that the byte-level re-derivation is Stage 3's own verifier's job. Both are reported.
    cited = set()
    unbacked, missing_bytes, bad_hash, reused_mismatch = [], [], [], []
    reused_delegated = 0

    for lane, rows in bundle.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            # The evidence lanes NEST their provenance; the acquisition lane carries it flat.
            # Reading only the flat shape checked the acquisition rows and silently skipped every
            # property and safety row -- a verifier that walks past the rows it exists to check is
            # worse than none, because it reports `pass`.
            prov = row.get("provenance") or {}
            sid = prov.get("source_record_id") or row.get("source_record_id")
            if not sid:
                continue
            cited.add(sid)
            rec = records.get(sid)
            if rec is None:
                unbacked.append(f"{lane}:{sid}")
                continue

            want = (prov.get("raw_response_sha256")
                    or row.get("raw_response_sha256") or row.get("raw_sha256"))
            if want is None:
                continue

            if rec.get("origin") == "reused_from_stage3":
                # Stage 4 holds no bytes for this response. Check it against the manifest, and say
                # plainly that the bytes themselves are Stage 3's to re-derive.
                if want != rec.get("raw_sha256"):
                    reused_mismatch.append(f"{lane}:{sid}")
                else:
                    reused_delegated += 1
                continue

            relpath = rec.get("cache_relpath")
            if not relpath or not os.path.exists(os.path.join(run_root, relpath)):
                missing_bytes.append(f"{lane}:{sid}")
                continue
            with open(os.path.join(run_root, relpath), "rb") as fh:
                got = _sha256(fh.read())
            if got != want:
                bad_hash.append(f"{lane}:{sid} cache={got[:12]} row={str(want)[:12]}")

    _check(checks, "every_cited_source_was_acquired", not unbacked,
           f"rows citing a source the acquisition never made: {unbacked[:5]}")
    _check(checks, "every_FETCHED_byte_is_in_the_cache", not missing_bytes,
           f"Stage-4-fetched rows resting on bytes that are not in the run root: {missing_bytes[:5]}")
    _check(checks, "every_FETCHED_row_hash_matches_the_cached_bytes", not bad_hash,
           f"a fetched row's hash does not reproduce from the cache: {bad_hash[:5]}")
    _check(checks, "every_REUSED_row_agrees_with_the_acquisition_manifest", not reused_mismatch,
           f"a reused row's hash disagrees with the manifest record it came from: "
           f"{reused_mismatch[:5]}")
    _check(checks, "reused_bytes_are_delegated_to_stage3_not_silently_passed", True,
           f"{reused_delegated} reused row(s): Stage 4 holds the hash, not the bytes. Byte-level "
           "re-derivation belongs to Stage 3's own verifier and is NOT claimed here.")

    # 3 -- no lane may hold evidence the acquisition never observed.
    fabricated = sorted(sid for sid in cited if sid in records and sid not in observed)
    _check(checks, "no_evidence_from_an_unobserved_response", not fabricated,
           f"rows rest on responses whose evidence_state is not `observed`: {fabricated[:5]}")

    # 4 -- an empty lane must be STATED, never merely empty.
    stated = {s["lane"] for s in (bundle.get("config") or {}).get("not_evaluated", [])}
    silent = sorted(lane for lane, rows in bundle.items()
                    if isinstance(rows, list) and not rows and lane not in stated)
    _check(checks, "every_absent_lane_is_stated_not_evaluated", not silent,
           f"lanes are empty but say nothing about why: {silent}. Silence reads as 'nothing was "
           f"wrong'; it must read as 'nobody looked'.")

    # 5 -- the lanes no public acquisition can reach must be EMPTY.
    invented = {lane: len(bundle.get(lane) or []) for lane in UNACQUIRABLE_LANES
                if bundle.get(lane)}
    _check(checks, "no_brain_exposure_or_safety_inferred_from_missing_data", not invented,
           f"a lane no public source supplies is populated: {invented}. A brain concentration, "
           "an efflux ratio, an NEBPI observation or an fu that no acquired byte reports has "
           "been manufactured.")

    # 6 -- organ_system is source-backed or `unspecified`. NESTED, like the rest of the evidence
    # provenance: reading a flat `row["organ_system"]` would check nothing and report `pass`.
    inferred = sorted({
        str((r.get("organ_system_evidence") or {}).get("organ_system"))
        for r in (bundle.get("safety_records") or [])
        if (r.get("organ_system_evidence") or {}).get("organ_system")
        and (r["organ_system_evidence"]["organ_system"]) not in LEGAL_ORGAN_SYSTEMS
    })
    _check(checks, "no_inferred_organ_system", not inferred,
           f"organ_system values no source states: {inferred}")

    status = "pass" if all(c["status"] == "pass" for c in checks) else "fail"
    return {"schema_id": "spot.stage04_bundle_verification.v1",
            "status": status, "bundle": bundle_path, "checks": checks}


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="verify_bundle", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle")
    ap.add_argument("--run-root", required=True)
    args = ap.parse_args(argv)

    report = verify_bundle(args.bundle, args.run_root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
