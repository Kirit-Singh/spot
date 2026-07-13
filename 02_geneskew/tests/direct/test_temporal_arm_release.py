"""The bound Stage-1 v3 release: the program axis and the condition universe, DERIVED.

The verifier reads the CURRENT v3 release shape (``spot.stage01_v3_release.v1``, with a
``selector`` and ``components``). The LEGACY manifest shape (``artifacts``) is refused by
name at a named gate — a Stage-2 lane that silently accepted either would be binding to
whichever one happened to be lying around.

Nothing here is a fixture assumption about fields the real view does not have: the view
carries ``base_portable`` per program and NOTHING called ``view_id``,
``base_portable_programs``, ``base_portability_source_field`` or a per-program
``method_hash``, so the admitted set is derived from ``base_portable`` alone and any
per-program identity is an independently hashed canonical PROJECTION of the program.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_ANALYSIS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                         "analysis"))
if _ANALYSIS not in sys.path:
    sys.path.insert(0, _ANALYSIS)
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fixtures_arm_verifier as FX  # noqa: E402
from verify_temporal_arms import canonical, release  # noqa: E402


class TestTheReleaseShapeIsGated:
    def test_the_current_v3_release_shape_loads(self, tmp_path):
        root = FX.stage_release(tmp_path)
        rel = release.load_release(root)
        assert rel.schema_version == "spot.stage01_v3_release.v1"

    def test_the_legacy_manifest_shape_is_refused_by_name(self, tmp_path):
        root = FX.stage_release(tmp_path, mutate_release=FX.as_legacy_manifest)
        with pytest.raises(release.ReleaseRefused, match="LEGACY"):
            release.load_release(root)

    def test_a_forged_schema_version_is_refused(self, tmp_path):
        root = FX.stage_release(
            tmp_path,
            mutate_release=lambda d: d.update({"schema": "spot.made_up.v9"}))
        with pytest.raises(release.ReleaseRefused, match="schema"):
            release.load_release(root)

    def test_an_artifacts_block_beside_components_is_still_the_legacy_shape(self, tmp_path):
        root = FX.stage_release(tmp_path,
                                mutate_release=lambda d: d.update({"artifacts": {}}))
        with pytest.raises(release.ReleaseRefused, match="LEGACY"):
            release.load_release(root)


class TestTheReleaseRootIsStagedExplicitly:
    def test_component_paths_resolve_against_the_staged_root_never_a_default(self, tmp_path):
        root = FX.stage_release(tmp_path)
        rel = release.load_release(root)
        assert rel.release_root == os.path.abspath(root)

    def test_an_absolute_component_path_is_refused(self, tmp_path):
        root = FX.stage_release(
            tmp_path,
            mutate_release=lambda d: d["components"]["scorer_view"].update(
                {"path": "/Fixture/Machine/spot/scorer_view.json"}))
        with pytest.raises(release.ReleaseRefused, match="absolute|relative|resolve"):
            release.load_release(root)

    def test_a_component_path_that_escapes_the_root_is_refused(self, tmp_path):
        root = FX.stage_release(
            tmp_path,
            mutate_release=lambda d: d["components"]["scorer_view"].update(
                {"path": "../../etc/passwd"}))
        with pytest.raises(release.ReleaseRefused):
            release.load_release(root)

    def test_a_component_whose_bytes_do_not_match_its_declared_hash_is_refused(self, tmp_path):
        root = FX.stage_release(
            tmp_path,
            mutate_release=lambda d: d["components"]["scorer_view"].update(
                {"raw_sha256": "0" * 64}))
        with pytest.raises(release.ReleaseRefused, match="raw_sha256"):
            release.load_release(root)


class TestTheScorerView:
    def test_the_scorer_view_is_found_by_its_own_schema_not_by_a_key_name(self, tmp_path):
        root = FX.stage_release(tmp_path, scorer_component_name="whatever_they_call_it")
        rel = release.load_release(root)
        assert rel.scorer_view["view_kind"] == FX.VIEW_KIND

    def test_two_scorer_views_are_refused_rather_than_one_being_picked(self, tmp_path):
        root = FX.stage_release(tmp_path, duplicate_scorer_view=True)
        with pytest.raises(release.ReleaseRefused, match="exactly one"):
            release.load_release(root)

    def test_no_scorer_view_is_refused(self, tmp_path):
        root = FX.stage_release(tmp_path, drop_scorer_view=True)
        with pytest.raises(release.ReleaseRefused, match="exactly one"):
            release.load_release(root)

    def test_the_loader_reads_no_field_the_real_view_does_not_have(self, tmp_path):
        """The real view has no view_id, no base_portable_programs, no
        base_portability_source_field and no per-program method_hash. It must still load."""
        root = FX.stage_release(tmp_path)
        view = json.loads(open(os.path.join(root, "scorer_view.json")).read())
        for absent in ("view_id", "base_portable_programs",
                       "base_portability_source_field"):
            assert absent not in view
        assert all("method_hash" not in p for p in view["programs"])
        assert release.load_release(root).admitted_programs          # loads anyway


class TestTheProgramAxisIsDerived:
    def test_admitted_programs_are_derived_from_base_portable(self, tmp_path):
        rel = release.load_release(FX.stage_release(tmp_path))
        assert sorted(rel.admitted_programs) == sorted(FX.PORTABLE_IDS)
        assert FX.NON_PORTABLE_ID not in rel.admitted_programs

    def test_the_count_is_a_consequence_not_a_constant(self, tmp_path):
        """The fixture ships ELEVEN programs so a hard-coded 10 cannot pass."""
        rel = release.load_release(FX.stage_release(tmp_path))
        assert len(rel.scorer_view["programs"]) == len(FX.PORTABLE_IDS) + 1
        assert rel.n_admitted_programs == len(FX.PORTABLE_IDS)

    def test_the_derived_set_must_agree_with_the_releases_own_selector(self, tmp_path):
        root = FX.stage_release(
            tmp_path,
            mutate_release=lambda d: d["selector"].update(
                {"admitted_programs": FX.PORTABLE_IDS[:5]}))
        with pytest.raises(release.ReleaseRefused, match="admitted_programs"):
            release.load_release(root)

    def test_a_base_portable_program_with_no_projectable_axis_is_refused_not_dropped(
            self, tmp_path):
        root = FX.stage_release(tmp_path, break_panel_of=FX.PORTABLE_IDS[0])
        with pytest.raises(release.ReleaseRefused, match="projectable"):
            release.load_release(root)

    def test_the_per_program_hash_is_the_WHOLE_record_as_stage1_emitted_it(self, tmp_path):
        """Not a four-field summary of it: a summary hashes the same after Stage-1 changes a
        field the summary never looked at, and the map goes on vouching for a program it no
        longer describes."""
        root = FX.stage_release(tmp_path)
        rel = release.load_release(root)
        with open(os.path.join(root, "scorer_view.json")) as fh:
            view = json.load(fh)

        for pid, sha in rel.program_projection_sha256.items():
            record = next(p for p in view["programs"] if p["program_id"] == pid)
            assert sha == canonical.content_hash(record)

        # the rule is Stage-1's, and it is named
        assert release.PER_PROGRAM_PROJECTION_RULE_ID == \
            "spot.stage01_stage2_registry_view.program_record.canonical_sha256.v1"

    def test_the_map_is_keyed_on_exactly_the_base_portable_programs(self, tmp_path):
        rel = release.load_release(FX.stage_release(tmp_path))
        assert sorted(rel.program_projection_sha256) == sorted(FX.PORTABLE_IDS)
        assert FX.NON_PORTABLE_ID not in rel.program_projection_sha256

    def test_ARRAY_ORDER_is_preserved_so_a_reordered_panel_is_a_different_record(
            self, tmp_path):
        """Sorting the panel before hashing would make a reordered panel hash identical to
        the original. A reordering is a different record, and Stage-1's order is content."""
        a = release.load_release(FX.stage_release(tmp_path / "a"))
        b = release.load_release(FX.stage_release(
            tmp_path / "b", reverse_panel_of=FX.PORTABLE_IDS[0]))
        pid = FX.PORTABLE_IDS[0]
        assert a.program_projection_sha256[pid] != b.program_projection_sha256[pid]
        # ...and no OTHER program moved
        for other in FX.PORTABLE_IDS[1:]:
            assert a.program_projection_sha256[other] == b.program_projection_sha256[other]

    def test_a_field_stage1_changed_moves_the_hash_even_if_no_panel_did(self, tmp_path):
        """The four-field derivation would miss this entirely."""
        a = release.load_release(FX.stage_release(tmp_path / "a"))
        b = release.load_release(FX.stage_release(
            tmp_path / "b", flip_extra_field_of=FX.PORTABLE_IDS[0]))
        pid = FX.PORTABLE_IDS[0]
        assert a.program_projection_sha256[pid] != b.program_projection_sha256[pid]


