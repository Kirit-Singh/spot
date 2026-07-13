"""The TRUE Stage-3 v2 admission contract — native `drug_annotation.v2.json` + `manifest.v2`.

This is a SECOND, separate contract module. It is not `stage3_contract_v2.py`, which despite its
name is the v2 of Stage 4's RESTATEMENT of the **v1** contract: that file pins
`spot.stage03_drug_annotation.v1/2026-07-12-r8`, reads `drug_annotation.json`, and knows the old
candidate keys. Widening it to swallow v2 would be the misreading the seam exists to prevent — a v2
document read by a v1 reader, its new fields silently ignored, its evidence admitted against a
contract nobody checked it against, every downstream hash a self-consistent hash of a misreading.

So: a new module, a new set of pins, and until W16 publishes them, **every pin is None and every v2
bundle is refused**.

    NATIVE_DOC        = None    ← W16 names the document file
    NATIVE_MANIFEST   = None    ← W16 names the manifest file
    SCHEMA_SET_SHA256 = None    ← W16 PUBLISHES; Stage 4 re-derives and compares
    VERIFIER_ENTRY    = None    ← W16 names it. NOT verifier.verify_stage3, which is v1's
    MANIFEST_IDENTITY = None    ← the manifest's own schema id

Each is a single line. Pinning is an ACT — one deliberate edit per value, after reading W16's
handoff — never a silent widening to accept whatever arrived.

Why every one of them is load-bearing:

  * a hash Stage 4 computes for itself pins nothing. It is Stage 4 agreeing with Stage 4;
  * v1's verifier pointed at a v2 bundle judges the v2 contract by v1's rules, or judges nothing,
    and either way exits and lets the bundle be recorded as externally verified. That is not a
    weaker gate. It is a gate that reports PASS without having looked, while the operator believes
    gate 2 ran;
  * a document Stage 4 finds by guessing a filename is a document Stage 4 might not find at all.

`admit_v2()` below is the shape of the real admission, written now so that when the pins land the
change is the pins and the field mapping — not the architecture.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional

from .firewall import Rejection

STAGE3_V2_SCHEMA = "spot.stage03_drug_annotation.v2"

# ─── THE PINS. Every one None = every v2 bundle refused. ────────────────────────────────────
#
# W16 supplies all five. Nothing here is guessed, and nothing may be inferred from a fixture: a
# fixture that disagrees with the contract it demonstrates will be believed over the contract.

# STRUCTURE — published by W16 and corrected by the native-v2 audit. These are facts now, not
# guesses, so they are pinned. Note `manifest.json`, NOT `manifest.v2.json`: the manifest keeps its
# v1 filename and declares its v2 identity INSIDE. A contract is what a document declares, never
# what its filename suggests — and here the filename would have suggested the wrong thing.
NATIVE_DOC: str = "drug_annotation.v2.json"
NATIVE_MANIFEST: str = "manifest.json"
DOC_IDENTITY: str = "spot.stage03_drug_annotation.v2"
MANIFEST_IDENTITY: str = "spot.stage03_manifest.v2"
VERIFIER_ENTRY: str = "verifier.verify_stage3_v2"

# The eight native v2 tables. Enumerated, so a bundle missing one is refused rather than partially
# read — and so a table added later that nobody added here cannot arrive unnoticed.
NATIVE_TABLES: tuple[str, ...] = (
    "arm_slots", "target_drug_edges", "pathway_context", "arm_summaries",
    "candidates", "source_records", "dispositions", "provenance",
)

# ─── THE ONE PIN STILL OWED ─────────────────────────────────────────────────────────────────
#
# `method.schemas_sha256`, as PUBLISHED by W16 in the bundle's method block.
#
# I had this wrong, and the correction matters. My first version hashed the document and manifest
# INSTANCES and called the result the schema set. That is not schema-set identity — it is a digest
# of one bundle's contents, which changes with every bundle. Pinning it would have pinned a
# particular emission and refused every other one, while wearing the name of a contract pin.
#
# The schema SET identifies the CONTRACT: the schemas the bundle was written against. It is
# published in `method.schemas_sha256`, Stage 4 compares against it, and Stage 4 does not compute
# it for itself — a hash Stage 4 derived would just be Stage 4 agreeing with Stage 4.
SCHEMAS_SHA256: Optional[str] = None

# The v1 verifier, named so it can be refused by name. Running this against a v2 bundle is the
# failure mode that looks most like success.
V1_VERIFIER_ENTRY = "verifier.verify_stage3"

# What `verifier.verify_stage3_v2` needs, out-of-process. Every one of these is a separate input
# the verifier re-derives from — which is exactly why gate 2 is worth running: it does not take the
# bundle's word for its own upstream.
# Read from W16's `verifier/verify_stage3_v2.py` at ee4810c — the real flags, not my guess at them.
# I had `bundle_root_15`; the flag is `--stage2-bundles-root`. A flag Stage 4 invented is a verifier
# Stage 4 never actually runs.
VERIFIER_INPUTS: tuple[str, ...] = (
    "bundle",                      # the Stage-3 v2 store bundle
    "stage2_aggregate_manifest",   # spot.stage02_run_manifest.v3_topology_only
    "stage2_aggregate_report",     # spot.stage02_run_manifest_verification.v1
    "stage2_bundles_root",
    "stage1_release",
    "universe_store",
    "stage3_bridge",
    "artifact_class",
)
VERIFIER_PASS_EXIT = 0             # `return 1 if rep.failures else 0`

# ─── THE SELECTION VIEW — a SEPARATE artifact, and the architecture agrees with Stage 4's ────
#
# W16 emits `spot.stage03_selection_view.v1` beside the store, and enforces the same rule Stage 4
# does: the STORE is selection-independent, and a selection identity or an A/B role LEAKING into it
# is a refusal (`a_selection_identity_leaked_into_the_global_store`). Selection is a projection.
#
# The view carries BOTH identities, and W16 says why binding only one is a silent failure in either
# direction: with only `selection_id`, a method revision looks like a NEW question; with only
# `question_id`, a stale run masquerades as current. Stage 4 binds both.
SELECTION_VIEW_SCHEMA = "spot.stage03_selection_view.v1"
STORE_SCHEMA = "spot.stage03_drug_annotation.v2"

# The view's seven row tables (the store's eighth, `provenance`, is not projected).
VIEW_TABLES: tuple[str, ...] = (
    "arm_slots", "arm_summaries", "candidates", "dispositions",
    "pathway_context", "source_records", "target_drug_edges",
)

# Every one of these must be FALSE in an admitted view. A view that PERMITS a combined objective is
# a view that may contain one, and Stage 4 refuses the permission, not merely the value: a flag that
# says "allowed" is a promise nobody kept yet.
FORBIDDEN_PERMISSIONS = (
    "combined_objective_permitted",
    "candidate_rank_permitted",     # per-arm `arm_rank` is fine; a CANDIDATE-level rank is not
    "headline_arm_permitted",
    "p_q_fdr_permitted",
)

# Arm keys are matched by EXACT STRING EQUALITY, never by prefix. W16 states this as a guarantee
# (`arm_keys_are_matched_by_exact_string_equality_never_by_prefix`), and Stage 4's projection
# already does exactly that — a prefix match would silently merge `away_from_A` with
# `away_from_A_strict`, which are different arms.
ARM_KEY_MATCH = "exact_string_equality"

# ─── THE QUESTION IDENTITY (v2 only) ────────────────────────────────────────────────────────
#
# Aligned to Stage-1 `539431d`: the v2 `question_id` is a **16-hex, biology-only** identity derived
# over the ENDPOINT CONDITIONS, independently re-derived, and **distinct from `selection_id`**.
#
# W16's current uncommitted `selection_v3` identity is a **64-hex alternate payload** — stale and
# wrong. Those bytes are not pinned and not admitted, and this rejects them BY NAME rather than
# letting a plausible-looking hash through.
#
# Why each rule is load-bearing:
#
#   * 16-hex, biology-only. A question is a statement about BIOLOGY — which endpoint conditions are
#     being contrasted. An identity that absorbs run ids, code hashes or wall-clock into itself is
#     not a question identity: the same biological question asked twice would get two ids, and
#     nothing downstream could tell that it was the same question.
#   * 64-hex is REJECTED, not merely "wrong length". A 64-hex value is what you get when a
#     full-payload sha256 is handed over in place of the biology-only derivation. It LOOKS like an
#     id, it is stable, it is self-consistent — and it identifies the wrong thing. That is exactly
#     the class of value that gets pinned by accident.
#   * DISTINCT from selection_id. A question_id equal to the selection_id is not a question
#     identity; it is the selection wearing a question's name, and every "same question, different
#     selection" comparison downstream silently becomes false.
#
# v1 is untouched: its ids are 32-hex with an `rq_` prefix, and this rule is v2-only. It lives in
# the v2 module for exactly that reason.
QUESTION_ID_HEX_LEN = 16
REJECTED_QUESTION_ID_HEX_LENS = (64,)
STAGE1_ALIGNMENT = "539431d"


class Stage3V2QuestionIdentityRejected(Rejection):
    """The v2 question identity is not the biology-only one Stage 1 derives."""


def assert_question_identity(question_id: Any, selection_id: Any) -> None:
    """The v2 question identity: 16-hex, biology-only, and NOT the selection id."""
    qid = str(question_id or "")
    core = qid[3:] if qid.startswith("rq_") else qid

    if not core or any(c not in "0123456789abcdef" for c in core.lower()):
        raise Stage3V2QuestionIdentityRejected(
            "stage3_v2_question_id_not_hex",
            f"question_id {qid!r} is not a hex identity. Stage 4 expects the biology-only "
            f"{QUESTION_ID_HEX_LEN}-hex question id Stage 1 derives over the endpoint conditions "
            f"(aligned to Stage-1 {STAGE1_ALIGNMENT}).",
        )

    if len(core) in REJECTED_QUESTION_ID_HEX_LENS:
        raise Stage3V2QuestionIdentityRejected(
            "stage3_v2_question_id_alternate_payload",
            f"question_id {qid!r} is {len(core)}-hex. That is the ALTERNATE PAYLOAD identity — a "
            "full-payload digest handed over in place of the biology-only derivation. It looks "
            "like an id, it is stable, it is self-consistent, and it identifies the wrong thing: "
            "the same biological question asked twice would get two ids, and nothing downstream "
            f"could tell it was the same question. Stage 4 requires the {QUESTION_ID_HEX_LEN}-hex "
            f"biology-only question id over the endpoint conditions (Stage-1 {STAGE1_ALIGNMENT}), "
            "independently re-derived.",
        )

    if len(core) != QUESTION_ID_HEX_LEN:
        raise Stage3V2QuestionIdentityRejected(
            "stage3_v2_question_id_wrong_width",
            f"question_id {qid!r} is {len(core)}-hex; Stage 4 expects {QUESTION_ID_HEX_LEN}-hex "
            f"(biology-only, over the endpoint conditions, Stage-1 {STAGE1_ALIGNMENT}).",
        )

    if str(selection_id or "") == qid:
        raise Stage3V2QuestionIdentityRejected(
            "stage3_v2_question_id_not_distinct_from_selection",
            f"question_id and selection_id are both {qid!r}. A question identity equal to the "
            "selection identity is not a question identity — it is the selection wearing a "
            "question's name, and every 'same question, different selection' comparison "
            "downstream silently becomes false.",
        )


class Stage3V2ContractNotPinned(Rejection):
    """A v2 bundle arrived before Stage 4 pinned the v2 contract. Refused, never guessed at."""


# ─── RANK: per-arm is LEGITIMATE, combined is not ───────────────────────────────────────────
#
# I had this wrong too, and the error would have refused every real v2 bundle.
#
# v2 carries a **nullable per-arm `arm_rank`** — a candidate's position WITHIN one arm, which is a
# statement about that arm and nothing else. That is legitimate evidence and Stage 4 carries it.
#
# What is prohibited is a COMBINED or CANDIDATE-LEVEL rank: one number ordering candidates ACROSS
# arms. That is the combined objective, and it is the thing this whole pipeline refuses to compute —
# it fuses arms that were never comparable and hides the fusion behind a single tidy integer.
#
# The distinction is the difference between "3rd strongest in away_from_A" (a fact about an arm) and
# "3rd best candidate" (a verdict nobody is entitled to).
PERMITTED_RANK_FIELDS = ("arm_rank",)
PROHIBITED_RANK_FIELDS = (
    "rank", "overall_rank", "candidate_rank", "combined_rank", "combined_score",
    "overall_score", "composite_score", "priority", "traffic_light",
)


class Stage3V2CombinedRankRejected(Rejection):
    """A rank across arms is a combined objective wearing an integer's clothes."""


