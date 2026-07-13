"""The Stage-3 **v2** artifact contract, RESTATED for the independent verifier.

Imports NOTHING from ``druglink``. Every rule below is written out again from the v2
design (audit steps 1-8), exactly as ``verifier/policy.py`` restates the v1 rules. If the
producer and this file ever disagree, verification FAILS — which is the point. A verifier
that imported ``druglink.stage2_aggregate`` / ``druglink.direction`` would bless whatever
those modules decided to do today, and could only prove the producer agreed with itself.

This lane has met that defect five times: B6 (a manifest that never recomputed its own
identity), M4b (a verifier that was a stale copy of its generator's rule), the temporal
``verification_ref`` pointing at the producer's own module, a producer's ``pending`` release
read as an admission, and — the verifier's own — admitting a store because *its* check
passed while the *producer's* gate was fail-open.

WHAT THE v2 BUNDLE IS
---------------------
A content-addressed directory:

    manifest.json            self-hashing; inventories every file by content AND file hash
    <document_file>          the drug-annotation document (name is DATA, read from manifest)
    <table>.parquet          the five v2 tables (:data:`TABLES`)

Identity is derived, never declared::

    canonical_content_sha256 = chash(document - {bundle_id, canonical_content_sha256,
                                                 document_sha256, created_at})
    bundle_id                = prefix[artifact_class] + canonical_content_sha256[:16]
    document_sha256          = chash(document - {document_sha256})
    manifest_sha256          = chash(manifest  - {manifest_sha256, created_at})

Paths and timestamps stay OUTSIDE scientific content addressing, so the same inputs
rebuild the same id.
"""
from __future__ import annotations

from typing import Any

from . import v2_admission as v2
from .v2_admission import (  # noqa: F401  (one front door: `v2_store` reads it off THIS module)
    ADMISSION_REPORT_SHA256,
    ADMITTED_PRODUCER_COMMIT,
    ADMITTED_STORE_ID,
)
from .v2_direction import (  # noqa: F401  (one front door for the restated vocabulary)
    ABUNDANCE_REDUCTION,
    ACTION_ABUNDANCE_REDUCTION,
    ACTION_EXPLICIT_UNKNOWN,
    ACTION_FUNCTIONAL_ACTIVATION,
    ACTION_FUNCTIONAL_INHIBITION,
    DIRECTION_POLICY_VERSION,
    EFFECT_UNKNOWN,
    FUNCTIONAL_ACTIVATION,
    FUNCTIONAL_INHIBITION,
    INTERVENTION_EFFECTS,
    OBJECTIVE_DECLARATIONS,
    OBJECTIVE_KEYS,
    OBJECTIVE_PREFIXES,
    REASON_NON_RANKABLE_LANE,
    STAT_KEY_RE,
    VerifierContractError,
    canonical_number,
    direction_vocabulary_digest,
    intervention_effect,
    is_objective_key,
    is_stat_key,
    objective_keys_in,
    stage4_assessment,
    stat_keys_in,
    summary_state,
    true_objective_declarations,
    value_strings,
    walk_keys,
)
from .v2_sign import (  # noqa: F401  (one front door for the restated SIGN rule)
    FIELD_ARM_VALUE,
    FIELD_EVALUABLE,
    FIELD_MODALITY,
    FIELD_MODULATION,
    FIELD_NAMESPACE,
    FIELD_PHENOCOPY_CLASS,
    GATE_CLAIMS_EQUIVALENCE,
    GATE_EDGE_SIGN_DISAGREES_WITH_ITS_OWN_ARM_VALUE,
    GATE_EVALUABILITY_NOT_DECLARED,
    GATE_MODALITY_NOT_DECLARED,
    GATE_MODALITY_VOCABULARY_DIVERGENCE,
    GATE_MODULATION_DERIVED_FROM_MODALITY_ALONE,
    GATE_NAMESPACE_NOT_DECLARED,
    GATE_NO_EVIDENCE_RELATION,
    GATE_NON_PHENOCOPY_IN_SUPPORTED_EVIDENCE,
    GATE_PHENOCOPY_CLASS_NOT_DECLARED,
    GATE_SERIALIZED_MODULATION_DISAGREES_WITH_THE_SIGN,
    GATE_SIGN_READ_FROM_AN_INFERRED_ROW,
    GATE_SUPPORTED_ON_A_NON_SUPPORTING_SIGN,
    GATE_UNKNOWN_MODALITY,
    GATE_UNKNOWN_NAMESPACE,
    GATE_UNKNOWN_SERIALIZED_MODULATION,
    MOD_DECREASE,
    MOD_INCREASE,
    MOD_NO_DIRECTION,
    MOD_NOT_EVALUATED,
    MODALITY_CRISPRA,
    MODALITY_CRISPRI,
    MODALITY_PERFORMED_ACTION,
    PHENOCOPY_RELATIONS,
    SIGN_EPS,
    SIGN_NO_DIRECTIONAL_RESPONSE,
    SIGN_NOT_EVALUABLE,
    SIGN_OPPOSES_DESIRED_CHANGE,
    SIGN_STATES,
    SIGN_SUPPORTS_DESIRED_CHANGE,
    TARGET_MODULATIONS,
    W3_NAMESPACES,
    W3_REQUIRED_ROW_FIELDS,
    SignRuleError,
    check_serialized_modulation,
    classify,
    declared_modality,
    desired_target_modulation,
    evaluable_of,
    namespace_of,
    observed_sign_state,
    phenocopies,
    phenocopy_class_of,
    phenocopying_actions,
)
from .v2_sign_gates import (  # noqa: F401  (the SIGN gates, on the rows actually emitted)
    agonists_in_supported_evidence,
    edge_refusals,
    semantic_vocabulary,
)
from .v2_tables import (  # noqa: F401  (one front door for the restated table contract)
    RECONSTRUCTED_TABLES,
    TABLES,
)

