"""The Stage-3 contract is FROZEN. These tests make that enforceable, not declarative.

Stage 4 (window 6) rebases onto this branch and binds to
``spot.stage03_drug_annotation.v1``. A freeze that lives only in a handoff document is a
promise nobody can check: the schema bytes could drift and the first thing to notice would
be a Stage-4 integration failure, far from the edit that caused it.

So the frozen hashes are PINNED here. Editing a frozen schema now fails THIS test, in THIS
lane, with a message that says what to do about it — which is the whole point of a freeze.

Unfreezing is allowed. It is just not allowed to happen SILENTLY: bump the schema id, hand
Stage 4 the new hash, and update the pin deliberately.

**What external review finding B6 taught this file.** The r7 freeze pinned the CONTRACT
BYTES and nothing else — so a hole in the VERIFIER (it never recomputed the manifest's own
identity, and accepted a forged one) was completely invisible to the freeze. A frozen schema
that only a broken verifier admits is not a frozen product.

So the freeze now also pins the verifier's GATE INVENTORY. A check cannot be silently
deleted, renamed or lost: the gate set is hashed, and a gate that stops running is a gate
that stops protecting. The pin is over gate NAMES, not verifier source bytes — a comment
edit must not break a freeze, but a missing gate must.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from druglink import artifacts_v2 as av2
from druglink import env
from druglink import schemas

_HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_DIR = os.path.abspath(os.path.join(_HERE, "..", "schemas"))

# The generic contract Stage 4 consumes, and the digest of the whole schema set.
# Re-hashed at the r7 freeze; UNCHANGED at the r8/B6 freeze — B6 was a verifier defect,
# and the contract Stage 4 binds to never moved. See the round's HANDOFF.md §5.
FROZEN_CONTRACT = "spot.stage03_drug_annotation.v1"
FROZEN_CONTRACT_SHA256 = \
    "361d0833d5cb099155ac6ad87557c728fcd64feba1e2ccbf7938bd2c6f4c9eed"

# THE SCHEMA SET MOVED, DELIBERATELY, AND v1 DID NOT.
#
# A NEW schema was ADDED: `spot.stage03_drug_annotation.v2` (the reusable-arm / three-typed-
# origin contract, audit B8 + step 6). The set digest covers names AND per-file hashes, so an
# ADDED file moves it — which is the test doing its job, not a nuisance.
#
# This is the sanctioned unfreeze path and not a re-pin to make a failure go away: v1's own
# bytes are UNCHANGED (FROZEN_CONTRACT_SHA256 above still holds, and
# `test_the_generic_stage4_contract_is_byte_frozen` proves it), because v2 is a new $id rather
# than a widening of v1. Widening the v1 origin enum remains forbidden and is still caught by
# tests/test_stage3_to_stage4_freeze_mutation.py.
#
# The v2 contract moved AGAIN as its schema was completed (the seven-table layout, the
# published `document_file`, per-row namespace, explicit missingness, and the sign-derived
# direction fields). Each move is a deliberate re-pin of a NEW $id — never an edit to v1.
#
# --- THE SELECTION-VIEW ROUND. TWO deliberate moves, and v1 STILL did not budge. ------------
#
# 1. A NEW schema was ADDED: `spot.stage03_selection_view.v1` — the browser-safe PROJECTION of
#    the selection-independent v2 store onto ONE verified Stage-1 v3 selection. It is a new $id,
#    not a widening of anything, and the set digest moves because an ADDED file must move it.
#
# 2. `spot.stage03_drug_annotation.v2` was CORRECTED. Its `independent_report` block carried TWO
#    defects that made it impossible to admit a GENUINE Stage-2 release — and that nobody could
#    hit, because until this round no v2 bundle had ever been built from native bytes:
#
#      * `additionalProperties: false` with no `manifest_sha256` / `manifest_sha256_recomputed`,
#        while `bundle_v2.bind_report` emits exactly those (the NATIVE binding: the report must
#        admit THIS manifest by the semantic self-hash Stage 3 re-derives). Every real release
#        was refused by its own schema;
#      * `verifier_id: {pattern: "independent"}` — the retired substring rule. The real Stage-2
#        verifier is `spot.stage02.run_manifest.verifier.v1` and its id contains no such
#        substring, so this REFUSED every genuine report while ADMITTING any forgery that merely
#        named itself "…independent…". The LOADER was fixed for exactly this reason
#        (`stage2_aggregate._check_report`: independence is the STRUCTURED FIELD
#        `generator_is_not_verifier`, because a name is not a binding) — and the schema kept the
#        rule the code had already thrown out. `table_hashes` had also fallen behind the producer
#        and omitted `pathway_context`.
#
#    A schema that refuses the real thing and admits the forgery is worse than no schema. Fixed,
#    re-pinned, and reported.
#
# --- THE STORE-IDENTITY ROUND (this commit). v1 STILL did not budge. -----------------------
#
# `spot.stage03_selection_view.v1` was CORRECTED. Its `store` block let a view publish a
# `table_hashes` map it had COPIED out of the bundle document and never re-derived — so a view
# built over MUTATED rows still shipped the digest of the rows it was NOT over. The block now
# names all EIGHT tables, the document, the store manifest, the verifier that re-derived them,
# and the gates that ran. See `druglink.view_store`.
#
# AND THE SCHEMA-SET DIGEST ITSELF WAS AMBIGUOUS. This file used to pin a PRIVATE digest of the
# schema directory, while every emitted bundle published a DIFFERENT one (`method.schemas_sha256`,
# from `druglink.schemas.schemas_tree`). Both were called "the schema set". The value handed to
# Stage 4 in the ee4810c commit message (3f23a901…) was the private one — a number that appears
# in NO artifact — while the fixture carried the real one (b618022e…), which nothing pinned and
# which then went STALE when the v2 schema was corrected the following commit. Neither number was
# a lie; the LABEL was. There is now ONE schema-set identity, and it is the one in the artifacts.
#
# --- THE PROJECTION-SEAL ROUND (this commit). v1 STILL did not budge. ----------------------
#
# `spot.stage03_selection_view.v1` was CORRECTED again, and this is the defect it closes:
#
#     the PROJECTED tables were a BARE ROW LIST. Nothing bound them.
#
# `view["tables"]["arm_slots"][0]["arm_context_sha256"] = "MUTATED"`, applied AFTER the view was
# sealed, was ADMITTED by `view_contract.validate()`. Every hash in the document stayed mutually
# consistent — because the view's `store.table_hashes` describe the GLOBAL STORE, and the store
# had not been touched. The rows a consumer READS had been. The store-identity round (d18264c)
# closed the same class of hole one level up (a hash you COPY is not a hash you CHECKED); this
# one is its mirror: the view republished NOTHING about the rows it actually shipped.
#
# So every projected table now carries its own identity — raw bytes of the store table it was
# drawn from, canonical content of the ROWS IT SHIPS, row count, column contract — and the schema
# REQUIRES it. The schema had to move: the view's top level is `additionalProperties: false`, so
# the seal could not even be carried, let alone enforced, without it. See `druglink.view_projection`.
#
# WHAT THE STAGE-4 (W6) AND FRONTEND (W12) OWNERS MUST BE TOLD, before a view is consumed:
#     schema set   23559703… -> b19f26cb…      (= method.schemas_sha256 in EVERY bundle — RE-PINNED)
#     v1 contract  361d0833…   UNCHANGED, and it has never moved (verify this first)
#     v2 contract  e6b537d7…   UNCHANGED this round (still NOT consumed by Stage 4)
#     view schema  abd65920… -> ad2cae5b…      (W12 / W6 consume this — RE-PINNED)
FROZEN_SCHEMA_SET_SHA256 = \
    "fc7ed2674dd62472ecf619b922c135d66070828941520455e5a3cb287392c551"
FROZEN_V2_CONTRACT = "spot.stage03_drug_annotation.v2"
FROZEN_V2_CONTRACT_SHA256 = \
    "54f45eac0c37f2ae886f06155ae0e171879e180ef41e23649edeb02fd4702413"
FROZEN_VIEW_CONTRACT = "spot.stage03_selection_view.v1"
FROZEN_VIEW_CONTRACT_SHA256 = \
    "ad2cae5b3c3d85b18e78fde9a121a6ac7debd4f3404e93e2ed77e8757d44d0f1"

# The verifier's gate inventory on a clean bundle (sorted check names, newline-joined).
# NEW at r8, closing the class of defect B6 belonged to: the freeze pinned the contract
# but not the thing that ADMITS it, so a verifier that had quietly stopped checking
# something was indistinguishable from one that never checked it.
FROZEN_VERIFIER_GATESET_SHA256 = \
    "aeb211bc59da0f1338843ec51a3d29a8b662ca7627c4476f0289a255ecf73dff"
FROZEN_VERIFIER_N_CHECKS = 61          # 60 at r7 + the B6 manifest-identity gate

_UNFREEZE = (
    "\n\nThe Stage-3 contract is FROZEN and Stage 4 binds to these bytes. If this change "
    "is intended: bump the schema $id, re-hash, hand the new hash to the Stage-4 owner "
    "(window 6), and update the pin in this file — in that order. Do not just update the "
    "pin to make this pass; that silently breaks the consumer this freeze exists to "
    "protect."
)

# The vocabulary the contract retired. It is refused structurally elsewhere; here we hold
# the frozen BYTES to never quietly reintroduce it.
RETIRED = (
    "production_candidate", "production_promotion_eligible",
    "may_write_production_pointer", "production_pointer_written",
    "research_pk_annotation_eligible", "spot.stage03_research_annotation.v1",
)


def _sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _schema_set_sha256() -> str:
    """THE PRODUCER'S OWN SCHEMA-SET DIGEST — the one every bundle publishes.

    THERE USED TO BE TWO. This test hashed the schema directory with its own private loop
    (sorted name + per-file hash), while every emitted artifact carried a DIFFERENT number:
    ``method.schemas_sha256``, from :func:`druglink.schemas.schemas_tree`. Two digests over the
    same directory, both called "the schema set" in the round's commit messages — so the number
    handed to the Stage-4 owner (``3f23a901…``) appeared in no artifact anywhere, and the number
    that DID appear in every bundle (``b618022e…``) was never pinned by anything. An external
    reviewer read one, recomputed the other, and could not reconcile them. They were both
    "right"; the LABEL was wrong, and a pin nobody can find in an artifact protects nothing.

    So the freeze now pins the digest the artifacts actually carry. One schema set, one identity,
    checkable in any bundle a consumer opens.
    """
    return schemas.schemas_tree()["schemas_sha256"]


def test_the_generic_stage4_contract_is_byte_frozen():
    path = os.path.join(SCHEMA_DIR, f"{FROZEN_CONTRACT}.json")
    got = _sha256(path)
    assert got == FROZEN_CONTRACT_SHA256, (
        f"{FROZEN_CONTRACT} changed: {got} != pinned {FROZEN_CONTRACT_SHA256}" + _UNFREEZE)


def test_the_whole_schema_set_is_byte_frozen():
    """Catches what a single-file pin cannot: a renamed, deleted or ADDED schema."""
    got = _schema_set_sha256()
    assert got == FROZEN_SCHEMA_SET_SHA256, (
        f"the schemas/ set changed: {got} != pinned {FROZEN_SCHEMA_SET_SHA256}" + _UNFREEZE)


def test_the_PRODUCTION_pin_and_the_FREEZE_pin_are_the_SAME_number():
    """The projection seal binds `schemas_sha256` EXACTLY, against a pin in PRODUCTION code
    (`view_projection.PINNED_SCHEMAS_SHA256`). Two pins over one fact can drift, and a drifted
    pin protects nothing — so they are asserted equal here, once, by name.

    EXACT equality, never a substring and never a pattern. The v2 schema once carried
    `verifier_id: {pattern: "independent"}`: it refused every honest Stage-2 report and admitted
    any forgery that renamed itself. That rule is dead and its SHAPE may not come back.
    """
    from druglink import view_projection as vp
    assert vp.PINNED_SCHEMAS_SHA256 == FROZEN_SCHEMA_SET_SHA256
    assert vp.bound_schemas_sha256() == FROZEN_SCHEMA_SET_SHA256    # re-derived from the files


def test_the_pinned_schema_set_is_the_one_EVERY_BUNDLE_PUBLISHES():
    """The pin and the artifact must be the SAME number, or the pin is about nothing.

    A freeze on a digest no emitted artifact carries cannot be checked by the consumer it exists
    to protect: Stage 4 opens a bundle, reads ``method.schemas_sha256``, and must be able to
    compare it with what it was told.
    """
    assert env.method_block()["schemas_sha256"] == FROZEN_SCHEMA_SET_SHA256


def test_the_published_W12_VIEW_FIXTURE_names_the_CURRENT_schema_set():
    """The example W12 and W6 build against may not carry a STALE schema identity.

    It did. The fixture was emitted at ee4810c, the v2 schema was corrected the next commit, and
    the checked-in view kept publishing the OLD ``schemas_sha256`` — naming a schema set that no
    longer existed. Nothing caught it: the fixture's shape test compares KEYS, not values, and
    the schema-set pin lived in a digest the fixture did not use. A published artifact that names
    the wrong method identity is reproducible only by accident.
    """
    with open(os.path.join(_HERE, "..", "selection_view.fixture.v1.json"), encoding="utf-8") as fh:
        view = json.load(fh)
    got = view["store"]["schemas_sha256"]
    assert got == FROZEN_SCHEMA_SET_SHA256, (
        f"the published selection-view fixture names schema set {got} but the schemas on disk "
        f"hash to {FROZEN_SCHEMA_SET_SHA256}. Regenerate it: "
        "python 03_druglink/tests/emit_view_fixture.py")


def test_the_verifier_gate_inventory_is_frozen(tmp_path, analysis_build, direct_run,
                                               analysis_cache):
    """A gate that stops running is a gate that stops protecting — and B6 proved that is
    not hypothetical. Pin the gate NAMES so a check cannot vanish unnoticed.

    Names, not source bytes: reformatting the verifier must not break a freeze, but
    losing a check must.
    """
    from druglink import artifacts
    from verifier import verify_stage3

    bundle = artifacts.write_bundle(
        output_root=str(tmp_path / "gateset"), artifact_class="analysis",
        document=analysis_build["document"], doc_id=analysis_build["document_id"],
        tables=analysis_build["tables"], created_at="2026-07-12T00:00:00+00:00")
    rep = verify_stage3.verify(
        bundle=bundle, cache_root=analysis_cache, direct_run=direct_run["run_dir"],
        direct_inputs_root=direct_run["inputs_root"], artifact_class="analysis",
        direct_analysis=direct_run["analysis"])

    failed = [n for n, ok, _ in rep.checks if not ok]
    assert not failed, f"an honest bundle must verify with ZERO failures: {failed}"

    names = sorted(n for n, _, _ in rep.checks)
    got = hashlib.sha256("\n".join(names).encode()).hexdigest()

    assert len(rep.checks) == FROZEN_VERIFIER_N_CHECKS, (
        f"the verifier ran {len(rep.checks)} checks, pinned at "
        f"{FROZEN_VERIFIER_N_CHECKS}" + _UNFREEZE)
    assert got == FROZEN_VERIFIER_GATESET_SHA256, (
        f"the verifier gate set changed: {got} != pinned "
        f"{FROZEN_VERIFIER_GATESET_SHA256}" + _UNFREEZE)


def test_the_manifest_identity_gate_is_in_the_frozen_inventory():
    """B6's gate, named explicitly. If it is ever deleted, this says so by name rather
    than leaving a bare hash mismatch for someone to decode."""
    from verifier import checks
    assert checks.MANIFEST_IDENTITY_GATE
    assert set(checks.MANIFEST_IDENTITY_EXCLUDED) == {"manifest_sha256", "created_at"}


def test_the_frozen_contract_still_declares_its_own_id():
    """A hash pin proves the bytes; this proves the bytes still say what we handed over."""
    with open(os.path.join(SCHEMA_DIR, f"{FROZEN_CONTRACT}.json")) as fh:
        doc = json.load(fh)
    assert doc["$id"] == FROZEN_CONTRACT
    assert doc["properties"]["schema_version"]["const"] == FROZEN_CONTRACT
    assert doc["properties"]["artifact_class"]["const"] == "analysis"


def test_v2_is_a_NEW_id_and_v1_is_not_widened_to_reach_it():
    """The v2 lane ships its own contract. It must not have been bought by editing v1.

    The temptation the mutation suite already caught once was to widen v1's `origin_type` enum
    so the three typed v2 origins would validate. That silently moves bytes Stage 4 is bound
    to. So: v2 declares its own $id and its own origins, and v1 still declares only its pair.
    """
    with open(os.path.join(SCHEMA_DIR, f"{FROZEN_V2_CONTRACT}.json")) as fh:
        v2 = json.load(fh)
    with open(os.path.join(SCHEMA_DIR, f"{FROZEN_CONTRACT}.json")) as fh:
        v1 = json.load(fh)

    got = _sha256(os.path.join(SCHEMA_DIR, f"{FROZEN_V2_CONTRACT}.json"))
    assert got == FROZEN_V2_CONTRACT_SHA256, (
        f"the v2 contract moved: {got} != pinned {FROZEN_V2_CONTRACT_SHA256}" + _UNFREEZE)

    assert v2["$id"] == FROZEN_V2_CONTRACT
    assert set(v2["$defs"]["origin_type"]["enum"]) == {
        "direct_target", "temporal_cross_time_measured", "endpoint_pathway_context"}
    # v1 keeps its own pair, and never learns the v2 origins.
    assert set(v1["$defs"]["origin_type"]["enum"]) == {"direct_target", "pathway_node"}
    assert "temporal_cross_time_measured" not in json.dumps(v1)


def test_the_v2_report_binding_admits_the_REAL_verifier_and_not_a_self_named_forgery():
    """The retired substring rule is GONE, and it may never come back.

    `verifier_id: {pattern: "independent"}` refused every genuine Stage-2 report (the real
    verifier is `spot.stage02.run_manifest.verifier.v1`) while admitting anything that named
    itself "…independent…". A name is not a binding. Independence is the STRUCTURED FIELD the
    loader checks; the schema must not re-impose a rule the code correctly threw out.
    """
    with open(os.path.join(SCHEMA_DIR, f"{FROZEN_V2_CONTRACT}.json")) as fh:
        v2 = json.load(fh)
    report = v2["$defs"]["stage2_aggregate_binding"]["properties"]["independent_report"]
    assert "pattern" not in report["properties"]["verifier_id"], (
        "the v2 schema re-imposed a substring rule on the verifier id. It would refuse the real "
        "Stage-2 report and admit a forgery that renamed itself." + _UNFREEZE)
    # It must bind the manifest the report claims to have admitted — by BOTH of the report's
    # own hashes, which is what makes an ADMIT about THESE bytes rather than some others.
    for field in ("manifest_sha256", "manifest_sha256_recomputed"):
        assert field in report["required"], f"the v2 report binding dropped {field!r}" + _UNFREEZE


def test_the_selection_view_contract_is_byte_frozen():
    """W12 (frontend) and W6 (Stage-4) build against these exact bytes.

    The view is a PROJECTION: it never re-ranks, never promotes and never writes back. Those
    guarantees are enum-locked in the schema, so revoking one moves this hash instead of quietly
    changing what a shipped page means.
    """
    path = os.path.join(SCHEMA_DIR, f"{FROZEN_VIEW_CONTRACT}.json")
    got = _sha256(path)
    assert got == FROZEN_VIEW_CONTRACT_SHA256, (
        f"{FROZEN_VIEW_CONTRACT} changed: {got} != pinned {FROZEN_VIEW_CONTRACT_SHA256}"
        + _UNFREEZE)

    with open(path) as fh:
        view = json.load(fh)
    assert view["$id"] == FROZEN_VIEW_CONTRACT
    # A ROLE is a property of the QUESTION. The view assigns one; the store never carries one.
    assert set(view["$defs"]["role"]["enum"]) == {"away_from_A", "toward_B"}
    assert set(view["$defs"]["analysis_mode"]["enum"]) == {
        "within_condition", "temporal_cross_condition"}
    # The three typed origins survive the projection, and stay separable.
    assert set(view["$defs"]["origin_type"]["enum"]) == {
        "direct_target", "temporal_cross_time_measured", "endpoint_pathway_context"}

    # THE VIEW MUST NAME THE BYTES IT IS A PROJECTION OF — all EIGHT tables, the document, and
    # the store manifest. Required in the schema, so a view that goes back to COPYING the
    # bundle's own claims about itself cannot validate.
    store = view["properties"]["store"]
    for field in ("table_hashes", "table_hashes_are_re_derived_not_copied", "document_sha256",
                  "store_manifest_sha256", "store_identity_verifier_id", "store_identity_checks",
                  "n_tables_verified"):
        assert field in store["required"], f"the view store block dropped {field!r}" + _UNFREEZE
    assert store["properties"]["n_tables_verified"]["const"] == 8
    assert sorted(store["properties"]["table_hashes"]["required"]) == sorted(av2.SCIENTIFIC_TABLES)
    assert len(av2.SCIENTIFIC_TABLES) == 8

    # THE VIEW MUST NAME THE ROWS IT SHIPS, not merely the store it drew them from. The `store`
    # block above is about the GLOBAL release; a consumer reads the PROJECTED SUBSET, and until
    # this round nothing in the document was about it. Required in the schema, so a view whose
    # tables are a bare row list cannot validate.
    from druglink import view_projection as vp
    projection = view["properties"]["projection"]
    for field in ("tables", "projection_sha256", "schemas_sha256", "n_tables_sealed",
                  "projection_verifier_id", "projection_checks", "arm_evidence_order_sha256",
                  "projection_schema_set_sha256", "row_order_carries_meaning"):
        assert field in projection["required"], f"the projection seal dropped {field!r}" + _UNFREEZE
    assert "projection" in view["required"]
    assert projection["properties"]["n_tables_sealed"]["const"] == 7
    assert sorted(projection["properties"]["tables"]["required"]) == sorted(vp.SEALED_TABLES)
    # Every sealed table names RAW bytes AND canonical content. They fail differently.
    for field in ("raw_sha256", "content_sha256", "row_count", "schema_id"):
        assert field in view["$defs"]["sealed_table"]["required"]
    # An EXACT const, never a pattern — the retired substring rule may not come back in this shape.
    assert projection["properties"]["projection_verifier_id"]["const"] == vp.PROJECTION_VERIFIER_ID
    assert "pattern" not in projection["properties"]["projection_verifier_id"]
    # The receipts are stamped with the projection they admit, so a stale one cannot travel.
    for block in ("store", "admission"):
        assert "projection_sha256" in view["properties"][block]["required"]

    # The guarantees are REQUIRED, so a view that quietly drops one fails its own schema.
    for promise in ("the_stores_eight_table_hashes_are_re_derived_before_projection_never_copied",
                    "the_global_store_carries_no_selection_identity_at_any_depth",
                    "a_single_cell_edited_after_sealing_is_refused_by_name",
                    "every_projected_table_carries_its_own_raw_and_canonical_identity",
                    "a_row_set_is_a_set_and_a_reorder_is_not_a_finding_but_a_duplicate_is_refused",
                    "the_arm_evidence_order_is_meaning_and_a_swap_of_the_poles_is_refused",
                    "the_view_never_re_ranks_or_re_orders_the_store",
                    "the_view_never_promotes_an_evidence_class",
                    "the_view_never_writes_back_to_the_store",
                    "arm_keys_are_matched_by_exact_string_equality_never_by_prefix"):
        assert promise in view["properties"]["guarantees"]["required"]


@pytest.mark.parametrize("term", RETIRED)
def test_no_frozen_schema_reintroduces_retired_vocabulary(term):
    for name in sorted(os.listdir(SCHEMA_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(SCHEMA_DIR, name)) as fh:
            body = fh.read()
        # The drug-annotation contract NAMES the retired terms in its description, to say
        # they are refused. That is the contract speaking, not a field being offered.
        doc = json.loads(body)
        offered = json.dumps({k: v for k, v in doc.items() if k != "description"})
        assert term not in offered, (
            f"{name} reintroduces retired vocabulary {term!r} outside its description")