class TestTheConditionUniverse:
    def test_the_conditions_come_from_the_release_selector(self, tmp_path):
        rel = release.load_release(FX.stage_release(tmp_path))
        assert rel.conditions == tuple(FX.CONDITIONS)

    def test_three_conditions_give_exactly_six_ordered_pairs(self, tmp_path):
        rel = release.load_release(FX.stage_release(tmp_path))
        assert len(rel.ordered_pairs) == 6

    def test_a_reordered_condition_list_is_a_different_time_axis_and_is_refused(
            self, tmp_path):
        root = FX.stage_release(
            tmp_path,
            mutate_release=lambda d: d["selector"].update(
                {"conditions": list(reversed(FX.CONDITIONS))}))
        rel = release.load_release(root)
        with pytest.raises(release.ReleaseRefused, match="order"):
            release.require_conditions(rel, FX.CONDITIONS)

    def test_a_forged_condition_is_refused_against_the_pinned_universe(self, tmp_path):
        root = FX.stage_release(
            tmp_path,
            mutate_release=lambda d: d["selector"].update(
                {"conditions": [FX.CONDITIONS[0], FX.CONDITIONS[1], "FixStim24"]}))
        rel = release.load_release(root)
        with pytest.raises(release.ReleaseRefused, match="FixStim24|does not match"):
            release.require_conditions(rel, FX.CONDITIONS)

    def test_a_missing_condition_is_refused_against_the_pinned_universe(self, tmp_path):
        root = FX.stage_release(
            tmp_path,
            mutate_release=lambda d: d["selector"].update(
                {"conditions": list(FX.CONDITIONS[:2])}))
        rel = release.load_release(root)
        assert len(rel.ordered_pairs) == 2                 # derived, not assumed
        with pytest.raises(release.ReleaseRefused):
            release.require_conditions(rel, FX.CONDITIONS)

    def test_a_duplicated_condition_is_refused_at_load(self, tmp_path):
        root = FX.stage_release(
            tmp_path,
            mutate_release=lambda d: d["selector"].update(
                {"conditions": [FX.CONDITIONS[0], FX.CONDITIONS[0], FX.CONDITIONS[1]]}))
        with pytest.raises(release.ReleaseRefused, match="duplicate"):
            release.load_release(root)


