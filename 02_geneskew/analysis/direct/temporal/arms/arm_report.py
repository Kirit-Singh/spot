"""The INDEPENDENT temporal-arm verification report — a separate typed artifact.

WHY A SEPARATE FILE, AND NOT A FLAG IN THE BUNDLE
-------------------------------------------------
The aggregate run-manifest refuses to admit an arm on the strength of a self-verdict baked
into the bundle: "a two-byte file saying ``{"verdict":"admit"}`` passed" is exactly the
hole it was rebuilt to close. So admission rides on a SEPARATE typed report that

  * is signed by a NAMED verifier (``verifier_id``) whose identity + gate inventory the
    aggregate pins OUTSIDE the run — a forger writes the report, so the report cannot be
    trusted to declare its own authority;
  * BINDS THE BUNDLE IT JUDGED — ``bundle_id`` plus the raw sha256 of ``arm_bundle.json``
    AND of ``temporal_provenance.json`` — because an ADMIT that names no bundle can be
    copied onto any bundle;
  * records every pinned gate as PASSED — an ADMIT that ran no gates checked nothing.

GENERATOR IS NOT VERIFIER
-------------------------
``generator_is_not_verifier: true`` is honest here: the report is produced by
``arm_admission`` — a module that re-derives every claim from the SHIPPED BYTES read back
off disk, structurally separate from ``arm_bundle`` which generated them. The producer
orchestrates the call exactly as the legacy temporal runner calls its own separate
verifier; it does not get to vote on the verdict.

THE IDENTITY IS THE INDEPENDENT VERIFIER'S, NOT A SELF-VERIFIER'S
----------------------------------------------------------------
``VERIFIER_ID`` is the INDEPENDENT temporal-arm verifier contract
(``spot.stage02.temporal.arm.independent_verifier.v1``) — the same identity the standalone
verifier lane (W11) signs with, NOT a producer-private "self-verifier" id. The producer
REFERENCES this contract; it does not certify itself under a name only it uses. The report
is produced by ``arm_admission``, which re-derives from the shipped bytes and is structurally
separate from the generator — so signing the independent contract is honest, and W11
re-running the same contract on the same bytes reaches the same verdict.

WHAT THE AGGREGATE LANE PINS
----------------------------
``VERIFIER_ID``, ``SCHEMA_VERIFICATION`` and ``REQUIRED_GATES`` are the PUBLISHED identity
of this contract. The aggregate's ``--expect-verifiers`` pin must name exactly these, so the
report is checked against an expectation set outside the run rather than one it declares
itself. They are stable; changing one is a versioned interface change, coordinated, never
silent.
"""
from __future__ import annotations

from typing import Any

SCHEMA_VERIFICATION = "spot.stage02_temporal_arm_verification.v1"
# THE INDEPENDENT verifier contract (shared with the standalone W11 verifier lane), never a
# producer-private self-verifier id. The producer references this; it does not self-certify.
VERIFIER_ID = "spot.stage02.temporal.arm.independent_verifier.v1"

# The ROOT external-admission envelope W11 alone writes, over the whole six-bundle release
# (sealed cross-check a12f7eee, §C). The producer only DECLARES this as required; it never
# emits it. NOTE for W11/W3: the sealed report's §A/§C prose also names
# ``spot.stage02_temporal_arm_verifier_report.v1`` for the required report schema — a
# discrepancy in the report itself; this producer declares the §C/root envelope schema and
# flags it for reconciliation.
EXTERNAL_ADMISSION_SCHEMA = "spot.stage02_temporal_arm_external_admission.v1"
VERIFIER_REPORT_SCHEMA = "spot.stage02_temporal_arm_verifier_report.v1"

ADMIT = "admit"
REJECT = "reject"

# The gate inventory this verifier PUBLISHES for the aggregate to pin. Every one of these
# runs on a complete bundle, so a report that omits any of them from its passed set is a
# report from a verifier that skipped part of the contract.
REQUIRED_GATES = (
    "no_pq_or_combined_objective",
    "no_role_pole_pareto_concordance_pair_or_batch_field",
    "no_machine_local_path_hostname_or_private_address",
    "bundle_declares_the_temporal_lane",
    "bundle_declares_the_temporal_cross_condition_mode",
    "bundle_declares_the_crispri_knockdown_modality",
    "bundle_binds_a_structural_code_identity_without_self_admitting_clean",
    "method_digest_and_code_identity_are_both_bound_as_distinct_roles",
    "no_pole_derived_or_pair_based_program_projection_field",
    "stage1_binding_is_complete_and_non_null",
    "stage1_binding_programs_match_the_admitted_program_set",
    "arm_inventory_is_every_program_x_every_desired_change",
    "arm_record_joins_to_exactly_one_base_record",
    "arm_record_and_its_base_record_name_the_same_target",
    "arm_value_is_the_sign_transform_of_the_base_delta",
    "desired_target_modulation_rederives_from_the_arm_value",
    "rank_rederives_by_the_frozen_rule",
    "ranking_binding_matches_the_arm",
    "bundle_id_covers_its_own_content",
)


def build_report(result: dict[str, Any], *, bundle_id: str,
                 arm_bundle_sha256: str, provenance_sha256: str) -> dict[str, Any]:
    """The typed report over a ``verify_bundle`` result. Binds the bundle it judged.

    ``result`` is what ``arm_admission.verify_bundle`` returned — it already re-derived
    every claim from the shipped bytes and recorded each gate. This shapes that into the
    artifact the aggregate reads, and binds the exact bytes ``bundle_id`` and the two file
    hashes so the ADMIT cannot be lifted onto a different bundle.
    """
    checks = list(result.get("checks") or [])
    failed = [c["gate"] for c in checks if c.get("status") != "pass"]
    return {
        "schema_version": SCHEMA_VERIFICATION,
        "verifier_id": VERIFIER_ID,
        # the two declarations the aggregate requires, and that this lane earns:
        "generator_is_not_verifier": True,
        "fail_closed": True,
        "verdict": ADMIT if not failed else REJECT,
        "n_failed": len(failed),
        "failed_gates": failed,
        "checks": checks,
        # THE BINDING. What this admission is an admission OF.
        "bundle_id": bundle_id,
        "binds": {
            "arm_bundle_sha256": arm_bundle_sha256,
            "provenance_sha256": provenance_sha256,
        },
        # this lane's published gate inventory, so a reader can see what "admit" covered
        "required_gates": list(REQUIRED_GATES),
    }
