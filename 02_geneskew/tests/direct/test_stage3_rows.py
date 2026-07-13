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


def _record(target="ENSG00000111111", value=0.5, evaluable=True, rank=1):
    """A SEAM-B row: the ADMITTED, NORMALIZED ranking record. What Stage 3 actually reads."""
    return {"target_id": target, "arm_value": value, "evaluable": evaluable, "rank": rank}


def _identity(target="ENSG00000111111", lane="temporal", **kw):
    """The record the ranking row JOINS to. Identity lives here, never on the arm row.

    Each lane declares the assay in its OWN field — Direct's screen rows say
    `crispri_modality`, temporal's base_records say `perturbation_modality`.
    """
    rec = {"target_id": target, "target_id_namespace": UNIVERSE[target],
           "target_symbol": "SYM", "target_ensembl": target if target.startswith("ENSG")
           else None,
           S.IDENTITY_JOIN[lane]["modality_field"]: "CRISPRi_knockdown"}
    rec.update(kw)
    return rec


def _row(lane="temporal", program_effect_direction="increase", target="ENSG00000111111",
         identity=None, **kw):
    return S.build_row(
        lane=lane, record=_record(target=target, **kw),
        identity=(identity if identity is not None else
                  # pathway has no identity join at all — the builder must refuse the LANE,
                  # and it must get that far
                  _identity(target, lane) if lane in S.TARGET_EVIDENCE_LANES else {"x": 1}),
        arm_key=f"{lane}|PRG-1|{program_effect_direction}|condition=Stim48hr",
        program_id="PRG-1", program_effect_direction=program_effect_direction,
        context=CTX)


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
    def test_the_universe_is_11522_ensembl_plus_the_4_known_symbols(self):
        """The documented expectation, so a change in the release is noticed, not absorbed."""
        assert S.EXPECTED_UNIVERSE == {"n_targets": 11526, "n_ensembl": 11522, "n_symbol": 4}
        assert S.KNOWN_SYMBOL_TARGETS == ("MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM")


class TestTheTWOSEAMSAndWhichOneStage3Reads:
    """SEAM A is raw and per-lane. SEAM B is the admitted, normalized, BOUND ranking."""

    def test_stage3_reads_the_NORMALIZED_record_not_a_raw_producer_shape(self):
        assert S.NORMALIZED_ROW_FIELDS == ("target_id", "arm_value", "evaluable", "rank")
        # ...and that IS the bound ranking artifact's row, per arm_topology
        from direct.arm_topology import ARM_RANKING_ROWS
        assert S.RANKING_RECORDS_KEY == ARM_RANKING_ROWS == "records"

    def test_a_RAW_producer_row_is_REFUSED_by_the_row_builder(self):
        """Direct's raw arm row says `value`. Handing it straight to Stage 3 would read
        arm_value=None -> `not_evaluated`: silent, plausible, and wrong."""
        raw = {"target_id": "ENSG00000111111", "arm_value": 0.5, "evaluable": True}  # no rank
        with pytest.raises(S.RowContractError, match="never a raw producer shape"):
            S.build_row(lane="temporal", record=raw, identity=_identity(),
                        arm_key="temporal|PRG-1|increase|condition=Stim48hr",
                        program_id="PRG-1", program_effect_direction="increase", context=CTX)

    def test_the_ADAPTER_normalizes_a_raw_row_explicitly(self):
        raw = {"target_id": "ENSG00000111111", "value": 0.5, "evaluable": True, "rank": 1}
        assert S.normalize_raw_row("direct", raw) == _record()

    def test_temporals_raw_row_already_says_arm_value(self):
        raw = {"target_id": "ENSG00000111111", "arm_value": 0.5, "evaluable": True, "rank": 1}
        assert S.normalize_raw_row("temporal", raw) == _record()


