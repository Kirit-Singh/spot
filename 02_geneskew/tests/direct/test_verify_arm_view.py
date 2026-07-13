"""The admitted program set, DERIVED from the CURRENT generic v3 release — never counted.

The addendum freezes the topology as "10 base-portable programs; Th9 is excluded as
non-portable", and then says the thing that matters: *the verifier derives this set from
the bound v3 release, never from a legacy registry path or a copied count.*

So these tests never assert "10" against a constant. They build a CLEARLY SYNTHETIC
release in the CURRENT shape (`spot.stage01_v3_release.v1`, as emitted at Stage-1
d9bd4e5+55899ac: hash-pinned `components` + a generic `selector`) which declares ten
base-portable programs and one non-portable one. The derivation must yield ten programs
and the twenty arm keys that follow — and nine when the release says nine.

The PRE-GENERIC release shape (`spot.stage01_release_manifest.v1`) is refused BY NAME. It
hard-coded a biological pair, and a verifier that quietly accepted it would be admitting
arms derived from a topology the addendum retired.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "analysis", "direct"))

import verify_arm_rules as AR  # noqa: E402
import verify_arm_view as AV  # noqa: E402

# A synthetic stand-in for the frozen v3 topology: ten base-portable programs and one the
# release marks non-portable, as Th9 is. The NAMES are fixture names; the SHAPE is real.
SYNTHETIC_TEN = [f"fx_prog{i:02d}" for i in range(1, 11)]
SYNTHETIC_NONPORTABLE = "fx_th9_like"


def _program(pid, portable=True, panel=3, control=15):
    return {
        "program_id": pid, "primary": True, "base_portable": portable,
        "panel_ensembl": [f"ENSG{i:011d}" for i in range(panel)],
        "control_ensembl": [f"ENSG{i:011d}" for i in range(100, 100 + control)],
    }


def _view_doc(portable=SYNTHETIC_TEN, nonportable=(SYNTHETIC_NONPORTABLE,)):
    """A synthetic `spot.stage01_stage2_registry_view.v1` — the executable scorer view."""
    programs = [_program(p) for p in portable]
    programs += [_program(p, portable=False, panel=1, control=0) for p in nonportable]
    # top keys as the REAL view carries them: view_kind / method_version /
    # effect_universe* / programs. No view_id, no base_portable_programs, no
    # base_portability_source_field, no per-program method_hash — the verifier reads none
    # of those, and this fixture must not invent them.
    return {"schema_version": AV.STAGE1_VIEW_SCHEMA,
            "method_version": "stage1-continuous-v3.0.1",
            "view_kind": "executable_scorer_projection",
            "effect_universe_id": "fx_effect_universe",
            "effect_universe_symbols_sha256": "0" * 64,
            "effect_universe_n_symbols": 18,
            "n_programs": len(programs), "programs": programs}


def write_v3_release(root, view=None, selector_overrides=None, schema=None,
                     reseal=True):
    """A CLEARLY SYNTHETIC release in the CURRENT generic v3 shape."""
    os.makedirs(root, exist_ok=True)
    view = view or _view_doc()
    view_path = os.path.join(root, "stage01_stage2_registry_view.json")
    with open(view_path, "w") as fh:
        json.dump(view, fh, indent=1)

    admitted = sorted(p["program_id"] for p in view["programs"]
                      if p.get("base_portable"))
    excluded = sorted(p["program_id"] for p in view["programs"]
                      if not p.get("base_portable"))
    view_canon = AV.canonical_content_sha256(view)

    selector = {
        "kind": "generic_continuous_program_selector",
        "selection_schema": "spot.stage01_selection.v3",
        "program_set_source": "v3_scorer_view",
        "registry_scorer_view_canonical_sha256": view_canon,
        "admitted_programs": admitted,
        "excluded_nonportable": excluded,
        "directions": ["high", "low"],
        "conditions": ["Rest", "Stim8hr", "Stim48hr"],
        "desired_change_mapping": {
            "away_from_A(high)": "decrease", "away_from_A(low)": "increase",
            "toward_B(high)": "increase", "toward_B(low)": "decrease",
        },
        "arm_keying": {"direct": "(program, desired_change, condition)"},
    }
    selector.update(selector_overrides or {})

    release = {
        "schema": schema or AV.STAGE1_RELEASE_SCHEMA_V3,
        "method_version": "stage1-continuous-v3.0.1",
        "registry_scorer_view_canonical_sha256": view_canon,
        "selector": selector,
        "components": {
            "stage2_registry_view": {
                "path": os.path.relpath(view_path, root),
                "raw_sha256": hashlib.sha256(open(view_path, "rb").read()).hexdigest(),
                "canonical_content_sha256": view_canon,
                "role": "executable_scorer_view",
            },
        },
    }
    if reseal:
        release["self_release_sha256"] = AV.release_self_sha256(release)
    path = os.path.join(root, "stage01_v3_release.json")
    with open(path, "w") as fh:
        json.dump(release, fh, indent=1)
    return path


# --------------------------------------------------------------------------- #
# The CURRENT generic v3 release shape (Stage-1 d9bd4e5 + 55899ac).
# --------------------------------------------------------------------------- #
class TestTheCurrentGenericV3ReleaseShapeIsWhatIsConsumed:
    def test_the_admitted_set_is_derived_from_the_BOUND_scorer_view_component(
            self, tmp_path):
        rel = AV.load_v3_release(write_v3_release(str(tmp_path)), str(tmp_path))
        assert rel["admitted_program_ids"] == sorted(SYNTHETIC_TEN)
        assert rel["n_admitted_programs"] == 10

    def test_ten_admitted_programs_yield_exactly_TWENTY_arm_keys(self, tmp_path):
        rel = AV.load_v3_release(write_v3_release(str(tmp_path)), str(tmp_path))
        keys = AR.expected_arm_keys(rel["admitted_program_ids"], "Rest")
        assert len(keys) == 20 == AR.expected_slots(rel["admitted_program_ids"])

    def test_the_NON_PORTABLE_program_is_excluded_the_way_Th9_is(self, tmp_path):
        rel = AV.load_v3_release(write_v3_release(str(tmp_path)), str(tmp_path))
        assert SYNTHETIC_NONPORTABLE not in rel["admitted_program_ids"]
        assert SYNTHETIC_NONPORTABLE in rel["stage2_arm_view"]["excluded_program_ids"]

    def test_the_count_FOLLOWS_the_release_and_is_not_a_constant(self, tmp_path):
        nine = SYNTHETIC_TEN[:9]
        rel = AV.load_v3_release(
            write_v3_release(str(tmp_path), view=_view_doc(portable=nine)),
            str(tmp_path))
        assert rel["n_admitted_programs"] == 9
        assert AR.expected_slots(rel["admitted_program_ids"]) == 18

    def test_the_release_binds_the_scorer_view_by_CANONICAL_hash(self, tmp_path):
        rel = AV.load_v3_release(write_v3_release(str(tmp_path)), str(tmp_path))
        assert len(rel["stage1_scorer_view_canonical_sha256"]) == 64


class TestAStaleOrForgedReleaseShapeIsRefusedByName:
    def test_the_PRE_GENERIC_release_manifest_shape_is_refused_BY_NAME(self, tmp_path):
        # spot.stage01_release_manifest.v1 hard-coded a biological pair. Accepting it
        # would admit arms derived from a topology the addendum retired.
        path = os.path.join(str(tmp_path), "old.json")
        with open(path, "w") as fh:
            json.dump({"schema_version": AV.STAGE1_RELEASE_SCHEMA_STALE,
                       "method_version": "stage1-continuous-v3.0.1",
                       "artifacts": {"registry": {"path": "r.json"}}}, fh)
        with pytest.raises(AV.ScorerViewError) as exc:
            AV.load_v3_release(path, str(tmp_path))
        assert exc.value.reason == AV.REFUSE_STALE_RELEASE_SHAPE

    def test_an_UNKNOWN_release_schema_is_refused_not_guessed(self, tmp_path):
        path = os.path.join(str(tmp_path), "weird.json")
        with open(path, "w") as fh:
            json.dump({"schema": "spot.stage01_something_else.v9"}, fh)
        with pytest.raises(AV.ScorerViewError) as exc:
            AV.load_v3_release(path, str(tmp_path))
        assert exc.value.reason == AV.REFUSE_UNKNOWN_RELEASE_SHAPE

    def test_a_release_that_does_not_BIND_its_scorer_view_is_refused(self, tmp_path):
        path = write_v3_release(str(tmp_path))
        doc = json.load(open(path))
        del doc["registry_scorer_view_canonical_sha256"]
        doc["self_release_sha256"] = AV.release_self_sha256(doc)
        with open(path, "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(AV.ScorerViewError) as exc:
            AV.load_v3_release(path, str(tmp_path))
        assert exc.value.reason == AV.REFUSE_VIEW_NOT_BOUND

    def test_MUTATED_scorer_view_bytes_are_refused_against_the_pinned_raw_hash(
            self, tmp_path):
        path = write_v3_release(str(tmp_path))
        view_path = os.path.join(str(tmp_path), "stage01_stage2_registry_view.json")
        view = json.load(open(view_path))
        view["programs"][0]["base_portable"] = False      # silently drop a program
        with open(view_path, "w") as fh:
            json.dump(view, fh, indent=1)
        with pytest.raises(AV.ScorerViewError) as exc:
            AV.load_v3_release(path, str(tmp_path))
        assert exc.value.reason == AV.REFUSE_COMPONENT_HASH_MISMATCH

    def test_a_RESEALED_scorer_view_still_fails_the_hash_the_RELEASE_binds(
            self, tmp_path):
        # reseal the component entry too — the release's own top-level binding still
        # names the original view, so the swap is caught there
        path = write_v3_release(str(tmp_path))
        view_path = os.path.join(str(tmp_path), "stage01_stage2_registry_view.json")
        view = json.load(open(view_path))
        view["programs"][0]["base_portable"] = False
        with open(view_path, "w") as fh:
            json.dump(view, fh, indent=1)
        doc = json.load(open(path))
        comp = doc["components"]["stage2_registry_view"]
        comp["raw_sha256"] = hashlib.sha256(open(view_path, "rb").read()).hexdigest()
        comp["canonical_content_sha256"] = AV.canonical_content_sha256(view)
        doc["self_release_sha256"] = AV.release_self_sha256(doc)
        with open(path, "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(AV.ScorerViewError) as exc:
            AV.load_v3_release(path, str(tmp_path))
        assert exc.value.reason == AV.REFUSE_VIEW_HASH_MISMATCH

    def test_a_release_whose_SELF_HASH_does_not_re_derive_is_refused(self, tmp_path):
        path = write_v3_release(str(tmp_path))
        doc = json.load(open(path))
        doc["method_version"] = "stage1-continuous-v9.9.9"   # not resealed
        with open(path, "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(AV.ScorerViewError) as exc:
            AV.load_v3_release(path, str(tmp_path))
        assert exc.value.reason == AV.REFUSE_SELF_HASH_MISMATCH

    def test_a_DECLARED_admitted_list_that_disagrees_with_the_derivation_is_refused(
            self, tmp_path):
        # the release may DECLARE its admitted set; it may not OVERRIDE the derivation
        path = write_v3_release(
            str(tmp_path),
            selector_overrides={"admitted_programs": sorted(SYNTHETIC_TEN)[:5]},
            reseal=False)
        doc = json.load(open(path))
        doc["self_release_sha256"] = AV.release_self_sha256(doc)
        with open(path, "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(AV.ScorerViewError) as exc:
            AV.load_v3_release(path, str(tmp_path))
        assert exc.value.reason == AV.REFUSE_ADMITTED_SET_DISAGREES

    def test_a_FORGED_desired_change_mapping_is_refused(self, tmp_path):
        # the verifier RE-DERIVES the mapping; a release that swapped it is refused
        forged = {"away_from_A(high)": "increase", "away_from_A(low)": "decrease",
                  "toward_B(high)": "decrease", "toward_B(low)": "increase"}
        path = write_v3_release(
            str(tmp_path), selector_overrides={"desired_change_mapping": forged},
            reseal=False)
        doc = json.load(open(path))
        doc["self_release_sha256"] = AV.release_self_sha256(doc)
        with open(path, "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(AV.ScorerViewError) as exc:
            AV.load_v3_release(path, str(tmp_path))
        assert exc.value.reason == AV.REFUSE_MAPPING_FORGED


# --------------------------------------------------------------------------- #
# The Stage-2 arm view derived from whichever program source the lane binds.
# --------------------------------------------------------------------------- #
class TestTheAdmittedSetIsDerivedNeverDeclared:
    def test_a_program_is_admitted_iff_the_release_marks_it_base_portable(self):
        view = AV.stage2_arm_view(AV.programs_from_doc(_view_doc()))
        assert view["admitted_program_ids"] == sorted(SYNTHETIC_TEN)

    def test_a_release_that_does_not_DECLARE_portability_is_REFUSED(self):
        doc = _view_doc()
        del doc["programs"][0]["base_portable"]
        with pytest.raises(AV.ScorerViewError) as exc:
            AV.stage2_arm_view(AV.programs_from_doc(doc))
        assert exc.value.reason == AV.REFUSE_PORTABILITY_UNDECLARED

    def test_a_release_that_admits_NOTHING_is_REFUSED_not_emitted_empty(self):
        with pytest.raises(AV.ScorerViewError) as exc:
            AV.stage2_arm_view(AV.programs_from_doc(_view_doc(portable=[])))
        assert exc.value.reason == AV.REFUSE_NO_ADMITTED


class TestTheViewHashBindsTheScorerProjectionNotJustTheIds:
    def test_the_same_ids_with_a_DIFFERENT_PANEL_are_a_DIFFERENT_view(self):
        a = _view_doc()
        b = _view_doc()
        b["programs"][0]["panel_ensembl"] = ["ENSG00000000042"]
        assert AV.stage2_arm_view(AV.programs_from_doc(a))["scorer_view_sha256"] != \
            AV.stage2_arm_view(AV.programs_from_doc(b))["scorer_view_sha256"], \
            "a bundle keyed only on the ids could be re-attributed from one to the other"

    def test_the_view_hash_is_stable_under_panel_gene_ORDER(self):
        a, b = _view_doc(), _view_doc()
        b["programs"][0]["panel_ensembl"] = list(
            reversed(b["programs"][0]["panel_ensembl"]))
        assert AV.stage2_arm_view(AV.programs_from_doc(a))["scorer_view_sha256"] == \
            AV.stage2_arm_view(AV.programs_from_doc(b))["scorer_view_sha256"]

    def test_every_admitted_program_carries_its_own_projection_binding(self):
        view = AV.stage2_arm_view(AV.programs_from_doc(_view_doc()))
        for pid in view["admitted_program_ids"]:
            detail = view["programs"][pid]
            assert detail["n_panel"] == 3 and detail["n_control"] == 15
            assert len(detail["panel_sha256"]) == 64
            assert len(detail["control_sha256"]) == 64

    def test_the_view_never_claims_a_legacy_registry_derivation(self):
        view = AV.stage2_arm_view(AV.programs_from_doc(_view_doc()))
        assert view["derived_from_legacy_registry"] is False

    def test_the_per_program_id_is_COMPUTED_not_read_from_a_nonexistent_field(self):
        # the real scorer view carries no per-program method_hash / projection id. So the
        # record is SPECIFIED here and hashed from the program's own bytes.
        prog = _program("fx_prog01")
        assert "method_hash" not in prog and "program_projection_sha256" not in prog
        rec = AV.program_projection("fx_prog01", prog)
        assert len(rec["program_projection_sha256"]) == 64

    def test_the_program_projection_hash_changes_with_the_PANEL_MEMBERSHIP(self):
        a = AV.program_projection("p", _program("p"))
        b = dict(_program("p"), panel_ensembl=["ENSG00000000042"])
        assert a["program_projection_sha256"] != \
            AV.program_projection("p", b)["program_projection_sha256"]

    def test_the_program_projection_hash_is_stable_under_panel_ORDER(self):
        prog = _program("p")
        shuffled = dict(prog, panel_ensembl=list(reversed(prog["panel_ensembl"])))
        assert AV.program_projection("p", prog)["program_projection_sha256"] == \
            AV.program_projection("p", shuffled)["program_projection_sha256"]


class TestTheREALStage1ReleaseOnDisk:
    """Compatibility with the ACTUAL Stage-1 generic v3 release (d9bd4e5 + 55899ac).

    Not a fixture: the real scorer view, read from disk, hashed by this verifier's own
    canonicalisation. If Stage-1 is not staged on this host the tests skip rather than
    quietly pass — a compatibility claim nobody ran is not a compatibility claim.
    """

    # the frozen bindings the release declares
    VIEW_CANONICAL = "5d1d8c36"
    SCORER_PROJECTION = "008c1da1"
    NONPORTABLE = "th9_like"

    def _view(self):
        for root in ("/home/tcelab/worktrees/spot-stage2-integration",
                     "/home/tcelab/projects/spot"):
            path = os.path.join(
                root, "01_programs", "app", "data",
                "stage01_stage2_registry_view.json")
            if os.path.exists(path):
                return json.load(open(path))
        pytest.skip("the Stage-1 v3 scorer view is not staged on this host")

    def test_the_view_canonical_hash_RE_DERIVES_to_the_frozen_5d1d8c36(self):
        canon = AV.canonical_content_sha256(self._view())
        assert canon.startswith(self.VIEW_CANONICAL), canon

    def test_the_real_release_admits_TEN_programs_and_excludes_Th9(self):
        view = AV.stage2_arm_view(AV.programs_from_doc(self._view()))
        assert view["n_admitted_programs"] == 10
        assert view["n_release_programs"] == 11
        assert view["excluded_program_ids"] == [self.NONPORTABLE]

    def test_the_real_release_yields_SIXTY_direct_logical_slots(self):
        # 10 admitted programs x 2 desired changes x 3 conditions, DERIVED
        view = AV.stage2_arm_view(AV.programs_from_doc(self._view()))
        total = sum(len(AR.expected_arm_keys(view["admitted_program_ids"], c))
                    for c in ("Rest", "Stim8hr", "Stim48hr"))
        assert total == 60

    def test_the_real_view_carries_none_of_the_fields_this_verifier_must_not_read(self):
        # no view_id, no base_portable_programs, no base_portability_source_field, and no
        # per-program method_hash. The derivation reads base_portable and the gene sets.
        view = self._view()
        for absent in ("view_id", "base_portable_programs",
                       "base_portability_source_field"):
            assert absent not in view
        for prog in view["programs"]:
            assert "method_hash" not in prog
            assert "base_portable" in prog


class TestTheComponentsResolveAgainstAnExplicitlyStagedRoot:
    def test_a_component_path_that_ESCAPES_the_staged_root_is_refused(self, tmp_path):
        path = write_v3_release(str(tmp_path), reseal=False)
        doc = json.load(open(path))
        doc["components"]["stage2_registry_view"]["path"] = "../../etc/passwd"
        doc["self_release_sha256"] = AV.release_self_sha256(doc)
        with open(path, "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(AV.ScorerViewError) as exc:
            AV.load_v3_release(path, str(tmp_path))
        assert exc.value.reason == AV.REFUSE_COMPONENT_PATH_ESCAPES_ROOT

    def test_a_component_missing_UNDER_THE_STAGED_ROOT_is_refused(self, tmp_path):
        path = write_v3_release(str(tmp_path))
        elsewhere = tmp_path / "not-the-staging-root"
        elsewhere.mkdir()
        with pytest.raises(AV.ScorerViewError) as exc:
            AV.load_v3_release(path, str(elsewhere))
        assert exc.value.reason == AV.REFUSE_COMPONENT_MISSING

    def test_a_scorer_view_with_an_UNKNOWN_schema_is_refused_by_name(self, tmp_path):
        view = dict(_view_doc(), schema_version="spot.stage01_something_else.v9")
        path = write_v3_release(str(tmp_path), view=view)
        with pytest.raises(AV.ScorerViewError) as exc:
            AV.load_v3_release(path, str(tmp_path))
        assert exc.value.reason == AV.REFUSE_VIEW_SHAPE
