"""THE STAGE-3 BRIDGE: a SEPARATE aggregate root, built AFTER the lanes are admitted.

WHY IT IS NOT WRITTEN INTO THE BUNDLES
--------------------------------------
An earlier version wrote ``stage3_rows.json`` INTO each native bundle directory. That is
wrong, and quietly destructive: adding a file to a bundle changes that bundle's file topology
AFTER its producer emitted it and AFTER its independent verifier admitted it — invalidating
exactly the bindings the admission rests on. W10's Direct report, the temporal admission and
the pathway admission all bind the tree they were shown.

The typed rows are a CONSUMER of admitted bytes, not part of them. So they live BESIDE the
lanes, in their own content-addressed root, BOUND BY HASH to: the native bundles they were
rebuilt from, the lane admissions that cleared those bundles, the Stage-1 release, and each
lane's exact identity/assay source.

The producer of this bridge admits nothing. ``verify_stage3_bridge`` reopens the admitted
native bytes and REBUILDS every row and context — because a self-hash proves only that a
document agrees with itself, and a forgery can be made to agree with itself.

THE FOUR ARTIFACTS STAGE 3 CONSUMES (W16's `--v2` path; all four REQUIRED)
-------------------------------------------------------------------------
    python -m direct.stage3_bridge \
      --bundles-root OUT --bridge-root OUT --verify

    OUT/stage2_run_manifest.json            the aggregate       (immutable; never re-sealed)
    OUT/stage2_aggregate_verification.json  its INDEPENDENT report
    OUT/stage3_bridge.json                  --stage2-bridge
    OUT/stage3_bridge_verification.json     --stage2-bridge-report
    OUT/stage2_stage3_receipt.json          --stage2-bridge-receipt   <- THE JOIN
    OUT/stage3_receipt_verification.json    the receipt's OWN report

THE RECEIPT IS NOT OPTIONAL. It is the only artifact that ties an ADMITTED aggregate to this
bridge, and it is the reason the aggregate never has to be re-sealed. Without it Stage 3 is
trusting a bridge that merely *claims* which aggregate it was built over. So it is verified
like any other referent — reopened, re-derived, and refused if it names a different bridge, a
different aggregate, or a report that never admitted anything.

Its report is written SEPARATELY, and must be: the receipt BINDS the bridge report, so
re-writing that report while checking the receipt would invalidate the very hash the receipt
was built on. The chain only grows forward.
"""
from __future__ import annotations

from typing import Any

from . import stage3_rows as R
from .stage3_rows import DIRECT_IDENTITY_REQUIREMENT, ROW_RULE_ID, STAGE3_MATCHING_POLICY
from .target_identity import TARGET_IDENTITY_FILE

BRIDGE_FILE = "stage3_bridge.json"
BRIDGE_SCHEMA = "spot.stage02_stage3_bridge.v1"


def build_bridge(*, bindings: dict[str, Any], rows: list, contexts: list) -> dict[str, Any]:
    """The typed Stage-3 handoff, BOUND to the admitted native bytes it was rebuilt from."""
    import hashlib
    import json

    doc: dict[str, Any] = {
        "schema_version": BRIDGE_SCHEMA,
        "rule_id": ROW_RULE_ID,
        "matching_policy": STAGE3_MATCHING_POLICY,
        # WHAT IT WAS BUILT FROM: the native bundles + their file hashes, the lane admissions,
        # the Stage-1 hashes, and the exact identity/assay source of each lane.
        "bindings": bindings,
        "target_rows": list(rows),
        "n_target_rows": len(rows),
        "pathway_contexts": list(contexts),
        "n_pathway_contexts": len(contexts),
        "direct_identity_requirement": DIRECT_IDENTITY_REQUIREMENT,
        "verdict": "pending_independent_verification",
        "admitted": False,
        "self_admitted": False,
    }
    doc["bridge_sha256"] = hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode()).hexdigest()
    return doc


# --------------------------------------------------------------------------- #
# THE RECEIPT. The aggregate stays IMMUTABLE.
#
# The bridge is DOWNSTREAM of aggregate admission, so it cannot live inside the aggregate
# manifest: the manifest's hash was fixed when it was admitted, and writing a bridge reference
# into it afterwards would mean re-sealing an artifact an independent verifier had already
# cleared. Every admission upstream binds the tree it was shown. So NOTHING upstream is ever
# rewritten — the chain only ever grows forward:
#
#   bundles -> lane admissions -> aggregate manifest -> aggregate report
#           -> bridge -> bridge report -> RECEIPT
#
# The RECEIPT is the join. It binds the aggregate (raw + canonical) and the bridge (raw +
# canonical), so a reader can walk from an admitted release to its Stage-3 handoff without
# either artifact having been touched after it was admitted.
# --------------------------------------------------------------------------- #
RECEIPT_FILE = "stage2_stage3_receipt.json"
RECEIPT_SCHEMA = "spot.stage02_stage3_receipt.v1"
BRIDGE_REPORT_FILE = "stage3_bridge_verification.json"
RECEIPT_REPORT_FILE = "stage3_receipt_verification.json"