class TestTheScorerBindingHashes:
    def test_the_whole_scorer_view_is_bound_by_its_canonical_hash(self, tmp_path):
        root = FX.stage_release(tmp_path)
        rel = release.load_release(root)
        view = json.loads(open(os.path.join(root, "scorer_view.json")).read())
        assert rel.scorer_view_sha256 == canonical.content_hash(view)

    def test_the_scorer_projection_is_STAGE_1s_registry_projection(self, tmp_path):
        """It is not an invention of this lane. Stage-1 projects its PROGRAM REGISTRY, strips
        the fields that do not feed scoring — provenance, rationale, and display-only labels —
        and hashes that. The display-only strip is the point of the rule: a cosmetic relabel
        must never move the scorer-core invariant, or every lane pinned to it would
        re-verify for a reason that has nothing to do with the science."""
        root = FX.stage_release(tmp_path)
        rel = release.load_release(root)
        with open(os.path.join(root, "registry_v3.json")) as fh:
            registry = json.load(fh)
        assert rel.scorer_projection_sha256 == canonical.content_hash(
            release.registry_scorer_projection(registry))
        assert "display_label" in release.SCORER_PROJECTION_PROV_PROG

    def test_a_cosmetic_relabel_does_NOT_move_the_scorer_projection(self, tmp_path):
        """The invariant the strip exists to protect."""
        root = FX.stage_release(tmp_path)
        before = release.load_release(root).scorer_projection_sha256
        with open(os.path.join(root, "registry_v3.json")) as fh:
            registry = json.load(fh)
        registry["programs"][0]["display_label"] = "A Prettier Name"
        assert release.registry_scorer_projection(registry)
        after = canonical.content_hash(release.registry_scorer_projection(registry))
        assert after == before

    def test_touching_an_admitted_panel_moves_the_projection_hash(self, tmp_path):
        a = release.load_release(FX.stage_release(tmp_path / "a"))
        b = release.load_release(FX.stage_release(tmp_path / "b",
                                                  extra_panel_gene=FX.PORTABLE_IDS[0]))
        assert a.scorer_projection_sha256 != b.scorer_projection_sha256
        assert a.scorer_view_sha256 != b.scorer_view_sha256

    def test_a_declared_binding_prefix_that_does_not_match_is_refused(self, tmp_path):
        rel = release.load_release(FX.stage_release(tmp_path))
        release.require_scorer_binding(rel, view_prefix=rel.scorer_view_sha256[:8])
        with pytest.raises(release.ReleaseRefused, match="scorer_view"):
            release.require_scorer_binding(rel, view_prefix="deadbeef")
        with pytest.raises(release.ReleaseRefused, match="scorer_projection"):
            release.require_scorer_binding(rel, projection_prefix="deadbeef")

    def test_the_frozen_release_pins_are_declared_and_never_defaulted(self):
        """The 55899ac release's own values, recorded so a caller can pin them. They are
        NOT applied by default: this worktree ships no release, and a pin nobody supplied
        must never silently pass."""
        assert release.FROZEN_SCORER_VIEW_SHA256_PREFIX == "5d1d8c36"
        assert release.FROZEN_SCORER_PROJECTION_SHA256_PREFIX == "008c1da1"


