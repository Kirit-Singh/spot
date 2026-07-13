"""NINE ATTACKS on the aggregate run manifest. Each dies at a NAMED gate.

The manifest is the last thing between a partial, mismatched or forged set of lane outputs
and a release. So it is attacked here the way it would actually be attacked: not with
nonsense, but with runs that LOOK complete — the right number of directories, the right
filenames, the right hashes — and are not the same science.

Every bundle is a FIXTURE. What is real is the gate that stops it.
"""
from __future__ import annotations

import json
import os
import shutil

import fixtures_run_manifest as F
import pytest
from direct import run_manifest
from direct import verify_run_manifest as V
from direct.hashing import content_hash


def _manifest(tmp_path, run, name="manifest.json", allow_partial=False):
    release = run_manifest.load_release(run["release_path"], run["release_root"])
    bundles = [run_manifest.bind_bundle(d)
               for d in run["direct"] + run["temporal"] + run["pathway"]]
    return run_manifest.build(
        bundles=bundles, out_path=os.path.join(str(tmp_path), name),
        release=release, allow_partial=allow_partial,
        code_identity={"commit": "f" * 40, "clean_tree": True,
                       "manifest_sha256": "0" * 64, "canonical_digest": "0" * 16})


def _reseal(path, **fields):
    """What a forger with repo access does: edit the manifest and RE-SEAL its self-hash."""
    doc = json.load(open(path))
    doc.update(fields)
    doc["manifest_sha256"] = content_hash(
        {k: v for k, v in doc.items() if k not in ("created_at", "manifest_sha256")})
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
    return path


def _forge_complete(path):
    """Claim a complete TOPOLOGY. (Admission is a separate claim — see the class below.)"""
    return _reseal(path, topology_complete=True)


def _verify(run, manifest_path, expect_release_sha256=None):
    return V.verify(manifest_path=manifest_path, bundles_root=run["root"],
                    release_path=run["release_path"],
                    release_root=run["release_root"],
                    expect_release_sha256=(expect_release_sha256
                                           or run["expect_release_sha256"]),
                    expect_gene_sets_path=run["pinned_gene_sets"],
                    expect_verifiers_path=run["pinned_verifiers"],
                    expected_code_identity_path=run["expected_code_identity"])


def _clone(src, dst_name):
    dst = os.path.join(os.path.dirname(src), dst_name)
    shutil.copytree(src, dst)
    return dst


def _patch(bundle_dir, filename, mutate):
    path = os.path.join(bundle_dir, filename)
    doc = json.load(open(path))
    mutate(doc)
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)


def test_a_clean_complete_run_is_ADMITTED(tmp_path):
    """The control. Without it, every REJECT below proves nothing."""
    run = F.complete_run(tmp_path)
    doc = _verify(run, _manifest(tmp_path, run)["path"])
    assert doc["verdict"] == V.R.ADMIT, doc["failed_gates"]
    assert doc["n_arm_slots"] == doc["n_expected_arm_slots"] == 300
    assert doc["n_bundles"] == 15
    assert doc["selection_capacity"]["total_valid_ordered_selections"] == 3540


# --------------------------------------------------------------------------- #
# 1-3. ONE RESULT, REPEATED. The old manifest counted 3/6/6 and called it complete.
# --------------------------------------------------------------------------- #
def test_1_one_DIRECT_result_repeated_three_times(tmp_path):
    run = F.complete_run(tmp_path)
    first = run["direct"][0]
    run["direct"] = [first, _clone(first, "COPY-direct-2"),
                     _clone(first, "COPY-direct-3")]
    doc = _verify(run, _forge_complete(_manifest(tmp_path, run, allow_partial=True)["path"]))

    assert doc["verdict"] == V.R.REJECT
    assert V.G_DIRECT_SLOTS in doc["failed_gates"]
    # three copies of one condition: 20 slots filled three times over, 40 never
    assert doc["n_arm_slots"] == 20 + 120 + 120


def test_2_one_TEMPORAL_result_repeated_six_times(tmp_path):
    run = F.complete_run(tmp_path)
    first = run["temporal"][0]
    run["temporal"] = [first] + [_clone(first, f"COPY-temporal-{i}")
                                 for i in range(2, 7)]
    doc = _verify(run, _forge_complete(_manifest(tmp_path, run, allow_partial=True)["path"]))

    assert doc["verdict"] == V.R.REJECT
    assert V.G_TEMPORAL_SLOTS in doc["failed_gates"]


def test_3_one_PATHWAY_result_repeated_six_times(tmp_path):
    run = F.complete_run(tmp_path)
    first = run["pathway"][0]
    run["pathway"] = [first] + [_clone(first, f"COPY-pathway-{i}") for i in range(2, 7)]
    doc = _verify(run, _forge_complete(_manifest(tmp_path, run, allow_partial=True)["path"]))

    assert doc["verdict"] == V.R.REJECT
    assert V.G_PATHWAY_SLOTS in doc["failed_gates"]


