"""The Stage-2 aggregate admission gate, attacked from every side it could give way.

NON-PRODUCTION FIXTURES. Every release built here declares ``artifact_class="fixture"``,
its programs are ``FIXTURE_PROG_*`` and its targets ``FIXTURE_TGT_*``. There is no
biological candidate anywhere in this file, and :func:`druglink.stage2_aggregate
.require_analysis` refuses these aggregates by name — a sealed test release can be admitted
as a *fixture* and can never be laundered into the analysis path.

What is under test is the thing the audit's B2 asked for: admission is on the BYTES —
manifest, independent report, 15 bundles, Stage-1 release — and never on a source-code
Boolean. Every refusal must NAME its gate; a test that merely asserts "it raised" would
pass against a module that raised for the wrong reason.
"""
from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import json
import os

import pytest

from druglink import stage2_aggregate as sa
from druglink.hashing import content_hash

PROGRAMS = tuple(f"FIXTURE_PROG_{i:02d}" for i in range(sa.N_PROGRAMS))
TARGETS = ("FIXTURE_TGT_00", "FIXTURE_TGT_01", "FIXTURE_TGT_02")
INDEPENDENT = "spot.stage02.aggregate.independent_verifier.v1"


def _hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# A sealed, NON-PRODUCTION 15-bundle release. Synthetic programs, synthetic targets.
# --------------------------------------------------------------------------- #
def _base_records(lane: str) -> list[dict]:
    out = []
    for prog in PROGRAMS:
        for tgt in TARGETS:
            base = {"base_key": f"{prog}|{tgt}", "program_id": prog, "target_id": tgt,
                    "target_id_namespace": "fixture", "target_symbol": f"SYM_{tgt[-2:]}",
                    "target_ensembl": f"ENSGT{tgt[-2:]}", "evaluable": True}
            if lane == sa.LANE_TEMPORAL:
                base["from_released_estimate_id"] = f"{tgt}|from"
                base["to_released_estimate_id"] = f"{tgt}|to"
            else:
                base["released_estimate_id"] = f"{tgt}|est"
            out.append(base)
    return out


def _records(lane: str, prog: str, source: str | None) -> list[dict]:
    rows = []
    for i, tgt in enumerate(TARGETS):
        if lane == sa.LANE_PATHWAY:
            # An inferred pathway node: nobody perturbed it, so it carries no value and
            # no rank. Null stays null.
            rows.append({"target_id": tgt, "target_id_namespace": "fixture",
                         "set_id": f"{source}:FIXTURE_SET_{i}", "arm_value": None,
                         "rank": None, "evaluable": False})
        else:
            rows.append({"base_key": f"{prog}|{tgt}", "target_id": tgt,
                         "arm_value": 0.5 + i / 10,
                         # the third target is UNRANKED — it must arrive as null, never 0
                         "rank": None if i == 2 else i + 1,
                         "evaluable": i != 2,
                         "desired_target_modulation": "supports_target_inhibition"})
    return rows


def _bundle_doc(key: str, lane: str, ctx: dict) -> dict:
    arms = []
    for prog in PROGRAMS:
        for change in sa.DESIRED_CHANGES:
            arm_key = f"{key}|{prog}|{change}"
            arms.append({
                "arm_key": arm_key, "program_id": prog, "desired_change": change,
                "ranking": {"path": f"rankings/{prog}__{change}.json",
                            "raw_sha256": _hex(f"raw|{arm_key}"),
                            "canonical_sha256": _hex(f"canon|{arm_key}")},
                "records": _records(lane, prog, ctx.get("pathway_source"))})
    doc = {"schema_version": f"spot.stage02_{lane}_arm_bundle.v1",
           "artifact_class": "fixture", "bundle_key": key, "lane": lane,
           "context": dict(ctx), "arms": arms}
    if lane != sa.LANE_PATHWAY:
        doc["base_records"] = _base_records(lane)
    return doc


def _contexts() -> list[tuple[str, str, dict]]:
    out = [(f"{sa.LANE_DIRECT}|{c}", sa.LANE_DIRECT, {"condition": c})
           for c in sa.CONDITIONS]
    out += [(f"{sa.LANE_TEMPORAL}|{a}|{b}", sa.LANE_TEMPORAL,
             {"from_condition": a, "to_condition": b})
            for a, b in sa.ordered_condition_pairs()]
    out += [(f"{sa.LANE_PATHWAY}|{c}|{s}", sa.LANE_PATHWAY,
             {"condition": c, "pathway_source": s})
            for c in sa.CONDITIONS for s in sa.PATHWAY_SOURCES]
    return out


