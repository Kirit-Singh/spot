"""Stage-4 CLI.

    python -m analysis.run_stage4 --fixtures --outputs-root 04_PKPD/outputs
    python -m analysis.run_stage4 --stage3-annotation-bundle <dir> --evidence-bundle <json> \
        --require-external-verifier --outputs-root 04_PKPD/outputs
    python -m analysis.run_stage4 --stage3-bundle <dir-or-document> [--evidence-bundle <json>]

The CURRENT frozen-Stage-3 door is --stage3-annotation-bundle
(`spot.stage03_drug_annotation.v1`, r8 e5aa666). For a REAL run add --require-external-verifier
so admission runs BOTH gates — Stage-4's own byte restatement AND Stage-3's
`verifier.verify_stage3` (gate 2, out-of-process) — with the Stage-3 build context in
SPOT_STAGE3_VERIFIER_ROOT / SPOT_STAGE3_CACHE_ROOT / SPOT_STAGE3_DIRECT_RUN /
SPOT_STAGE3_DIRECT_INPUTS_ROOT (+ optional SPOT_STAGE3_DIRECT_ANALYSIS). Without the flag the
bundle is admitted on gate 1 alone and the run is NOT a data-bound integration.

The doors, and no others:

  --stage3-membership-receipt + --stage3-membership-bundle
                    NATIVE v2. W16's `spot.stage03_membership_receipt.v1`, READ FROM DISK: every
                    hash it states is recomputed, and the hash-bound selection view it names is
                    what gets projected -- never a copy the caller passes in. A production pointer
                    is REFUSED for a fixture BY NAME (`stage3_bundle_is_a_fixture`).

  --stage3-annotation-bundle  the current frozen-Stage-3 contract. Admits only rows with
                    stage4_assessment_status=queued; an assessment is not promotion. With
                    --require-external-verifier a bundle Stage-3's own verifier never passed is
                    REFUSED (exit 2). A real evidence bundle is still required to emit scorecards.

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
from .membership_door import run_membership_door
from .contract_version import SCHEMA_TO_VERSION, ContractVersion
from .method_config import STAGE4_DIR, MethodBundle, load_method_bundle
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


def method_for_contract(version: ContractVersion) -> MethodBundle:
    """The method bundle the ADMITTED contract requires.

    A v2 run MUST bind the v2 method. `safety_taxonomy_v2.prohibited_outputs_v2.
    additional_forbidden_field_names` is where the nested no-p/q firewall lives — `p_value`,
    `q_value`, `fdr`, `adjusted_p`, and the organ/toxicity score names. Load v1 for a v2 run and
    none of them is forbidden: the firewall is not weakened, it is ABSENT, and a nested `p_value`
    sails straight through. Stage 4 computes no statistic and consumes none; a forbidden-field
    list that was never loaded is not a list.

    v1 keeps exactly its seven frozen files. A v2 addition may never reach into it — those bytes
    are hashed into the identity of every release ever emitted.
    """
    return load_method_bundle(version=version)


def contract_of_evidence_bundle(path: Optional[str]) -> ContractVersion:
    """The contract the bundle DECLARES. Nothing is inferred, and no bundle means v1.

    An unrecognised schema is left to `load_evidence_bundle`, which refuses it by name — reading
    the id here is only how the method gets chosen, never how a bundle gets admitted.
    """
    if not path or not os.path.exists(path):
        return ContractVersion.V1
    try:
        with open(path, encoding="utf-8") as fh:
            schema = (json.load(fh) or {}).get("schema_id")
    except (OSError, json.JSONDecodeError):
        return ContractVersion.V1        # the door will refuse it, with a better message
    return SCHEMA_TO_VERSION.get(str(schema), ContractVersion.V1)


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
        # v2 lanes. A v1 bundle has neither, and the profile refuses a v1 bundle that carries
        # one -- the v1 digest would not cover it.
        fraction_unbound=bundle.get("fraction_unbound", []),
        acquisitions=bundle.get("source_acquisition", []),
        config=bundle["config"],
        # The bundle declares its contract; the run speaks that contract. `run_pipeline` then
        # refuses a v2 bundle that does not actually carry it.
        contract_version=bundle["contract_version"],
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
                        receipt_out: Optional[str], write_pointer: bool, method: Any,
                        require_external_verifier: bool = False) -> int:
    """The only door from Stage 3's spot.stage03_drug_annotation.v1 into Stage 4.

    `require_external_verifier=True` is the REAL-run setting: it refuses a bundle that Stage
    3's own `verifier.verify_stage3` (gate 2) has not actually passed. The Rejection it raises
    is caught by `main`, which prints `REFUSED [stage3_external_verifier_not_run]` and exits 2.
    """
    admission = adapt_annotation_bundle(
        bundle_path, require_external_verifier=require_external_verifier)

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
    ap.add_argument("--stage3-membership-receipt",
                    help="NATIVE v2: the path to W16's spot.stage03_membership_receipt.v1 on disk. "
                         "Its bytes are read and every hash it states is recomputed; a receipt "
                         "handed over in memory is refused.")
    ap.add_argument("--stage3-membership-bundle",
                    help="NATIVE v2: the bundle directory the receipt's `view.path` resolves "
                         "against. Required with --stage3-membership-receipt: without it nothing "
                         "the receipt names could be re-hashed.")
    ap.add_argument("--stage3-store-dir",
                    help="NATIVE v2, optional: the directory holding the store's parquet. Supplied "
                         "-> the corroborating tables are re-hashed against store.table_hashes and "
                         "the projection may claim the global store.")
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
    ap.add_argument("--require-external-verifier", action="store_true",
                    help="a REAL run: require Stage-3's own verifier.verify_stage3 (gate 2) to "
                         "have actually PASSED before admitting the bundle. Needs the Stage-3 "
                         "build context in SPOT_STAGE3_VERIFIER_ROOT / SPOT_STAGE3_CACHE_ROOT / "
                         "SPOT_STAGE3_DIRECT_RUN / SPOT_STAGE3_DIRECT_INPUTS_ROOT "
                         "(+ optional SPOT_STAGE3_DIRECT_ANALYSIS). Refuses if gate 2 did not run.")
    args = ap.parse_args(argv)

    doors = [bool(args.stage3_bundle), bool(args.stage3_annotation_bundle),
             bool(args.fixtures), bool(args.stage3_membership_receipt)]
    if sum(doors) != 1:
        print("REFUSED [no_input] supply exactly one of --stage3-bundle, "
              "--stage3-annotation-bundle or --fixtures", file=sys.stderr)
        return 2

    # The method is chosen by the contract the evidence bundle DECLARES — binding v1 for a
    # v2 run would leave the nested no-p/q firewall unloaded.
    method = method_for_contract(contract_of_evidence_bundle(args.evidence_bundle))
    try:
        # A verification flag may NEVER be silently ignored.
        #
        # `--require-external-verifier` reached only the annotation door. The wire door and the
        # fixture door accepted the flag, dropped it, and exited 0 — so a caller who asked for
        # Stage 3's own verifier to have passed was told the run succeeded when the gate had never
        # been consulted at all. A gate that is quietly skipped is worse than one that is absent:
        # the operator believes it ran.
        #
        # The wire door has no external-verifier context to consult, so the combination is refused
        # BY NAME rather than honoured-in-appearance.
        if args.require_external_verifier and not args.stage3_annotation_bundle:
            door = "--stage3-bundle" if args.stage3_bundle else "--fixtures"
            raise Rejection(
                "external_verifier_not_applicable_to_this_door",
                f"--require-external-verifier was given with {door}, which has no Stage-3 "
                "external-verifier context to consult. This flag is only meaningful on "
                "--stage3-annotation-bundle, the door a real Stage-3 bundle comes through. It is "
                "refused rather than ignored: a verification you asked for and did not get, "
                "reported as success, is the worst of the three outcomes.",
            )

        if args.stage3_membership_receipt:
            if not args.stage3_membership_bundle:
                print("REFUSED [stage3_membership_bundle_required] --stage3-membership-receipt "
                      "needs --stage3-membership-bundle: without the bundle nothing the receipt "
                      "names could be re-hashed, and a receipt is a claim ABOUT bytes.")
                return 2
            return run_membership_door(args.stage3_membership_receipt,
                                       args.stage3_membership_bundle, args.outputs_root,
                                       args.write_production_pointer, args.stage3_store_dir)
        if args.stage3_annotation_bundle:
            return run_annotation_door(args.stage3_annotation_bundle, args.evidence_bundle,
                                       args.outputs_root, args.receipt_out,
                                       args.write_production_pointer, method,
                                       require_external_verifier=args.require_external_verifier)
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