# --------------------------------------------------------------------------- #
# 4-5. THE SAME SHAPE, DIFFERENT SCIENCE.
# --------------------------------------------------------------------------- #
def test_4_one_lane_produced_from_ANOTHER_COMMIT(tmp_path):
    run = F.complete_run(tmp_path)
    _patch(run["temporal"][2], "temporal_provenance.json",
           lambda d: d["run_binding"]["code_identity"].update(
               {"commit": "a" * 40, "canonical_digest": "deadbeefdeadbeef"}))
    doc = _verify(run, _manifest(tmp_path, run)["path"])

    assert doc["verdict"] == V.R.REJECT
    assert V.G_CODE in doc["failed_gates"]


def test_5_one_lane_bound_to_ANOTHER_SELECTION(tmp_path):
    run = F.complete_run(tmp_path)
    _patch(run["pathway"][4], "pathway_provenance.json",
           lambda d: d["run_binding"]["selection_release"].update(
               {"release_id": "FIXTURE-a-different-stage1-release",
                "scorer_view_raw_sha256": "b" * 64}))
    doc = _verify(run, _manifest(tmp_path, run)["path"])

    assert doc["verdict"] == V.R.REJECT
    assert V.G_SELECTION in doc["failed_gates"]


# --------------------------------------------------------------------------- #
# 6. AN UNADMITTED ARM.
# --------------------------------------------------------------------------- #
def test_6_a_verification_report_changed_to_REJECT(tmp_path):
    run = F.complete_run(tmp_path)
    _patch(run["direct"][1], "verification.json",
           lambda d: d.update({"verdict": "reject", "n_failed": 1}))
    doc = _verify(run, _manifest(tmp_path, run)["path"])

    assert doc["verdict"] == V.R.REJECT
    assert V.G_VERDICT in doc["failed_gates"]


# --------------------------------------------------------------------------- #
# 7. THE RIGHT FILENAMES, THE WRONG BYTES.
# --------------------------------------------------------------------------- #
def test_7_arbitrary_bytes_stored_under_expected_filenames(tmp_path):
    run = F.complete_run(tmp_path)
    path = _manifest(tmp_path, run)["path"]

    # the bundle was bound; NOW its ranking is replaced with junk under the same name
    ranking = os.path.join(run["direct"][0], "rankings", "treg_like__decrease.json")
    with open(ranking, "w") as fh:
        fh.write("not json, just bytes that happen to sit at an expected path")

    doc = _verify(run, path)
    assert doc["verdict"] == V.R.REJECT
    assert V.G_BYTES in doc["failed_gates"]


def test_7b_the_producer_refuses_to_BIND_arbitrary_bytes(tmp_path):
    run = F.complete_run(tmp_path)
    with open(os.path.join(run["direct"][0], "arm_bundle.json"), "w") as fh:
        fh.write("{{ not json")
    with pytest.raises(run_manifest.RunManifestError, match="not readable JSON"):
        run_manifest.bind_bundle(run["direct"][0])


# --------------------------------------------------------------------------- #
# 8. A SELF-HASH THE MANIFEST DOES NOT HAVE.
# --------------------------------------------------------------------------- #
def test_8_a_FORGED_aggregate_manifest_sha256(tmp_path):
    run = F.complete_run(tmp_path)
    path = _manifest(tmp_path, run)["path"]
    doc = json.load(open(path))
    doc["manifest_sha256"] = "0" * 64          # a value the caller simply supplied
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)

    report = _verify(run, path)
    assert report["verdict"] == V.R.REJECT
    assert V.G_SELF_HASH in report["failed_gates"]
    assert report["manifest_sha256_recomputed"] != "0" * 64


def test_8b_a_field_edited_after_sealing_is_caught(tmp_path):
    run = F.complete_run(tmp_path)
    path = _manifest(tmp_path, run)["path"]
    doc = json.load(open(path))
    doc["n_expected_arm_slots"] = 20           # keep the old hash; move the content
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)

    report = _verify(run, path)
    assert report["verdict"] == V.R.REJECT
    assert V.G_SELF_HASH in report["failed_gates"]


# --------------------------------------------------------------------------- #
# 9. THE SNEAKY ONE: a missing slot back-filled by a duplicate, RELABELLED so the
#    topology looks perfect. Only the content address gives it away.
# --------------------------------------------------------------------------- #
def test_9_a_missing_slot_replaced_by_a_DUPLICATE(tmp_path):
    run = F.complete_run(tmp_path)
    conds = run["conditions"]
    # the first condition's bundle never ran; the second's is copied into its place
    missing, stand_in = conds[0], run["direct"][1]

    dupe = _clone(stand_in, f"COPY-direct-{missing}")
    # relabel it to the slot it is filling — but keep the bundle_id it was born with,
    # which is what a copied artifact actually does
    def relabel(d):
        d["context"] = {"condition": missing}
        for arm in d["arms"]:
            parts = arm["arm_key"].split("|")
            arm["arm_key"] = "|".join(parts[:3] + [missing])
    _patch(dupe, "arm_bundle.json", relabel)

    run["direct"] = [run["direct"][1], run["direct"][2], dupe]

    # the PRODUCER refuses outright: a duplicate bundle id is not a complete run
    with pytest.raises(run_manifest.RunManifestError, match="duplicate bundle ids"):
        _manifest(tmp_path, run)

    # so the forger goes around it — --allow-partial, then declare it complete and
    # re-seal the self-hash. The verifier is not fooled.
    doc = _verify(run, _forge_complete(
        _manifest(tmp_path, run, allow_partial=True)["path"]))

    # every slot LOOKS filled...
    assert doc["n_arm_slots"] == 300
    # ...and it is still refused, because one invocation repeated is not two
    assert doc["verdict"] == V.R.REJECT
    assert V.G_UNIQUE in doc["failed_gates"]


