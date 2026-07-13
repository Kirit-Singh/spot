"""PATHWAY AS CONTEXT. It contextualizes a measured edge; it NEVER sources one.

THE DISTINCTION THIS MODULE EXISTS TO HOLD
------------------------------------------
Every drug claim traces back to a target where a knockdown was ACTUALLY PERFORMED and a sign was
ACTUALLY OBSERVED. The pathway only says which SET that target sits in.

A pathway record is a GENE-SET ENRICHMENT: an ``enrichment_value`` over a set, plus a
``leading_edge``. It is a SET-LEVEL statistic. Nobody knocked down a set. So it has no CRISPRi
sign, and turning it into a drug edge would hand a set-level number a direction it never had —
guilt by association wearing the costume of a measurement.

THE JOIN
--------
  1. Take the MEASURED (Direct/temporal) target rows — the ones with a real CRISPRi sign.
  2. Join admitted pathway records to those rows through the pathway record's ``leading_edge``
     target ids AND their namespaces — EXACT typed identity. Never by symbol, never by gene-set
     id, never by name.
  3. Drug mechanisms attach to THOSE TARGETS: the measured ones. A mechanism is always
     GENE-TARGET-SPECIFIC.
  4. The association then carries the pathway refs — ``pathway_id``, ``pathway_source``,
     ``coverage``, ``convergence`` — so a reader can see "drugs along a pathway" without the
     pathway ever having produced a drug claim.

WHAT IS REFUSED, BY NAME
------------------------
  * an ``enrichment_value`` used to SOURCE an edge          -> a set-level number given a sign
  * a gene-set id reaching the target join as a TARGET      -> a GO/Reactome id is not a target
  * a pathway member with NO measured support               -> NO edge. Not a weak one, not a
    low-ranked one, not a tie-break. It is carried as typed CONTEXT with stated missingness.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from . import stage2_aggregate as sa

PATHWAY_CONTEXT_V2_POLICY_VERSION = "stage3-pathway-context-v2-never-sources-an-edge"

# --------------------------------------------------------------------------- #
# THE PATHWAY LANE IS NOT ADMITTED. It contributes ZERO — by name, not by omission.
#
# TWO independent reasons, either of which alone is disqualifying:
#
#  1. W3's pathway verifier FAILS OPEN to resealed target/modulation fields. A verifier that
#     fails open admits exactly the artifact it was built to refuse, so its ADMIT carries no
#     information at all. Bytes admitted by a fail-open gate are unadmitted bytes with a
#     certificate stapled to them.
#  2. The context token contract is not final. Three spellings are live for one concept
#     (`pathway_id` / `gene_set_id` / `set_id`), and the native `leading_edge` entries may carry
#     neither a target id nor a namespace — so the exact-typed join this module requires cannot
#     even be attempted.
#
# So the lane REFUSES rather than guessing a field. There is deliberately NO fallback chain
# (`pathway_id or gene_set_id or set_id`), NO default source and NO coercion: three spellings
# absorbed by an alias layer is how a contract rots silently while both lanes stay green.
#
# ZERO IS THE HONEST OUTPUT. It says "Stage 2 has not yet told us, in bytes anyone can check,
# which sets these genes are in" — which is exactly true. Flip this to True only when W3's final
# context schema lands AND their verifier fails closed AND the lane is re-admitted.
PATHWAY_LANE_ADMITTED = False
PATHWAY_LANE_NOT_ADMITTED_REASON = (
    "W3's pathway verifier fails open to resealed target/modulation fields, so its ADMIT carries "
    "no information; and the context token contract is not final (pathway_id / gene_set_id / "
    "set_id are all live, and native leading_edge entries may carry no typed target identity). "
    "Stage 3 does not consume bytes admitted by a fail-open gate, and does not guess a field "
    "name. The lane contributes ZERO context until both are fixed and the lane is re-admitted.")

# The EXACT context-record schema Stage 3 will assert once W3's tokens are final. It is a CLOSED
# set: a renamed field, a missing field and an unexpected extra field are each a NAMED REFUSAL.
# Nothing here is aliased and nothing is defaulted.
CONTEXT_RECORD_FIELDS = frozenset({
    "pathway_id", "pathway_source", "leading_edge", "coverage", "convergence",
    "enrichment_value",
})

# The typed pathway record's fields. A gene-set id is NOT a target id, and it never becomes one.
FIELD_PATHWAY_ID = "pathway_id"
FIELD_PATHWAY_SOURCE = "pathway_source"
FIELD_LEADING_EDGE = "leading_edge"
FIELD_COVERAGE = "coverage"
FIELD_CONVERGENCE = "convergence"
FIELD_ENRICHMENT_VALUE = "enrichment_value"

# The set-level fields that may NEVER reach a drug edge. An enrichment value has no CRISPRi sign.
SET_LEVEL_ONLY_FIELDS = (FIELD_ENRICHMENT_VALUE, FIELD_COVERAGE, FIELD_CONVERGENCE)

CONTEXT_COLUMNS: tuple[str, ...] = (
    "pathway_context_id", "arm_key", "lane", "program_id", "desired_change",
    "pathway_id", "pathway_source", "coverage", "convergence",
    "target_id", "target_id_namespace",
    "has_measured_support", "measured_support_status",
    "n_drug_edges_contextualized",
)
CONTEXT_KEY: tuple[str, ...] = ("pathway_context_id",)

# The stated missingness for a pathway member nobody perturbed. It is a VALUE, not a silence.
SUPPORT_MEASURED = "contextualizes_a_measured_target"
SUPPORT_NONE = "pathway_member_with_no_measured_perturbation_never_earns_a_drug_edge"

GATE_PATHWAY_LANE_NOT_ADMITTED = "the_pathway_lane_was_admitted_by_a_verifier_that_fails_open"
GATE_PATHWAY_SCHEMA_FIELD_UNKNOWN = "a_pathway_context_record_carries_a_field_the_schema_has_not"
GATE_PATHWAY_SCHEMA_FIELD_MISSING = "a_pathway_context_record_is_missing_a_required_schema_field"
GATE_ENRICHMENT_VALUE_SOURCED_AN_EDGE = \
    "a_gene_set_enrichment_value_was_used_to_source_a_drug_edge"
GATE_GENE_SET_ID_AS_TARGET = "a_gene_set_id_was_joined_as_though_it_were_a_drug_target"
GATE_PATHWAY_EDGE_IN_THE_EDGE_TABLE = "a_pathway_origin_edge_reached_the_drug_edge_table"


class PathwayContextError(ValueError):
    """A named, fail-closed refusal. The pathway contributes CONTEXT or nothing."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _leading_edge(record: Mapping[str, Any]) -> list[tuple[str, str]]:
    """The record's leading-edge TARGETS, by EXACT typed identity. Never a symbol, never a set id.

    A leading edge entry that carries no namespace is refused rather than joined on its bare id:
    a namespace-less id is a name, and a name is not an identity.
    """
    out: list[tuple[str, str]] = []
    for entry in (record.get(FIELD_LEADING_EDGE) or ()):
        if not isinstance(entry, Mapping):
            raise PathwayContextError(
                GATE_GENE_SET_ID_AS_TARGET,
                f"a leading_edge entry is {entry!r}, not a typed target. A bare token here is a "
                "gene-set id or a symbol being passed off as a target identity")
        tid, ns = entry.get("target_id"), entry.get("target_id_namespace")
        if not tid or not ns:
            raise PathwayContextError(
                GATE_GENE_SET_ID_AS_TARGET,
                f"a leading_edge entry carries target_id={tid!r} / namespace={ns!r}. The join is "
                "by exact typed identity and never degrades to a symbol or a set id")
        out.append((str(tid), str(ns)))
    return out


