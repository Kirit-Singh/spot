"""B2 — THE PRODUCTION PATHWAY RUNNER. Generates; it does not verify.

Before this existed, enrichment and convergence could only be reached from test
scaffolding: there was no entry point that took the REAL masked signatures and the REAL
pinned gene sets and produced an artifact anybody could admit, cite or refute. A method
that only runs inside its own tests has not been run.

WHAT IT CONSUMES
----------------
  * the same inputs, the same binding and the same RELEASE GATE as the direct screen
    (``run_screen.prepare`` + ``preflight.assess``). A pathway result that could stand on
    inputs the screen would have refused would be a back door around the gate;
  * the TARGET-MASKED SIGNATURES, built by ``run_screen.condition_rows`` from the very
    mask each score was taken under — not re-derived here. A signature masked differently
    from the number it explains would explain a different number;
  * a PINNED gene-set bundle (``genesets.load``): release id, sha256, namespace, licence
    and the effect-universe binding, all checked.

WHAT IT COMPUTES
----------------
  * per-arm ENRICHMENT (``enrichment.py``, post-M1: the edge is direction-aware, so a
    negative enrichment names the members at the BOTTOM that produced it);
  * signature CONVERGENCE (``convergence.py``, post-B1: computed on the subgraph induced
    by each set's OWN members, so a non-member can never bridge two of them).

Only INTRA-SET pairs are computed. After B1 they are the only pairs any set is allowed to
stand on, and the all-pairs form would be ~63M similarities over the release's 11k
targets to produce numbers nothing may use.

WHAT IT EMITS
-------------
A CONTENT-ADDRESSED artifact under ``<out_root>/<pathway_run_id>/``, mirroring the direct
lane's contract: the records, the provenance that names every input and method hash, and
an independent verifier's ADMISSION. No p. No q. No FDR. No combined objective.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any, Optional

from . import config, convergence, emit, enrichment, gate, genesets, pathway, runid
from . import run_screen as rs
from .hashing import canonical_json, content_hash, sha256_hex

_HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PROVENANCE = "spot.stage02_pathway_provenance.v1"
PATHWAY_RUN_ID_LEN = 16
RUNNER_ID = "spot.stage02.pathway.runner.v1"


def method_block(bundle: Optional[dict[str, Any]]) -> dict[str, Any]:
    """The pathway method, as one hashable object.

    It binds the WITHIN-CONDITION method too: enrichment ranks the screen's arm values
    and convergence compares the screen's masked signatures, so a change to the direct
    method changes what this measured.
    """
    return {
        "runner_id": RUNNER_ID,
        "pathway_method": pathway.method_block(bundle),
        "within_condition_method": runid.method_block(),
        "within_condition_config_sha256": runid.config_sha256(),
        "code_tree_sha256": runid.code_tree_sha256(_HERE),
    }


def build_pathway(args) -> dict[str, Any]:
    """Compute the pathway evidence table from the real signatures and pinned sets."""
    created_at = _dt.datetime.now(_dt.timezone.utc).isoformat()

    # THE SAME binding and THE SAME release gate the screen runs.
    ctx = rs.prepare(args)
    from . import preflight
    verdict = preflight.assess(args, ctx)
    if verdict["verdict"] != preflight.GO:
        detail = "; ".join(f"[{f['check']}] {f['error']}" for f in verdict["failures"])
        raise gate.GateError(
            f"release gate refused this pathway run; no artifact was written. {detail}",
            report=verdict)

    manifest = rs.stage2_input_manifest(args)
    identity_hashes = rs.identity_hashes_of(manifest)
    gene_universe = ctx["gene_universe"]

    # ---- the PINNED gene sets, bound to THIS run's effect universe ----
    bundle = genesets.load(getattr(args, "gene_sets", None),
                           gene_universe["gene_ids"], gene_universe["sha256"])
    if bundle is None:
        raise gate.GateError(
            "pathway run requires --gene-sets: a pinned, licensed, release-identified "
            "gene-set bundle bound to this run's effect universe. There is no default "
            "and no fallback — an unnamed gene-set release cannot be reproduced or "
            "contested, and a pathway result computed against one is not evidence")

    # ---- the SIGNATURES: only gene-set members, masked by the score's own mask ----
    members = {g for s in bundle["sets"].values() for g in s["genes"]}
    built = rs.condition_rows(ctx=ctx, args=args, cond=ctx["cond"],
                              identity_hashes=identity_hashes,
                              guide_ids=ctx["guide_ids"], donor_ids=ctx["donor_ids"],
                              signature_targets=members)
    rows, signatures = built["screen"], built["signatures"]

    # ---- the two evidence lines, side by side, never fused ----
    pairs = convergence.pairwise_within_sets(bundle, signatures)
    doc = pathway.build_records(rows, bundle, signatures,
                                identity_hashes["direct_config_sha256"],
                                pairs=pairs)

    # ---- CONTENT ADDRESSING: the artifact is named by what produced it ----
    binding = {
        "runner_id": RUNNER_ID,
        "pathway_method": method_block(bundle),
        "lane": ctx["lane"],
        "selection": {
            "selection_id": ctx["selection"].selection_id,
            "question_id": ctx["selection"].question_id,
            "selection_contract_sha256": ctx["selection"].contract_sha256,
            "analysis_condition": ctx["selection"].analysis_condition,
        },
        "gene_sets": genesets.binding_block(bundle),
        "stage2_inputs": sorted(
            [{"name": i["name"], "sha256": i["sha256"], "size_bytes": i["size_bytes"]}
             for i in manifest], key=lambda i: i["name"]),
        "gene_universe_sha256": gene_universe["sha256"],
        "evidence_domain": rs._domain_block(ctx),
        "release_gate": verdict["release_gate"],
        # M2: the reproducible code-identity tuple; a release lane refuses a dirty tree
        "code_identity": rs.code_identity_for(
            ctx["lane"], getattr(args, "allow_dirty_tree", False)),
        "environment_lock": runid.env_lock_block(args.env_lock),
        # WHAT the records are, by content: a run that emitted different records under
        # the same id would be citing numbers it does not hold.
        "records_sha256": doc["records_sha256"],
    }
    full = sha256_hex(canonical_json(binding))
    pathway_run_id = full[:PATHWAY_RUN_ID_LEN]
    method_sha = content_hash(method_block(bundle))

    for r in doc["records"]:
        r["pathway_run_id"] = pathway_run_id
        r["pathway_method_sha256"] = method_sha

    out_dir = os.path.join(args.out_root, pathway_run_id)
    os.makedirs(out_dir, exist_ok=True)

    result = dict(doc, pathway_run_id=pathway_run_id,
                  pathway_method_sha256=method_sha,
                  n_signature_targets=len(signatures),
                  n_intra_set_pairs=len(pairs))
    emit.write_json(os.path.join(out_dir, "pathway.json"), result)

    prov = {
        "schema_version": SCHEMA_PROVENANCE,
        "pathway_run_id": pathway_run_id,
        "pathway_run_sha256": full,
        "pathway_method_sha256": method_sha,
        "created_at": created_at,
        "run_binding": binding,
        "n_records": doc["n_records"],
        "n_convergent": doc["n_convergent"],
        "n_single_target_support": doc["n_single_target_support"],
        "n_signature_targets": len(signatures),
        "n_intra_set_pairs": len(pairs),
        # said where a reader looks, not only in the method doc
        "inference_status": enrichment.INFERENCE_STATUS,
        "no_pq_reason": enrichment.NO_PQ_REASON,
        "files": manifest,
    }
    emit.write_json(os.path.join(out_dir, "pathway_provenance.json"), prov)

    from . import verify_pathway
    verification = verify_pathway.verify(out_dir=out_dir, provenance=prov)
    emit.write_json(os.path.join(out_dir, "pathway_verification.json"), verification)

    return {
        "pathway_run_id": pathway_run_id,
        "pathway_run_sha256": full,
        "pathway_method_sha256": method_sha,
        "out_dir": out_dir,
        "n_records": doc["n_records"],
        "n_convergent": doc["n_convergent"],
        "n_signature_targets": len(signatures),
        "n_intra_set_pairs": len(pairs),
        "records_sha256": doc["records_sha256"],
        "verification": verification,
    }


def main(argv=None) -> int:
    import argparse

    from .cli import main as _direct_main  # noqa: F401  (same argument surface)

    ap = argparse.ArgumentParser(
        description="Stage-2 pathway runner: per-arm enrichment + signature convergence")
    ap.add_argument("--selection", required=True)
    ap.add_argument("--registry", required=True)
    ap.add_argument("--de-main", required=True)
    ap.add_argument("--by-guide", required=True)
    ap.add_argument("--by-donors", required=True)
    ap.add_argument("--sgrna", required=True)
    ap.add_argument("--gene-sets", required=True,
                    help="the PINNED gene-set bundle: release id + sha256 + namespace + "
                         "licence, bound to this run's effect universe")
    ap.add_argument("--guide-manifest", default=None)
    ap.add_argument("--source-registry", default=None)
    ap.add_argument("--stage1-release", default=None)
    ap.add_argument("--stage1-validation", default=None)
    ap.add_argument("--stage1-gate-spec", default=None)
    ap.add_argument("--target-identity-map", default=None)
    ap.add_argument("--donor-crosswalk", default=None)
    ap.add_argument("--env-lock", default=None)
    ap.add_argument("--allow-dirty-tree", action="store_true",
                    help="take a RELEASE-grade run from an uncommitted tree. The digest "
                         "then describes bytes that exist in no commit, so this is "
                         "RECORDED in the run binding and CHANGES the run id — a dirty "
                         "release is allowed to exist, not to look like a clean one.")
    ap.add_argument("--lane", default=config.LANE_PRODUCTION, choices=list(config.LANES))
    ap.add_argument("--strict-replay", action="store_true")
    ap.add_argument("--pseudobulk", default=None)
    ap.add_argument("--out-root", required=True)
    args = ap.parse_args(argv)

    try:
        result = build_pathway(args)
    except gate.GateError as exc:
        print(json.dumps(exc.report or {"verdict": "NO_GO", "error": str(exc)},
                         indent=2, sort_keys=True))
        return 1

    from . import verify_pathway
    v = result["verification"]
    print(json.dumps({
        "pathway_run_id": result["pathway_run_id"],
        "pathway_method_sha256": result["pathway_method_sha256"],
        "out_dir": result["out_dir"],
        "n_records": result["n_records"],
        "n_convergent": result["n_convergent"],
        "n_signature_targets": result["n_signature_targets"],
        "n_intra_set_pairs": result["n_intra_set_pairs"],
        "records_sha256": result["records_sha256"],
        "verification": {"verdict": v["verdict"], "n_failed": v["n_failed"]},
        "inference_status": enrichment.INFERENCE_STATUS,
    }, indent=2))
    return 0 if v["verdict"] == verify_pathway.ADMIT else 1


if __name__ == "__main__":
    raise SystemExit(main())
