"""The independent pathway RELEASE verifier + CLI (pathway_arm_external_admission.json).

An envelope over the (condition x source) bundles that is anchored OUTWARD — the universe to the
Stage-1 v3 release, each cell's local validity to its INDEPENDENT per-bundle report, the solver
lock to a pinned constant, the producer inventory byte-bound and re-derived. The fixtures build
the REAL producer shapes (a display-cased Stage-1 release selector, a pathway_release.py-shaped
PENDING inventory, signature_matrix_verification.v1 reports), so the tests attack production
bytes, not a shape the verifier is free to define.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest
from direct import verify_pathway_release as VR
from direct import verify_rules as R

CONDITIONS = ["Rest", "Stim8hr", "Stim48hr"]
SOURCES = ["reactome", "go_bp"]                     # lowercase ids, as the bundles carry them
RELEASE_SOURCES = ["GO-BP", "Reactome"]             # display-case, as selector.pathway_sources
LOCK = VR.STAGE2_SOLVER_LOCK_SHA256
STAGE1 = {"registry_raw_sha256": "a" * 64, "method_version": "stage1-continuous-v3.0.1"}
SCORER_VIEW = "5" * 64
CODE_IDENTITY = {"lane": "production", "code_tree_sha256": "c" * 64}


def _write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _hashes(path):
    with open(path, "rb") as fh:
        raw = hashlib.sha256(fh.read()).hexdigest()
    with open(path) as fh:
        return {"raw_sha256": raw, "canonical_sha256": R.content_sha256(json.load(fh))}


def _bundle(root, cond, src, *, scorer=SCORER_VIEW, code=None, stage1=None,
            release_scorer="r" * 64, env_lock=LOCK, records=None, doc_source=None,
            doc_condition=None):
    """One well-formed bundle dir with a re-derivable run id. Bundle source is lowercase."""
    binding = {
        "condition": cond, "source": src,
        "scorer_view_sha256": scorer,
        "release_scorer_view_canonical_sha256": release_scorer,
        "code_identity": code if code is not None else CODE_IDENTITY,
        "stage1_release_hashes": stage1 if stage1 is not None else STAGE1,
        "stage1_release_kind": "fixture",
        "environment_lock": {"sha256": env_lock, "status": "locked"},
        "records_sha256": records or hashlib.sha256(f"{cond}:{src}".encode()).hexdigest(),
    }
    full = R.content_sha256(binding)
    d = os.path.join(root, full[:VR.RUN_ID_LEN])
    prov = {"pathway_run_id": full[:VR.RUN_ID_LEN], "pathway_run_sha256": full,
            "run_binding": binding}
    doc = {"condition": doc_condition or cond, "source": doc_source or src,
           "bundle_id": full[:VR.RUN_ID_LEN], "arms": [],
           "schema_version": "spot.stage02_pathway_arm.v1"}
    _write(os.path.join(d, VR.PROVENANCE_FILE), prov)
    _write(os.path.join(d, VR.BUNDLE_FILE), doc)
    return d


def _run_id(d):
    prov = json.load(open(os.path.join(d, VR.PROVENANCE_FILE)))
    return R.content_sha256(prov["run_binding"])[:VR.RUN_ID_LEN]


def _release_file(path, conds=CONDITIONS, srcs=RELEASE_SOURCES):
    _write(path, {"schema": VR.STAGE1_RELEASE_SCHEMA, "method_version": STAGE1["method_version"],
                  "selector": {"conditions": list(conds), "pathway_sources": list(srcs)}})
    return path


def _inventory(path, dirs, root, *, status="pending",
               required_verifier_id=VR.VERIFIER_ID, schema=VR.RELEASE_SCHEMA, generic=False):
    """A pathway_release.py-shaped PENDING inventory over the bundle dirs."""
    entries = []
    for d in dirs:
        prov = json.load(open(os.path.join(d, VR.PROVENANCE_FILE)))
        b = prov["run_binding"]
        files = {VR.BUNDLE_FILE: _hashes(os.path.join(d, VR.BUNDLE_FILE)),
                 VR.PROVENANCE_FILE: _hashes(os.path.join(d, VR.PROVENANCE_FILE))}
        entry = {"bundle_key": f"{b['condition']}|{b['source']}",
                 "bundle_id": prov["pathway_run_id"],
                 "relative_dir": os.path.relpath(d, root).replace(os.sep, "/"),
                 "n_arms": 0, "arm_keys": [], "files": files, "rankings": {}}
        if generic:                                 # the GENERIC release_inventory entry shape
            entry["context"] = {"condition": b["condition"], "gene_set_source": b["source"]}
        else:                                       # the pathway producer's flat shape
            entry["condition"], entry["source"] = b["condition"], b["source"]
        entries.append(entry)
    inv = {"schema_version": schema, "lane": "pathway",
           "release_id_rule": "sha256(canonical JSON excluding release_id)",
           "required_verifier_id": required_verifier_id,
           "n_bundles": len(entries), "bundles": sorted(entries, key=lambda e: e["bundle_key"]),
           "external_admission": {"status": status,
                                  "required_verifier_id": required_verifier_id,
                                  "required_report_schema_version":
                                      "spot.stage02_temporal_arm_external_admission.v1"}}
    inv["release_id"] = R.content_sha256(inv)
    _write(path, inv)
    return path


def _report(path, run_id, *, verdict="admit", n_failed=0, gates=None, tamper=False):
    """An INDEPENDENT signature_matrix_verification.v1 report for one bundle."""
    body = {"schema_version": VR.BUNDLE_REPORT_SCHEMA, "verifier_id": VR.BUNDLE_VERIFIER_ID,
            "generator_is_not_verifier": True, "fail_closed": True,
            "n_bundles": 1, "n_conditions": 1, "run_ids": [run_id],
            "verdict": verdict, "n_failed": n_failed,
            "gates": gates if gates is not None
            else [{"check": "V1", "status": "pass"}, {"check": "V_IDENTITY", "status": "pass"}]}
    sha = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if tamper:
        body["gates"].append({"check": "SNUCK_IN", "status": "pass"})   # bytes != sealed sha
    _write(path, dict(body, report_sha256=sha))
    return path


def _reports(rep_dir, dirs):
    return [_report(os.path.join(rep_dir, f"r{i}.json"), _run_id(d))
            for i, d in enumerate(dirs)]


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
        assert body["verifier_id"] == "spot.stage02.pathway.arm.independent_verifier.v1"
        assert "temporal" not in body["schema_version"]
        assert body["n_bundles"] == 6 and body["n_failed"] == 0 and body["verdict"] == "ADMIT"

    def test_the_display_cased_release_sources_case_fold_to_the_bundle_ids(self, release):
        # release selector says GO-BP / Reactome; the bundles say go_bp / reactome
        assert json.load(open(release["release"]))["selector"]["pathway_sources"] == RELEASE_SOURCES
        assert _verify(release)["verdict"] == VR.ADMIT

    def test_the_envelope_report_id_is_the_integration_self_hash(self, release):
        body = _verify(release)["body"]
        rest = {k: v for k, v in body.items() if k != VR.REPORT_ID_FIELD}
        assert body[VR.REPORT_ID_FIELD] == R.content_sha256(rest)
        assert len(body[VR.REPORT_ID_FIELD]) == 64

    def test_the_envelope_binds_the_producer_release_and_carries_the_gate_inventory(self, release):
        body = _verify(release)["body"]
        inv = json.load(open(release["inventory"]))
        assert body["binds"]["producer_release_id"] == inv["release_id"]
        assert body["binds"]["producer_release_raw_sha256"] == \
            hashlib.sha256(open(release["inventory"], "rb").read()).hexdigest()
        assert set(body["gate_inventory"]) == set(VR.GATE_INVENTORY)
        assert {g["check"] for g in body["gates"]} == set(VR.GATE_INVENTORY)

    def test_the_generic_context_relative_dir_inventory_shape_is_accepted(self, tmp_path):
        rel = _build(tmp_path, generic_inv=True)
        assert "context" in json.load(open(rel["inventory"]))["bundles"][0]
        assert _verify(rel)["verdict"] == VR.ADMIT, sorted(_failed(_verify(rel)))


# =========================================================================== #
# FINDING 1 — the universe is anchored to the release, not the bundles
# =========================================================================== #
class TestTheAuthoritativeUniverse:
    def test_a_wrong_but_3x2_universe_is_REFUSED(self, tmp_path):
        # a fully self-consistent Foo/Bar/Baz x X/Y forgery: 3x2, but not the release's grid
        rel = _build(tmp_path, conds=["Foo", "Bar", "Baz"], srcs=["x", "y"])
        rel["release"] = _release_file(str(tmp_path / "rel.json"))   # authoritative: Rest/...
        res = _verify(rel)
        assert res["verdict"] == VR.REFUSE and VR.G_TOPOLOGY in _failed(res)

    def test_a_MISSING_release_anchor_is_fail_closed(self, release):
        res = _verify(release, release=None)
        assert res["verdict"] == VR.REFUSE and VR.G_RELEASE_ANCHOR in _failed(res)

    def test_a_release_with_the_WRONG_schema_is_REFUSED(self, release):
        rel = json.load(open(release["release"]))
        rel["schema"] = "spot.stage01_v3_release.WRONG"
        _write(release["release"], rel)
        res = _verify(release)
        assert res["verdict"] == VR.REFUSE and VR.G_RELEASE_ANCHOR in _failed(res)


# =========================================================================== #
# FINDING 2 & 3 — all-null bindings, null run id, distinctness
# =========================================================================== #
class TestTheReleaseIdentity:
    def test_ALL_NULL_bindings_do_not_pass_as_one_release(self, tmp_path):
        rel = _build(tmp_path, scorer=None, code=None, release_scorer=None, stage1=None,
                     env_lock=None)
        res = _verify(rel)
        assert res["verdict"] == VR.REFUSE and VR.G_ONE_RELEASE in _failed(res)

    def test_two_scorer_views_are_not_one_release(self, release):
        d = release["dirs"][0]
        # recompute the whole bundle with a different scorer view (its run id changes with it)
        rogue = _bundle(release["root"], "Rest", "reactome", scorer="7" * 64,
                        records=hashlib.sha256(b"rogue").hexdigest())
        dirs = [x for x in release["dirs"] if x != d] + [rogue]
        rel = dict(release, dirs=dirs)
        rel["inventory"] = _inventory(str(release["tmp"] / "i2.json"), dirs, release["root"])
        rel["reports"] = _reports(str(release["tmp"] / "v2"), dirs)
        res = _verify(rel)
        assert res["verdict"] == VR.REFUSE and VR.G_ONE_RELEASE in _failed(res)

    def test_a_swapped_off_pin_solver_lock_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path, env_lock="e" * 64)          # single-valued but NOT the pin
        res = _verify(rel)
        assert res["verdict"] == VR.REFUSE and VR.G_ONE_RELEASE in _failed(res)

    def test_a_NULL_run_id_is_REFUSED(self, release):
        d = release["dirs"][0]
        prov = json.load(open(os.path.join(d, VR.PROVENANCE_FILE)))
        prov["pathway_run_id"] = None
        _write(os.path.join(d, VR.PROVENANCE_FILE), prov)
        res = _verify(release)
        assert res["verdict"] == VR.REFUSE and VR.G_REOPEN in _failed(res)


# =========================================================================== #
# FINDING 4 — every cell must carry an INDEPENDENT admitting report
# =========================================================================== #
class TestEveryCellIsIndependentlyAdmitted:
    def test_NO_per_bundle_reports_is_fail_closed(self, release):
        res = _verify(release, reports=[])
        assert res["verdict"] == VR.REFUSE and VR.G_BUNDLE_ADMITTED in _failed(res)

    def test_a_REJECTING_per_bundle_report_blocks_the_release(self, release):
        _report(release["reports"][0], _run_id(release["dirs"][0]),
                verdict="reject", n_failed=1,
                gates=[{"check": "V_IDENTITY", "status": "fail"}])
        res = _verify(release)
        assert res["verdict"] == VR.REFUSE and VR.G_BUNDLE_ADMITTED in _failed(res)

    def test_a_report_with_a_single_FAILED_gate_blocks_the_release(self, release):
        _report(release["reports"][0], _run_id(release["dirs"][0]),
                gates=[{"check": "V1", "status": "pass"}, {"check": "V6", "status": "fail"}])
        res = _verify(release)
        assert res["verdict"] == VR.REFUSE and VR.G_BUNDLE_ADMITTED in _failed(res)

    def test_a_TAMPERED_report_whose_self_hash_no_longer_holds_is_REFUSED(self, release):
        _report(release["reports"][0], _run_id(release["dirs"][0]), tamper=True)
        res = _verify(release)
        assert res["verdict"] == VR.REFUSE and VR.G_BUNDLE_ADMITTED in _failed(res)

    def test_a_FORGED_producer_verification_is_not_an_independent_report(self, release):
        # the producer's own pathway_verification.json, dressed as ADMIT, is NOT admitted
        forged = os.path.join(str(release["tmp"]), "producer_verification.json")
        _write(forged, {"schema_version": "spot.stage02_pathway_verification.v1",
                        "verdict": "admit", "n_failed": 0, "run_ids": [_run_id(release["dirs"][0])],
                        "gates": [{"check": "x", "status": "pass"}], "report_sha256": "0" * 64})
        reports = [forged] + release["reports"][1:]
        res = _verify(release, reports=reports)
        assert res["verdict"] == VR.REFUSE and VR.G_BUNDLE_ADMITTED in _failed(res)

    def test_mutating_a_bundle_AFTER_its_report_unbinds_the_report(self, release):
        # reseal a bundle's run id (ranking change): the report still names the OLD id -> the
        # cell no longer carries an admitting report, and the inventory bytes no longer match
        d = release["dirs"][0]
        pp = os.path.join(d, VR.PROVENANCE_FILE)
        prov = json.load(open(pp))
        prov["run_binding"]["records_sha256"] = "8" * 64
        full = R.content_sha256(prov["run_binding"])
        prov["pathway_run_id"], prov["pathway_run_sha256"] = full[:VR.RUN_ID_LEN], full
        _write(pp, prov)
        res = _verify(release)
        assert res["verdict"] == VR.REFUSE and VR.G_BUNDLE_ADMITTED in _failed(res)


# =========================================================================== #
# FINDING 5 — the real producer inventory shape, byte-bound
# =========================================================================== #
class TestTheProducerInventory:
    def test_a_MISSING_bundle_partial_release_is_REFUSED(self, release):
        res = _verify(release, dirs=release["dirs"][:5])
        assert res["verdict"] == VR.REFUSE and VR.G_TOPOLOGY in _failed(res)

    def test_an_EXTRA_duplicate_cell_is_REFUSED(self, release):
        dup = _bundle(release["root"], "Rest", "reactome",
                      records=hashlib.sha256(b"dup").hexdigest())
        res = _verify(release, dirs=release["dirs"] + [dup])
        assert res["verdict"] == VR.REFUSE and VR.G_TOPOLOGY in _failed(res)

    def test_a_bundle_LYING_about_its_own_source_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        d = rel["dirs"][0]
        bp = os.path.join(d, VR.BUNDLE_FILE)
        doc = json.load(open(bp))
        doc["source"] = "go_bp"                             # doc lies; run_binding still reactome
        _write(bp, doc)
        rel["inventory"] = _inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"])
        res = _verify(rel)
        assert res["verdict"] == VR.REFUSE and VR.G_SOURCE in _failed(res)

    def test_a_FORGED_inventory_that_does_not_match_disk_is_REFUSED(self, release):
        inv = json.load(open(release["inventory"]))
        inv["bundles"][0]["files"][VR.BUNDLE_FILE]["canonical_sha256"] = "0" * 64
        inv["release_id"] = R.content_sha256({k: v for k, v in inv.items() if k != "release_id"})
        _write(release["inventory"], inv)
        res = _verify(release)
        assert res["verdict"] == VR.REFUSE and VR.G_INVENTORY_BYTES in _failed(res)

    def test_an_inventory_whose_release_id_does_not_rederive_is_REFUSED(self, release):
        inv = json.load(open(release["inventory"]))
        inv["release_id"] = "f" * 64                        # a resealed-but-not-recomputed id
        _write(release["inventory"], inv)
        res = _verify(release)
        assert res["verdict"] == VR.REFUSE and VR.G_INVENTORY_PRESENT in _failed(res)

    def test_an_inventory_that_is_NOT_pending_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        rel["inventory"] = _inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"],
                                      status="admit")
        res = _verify(rel)
        assert res["verdict"] == VR.REFUSE and VR.G_INVENTORY_PRESENT in _failed(res)

    def test_an_inventory_requiring_ANOTHER_verifier_is_REFUSED(self, tmp_path):
        rel = _build(tmp_path)
        rel["inventory"] = _inventory(str(tmp_path / "i.json"), rel["dirs"], rel["root"],
                                      required_verifier_id="some.other.verifier.v1")
        res = _verify(rel)
        assert res["verdict"] == VR.REFUSE and VR.G_INVENTORY_PRESENT in _failed(res)

    def test_a_MISSING_inventory_is_fail_closed(self, release):
        res = _verify(release, inv=None)
        assert res["verdict"] == VR.REFUSE and VR.G_INVENTORY_PRESENT in _failed(res)

    @pytest.mark.skipif(
        not os.path.exists("/home/tcelab/worktrees/spot-stage2-w3/02_geneskew/"
                           "analysis/direct/pathway_release.py"),
        reason="the real pathway producer is not checked out")
    def test_the_REAL_pathway_producer_inventory_is_accepted(self, tmp_path):
        import importlib.util
        import sys
        w3 = "/home/tcelab/worktrees/spot-stage2-w3/02_geneskew"
        sys.path.insert(0, os.path.join(w3, "analysis"))
        spec = importlib.util.spec_from_file_location(
            "direct.pathway_release", os.path.join(w3, "analysis/direct/pathway_release.py"))
        # the producer builds the inventory over MY bundle dirs; my verifier then re-derives it
        rel = _build(tmp_path)
        try:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as exc:                            # noqa: BLE001
            pytest.skip(f"real producer not importable in isolation: {exc}")
        mod.build_release(rel["dirs"], rel["root"], conditions=CONDITIONS, sources=SOURCES,
                          write=True)
        inv = os.path.join(rel["root"], mod.RELEASE_FILENAME)
        res = _verify(rel, inv=inv)
        assert res["verdict"] == VR.ADMIT, sorted(_failed(res))


# =========================================================================== #
# FINDING 6 — the integration adapter can consume the envelope
# =========================================================================== #
class TestTheIntegrationAdapterContract:
    def test_report_id_recomputes_under_the_integration_canonical_rule(self, release):
        body = _verify(release)["body"]
        # verify_release_envelope.self_hash(doc, "report_id"): canonical JSON minus report_id
        canon = json.dumps({k: v for k, v in body.items() if k != "report_id"},
                           sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        assert hashlib.sha256(canon.encode()).hexdigest() == body["report_id"]

    def test_the_verdict_token_is_one_the_adapter_maps(self, release):
        # NATIVE_TO_DISPOSITION accepts exactly ADMIT / REFUSE / REJECT (byte-exact)
        assert _verify(release)["body"]["verdict"] in ("ADMIT", "REFUSE", "REJECT")

    def test_the_schema_stays_lane_specific_not_temporal(self, release):
        # the W1 coordination item: the schema is pathway-specific, so a temporal envelope can
        # never stand in for a pathway release. Integration must ADD this to its accepted set.
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
        code = VR.main(self._argv(release, out=out))
        assert code == 0
        body = json.load(open(out))
        assert body["verdict"] == "ADMIT"
        assert body["schema_version"] == "spot.stage02_pathway_arm_external_admission.v1"
        assert len(body["report_id"]) == 64

    def test_a_partial_release_exits_NONZERO(self, release, tmp_path):
        out = str(tmp_path / VR.ADMISSION_FILE)
        assert VR.main(self._argv(release, dirs=release["dirs"][:4], out=out)) == 1
        assert json.load(open(out))["verdict"] == "REFUSE"