# --------------------------------------------------------------------------- #
# The topology-specific attacks the reusable-arm release introduces.
# --------------------------------------------------------------------------- #
def test_a_PAIR_SPECIFIC_bundle_cannot_satisfy_completeness(tmp_path):
    run = F.complete_run(tmp_path)
    shutil.rmtree(run["direct"][0])
    run["direct"][0] = F.build_bundle(
        run["root"], "direct", {"condition": run["conditions"][0]}, run["staged"],
        arms_for=[("treg_like", "decrease"), ("th1_like", "increase")])
    doc = _verify(run, _forge_complete(
        _manifest(tmp_path, run, allow_partial=True)["path"]))

    assert doc["verdict"] == V.R.REJECT
    assert V.G_ALL_ARM in doc["failed_gates"]


def test_a_MISLABELLED_desired_change_is_caught_by_the_frozen_table(tmp_path):
    run = F.complete_run(tmp_path)
    # away_from_A(high) DECREASES the program; claim it as an increase
    def mislabel(d):
        for arm in d["arms"]:
            if arm["desired_change"] == "decrease":
                arm["desired_change"] = "increase"
                break
    _patch(run["direct"][0], "arm_bundle.json", mislabel)
    doc = _verify(run, _manifest(tmp_path, run, allow_partial=True)["path"])

    assert doc["verdict"] == V.R.REJECT
    assert V.G_MAPPING in doc["failed_gates"]


def test_a_DECLARED_hit_count_that_the_bytes_do_not_support_is_caught(tmp_path):
    run = F.complete_run(tmp_path)
    _patch(run["pathway"][0], "arm_bundle.json",
           lambda d: d["arms"][0]["n_hits_by_set"].update({"FIXTURE-SET-1": 99}))
    doc = _verify(run, _manifest(tmp_path, run)["path"])

    assert doc["verdict"] == V.R.REJECT
    assert V.G_RECONSTRUCT in doc["failed_gates"]


def test_a_PARTIAL_run_is_never_release_admissible(tmp_path):
    run = F.complete_run(tmp_path)
    run["pathway"] = run["pathway"][:-1]
    doc = _verify(run, _manifest(tmp_path, run, allow_partial=True)["path"])

    assert doc["verdict"] == V.R.REJECT
    assert V.G_PATHWAY_SLOTS in doc["failed_gates"]
    assert doc["n_arm_slots"] == 280


# --------------------------------------------------------------------------- #
# THE THREE FAIL-OPEN SEAMS an independent review found in 8263431+511f672.
#
# Each of these PASSED the first verifier. None of them is nonsense: they are the forgeries
# that fit the shape of the check that was being made.
# --------------------------------------------------------------------------- #
class TestAGeneSetSourceNameIsNotAGeneSetIdentity:
    """SEAM 1: the source NAME matched, so a forged release passed."""

    @staticmethod
    def _forge(run, source, **fields):
        for d in run["pathway"]:
            inv = json.load(open(os.path.join(d, "arm_bundle.json")))
            if inv["context"]["gene_set_source"] != source:
                continue
            _patch(d, "arm_bundle.json",
                   lambda doc: doc["gene_sets"].update(fields))

    def test_a_FORGED_release_under_the_right_source_name_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        # every bundle of this source gets the SAME forged identity, so it is
        # self-consistent and still differs from the other source — the old check passed
        self._forge(run, "Reactome",
                    release_id="FIXTURE-Reactome-release-v99-NOT-THE-PINNED-ONE",
                    raw_sha256="c" * 64, canonical_sha256="d" * 64)
        doc = _verify(run, _forge_complete(
            _manifest(tmp_path, run, allow_partial=True)["path"]))

        assert doc["verdict"] == V.R.REJECT
        assert V.G_GENESET_ID in doc["failed_gates"]

    @pytest.mark.parametrize("field,value", [
        ("gene_set_license", "FIXTURE-a-licence-we-never-pinned"),
        ("gene_id_namespace", "hgnc_symbol"),
        ("target_universe_sha256", "e" * 64),
    ])
    def test_every_bound_field_of_the_identity_is_compared(self, tmp_path, field, value):
        # a set of HGNC symbols tested against an Ensembl universe overlaps in almost
        # nothing, and "no enrichment" is the answer you get. That is a failed join
        # wearing a null result, and the namespace is part of the identity for that reason.
        run = F.complete_run(tmp_path)
        self._forge(run, "GO-BP", **{field: value})
        doc = _verify(run, _forge_complete(
            _manifest(tmp_path, run, allow_partial=True)["path"]))

        assert doc["verdict"] == V.R.REJECT
        assert V.G_GENESET_ID in doc["failed_gates"]