def assert_no_combined_rank(row: dict[str, Any], where: str) -> None:
    """Per-arm `arm_rank` is fine. A candidate-level rank is not."""
    found = sorted(f for f in PROHIBITED_RANK_FIELDS if f in row)
    if found:
        raise Stage3V2CombinedRankRejected(
            "stage3_v2_combined_rank_present",
            f"{where} carries {found}. A per-arm `arm_rank` is a statement about ONE arm and is "
            "carried; a candidate-level or combined rank orders candidates ACROSS arms that were "
            "never comparable, and hides the fusion behind a single tidy integer. "
            f"Permitted: {list(PERMITTED_RANK_FIELDS)}.",
        )


def pins() -> dict[str, Optional[str]]:
    """Everything Stage 4 binds. Only `schemas_sha256` is still owed by W16."""
    return {
        "native_doc": NATIVE_DOC,
        "native_manifest": NATIVE_MANIFEST,
        "doc_identity": DOC_IDENTITY,
        "manifest_identity": MANIFEST_IDENTITY,
        "verifier_entry": VERIFIER_ENTRY,
        "schemas_sha256": SCHEMAS_SHA256,
    }


def unpinned() -> list[str]:
    """Which pins W16 still owes. Named individually, so 'not ready' is never a vague state."""
    return sorted(name for name, value in pins().items() if value is None)


