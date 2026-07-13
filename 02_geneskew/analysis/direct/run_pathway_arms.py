"""THE ALL-ARM PATHWAY PRODUCER: one bundle per (condition, source). Six in the release.

3 conditions x 2 pinned sources. Each bundle carries every admitted program's TWO enrichment
arms — |admitted| x 2 reusable slots — and ONE shared convergence artifact.

There is no pair, no role, no pole, no Pareto, no concordance, no joint status and no
combined score anywhere in it. A pathway arm is reusable precisely because it does not know
which question is about to cite it.

WHY CONVERGENCE IS EMITTED ONCE AND REFERENCED TWENTY TIMES
-----------------------------------------------------------
Enrichment is per (program, desired_change): it is computed over a RANKED LIST, and a ranking
is not antisymmetric, so all 20 arms are COMPUTED — never inferred one from the other.
Convergence is not like that: it depends only on the masked signatures for the (condition,
source), and it does not know which program is being asked about or in which direction. So it
is computed ONCE, hashed, and REFERENCED by all 20 arms. Restating one claim 20 times is 20
chances to disagree with it, and a reader cannot tell which copy was the one that got checked.

THE RUN ID IS TAKEN LAST
------------------------
Every binding — the gene-set source bytes, both universes, the rankings, the masks, the
signatures, the code and input identities, the scorer view — is assembled BEFORE the id is
computed over them. An id taken early is an id that does not cover what came after it.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
from typing import Any

from . import arm_bundle as ab
from . import (
    config,
    emit,
    gate,
    genesets,
    pathway_arms,
    pathway_evidence,
    preflight,
    run_arms,
    runid,
    scorer_view,
)
from . import run_screen as rs
from . import universe as uni
from .hashing import canonical_json, content_hash, sha256_hex

SCHEMA_REQUEST = "spot.stage02_pathway_arm_request.v1"
SCHEMA_PROVENANCE = "spot.stage02_pathway_arm_provenance.v1"
RUNNER_ID = "spot.stage02.pathway.all_arm_runner.v1"
RUN_ID_LEN = 16

# THE PHYSICAL CONTRACT. Emitted natively — no rename, no copy step.
BUNDLE_FILE = "arm_bundle.json"
PROVENANCE_FILE = "pathway_provenance.json"
VERIFICATION_FILE = "pathway_verification.json"
CONVERGENCE_FILE = "convergence.json"


def build_pathway_arms(args) -> dict[str, Any]:
    """ONE (condition, source) all-arm pathway bundle."""
    created_at = _dt.datetime.now(_dt.timezone.utc).isoformat()

    # BUNDLE-SCOPED: a lane and a context. No pair is loaded and none is bound.
    ctx = rs.prepare_bundle(args, cond=args.condition)
    verdict = preflight.assess(args, ctx)
    if verdict["verdict"] != preflight.GO:
        detail = "; ".join(f"[{f['check']}] {f['error']}" for f in verdict["failures"])
        raise gate.GateError(
            f"release gate refused this pathway arm bundle; nothing was written. {detail}",
            report=verdict)

    view = scorer_view.view(ctx["release"])
    admitted = view["admitted_program_ids"]
    cond = ctx["cond"]
    gene_universe = ctx["gene_universe"]
    target_universe = uni.target_universe(ctx["identities_by_condition"])

    bundle = genesets.load(getattr(args, "gene_sets", None),
                           gene_universe["gene_ids"], gene_universe["sha256"],
                           target_universe["target_ids"], target_universe["sha256"])
    if bundle is None:
        raise gate.GateError(
            "a pathway arm bundle requires --gene-sets: a pinned, licensed, "
            "release-identified gene-set bundle bound to BOTH of this run's universes. "
            "There is no default and no fallback")
    source = str(bundle["gene_set_release"]["source"])

    # ONE scan: the base deltas every arm is a sign transform of, the masks they were taken
    # under, and the signatures convergence is computed from — all under the SAME mask.
    members = {g for s in bundle["sets"].values() for g in s["genes_target"]}
    scan = run_arms.base_deltas(ctx=ctx, args=args, cond=cond, admitted=admitted,
                                signature_targets=members)
    arm_rows = ab.build_rows(condition=cond, admitted=admitted,
                             base_by_program=scan["base"])
    signatures = scan["signatures"]

    # THE ONE convergence claim for this (condition, source) — no program, no direction.
    conv = pathway_arms.convergence_artifact(
        bundle=bundle, signatures=signatures, condition=cond, source=source,
        readout_universe_sha256=gene_universe["sha256"])

    doc = pathway_arms.build(condition=cond, source=source, view=view, bundle=bundle,
                             arm_rows=arm_rows, convergence_doc=conv)

    # ---- EVERY binding, assembled BEFORE the id is taken over them ----
    evidence_doc = pathway_evidence.build(arm_rows_evidence(arm_rows), bundle,
                                          target_universe, gene_universe)
    evidence_doc["arm_rankings"] = {
        k: [{"target_id": t, "score": v, "rank": i + 1}
            for i, (t, v) in enumerate(r)]
        for k, r in pathway_arms.ranked_by_arm(arm_rows).items()
    }
    sig_rows = pathway_evidence.signature_rows(signatures)
    manifest = rs.stage2_input_manifest(args)

    binding = {
        "runner_id": RUNNER_ID,
        "lane": ctx["lane"],
        "condition": cond,
        "source": source,
        "request": {
            "schema_version": SCHEMA_REQUEST,
            "condition": cond,
            "source": source,
            "names_a_program_pair": False,
            "scorer_view_sha256": view["scorer_view_sha256"],
            "admitted_program_ids": admitted,
            "n_expected_arm_slots": pathway_arms.expected_slots(admitted),
        },
        "method": doc["method"],
        "scorer_view_sha256": view["scorer_view_sha256"],
        "release_scorer_view_canonical_sha256":
            view["release_scorer_view_canonical_sha256"],
        "gene_universe_sha256": gene_universe["sha256"],
        "target_universe_sha256": target_universe["sha256"],
        "n_effect_universe_genes": len(gene_universe["gene_ids"]),
        "n_target_universe_genes": target_universe["n_targets"],
        "mask_sha256": emit.mask_content_sha256(scan["mask_rows"]),
        "stage2_inputs": sorted(
            [{"name": i["name"], "sha256": i["sha256"], "size_bytes": i["size_bytes"]}
             for i in manifest], key=lambda i: i["name"]),
        "evidence_artifacts": pathway_evidence.binding_block(
            evidence_doc, sig_rows,
            gene_sets=pathway_evidence.gene_set_source_block(args.gene_sets, bundle)),
        "evidence_domain": rs._domain_block(ctx),
        "release_gate": verdict["release_gate"],
        "code_identity": rs.code_identity_for(
            ctx["lane"], getattr(args, "allow_dirty_tree", False)),
        "environment_lock": runid.env_lock_block(getattr(args, "env_lock", None)),
        "direct_arm_rows_sha256": ab.rows_sha256(arm_rows),
        "convergence_sha256": conv["convergence_sha256"],
        "records_sha256": doc["records_sha256"],
    }
    # ...and ONLY NOW the id, over all of it.
    full = sha256_hex(canonical_json(binding))
    run_id = full[:RUN_ID_LEN]

    out_dir = os.path.join(args.out_root, run_id)
    os.makedirs(out_dir, exist_ok=True)

    emit.write_json(os.path.join(out_dir, BUNDLE_FILE), dict(doc, pathway_run_id=run_id))
    emit.write_json(os.path.join(out_dir, CONVERGENCE_FILE),
                    dict(conv, pathway_run_id=run_id))
    evidence_paths = pathway_evidence.write(evidence_doc, sig_rows, out_dir,
                                            gene_sets_source=args.gene_sets)

    prov = {
        "schema_version": SCHEMA_PROVENANCE,
        "pathway_run_id": run_id,
        "pathway_run_sha256": full,
        "created_at": created_at,
        "run_binding": binding,
        "evidence_artifacts": pathway_evidence.written_block(
            binding["evidence_artifacts"], evidence_paths),
        # the signature artifact, referenced BY CONTENT so a condition-shared content-
        # addressed store (W7) can hold ONE copy for the two sources of a condition. The
        # reference is the hash; where the bytes live is the store's business. No gene is
        # dropped to make it smaller — a signature with genes removed is a different
        # signature.
        "signature_reference": {
            "content_sha256": content_hash(sig_rows),
            "readout_universe_sha256": gene_universe["sha256"],
            "n_signature_targets": len(signatures),
            "n_rows": len(sig_rows),
            "columns": list(pathway_evidence.SIGNATURE_COLUMNS),
            "path_in_bundle": pathway_evidence.SIGNATURES_FILE,
            "shareable_scope": "condition",
            "genes_dropped": 0,
        },
        "n_records": doc["n_records"],
        "n_arm_slots": doc["n_arm_slots"],
        "n_expected_arm_slots": doc["n_expected_arm_slots"],
        "inference_status": config.INFERENCE_STATUS,
    }
    emit.write_json(os.path.join(out_dir, PROVENANCE_FILE), prov)

    # FAIL-CLOSED, and not self-admission: W4's independent verifier reads the SHIPPED bytes
    # at these exact paths and decides. A producer that admitted its own output would be
    # marking its own homework.
    emit.write_json(os.path.join(out_dir, VERIFICATION_FILE), {
        "schema_version": "spot.stage02_pathway_arm_verification.v1",
        "pathway_run_id": run_id,
        "pathway_run_sha256": full,
        "generator_is_not_verifier": True,
        "fail_closed": True,
        "verifier_id": None,
        "verdict": "pending_independent_verification",
        "admitted": False,
        "verified_paths": [BUNDLE_FILE, PROVENANCE_FILE, CONVERGENCE_FILE,
                           pathway_evidence.EVIDENCE_FILE,
                           pathway_evidence.GENE_SETS_FILE,
                           pathway_evidence.SIGNATURES_FILE],
        "records_sha256": doc["records_sha256"],
        "convergence_sha256": conv["convergence_sha256"],
    })

    return {"pathway_run_id": run_id, "out_dir": out_dir, "condition": cond,
            "source": source, "lane": ctx["lane"],
            "n_admitted_programs": view["n_admitted_programs"],
            "n_arm_slots": doc["n_arm_slots"],
            "n_expected_arm_slots": doc["n_expected_arm_slots"],
            "n_records": doc["n_records"], "bundle": doc, "convergence": conv,
            "provenance": prov}


def arm_rows_evidence(arm_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The rows ``pathway_evidence`` needs. It re-keys the rankings itself, per arm."""
    return arm_rows


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m direct.run_pathway_arms",
        description="Emit ONE (condition, source) all-arm pathway bundle: every admitted "
                    "program's increase and decrease enrichment arms, plus the ONE shared "
                    "convergence artifact. Names a context, never an A/B pair.")
    ap.add_argument("--condition", required=True)
    ap.add_argument("--gene-sets", required=True)
    ap.add_argument("--registry", default=None)
    ap.add_argument("--stage1-release", default=None)
    ap.add_argument("--stage1-validation", default=None)
    ap.add_argument("--stage1-gate-spec", default=None)
    ap.add_argument("--de-main", required=True)
    ap.add_argument("--by-guide", default=None)
    ap.add_argument("--by-donors", default=None)
    ap.add_argument("--sgrna", default=None)
    ap.add_argument("--guide-manifest", default=None)
    ap.add_argument("--source-registry", default=None)
    ap.add_argument("--target-identity-map", default=None)
    ap.add_argument("--lane", default=config.LANE_PRODUCTION, choices=list(config.LANES))
    ap.add_argument("--strict-replay", action="store_true")
    ap.add_argument("--strict-replay-source", default=None)
    ap.add_argument("--pseudobulk", default=None)
    ap.add_argument("--env-lock", default=None)
    ap.add_argument("--allow-dirty-tree", action="store_true")
    ap.add_argument("--out-root", required=True)
    return ap


def main(argv=None) -> dict[str, Any]:
    args = build_parser().parse_args(argv)
    r = build_pathway_arms(args)
    print(json.dumps({k: r[k] for k in (
        "pathway_run_id", "condition", "source", "lane", "out_dir",
        "n_admitted_programs", "n_arm_slots", "n_expected_arm_slots", "n_records")},
        indent=2))
    return r


if __name__ == "__main__":
    main()
