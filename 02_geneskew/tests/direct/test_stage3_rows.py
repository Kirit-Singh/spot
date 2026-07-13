"""THE STAGE-2 -> STAGE-3 ROW: the inversion, the wrong gene, and every sign case.

Two failures are being made impossible here, and both of them are silent:

  1. Stage 3 reading the PROGRAM direction as the TARGET direction, and prescribing an
     agonist for a target whose knockdown helped.
  2. A namespace guessed from the shape of an id, attaching the wrong gene to a drug —
     three of the four symbol targets carry an ENSG-looking key belonging to another gene.

Every value here is a FIXTURE. What is real is the refusal.
"""
from __future__ import annotations

import os
import sys

import pytest
from direct import stage3_rows as S

# The verifier's modules are loaded FLAT — as the verifier process loads them, not as part of
# the producer's package. Importing it as `direct.verify_stage3_rows` would quietly give it
# the producer's import graph, which is the one thing it is supposed not to have.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "analysis", "direct"))
import verify_stage3_rows as V  # noqa: E402

# A fixture universe: two Ensembl targets and one of the four real symbol targets.
UNIVERSE = {
    "ENSG00000111111": S.ENSEMBL_GENE_ID,
    "ENSG00000222222": S.ENSEMBL_GENE_ID,
    "OCLM": S.GENE_SYMBOL,
}

CTX = {"condition": "Stim48hr"}


def _native(lane="direct", target="ENSG00000111111", value=0.5, evaluable=True, rank=1):
    spec = S.NATIVE_ROW[lane]
    row = {"target_id": target, spec["value_field"]: value, "rank": rank}
    if spec["evaluable_field"]:
        row[spec["evaluable_field"]] = evaluable
    return row


def _row(lane="direct", program_effect_direction="increase", **kw):
    return S.build_row(
        lane=lane, native=_native(lane, **kw), arm_key=f"{lane}|PRG-1|"
        f"{program_effect_direction}|condition=Stim48hr", program_id="PRG-1",
        program_effect_direction=program_effect_direction,
        namespace_of=UNIVERSE, context=CTX)


class TestTheThreeThingsAreSaidSEPARATELY:
    """What was DONE, the PROGRAM axis, and what is IMPLIED — three fields, never one."""

    def test_the_assay_is_on_the_row_and_is_not_a_direction(self):
        row = _row()
        assert row["observed_perturbation_modality"] == "CRISPRi_knockdown"
        assert row["perturbation_target_effect"] == "target_transcript_reduced"

    def test_the_modality_is_the_SAME_whatever_the_program_direction(self):
        """The assay does not change because we want the program to go the other way."""
        up = _row(program_effect_direction="increase")
        down = _row(program_effect_direction="decrease")
        assert (up["observed_perturbation_modality"]
                == down["observed_perturbation_modality"] == "CRISPRi_knockdown")

    def test_the_claim_is_a_PHENOCOPY_and_never_an_EQUIVALENCE(self):
        row = _row()
        assert row["phenocopy_claim"] == "putative_crispri_phenocopy"
        assert row["claim_is_equivalence"] is False


class TestTheSignRule:
    """The whole pharmacology, one sign at a time."""

    @pytest.mark.parametrize("program_direction", ["increase", "decrease"])
    def test_POSITIVE_means_inhibition_is_observed_compatible(self, program_direction):
        """Positive = the knockdown moved the program the desired way. EITHER way.

        This is the test that would have caught the inversion: the answer is `decrease`
        (inhibit the target) whether the program was meant to go UP or DOWN.
        """
        row = _row(program_effect_direction=program_direction, value=0.42)
        assert row["desired_target_modulation"] == "decrease"
        assert row["phenocopy_class"] == "inhibition_observed_compatible"
        assert S.is_supported(row) is True

    @pytest.mark.parametrize("program_direction", ["increase", "decrease"])
    def test_NEGATIVE_means_an_inhibitor_is_OPPOSED_not_an_agonist_SUPPORTED(
            self, program_direction):
        """A sign inversion is not a recommendation. No CRISPRa arm was ever run."""
        row = _row(program_effect_direction=program_direction, value=-0.42)
        assert row["desired_target_modulation"] == "increase"
        assert row["phenocopy_class"] == "inhibitor_opposed"
        # ...and it is NOT supported evidence for anything
        assert S.is_supported(row) is False

    def test_NEAR_ZERO_is_no_directional_response(self):
        row = _row(value=1e-12)
        assert row["desired_target_modulation"] == "no_direction_evidence"
        assert row["phenocopy_class"] == "no_directional_response"

    def test_NOT_EVALUABLE_is_not_a_direction(self):
        row = _row(value=0.9, evaluable=False)
        assert row["desired_target_modulation"] == "not_evaluated"
        assert row["phenocopy_class"] == "not_evaluable"
        assert S.is_supported(row) is False

    def test_a_NULL_value_is_not_evaluated_not_no_direction(self):
        row = _row(value=None)
        assert row["desired_target_modulation"] == "not_evaluated"