def is_pinned() -> bool:
    return not unpinned()


def assert_pinned() -> None:
    """The gate. Refuses while ANY pin is missing — a partially pinned contract is not a contract."""
    missing = unpinned()
    if not missing:
        return
    raise Stage3V2ContractNotPinned(
        "stage3_v2_contract_not_pinned",
        f"Stage 4 has not pinned the v2 contract: {missing} are unset. The structure is published "
        f"(doc={NATIVE_DOC}, manifest={NATIVE_MANIFEST}, verifier={VERIFIER_ENTRY}); what is still "
        "owed is the PUBLISHED `method.schemas_sha256` — the identity of the SCHEMAS the bundle was "
        "written against. Stage 4 does not compute it for itself: a hash Stage 4 derived would be "
        "Stage 4 agreeing with Stage 4, and a digest of the document+manifest INSTANCES is not "
        "schema-set identity at all — it changes with every bundle. Stage 4 will NOT fall back to "
        f"the v1 reader, and will NOT fall back to {V1_VERIFIER_ENTRY!r}: judging a v2 bundle by "
        "v1's rules reports PASS without having looked.",
    )


def published_schemas_sha256(bundle_dir: str) -> str:
    """The schema-set identity the BUNDLE publishes, read from `method.schemas_sha256`.

    Read, not derived. Stage 4 compares it against the pin W16 published; it never computes a
    substitute, and it never mistakes a digest of this bundle's contents for the identity of the
    contract the bundle was written against.
    """
    path = os.path.join(bundle_dir, NATIVE_DOC)
    if not os.path.exists(path):
        raise Stage3V2ContractNotPinned(
            "stage3_v2_native_document_missing",
            f"the v2 contract names {NATIVE_DOC!r}, and this bundle does not carry it. Stage 4 "
            "does not go looking for a document under another name: a file found by guessing is a "
            "file that might not be the one the contract meant.",
        )
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)

    declared = ((doc.get("method") or {}).get("schemas_sha256"))
    if not declared:
        raise Stage3V2ContractNotPinned(
            "stage3_v2_schemas_sha256_absent",
            f"{NATIVE_DOC} declares no `method.schemas_sha256`. A bundle that cannot say which "
            "schemas it was written against cannot be checked against the schemas Stage 4 pinned.",
        )
    return str(declared)