def check_no_set_level_source(record: Mapping[str, Any], *, arm_key: str) -> None:
    """A set-level statistic may never SOURCE a drug edge. Refused by name, at the seam."""
    present = [f for f in SET_LEVEL_ONLY_FIELDS if record.get(f) is not None]
    if present:
        raise PathwayContextError(
            GATE_ENRICHMENT_VALUE_SOURCED_AN_EDGE,
            f"arm {arm_key!r} offered a record carrying {present} to the measured drug-edge "
            "path. An enrichment value is a SET-LEVEL statistic: nobody knocked down a set, so "
            "it has no CRISPRi sign, and sourcing an edge from it would hand a set-level number "
            "a direction it never had")


def assert_context_schema(record: Mapping[str, Any], *, arm_key: str) -> None:
    """The EXACT context schema. A renamed, missing or extra field is a NAMED REFUSAL.

    Not a normaliser and not a best-effort read: Stage 3 asserts the one vocabulary it was given
    and refuses everything else. `gene_set_id` and `set_id` are NOT accepted as `pathway_id` —
    accepting them would be the alias layer that lets the contract rot while both lanes stay
    green.
    """
    got = set(record)
    unknown = sorted(got - CONTEXT_RECORD_FIELDS)
    if unknown:
        raise PathwayContextError(
            GATE_PATHWAY_SCHEMA_FIELD_UNKNOWN,
            f"arm {arm_key!r} carries a pathway context record with {unknown}, which the schema "
            f"does not have (it is exactly {sorted(CONTEXT_RECORD_FIELDS)}). A field Stage 3 "
            "cannot name is a field nobody agreed to, and a renamed one absorbed by an alias is "
            "a contract rotting in silence")
    missing = sorted(CONTEXT_RECORD_FIELDS - got)
    if missing:
        raise PathwayContextError(
            GATE_PATHWAY_SCHEMA_FIELD_MISSING,
            f"arm {arm_key!r} carries a pathway context record missing {missing}. A missing field "
            "is a refusal, never a default")


