"""The EVIDENCE a bundle stands on: the perturbation it ran, and the RANKING BYTES.

Split out of ``bundle`` because these are a different question. ``bundle`` re-derives the
arithmetic of the arms; this module opens the files those arms CITE and checks that the
citation is real — that the bytes exist, that they hash to what the arm claims, that they
are the arm's own rows, and that the rank re-derives from them.

An arm that bound a ranking file nobody wrote would be citing evidence that does not exist,
and a hash of nothing is not a binding.
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import rules, schema
from .canonical import content_hash, sha256_hex
from .failures import Failures, allowlist


def perturbation(f: Failures, doc: dict[str, Any], where: str) -> None:
    """The modality Stage 3 reads the orientation against, and the limits on that reading."""
    p = doc["perturbation"]
    f.check("perturbation_modality_is_crispri_knockdown",
            p["perturbation_modality"] == rules.PERTURBATION_MODALITY, where,
            f"shipped {p['perturbation_modality']!r}; the orientation rule is only "
            "meaningful against a knockdown, and a different modality would invert what a "
            "positive arm value suggests")
    f.check("the_declared_orientation_rule_is_the_frozen_one",
            p["positive_response_to_knockdown"] == rules.MOD_SUPPORTS_INHIBITION
            and p["negative_response_to_knockdown"] == rules.MOD_OPPOSED_NEEDS_ACTIVATION
            and p["null_or_unresolved_response"] == rules.MOD_NOT_EVALUABLE
            and sorted(p["modulations"]) == sorted(rules.TARGET_MODULATIONS), where,
            str(p))
    f.check("pharmacologic_reversibility_is_not_assumed",
            p["pharmacologic_reversibility_assumed"] is False, where,
            "an OPPOSED arm says the desired change would require ACTIVATING the target. "
            "This screen knocked the target DOWN; it cannot speak to whether a drug could "
            "activate it, and an artifact that assumed so would launder a knockdown into a "
            "prescription")
    f.check("the_modulation_claim_is_suggestive_not_confirmatory",
            p["is_suggestive_not_confirmatory"] is True, where,
            "a druggability signal may SUGGEST but never CONFIRM")


def rankings(f: Failures, doc: dict[str, Any], where: str, artifact_dir: str) -> None:
    """The BYTES each arm's rank and counts stand on — reopened, hashed, and RE-RANKED.

    The arm binds a ranking file rather than restating its ranking, so an independent
    verifier can open the bytes and recompute the ranking instead of trusting the arm's own
    summary. Which means those bytes must EXIST: an arm that bound a ranking file nobody
    wrote would be citing evidence that does not exist, and a hash of nothing is not a
    binding.
    """
    if not artifact_dir:
        return
    for arm in doc["arms"]:
        key = arm["arm_key"]
        binding = arm.get("ranking")
        if not allowlist(f, binding, schema.RANKING_BINDING_KEYS,
                          "ranking_binding_keys_are_the_exact_allowlist", key):
            continue

        rel = str(binding["path"])
        f.check("the_ranking_path_is_bundle_relative_and_does_not_escape",
                not os.path.isabs(rel) and ".." not in rel.split("/")
                and rel.startswith(f"{schema.RANKINGS_DIRNAME}/"), key, rel)
        path = os.path.normpath(os.path.join(artifact_dir, rel))
        if not f.check("every_arm_binds_a_ranking_file_that_actually_exists",
                       os.path.exists(path), key,
                       f"{rel!r} is bound by the arm but was never written; an arm citing "
                       "evidence nobody wrote is worse than one citing none"):
            continue

        with open(path, "rb") as fh:
            raw = fh.read()
        ranking = json.loads(raw)
        f.check("the_ranking_file_raw_sha256_matches_the_bytes_on_disk",
                binding["raw_sha256"] == sha256_hex(raw), key, "")
        f.check("the_ranking_file_canonical_sha256_matches_its_content",
                binding["canonical_sha256"] == content_hash(ranking), key, "")

        problems = schema.exact_keys(ranking, schema.RANKING_FILE_KEYS, "ranking")
        if not f.check("ranking_file_keys_are_the_exact_allowlist", not problems, key,
                       "; ".join(problems)):
            continue
        f.check("the_ranking_file_names_the_arm_it_belongs_to",
                ranking["schema_version"] == schema.SCHEMA_RANKING
                and ranking["arm_key"] == key, key, str(ranking.get("arm_key")))

        # REFERENTIAL INTEGRITY: the bound bytes ARE this arm's rows, not a copy that could
        # drift from them. Then the rank is RE-DERIVED from those bytes.
        f.check("the_ranking_file_carries_exactly_this_arms_retained_rows",
                ranking["ranked"] == arm["records"], key,
                "the bound ranking bytes are not the arm's own rows; two copies of one "
                "ranking are two chances to disagree, and a reader cannot tell which was "
                "the one that got checked")
        want = rules.rank_population(ranking["ranked"])
        bad = [r["target_id"] for r in ranking["ranked"]
               if r["rank"] != want.get(r["target_id"])]
        f.check("the_rank_rederives_from_the_bound_ranking_bytes", not bad, key,
                f"{bad[:3]} do not re-rank from the bytes the arm binds")


