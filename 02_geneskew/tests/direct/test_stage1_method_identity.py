"""The contract's `estimator.method_sha256`: BOUND, PRESERVED, and NOT re-derived here.

TWO DIFFERENT HASHES WEAR THE NAME `method_sha256`, and conflating them is the bug this file
exists to prevent:

  1. THE CONTRACT'S — Stage-1's ESTIMAND-IDENTITY hash: what is being estimated (a
     population-level difference-in-differences on program projections). Stage-1 says in so
     many words that it is NOT a code-tree or batch-policy hash. It is minted in the
     temporal-arms lane and this lane cannot recompute it.
  2. THIS BRANCH'S — `estimator_registry()[...]["method_sha256"]`: an IMPLEMENTATION binding
     over the temporal code trees and the frozen batch policy. WHICH CODE would run.

They answer different questions, they are not equal, and they are not supposed to be. A gate
that compared them would REFUSE the authoritative Stage-1 contract — a false refusal, which
is exactly as damaging as a false admission. Worse, the code-tree hash MOVES on every code
edit (see the test below), so such a gate would break the contract every time anyone touched
Stage-2.

So the declared identity is carried verbatim through bytes that ARE proved (the contract's own
content hash, the pinned schema, the admitted release), it is LABELLED as not-locally-derived,
and the re-derivation of the implementation binding is left to its owner: the temporal
producer/verifier (W5/W11). The absence of that check is a DECLARED LIMIT with a name, not a
silence a reader has to interpret.
"""
from __future__ import annotations

import copy

import fixtures_stage1_contract as S1
import pytest
from direct import stage1_v3 as G
from direct.hashing import content_hash
from test_stage1_v3 import SCHEMA_PATH, emit

pytestmark = pytest.mark.skipif(
    not SCHEMA_PATH, reason="the pinned v3 schema is not present")


@pytest.fixture(scope="module")
def schema():
    return G.load_schema(SCHEMA_PATH)


def _resealed(doc):
    payload = {k: v for k, v in doc.items() if k != "full_contract_content_sha256"}
    doc["full_contract_content_sha256"] = content_hash(payload)
    return doc


def temporal(**over):
    return emit(mode=G.MODE_TEMPORAL, conditions=["Stim8hr", "Stim48hr"], **over)


class TestTheDeclaredIdentityIsPRESERVED:
    def test_the_REAL_contracts_method_hash_survives_verbatim(self, schema):
        """The authoritative bytes, through the gate, unchanged."""
        doc = S1.producer_fixture("temporal_ready")
        mi = G.validate(doc, schema)["estimator_method_identity"]
        assert mi["method_sha256"] == S1.TEMPORAL_METHOD_SHA256
        assert mi["method_sha256"] == doc["estimator"]["method_sha256"]
        assert mi["method_id"] == "spot.stage02.temporal_cross_condition.v1"
        assert mi["declared"] is True

    def test_it_travels_into_the_RUN_IDENTITY(self, schema):
        """Bound into the run binding — so a run cannot be re-attributed to another method."""
        doc = temporal()
        sel = G.as_selection(G.validate(doc, schema), doc, lane="production")
        block = G.binding_block(sel)
        assert block["estimator_method_identity"]["method_sha256"] == \
            doc["estimator"]["method_sha256"]

    def test_a_WITHIN_condition_contract_declares_NO_method_and_says_so(self, schema):
        """Stage-1 binds no method block for the within estimator. Absent != faked."""
        mi = G.validate(emit(), schema)["estimator_method_identity"]
        assert mi["declared"] is False
        assert "method_sha256" not in mi
        assert mi["rederived_by_stage2_direct"] is False