CONTRACT_ID = "spot.stage03_v2_artifact.v1"

# --------------------------------------------------------------------------- #
# Artifact class, schema, identity.
# --------------------------------------------------------------------------- #
ANALYSIS = "analysis"
FIXTURE = "fixture"
ARTIFACT_CLASSES = (ANALYSIS, FIXTURE)

# ONE schema id for both classes. The fixture firewall is carried by the fields a reader
# cannot miss — artifact_class, the fx_ bundle-id prefix, the distinct document filename and
# data_status=synthetic_fixture_only — rather than by a second schema id that a relabel would
# only have to rewrite once.
DOC_SCHEMA = "spot.stage03_drug_annotation.v2"
MANIFEST_SCHEMA = "spot.stage03_manifest.v2"
BUNDLE_ID_PREFIX = {ANALYSIS: "s3_", FIXTURE: "fx_"}

# THE PUBLISHED DOCUMENT FILENAME. Restated, because Stage 4 opens this file BY NAME.
#
# A producer that writes `drug_annotation.v2.json` and a consumer that opens
# `drug_annotation_v2.json` do not fail loudly — the reader finds nothing, and "no candidates"
# becomes indistinguishable from "no file". That is the quietest failure in the whole handoff,
# so the spelling is a NAMED gate rather than a convention.
DOC_FILE = {ANALYSIS: "drug_annotation.v2.json",
            FIXTURE: "fixture_drug_annotation.v2.json"}

DOC_IDENTITY_EXCLUDED = ("bundle_id", "canonical_content_sha256", "document_sha256",
                         "created_at")
MANIFEST_IDENTITY_EXCLUDED = ("manifest_sha256", "created_at")

# --------------------------------------------------------------------------- #
# The Stage-2 aggregate topology. DERIVED here, never read from a declared count:
# a producer that can declare its own completeness can declare a PARTIAL release
# complete, and a missing bundle then looks exactly like one computed and found empty.
# --------------------------------------------------------------------------- #
CONDITIONS = ("Rest", "Stim8hr", "Stim48hr")
PATHWAY_SOURCES = ("Reactome", "GO-BP")
DESIRED_CHANGES = ("increase", "decrease")
N_PROGRAMS = 10

