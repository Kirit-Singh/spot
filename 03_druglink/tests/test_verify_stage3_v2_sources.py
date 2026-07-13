"""Adversarial attacks on the Stage-3 v2 verifier's INPUT admission (audit step 9, part 1).

The Stage-2 aggregate and the admitted universe store, attacked from every side they could
give way. The emitted-bundle attacks live in ``test_verify_stage3_v2.py``; these two files
are split only because the project gate is 500 lines a module.

Every refusal must NAME its gate. A test that merely asserted "it raised" would pass against
a verifier that refused for the wrong reason — and a rewording of the message would silently
retire the check.

NON-PRODUCTION: FIXTURE_* programs, FIXTURE_* targets, FIXTURE_CHEMBL_* molecules. Nothing
here is a scientific finding.
"""
from __future__ import annotations

import json
import os

import pytest
from druglink.hashing import content_hash
from v2_fixture import write_aggregate, write_store
from v2_world import named, refused

from verifier import canon
from verifier import eligibility_evidence as ee
from verifier import v2_contract as C
from verifier import v2_rebuild as vb
from verifier import v2_reconstruct as vr
from verifier.report import Report

# --------------------------------------------------------------------------- #
# BLOCKED, AND SAID OUT LOUD RATHER THAN FABRICATED.
#
# Every attack below is driven by ``v2_fixture.write_aggregate``, which writes the RETIRED
# INVENTED Stage-2 envelope: ``spot.stage02_aggregate_run_manifest.v1`` with an ``inventory[]``
# array, an ``admits{}`` block and a verifier id chosen to contain the word "independent". Stage 2
# has NEVER emitted any of that. The native loader — producer and verifier alike — now refuses it
# BY NAME, which is exactly right and is why these error at setup.
#
# They cannot be repaired here. To run, they need bytes that DO NOT EXIST on this host:
#
#   1. a generated NATIVE aggregate      (spot.stage02_run_manifest.v3_topology_only) — the
#      release_root bytes exist, but the arms carry NEITHER namespace NOR modality; and
#   2. W3's generated STAGE-3 BRIDGE     (stage3_bridge.json + its separate verification report
#      + the stage2_stage3_receipt) — which is CODE-ONLY in W3's tree today. No bridge document
#      exists anywhere on this machine.
#
# The two honest options were: hand-write those bytes so the suite goes green, or say the gate is
# RED. Hand-writing them is the precise defect this lane exists to catch — a fixture that can
# drift from the producer without a test failing is how a loader ends up parsing a schema nobody
# emits, and it is what made the retired envelope look admitted for 34 tests. So: RED, by name.
#
# The attacks are KEPT, not deleted: they are the specification these bytes will be judged
# against the day they land. What is testable WITHOUT inventing bytes — the sign rule, the
# phenocopy set, the emitted-row gates and the bridge's refusals — is tested, over test vectors,
# in ``test_verify_stage3_v2_sign.py``.
# --------------------------------------------------------------------------- #
pytest.skip(
    "BLOCKED on bytes that do not exist: W3's generated NATIVE aggregate (whose arms carry "
    "neither namespace nor modality) and W3's STAGE-3 BRIDGE (code-only today — no "
    "stage3_bridge.json, no bridge report, no receipt exists on this host). These attacks drive "
    "the RETIRED invented `spot.stage02_aggregate_run_manifest.v1` envelope, which the native "
    "gate now refuses by name. Fabricating the missing bytes to turn this suite green is the "
    "exact defect the lane exists to catch, so the gate stays RED and is reported as such. The "
    "deterministic half — the sign rule, the phenocopy set, the emitted-row gates and the "
    "bridge's refusals — is exercised in test_verify_stage3_v2_sign.py.",
    allow_module_level=True)



def _admit(tmp_path, **hooks):
    rep = Report()
    paths = write_aggregate(str(tmp_path / "agg"), **hooks)
    agg = vr.admit_aggregate(rep, manifest_path=paths["manifest"],
                             report_path=paths["report"],
                             bundles_root=paths["bundles_root"],
                             stage1_release=paths["stage1_release"])
    return rep, agg, paths


