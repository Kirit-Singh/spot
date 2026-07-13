"""BLOCKER 1 fix: the exact human-single-protein direct-gene eligibility predicate.

A ChEMBL ``SINGLE PROTEIN`` label is not sufficient: the target can be non-human,
homologous, a species-group representative, or multi-component. Direct-gene eligibility
requires ALL of the frozen predicates AND exactly one total component (which is the
eligible human protein). Anything else is a NAMED non-rankable disposition — never a
silent gene edge, never last-write-wins.

Frozen SQL (its text is hashed into the extraction provenance)::

    td.target_type = 'SINGLE PROTEIN'
    AND td.tax_id = 9606
    AND td.species_group_flag = 0
    AND cs.component_type = 'PROTEIN'
    AND cs.tax_id = 9606
    AND tc.homologue = 0

with a proof of exactly one eligible AND exactly one total component.
"""
from __future__ import annotations

import collections
from typing import Any, Iterable

ELIGIBILITY_POLICY_VERSION = "stage3-universe-target-eligibility-v1"
EVIDENCE_SCHEMA = "spot.stage03_target_eligibility_evidence.v1"
HUMAN_TAX_ID = 9606

# The frozen predicate text; hashed into extraction provenance so a loosened gate cannot
# be reproduced by accident.
ELIGIBLE_SINGLE_PROTEIN_SQL = (
    "td.target_type = 'SINGLE PROTEIN' AND td.tax_id = 9606 "
    "AND td.species_group_flag = 0 AND cs.component_type = 'PROTEIN' "
    "AND cs.tax_id = 9606 AND tc.homologue = 0")

DISP_ELIGIBLE = "eligible_human_single_protein"


def _dedup_components(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for c in components:
        key = (c.get("component_type"), c.get("tax_id"), c.get("homologue"),
               c.get("accession"))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def evaluate(target: dict[str, Any]) -> dict[str, Any]:
    """Decide direct-gene eligibility for one ChEMBL target. Fail-closed, named."""
    def out(eligible: bool, disposition: str, accession: Any = None) -> dict[str, Any]:
        return {"eligible": eligible, "disposition": disposition,
                "accession": accession,
                "target_chembl_id": target.get("target_chembl_id")}

    if target.get("target_type") != "SINGLE PROTEIN":
        return out(False, "reject_wrong_target_type")
    if target.get("tax_id") != HUMAN_TAX_ID:
        return out(False, "reject_nonhuman_target_taxon")
    if target.get("species_group_flag") != 0:
        return out(False, "reject_species_group")

    components = _dedup_components(list(target.get("components") or []))
    # Exactly one TOTAL component (after de-duplicating identical join rows).
    if len(components) != 1:
        return out(False, "reject_component_cardinality")

    c = components[0]
    if c.get("component_type") != "PROTEIN":
        return out(False, "reject_nonprotein_component")
    if c.get("tax_id") != HUMAN_TAX_ID:
        return out(False, "reject_nonhuman_component_taxon")
    if c.get("homologue") != 0:
        return out(False, "reject_homologue")
    if not c.get("accession"):
        return out(False, "reject_missing_accession")

    return out(True, DISP_ELIGIBLE, accession=c["accession"])


def evidence_record(target: dict[str, Any],
                    verdict: dict[str, Any] | None = None) -> dict[str, Any]:
    """Sanitized, independently revalidatable eligibility evidence for ONE target
    (accepted OR rejected): the exact predicate fields + the verdict. No machine paths."""
    verdict = verdict or evaluate(target)
    comps = _dedup_components(list(target.get("components") or []))
    return {
        "target_chembl_id": target.get("target_chembl_id"),
        "target_type": target.get("target_type"),
        "tax_id": target.get("tax_id"),
        "species_group_flag": target.get("species_group_flag"),
        "n_components": len(comps),
        "components": [{"component_type": c.get("component_type"),
                        "tax_id": c.get("tax_id"), "homologue": c.get("homologue"),
                        "accession": c.get("accession")} for c in comps],
        "eligible": verdict["eligible"],
        "disposition": verdict["disposition"],
        "accession": verdict["accession"],
    }


def eligibility_evidence_artifact(
        records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Content-addressable evidence artifact over accepted AND rejected records. Bound
    into the universe manifest / store_id so the eligibility gate is revalidatable."""
    recs = sorted(records, key=lambda r: (r.get("target_chembl_id") or ""))
    by = dict(collections.Counter(r["disposition"] for r in recs))
    return {
        "schema": EVIDENCE_SCHEMA,
        "eligibility_policy_version": ELIGIBILITY_POLICY_VERSION,
        "eligible_single_protein_sql": ELIGIBLE_SINGLE_PROTEIN_SQL,
        "counts": {"n_total": len(recs),
                   "n_eligible": sum(1 for r in recs if r["eligible"]),
                   "n_rejected": sum(1 for r in recs if not r["eligible"]),
                   "by_disposition": dict(sorted(by.items()))},
        "records": recs,
    }
