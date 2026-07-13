"""THE TYPED LANE ADMISSION: a report that BINDS THE BYTES, not a file that says ADMIT.

THE DEFECT THIS CLOSES — and it made production mode self-attested
------------------------------------------------------------------
The previous admission check accepted ANY file at the expected name whose ``verdict`` was
``ADMIT``, and stored only that file's raw hash. The verifier then checked that the same file
still existed and still hashed to that value. So:

    echo '{"verdict":"ADMIT"}' > direct_admission_Rest.json

...beside an unadmitted store, or a DIFFERENT store, and both the producer and the verifier
accepted it. The release admitted itself. An admission that only has to SAY "admit" is not an
admission; it is a filename.

WHAT AN ADMISSION HAS TO PROVE
------------------------------
That an INDEPENDENT verifier ran, over THESE EXACT BYTES, and found nothing wrong:

  * it is the real report SHAPE, from the real VERIFIER, at the PINNED code hash;
  * its own content hash RE-DERIVES (it was not edited after it was written);
  * it ran a FULL GATE INVENTORY whose own hash re-derives, and ZERO gates failed —
    a report with one gate and no failures has verified nothing;
  * it recomputed EVERYTHING (`recompute_mode: all`) — not a spot check;
  * its BOUND ARTIFACT names the bundle ON DISK: the run id, the row hash, and every
    artifact file, each of which must be present and hash to what the report says;
  * it names the SAME Stage-1 identity this projection is bound to — a report that
    verified a bundle built against a STALE Stage-1 release verified a different release;
  * the arm being asked for is IN the inventory the report actually verified.

A forged report must therefore reproduce a complete, self-consistent verification of the real
bytes — which is what the real verifier produces. THE LIMIT IS NAMED: without a signature,
nothing here proves WHO wrote the report, only that it is about these bytes and internally
whole. Signing is the owner's call and is declared, not silently assumed away.

NO ABSOLUTE PATHS are ever serialized: a binding that carried this host's directory layout
would be a binding to a machine, not to a release.
"""
from __future__ import annotations

import json
import os
from typing import Any

from .hashing import content_hash, file_sha256

# --------------------------------------------------------------------------- #
# W10 — the Direct all-arm bundle verifier. Its REAL report, read off its own emitter.
# --------------------------------------------------------------------------- #
W10_REPORT_FILE = "w10_admission_{condition}.json"
W10_REPORT_SCHEMA = "spot.stage02_direct_arm_bundle_verification.v1"
W10_VERIFIER_ID = "spot.stage02.direct.arm_bundle.verifier.v1"
W10_VERIFIER_CODE = "8290802638898db622a8baf19f233b54b5f6f1c8434f192730aa28f829f8715f"
W10_RECOMPUTE_MODE = "all"

# A report with one gate and no failures has verified nothing. W10 runs 107; the floor is set
# well below that so a gate being ADDED is not an outage, and a report that ran a handful of
# checks and called itself an admission is still refused.
W10_MIN_GATES = 50

# Load-bearing gates by name. Their ABSENCE is the finding: a report that never checked the
# bytes on disk did not check the bytes on disk, whatever its verdict says.
W10_REQUIRED_GATE_MARKERS = (
    "BYTES ON DISK",
    "RE-DERIVE from the shipped parquet rows",
    "arm key re-derives",
)

# The authoritative Stage-2 solver lock. A bundle verified under another environment is a
# bundle whose numbers were produced by another solver.
SOLVER_LOCK_SHA256 = "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe"