def verifier_argv(bundle_dir: str, inputs: dict[str, str]) -> list[str]:
    """The out-of-process gate-2 invocation. Every input is REQUIRED — the verifier re-derives from
    each of them, which is precisely why it does not take the bundle's word for its own upstream.

    Deliberately NOT gated on `assert_pinned()`: the verifier entry and its inputs are published and
    pinned, and the outstanding `schemas_sha256` is a separate check that `admit_v2` makes. Building
    the argv is not admitting the bundle.
    """
    missing = [name for name in VERIFIER_INPUTS if name != "bundle" and name not in inputs]
    if missing:
        raise Stage3V2ContractNotPinned(
            "stage3_v2_verifier_inputs_missing",
            f"{VERIFIER_ENTRY} requires {list(VERIFIER_INPUTS)} and {missing} were not supplied. "
            "A verifier run without its upstream inputs cannot re-derive anything, so it would "
            "confirm only that the bundle agrees with itself — which a forged bundle also does.",
        )

    argv = [sys.executable, "-m", VERIFIER_ENTRY, "--bundle", bundle_dir]
    for name in VERIFIER_INPUTS:
        if name == "bundle":
            continue
        argv += [f"--{name.replace('_', '-')}", inputs[name]]
    return argv


class Stage3V2ViewRejected(Rejection):
    """The selection view cannot be bound, or permits something Stage 4 refuses."""


