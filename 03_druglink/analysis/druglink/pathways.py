"""Pathway-node hypotheses: a SECOND, separate lever lane.

Stage 2 answers two different kinds of question. It measures **direct targets** — genes
it actually perturbed, whose arms moved. It may also propose **pathway nodes** — genes
inferred to sit in a pathway implicated by those perturbations, which were themselves
NEVER PERTURBED.

Those are not the same evidence and this module never lets them become the same:

  * a pathway node carries ``origin_type=pathway_node`` end to end, so no downstream
    table, count or handoff can mistake it for a measured target;
  * a node must state its OWN desired direction. It never inherits one from the pathway
    it belongs to, and no direction propagates between sibling nodes — "in the same
    pathway" is not evidence about a gene;
  * a node must cite at least one CONTRIBUTING PERTURBATION that really exists in this
    Direct run, on the SAME arm. A node no measured perturbation supports is refused;
  * the strongest thing a drug on a pathway node can ever be is a
    ``pathway_hypothesis``. It can never be an ``observed_perturbation``, and it is
    never counted alongside a measured direct target.

The document is bound to the Direct run by ``run_id`` AND ``run_binding_sha256``: a
pathway file computed against a different screen answers a different question and is
refused.

**Stage 2 OWNS and EMITS this document.** Stage 3 is the consumer. The schema name
``spot.stage02_pathway_hypotheses.v1`` and the required fields below are a CONSUMER
PROPOSAL pending the Stage-2 owner's agreement — **the lane is not frozen**, and this
worktree neither edits Stage 2 nor freezes a Stage-2 contract.

The lane is OPTIONAL and currently unfed: a run given no pathway document records the
lane as ``not_evaluated`` and proceeds on direct targets alone. Nothing is invented.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from . import artifact_class as ac
from .armlever import ARMS
from .direction import (MOD_DECREASE, MOD_INCREASE, MOD_NO_DIRECTION,
                        MOD_NOT_EVALUATED, ORIGIN_PATHWAY_NODE)
from . import science_registry as sr
from .canonical_number import canonical_number, canonical_sha256, rule_block
from .pathway_binding import (BINDING_FIELDS, PathwayError, check_enrichment,
                              enrichment_binding, node_enrichment_binding)
from .hashing import content_hash, short_id

# OWNED AND EMITTED BY STAGE 2. Stage 3 is the CONSUMER. This name is a
# consumer PROPOSAL until the Stage-2 owner agrees it; the lane is NOT frozen.
PATHWAY_SCHEMA = "spot.stage02_pathway_hypotheses.v1"
PATHWAY_CONTRACT_STATUS = "consumer_proposal_pending_stage2_owner_agreement"
PATHWAY_POLICY_VERSION = (
    "stage3-pathways-v3-registry-resolved-science-and-hash-bound-enrichment")

# CLOSED enum. What kind of COMPUTED evidence puts a gene in the pathway.
EVIDENCE_STATUSES = ("computed_enrichment_member", "computed_enrichment_leading_edge",
                     "curated_pathway_member", "network_propagation_neighbour")

# An enrichment statistic is a NUMBER. Stringifying a programmatically computed
# statistic destroys it. What it needs is not a string — it is the context that makes
# the number reproducible and interpretable.

DECLARED_MODULATIONS = (MOD_DECREASE, MOD_INCREASE, MOD_NO_DIRECTION,
                        MOD_NOT_EVALUATED)

NOT_EVALUATED = {"pathway_lane": "not_evaluated",
                 "reason": "no_stage2_pathway_document_supplied",
                 "pathway_contract_status":
                     "consumer_proposal_pending_stage2_owner_agreement",
                 "n_pathways": 0, "n_nodes": 0}

IMMUTABLE_KEY = ("direct_run_id", "pathway_id", "target_ensembl", "desired_arm")


# PathwayError is defined in .pathway_binding and re-exported here: every existing caller
# — and every test — raises and catches it from this module.
__all__ = ["PathwayError", "BINDING_FIELDS", "admit", "load", "index_by_key",
           "vocabularies"]


def load(path: Optional[str], *, artifact_class: str, direct,
         science_registry_root: Optional[str] = None) -> dict[str, Any]:
    """Admit a pathway-hypothesis document, or record an explicitly unevaluated lane."""
    ac.require(artifact_class)
    if not path:
        return {"levers": [], "pathways": [], "dispositions": [],
                "ref": dict(NOT_EVALUATED)}

    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    return admit(doc, artifact_class=artifact_class, direct=direct,
                 science_registry_root=science_registry_root)


def admit(doc: dict[str, Any], *, artifact_class: str, direct,
          science_registry_root: Optional[str] = None) -> dict[str, Any]:
    if not isinstance(doc, dict):
        raise PathwayError("pathway hypotheses must be a JSON object")
    if doc.get("schema_version") != PATHWAY_SCHEMA:
        raise PathwayError(
            f"pathway document schema_version={doc.get('schema_version')!r}; "
            f"Stage 3 consumes {PATHWAY_SCHEMA!r}")
    if doc.get("artifact_class") != artifact_class:
        raise PathwayError(
            f"{artifact_class} refuses a pathway document declaring "
            f"artifact_class={doc.get('artifact_class')!r}")

    # Bound to THIS Direct run, by run id AND by the binding hash Stage 3 recomputed.
    if doc.get("direct_run_id") != direct.run_id:
        raise PathwayError(
            f"the pathway document was computed against Direct run "
            f"{doc.get('direct_run_id')!r}, but this run admitted {direct.run_id!r}; "
            "it answers a different question")
    if doc.get("direct_run_binding_sha256") != direct.binding_sha256:
        raise PathwayError(
            "the pathway document's Direct binding hash does not match the binding "
            "Stage 3 independently derived from the Direct run")
    return _expand(doc, direct, science_registry_root)


def _expand(doc: dict[str, Any], direct,
            science_registry_root: Optional[str] = None) -> dict[str, Any]:
    from .armlever import expand as expand_arms

    arms = expand_arms(direct.screen, direct_run_id=direct.run_id)["arm_levers"]
    # Contributing perturbations must be REAL, measured, direct-target arms.
    measured = {(row["target_ensembl"], row["desired_arm"]): row
                for row in arms if row["gene_target_drug_edge_permitted"]}

    levers: list[dict[str, Any]] = []
    pathways: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []
    resolved_refs: list[dict[str, str]] = []
    seen: set[tuple] = set()

    for pathway in doc.get("pathways") or []:
        pathway_id = str(pathway.get("pathway_id") or "")
        if not pathway_id:
            raise PathwayError("every pathway must carry a pathway_id")
        # A pathway without a pinned release + content hash cannot be reproduced: the
        # membership of "the same" GO/Reactome term changes between releases.
        release = pathway.get("pathway_source_release")
        source_sha = pathway.get("pathway_source_sha256")
        if not release or not source_sha:
            raise PathwayError(
                f"pathway {pathway_id}: pathway_source_release and "
                "pathway_source_sha256 are required. A pathway term's membership "
                "changes between releases, so an unpinned pathway is not reproducible.")
        enrichment = pathway.get("computed_enrichment") or {}
        check_enrichment(pathway_id, enrichment)
        universe = enrichment.get("universe_binding") or {}
        if not (universe.get("universe_id") and universe.get("universe_sha256")):
            raise PathwayError(
                f"pathway {pathway_id}: computed_enrichment.universe_binding "
                "(universe_id + universe_sha256) is required. An enrichment statistic "
                "is meaningless without the gene UNIVERSE it was computed against: the "
                "same overlap in a different universe is a different result.")
        if not enrichment.get("gene_set_release") or not enrichment.get(
                "gene_set_sha256"):
            raise PathwayError(
                f"pathway {pathway_id}: computed_enrichment needs gene_set_release + "
                "gene_set_sha256.")
        # Claude Science references are RESOLVED and RE-HASHED against the registry.
        # A dangling or altered record fails closed here, before anything is emitted.
        p_refs = sr.check_refs(pathway_id, pathway.get("science_evidence_refs"))
        sr.resolve_all(science_registry_root, p_refs, where=f"pathway {pathway_id}")
        resolved_refs.extend(p_refs)

        # The parent enrichment is CONTENT-ADDRESSED. Every node must bind to this exact
        # record — by id + gene-set + universe hashes — or repeat the whole binding
        # inline. A node that binds to neither has a dangling parent and is refused.
        parent = enrichment_binding(pathway_id, enrichment, universe)

        pathways.append({
            "direct_run_id": direct.run_id,
            "pathway_id": pathway_id,
            "pathway_record_id": parent["pathway_record_id"],
            "pathway_source": pathway.get("pathway_source"),
            "pathway_source_release": str(release),
            "pathway_source_sha256": str(source_sha),
            "n_nodes": len(pathway.get("nodes") or []),
            # Computed enrichment and Claude Science output are kept APART. Only the
            # computed side may ever support a node; the science record is REFERENCED.
            "computed_enrichment_method_id": str(enrichment["method_id"]),
            "computed_statistic_name": str(enrichment["statistic_name"]),
            # ONE canonical numeric path. No float ever reaches a hash.
            "computed_enrichment_value": canonical_number(
                enrichment["enrichment_value"]),
            "computed_rounding_rule_id": rule_block()["rounding_rule_id"],
            "computed_rounding_rule": str(enrichment["rounding_rule"]),
            "computed_inference_status": str(enrichment["inference_status"]),
            "gene_set_release_id": parent["gene_set_release_id"],
            "gene_set_sha256": parent["gene_set_sha256"],
            "universe_id": parent["universe_id"],
            "universe_sha256": parent["universe_sha256"],
            # The FULL typed triple, end to end. An id alone is not a binding.
            "science_evidence_refs": p_refs,
            "n_science_evidence_refs": len(p_refs),
        })

        for node in pathway.get("nodes") or []:
            lever = _node_lever(node, pathway_id, direct, measured, parent,
                                science_registry_root, resolved_refs)
            key = tuple(lever[k] for k in IMMUTABLE_KEY)
            if key in seen:
                raise PathwayError(
                    f"duplicate immutable pathway-node key: {dict(zip(IMMUTABLE_KEY, key))}")
            seen.add(key)

            if not lever["contributing_perturbations"]:
                # A node no measured perturbation supports is not a hypothesis, it is
                # a guess. It stays visible and is barred from every drug edge.
                lever["gene_target_drug_edge_permitted"] = False
                dispositions.append({
                    "subject_kind": "pathway_node",
                    "subject_id": f"{pathway_id}:{lever['target_ensembl']}",
                    "state": "no_contributing_perturbation",
                    "reason": "no measured Direct arm supports this node on this arm",
                    "detail": f"desired_arm={lever['desired_arm']}",
                    "source_record_id": None,
                })
            levers.append(lever)

    levers.sort(key=lambda r: tuple(str(r[k]) for k in IMMUTABLE_KEY))
    ref = {
        "pathway_lane": "evaluated",
        "pathway_contract_status": PATHWAY_CONTRACT_STATUS,
        "pathway_policy_version": PATHWAY_POLICY_VERSION,
        # ONE canonical numeric path: every number in the document becomes its exact
        # canonical decimal string BEFORE serialisation, so no float is ever rendered by
        # whatever json.dumps happened to feel like doing.
        "pathway_document_sha256": canonical_sha256(doc),
        **rule_block(),
        "pathway_method": doc.get("method"),
        "n_pathways": len(pathways),
        "n_nodes": len(levers),
        "n_nodes_with_contributing_perturbation": sum(
            1 for lever in levers if lever["contributing_perturbations"]),
        "science_evidence_refs_resolved": len(resolved_refs),
        "science_evidence_records_are_resolved_and_rehashed": True,
        "every_node_binds_a_hash_bound_parent_enrichment": True,
        "nodes_never_inherit_a_direction_from_their_pathway": True,
        "pathway_evidence_is_arm_specific": True,
        "pathway_node_is_never_a_measurement": True,
        "claude_science_interpretation_is_provenance_not_enrichment": True,
    }
    return {"levers": levers, "pathways": pathways, "dispositions": dispositions,
            "ref": ref}


def _node_lever(node: dict[str, Any], pathway_id: str, direct,
                measured: dict[tuple, dict[str, Any]],
                parent: dict[str, str], science_registry_root: Optional[str],
                resolved_refs: list[dict[str, str]]) -> dict[str, Any]:
    ensembl = node.get("target_ensembl")
    arm = node.get("desired_arm")
    if not ensembl or not str(ensembl).startswith("ENSG"):
        raise PathwayError(
            f"pathway {pathway_id}: a node must carry an exact Ensembl gene id; got "
            f"{ensembl!r}. A symbol is not an accession.")
    if arm not in ARMS:
        raise PathwayError(
            f"pathway {pathway_id}/{ensembl}: desired_arm must be one of {list(ARMS)}; "
            f"got {arm!r}. A node belongs to ONE arm.")

    # The node states its OWN direction. It is never inherited from the pathway.
    modulation = node.get("desired_target_modulation")
    if modulation not in DECLARED_MODULATIONS:
        raise PathwayError(
            f"pathway {pathway_id}/{ensembl}/{arm}: the node must state its own "
            f"desired_target_modulation (one of {list(DECLARED_MODULATIONS)}); got "
            f"{modulation!r}. A node never inherits a direction from its pathway.")

    # The node must state what KIND of COMPUTED evidence puts it in the pathway.
    evidence_status = node.get("evidence_status")
    if evidence_status not in EVIDENCE_STATUSES:
        raise PathwayError(
            f"pathway {pathway_id}/{ensembl}/{arm}: evidence_status must be one of "
            f"{list(EVIDENCE_STATUSES)}; got {evidence_status!r}. It is a CLOSED enum — "
            "a node with no stated (or unrecognised) computed evidence is a guess.")

    # ARM-SPECIFIC programmatic evidence. A pathway enriched on the OTHER arm is not
    # evidence for this node on this arm — that is the inheritance this rejects.
    programmatic = node.get("programmatic_evidence") or {}
    check_enrichment(f"{pathway_id}/{ensembl}/{arm}", programmatic)
    evidence_arm = programmatic.get("desired_arm")
    if evidence_arm != arm:
        raise PathwayError(
            f"pathway {pathway_id}/{ensembl}/{arm}: programmatic_evidence is for arm "
            f"{evidence_arm!r}. Pathway evidence is ARM-SPECIFIC: evidence computed on "
            "one arm can never support a node on the other.")

    contributing: list[dict[str, Any]] = []
    for cite in node.get("contributing_perturbations") or []:
        cited_arm = cite.get("desired_arm", arm)
        if cited_arm != arm:
            # A perturbation measured on the OTHER arm is not evidence for this node on
            # this arm. Wrong-arm inheritance is refused, not silently accepted.
            continue
        source = measured.get((cite.get("target_ensembl"), arm))
        if source is None:
            # A citation to a perturbation this screen does not contain is not evidence.
            continue
        contributing.append({
            # The contributing perturbation's ID, bound to the measured arm lever.
            "contributing_perturbation_id": source["arm_lever_key"],
            "perturbed_target_ensembl": source["target_ensembl"],
            "desired_arm": arm,
            "arm_rank": source["arm_rank"],
            "arm_evidence_tier": source["arm_evidence_tier"],
            "arm_value_canonical_decimal": source["arm_value_canonical_decimal"],
            "arm_desired_target_modulation": source["arm_desired_target_modulation"],
        })
    contributing.sort(key=lambda c: (c["perturbed_target_ensembl"],))

    where = f"{pathway_id}/{ensembl}/{arm}"
    # Claude Science references RESOLVED and RE-HASHED. Dangling or altered fails closed.
    n_refs = sr.check_refs(where, node.get("science_evidence_refs"))
    sr.resolve_all(science_registry_root, n_refs, where=where)
    resolved_refs.extend(n_refs)

    # The node must bind to a hash-bound parent enrichment, or be refused.
    binding = node_enrichment_binding(where, node, parent)
    lever = {
        "direct_run_id": direct.run_id,
        "pathway_id": pathway_id,
        "target_ensembl": str(ensembl),
        "target_id": str(ensembl),
        "target_id_namespace": "ensembl_gene_id",
        "target_symbol": node.get("target_symbol"),
        "desired_arm": arm,
        "origin_type": ORIGIN_PATHWAY_NODE,
        "arm_desired_target_modulation": modulation,
        # A pathway node has NO measured arm of its own: no rank, no value, no tier.
        "arm_rank": None,
        "arm_value_source_string": None,
        "arm_value_canonical_decimal": None,
        "arm_evidence_tier": "not_evaluated",
        "arm_support_state": "not_evaluated",
        "arm_state": "pathway_node_not_perturbed",
        "arm_evaluable": modulation in (MOD_DECREASE, MOD_INCREASE),
        "evidence_status": str(evidence_status),
        "programmatic_evidence_method_id": str(programmatic["method_id"]),
        "programmatic_statistic_name": str(programmatic["statistic_name"]),
        # ONE canonical numeric path, plus the rounding rule that reproduces it.
        "programmatic_enrichment_value": canonical_number(
            programmatic["enrichment_value"]),
        "programmatic_rounding_rule_id": rule_block()["rounding_rule_id"],
        "programmatic_rounding_rule": str(programmatic["rounding_rule"]),
        "programmatic_inference_status": str(programmatic["inference_status"]),
        # The node's HASH-BOUND parent enrichment. Not a dangling reference.
        "pathway_record_id": binding["pathway_record_id"],
        "gene_set_release_id": binding["gene_set_release_id"],
        "gene_set_sha256": binding["gene_set_sha256"],
        "universe_id": binding["universe_id"],
        "universe_sha256": binding["universe_sha256"],
        # Claude Science is referenced by the FULL TYPED TRIPLE, end to end. An id alone
        # is not a binding, so an id alone is not what is carried.
        "science_evidence_refs": n_refs,
        "n_science_evidence_refs": len(n_refs),
        "contributing_perturbations": contributing,
        "n_contributing_perturbations": len(contributing),
        "target_identity_state": "ensembl_mapped",
        "gene_target_drug_edge_permitted": True,
        # A node was NEVER perturbed, so it can never be a measured direction.
        "arm_direction_measured": False,
    }
    lever["pathway_node_key"] = content_hash({k: lever[k] for k in IMMUTABLE_KEY})
    lever["pathway_node_id"] = short_id(lever)
    return lever


def index_by_key(levers: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Nodes keyed by (target_ensembl, desired_arm), for the drug-edge join.

    A node barred from gene-drug edges (no contributing perturbation) is not indexed.
    If two pathways propose the same gene on the same arm, the node with the most
    contributing perturbations wins the JOIN — but BOTH rows stay in the emitted table,
    because a pathway is provenance, not a tie to be broken silently.
    """
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for lever in sorted(levers,
                        key=lambda r: (-r["n_contributing_perturbations"],
                                       r["pathway_id"])):
        if not lever["gene_target_drug_edge_permitted"]:
            continue
        out.setdefault((lever["target_ensembl"], lever["desired_arm"]), lever)
    return out


def vocabularies() -> dict[str, Any]:
    return {
        "pathway_policy_version": PATHWAY_POLICY_VERSION,
        "pathway_schema": PATHWAY_SCHEMA,
        "pathway_contract_status": PATHWAY_CONTRACT_STATUS,
        "immutable_key": list(IMMUTABLE_KEY),
        "node_must_state_its_own_direction": True,
        "node_requires_a_contributing_measured_perturbation": True,
        "node_requires_arm_specific_programmatic_evidence": True,
        "pathway_requires_a_pinned_release_and_hash": True,
        "pathway_node_is_never_a_measurement": True,
        "claude_science_interpretation_is_provenance_not_enrichment": True,
        "gene_and_pathway_evidence_are_never_merged": True,
    }
