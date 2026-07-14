"""The Stage-3 wire contract, transcribed into Stage 4 and frozen here.

Stage 4 must be able to say "these parquet rows are the rows Stage 3 hashed" WITHOUT
importing Stage-3 code — otherwise a bug or a tamper in Stage 3's own hasher would
validate itself. So the table set, the column order, the display-column exclusions, the
sort keys, the candidate content projection and the canonical JSON rule are all restated
here, independently, from the Stage-3 contract at `03_druglink/analysis/druglink`
(`artifacts.py`, `hashing.py`, `candidates.py`, `namespaces.py`).

Two rules carried across verbatim, because the content hashes are meaningless without them:

  * floats are NOT canonicalisable. Every magnitude is an exact source string plus a
    canonical decimal string, so 4.0e-7 M and 4.9e-7 M can never hash alike. A float
    anywhere in a Stage-3 table is a rejection, not a rounding decision.
  * `preferred_name` and `target_symbol` are DISPLAY columns: excluded from the content
    hash (and so from the Stage-3 bundle id), but still covered by the file hash.

If Stage 3 changes its tables, this transcription stops matching and every bundle is
refused with `stage3_table_contract_mismatch` — which is the correct failure. Bump
`STAGE3_TABLE_CONTRACT_VERSION` only after re-reading the Stage-3 contract.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

STAGE3_TABLE_CONTRACT_VERSION = "spot.stage03.tables.v1"
STAGE3_MANIFEST_SCHEMA = "spot.stage03_manifest.v1"

# Excluded from CONTENT hashes (and so from the bundle id); still covered by file hashes.
DISPLAY_COLUMNS = frozenset({"preferred_name", "target_symbol"})

# Canonicalisable value kinds. Stage 3 emits nothing else — notably no floats.
STR, INT, BOOL, LIST_STR, LIST_INT = "str", "int", "bool", "list_str", "list_int"


def _cols(spec: str) -> dict[str, str]:
    """"a b:int c:list_str" -> {"a": "str", "b": "int", "c": "list_str"} (order preserved)."""
    out: dict[str, str] = {}
    for token in spec.split():
        name, _, kind = token.partition(":")
        out[name] = kind or STR
    return out


# table -> (column -> value kind, in EXACT emitted column order), sort keys
TABLES: dict[str, tuple[dict[str, str], tuple[str, ...]]] = {
    "source_records": (_cols(
        "source_record_id namespace source adapter adapter_version adapter_status "
        "source_release source_endpoint retrieval_url query_canonical license attribution "
        "acquisition_status raw_sha256 raw_bytes:int raw_media_type access_record_sha256 "
        "parse_status parse_detail"),
        ("source_record_id",)),
    "target_entities": (_cols(
        "target_entity_id source source_target_id target_type target_entity_class organism "
        "direct_gene_lane_eligible:bool component_rule source_record_ids:list_str"),
        ("target_entity_id",)),
    "target_entity_components": (_cols(
        "target_entity_id uniprot_id target_ensembl component_role component_relationship "
        "source_record_id"),
        ("target_entity_id", "uniprot_id")),
    "drug_forms": (_cols(
        "form_id preferred_name form_class moiety_assignment_status active_moiety_id "
        "ingredient_form_ids:list_str n_ingredients:int route route_status formulation "
        "formulation_status development_states:list_str identity_conflicts:list_str "
        "source_record_ids:list_str"),
        ("form_id",)),
    "drug_identifiers": (_cols(
        "form_id id_type id_value source source_record_id"),
        ("form_id", "id_type", "id_value", "source_record_id")),
    "drug_form_relations": (_cols(
        "from_form_id relation to_form_id source source_record_id"),
        ("from_form_id", "relation", "to_form_id", "source_record_id")),
    "active_moieties": (_cols(
        "active_moiety_id preferred_name moiety_inchikey moiety_chembl_id moiety_pubchem_cid "
        "moiety_rxcui moiety_unii identity_status identity_conflicts:list_str "
        "form_ids:list_str development_states:list_str development_state_aggregate "
        "source_record_ids:list_str"),
        ("active_moiety_id",)),
    "mechanism_assertions": (_cols(
        "assertion_id source source_record_id source_record_row_id source_molecule_id form_id "
        "target_entity_id action_type_source action_type_normalized mechanism_of_action_text "
        "direct_interaction_flag:int directness_class mechanism_refs:list_str ref_urls:list_str"),
        ("assertion_id",)),
    "target_drug_edges": (_cols(
        "edge_id target_ensembl target_symbol target_entity_id target_entity_class uniprot_id "
        "form_id active_moiety_id action_type_normalized directness_state "
        "directness_classes:list_str n_assertions:int assertion_ids:list_str lane "
        "perturbation_modality observed_genetic_direction observed_module_direction "
        "desired_target_modulation translation_support pharmacologic_effect "
        "mechanism_direction_match direction_reason action_conflict:bool stage2_evidence_tier "
        "stage3_eligible:bool source_record_ids:list_str"),
        ("edge_id",)),
    "potency_evidence": (_cols(
        "potency_row_id form_id source_molecule_id active_moiety_id target_entity_id "
        "source_target_id edge_ids:list_str potency_type relation relation_status "
        "value_source_string value_canonical_decimal unit_source form_binding "
        "transfer_policy_id activity_id assay_id assay_type assay_description "
        "assay_confidence_score:int confidence_class assay_organism target_organism "
        "assay_cell_line document_id ref_url source source_record_id"),
        ("potency_row_id",)),
    "method_manifests": (_cols(
        "method_manifest_id lane method_version method_sha256 rule_id required_fields:list_str "
        "denominator_fields:list_str context_id compartment_id desired_signature_sha256 "
        "gene_universe_sha256 source_record_id"),
        ("method_manifest_id",)),
    "gbm_context": (_cols(
        "row_id target_ensembl dataset_id dataset_version context_id compartment_id "
        "n_patients:int n_patients_detected:int n_cells:int detection_fraction_source_string "
        "detection_fraction_canonical_decimal row_state method_manifest_id source_record_id"),
        ("row_id",)),
    "lincs_support": (_cols(
        "row_id signature_id pert_id form_id active_moiety_id cell_line cell_context_class "
        "dose_source_string dose_canonical_decimal dose_unit time_source_string time_unit "
        "n_replicates:int connectivity_source_string desired_signature_sha256 "
        "gene_universe_sha256 row_state method_manifest_id source_record_id"),
        ("row_id",)),
    "dispositions": (_cols(
        "disposition_id subject_kind subject_id state reason detail source_record_id"),
        ("disposition_id",)),
    "candidates": (_cols(
        "rank:int candidate_id active_moiety_id preferred_name identity_status lane "
        "lane_reasons:list_str mechanism_direction_state matched_edge_ids:list_str "
        "opposed_edge_ids:list_str unknown_edge_ids:list_str levers_matched:list_str "
        "levers_opposed:list_str form_ids:list_str stage2_evidence_tier stage2_tiers:list_str "
        "directness_state directness_states:list_str gbm_context_state gbm_denominators "
        "perturb2state_state perturb2state_denominators lincs_state lincs_denominators "
        "development_state_aggregate n_potency_rows:int production_candidate:bool "
        "stage3_eligible:bool stage4_eligible:bool rank_tuple:list_int rank_labels:list_str "
        "source_record_ids:list_str"),
        ("lane", "candidate_id")),
}

TABLE_FILES = tuple(sorted(f"{name}.parquet" for name in TABLES))

# The document keys the bundle id is derived from, per namespace.
SCHEMA_BY_NAMESPACE = {
    "production": "spot.stage03_drug_candidate_set.v1",
    "research_only": "spot.stage03_research_annotation.v1",
    "fixture": "spot.fixture.stage03_bundle.v1",
}
OUTPUT_DOC = {
    "production": "drug_candidate_set.json",
    "research_only": "research_annotation.json",
    "fixture": "fixture_bundle.json",
}
RANKED_KEY = {"production": "primary_candidates", "research_only": "annotated_candidates",
              "fixture": "fixture_candidates"}
INSPECTABLE_KEY = {"production": "secondary_candidates",
                   "research_only": "inspectable_candidates",
                   "fixture": "fixture_inspectable_candidates"}
DOCUMENT_ID_KEY = {"production": "candidate_set_id",
                   "research_only": "research_annotation_id",
                   "fixture": "fixture_bundle_id"}
DOCUMENT_ID_PREFIX = {"production": "cs_", "research_only": "ra_", "fixture": "fx_"}

# The per-candidate projection the canonical content hash is taken over. `preferred_name`
# and `rank_labels` are deliberately NOT here: they are display, not identity.
CANDIDATE_CONTENT_KEYS = (
    "candidate_id", "active_moiety_id", "identity_status", "lane", "lane_reasons",
    "rank", "rank_tuple", "mechanism_direction_state", "matched_edge_ids",
    "opposed_edge_ids", "unknown_edge_ids", "levers_matched", "levers_opposed",
    "form_ids", "stage2_evidence_tier", "stage2_tiers", "directness_state",
    "directness_states", "gbm_context_state", "gbm_denominators",
    "perturb2state_state", "perturb2state_denominators", "lincs_state",
    "lincs_denominators", "development_state_aggregate", "n_potency_rows",
    "production_candidate", "stage3_eligible", "stage4_eligible", "source_record_ids",
)


class ContractError(ValueError):
    """A value cannot be canonically serialised the way Stage 3 serialised it."""


def reject_uncanonical(node: Any, path: str = "$") -> None:
    """Floats — and anything else Stage 3 would refuse to hash — are a rejection."""
    if isinstance(node, float):
        raise ContractError(
            f"float at {path}: Stage-3 canonical content carries exact decimal strings, "
            "never floats (a float grid collapses two distinct magnitudes into one hash)")
    if isinstance(node, Mapping):
        for k, v in node.items():
            reject_uncanonical(v, f"{path}.{k}")
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            reject_uncanonical(v, f"{path}[{i}]")
    elif not isinstance(node, (str, int, bool, type(None))):
        raise ContractError(f"uncanonicalisable type at {path}: {type(node).__name__}")


def cjson(obj: Any) -> str:
    """Stage 3's canonical JSON rule, restated."""
    reject_uncanonical(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def content_hash(obj: Any) -> str:
    return sha256_hex(cjson(obj))


def row_key(row: Mapping[str, Any], keys: Sequence[str]) -> list:
    """A total order in which a missing value sorts distinctly from any present one."""
    out: list = []
    for k in keys:
        v = row.get(k)
        out.append((0, "") if v is None else (1, cjson(v)))
    out.append((1, cjson(row)))
    return out


def table_hash(rows: Iterable[Mapping[str, Any]], sort_keys: Sequence[str]) -> str:
    """Row-order-invariant hash over the exact emitted cell values."""
    materialised = [dict(r) for r in rows]
    for r in materialised:
        reject_uncanonical(r)
    return sha256_hex(cjson(sorted(materialised, key=lambda r: row_key(r, sort_keys))))


def content_columns(table: str) -> list[str]:
    kinds, _ = TABLES[table]
    return [c for c in kinds if c not in DISPLAY_COLUMNS]


def content_sort_keys(table: str) -> tuple[str, ...]:
    _kinds, sort_keys = TABLES[table]
    cols = content_columns(table)
    return tuple(k for k in sort_keys if k in cols) or (cols[0],)


def table_content_hash(table: str, rows: Iterable[Mapping[str, Any]]) -> str:
    """The scientific identity of one table, recomputed from its ACTUAL rows."""
    cols = content_columns(table)
    projected = [{c: r.get(c) for c in cols} for r in rows]
    return table_hash(projected, content_sort_keys(table))


def kind_of(value: Any) -> str:
    """The canonical kind of one cell. `bool` is checked before `int`: in Python it IS one."""
    if isinstance(value, bool):
        return BOOL
    if isinstance(value, int):
        return INT
    if isinstance(value, str):
        return STR
    if isinstance(value, list):
        if all(isinstance(v, bool) for v in value) and value:
            return "list_bool"
        if all(isinstance(v, int) and not isinstance(v, bool) for v in value) and value:
            return LIST_INT
        if all(isinstance(v, str) for v in value):
            return LIST_STR  # an empty list is compatible with any list kind
        return "list_mixed"
    return type(value).__name__


def cell_kind_ok(declared: str, value: Any) -> bool:
    """None is always admissible (Stage 3 emits null columns); otherwise the kind must match."""
    if value is None:
        return True
    actual = kind_of(value)
    if declared in (LIST_STR, LIST_INT) and actual in (LIST_STR, LIST_INT):
        # An empty list satisfies either; a populated one must match exactly.
        return not value or actual == declared
    return actual == declared


def contract_sha256() -> str:
    """This transcription's own identity. It enters the Stage-4 scorecard id via the code hash."""
    return content_hash({
        "version": STAGE3_TABLE_CONTRACT_VERSION,
        "manifest_schema": STAGE3_MANIFEST_SCHEMA,
        "display_columns": sorted(DISPLAY_COLUMNS),
        "candidate_content_keys": list(CANDIDATE_CONTENT_KEYS),
        "tables": {
            name: {"columns": list(kinds), "kinds": kinds, "sort_keys": list(sort_keys)}
            for name, (kinds, sort_keys) in sorted(TABLES.items())
        },
    })