# --------------------------------------------------------------------------- #
# W11 (temporal) and W4 (pathway) — their EXTERNAL ADMISSION contracts, in-tree.
# Each must BIND the release it admitted, by hash. A verdict that names no artifact could be
# moved onto any artifact.
# --------------------------------------------------------------------------- #
EXTERNAL = {
    "temporal": {
        "file": "temporal_arm_external_admission.json",
        "schema": "spot.stage02_temporal_arm_external_admission.v1",
        "verifier_id": "spot.stage02.temporal.arm.independent_verifier.v1",
        "inventory": "temporal_arm_release.json",
        "inventory_schema": "spot.stage02_temporal_arm_release.v1",
        "gates": (),          # W11's exact inventory is not yet published — see LIMITS
        "owner": "W11",
    },
    "pathway": {
        "file": "pathway_arm_external_admission.json",
        "schema": "spot.stage02_pathway_arm_external_admission.v1",
        "verifier_id": "spot.stage02.pathway.arm.independent_verifier.v1",
        "inventory": "pathway_arm_release.json",
        "inventory_schema": "spot.stage02_pathway_arm_release.v1",
        # W4's EXACT 12-gate inventory (verify_pathway_release @ ef136a9). A report that ran a
        # different set of gates is not this verifier's admission.
        "gates": (
            "the_condition_and_source_universe_comes_from_the_authoritative_stage1_release",
            "the_bundles_are_exactly_the_authoritative_condition_x_source_grid_once_each",
            "every_bundle_reopens_and_its_nonnull_run_id_rederives_from_its_own_binding",
            "one_scorer_view_and_stage1_that_match_the_release_pins_and_the_pinned_solver_lock",
            "every_cell_has_a_distinct_nonnull_run_id_and_distinct_nonnull_arm_record_bytes",
            "each_bundle_agrees_with_itself_about_which_condition_x_source_cell_it_is",
            "method_gene_sets_binds_two_pinned_sources_agrees_with_provenance_one_universe",
            "the_gene_set_universes_match_the_authoritative_native_run_binding_universe_fields",
            "no_p_q_fdr_inferential_key_at_any_depth_of_any_shipped_document",
            "every_cell_has_one_independent_admitting_report_with_the_exact_gate_inventory",
            "the_producer_inventory_is_present_pending_native_rederives_and_binds_this",
            "the_producer_inventory_binds_the_exact_bytes_that_landed_on_disk",
        ),
        "owner": "W4",
    },
}

# NAMED GATES.
G_ABSENT = "the_lane_ships_no_independent_verification_report"
G_SHAPE = "the_report_is_not_the_independent_verifiers_real_report_shape"
G_VERIFIER = "the_report_was_not_written_by_the_pinned_independent_verifier"
G_SELF_HASH = "the_report_does_not_hash_to_what_it_says_it_does"
G_VERDICT = "the_report_does_not_ADMIT_with_zero_failed_gates"
G_GATES = "the_report_did_not_run_the_gate_inventory_an_admission_requires"
G_RECOMPUTE = "the_report_did_not_recompute_everything_it_claims_to_have_verified"
G_BOUND_BYTES = "the_report_does_not_bind_the_bundle_bytes_that_are_on_disk"
G_BOUND_SUBJECT = "the_report_admitted_a_different_bundle_than_the_one_being_read"
G_STALE_STAGE1 = "the_report_verified_a_bundle_built_against_a_different_stage1_release"
G_ARM_NOT_VERIFIED = "the_arm_being_asked_for_is_not_in_the_inventory_the_report_verified"
G_ENV = "the_report_verified_a_bundle_built_under_another_solver_environment"
G_EMPTY_INVENTORY = "the_report_verified_an_EMPTY_set_of_arms_or_bundles_and_admitted_it"
G_PRODUCER_SELF_ADMITTED = "the_producer_inventory_admitted_itself"

PRODUCER_PENDING = "pending_independent_verification"


class AdmissionError(ValueError):
    def __init__(self, gate: str, message: str):
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _refuse(gate: str, message: str) -> None:
    raise AdmissionError(gate, message)


def _load(path: str) -> Any:
    if not os.path.exists(path):
        _refuse(G_ABSENT,
                f"no independent verification report at {os.path.basename(path)}. A store "
                "nobody verified is not evidence, and an unadmitted answer is "
                "indistinguishable from an admitted one once it is on a page")
    with open(path) as fh:
        return json.load(fh)


def _self_hash(doc: dict, field: str) -> None:
    claimed = doc.get(field)
    derived = content_hash({k: v for k, v in doc.items() if k != field})
    if claimed != derived:
        _refuse(G_SELF_HASH,
                f"{field} says {str(claimed)[:16]}; the report's own content hashes to "
                f"{derived[:16]}. It was edited after it was written, and a report that can "
                "be edited after it is cited is a claim, not a result")


