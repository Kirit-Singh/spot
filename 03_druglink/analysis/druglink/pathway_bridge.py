"""The Stage-2 pathway → Stage-3 bridge (v2). TYPED INTERFACE — fixtures pending.

Stage 3 has always had a pathway lane, and it has always been **unfed**: `run_stage3`
defaults `pathway_hypotheses` to empty, so the whole lane has been dead code. This is the
bridge that feeds it from the **reusable pathway arm bundles**
(`spot.stage02_pathway_arm_bundle.v1`), because "drugs along an implicated pathway" is a
product requirement, not an optional extra.

THE ONE RULE EVERYTHING ELSE SERVES
-----------------------------------
**A direction is never inherited from pathway membership or enrichment.**

An enrichment says *this set is over-represented at one end of an arm's ranking*. It says
nothing whatsoever about what perturbing any INDIVIDUAL member would do. A gene can sit in
a set enriched for "decrease" and itself do nothing, or the opposite. Letting a node inherit
the arm's desired direction from the set it belongs to would manufacture a
direction-compatible drug target out of guilt by association — a claim with no measurement
under it, wearing the costume of one.

So:

* a **measured** target keeps the direction **its own arm value** gave it, and nothing else;
* an **unmeasured** node gets a direction ONLY if it carries its **own** source-backed
  `desired_target_modulation` **and** an evidence locator that resolves;
* otherwise it is **`direction_unresolved`**, and a `direction_unresolved` node **may not
  improve drug ordering**. It is emitted, it is visible, it is honest — and it is inert.

TWO EVIDENCE CLASSES, NEVER MERGED
----------------------------------
* **measured perturbation target** → an `observed_perturbation` lever. It was perturbed;
  the screen has something to say about it.
* **every other pathway member** → `pathway_context` or `pathway_hypothesis` ONLY. Nobody
  perturbed it. Its entire claim to relevance is the enrichment that named it, and an
  enrichment is a statement about a SET.

Stage 3 and the UI must show these distinctly. A reader who cannot tell a measured lever
from an inferred neighbour has been told the second thing is the first.

CROSS-TIME
----------
Under a `temporal_cross_condition` selection the pathway panels are the **ENDPOINT** pathway
contexts — A at `from_condition`, B at `to_condition`. They are two WITHIN-condition
readings shown side by side. They are **never** "temporal enrichment", never a fate claim,
never a longitudinal statistic: nothing was measured across time for pathways, and naming a
cross-time pathway statistic would invent one. Refused at any nesting depth by
``join_semantics.refuse_temporal_pathway_claim``.
"""
from __future__ import annotations

from typing import Any, Optional

from . import join_semantics as js

BRIDGE_SCHEMA = "spot.stage03_pathway_bridge.v2"
BRIDGE_METHOD_ID = "spot.stage03.pathway_bridge.v2"

# The upstream contracts this bridge consumes. Both must be ADMITTED by their own
# independent verifier before Stage 3 will read a byte of them.
PATHWAY_ARM_BUNDLE_SCHEMA = "spot.stage02_pathway_arm_bundle.v1"
CONVERGENCE_SCHEMA = "spot.stage02_pathway_convergence.v1"

# --------------------------------------------------------------------------- #
# Node classes. A node is what it was, not what its neighbours were.
# --------------------------------------------------------------------------- #
MEASURED_LEVER = "measured_perturbation_target"
PATHWAY_CONTEXT = "pathway_context"
PATHWAY_HYPOTHESIS = "pathway_hypothesis"
NODE_CLASSES = (MEASURED_LEVER, PATHWAY_CONTEXT, PATHWAY_HYPOTHESIS)

# Only a measured lever is evidence that something was DONE to this gene.
MEASURED_CLASSES = frozenset({MEASURED_LEVER})
INFERRED_CLASSES = frozenset({PATHWAY_CONTEXT, PATHWAY_HYPOTHESIS})

# --------------------------------------------------------------------------- #
# Direction states.
# --------------------------------------------------------------------------- #
DIRECTION_UNRESOLVED = "direction_unresolved"