def build_release(root, *, mutate_bundles=None, mutate_inventory=None,
                  mutate_manifest=None, mutate_after_seal=None, mutate_report=None,
                  artifact_class="fixture", mutate_disk=None):
    """Write a sealed NON-PRODUCTION release; return the four admission paths."""
    root = str(root)
    bundles_root = os.path.join(root, "bundles")
    docs = {key: _bundle_doc(key, lane, ctx) for key, lane, ctx in _contexts()}
    if mutate_bundles:
        mutate_bundles(docs)

    inventory = []
    for key, lane, ctx in _contexts():
        rel = os.path.join(lane, key.replace("|", "__") + ".json")
        full = os.path.join(bundles_root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        payload = json.dumps(docs[key], sort_keys=True, separators=(",", ":"))
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(payload)
        inventory.append({"bundle_key": key, "lane": lane, "path": rel,
                          "raw_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                          "canonical_sha256": content_hash(
                              json.loads(json.dumps(docs[key]), parse_float=str)),
                          **ctx})
    if mutate_inventory:
        mutate_inventory(inventory)

    stage1_path = os.path.join(root, "stage1_release.json")
    with open(stage1_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"release_id": "fixture_stage1_v3", "programs": list(PROGRAMS)},
                            sort_keys=True))

    manifest = {
        "schema_version": sa.AGGREGATE_MANIFEST_SCHEMA,
        "artifact_class": artifact_class,
        "generated_at": "2026-07-13T00:00:00Z",
        "stage1_release": {"release_id": "fixture_stage1_v3",
                           "raw_sha256": sa.file_sha256(stage1_path)},
        "inventory": inventory,
    }
    if mutate_manifest:
        mutate_manifest(manifest)
    manifest[sa.SELF_HASH_FIELD] = sa.manifest_self_hash(manifest)
    if mutate_after_seal:
        mutate_after_seal(manifest)

    manifest_path = os.path.join(root, "aggregate_run_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(manifest, sort_keys=True))

    report = {"schema_version": sa.AGGREGATE_REPORT_SCHEMA, "verifier_id": INDEPENDENT,
              "verdict": sa.ADMIT,
              "admits": {"manifest_raw_sha256": sa.file_sha256(manifest_path),
                         "manifest_canonical_sha256": content_hash(manifest)}}
    if mutate_report:
        mutate_report(report)
    report_path = os.path.join(root, "aggregate_verification.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(report, sort_keys=True))

    paths = {"manifest_path": manifest_path, "report_path": report_path,
             "bundles_root": bundles_root, "stage1_release_path": stage1_path}
    if mutate_disk:
        mutate_disk(paths)
    return paths


@pytest.fixture(scope="module")
def honest(tmp_path_factory):
    return build_release(tmp_path_factory.mktemp("s2_aggregate"))


@pytest.fixture(scope="module")
def admitted(honest):
    return sa.admit_aggregate(**honest)


def _gate(exc) -> str:
    return str(exc.value)


# --------------------------------------------------------------------------- #
# The honest release. NON-VACUOUS: nothing here passes on an empty collection.
# --------------------------------------------------------------------------- #
def test_the_topology_is_exactly_15_bundles_and_300_arm_slots(admitted):
    assert len(admitted.bundles) == 15
    assert len(admitted.arms) == 300
    assert admitted.counts["bundles_per_lane"] == {"direct": 3, "temporal": 6,
                                                   "pathway": 6}
    assert admitted.counts["arms_per_lane"] == {"direct": 60, "temporal": 120,
                                                "pathway": 120}
    assert len({b.bundle_key for b in admitted.bundles}) == 15
    assert len({a.arm_key for a in admitted.arms}) == 300
    assert admitted.program_ids == tuple(sorted(PROGRAMS))


def test_the_counts_are_derived_from_the_conditions_not_copied(admitted):
    assert sa.N_BUNDLES == 3 + 6 + 6
    assert sa.N_ARM_SLOTS == 300
    assert len(sa.ordered_condition_pairs()) == 6
    assert ("Rest", "Stim48hr") in sa.ordered_condition_pairs()
    assert ("Stim48hr", "Rest") in sa.ordered_condition_pairs()   # a DISTINCT bundle
    assert admitted.counts["topology_is_derived_not_declared"] is True


def test_every_arm_retains_its_reusable_identity_and_context(admitted):
    assert admitted.arms, "non-vacuous guard: there must be arms to check"
    for arm in admitted.arms:
        assert arm.arm_key and arm.program_id in PROGRAMS
        assert arm.desired_change in sa.DESIRED_CHANGES
        assert arm.lane in sa.LANES
        if arm.lane == sa.LANE_TEMPORAL:
            assert arm.from_condition and arm.to_condition
            assert arm.from_condition != arm.to_condition
        elif arm.lane == sa.LANE_PATHWAY:
            assert arm.condition and arm.pathway_source in sa.PATHWAY_SOURCES
        else:
            assert arm.condition in sa.CONDITIONS
        assert arm.ranking["raw_sha256"] and arm.ranking["canonical_sha256"]
        assert arm.provenance["manifest_self_hash"] == admitted.manifest_self_hash
        assert arm.provenance["independent_verifier_id"] == INDEPENDENT
        assert arm.provenance["bundle_raw_sha256"]
        assert arm.records, "an arm with no records retains no target identity"


def test_measured_records_carry_exact_identity_and_a_released_estimate(admitted):
    measured = [a for a in admitted.arms if a.lane in sa.MEASURED_LANES]
    assert len(measured) == 180
    for arm in measured:
        for rec in arm.records:
            assert rec["target_id"] in TARGETS
            assert rec["target_id_namespace"] == "fixture"
            assert rec["released_estimate_id"]
            if arm.lane == sa.LANE_TEMPORAL:
                # a DiD stands on BOTH endpoints; reporting one misattributes the change
                assert set(rec["released_estimate_id"]) == {"from", "to"}


def test_an_unranked_target_arrives_as_NULL_never_zero_and_never_last(admitted):
    unranked = [r for a in admitted.arms for r in a.records if r["rank"] is None]
    assert unranked, "non-vacuous guard: the fixture must contain unranked targets"
    for rec in unranked:
        assert rec["rank"] is None
        assert rec["rank"] != 0
    ranked = [r for a in admitted.arms for r in a.records if r["rank"] is not None]
    assert ranked and all(r["rank"] >= 1 for r in ranked)


def test_an_arm_carries_no_pair_role_no_pole_and_no_combined_score(admitted):
    names = {f.name for f in dataclasses.fields(sa.LoadedArm)}
    record_keys = set(admitted.arms[0].records[0])
    for banned in ("away_from_A", "toward_B", "role", "pole", "desired_arm",
                   "score", "combined_score", "total"):
        assert banned not in names and banned not in record_keys
    assert admitted.counts["pair_roles_assigned"] is False
    assert admitted.counts["combined_objective_permitted"] is False


# --------------------------------------------------------------------------- #
# THE POINT OF THE MODULE: admission is on the bytes, not on a source constant.
# --------------------------------------------------------------------------- #
def test_admission_is_not_a_source_code_boolean():
    """The gate this module replaces was a constant. A constant admits nothing.

    Checked over the AST, not the text: the prose names the flag deliberately (that is
    the whole point of the module), so a substring search would pass on a module that
    still *read* it. Only an actual load of the name counts.
    """
    with open(sa.__file__, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "DETACHED_CLONE_MATRIX_GREEN" not in names, (
        "admission still reads the stale source-code flag")

    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                for a in n.names}
    assert "arm_query" not in imported

    module_bools = [k for k, v in vars(sa).items() if isinstance(v, bool)]
    assert module_bools == [], (
        f"module-level Booleans {module_bools} — a constant in a source file names no "
        "manifest, no report, no verifier and no bytes; it cannot admit anything")


def test_the_manifest_must_prove_its_own_identity(tmp_path):
    def tamper(manifest):
        manifest["inventory"][0]["raw_sha256"] = "f" * 64      # resealed? no: post-seal
    paths = build_release(tmp_path, mutate_after_seal=tamper)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_MANIFEST_SELF_HASH in _gate(exc)


def test_the_self_hash_ignores_non_semantic_timestamps():
    a = {"artifact_class": "fixture", "inventory": [], "generated_at": "2026-01-01"}
    b = dict(a, generated_at="2099-12-31")
    assert sa.manifest_self_hash(a) == sa.manifest_self_hash(b)
    c = dict(a, inventory=[{"bundle_key": "direct|Rest"}])
    assert sa.manifest_self_hash(c) != sa.manifest_self_hash(a)


# --------------------------------------------------------------------------- #
# The independent report. It must ADMIT, and it must admit THESE bytes.
# --------------------------------------------------------------------------- #
def test_a_report_binding_a_DIFFERENT_manifest_is_refused(tmp_path):
    paths = build_release(
        tmp_path,
        mutate_report=lambda r: r["admits"].update({"manifest_raw_sha256": "f" * 64}))
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_REPORT_BINDS_ANOTHER_MANIFEST in _gate(exc)


def test_a_report_binding_a_different_CANONICAL_hash_is_refused(tmp_path):
    paths = build_release(
        tmp_path,
        mutate_report=lambda r: r["admits"].update(
            {"manifest_canonical_sha256": "e" * 64}))
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_REPORT_BINDS_ANOTHER_MANIFEST in _gate(exc)


def test_a_report_that_names_no_hash_at_all_is_an_opinion_not_an_admission(tmp_path):
    paths = build_release(tmp_path, mutate_report=lambda r: r.update({"admits": {}}))
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_REPORT_BINDS_NOTHING in _gate(exc)


def test_a_verdict_that_is_not_admit_is_refused(tmp_path):
    paths = build_release(tmp_path, mutate_report=lambda r: r.update({"verdict": "reject"}))
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_VERDICT_NOT_ADMIT in _gate(exc)


def test_a_non_independent_verifier_cannot_admit(tmp_path):
    paths = build_release(
        tmp_path,
        mutate_report=lambda r: r.update({"verifier_id": "spot.stage02.self_verifier.v1"}))
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_VERIFIER_NOT_INDEPENDENT in _gate(exc)


def test_the_report_may_not_BE_the_manifest(honest):
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(manifest_path=honest["manifest_path"],
                           report_path=honest["manifest_path"],
                           bundles_root=honest["bundles_root"],
                           stage1_release_path=honest["stage1_release_path"])
    assert sa.GATE_SELF_ADMISSION in _gate(exc)


def test_a_missing_manifest_refuses_and_never_falls_back_to_a_fixture(tmp_path):
    paths = build_release(tmp_path)
    os.remove(paths["manifest_path"])
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_ARTIFACT_NOT_ON_DISK in _gate(exc)


# --------------------------------------------------------------------------- #
# Path traversal. Every bundle resolves INSIDE the root, or it is not read.
# --------------------------------------------------------------------------- #
def test_a_traversing_bundle_path_is_refused(tmp_path):
    def escape(inv):
        inv[0]["path"] = "../../etc/arm_bundle.json"
    paths = build_release(tmp_path, mutate_inventory=escape)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_PATH_TRAVERSAL in _gate(exc)


def test_an_absolute_bundle_path_is_refused(tmp_path):
    def escape(inv):
        inv[4]["path"] = "/etc/passwd"
    paths = build_release(tmp_path, mutate_inventory=escape)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_PATH_TRAVERSAL in _gate(exc)


def test_a_symlink_out_of_the_root_is_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "arm_bundle.json").write_text("{}", encoding="utf-8")

    def link(paths):
        target = os.path.join(paths["bundles_root"], "direct", "escape.json")
        os.symlink(str(outside / "arm_bundle.json"), target)

    paths = build_release(tmp_path / "rel",
                          mutate_inventory=lambda inv: inv[0].update(
                              {"path": "direct/escape.json"}),
                          mutate_disk=link)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_PATH_TRAVERSAL in _gate(exc)


# --------------------------------------------------------------------------- #
# The inventory: missing, duplicate, unknown, partial — each refused BY NAME.
# --------------------------------------------------------------------------- #
def test_a_missing_bundle_is_refused(tmp_path):
    paths = build_release(tmp_path, mutate_inventory=lambda inv: inv.pop(7))
    with pytest.raises(sa.AggregateTopologyRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_MISSING_BUNDLE in _gate(exc)


def test_a_missing_LANE_is_refused_and_named(tmp_path):
    def drop_temporal(inv):
        inv[:] = [e for e in inv if e["lane"] != sa.LANE_TEMPORAL]
    paths = build_release(tmp_path, mutate_inventory=drop_temporal)
    with pytest.raises(sa.AggregateTopologyRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_MISSING_BUNDLE in _gate(exc)
    assert "temporal|Rest|Stim8hr" in _gate(exc)


def test_a_duplicate_bundle_key_cannot_fill_a_missing_slot(tmp_path):
    def dup(inv):
        inv[14] = copy.deepcopy(inv[0])          # count still says 15
    paths = build_release(tmp_path, mutate_inventory=dup)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_DUPLICATE_BUNDLE in _gate(exc)


def test_an_unknown_lane_is_refused(tmp_path):
    paths = build_release(
        tmp_path, mutate_inventory=lambda inv: inv[0].update({"lane": "chronological"}))
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_UNKNOWN_LANE in _gate(exc)


def test_an_unknown_CONTEXT_is_refused(tmp_path):
    def alien(inv):
        inv[0].update({"bundle_key": "direct|Stim72hr", "condition": "Stim72hr"})
    paths = build_release(tmp_path, mutate_inventory=alien)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_UNKNOWN_LANE in _gate(exc)


def test_a_bundle_key_that_disagrees_with_its_own_context_is_refused(tmp_path):
    def mislabel(inv):
        inv[0]["bundle_key"] = "direct|Stim48hr"          # entry's condition is Rest
    paths = build_release(tmp_path, mutate_inventory=mislabel)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_UNKNOWN_LANE in _gate(exc)


def test_a_partial_inventory_is_never_admissible(tmp_path):
    paths = build_release(tmp_path, mutate_inventory=lambda inv: inv.clear())
    with pytest.raises(sa.AggregateTopologyRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_INCOMPLETE_TOPOLOGY in _gate(exc)


def test_a_partial_BUNDLE_short_of_its_arm_slots_is_refused(tmp_path):
    def drop_arms(docs):
        docs["temporal|Rest|Stim48hr"]["arms"] = \
            docs["temporal|Rest|Stim48hr"]["arms"][:18]
    paths = build_release(tmp_path, mutate_bundles=drop_arms)
    with pytest.raises(sa.AggregateTopologyRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_INCOMPLETE_TOPOLOGY in _gate(exc)
    assert "298" in _gate(exc)


def test_a_missing_program_across_the_release_is_refused(tmp_path):
    def drop_program(docs):
        for doc in docs.values():
            doc["arms"] = [a for a in doc["arms"] if a["program_id"] != PROGRAMS[3]]
    paths = build_release(tmp_path, mutate_bundles=drop_program)
    with pytest.raises(sa.AggregateTopologyRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_INCOMPLETE_TOPOLOGY in _gate(exc)
    assert "9 programs" in _gate(exc)


# --------------------------------------------------------------------------- #
# The bytes on disk are the bytes that were admitted.
# --------------------------------------------------------------------------- #
def test_a_bundle_mutated_after_admission_is_refused(tmp_path):
    def mutate(paths):
        victim = os.path.join(paths["bundles_root"], "direct", "direct__Rest.json")
        with open(victim, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["arms"][0]["records"][2]["rank"] = 1        # promote the UNRANKED target
        with open(victim, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, sort_keys=True, separators=(",", ":")))

    paths = build_release(tmp_path, mutate_disk=mutate)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_BUNDLE_BYTES_MOVED in _gate(exc)


def test_a_stage1_release_that_is_not_the_pinned_one_is_refused(tmp_path):
    def swap(paths):
        with open(paths["stage1_release_path"], "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"release_id": "some_other_release"}))

    paths = build_release(tmp_path, mutate_disk=swap)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_STAGE1_RELEASE_UNBOUND in _gate(exc)


def test_a_dangling_base_key_resolves_to_no_identity_and_is_refused(tmp_path):
    def dangle(docs):
        docs["direct|Rest"]["arms"][0]["records"][0]["base_key"] = "NOPE|NOPE"
    paths = build_release(tmp_path, mutate_bundles=dangle)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_ARM_IDENTITY_UNRESOLVED in _gate(exc)


def test_a_base_key_resolving_to_a_DIFFERENT_target_is_refused(tmp_path):
    def swap(docs):
        rec = docs["direct|Rest"]["arms"][0]["records"][0]
        rec["base_key"] = f"{PROGRAMS[0]}|{TARGETS[1]}"     # says TGT_00, resolves TGT_01
    paths = build_release(tmp_path, mutate_bundles=swap)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_ARM_IDENTITY_UNRESOLVED in _gate(exc)


# --------------------------------------------------------------------------- #
# The fixture firewall. These sealed releases can never become an analysis.
# --------------------------------------------------------------------------- #
def test_a_fixture_aggregate_is_refused_by_the_analysis_path(admitted):
    assert admitted.artifact_class == "fixture"
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.require_analysis(admitted)
    assert sa.GATE_FIXTURE_FIREWALL in _gate(exc)


def test_an_unknown_artifact_class_is_refused(tmp_path):
    from druglink import artifact_class as ac
    paths = build_release(tmp_path, artifact_class="production")
    with pytest.raises(ac.ArtifactClassError):
        sa.admit_aggregate(**paths)
