"""The Stage-3 drug-annotation document.

Content-addressed: the bundle id is the hash of everything that could change the
science — the verified Direct binding, the frozen acquisition (and its verification
gate), the pathway lane, the Stage-2 joint context, the method and vocabularies, the
table content hashes, and the candidates. Timestamps and paths are excluded, so
re-running the same inputs reproduces the same id.

It carries NO combined score, NO candidate rank, and NO promotion/eligibility field —
there is no key for one to live in, and :func:`artifact_class.check_no_retired_keys`
refuses the document structurally if one ever appears. Deferred sources and the pathway
lane are explicit ``not_evaluated``: an absent lane is never a favourable one.
"""
from __future__ import annotations

from typing import Any, Optional

from . import (artifact_class as ac, canonical_number, env, joint_context,
               schemas, science_review, workflow as wf)
from .armlever import ARMS
from .direction import V1_ORIGIN_TYPES
from .hashing import content_hash, without

# Lanes this release deliberately does not evaluate. Absence of evidence is recorded as
# absence of evidence — never as a favourable result, and never as a zero.
DEFERRED_LANES = {
    "open_targets": "not_evaluated",
    "pubchem": "not_evaluated",
    "rxnorm": "not_evaluated",
    "lincs": "not_evaluated",
    "depmap": "not_evaluated",
    "gbm_context": "not_evaluated",
    "perturb2state": "not_evaluated",
}

CANDIDATE_CONTENT_KEYS = (
    "candidate_id", "active_moiety_id", "identity_status", "identity_conflicts",
    "arm_evidence_states", "observed_perturbation_arms",
    "inverse_direction_hypothesis_arms", "inverse_direction_support",
    "pathway_hypothesis_arms", "opposed_arms", "stage3_evidence_classes",
    "disease_context_review_status", "disease_context_review_result",
    "disease_context_review_reason", "disease_context_review_evidence_refs",
    "disease_context_reviewed_by", "form_ids", "target_ensembls", "n_edges",
    "n_direct_gene_edges", "development_state_aggregate", "n_potency_rows",
    "potency_state", "stage4_assessment_status", "stage4_assessment_reason",
    "source_record_ids",
)


def candidate_content(c: dict[str, Any]) -> dict[str, Any]:
    return {k: c[k] for k in CANDIDATE_CONTENT_KEYS}