# --------------------------------------------------------------------------- #
# DIRECT — W10's FULL report. Not a renamed verdict stub.
# --------------------------------------------------------------------------- #
def bind_direct(bundles_root: str, *, condition: str, bundle_dir: str, arm_key: str,
                stage1: dict[str, Any]) -> dict[str, Any]:
    """The typed Direct admission: W10's report, proved against the bundle ON DISK."""
    rel = W10_REPORT_FILE.format(condition=condition)
    rep = _load(os.path.join(bundles_root, rel))

    if rep.get("schema_version") != W10_REPORT_SCHEMA:
        _refuse(G_SHAPE,
                f"schema {rep.get('schema_version')!r} is not {W10_REPORT_SCHEMA!r}. A file "
                "that merely says ADMIT is a filename, not an admission")
    if rep.get("verifier_id") != W10_VERIFIER_ID:
        _refuse(G_VERIFIER, f"verifier_id {rep.get('verifier_id')!r}")
    if rep.get("verifier_code_sha256") != W10_VERIFIER_CODE:
        _refuse(G_VERIFIER,
                f"verifier_code_sha256 {str(rep.get('verifier_code_sha256'))[:16]} is not the "
                f"pinned W10 checkout {W10_VERIFIER_CODE[:16]}")
    if rep.get("independent_of_generator") is not True:
        _refuse(G_VERIFIER, "the report does not claim independence from the generator")

    _self_hash(rep, "report_sha256")

    if rep.get("verdict") != "ADMIT" or rep.get("n_failed") != 0 or rep.get("failed_gates"):
        _refuse(G_VERDICT,
                f"verdict {rep.get('verdict')!r} with n_failed={rep.get('n_failed')!r} and "
                f"failed_gates={rep.get('failed_gates')!r}")

    inv = rep.get("gate_inventory") or []
    if len(inv) < W10_MIN_GATES or rep.get("n_gates") != len(inv):
        _refuse(G_GATES,
                f"the report ran {len(inv)} gate(s); an admission requires at least "
                f"{W10_MIN_GATES}. A report with one gate and no failures has verified nothing")
    if rep.get("gate_inventory_sha256") != content_hash(inv):
        _refuse(G_GATES, "the gate inventory does not hash to what the report says it does")
    for marker in W10_REQUIRED_GATE_MARKERS:
        if not any(marker in g for g in inv):
            _refuse(G_GATES,
                    f"no gate in this report checks {marker!r}. Its absence IS the finding: a "
                    "report that never checked it did not check it, whatever its verdict says")

    bound = rep.get("bound_artifact") or {}
    if bound.get("recompute_mode") != W10_RECOMPUTE_MODE:
        _refuse(G_RECOMPUTE,
                f"recompute_mode is {bound.get('recompute_mode')!r}, not "
                f"{W10_RECOMPUTE_MODE!r}. A spot check is not a verification")

    # ---- THE SUBJECT: this report is about THIS bundle, not a neighbour's ----
    with open(os.path.join(bundle_dir, "arm_bundle.json")) as fh:
        doc = json.load(fh)
    if str(bound.get("condition")) != condition:
        _refuse(G_BOUND_SUBJECT,
                f"the report admits condition {bound.get('condition')!r}; this projection "
                f"asks about {condition!r}. A genuine report about another condition is still "
                "a report about another question")
    if str(bound.get("arm_bundle_run_id")) != str(doc.get("arm_bundle_run_id")):
        _refuse(G_BOUND_SUBJECT,
                f"the report admits bundle {str(bound.get('arm_bundle_run_id'))[:16]}; the "
                f"bundle on disk is {str(doc.get('arm_bundle_run_id'))[:16]}")
    if str(bound.get("arm_rows_sha256")) != str(doc.get("arm_rows_sha256")):
        _refuse(G_BOUND_BYTES,
                "the report's arm_rows_sha256 is not the one the bundle on disk declares")

    # ---- THE BYTES: every artifact the report bound is here, and is those bytes ----
    files = bound.get("artifact_sha256") or {}
    if not files:
        _refuse(G_BOUND_BYTES,
                "the report binds no artifact hashes at all — it could be moved onto any "
                "bundle and would still 'admit' it")
    for name, want in sorted(files.items()):
        p = os.path.join(bundle_dir, name)
        if not os.path.exists(p):
            _refuse(G_BOUND_BYTES, f"the report binds {name}, which is not in this bundle")
        if file_sha256(p) != want:
            _refuse(G_BOUND_BYTES,
                    f"{name}: the report bound {str(want)[:16]}; on disk it is "
                    f"{file_sha256(p)[:16]}. The report verified different bytes")

    # ---- THE ENVIRONMENT and the STAGE-1 IDENTITY ----
    if str(bound.get("solver_lock_sha256")) != SOLVER_LOCK_SHA256:
        _refuse(G_ENV,
                f"the bundle was verified under solver lock "
                f"{str(bound.get('solver_lock_sha256'))[:16]}, not the authoritative "
                f"{SOLVER_LOCK_SHA256[:16]}")
    for field, want in stage1.items():
        # W10's bound artifact carries the SCORER identity. It does not carry the release RAW
        # sha — that is the field W4's pathway admission binds, and demanding it of W10 would
        # refuse every genuine Direct report.
        if field == "stage1_release_raw_sha256":
            continue
        if want and str(bound.get(field)) != str(want):
            _refuse(G_STALE_STAGE1,
                    f"the report verified a bundle built against {field}="
                    f"{str(bound.get(field))[:16]}; this projection is bound to "
                    f"{str(want)[:16]}. It verified a different release")

    # ---- THE ARM INVENTORY. EMPTY IS A REFUSAL. ----
    #
    # This was `if keys and arm_key not in keys` — so a report whose arm_inventory was EMPTY
    # skipped the check entirely and ADMITTED. A verification that covered no arms is not a
    # verification of any arm, and admitting on it admits nothing.
    keys = [str(a.get("arm_key")) for a in (bound.get("arm_inventory") or [])]
    if not keys:
        _refuse(G_EMPTY_INVENTORY,
                "the report's arm_inventory is EMPTY. A verification that covered no arms is "
                "not a verification of any arm")
    if len(keys) != len(set(keys)):
        _refuse(G_EMPTY_INVENTORY, "the arm inventory repeats an arm")
    declared = doc.get("arms") or []
    if declared and len(keys) != len(declared):
        _refuse(G_EMPTY_INVENTORY,
                f"the report verified {len(keys)} arm(s); the bundle ships {len(declared)}. A "
                "report that covered only some of the arms admits only some of them")
    if arm_key not in keys:
        _refuse(G_ARM_NOT_VERIFIED,
                f"the arm {arm_key!r} is not among the {len(keys)} arms this report verified")

    return {
        "admitted": True,
        "owner": "W10",
        "report": rel,                      # a NAME, never an absolute path
        "report_schema": W10_REPORT_SCHEMA,
        "verifier_id": W10_VERIFIER_ID,
        "verifier_code_sha256": W10_VERIFIER_CODE,
        "report_sha256": rep["report_sha256"],
        "recompute_mode": W10_RECOMPUTE_MODE,
        "n_gates": rep["n_gates"],
        "n_failed": 0,
        "gate_inventory_sha256": rep["gate_inventory_sha256"],
        "bound_bundle_run_id": bound.get("arm_bundle_run_id"),
        "bound_arm_rows_sha256": bound.get("arm_rows_sha256"),
        "bound_artifact_files": sorted(files),
        "n_arms_verified": len(keys),
        "solver_lock_sha256": SOLVER_LOCK_SHA256,
        "signature_limit": ("no signature: this proves the report is ABOUT these bytes and is "
                            "internally whole. It does not prove WHO wrote it"),
    }


