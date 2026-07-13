"""THE SCHEMA the temporal arm release must satisfy. Exact allowlists, four firewalls.

An unknown key is a REJECT, not a warning. A producer that grows a field has to come here
and authorise it — which is the whole point: an artifact that can quietly gain a column
can quietly gain a claim.

FOUR RECURSIVE FIREWALLS, over the WHOLE artifact, at any depth
--------------------------------------------------------------
1. INFERENCE      p / q / FDR / significance. This estimator has NO calibrated null, so a
                  number that merely LOOKS like significance would be READ as significance.
2. OBJECTIVE      combined / balanced / weighted / composite / objective / score. There is
                  no combined arm objective, and a target opposing one arm must never be
                  able to buy rank with a large value on the other.
3. JOIN-TIME      pair / Pareto / concordance / joint / role / pole / batch. Every one is a
                  COMPARISON-SCOPED property, and a reusable arm carrying one would be a
                  pair-shaped artifact wearing a reusable arm's key.
4. MACHINE        absolute paths, hostnames, private addresses. Not content: an artifact
                  whose bytes contain the machine that made them cannot be content-addressed
                  and leaks a filesystem into a published record. Runs on KEYS and on STRING
                  VALUES, because a path hides equally well in either.

The firewalls are TOKEN rules, not substring rules. A substring rule for "p" would refuse
every key containing the letter, and a firewall that refuses everything is one somebody
turns off. ``n_panel_surviving`` is not a p-value, and it survives.

TWO EXEMPTION KINDS, BOTH NARROW
--------------------------------
* NEGATIVE DECLARATIONS. The artifact must be able to write its own prohibition down, or the
  rule would be unstatable. ``bundle_carries_role_or_pole`` is exempt ONLY while it is
  exactly ``False``. Flip it and the firewall fires — precisely the event it exists to catch.
* EXACT SPELLINGS. ``qc_ontarget_significant`` is the UPSTREAM QC gate's own boolean, a gate
  outcome and not a p-value. The exemption is the exact spelling, not the shape: there is no
  pattern-shaped hole for a ``combined_significant`` to walk through.
"""
from __future__ import annotations

from typing import Any, Iterable

from .firewall import (  # noqa: F401  (re-exported: one import site for the schema)
    BANNED_EXACT_NAMES,
    BANNED_SUBSTRING_RE,
    BANNED_TOKENS,
    EXACT_SPELLING_EXEMPTIONS,
    INFERENCE_TOKENS,
    JOIN_TIME_TOKENS,
    NEGATIVE_DECLARATIONS,
    OBJECTIVE_TOKENS,
    banned_keys,
    machine_path_hits,
    tokens,
)

SCHEMA_BUNDLE = "spot.stage02_temporal_arm_bundle.v1"
SCHEMA_VERIFICATION = "spot.stage02_temporal_arm_verification.v1"
SCHEMA_REPORT = "spot.stage02_temporal_arm_verifier_report.v1"

BUNDLE_KIND = "temporal"

# --------------------------------------------------------------------------- #
# THE ON-DISK LAYOUT. One place, so converging on a producer's native filename set is a
# reviewed DATA change and not a rewrite of the verifier.
#
# These are the names the producer at this base ACTUALLY writes. They are not a preference:
# they are what the bytes on disk are called, and a verifier that looked for a name nobody
# emits would report a missing artifact for a release that is entirely present.
# --------------------------------------------------------------------------- #
BUNDLE_FILENAME = "arm_bundle.json"
PROVENANCE_FILENAME = "temporal_provenance.json"
VERIFICATION_FILENAME = "temporal_verification.json"
RANKINGS_DIRNAME = "rankings"
PREFLIGHT_FILENAME = "temporal_preflight.json"

# THE PRODUCER'S IMMUTABLE ROOT INVENTORY. Mandatory: it is the single artifact that says
# WHAT the release IS, and a verifier that shrugged at its absence would admit whatever
# happened to be lying in the directory.
INVENTORY_FILENAME = "temporal_arm_release.json"
SCHEMA_INVENTORY = "spot.stage02_temporal_arm_release.v1"

# THIS LANE'S EXTERNAL ADMISSION — ONE file, at the RELEASE ROOT. Never inside a bundle
# directory: the producer's bundle dirs and its preflight are its own, and an external
# verifier that rewrote them would be editing the evidence it was judging.
#
# The filename, the schema, the id rule and the binding set are THE AGGREGATE'S. It is the
# reader, and a producer of an artifact nobody can read has not produced it. Its rules:
#   * ``report_id`` is the FULL sha256 of the canonical JSON excluding ``report_id`` —
#     the same self-hash rule the producer's inventory declares, so one rule covers both;
#   * the admission binds the producer's release IDENTITY and its RAW BYTES, so a reader
#     can prove the admission is over the release it is actually holding. An envelope that
#     admits a different release is an admission of something else.
ENVELOPE_FILENAME = "temporal_arm_external_admission.json"
SCHEMA_ENVELOPE = "spot.stage02_temporal_arm_external_admission.v1"

