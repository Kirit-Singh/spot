"""Adapter boundary: raw public-response bytes in, normalised records out.

An adapter is versioned and carries a readiness status:

  production_ready            validated against a PINNED, acquired current public
                              response AND cleared for the production lane. No
                              adapter has this status today.
  research_ready              its parse is tested against REAL pinned bytes from
                              the current public release (UniProt 2026_02, ChEMBL
                              37). It may run in the RESEARCH lane. It is still
                              NOT production-ready: research readiness is evidence
                              that the parse matches today's response, not that the
                              lane has cleared a production gate.
  fixture_shaped              parses bytes shaped like the documented public
                              response, but no pinned real response has been
                              acquired, so it may not run in the research or
                              production lanes.
  not_ready_no_pinned_response the public contract changed (or was never pinned);
                              the adapter refuses to parse and emits an explicit
                              unsupported_schema disposition instead of guessing.

Any payload that does not match the shape the adapter declares raises
:class:`UnsupportedSchema`. Stage 3 records that as a disposition; it never
falls back to a "best effort" parse.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

PRODUCTION_READY = "production_ready"
RESEARCH_READY = "research_ready"
FIXTURE_SHAPED = "fixture_shaped"
NOT_READY = "not_ready_no_pinned_response"


class UnsupportedSchema(ValueError):
    """The raw response does not match the shape this adapter version supports."""


@dataclass(frozen=True)
class Adapter:
    name: str
    version: str
    source: str
    status: str
    endpoints: tuple[str, ...]
    parse: Callable[[Any, dict[str, Any], str], list[dict[str, Any]]]
    note: str = ""


def ids(*, inchikey: Optional[str] = None, chembl_id: Optional[str] = None,
        pubchem_cid: Optional[Any] = None, rxcui: Optional[Any] = None,
        unii: Optional[str] = None) -> dict[str, Any]:
    """Identifier bag. Numeric IDs are carried as STRINGS: they are labels."""
    out = {
        "inchikey": inchikey,
        "chembl_id": chembl_id,
        "pubchem_cid": str(pubchem_cid) if pubchem_cid not in (None, "") else None,
        "rxcui": str(rxcui) if rxcui not in (None, "") else None,
        "unii": unii,
    }
    return {k: v for k, v in out.items() if v is not None}


def form_claim(*, source: str, source_record_id: str, identifiers: dict[str, Any],
               form_class: Optional[str] = None,
               relations: Optional[list[dict[str, Any]]] = None,
               route: Optional[str] = None, formulation: Optional[str] = None,
               preferred_name: Optional[str] = None,
               development_state: Optional[str] = None) -> dict[str, Any]:
    """One source's statement about one chemical/product entity."""
    return {
        "record_kind": "form_claim",
        "source": source,
        "source_record_id": source_record_id,
        "identifiers": identifiers,
        "form_class": form_class,
        "relations": relations or [],
        "route": route,
        "formulation": formulation,
        "preferred_name": preferred_name,
        "development_state": development_state,
    }


def relation(rel: str, to_identifiers: dict[str, Any]) -> dict[str, Any]:
    return {"relation": rel, "to_identifiers": to_identifiers}


def mechanism(*, source: str, source_record_id: str, source_row_id: Optional[str],
              source_molecule_id: str, molecule_identifiers: dict[str, Any],
              source_target_id: Optional[str], action_type_source: Optional[str],
              mechanism_of_action_text: Optional[str] = None,
              direct_interaction_flag: Optional[int] = None,
              mechanism_refs: Optional[list[str]] = None,
              ref_urls: Optional[list[str]] = None) -> dict[str, Any]:
    return {
        "record_kind": "mechanism",
        "source": source,
        "source_record_id": source_record_id,
        "source_row_id": source_row_id,
        "source_molecule_id": source_molecule_id,
        "molecule_identifiers": molecule_identifiers,
        "source_target_id": source_target_id,
        "action_type_source": action_type_source,
        "mechanism_of_action_text": mechanism_of_action_text,
        "direct_interaction_flag": direct_interaction_flag,
        "mechanism_refs": sorted(mechanism_refs or []),
        "ref_urls": sorted(ref_urls or []),
    }


def potency(*, source: str, source_record_id: str, source_molecule_id: str,
            molecule_identifiers: dict[str, Any], source_target_id: Optional[str],
            potency_type: str, relation_source: Optional[str],
            value_source_string: Optional[str], unit_source: Optional[str],
            activity_id: Optional[str] = None, assay_id: Optional[str] = None,
            assay_type: Optional[str] = None,
            assay_description: Optional[str] = None,
            assay_confidence_score: Optional[int] = None,
            assay_organism: Optional[str] = None,
            target_organism: Optional[str] = None,
            assay_cell_line: Optional[str] = None,
            document_id: Optional[str] = None,
            ref_url: Optional[str] = None) -> dict[str, Any]:
    """One measurement, verbatim. The value stays a STRING; nothing is rounded."""
    return {
        "record_kind": "potency",
        "source": source,
        "source_record_id": source_record_id,
        "source_molecule_id": source_molecule_id,
        "molecule_identifiers": molecule_identifiers,
        "source_target_id": source_target_id,
        "potency_type": potency_type,
        "relation_source": relation_source,
        "value_source_string": value_source_string,
        "unit_source": unit_source,
        "activity_id": activity_id,
        "assay_id": assay_id,
        "assay_type": assay_type,
        "assay_description": assay_description,
        "assay_confidence_score": assay_confidence_score,
        "assay_organism": assay_organism,
        "target_organism": target_organism,
        "assay_cell_line": assay_cell_line,
        "document_id": document_id,
        "ref_url": ref_url,
    }


def target_entity(*, source: str, source_record_id: str, source_target_id: str,
                  target_type: str, organism: Optional[str],
                  components: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "record_kind": "target_entity",
        "source": source,
        "source_record_id": source_record_id,
        "source_target_id": source_target_id,
        "target_type": target_type,
        "organism": organism,
        "components": components,
    }


def gene_map(*, source: str, source_record_id: str, target_ensembl: str,
             uniprot_id: str, organism: Optional[str] = None) -> dict[str, Any]:
    return {
        "record_kind": "gene_map",
        "source": source,
        "source_record_id": source_record_id,
        "target_ensembl": target_ensembl,
        "uniprot_id": uniprot_id,
        "organism": organism,
    }


def lane_row(kind: str, *, source: str, source_record_id: str,
             payload: dict[str, Any]) -> dict[str, Any]:
    return {"record_kind": kind, "source": source,
            "source_record_id": source_record_id, "payload": payload}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise UnsupportedSchema(message)