class TestAnAdmitStringIsNotAnIndependentAdmission:
    """SEAM 2: ``report["verdict"] == "admit"`` was the whole check."""

    def test_a_two_line_ADMIT_STUB_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        with open(os.path.join(run["direct"][0], "verification.json"), "w") as fh:
            json.dump({"verdict": "admit"}, fh)      # the bundle will bind these bytes
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert V.G_VERDICT in doc["failed_gates"]

    def test_a_report_from_the_WRONG_VERIFIER_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        _patch(run["temporal"][0], "temporal_verification.json",
               lambda d: d.update({"verifier_id": "FIXTURE.a.verifier.nobody.pinned"}))
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert V.G_VERDICT in doc["failed_gates"]

    def test_a_report_that_JUDGED_ANOTHER_BUNDLE_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        # a genuine, fully-typed ADMIT — for a different bundle. Copied across.
        donor = json.load(open(os.path.join(run["direct"][1], "verification.json")))
        with open(os.path.join(run["direct"][0], "verification.json"), "w") as fh:
            json.dump(donor, fh, indent=2, sort_keys=True)
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert V.G_VERDICT in doc["failed_gates"]

    def test_an_ADMIT_that_RAN_NO_GATES_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        _patch(run["pathway"][0], "pathway_verification.json",
               lambda d: d.update({"checks": []}))   # admitted, having checked nothing
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert V.G_VERDICT in doc["failed_gates"]

    def test_an_ADMIT_carrying_FAILED_GATES_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        _patch(run["direct"][2], "verification.json",
               lambda d: d.update({"n_failed": 2, "failed_gates": ["a", "b"]}))
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert V.G_VERDICT in doc["failed_gates"]


class TestCleanTreeIsNotSomethingTheRunGetsToAssert:
    """SEAM 3: ``clean_tree: true`` was believed because the artifact said so."""

    def test_a_RESEALED_clean_tree_over_ANOTHER_COMMIT_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        # EVERY bundle resealed to the same other commit: internally consistent, still
        # claiming a clean checkout. Only a witness outside the run can catch it.
        for d in run["direct"] + run["temporal"] + run["pathway"]:
            name = ("provenance.json" if d in run["direct"] else
                    "temporal_provenance.json" if d in run["temporal"]
                    else "pathway_provenance.json")
            _patch(d, name, lambda doc: doc["run_binding"]["code_identity"].update(
                {"commit": "9" * 40, "clean_tree": True,
                 "canonical_digest": "9999999999999999"}))
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert V.G_CODE in doc["failed_gates"]

    def test_a_DIRTY_tree_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        _patch(run["direct"][0], "provenance.json",
               lambda d: d["run_binding"]["code_identity"].update({"clean_tree": False}))
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert V.G_CLEAN in doc["failed_gates"]


class TestTheConditionUniverseComesFromTheRelease:
    """The batch policy is no longer an authority. The release is — and it is PINNED.

    A confound diagnostic was never the right place to learn which conditions exist, and
    batch is now out of the reusable temporal chain entirely. So the conditions come from
    ``release.selector.conditions``, and the release is content-addressed against a pin
    held OUTSIDE the run: forging, dropping or REORDERING that list changes the hash.
    """

    @staticmethod
    def _mutate_conditions(run, conditions):
        doc = json.load(open(run["release_path"]))
        doc["selector"]["conditions"] = conditions
        with open(run["release_path"], "w") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)

    def test_a_FORGED_condition_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        path = _manifest(tmp_path, run)["path"]
        self._mutate_conditions(run, ["Rest", "Stim8hr", "FORGED_CONDITION"])
        doc = _verify(run, path)

        assert doc["verdict"] == V.R.REJECT
        assert V.G_RELEASE_PIN in doc["failed_gates"]

    def test_a_MISSING_condition_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        path = _manifest(tmp_path, run)["path"]
        self._mutate_conditions(run, ["Rest", "Stim8hr"])
        doc = _verify(run, path)

        assert doc["verdict"] == V.R.REJECT
        assert V.G_RELEASE_PIN in doc["failed_gates"]

    def test_a_REORDERED_condition_list_is_REJECTED(self, tmp_path):
        # the sneaky one: the SET is identical, so every slot still fills and the topology
        # looks perfect. Only the content address of the release notices.
        run = F.complete_run(tmp_path)
        path = _manifest(tmp_path, run)["path"]
        self._mutate_conditions(run, ["Stim48hr", "Stim8hr", "Rest"])
        doc = _verify(run, path)

        assert doc["n_arm_slots"] == 300          # every slot still filled...
        assert doc["verdict"] == V.R.REJECT       # ...and still refused
        assert V.G_RELEASE_PIN in doc["failed_gates"]

    def test_the_conditions_are_the_RELEASES_in_its_own_order(self, tmp_path):
        run = F.complete_run(tmp_path)
        doc = _verify(run, _manifest(tmp_path, run)["path"])
        assert doc["conditions"] == ["Rest", "Stim8hr", "Stim48hr"]
        assert doc["verdict"] == V.R.ADMIT, doc["failed_gates"]

    def test_a_FORGED_base_portable_flag_is_caught_by_the_selector_crosscheck(
            self, tmp_path):
        run = F.complete_run(tmp_path)
        path = _manifest(tmp_path, run)["path"]
        view_path = os.path.join(run["release_root"], F.VIEW_PATH)
        view = json.load(open(view_path))
        for p in view["programs"]:
            if p["program_id"] == "th9_like":
                p["base_portable"] = True         # promote the non-portable program
        with open(view_path, "w") as fh:
            json.dump(view, fh, indent=2, sort_keys=True)
        doc = _verify(run, path)

        assert doc["verdict"] == V.R.REJECT
        # the staged view no longer hashes to what the release binds
        assert V.G_VIEW_PIN in doc["failed_gates"]