AGGREGATE_MANIFEST = "stage2_run_manifest.json"
AGGREGATE_REPORT = "stage2_aggregate_verification.json"


class BridgeError(ValueError):
    """The bridge cannot be built. Refuse; never repair."""


def jsonable(value):
    """pandas NaN/NA -> JSON null. A NaN is not a number, and it is not equal to itself.

    A non-evaluable Direct row carries a NULL value and a NULL rank — the row that says "this
    arm could not score this target", which a consumer must never mistake for a zero. Round-
    tripped through parquet those nulls come back as float('nan'), and then `json.dump` writes
    the literal `NaN` (which is not JSON) and `NaN != NaN` makes the row unequal to its own
    rebuild. So they are normalized here, once, at the seam where parquet becomes JSON.
    """
    import math
    if value is None:
        return None
    if hasattr(value, "item"):                  # numpy scalar -> python scalar
        try:
            value = value.item()
        except (AttributeError, ValueError):
            return value
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if math.isinf(value):
            raise BridgeError(f"an infinite value ({value!r}) is not a measurement")
    return value


def _dump(doc, path):
    """JSON with NO NaN. `allow_nan=False` REFUSES rather than writing invalid JSON."""
    import json
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True, allow_nan=False)


def _raw(path):
    import hashlib
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _canon(obj):
    import hashlib
    import json
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def _bind_file(path):
    import json
    with open(path) as fh:
        doc = json.load(fh)
    return {"path": path, "raw_sha256": _raw(path), "canonical_sha256": _canon(doc)}, doc


def preconditions(bundles_root: str) -> tuple:
    """THE GATE. The bridge runs ONLY over a release that is already, independently, ADMITTED.

    Not "mostly admitted", and not "admitted except pathway". A Stage-3 handoff for a release
    nobody cleared is worse than no handoff at all: it looks exactly like one that was.
    """
    import os

    mpath = os.path.join(bundles_root, AGGREGATE_MANIFEST)
    rpath = os.path.join(bundles_root, AGGREGATE_REPORT)
    for path, what in ((mpath, "aggregate manifest"), (rpath, "aggregate verifier report")):
        if not os.path.exists(path):
            raise BridgeError(
                f"no {what} at {path}. The bridge is DOWNSTREAM of aggregate admission — run "
                "`python -m direct.run_release ... --verify` first")

    manifest_binding, manifest = _bind_file(mpath)
    report_binding, report = _bind_file(rpath)

    if report.get("verdict") != "admit":
        raise BridgeError(
            f"the aggregate verifier's verdict is {report.get('verdict')!r}, not 'admit' "
            f"({report.get('n_failed')} failed gate(s)). The bridge does not run over a "
            "release that was not cleared")

    # ...and every lane's NATIVE admission, from the manifest the verifier admitted.
    lanes = manifest.get("lane_admissions") or {}
    refused = [lane for lane, a in lanes.items()
               if a.get("aggregate_disposition") != "admitted"]
    if refused or not lanes:
        raise BridgeError(
            f"lane(s) {refused or 'none at all'} are not independently admitted in the "
            "aggregate manifest; every lane admits before the bridge builds")

    return {"manifest": manifest_binding, "report": report_binding}, manifest, report


def receipt(*, aggregate: dict, bridge_binding: dict, report_binding: dict) -> dict[str, Any]:
    """The POST-AGGREGATE RECEIPT: it joins an immutable aggregate to its Stage-3 handoff."""
    doc = {
        "schema_version": RECEIPT_SCHEMA,
        "aggregate_is_immutable": True,
        "aggregate_was_resealed": False,
        "why": ("the aggregate manifest and its independent report were hashed when they were "
                "admitted; the bridge references them and NEITHER is rewritten. The chain only "
                "grows forward"),
        "aggregate": aggregate,
        "bridge": bridge_binding,
        "bridge_report": report_binding,
    }
    doc["receipt_sha256"] = _canon(doc)
    return doc