def bind_selection_view_v2(view: dict[str, Any]) -> dict[str, Any]:
    """Bind W16's `spot.stage03_selection_view.v1`. Both identities, and no permissions.

    PROVISIONAL: W16 is still running its own verification of ee4810c. This binds the contract so
    the adapter is finished, and it does NOT mark Stage 3 -> 4 admitted. Admission needs an
    independent re-audit and one real bundle through the whole chain.
    """
    declared = str(view.get("schema_version") or "")
    if declared != SELECTION_VIEW_SCHEMA:
        raise Stage3V2ViewRejected(
            "stage3_v2_view_schema_unknown",
            f"the selection view declares {declared!r}, not {SELECTION_VIEW_SCHEMA!r}.",
        )

    selection = view.get("selection") or {}
    question_id = selection.get("question_id")
    selection_id = selection.get("selection_id")

    # BOTH, and W16 says exactly why: with only `selection_id`, a method revision looks like a NEW
    # question; with only `question_id`, a stale run masquerades as current. Binding one is a silent
    # failure in either direction.
    if not question_id or not selection_id:
        raise Stage3V2ViewRejected(
            "stage3_v2_view_identity_incomplete",
            "the view must carry BOTH `question_id` and `selection_id`. With only selection_id a "
            "method revision looks like a new question; with only question_id a stale run "
            "masquerades as current. Binding one is a silent failure in either direction.",
        )
    assert_question_identity(question_id, selection_id)

    # `selection_full_sha256` is the 64-hex form of the SELECTION id and is entirely legitimate. It
    # is not, and must never be used as, the question identity — that confusion is the alternate
    # payload this module refuses by name.
    full = str(selection.get("selection_full_sha256") or "")
    if full and not full.startswith(str(selection_id)):
        raise Stage3V2ViewRejected(
            "stage3_v2_selection_full_sha_mismatch",
            f"`selection_full_sha256` ({full[:16]}…) does not begin with `selection_id` "
            f"({selection_id!r}). The 16-hex id is the first 16 of the 64-hex digest; if they "
            "disagree, one of them is stale.",
        )

    permitted = sorted(f for f in FORBIDDEN_PERMISSIONS if view.get(f))
    if permitted:
        raise Stage3V2ViewRejected(
            "stage3_v2_view_permits_a_forbidden_output",
            f"the view sets {permitted} to true. Stage 4 refuses the PERMISSION, not merely the "
            "value: a flag that says a combined objective, a candidate-level rank, a headline arm "
            "or a p/q value is allowed is a promise nobody has kept yet. A per-arm `arm_rank` is "
            "fine — it is a statement about one arm; a candidate-level rank orders candidates "
            "across arms that were never comparable.",
        )

    store = view.get("store") or {}
    if str(store.get("bundle_schema") or "") != STORE_SCHEMA:
        raise Stage3V2ViewRejected(
            "stage3_v2_view_store_schema_mismatch",
            f"the view projects a store declaring {store.get('bundle_schema')!r}, and Stage 4 "
            f"admits {STORE_SCHEMA!r}.",
        )

    missing_tables = sorted(set(VIEW_TABLES) - set((view.get("tables") or {})))
    if missing_tables:
        raise Stage3V2ViewRejected(
            "stage3_v2_view_table_missing",
            f"the view is missing {missing_tables}. A table absent from a projection is "
            "indistinguishable from a table whose rows nobody found.",
        )

    return {
        "schema": SELECTION_VIEW_SCHEMA,
        "view_id": view.get("view_id"),
        "view_content_sha256": view.get("view_content_sha256"),
        "view_method_id": view.get("view_method_id"),
        "question_id": question_id,
        "selection_id": selection_id,
        "analysis_mode": selection.get("analysis_mode"),
        "conditions": selection.get("conditions"),
        "selected_arms": view.get("selected_arms"),
        "store_bundle_id": store.get("bundle_id"),
        "store_canonical_content_sha256": store.get("canonical_content_sha256"),
        "arm_key_match": ARM_KEY_MATCH,
        # NOT admitted. Bound.
        "admission_state": "provisional_pending_independent_reaudit_and_one_real_bundle",
    }


