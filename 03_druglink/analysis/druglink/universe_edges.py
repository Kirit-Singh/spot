"""What happens to a source drug ASSERTION once its target is admitted.

Split out of :mod:`druglink.universe_rows` (which owns TARGET identity: the typed universe
and the store on disk) once it crossed the 500-line gate — the same seam the verifier lane
already draws between ``cache_identity`` and ``cache_evidence``.

This module owns the three semantics the store paid for, and enforces them at EMIT time
rather than merely at load time — a gate that holds only where you happened to look is not a
gate:

1. **An ambiguous_identity row carries no rankable evidence.** The row says ``drugs: []`` and
   is honest. But six source assertions are preserved one level down under
   ``ambiguous_source_assertions`` — mec 6210 and 6862, on the three calmodulin genes that
   encode an identical protein and therefore share every accession. A consumer that flattens
   reads the ASSERTION, not the row, and flattening is the obvious thing to do. So the check
   is recursive, container-agnostic and depth-agnostic.

2. **A variant assertion never ranks a gene.** A V617F inhibitor is evidence about V617F, not
   about wild-type JAK2 — the whole clinical point is that it is not — and the screen
   perturbed the wild-type gene. ``variant_id = -1`` is ChEMBL's UNDEFINED MUTATION sentinel:
   it means "there is a mutation and we do not know which one", so reading it as null converts
   an unknown mutant into a wild-type claim. Absence is not permission: an assertion that
   merely OMITS ``general_gene_rankable`` is refused, because omission is exactly how 29
   variant assertions reached general-gene ranking.

3. **The cache holds no Stage-3 verdict.** ``action_type`` travels verbatim (``INHIBITOR``,
   ``AGONIST``, …); direction is recomputed at build time from the frozen Stage-3 vocabulary
   against the arm's own desired change. A cached direction is a verdict nobody can re-derive,
   and it outlives the vocabulary that produced it. ``max_phase`` is regulatory CONTEXT about
   a molecule, preserved exactly and refused as a sort key by name.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

from .hashing import content_hash, short_id
from . import universe_verify as uv
from .universe_verify import FORBIDDEN_DRUG_KEYS

if TYPE_CHECKING:                       # a type reference only — importing
    from .universe_rows import AdmittedStore   # universe_rows here would be circular

EDGE_POLICY_VERSION = "stage3-universe-edges-v1"

# The three lanes an assertion may occupy. Exactly ONE of them may rank a gene.
LANE_GENERAL = "general_gene_rankable"
LANE_VARIANT = "variant_specific_non_rankable"
LANE_AMBIGUOUS = "ambiguous_identity_non_rankable"
RANKABLE_LANES = frozenset({LANE_GENERAL})

# Where each lane's assertions live in a store row. The PRODUCER's names are the contract.
LANE_CONTAINERS = ((LANE_GENERAL, "drugs"),
                   (LANE_VARIANT, "variant_specific_assertions"),
                   (LANE_AMBIGUOUS, "ambiguous_source_assertions"))

DISP_AMBIGUOUS_IDENTITY = "ambiguous_identity"

# ChEMBL's UNDEFINED MUTATION sentinel. NOT null. NOT wild-type.
VARIANT_UNDEFINED_MUTATION = -1

# max_phase is CONTEXT. Any of these as a sort or gate key is a refusal.
MAX_PHASE_KEYS = frozenset({"max_phase", "max_phase_source", "max_phase_canonical",
                            "max_phase_rank", "phase", "development_phase"})

# The identity an edge cannot be checked against its source without.
REQUIRED_SOURCE_FIELDS = ("source_row_id", "molecule_chembl_id", "target_chembl_id",
                          "action_type_source")

GATE_AMBIGUOUS_ROW_HAS_RANKABLE_EVIDENCE = \
    "an_ambiguous_identity_row_carries_rankable_drug_evidence"
GATE_VARIANT_IN_GENERAL_LANE = "a_variant_assertion_reached_the_general_gene_lane"
GATE_CACHE_CARRIES_A_DIRECTION_VERDICT = \
    "the_cache_carries_a_stage3_direction_or_ranking_verdict"
GATE_MISSING_SOURCE_IDENTITY = "a_source_assertion_lost_its_source_identity"
GATE_MAX_PHASE_IS_NOT_A_RANK = "max_phase_is_context_and_may_never_gate_or_rank"


class UniverseRowsError(ValueError):
    """A named, fail-closed refusal. Never fall back to a fixture or a partial answer."""

    def __init__(self, gate: str, message: str):
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


class DrugEdgeError(UniverseRowsError):
    """An edge could not be emitted without violating a store semantic."""


def _rankability_nodes(node: Any, path: str = "$"):
    """Every dict at ANY depth that makes a rankability claim. Container-agnostic."""
    if isinstance(node, Mapping):
        if "general_gene_rankable" in node:
            yield path, node
        for key, value in node.items():
            yield from _rankability_nodes(value, f"{path}.{key}")
    elif isinstance(node, (list, tuple)):
        for i, item in enumerate(node):
            yield from _rankability_nodes(item, f"{path}[{i}]")


def is_variant_assertion(assertion: Mapping[str, Any]) -> bool:
    """A ``variant_id`` of ANY value — the ``-1`` sentinel included — is a variant assertion."""
    return assertion.get("variant_id") not in (None, "")


def gate_row(row: Mapping[str, Any]) -> None:
    """The store's three semantics, enforced on the row we are about to emit edges from."""
    tid = row.get("target_id")

    if row.get("disposition") == DISP_AMBIGUOUS_IDENTITY:
        if row.get("drugs"):
            raise DrugEdgeError(
                GATE_AMBIGUOUS_ROW_HAS_RANKABLE_EVIDENCE,
                f"{tid} has a shared UniProt accession and still carries {len(row['drugs'])} "
                "rankable drug assertion(s): one mechanism would become independent-looking "
                "evidence for every gene that accession maps to")
        for path, node in _rankability_nodes(row):
            if node.get("general_gene_rankable") is not False:
                raise DrugEdgeError(
                    GATE_AMBIGUOUS_ROW_HAS_RANKABLE_EVIDENCE,
                    f"{tid}{path[1:]} (mec {node.get('source_row_id')}) claims "
                    f"general_gene_rankable={node.get('general_gene_rankable')!r} inside an "
                    "ambiguous_identity row. Non-rankability holds at ANY depth, in ANY "
                    "container, however honestly that container is named — a consumer that "
                    "flattens assertions reads the assertion, not the row")

    for a in (row.get("drugs") or []):
        if is_variant_assertion(a):
            raise DrugEdgeError(
                GATE_VARIANT_IN_GENERAL_LANE,
                f"{tid}: mec {a.get('source_row_id')} carries variant_id="
                f"{a.get('variant_id')!r} in the GENERAL lane. A V617F inhibitor is evidence "
                "about V617F, not about wild-type JAK2 — and the screen perturbed the "
                f"wild-type gene. variant_id {VARIANT_UNDEFINED_MUTATION} is ChEMBL's "
                "UNDEFINED MUTATION sentinel, which is emphatically not 'no variant'")
        if a.get("general_gene_rankable") is False:
            raise DrugEdgeError(
                GATE_VARIANT_IN_GENERAL_LANE,
                f"{tid}: mec {a.get('source_row_id')} sits in the general lane while "
                "declaring itself non-rankable; the lane and the flag must agree")

    for a in (row.get("variant_specific_assertions") or []):
        if a.get("general_gene_rankable") is not False:
            raise DrugEdgeError(
                GATE_VARIANT_IN_GENERAL_LANE,
                f"{tid}: variant mec {a.get('source_row_id')} must be EXPLICITLY "
                "general_gene_rankable=false. An absent field is not a denial, and omission "
                "is exactly how 29 variant assertions reached general-gene ranking")