class TestBatchCommentaryIsRefusedByTheVerifierToo:
    def test_batch_commentary_in_a_temporal_bundle_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        # the producer refuses it, so a forger must write it in AFTER the manifest is built
        path = _manifest(tmp_path, run)["path"]
        _patch(run["temporal"][0], "arm_bundle.json",
               lambda d: d.update({"batch_status": "partially_confounded"}))
        doc = _verify(run, path)

        assert doc["verdict"] == V.R.REJECT
        assert V.G_NO_BATCH in doc["failed_gates"]


class TestRetainedRowsAreNotRanks:
    """W5 RETAINS every target with ``rank: null`` when it is not rankable.

    So "in the rows" is not "in the ranking". Counting rows instead of non-null ranks
    would inflate every hit count by exactly the targets the arm could NOT evaluate — the
    ones least entitled to support a claim — and the inflated number would look like
    ordinary evidence.
    """

    def test_a_RETAINED_but_UNRANKED_member_is_not_a_hit(self, tmp_path):
        run = F.complete_run(tmp_path)
        inv = json.load(open(os.path.join(run["pathway"][0], "arm_bundle.json")))
        arm = inv["arms"][0]
        ranking = json.load(open(os.path.join(run["pathway"][0],
                                              arm["ranking"]["path"])))

        # the member IS in the rows...
        rows = {r["target_id"] for r in ranking["records"]}
        assert F.UNRANKABLE_MEMBER in rows
        # ...retained with rank null...
        assert next(r for r in ranking["records"]
                    if r["target_id"] == F.UNRANKABLE_MEMBER)["rank"] is None
        # ...and FIXTURE-SET-1 has 3 members, of which only 2 are ranked
        assert len(F.FIXTURE_SETS["FIXTURE-SET-1"]) == 3
        assert arm["n_hits_by_set"]["FIXTURE-SET-1"] == 2

    def test_counting_the_RETAINED_row_as_a_hit_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        # the producer claims all 3 members of the set — i.e. it counted rows, not ranks
        _patch(run["pathway"][0], "arm_bundle.json",
               lambda d: d["arms"][0]["n_hits_by_set"].update({"FIXTURE-SET-1": 3}))
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert V.G_RECONSTRUCT in doc["failed_gates"]

    def test_an_n_ranked_that_counts_ROWS_instead_of_RANKS_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        d = run["temporal"][0]
        inv = json.load(open(os.path.join(d, "arm_bundle.json")))
        rows = len(json.load(open(os.path.join(d, inv["arms"][0]["ranking"]["path"])))
                   ["records"])
        _patch(d, "arm_bundle.json",
               lambda doc: doc["arms"][0].update({"n_ranked": rows}))
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert V.G_RECONSTRUCT in doc["failed_gates"]

    def test_a_BOUND_ranking_that_does_not_EXIST_is_never_bound(self, tmp_path):
        # "never bind nonexistent files": the producer refuses rather than recording a
        # path to bytes that are not there
        run = F.complete_run(tmp_path)
        d = run["direct"][0]
        inv = json.load(open(os.path.join(d, "arm_bundle.json")))
        os.remove(os.path.join(d, inv["arms"][0]["ranking"]["path"]))
        with pytest.raises(run_manifest.RunManifestError, match="not in the bundle"):
            run_manifest.bind_bundle(d)