LANE_DIRECT = "direct"
LANE_TEMPORAL = "temporal"
LANE_PATHWAY = "pathway"
LANES = (LANE_DIRECT, LANE_TEMPORAL, LANE_PATHWAY)
MEASURED_LANES = frozenset({LANE_DIRECT, LANE_TEMPORAL})

# The lane decides the typed origin. A consumer must never have to read `time_scope`.
ORIGIN_FOR_LANE = {LANE_DIRECT: v2.ORIGIN_DIRECT,
                   LANE_TEMPORAL: v2.ORIGIN_TEMPORAL,
                   LANE_PATHWAY: v2.ORIGIN_PATHWAY}

# --------------------------------------------------------------------------- #
# THE NATIVE STAGE-2 CONTRACT, restated. These are the bytes Stage-2's real CLIs emit.
#
# The retired restatement read an `inventory[]` array, an `admits{}` block and a verifier id
# containing the substring "independent". Stage 2 emits NONE of them: it emits `bundles[]` (each
# an all-arm bundle DIRECTORY), and its report binds the manifest TOP-LEVEL with `manifest_sha256`
# + `manifest_sha256_recomputed`. Reading `report.get("admits") or {}` against the real bytes
# yields `{}` — a check on a field that does not exist, which is not a check.
#
# INDEPENDENCE IS A STRUCTURED FIELD, NOT A NAME. The real verifier's id does not contain the
# word "independent", so a substring gate would have REFUSED the genuine report while ADMITTING
# any forgery that merely named itself "…independent…". The assertion is `generator_is_not_verifier`
# and the identity is the EXACT pinned id — both are checked, and a null is a refusal.
# --------------------------------------------------------------------------- #
STAGE2_MANIFEST_SCHEMA = "spot.stage02_run_manifest.v3_topology_only"
STAGE2_REPORT_SCHEMA = "spot.stage02_run_manifest_verification.v1"
STAGE2_AGGREGATE_VERIFIER_ID = "spot.stage02.run_manifest.verifier.v1"
ADMIT = "admit"
ADMITTED = "admitted"
SELF_HASH_FIELD = "manifest_sha256"
# The producer's SEMANTIC self-hash excludes exactly these three: the hash cannot cover itself,
# the clock is not content, and `path` is where the file happens to sit on one machine.
SELF_HASH_EXCLUDED = ("created_at", "manifest_sha256", "path")
ARM_BUNDLE_FILE = "arm_bundle.json"
# Stage 2 names the pathway axis `gene_set_source` in a bundle context; Stage 3 has always
# called it `pathway_source`. The rename happens once, here, and is recorded.
NATIVE_PATHWAY_SOURCE_KEY = "gene_set_source"
NON_SEMANTIC_FIELDS = ("generated_at", "created_at", "started_at", "finished_at",
                       "completed_at", "elapsed_seconds")

# THE PATHWAY LANE IS NOT ADMITTED, and so it must contribute EXACTLY ZERO.
#
# W3's pathway verifier FAILS OPEN to resealed target/modulation fields: a verifier that fails
# open admits precisely the artifact it was built to refuse, so its ADMIT carries no information.
# Bytes admitted by a fail-open gate are unadmitted bytes with a certificate stapled to them. The
# verifier therefore REFUSES BY NAME if the pathway lane contributed anything at all — an edge, a
# context row, a rank or a direction. Zero is the honest output, and it is checked rather than
# assumed.
PATHWAY_LANE_ADMITTED = False


def ordered_condition_pairs() -> tuple[tuple[str, str], ...]:
    """Every ORDERED pair. Rest->Stim48hr is not Stim48hr->Rest: the DiD changes sign."""
    return tuple((a, b) for a in CONDITIONS for b in CONDITIONS if a != b)