# --------------------------------------------------------------------------- #
# THE ASSEMBLER. Reads the ADMITTED native bytes; writes ONLY into the bridge root.
# --------------------------------------------------------------------------- #
def _identity_of(bundle_dir: str) -> dict:
    """Direct's identity, through the SHARED LOADER — the producer's bytes, in place."""
    from .target_identity import load
    doc = load(bundle_dir)["doc"]
    return {str(r["target_id"]): r for r in doc["records"]}


def _direct_rows(bundle_dir: str, context: dict) -> list:
    """Direct's rows are `arms.parquet` — there is no rankings/ directory on this lane."""
    import os

    import pandas as pd

    path = os.path.join(bundle_dir, "arms.parquet")
    if not os.path.exists(path):
        raise BridgeError(f"{bundle_dir}: no arms.parquet — Direct's rows live there")
    identity = _identity_of(bundle_dir)

    out = []
    for rec in pd.read_parquet(path).to_dict("records"):
        rec = {k: jsonable(v) for k, v in rec.items()}     # NaN -> null, at the parquet seam
        ident = identity.get(str(rec.get("target_id")))
        if ident is None:
            raise BridgeError(
                f"{bundle_dir}: target {rec.get('target_id')!r} is scored but has no "
                f"{TARGET_IDENTITY_FILE} row. It would drop out of the Stage-3 join and "
                "disappear without a trace")
        out.append(R.build_row(
            lane="direct",
            record={"target_id": rec["target_id"], "arm_value": rec["value"],
                    "evaluable": rec["evaluable"], "rank": rec["rank"]},
            identity=ident, arm_key=str(rec["arm_key"]),
            program_id=str(rec["program_id"]),
            program_effect_direction=str(rec["desired_change"]), context=context))
    return out


def endpoint_identity(direct_dirs: dict, context: dict) -> dict:
    """The CANONICAL identity of a temporal arm's targets: BOTH Direct endpoints, in agreement.

    The temporal producer's own identity mirrors are NULL (276a9ad leaves target_symbol,
    target_ensembl and target_id_namespace at their dataclass defaults), so they are not read
    at all. A temporal arm is a DIFFERENCE BETWEEN TWO DIRECT ENDPOINTS, so its targets are
    exactly as identified as those two endpoints agree they are.

    If the endpoints disagree about who a target is, the target is NOT ONE TARGET — and
    picking a side would silently attach one endpoint's gene to a difference computed across
    two. So a disagreement REFUSES.
    """
    frm, to = context.get("from_condition"), context.get("to_condition")
    ends = {}
    for cond in (frm, to):
        d = direct_dirs.get(cond)
        if d is None:
            raise BridgeError(
                f"the temporal bundle {frm}->{to} has no admitted Direct endpoint for "
                f"{cond!r}. Its identity comes from BOTH endpoints' {TARGET_IDENTITY_FILE}; "
                "the temporal lane's own identity fields are null and are never trusted")
        ends[cond] = _identity_of(d)

    a, b = ends[frm], ends[to]
    canonical = {}
    for target_id in sorted(set(a) & set(b)):
        ra, rb = a[target_id], b[target_id]
        tuple_a = tuple(ra.get(k) for k in TARGET_IDENTITY_TUPLE)
        tuple_b = tuple(rb.get(k) for k in TARGET_IDENTITY_TUPLE)
        if tuple_a != tuple_b:
            raise BridgeError(
                f"target {target_id!r}: the {frm!r} and {to!r} endpoints DISAGREE about its "
                f"identity ({tuple_a} vs {tuple_b}). A target the two endpoints identify "
                "differently is not one target, and a difference computed across them is a "
                "difference between two different genes")
        canonical[target_id] = ra
    return canonical


TARGET_IDENTITY_TUPLE = ("target_id_namespace", "target_symbol", "target_ensembl",
                         "observed_perturbation_modality")