class TestPathwayIsNOTATargetEvidenceLane:
    """Its records are one per (arm x GENE SET): an enrichment value and a leading edge."""

    def test_pathway_is_not_a_target_evidence_lane(self):
        assert S.TARGET_EVIDENCE_LANES == ("direct", "temporal")
        assert S.PATHWAY_LANE_ROLE["carries_crispri_target_rows"] is False

    def test_a_PATHWAY_target_row_is_REFUSED_by_the_builder(self):
        with pytest.raises(S.RowContractError, match="not a target-evidence lane"):
            _row(lane="pathway")

    def test_pathway_has_NO_raw_target_row_to_normalize(self):
        assert S.RAW_PRODUCER_ROW["pathway"] is None
        with pytest.raises(S.RowContractError, match="no raw TARGET row"):
            S.normalize_raw_row("pathway", {"gene_set_id": "GO:1", "enrichment_value": 2.0})

    def test_pathway_context_reads_the_NATIVE_set_id_field(self):
        """The producer names its gene sets `set_id`. A `.get("gene_set_id")` against these
        bytes returns None on every record, forever, and nothing would ever say so."""
        assert S.PATHWAY_SET_ID_FIELD == "set_id"
        native = {"set_id": "GO:0006955", "enrichment_value": 2.4,
                  "leading_edge": ["ENSG00000111111"]}
        ctx = S.pathway_context(arm_key="pathway|PRG-1|increase|condition=Stim48hr",
                                program_id="PRG-1", record=native, context=CTX,
                                namespace_of=UNIVERSE)
        assert ctx["gene_set_id"] == "GO:0006955"
        assert ctx["enrichment_value"] == 2.4

    def test_every_LEADING_EDGE_target_carries_its_OWN_explicit_namespace(self):
        """This is what lets Stage 3 walk a pathway to its genes and then to a drug."""
        native = {"set_id": "GO:1", "enrichment_value": 2.0,
                  "leading_edge": ["ENSG00000111111", "OCLM"]}
        ctx = S.pathway_context(arm_key="pathway|p|increase|condition=X", program_id="p",
                                record=native, context=CTX, namespace_of=UNIVERSE)
        assert [e["target_id_namespace"] for e in ctx["leading_edge"]] == [
            "ensembl_gene_id", "gene_symbol"]
        assert ctx["n_leading_edge_joinable"] == 2

    def test_an_UNRESOLVED_leading_edge_target_is_explicitly_NON_JOINABLE_not_sniffed(self):
        """Never dropped so the pathway looks cleaner than its evidence."""
        native = {"set_id": "GO:1", "enrichment_value": 2.0,
                  "leading_edge": ["ENSG00000999999"]}      # looks Ensembl; is not in the map
        ctx = S.pathway_context(arm_key="pathway|p|increase|condition=X", program_id="p",
                                record=native, context=CTX, namespace_of=UNIVERSE)
        e = ctx["leading_edge"][0]
        assert e["joinable"] is False and e["target_id_namespace"] is None
        assert e["status"] == S.LEADING_EDGE_NON_JOINABLE
        assert ctx["n_leading_edge"] == 1 and ctx["n_leading_edge_joinable"] == 0

    def test_a_pathway_record_using_the_CONTRACTS_name_is_REFUSED(self):
        """`gene_set_id` is MY word. The producer's bytes say `set_id`, and a record that
        does not carry the producer's field is not one of the producer's records."""
        with pytest.raises(S.RowContractError, match="set_id"):
            S.pathway_context(arm_key="pathway|p|increase|condition=X", program_id="p",
                              record={"gene_set_id": "GO:1", "enrichment_value": 2.0},
                              context=CTX, namespace_of=UNIVERSE)

    def test_pathway_context_CARRIES_the_refusal_on_the_record(self):
        native = {"set_id": "GO:0006955", "enrichment_value": 2.4,
                  "leading_edge": ["ENSG00000111111"]}
        ctx = S.pathway_context(arm_key="pathway|PRG-1|increase|condition=Stim48hr",
                                program_id="PRG-1", record=native, context=CTX,
                                namespace_of=UNIVERSE)
        assert ctx["is_a_crispri_target_row"] is False
        assert ctx["may_be_matched_to_a_drug_as_a_target"] is False
        assert "leading_edge" in ctx["links_to_targets_via"]
        # it carries an ENRICHMENT value — a statement about a GENE SET, not about a target
        assert "arm_value" not in ctx and "desired_target_modulation" not in ctx