def expected_bundle_keys() -> dict[str, str]:
    """The 15 bundle keys the release must have -> their lane. Derived, never declared."""
    keys = {f"{LANE_DIRECT}|{c}": LANE_DIRECT for c in CONDITIONS}
    keys.update({f"{LANE_TEMPORAL}|{a}|{b}": LANE_TEMPORAL
                 for a, b in ordered_condition_pairs()})
    keys.update({f"{LANE_PATHWAY}|{c}|{s}": LANE_PATHWAY
                 for c in CONDITIONS for s in PATHWAY_SOURCES})
    return keys


N_BUNDLES = len(expected_bundle_keys())                       # 15
N_ARM_SLOTS = N_BUNDLES * N_PROGRAMS * len(DESIRED_CHANGES)   # 300


def entry_key(entry: dict[str, Any]) -> str:
    """The key IMPLIED by an inventory entry's own context. A key that disagrees with its
    context is a mislabelled bundle, and a mislabelled bundle fills the wrong slot."""
    lane = entry.get("lane")
    ctx = {LANE_DIRECT: (entry.get("condition"),),
           LANE_TEMPORAL: (entry.get("from_condition"), entry.get("to_condition")),
           LANE_PATHWAY: (entry.get("condition"), entry.get("pathway_source"))}.get(lane)
    return "|".join([str(lane), *(str(c) for c in ctx)]) if ctx else ""


# --------------------------------------------------------------------------- #
# The admitted universe store. Literals, not derivations: a store can be perfectly
# consistent with a universe NOBODY admitted — that is what a forgery is.
# --------------------------------------------------------------------------- #
STORE_MANIFEST_NAME = "universe_manifest.json"
STORE_ROWS_NAME = "universe_store.rows.json"
STORE_ELIGIBILITY_NAME = "target_eligibility_evidence.json"
STORE_PROVENANCE_NAME = "source_provenance.public.json"
STORE_LICENSE_NAME = "CHEMBL_LICENSE"
STORE_ATTRIBUTION_NAME = "CHEMBL_REQUIRED_ATTRIBUTION"
STORE_JSON_ARTIFACTS = (STORE_ROWS_NAME, STORE_ELIGIBILITY_NAME, STORE_PROVENANCE_NAME)
STORE_TEXT_ARTIFACTS = (STORE_LICENSE_NAME, STORE_ATTRIBUTION_NAME)
STORE_ARTIFACT_PINS = {STORE_ROWS_NAME: "store_rows_sha256",
                       STORE_ELIGIBILITY_NAME: "eligibility_evidence_sha256",
                       STORE_PROVENANCE_NAME: "public_source_provenance_sha256"}

ADMITTED_TYPED_UNIVERSE_SHA256 = \
    "1c19db2b5d666a8f33c715cb634cf111953c7cdd6c23d082e9b375643a3e7cc8"
# The hash of []. Named, so the B6 defect is refused BY NAME and not merely by a compare
# that a future edit could invert. The audited CLI passed exactly this.
EMPTY_TYPED_UNIVERSE_SHA256 = \
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
N_ADMITTED_UNIVERSE_TARGETS = 11_526

# --------------------------------------------------------------------------- #
# THE NAMESPACE VOCABULARY. ONE vocabulary — the one Stage 2 (W3) serializes.
#
# Restated here, as everything in this file is: the verifier must be able to say what the
# tokens ARE without asking the producer, or it can only prove the producer agrees with itself.
#
# The store was RE-EMITTED onto these tokens (a vocabulary re-pin: the scientific content hash,
# taken with the namespace projected out, is identical across it — 95f81cb1…). Its retired
# vocabulary is kept below so the stale store refuses BY NAME. There is NO alias map, here or
# anywhere: an unknown token is a named refusal, never a coercion.
# --------------------------------------------------------------------------- #
NS_ENSEMBL_GENE = "ensembl_gene_id"
NS_SYMBOL = "gene_symbol"
STORE_NAMESPACES = (NS_ENSEMBL_GENE, NS_SYMBOL)
RETIRED_NAMESPACES = ("ensembl_gene", "symbol")
ADMITTED_SCIENTIFIC_CONTENT_SHA256 = \
    "95f81cb11abf1b39d9345edb182344f0b90b60e08dd7605145b40c08eda391eb"

