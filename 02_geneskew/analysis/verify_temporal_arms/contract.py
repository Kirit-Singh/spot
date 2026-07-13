"""THE INTEGRATION SEAM, EMITTED AS BYTES.

An aggregate BINDS this instead of transcribing it. A contract copied by hand is a contract
that drifts, and the drift is invisible until a release is admitted against the wrong thing —
so the fields below are the constants the verifier actually runs on, not a description of
them, and ``--print-contract`` hands them over as JSON.

Three things it settles, because each has already gone wrong once:

  * WHAT THIS LANE READS. The PRODUCER-NATIVE inventory, under the producer's own release
    root. Not a generic one, and not a copy at the aggregate root: a second inventory is a
    second thing to keep in sync, and it is the copy that gets admitted while the original is
    what shipped.
  * WHAT ``--w10-report`` MUST BE. An ADMISSION — a document that says, in named fields, that
    an independent lane admitted the Direct bundle. Not the producer's own verification slot
    (which ships PENDING and says so), and not a gate report that carries a verdict but no
    admission flags.
  * WHAT AN AGGREGATE BINDS. A POINTER plus a re-derivation. Never a copy.
"""
from __future__ import annotations

from typing import Any

from . import direct_source, schema, w10

VERIFIER_ID = "spot.stage02.temporal.arm.independent_verifier.v1"

CONTRACT_SCHEMA = "spot.stage02_temporal_arm_verifier_contract.v1"