# --------------------------------------------------------------------------- #
# THE ACTUAL STAGE-1 RELEASE. Not a fixture of it — the bytes Stage-1 ships.
# --------------------------------------------------------------------------- #
_STAGE1_COMMIT = "539431d"
_STAGE1_RELEASE = "01_programs/analysis/stage2_bridge/release/stage01_v3_release.json"


def _repo():
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "..", "..", ".."))


def _has_stage1():
    import subprocess
    return subprocess.run(("git", "-C", _repo(), "cat-file", "-e",
                           f"{_STAGE1_COMMIT}:{_STAGE1_RELEASE}"),
                          capture_output=True).returncode == 0


@pytest.fixture(scope="module")
def stage1_checkout(tmp_path_factory):
    """A CLEAN detached checkout of Stage-1's release commit. Its bytes, unmodified."""
    import subprocess

    if not _has_stage1():
        pytest.skip("the Stage-1 release commit is not in this repository")
    path = str(tmp_path_factory.mktemp("stage1") / "checkout")
    subprocess.run(("git", "-C", _repo(), "worktree", "add", "--detach", path,
                    _STAGE1_COMMIT), capture_output=True, check=True)
    yield path
    subprocess.run(("git", "-C", _repo(), "worktree", "remove", "--force", path),
                   capture_output=True)


