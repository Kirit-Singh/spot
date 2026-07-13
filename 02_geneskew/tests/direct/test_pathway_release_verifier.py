"""The independent pathway RELEASE verifier + CLI (pathway_arm_external_admission.json).

An envelope over the (condition x source) bundles, anchored OUTWARD: the universe AND the
scorer/method pins to the Stage-1 v3 release, each cell's local validity to its INDEPENDENT
per-bundle report (one to one, exact gate inventory, attested bytes), the two gene-set source
artifacts pinned, the solver lock to a constant, the producer inventory native-shaped, its
release_id mandatory and byte-bound. The fixtures build the REAL producer shapes so the tests
attack production bytes.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest
from direct import verify_pathway_release as VR
from direct import verify_rules as R
from direct import verify_signature_matrix as SM

CONDITIONS = ["Rest", "Stim8hr", "Stim48hr"]
SOURCES = ["reactome", "go_bp"]                     # lowercase ids, as the bundles carry them
RELEASE_SOURCES = ["GO-BP", "Reactome"]             # display-case, as selector.pathway_sources
LOCK = VR.STAGE2_SOLVER_LOCK_SHA256
SCORER_CANON = "v" * 64                             # release pin == bundle release-scorer-view
METHOD = "stage1-continuous-v3.0.1"
SCORER_VIEW = "5" * 64
CODE_IDENTITY = {"lane": "production", "code_tree_sha256": "c" * 64}

# the EXACT per-bundle gate inventory, taken from the producer-verifier's own constants
BUNDLE_GATES = [SM.V1, SM.V1_REFMAN, SM.V2_VALUES, SM.V2_BITS, SM.V2_CANON, SM.V2_ANCHOR,
                SM.V2_FINITE, SM.V3, SM.V4, SM.V5, SM.V6, SM.V7, SM.V8, SM.V9, SM.V10,
                SM.V_IDENTITY, SM.V_EXTERNAL_MASK, SM.V_SOLVER_LOCK, SM.V_QC, SM.V_STALE_SOURCE,
                SM.V_RELEASE_ROOT]


def _write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _raw(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _hashes(path):
    return {"raw_sha256": _raw(path), "canonical_sha256": R.content_sha256(json.load(open(path)))}


def _gene_doc(tag):
    return {"schema_version": "spot.stage02_gene_sets.v1", "source": tag, "n_sets": 10,
            "gene_set_release": {"source": tag, "release_id": f"{tag}-2024", "sha256": "g" * 64}}


def _bundle(root, cond, src, *, scorer=SCORER_VIEW, code=None, release_scorer=SCORER_CANON,
            method=METHOD, env_lock=LOCK, records=None, doc_source=None, gene_tag=None):
    binding = {
        "condition": cond, "source": src,
        "scorer_view_sha256": scorer,
        "release_scorer_view_canonical_sha256": release_scorer,
        "code_identity": code if code is not None else CODE_IDENTITY,
        "stage1_release_hashes": {"registry_raw_sha256": "a" * 64, "method_version": method},
        "stage1_release_kind": "fixture",
        "environment_lock": {"sha256": env_lock, "status": "locked"},
        "records_sha256": records or hashlib.sha256(f"{cond}:{src}".encode()).hexdigest(),
    }
    full = R.content_sha256(binding)
    d = os.path.join(root, full[:VR.RUN_ID_LEN])
    _write(os.path.join(d, VR.PROVENANCE_FILE),
           {"pathway_run_id": full[:VR.RUN_ID_LEN], "pathway_run_sha256": full,
            "run_binding": binding})
    _write(os.path.join(d, VR.BUNDLE_FILE),
           {"condition": cond, "source": doc_source or src, "bundle_id": full[:VR.RUN_ID_LEN],
            "arms": [], "schema_version": "spot.stage02_pathway_arm.v1"})
    _write(os.path.join(d, VR.GENE_SETS_FILE), _gene_doc(gene_tag or src))
    return d


def _run_id(d):
    return R.content_sha256(json.load(open(os.path.join(d, VR.PROVENANCE_FILE)))["run_binding"]
                            )[:VR.RUN_ID_LEN]


def _release_file(path, conds=CONDITIONS, srcs=RELEASE_SOURCES, scorer=SCORER_CANON,
                  method=METHOD):
    _write(path, {"schema": VR.STAGE1_RELEASE_SCHEMA, "method_version": method,
                  "registry_scorer_view_canonical_sha256": scorer, "self_release_sha256": "s" * 64,
                  "selector": {"conditions": list(conds), "pathway_sources": list(srcs),
                               "registry_scorer_view_canonical_sha256": scorer}})
    return path


def _report(path, d, *, verdict="admit", n_failed=0, gates=None, run_ids=None, tamper=False,
            attest_gene=True):
    rid = _run_id(d)
    gate_list = BUNDLE_GATES if gates is None else gates
    att = {rid: {VR.PROVENANCE_FILE: _raw(os.path.join(d, VR.PROVENANCE_FILE))}}
    if attest_gene:
        att[rid][VR.GENE_SETS_FILE] = _raw(os.path.join(d, VR.GENE_SETS_FILE))
    body = {"schema_version": VR.BUNDLE_REPORT_SCHEMA, "verifier_id": VR.BUNDLE_VERIFIER_ID,
            "generator_is_not_verifier": True, "fail_closed": True, "n_bundles": 1,
            "n_conditions": 1, "run_ids": [rid] if run_ids is None else run_ids,
            "bound_artifacts": att, "verdict": verdict, "n_failed": n_failed,
            "gates": [{"check": g, "status": "pass"} for g in gate_list]}
    sha = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if tamper:
        body["gates"].append({"check": "SNUCK_IN", "status": "pass"})
    _write(path, dict(body, report_sha256=sha))
    return path


def _reports(rep_dir, dirs):
    return [_report(os.path.join(rep_dir, f"r{i}.json"), d) for i, d in enumerate(dirs)]


def _inventory(path, dirs, root, *, status="pending", required_verifier_id=VR.VERIFIER_ID,
               schema=VR.RELEASE_SCHEMA, generic=False, conds=CONDITIONS, srcs=SOURCES,
               drop=None, extra=False, release_id=True, env_lock_sha=LOCK):
    entries = []
    for d in dirs:
        b = json.load(open(os.path.join(d, VR.PROVENANCE_FILE)))["run_binding"]
        entry = {"bundle_key": f"{b['condition']}|{b['source']}", "bundle_id": _run_id(d),
                 "relative_dir": os.path.relpath(d, root).replace(os.sep, "/"),
                 "n_arms": 0, "arm_keys": [],
                 "files": {VR.BUNDLE_FILE: _hashes(os.path.join(d, VR.BUNDLE_FILE)),
                           VR.PROVENANCE_FILE: _hashes(os.path.join(d, VR.PROVENANCE_FILE))},
                 "rankings": {}}
        if generic:
            entry["context"] = {"condition": b["condition"], "gene_set_source": b["source"]}
        else:
            entry["condition"], entry["source"] = b["condition"], b["source"]
        entries.append(entry)
    inv = {"schema_version": schema,
           "release_id_rule": "sha256(canonical JSON excluding release_id)",
           "lane": "pathway", "stage1_binding": {"method_version": METHOD},
           "env_lock": {"sha256": env_lock_sha, "status": "locked"},
           "env_lock_sha256": env_lock_sha,
           "topology": {"topology_rule_id": "spot.stage02.pathway.arm.topology.v1",
                        "n_conditions": len(conds), "n_sources": len(srcs),
                        "conditions": list(conds), "sources": list(srcs),
                        "expected_n_bundles": len(conds) * len(srcs),
                        "grid": [f"{c}|{s}" for c in conds for s in srcs]},
           "n_bundles": len(entries), "n_logical_arms": 0, "arm_keys": [],
           "bundles": sorted(entries, key=lambda e: e["bundle_key"]),
           "external_admission": {"status": status, "required_verifier_id": required_verifier_id,
                                  "required_report_schema_version":
                                      "spot.stage02_temporal_arm_external_admission.v1"}}
    if drop:
        inv.pop(drop, None)
    if extra:
        inv["surprise_field"] = "not native"
    if release_id:
        inv["release_id"] = R.content_sha256(inv)
    _write(path, inv)
    return path


def _build(tmp, *, conds=CONDITIONS, srcs=SOURCES, generic_inv=False, **bundle_kw):
    root = str(tmp / "pathway")
    dirs = [_bundle(root, c, s, **bundle_kw) for c in conds for s in srcs]
    return {
        "root": root, "dirs": dirs, "tmp": tmp,
        "release": _release_file(str(tmp / "stage01_v3_release.json")),
        "inventory": _inventory(str(tmp / VR.RELEASE_FILE), dirs, root, generic=generic_inv),
        "reports": _reports(str(tmp / "verification"), dirs),
    }


@pytest.fixture
def release(tmp_path):
    return _build(tmp_path)


def _verify(rel, dirs=None, inv="_", release="_", reports="_"):
    return VR.verify(
        bundle_dirs=rel["dirs"] if dirs is None else dirs,
        inventory_path=rel["inventory"] if inv == "_" else inv,
        release_path=rel["release"] if release == "_" else release,
        bundle_report_paths=rel["reports"] if reports == "_" else reports)


def _failed(res):
    return {c["check"] for c in res["checks"] if c["status"] == VR.FAIL}


# =========================================================================== #
# THE HONEST RELEASE
# =========================================================================== #
class TestTheHonestReleaseAdmits:
    def test_it_admits_with_a_lane_specific_envelope(self, release):
        res = _verify(release)
        assert res["verdict"] == VR.ADMIT, sorted(_failed(res))
        body = res["body"]
        assert body["schema_version"] == "spot.stage02_pathway_arm_external_admission.v1"
        assert "temporal" not in body["schema_version"]
        assert body["n_bundles"] == 6 and body["n_failed"] == 0 and body["verdict"] == "ADMIT"

    def test_the_pinned_gate_inventory_matches_the_producer_verifier(self):
        assert VR.REQUIRED_BUNDLE_GATES == set(BUNDLE_GATES)
        assert len(VR.REQUIRED_BUNDLE_GATES) == 21

    def test_it_binds_exactly_two_gene_set_source_artifacts(self, release):
        art = _verify(release)["body"]["gene_set_source_artifacts"]
        assert set(art) == {"reactome", "go_bp"} and len(set(art.values())) == 2

    def test_the_envelope_report_id_is_the_integration_self_hash(self, release):
        body = _verify(release)["body"]
        rest = {k: v for k, v in body.items() if k != VR.REPORT_ID_FIELD}
        assert body[VR.REPORT_ID_FIELD] == R.content_sha256(rest) and len(body["report_id"]) == 64

    def test_the_generic_context_relative_dir_inventory_is_accepted(self, tmp_path):
        rel = _build(tmp_path, generic_inv=True)
        assert _verify(rel)["verdict"] == VR.ADMIT, sorted(_failed(_verify(rel)))


# =========================================================================== #
# universe + external scorer/method pins
# =========================================================================== #
class TestTheAuthoritativeUniverseAndPins:
    def test_a_wrong_but_3x2_universe_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path, conds=["Foo", "Bar", "Baz"], srcs=["x", "y"])
        rel["release"] = _release_file(str(tmp_path / "rel.json"))
        assert VR.G_TOPOLOGY in _failed(_verify(rel))

    def test_a_MISSING_release_anchor_is_fail_closed(self, release):
        assert VR.G_RELEASE_ANCHOR in _failed(_verify(release, release=None))

    def test_six_bundles_sharing_a_WRONG_scorer_view_are_REFUSED(self, tmp_path):
        # shared but not the release's pin — agreement with each other is not enough
        rel = _build(tmp_path, release_scorer="9" * 64)
        assert VR.G_ONE_RELEASE in _failed(_verify(rel))

    def test_six_bundles_sharing_a_WRONG_method_version_are_REFUSED(self, tmp_path):
        rel = _build(tmp_path, method="stage1-continuous-vWRONG")
        assert VR.G_ONE_RELEASE in _failed(_verify(rel))

    def test_ALL_NULL_bindings_do_not_pass_as_one_release(self, tmp_path):
        rel = _build(tmp_path, scorer=None, code=None, release_scorer=None, env_lock=None)
        assert VR.G_ONE_RELEASE in _failed(_verify(rel))

    def test_a_swapped_off_pin_solver_lock_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path, env_lock="e" * 64)
        assert VR.G_ONE_RELEASE in _failed(_verify(rel))

    def test_a_NULL_run_id_is_REFUSED(self, release):
        d = release["dirs"][0]
        prov = json.load(open(os.path.join(d, VR.PROVENANCE_FILE)))
        prov["pathway_run_id"] = None
        _write(os.path.join(d, VR.PROVENANCE_FILE), prov)
        assert VR.G_REOPEN in _failed(_verify(release))


# =========================================================================== #
# the two gene-set source artifacts
# =========================================================================== #
class TestTheGeneSetSources:
    def test_two_sources_sharing_one_artifact_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path, gene_tag="shared")            # every bundle the same gene-set file
        assert VR.G_GENE_SETS in _failed(_verify(rel))

    def test_a_source_whose_bundles_disagree_on_the_artifact_is_REFUSED(self, release):
        d = release["dirs"][0]
        _write(os.path.join(d, VR.GENE_SETS_FILE), _gene_doc("reactome-TAMPERED"))
        assert VR.G_GENE_SETS in _failed(_verify(release))

    def test_a_MISSING_gene_set_file_is_REFUSED(self, release):
        os.remove(os.path.join(release["dirs"][0], VR.GENE_SETS_FILE))
        assert VR.G_GENE_SETS in _failed(_verify(release))

    def test_a_gene_set_the_report_never_attested_is_REFUSED(self, release):
        # swap the gene-set bytes AFTER the report was emitted: the report attests the old hash
        d = release["dirs"][0]
        gs = os.path.join(d, VR.GENE_SETS_FILE)
        doc = json.load(open(gs))
        doc["n_sets"] = 999
        _write(gs, doc)
        assert VR.G_GENE_SETS in _failed(_verify(release))


# =========================================================================== #
# one independent admitting report per cell, exact gate inventory
# =========================================================================== #
class TestEveryCellIsIndependentlyAdmitted:
    def test_NO_reports_is_fail_closed(self, release):
        assert VR.G_BUNDLE_ADMITTED in _failed(_verify(release, reports=[]))

    def test_ONE_report_listing_all_six_run_ids_is_REFUSED(self, release):
        allids = [_run_id(d) for d in release["dirs"]]
        one = _report(os.path.join(str(release["tmp"]), "all.json"), release["dirs"][0],
                      run_ids=allids)
        assert VR.G_BUNDLE_ADMITTED in _failed(_verify(release, reports=[one]))

    def test_a_REJECTING_report_blocks_the_release(self, release):
        _report(release["reports"][0], release["dirs"][0], verdict="reject", n_failed=1)
        assert VR.G_BUNDLE_ADMITTED in _failed(_verify(release))

    def test_a_TRUNCATED_gate_inventory_is_REFUSED(self, release):
        _report(release["reports"][0], release["dirs"][0], gates=BUNDLE_GATES[:-1])
        assert VR.G_BUNDLE_ADMITTED in _failed(_verify(release))

    def test_an_EXTRA_unknown_gate_is_REFUSED(self, release):
        _report(release["reports"][0], release["dirs"][0], gates=BUNDLE_GATES + ["V_MADE_UP"])
        assert VR.G_BUNDLE_ADMITTED in _failed(_verify(release))

    def test_a_DUPLICATE_gate_is_REFUSED(self, release):
        _report(release["reports"][0], release["dirs"][0], gates=BUNDLE_GATES + [BUNDLE_GATES[0]])
        assert VR.G_BUNDLE_ADMITTED in _failed(_verify(release))

    def test_a_single_FAILED_gate_is_REFUSED(self, release):
        g = [{"check": x, "status": "pass"} for x in BUNDLE_GATES]
        # build a report whose gates all named but one FAILED — reuse _report with custom gates
        d = release["dirs"][0]
        rid = _run_id(d)
        body = {"schema_version": VR.BUNDLE_REPORT_SCHEMA, "verifier_id": VR.BUNDLE_VERIFIER_ID,
                "generator_is_not_verifier": True, "fail_closed": True, "n_bundles": 1,
                "n_conditions": 1, "run_ids": [rid],
                "bound_artifacts": {rid: {VR.PROVENANCE_FILE: _raw(os.path.join(
                    d, VR.PROVENANCE_FILE)), VR.GENE_SETS_FILE: _raw(os.path.join(
                        d, VR.GENE_SETS_FILE))}},
                "verdict": "admit", "n_failed": 0,
                "gates": g[:-1] + [{"check": BUNDLE_GATES[-1], "status": "fail"}]}
        sha = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        _write(release["reports"][0], dict(body, report_sha256=sha))
        assert VR.G_BUNDLE_ADMITTED in _failed(_verify(release))

    def test_a_TAMPERED_report_self_hash_is_REFUSED(self, release):
        _report(release["reports"][0], release["dirs"][0], tamper=True)
        assert VR.G_BUNDLE_ADMITTED in _failed(_verify(release))

    def test_a_FORGED_producer_verification_is_not_an_independent_report(self, release):
        forged = os.path.join(str(release["tmp"]), "producer_verification.json")
        _write(forged, {"schema_version": "spot.stage02_pathway_verification.v1",
                        "verdict": "admit", "n_failed": 0,
                        "run_ids": [_run_id(release["dirs"][0])], "report_sha256": "0" * 64,
                        "gates": [{"check": g, "status": "pass"} for g in BUNDLE_GATES]})
        reports = [forged] + release["reports"][1:]
        assert VR.G_BUNDLE_ADMITTED in _failed(_verify(release, reports=reports))

    def test_mutating_a_bundle_AFTER_its_report_unbinds_it(self, release):
        d = release["dirs"][0]
        pp = os.path.join(d, VR.PROVENANCE_FILE)
        prov = json.load(open(pp))
        prov["run_binding"]["records_sha256"] = "8" * 64
        full = R.content_sha256(prov["run_binding"])
        prov["pathway_run_id"], prov["pathway_run_sha256"] = full[:VR.RUN_ID_LEN], full
        _write(pp, prov)
        assert VR.G_BUNDLE_ADMITTED in _failed(_verify(release))


# =========================================================================== #
# the native producer inventory
# =========================================================================== #
class TestTheProducerInventory:
    def test_a_MISSING_bundle_partial_release_is_REFUSED(self, release):
        assert VR.G_TOPOLOGY in _failed(_verify(release, dirs=release["dirs"][:5]))

    def test_a_bundle_LYING_about_its_own_source_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        d = rel["dirs"][0]
        bp = os.path.join(d, VR.BUNDLE_FILE)
        doc = json.load(open(bp))
        doc["source"] = "go_bp"
        _write(bp, doc)
        rel["inventory"] = _inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"])
        assert VR.G_SOURCE in _failed(_verify(rel))

    def test_a_FORGED_inventory_that_does_not_match_disk_is_REFUSED(self, release):
        inv = json.load(open(release["inventory"]))
        inv["bundles"][0]["files"][VR.BUNDLE_FILE]["canonical_sha256"] = "0" * 64
        inv["release_id"] = R.content_sha256({k: v for k, v in inv.items() if k != "release_id"})
        _write(release["inventory"], inv)
        assert VR.G_INVENTORY_BYTES in _failed(_verify(release))

    def test_a_MISSING_release_id_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        rel["inventory"] = _inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"],
                                      release_id=False)
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(rel))

    def test_an_inventory_release_id_that_does_not_rederive_is_REFUSED(self, release):
        inv = json.load(open(release["inventory"]))
        inv["release_id"] = "f" * 64
        _write(release["inventory"], inv)
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(release))

    def test_an_inventory_OMITTING_a_native_field_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        rel["inventory"] = _inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"],
                                      drop="topology")
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(rel))

    def test_an_inventory_with_an_EXTRA_non_native_field_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        rel["inventory"] = _inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"],
                                      extra=True)
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(rel))

    def test_an_inventory_topology_that_disagrees_with_the_release_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        rel["inventory"] = _inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"],
                                      conds=["Rest", "Stim8hr", "OTHER"])
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(rel))

    def test_a_wrong_env_lock_sha_in_the_inventory_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        rel["inventory"] = _inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"],
                                      env_lock_sha="d" * 64)
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(rel))

    def test_an_inventory_that_is_NOT_pending_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        rel["inventory"] = _inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"],
                                      status="admit")
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(rel))

    def test_a_MISSING_inventory_is_fail_closed(self, release):
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(release, inv=None))

    @pytest.mark.skipif(
        not os.path.exists("/home/tcelab/worktrees/spot-stage2-w3/02_geneskew/"
                           "analysis/direct/pathway_release.py"),
        reason="the real pathway producer is not checked out")
    def test_the_REAL_pathway_producer_inventory_is_accepted(self, tmp_path):
        import importlib.util
        import sys
        w3 = "/home/tcelab/worktrees/spot-stage2-w3/02_geneskew"
        sys.path.insert(0, os.path.join(w3, "analysis"))
        rel = _build(tmp_path)
        spec = importlib.util.spec_from_file_location(
            "direct.pathway_release", os.path.join(w3, "analysis/direct/pathway_release.py"))
        try:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.build_release(rel["dirs"], rel["root"], conditions=CONDITIONS, sources=SOURCES,
                              write=True)
        except Exception as exc:                            # noqa: BLE001
            pytest.skip(f"real producer not importable in isolation: {exc}")
        inv = os.path.join(rel["root"], mod.RELEASE_FILENAME)
        res = _verify(rel, inv=inv)
        assert res["verdict"] == VR.ADMIT, sorted(_failed(res))


# =========================================================================== #
# the integration adapter contract (finding 6 / W1 coordination)
# =========================================================================== #
class TestTheIntegrationAdapterContract:
    def test_report_id_recomputes_under_the_integration_canonical_rule(self, release):
        body = _verify(release)["body"]
        canon = json.dumps({k: v for k, v in body.items() if k != "report_id"},
                           sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        assert hashlib.sha256(canon.encode()).hexdigest() == body["report_id"]

    def test_the_verdict_token_is_one_the_adapter_maps(self, release):
        assert _verify(release)["body"]["verdict"] in ("ADMIT", "REFUSE", "REJECT")

    def test_the_schema_stays_lane_specific_not_temporal(self, release):
        body = _verify(release)["body"]
        assert body["schema_version"] == "spot.stage02_pathway_arm_external_admission.v1"
        assert body["schema_version"] != "spot.stage02_temporal_arm_external_admission.v1"


# =========================================================================== #
# THE CLI
# =========================================================================== #
class TestTheCLI:
    def _argv(self, rel, dirs=None, out=None):
        argv = []
        for d in (dirs if dirs is not None else rel["dirs"]):
            argv += ["--bundle", d]
        for rep in rel["reports"]:
            argv += ["--bundle-report", rep]
        argv += ["--release", rel["release"], "--inventory", rel["inventory"], "--out", out]
        return argv

    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as e:
            VR.main(["--help"])
        assert e.value.code == 0
        assert "inventory" in capsys.readouterr().out

    def test_honest_release_exits_zero_and_persists_the_envelope(self, release, tmp_path):
        out = str(tmp_path / VR.ADMISSION_FILE)
        assert VR.main(self._argv(release, out=out)) == 0
        body = json.load(open(out))
        assert body["verdict"] == "ADMIT" and len(body["report_id"]) == 64
        assert body["schema_version"] == "spot.stage02_pathway_arm_external_admission.v1"

    def test_a_partial_release_exits_NONZERO(self, release, tmp_path):
        out = str(tmp_path / VR.ADMISSION_FILE)
        assert VR.main(self._argv(release, dirs=release["dirs"][:4], out=out)) == 1
        assert json.load(open(out))["verdict"] == "REFUSE"
