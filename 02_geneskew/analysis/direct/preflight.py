"""``--preflight-only``: prove the run is admissible BEFORE reading an effect matrix.

The expensive part of a real Direct run is the dense pooled effect layers. Everything
that can REFUSE the run — the Stage-1 selection and release, the public source pins,
the global pooled-main scope identity, the contributor manifest, its source-record
table, the completeness-bearing replay report, and the explicit support contract — is
decidable from metadata alone. So it is decided first, and a run that was going to fail
fails before it costs anything.

Two properties make this a preflight rather than a second, parallel implementation:

  * it calls ``run_screen.prepare`` — the SAME binding the real build calls. A
    preflight that validated something other than what the run consumes would be a
    preflight of a different program, and would certify nothing about this one. There
    is no custom audit loader anywhere in this path;
  * it writes NO scientific result artifact. It emits one machine-readable verdict and
    nothing else. A preflight that could write a screen could be mistaken for a run.

Strict replay (``--strict-replay``) re-derives the contributor completeness from the
raw ~44 GB source instead of trusting the pinned report. That is the release gate, and
it runs on tcefold, never on the orchestration host.
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import config, domain, gate, run_screen, stage1_v3
from . import manifest as mf

SCHEMA_VERSION = "spot.stage02_direct_preflight.v1"

GO = "GO"
NO_GO = "NO_GO"

# The questions preflight answers. Each is decidable without a dense read.
CHECKS = (
    "stage1_selection_and_release_bind",
    "public_source_pins_verify",
    "global_pooled_main_scope_identity",
    "contributor_manifest_resolves",
    "source_record_table_resolves",
    "completeness_report_is_the_release_gate",
    "selected_condition_main_count",
    "support_is_explicitly_unavailable",
    gate.CHECK_STRICT,
)


def _manifest_block(ctx: dict) -> dict[str, Any]:
    doc = ctx["manifest_doc"]
    if doc is None:
        # Absence is a STATE — flags and enums, not a paragraph. The one place the
        # consequences are spelled out in prose is the method docs; every run that
        # hits this emits the same machine-readable block.
        return dict(mf.ABSENT_BLOCK)
    return {
        "status": "bound",
        "schema_version": doc["schema_version"],
        "source_record_table_schema_version":
            doc["source_record_table_schema_version"],
        "evidence_domain": doc["evidence_domain"],
        "n_rows": doc["n_rows"],
        "n_scopes": doc["n_scopes"],
        "canonical_sha256": doc["canonical_sha256"],
        "manifest_sha256": doc["manifest_sha256"],
        "source_record_table": doc["source_record_table"],
        "source_replay_report": doc["source_replay_report"],
        "sources": doc["sources"],
        "evidence_resolution": doc["resolution"],
        "source_replay": doc["source_replay"],
    }


def strict_replay(args, ctx, failures: list[dict[str, str]]) -> dict[str, Any]:
    """Re-derive the completeness verdict from the RAW source, then COMPARE.

    The pinned report is a claim by the producer. ``--strict-replay`` runs the same v2
    implementation the report was supposed to come from, against the raw ~44 GB source,
    and checks the fresh verdict agrees with the pinned one. A report that says
    "complete" over a source that says otherwise dies here.

    Expensive by construction; this is the release gate, not the every-invocation
    default, and it runs on tcefold. It writes no scientific result.
    """
    from . import replay  # h5py-heavy; imported only when used
    doc = ctx["manifest_doc"]
    pinned = dict(doc["source_replay"])
    src = getattr(args, "strict_replay_source", None) or args.pseudobulk
    fresh = replay.build_report(
        table_path=_source_path(args, doc["source_record_table"]),
        manifest_path=args.guide_manifest, source_path=src,
        source_id=pinned.get("source_id"))

    agree = (fresh["verdict"] == pinned["status"]
             and fresh["completeness_verdict"] == pinned["completeness_verdict"]
             and fresh["n_scopes_incomplete"] == 0
             and fresh["n_scopes_complete"] == pinned["n_scopes_complete"]
             and fresh["n_records_offset_proven"]
             == pinned["n_records_offset_proven"]
             and fresh["n_nontargeting_guides_cited"] == 0
             # THE SOURCE CLASSIFICATION, re-derived here from the raw source. A fresh
             # replay that found a downgraded scope disagrees with any pinned report that
             # did not, and no release may stand on the difference.
             and fresh["n_scopes_downgraded"] == 0
             and fresh["n_scopes_overclaimed"] == 0
             and fresh["n_scopes_source_determinable"]
             == pinned["n_scopes_source_determinable"]
             and fresh["n_scopes_source_non_determinable"]
             == pinned["n_scopes_source_non_determinable"]
             and fresh["source_sha256"] == pinned["source_sha256"]
             and fresh["source_record_table_sha256"]
             == pinned["source_record_table_sha256"])
    if not agree:
        failures.append({
            "check": "strict_replay_agrees_with_the_pinned_release_gate",
            "error": f"fresh verdict={fresh['verdict']}/"
                     f"{fresh['completeness_verdict']} "
                     f"(complete={fresh['n_scopes_complete']}, "
                     f"incomplete={fresh['n_scopes_incomplete']}, "
                     f"offset_proven={fresh['n_records_offset_proven']}, "
                     f"nontargeting={fresh['n_nontargeting_guides_cited']}) does not "
                     f"agree with the pinned report",
        })
    return {
        "ran": True,
        "agrees_with_pinned_report": agree,
        "verdict": fresh["verdict"],
        "completeness_verdict": fresh["completeness_verdict"],
        "n_records": fresh["n_records"],
        "n_replayed": fresh["n_replayed"],
        "n_failed": fresh["n_failed"],
        "n_scopes_determined": fresh["n_scopes_determined"],
        "n_scopes_ambiguous": fresh["n_scopes_ambiguous"],
        "n_scopes_complete": fresh["n_scopes_complete"],
        "n_scopes_incomplete": fresh["n_scopes_incomplete"],
        "n_records_offset_proven": fresh["n_records_offset_proven"],
        "n_nontargeting_guides_cited": fresh["n_nontargeting_guides_cited"],
        "n_scopes_source_determinable": fresh["n_scopes_source_determinable"],
        "n_scopes_source_non_determinable":
            fresh["n_scopes_source_non_determinable"],
        "n_scopes_downgraded": fresh["n_scopes_downgraded"],
        "n_scopes_overclaimed": fresh["n_scopes_overclaimed"],
        "source_sha256": fresh["source_sha256"],
        "source_record_table_sha256": fresh["source_record_table_sha256"],
    }


def _source_path(args, name: str) -> str:
    """Locate a manifest source by the trusted registry, never by guessing a path."""
    from . import io_data
    registry = io_data.load_source_registry(args.source_registry) or {}
    base = os.path.dirname(os.path.abspath(args.source_registry)) \
        if args.source_registry else ""
    return os.path.join(base, str((registry.get(name) or {}).get("path", name)))


def run(args) -> dict[str, Any]:
    """Bind every input short of the dense layers, then ASSESS it. Returns the verdict.

    Raises nothing on a scientific refusal — it CATCHES the refusal and reports it, so
    a caller gets a machine-readable NO-GO with the exact contract that failed rather
    than a traceback.
    """
    try:
        # THE SAME selection-load + admission the build runs. Not a parallel "audit loader":
        # a preflight that bound a different contract than production would certify a
        # different run, and its GO would be worse than no preflight at all.
        ctx = run_screen.load_and_prepare(args, expect_mode=stage1_v3.MODE_WITHIN)
    except Exception as exc:                     # a refusal IS the answer
        return {
            "schema_version": SCHEMA_VERSION,
            "verdict": NO_GO,
            "lane": getattr(args, "lane", None),
            "strict_replay": {"ran": False},
            "release_gate": None,
            "dense_layer_reads": 0,
            "result_artifacts_written": 0,
            "checks": list(CHECKS),
            "failures": [{"check": "prepare",
                          "error": f"{type(exc).__name__}: {exc}"}],
        }
    return assess(args, ctx)


def assess(args, ctx: dict[str, Any]) -> dict[str, Any]:
    """Every refusal, over an ALREADY-BOUND ctx. THE one gate, run by preflight AND
    by the build.

    ``build_screen`` calls this with the very ctx it is about to score, so a build
    cannot execute a weaker set of checks than a preflight of the same inputs — which
    it could, trivially, when the checks lived only inside ``--preflight-only``.
    """
    failures: list[dict[str, str]] = []
    doc = ctx["manifest_doc"]
    support = ctx["support_contract"]

    if doc is None:
        failures.append({
            "check": "contributor_manifest_resolves",
            "error": "no contributor manifest was supplied; without one every main "
                     "estimate is unresolved and the run has no evidence to stand on",
        })

    # The support contract must actually SAY unavailable. A run that quietly began
    # granting guide/donor support would be a different scientific claim.
    if support["guide_support_available"] or support["donor_support_available"] \
            or support["support_may_elevate_evidence_tier"]:
        failures.append({
            "check": "support_is_explicitly_unavailable",
            "error": f"the support contract claims support: {support}",
        })

    strict = {"ran": False}
    if getattr(args, "strict_replay", False) and doc is not None:
        try:
            strict = strict_replay(args, ctx, failures)
        except Exception as exc:
            failures.append({"check": "strict_replay",
                             "error": f"{type(exc).__name__}: {exc}"})
            strict = {"ran": True, "agrees_with_pinned_report": False}

    # THE RELEASE GATE. A release-grade lane may not stand on the pinned report: strict
    # replay must have run FRESH, in THIS invocation, against the raw source. There is
    # no artifact that can be presented instead — a gate a producer can satisfy by
    # authoring a file is not a gate.
    release_gate = None
    try:
        release_gate = gate.release_gate(lane=ctx["lane"], strict_replay=strict)
    except gate.GateError as exc:
        failures.append({"check": gate.CHECK_STRICT, "error": str(exc)})

    verdict = NO_GO if failures else GO
    return {
        "schema_version": SCHEMA_VERSION,
        "verdict": verdict,
        "lane": ctx["lane"],
        "strict_replay": strict,
        "release_gate": release_gate,
        # A preflight that read a dense layer, or wrote a result, would not be one.
        "dense_layer_reads": 0,
        "result_artifacts_written": 0,
        "checks": list(CHECKS),
        "failures": failures,
        "stage1": {
            "selection_id": ctx["selection"].selection_id,
            "question_id": ctx["selection"].question_id,
            "analysis_condition": ctx["cond"],
            "stage1_method_version": ctx["selection"].stage1_method_version,
            "release_kind": ctx["release"].kind,
            "production_eligible": ctx["axis"]["production_eligible"],
            "stage3_eligible": ctx["axis"]["stage3_eligible"],
            "production_gate_passed": ctx["axis"]["production_gate_passed"],
        },
        # WHAT CONTRACT WAS CERTIFIED. The identical block the build binds into its run
        # identity — so "the preflight passed" is checkable against "the build ran this",
        # rather than being two assertions about two things that share a name.
        "stage1_v3": stage1_v3.binding_block(ctx.get("v3")),
        "legacy_selection": run_screen.legacy_selection_block(args, ctx.get("v3")),
        "evidence_domain": run_screen._domain_block(ctx),
        "contributor_manifest": _manifest_block(ctx),
        "support_contract": support,
        "observed_support": ctx["observed_support"],
        "gene_universe": {
            "n_genes": ctx["gene_universe"]["n_genes"],
            "sha256": ctx["gene_universe"]["sha256"],
            "retained_fraction_of_reference":
                ctx["gene_universe"]["retained_fraction_of_reference"],
        },
        "donor_splits": {
            "donor_tokens": ctx["splits"]["donor_tokens"],
            "n_splits": ctx["splits"]["n_splits"],
            "status": ctx["splits"]["status"],
        },
        "method": {
            "method_id": config.METHOD_ID,
            "method_version": config.METHOD_VERSION,
            "combined_objective_permitted": config.COMBINED_OBJECTIVE_PERMITTED,
            "arms": list(config.ARMS),
            "support_available_in_this_pass": config.SUPPORT_AVAILABLE_IN_THIS_PASS,
            "evidence_domain": domain.DOMAIN_ID,
        },
    }


def write(report: dict[str, Any], path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path
