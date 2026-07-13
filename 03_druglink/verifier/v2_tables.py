"""The SEVEN v2 tables, RESTATED. Imports nothing from ``druglink``.

Written out again from the contract rather than imported from the producer. A verifier that
imported ``druglink.candidates_v2.TABLES`` would bless whatever column set the producer
happened to define today, and could only prove the producer agreed with itself. If the two
restatements ever disagree, verification FAILS — which is the point.

Two tables exist because their ABSENCE is the defect:

``arm_slots``
    EVERY arm slot the release resolved, including the ones no drug evidence reached. Without
    it, "this arm had no drug evidence" and "this arm never ran" are the same silence, and a
    consumer counting rows reports the second as the first. Silent zero-coverage wearing a
    green check is the defect this project keeps finding.

``source_records``
    Every VERBATIM source assertion, INCLUDING the ones that may never rank a gene — the
    variant-specific and ambiguous-identity lanes. A dropped assertion is indistinguishable
    from a drug nobody found.

ABSENCE IS A VALUE
------------------
Every nullable magnitude travels with a companion ``*_status`` that SAYS why it is absent. A
null a consumer coerces becomes a 0, and a 0 sorts — which is exactly how an unranked target
reaches first place.
"""
from __future__ import annotations

from typing import Any, Mapping

from . import canon

# --------------------------------------------------------------------------- #
# The missingness vocabulary. Restated.
# --------------------------------------------------------------------------- #
STATED = "stated"
NOT_STATED = "not_stated_by_source"
NOT_APPLICABLE_INFERRED = "not_applicable_inferred_origin"
RANKED = "ranked"
UNRANKED = "unranked_by_source"
NO_DRUG_EVIDENCE = "no_general_drug_evidence"
MISSINGNESS_STATES = (STATED, NOT_STATED, NOT_APPLICABLE_INFERRED, RANKED, UNRANKED,
                      NO_DRUG_EVIDENCE)

# (value column, status column, table). The status must be a known state, it must not claim
# a value that is absent, and a null must never have become a 0.
STATED_ABSENCE = (
    ("arm_rank", "arm_rank_status", "target_drug_edges"),
    ("arm_value_source_string", "arm_value_status", "target_drug_edges"),
    ("on_target_evidence", "on_target_evidence_status", "target_drug_edges"),
    ("max_phase_source", "max_phase_status", "target_drug_edges"),
    ("max_phase_source", "max_phase_status", "source_records"),
    ("inchikey", "inchikey_status", "source_records"),
)

# Columns a downstream stage joins or reopens on. An empty string satisfies a schema and
# proves nothing, so each is asserted NON-EMPTY on every row of its table.
#
# THE TWO SIGN FIELDS ARE IN HERE ON PURPOSE. `observed_perturbation_modality` says what was
# TESTED and `observed_sign_state` says whether it HELPED; a bundle that carries an edge missing
# either of them has an edge whose direction nobody can check.
REQUIRED_NON_EMPTY = {
    "arm_slots": ("arm_slot_id", "arm_key", "lane", "program_id", "desired_change",
                  "origin_type", "arm_evidence_state", "arm_context_sha256"),
    "target_drug_edges": ("edge_id", "arm_key", "origin_type", "target_id",
                          "target_id_namespace", "candidate_id", "active_moiety_id",
                          "source_record_id", "source_locator", "source_release",
                          "action_type_source", "directional_evidence_status",
                          "direction_vocabulary_digest", "modality_vocabulary_digest",
                          "observed_perturbation_modality", "observed_sign_state",
                          "desired_target_modulation", "stage2_desired_target_modulation",
                          "stage2_phenocopy_class", "mechanism_match_status",
                          "evidence_relation", "evidence_relation_caveat",
                          "arm_rank_status", "arm_value_status", "max_phase_status",
                          "stage2_aggregate_verifier_id", "stage2_aggregate_verdict"),
    "arm_summaries": ("arm_summary_id", "candidate_id", "active_moiety_id", "arm_key",
                      "origin_type", "arm_evidence_state", "evidence_relation_caveat"),
    "candidates": ("candidate_id", "active_moiety_id", "identity_status",
                   "max_phase_status", "stage4_assessment_status",
                   "stage4_assessment_reason", "evidence_relation_caveat"),
    "source_records": ("source_record_id", "candidate_id", "active_moiety_id",
                       "target_id", "target_id_namespace", "assertion_lane",
                       "action_type_source", "source_locator", "source_scheme",
                       "source_release", "source_sha256", "source_license",
                       "max_phase_status", "inchikey_status"),
    "dispositions": ("disposition_id", "subject_kind", "subject_id", "state", "reason"),
    "provenance": ("provenance_id", "kind", "subject", "detail"),
}