def canonical_content(*, artifact_class: str, upstream: dict[str, Any],
                      acquisition: dict[str, Any], pathway: dict[str, Any],
                      joint: dict[str, Any], science_registry: dict[str, Any],
                      review: dict[str, Any], method: dict[str, Any],
                      table_hashes: dict[str, str],
                      candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Everything the bundle id commits to. No timestamps, no paths, no labels."""
    return {
        "schema_version": ac.OUTPUT_SCHEMA[artifact_class],
        "artifact_class": artifact_class,
        "upstream": upstream,
        "acquisition": acquisition,
        "pathway_hypotheses": pathway,
        "stage2_joint_context": joint,
        "science_evidence_registry": science_registry,
        "disease_context_review": review,
        "method": method,
        "deferred_lanes": dict(sorted(DEFERRED_LANES.items())),
        "table_hashes": dict(sorted(table_hashes.items())),
        "candidates": [candidate_content(c) for c in candidates],
    }


def build_document(*, artifact_class: str, upstream: dict[str, Any],
                   acquisition: dict[str, Any], table_hashes: dict[str, str],
                   candidates: list[dict[str, Any]], counts: dict[str, Any],
                   pathway: Optional[dict[str, Any]] = None,
                   joint: Optional[dict[str, Any]] = None,
                   science_registry: Optional[dict[str, Any]] = None,
                   review: Optional[dict[str, Any]] = None,
                   created_at: Optional[str] = None) -> dict[str, Any]:
    ac.require(artifact_class)
    method = env.method_block()
    pathway = pathway or {"pathway_lane": "not_evaluated", "n_pathways": 0,
                          "n_nodes": 0}
    joint = joint or {"stage2_joint_context": joint_context.NOT_PROVIDED}
    science_registry = science_registry or {"science_registry": "not_provided",
                                            "n_records": 0}
    review = review or dict(science_review.NOT_PROVIDED)

    content = canonical_content(
        artifact_class=artifact_class, upstream=upstream, acquisition=acquisition,
        pathway=pathway, joint=joint, science_registry=science_registry,
        review=review, method=method, table_hashes=table_hashes,
        candidates=candidates)
    content_sha = content_hash(content)
    doc_id = ac.bundle_id(artifact_class, content_sha)

    doc: dict[str, Any] = {
        "schema_version": ac.OUTPUT_SCHEMA[artifact_class],
        "artifact_class": artifact_class,
        "bundle_id": doc_id,
        "canonical_content_sha256": content_sha,
        "document_sha256": "",
        "upstream": upstream,
        "acquisition": acquisition,
        # The pathway-node lane. `not_evaluated` when Stage 2 supplied no document.
        "pathway_hypotheses": pathway,
        # Stage-2 joint context, republished verbatim. TYPED, never numeric, and never
        # read by the direction engine.
        "stage2_joint_context": joint,
        # Every referenced Claude Science record is RESOLVED and RE-HASHED against this
        # registry. A dangling or altered record fails closed before anything is emitted.
        "science_evidence_registry": science_registry,
        # An ingestible RESULT, not a one-way pending flag. A substantive verdict must
        # pay for itself with evidence bindings that resolve.
        "disease_context_review": review,
        # ONE canonical numeric representation. Every number that enters a hash goes
        # through it, and the rounding rule that reproduces the bytes is stated here.
        **canonical_number.rule_block(),
        "method": method,
        "desired_arms": list(ARMS),
        "arms_are_independent": True,
        "combined_objective_permitted": False,
        "headline_arm_permitted": False,
        # The origins THIS BUNDLE contains — the v1 pair. NOT the engine's full closed set.
        #
        # These bytes are validated against the FROZEN Stage-3 schema set and hashed into the
        # bundle id, and Stage 4 binds them by SHA. The engine learned two further origins for
        # the v2 lane; announcing them here would move a downstream consumer's pinned bytes to
        # describe a lane that has not shipped a bundle. When v2 ships, the schema $id bumps,
        # the set is re-hashed, and the new hash goes to the Stage-4 owner — in that order.
        "origin_types": list(V1_ORIGIN_TYPES),
        "gene_and_pathway_evidence_are_never_merged": True,
        "directional_evidence_statuses": list(wf.DIRECTIONAL_EVIDENCE_STATUSES),
        "drug_mapping_statuses": list(wf.DRUG_MAPPING_STATUSES),
        "stage4_assessment_statuses": list(wf.STAGE4_ASSESSMENT_STATUSES),
        "stage4_assessment_note": wf.STAGE4_ASSESSMENT_NOTE,
        # A LABEL, not a tier. Unordered, and never comparable to a Direct arm evidence
        # tier or a Stage-2 Pareto tier.
        "stage3_evidence_classes": list(wf.EVIDENCE_CLASSES),
        "evidence_classes_are_unordered": True,
        "inverse_direction_hypothesis_is_never_observed_gain_of_function": True,
        "stage3_never_alters_direct_ranks_or_stage2_pareto_tiers": True,
        "data_status": _data_status(artifact_class, acquisition),
        "inference_status": "not_calibrated",
        "deferred_lanes": dict(sorted(DEFERRED_LANES.items())),
        "table_hashes": dict(sorted(table_hashes.items())),
        "counts": counts,
        "candidates": candidates,
        "created_at": created_at,
    }
    doc["document_sha256"] = content_hash(without(doc, ("document_sha256",)))

    # Structural: the retired promotion/eligibility vocabulary may not appear at ANY
    # depth, and a fixture may never wear an analysis id.
    ac.check_no_retired_keys(doc)
    ac.check_bundle_id(artifact_class, doc_id)
    schemas.validate(doc, ac.OUTPUT_SCHEMA[artifact_class],
                     context=f"{artifact_class}_drug_annotation")
    return doc


def _data_status(artifact_class: str, acquisition: dict[str, Any]) -> str:
    if artifact_class == ac.FIXTURE:
        return "synthetic_fixture_only"
    if not acquisition.get("n_acquired_public"):
        return "no_sources_acquired"
    return "acquired_public_responses"