def build_edge(row: Mapping[str, Any], assertion: Mapping[str, Any], lane: str,
               binding: Mapping[str, Any]) -> dict[str, Any]:
    """One source assertion, preserved VERBATIM and typed by its lane.

    Nothing here is derived: no direction, no intervention effect, no phase gate, no score.
    ``action_type_source`` leaves exactly as ChEMBL wrote it, and the frozen Stage-3 direction
    vocabulary reads it at build time against the arm's own desired change.
    """
    forbidden = FORBIDDEN_DRUG_KEYS & set(assertion.keys())
    if forbidden:
        raise DrugEdgeError(
            GATE_CACHE_CARRIES_A_DIRECTION_VERDICT,
            f"{row.get('target_id')}: mec {assertion.get('source_row_id')} carries "
            f"{sorted(forbidden)}. The cache may hold only source-faithful fields; a cached "
            "direction is a verdict nobody can re-derive, and it outlives the vocabulary that "
            "produced it")
    if any(assertion.get(k) in (None, "") for k in REQUIRED_SOURCE_FIELDS):
        raise DrugEdgeError(
            GATE_MISSING_SOURCE_IDENTITY,
            f"{row.get('target_id')}: an assertion is missing one of {REQUIRED_SOURCE_FIELDS}. "
            "ChEMBL's REQUIRED.ATTRIBUTION is to preserve the ChEMBL IDs, and an edge that "
            "cannot name its source row cannot be checked against the source")

    edge = {
        "target_id": row["target_id"],
        "target_id_namespace": row["target_id_namespace"],
        "target_disposition": row["disposition"],
        "lane": lane,
        "general_gene_rankable": (lane == LANE_GENERAL
                                  and assertion.get("general_gene_rankable") is True),
        # ChEMBL identities, verbatim.
        "molecule_chembl_id": assertion.get("molecule_chembl_id"),
        "target_chembl_id": assertion.get("target_chembl_id"),
        "pref_name": assertion.get("pref_name"),
        "molecule_type": assertion.get("molecule_type"),
        "inchikey": assertion.get("inchikey"),
        "source_row_id": assertion.get("source_row_id"),          # = ChEMBL mec_id
        # The mechanism, verbatim. action_type carries NO Stage-3 verdict.
        "action_type_source": assertion.get("action_type_source"),
        "mechanism_of_action": assertion.get("mechanism_of_action"),
        "mechanism_refs": list(assertion.get("mechanism_refs") or []),
        "selectivity_comment": assertion.get("selectivity_comment"),
        "direct_interaction": assertion.get("direct_interaction"),
        "molecular_mechanism": assertion.get("molecular_mechanism"),
        "disease_efficacy": assertion.get("disease_efficacy"),
        # Context only. Never a gate, never a rank.
        "max_phase_source": assertion.get("max_phase_source"),
        "max_phase_canonical": assertion.get("max_phase_canonical"),
        "max_phase_is_context_only": True,
        # Rankability dispositions, verbatim. -1 is preserved, never nulled.
        "variant_id": assertion.get("variant_id"),
        "variant_specific": assertion.get("variant_specific"),
        "variant_disposition": assertion.get("variant_disposition"),
        "ambiguity_disposition": assertion.get("ambiguity_disposition"),
        "cross_ref_provenance": dict(assertion.get("cross_ref_provenance") or {}),
        # Release / licence / attribution bindings.
        "release_binding": dict(binding),
        # Stated, so that nothing downstream has to assume it.
        "direction_decided_in_cache": False,
        "edge_policy_version": EDGE_POLICY_VERSION,
    }
    edge["edge_id"] = short_id(edge)
    return edge