class TestTheProducerMayNotAdmitItsOwnRun:
    """The audit's blocker: `complete` + `release_admissible` were set from the TOPOLOGY.

    A correctly-shaped run is not a verified one, and the shape is all the producer can
    see. So a run whose lane reports were bare verdict strings, or which bound inconsistent
    selections, was stamped release_admissible=TRUE by the thing that produced it — and only
    refused later by the external verifier. Anything reading the manifest in between would
    have read an admission that nobody granted.
    """

    def test_the_producer_emits_TOPOLOGY_ONLY_and_never_admits(self, tmp_path):
        doc = _manifest(tmp_path, F.complete_run(tmp_path))
        assert doc["topology_complete"] is True          # the shape is right...
        assert doc["release_admissible"] is not True     # ...and that is NOT an admission
        assert doc["admission"]["status"] == "pending_independent_aggregate_admission"
        assert doc["admission"]["granted_by"] is None
        assert doc["admission"]["producer_may_declare_admission"] is False
        assert doc["topology_complete_is_an_admission"] is False

    def test_a_TOPOLOGY_COMPLETE_but_UNVERIFIED_run_is_PENDING(self, tmp_path):
        # the exact fixture the audit named: every slot filled, nothing verified yet
        run = F.complete_run(tmp_path)
        doc = json.load(open(_manifest(tmp_path, run)["path"]))
        assert doc["topology_complete"] is True
        assert doc["release_admissible"] is not True
        assert doc["admission"]["granted_by"] is None

    def test_ONLY_the_separate_verifier_can_admit(self, tmp_path):
        run = F.complete_run(tmp_path)
        report = _verify(run, _manifest(tmp_path, run)["path"])
        assert report["verdict"] == V.R.ADMIT, report["failed_gates"]
        assert report["release_admissible"] is True
        assert report["admission"]["granted_by"] == V.VERIFIER_ID
        assert report["admission"]["topology_complete_is_an_admission"] is False

    def test_a_BARE_VERDICT_report_is_topology_complete_but_NOT_admitted(self, tmp_path):
        # the incomplete bare-verdict fixture: shape perfect, admission refused
        run = F.complete_run(tmp_path)
        with open(os.path.join(run["direct"][0], "verification.json"), "w") as fh:
            json.dump({"verdict": "admit"}, fh)
        doc = _manifest(tmp_path, run)

        assert doc["topology_complete"] is True          # the producer sees only shape...
        assert doc["release_admissible"] is not True

        report = _verify(run, doc["path"])               # ...and the verifier refuses
        assert report["verdict"] == V.R.REJECT
        assert report["release_admissible"] is False
        assert V.G_VERDICT in report["failed_gates"]

    def test_an_INCONSISTENT_SELECTION_run_is_topology_complete_but_NOT_admitted(
            self, tmp_path):
        run = F.complete_run(tmp_path)
        _patch(run["pathway"][2], "pathway_provenance.json",
               lambda d: d["run_binding"]["selection_release"].update(
                   {"release_canonical_sha256": "c" * 64}))
        doc = _manifest(tmp_path, run)

        assert doc["topology_complete"] is True
        assert doc["release_admissible"] is not True

        report = _verify(run, doc["path"])
        assert report["verdict"] == V.R.REJECT
        assert report["release_admissible"] is False
        assert V.G_SELECTION in report["failed_gates"]

    def test_a_manifest_that_SELF_DECLARES_admission_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        path = _reseal(_manifest(tmp_path, run)["path"], release_admissible=True)
        doc = _verify(run, path)

        assert doc["verdict"] == V.R.REJECT
        assert V.G_NO_SELF_ADMISSION in doc["failed_gates"]

    def test_a_manifest_that_resurrects_the_old_complete_flag_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        path = _reseal(_manifest(tmp_path, run)["path"], complete=True)
        doc = _verify(run, path)

        assert doc["verdict"] == V.R.REJECT
        assert V.G_NO_SELF_ADMISSION in doc["failed_gates"]


class TestTheNativeStage1AndCodeBindings:
    """What replaces the pair-based per-arm fields: the bundle's OWN Stage-1 + build."""

    def test_a_bundle_binding_ANOTHER_SCORER_VIEW_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        _patch(run["temporal"][1], "temporal_provenance.json",
               lambda d: d["run_binding"]["selection_release"].update(
                   {"registry_scorer_view_sha256": "e" * 64}))
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert V.G_PROJECTION in doc["failed_gates"]

    def test_a_bundle_whose_ARMS_STAND_ON_another_program_set_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        _patch(run["direct"][0], "provenance.json",
               lambda d: d["program_admission"].update(
                   {"programs": ["treg_like", "th9_like"]}))   # th9 is not admitted
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert V.G_PROJECTION in doc["failed_gates"]

    def test_a_bundle_that_binds_NO_code_identity_is_REJECTED(self, tmp_path):
        # an arm nobody can attribute to a build is an arm that could have come from
        # anywhere — this is what makes "a lane from another commit" catchable at all
        run = F.complete_run(tmp_path)
        _patch(run["pathway"][0], "pathway_provenance.json",
               lambda d: d["run_binding"].pop("code_identity"))
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert V.G_CODE in doc["failed_gates"]

    def test_a_bundle_that_RECORDED_a_dirty_tree_is_REJECTED(self, tmp_path):
        # the producer RECORDS its tree state; the VERIFIER decides the final status
        run = F.complete_run(tmp_path)
        _patch(run["direct"][0], "provenance.json",
               lambda d: d["run_binding"]["code_identity"].update({"clean_tree": False}))
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert V.G_CLEAN in doc["failed_gates"]

    def test_a_bundle_built_by_a_DIFFERENT_METHOD_is_REJECTED(self, tmp_path):
        # the build and what the code DID are separate roles; neither stands in for the
        # other, and both must agree across the run
        run = F.complete_run(tmp_path)
        _patch(run["temporal"][3], "temporal_provenance.json",
               lambda d: d["run_binding"].update(
                   {"temporal_method_sha256": "f" * 64}))
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert V.G_METHOD in doc["failed_gates"]


