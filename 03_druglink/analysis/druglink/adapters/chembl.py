"""ChEMBL adapters: molecule hierarchy, mechanisms, activities, targets.

Target-entity semantics (the audit's finding 6):

  * ``SINGLE PROTEIN``  -> a gene-level entity; may enter the direct gene lane.
  * ``PROTEIN COMPLEX`` / ``PROTEIN FAMILY`` / ``PROTEIN COMPLEX GROUP`` etc.
    -> distinct NON-GENE entities with component/member roles. There is no frozen
    component-specific translation rule, so their direction is unknown by policy.

Assay confidence (ChEMBL's documented target-confidence scale):

  * 9 = "Direct single protein target assigned" -> ``direct_single_protein``;
  * 8 = "Homologous single protein target assigned" -> ``homologous_single_protein``,
    which is NOT direct curated evidence and must never be labelled as such;
  * <= 7 or absent -> indirect / unknown.

Values are never parsed into floats: ``standard_value`` is kept as the exact
source string. A missing ``standard_relation`` stays missing; it is not "=".

ChEMBL derivatives require CC BY-SA attribution (carried in the manifest entry).

``research_ready``: these parses are tested against pinned REAL ChEMBL 37 responses
(``tests/test_public_acquisition.py``). They are not production-ready.

v3 exists because of what the real bytes actually say: ChEMBL 37 serialises
``max_phase`` as a JSON NUMBER (``4.0``, not ``"4"``). The v2 lookup keyed on
``str(4.0) == "4.0"`` missed every bucket and recorded IPILIMUMAB -- an approved
drug -- with development_state ``None``, i.e. as if ChEMBL had said nothing. The
phase is now normalised through the exact decimal, so a stated phase is never lost
and an UNSTATED phase (null) still stays null.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from . import base
from .base import require

SOURCE = "chembl"
VERSION = "chembl-adapter-v3"

# Target-entity classes and assay-confidence semantics live in druglink.targets;
# the adapter passes ChEMBL's raw target_type and confidence_score through.
_PHASE = {"4": "approved", "3": "phase_3", "2": "phase_2", "1": "phase_1",
          "0": "preclinical"}


def _phase_key(phase: Any) -> Optional[str]:
    """ChEMBL's max_phase, whatever its JSON type, as an exact integer string.

    4, 4.0 and "4" are the same stated phase. A non-integral or unparseable value
    (e.g. 0.5, "N/A") is NOT coerced into a neighbouring bucket -- it maps to no
    bucket at all, and the drug's development state stays unstated.
    """
    if phase is None or isinstance(phase, bool):
        return None
    try:
        dec = Decimal(str(phase))
    except (InvalidOperation, ValueError):
        return None
    if not dec.is_finite() or dec != dec.to_integral_value():
        return None
    return str(int(dec))


def _dev_state(mol: dict[str, Any]) -> Optional[str]:
    if mol.get("withdrawn_flag"):
        return "withdrawn"
    key = _phase_key(mol.get("max_phase"))
    return _PHASE.get(key) if key is not None else None


def _xrefs(mol: dict[str, Any]) -> dict[str, Any]:
    cid = unii = None
    for x in mol.get("cross_references") or []:
        src, xid = x.get("xref_src"), x.get("xref_id")
        if not xid:
            continue
        if src in ("PubChem", "PubChem CID") and cid is None:
            cid = xid
        elif src in ("UNII", "FDA SRS") and unii is None:
            unii = xid
    return {"pubchem_cid": cid, "unii": unii}


def parse_molecule(raw: Any, entry: dict[str, Any], src_id: str) -> list[dict[str, Any]]:
    require(isinstance(raw, dict) and isinstance(raw.get("molecules"), list),
            "chembl molecule response must carry a 'molecules' array")
    out: list[dict[str, Any]] = []
    for mol in raw["molecules"]:
        require("molecule_chembl_id" in mol, "molecule row without molecule_chembl_id")
        cid = mol["molecule_chembl_id"]
        hier = mol.get("molecule_hierarchy") or {}
        parent = hier.get("parent_chembl_id")
        active = hier.get("active_chembl_id")
        x = _xrefs(mol)
        inchikey = (mol.get("molecule_structures") or {}).get("standard_inchi_key")
        self_ids = base.ids(chembl_id=cid, inchikey=inchikey,
                            pubchem_cid=x["pubchem_cid"], unii=x["unii"])

        relations: list[dict[str, Any]] = []
        if mol.get("prodrug") == 1 and active and active != cid:
            form_class = "prodrug"
            relations.append(base.relation("is_prodrug_of", base.ids(chembl_id=active)))
        elif mol.get("active_metabolite_of"):
            # An active metabolite IS an active species: it is its own moiety.
            form_class = "active_metabolite"
            relations.append(base.relation(
                "is_active_metabolite_of",
                base.ids(chembl_id=mol["active_metabolite_of"])))
            relations.append(base.relation("is_parent_of_self", base.ids(chembl_id=cid)))
        elif parent and parent != cid:
            form_class = "salt"
            relations.append(base.relation("is_salt_of",
                                           base.ids(chembl_id=active or parent)))
        else:
            form_class = "parent"
            relations.append(base.relation("is_parent_of_self", base.ids(chembl_id=cid)))

        out.append(base.form_claim(
            source=SOURCE, source_record_id=src_id, identifiers=self_ids,
            form_class=form_class, relations=relations,
            preferred_name=mol.get("pref_name"),
            development_state=_dev_state(mol)))
    return out


def parse_mechanism(raw: Any, entry: dict[str, Any], src_id: str) -> list[dict[str, Any]]:
    require(isinstance(raw, dict) and isinstance(raw.get("mechanisms"), list),
            "chembl mechanism response must carry a 'mechanisms' array")
    out: list[dict[str, Any]] = []
    for m in raw["mechanisms"]:
        require("molecule_chembl_id" in m, "mechanism row without molecule_chembl_id")
        refs = [r["ref_id"] for r in (m.get("mechanism_refs") or []) if r.get("ref_id")]
        urls = [r["ref_url"] for r in (m.get("mechanism_refs") or []) if r.get("ref_url")]
        out.append(base.mechanism(
            source=SOURCE, source_record_id=src_id,
            source_row_id=(str(m["mec_id"]) if m.get("mec_id") is not None else None),
            source_molecule_id=m["molecule_chembl_id"],
            molecule_identifiers=base.ids(chembl_id=m["molecule_chembl_id"]),
            source_target_id=m.get("target_chembl_id"),
            action_type_source=m.get("action_type"),
            mechanism_of_action_text=m.get("mechanism_of_action"),
            direct_interaction_flag=m.get("direct_interaction"),
            mechanism_refs=refs, ref_urls=urls))
    return out


def parse_activity(raw: Any, entry: dict[str, Any], src_id: str) -> list[dict[str, Any]]:
    require(isinstance(raw, dict) and isinstance(raw.get("activities"), list),
            "chembl activity response must carry an 'activities' array")
    out: list[dict[str, Any]] = []
    for a in raw["activities"]:
        require("molecule_chembl_id" in a, "activity row without molecule_chembl_id")
        value = a.get("standard_value")
        out.append(base.potency(
            source=SOURCE, source_record_id=src_id,
            source_molecule_id=a["molecule_chembl_id"],
            molecule_identifiers=base.ids(chembl_id=a["molecule_chembl_id"]),
            source_target_id=a.get("target_chembl_id"),
            potency_type=a.get("standard_type") or "unknown",
            relation_source=a.get("standard_relation"),   # may be null -> not_reported
            value_source_string=(None if value is None else str(value)),
            unit_source=a.get("standard_units"),
            activity_id=(str(a["activity_id"]) if a.get("activity_id") is not None
                         else None),
            assay_id=a.get("assay_chembl_id"),
            assay_type=a.get("assay_type"),
            assay_description=a.get("assay_description"),
            assay_confidence_score=a.get("confidence_score"),
            assay_organism=a.get("assay_organism"),
            target_organism=a.get("target_organism"),
            assay_cell_line=a.get("assay_cell_type") or a.get("cell_chembl_id"),
            document_id=a.get("document_chembl_id"),
            ref_url=a.get("document_url")))
    return out


def parse_target(raw: Any, entry: dict[str, Any], src_id: str) -> list[dict[str, Any]]:
    require(isinstance(raw, dict) and isinstance(raw.get("targets"), list),
            "chembl target response must carry a 'targets' array")
    out: list[dict[str, Any]] = []
    for t in raw["targets"]:
        require("target_chembl_id" in t and "target_type" in t,
                "target row without target_chembl_id/target_type")
        ttype = t["target_type"]
        components = [
            {"uniprot_id": c["accession"],
             "component_relationship": c.get("relationship")}
            for c in (t.get("target_components") or []) if c.get("accession")
        ]
        out.append(base.target_entity(
            source=SOURCE, source_record_id=src_id,
            source_target_id=t["target_chembl_id"], target_type=ttype,
            organism=t.get("organism"), components=components))
    return out


_PINNED = "parse tested against pinned real ChEMBL 37 responses"

ADAPTERS = {
    "chembl_molecule": base.Adapter(
        "chembl_molecule", VERSION, SOURCE, base.RESEARCH_READY,
        ("/chembl/api/data/molecule",), parse_molecule, note=_PINNED),
    "chembl_mechanism": base.Adapter(
        "chembl_mechanism", VERSION, SOURCE, base.RESEARCH_READY,
        ("/chembl/api/data/mechanism",), parse_mechanism, note=_PINNED),
    # NOT research_ready: activity/potency is not acquired in this release, so no
    # real pinned activity response has been parsed. Readiness is earned by a test
    # against real bytes, never granted by association with a sibling adapter.
    # Potency therefore stays not_evaluated -- which is not zero, and not "no
    # evidence of activity".
    "chembl_activity": base.Adapter(
        "chembl_activity", VERSION, SOURCE, base.FIXTURE_SHAPED,
        ("/chembl/api/data/activity",), parse_activity,
        note="no real pinned activity response has been acquired"),
    "chembl_target": base.Adapter(
        "chembl_target", VERSION, SOURCE, base.RESEARCH_READY,
        ("/chembl/api/data/target",), parse_target, note=_PINNED),
}
