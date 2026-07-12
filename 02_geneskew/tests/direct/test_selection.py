"""The Stage-1 selection contract is consumed, never constructed or repaired."""

import pytest
from direct import selection as sel_mod
from direct.selection import SelectionError
from fixtures_direct import CONDITION, write_selection


def _contract(**over):
    base = {
        "schema_version": "spot.stage01_selection_contract.v1",
        "lane": "synthetic",
        "A": {"program_id": "program_a", "direction": "high"},
        "B": {"program_id": "program_b", "direction": "low"},
        "analysis_condition": CONDITION,
        "combination_policy": "deferred_to_stage2",
        "ids": {"question_id": "q" * 16, "selection_id": "s" * 16},
        "hashes": {"registry_sha256": "r" * 64,
                   "method_version": "stage1-continuous-v3.0.1",
                   "input_manifest_sha256": "m" * 64, "code_sha256": "c" * 64},
    }
    base.update(over)
    return base


def test_a_contract_must_declare_its_lane():
    c = _contract()
    del c["lane"]
    with pytest.raises(SelectionError, match="lane must be one of"):
        sel_mod.parse_selection(c, contract_sha256="x")
    with pytest.raises(SelectionError, match="lane must be one of"):
        sel_mod.parse_selection(_contract(lane="staging"), contract_sha256="x")


def test_valid_contract_parses_two_ordered_axes_and_one_condition():
    s = sel_mod.parse_selection(_contract(), contract_sha256="deadbeef")
    assert s.lane == "synthetic"
    assert (s.a.program_id, s.a.direction, s.a.sign) == ("program_a", "high", +1)
    assert (s.b.program_id, s.b.direction, s.b.sign) == ("program_b", "low", -1)
    assert s.analysis_condition == CONDITION
    assert s.selection_id == "s" * 16
    assert s.contract_sha256 == "deadbeef"
    # pending Stage-1 v3 validation is carried as an explicit null, not invented
    assert s.stage1_validation_sha256 is None


@pytest.mark.parametrize("method_version", [
    "stage1-continuous-v2",
    "stage1-continuous-v2.1",
    "stage1-continuous-v1",
    "stage1-balanced-v9",
    "",
])
def test_stale_or_unsupported_stage1_selections_are_rejected(method_version):
    c = _contract()
    c["hashes"]["method_version"] = method_version
    with pytest.raises(SelectionError):
        sel_mod.parse_selection(c, contract_sha256="x")


@pytest.mark.parametrize("key", ["objective", "balanced_a_to_b", "sensitivity"])
def test_contract_carrying_a_stage2_combination_objective_is_rejected(key):
    """The arm combination is Stage-2 descriptive output; it may not come back
    through Stage 1 as an executable objective."""
    with pytest.raises(SelectionError, match="never be handed back"):
        sel_mod.parse_selection(_contract(**{key: "balanced_a_to_b"}),
                                contract_sha256="x")


def test_identical_programs_rejected():
    with pytest.raises(SelectionError, match="same program"):
        sel_mod.parse_selection(
            _contract(A={"program_id": "p", "direction": "high"},
                      B={"program_id": "p", "direction": "low"}),
            contract_sha256="x")


@pytest.mark.parametrize("cond", ["All", "all_conditions", ""])
def test_non_executable_condition_rejected(cond):
    with pytest.raises(SelectionError, match="executable condition"):
        sel_mod.parse_selection(_contract(analysis_condition=cond),
                                contract_sha256="x")


def test_bad_direction_rejected():
    with pytest.raises(SelectionError, match="direction"):
        sel_mod.parse_selection(
            _contract(A={"program_id": "program_a", "direction": "up"}),
            contract_sha256="x")


def test_missing_selection_id_rejected():
    with pytest.raises(SelectionError, match="selection_id"):
        sel_mod.parse_selection(_contract(ids={"question_id": "q"}),
                                contract_sha256="x")


# --------------------------------------------------------------------------- #
# Registry / release binding (see test_trust_attacks.py for the forgery attacks).
# --------------------------------------------------------------------------- #
def test_ids_must_re_derive_from_the_science(tmp_path):
    """A contract cannot bless itself: the ids are derived, and a forged id simply
    fails to reproduce."""
    from fixtures_direct import derived_ids
    good = _contract()
    good["ids"] = derived_ids(good)
    sel = sel_mod.parse_selection(good, contract_sha256="x")
    check = sel_mod.recomputed_ids(sel)
    assert check["question_id_matches_declared"]
    assert check["selection_id_matches_declared"]

    forged = dict(good, ids={"question_id": "fx_deadbeef", "selection_id": "fx_beef"})
    bad = sel_mod.parse_selection(forged, contract_sha256="x")
    assert not sel_mod.recomputed_ids(bad)["question_id_matches_declared"]


def test_the_fixture_namespace_is_required_by_the_fixture_loader(tmp_path):
    path = str(tmp_path / "sel.json")
    write_selection(path, registry_sha="r" * 64, lane="synthetic")
    sel = sel_mod.load_fixture_selection(path)          # fx_ ids -> accepted
    assert sel.lane == "synthetic"
    assert sel.question_id.startswith("fx_")

    with pytest.raises(SelectionError, match="lane"):
        sel_mod.load_production_selection(path)


def test_load_selection_hashes_the_contract_file(tmp_path):
    path = str(tmp_path / "sel.json")
    write_selection(path, registry_sha="r" * 64)
    s = sel_mod.load_selection(path)
    assert len(s.contract_sha256) == 64
    assert s.stage1_method_version.startswith("stage1-continuous-v3")