class TestTheLIMITIsDECLAREDNotSilent:
    def test_the_binding_says_it_was_NOT_rederived_and_names_the_OWNER(self, schema):
        mi = G.validate(temporal(), schema)["estimator_method_identity"]
        assert mi["rederived_by_stage2_direct"] is False
        assert mi["rule_id"] == G.METHOD_IDENTITY_RULE_ID
        assert mi["rederivation_owner"] == G.METHOD_IDENTITY_REDERIVATION_OWNER
        assert "W5_W11" in mi["rederivation_owner"]
        assert mi["not_rederived_because"]

    def test_the_binding_says_WHAT_KIND_of_hash_it_is_and_what_it_is_NOT(self, schema):
        mi = G.validate(temporal(), schema)["estimator_method_identity"]
        assert mi["identity_kind"] == "stage1_estimand_identity_hash"
        assert mi["is_not"] == "stage2_implementation_code_tree_hash"

    def test_it_names_the_PROVED_bytes_that_anchor_it(self, schema):
        """Not re-derived is not unanchored: it rides inside bytes that ARE proved."""
        mi = G.validate(temporal(), schema)["estimator_method_identity"]
        assert set(mi["anchored_by"]) == {"full_contract_content_sha256",
                                          "selection_schema_sha256",
                                          "admitted_stage1_v3_release"}

    def test_editing_the_method_hash_in_flight_BREAKS_the_contract_hash(self, schema):
        """The anchor doing its work: the declared identity cannot be swapped in transit."""
        doc = temporal()
        doc["estimator"]["method_sha256"] = "d" * 64        # NOT resealed
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        assert exc.value.reason == G.REFUSE_CONTENT_HASH


class TestTheTwoHashesAreNEVERCONFLATED:
    def test_they_are_DIFFERENT_quantities_and_the_gate_does_not_compare_them(self, schema):
        """The real contract admits even though the two hashes differ. That is the point."""
        doc = S1.producer_fixture("temporal_ready")
        bound = G.validate(doc, schema)          # admits
        declared = bound["estimator_method_identity"]["method_sha256"]
        local = G.estimator_registry()[G.ESTIMATOR_TEMPORAL]["method_sha256"]
        assert declared == S1.TEMPORAL_METHOD_SHA256
        assert declared != local                 # different quantities, by construction
        assert bound["execution_status"] == G.EXECUTION_READY

    def test_the_LOCAL_hash_moves_when_the_CODE_moves_and_the_declared_one_does_not(self):
        """WHY a comparison gate would be wrong, demonstrated rather than argued.

        The local hash binds code trees, so it moves whenever Stage-2 is edited — this repair
        moved it. The contract's estimand identity is a statement about WHAT is estimated and
        does not move. A gate comparing them would refuse the authoritative contract every
        time anyone touched Stage-2, which is not a safety property; it is an outage.
        """
        local = G.estimator_registry()[G.ESTIMATOR_TEMPORAL]["method_sha256"]
        assert len(local) == 64
        # the value Stage-1 minted, and the two historical local values this branch has had:
        # both differ from it, and they differ from EACH OTHER (the code moved under us).
        assert local != S1.TEMPORAL_METHOD_SHA256
        assert S1.TEMPORAL_METHOD_SHA256 == \
            "343f20db53aed3f34f45f6c4adebc2cdf26985ab179b7df264dbd0d02587c4b5"

    def test_no_refusal_reason_mentions_a_method_hash_MISMATCH(self):
        """A named gate that does not exist must not look as though it does."""
        reasons = [v for k, v in vars(G).items() if k.startswith("REFUSE_")]
        assert not [r for r in reasons if "method_sha256" in r and "mismatch" in r]
        # the only method-identity refusal is about a MISSING binding, never a mismatch
        assert G.REFUSE_METHOD_IDENTITY_MISSING == \
            "the_estimator_names_a_method_but_binds_no_method_identity"


class TestNamingAMethodWithoutBindingOneIsREFUSED:
    """Stage-1's own words: a contract naming no method hash has admitted only a word."""

    @pytest.mark.parametrize("sha", [None, "", "abc", "Z" * 64, "a" * 63])
    def test_a_method_named_with_NO_valid_identity_is_refused(self, schema, sha):
        doc = temporal()
        if sha is None:
            doc["estimator"].pop("method_sha256")
        else:
            doc["estimator"]["method_sha256"] = sha
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(_resealed(doc), schema)
        # the schema refuses a malformed 64-hex; the gate refuses an absent one. NEITHER
        # admits, and that is the whole requirement.
        assert exc.value.reason in (G.REFUSE_SCHEMA, G.REFUSE_METHOD_IDENTITY_MISSING)

    def test_the_check_is_GENERIC_over_any_estimator_that_names_a_method(self, schema):
        """No mode is special-cased, so the next estimator inherits the check for free."""
        doc = copy.deepcopy(emit())                    # a WITHIN-condition contract
        doc["estimator"]["method_id"] = "some.future.within.method.v9"
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(_resealed(doc), schema)
        assert exc.value.reason == G.REFUSE_METHOD_IDENTITY_MISSING