# The arm identity every row that names an arm carries. A ROLE (away_from_A / toward_B) is
# what a SELECTION gives an arm at join time; there is no column for one, anywhere.
ARM_IDENTITY_COLUMNS: tuple[str, ...] = (
    "arm_key", "lane", "program_id", "desired_change",
    "condition", "from_condition", "to_condition", "pathway_source",
    "arm_context_sha256",
)

# Every upstream identity an emitted row stands on. A row nobody can trace is a row nobody
# can check.
#
# THE NATIVE ADMISSION KEYS. The retired columns read `stage2_independent_verifier_id` /
# `stage2_independent_verdict` — keys Stage-2's loader has NEVER emitted. Every edge therefore
# carried a NULL verifier identity and a NULL verdict, and nothing crashed; the verifier read the
# same wrong keys, so producer and verifier AGREED on None and the reconstruction matched. A
# binding both sides get wrong in the same way is a binding nobody has. These are the real ones,
# and a null in either is a NAMED refusal.
UPSTREAM_COLUMNS: tuple[str, ...] = (
    "stage2_manifest_raw_sha256", "stage2_manifest_canonical_sha256",
    "stage2_manifest_self_hash", "stage2_aggregate_verifier_id",
    "stage2_aggregate_verdict", "stage1_release_sha256",
    "bundle_key", "bundle_raw_sha256", "bundle_canonical_sha256",
    "ranking_raw_sha256", "ranking_canonical_sha256",
    "universe_store_id", "typed_universe_sha256",
)

ARM_SLOT_COLUMNS: tuple[str, ...] = (
    ("arm_slot_id",)
    + ARM_IDENTITY_COLUMNS
    + ("origin_type", "origin_is_measured", "condition_pair_is_ordered",
       # `n_records` counts ROWS; `n_ranked` counts NON-NULL RANKS. They are DIFFERENT numbers,
       # and a hit count taken from rows inflates by exactly the targets the arm could not
       # evaluate — the ones least entitled to support a claim.
       "n_records", "n_ranked", "n_targets", "n_targets_in_admitted_universe",
       "n_source_assertions", "n_rankable_assertions", "n_edges",
       "arm_evidence_state", "directional_evidence_statuses", "target_ids")
    + UPSTREAM_COLUMNS
)

EDGE_COLUMNS: tuple[str, ...] = (
    ("edge_id",)
    + ARM_IDENTITY_COLUMNS
    + ("origin_type", "origin_is_measured",
       # THE TWO FACTS, IN SEPARATE FIELDS. The modality says WHAT WAS TESTED and stands alone;
       # the sign says whether doing it HELPED. `desired_target_modulation` is DERIVED FROM BOTH
       # — never from the modality alone — and `stage2_desired_target_modulation` is the
       # producer's own serialized token, carried so the verifier can REQUIRE it to equal the
       # sign it re-derived for itself.
       "observed_perturbation_modality", "observed_sign_state", "desired_target_modulation",
       "stage2_desired_target_modulation", "stage2_phenocopy_class",
       # On an OPPOSING sign the compatible action is NULL: the screen supports nothing, and the
       # inverse is named as the untested hypothesis it is.
       "observed_compatible_action", "untested_inverse_action",
       "pharmacologic_reversibility_assumed",
       # PHENOCOPY, NOT EQUIVALENCE — as FIELDS, because Stage 4 reads fields. An agonist on a
       # CRISPRi arm carries the UNTESTED-INVERSE relation, never a phenocopy relation.
       "evidence_relation", "evidence_relation_caveat", "evidence_is_equivalence",
       "mechanism_phenocopies_modality",
       "target_id", "target_id_namespace", "target_symbol", "target_ensembl",
       "released_estimate_id", "set_id",
       # PATHWAY CONTEXT on an edge whose evidence is MEASURED. The pathway says which set the
       # target sits in; it contributed no direction and sourced no claim.
       "pathway_refs", "n_pathway_refs",
       "arm_rank", "arm_rank_status", "arm_evaluable",
       "arm_value_source_string", "arm_value_canonical_decimal", "arm_value_status",
       "on_target_evidence", "on_target_evidence_status",
       "mechanism_match_status",
       "source_record_id", "source_locator", "source_release",
       "mec_id", "molecule_chembl_id", "target_chembl_id",
       "candidate_id", "active_moiety_id", "assertion_lane", "general_gene_rankable",
       "action_type_source", "action_type_normalized",
       "max_phase_source", "max_phase_status", "max_phase_is_context_only",
       "direction_vocabulary_digest", "modality_vocabulary_digest",
       "intervention_effect", "intervention_effect_reason",
       "directional_evidence_status", "directional_evidence_reason",
       "observed_perturbation_support", "stage3_evidence_class")
    + UPSTREAM_COLUMNS
)

