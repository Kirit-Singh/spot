"""THE NEUTRAL ADMISSION ADAPTER — one seam over the immutable native W10 report.

Step0, temporal, P2S, pathway and the aggregate run manifest all read the SAME Direct
admission through THIS module, instead of three ad-hoc field-pickings and a Markdown file
pinned by hash. A reader that normalises before comparing — `.upper()` on the verdict, a
regex over Markdown — has thrown away the only evidence it had.

THE NATIVE REPORT IS THE SOLE SOURCE, AND IT IS NOT TOUCHED
----------------------------------------------------------
W10's independent verifier emits `spot.stage02_direct_arm_bundle_verification.v1` (and the
release equivalent). This adapter does not change it, does not add fields to it, and does not
move the `verifier_code_sha256` that P2S pins. It READS the report and the bundle from disk
and DERIVES a normalized `spot.stage02.direct_admission_binding.v1` — every value in which was
re-hashed or re-derived from bytes, never copied and trusted from the report.

INDEPENDENCE RULE (test-enforced): imports nothing from the PRODUCER. It reuses W10's own
verifier modules (its canonical mask projection, its hash function) because those are the same
lane; it never imports `run_arms`, `arm_bundle`, `masks` or any generator module.

WHAT THE ADAPTER RE-DERIVES AND WHAT IT REFUSES
-----------------------------------------------
  * the self-hash, re-computed from the report body — a report edited after it was cited;
  * the verdict token, byte-exact ADMIT / REFUSE — no case-fold, no guess;
  * an ADMIT that carries failed gates — a verdict against its own evidence;
  * a self-admission — the producer's pending slot handed in as a verdict;
  * the report is W10's — pinned verifier_id + spec, so another checker cannot pass as W10;
  * every bundle file, re-hashed from disk against the report's claim — a stale/swapped bundle;
  * the mask, re-derived from the shipped masks.parquet and cross-checked against the bundle's
    own binding — a bundle whose mask table was edited;
  * the environment lock, against the hard pin — a different environment;
  * the condition, against the bundle's own provenance — a report about another context.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import verify_arm_science as S  # noqa: E402  (W10's own canonical mask projection)

# THE VERSION-LOCKED PINS — ids, spec, code hash, solver lock, required gates. Restated in
# their own module (verify_arm_contract_pins), never borrowed from the verifier's live
# constants: a pin the adapter took from the thing it normalises is a pin nobody checked.
from verify_arm_contract_pins import (  # noqa: E402
    PINNED_SOLVER_LOCK_SHA256,
    REQUIRED_GATES,
    W10_SPEC_SHA256,
    W10_VERIFIER_CODE_SHA256,
    W10_VERIFIER_ID_BUNDLE,
    W10_VERIFIER_ID_RELEASE,
)
from verify_arm_rules import content_sha256, sha256_file  # noqa: E402

BINDING_SCHEMA = "spot.stage02.direct_admission_binding.v1"
SCHEMA_PATH = os.path.join(
    _HERE, "schemas", "stage02_direct_admission_binding.schema.json")

SCHEMA_BUNDLE = "spot.stage02_direct_arm_bundle_verification.v1"
SCHEMA_RELEASE = "spot.stage02_direct_release_verification.v1"
SCHEMAS = (SCHEMA_BUNDLE, SCHEMA_RELEASE)

VERDICT_ADMIT = "ADMIT"
VERDICT_REFUSE = "REFUSE"
VERDICTS = (VERDICT_ADMIT, VERDICT_REFUSE)
SELF_ADMISSION_VERDICT = "pending_independent_verification"
ADMITTED = "admitted"
REFUSED = "refused"

SELF_HASH_FIELD = "report_sha256"
BUNDLE_PROVENANCE_FILE = "provenance.json"
MASKS_FILE = "masks.parquet"

REQUIRED_TOP = (
    "schema_version", "verifier_id", "spec_sha256", "verifier_code_sha256",
    "independent_of_generator", "gate_inventory", "gate_inventory_sha256",
    "n_gates", "n_passed", "n_failed", "failed_gates", "verdict", "bound_artifact",
    "report_sha256",
)
REQUIRED_BUNDLE_PROVENANCE = (
    "arm_bundle_run_id", "condition", "lane", "arm_rows_sha256",
    "solver_lock_sha256", "artifact_sha256",
)
# A RELEASE lane binds the Stage-1 v3 release, so its scorer-view identity must be present.
# A synthetic bundle has no bound release and legitimately carries a null there.
RELEASE_LANES = ("production", "research_only")
REQUIRED_RELEASE_PROVENANCE = (
    "direct_release_run_id", "expected_conditions",
    "stage1_scorer_view_canonical_sha256", "solver_lock_sha256", "bundles",
)

REFUSE_NOT_A_DOCUMENT = "the_report_is_not_a_json_object"
REFUSE_UNREADABLE = "the_report_is_not_readable_json"
REFUSE_MISSING_FIELD = "the_report_is_missing_a_required_field"
REFUSE_UNKNOWN_SCHEMA = "the_report_declares_an_unrecognised_schema_version"
REFUSE_SELF_HASH = "the_report_does_not_hash_to_its_own_content"
REFUSE_UNKNOWN_VERDICT = "the_verdict_token_is_not_byte_exactly_admit_or_refuse"
REFUSE_ADMIT_WITH_FAILURES = "an_admit_report_carries_failed_gates"
REFUSE_SELF_ADMITTED = "the_report_is_the_producers_self_admission_slot"
REFUSE_NOT_INDEPENDENT = "the_report_does_not_declare_generator_is_not_verifier"
REFUSE_WRONG_VERIFIER = "the_report_is_not_from_the_pinned_w10_verifier"
REFUSE_SPEC_DRIFT = "the_report_was_written_against_a_different_spec"
REFUSE_GATE_INVENTORY = "the_gate_inventory_hash_does_not_re_derive"
REFUSE_WRONG_CODE = "the_report_is_not_from_the_pinned_w10_verifier_code"
REFUSE_GATE_COUNTS = "the_gate_counts_do_not_agree_with_the_gate_list"
REFUSE_GATE_MISSING = "a_security_critical_gate_is_absent_from_the_inventory"
REFUSE_MISSING_PROVENANCE = "the_report_is_missing_a_required_provenance_binding"
REFUSE_WRONG_ENV = "the_environment_lock_is_not_the_pinned_stage2_lock"
REFUSE_BUNDLE_BYTES = "a_bundle_file_on_disk_does_not_hash_to_the_admitted_value"
REFUSE_MASK = "the_masks_parquet_does_not_re_derive_the_bound_mask_identity"
REFUSE_CONDITION = "the_report_condition_is_not_the_bundle_condition"
REFUSE_BUNDLE_MISSING = "the_direct_bundle_is_not_on_disk"


class ContractError(ValueError):
    """The report does not satisfy the contract. Refuse; never normalise and proceed."""

    def __init__(self, reason: str, message: str):
        super().__init__(f"[{reason}] {message}")
        self.reason = reason


def _refuse(reason: str, message: str):
    raise ContractError(reason, message)


def _expected_verifier_id(schema_version: str) -> str:
    return (W10_VERIFIER_ID_BUNDLE if schema_version == SCHEMA_BUNDLE
            else W10_VERIFIER_ID_RELEASE)


def validate_report(report: Any) -> None:
    """Fail-closed validation of the NATIVE W10 report envelope. Raises ContractError.

    The native shape is NOT altered — this reads it as it is.
    """
    if not isinstance(report, dict):
        _refuse(REFUSE_NOT_A_DOCUMENT,
                f"expected a JSON object, got {type(report).__name__}")

    missing = [f for f in REQUIRED_TOP if f not in report]
    if missing:
        _refuse(REFUSE_MISSING_FIELD, f"required field(s) absent: {missing}")

    schema_version = report["schema_version"]
    if schema_version not in SCHEMAS:
        _refuse(REFUSE_UNKNOWN_SCHEMA,
                f"schema_version {schema_version!r} is not one of {list(SCHEMAS)}")

    # THE SELF-HASH, re-derived from the body — never read and trusted.
    declared = report[SELF_HASH_FIELD]
    body = {k: v for k, v in report.items() if k != SELF_HASH_FIELD}
    derived = content_sha256(body)
    if not declared or declared != derived:
        _refuse(REFUSE_SELF_HASH,
                f"declared {str(declared)[:16]}... but the body hashes to {derived[:16]}...")

    if report.get("independent_of_generator") is not True:
        _refuse(REFUSE_NOT_INDEPENDENT,
                "independent_of_generator is not true; a report that will not assert "
                "generator != verifier is not an independent admission")

    if report.get("verifier_id") is None or report["verdict"] == SELF_ADMISSION_VERDICT:
        _refuse(REFUSE_SELF_ADMITTED,
                f"verifier_id={report.get('verifier_id')!r} verdict={report['verdict']!r} "
                "— this is the producer's un-filled slot, not an independent verdict")

    if report["verifier_id"] != _expected_verifier_id(schema_version):
        _refuse(REFUSE_WRONG_VERIFIER,
                f"the report is signed {report['verifier_id']!r}, not the pinned W10 "
                f"verifier {_expected_verifier_id(schema_version)!r}")

    if report.get("spec_sha256") != W10_SPEC_SHA256:
        _refuse(REFUSE_SPEC_DRIFT,
                f"the report was written against spec "
                f"{str(report.get('spec_sha256'))[:16]}..., not the pinned "
                f"{W10_SPEC_SHA256[:16]}...")

    # WHICH CODE ran. A weakened fork keeps the id; it cannot keep the code hash.
    if report.get("verifier_code_sha256") != W10_VERIFIER_CODE_SHA256:
        _refuse(REFUSE_WRONG_CODE,
                f"the report was produced by verifier code "
                f"{str(report.get('verifier_code_sha256'))[:16]}..., not the pinned "
                f"{W10_VERIFIER_CODE_SHA256[:16]}...")

    verdict = report["verdict"]
    if verdict not in VERDICTS:
        _refuse(REFUSE_UNKNOWN_VERDICT,
                f"verdict {verdict!r} is not byte-exactly one of {list(VERDICTS)}")

    if verdict == VERDICT_ADMIT and (
            int(report.get("n_failed") or 0) != 0 or (report.get("failed_gates") or [])):
        _refuse(REFUSE_ADMIT_WITH_FAILURES,
                f"ADMIT with n_failed={report.get('n_failed')!r} "
                f"failed_gates={report.get('failed_gates')!r}")

    inv = report.get("gate_inventory") or []
    gates = report.get("gates") or []
    if content_sha256(inv) != report.get("gate_inventory_sha256"):
        _refuse(REFUSE_GATE_INVENTORY,
                "gate_inventory_sha256 does not re-derive from the gate inventory")

    # COUNT CONSISTENCY. n_gates=999 with a 77-gate list, an empty list with n_gates=0, a
    # padded n_passed — all internally plausible until the counts are checked against the
    # list they claim to summarise. The inventory IS the gate names, in order.
    gate_names = [g.get("gate") for g in gates if isinstance(g, dict)]
    passed = [g for g in gates if isinstance(g, dict) and g.get("passed")]
    failed_names = [g.get("gate") for g in gates
                    if isinstance(g, dict) and not g.get("passed")]
    if not (int(report["n_gates"]) == len(inv) == len(gates)):
        _refuse(REFUSE_GATE_COUNTS,
                f"n_gates={report['n_gates']} but the inventory has {len(inv)} names and "
                f"{len(gates)} gate records")
    if gate_names != inv:
        _refuse(REFUSE_GATE_COUNTS,
                "the gate records are not the gate inventory, in order")
    if int(report["n_passed"]) != len(passed) \
            or int(report["n_failed"]) != len(failed_names) \
            or int(report["n_passed"]) + int(report["n_failed"]) != len(gates):
        _refuse(REFUSE_GATE_COUNTS,
                f"n_passed={report['n_passed']}/n_failed={report['n_failed']} do not agree "
                f"with {len(passed)} passed / {len(failed_names)} failed records")
    if sorted(report.get("failed_gates") or []) != sorted(failed_names):
        _refuse(REFUSE_GATE_COUNTS,
                "failed_gates does not match the gates that record passed=false")

    # THE SECURITY-CRITICAL GATES MUST HAVE RUN. An empty inventory, or a resealed deletion
    # of the mask / env / bytes gate, leaves an internally-consistent report that never
    # checked the thing that matters. Pinning the code sha says the report NAMES the right
    # code; this says its inventory CONTAINS the checks that code is supposed to run.
    required = REQUIRED_GATES.get(report["verifier_id"], ())
    haystack = "\n".join(str(n) for n in inv)
    absent = [r for r in required if r not in haystack]
    if absent:
        _refuse(REFUSE_GATE_MISSING,
                f"{len(absent)} security-critical gate(s) absent from the inventory: "
                f"{[a[:40] for a in absent[:3]]}")

    bound = report["bound_artifact"]
    if not isinstance(bound, dict):
        _refuse(REFUSE_MISSING_PROVENANCE, "bound_artifact is not an object")
    required = (REQUIRED_BUNDLE_PROVENANCE if schema_version == SCHEMA_BUNDLE
                else REQUIRED_RELEASE_PROVENANCE)
    absent = [f for f in required if f not in bound or bound.get(f) in (None, "")]
    if absent:
        _refuse(REFUSE_MISSING_PROVENANCE,
                f"bound_artifact does not name {absent}")

    if schema_version == SCHEMA_BUNDLE and \
            bound.get("solver_lock_sha256") != PINNED_SOLVER_LOCK_SHA256:
        _refuse(REFUSE_WRONG_ENV,
                f"the arms were computed under solver lock "
                f"{str(bound.get('solver_lock_sha256'))[:16]}..., not the pin "
                f"{PINNED_SOLVER_LOCK_SHA256[:16]}...")

    # A release-grade lane must name the Stage-1 scorer view its arms were projected under.
    if schema_version == SCHEMA_BUNDLE and bound.get("lane") in RELEASE_LANES \
            and not bound.get("stage1_scorer_view_canonical_sha256"):
        _refuse(REFUSE_MISSING_PROVENANCE,
                f"a {bound.get('lane')!r} bundle must name "
                "stage1_scorer_view_canonical_sha256; it is null")


def _rederive_mask_from_disk(bundle_dir: str) -> Optional[str]:
    """RE-DERIVE the mask identity from the shipped masks.parquet, in canonical order.

    The same projection W10's own science gate uses — reused, not re-implemented, so the two
    cannot drift. Returns None if the table is unreadable.
    """
    import pandas as pd

    path = os.path.join(bundle_dir, MASKS_FILE)
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    rows = [{c: (None if pd.isna(r[c]) else r[c]) for c in df.columns}
            for _, r in df.iterrows()]
    return content_sha256(S._canonical_mask_rows(rows))


def _verify_bundle_on_disk(report: dict, bundle_dir: str) -> dict[str, Any]:
    """Re-hash every bundle file and re-derive the mask. Fail-closed on any mismatch."""
    if not bundle_dir or not os.path.isdir(bundle_dir):
        _refuse(REFUSE_BUNDLE_MISSING, f"--bundle {bundle_dir!r} is not a directory")

    bound = report["bound_artifact"]
    claimed = dict(bound.get("artifact_sha256") or {})
    observed: dict[str, str] = {}
    drift = []
    for name, want in sorted(claimed.items()):
        p = os.path.join(bundle_dir, name)
        if not os.path.exists(p):
            drift.append(f"{name} (admitted, absent on disk)")
            continue
        got = sha256_file(p)
        observed[name] = got
        if got != want:
            drift.append(f"{name} (admitted {want[:12]}..., on disk {got[:12]}...)")
    if drift:
        _refuse(REFUSE_BUNDLE_BYTES,
                f"{len(drift)} bundle file(s) do not hash to the admitted value: "
                f"{drift[:3]}")

    # THE MASK, re-derived from masks.parquet AND cross-checked against the bundle's own
    # provenance binding — provenance ("what the run bound") plus masks.parquet ("the bytes").
    prov_path = os.path.join(bundle_dir, BUNDLE_PROVENANCE_FILE)
    bound_mask = None
    prov_condition = None
    prov_lock = None
    if os.path.exists(prov_path):
        with open(prov_path) as fh:
            prov = json.load(fh)
        rb = prov.get("run_binding") or {}
        bound_mask = rb.get("mask_sha256")
        prov_condition = rb.get("condition")
        prov_lock = (rb.get("environment_lock") or {}).get("sha256")

    rederived_mask = _rederive_mask_from_disk(bundle_dir)
    if bound_mask is not None and rederived_mask is not None \
            and rederived_mask != bound_mask:
        _refuse(REFUSE_MASK,
                f"masks.parquet re-derives {str(rederived_mask)[:16]}..., but the bundle "
                f"bound {str(bound_mask)[:16]}...")

    if prov_condition is not None and prov_condition != bound.get("condition"):
        _refuse(REFUSE_CONDITION,
                f"the report condition {bound.get('condition')!r} is not the bundle's own "
                f"{prov_condition!r}")

    if prov_lock is not None and prov_lock != PINNED_SOLVER_LOCK_SHA256:
        _refuse(REFUSE_WRONG_ENV,
                f"the bundle's provenance binds lock {str(prov_lock)[:16]}..., not the pin")

    return {"artifact_sha256": observed,
            "mask_sha256": rederived_mask if rederived_mask is not None else bound_mask}


def normalize(report: dict, bundle_dir: Optional[str] = None) -> dict[str, Any]:
    """Derive the normalized `spot.stage02.direct_admission_binding.v1`. Self-hashed.

    With ``bundle_dir``, every bundle file is re-hashed and the mask re-derived from disk;
    without it, the binding carries only what the (validated) report claimed and
    ``bundle_verified_on_disk`` is false. A consumer that needs the on-disk guarantee must
    pass the bundle.
    """
    validate_report(report)
    bound = report["bound_artifact"]
    is_bundle = report["schema_version"] == SCHEMA_BUNDLE

    disk: dict[str, Any] = {"artifact_sha256": {}, "mask_sha256": None}
    verified = False
    if bundle_dir is not None and is_bundle:
        disk = _verify_bundle_on_disk(report, bundle_dir)
        verified = True

    binding = {
        "binding_schema": BINDING_SCHEMA,
        "source_report_sha256": content_sha256(
            {k: v for k, v in report.items() if k != SELF_HASH_FIELD}),
        "source_report_schema": report["schema_version"],
        "subject_kind": "bundle" if is_bundle else "release",
        "native_verdict": report["verdict"],              # byte-exact, not folded
        "disposition": ADMITTED if report["verdict"] == VERDICT_ADMIT else REFUSED,
        "verifier_id": report["verifier_id"],
        "verifier_code_sha256": report["verifier_code_sha256"],
        "spec_sha256": report["spec_sha256"],
        "bundle_id": bound.get("arm_bundle_run_id"),
        "release_id": bound.get("direct_release_run_id"),
        "condition": bound.get("condition"),
        "lane": bound.get("lane"),
        "solver_lock_sha256": bound.get("solver_lock_sha256"),
        "stage1_scorer_view_canonical_sha256":
            bound.get("stage1_scorer_view_canonical_sha256"),
        "registry_scorer_projection_sha256":
            bound.get("registry_scorer_projection_sha256"),
        "arm_rows_sha256": bound.get("arm_rows_sha256"),
        "mask_sha256": disk["mask_sha256"],
        "direct_bundle_sha256": disk["artifact_sha256"],
        "bundle_verified_on_disk": verified,
        "n_failed": report["n_failed"],
    }
    binding["binding_sha256"] = content_sha256(binding)
    validate_binding(binding)
    return binding


REFUSE_BINDING_INVALID = "the_normalized_binding_does_not_satisfy_its_own_schema"

# The types the binding schema declares. A field allowed to be null is checked as such;
# every other required field must be a non-empty string of the stated kind. This is the
# adapter proving its OWN output conforms — so a release binding whose arm_rows is null, or a
# bundle binding missing a hash, is caught HERE rather than by a downstream consumer.
_BINDING_NULLABLE = frozenset({
    "release_id", "condition", "lane", "stage1_scorer_view_canonical_sha256",
    "registry_scorer_projection_sha256", "arm_rows_sha256", "mask_sha256", "bundle_id",
})


def validate_binding(binding: dict) -> None:
    """The adapter validates its OWN normalized output against the published schema."""
    schema = _load_schema()
    missing = [f for f in schema["required"] if f not in binding]
    if missing:
        _refuse(REFUSE_BINDING_INVALID, f"binding is missing {missing}")
    # the self-hash
    derived = content_sha256({k: v for k, v in binding.items() if k != "binding_sha256"})
    if binding.get("binding_sha256") != derived:
        _refuse(REFUSE_BINDING_INVALID, "binding_sha256 does not re-derive")
    # required non-nullable strings must be present and non-empty
    for f in schema["required"]:
        v = binding.get(f)
        if f in _BINDING_NULLABLE:
            continue
        if f in ("bundle_verified_on_disk",):
            if not isinstance(v, bool):
                _refuse(REFUSE_BINDING_INVALID, f"{f} is not a bool")
            continue
        if f in ("n_failed",):
            if not isinstance(v, int):
                _refuse(REFUSE_BINDING_INVALID, f"{f} is not an int")
            continue
        if f == "direct_bundle_sha256":
            if not isinstance(v, dict):
                _refuse(REFUSE_BINDING_INVALID, f"{f} is not an object")
            continue
        if not isinstance(v, str) or not v:
            _refuse(REFUSE_BINDING_INVALID, f"{f} must be a non-empty string, got {v!r}")


_SCHEMA_CACHE: dict[str, Any] = {}


def _load_schema() -> dict:
    if "schema" not in _SCHEMA_CACHE:
        with open(SCHEMA_PATH) as fh:
            _SCHEMA_CACHE["schema"] = json.load(fh)
    return _SCHEMA_CACHE["schema"]


def load_and_normalize(report_path: str,
                       bundle_dir: Optional[str] = None) -> dict[str, Any]:
    """Read a native report off disk, validate it, and return the normalized binding."""
    if not report_path or not os.path.exists(report_path):
        _refuse(REFUSE_UNREADABLE, f"no admission report at {report_path!r}")
    try:
        with open(report_path) as fh:
            report = json.load(fh)
    except (ValueError, OSError) as exc:
        _refuse(REFUSE_UNREADABLE, f"not readable JSON ({exc})")
    return normalize(report, bundle_dir)


def disposition(report: dict) -> str:
    """The native verdict → the aggregate disposition. BYTE-EXACT; unknown token refuses."""
    validate_report(report)
    return ADMITTED if report["verdict"] == VERDICT_ADMIT else REFUSED


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m direct.verify_arm_contract",
        description="Validate a native W10 Direct admission report and emit the normalized "
                    "binding. Exit 0 = valid, 1 = invalid (typed reason on stderr).")
    ap.add_argument("--report", required=True, help="the native W10 admission report JSON")
    ap.add_argument("--bundle", default=None,
                    help="the Direct bundle directory, to re-hash files + re-derive the mask")
    ap.add_argument("--out", default=None, help="write the normalized binding here")
    args = ap.parse_args(argv)
    try:
        binding = load_and_normalize(args.report, args.bundle)
    except ContractError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(binding, fh, indent=2, sort_keys=True)
            fh.write("\n")
    print(f"VALID  {binding['subject_kind']}  verdict={binding['native_verdict']}  "
          f"disposition={binding['disposition']}  "
          f"on_disk={binding['bundle_verified_on_disk']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