# --------------------------------------------------------------------------- #
# The honest aggregate. NON-VACUOUS, or none of the refusals below mean anything.
# --------------------------------------------------------------------------- #
def test_the_honest_aggregate_admits_the_FULL_15_bundle_300_arm_topology(v2_world):
    rep = Report()
    agg = vr.admit_aggregate(rep, manifest_path=v2_world["paths"]["manifest"],
                             report_path=v2_world["paths"]["report"],
                             bundles_root=v2_world["paths"]["bundles_root"],
                             stage1_release=v2_world["paths"]["stage1_release"])
    assert agg is not None and not rep.failures
    assert len(agg["bundles"]) == C.N_BUNDLES == 15
    assert len(agg["arms"]) == C.N_ARM_SLOTS == 300
    lanes = [b["lane"] for b in agg["bundles"]]
    assert lanes.count(C.LANE_DIRECT) == 3
    assert lanes.count(C.LANE_TEMPORAL) == 6
    assert lanes.count(C.LANE_PATHWAY) == 6
    assert all(a["records"] for a in agg["arms"]), "an empty arm proves nothing"


# --------------------------------------------------------------------------- #
# 1. The admission chain: report -> manifest -> bytes.
# --------------------------------------------------------------------------- #
def test_an_UNRELATED_admission_digest_is_refused(tmp_path):
    """An honest manifest plus an ADMIT for someone else's bytes admits nothing (B3)."""
    rep, agg, _ = _admit(tmp_path, mutate_report=lambda r, _m, _p: r["admits"].update(
        {"manifest_raw_sha256": "0" * 64}))
    assert agg is None
    assert refused(rep, C.GATE_REPORT_BINDS_ANOTHER_MANIFEST)


def test_a_friendly_VERIFIER_NAME_with_no_bound_report_is_refused(tmp_path):
    """B4, exactly: `totally_independent_but_unbound` binds no bytes, so it admits nothing."""
    def forge(report, _manifest, _path):
        report["verifier_id"] = "totally_independent_but_unbound"
        report.pop("admits")

    rep, agg, _ = _admit(tmp_path, mutate_report=forge)
    assert agg is None
    assert refused(rep, C.GATE_REPORT_BINDS_NOTHING)


def test_a_PRODUCER_SELF_ADMISSION_is_refused(tmp_path):
    """A producer agreeing with itself is the one thing an independent verifier rules out."""
    rep, agg, _ = _admit(tmp_path, mutate_report=lambda r, _m, _p: r.update(
        {"verifier_id": "stage02-producer-selfcheck-v1"}))
    assert agg is None
    assert refused(rep, C.GATE_VERIFIER_NOT_INDEPENDENT)


def test_a_verdict_that_is_not_ADMIT_is_refused(tmp_path):
    """A producer's `pending` release read as an admission is one of the five defects."""
    rep, agg, _ = _admit(tmp_path, mutate_report=lambda r, _m, _p: r.update(
        {"verdict": "pending"}))
    assert agg is None
    assert refused(rep, C.GATE_VERDICT_NOT_ADMIT)


def test_the_WRONG_manifest_report_PAIR_is_refused(tmp_path):
    """Two honest releases. A's manifest with B's report is not an admission of A."""
    a = write_aggregate(str(tmp_path / "a"))
    b = write_aggregate(str(tmp_path / "b"),
                        mutate_manifest=lambda m: m.update({"run_id": "release_b"}))
    rep = Report()
    agg = vr.admit_aggregate(rep, manifest_path=a["manifest"], report_path=b["report"],
                             bundles_root=a["bundles_root"],
                             stage1_release=a["stage1_release"])
    assert agg is None
    assert refused(rep, C.GATE_REPORT_BINDS_ANOTHER_MANIFEST)


def test_the_report_and_the_manifest_may_not_be_the_SAME_FILE(tmp_path):
    _rep, _agg, paths = _admit(tmp_path)
    rep = Report()
    agg = vr.admit_aggregate(rep, manifest_path=paths["manifest"],
                             report_path=paths["manifest"],
                             bundles_root=paths["bundles_root"],
                             stage1_release=paths["stage1_release"])
    assert agg is None
    assert refused(rep, C.GATE_SELF_ADMISSION)


def test_a_forged_manifest_SELF_HASH_is_refused(tmp_path):
    """B6, again: a manifest that cannot recompute its own identity is not a root of trust —
    it is a document asserting a number."""
    def forge(_bundles_root, manifest_path, _report_path):
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
        manifest["manifest_sha256"] = "f" * 64
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, sort_keys=True, separators=(",", ":"))

    rep, agg, _ = _admit(tmp_path, mutate_after_seal=forge)
    assert agg is None
    assert refused(rep, C.GATE_MANIFEST_SELF_HASH)


