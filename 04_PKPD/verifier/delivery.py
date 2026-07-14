"""Independent restatement of the delivery-requirement reduction.

Rebuilt from `delivery_assignments.parquet` + `method/delivery_rules_v1.json` alone, and
importing nothing from `analysis/`. The generator's `delivery_evidence.parquet` is the
thing being CHECKED here, never an input to the check.

The audit fed the same two assignments in two orders. The engine took `mine[0]`, so one
order produced `local_CNS_target_engagement_required` with `nebpi_primary_gate=true` and
the other produced `delivery_requirement_uncertain` with no gate — under ONE
`scorecard_set_id`, with both verifications passing. The reduction below is a function of
the SET of rows:

    0 rows                  -> no_assignment
    1 row (after dedupe)    -> validated and applied
    >1 distinct rows        -> conflicting_assignments -> uncertain

Byte-identical rows collapse (they are one record). Anything less than byte-identical is a
distinct row — including two rows that request the SAME requirement on different bases,
because the basis, the assigner and the evidence binding are part of the claim.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from . import canon

# The whole assignment row: the unit of identity. Every one of these is a column of
# delivery_assignments.parquet, so a distinct row can never be mistaken for a duplicate.
ASSIGNMENT_IDENTITY_FIELDS = (
    "assignment_id", "candidate_id", "context_id", "requirement", "basis", "assigned_by",
    "rule_id", "rule_version", "rationale", "evidence_source_record_id",
    "evidence_source_url", "evidence_access_date", "evidence_release_version",
    "evidence_sha256", "evidence_extraction_transform",
)

UNCERTAIN = "delivery_requirement_uncertain"
TARGET_BIOLOGY_ONLY = "target_biology_only"


def _identity(a: dict) -> str:
    return canon.chash({k: a.get(k) for k in ASSIGNMENT_IDENTITY_FIELDS})


def _gate_for(rules: dict[str, Any], requirement: str) -> Optional[bool]:
    """A requirement outside the method's vocabulary gates NOTHING.

    A tampered release can carry any string here. Raising would abort the verifier, and an
    aborted verifier is not a verdict — so an unknown requirement resolves to no gate, the
    rebuilt decision then disagrees with the emitted one, and the release fails.
    """
    for v in rules["values"]:
        if v["value"] == requirement:
            return v["nebpi_primary_gate"]
    return None


def _rejected_assigner_patterns(rules: dict[str, Any]) -> list[str]:
    for r in rules["assignment_rules"]:
        if r["rule_id"] == "llm_is_not_an_assigner":
            return [p.lower() for p in r["rejected_assigner_patterns"]]
    return []


def _looks_like_a_model(assigned_by: str, patterns: list[str]) -> bool:
    low = (assigned_by or "").lower()
    for pat in patterns:
        if re.search(rf"\b{re.escape(pat)}\b", low) or pat in low.replace("-", " ").split():
            return True
    return False


def rebuild_delivery(tables: dict[str, list[dict]], method: dict) -> dict[tuple[str, str], dict]:
    """Re-derive one delivery decision per (candidate, context) from the assignment rows."""
    rules = method["delivery_rules"]
    patterns = _rejected_assigner_patterns(rules)

    by_key: dict[tuple[str, str], dict[str, dict]] = {}
    for a in tables.get("delivery_assignments", []):
        key = (a["candidate_id"], a["context_id"])
        by_key.setdefault(key, {}).setdefault(_identity(a), a)

    out: dict[tuple[str, str], dict] = {}
    for ctx in tables.get("contexts", []):
        key = (ctx["candidate_id"], ctx["context_id"])
        unique = by_key.get(key, {})
        rows = [unique[k] for k in sorted(unique)]

        def uncertain(code: str, downgraded_from: Optional[str] = None,
                      conflicting: tuple[str, ...] = ()) -> dict:
            return {
                "delivery_requirement": UNCERTAIN,
                "nebpi_primary_gate": _gate_for(rules, UNCERTAIN),
                "reason_code": code,
                "downgraded_from": downgraded_from,
                "assignment_id": None,
                "conflicting_assignment_ids": list(conflicting),
                "evidence_source_record_id": None,
                "evidence_sha256": None,
            }

        if not rows:
            out[key] = uncertain("no_assignment")
            continue
        if len(rows) > 1:
            out[key] = uncertain(
                "conflicting_assignments",
                conflicting=tuple(sorted(r["assignment_id"] for r in rows)),
            )
            continue

        a = rows[0]
        req = a["requirement"]
        if req not in {v["value"] for v in rules["values"]}:
            out[key] = {**uncertain("unknown_delivery_requirement", downgraded_from=req),
                        "assignment_id": a["assignment_id"]}
        elif req == UNCERTAIN:
            out[key] = {**uncertain("explicitly_uncertain"), "assignment_id": a["assignment_id"]}
        elif _looks_like_a_model(a["assigned_by"], patterns):
            out[key] = {**uncertain("assigner_not_accepted", downgraded_from=req),
                        "assignment_id": a["assignment_id"]}
        elif a["basis"] == TARGET_BIOLOGY_ONLY:
            out[key] = {
                **uncertain("immune_target_is_not_evidence_of_systemic_priming",
                            downgraded_from=req),
                "assignment_id": a["assignment_id"],
            }
        elif not a.get("evidence_source_record_id") or not a.get("evidence_sha256"):
            out[key] = {**uncertain("no_evidence_binding", downgraded_from=req),
                        "assignment_id": a["assignment_id"]}
        else:
            out[key] = {
                "delivery_requirement": req,
                "nebpi_primary_gate": _gate_for(rules, req),
                "reason_code": "assigned",
                "downgraded_from": None,
                "assignment_id": a["assignment_id"],
                "conflicting_assignment_ids": [],
                "evidence_source_record_id": a["evidence_source_record_id"],
                "evidence_sha256": a["evidence_sha256"],
            }
    return out