# A node may only be direction-compatible via one of these provenances. Note what is
# ABSENT: there is no "inherited_from_pathway" and no "inherited_from_enrichment", and
# there is no code path that could produce one.
DIRECTION_FROM_OWN_ARM = "own_measured_arm_value"
DIRECTION_FROM_OWN_SOURCE = "own_source_backed_annotation"
DIRECTION_PROVENANCES = (DIRECTION_FROM_OWN_ARM, DIRECTION_FROM_OWN_SOURCE)

# Vocabulary a node might use to claim it inherited a direction. Refused by name, so the
# refusal survives someone inventing a friendly synonym for it.
INHERITED_DIRECTION_CLAIMS = frozenset({
    "inherited_desired_target_modulation", "desired_direction_from_pathway",
    "direction_from_enrichment", "direction_from_set", "set_direction",
    "pathway_desired_change", "enrichment_direction", "inherited_direction",
    "membership_direction", "direction_by_membership",
})

# Bindings every emitted pathway record must carry. A pathway claim whose gene set,
# universe, coverage, convergence or source cannot be named is a claim nobody can check.
REQUIRED_PATHWAY_BINDINGS = (
    "pathway_arm_key",              # the reusable arm this enrichment belongs to
    "direct_arm_key",               # the ranking it was computed over
    "set_id",                       # the pathway
    "source",                       # Reactome | GO-BP
    "gene_set_release",             # the pinned release
    "gene_set_sha256",              # ...and its bytes
    "universe_id",                  # the target universe membership was tested in
    "universe_sha256",
    "coverage_disposition",         # rankable / descriptive-only / undefined
    "convergence_ref",              # the shared convergence artifact for (condition, source)
)

# What an unmeasured node must carry to be allowed a direction AT ALL.
REQUIRED_NODE_PROVENANCE = (
    "target_id", "target_id_namespace", "set_id", "membership_source",
    "membership_sha256",
)
REQUIRED_SOURCE_DIRECTION = (
    "desired_target_modulation",    # its OWN, not the arm's
    "modulation_source_id",         # who says so
    "modulation_evidence_locator",  # ...and exactly where
    "modulation_evidence_sha256",   # ...and the bytes
)


class PathwayBridgeError(ValueError):
    """The pathway bundle and Stage-3's contract do not agree."""


# --------------------------------------------------------------------------- #
# Admission.
# --------------------------------------------------------------------------- #
def require_admitted_bundle(bundle: dict[str, Any]) -> None:
    """Stage 3 reads no byte of a bundle its own independent verifier has not admitted."""
    if bundle.get("schema_version") != PATHWAY_ARM_BUNDLE_SCHEMA:
        raise PathwayBridgeError(
            f"expected {PATHWAY_ARM_BUNDLE_SCHEMA}, got "
            f"{bundle.get('schema_version')!r}")

    ref = bundle.get("verification_ref") or {}
    verifier = ref.get("verifier_id")
    if not verifier:
        raise PathwayBridgeError(
            "the pathway arm bundle carries no verification_ref: Stage 3's admission "
            "contract is that the producer's own INDEPENDENT verifier reconstructed this "
            "bundle, and an unverified bundle is refused, not assumed")
    if "independent" not in verifier:
        raise PathwayBridgeError(
            f"verification_ref names {verifier!r}, which is not an INDEPENDENT verifier. "
            "A bundle that verifies itself proves only that the producer agreed with "
            "itself — that is the self-consistency an independent verifier exists to "
            "refuse.")

    # No pathway artifact may carry a statistic computed ACROSS time, at any depth.
    js.refuse_temporal_pathway_claim(bundle, what="pathway arm bundle")


def require_bindings(record: dict[str, Any]) -> None:
    missing = [k for k in REQUIRED_PATHWAY_BINDINGS if record.get(k) in (None, "")]
    if missing:
        raise PathwayBridgeError(
            f"pathway record {record.get('set_id')!r} is missing bindings {missing}: a "
            "pathway claim whose gene set, universe, coverage, convergence or source "
            "cannot be named is a claim nobody can check")