def test_a_stage2_artifact_MUTATED_AFTER_admission_is_refused(tmp_path):
    """The independent verifier read these bytes; someone changed them afterwards."""
    def tamper(bundles_root, _manifest_path, _report_path):
        victim = os.path.join(bundles_root, "direct", "direct__Rest.json")
        with open(victim, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["arms"][0]["records"][0]["rank"] = 999
        with open(victim, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, sort_keys=True, separators=(",", ":"))

    rep, agg, _ = _admit(tmp_path, mutate_after_seal=tamper)
    assert agg is None
    assert refused(rep, C.GATE_BUNDLE_BYTES_MOVED)


def test_a_Stage1_release_that_is_not_the_pinned_one_is_refused(tmp_path):
    def swap(_bundles_root, manifest_path, _report_path):
        with open(os.path.join(os.path.dirname(manifest_path), "stage1_release.json"),
                  "w", encoding="utf-8") as fh:
            fh.write('{"release_id": "some_other_release"}')

    rep, agg, _ = _admit(tmp_path, mutate_after_seal=swap)
    assert agg is None
    assert refused(rep, C.GATE_STAGE1_RELEASE_UNBOUND)


# --------------------------------------------------------------------------- #
# 2. Topology: 15 bundles and 300 arm slots, both DERIVED.
# --------------------------------------------------------------------------- #
def test_a_MISSING_bundle_is_refused(tmp_path):
    """A missing bundle is indistinguishable from one computed and found empty."""
    rep, agg, _ = _admit(tmp_path, mutate_inventory=lambda inv: inv.pop(0))
    assert agg is None
    assert refused(rep, C.GATE_MISSING_BUNDLE)


def test_a_DUPLICATE_bundle_key_is_refused(tmp_path):
    """A duplicate silently fills a missing slot, and the count still looks right."""
    rep, agg, _ = _admit(tmp_path,
                         mutate_inventory=lambda inv: inv.__setitem__(1, dict(inv[0])))
    assert agg is None
    assert refused(rep, C.GATE_DUPLICATE_BUNDLE)


def test_an_UNKNOWN_lane_or_a_MISLABELLED_context_is_refused(tmp_path):
    """A bundle whose key disagrees with its own context fills the wrong slot."""
    rep, agg, _ = _admit(
        tmp_path, mutate_inventory=lambda inv: inv[0].update({"condition": "Stim8hr"}))
    assert agg is None
    assert refused(rep, C.GATE_UNKNOWN_LANE)


def test_a_PARTIAL_arm_inventory_is_refused(tmp_path):
    def drop_arms(docs):
        docs[f"{C.LANE_DIRECT}|Rest"]["arms"] = docs[f"{C.LANE_DIRECT}|Rest"]["arms"][:5]

    rep, agg, _ = _admit(tmp_path, mutate_bundles=drop_arms)
    assert agg is None
    assert refused(rep, C.GATE_INCOMPLETE_TOPOLOGY)


def test_an_arm_record_that_resolves_to_NO_TARGET_IDENTITY_is_refused(tmp_path):
    def orphan(docs):
        doc = docs[f"{C.LANE_DIRECT}|Rest"]
        doc["arms"][0]["records"][0]["base_key"] = "NOTHING_RESOLVES_TO_THIS"

    rep, agg, _ = _admit(tmp_path, mutate_bundles=orphan)
    assert agg is None
    assert refused(rep, C.GATE_ARM_IDENTITY_UNRESOLVED)


@pytest.mark.parametrize("path", ["/etc/passwd", "../../outside.json",
                                  "direct/../../escape.json"])
def test_a_bundle_path_OUTSIDE_the_explicit_root_is_refused(tmp_path, path):
    rep, agg, _ = _admit(tmp_path,
                         mutate_inventory=lambda inv: inv[0].update({"path": path}))
    assert agg is None
    assert refused(rep, C.GATE_PATH_TRAVERSAL)


def test_a_MISSING_artifact_is_a_NAMED_refusal_and_never_an_exception(tmp_path):
    rep = Report()
    agg = vr.admit_aggregate(rep, manifest_path=str(tmp_path / "nope.json"),
                             report_path=str(tmp_path / "also_nope.json"),
                             bundles_root=str(tmp_path), stage1_release="")
    assert agg is None
    assert refused(rep, C.GATE_ARTIFACT_NOT_ON_DISK)


# --------------------------------------------------------------------------- #
# 3. The typed universe and the admitted store.
# --------------------------------------------------------------------------- #
def test_an_EMPTY_typed_universe_is_refused_BY_NAME():
    """The audited CLI passed exactly this. [] is not 'no universe supplied' — it is a
    universe that covers NOTHING, and it has a hash."""
    rep = Report()
    assert vr.derive_typed_universe(rep, []) is None
    assert refused(rep, C.GATE_EMPTY_TYPED_UNIVERSE)
    assert canon.chash([]) == C.EMPTY_TYPED_UNIVERSE_SHA256


def test_the_WRONG_typed_universe_is_refused_on_the_ANALYSIS_path(v2_world):
    """The sealed store is internally perfect and is NOT the admitted universe. A store can
    be perfectly consistent with a universe nobody admitted — that is what a forgery is."""
    rep = Report()
    store = vr.open_store(rep, store_dir=v2_world["store"], artifact_class="analysis")
    assert store is not None, "the store is intact; the refusal is about ADMISSION"
    assert store["typed_universe"], "a vacuous universe would prove nothing"
    assert refused(rep, C.GATE_NOT_THE_ADMITTED_UNIVERSE)
    assert refused(rep, C.GATE_NOT_THE_ADMITTED_STORE)

    clean = Report()
    assert vr.open_store(clean, store_dir=v2_world["store"],
                         artifact_class="fixture") is not None
    assert not clean.failures, "the same bytes admit as the FIXTURE they declare"


def test_a_typed_universe_that_is_not_the_one_the_STORE_BINDS_is_refused(tmp_path):
    def tamper(store_dir):
        path = os.path.join(store_dir, C.STORE_MANIFEST_NAME)
        with open(path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
        manifest["universe_binding"]["universe_targets_sha256"] = "a" * 64
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, sort_keys=True, separators=(",", ":"))

    rep = Report()
    store = write_store(str(tmp_path / "store"), mutate_after_seal=tamper)
    vr.open_store(rep, store_dir=store, artifact_class="fixture")
    assert refused(rep, C.GATE_TYPED_UNIVERSE_HASH_MISMATCH)


def test_a_store_ROW_mutation_after_sealing_is_refused(tmp_path):
    """The manifest is untouched, so this is the artifact that moved."""
    def tamper(store_dir):
        path = os.path.join(store_dir, C.STORE_ROWS_NAME)
        with open(path, "r", encoding="utf-8") as fh:
            rows = json.load(fh)
        rows[0]["drugs"][0]["action_type_source"] = "AGONIST"   # never stated by ChEMBL
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, sort_keys=True, separators=(",", ":"))

    rep = Report()
    store = write_store(str(tmp_path / "store"), mutate_after_seal=tamper)
    assert vr.open_store(rep, store_dir=store, artifact_class="fixture") is None
    assert refused(rep, C.GATE_STORE_ARTIFACT_HASH_DRIFT)