# The name the producer used to write its self-signed verdict under. It must not exist:
# neither at the root, nor in a bundle directory.
LEGACY_VERDICT_FILENAME = "temporal_verification.json"

SCHEMA_PROVENANCE = "spot.stage02_temporal_arm_provenance.v1"
SCHEMA_RANKING = "spot.stage02_temporal_arm_ranking.v1"

# The perturbation, and the ONE orientation rule Stage 3 reads.
PERTURBATION_MODALITY = "CRISPRi_knockdown"
MOD_NOT_EVALUABLE = "not_evaluable"
MOD_SUPPORTS_INHIBITION = "supports_target_inhibition"
MOD_OPPOSED_NEEDS_ACTIVATION = "opposed_would_require_target_activation"
MOD_NO_RESPONSE = "no_directional_response"

# --------------------------------------------------------------------------- #
# The exact key allowlists, per record kind.
# --------------------------------------------------------------------------- #
BUNDLE_KEYS = frozenset({
    "schema_version", "bundle_kind", "lane", "analysis_mode", "context", "bundle_key",
    "bundle_id", "from_condition", "to_condition",
    "n_programs", "n_desired_changes", "n_arms", "n_targets", "n_base_records",
    "arm_keys", "base_records", "arms", "program_admission", "estimand", "perturbation",
    "method", "code_identity", "env_lock", "endpoint_source", "stage1_binding",
    "external_admission_requirement", "preflight_ref", "bundle_is_pair_agnostic",
    "bundle_carries_role_or_pole",
})

# WHICH ENVIRONMENT the release was built in. Its own block, so it can be refused on its own.
ENV_LOCK_KEYS = frozenset({
    "env_lock_sha256", "env_lock_name", "env_lock_rule_id", "env_lock_is_synthetic",
    "env_lock_verified_from_bytes",
})

# WHERE THE TWO NUMBERS CAME FROM. A temporal arm is a difference of two within-condition
# numbers, and this says whether anybody measured them.
ENDPOINT_SOURCE_KEYS = frozenset(
    {"endpoint_source", "env_lock_sha256"}
    | {f"{e}_{k}" for e in ("from", "to") for k in
       ("direct_bundle_id", "direct_bundle_sha256", "arm_rows_sha256",
        "scorer_view_sha256", "gene_universe_sha256", "w10_report_sha256")})

# WHAT the bundle REQUIRES of an external admission — a requirement, never a verdict.
EXTERNAL_ADMISSION_REQUIREMENT_KEYS = frozenset({
    "required_report_schema_version", "required_verifier_id", "scope",
})
# WHERE the producer's own preflight lives. A pointer to a self-check, not to an admission.
PREFLIGHT_REF_KEYS = frozenset({
    "preflight_file", "preflight_schema_version", "preflight_verifier_id",
    "provenance_file",
})

CONTEXT_KEYS = frozenset({"from_condition", "to_condition"})

# The perturbation and the SUGGESTIVE modulation rule, stated ONCE at bundle scope.
PERTURBATION_KEYS = frozenset({
    "perturbation_modality", "modulation_rule_id", "positive_response_to_knockdown",
    "negative_response_to_knockdown", "null_or_unresolved_response",
    "pharmacologic_reversibility_assumed", "is_suggestive_not_confirmatory",
    "modulations",
})

# WHERE the independent verification lives and WHO signs it. A POINTER, never a verdict.


ARM_KEYS = frozenset({
    "arm_key", "program_id", "desired_change", "from_condition", "to_condition",
    "n_targets", "n_evaluable", "n_ranked", "records", "ranking",
})

# Each arm BINDS the bytes its rank and counts stand on.
RANKING_BINDING_KEYS = frozenset({"path", "raw_sha256", "canonical_sha256"})
RANKING_FILE_KEYS = frozenset({"schema_version", "arm_key", "ranked"})

ARM_RECORD_KEYS = frozenset({
    "target_id", "base_key", "arm_value", "evaluable", "temporal_status",
    "desired_target_modulation", "rank",
})

