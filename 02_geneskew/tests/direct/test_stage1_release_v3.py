"""Direct loads the AUTHORITATIVE Stage-1 generic release — natively, and provably.

BLOCKER 2. Stage-1 `55899ac` ships `spot.stage01_v3_release.v1`: a `schema`, a `selector` and
`components`. Direct accepted only `spot.stage01_release_manifest.v1` with an `artifacts` map,
so it refused the real release on sight:

    TrustError Stage-1 release manifest: schema_version must be
    'spot.stage01_release_manifest.v1'

Behind that refusal sat a second seam, and it is the one that matters scientifically: the
PRIMARY v3 registry does not carry `base_portable`. Only the executable Stage-2 registry view
does. So Direct must bind and load the VIEW — and REFUSE the primary registry as a stand-in,
by name, rather than silently reading a registry that cannot say which programs may carry a
reusable arm at all.

The class below marked `TestTheRealStage1Release` runs against the genuine bytes of 55899ac,
staged out of git. It is skipped — never quietly passed — when that ref is not fetched.
"""
from __future__ import annotations

import json
import os
import subprocess

import fixtures_v3_release as V3
import pytest
from direct import scorer_view, trust
from direct import stage1_release_v3 as rel

# The frozen Stage-1 pins. Re-derived by the loader from bytes; asserted here so a drift in
# either side is a loud test failure rather than a quiet re-attribution.
REAL_SELF_HASH = "9bc851709595adb0953a3affffa8c2bbb1fd8355112fbd9565b4b97deb29866d"
REAL_SCORER_VIEW = "5d1d8c362ee55dba048c8b5d6718cffe4525acbcda230d503f4899433c052a0c"
REAL_SCORER_PROJECTION = "008c1da121a1ea3b08871f1bc0339b120d5dc9b46d01619768eebd046331bd85"
REAL_COMMIT = "55899ac5fb780cdbcc638092fde7a53478f92070"
REAL_ADMITTED = ["cd4_ctl_like", "diff_activated", "diff_checkpoint", "diff_memory",
                 "diff_naive", "tfh_like", "th17_like", "th1_like", "th2_like",
                 "treg_like"]