def test_a_PROVENANCE_mutation_after_sealing_is_refused(tmp_path):
    """The defect that made an earlier producer gate fail-open: it never opened this file."""
    def tamper(store_dir):
        path = os.path.join(store_dir, C.STORE_PROVENANCE_NAME)
        with open(path, "r", encoding="utf-8") as fh:
            prov = json.load(fh)
        prov[0]["release"] = "2026_03"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(prov, fh, sort_keys=True, separators=(",", ":"))

    rep = Report()
    store = write_store(str(tmp_path / "store"), mutate_after_seal=tamper)
    assert vr.open_store(rep, store_dir=store, artifact_class="fixture") is None
    assert refused(rep, C.GATE_STORE_ARTIFACT_HASH_DRIFT)


def test_a_DELETED_store_artifact_is_a_NAMED_refusal(tmp_path):
    """A gate cannot catch a mutation to a file it never reads — so a deletion refuses BY NAME."""
    store = write_store(str(tmp_path / "store"),
                        mutate_after_seal=lambda d: os.remove(
                            os.path.join(d, C.STORE_PROVENANCE_NAME)))
    rep = Report()
    assert vr.open_store(rep, store_dir=store, artifact_class="fixture") is None
    assert refused(rep, C.GATE_STORE_MISSING_ARTIFACT)