_ENDS = ("from", "to")
_ENDPOINT_FIELDS = (
    "present", "delta", "projection_status", "evaluable", "state", "reasons",
    "released_estimate_id", "base_qc_passed", "base_qc_state", "base_qc_reasons",
    # the marker/control decomposition: the two means the delta is the difference of
    "panel_mean", "control_mean", "n_panel_surviving", "n_control_surviving",
    # upstream QC provenance, carried verbatim
    "qc_ontarget_significant", "qc_ontarget_effect_size", "qc_target_baseMean",
    "qc_low_target_expression",
    # the exact contributor mask that produced the projection
    "mask_resolved", "estimate_mask_sha256", "mask_gene_count", "mask_unresolved_reason",
    # the support denominators
    "n_guide_slots_released", "n_guides_mapped", "n_guides_evaluated", "n_splits_total",
    "n_splits_evaluable", "donor_split_denominator", "effective_donor_n", "n_cells_target",
)
BASE_RECORD_KEYS = frozenset(
    {"base_key", "program_id", "target_id", "target_symbol", "target_ensembl",
     "target_id_namespace", "perturbation_modality", "from_condition", "to_condition",
     "temporal_status", "evaluable", "base_delta"}
    | {f"{e}_{k}" for e in _ENDS for k in _ENDPOINT_FIELDS})

PROGRAM_ADMISSION_KEYS = frozenset({
    "program_admission_rule_id", "program_admission_rule", "programs_derived_from",
    "programs_copied_from_a_list", "program_count_is_derived",
    "registry_scorer_view_sha256", "programs", "n_programs",
})

ESTIMAND_KEYS = frozenset({
    "estimator_id", "estimator_version", "estimand_id", "estimand_level",
    "estimand_is_per_cell_fate", "estimand_is_lineage_traced",
    "estimand_is_author_early_late_cluster_class", "estimand_is_a_rate_or_slope",
    "formula_id", "base_formula_id", "base_formula", "arm_value_formula_id",
    "arm_value_formula", "sign_transform_quantity", "sign_by_desired_change",
    "arms_are_sign_transforms_of_one_base_delta", "arms_are_two_experimental_estimates",
    "rank_rule", "inference_status", "no_pq_reason",
})

RANK_RULE_KEYS = frozenset({
    "rank_population", "rank_direction", "rank_tie_break", "rank_null_rule",
    "rank_numbering", "ranks_are_independent_per_desired_change",
    "rank_inferred_from_the_other_arm",
})

METHOD_KEYS = frozenset({
    "estimator_id", "estimator_version", "temporal_method_sha256",
    "direct_method_version", "direct_config_sha256", "effect_source_sha256",
    "effect_universe_sha256", "inference_status",
})

# ``temporal_verification.json`` — the verdict file. NOTE WHAT THIS IS AND IS NOT: the
# producer writes it, so as shipped it is a SELF-REPORT. It is recorded and never counted as
# evidence here, and a producer-written verdict that signs itself with the INDEPENDENT
# verifier's id is refused by name (see ``verify._verdict_file``).
VERIFICATION_KEYS = frozenset({
    "schema_version", "verifier_id", "generator_is_not_verifier", "fail_closed",
    "verdict", "n_failed", "failed_gates", "checks", "bundle_id", "binds",
    "required_gates",
})
VERIFICATION_BINDS_KEYS = frozenset({"arm_bundle_sha256", "provenance_sha256"})

# ---- the producer's IMMUTABLE root inventory ----
INVENTORY_KEYS = frozenset({
    "schema_version", "lane", "analysis_mode", "n_bundles", "n_logical_arms", "bundles",
    "arm_keys", "external_admission", "stage1_binding", "topology", "env_lock",
    "env_lock_sha256", "release_id", "release_id_rule",
})
TOPOLOGY_KEYS = frozenset({
    "topology_rule_id", "selector_condition_sequence", "ordered_pairs", "expected_arm_keys",
    "expected_n_bundles", "expected_n_logical_arms", "n_conditions", "n_desired_changes",
    "n_ordered_pairs", "n_programs",
})
INVENTORY_BUNDLE_KEYS = frozenset({
    "bundle_key", "bundle_id", "from_condition", "to_condition", "relative_dir", "n_arms",
    "arm_keys", "files", "rankings",
})
INVENTORY_FILE_KEYS = frozenset({"raw_sha256", "canonical_sha256"})
# The producer says PENDING and names what it requires. It never says admit.
EXTERNAL_ADMISSION_KEYS = frozenset({
    "required_report_schema_version", "required_verifier_id", "status",
})
EXTERNAL_ADMISSION_PENDING = "pending"
# TWO PROJECTION BINDINGS, AND NEITHER SUBSTITUTES FOR THE OTHER: the SCALAR asks "is this
# the same program axis?", the 10-key MAP asks "...and if not, WHICH program moved?". The
# scalar alone cannot name the program; the map alone lets a producer ship ten
# self-consistent hashes over an axis Stage-2 never bound. Both required, both re-derived.
STAGE1_BINDING_KEYS = frozenset({
    "admitted_programs", "selector_condition_sequence", "n_conditions", "n_programs",
    "programs_derived_from", "registry_scorer_view_sha256",
    "registry_scorer_projection_sha256", "per_program_projection_sha256",
    "per_program_projection_rule_id",
    "release_self_sha256", "scorer_view_raw_sha256", "scorer_view_canonical_sha256",
    "effect_source_sha256", "effect_universe_sha256",
})