DISP_DRUG_EVIDENCE = "drug_evidence"
DISP_NO_DRUG_EVIDENCE = "no_drug_evidence"
DISP_AMBIGUOUS_IDENTITY = "ambiguous_identity"
DISP_UNSUPPORTED_NAMESPACE = "unsupported_namespace"
STORE_DISPOSITIONS = (DISP_DRUG_EVIDENCE, DISP_NO_DRUG_EVIDENCE, DISP_AMBIGUOUS_IDENTITY,
                      DISP_UNSUPPORTED_NAMESPACE)

# Where each assertion lane lives in a store row. Exactly ONE lane may rank a gene.
LANE_GENERAL = "general_gene_rankable"
LANE_VARIANT = "variant_specific_non_rankable"
LANE_AMBIGUOUS = "ambiguous_identity_non_rankable"
LANE_CONTAINERS = ((LANE_GENERAL, "drugs"),
                   (LANE_VARIANT, "variant_specific_assertions"),
                   (LANE_AMBIGUOUS, "ambiguous_source_assertions"))
RANKABLE_LANES = frozenset({LANE_GENERAL})

# ChEMBL's UNDEFINED MUTATION sentinel. NOT null, and emphatically not wild-type.
VARIANT_UNDEFINED_MUTATION = -1

# A cached Stage-3 verdict is a verdict nobody can re-derive, and it outlives the
# vocabulary that produced it.
FORBIDDEN_ASSERTION_KEYS = frozenset({
    "direction", "intervention_effect", "directional_evidence_status",
    "development_state", "development_phase", "rank", "score", "gate", "priority"})
REQUIRED_ASSERTION_FIELDS = ("source_row_id", "molecule_chembl_id", "target_chembl_id",
                             "action_type_source")

# --------------------------------------------------------------------------- #
# The SEVEN v2 tables. Restated in :mod:`verifier.v2_tables` — column allowlists ARE the
# contract: an unknown column is a field nobody agreed to, and no downstream consumer can
# be expected to refuse it.
#
# Keyed by REUSABLE ARM IDENTITY (arm_key | program_id | desired_change | context), never
# by a selection's `away_from_A`/`toward_B` role — a role is what a SELECTION gives an arm
# at join time, and baking one in fuses two questions under one key.
# --------------------------------------------------------------------------- #
# Every ABSENCE the v2 tables name. A target with no drug evidence, a source assertion that
# may never rank, a target the store never covered: each is a DIFFERENT fact, and each is
# said out loud rather than left as a missing row.
STATE_NOT_IN_UNIVERSE = "target_not_in_admitted_typed_universe"
STATE_NO_DRUG_EVIDENCE = "target_carries_no_source_drug_assertion"
STATE_UNSUPPORTED_NAMESPACE = "target_namespace_unreachable_by_this_acquisition_route"
STATE_NON_RANKABLE = "source_assertion_is_not_general_gene_rankable"
STATE_PATHWAY_LANE_NOT_ADMITTED = "pathway_lane_not_admitted_verifier_fails_open"
GATE_TARGET_NOT_IN_ADMITTED_UNIVERSE = "the_target_is_not_in_the_admitted_typed_universe"
GATE_PATHWAY_LANE_NOT_ADMITTED = "the_pathway_lane_was_admitted_by_a_verifier_that_fails_open"