def require_admitted(arm_key: str) -> None:
    """The lane contributes NOTHING until it is admitted by a gate that fails CLOSED."""
    if not PATHWAY_LANE_ADMITTED:
        raise PathwayContextError(
            GATE_PATHWAY_LANE_NOT_ADMITTED,
            f"arm {arm_key!r} belongs to the pathway lane. {PATHWAY_LANE_NOT_ADMITTED_REASON}")


def index_by_target(arms: Sequence[sa.LoadedArm]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """(target_id, namespace) -> the pathway refs whose LEADING EDGE contains that exact target.

    Built ONLY from the pathway arms, and keyed ONLY by typed target identity. The gene-set id
    never becomes a key: a GO/Reactome id is not a drug target and can never carry a mechanism.
    """
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for arm in arms:
        if arm.lane != sa.LANE_PATHWAY:
            continue
        # NOT ADMITTED -> ZERO context. No partial join, no best-effort ref, no guessed field.
        if not PATHWAY_LANE_ADMITTED:
            return {}
        for rec in arm.records:
            assert_context_schema(rec, arm_key=arm.arm_key)
            ref = {
                "pathway_id": rec.get(FIELD_PATHWAY_ID),
                "pathway_source": (rec.get(FIELD_PATHWAY_SOURCE)
                                   or arm.bundle.pathway_source),
                "coverage": rec.get(FIELD_COVERAGE),
                "convergence": rec.get(FIELD_CONVERGENCE),
            }
            for key in _leading_edge(rec):
                out.setdefault(key, []).append(dict(ref, arm_key=arm.arm_key,
                                                    program_id=arm.program_id,
                                                    desired_change=arm.desired_change,
                                                    lane=arm.lane))
    return out


def refs_for(index: Mapping[tuple[str, str], list[dict[str, Any]]],
             target_id: str, namespace: str) -> list[dict[str, Any]]:
    """The pathway refs that CONTEXTUALIZE this measured target. Never a source of direction."""
    return [{"pathway_id": r["pathway_id"], "pathway_source": r["pathway_source"],
             "coverage": r["coverage"], "convergence": r["convergence"]}
            for r in index.get((str(target_id), str(namespace)), ())]


def build_context(index: Mapping[tuple[str, str], list[dict[str, Any]]], *,
                  measured_targets: Iterable[tuple[str, str]],
                  edges: Sequence[Mapping[str, Any]],
                  short_id) -> list[dict[str, Any]]:
    """One row per (pathway ref, target). A member with NO measured support is CARRIED, not
    dropped — and it earns no edge, no rank, no support and no direction claim.

    Its absence of support is a STATED value (:data:`SUPPORT_NONE`), because "this pathway member
    was never perturbed" and "this pathway member was perturbed and found inert" are different
    facts, and a missing row would make them the same silence.
    """
    measured = {(str(t), str(ns)) for t, ns in measured_targets}
    n_edges: dict[tuple[str, str], int] = {}
    for edge in edges:
        key = (str(edge.get("target_id")), str(edge.get("target_id_namespace")))
        n_edges[key] = n_edges.get(key, 0) + 1

    out: list[dict[str, Any]] = []
    for (tid, ns), refs in sorted(index.items()):
        supported = (tid, ns) in measured
        for ref in refs:
            row = {
                "arm_key": ref["arm_key"], "lane": ref["lane"],
                "program_id": ref["program_id"], "desired_change": ref["desired_change"],
                "pathway_id": ref["pathway_id"], "pathway_source": ref["pathway_source"],
                "coverage": ref["coverage"], "convergence": ref["convergence"],
                "target_id": tid, "target_id_namespace": ns,
                "has_measured_support": supported,
                "measured_support_status": (SUPPORT_MEASURED if supported else SUPPORT_NONE),
                # A member with no measured support contextualizes NOTHING. Zero, and it says so.
                "n_drug_edges_contextualized": n_edges.get((tid, ns), 0) if supported else 0,
            }
            row["pathway_context_id"] = short_id(
                {k: row.get(k) for k in CONTEXT_COLUMNS if k != "pathway_context_id"})
            out.append(row)
    return sorted(out, key=lambda r: str(r["pathway_context_id"]))


def check_edges_are_all_measured(edges: Iterable[Mapping[str, Any]],
                                 inferred_origins: Iterable[str]) -> None:
    """EVERY drug edge traces to a MEASURED target. Not one carries a pathway origin."""
    inferred = set(inferred_origins)
    for edge in edges:
        if edge.get("origin_type") in inferred:
            raise PathwayContextError(
                GATE_PATHWAY_EDGE_IN_THE_EDGE_TABLE,
                f"edge {edge.get('edge_id')!r} carries origin {edge.get('origin_type')!r}. The "
                "pathway CONTEXTUALIZES an edge whose evidence is measured; it never SOURCES "
                "one. Every drug claim traces back to a target where a knockdown was actually "
                "performed and a sign actually observed")


def vocabularies() -> dict[str, Any]:
    """The pathway-context contract, hashed into the v2 bundle id."""
    return {
        "pathway_context_v2_policy_version": PATHWAY_CONTEXT_V2_POLICY_VERSION,
        "measured_support_statuses": [SUPPORT_MEASURED, SUPPORT_NONE],
        "set_level_only_fields": list(SET_LEVEL_ONLY_FIELDS),
        "the_pathway_contextualizes_a_measured_edge_it_never_sources_one": True,
        "a_gene_set_enrichment_value_never_sources_a_drug_edge": True,
        "a_gene_set_id_is_never_a_drug_target": True,
        "a_pathway_member_without_measured_support_earns_no_drug_edge": True,
        "pathway_direction_is_never_inherited_from_set_membership": True,
        "the_join_is_by_exact_typed_leading_edge_identity_never_by_symbol": True,
    }