def _temporal_rows(bundle_dir: str, context: dict, identity: dict) -> list:
    """Temporal ships rankings/ with `arm_value`; identity is the CANONICAL endpoint join."""
    import json
    import os

    out, rdir = [], os.path.join(bundle_dir, "rankings")
    for fname in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(rdir, fname)) as fh:
            doc = json.load(fh)
        # THE ARM KEY IS STORED ONCE, AT THE TOP OF THE RANKING DOCUMENT. The ranked records
        # do NOT repeat it — reading `rec["arm_key"]` KeyErrors on every real temporal bundle.
        arm_key = str(doc.get("arm_key") or "")
        if not arm_key:
            raise BridgeError(
                f"{bundle_dir}/{fname}: the ranking document carries no arm_key. Temporal "
                "stores it ONCE at the top level; its records do not repeat it")
        for rec in (doc.get("records") or doc.get("ranked") or []):
            ident = identity.get(str(rec.get("target_id")))
            if ident is None:
                raise BridgeError(
                    f"{bundle_dir}: target {rec.get('target_id')!r} is ranked but neither "
                    "admitted Direct endpoint identifies it. It would drop out of the Stage-3 "
                    "join and disappear without a trace")
            out.append(R.build_row(
                lane="temporal", record=rec, identity=ident, arm_key=arm_key,
                program_id=arm_key.split("|")[1],
                program_effect_direction=arm_key.split("|")[2], context=context))
    return out


def _pathway_contexts(bundle_dir: str, context: dict, namespace_of: dict) -> list:
    """Pathway's NATIVE records: one per (pathway_arm_key x set_id). NOT a rankings/ dir."""
    import json
    import os

    with open(os.path.join(bundle_dir, "arm_bundle.json")) as fh:
        bundle = json.load(fh)
    out = []
    for rec in (bundle.get("records") or []):
        arm_key = str(rec.get("pathway_arm_key") or rec.get("arm_key"))
        out.append(R.pathway_context(
            arm_key=arm_key, program_id=arm_key.split("|")[1] if "|" in arm_key else "",
            record=rec, context=context, namespace_of=namespace_of,
            source_artifact=(bundle.get("bindings") or {}).get("gene_set_membership")))
    return out


