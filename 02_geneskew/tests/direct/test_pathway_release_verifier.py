"""The independent pathway RELEASE verifier + CLI (pathway_arm_external_admission.json).

An envelope over the (condition x source) bundles, anchored OUTWARD: the universe AND the
scorer/method pins to the Stage-1 v3 release, each cell's local validity to its INDEPENDENT
per-bundle report (one to one, exact gate inventory, attested bytes), the two gene-set source
artifacts pinned, the solver lock to a constant, and the PRODUCER inventory in its REAL native
shape (release_inventory.py: un-admitted verdict/admitted/self_admitted/verifier_id, solver_lock
+ stage1_binding, context/relative_dir entries — NOT env_lock/topology), release_id mandatory
and byte-bound. A test invokes the REAL release_inventory.build so the shape is not assumed.
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
SOURCES = ["reactome", "go_bp"]
RELEASE_SOURCES = ["GO-BP", "Reactome"]             # display-case, as selector.pathway_sources
LOCK = VR.STAGE2_SOLVER_LOCK_SHA256
SCORER_CANON = "v" * 64
METHOD = "stage1-continuous-v3.0.1"
SCORER_VIEW = "5" * 64
CODE_IDENTITY = {"lane": "production", "code_tree_sha256": "c" * 64}
W3C = "/home/tcelab/worktrees/spot-stage2-w3c/02_geneskew"

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
    rid = full[:VR.RUN_ID_LEN]
    d = os.path.join(root, rid)
    _write(os.path.join(d, VR.PROVENANCE_FILE),
           {"pathway_run_id": rid, "pathway_run_sha256": full, "run_binding": binding})
    # the REAL native pathway arm_bundle shape (bundle_normalize contract)
    _write(os.path.join(d, VR.BUNDLE_FILE),
           {"schema_version": "spot.stage02_pathway_arm_bundle.v1", "pathway_run_id": rid,
            "condition": cond, "source": doc_source or src,
            "arms": [{"pathway_arm_key": f"PROG|increase|{cond}|{src}",
                      "records_sha256": binding["records_sha256"]}]})
    _write(os.path.join(d, VR.GENE_SETS_FILE), _gene_doc(gene_tag or src))
    _write(os.path.join(d, "signature_ref.json"), {"condition": cond, "source": src, "ref": rid})
    _write(os.path.join(d, "convergence.json"), {"condition": cond, "source": src, "conv": rid})
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


def _report(path, d, *, verdict="admit", n_failed=0, gates=None, run_ids=None, tamper=False):
    rid = _run_id(d)
    gate_list = BUNDLE_GATES if gates is None else gates
    att = {rid: {VR.PROVENANCE_FILE: _raw(os.path.join(d, VR.PROVENANCE_FILE)),
                 VR.GENE_SETS_FILE: _raw(os.path.join(d, VR.GENE_SETS_FILE))}}
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


def _files_of(d):
    """Every file in a bundle dir, keyed by relpath, {raw_sha256, canonical for json} — exactly
    as release_inventory._files_of names them."""
    out = {}
    for base, _dirs, names in os.walk(d):
        for name in names:
            p = os.path.join(base, name)
            rel = os.path.relpath(p, d).replace(os.sep, "/")
            entry = {"raw_sha256": _raw(p)}
            if rel.endswith(".json"):
                entry["canonical_sha256"] = R.content_sha256(json.load(open(p)))
            out[rel] = entry
    return out


def _native_inventory(path, dirs, root, *, status="pending", verdict=VR.VERDICT_PENDING,
                      admitted=False, self_admitted=False, verifier_id=None, solver_lock=LOCK,
                      s1_scorer=SCORER_CANON, s1_conds=CONDITIONS, schema=VR.RELEASE_SCHEMA,
                      lane="pathway", drop=None, extra=False, release_id=True):
    """The REAL release_inventory.build native shape, hand-built for attack isolation."""
    entries, arm_keys = [], []
    for d in dirs:
        doc = json.load(open(os.path.join(d, VR.BUNDLE_FILE)))
        keys = [a["pathway_arm_key"] for a in doc["arms"]]
        arm_keys += keys
        ctx = {"condition": doc["condition"], "gene_set_source": doc["source"]}
        entries.append({"bundle_id": doc["pathway_run_id"], "context": ctx,
                        "relative_dir": os.path.relpath(d, root).replace(os.sep, "/"),
                        "n_arms": len(doc["arms"]), "files": _files_of(d), "rankings": {}})
    body = {"schema_version": schema, "lane": lane,
            "release_id_rule": "sha256(canonical JSON excluding the id and admission fields)",
            "n_bundles": len(entries), "n_logical_arms": len(arm_keys),
            "arm_keys": sorted(arm_keys),
            "bundles": sorted(entries, key=lambda e: e["bundle_id"]),
            "stage1_binding": {"release_canonical_sha256": "rc" * 32,
                               "registry_scorer_view_canonical_sha256": s1_scorer,
                               "admitted_programs": ["PROG"], "conditions": list(s1_conds)},
            "solver_lock_sha256": solver_lock, "producer_commit": "cafe" * 10,
            "independent_verifier_commit": None,
            "external_admission": {"status": status}}
    doc = dict(body, verdict=verdict, admitted=admitted, self_admitted=self_admitted,
               verifier_id=verifier_id)
    if drop:
        doc.pop(drop, None)
    if extra:
        doc["surprise_field"] = "not native"
    if release_id:
        doc["release_id"] = R.content_sha256(doc)
    _write(path, doc)
    return path


def _build(tmp, **bundle_kw):
    conds = bundle_kw.pop("conds", CONDITIONS)
    srcs = bundle_kw.pop("srcs", SOURCES)
    root = str(tmp / "pathway")
    dirs = [_bundle(root, c, s, **bundle_kw) for c in conds for s in srcs]
    return {
        "root": root, "dirs": dirs, "tmp": tmp,
        "release": _release_file(str(tmp / "stage01_v3_release.json")),
        "inventory": _native_inventory(str(tmp / VR.RELEASE_FILE), dirs, root),
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
        rel = _build(tmp_path, gene_tag="shared")
        assert VR.G_GENE_SETS in _failed(_verify(rel))

    def test_a_source_whose_bundles_disagree_on_the_artifact_is_REFUSED(self, release):
        _write(os.path.join(release["dirs"][0], VR.GENE_SETS_FILE), _gene_doc("reactome-TAMPER"))
        assert VR.G_GENE_SETS in _failed(_verify(release))

    def test_a_MISSING_gene_set_file_is_REFUSED(self, release):
        os.remove(os.path.join(release["dirs"][0], VR.GENE_SETS_FILE))
        assert VR.G_GENE_SETS in _failed(_verify(release))

    def test_a_gene_set_the_report_never_attested_is_REFUSED(self, release):
        gs = os.path.join(release["dirs"][0], VR.GENE_SETS_FILE)
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
        d = release["dirs"][0]
        rid = _run_id(d)
        body = {"schema_version": VR.BUNDLE_REPORT_SCHEMA, "verifier_id": VR.BUNDLE_VERIFIER_ID,
                "generator_is_not_verifier": True, "fail_closed": True, "n_bundles": 1,
                "n_conditions": 1, "run_ids": [rid],
                "bound_artifacts": {rid: {VR.PROVENANCE_FILE: _raw(os.path.join(
                    d, VR.PROVENANCE_FILE)), VR.GENE_SETS_FILE: _raw(os.path.join(
                        d, VR.GENE_SETS_FILE))}}, "verdict": "admit", "n_failed": 0,
                "gates": [{"check": g, "status": "pass"} for g in BUNDLE_GATES[:-1]]
                + [{"check": BUNDLE_GATES[-1], "status": "fail"}]}
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
        assert VR.G_BUNDLE_ADMITTED in _failed(
            _verify(release, reports=[forged] + release["reports"][1:]))

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
# the REAL native producer inventory (release_inventory.py)
# =========================================================================== #
class TestTheNativeProducerInventory:
    def test_a_MISSING_bundle_partial_release_is_REFUSED(self, release):
        assert VR.G_TOPOLOGY in _failed(_verify(release, dirs=release["dirs"][:5]))

    def test_a_bundle_LYING_about_its_own_source_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        d = rel["dirs"][0]
        bp = os.path.join(d, VR.BUNDLE_FILE)
        doc = json.load(open(bp))
        doc["source"] = "go_bp"
        _write(bp, doc)
        rel["inventory"] = _native_inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"])
        assert VR.G_SOURCE in _failed(_verify(rel))

    def test_a_FORGED_inventory_that_does_not_match_disk_is_REFUSED(self, release):
        inv = json.load(open(release["inventory"]))
        first = inv["bundles"][0]
        first["files"]["arm_bundle.json"]["canonical_sha256"] = "0" * 64
        inv["release_id"] = R.content_sha256({k: v for k, v in inv.items() if k != "release_id"})
        _write(release["inventory"], inv)
        assert VR.G_INVENTORY_BYTES in _failed(_verify(release))

    def test_a_MISSING_release_id_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        rel["inventory"] = _native_inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"],
                                             release_id=False)
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(rel))

    def test_an_inventory_release_id_that_does_not_rederive_is_REFUSED(self, release):
        inv = json.load(open(release["inventory"]))
        inv["release_id"] = "f" * 64
        _write(release["inventory"], inv)
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(release))

    def test_an_inventory_OMITTING_a_native_field_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        rel["inventory"] = _native_inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"],
                                             drop="stage1_binding")
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(rel))

    def test_an_inventory_with_an_EXTRA_non_native_field_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        rel["inventory"] = _native_inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"],
                                             extra=True)
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(rel))

    def test_a_SELF_ADMITTED_inventory_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        rel["inventory"] = _native_inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"],
                                             admitted=True, verdict="admitted",
                                             verifier_id="spot.stage02.pathway.arm.independent_verifier.v1")
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(rel))

    def test_a_wrong_solver_lock_sha_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        rel["inventory"] = _native_inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"],
                                             solver_lock="d" * 64)
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(rel))

    def test_a_stage1_binding_scorer_that_is_not_the_release_pin_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        rel["inventory"] = _native_inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"],
                                             s1_scorer="7" * 64)
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(rel))

    def test_a_stage1_binding_conditions_mismatch_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        rel["inventory"] = _native_inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"],
                                             s1_conds=["Rest", "Stim8hr", "OTHER"])
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(rel))

    def test_a_MISSING_inventory_is_fail_closed(self, release):
        assert VR.G_INVENTORY_PRESENT in _failed(_verify(release, inv=None))

    @pytest.mark.skipif(
        not os.path.exists(os.path.join(W3C, "analysis/direct/release_inventory.py")),
        reason="the real release_inventory producer is not checked out")
    def test_the_REAL_release_inventory_build_is_accepted(self, tmp_path):
        # invoke the REAL producer in a SUBPROCESS (PYTHONPATH=w3c) so its `direct` package never
        # pollutes this process's module resolution — the shape is validated, not assumed.
        import subprocess
        import sys
        rel = _build(tmp_path)
        inv = os.path.join(str(tmp_path), "real_pathway_arm_release.json")
        script = (
            "import json,sys\n"
            "from direct import release_inventory as RI\n"
            "dirs=sys.argv[3:]\n"
            "stage1={'release_canonical_sha256':'rc'*32,"
            f"'registry_scorer_view_canonical_sha256':{SCORER_CANON!r},"
            "'admitted_programs':['PROG'],'conditions':" + repr(CONDITIONS) + "}\n"
            "doc=RI.build(lane='pathway',bundle_dirs=dirs,root=sys.argv[1],expect_bundles=6,"
            f"stage1=stage1,env_lock_sha256={LOCK!r},producer_commit='abc123',verifier_commit=None)\n"
            "json.dump(doc,open(sys.argv[2],'w'),indent=2,sort_keys=True)\n")
        p = subprocess.run([sys.executable, "-c", script, rel["root"], inv, *rel["dirs"]],
                           env={**os.environ, "PYTHONPATH": os.path.join(W3C, "analysis")},
                           capture_output=True, text=True)
        if p.returncode != 0:
            pytest.skip(f"real producer not runnable in isolation: {p.stderr[-400:]}")
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