# WHY THE PATHWAY LANE CONTRIBUTES NOTHING. Restated, because the reconstruction emits it as the
# STATED reason on every pathway arm's disposition — and a reason nobody can re-derive is a
# reason nobody can check. ZERO is the honest output: it says "Stage 2 has not yet told us, in
# bytes anyone can check, which sets these genes are in", which is exactly true.
PATHWAY_LANE_NOT_ADMITTED_DETAIL = (
    "a pathway record is a gene-set enrichment, not a measured per-target knockdown effect: no "
    "CRISPRi sign, never rankable as measured support, never a drug direction — a direction is "
    "not inherited from set membership. "
    "W3's pathway verifier fails open to resealed target/modulation fields, so its ADMIT carries "
    "no information; and the context token contract is not final (pathway_id / gene_set_id / "
    "set_id are all live, and native leading_edge entries may carry no typed target identity). "
    "Stage 3 does not consume bytes admitted by a fail-open gate, and does not guess a field "
    "name. The lane contributes ZERO context until both are fixed and the lane is re-admitted.")

# How a source assertion is ADDRESSED. A locator is not a URL: it is a stable coordinate —
# release + table + row id — that a reader can reopen.
SOURCE_SCHEME_CHEMBL = "chembl"
SOURCE_TABLE_DRUG_MECHANISM = "drug_mechanism"

# WHAT THE SCREEN DID is DECLARED PER ROW (`observed_perturbation_modality`), never assumed.
#
# A hardcoded `PERTURBATION_MODALITY = "CRISPRi_knockdown"` stood here, and a
# `MODULATION_TO_DESIRED` table beside it that mapped Stage-2's modulation token straight onto a
# desired direction. Both are RETIRED:
#
#   * assuming the modality means the compatible-mechanism set is chosen by Stage-3's guess about
#     an experiment it did not run — and it silently mis-types a CRISPRa arm as a knockdown;
#   * mapping the token to a direction reads the PRODUCER'S ANSWER. The direction is re-derived
#     from the SIGNED arm_value against the declared modality (:mod:`verifier.v2_sign`), and the
#     producer's token is then REQUIRED to equal it. A disagreement is a named refusal.

# --------------------------------------------------------------------------- #
# Named gates. Every refusal names one, so it can be grepped, tested and cited — never
# inferred from a message someone later rewords.
# --------------------------------------------------------------------------- #
GATE_ARTIFACT_NOT_ON_DISK = "aggregate_artifact_is_not_on_disk"
GATE_MANIFEST_SELF_HASH = "manifest_does_not_recompute_its_own_identity"
GATE_MANIFEST_NOT_NATIVE = "manifest_is_not_the_native_stage2_run_manifest_schema"
GATE_REPORT_NOT_NATIVE = "report_is_not_the_native_stage2_verification_schema"
GATE_SELF_ADMISSION = "the_report_and_the_manifest_are_the_same_artifact"
GATE_VERIFIER_NOT_PINNED = "report_was_not_written_by_the_pinned_aggregate_verifier"
GATE_GENERATOR_IS_VERIFIER = "report_does_not_assert_generator_is_not_verifier"
GATE_VERDICT_NOT_ADMIT = "verification_report_does_not_say_admit"
GATE_GATES_FAILED = "the_aggregate_verifier_recorded_failed_gates"
GATE_TOPOLOGY_NOT_COMPLETE = "the_verifier_did_not_find_the_topology_complete"
GATE_NOT_RELEASE_ADMISSIBLE = "the_verifier_did_not_find_the_release_admissible"
GATE_ADMISSION_NOT_GRANTED = "the_admission_status_is_not_admitted"
GATE_REPORT_BINDS_NOTHING = "verification_report_binds_no_manifest_bytes"
GATE_REPORT_BINDS_ANOTHER_MANIFEST = "verification_report_admits_a_different_manifest"
GATE_STAGE1_RELEASE_UNBOUND = "stage1_release_on_disk_is_not_the_pinned_release"
GATE_ARM_INDEX_DISAGREES = "the_manifests_arm_index_disagrees_with_the_bundles_bytes"
GATE_STAGE2_ADMISSION_NOT_CARRIED = "an_edge_carries_no_stage2_verifier_identity_or_verdict"
GATE_PATH_TRAVERSAL = "bundle_path_escapes_the_bundles_root"
GATE_UNKNOWN_LANE = "inventory_names_a_lane_or_context_the_release_does_not_have"
GATE_DUPLICATE_BUNDLE = "inventory_carries_a_duplicate_bundle_key"
GATE_MISSING_BUNDLE = "inventory_is_missing_a_bundle_the_release_must_have"
GATE_INCOMPLETE_TOPOLOGY = "the_release_does_not_resolve_its_full_arm_topology"
GATE_BUNDLE_BYTES_MOVED = "bundle_on_disk_is_not_the_bundle_the_manifest_inventoried"
GATE_ARM_IDENTITY_UNRESOLVED = "an_arm_record_resolves_to_no_target_identity"

