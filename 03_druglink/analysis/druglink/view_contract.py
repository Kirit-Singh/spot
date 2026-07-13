"""THE BROWSER PROJECTION CONTRACT: what a UI receives, and what it may never receive.

The view (:mod:`druglink.selection_view`) is what a STATIC browser is handed for ONE verified
selection. So the contract has to be checkable by the producer BEFORE the bytes leave, because a
browser cannot refuse what it has already rendered.

STRICT MEANS AN UNKNOWN FIELD IS A REFUSAL, NOT AN EXTRA
-------------------------------------------------------
A permissive schema is how a field nobody agreed to reaches a consumer that cannot be expected to
refuse it — and how a pooled score, a promoted hypothesis or a machine-local path arrives
looking like part of the contract. Every field is enumerated. An unexpected one is a NAMED
refusal.

The row columns are DERIVED from the producer's own column tuples (``candidates_v2`` /
``pathway_context_v2``) rather than restated, so the contract and the tables it describes cannot
drift apart. The JSON schema (``spot.stage03_selection_view.v1``) locks the DOCUMENT envelope and
enum-locks the vocabularies; this module locks the ROWS. Both run, and both must pass.

WHAT MAY NEVER CROSS THE SEAM
-----------------------------
* a machine-local or absolute filesystem path — the view is content-addressed, and a path is a
  fact about the host that produced it, not about the science;
* a combined / balanced / weighted / headline / composite objective, at any depth;
* a p, q, FDR or adjusted p — Stage 3 is ``inference_status=not_calibrated``: it has no null
  distribution and no multiple-testing frame, so such a field would have the FORM of a calibrated
  statistic and none of the meaning, and a reader would be right to trust it;
* a retired promotion / eligibility key;
* an unbounded blob — a browser has to render this.
"""
from __future__ import annotations

from typing import Any, Mapping

from . import artifact_class as ac
from . import bundle_v2 as bv2
from . import candidates_v2 as cv2
from . import pathway_context_v2 as pc2
from . import schemas
from . import selection_view as sv
from .hashing import contains_local_path
from .view_store import (  # noqa: F401  (the store's invariant is enforced where the store is)
    GATE_ROLE_IN_THE_STORE,
    GATE_SELECTION_IN_THE_STORE,
    ROLE_COLUMN,
    STORE_IDENTITY_VERIFIER_ID,
    check_store_is_selection_independent,
    checks as store_identity_checks,
)

# ROLE_COLUMN — the one annotation the projection stamps on a row: EVERY role THIS question gives
# its arm. A LIST, because one reusable arm can carry BOTH roles — away_from_A(high) and
# toward_B(low) are both `decrease`, and Stage 1 admits that selection. A scalar would report only
# the first. It is DEFINED in `view_store`, beside the refusal that keeps it OUT of the store, so
# the column the view adds and the column the store forbids can never drift apart.

# The candidate's VIEW-SCOPED evidence, alongside (never instead of) the store's global fields.
VIEW_CANDIDATE_COLUMNS: tuple[str, ...] = (
    "view_arm_keys_by_origin", "view_n_edges_by_origin", "view_roles", "view_edge_ids",
    "view_stage3_evidence_classes", "view_directional_evidence_statuses",
    "view_observed_perturbation_support", "view_arm_ranks",
)

# EVERY column a projected row may carry. DERIVED from the producer, so the two cannot drift.
ROW_COLUMNS: dict[str, frozenset[str]] = {
    "arm_slots": frozenset(cv2.ARM_SLOT_COLUMNS) | {ROLE_COLUMN},
    "target_drug_edges": frozenset(cv2.EDGE_COLUMNS) | {ROLE_COLUMN},
    "arm_summaries": frozenset(cv2.ARM_SUMMARY_COLUMNS) | {ROLE_COLUMN},
    "candidates": frozenset(cv2.CANDIDATE_COLUMNS) | frozenset(VIEW_CANDIDATE_COLUMNS),
    "pathway_context": frozenset(pc2.CONTEXT_COLUMNS) | {ROLE_COLUMN},
    "source_records": frozenset(cv2.SOURCE_RECORD_COLUMNS),
    "dispositions": frozenset(cv2.DISPOSITION_COLUMNS) | {ROLE_COLUMN},
}

# The document's own top-level fields. Enumerated, because "strict" has to mean something.
DOCUMENT_FIELDS: frozenset[str] = frozenset({
    "schema_version", "artifact_class", "view_method_id", "view_id", "view_content_sha256",
    "selection", "selected_arms", "store", "admission",
    "origin_type", "origin_types_present", "arm_evidence", "tables", "counts",
    "guarantees", "missingness", "inference_status",
    "combined_objective_permitted", "candidate_rank_permitted", "headline_arm_permitted",
    "p_q_fdr_permitted",
})

# A browser has to render this. These are ENGINEERING bounds, not scientific ones: they exist so
# a pathological store cannot ship a document no UI can open. Exceeding one is a refusal that
# names the table, never a silent truncation — a truncated table is a dropped row, and a dropped
# row is indistinguishable from a row nobody found.
MAX_ROWS_PER_TABLE = 50_000
MAX_STRING_LEN = 16_384

