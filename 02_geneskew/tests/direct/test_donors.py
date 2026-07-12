"""Six overlapping donor-pair estimates are three complementary splits, not six."""
import pytest
from direct import donors

DONORS = ["D1", "D2", "D3", "D4"]
PAIRS = ["D1_D2", "D1_D3", "D1_D4", "D2_D3", "D2_D4", "D3_D4"]
EPS = 1e-9


def test_six_pairs_collapse_into_three_complementary_splits():
    out = donors.complementary_splits(PAIRS)
    assert out["status"] == donors.COMPLETE
    assert out["n_donors"] == 4
    assert out["n_splits"] == 3                    # NOT six replicates
    assert out["n_splits_expected"] == 3
    assert out["unpaired_pairs"] == []
    assert [s.split_id for s in out["splits"]] == [
        "D1_D2|D3_D4", "D1_D3|D2_D4", "D1_D4|D2_D3"]
    # every split partitions all four donors into two disjoint halves
    for s in out["splits"]:
        halves = set(s.half_a.split("_")) | set(s.half_b.split("_"))
        assert halves == set(DONORS)
        assert not (set(s.half_a.split("_")) & set(s.half_b.split("_")))


def test_donor_tokens_come_from_one_exact_parser_and_are_emitted_verbatim():
    real = ["CE0006864_CE0008162", "CE0008678_CE0010866",
            "CE0006864_CE0008678", "CE0008162_CE0010866",
            "CE0006864_CE0010866", "CE0008162_CE0008678"]
    out = donors.complementary_splits(real)
    assert out["donor_tokens"] == ["CE0006864", "CE0008162", "CE0008678",
                                   "CE0010866"]          # verbatim, not renamed
    assert out["status"] == donors.COMPLETE
    assert out["n_splits"] == 3
    assert donors.parse_pair_tokens("CE0006864_CE0008162") == \
        ("CE0006864", "CE0008162")


def test_an_unparseable_modality_name_is_a_hard_failure():
    for bad in ("CE0006864", "A_B_C", "_B", ""):
        with pytest.raises(donors.DonorTokenError):
            donors.parse_pair_tokens(bad)


def test_stage1_donor_crosswalk_is_never_guessed():
    tokens = ["CE0006864", "CE0008162", "CE0008678", "CE0010866"]
    absent = donors.donor_crosswalk(tokens, None)
    assert absent["status"] == "unavailable"
    assert absent["release_tokens"] == tokens
    assert absent["stage1_labels"] is None

    bound = donors.donor_crosswalk(tokens, {
        "donor_1": "CE0006864", "donor_2": "CE0008162",
        "donor_3": "CE0008678", "donor_4": "CE0010866"})
    assert bound["status"] == "bound"

    partial = donors.donor_crosswalk(tokens, {"donor_1": "CE0006864"})
    assert partial["status"] == "invalid"
    assert partial["unmapped_release_tokens"] == ["CE0008162", "CE0008678",
                                                  "CE0010866"]


def test_a_pair_without_its_complement_is_reported_not_dropped():
    out = donors.complementary_splits(["D1_D2", "D1_D3", "D2_D4"])
    assert out["status"] == donors.INCOMPLETE
    assert "D1_D2" in out["unpaired_pairs"]        # D3_D4 was not released
    assert [s.split_id for s in out["splits"]] == ["D1_D3|D2_D4"]


def _splits():
    return donors.complementary_splits(PAIRS)["splits"]


def test_split_is_evaluable_only_when_both_disjoint_halves_produced_a_value():
    values = {p: 1.0 for p in PAIRS}
    values["D3_D4"] = None                        # one half of split 1 missing
    out = donors.split_support(1.0, values, _splits(), EPS)
    assert out["n_splits_total"] == 3
    assert out["n_splits_evaluable"] == 2
    assert out["n_splits_missing"] == 1
    assert out["donor_split_support"] is False    # honest denominator, not 2/2
    missing = [r for r in out["rows"] if not r["evaluable"]]
    assert missing[0]["split_id"] == "D1_D2|D3_D4"
    assert missing[0]["missing_halves"] == "D3_D4"
    assert missing[0]["missing_reason"] == "half_estimate_unavailable"


def test_internal_discordance_between_the_two_donor_halves_is_reported():
    values = {p: 1.0 for p in PAIRS}
    values["D3_D4"] = -1.0                        # halves of split 1 disagree
    out = donors.split_support(1.0, values, _splits(), EPS)
    assert out["n_splits_evaluable"] == 3
    assert out["n_splits_internally_discordant"] == 1
    assert out["n_splits_internally_concordant"] == 2
    assert out["n_splits_agreeing_with_main"] == 2
    assert out["donor_split_support"] is False


def test_full_agreement_across_all_three_splits_supports():
    out = donors.split_support(1.0, {p: 1.0 for p in PAIRS}, _splits(), EPS)
    assert out["n_splits_evaluable"] == 3
    assert out["n_splits_agreeing_with_main"] == 3
    assert out["donor_split_support"] is True
    assert out["donor_split_support_denominator"] == 3


def test_support_requires_agreement_with_the_main_estimate_too():
    # both halves agree with each other, but against the main estimate
    out = donors.split_support(-1.0, {p: 1.0 for p in PAIRS}, _splits(), EPS)
    assert out["n_splits_internally_concordant"] == 3
    assert out["n_splits_agreeing_with_main"] == 0
    assert out["donor_split_support"] is False


def test_a_zero_signed_main_estimate_never_gains_support():
    out = donors.split_support(0.0, {p: 1.0 for p in PAIRS}, _splits(), EPS)
    assert out["donor_split_support"] is False


def test_no_evaluable_split_is_no_support():
    out = donors.split_support(1.0, {p: None for p in PAIRS}, _splits(), EPS)
    assert out["n_splits_evaluable"] == 0
    assert out["n_splits_missing"] == 3
    assert out["donor_split_support"] is False