class TestIdentityIsJOINEDNeverSniffed:
    def test_the_join_key_is_the_lanes_own(self):
        assert S.IDENTITY_JOIN["temporal"]["join_on"] == "base_key"
        assert S.IDENTITY_JOIN["temporal"]["record"] == "base_records"

    def test_a_row_with_NO_joined_identity_is_REFUSED_not_dropped(self):
        with pytest.raises(S.RowContractError, match="unresolved_target_identity"):
            _row(identity={})

    def test_a_join_that_LANDS_ON_ANOTHER_TARGET_is_REFUSED(self):
        """The wrong gene attached to a drug — silently, and with a valid-looking row."""
        with pytest.raises(S.RowContractError, match="wrong gene"):
            _row(target="ENSG00000111111", identity=_identity("ENSG00000222222"))

    def test_a_symbol_target_keeps_its_JOINED_symbol_namespace(self):
        assert _row(target="OCLM")["target_id_namespace"] == "gene_symbol"

    def test_the_MODALITY_is_read_off_the_joined_record_not_asserted(self):
        bad = _identity()
        bad["perturbation_modality"] = "CRISPRa_activation"
        with pytest.raises(S.RowContractError, match="one assay"):
            _row(identity=bad)

    def test_a_MISSING_modality_REFUSES_and_is_NEVER_defaulted_to_CRISPRi(self):
        """THE FAIL-OPEN THIS CLOSES. The field was defaulted, so a row with its modality
        DELETED sailed through and was classed `inhibition_observed_compatible`. The row
        exists to stop a drug direction being assumed — and it was assuming the ASSAY."""
        blank = _identity()
        del blank["perturbation_modality"]
        with pytest.raises(S.RowContractError, match=S.G_MODALITY_ABSENT):
            _row(identity=blank)

    def test_TEMPORAL_declares_the_assay_on_the_record_it_joins_to(self):
        assert S.IDENTITY_JOIN["temporal"]["modality_field"] == "perturbation_modality"
        assert S.IDENTITY_JOIN["temporal"]["record"] == "base_records"

    def test_DIRECT_binds_NO_identity_source_and_therefore_BUILDS_NO_ROWS(self):
        """The native all-arm bundle has NO screen.parquet and no identity table.

        arm_artifacts.VERIFIED_PATHS is arm_bundle/provenance/arms/masks/contributing_guides/
        guide_support/donor_support/input_manifest/gene_universe. `arms` carries target_id and
        nothing else; masks and contributing_guides omit the namespace and the symbol;
        provenance.target_identity_map is optional metadata plus a hash; and the CRISPRi
        modality exists only in config and is never emitted. So Direct cannot say, in bound
        bytes, who a target is or what was done to it — and a contract that named a file which
        does not exist would pass fixtures and fail on the release.
        """
        assert "direct" not in S.IDENTITY_JOIN
        with pytest.raises(S.RowContractError, match=S.G_NO_IDENTITY_SOURCE):
            S.build_row(lane="direct", record=_record(), identity={"target_id": "X"},
                        arm_key="direct|PRG-1|increase|condition=Stim48hr",
                        program_id="PRG-1", program_effect_direction="increase", context=CTX)

    def test_the_DIRECT_producer_requirement_is_stated_as_a_contract(self):
        req = S.DIRECT_IDENTITY_REQUIREMENT
        # ONE shared constant: producer, W10, P2S and the bridge all bind THIS file.
        assert req["file"] == S.TARGET_IDENTITY_FILE == "target_identity.json"
        assert req["schema_version"] == "spot.stage02_target_identity.v1"
        assert req["required_columns"] == ("target_id", "target_id_namespace",
                                           "target_symbol", "target_ensembl",
                                           "observed_perturbation_modality")


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

    def test_a_PATHWAY_ENRICHMENT_record_smuggled_in_as_a_target_row_is_REFUSED(self):
        """The masquerade: an enrichment value read as a target's arm value."""
        row = _row()
        row["lane"] = "pathway"
        bad = V.verify_row(row, universe=UNIVERSE)
        assert any(V.G_LANE in b for b in bad)
        assert any("not a measurement of a target under knockdown" in b for b in bad)

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


class TestTheTwoNORMALIZERSAreIndependentAndAGREE:
    """The producer has `bundle_shapes`; the verifier restates the shapes in
    `verify_manifest_rules`. Two copies on purpose — a verifier that imported the producer's
    normalizer would identify a lane exactly the way the producer does, agree by
    construction, and be unable to catch it mis-identifying one.

    So: they must never IMPORT one another, and they must never DISAGREE.
    """

    def test_the_verifier_does_NOT_import_the_producers_normalizer(self):
        import verify_manifest_rules as R
        assert "bundle_shapes" not in str(getattr(R, "__dict__", {}).keys())

    @pytest.mark.parametrize("lane", ["direct", "temporal", "pathway"])
    def test_the_two_restatements_AGREE_on_every_lane(self, lane):
        import verify_manifest_rules as R
        from direct import bundle_shapes as BS

        producer = BS.NATIVE_BUNDLE[lane]
        verifier = R.NATIVE_BUNDLE_SHAPE[lane]
        assert producer["schema_version"] == verifier["schema"]
        assert producer["id_field"] == verifier["id_field"]
        assert producer["context_fields"] == verifier["context_fields"]

    @pytest.mark.parametrize("lane", ["direct", "temporal", "pathway"])
    def test_they_NORMALIZE_a_real_native_bundle_identically(self, lane):
        import verify_manifest_rules as R
        from direct import bundle_shapes as BS

        spec = BS.NATIVE_BUNDLE[lane]
        doc = {"schema_version": spec["schema_version"], spec["id_field"]: "B-1", "arms": []}
        doc.update({f: f"v-{f}" for f in spec["context_fields"]})

        p, v = BS.normalize(doc), R.native_view(doc)
        assert (p["lane"], p["bundle_id"], p["context"]) == \
               (v["lane"], v["bundle_id"], v["context"])

    def test_BOTH_refuse_a_schema_that_names_no_lane(self):
        import verify_manifest_rules as R
        from direct import bundle_shapes as BS
        from direct.arm_topology import RunManifestError

        doc = {"schema_version": "spot.stage02_direct_arm_bundle.v2", "arms": []}
        assert R.native_view(doc) is None
        with pytest.raises(RunManifestError, match="no known lane"):
            BS.normalize(doc)