GATE_UNKNOWN_FIELD = "the_view_carries_a_field_the_projection_contract_does_not_have"
GATE_LOCAL_PATH = "the_view_carries_a_machine_local_or_absolute_filesystem_path"
GATE_UNBOUNDED = "the_view_carries_a_payload_no_browser_can_be_asked_to_render"


class ViewContractError(ValueError):
    """A named, fail-closed refusal. The view does not leave the producer."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _refuse(gate: str, message: str) -> None:
    raise ViewContractError(gate, message)


def _check_strings(node: Any, path: str = "$") -> None:
    if isinstance(node, str) and len(node) > MAX_STRING_LEN:
        _refuse(GATE_UNBOUNDED,
                f"{path} holds a {len(node)}-character string (cap {MAX_STRING_LEN}). A blob "
                "nobody bounded is a blob a browser is asked to render and cannot.")
    if isinstance(node, Mapping):
        for key, value in node.items():
            _check_strings(value, f"{path}.{key}")
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            _check_strings(value, f"{path}[{i}]")


def check_rows(view: Mapping[str, Any]) -> None:
    """Every projected row carries EXACTLY the columns its table's contract has. No extras."""
    tables = view.get("tables") or {}
    unknown_tables = sorted(set(tables) - set(ROW_COLUMNS))
    if unknown_tables:
        _refuse(GATE_UNKNOWN_FIELD,
                f"the view ships table(s) {unknown_tables} the projection contract does not "
                f"have; it projects exactly {sorted(ROW_COLUMNS)}.")
    for name, rows in sorted(tables.items()):
        if len(rows) > MAX_ROWS_PER_TABLE:
            _refuse(GATE_UNBOUNDED,
                    f"{name} carries {len(rows)} rows (cap {MAX_ROWS_PER_TABLE}). The cap is a "
                    "refusal, never a truncation: a truncated table is a dropped row, and a "
                    "dropped row is indistinguishable from a row nobody found.")
        allowed = ROW_COLUMNS[name]
        for row in rows:
            extra = sorted(set(row) - allowed)
            if extra:
                _refuse(GATE_UNKNOWN_FIELD,
                        f"a {name} row carries {extra}, which the projection contract does not "
                        "have. A field nobody agreed to is a field no consumer can be expected "
                        "to refuse — and it is exactly how a pooled score or a promoted "
                        "hypothesis reaches a UI looking like part of the contract.")


def check_browser_safe(view: Mapping[str, Any]) -> None:
    """No machine-local path, no pooled objective, no p/q/FDR, no retired key, no blob."""
    extra = sorted(set(view) - DOCUMENT_FIELDS)
    if extra:
        _refuse(GATE_UNKNOWN_FIELD,
                f"the view document carries top-level field(s) {extra} the contract does not "
                f"have; it is exactly {sorted(DOCUMENT_FIELDS)}.")

    hits = contains_local_path(view)
    if hits:
        _refuse(GATE_LOCAL_PATH,
                f"the view carries machine-local path(s) at {hits[:3]}. A view is "
                "content-addressed and travels to a browser on another host: a path is a fact "
                "about the machine that produced it, not about the science, and it is the "
                "easiest way for an absolute filesystem location to reach a shipped page.")

    # The two structural firewalls, RE-ASSERTED on the bytes that actually leave. The store
    # already refuses both; a property nobody re-checks on the emitted document is a property
    # the next writer can drop.
    ac.check_no_retired_keys({"view": view})
    bv2.check_no_combined_objective(view)
    bv2.check_no_pq_fdr(view)
    _check_strings(view)


def validate(view: Mapping[str, Any]) -> Mapping[str, Any]:
    """The whole contract: the schema, the rows, and the browser firewall. All three."""
    schemas.validate(dict(view), sv.VIEW_SCHEMA, context="stage3_selection_view")
    check_rows(view)
    check_browser_safe(view)
    return view


def contract() -> dict[str, Any]:
    """The contract itself, publishable to W12 / W6 — the shape, not an example of it."""
    return {
        "schema_version": sv.VIEW_SCHEMA,
        "view_method_id": sv.VIEW_METHOD_ID,
        "document_fields": sorted(DOCUMENT_FIELDS),
        "tables": {name: sorted(cols) for name, cols in sorted(ROW_COLUMNS.items())},
        "join_time_annotation": ROLE_COLUMN,
        "view_scoped_candidate_fields": list(VIEW_CANDIDATE_COLUMNS),
        "strict": True,
        "an_unknown_field_is_a_refusal_not_an_extra": True,
        "no_machine_local_paths": True,
        # WHAT THE PRODUCER PROVED BEFORE IT PROJECTED. The view's `store` block is not a copy of
        # the bundle's claims about itself: every hash in it was re-derived from the rows in hand
        # and re-read from the store on disk, and these are the gates that had to pass first.
        "store_identity_verifier_id": STORE_IDENTITY_VERIFIER_ID,
        "store_identity_checks": store_identity_checks(),
        "max_rows_per_table": MAX_ROWS_PER_TABLE,
        "max_string_length": MAX_STRING_LEN,
        "guarantees": sv.guarantees(),
        "vocabularies": sv.vocabularies(),
    }
