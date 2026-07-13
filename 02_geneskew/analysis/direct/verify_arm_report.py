"""The TYPED verification report for a Direct all-arm bundle, and the frozen constants.

INDEPENDENCE RULE (test-enforced): imports nothing from the generator.

The report is BOUND to the artifact it is about — the run id, the arm bytes, the on-disk
hashes and the exact arm inventory — and to the CODE that produced it. A verdict that did
not say which checker, over which bytes, under which gates, is a claim rather than a
result, and Stage 3 consumes this as a contract.
"""
from __future__ import annotations

import os
import sys
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import verify_arm_rules as AR  # noqa: E402

VERIFIER_ID = "spot.stage02.direct.arm_bundle.verifier.v1"
REPORT_SCHEMA = "spot.stage02_direct_arm_bundle_verification.v1"
SPEC_SHA256 = "c477356278c5b7d2842659f5354792c9db7203ee774f8dd70653921124477a9f"

BUNDLE_FILE = "arm_bundle.json"
PROVENANCE_FILE = "provenance.json"
ROWS_FILE = "arms.parquet"
MASKS_FILE = "masks.parquet"
CONTRIB_FILE = "contributing_guides.parquet"
GUIDE_SUPPORT_FILE = "guide_support.parquet"
DONOR_SUPPORT_FILE = "donor_support.parquet"
INPUTS_FILE = "input_manifest.json"
UNIVERSE_FILE = "gene_universe.json"
TARGET_IDENTITY_FILE = "target_identity.json"
VERIFICATION_FILE = "verification.json"

EXPECTED_FILES = {BUNDLE_FILE, PROVENANCE_FILE, ROWS_FILE, MASKS_FILE, CONTRIB_FILE,
                  GUIDE_SUPPORT_FILE, DONOR_SUPPORT_FILE, INPUTS_FILE, UNIVERSE_FILE,
                  TARGET_IDENTITY_FILE, VERIFICATION_FILE}

BUNDLE_SCHEMA = "spot.stage02_direct_arm_bundle.v1"
REQUEST_SCHEMA = "spot.stage02_arm_bundle_request.v1"
PROVENANCE_SCHEMA = "spot.stage02_arm_bundle_provenance.v1"
VERIFICATION_SCHEMA = "spot.stage02_arm_bundle_verification.v1"
RUNNER_ID = "spot.stage02.direct.all_arm_runner.v1"
BUNDLE_RUN_ID_LEN = 16

# The verdict the PRODUCER writes into verification.json. It is not a verdict — it is the
# slot this verifier fills. A bundle that arrived already admitting itself is refused: a
# generator that signs its own homework is the same process asserting twice.
VERDICT_PENDING = "pending_independent_verification"

LANES = ("production", "research_only", "synthetic")
RELEASE_LANES = ("production", "research_only")
INFERENCE_STATUS = "not_calibrated"

# The MODULES this verifier IS. Hashed into every report, so a verdict cannot be
# attributed to code that did not produce it — and a weakened checker cannot pass itself
# off as this one.
VERIFIER_MODULES = ("verify_arm_bundle.py", "verify_arm_gates.py",
                    "verify_arm_report.py", "verify_arm_rules.py",
                    "verify_arm_science.py", "verify_arm_view.py",
                    "verify_arm_recompute.py", "verify_direct_release.py",
                    "verify_target_identity.py")
# The producer modules this verifier may never import. ASSERTED against its own source at
# run time (see verify_arm_gates.gate_independence), never merely promised here.
FORBIDDEN_IMPORTS = ("direct.arm_bundle", "direct.run_arms", "direct.scorer_view",
                     "direct.arm_keys", "direct.hashing", "direct.masks",
                     "direct.projection", "direct.disposition")


def verifier_code_sha256() -> str:
    """WHICH checker ran. A report that did not name its own code is unfalsifiable."""
    return AR.content_sha256(
        {m: AR.sha256_file(os.path.join(_HERE, m)) for m in sorted(VERIFIER_MODULES)})


class Report:
    """A TYPED verification report, bound to the artifact it is about."""

    def __init__(self, verifier_code_sha256: str):
        self.gates: list[dict[str, Any]] = []
        self.verifier_code_sha256 = verifier_code_sha256
        self.bound: dict[str, Any] = {}

    def gate(self, name: str, ok: bool, detail: str = "") -> bool:
        self.gates.append({"gate": name, "passed": bool(ok), "detail": str(detail)})
        return bool(ok)

    @property
    def failed(self) -> list[str]:
        return [g["gate"] for g in self.gates if not g["passed"]]

    def doc(self) -> dict[str, Any]:
        names = [g["gate"] for g in self.gates]
        verdict = "ADMIT" if (self.gates and not self.failed) else "REFUSE"
        body = {
            "schema_version": REPORT_SCHEMA,
            "verifier_id": VERIFIER_ID,
            "spec_sha256": SPEC_SHA256,
            "verifier_code_sha256": self.verifier_code_sha256,
            "independent_of_generator": True,
            "generator_modules_not_imported": list(FORBIDDEN_IMPORTS),
            "gate_inventory": names,
            "gate_inventory_sha256": AR.content_sha256(names),
            "bound_artifact": self.bound,
            "gates": self.gates,
            "n_gates": len(self.gates),
            "n_passed": len(self.gates) - len(self.failed),
            "n_failed": len(self.failed),
            "failed_gates": self.failed,
            "verdict": verdict,
        }
        # CONTENT-ADDRESSED. The aggregate run manifest binds this hash, so a verdict
        # cannot be swapped for a friendlier one after the fact, and a report cannot be
        # re-attributed to a bundle it is not about. A report that could be edited after
        # it was cited is a claim, not a result.
        return dict(body, report_sha256=AR.content_sha256(body))

    def render(self) -> str:
        out = [f"  [{'PASS' if g['passed'] else 'FAIL'}] {g['gate']}"
               + (f" — {g['detail']}" if g["detail"] and not g["passed"] else "")
               for g in self.gates]
        doc = self.doc()
        out += ["", f"{doc['n_passed']}/{doc['n_gates']} gates passed",
                f"VERDICT: {doc['verdict']}"]
        return "\n".join(out)