# ─── THE RECEIPT CHECKS — why ee4810c is NOT pinned ──────────────────────────────────────────
#
# The independent audit found the identity and parity issues fixed at ee4810c, and two that are
# not. Both are visible in the bytes, and both are the kind that a green suite cannot see:
#
#   1. POST-SEAL TABLE MUTATION. The view's `tables` are plain lists of rows. The sealed
#      `table_hashes` live in `store`, and describe the STORE's tables — they are never re-bound to
#      the PROJECTED rows. So a row can be changed, added or dropped in the view after the store was
#      sealed, and nothing in the view disagrees with anything else in the view. Every hash still
#      reproduces. A projection that cannot be checked against the thing it projects is not a
#      projection; it is a second, unverified artifact wearing the store's identity.
#
#   2. THE VERIFIED STORE RECEIPT IS NOT REBOUND. The view names the store's hashes but does not
#      carry a receipt Stage 4 can re-derive the projection from. "The store verified" and "this
#      view came from that verified store" are different claims, and only the first is made.
#
# Stage 4 therefore REFUSES ee4810c by name. The refusal IS the finding — it is not a bug in the
# adapter, and it must not be worked around by pinning.
STORE_RECEIPT_FIELDS = ("bundle_id", "canonical_content_sha256", "code_tree_sha256",
                        "schemas_sha256", "table_hashes")


def assert_tables_sealed(view: dict[str, Any]) -> None:
    """Every projected table must be bound to a hash Stage 4 can re-derive from ITS OWN rows."""
    tables = view.get("tables") or {}
    unsealed = sorted(name for name, rows in tables.items() if isinstance(rows, list))
    if unsealed:
        raise Stage3V2ViewRejected(
            "stage3_v2_view_tables_not_sealed",
            f"the view projects {unsealed} as bare row lists, with no per-table content hash bound "
            "to the projected rows. The sealed `store.table_hashes` describe the STORE's tables, "
            "not this projection — so a row can be changed, added or dropped after the store was "
            "sealed and nothing in the view would disagree with anything else in the view. Every "
            "hash would still reproduce. A projection that cannot be checked against the thing it "
            "projects is a second, unverified artifact wearing the store's identity. Each table "
            "must carry the hash of its own projected rows, and the row set it was projected FROM.",
        )