def integration_contract() -> dict[str, Any]:
    """THE SEAM, as bytes. What this lane reads, what it writes, and what it requires.

    Emitted so an aggregate BINDS it instead of transcribing it: a contract copied by hand
    is a contract that drifts, and the drift is invisible until a release is admitted against
    the wrong thing.
    """
    return {
        "schema_version": CONTRACT_SCHEMA,
        "verifier_id": VERIFIER_ID,

        # WHAT THIS LANE READS. The PRODUCER-NATIVE inventory, under the producer's own
        # release root. Point --bundle-root at it. Do NOT copy or regenerate it at the
        # aggregate root: a second inventory is a second thing to keep in sync, and the copy
        # is what gets admitted while the original is what shipped.
        "reads": {
            "bundle_root": "the producer's NATIVE temporal release root (e.g. OUT/temporal)",
            "producer_inventory_file": schema.INVENTORY_FILENAME,
            "producer_inventory_schema": schema.SCHEMA_INVENTORY,
            "producer_inventory_is_mandatory": True,
            "generic_or_copied_inventory_accepted": False,
        },

        # WHAT THIS LANE WRITES. Exactly one file, and it never rewrites an existing byte.
        #
        # WHERE it lands has TWO answers, and they are not the same answer. By default it is
        # filed beside the inventory it admits — which ADDS A FILE UNDER THE PRODUCER'S ROOT.
        # No producer byte is modified, but "modifies nothing" and "writes nothing there" are
        # different claims, and collapsing them into one is how a contract starts lying.
        # ``--admission-out`` is the way to leave that root untouched entirely.
        "writes": {
            "external_admission_file": schema.ENVELOPE_FILENAME,
            "external_admission_schema": schema.SCHEMA_ENVELOPE,
            "report_id_rule": "sha256(canonical JSON excluding report_id)",
            # TRUE IN BOTH MODES: no byte the producer wrote is ever rewritten.
            "producer_bytes_modified": False,
            # THE PATH IS NOT THE BINDING, and never was. The admission binds the producer's
            # release id and the exact inventory bytes, so a reader holding the receipt can
            # get back to the release it admits from anywhere in the tree.
            "path_is_not_the_binding": True,
            "default": {
                "location": f"<bundle_root>/{schema.ENVELOPE_FILENAME}",
                "adds_a_file_under_the_producer_root": True,
                "producer_bytes_modified": False,
            },
            "override": {
                "flag": "--admission-out FILE",
                "aggregate_usage": (
                    "--bundle-root OUT/temporal (the producer's NATIVE root, read-only) "
                    "with --admission-out OUT/temporal_arm_external_admission.json"),
                "adds_a_file_under_the_producer_root": False,
                "producer_bytes_modified": False,
            },
        },

        # WHAT --w10-report MUST BE. Not the producer's in-bundle verification.json (that
        # slot ships PENDING and un-admitted, and is refused by path AND by content), and not
        # a gate report that carries a verdict but no admission flags. An ADMISSION is a
        # document that says, in these exact fields, that an independent lane admitted it.
        "w10_admission_document": {
            "schema_version": direct_source.W10_REPORT_SCHEMA,
            "verifier_id": direct_source.W10_VERIFIER_ID,

            # THERE ARE NO ADMISSION BOOLEANS, AND NONE ARE REQUIRED.
            #
            # W10's native report carries no ``admitted`` and no ``self_admitted``. It never
            # did. Requiring them is requiring fields that do not exist — a false refusal of
            # a sound report. And it does not need them: a boolean is a CLAIM, and this
            # report ships the thing the claim would have stood for.
            "admission_booleans": {
                "admitted": "ABSENT from the native report — not required, not read",
                "self_admitted": "ABSENT from the native report — not required, not read",
                "why": ("a flag can be set by anyone about anything; the evidence below is "
                        "checked against the bundle in hand, which a flag cannot be"),
            },

            # THE EVIDENCE THAT IS REQUIRED, and what each of it rules out. A PARTIAL
            # PARSER IS A FORGER'S SPECIFICATION: check only the schema, the id, the verdict
            # and a self-hash, and you have described exactly the document that defeats you —
            # correct everywhere you looked, fabricated everywhere else.
            "required_evidence": {
                "spec_sha256": w10.FROZEN_SPEC_SHA256,
                "verifier_code_sha256": w10.FROZEN_VERIFIER_CODE_SHA256,
                "gate_inventory_sha256": w10.FROZEN_GATE_INVENTORY_SHA256,
                "n_gates": w10.FROZEN_N_GATES,
                "gate_profile": w10.PROFILE_BUNDLE_PRODUCTION,
                "w10_pinned_verifier_commit": w10.W10_PINNED_VERIFIER_COMMIT,
                # ENFORCED ALWAYS, pins or no pins: overriding the exact-inventory hash may
                # not switch the gate CONTENT check off, or a resealed deletion of the mask
                # check would sail through on a hash it chose for itself.
                "required_gates_always_enforced": list(w10.REQUIRED_GATE_SUBSTRINGS),
                "verdict": f"{w10.W10_ADMIT!r}, with n_failed 0 and failed_gates empty",
                "independent_of_generator": "true",
                "report_sha256": "sha256(canonical JSON excluding report_sha256)",
                "gate_records": ("must BE the gate_inventory they claim: same names, same "
                                 "order, no duplicates, every one passed, and the counts "
                                 "consistent with the records rather than with each other"),
                "bound_artifact": {
                    "required_fields": list(w10.BOUND_REQUIRED),
                    "condition": "the condition this endpoint asked for",
                    "arm_rows_sha256": "the rows on disk",
                    "solver_lock_sha256": direct_source.AUTHORITATIVE_ENV_LOCK_SHA256,
                    "artifact_sha256": (
                        "the EXACT, COMPLETE bundle file set — no subset, no superset, no "
                        "duplicates — and every file must still hash to what it hashed to "
                        "when the report was written"),
                },
                "artifact_file_set": sorted(w10.EXPECTED_FILES),
                "n_artifact_files": len(w10.EXPECTED_FILES),
                # A SAMPLE REPORT IS A DIAGNOSTIC, NOT AN ADMISSION. W10's --recompute
                # DEFAULTS to 'sample': it re-derives a handful of targets. It carries the
                # SAME 90 gates and the SAME inventory hash as a full run, so the gate profile
                # cannot tell them apart — and taking one for the other leaves every temporal
                # number standing on numbers nobody re-derived.
                "recompute_mode": w10.RECOMPUTE_ALL,
                "recompute_completeness": (
                    "n_targets_recomputed == n_masks_rederived == n_targets_in_bundle, and "
                    "n_targets_in_bundle / n_arm_rows must be THIS bundle's own counts — "
                    "'all' has to mean all, and the counts are what say whether it did"),
                "sample_mode_is_admissible": False,
            },

            "must_not_be": {
                "path": f"the Direct bundle's own {direct_source.VERIFICATION_FILE}",
                "schema_version": direct_source.VERIFICATION_SLOT_SCHEMA,
                "verdict": direct_source.PENDING_VERDICT,
                "why": ("the producer's slot ships PENDING and un-admitted: it says in its "
                        "own bytes that it is not an admission, and a producer that could "
                        "admit itself by shipping a file with the right name in the right "
                        "place would not be admitted by anybody"),
            },
        },

        # HOW AN AGGREGATE BINDS THE RESULT. A POINTER, plus a re-derivation. Never a copy.
        "aggregate_binding": {
            "native_release_root": "<relative to the aggregate root; never absolute>",
            "producer_inventory": {
                "file": schema.INVENTORY_FILENAME,
                "schema_version": schema.SCHEMA_INVENTORY,
                "release_id": "<inventory.release_id>",
                "raw_sha256": "<sha256 of the inventory bytes on disk>",
            },
            "external_admission": {
                "file": schema.ENVELOPE_FILENAME,
                "schema_version": schema.SCHEMA_ENVELOPE,
                "verifier_id": VERIFIER_ID,
                "report_id": "<envelope.report_id>",
                "raw_sha256": "<sha256 of the envelope bytes on disk>",
                "verdict": "ADMIT",
            },
            "aggregate_must_rederive": [
                "sha256(native inventory bytes) == producer_inventory.raw_sha256",
                "envelope.binds.producer_release_id == producer_inventory.release_id",
                "envelope.binds.producer_release_raw_sha256 == "
                "producer_inventory.raw_sha256",
                "envelope.verifier_id == this verifier_id and envelope.verdict == ADMIT",
            ],
        },
        "exit_codes": {"0": "ADMIT", "1": "REJECT"},
    }