def assemble(bundles_root: str, bridge_root: str) -> dict[str, Any]:
    """Build the bridge from the ADMITTED release. Writes ONLY into ``bridge_root``."""
    import os

    from . import bundle_shapes as BS

    aggregate, manifest, _report = preconditions(bundles_root)

    # THE DIRECT ENDPOINTS FIRST. Temporal's identity is the canonical join across BOTH of
    # them, and pathway's leading edge resolves against the same declared identity — so the
    # Direct bundles must be located before either lane can be built.
    direct_dirs = _direct_bundles_by_condition(bundles_root)

    rows, contexts, native = [], [], {}
    for base, dirs, files in os.walk(bundles_root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if BS.BUNDLE_FILE not in files:
            continue
        norm = BS.read(base)
        if norm is None:
            continue
        lane, ctx = norm["lane"], norm["context"]
        rel = os.path.relpath(base, bundles_root).replace(os.sep, "/")

        names, source = [BS.BUNDLE_FILE], None
        if lane == "direct":
            rows += _direct_rows(base, ctx)
            names += ["arms.parquet", TARGET_IDENTITY_FILE]
            source = {"kind": "identity_artifact", "file": TARGET_IDENTITY_FILE}
        elif lane == "temporal":
            rows += _temporal_rows(base, ctx, endpoint_identity(direct_dirs, ctx))
            names += [f"rankings/{f}" for f in sorted(os.listdir(os.path.join(base,
                      "rankings")))] if os.path.isdir(os.path.join(base, "rankings")) else []
            # BIND BOTH Direct identity artifacts, by hash. The temporal lane's own identity
            # fields are NULL (276a9ad) and are never read; these two are the source.
            endpoints = {}
            for cond in (ctx.get("from_condition"), ctx.get("to_condition")):
                dd = direct_dirs[cond]
                endpoints[cond] = {
                    "relative_dir": os.path.relpath(dd, bundles_root).replace(os.sep, "/"),
                    "raw_sha256": _raw(os.path.join(dd, TARGET_IDENTITY_FILE)),
                }
            source = {"kind": "direct_endpoints", "file": TARGET_IDENTITY_FILE,
                      "endpoints": endpoints, "endpoints_must_agree_exactly": True,
                      "trusts_the_temporal_identity_mirrors": False}
        else:
            # THE NAMESPACE OF EVERY LEADING-EDGE TARGET — from the same declared identity the
            # typed target evidence uses. Never sniffed from the shape of the id.
            contexts += _pathway_contexts(base, ctx, _release_namespaces(bundles_root))
            source = {"kind": "none_pathway_is_context_only"}

        native[rel] = {
            "lane": lane, "bundle_id": norm["bundle_id"], "context": ctx,
            "identity_source": source,
            "files": {n: _raw(os.path.join(base, n)) for n in names
                      if os.path.exists(os.path.join(base, n))},
        }

    doc = build_bridge(
        bindings={
            "aggregate": aggregate,
            "native_bundles": native,
            "lane_admissions": manifest.get("lane_admissions") or {},
            "stage1": manifest.get("stage1_v3_release") or {},
            "identity_source": {"direct": TARGET_IDENTITY_FILE,
                                "temporal": "arm_bundle.json:base_records"},
        },
        rows=rows, contexts=contexts)

    os.makedirs(bridge_root, exist_ok=True)
    _dump(doc, os.path.join(bridge_root, BRIDGE_FILE))     # allow_nan=False: no NaN bytes
    return doc


def _direct_bundles_by_condition(bundles_root: str) -> dict:
    """condition -> the Direct bundle directory. The identity source for every other lane."""
    import json
    import os

    from . import bundle_shapes as BS

    out: dict = {}
    for base, dirs, files in os.walk(bundles_root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if BS.BUNDLE_FILE not in files:
            continue
        try:
            with open(os.path.join(base, BS.BUNDLE_FILE)) as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        if BS.lane_of(doc) == "direct":
            out[str(doc.get("condition"))] = base
    return out


def _release_namespaces(bundles_root: str) -> dict:
    """target_id -> namespace, from every Direct bundle's SHARED identity artifact."""
    import os

    from . import bundle_shapes as BS

    out: dict = {}
    for base, dirs, files in os.walk(bundles_root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if BS.BUNDLE_FILE not in files:
            continue
        norm = BS.read(base)
        if norm and norm["lane"] == "direct":
            for tid, rec in _identity_of(base).items():
                out[tid] = rec["target_id_namespace"]
    return out


def main(argv=None) -> int:
    """Build the bridge over an ADMITTED release, then hand it to the SEPARATE verifier."""
    import argparse
    import json
    import os
    import subprocess
    import sys

    ap = argparse.ArgumentParser(
        description="Build the Stage-3 bridge from an ADMITTED Stage-2 release. Runs only "
                    "after the lane and aggregate admissions are green. Launches no compute, "
                    "and writes NOTHING into any bundle directory.")
    ap.add_argument("--bundles-root", required=True)
    ap.add_argument("--bridge-root", required=True,
                    help="a SEPARATE directory. Never a bundle dir.")
    ap.add_argument("--verify", action="store_true",
                    help="run the SEPARATE bridge verifier as its OWN process; its exit code "
                         "becomes ours, and it writes its own report")
    args = ap.parse_args(argv)

    try:
        doc = assemble(args.bundles_root, args.bridge_root)
    except (BridgeError, R.RowContractError) as exc:
        print(json.dumps({"built": False, "error": str(exc)}, indent=2))
        return 1

    print(json.dumps({"built": True, "n_target_rows": doc["n_target_rows"],
                      "n_pathway_contexts": doc["n_pathway_contexts"],
                      "bridge_sha256": doc["bridge_sha256"],
                      "wrote_into_a_bundle_dir": False}, indent=2))
    if not args.verify:
        return 0

    report_path = os.path.join(args.bridge_root, BRIDGE_REPORT_FILE)
    env = dict(os.environ)
    analysis = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = analysis + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "direct.verify_stage3_bridge",
         "--bridge-root", args.bridge_root, "--bundles-root", args.bundles_root,
         "--report", report_path], env=env, capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0 or not os.path.exists(report_path):
        return proc.returncode or 1

    # THE RECEIPT — written only once the SEPARATE verifier has admitted the bridge.
    bridge_binding, _ = _bind_file(os.path.join(args.bridge_root, BRIDGE_FILE))
    report_binding, _ = _bind_file(report_path)
    rec = receipt(aggregate=doc["bindings"]["aggregate"], bridge_binding=bridge_binding,
                  report_binding=report_binding)
    _dump(rec, os.path.join(args.bridge_root, RECEIPT_FILE))

    # ...and the SEPARATE verifier re-derives the receipt it did not write. Stage 3 gates on
    # this file, so it is a referent like any other: a receipt nobody checked is a claim.
    receipt_report = os.path.join(args.bridge_root, RECEIPT_REPORT_FILE)
    proc = subprocess.run(
        [sys.executable, "-m", "direct.verify_stage3_bridge",
         "--bridge-root", args.bridge_root, "--bundles-root", args.bundles_root,
         "--report", receipt_report, "--receipt-only"], env=env, capture_output=True,
        text=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    print(json.dumps({"receipt": RECEIPT_FILE,
                      "receipt_report": RECEIPT_REPORT_FILE,
                      "aggregate_was_resealed": rec["aggregate_was_resealed"],
                      "receipt_independently_verified": proc.returncode == 0}, indent=2))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