# --------------------------------------------------------------------------- #
# TEMPORAL (W11) / PATHWAY (W4) — the external admission, BOUND to the release it cleared.
# --------------------------------------------------------------------------- #
def bind_external(bundles_root: str, lane: str, *, bundle_dir: str,
                  stage1: dict | None = None) -> dict[str, Any]:
    """W11 / W4: the FULL envelope AND the producer inventory — not merely their hashes.

    It used to check the schema, the verifier id, the verdict, the self-hash and the inventory
    hash, and stop. So a report could assert nothing about its own independence, run NO GATES
    AT ALL, and clear an EMPTY release — and an admission over an empty release admits nothing
    while looking exactly like one that admits everything.
    """
    spec = EXTERNAL[lane]
    stage1 = stage1 or {}
    rep = _load(os.path.join(bundles_root, spec["file"]))

    if rep.get("schema_version") != spec["schema"]:
        _refuse(G_SHAPE, f"[{lane}] schema {rep.get('schema_version')!r} is not "
                         f"{spec['schema']!r}")
    if rep.get("verifier_id") != spec["verifier_id"]:
        _refuse(G_VERIFIER, f"[{lane}] verifier_id {rep.get('verifier_id')!r}")
    if str(rep.get("lane", lane)) != lane:
        _refuse(G_SHAPE, f"[{lane}] the report says it is about lane {rep.get('lane')!r}")
    if rep.get("generator_is_not_verifier") is not True:
        _refuse(G_VERIFIER, f"[{lane}] the report does not assert generator_is_not_verifier")
    if rep.get("fail_closed") is not True:
        _refuse(G_VERIFIER, f"[{lane}] the report does not assert fail_closed")
    if rep.get("verdict") != "ADMIT" or int(rep.get("n_failed") or 0) != 0:
        _refuse(G_VERDICT, f"[{lane}] verdict {rep.get('verdict')!r} / n_failed "
                           f"{rep.get('n_failed')!r}")
    _self_hash(rep, "report_id")

    if spec["gates"]:
        got = tuple(rep.get("gate_inventory") or ())
        if got != spec["gates"]:
            _refuse(G_GATES,
                    f"[{lane}] the report ran {len(got)} gate(s); this verifier's EXACT "
                    f"inventory is {len(spec['gates'])} named gates. A report that ran a "
                    "different set of gates is not this verifier's admission")

    # ---- THE PRODUCER INVENTORY IT CLEARED ----
    inv_path = os.path.join(bundles_root, spec["inventory"])
    inv = _load(inv_path)
    binds = rep.get("binds") or {}
    if not binds:
        _refuse(G_BOUND_BYTES, f"[{lane}] the report binds NOTHING")
    if inv.get("schema_version") != spec["inventory_schema"]:
        _refuse(G_SHAPE, f"[{lane}] the producer inventory schema is "
                         f"{inv.get('schema_version')!r}")
    if inv.get("verdict") != PRODUCER_PENDING or inv.get("admitted") is not False \
            or inv.get("self_admitted") is not False:
        _refuse(G_PRODUCER_SELF_ADMITTED,
                f"[{lane}] the producer inventory is not PENDING/un-admitted. A release that "
                "admitted itself was never independently admitted")

    inv_raw = file_sha256(inv_path)
    if str(binds.get("inventory_raw_sha256")) != inv_raw:
        _refuse(G_BOUND_BYTES, f"[{lane}] the report bound another inventory's bytes")
    if str(binds.get("producer_release_raw_sha256")) != inv_raw:
        _refuse(G_BOUND_BYTES,
                f"[{lane}] producer_release_raw_sha256 is not the inventory on disk")
    if str(binds.get("producer_release_id")) != str(inv.get("release_id")):
        _refuse(G_BOUND_SUBJECT, f"[{lane}] the report admits another release")
    rederived = content_hash({k: v for k, v in inv.items() if k != "release_id"})
    if str(inv.get("release_id")) != rederived:
        _refuse(G_SELF_HASH, f"[{lane}] the inventory's release_id does not re-derive")

    # THE ACTUAL STAGE-1 FIELD W4 BINDS.
    want_s1 = stage1.get("stage1_release_raw_sha256")
    if want_s1 and str(binds.get("stage1_release_raw_sha256")) != str(want_s1):
        _refuse(G_STALE_STAGE1,
                f"[{lane}] the report cleared a release built against Stage-1 "
                f"{str(binds.get('stage1_release_raw_sha256'))[:16]}, not {str(want_s1)[:16]}")

    # ---- THE BUNDLE LIST. EMPTY IS A REFUSAL. ----
    bundles = inv.get("bundles") or []
    if not bundles:
        _refuse(G_EMPTY_INVENTORY,
                f"[{lane}] the cleared inventory lists NO bundles. An admission over an empty "
                "release admits nothing, and it looks exactly like one that admits everything")
    if int(inv.get("n_bundles") or 0) != len(bundles):
        _refuse(G_EMPTY_INVENTORY, f"[{lane}] n_bundles disagrees with the bundle list")

    with open(os.path.join(bundle_dir, "arm_bundle.json")) as fh:
        doc = json.load(fh)
    mine = str(doc.get("bundle_id") or doc.get("pathway_run_id"))
    entry = next((b for b in bundles if str(b.get("bundle_id")) == mine), None)
    if entry is None:
        _refuse(G_BOUND_SUBJECT,
                f"[{lane}] the bundle being read ({mine[:16]}) is not in the cleared inventory")

    # ---- EVERY BOUND FILE HASH, against the bytes on disk ----
    for group in ("files", "rankings"):
        for name, e in sorted((entry.get(group) or {}).items()):
            p = os.path.join(bundle_dir, name)
            want = e.get("raw_sha256") if isinstance(e, dict) else e
            if not os.path.exists(p) or file_sha256(p) != want:
                _refuse(G_BOUND_BYTES,
                        f"[{lane}] {name}: the cleared inventory bound different bytes")

    return {
        "admitted": True, "owner": spec["owner"], "report": spec["file"],
        "report_schema": spec["schema"], "verifier_id": spec["verifier_id"],
        "report_id": rep["report_id"], "bound_inventory": spec["inventory"],
        "bound_inventory_sha256": inv_raw, "bound_bundle_id": mine,
        "n_bundles": len(bundles),
        "signature_limit": ("no signature: this proves the report is ABOUT these bytes and is "
                            "internally whole. It does not prove WHO wrote it"),
    }