REAL_CONDITIONS = ["Rest", "Stim8hr", "Stim48hr"]

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _stage_real_release(root: str) -> str:
    """Materialise the genuine 55899ac release + components into a staged root."""
    release_rel = "01_programs/analysis/stage2_bridge/release/stage01_v3_release.json"
    try:
        blob = subprocess.run(["git", "-C", REPO, "show", f"{REAL_COMMIT}:{release_rel}"],
                              capture_output=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip(f"Stage-1 {REAL_COMMIT[:7]} is not fetched in this worktree")

    dest = os.path.join(root, release_rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(blob)

    release = json.loads(blob)
    for comp in release["components"].values():
        path = comp.get("path")
        if not path:
            continue                       # declared, not served (the scores parquet)
        out = os.path.join(root, path)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        got = subprocess.run(["git", "-C", REPO, "show", f"{REAL_COMMIT}:{path}"],
                             capture_output=True, check=True).stdout
        with open(out, "wb") as fh:
            fh.write(got)
    return dest


class TestTheRealStage1Release:
    """The bytes Stage-1 actually froze. Nothing here is a fixture."""

    @pytest.fixture
    def loaded(self, tmp_path):
        root = str(tmp_path / "staged")
        path = _stage_real_release(root)
        return rel.load(path, root=root, lane="production")

    def test_the_authoritative_v3_release_LOADS(self, loaded):
        assert loaded.kind == "production"
        assert loaded.method_version == "stage1-continuous-v3.0.1"

    def test_the_release_SELF_HASH_is_re_derived_from_its_own_bytes(self, loaded):
        assert loaded.hashes["release_self_sha256"] == REAL_SELF_HASH

    def test_the_admitted_set_is_DERIVED_from_base_portable_not_copied(self, loaded):
        # ten programs, and Th9 is not one of them — because the VIEW says it is not
        # portable, not because anything wrote down "10"
        assert list(loaded.admitted_programs) == sorted(REAL_ADMITTED)
        assert "th9_like" not in loaded.admitted_programs
        assert loaded.scorer["excluded_program_ids"] == ["th9_like"]
        assert len(loaded.admitted_programs) == 10

    def test_the_derived_set_AGREES_with_the_release_selector(self, loaded):
        assert loaded.scorer["selector_agrees"] is True
        assert sorted(loaded.scorer["selector_admitted_programs"]) == sorted(REAL_ADMITTED)

    def test_the_scorer_view_and_projection_hashes_are_BOUND(self, loaded):
        assert loaded.hashes["registry_scorer_view_canonical_sha256"] == REAL_SCORER_VIEW
        assert loaded.hashes["registry_scorer_projection_sha256"] == REAL_SCORER_PROJECTION

    def test_the_three_DIRECT_conditions_come_from_the_release(self, loaded):
        assert list(loaded.conditions) == REAL_CONDITIONS

    def test_the_scorer_view_drives_the_ADMITTED_SET_through_the_ordinary_view(self, loaded):
        # the same scorer_view.view() the producer calls, over the real release
        view = scorer_view.view(loaded)
        assert view["n_admitted_programs"] == 10
        assert view["excluded_program_ids"] == ["th9_like"]
        assert view["derived_from_legacy_registry"] is False

    def test_the_LEGACY_loader_still_refuses_it_which_is_why_this_module_exists(
            self, tmp_path):
        root = str(tmp_path / "staged")
        path = _stage_real_release(root)
        with pytest.raises(trust.TrustError):
            trust.load_production_release(path)


class TestTheLoaderProvesTheBytes:
    @pytest.fixture
    def staged(self, tmp_path):
        root = str(tmp_path / "root")
        return root, V3.stage_release(root)

    def test_a_clean_staged_release_loads(self, staged):
        root, path = staged
        r = rel.load(path, root=root, lane="production")
        assert list(r.admitted_programs) == sorted([V3.PROGRAM_A, V3.PROGRAM_B])
        assert V3.NONPORTABLE not in r.admitted_programs

    def test_a_release_whose_SELF_HASH_does_not_cover_its_bytes_is_REFUSED(self, tmp_path):
        root = str(tmp_path / "root")
        path = V3.stage_release(root, reseal=False)
        with pytest.raises(rel.Stage1ReleaseError) as exc:
            rel.load(path, root=root, lane="production")
        assert exc.value.reason == rel.REFUSE_SELF_HASH

    def test_a_TAMPERED_component_is_REFUSED_on_its_raw_bytes(self, staged):
        root, path = staged
        view = os.path.join(root, V3.VIEW_PATH)
        with open(view) as fh:
            doc = json.load(fh)
        doc["programs"][2]["base_portable"] = True          # admit the nonportable program
        with open(view, "w") as fh:
            json.dump(doc, fh, indent=1, sort_keys=True)
        with pytest.raises(rel.Stage1ReleaseError) as exc:
            rel.load(path, root=root, lane="production")
        assert exc.value.reason == rel.REFUSE_COMPONENT_RAW

    def test_a_component_the_release_does_not_ship_is_REFUSED(self, staged):
        root, path = staged
        os.remove(os.path.join(root, V3.VIEW_PATH))
        with pytest.raises(rel.Stage1ReleaseError) as exc:
            rel.load(path, root=root, lane="production")
        assert exc.value.reason == rel.REFUSE_COMPONENT_MISSING

    def test_a_component_path_may_not_ESCAPE_the_staged_root(self, staged):
        root, path = staged
        V3.rewrite(path, lambda r: r["components"]["stage2_registry_view"].update(
            {"path": "../../../etc/passwd"}))
        with pytest.raises(rel.Stage1ReleaseError) as exc:
            rel.load(path, root=root, lane="production")
        assert exc.value.reason == rel.REFUSE_PATH_ESCAPE


class TestThePrimaryRegistryMayNotStandInForTheScorerView:
    """The seam behind the schema refusal. A registry that cannot declare portability
    cannot decide which programs carry a reusable arm."""

    def test_pointing_the_view_component_at_the_PRIMARY_REGISTRY_is_REFUSED(self, tmp_path):
        root = str(tmp_path / "root")
        # a fully coherent forgery: the component points at the primary registry and its
        # raw/canonical hashes are honestly re-derived for it, so ONLY the content can refuse
        path = V3.stage_release(root, view_path=V3.REGISTRY_PATH,
                                view_doc=V3.primary_registry_doc())
        with pytest.raises(rel.Stage1ReleaseError) as exc:
            rel.load(path, root=root, lane="production")
        assert exc.value.reason == rel.REFUSE_PRIMARY_REGISTRY_SUBSTITUTION

    def test_a_view_that_declares_no_PORTABILITY_is_REFUSED_not_defaulted(self, tmp_path):
        root = str(tmp_path / "root")
        doc = V3.scorer_view_doc()
        for p in doc["programs"]:
            p.pop("base_portable")
        path = V3.stage_release(root, view_doc=doc)
        with pytest.raises(rel.Stage1ReleaseError) as exc:
            rel.load(path, root=root, lane="production")
        assert exc.value.reason == rel.REFUSE_PRIMARY_REGISTRY_SUBSTITUTION


class TestTheLoaderRefusesLegacyAndForeignShapes:
    def test_a_LEGACY_release_manifest_is_REFUSED_by_the_v3_loader(self, tmp_path):
        # the shape Direct used to accept: schema_version + an artifacts map
        path = str(tmp_path / "legacy_release.json")
        with open(path, "w") as fh:
            json.dump({"schema_version": trust.RELEASE_SCHEMA,
                       "method_version": "stage1-continuous-v3.0.1",
                       "artifacts": {}}, fh)
        with pytest.raises(rel.Stage1ReleaseError) as exc:
            rel.load(path, root=str(tmp_path), lane="production")
        assert exc.value.reason == rel.REFUSE_NOT_V3

    def test_a_BARE_REGISTRY_handed_in_as_a_release_is_REFUSED(self, tmp_path):
        path = str(tmp_path / "registry.json")
        with open(path, "w") as fh:
            json.dump(V3.primary_registry_doc(), fh)
        with pytest.raises(rel.Stage1ReleaseError) as exc:
            rel.load(path, root=str(tmp_path), lane="production")
        assert exc.value.reason == rel.REFUSE_NOT_V3


class TestABundleCanActuallyBeBuiltOnTheV3Release:
    """The loader is not the point; a BUNDLE bound to the real release shape is."""

    def _build(self, synthetic_run, tmp_path, root, release_path):
        from direct import run_arms
        args = synthetic_run()
        ns = run_arms.build_parser().parse_args([
            "--condition", "StimX", "--out-root", str(tmp_path / "out"),
            "--de-main", args.de_main, "--by-guide", args.by_guide,
            "--by-donors", args.by_donors, "--sgrna", args.sgrna,
            "--guide-manifest", args.guide_manifest,
            "--source-registry", args.source_registry,
            "--pseudobulk", args.pseudobulk,
            "--lane", "synthetic", "--allow-dirty-tree",
            "--stage1-release", release_path, "--stage1-release-root", root])
        return run_arms.build_bundle(ns)

    def test_the_bundle_binds_the_v3_RELEASE_and_its_scorer_view(self, synthetic_run,
                                                                 tmp_path):
        root = str(tmp_path / "root")
        path = V3.stage_release(root)
        result = self._build(synthetic_run, tmp_path, root, path)

        binding = result["provenance"]["run_binding"]
        hashes = binding["arm_bundle_request"]["stage1_release_hashes"]
        assert hashes["release_schema"] == rel.RELEASE_SCHEMA
        assert hashes["release_self_sha256"]
        assert hashes["registry_scorer_view_canonical_sha256"]
        # the admitted set came from the VIEW's base_portable, and the nonportable program
        # got no arm at all
        admitted = result["bundle"]["scorer_view"]["admitted_program_ids"]
        assert admitted == sorted([V3.PROGRAM_A, V3.PROGRAM_B])
        assert V3.NONPORTABLE not in admitted
        assert result["n_arm_slots"] == 2 * len(admitted)

    def test_a_v3_release_WITHOUT_a_staged_root_is_REFUSED_not_guessed(self, synthetic_run,
                                                                       tmp_path):
        from direct import run_arms
        from direct import selection as sel
        root = str(tmp_path / "root")
        path = V3.stage_release(root)
        args = synthetic_run()
        ns = run_arms.build_parser().parse_args([
            "--condition", "StimX", "--out-root", str(tmp_path / "out"),
            "--de-main", args.de_main, "--lane", "synthetic", "--allow-dirty-tree",
            "--stage1-release", path])          # no --stage1-release-root
        with pytest.raises(sel.SelectionError, match="stage1-release-root"):
            run_arms.build_bundle(ns)


class TestTheScorerViewCannotBeReAttributed:
    def test_a_view_whose_canonical_hash_DISAGREES_with_the_release_is_REFUSED(self,
                                                                              tmp_path):
        root = str(tmp_path / "root")
        path = V3.stage_release(root)
        # the release now advertises a scorer view that is not the one it ships — resealed,
        # so the document is internally consistent and only the BYTES can refuse it
        V3.rewrite(path, lambda r: r.update(
            {"registry_scorer_view_canonical_sha256": "f" * 64}))
        with pytest.raises(rel.Stage1ReleaseError) as exc:
            rel.load(path, root=root, lane="production")
        assert exc.value.reason == rel.REFUSE_SCORER_VIEW_MISMATCH

    def test_a_SELECTOR_that_disagrees_with_base_portable_is_REFUSED(self, tmp_path):
        root = str(tmp_path / "root")
        path = V3.stage_release(root)
        # the selector claims a program the view does not mark portable
        V3.rewrite(path, lambda r: r["selector"].update(
            {"admitted_programs": [V3.PROGRAM_A, V3.PROGRAM_B, V3.NONPORTABLE]}))
        with pytest.raises(rel.Stage1ReleaseError) as exc:
            rel.load(path, root=root, lane="production")
        assert exc.value.reason == rel.REFUSE_ADMITTED_MISMATCH

    def test_a_selector_that_DROPS_an_admitted_program_is_REFUSED(self, tmp_path):
        root = str(tmp_path / "root")
        path = V3.stage_release(root)
        V3.rewrite(path, lambda r: r["selector"].update(
            {"admitted_programs": [V3.PROGRAM_A]}))
        with pytest.raises(rel.Stage1ReleaseError) as exc:
            rel.load(path, root=root, lane="production")
        assert exc.value.reason == rel.REFUSE_ADMITTED_MISMATCH
