"""spot Stage-3: direction-aware target -> drug linkage. Two arms, two origins.

The only input is a VERIFIED Stage-2 Direct run directory (``direct_run``). There is no
caller-authored lever set and no fallback path.

Direct asks two independent questions — move AWAY from A, and move TOWARD B — so one
screen row becomes exactly two arm-lever rows (``armlever``), each reading only its own
pole. Stage 2 may also propose pathway NODES: genes it never perturbed (``pathways``).
Measured targets and inferred nodes are separate origins and never merge.

There is no combined, balanced, best-of, primary, headline or overall score or rank
anywhere in this package. Stage-2 joint context (joint_status, pareto_tier,
joint_ordering_method_id) is republished verbatim as TYPED context and is never read by
the direction engine (``joint_context``).

What a drug DOES (``direction.intervention_effect``) is kept strictly apart from what
the screen TESTED: an inhibitor reduces function and asserts nothing about abundance,
and activation is never inferred from inhibition.

Stage 3 reports scientific workflow STATES (``workflow``) — directional_evidence_status,
drug_mapping_status, stage4_assessment_status. It has NO promotion, eligibility or
recommendation vocabulary: that is retired. A Stage-4 assessment is not biological
promotion and not a recommendation.

Two artifact classes and one firewall (``artifact_class``): ``analysis`` (a real
computation over real inputs) and ``fixture`` (synthetic; never relabelled, never
reaches Stage 4).
"""
from __future__ import annotations

__all__ = [
    "acq_manifest", "acquire_public", "acquisition", "adapters", "armlever",
    "artifact_class", "artifacts", "bundle", "candidates", "direct_run", "direction",
    "drug_mapping", "env", "hashing", "http_public", "identity", "joint_context",
    "mechanisms", "pathways", "potency", "run_stage3", "schemas", "targets",
    "verify_acq_pages", "verify_acquisition", "workflow",
]
