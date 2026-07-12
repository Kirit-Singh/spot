"""What the run is made of: code, schemas, vocabularies, adapters, solver lock.

All five are hashed and bound into the bundle ID, so a research annotation cannot be
reproduced-by-accident under a different engine, a loosened schema, a re-tuned
vocabulary, a changed adapter or a different Linux dependency solve.
"""
from __future__ import annotations

import functools
import os
from typing import Any

from . import (armlever, artifact_class as ac, direction, identity,
               joint_context, pathways, potency, science_review, targets,
               workflow)
from .acquisition import adapters_manifest
from .hashing import content_hash, file_sha256, tree_hash
from .schemas import schemas_tree

STAGE3_METHOD_VERSION = "stage3-druglink-v4-workflow-states"

_HERE = os.path.dirname(os.path.abspath(__file__))
CODE_ROOT = _HERE
ENV_LOCK = os.path.abspath(os.path.join(_HERE, "..", "..", "env",
                                        "stage3.linux-cpython312.lock"))


@functools.lru_cache(maxsize=1)
def code_tree() -> dict[str, Any]:
    return tree_hash(CODE_ROOT, (".py",))


@functools.lru_cache(maxsize=1)
def env_lock() -> dict[str, Any]:
    if not os.path.exists(ENV_LOCK):
        raise FileNotFoundError(
            "the Stage-3 Linux environment lock is missing; a run cannot be "
            "content-addressed without it")
    return {"env_lock_file": os.path.basename(ENV_LOCK),
            "env_lock_sha256": file_sha256(ENV_LOCK)}


@functools.lru_cache(maxsize=1)
def vocabularies() -> dict[str, Any]:
    return {
        "armlever": armlever.vocabularies(),
        "direction": direction.vocabularies(),
        "workflow": workflow.vocabularies(),
        "disease_context_review": science_review.vocabularies(),
        "pathways": pathways.vocabularies(),
        "joint_context": joint_context.vocabularies(),
        "artifact_classes": list(ac.ARTIFACT_CLASSES),
        "retired_keys": sorted(ac.RETIRED_KEYS),
        "identity_policy_version": identity.IDENTITY_POLICY_VERSION,
        "potency_policy_version": potency.POTENCY_POLICY_VERSION,
        "target_policy_version": targets.TARGET_POLICY_VERSION,
    }


@functools.lru_cache(maxsize=1)
def method_block() -> dict[str, Any]:
    return {
        "stage3_method_version": STAGE3_METHOD_VERSION,
        "armlever_policy_version": armlever.ARMLEVER_POLICY_VERSION,
        "direction_policy_version": direction.DIRECTION_POLICY_VERSION,
        "workflow_policy_version": workflow.WORKFLOW_POLICY_VERSION,
        "pathway_policy_version": pathways.PATHWAY_POLICY_VERSION,
        "joint_context_policy_version": joint_context.JOINT_CONTEXT_POLICY_VERSION,
        "identity_policy_version": identity.IDENTITY_POLICY_VERSION,
        "potency_policy_version": potency.POTENCY_POLICY_VERSION,
        "target_policy_version": targets.TARGET_POLICY_VERSION,
        "vocabularies_sha256": content_hash(vocabularies()),
        "adapters_sha256": content_hash(adapters_manifest()),
        "schemas_sha256": schemas_tree()["schemas_sha256"],
        "code_tree_sha256": code_tree()["tree_sha256"],
        "env_lock_sha256": env_lock()["env_lock_sha256"],
        # Named negatively and bound into the ID: reviving a combined objective
        # changes the method hash and therefore every downstream identifier.
        "combined_objective_permitted": False,
        "headline_arm_permitted": False,
        "candidate_rank_permitted": False,
        "promotion_and_eligibility_vocabulary_is_retired": True,
        "stage4_assessment_is_not_promotion_or_recommendation": True,
        "pathway_node_is_never_a_measurement": True,
        "stage2_joint_context_never_infers_drug_direction": True,
    }