# A NULL BINDING IS NOT A BINDING. Each of these must be present AND non-null AND equal to
# what this lane independently derived from the Stage-1 release it loaded. A field that is
# allowlisted but never checked is a field that can say anything — which is exactly how a
# release ships with its identity set to null and is admitted anyway.
STAGE1_BINDING_REQUIRED_NONNULL = frozenset({
    "per_program_projection_rule_id",
    "registry_scorer_view_sha256", "registry_scorer_projection_sha256",
    "per_program_projection_sha256", "release_self_sha256", "scorer_view_raw_sha256",
    "scorer_view_canonical_sha256", "selector_condition_sequence", "admitted_programs",
    "programs_derived_from", "effect_source_sha256", "effect_universe_sha256",
})

# ---- the producer's own preflight: RECORDED, never evidence ----
PREFLIGHT_KEYS = frozenset({
    "schema_version", "preflight_id", "role", "status", "self_check_passed",
    "generator_is_not_verifier", "is_admission", "n_gates_checked", "n_failed",
    "failed_gates", "checks",
})

# ---- WHICH BUILD produced the bytes ----
CODE_IDENTITY_KEYS = frozenset({
    "digest_id", "include_rule_id", "binding_rule_id", "digest_root", "commit",
    "clean_tree", "n_dirty_paths", "manifest_sha256", "canonical_digest", "n_files",
    "clean_checkout_required",
})

PROVENANCE_KEYS = frozenset({
    "schema_version", "bundle_id", "bundle_key", "lane", "context", "bundle_file",
    "bundle_raw_sha256", "bundle_canonical_sha256", "n_programs", "n_arms", "n_targets",
    "n_base_records", "method", "program_admission", "estimand", "run_binding",
})
# A FIXED EXACT-KEY object. Each bound hash is its OWN named field: a method hash is not a
# build, and a build is not a method, so ``code_identity`` sits beside them, not inside them.
RUN_BINDING_KEYS = frozenset({
    "code_identity", "estimator_id", "estimator_version", "temporal_method_sha256",
    "stage2_inputs", "selection_release",
})

# THE CANONICAL STAGE-2 INPUTS — ONE fixed-key object, not five fields loose in run_binding
# and not a list of {role, value} pairs. The field name IS the role, so there is nothing to
# interpret and nothing to drift; and because it is ONE object, "the inputs" is a thing a
# reader can hash, compare and refuse as a unit rather than five things it might forget one
# of. Every one of these is REQUIRED and none may be null.
STAGE2_INPUTS_KEYS = frozenset({
    "direct_method_version", "direct_config_sha256", "effect_source_sha256",
})
# The STAGE-1 binding, independently verifiable. No pair and no pole field.
SELECTION_RELEASE_KEYS = frozenset({
    "registry_scorer_view_sha256", "programs_derived_from", "admitted_programs",
    "n_programs", "effect_universe_sha256", "effect_source_sha256",
})

# The producer's OWN report, recorded and NEVER trusted. Allowlisted so the file can be
# read at all; it contributes no evidence to this verifier's verdict.
PRODUCER_REPORT_KEYS = frozenset({
    "admitted", "failures", "n_arms", "n_base_records", "bundle_id", "bundle_key",
})

# THE INDEPENDENT VERIFIER'S CONTRACT ID. A producer that wants to say "this artifact was
# verified" must reference THIS contract — a producer referencing its own self-verification
# id is claiming an independent check it performed on itself, which is the one thing a
# verification reference must never be able to mean.
INDEPENDENT_VERIFIER_CONTRACT = "spot.stage02.temporal.arm.independent_verifier.v1"

# OPTIONAL, because the producer at this base does not emit it yet. It is not invented into
# existence here: when it is present it MUST name the contract above, and when it is absent
# that is recorded rather than assumed to be fine.
PRODUCER_REPORT_OPTIONAL_KEYS = frozenset({"verification_ref"})



class SchemaRejected(ValueError):
    """The artifact is not the one the contract describes. Refuse; never repair."""



def unknown_keys(got: Any, allowed: Iterable[str]) -> list[str]:
    """Keys the contract does not authorise. An unknown key is an unauthorised claim."""
    return sorted(set(got) - set(allowed))


def missing_keys(got: Any, allowed: Iterable[str]) -> list[str]:
    """Keys the contract requires. A missing one means this is not that artifact."""
    return sorted(set(allowed) - set(got))


def exact_keys(got: Any, allowed: Iterable[str], what: str) -> list[str]:
    """Both directions at once, as named failures."""
    return ([f"{what}.unknown_key:{k}" for k in unknown_keys(got, allowed)]
            + [f"{what}.missing_key:{k}" for k in missing_keys(got, allowed)])
