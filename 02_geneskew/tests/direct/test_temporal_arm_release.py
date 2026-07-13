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
            mutate_release=lambda d: d.update({"schema_version": "spot.made_up.v9"}))
        with pytest.raises(release.ReleaseRefused, match="schema_version"):
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
        with pytest.raises(release.ReleaseRefused, match="absolute|relative"):
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

    def test_the_scorer_projection_is_the_admitted_program_axis_only(self, tmp_path):
        rel = release.load_release(FX.stage_release(tmp_path))
        proj = release.scorer_projection(rel.scorer_view)
        assert proj["n_programs"] == len(FX.PORTABLE_IDS)
        assert [p["program_id"] for p in proj["programs"]] == sorted(FX.PORTABLE_IDS)
        assert rel.scorer_projection_sha256 == canonical.content_hash(proj)

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
