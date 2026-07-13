"""B1 — convergence must rest on INTRA-PATHWAY support, never a global component.

The defect: perturbations were clustered GLOBALLY, and a pathway was called convergent
when two of its members landed in the same global connected component — even when the
only thing linking them was a gene OUTSIDE the pathway. That fabricates a mechanism: it
reports "these two pathway members do the same thing" on the strength of a similarity
neither of them has to the other.

The rule now: a pathway's convergence is computed on the subgraph INDUCED BY ITS OWN
MEMBERS. An edge to a non-member cannot carry support into the set, because it is not
evidence about the set.
"""
from __future__ import annotations

import pytest
from direct import convergence

# Two in-pathway members, A and B, and a BRIDGE that is not in the pathway.
# A ~ BRIDGE and B ~ BRIDGE are both supportive; A ~ B is NOT.
IN_A, IN_B, BRIDGE = "ENSG_IN_A", "ENSG_IN_B", "ENSG_OUT_BRIDGE"

N = 40


def _vec(pattern: list[float]) -> dict[str, float]:
    return {f"G{i:03d}": v for i, v in enumerate(pattern)}


@pytest.fixture
def bridged_signatures():
    """A and B are ORTHOGONAL to each other; each is 45 degrees from the BRIDGE.

    cos(A, BRIDGE) = cos(B, BRIDGE) = 1/sqrt(2) ~ 0.707  -> both supportive (>= 0.5)
    cos(A, B)      = 0.0                                 -> NOT supportive
    """
    half = N // 2
    a = _vec([1.0] * half + [0.0] * half)
    b = _vec([0.0] * half + [1.0] * half)
    bridge = _vec([1.0] * N)
    return {IN_A: a, IN_B: b, BRIDGE: bridge}


@pytest.fixture
def genuine_signatures():
    """A and B genuinely agree with EACH OTHER. No bridge is needed or used."""
    a = _vec([1.0] * N)
    b = _vec([0.9] * N)
    unrelated = _vec([1.0 if i % 2 else -1.0 for i in range(N)])
    return {IN_A: a, IN_B: b, BRIDGE: unrelated}


def _bundle(members: list[str]) -> dict:
    # B1: membership lives in the PERTURBATION-TARGET space — the space the arms rank and
    # the space signatures exist in. `genes_readout` is the signature VECTOR space's view.
    return {"sets": {"PW:TEST": {"name": "the pathway under test",
                                 "genes_target": members,
                                 "n_genes_target": len(members),
                                 "genes_readout": members,
                                 "n_genes_readout": len(members)}}}


def _converge(signatures, members):
    pairs = convergence.pairwise(signatures)
    return convergence.converge_sets(_bundle(members), signatures, pairs)[0]


class TestTheOutOfPathwayBridgeCannotCarrySupport:
    def test_the_bridge_really_does_link_them_globally(self, bridged_signatures):
        # The premise of the defect: globally, all three are one connected component.
        pairs = convergence.pairwise(bridged_signatures)
        supportive = {(p["target_a"], p["target_b"]) for p in pairs if p["supportive"]}
        assert (IN_A, BRIDGE) in supportive or (BRIDGE, IN_A) in supportive
        assert (IN_B, BRIDGE) in supportive or (BRIDGE, IN_B) in supportive
        # ...and yet the two pathway members do NOT agree with each other
        assert (IN_A, IN_B) not in supportive

    def test_two_members_linked_ONLY_through_a_non_member_are_NOT_convergent(
            self, bridged_signatures):
        c = _converge(bridged_signatures, [IN_A, IN_B])
        assert c["convergent"] is False
        assert c["n_supporting_perturbations"] < 2
        assert c["convergence_refused_reason"] == "fewer_than_two_perturbations_converge"

    def test_the_non_member_is_never_counted_as_a_supporting_perturbation(
            self, bridged_signatures):
        c = _converge(bridged_signatures, [IN_A, IN_B])
        assert BRIDGE not in c["supporting_perturbations"]
        assert BRIDGE not in c["measured_perturbations"]

    def test_no_supportive_pair_it_stands_on_touches_a_non_member(
            self, bridged_signatures):
        c = _converge(bridged_signatures, [IN_A, IN_B])
        for p in c["pairwise_support"]:
            assert p["target_a"] in (IN_A, IN_B)
            assert p["target_b"] in (IN_A, IN_B)

    def test_admitting_the_bridge_to_the_pathway_makes_it_convergent_again(
            self, bridged_signatures):
        # The control on the control: the support was always real, it just was not
        # support ABOUT this pathway. Put the bridge IN the pathway and it counts.
        c = _converge(bridged_signatures, [IN_A, IN_B, BRIDGE])
        assert c["convergent"] is True
        assert c["n_supporting_perturbations"] == 3


class TestGenuineIntraPathwaySupportStillConverges:
    def test_two_members_that_agree_with_EACH_OTHER_are_convergent(
            self, genuine_signatures):
        c = _converge(genuine_signatures, [IN_A, IN_B])
        assert c["convergent"] is True
        assert c["n_supporting_perturbations"] == 2
        assert sorted(c["supporting_perturbations"]) == sorted([IN_A, IN_B])

    def test_it_names_the_intra_pathway_pair_that_carries_the_claim(
            self, genuine_signatures):
        c = _converge(genuine_signatures, [IN_A, IN_B])
        assert c["n_supportive_pairs"] == 1
        p = c["pairwise_support"][0]
        assert {p["target_a"], p["target_b"]} == {IN_A, IN_B}
        assert p["similarity"] >= convergence.SIMILARITY_THRESHOLD

    def test_an_unrelated_non_member_does_not_change_the_verdict(
            self, genuine_signatures):
        with_bridge = _converge(genuine_signatures, [IN_A, IN_B, BRIDGE])
        assert with_bridge["convergent"] is True
        # the unrelated member is measured but supports nothing
        assert BRIDGE in with_bridge["measured_perturbations"]
        assert BRIDGE not in with_bridge["supporting_perturbations"]


class TestTheRestrictionIsDeclaredAndBound:
    def test_the_module_declares_that_support_is_intra_pathway_only(self):
        assert convergence.MEMBERSHIP_RESTRICTION
        assert "non_member" in convergence.MEMBERSHIP_RESTRICTION
        assert convergence.SUPPORT_MAY_ROUTE_THROUGH_NON_MEMBERS is False

    def test_the_convergence_definition_is_named(self):
        assert convergence.CONVERGENCE_DEFINITION
        assert "intra" in convergence.CONVERGENCE_DEFINITION

    def test_there_is_no_global_clustering_function_left_to_call(self):
        # The defect was reachable because a global component was in the API at all.
        assert not hasattr(convergence, "clusters")

    def test_the_definition_and_the_restriction_enter_the_method_hash(self):
        from direct import pathway
        block = pathway.method_block(None)
        assert block["convergence_definition"] == convergence.CONVERGENCE_DEFINITION
        assert block["convergence_membership_restriction"] == \
            convergence.MEMBERSHIP_RESTRICTION
        assert block["convergence_support_may_route_through_non_members"] is False