class TestTheREALStage1Release:
    """The bytes Stage-1 actually ships, loaded exactly as they are.

    The correct response to native bytes that do not match an assumption is to fix the
    assumption — never to translate the bytes. A verifier that admitted a rewritten copy would
    have verified something nobody shipped.
    """

    def test_the_native_release_loads_and_every_declared_hash_RE_DERIVES(
            self, stage1_checkout):
        rel = release.load_release(os.path.join(stage1_checkout, _STAGE1_RELEASE))

        # its own identity, by its own declared rule
        assert rel.release_self_sha256 == (
            "2262430931707552f4414808be3d6734fa3c7287748ec23339ce3ef498224b11")
        assert rel.release_raw_sha256 == (
            "0c336546db10746bba1569ccc6bef7dedf9679effd24e17d0c07a5ab04dbef73")

        # The native self identity and complete-file hash are distinct bindings. There is
        # no backwards alias whose ambiguous name can silently swap one for the other.
        assert not hasattr(rel, "self_release_sha256")
        assert rel.binding_block()["stage1_release_self_sha256"] == \
            rel.release_self_sha256
        assert rel.binding_block()["stage1_release_raw_sha256"] == rel.release_raw_sha256

        # the scorer identity — RE-DERIVED from the registry it binds, not read off the release
        assert rel.scorer_view_sha256.startswith("5d1d8c36")
        assert rel.scorer_projection_sha256 == (
            "008c1da121a1ea3b08871f1bc0339b120d5dc9b46d01619768eebd046331bd85")

        # the topology the temporal lane stands on
        assert list(rel.conditions) == ["Rest", "Stim8hr", "Stim48hr"]
        assert len(rel.ordered_pairs) == 6
        assert rel.n_admitted_programs == 10
        assert rel.n_logical_arms == 120

    def test_the_release_is_read_under_its_NATIVE_name_and_key(self, stage1_checkout):
        """``stage01_v3_release.json``, and ``schema`` — not ``release.json`` / ``schema_version``.
        Looking for the wrong name reports a missing release for one entirely present, which
        is exactly what the real run did."""
        with open(os.path.join(stage1_checkout, _STAGE1_RELEASE)) as fh:
            doc = json.load(fh)
        assert release.RELEASE_FILENAME == "stage01_v3_release.json"
        assert release.SCHEMA_KEY == "schema"
        assert doc["schema"] == "spot.stage01_v3_release.v1"
        assert "schema_version" not in doc

    def test_a_component_staged_OUTSIDE_the_repo_is_bound_not_refused(self, stage1_checkout):
        """One component names a ``location`` and its hashes, not a path. It is a BINDING that
        this verifier cannot open — refusing it would refuse the release, and inventing a path
        for it would invent the very thing the hash exists to pin."""
        with open(os.path.join(stage1_checkout, _STAGE1_RELEASE)) as fh:
            doc = json.load(fh)
        offrepo = [n for n, c in doc["components"].items() if "path" not in c]
        assert offrepo == ["scores_parquet"]
        assert doc["components"]["scores_parquet"]["raw_sha256_staged"]
        release.load_release(os.path.join(stage1_checkout, _STAGE1_RELEASE))   # loads

    def test_the_WRONG_FILENAME_is_refused_by_name(self, stage1_checkout, tmp_path):
        import shutil

        src = os.path.join(stage1_checkout, _STAGE1_RELEASE)
        d = str(tmp_path / "wrong")
        os.makedirs(d)
        shutil.copy(src, os.path.join(d, "release.json"))     # the name W11 used to expect
        with pytest.raises(release.ReleaseRefused, match="stage01_v3_release.json"):
            release.load_release(d)

    def test_the_WRONG_SCHEMA_KEY_is_refused(self, stage1_checkout, tmp_path):
        with open(os.path.join(stage1_checkout, _STAGE1_RELEASE)) as fh:
            doc = json.load(fh)
        doc["schema_version"] = doc.pop("schema")             # the key W11 used to expect
        d = str(tmp_path / "key")
        os.makedirs(d)
        with open(os.path.join(d, release.RELEASE_FILENAME), "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(release.ReleaseRefused, match="schema"):
            release.load_release(d, content_root=stage1_checkout)

    def test_a_MUTATED_release_whose_self_hash_no_longer_follows_is_refused(
            self, stage1_checkout, tmp_path):
        """A release whose id does not follow its content can be edited and keep its name."""
        with open(os.path.join(stage1_checkout, _STAGE1_RELEASE)) as fh:
            doc = json.load(fh)
        doc["method_version"] = "tampered"                    # the id is now stale
        d = str(tmp_path / "self")
        os.makedirs(d)
        with open(os.path.join(d, release.RELEASE_FILENAME), "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(release.ReleaseRefused, match="self_release_sha256"):
            release.load_release(d, content_root=stage1_checkout)

    def test_a_release_declaring_a_scorer_projection_its_registry_does_not_yield_is_refused(
            self, stage1_checkout, tmp_path):
        with open(os.path.join(stage1_checkout, _STAGE1_RELEASE)) as fh:
            doc = json.load(fh)
        doc["registry_scorer_projection_sha256"] = "0" * 64
        doc.pop("self_release_sha256")
        doc["self_release_sha256"] = canonical.content_hash(doc)   # resealed
        d = str(tmp_path / "proj")
        os.makedirs(d)
        with open(os.path.join(d, release.RELEASE_FILENAME), "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(release.ReleaseRefused,
                           match="registry_scorer_projection_sha256"):
            release.load_release(d, content_root=stage1_checkout)