GATE_STORE_NOT_FOUND = "the_universe_store_is_not_on_disk"
GATE_STORE_MISSING_ARTIFACT = "a_required_store_artifact_is_missing"
GATE_STORE_ARTIFACT_HASH_DRIFT = "a_store_artifact_no_longer_hashes_to_its_manifest_pin"
GATE_EMPTY_TYPED_UNIVERSE = "the_typed_universe_is_empty"
GATE_MALFORMED_STORE_ROW = "a_store_row_is_not_a_typed_universe_row"
GATE_DUPLICATE_TYPED_IDENTITY = "two_store_rows_claim_one_typed_identity"
GATE_TYPED_UNIVERSE_HASH_MISMATCH = \
    "the_derived_typed_universe_is_not_the_one_the_store_binds"
GATE_NOT_THE_ADMITTED_UNIVERSE = "this_is_not_the_typed_universe_that_was_admitted"
GATE_NOT_THE_ADMITTED_STORE = "this_is_not_the_store_an_independent_verifier_admitted"
GATE_UNKNOWN_NAMESPACE_TOKEN = "a_store_row_carries_a_namespace_token_nobody_agreed_to"
GATE_LICENSE_BINDING_MISSING = \
    "the_store_does_not_carry_its_source_licence_and_attribution"
GATE_CACHE_CARRIES_A_DIRECTION_VERDICT = \
    "the_cache_carries_a_stage3_direction_or_ranking_verdict"
GATE_MISSING_SOURCE_IDENTITY = "a_source_assertion_lost_its_source_identity"
GATE_VARIANT_IN_GENERAL_LANE = "a_variant_assertion_reached_the_general_gene_lane"
GATE_AMBIGUOUS_ROW_HAS_RANKABLE_EVIDENCE = \
    "an_ambiguous_identity_row_carries_rankable_drug_evidence"
GATE_SYMBOL_JOIN = "an_arm_was_joined_to_a_source_assertion_by_symbol"
GATE_INFERRED_ROW_CARRIES_A_MEASURED_RANK = \
    "an_inferred_origin_row_carries_a_measured_rank"

GATE_BUNDLE_NOT_ON_DISK = "the_stage3_v2_bundle_is_not_on_disk"
GATE_DOCUMENT_FILENAME = "the_document_is_not_named_what_the_contract_publishes"
GATE_BUNDLE_MANIFEST_SELF_HASH = "the_bundle_manifest_does_not_recompute_its_own_identity"
GATE_DOCUMENT_IDENTITY = "the_document_does_not_recompute_its_own_identity"
GATE_BUNDLE_ID_NOT_DERIVED = "the_bundle_id_is_not_derived_from_its_canonical_content"
GATE_FILE_HASH_DRIFT = "a_bundle_file_no_longer_hashes_to_its_manifest_entry"
GATE_BUNDLE_INVENTORY = "the_bundle_inventory_is_not_exact"
GATE_TABLE_HASH_DRIFT = "an_emitted_table_is_not_the_table_the_bundle_binds"
GATE_UNKNOWN_COLUMN = "a_table_carries_a_column_the_v2_contract_does_not_define"
GATE_RECONSTRUCTION_MISMATCH = \
    "the_emitted_evidence_is_not_what_an_independent_pass_reconstructs"
