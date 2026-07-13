"""Stage-4 CLI.

    python -m analysis.run_stage4 --fixtures --outputs-root 04_PKPD/outputs
    python -m analysis.run_stage4 --stage3-bundle <dir-or-document> [--evidence-bundle <json>]

Two doors, and no third:

  --stage3-bundle   a REAL Stage-3 emission (bundle directory, or the document inside it).
                    It goes through `stage3_adapter.load_stage3_bundle` + `adapt`, which
                    reconstruct every table's content hash from the parquet rows before
                    believing a word of it. What happens next depends on what Stage 3
                    actually emitted:

                      research annotation   inspected, never admitted. Zero candidates,
                                            zero scorecards. Stage 3's own words: "an
                                            ANNOTATION, never a candidate set".
                      fixture bundle        admitted as FIXTURE candidates. A run over it
                                            is a labelled smoke path and can never write a
                                            production pointer.
                      candidate set         admitted as production candidates — and then
                                            the engine runs ONLY if a real evidence bundle
                                            is supplied. Without one it emits an admission
                                            receipt and stops.

  --fixtures        the engine's own internal fixtures, for exercising the lanes offline.

Fail-closed by design:

  * a PRODUCTION POINTER is never written from fixture inputs, from a research-only
    namespace, or from a set with no production-eligible candidate;
  * a SELECTION (a ranked or chosen candidate) is never emitted at all — Stage 4 is an
    evidence engine, and a selection needs real, independently reviewed public-source
    evidence;
  * a candidate set with NO evidence never becomes a scorecard set. Running ten empty
    lanes would emit a complete-looking artifact whose every field says "not_evaluated".
    An empty lane is not a finding.

There is no --force. The refusals are not options.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

from .contracts import Namespace
from .evidence_bundle import is_empty, load_evidence_bundle
from .emit import emit
from .firewall import Rejection
from .method_config import STAGE4_DIR, load_method_bundle
from .pipeline import Stage4Inputs, Stage4Result, run_pipeline
from .stage3_adapter import Stage3Admission, adapt, load_stage3_bundle
from .stage3_annotation import (
    ADAPTER_ID as ANNOTATION_ADAPTER_ID,
    AnnotationAdmission,
    adapt_annotation_bundle,
)
from .verify import verify_output_dir

DEFAULT_OUTPUTS_ROOT = os.path.join(STAGE4_DIR, "outputs")
PRODUCTION_POINTER = "PRODUCTION_POINTER.json"
RECEIPT_SCHEMA = "spot.stage04_admission_receipt.v1"


class ProductionGateRefusal(Exception):
    """The run is not allowed to become something a downstream stage would trust."""


def production_pointer_decision(inputs: Stage4Inputs, result: Stage4Result) -> dict[str, Any]:
    """May this run advertise itself as the production scorecard set? -> reasons why not."""
    refusals: list[str] = []

    if inputs.candidate_set.is_fixture:
        refusals.append(
            "fixture_input: the candidate set is labelled is_fixture. Fixture evidence must "
            "never be reachable from a production pointer."
        )
    if any(s.is_fixture for s in inputs.sources.values()):
        refusals.append(
            "fixture_sources: at least one source record is a fixture, so at least one number "
            "in this run is not a real public-source observation."
        )
    if inputs.candidate_set.namespace == Namespace.RESEARCH_ONLY:
        refusals.append("research_only_namespace: the upstream candidate set is research-only.")
    if not any(cr.production_eligible for cr in result.candidates):
        refusals.append("no_production_eligible_candidate: no candidate in this set is production eligible.")

    return {
        "production_pointer_written": False,
        "eligible": not refusals,
        "refusals": refusals,
        "note": (
            "Even an eligible run does not write a production pointer in this pass: no real "
            "public-source evidence set has been independently reviewed for Stage 4."
        ),
    }


def write_production_pointer(outputs_root: str, inputs: Stage4Inputs, result: Stage4Result,
                             scorecard_set_id: str) -> None:
    """Fail-closed: refuses, always, in this pass."""
    decision = production_pointer_decision(inputs, result)
    if not decision["eligible"]:
        raise ProductionGateRefusal(
            "refusing to write a production pointer:\n  - " + "\n  - ".join(decision["refusals"])
        )
    raise ProductionGateRefusal(
        "refusing to write a production pointer: no independently reviewed real-source "
        "evidence set has been consumed. "
        f"(candidate set would otherwise have been {scorecard_set_id!r} in {outputs_root!r})"
    )


# ----------------------------------------------------------------- the Stage-3 door


def admission_receipt(admission: Stage3Admission, ran: bool, reason: str,
                      reason_code: str) -> dict[str, Any]:
    """A compact, machine-readable statement of what was admitted and what was NOT produced."""
    i = admission.inspection
    return {
        "schema_id": RECEIPT_SCHEMA,
        "stage3": {
            "schema_version": i.stage3_schema_version,
            "namespace": i.stage3_namespace,
            "document_id": i.stage3_document_id,
            "document_sha256": i.document_sha256,
            "canonical_content_sha256": i.canonical_content_sha256,
            "data_status": i.data_status,
            "source_status": i.source_status,
            "stage4_eligible": i.stage4_eligible,
        },
        "admission": {
            "admitted_as_candidates": i.admitted_as_candidates,
            "inspected_only": i.n_inspectable,
            "refusal_reason": i.refusal_reason,
        },
        "stage4_run": {
            "scorecards_emitted": ran,
            "reason_code": reason_code,
            "reason": reason,
        },
        "hard_rules": [
            "A research annotation is inspected, never admitted as a candidate.",
            "A candidate set with no evidence bundle yields a receipt, never a scorecard set.",
            "No drug is ranked, selected, or asserted to be safe or brain-permeable here.",
        ],
    }


def stage3_inputs(admission: Any, evidence_path: Optional[str]) -> Stage4Inputs:
    """Bind the adapted Stage-3 candidates to a REAL evidence bundle. Never to an empty one."""
    assert admission.candidate_set is not None
    bundle = load_evidence_bundle(evidence_path or "")
    if is_empty(bundle):
        raise Rejection(
            "evidence_bundle_empty",
            f"the evidence bundle at {evidence_path!r} carries no observation in any lane. "
            "Stage 4 will not emit a scorecard set built from empty lanes: every field would "
            "read 'not_evaluated' and the artifact would look like a result.",
        )

    # Stage-3's source records, plus any the evidence bundle brings. Stage 3's classes are
    # carried across untouched — a synthetic_fixture stays a synthetic_fixture.
    sources = dict(admission.source_records)
    sources.update(bundle["sources"])

    return Stage4Inputs(
        candidate_set=admission.candidate_set,
        contexts=bundle["contexts"],
        sources=sources,
        properties=bundle["properties"],
        potencies=bundle["potencies"],
        transporters=bundle["transporters"],
        exposures=bundle["exposures"],
        delivery_assignments=bundle["delivery_assignments"],
        nebpi_observations=bundle["nebpi_observations"],
        safety_records=bundle["safety_records"],
        potency_context_links=bundle["potency_context_links"],
        search_manifests=bundle["search_manifests"],
        config=bundle["config"],
    )


def fixture_inputs() -> Stage4Inputs:
    sys.path.insert(0, os.path.join(STAGE4_DIR, "tests"))
    from fixtures import stage4_inputs  # test-support module; fixtures only

    return stage4_inputs()


def _run_and_report(inputs: Stage4Inputs, method: Any, outputs_root: str,
                    write_pointer: bool) -> int:
    result = run_pipeline(inputs, method)
    out_dir, manifest = emit(inputs, result, method, outputs_root)
    verification = verify_output_dir(out_dir, inputs, method)

    print(f"scorecard_set_id : {manifest['scorecard_set_id']}")
    print(f"output_dir       : {out_dir}")
    print(f"is_fixture       : {manifest['is_fixture']}")
    print(f"verification     : {verification['status']} "
          f"({verification['n_checks']} checks, {verification['n_failed']} failed)")
    print(f"environment lock : {manifest['environment']['lock_file']} "
          f"(matches runtime: {manifest['environment']['observed_matches_lock']})")

    with open(os.path.join(out_dir, "selection.json"), encoding="utf-8") as fh:
        selection = json.load(fh)
    print(f"selection        : {selection['selection_status']} (no ranking is emitted)")

    decision = production_pointer_decision(inputs, result)
    print(f"production ptr   : not written — {len(decision['refusals'])} refusal(s)")
    for r in decision["refusals"]:
        print(f"                   - {r}")

    if write_pointer:
        try:
            write_production_pointer(outputs_root, inputs, result, manifest["scorecard_set_id"])
        except ProductionGateRefusal as exc:
            print(f"\nREFUSED: {exc}", file=sys.stderr)
            return 3

    if verification["status"] != "pass":
        for c in verification["checks"]:
            if c["status"] == "fail":
                print(f"FAIL {c['check_id']}: {c['detail']}", file=sys.stderr)
        return 1

    if manifest["is_fixture"]:
        print("\nThis is a FIXTURE run. No real drug is characterised, ranked, or claimed to "
              "be safe, brain-permeable or NEBPI-classified.")
    return 0


def _emit_receipt(receipt: dict[str, Any], path: Optional[str]) -> None:
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(receipt, fh, indent=2, sort_keys=True)
            fh.write("\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


def run_stage3_door(bundle_path: str, evidence_path: Optional[str], outputs_root: str,
                    receipt_out: Optional[str], write_pointer: bool, method: Any) -> int:
    """The only door a real Stage-3 emission comes through."""
    admission = adapt(*load_stage3_bundle(bundle_path))
    i = admission.inspection

    # A research annotation is inspected, never admitted. Stage 3 says so itself.
    if admission.candidate_set is None:
        _emit_receipt(
            admission_receipt(
                admission, ran=False,
                reason_code="inspection_only" if i.stage3_namespace == "research_only"
                else "no_admissible_candidate",
                reason=i.refusal_reason or "no candidate was admitted",
            ),
            receipt_out,
        )
        return 0

    if not evidence_path:
        _emit_receipt(
            admission_receipt(
                admission, ran=False, reason_code="no_evidence_bundle_supplied",
                reason=(
                    f"{i.admitted_as_candidates} candidate(s) admitted from {i.stage3_document_id}, "
                    "but no --evidence-bundle was supplied. Stage 4 characterises molecules "
                    "against acquired public-source observations; it does not manufacture them. "
                    "Running with empty lanes would emit an artifact that reads like a result "
                    "and contains none, so no scorecard set is written."
                ),
            ),
            receipt_out,
        )
        return 0

    inputs = stage3_inputs(admission, evidence_path)
    print(f"stage3 admission : {i.admitted_as_candidates} candidate(s) from "
          f"{i.stage3_document_id} (namespace={i.stage3_namespace})")
    return _run_and_report(inputs, method, outputs_root, write_pointer)


def annotation_receipt(admission: AnnotationAdmission, ran: bool, reason_code: str,
                       reason: str) -> dict[str, Any]:
    """What was queued, what was not, and the exact bytes it all rests on."""
    return {
        "schema_id": RECEIPT_SCHEMA,
        "adapter": ANNOTATION_ADAPTER_ID,
        "stage3": {
            "schema_version": admission.schema_version,
            "artifact_class": admission.artifact_class,
            "bundle_id": admission.bundle_id,
            "document_sha256": admission.document_sha256,
            "canonical_content_sha256": admission.canonical_content_sha256,
            "manifest_sha256": admission.manifest_sha256,
            "data_status": admission.data_status,
        },
        "admission": {
            "candidates_in_bundle": admission.n_candidates_in_bundle,
            "queued": admission.admitted_as_candidates,
            "not_queued": admission.not_queued,
            "not_queued_reasons": admission.not_queued_reasons,
            "refusal_reason": admission.refusal_reason,
        },
        # Independent hypotheses, carried without collapse. No combined rank exists.
        "arm_evidence_states": {
            q.candidate_id: [
                {"desired_arm": a.desired_arm, "origin_type": a.origin_type,
                 "arm_evidence_state": a.arm_evidence_state}
                for a in q.arm_evidence_states
            ]
            for q in admission.queued
        },
        "inverse_direction_hypotheses": {
            q.candidate_id: q.inverse_direction_hypothesis_arms
            for q in admission.queued if q.inverse_direction_hypothesis_arms
        },
        # A COMPLETABLE disease-context review, reported verbatim. `pending` is not reviewed;
        # `insufficient` is not a soft yes. Stage 4 interprets none of it.
        "disease_context_review": {
            q.candidate_id: {
                "status": q.disease_context_review.status,
                "result": q.disease_context_review.result,
                "reason": q.disease_context_review.reason,
                "reviewed_by": q.disease_context_review.reviewed_by,
                "evidence_refs": q.disease_context_review.evidence_refs,
            }
            for q in admission.queued
        },
        # Typed REFERENCES. Never dereferenced, embedded or summarised by Stage 4.
        "science_evidence_refs": (admission.queued[0].science_evidence_refs
                                  if admission.queued else []),
        "stage4_run": {"scorecards_emitted": ran, "reason_code": reason_code,
                       "reason": reason},
        "hard_rules": [
            "Only rows with stage4_assessment_status=queued are assessed.",
            "A Stage-4 assessment is not biological promotion and not a recommendation.",
            "away_from_A and toward_B stay separate: no combined rank, no headline arm.",
            "An inverse-direction hypothesis is never observed gain of function, and is "
            "pending a Claude Science plausibility review.",
            "A pathway_node result is never reported as a measured one.",
            "A production pointer can never be written from a Stage-3 assessment.",
        ],
    }


def run_annotation_door(bundle_path: str, evidence_path: Optional[str], outputs_root: str,
                        receipt_out: Optional[str], write_pointer: bool, method: Any) -> int:
    """The only door from Stage 3's spot.stage03_drug_annotation.v1 into Stage 4."""
    admission = adapt_annotation_bundle(bundle_path)

    if admission.candidate_set is None:
        _emit_receipt(
            annotation_receipt(admission, ran=False, reason_code="no_queued_candidate",
                               reason=admission.refusal_reason or "no candidate was queued"),
            receipt_out)
        return 0

    if not evidence_path:
        _emit_receipt(
            annotation_receipt(
                admission, ran=False, reason_code="no_evidence_bundle_supplied",
                reason=(
                    f"{admission.admitted_as_candidates} queued candidate(s) admitted from "
                    f"{admission.bundle_id}, but no --evidence-bundle was supplied. Stage 4 "
                    "characterises molecules against acquired public-source observations; it "
                    "does not manufacture them.")),
            receipt_out)
        return 0

    inputs = stage3_inputs(admission, evidence_path)
    print(f"stage3 annotation: {admission.admitted_as_candidates} of "
          f"{admission.n_candidates_in_bundle} candidate(s) queued from "
          f"{admission.bundle_id} (artifact_class=analysis)")
    print(f"                   {admission.not_queued} not queued by Stage 3")
    return _run_and_report(inputs, method, outputs_root, write_pointer)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="run_stage4", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage3-bundle",
                    help="a real Stage-3 emission: the bundle directory, or the document in it")
    ap.add_argument("--stage3-annotation-bundle",
                    help="a Stage-3 spot.stage03_drug_annotation.v1 bundle directory "
                         "(artifact_class=analysis). Admits only rows with "
                         "stage4_assessment_status=queued. An assessment is not promotion.")
    ap.add_argument("--evidence-bundle",
                    help="a spot.stage04_evidence_bundle.v1 document of acquired observations")
    ap.add_argument("--fixtures", action="store_true",
                    help="run the engine on its own labelled internal fixtures")
    ap.add_argument("--receipt-out", help="write the Stage-3 admission receipt here")
    ap.add_argument("--outputs-root", default=DEFAULT_OUTPUTS_ROOT)
    ap.add_argument("--write-production-pointer", action="store_true",
                    help="attempt to advertise this run as the production scorecard set (will refuse)")
    args = ap.parse_args(argv)

    doors = [bool(args.stage3_bundle), bool(args.stage3_annotation_bundle),
             bool(args.fixtures)]
    if sum(doors) != 1:
        print("REFUSED [no_input] supply exactly one of --stage3-bundle, "
              "--stage3-annotation-bundle or --fixtures", file=sys.stderr)
        return 2

    method = load_method_bundle()
    try:
        if args.stage3_annotation_bundle:
            return run_annotation_door(args.stage3_annotation_bundle, args.evidence_bundle,
                                       args.outputs_root, args.receipt_out,
                                       args.write_production_pointer, method)
        if args.stage3_bundle:
            return run_stage3_door(args.stage3_bundle, args.evidence_bundle, args.outputs_root,
                                   args.receipt_out, args.write_production_pointer, method)
        return _run_and_report(fixture_inputs(), method, args.outputs_root,
                               args.write_production_pointer)
    except Rejection as exc:
        print(f"REFUSED [{exc.code}] {exc.detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
