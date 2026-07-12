"""What makes an enrichment admissible, and how a node BINDS to the one it came from.

Two questions, one answer, so they live together:

  * **Is this enrichment a result?** A computed statistic is a NUMBER, plus the context
    that makes it mean anything — which statistic, computed how, against which gene-set
    release and which universe, under which exact rounding rule. Strip any of those and
    the number is irreproducible. A ``p_value`` is refused outright while
    ``inference_status=not_calibrated``: with no calibrated null, a p-value is not a
    p-value.

  * **Does this node descend from it?** A pathway node is INFERRED — nobody perturbed it.
    Its entire claim to relevance is the enrichment that produced it, so it must bind that
    enrichment by CONTENT HASH: ``pathway_record_id`` is the canonical hash of the
    enrichment record itself. A node cannot go on pointing at a parent whose gene set,
    universe, method or statistic has changed underneath it — the id would no longer
    match.

A node may reference its parent (``parent_enrichment_ref``) or repeat the complete
binding inline. Either is admissible; NEITHER is not. A node with a dangling parent is
refused, not emitted with a citation nobody can follow.
"""
from __future__ import annotations

from typing import Any

from .canonical_number import canonical_number, canonical_sha256

REQUIRED_ENRICHMENT_FIELDS = ("method_id", "statistic_name", "enrichment_value",
                              "inference_status", "rounding_rule")
CALIBRATION_REQUIRED_FOR = ("p_value", "q_value")

BINDING_FIELDS = ("pathway_record_id", "gene_set_release_id", "gene_set_sha256",
                  "universe_id", "universe_sha256")


class PathwayError(ValueError):
    """The pathway lane is malformed, unbound, or claims more than it computed."""


def check_enrichment(where: str, enrichment: dict[str, Any]) -> None:
    """A computed enrichment is a NUMBER, plus the context that makes it mean something.

    Stringifying a programmatically computed statistic destroys it, so ``enrichment_value``
    must be numeric. What it needs instead is: WHAT statistic it is, HOW it was computed,
    the EXACT rounding rule, and the gene-set/universe it was computed against — without
    those the number is irreproducible and uninterpretable.

    ``p_value`` / ``q_value`` are REFUSED while ``inference_status=not_calibrated``: no
    calibrated null exists, and a p-value without one is not a p-value.
    """
    for field in REQUIRED_ENRICHMENT_FIELDS:
        if enrichment.get(field) in (None, ""):
            raise PathwayError(
                f"{where}: computed enrichment is missing {field!r}. A Claude Science "
                "reading is provenance, not enrichment, and can never stand in for a "
                "computed result.")

    value = enrichment["enrichment_value"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PathwayError(
            f"{where}: enrichment_value={value!r} must be NUMERIC. A programmatically "
            "computed statistic is a number; stringifying it destroys it.")

    status = enrichment["inference_status"]
    if status != "not_calibrated":
        raise PathwayError(
            f"{where}: inference_status={status!r}. Stage 3 consumes only "
            "'not_calibrated' today; a calibrated method must be independently "
            "justified before its inference status is accepted.")
    for field in CALIBRATION_REQUIRED_FOR:
        if enrichment.get(field) is not None:
            raise PathwayError(
                f"{where}: {field} is present while inference_status=not_calibrated. "
                "No calibrated null exists, and a p/q value without one is not a p/q "
                "value. Emit it only when a calibrated method is independently "
                "justified.")


def enrichment_binding(pathway_id: str, enrichment: dict[str, Any],
                        universe: dict[str, Any]) -> dict[str, str]:
    """Content-address the parent enrichment. A node binds to THIS, or it is refused.

    ``pathway_record_id`` is the canonical hash of the enrichment record itself, so a
    node cannot claim a parent whose gene set, universe, method or statistic has since
    changed — the id would no longer match.
    """
    record = {
        "pathway_id": pathway_id,
        "method_id": str(enrichment["method_id"]),
        "statistic_name": str(enrichment["statistic_name"]),
        "enrichment_value": canonical_number(enrichment["enrichment_value"]),
        "inference_status": str(enrichment["inference_status"]),
        "rounding_rule": str(enrichment["rounding_rule"]),
        "gene_set_release_id": str(enrichment["gene_set_release"]),
        "gene_set_sha256": str(enrichment["gene_set_sha256"]),
        "universe_id": str(universe["universe_id"]),
        "universe_sha256": str(universe["universe_sha256"]),
    }
    return {
        "pathway_record_id": canonical_sha256(record),
        "gene_set_release_id": record["gene_set_release_id"],
        "gene_set_sha256": record["gene_set_sha256"],
        "universe_id": record["universe_id"],
        "universe_sha256": record["universe_sha256"],
    }


def node_enrichment_binding(where: str, node: dict[str, Any],
                             parent: dict[str, str]) -> dict[str, str]:
    """Bind a node to its parent enrichment — by reference, or by full inline repeat.

    Either is admissible; NEITHER is not. A node whose enrichment binding cannot be
    resolved to a hash-bound parent is a dangling claim, and is REFUSED rather than
    emitted with a reference nobody can follow.
    """
    ref = node.get("parent_enrichment_ref")
    inline = node.get("programmatic_evidence") or {}
    inline_universe = inline.get("universe_binding") or {}

    if ref:
        if not isinstance(ref, dict):
            raise PathwayError(
                f"{where}: parent_enrichment_ref must be an object carrying "
                f"{list(BINDING_FIELDS)}.")
        missing = [f for f in BINDING_FIELDS if not ref.get(f)]
        if missing:
            raise PathwayError(
                f"{where}: parent_enrichment_ref is missing {missing}. A partial "
                "reference is a dangling reference: the node would claim a parent "
                "enrichment nobody can resolve.")
        mismatched = [f for f in BINDING_FIELDS if str(ref[f]) != parent[f]]
        if mismatched:
            raise PathwayError(
                f"{where}: parent_enrichment_ref does not resolve to this pathway's "
                f"enrichment record — {mismatched} disagree. The node binds a parent "
                "whose gene set, universe or method is not the one that was computed.")
        return {f: parent[f] for f in BINDING_FIELDS}

    # No reference — then the node must repeat the COMPLETE binding inline.
    inline_binding = {
        "gene_set_release_id": inline.get("gene_set_release"),
        "gene_set_sha256": inline.get("gene_set_sha256"),
        "universe_id": inline_universe.get("universe_id"),
        "universe_sha256": inline_universe.get("universe_sha256"),
    }
    missing = [f for f, v in inline_binding.items() if not v]
    if missing:
        raise PathwayError(
            f"{where}: the node has NO resolvable parent enrichment. Give it a "
            f"parent_enrichment_ref ({list(BINDING_FIELDS)}), or repeat the complete "
            f"gene-set release + universe binding inline (missing {missing}). A node "
            "with a dangling parent enrichment is not a hypothesis, it is a claim with "
            "nothing behind it.")
    mismatched = [f for f, v in inline_binding.items() if str(v) != parent[f]]
    if mismatched:
        raise PathwayError(
            f"{where}: the node's inline enrichment binding disagrees with its "
            f"pathway's computed enrichment on {mismatched}.")
    return {"pathway_record_id": parent["pathway_record_id"], **inline_binding}