def assert_store_receipt_rebound(view: dict[str, Any]) -> None:
    """"The store verified" and "this view came from that verified store" are different claims."""
    store = view.get("store") or {}
    missing = sorted(f for f in STORE_RECEIPT_FIELDS if not store.get(f))
    if missing:
        raise Stage3V2ViewRejected(
            "stage3_v2_store_receipt_incomplete",
            f"the view's store block is missing {missing}. Stage 4 re-derives the projection from "
            "the verified store; it cannot do that from a store it cannot identify.",
        )

    if not view.get("view_content_sha256"):
        raise Stage3V2ViewRejected(
            "stage3_v2_view_content_not_sealed",
            "the view declares no `view_content_sha256`, so nothing binds its content to the store "
            "it claims to project.",
        )


def assert_store_is_selection_independent(view: dict[str, Any]) -> None:
    """No selection identity, and no A/B role, may live in the STORE.

    W16 enforces this at emission (`a_selection_identity_leaked_into_the_global_store`) — Stage 4
    re-checks it, because a gate the producer runs on itself is not a gate. A store carrying a
    question id is a store built FOR one question, and it is not reusable for the next.
    """
    store = view.get("store") or {}
    leaked = sorted(k for k in store
                    if k.lower() in ("selection_id", "question_id", "selection_roles", "roles"))
    if leaked:
        raise Stage3V2ViewRejected(
            "stage3_v2_selection_leaked_into_the_store",
            f"the store block carries {leaked}. A store that knows which question it was built for "
            "is not selection-independent, and the next question needs a whole new acquisition.",
        )


def check_view_receipt(view: dict[str, Any]) -> dict[str, Any]:
    """Every receipt check, in order. Refuses ee4810c — and the refusal is the finding."""
    bound = bind_selection_view_v2(view)
    assert_store_is_selection_independent(view)
    assert_store_receipt_rebound(view)
    assert_tables_sealed(view)
    bound["receipt_state"] = "checked"
    return bound


def admit_v2(bundle_dir: str, *, inputs: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """The real v2 admission. Refuses today: `schemas_sha256` is unpinned.

    Written now so that when W16 publishes the hash, the change is the PIN and the field mapping —
    not the architecture. The gate order is the point:

        1. the contract is pinned at all                (else nothing below can be checked)
        2. both native documents are present, by their REAL names
        3. each declares its v2 identity (a contract is what a document DECLARES)
        4. the bundle's published `method.schemas_sha256` EQUALS the pin
        5. all eight native tables are present
        6. gate 2: verify_stage3_v2 PASSES out-of-process, over all its required inputs

    Only then are candidates read — with multi-target / multi-mechanism evidence and its provenance
    preserved, never collapsed to one target or one mechanism per candidate.
    """
    assert_pinned()

    declared = published_schemas_sha256(bundle_dir)
    if declared != SCHEMAS_SHA256:
        raise Stage3V2ContractNotPinned(
            "stage3_v2_schemas_sha256_mismatch",
            f"this bundle was written against schema set {declared[:16]}…, and Stage 4 is pinned "
            f"to {str(SCHEMAS_SHA256)[:16]}…. The contract Stage 4 verified is not the contract "
            "that produced this bundle. Re-pinning is a deliberate act after re-reading W16's "
            "handoff — never a silent widening to accept whatever arrived.",
        )

    raise Stage3V2ContractNotPinned(  # pragma: no cover - unreachable until the pin lands
        "stage3_v2_adapter_not_written",
        "the v2 field mapping is written against the fields W16 publishes, over the eight native "
        f"tables {list(NATIVE_TABLES)}, preserving multi-target/multi-mechanism evidence and its "
        "provenance. Supply the minimal admitted fixture and it will be written.",
    )
