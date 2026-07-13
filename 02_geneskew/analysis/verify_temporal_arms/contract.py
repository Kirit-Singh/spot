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

from . import direct_source, schema

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

            # THE EVIDENCE THAT IS REQUIRED, and what each of it rules out.
            "required_evidence": {
                "verdict": f"{direct_source.W10_ADMIT!r}",
                "n_failed": "0, and failed_gates empty — an ADMIT with a failed gate is "
                            "not an admit",
                "independent_of_generator": "true — a report that imported the generator is "
                                            "the generator's opinion of itself",
                "report_sha256": "sha256(canonical JSON excluding report_sha256) — a report "
                                 "editable after it was cited is a claim, not a result",
                "gate_inventory_sha256": "sha256(canonical JSON of gate_inventory)",
                "bound_artifact.condition": "the condition this endpoint asked for",
                "bound_artifact.arm_rows_sha256": "the rows on disk",
                "bound_artifact.solver_lock_sha256":
                    direct_source.AUTHORITATIVE_ENV_LOCK_SHA256,
                "bound_artifact.artifact_sha256":
                    "a map of every file the report admitted; each must STILL hash to what "
                    "it hashed to when the report was written",
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


