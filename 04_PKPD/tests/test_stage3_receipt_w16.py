"""W16's ACTUAL receipt, read from disk. Not a receipt Stage 4 wrote for itself.

I invented `spot.stage03_independent_receipt.v2` and then "verified" it — from a dict Stage 4 handed
itself, against a schema no producer emits. Two schemas for one handoff is how a chain silently
breaks: each side verifies happily against its own idea of the document, and neither is verifying the
other. The authoritative artifact is **`spot.stage03_membership_receipt.v1`**, and these tests
consume the real emitted bytes.

The bundle is W16's worktree. If it is absent the real-chain tests SKIP — loudly, never silently
passing: a green suite that never opened the file is the failure mode this whole module exists to
catch.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil

import pytest

from analysis.arm_key_codec import MembershipError
from analysis.projection import build_v2_projection
from analysis.stage3_receipt import (
    RECEIPT_SCHEMA,
    SELF_HASH_FIELD,
    canonical_sha256,
    load_receipt,
)

W16_BUNDLE = "/home/tcelab/worktrees/spot-stage3-membership/03_druglink"
W16_RECEIPT = os.path.join(W16_BUNDLE, "membership_receipt.fixture.v1.json")
W16_VIEW = os.path.join(W16_BUNDLE, "selection_view.fixture.v1.json")

real_bytes = pytest.mark.skipif(
    not os.path.exists(W16_RECEIPT),
    reason=f"W16's emitted receipt is not on this host ({W16_RECEIPT})")


def _bundle(tmp_path) -> str:
    """A WRITABLE copy of W16's real bundle — so an attack can edit bytes without touching theirs."""
    dst = os.path.join(str(tmp_path), "bundle")
    os.makedirs(dst, exist_ok=True)
    for name in ("membership_receipt.fixture.v1.json", "selection_view.fixture.v1.json"):
        shutil.copy(os.path.join(W16_BUNDLE, name), os.path.join(dst, name))
    return dst


def _receipt_path(bundle: str) -> str:
    return os.path.join(bundle, "membership_receipt.fixture.v1.json")


def _reseal(receipt: dict) -> dict:
    """Re-seal after an edit — so the attack is not caught by the self-hash but by the ARTIFACTS.
    The point of a chain is that every link has to be forged."""
    body = {k: v for k, v in receipt.items() if k != SELF_HASH_FIELD}
    receipt[SELF_HASH_FIELD] = canonical_sha256(body)
    return receipt


