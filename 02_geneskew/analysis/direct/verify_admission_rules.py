"""THE ADMISSION CONTRACT, RESTATED FOR THE VERIFIER. It does not import the producer.

The independent verifier was importing ``direct.lane_admission`` — the PRODUCER'S admission
implementation — and calling it to "re-derive" the admissions. That is not a second opinion.
It is the same opinion, twice: any bug in the producer's contract was reproduced exactly by the
thing meant to catch it, and the two could never disagree. (My own audit probe forbids a
verifier importing a producer module. It did not fire because this pair was new. The probe now
covers it.)

So the contract is RESTATED here, from the verifiers' own bytes:

    W10  spot.stage02_direct_arm_bundle_verification.v1     (verify_arm_report.py)
    W11  spot.stage02_temporal_arm_external_admission.v1
    W4   spot.stage02_pathway_arm_external_admission.v1     (verify_pathway_release ef136a9)

A drift between this module and ``lane_admission`` is a FINDING, and a test proves it is
caught: a deliberate divergence in either one makes the pair disagree and the projection is
refused.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

W10_REPORT_FILE = "w10_admission_{condition}.json"
W10_REPORT_SCHEMA = "spot.stage02_direct_arm_bundle_verification.v1"
W10_VERIFIER_ID = "spot.stage02.direct.arm_bundle.verifier.v1"
W10_VERIFIER_CODE = "8290802638898db622a8baf19f233b54b5f6f1c8434f192730aa28f829f8715f"
W10_RECOMPUTE_MODE = "all"
W10_MIN_GATES = 50
W10_REQUIRED_GATE_MARKERS = ("BYTES ON DISK",
                             "RE-DERIVE from the shipped parquet rows",
                             "arm key re-derives")

SOLVER_LOCK_SHA256 = "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe"

# W4's EXACT gate inventory (verify_pathway_release ef136a9). A pathway admission that ran a
# different set of gates is not this verifier's admission.
W4_GATES = (
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
)


# --------------------------------------------------------------------------- #
# W11 — the TEMPORAL root envelope. Its REAL binds, and its PUBLISHED gate inventory.
#
# The committed contract was an invented hybrid: it demanded `inventory_raw_sha256` and a
# top-level `stage1_release_raw_sha256`, and it demanded the producer inventory carry
# top-level `verdict/admitted/self_admitted`. THE REAL BYTES HAVE NONE OF THOSE.
#
#   * the native inventory (temporal/arms/arm_release.py) says `external_admission.status =
#     pending` and carries NO top-level verdict/admitted/self_admitted at all — "pending is
#     the only honest producer state", in its own words. My check would have REFUSED the real
#     release: a fail-closed bug, which is still a bug.
#   * W11's root envelope binds the fourteen keys below, and the Stage-1 raw sha lives NESTED
#     at binds.stage1_release.stage1_release_raw_sha256 — not at the top level.
#   * its gate inventory is PUBLISHED: 188 gates, canonical sha256 dc9b6bc1…. `gates=()` is no
#     longer acceptable, and the count alone is not enough — the INVENTORY ITSELF is pinned.
# --------------------------------------------------------------------------- #
W11_N_GATES = 188
W11_GATE_INVENTORY_SHA256 = (
    "dc9b6bc14ba56c28efcc4bcabbca456fe49d0e816cba036546f85d98ee27ba97")

W11_BINDS_KEYS = frozenset({
    "bundles", "code_identity", "env_lock_sha256", "method", "native_release_root",
    "per_program_projection_sha256", "producer_release_canonical_sha256",
    "producer_release_file", "producer_release_id", "producer_release_raw_sha256",
    "rankings_digest", "registry_scorer_projection_sha256", "selector_condition_sequence",
    "stage1_release",
})

# The producer inventory's ONLY honest state. There is no top-level verdict to read.
PENDING_STATUS = "pending"

EXTERNAL = {
    "temporal": {
        "file": "temporal_arm_external_admission.json",
        "schema": "spot.stage02_temporal_arm_external_admission.v1",
        "verifier_id": "spot.stage02.temporal.arm.independent_verifier.v1",
        "inventory": "temporal_arm_release.json",
        "inventory_schema": "spot.stage02_temporal_arm_release.v1",
        # PUBLISHED: 188 gates, pinned by the canonical hash of the inventory ITSELF.
        "n_gates": W11_N_GATES,
        "gate_inventory_sha256": W11_GATE_INVENTORY_SHA256,
        "gates": (),                       # pinned by HASH, not by a copied list
        "binds_keys": W11_BINDS_KEYS,
        # W11's envelope is not known to carry these top-level assertions; W4's does. Requiring
        # them of W11 would REFUSE the real release, and a fail-closed bug is still a bug.
        "asserts": (),
        "owner": "W11",
    },
    "pathway": {
        "file": "pathway_arm_external_admission.json",
        "schema": "spot.stage02_pathway_arm_external_admission.v1",
        "verifier_id": "spot.stage02.pathway.arm.independent_verifier.v1",
        "inventory": "pathway_arm_release.json",
        "inventory_schema": "spot.stage02_pathway_arm_release.v1",
        "n_gates": len(W4_GATES),
        "gate_inventory_sha256": None,     # pinned by the exact LIST (ef136a9)
        "gates": W4_GATES,
        "binds_keys": frozenset({"producer_release_id", "producer_release_raw_sha256",
                                 "inventory_raw_sha256", "stage1_release_raw_sha256"}),
        "asserts": ("generator_is_not_verifier", "fail_closed"),
        "owner": "W4",
    },
}

PRODUCER_PENDING = "pending_independent_verification"

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
G_EMPTY_INVENTORY = "the_report_verified_an_EMPTY_set_of_arms_or_bundles_and_admitted_it"
G_ENV = "the_report_verified_a_bundle_built_under_another_solver_environment"
G_PRODUCER_SELF_ADMITTED = "the_producer_inventory_admitted_itself"


class AdmissionError(ValueError):
    def __init__(self, gate: str, message: str):
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _refuse(gate: str, message: str) -> None:
    raise AdmissionError(gate, message)


def canon(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def raw(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _load(path: str, what: str) -> Any:
    if not os.path.exists(path):
        _refuse(G_ABSENT, f"no {what} at {os.path.basename(path)}")
    with open(path) as fh:
        return json.load(fh)


def _self_hash(doc: dict, field: str) -> None:
    derived = canon({k: v for k, v in doc.items() if k != field})
    if doc.get(field) != derived:
        _refuse(G_SELF_HASH, f"{field} says {str(doc.get(field))[:16]}; its content hashes to "
                             f"{derived[:16]}")


def check_direct(bundles_root: str, *, condition: str, bundle_dir: str, arm_key: str,
                 stage1: dict) -> dict[str, Any]:
    rel = W10_REPORT_FILE.format(condition=condition)
    rep = _load(os.path.join(bundles_root, rel), "W10 verification report")

    if rep.get("schema_version") != W10_REPORT_SCHEMA:
        _refuse(G_SHAPE, f"schema {rep.get('schema_version')!r}")
    if rep.get("verifier_id") != W10_VERIFIER_ID:
        _refuse(G_VERIFIER, f"verifier_id {rep.get('verifier_id')!r}")
    if rep.get("verifier_code_sha256") != W10_VERIFIER_CODE:
        _refuse(G_VERIFIER, "verifier_code_sha256 is not the pinned W10 checkout")
    if rep.get("independent_of_generator") is not True:
        _refuse(G_VERIFIER, "the report does not claim independence from the generator")
    _self_hash(rep, "report_sha256")

    if rep.get("verdict") != "ADMIT" or rep.get("n_failed") != 0 or rep.get("failed_gates"):
        _refuse(G_VERDICT, f"verdict {rep.get('verdict')!r} / n_failed "
                           f"{rep.get('n_failed')!r}")

    inv = rep.get("gate_inventory") or []
    if len(inv) < W10_MIN_GATES or rep.get("n_gates") != len(inv):
        _refuse(G_GATES, f"{len(inv)} gate(s); an admission requires >= {W10_MIN_GATES}")
    if rep.get("gate_inventory_sha256") != canon(inv):
        _refuse(G_GATES, "the gate inventory does not hash to what the report says")
    for marker in W10_REQUIRED_GATE_MARKERS:
        if not any(marker in g for g in inv):
            _refuse(G_GATES, f"no gate checks {marker!r}")

    bound = rep.get("bound_artifact") or {}
    if bound.get("recompute_mode") != W10_RECOMPUTE_MODE:
        _refuse(G_RECOMPUTE, f"recompute_mode {bound.get('recompute_mode')!r}")

    doc = _load(os.path.join(bundle_dir, "arm_bundle.json"), "arm bundle")
    if str(bound.get("condition")) != condition:
        _refuse(G_BOUND_SUBJECT, f"the report admits condition {bound.get('condition')!r}")
    if str(bound.get("arm_bundle_run_id")) != str(doc.get("arm_bundle_run_id")):
        _refuse(G_BOUND_SUBJECT, "the report admits another bundle")
    if str(bound.get("arm_rows_sha256")) != str(doc.get("arm_rows_sha256")):
        _refuse(G_BOUND_BYTES, "arm_rows_sha256 is not the bundle's")

    files = bound.get("artifact_sha256") or {}
    if not files:
        _refuse(G_BOUND_BYTES, "the report binds no artifact hashes at all")
    for name, want in sorted(files.items()):
        p = os.path.join(bundle_dir, name)
        if not os.path.exists(p) or raw(p) != want:
            _refuse(G_BOUND_BYTES, f"{name}: the report verified different bytes")

    # THE ARM INVENTORY. EMPTY IS A REFUSAL: a report that verified NO arms and admitted
    # anyway has admitted nothing, and an `if keys and ...` guard let exactly that through.
    keys = [str(a.get("arm_key")) for a in (bound.get("arm_inventory") or [])]
    if not keys:
        _refuse(G_EMPTY_INVENTORY,
                "the report's arm_inventory is EMPTY. A verification that covered no arms is "
                "not a verification of any arm — and admitting on it admits nothing")
    if len(keys) != len(set(keys)):
        _refuse(G_EMPTY_INVENTORY, "the arm inventory repeats an arm")
    declared = doc.get("arms") or []
    if declared and len(keys) != len(declared):
        _refuse(G_EMPTY_INVENTORY,
                f"the report verified {len(keys)} arm(s); the bundle ships {len(declared)}. "
                "A report that covered only some of the arms admits only some of them")
    if arm_key not in keys:
        _refuse(G_ARM_NOT_VERIFIED, f"{arm_key!r} is not among the arms this report verified")

    if str(bound.get("solver_lock_sha256")) != SOLVER_LOCK_SHA256:
        _refuse(G_ENV, "the bundle was verified under another solver lock")
    for field, want in stage1.items():
        if field == "stage1_release_raw_sha256":
            continue                     # W10's bound artifact does not carry it; W4's does
        if want and str(bound.get(field)) != str(want):
            _refuse(G_STALE_STAGE1, f"{field}: the report verified a different release")

    return {"admitted": True, "owner": "W10", "report": rel,
            "report_sha256": rep["report_sha256"], "n_gates": rep["n_gates"],
            "n_arms_verified": len(keys), "recompute_mode": W10_RECOMPUTE_MODE}

def _check_external(bundles_root, lane, *, bundle_dir, stage1, EXTERNAL, canon_fn, raw_fn,
                    load_fn, self_hash_fn, refuse):
    """W11 / W4, against their REAL bytes. Shared shape; each side calls it with its own hashes."""
    spec = EXTERNAL[lane]
    stage1 = stage1 or {}
    rep = load_fn(os.path.join(bundles_root, spec["file"]), f"{spec['owner']} admission")

    if rep.get("schema_version") != spec["schema"]:
        refuse(G_SHAPE, f"[{lane}] schema {rep.get('schema_version')!r}")
    if rep.get("verifier_id") != spec["verifier_id"]:
        refuse(G_VERIFIER, f"[{lane}] verifier_id {rep.get('verifier_id')!r}")
    if str(rep.get("lane", lane)) != lane:
        refuse(G_SHAPE, f"[{lane}] the report says it is about lane {rep.get('lane')!r}")
    for field in spec["asserts"]:
        if rep.get(field) is not True:
            refuse(G_VERIFIER, f"[{lane}] the report does not assert {field}")
    if rep.get("verdict") != "ADMIT" or int(rep.get("n_failed") or 0) != 0:
        refuse(G_VERDICT, f"[{lane}] verdict {rep.get('verdict')!r} / n_failed "
                          f"{rep.get('n_failed')!r}")
    self_hash_fn(rep, "report_id")

    # ---- THE GATE INVENTORY. Pinned by its own hash where the verifier publishes one. ----
    inv_gates = list(rep.get("gate_inventory") or ())
    if not inv_gates:
        refuse(G_GATES, f"[{lane}] the report ran NO gates and admitted anyway")
    if spec["n_gates"] and len(inv_gates) != spec["n_gates"]:
        refuse(G_GATES, f"[{lane}] the report ran {len(inv_gates)} gate(s); this verifier "
                        f"publishes {spec['n_gates']}")
    if spec["gate_inventory_sha256"] and canon_fn(inv_gates) != spec["gate_inventory_sha256"]:
        refuse(G_GATES,
               f"[{lane}] the gate inventory hashes to {canon_fn(inv_gates)[:16]}; this "
               f"verifier's PUBLISHED inventory is {spec['gate_inventory_sha256'][:16]}. A "
               "report that ran a different set of gates is not this verifier's admission")
    if spec["gates"] and tuple(inv_gates) != spec["gates"]:
        refuse(G_GATES, f"[{lane}] the gate inventory is not this verifier's exact list")

    # ---- THE BINDS. Exactly the keys the verifier actually emits. ----
    binds = rep.get("binds") or {}
    if not binds:
        refuse(G_BOUND_BYTES, f"[{lane}] the report binds NOTHING")
    missing = sorted(spec["binds_keys"] - set(binds))
    if missing:
        refuse(G_BOUND_BYTES, f"[{lane}] the binds block is missing {missing}")

    # ---- THE PRODUCER INVENTORY IT CLEARED ----
    inv_path = os.path.join(bundles_root, spec["inventory"])
    inv = load_fn(inv_path, f"{lane} producer inventory")
    if inv.get("schema_version") != spec["inventory_schema"]:
        refuse(G_SHAPE, f"[{lane}] the inventory schema is {inv.get('schema_version')!r}")

    # THE NATIVE PENDING STATE. There is NO top-level verdict here: the native inventory says
    # `external_admission.status = pending` and nothing else — "pending is the only honest
    # producer state". Demanding top-level verdict/admitted/self_admitted REFUSED the real
    # release. And any INVENTED pending field is a refusal in the other direction: a producer
    # that wrote itself an `admitted` is a producer that admitted itself.
    if (inv.get("external_admission") or {}).get("status") != PENDING_STATUS:
        refuse(G_PRODUCER_SELF_ADMITTED,
               f"[{lane}] the inventory's external_admission.status is "
               f"{(inv.get('external_admission') or {}).get('status')!r}, not "
               f"{PENDING_STATUS!r}")
    for invented in ("verdict", "admitted", "self_admitted", "verifier_id"):
        if invented in inv:
            refuse(G_PRODUCER_SELF_ADMITTED,
                   f"[{lane}] the native inventory carries no {invented!r}; a producer that "
                   "wrote itself one wrote itself an admission")

    inv_raw = raw_fn(inv_path)
    if str(binds.get("producer_release_raw_sha256")) != inv_raw:
        refuse(G_BOUND_BYTES, f"[{lane}] the report bound another inventory's bytes")
    if str(binds.get("producer_release_id")) != str(inv.get("release_id")):
        refuse(G_BOUND_SUBJECT, f"[{lane}] the report admits another release")
    rederived = canon_fn({k: v for k, v in inv.items() if k != "release_id"})
    if str(inv.get("release_id")) != rederived:
        refuse(G_SELF_HASH, f"[{lane}] the inventory's release_id does not re-derive")
    if lane == "pathway" and str(binds.get("inventory_raw_sha256")) != inv_raw:
        refuse(G_BOUND_BYTES, f"[{lane}] inventory_raw_sha256 is not the inventory on disk")

    # ---- STAGE-1. NESTED for W11 (binds.stage1_release.stage1_release_raw_sha256); flat for W4.
    want_s1 = stage1.get("stage1_release_raw_sha256")
    if want_s1:
        got = (binds.get("stage1_release") or {}).get("stage1_release_raw_sha256") \
            if lane == "temporal" else binds.get("stage1_release_raw_sha256")
        if str(got) != str(want_s1):
            refuse(G_STALE_STAGE1,
                   f"[{lane}] the report cleared a release built against Stage-1 "
                   f"{str(got)[:16]}, not {str(want_s1)[:16]}")

    # ---- THE BUNDLE LIST. EMPTY IS A REFUSAL. ----
    bundles = inv.get("bundles") or []
    if not bundles:
        refuse(G_EMPTY_INVENTORY,
               f"[{lane}] the cleared inventory lists NO bundles. An admission over an empty "
               "release admits nothing, and looks exactly like one that admits everything")
    if int(inv.get("n_bundles") or 0) != len(bundles):
        refuse(G_EMPTY_INVENTORY, f"[{lane}] n_bundles disagrees with the bundle list")

    with open(os.path.join(bundle_dir, "arm_bundle.json")) as fh:
        doc = json.load(fh)
    mine = str(doc.get("bundle_id") or doc.get("pathway_run_id"))
    entry = next((b for b in bundles if str(b.get("bundle_id")) == mine), None)
    if entry is None:
        refuse(G_BOUND_SUBJECT,
               f"[{lane}] the bundle being read ({mine[:16]}) is not in the cleared inventory")

    # ---- EVERY BOUND FILE AND RANKING HASH, against the bytes on disk ----
    for group in ("files", "rankings"):
        for name, e in sorted((entry.get(group) or {}).items()):
            p = os.path.join(bundle_dir, name)
            want = e.get("raw_sha256") if isinstance(e, dict) else e
            if not os.path.exists(p) or raw_fn(p) != want:
                refuse(G_BOUND_BYTES,
                       f"[{lane}] {name}: the cleared inventory bound different bytes")

    return {"admitted": True, "owner": spec["owner"], "report": spec["file"],
            "report_id": rep["report_id"], "n_bundles": len(bundles),
            "n_gates": len(inv_gates), "bound_bundle_id": mine,
            "bound_inventory": spec["inventory"], "bound_inventory_sha256": inv_raw}


def check_external(bundles_root: str, lane: str, *, bundle_dir: str,
                   stage1: dict | None = None) -> dict[str, Any]:
    """The VERIFIER'S external admission check, with the VERIFIER'S OWN hashing."""
    return _check_external(bundles_root, lane, bundle_dir=bundle_dir, stage1=stage1,
                           EXTERNAL=EXTERNAL, canon_fn=canon, raw_fn=raw,
                           load_fn=_load, self_hash_fn=_self_hash, refuse=_refuse)