# --------------------------------------------------------------------------- #
# The rule. This is the whole module.
# --------------------------------------------------------------------------- #
def refuse_inherited_direction(node: dict[str, Any]) -> None:
    """A node may not claim a direction it got from the set it belongs to."""
    hits = sorted(k for k in node if k in INHERITED_DIRECTION_CLAIMS)
    if hits:
        raise PathwayBridgeError(
            f"node {node.get('target_id')!r} claims an INHERITED direction {hits}. An "
            "enrichment says a SET is over-represented at one end of a ranking; it says "
            "nothing about what perturbing this gene would do. A direction inherited from "
            "membership is guilt by association wearing the costume of a measurement.")


def classify(node: dict[str, Any], *, measured_target_ids: set[str]) -> str:
    """Measured, or inferred. Membership in an enriched set does not promote a node."""
    refuse_inherited_direction(node)
    tid = node.get("target_id")
    if tid in measured_target_ids:
        return MEASURED_LEVER
    return (PATHWAY_HYPOTHESIS if node.get("is_hypothesis") else PATHWAY_CONTEXT)


def resolve_direction(node: dict[str, Any], *, node_class: str,
                      measured_modulation: Optional[str] = None) -> dict[str, Any]:
    """The desired_target_modulation this node is ENTITLED to, and where it came from.

    Three outcomes, and only three:

      measured        -> its OWN arm's modulation. Never the pathway's.
      unmeasured + own source-backed annotation that RESOLVES -> that annotation.
      anything else   -> direction_unresolved, and it may not improve drug ordering.
    """
    refuse_inherited_direction(node)

    if node_class == MEASURED_LEVER:
        if not measured_modulation:
            raise PathwayBridgeError(
                f"{node.get('target_id')!r} is a measured lever but no arm modulation was "
                "supplied; Stage 3 will not fill it in from the pathway")
        return {"desired_target_modulation": measured_modulation,
                "direction_provenance": DIRECTION_FROM_OWN_ARM,
                "direction_is_compatible": True,
                "may_improve_drug_ordering": True}

    # Unmeasured. It gets a direction only if it BROUGHT one, with the bytes behind it.
    missing = [k for k in REQUIRED_SOURCE_DIRECTION if not node.get(k)]
    if missing:
        return {"desired_target_modulation": DIRECTION_UNRESOLVED,
                "direction_provenance": None,
                "direction_is_compatible": False,
                "may_improve_drug_ordering": False,
                "direction_unresolved_reason":
                    f"no source-backed direction of its own (missing {missing}); a "
                    "direction is never inherited from pathway membership or enrichment"}

    return {"desired_target_modulation": node["desired_target_modulation"],
            "direction_provenance": DIRECTION_FROM_OWN_SOURCE,
            "direction_is_compatible": True,
            "may_improve_drug_ordering": True,
            "modulation_source_id": node["modulation_source_id"],
            "modulation_evidence_locator": node["modulation_evidence_locator"],
            "modulation_evidence_sha256": node["modulation_evidence_sha256"]}


def endpoint_context(mode: str, *, from_condition: Optional[str] = None,
                     to_condition: Optional[str] = None) -> dict[str, Any]:
    """The pathway panel's context. Under cross-time: A at `from`, B at `to`. NEVER temporal."""
    label = js.admit_pathway_context(mode)
    ctx: dict[str, Any] = {"pathway_context_type": label,
                           "is_temporal_enrichment": False,
                           "is_longitudinal_statistic": False}
    if mode == js.TEMPORAL_CROSS_CONDITION:
        if not (from_condition and to_condition):
            raise PathwayBridgeError(
                "a cross-time pathway panel needs BOTH endpoints: A at from_condition and "
                "B at to_condition")
        ctx.update({"arm_A_endpoint_condition": from_condition,
                    "arm_B_endpoint_condition": to_condition,
                    "endpoints_are_within_condition_readings": True})
    return ctx


def ordering_contribution(resolved: dict[str, Any]) -> float:
    """A direction_unresolved node contributes NOTHING to drug ordering. Ever.

    Not a small weight, not a tie-break, not a tiebreaker-of-last-resort. Zero. A node with
    no direction under it cannot make a drug look better than one with a measurement.
    """
    return 1.0 if resolved.get("may_improve_drug_ordering") else 0.0