# --------------------------------------------------------------------------- #
# THE EXACT GENERATED BYTES. Not a hand-built dict that agrees with me by construction:
# the ranking files the real CLIs wrote into the W3 native-contract handoff.
# --------------------------------------------------------------------------- #
HANDOFF = os.path.join(os.path.expanduser("~"), ".spot-runs", "20260712T021343Z",
                       "W3_NATIVE_CONTRACT")


def _generated_rankings(lane):
    d = os.path.join(HANDOFF, f"example_bundle_{lane}", "rankings")
    if not os.path.isdir(d):
        pytest.skip(f"the generated {lane} bundle is not on this host")
    return [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".json")]


class TestOverTheEXACTGeneratedRankingFiles:
    """Whatever I believe the shape is, THESE are the bytes that shipped."""

    @pytest.mark.parametrize("lane", ["direct", "temporal", "pathway"])
    def test_every_generated_ranking_row_is_the_NORMALIZED_shape(self, lane):
        import json
        for path in _generated_rankings(lane):
            doc = json.load(open(path))
            assert S.RANKING_RECORDS_KEY in doc, f"{path}: no {S.RANKING_RECORDS_KEY!r}"
            for rec in doc[S.RANKING_RECORDS_KEY]:
                missing = [f for f in S.NORMALIZED_ROW_FIELDS if f not in rec]
                assert not missing, f"{path}: a record is missing {missing}"

    @pytest.mark.parametrize("lane", ["temporal"])
    def test_the_generated_TARGET_lanes_build_admissible_stage3_rows(self, lane):
        """End to end, on real bytes: bound ranking + joined identity -> an admitted row."""
        import json
        rows = []
        for path in _generated_rankings(lane):
            doc = json.load(open(path))
            program = os.path.basename(path).rsplit(".", 1)[0]
            program_id, change = program.split("__")
            for rec in doc[S.RANKING_RECORDS_KEY]:
                ident = {"target_id": rec["target_id"],
                         "target_id_namespace": S.GENE_SYMBOL,
                         "target_symbol": rec["target_id"], "target_ensembl": None,
                         S.IDENTITY_JOIN[lane]["modality_field"]: "CRISPRi_knockdown"}
                rows.append(S.build_row(
                    lane=lane, record=rec, identity=ident,
                    arm_key=f"{lane}|{program_id}|{change}|condition=X",
                    program_id=program_id, program_effect_direction=change,
                    context={"condition": "X"}))

        assert rows, f"the generated {lane} bundle bound no ranking rows"
        universe = {r["target_id"]: S.GENE_SYMBOL for r in rows}
        report = V.verify_rows(rows, universe=universe)
        assert report["verdict"] == "admit", report["failures"][:3]
        # ...and the direction really was re-derived, not copied off the program axis
        assert report["n_inhibition_observed_compatible"] + report["n_inhibitor_opposed"] > 0

    def test_the_generated_PATHWAY_rankings_may_NOT_become_target_rows(self):
        """They carry the normalized shape — but the lane still does not carry TARGET
        evidence, and the builder refuses it. Shape is not provenance."""
        import json
        path = _generated_rankings("pathway")[0]
        rec = json.load(open(path))[S.RANKING_RECORDS_KEY][0]
        with pytest.raises(S.RowContractError, match="not a target-evidence lane"):
            S.build_row(lane="pathway", record=rec, identity=_identity(),
                        arm_key="pathway|p|increase|condition=X", program_id="p",
                        program_effect_direction="increase", context={"condition": "X"})