class TestTheFiveRequiredNegatives:
    """The producer's per-bundle report is a PREFLIGHT. It admits nothing.

    An adversarial probe walked a clean 15-bundle run past this verifier with ZERO producer
    inventories and ZERO external admissions — and it was ADMITTED. It also resealed a
    role/value `stage2_inputs` list, and resealed a ranking with two ranks SWAPPED, and both
    were ADMITTED with n_failed=0.

    The reason is the same each time: every artifact the aggregate was reading lives inside
    the producer's own output directory, and a file cannot testify that some other process
    made it. These five negatives are the acceptance criteria.
    """

    def test_1_PRODUCER_PREFLIGHT_ALONE_admits_nothing(self, tmp_path):
        run = F.complete_run(tmp_path)
        os.remove(os.path.join(run["root"], F.ADMISSION_FILE))   # keep the preflights
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert doc["n_failed"] > 0
        assert V.G_EXTERNAL_ADMISSION in doc["failed_gates"]

    def test_2_a_MISSING_PRODUCER_INVENTORY_is_REFUSED(self, tmp_path):
        run = F.complete_run(tmp_path)
        os.remove(os.path.join(run["root"], F.INVENTORY_FILE))
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert doc["n_failed"] > 0
        assert V.G_INVENTORY in doc["failed_gates"]

    def test_3_a_RESEALED_stage2_inputs_ROLE_LIST_is_REFUSED(self, tmp_path):
        run = F.complete_run(tmp_path)
        _patch(run["temporal"][0], "temporal_provenance.json",
               lambda d: d["run_binding"].update({"stage2_inputs": [
                   {"role": "direct_config_sha256", "value": "x" * 64}]}))
        F.seal_release(run)                       # fully consistent reseal
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert doc["n_failed"] > 0
        assert V.G_KEYED_PROVENANCE in doc["failed_gates"]

    def test_4_a_RESEALED_RANK_SWAP_is_REFUSED(self, tmp_path):
        """Counts survive a swap. The evidence does not."""
        run = F.complete_run(tmp_path)
        d = run["temporal"][0]
        inv = json.load(open(os.path.join(d, "arm_bundle.json")))
        arm = inv["arms"][0]
        rpath = os.path.join(d, arm["ranking"]["path"])

        ranking = json.load(open(rpath))
        ranked = [r for r in ranking["records"] if r["rank"] is not None]
        ranked[0]["rank"], ranked[1]["rank"] = ranked[1]["rank"], ranked[0]["rank"]
        with open(rpath, "w") as fh:
            json.dump(ranking, fh, indent=2, sort_keys=True)

        # RESEAL EVERYTHING: the arm's ranking binding, the bundle, the inventory, the
        # envelope. Every hash is now self-consistent; every count is unchanged.
        arm["ranking"] = F._binding(d, arm["ranking"]["path"], ranking)
        with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
            json.dump(inv, fh, indent=2, sort_keys=True)
        F.seal_release(run)

        doc = _verify(run, _manifest(tmp_path, run)["path"])
        assert doc["verdict"] == V.R.REJECT
        assert doc["n_failed"] > 0
        assert V.G_RANKS in doc["failed_gates"]

    def test_5_an_EXTERNAL_ADMIT_for_ANOTHER_RELEASE_is_REFUSED(self, tmp_path):
        run = F.complete_run(tmp_path)
        F.write_external_admission(run, release_id="d" * 64)   # admits a different release
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert doc["n_failed"] > 0
        assert V.G_EXTERNAL_BINDS in doc["failed_gates"]

    def test_a_producer_that_ADMITS_ITSELF_in_its_inventory_is_REFUSED(self, tmp_path):
        # 'pending' is the only honest producer state
        run = F.complete_run(tmp_path)
        path = os.path.join(run["root"], F.INVENTORY_FILE)
        doc_i = json.load(open(path))
        doc_i["external_admission"]["status"] = "admit"
        doc_i["release_id"] = F._canon(
            {k: v for k, v in doc_i.items() if k != "release_id"})
        with open(path, "w") as fh:
            json.dump(doc_i, fh, indent=2, sort_keys=True)
        F.write_external_admission(run)

        doc = _verify(run, _manifest(tmp_path, run)["path"])
        assert doc["verdict"] == V.R.REJECT
        assert V.G_INVENTORY in doc["failed_gates"]