# The pathway CONTEXTUALIZES a measured edge; it never sources one. The lane is NOT ADMITTED, so
# this table must be EMPTY — and the column contract is restated anyway, because "empty" has to be
# a checked fact about a table that exists, not the silence of a table nobody emitted.
PATHWAY_CONTEXT_COLUMNS: tuple[str, ...] = (
    "pathway_context_id", "arm_key", "lane", "program_id", "desired_change",
    "pathway_id", "pathway_source", "coverage", "convergence",
    "target_id", "target_id_namespace",
    "has_measured_support", "measured_support_status",
    "n_drug_edges_contextualized",
)

ARM_SUMMARY_COLUMNS: tuple[str, ...] = (
    ("arm_summary_id", "candidate_id", "active_moiety_id")
    + ARM_IDENTITY_COLUMNS
    + ("origin_type", "arm_evidence_state", "n_edges",
       "n_observed_perturbation", "n_inverse_direction_hypothesis",
       "n_pathway_hypothesis", "n_opposed", "n_unresolved",
       "observed_perturbation_support", "stage3_evidence_classes",
       "evidence_relations", "evidence_is_equivalence", "evidence_relation_caveat",
       "mechanism_match_statuses", "n_edges_by_mechanism_match",
       "observed_perturbation_modalities", "observed_sign_states",
       "desired_target_modulations",
       "edge_ids", "arm_ranks", "target_ids")
)

CANDIDATE_COLUMNS: tuple[str, ...] = (
    "candidate_id", "active_moiety_id", "preferred_name", "identity_status",
    "molecule_chembl_ids", "inchikey", "molecule_types",
    "n_edges_by_origin", "n_arm_summaries_by_origin",
    "arm_keys", "origin_types", "lanes", "program_ids", "target_ids",
    "observed_perturbation_arm_keys", "inverse_direction_hypothesis_arm_keys",
    "pathway_hypothesis_arm_keys", "opposed_arm_keys", "unresolved_arm_keys",
    "observed_perturbation_support", "stage3_evidence_classes",
    # Carried on the CANDIDATE too: Stage 4 reads the candidate row, and must never mistake a
    # putative phenocopy for an equivalence, nor an untested inverse for a measurement.
    "evidence_relations", "evidence_is_equivalence", "evidence_relation_caveat",
    "mechanism_match_statuses", "n_edges_by_mechanism_match",
    "observed_perturbation_modalities", "observed_sign_states", "desired_target_modulations",
    "max_phase_sources", "max_phase_status", "max_phase_is_context_only",
    "source_locators", "source_releases", "source_licenses",
    "stage4_assessment_status", "stage4_assessment_reason",
    "source_record_ids",
)

SOURCE_RECORD_COLUMNS: tuple[str, ...] = (
    "source_record_id", "mec_id", "molecule_chembl_id", "target_chembl_id",
    "pref_name", "molecule_type", "inchikey", "inchikey_status",
    "candidate_id", "active_moiety_id", "identity_status",
    "target_id", "target_id_namespace", "target_disposition",
    "assertion_lane", "general_gene_rankable",
    "action_type_source", "mechanism_of_action", "mechanism_refs",
    "selectivity_comment", "direct_interaction", "molecular_mechanism",
    "disease_efficacy",
    "max_phase_source", "max_phase_canonical", "max_phase_status",
    "max_phase_is_context_only",
    "variant_id", "variant_specific", "variant_disposition", "ambiguity_disposition",
    "direction_decided_in_cache", "edge_policy_version",
    "source_locator", "source_scheme", "source_release", "source_sha256", "source_license",
    "source_required_attribution",
    "chembl_release", "chembl_source_sha256", "chembl_license",
    "chembl_required_attribution", "uniprot_release", "uniprot_source_sha256",
    "uniprot_license",
    "universe_store_id", "typed_universe_sha256",
)