def _write(path: str, doc: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


# ------------------------------------------------------------------ the real chain, end to end

@real_bytes
def test_W16s_ACTUAL_receipt_is_ADMITTED_with_every_hash_recomputed_from_disk():
    receipt, view = load_receipt(W16_RECEIPT, bundle_dir=W16_BUNDLE)

    assert receipt["schema_version"] == RECEIPT_SCHEMA
    assert receipt["verdict"] == "admit"
    # GENERATOR != VERIFIER. The boolean `generator_is_not_verifier` is a claim a producer could
    # simply write; the two named ids are the fact.
    assert receipt["generator_id"] != receipt["verifier_id"]
    assert receipt["membership"]["rule_id"] == \
        "spot.stage03.candidate_membership.evidence_rederived.v2"
    # The corroborating rows travel INSIDE the view, hash-bound by it — and the view is returned
    # SEPARATELY, never stuffed into the receipt dict.
    assert "_view_document" not in receipt
    tables = view["tables"]
    assert tables["candidates"] and tables["arm_summaries"]


@real_bytes
def test_the_REAL_view_and_receipt_project_END_TO_END():
    """Stage 4 displays W16's real candidates under W16's real selection, with membership re-derived
    from the store and every typed placement corroborated."""
    _receipt, view = load_receipt(W16_RECEIPT, bundle_dir=W16_BUNDLE)
    candidates = view["tables"]["candidates"]

    scorecards = {"scorecard_set_id": "sc1",
                  "candidates": [{"candidate_id": c["candidate_id"]} for c in candidates]}
    doc = build_v2_projection(scorecards, candidates, view,
                              stage3_receipt_path=W16_RECEIPT, stage3_bundle_dir=W16_BUNDLE)

    assert doc["counts"]["n_stage4_scorecards"] == len(candidates)
    assert doc["counts"]["n_displayed"] + doc["counts"]["n_out_of_view"] == len(candidates)
    assert doc["typed_arm_placements_corroborated"] > 0
    # The ordered A/B roles come from W16's own selection, not from Stage 4.
    slots = [(a["slot"], a["role"]) for a in doc["stage3_v2_selection"]["role_arms"]]
    assert slots == [("A", "away_from_A"), ("B", "toward_B")]
    for row in doc["candidates"]:
        assert row["stage3_v2_membership"]["membership_sha256"]


@real_bytes
def test_a_FORGED_caller_view_is_REFUSED_the_projection_uses_the_RECEIPT_BOUND_bytes():
    """THE ATTACK. The receipt is loaded and every hash recomputed — and then the projection used
    the view the CALLER passed in. One changed field (`question_id`) while the on-disk receipt and
    view stayed untouched was ADMITTED, and the forged question was emitted."""
    _r, view = load_receipt(W16_RECEIPT, bundle_dir=W16_BUNDLE)
    candidates = view["tables"]["candidates"]
    scorecards = {"scorecard_set_id": "sc1",
                  "candidates": [{"candidate_id": c["candidate_id"]} for c in candidates]}

    forged = json.loads(json.dumps(view))
    forged["selection"]["question_id"] = "FORGED_QUESTION_ID"

    with pytest.raises(MembershipError) as exc:
        build_v2_projection(scorecards, candidates, forged,
                            stage3_receipt_path=W16_RECEIPT, stage3_bundle_dir=W16_BUNDLE)
    assert exc.value.code == "stage4_caller_copy_is_not_the_hash_bound_artifact"


@real_bytes
def test_a_MUTATED_caller_candidate_list_is_REFUSED():
    """The same hole, one table over: the caller hands in rows that are not the bound rows."""
    _r, view = load_receipt(W16_RECEIPT, bundle_dir=W16_BUNDLE)
    candidates = view["tables"]["candidates"]
    scorecards = {"scorecard_set_id": "sc1",
                  "candidates": [{"candidate_id": c["candidate_id"]} for c in candidates]}

    mutated = json.loads(json.dumps(candidates))
    mutated[0]["preferred_name"] = "SMUGGLED"

    with pytest.raises(MembershipError) as exc:
        build_v2_projection(scorecards, mutated, view,
                            stage3_receipt_path=W16_RECEIPT, stage3_bundle_dir=W16_BUNDLE)
    assert exc.value.code == "stage4_caller_copy_is_not_the_hash_bound_artifact"


@real_bytes
def test_NO_internal_or_view_bytes_LEAK_into_the_stage4_artifact():
    """A Stage-4 artifact carrying a copy of Stage 3's whole view would be a second, unverified copy
    of it wearing Stage 3's identity."""
    _r, view = load_receipt(W16_RECEIPT, bundle_dir=W16_BUNDLE)
    candidates = view["tables"]["candidates"]
    scorecards = {"scorecard_set_id": "sc1",
                  "candidates": [{"candidate_id": c["candidate_id"]} for c in candidates]}
    doc = build_v2_projection(scorecards, candidates, view,
                              stage3_receipt_path=W16_RECEIPT, stage3_bundle_dir=W16_BUNDLE)

    blob = json.dumps(doc)
    assert "_view_document" not in blob
    assert "tables" not in doc["stage3_receipt"]

    def _no_private_keys(node, path="doc"):
        if isinstance(node, dict):
            for k, v in node.items():
                assert not str(k).startswith("_"), f"internal key {k!r} leaked at {path}"
                _no_private_keys(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                _no_private_keys(v, f"{path}[{i}]")

    _no_private_keys(doc)
    # The receipt carries the ids and hashes a reader needs to RE-VERIFY, and nothing more.
    assert doc["stage3_receipt"]["receipt_sha256"]
    assert doc["stage3_receipt"]["receipt_raw_sha256"]
    assert doc["stage3_receipt"]["bound_view_id"] == view["view_id"]


# ------------------------------------------------------------------------ the on-disk attacks

@real_bytes
def test_an_ALTERED_ON_DISK_receipt_is_REFUSED_even_though_the_CALLER_dict_is_CLEAN(tmp_path):
    """THE BLOCKER. The caller holds a perfectly clean receipt; the bytes on disk were edited after
    sealing. Stage 4 reads the bytes, not the caller's copy."""
    bundle = _bundle(tmp_path)
    path = _receipt_path(bundle)

    with open(path, encoding="utf-8") as fh:
        on_disk = json.load(fh)
    on_disk["store"]["store_manifest_sha256"] = "9" * 64      # edited AFTER sealing; hash NOT redone
    _write(path, on_disk)

    with pytest.raises(MembershipError) as exc:
        load_receipt(path, bundle_dir=bundle)
    assert exc.value.code == "stage4_stage3_receipt_self_hash_does_not_recompute"


@real_bytes
def test_a_RESEALED_receipt_over_ALTERED_VIEW_BYTES_is_still_REFUSED(tmp_path):
    """The forger fixes the self-hash. The view on disk still does not hash to what it claims —
    every link has to be forged, and the artifacts are the link a self-consistent receipt cannot
    reach."""
    bundle = _bundle(tmp_path)
    path = _receipt_path(bundle)

    view_path = os.path.join(bundle, "selection_view.fixture.v1.json")
    with open(view_path, encoding="utf-8") as fh:
        view = json.load(fh)
    view["tables"]["candidates"].append(dict(view["tables"]["candidates"][0],
                                             candidate_id="CAND_SMUGGLED"))
    _write(view_path, view)      # a row appended; the receipt's view hashes are now stale

    with pytest.raises(MembershipError) as exc:
        load_receipt(path, bundle_dir=bundle)
    assert exc.value.code == "stage4_stage3_view_does_not_rehash_to_its_receipt"


@real_bytes
def test_SEALED_FAKE_HASHES_over_an_EMPTY_bundle_are_REFUSED(tmp_path):
    """The exact probe: a receipt whose hashes are internally perfect, pointing at a bundle that
    contains nothing. The re-hash used to SKIP a file that was not there — and 'nothing to compare'
    is not 'nothing wrong'."""
    empty = os.path.join(str(tmp_path), "empty")
    os.makedirs(empty)

    with open(W16_RECEIPT, encoding="utf-8") as fh:
        receipt = json.load(fh)
    receipt["view"]["raw_sha256"] = "1" * 64          # fake…
    receipt["view"]["canonical_sha256"] = "2" * 64
    _reseal(receipt)                                  # …and sealed, so the self-hash is honest
    path = os.path.join(empty, "receipt.json")
    _write(path, receipt)

    with pytest.raises(MembershipError) as exc:
        load_receipt(path, bundle_dir=empty)
    assert exc.value.code == "stage4_stage3_view_is_not_in_the_bundle"


@real_bytes
def test_a_receipt_with_NO_bundle_dir_is_REFUSED_the_rehash_is_not_optional(tmp_path):
    """The re-hash ran only `if bundle_dir:`. An optional verification is not a verification; it is
    a verification the attacker chooses."""
    with pytest.raises(MembershipError) as exc:
        load_receipt(W16_RECEIPT, bundle_dir=None)
    assert exc.value.code == "stage4_stage3_bundle_dir_is_required"


@real_bytes
@pytest.mark.parametrize("bad", ["/etc/passwd", "../../outside.json", "a/../../b.json"])
def test_an_ABSOLUTE_or_TRAVERSING_view_path_is_REFUSED(tmp_path, bad):
    """An absolute path names a place on one machine; a traversing one names a document outside the
    bundle the receipt was sealed against."""
    bundle = _bundle(tmp_path)
    path = _receipt_path(bundle)

    with open(path, encoding="utf-8") as fh:
        receipt = json.load(fh)
    receipt["view"]["path"] = bad
    _reseal(receipt)
    _write(path, receipt)

    with pytest.raises(MembershipError) as exc:
        load_receipt(path, bundle_dir=bundle)
    assert exc.value.code == "stage4_stage3_receipt_path_is_not_bundle_relative"


@real_bytes
def test_a_SELF_SIGNED_receipt_is_REFUSED(tmp_path):
    """A producer that verifies its own output has not been verified. The two named ids are the
    fact — not the boolean the producer also publishes."""
    bundle = _bundle(tmp_path)
    path = _receipt_path(bundle)

    with open(path, encoding="utf-8") as fh:
        receipt = json.load(fh)
    receipt["verifier_id"] = receipt["generator_id"]
    receipt["generator_is_not_verifier"] = True          # the producer still SAYS it is independent
    _reseal(receipt)
    _write(path, receipt)

    with pytest.raises(MembershipError) as exc:
        load_receipt(path, bundle_dir=bundle)
    assert exc.value.code == "stage4_stage3_receipt_is_self_signed"


@real_bytes
def test_a_RETIRED_membership_rule_may_not_masquerade_as_the_one_in_force(tmp_path):
    """Rows computed under a retired rule look identical and mean something else."""
    bundle = _bundle(tmp_path)
    path = _receipt_path(bundle)

    with open(path, encoding="utf-8") as fh:
        receipt = json.load(fh)
    receipt["membership"]["rule_id"] = "spot.stage03.candidate_membership.exact_arm_key.v1"
    _reseal(receipt)
    _write(path, receipt)

    with pytest.raises(MembershipError) as exc:
        load_receipt(path, bundle_dir=bundle)
    assert exc.value.code == "stage4_stage3_membership_rule_is_not_the_one_in_force"


@real_bytes
def test_a_receipt_that_did_NOT_admit_is_REFUSED(tmp_path):
    bundle = _bundle(tmp_path)
    path = _receipt_path(bundle)

    with open(path, encoding="utf-8") as fh:
        receipt = json.load(fh)
    receipt["verdict"] = "refuse"
    _reseal(receipt)
    _write(path, receipt)

    with pytest.raises(MembershipError) as exc:
        load_receipt(path, bundle_dir=bundle)
    assert exc.value.code == "stage4_stage3_receipt_did_not_admit"


@real_bytes
def test_a_DIRTY_producer_tree_is_REFUSED(tmp_path):
    bundle = _bundle(tmp_path)
    path = _receipt_path(bundle)

    with open(path, encoding="utf-8") as fh:
        receipt = json.load(fh)
    receipt["producer_tree_is_clean"] = False
    _reseal(receipt)
    _write(path, receipt)

    with pytest.raises(MembershipError) as exc:
        load_receipt(path, bundle_dir=bundle)
    assert exc.value.code == "stage4_stage3_receipt_producer_tree_is_dirty"


@real_bytes
def test_a_receipt_DICT_is_REFUSED_it_must_come_from_DISK():
    from analysis.typed_membership import require_receipt

    with open(W16_RECEIPT, encoding="utf-8") as fh:
        receipt = json.load(fh)          # a perfectly valid receipt, in memory

    with pytest.raises(MembershipError) as exc:
        require_receipt(receipt, W16_BUNDLE)
    assert exc.value.code == "stage4_stage3_receipt_must_be_read_from_disk"


@real_bytes
def test_W16s_receipt_hash_rule_REPRODUCES_exactly():
    """`receipt_sha256 = sha256(canonical_json(receipt - receipt_sha256))`. If Stage 4's
    canonicalization differed by one flag, every receipt would refuse and the two stages would each
    be verifying their own idea of the document."""
    with open(W16_RECEIPT, "rb") as fh:
        receipt = json.loads(fh.read())

    body = {k: v for k, v in receipt.items() if k != SELF_HASH_FIELD}
    assert canonical_sha256(body) == receipt[SELF_HASH_FIELD]

    with open(W16_VIEW, "rb") as fh:
        raw = fh.read()
    view = json.loads(raw)
    assert hashlib.sha256(raw).hexdigest() == receipt["view"]["raw_sha256"]
    assert canonical_sha256(view) == receipt["view"]["canonical_sha256"]
    content = canonical_sha256(
        {k: v for k, v in view.items() if k not in ("view_id", "view_content_sha256")})
    assert content == receipt["view"]["view_content_sha256"]
    assert receipt["view"]["view_id"] == content[:16]


# ================== THE DOOR: the gate must run in PRODUCTION, not only in its own tests
#
# `build_v2_projection` had NO production caller. Every gate in the membership seam — the receipt
# re-hash, the ordered A/B roles, the exactly-one typed column, the join reconciliation — was
# reachable only from the tests that were written for it. A gate with no caller is a gate that never
# runs, and a suite that is its only consumer proves the code works, not that the pipeline uses it.

def _cli(*argv) -> tuple[int, str]:
    import contextlib
    import io

    from analysis.run_stage4 import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        code = main(list(argv))
    return code, buf.getvalue()


@real_bytes
def test_the_CLI_native_v2_door_RUNS_the_membership_seam_on_W16s_real_bytes(tmp_path):
    """The contract path: W16's real receipt + view, through the actual `run_stage4` dispatch."""
    out = os.path.join(str(tmp_path), "out")
    code, log = _cli("--stage3-membership-receipt", W16_RECEIPT,
                     "--stage3-membership-bundle", W16_BUNDLE, "--outputs-root", out)

    assert code == 0, log
    assert "verdict=admit" in log and "artifact_class=fixture" in log
    assert "typed placements" in log
    # And it says, in the run's own output, that this is not a result.
    assert "no drug fetched" in log

    with open(os.path.join(out, "browser_projection.v2.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["counts"]["n_displayed"] > 0
    assert doc["source_is_selection_view"] is True
    assert doc["store_is_global_and_was_not_filtered"] is False
    assert "_view_document" not in json.dumps(doc)


@real_bytes
def test_the_CLI_PRODUCTION_path_REFUSES_the_fixture_BY_NAME(tmp_path):
    """`artifact_class: fixture` is the real SHAPE — real producer, real verifier — but it is not a
    result. Publishing it would publish a fixture as a finding. Refused BY NAME, not incidentally,
    so the refusal says what is actually wrong."""
    out = os.path.join(str(tmp_path), "out")
    code, log = _cli("--stage3-membership-receipt", W16_RECEIPT,
                     "--stage3-membership-bundle", W16_BUNDLE, "--outputs-root", out,
                     "--write-production-pointer")

    assert code == 2, log
    assert "REFUSED [stage3_bundle_is_a_fixture]" in log
    # Nothing was published.
    assert not os.path.exists(os.path.join(out, "current.json"))


@real_bytes
def test_the_CLI_door_REFUSES_a_receipt_with_NO_bundle(tmp_path):
    """A receipt is a claim ABOUT bytes; without the bundle nothing it names could be re-hashed."""
    out = os.path.join(str(tmp_path), "out")
    code, log = _cli("--stage3-membership-receipt", W16_RECEIPT, "--outputs-root", out)

    assert code == 2, log
    assert "stage3_membership_bundle_required" in log


@real_bytes
def test_the_CLI_door_REFUSES_an_ALTERED_ON_DISK_receipt(tmp_path):
    """The door reads the bytes — it does not take the run's word for them."""
    bundle = _bundle(tmp_path)
    path = _receipt_path(bundle)
    with open(path, encoding="utf-8") as fh:
        on_disk = json.load(fh)
    on_disk["verdict"] = "admit"
    on_disk["store"]["store_manifest_sha256"] = "9" * 64      # edited after sealing
    _write(path, on_disk)

    out = os.path.join(str(tmp_path), "out")
    code, log = _cli("--stage3-membership-receipt", path,
                     "--stage3-membership-bundle", bundle, "--outputs-root", out)

    assert code == 2, log
    assert "stage4_stage3_receipt_self_hash_does_not_recompute" in log


@real_bytes
def test_the_CLI_door_REFUSES_a_SUBSTITUTED_caller_view(tmp_path):
    """The forged-question attack, through the door: the receipt and the receipt's own view stay
    untouched on disk, and a DIFFERENT view is dropped into the bundle at the path the receipt
    names. The receipt no longer describes the bytes it points at."""
    bundle = _bundle(tmp_path)
    view_path = os.path.join(bundle, "selection_view.fixture.v1.json")
    with open(view_path, encoding="utf-8") as fh:
        view = json.load(fh)
    view["selection"]["question_id"] = "FORGED_QUESTION_ID"
    _write(view_path, view)          # substituted; the receipt's view hashes are now stale

    out = os.path.join(str(tmp_path), "out")
    code, log = _cli("--stage3-membership-receipt", _receipt_path(bundle),
                     "--stage3-membership-bundle", bundle, "--outputs-root", out)

    assert code == 2, log
    assert "stage4_stage3_view_does_not_rehash_to_its_receipt" in log
    assert "FORGED_QUESTION_ID" not in log


@real_bytes
def test_the_LEGACY_doors_are_UNTOUCHED():
    """The native-v2 door is added beside them, never in place of them."""
    from analysis.run_stage4 import run_annotation_door, run_stage3_door  # noqa: F401

    code, log = _cli("--stage3-membership-receipt", W16_RECEIPT,
                     "--stage3-annotation-bundle", W16_BUNDLE)
    assert code == 2, log          # exactly ONE door per run