def test_a_RESEALED_eligibility_record_still_fails_the_REPLAY(tmp_path):
    """A resealed artifact hashes perfectly and STILL contradicts itself: the record's own
    inputs say 'reject' where its own verdict says 'accept'. Rehashing cannot remove that."""
    store = write_store(str(tmp_path / "store"))
    path = os.path.join(store, C.STORE_ELIGIBILITY_NAME)
    with open(path, "r", encoding="utf-8") as fh:
        evidence = json.load(fh)
    evidence["records"][0]["tax_id"] = 10090          # mouse, and still verdict=accepted
    evidence["content_sha256"] = ee.canonical_content_sha256(evidence["records"])
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(evidence, fh, sort_keys=True, separators=(",", ":"))

    manifest_path = os.path.join(store, C.STORE_MANIFEST_NAME)
    with open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    manifest["extraction"]["eligibility_evidence_sha256"] = content_hash(evidence)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, sort_keys=True, separators=(",", ":"))

    rep = Report()
    vr.open_store(rep, store_dir=store, artifact_class="fixture")
    assert not refused(rep, C.GATE_STORE_ARTIFACT_HASH_DRIFT), "the reseal held"
    assert named(rep, "REPLAYS from its own predicate inputs"), \
        "only the REPLAY can catch a resealed mutation"


# --------------------------------------------------------------------------- #
# 4. Store semantics, enforced where the edge is EMITTED.
# --------------------------------------------------------------------------- #
def _semantics(tmp_path, mutate_rows):
    rep = Report()
    store_dir = write_store(str(tmp_path / "store"), mutate_rows=mutate_rows)
    store = vr.open_store(rep, store_dir=store_dir, artifact_class="fixture")
    assert store is not None, [n for n, _ in rep.failures]
    vb.check_store_semantics(rep, store)
    return rep


def test_a_VARIANT_assertion_in_the_general_gene_lane_is_refused(tmp_path):
    """A V617F inhibitor is evidence about V617F, not wild-type JAK2 — and the screen
    perturbed the wild-type gene. -1 is the UNDEFINED MUTATION sentinel, not 'no variant'."""
    def promote(rows):
        rows[0]["drugs"][0]["variant_id"] = C.VARIANT_UNDEFINED_MUTATION

    assert refused(_semantics(tmp_path, promote), C.GATE_VARIANT_IN_GENERAL_LANE)


def test_a_variant_assertion_that_merely_OMITS_its_denial_is_refused(tmp_path):
    """Absence is not permission: omission is exactly how 29 variant assertions reached
    general-gene ranking."""
    def omit(rows):
        rows[1]["variant_specific_assertions"][0].pop("general_gene_rankable")

    assert refused(_semantics(tmp_path, omit), C.GATE_VARIANT_IN_GENERAL_LANE)


def test_an_AMBIGUOUS_row_carrying_rankable_drug_evidence_is_refused(tmp_path):
    """One mechanism would become independent-looking evidence for every gene the shared
    accession maps to (the CALM1/2/3 shape)."""
    def promote(rows):
        rows[2]["drugs"] = [dict(rows[2]["ambiguous_source_assertions"][0],
                                 general_gene_rankable=True)]

    assert refused(_semantics(tmp_path, promote),
                   C.GATE_AMBIGUOUS_ROW_HAS_RANKABLE_EVIDENCE)


def test_a_CACHED_stage3_direction_verdict_is_refused(tmp_path):
    """A cached direction is a verdict nobody can re-derive, and it outlives the vocabulary
    that produced it."""
    def cache_a_verdict(rows):
        rows[0]["drugs"][0]["intervention_effect"] = "functional_inhibition"

    assert refused(_semantics(tmp_path, cache_a_verdict),
                   C.GATE_CACHE_CARRIES_A_DIRECTION_VERDICT)


def test_an_assertion_that_cannot_NAME_ITS_SOURCE_ROW_is_refused(tmp_path):
    """ChEMBL's REQUIRED attribution is to preserve the ids, and an edge that cannot name its
    source row cannot be checked against the source."""
    def strip(rows):
        rows[0]["drugs"][0]["source_row_id"] = None

    assert refused(_semantics(tmp_path, strip), C.GATE_MISSING_SOURCE_IDENTITY)