class TestStage3MayOnlyMatchInhibitorsToObservedCompatibleRows:
    def test_the_policy_names_the_ONE_class_an_inhibitor_may_match(self):
        p = S.STAGE3_MATCHING_POLICY
        assert p["inhibitory_or_downregulating_mechanisms_may_match"] == [
            "inhibition_observed_compatible"]
        assert p["rankable_as_supported"] == ["inhibition_observed_compatible"]
        assert p["must_flag_opposition"] == ["inhibitor_opposed"]

    def test_an_agonist_is_NEVER_promoted_from_a_sign_inversion(self):
        assert S.STAGE3_MATCHING_POLICY["agonist_promotion_from_sign_inversion"] is False

    def test_an_unresolved_namespace_is_REFUSED_not_dropped(self):
        assert S.STAGE3_MATCHING_POLICY["unresolved_namespace"] == "refuse_never_silently_drop"


class TestTheNamespaceIsDECLAREDNeverSniffed:
    def test_a_symbol_target_keeps_its_symbol_namespace(self):
        row = _row(target="OCLM")
        assert row["target_id_namespace"] == "gene_symbol"

    def test_a_target_OUTSIDE_the_universe_is_REFUSED_not_guessed(self):
        """It LOOKS like an Ensembl id. That is exactly the trap: three of the four symbol
        targets carry an ENSG-looking release key belonging to a DIFFERENT gene."""
        with pytest.raises(S.RowContractError, match="unresolved_target_identity"):
            _row(target="ENSG00000999999")

    def test_the_universe_is_11522_ensembl_plus_the_4_known_symbols(self):
        """The documented expectation, so a change in the release is noticed, not absorbed."""
        assert S.EXPECTED_UNIVERSE == {"n_targets": 11526, "n_ensembl": 11522, "n_symbol": 4}
        assert S.KNOWN_SYMBOL_TARGETS == ("MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM")


class TestTheThreeNativeRowShapes:
    """Direct says `value`, temporal says `arm_value`, pathway says `score`."""

    @pytest.mark.parametrize("lane,field", [("direct", "value"), ("temporal", "arm_value"),
                                            ("pathway", "score")])
    def test_each_lane_value_is_read_from_ITS_OWN_field(self, lane, field):
        assert S.NATIVE_ROW[lane]["value_field"] == field
        row = _row(lane=lane, value=0.7)
        assert row["arm_value"] == 0.7
        assert row["desired_target_modulation"] == "decrease"

    def test_pathway_rankings_carry_no_evaluable_and_are_evaluable_by_construction(self):
        assert S.NATIVE_ROW["pathway"]["evaluable_field"] is None
        assert _row(lane="pathway", value=0.3)["evaluable"] is True

    def test_a_lane_that_SHIPS_a_modulation_must_AGREE_with_its_own_number(self):
        """temporal ships `desired_target_modulation`. A bundle whose label disagrees with
        its own value is refused — that disagreement IS the inversion, pre-baked."""
        native = _native("temporal", value=0.5)
        native["desired_target_modulation"] = "increase"          # the lie
        with pytest.raises(S.RowContractError, match="re-derives"):
            S.build_row(lane="temporal", native=native,
                        arm_key="temporal|PRG-1|increase|condition=Stim48hr",
                        program_id="PRG-1", program_effect_direction="increase",
                        namespace_of=UNIVERSE, context=CTX)


