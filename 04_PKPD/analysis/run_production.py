"""The production substitution runner: the whole chain, fail-closed at the first honest stop.

    admit (BOTH gates)  ->  plan  ->  acquire  ->  materialize  ->  verify  ->  project

One command, six steps, and a single rule: **a step runs only if every step before it earned it.**
The runner does not "continue with what it has". A chain that skips a gate and reports the rest as
green is worse than no chain, because the artifact at the end looks exactly like one that was
earned.

### Why it stops today

It stops at STEP 1, and it must:

  * **Gate 2 has never passed.** `verifier.verify_stage3` re-derives Stage 3's output from Direct's
    screen and the pinned acquisition cache. That build context does not exist yet, so gate 2 is
    `not_run` — and `not_run` is not a pass. This runner sets `require_external_verifier=True`
    unconditionally: there is no flag that turns it off, because a production substitution admitted
    on Stage-4's restatement alone is not a production substitution.
  * **A fixture-class bundle can never reach production.** `artifact_class != analysis` is refused
    by the contract restatement (gate 1), however good its evidence looks.

Because step 1 refuses, **no request is ever put on the wire**. That is not a hope about ordering:
the runner constructs its HTTP client with `allow_network=False` until admission has passed, and
the tests drive it with a transport that raises if it is called at all.

Nothing here loosens either gate, and nothing prefetches from an unadmitted bundle: the plan is
built from the ADMITTED tables, and there are none until admission returns.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

from .acquire_cache import RequestCache
from .acquire_http import Client
from .acquire_plan import plan_document, plan_queue
from .acquisition import RunRoot
from .firewall import Rejection
from .stage3_admission import PASSED, admit
from .stage3_contract_v2 import ANALYSIS_CLASS

MAX_CONCURRENCY = 4
RECEIPT = "production_run_receipt.json"

STEPS = ("admit", "plan", "acquire", "materialize", "verify", "project")


@dataclass
class StepResult:
    step: str
    status: str                      # passed | refused | not_reached
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProductionRun:
    """What ran, what refused, and what was never reached. `not_reached` is not `passed`."""

    steps: list[StepResult] = field(default_factory=list)
    stopped_at: Optional[str] = None
    stop_code: Optional[str] = None
    stop_detail: str = ""

    def record(self, result: StepResult) -> None:
        self.steps.append(result)

    def stop(self, step: str, code: str, detail: str) -> None:
        self.stopped_at = step
        self.stop_code = code
        self.stop_detail = detail
        self.record(StepResult(step=step, status="refused", detail=detail))
        for later in STEPS[STEPS.index(step) + 1:]:
            self.record(StepResult(
                step=later, status="not_reached",
                detail=f"the chain stopped at {step!r}. A step that was never reached is not a "
                       "step that passed."))

    @property
    def produced_an_artifact(self) -> bool:
        return self.stopped_at is None

    def document(self) -> dict[str, Any]:
        return {
            "schema_id": "spot.stage04_production_run_receipt.v1",
            "chain": list(STEPS),
            "steps": [
                {"step": s.step, "status": s.status, "detail": s.detail, **(
                    {"data": s.data} if s.data else {})}
                for s in self.steps
            ],
            "stopped_at": self.stopped_at,
            "stop_code": self.stop_code,
            "stop_detail": self.stop_detail,
            "produced_an_artifact": self.produced_an_artifact,
            "hard_rules": [
                "A step runs only if every step before it earned it. `not_reached` is not `passed`.",
                "Gate 2 (verifier.verify_stage3) is MANDATORY here and has no off switch. "
                "`not_run` is a refusal.",
                "artifact_class must be `analysis`. A fixture-class bundle never reaches "
                "production, however good its evidence looks.",
                "No request reaches the network before admission passes.",
                "No drug is ranked, scored, selected or recommended, and no PK value is invented.",
            ],
        }


def run_production(bundle_dir: str, run_root_dir: str, *, out_bundle: str,
                   outputs_root: str, client: Optional[Client] = None,
                   max_workers: int = MAX_CONCURRENCY) -> ProductionRun:
    """The chain. It returns a receipt whatever happens; it never returns a half-truth."""
    run = ProductionRun()

    # ---- STEP 1: admission. BOTH gates, and gate 2 has no off switch here. ----------------
    try:
        admission = admit(bundle_dir, require_external_verifier=True)
    except Rejection as exc:
        run.stop("admit", exc.code, exc.detail)
        return run

    if admission.document.get("artifact_class") != ANALYSIS_CLASS:
        run.stop("admit", "stage3_artifact_class_not_analysis",
                 f"artifact_class={admission.document.get('artifact_class')!r}. A fixture-class "
                 "bundle never reaches production.")
        return run
    if admission.external_verifier != PASSED:       # belt and braces: admit() already refuses
        run.stop("admit", "stage3_external_verifier_not_run",
                 f"external_verifier={admission.external_verifier!r}")
        return run

    run.record(StepResult(
        "admit", "passed",
        f"both gates: {', '.join(admission.gates)}",
        {"bundle_id": admission.bundle_id,
         "document_sha256": admission.document["document_sha256"],
         "external_verifier": admission.external_verifier}))

    # ---- STEP 2: plan. Built from the ADMITTED tables — never from unadmitted bytes. -------
    run_root = RunRoot(run_root_dir)
    plan = plan_document(plan_queue(client or Client(), admission.tables))
    run.record(StepResult("plan", "passed",
                          f"{plan['n_acquirable']}/{plan['n_candidates_queued']} queued candidate(s) "
                          f"acquirable, {plan['n_requests_total']} request(s)",
                          {"n_requests_total": plan["n_requests_total"]}))
    if plan["n_acquirable"] == 0:
        run.stop("acquire", "no_acquirable_candidate",
                 "the admitted bundle queued no candidate that any public source can be asked "
                 "about. There is nothing to acquire, and an empty acquisition is not a result.")
        return run

    # ---- STEP 3: acquisition. Network is permitted ONLY from here, after admission. --------
    from .run_acquire import run as run_acquire_step

    cache = RequestCache(run_root)
    http = client or Client(allow_network=True, cache=cache)
    try:
        _, acq_receipt = run_acquire_step(
            bundle_dir, run_root_dir, names=[], allow_network=True, setid=None,
            require_external_verifier=True, client=http, max_workers=max_workers,
            reuse_cache=True, acquire_queue=True)
    except Rejection as exc:
        run.stop("acquire", exc.code, exc.detail)
        return run
    run.record(StepResult("acquire", "passed",
                          f"fetched={acq_receipt['acquisition']['transport']['fetched']} "
                          f"reused={acq_receipt['acquisition']['transport']['reused_from_cache']}",
                          {"manifest_content_sha256":
                           acq_receipt["acquisition"]["manifest_content_sha256"]}))

    # ---- STEP 4: materialize the typed evidence bundle from what was ACTUALLY acquired -----
    from .run_materialize import main as materialize_main

    code = materialize_main(["--stage3-annotation-bundle", bundle_dir, "--run-root", run_root_dir,
                             "--out", out_bundle, "--contract", "v2"])
    if code != 0:
        run.stop("materialize", "materialization_failed",
                 f"run_materialize exited {code}")
        return run
    run.record(StepResult("materialize", "passed", f"evidence bundle at {os.path.basename(out_bundle)}"))

    # ---- STEP 5: score + emit + verify -----------------------------------------------------
    from .run_stage4 import main as stage4_main

    code = stage4_main(["--stage3-annotation-bundle", bundle_dir, "--evidence-bundle", out_bundle,
                        "--outputs-root", outputs_root, "--require-external-verifier"])
    if code != 0:
        run.stop("verify", "stage4_run_failed", f"run_stage4 exited {code}")
        return run
    run.record(StepResult("verify", "passed", "scorecards emitted and verified"))

    # ---- STEP 6: browser projection --------------------------------------------------------
    run.record(StepResult("project", "passed", "projection is emitted by the Stage-4 release"))
    return run


def main(argv: Optional[list[str]] = None, *, client: Optional[Client] = None) -> int:
    ap = argparse.ArgumentParser(prog="run_production", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage3-annotation-bundle", required=True,
                    help="the Stage-3 v2 artifact_class=analysis bundle")
    ap.add_argument("--run-root", required=True, help="OUTSIDE the working tree")
    ap.add_argument("--evidence-bundle-out", required=True)
    ap.add_argument("--outputs-root", required=True)
    ap.add_argument("--max-concurrency", type=int, default=MAX_CONCURRENCY)
    ap.add_argument("--receipt-out", help="write the production receipt here")
    args = ap.parse_args(argv)

    # NOTE there is no --skip-verifier, no --force, and no --allow-fixture. Their absence is the
    # feature: a production substitution that can be talked out of a gate is not one.
    run = run_production(
        args.stage3_annotation_bundle, args.run_root,
        out_bundle=args.evidence_bundle_out, outputs_root=args.outputs_root,
        client=client, max_workers=args.max_concurrency)

    doc = run.document()
    if args.receipt_out:
        with open(args.receipt_out, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
            fh.write("\n")

    for step in doc["steps"]:
        mark = {"passed": "PASS", "refused": "REFUSED", "not_reached": "not reached"}[step["status"]]
        print(f"  [{mark:^12}] {step['step']}: {step['detail']}")

    if run.stopped_at:
        print(f"\nREFUSED [{run.stop_code}] at step {run.stopped_at!r}: {run.stop_detail}",
              file=sys.stderr)
        print("No artifact was produced. A chain that stops is not a chain that failed — it is a "
              "chain that refused to manufacture a result it had not earned.", file=sys.stderr)
        return 2

    print("\nThe chain completed. No drug is ranked, and no PK value was invented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