def rankable_edges(edges: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The general-gene lane, and nothing else. Variant and ambiguous copies never rank."""
    return [dict(e) for e in edges
            if e.get("lane") in RANKABLE_LANES and e.get("general_gene_rankable") is True]


def order_edges(edges: Iterable[Mapping[str, Any]], *,
                by: Sequence[str]) -> list[dict[str, Any]]:
    """Deterministic ordering — and the ONE place ``max_phase`` is refused as a key.

    ``max_phase`` is regulatory context about a molecule, not evidence about a target. An
    approved drug for another disease is not stronger evidence here than a phase-1 drug for
    this one; sorting by it turns a context field into a silent objective.
    """
    bad = [k for k in by if k in MAX_PHASE_KEYS]
    if bad:
        raise DrugEdgeError(
            GATE_MAX_PHASE_IS_NOT_A_RANK,
            f"{bad} cannot order drug edges. max_phase is CONTEXT: it is preserved exactly "
            "(source + canonical) and may never gate or rank")
    rows = [dict(e) for e in edges]
    rows.sort(key=lambda e: tuple(content_hash(e.get(k)) for k in by))
    return rows



# The join's own vocabulary, moved here with the adapter it belongs to.
GATE_UNTYPED_TARGET_QUERY = "a_drug_edge_query_must_carry_an_exact_typed_target_identity"
GATE_NAMESPACE_CROSS_JOIN = "a_target_id_may_not_be_joined_across_namespaces"
GATE_TARGET_NOT_IN_ADMITTED_UNIVERSE = "the_target_is_not_in_the_admitted_typed_universe"
STORE_NAMESPACES = uv.STORE_NAMESPACES


# --------------------------------------------------------------------------- #
# 3. The adapter: typed target identity -> source drug assertions
#    (moved here from universe_rows, which breached the 500-line gate. universe_rows owns
#     target IDENTITY; this owns what happens once an identity is admitted. A move, not a
#     rewrite — universe_rows re-exports these, so the single front door is preserved.)
# --------------------------------------------------------------------------- #
def _release_binding(store: AdmittedStore) -> dict[str, Any]:
    rel = store.releases
    chembl = rel.get("chembl") or {}
    uniprot = rel.get("uniprot") or {}
    return {
        "store_id": store.store_id,
        "typed_universe_sha256": store.typed_universe_sha256,
        "chembl_release": chembl.get("source_release"),
        "chembl_source_sha256": chembl.get("source_sha256"),
        "chembl_doi": chembl.get("doi"),
        "chembl_license": chembl.get("license"),
        "chembl_required_attribution": chembl.get("attribution"),
        "uniprot_release": uniprot.get("source_release"),
        "uniprot_source_sha256": uniprot.get("source_sha256"),
        "uniprot_license": uniprot.get("license"),
        "uniprot_attribution": uniprot.get("attribution"),
    }


def _typed_key(query: Any) -> tuple[str, str]:
    """A query is a TYPED identity, or it is refused. A bare id is a symbol join waiting."""
    if isinstance(query, Mapping):
        tid, ns = query.get("target_id"), query.get("target_id_namespace")
    elif isinstance(query, (tuple, list)) and len(query) == 2:
        tid, ns = query
    else:
        raise DrugEdgeError(
            GATE_UNTYPED_TARGET_QUERY,
            f"{query!r} is not a typed target identity. The store is joined ONLY by exact "
            "(target_id, target_id_namespace). Joining by a bare id — a gene SYMBOL above all "
            "— looks identical the day it is written, and silently re-attributes every edge "
            "the first time a gene is renamed or a symbol is reused")
    if not tid or not ns:
        raise DrugEdgeError(
            GATE_UNTYPED_TARGET_QUERY,
            f"target_id={tid!r} target_id_namespace={ns!r}: both halves of the typed identity "
            "are required. A namespace-less id is a name, and names are not identities")
    return str(ns), str(tid)


def drug_edges_for_targets(store: AdmittedStore,
                           target_ids: Iterable[Any]) -> list[dict[str, Any]]:
    """Every SOURCE drug assertion held for these targets, joined by exact typed identity.

    ``target_ids`` are TYPED identities: ``{"target_id": …, "target_id_namespace": …}`` or a
    ``(target_id, namespace)`` pair. A bare string is refused — see :func:`_typed_key`.

    Every assertion is emitted — general, variant-specific, and ambiguous-identity copies
    alike — each typed by its lane and carrying its own rankability disposition. Only
    ``lane == general_gene_rankable`` may rank a gene (:func:`rankable_edges`). The
    non-rankable lanes travel with the result deliberately: an assertion that is silently
    dropped is indistinguishable from a drug nobody found, and the store's entire point is
    that those two are different things.

    A symbol-only target answers with ZERO edges and its ``unsupported_namespace``
    disposition — which means "this acquisition ROUTE cannot reach it", and never "no drug
    evidence exists".
    """
    binding = _release_binding(store)
    edges: list[dict[str, Any]] = []
    for query in target_ids:
        ns, tid = _typed_key(query)
        row = store.row_for(tid, ns)
        if row is None:
            other = [n for n in STORE_NAMESPACES if store.row_for(tid, n) is not None]
            if other:
                raise DrugEdgeError(
                    GATE_NAMESPACE_CROSS_JOIN,
                    f"{tid} is in the admitted universe under namespace {other[0]!r}, and you "
                    f"asked under {ns!r}. A namespace-crossing match is silent "
                    "mis-attribution, so the join refuses rather than guessing which one you "
                    "meant")
            raise DrugEdgeError(
                GATE_TARGET_NOT_IN_ADMITTED_UNIVERSE,
                f"{ns}:{tid} is not one of the {len(store.typed_universe)} targets in the "
                "admitted typed universe. The join is by exact typed identity and never "
                "degrades to a symbol match, so this refuses rather than answering about some "
                "other gene")
        gate_row(row)
        for lane, container in LANE_CONTAINERS:
            for assertion in (row.get(container) or []):
                edges.append(build_edge(row, assertion, lane, binding))

    edges.sort(key=lambda e: (e["target_id_namespace"], e["target_id"], e["lane"],
                              str(e["source_row_id"])))
    return edges