DISPOSITION_COLUMNS: tuple[str, ...] = (
    "disposition_id", "subject_kind", "subject_id", "state", "reason", "detail",
    "target_id", "target_id_namespace", "arm_key", "origin_type", "candidate_id",
    "source_record_id",
)

PROVENANCE_COLUMNS: tuple[str, ...] = (
    "provenance_id", "kind", "subject", "raw_sha256", "canonical_sha256",
    "verifier_id", "verdict", "detail",
)

# The column allowlist IS the contract: an unknown column is a field nobody agreed to, and no
# downstream consumer can be expected to refuse it.
TABLES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "arm_slots": (ARM_SLOT_COLUMNS, ("arm_slot_id",)),
    "target_drug_edges": (EDGE_COLUMNS, ("edge_id",)),
    "pathway_context": (PATHWAY_CONTEXT_COLUMNS, ("pathway_context_id",)),
    "arm_summaries": (ARM_SUMMARY_COLUMNS, ("arm_summary_id",)),
    "candidates": (CANDIDATE_COLUMNS, ("candidate_id",)),
    "source_records": (SOURCE_RECORD_COLUMNS, ("source_record_id",)),
    "dispositions": (DISPOSITION_COLUMNS, ("disposition_id",)),
    "provenance": (PROVENANCE_COLUMNS, ("provenance_id",)),
}

# The seven the verifier rebuilds ROW FOR ROW from the Stage-2 bundles and the admitted store.
# `pathway_context` is in here precisely BECAUSE it must be empty: an unadmitted lane's zero
# contribution is a fact to be reconstructed and compared, not a table to skip.
#
# `provenance` is the one exception: it binds the artifacts the bundle stands on, and its
# code/vocabulary digests are properties of the PRODUCER's tree — a verifier that recomputed them
# would be re-running the producer. It is checked against what THIS verifier re-admitted from
# disk instead (see verifier.v2_stage4.check_provenance).
RECONSTRUCTED_TABLES = ("arm_slots", "target_drug_edges", "pathway_context", "arm_summaries",
                        "candidates", "source_records", "dispositions")

# DISPLAY only: excluded from the CONTENT hash (a symbol is a label; the typed identity is the
# identity), and still covered by the FILE hash.
DISPLAY_COLUMNS = frozenset({"preferred_name", "pref_name", "target_symbol"})


def cell(value: Any) -> Any:
    """The exact value a table CELL holds. Restated, not imported.

    Lists and maps travel as canonical JSON STRINGS, so what is hashed is what is written and
    a re-read from parquet reproduces it byte for byte. A float never enters a Stage-3 hash:
    every magnitude travels as an exact source string plus a canonical decimal.
    """
    if isinstance(value, (list, tuple, dict)):
        return canon.cjson(value)
    if isinstance(value, float):
        raise canon.VerifierCanonError(
            f"a table cell holds the float {value!r}; every magnitude travels as an exact "
            "source string plus a canonical decimal")
    return value


def project(name: str, rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The rows as the contract defines them: exactly the allowlisted columns, encoded."""
    cols = TABLES[name][0]
    return [{c: cell(r.get(c)) for c in cols} for r in rows]


def content_hash(name: str, rows: list[Mapping[str, Any]]) -> str:
    """The row-order-invariant CONTENT hash the bundle BINDS — display columns excluded.

    A symbol is a label; the typed identity is the identity. Display-only columns are excluded
    from the content address (so renaming a gene cannot move a bundle id) and are still covered
    by the FILE hash — which is what catches one tampered with in the parquet.
    """
    cols, sort_keys = TABLES[name]
    content_cols = [c for c in cols if c not in DISPLAY_COLUMNS]
    keys = tuple(k for k in sort_keys if k in content_cols) or (content_cols[0],)
    return canon.table_hash([{c: cell(r.get(c)) for c in content_cols} for r in rows], keys)


def full_hash(name: str, rows: list[Mapping[str, Any]]) -> str:
    """EVERY column, display included. Used to compare an emitted table to the independent
    reconstruction: the bundle id need not cover a label, but the reconstruction still must
    reproduce it exactly."""
    return canon.table_hash(project(name, rows), TABLES[name][1])