GATE_ORIGIN_SWAP = "an_edge_origin_disagrees_with_the_lane_of_the_bundle_it_came_from"
GATE_COMBINED_OBJECTIVE = "the_bundle_carries_a_combined_or_weighted_objective"
GATE_SIGNIFICANCE_ALIAS = "the_bundle_carries_a_p_q_or_fdr_significance_alias"
GATE_LOCAL_PATH_LEAK = "the_bundle_leaks_a_machine_local_path"
GATE_FIXTURE_FIREWALL = "a_fixture_artifact_cannot_enter_the_analysis_path"
GATE_SCHEMA_ALLOWLIST = "the_bundle_does_not_declare_the_frozen_v2_schema_set"
GATE_CODE_ENV_PINS = "the_bundle_does_not_bind_the_expected_code_and_environment"
GATE_EMPTY_EVIDENCE = "the_admitted_evidence_is_empty_and_would_pass_vacuously"

# The Stage-4 read contract. Every one of these is a field a downstream stage must be able to
# READ, JOIN on, or REOPEN — and a column of empty strings satisfies a schema and proves
# nothing, so each is asserted non-empty on the rows themselves.
GATE_NO_SOURCE_LOCATOR = "a_source_record_has_no_addressable_locator"
GATE_NO_SOURCE_RELEASE = "a_source_record_names_no_release"
GATE_ABSENCE_NOT_STATED = "absence_is_not_stated_explicitly"
GATE_CANDIDATE_ID_NOT_STABLE = "a_candidate_id_is_not_the_same_identity_in_every_table"
GATE_ORIGIN_NOT_CARRIED = "the_typed_origins_are_not_carried_through_to_stage4"
GATE_EMPTY_REQUIRED_COLUMN = "a_column_a_downstream_stage_joins_on_is_empty"
GATE_ARM_SLOTS_INCOMPLETE = "the_bundle_does_not_emit_every_arm_slot_the_release_resolved"
GATE_PROVENANCE_BINDING = "the_provenance_rows_are_not_the_artifacts_the_bundle_stands_on"

# The store's own eligibility evidence, REPLAYED rather than read.
GATE_ELIGIBILITY_REPLAY = "an_eligibility_verdict_does_not_replay_from_its_own_inputs"
GATE_ELIGIBILITY_NOT_COVERED = "a_referenced_chembl_target_has_no_eligibility_record"
GATE_NOT_SINGLE_PROTEIN_IN_GENERAL_LANE = \
    "a_general_gene_assertion_is_not_an_eligible_human_single_protein"

# THE PATHWAY LANE, which must contribute ZERO — and says so by name rather than by omission.
GATE_PATHWAY_LANE_CONTRIBUTED = \
    "the_unadmitted_pathway_lane_contributed_evidence_to_this_bundle"
GATE_PATHWAY_SOURCED_AN_EDGE = "a_pathway_enrichment_record_produced_a_measured_drug_direction"
GATE_ENRICHMENT_SOURCED_AN_EDGE = \
    "a_gene_set_enrichment_value_was_used_to_source_a_drug_edge"
GATE_GENE_SET_ID_AS_TARGET = "a_gene_set_id_was_joined_as_though_it_were_a_drug_target"

# A COUNT OF ROWS IS NOT A COUNT OF RANKS. Stage 2 RETAINS every target with rank:null when it is
# not rankable, so "in the ranking" is NOT "in the rows" — and a hit count taken from rows would
# inflate by exactly the targets the arm could NOT evaluate, the ones least entitled to support a
# claim.
GATE_HIT_COUNT_COUNTED_ROWS_NOT_RANKS = "a_hit_count_counted_rows_not_ranks"
GATE_NULL_RANK_COERCED_TO_ZERO = "a_null_rank_was_coerced_to_a_zero_that_sorts_as_best"