class TestOneNativeFilenameSet:
    """The legacy ``temporal_arm_*`` names are not the native set and are refused.

    Native (W5): ``arm_bundle.json``, ``temporal_provenance.json``,
    ``temporal_verification.json``, ``rankings/*.json``.
    """

    def test_the_LEGACY_temporal_arm_names_are_REFUSED(self, tmp_path):
        run = F.complete_run(tmp_path)
        d = run["temporal"][0]
        os.rename(os.path.join(d, "arm_bundle.json"),
                  os.path.join(d, "temporal_arm_bundle.json"))
        os.rename(os.path.join(d, "temporal_verification.json"),
                  os.path.join(d, "temporal_arm_verification.json"))
        with pytest.raises(run_manifest.RunManifestError):
            run_manifest.bind_bundle(d)

    def test_the_native_set_is_what_a_bundle_actually_ships(self, tmp_path):
        run = F.complete_run(tmp_path)
        shipped = set(os.listdir(run["temporal"][0]))
        assert {"arm_bundle.json", "temporal_provenance.json",
                "temporal_verification.json", "rankings"} <= shipped
        assert not any(f.startswith("temporal_arm_") for f in shipped)


class TestTheAdmissionMustComeFromTheINDEPENDENTVerifier:
    def test_a_PRODUCER_SELF_VERIFICATION_id_is_REJECTED(self, tmp_path):
        # the producer's own `spot.stage02.temporal_arm.verifier.v1` is not the independent
        # verifier contract, and a bundle may not admit itself
        run = F.complete_run(tmp_path)
        _patch(run["temporal"][0], "temporal_verification.json",
               lambda d: d.update({"verifier_id": "spot.stage02.temporal_arm.verifier.v1"}))
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert V.G_VERDICT in doc["failed_gates"]

    def test_a_report_that_admits_ITSELF_is_REJECTED(self, tmp_path):
        run = F.complete_run(tmp_path)
        _patch(run["direct"][0], "verification.json",
               lambda d: d.update({"generator_is_not_verifier": False}))
        doc = _verify(run, _manifest(tmp_path, run)["path"])

        assert doc["verdict"] == V.R.REJECT
        assert V.G_VERDICT in doc["failed_gates"]


class TestTheVerifierIsIndependentOfTheProducer:
    """generator != verifier. Enforced, not intended."""

    @staticmethod
    def _imports(module):
        import ast
        src = open(module.__file__).read()
        names = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                # a relative import (level > 0) is an import from the generator package
                names.add(("." * node.level) + (node.module or ""))
        return names

    @pytest.mark.parametrize("module", [V, V.R])
    def test_it_imports_nothing_from_the_generator(self, module):
        producer = {"run_manifest", "arm_topology", "config", "hashing", "code_digest",
                    "emit", "pathway", "genesets", "projection", "arms", "direct"}
        imported = self._imports(module)
        assert not any(name.startswith(".") for name in imported), imported
        assert not (imported & producer), (
            f"{module.__name__} imports {imported & producer} from the generator; a "
            "verifier that reused the producer's functions would agree with it by "
            "construction")

    def test_the_two_desired_change_tables_were_derived_INDEPENDENTLY_and_AGREE(self):
        from direct import arm_topology as T
        for (role, pole), expected in V.R.SPEC_DESIRED_CHANGE.items():
            # the producer DERIVES it from ARM_FORMULA x POLE_SIGN; the verifier holds its
            # own frozen copy. They must agree — and either can catch the other drifting.
            assert T.desired_change_for(role, pole) == expected

    def test_the_two_slot_algebras_AGREE(self):
        from direct import arm_topology as T
        mine = T.expected_slots(["p1", "p2"], ["C1", "C2"], ["s1"])
        theirs = V.R.expected_slots(["p1", "p2"], ["C1", "C2"], ["s1"])
        assert {lane: sorted(mine[lane]) for lane in mine} == {
            lane: sorted(theirs[lane]) for lane in theirs}


def test_the_verifier_does_not_take_the_TOPOLOGY_from_the_manifest_it_audits(tmp_path):
    """A forger shrinks the expected run so a partial one satisfies it."""
    run = F.complete_run(tmp_path)
    run["pathway"] = run["pathway"][:-1]
    path = _manifest(tmp_path, run, allow_partial=True)["path"]
    doc = json.load(open(path))
    doc["conditions"] = run["conditions"][:1]        # "the run was only ever one condition"
    doc["gene_set_sources"] = ["Reactome"]
    doc["topology_complete"] = True
    doc["manifest_sha256"] = content_hash(
        {k: v for k, v in doc.items() if k not in ("created_at", "manifest_sha256")})
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)

    report = _verify(run, path)
    # the expectation came from the pinned batch policy and the pinned sources, not from
    # the document under test — so shrinking the document changes nothing
    assert report["verdict"] == V.R.REJECT
    assert report["conditions"] == run["conditions"]
    assert report["n_expected_arm_slots"] == 300
    assert V.G_PATHWAY_SLOTS in report["failed_gates"]