class TestTheINDEPENDENTVerifierMUTATIONS:
    """Each mutation is a plausible, internally-tidy row. Each must be REFUSED."""

    def test_a_clean_row_is_admitted(self):
        assert V.verify_row(_row(), universe=UNIVERSE) == []

    def test_THE_INVERSION_modulation_taken_from_the_PROGRAM_direction(self):
        """The bug itself: `desired_target_modulation` set to the program direction.

        The row is entirely self-consistent to a reader who does not re-derive. The arm value
        is positive — the knockdown HELPED — so an inhibitor is indicated; but the program
        direction is `increase`, and a Stage 3 reading THAT would look for an agonist.
        """
        row = _row(program_effect_direction="increase", value=0.5)
        row["desired_target_modulation"] = row["program_effect_direction"]   # increase
        row["phenocopy_class"] = "inhibitor_opposed"

        bad = V.verify_row(row, universe=UNIVERSE)
        assert any(V.G_DIRECTION in b for b in bad)
        assert any("never from the PROGRAM direction" in b for b in bad)

    def test_an_AGONIST_promoted_from_a_negative_value_is_REFUSED(self):
        row = _row(value=-0.5)
        row["desired_target_modulation"] = "increase"     # true...
        row["phenocopy_class"] = "inhibition_observed_compatible"   # ...but not SUPPORT
        row["supported"] = True

        bad = V.verify_row(row, universe=UNIVERSE)
        assert any(V.G_NO_AGONIST in b for b in bad)
        assert any("does not support an agonist" in b for b in bad)

    def test_a_ROW_ORIENTED_AGAINST_THE_WRONG_ARM_is_REFUSED(self):
        """Its sign means the opposite of what it says."""
        row = _row(program_effect_direction="increase")
        row["program_effect_direction"] = "decrease"      # the arm_key still says increase
        assert any(V.G_ORIENTATION in b for b in V.verify_row(row, universe=UNIVERSE))

    def test_a_SNIFFED_namespace_on_an_out_of_universe_target_is_REFUSED(self):
        row = _row()
        row["target_id"] = "ENSG00000999999"              # looks right; is not in the universe
        bad = V.verify_row(row, universe=UNIVERSE)
        assert any(V.G_NAMESPACE in b for b in bad)
        assert any("never drop it silently" in b for b in bad)

    def test_a_SYMBOL_target_relabelled_ensembl_is_REFUSED(self):
        row = _row(target="OCLM")
        row["target_id_namespace"] = "ensembl_gene_id"
        assert any(V.G_NAMESPACE in b for b in V.verify_row(row, universe=UNIVERSE))

    def test_a_ROW_CLAIMING_EQUIVALENCE_is_REFUSED(self):
        row = _row()
        row["claim_is_equivalence"] = True
        bad = V.verify_row(row, universe=UNIVERSE)
        assert any("An inhibitor is not a" in b for b in bad)

    def test_a_ROW_WITH_A_FOREIGN_MODALITY_is_REFUSED(self):
        row = _row()
        row["observed_perturbation_modality"] = "CRISPRa_activation"   # nobody ran this
        bad = V.verify_row(row, universe=UNIVERSE)
        assert any(V.G_MODALITY in b for b in bad)
        assert any("a perturbation nobody performed" in b for b in bad)

    def test_a_ROW_MISSING_THE_NAMESPACE_ENTIRELY_is_REFUSED(self):
        row = _row()
        del row["target_id_namespace"]
        assert any(V.G_FIELDS in b for b in V.verify_row(row, universe=UNIVERSE))

    @pytest.mark.parametrize("value,want", [(0.5, "inhibition_observed_compatible"),
                                            (-0.5, "inhibitor_opposed"),
                                            (0.0, "no_directional_response")])
    def test_the_verifier_RE_DERIVES_every_sign_case(self, value, want):
        rows = [_row(value=value)]
        report = V.verify_rows(rows, universe=UNIVERSE)
        assert report["verdict"] == "admit"
        assert report["rows_by_phenocopy_class"] == {want: 1}


class TestTheProducersTokensHaveNotDRIFTED:
    """A PIN TEST. My contract restates the producers' vocabulary; if theirs moves, this
    breaks — rather than the two quietly meaning different things by the same word."""

    def test_the_modality_token_is_the_producers_own(self):
        from direct import config
        assert S.OBSERVED_PERTURBATION_MODALITY == config.CRISPRI_MODALITY

    def test_the_sign_epsilon_is_the_producers_own(self):
        from direct import config
        assert S.SIGN_EPS == config.SIGN_EPS
        assert V.SIGN_EPS == config.SIGN_EPS

    def test_the_modulation_tokens_are_the_producers_own(self):
        from direct import disposition
        assert S.MOD_DECREASE == disposition.MOD_DECREASE
        assert S.MOD_INCREASE == disposition.MOD_INCREASE
        assert S.MOD_NO_DIRECTION == disposition.MOD_NO_DIRECTION
        assert S.MOD_NOT_EVALUATED == disposition.MOD_NOT_EVALUATED

    def test_the_namespace_enum_is_the_producers_own(self):
        from direct import identity
        assert S.NAMESPACES == identity.NAMESPACES

    def test_MY_sign_rule_agrees_with_the_PRODUCERS_on_every_case(self):
        """The producer decides; I re-derive. On these four cases they must agree exactly."""
        from direct import disposition
        for value in (0.5, -0.5, 0.0, 1e-12, None):
            for evaluable in (True, False):
                assert S.desired_target_modulation(value, evaluable=evaluable) == \
                    disposition.desired_modulation(value, evaluable=evaluable)
