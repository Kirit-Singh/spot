"""Safety evidence + named GBM treatment scenarios.

Two things this module refuses to do, both enforced by tests:

  * render `no_evidence_found` as safe. It is a statement about the search, not about
    the drug. Every row carries renders_as_safe=False and says so in words.
  * emit a traffic light, a composite tolerability score, or a recommendation.
    `assert_no_forbidden_fields` scans every artifact before it is written.
"""

from __future__ import annotations

from typing import Any, Iterable

from .evidence_records import (
    EvidenceState,
    FindingType,
    GbmScenario,
    InteractionType,
    LabelIdentity,
    Provenance,
    SafetyEvidenceRecord,
)
from .label_adapters import EMA_LABEL_SUPPORTED_ALLOWED, ParsedLabel

# The text a reader sees beside a safety finding. Declared in method/stage4_prose_v1.json and
# loaded from there — NOT typed here. Rewriting `no_evidence_found` to read like a clean bill of
# health is the most dangerous edit available on a release, so it is method data, hashed into the
# scorecard_set_id, and re-read cell-for-cell by the independent verifier.
def _load_display() -> dict[str, str]:
    import json
    import os

    from .method_config import METHOD_DIR

    with open(os.path.join(METHOD_DIR, "stage4_prose_v1.json"), encoding="utf-8") as fh:
        return dict(json.load(fh)["safety"]["evidence_state_display"])


EVIDENCE_STATE_DISPLAY: dict[str, str] = _load_display()


class ForbiddenFieldError(AssertionError):
    """An artifact tried to carry a combined clinical verdict."""


def render_evidence_state(state: str) -> dict[str, Any]:
    if state not in EVIDENCE_STATE_DISPLAY:
        raise ValueError(f"unknown evidence state {state!r}")
    return {
        "evidence_state": state,
        "display_text": EVIDENCE_STATE_DISPLAY[state],
        # Not one of the five states renders as "safe" — not even no_evidence_found.
        "renders_as_safe": False,
    }


class LabelIdentityError(ValueError):
    """The label is not a label for this candidate's active moiety."""


def safety_rows_from_label(
    parsed: ParsedLabel,
    candidate_id: str,
    active_moiety_id: str,
    source_record_id: str,
    access_date: str,
    extraction_transform: str,
    *,
    expected_unii: str | None = None,
    expected_moiety_name: str | None = None,
) -> list[SafetyEvidenceRecord]:
    """One row per boxed warning / contraindication / warning / interaction / adverse reaction.

    The label must actually BE this moiety's label. The audit attached six findings from a
    FIXTURIB / UNII ZZZZZZZZ99 label to active moiety FXM-004 simply because the caller
    said so; identity now has to be proven from the parsed label itself.
    """
    if parsed.label_source == "ema_label" and not EMA_LABEL_SUPPORTED_ALLOWED:
        raise LabelIdentityError(
            "the EMA cached shape is not validated against a live EMA response "
            "(EMA_ADAPTER_STATUS=shape_declared_unverified_against_live_source), so EMA rows "
            "cannot become label_supported evidence yet"
        )

    if expected_unii or expected_moiety_name:
        unii_ok = bool(expected_unii) and expected_unii in parsed.active_moiety_unii
        wanted_name = (expected_moiety_name or "").strip().lower()
        name_ok = bool(wanted_name) and any(
            wanted_name == n.strip().lower() for n in parsed.active_moiety_names
        )
        if not (unii_ok or name_ok):
            raise LabelIdentityError(
                f"label {parsed.product_identity!r} declares active moieties "
                f"{parsed.active_moiety_names} / UNII {parsed.active_moiety_unii}, which do not "
                f"match {active_moiety_id!r} (expected UNII {expected_unii!r} / name "
                f"{expected_moiety_name!r}). A label for a different molecule is not evidence "
                "about this one."
            )
    else:
        raise LabelIdentityError(
            "refusing to bind label findings to an active moiety without an identity to match "
            "on: pass expected_unii and/or expected_moiety_name"
        )

    if len(parsed.active_moiety_names) > 1 and not expected_unii:
        raise LabelIdentityError(
            f"label declares {len(parsed.active_moiety_names)} active moieties "
            f"{parsed.active_moiety_names}; a multi-ingredient product needs an unambiguous "
            "UNII to bind a finding to one moiety"
        )

    rows: list[SafetyEvidenceRecord] = []
    for i, f in enumerate(parsed.findings):
        rows.append(
            SafetyEvidenceRecord(
                evidence_id=f"{candidate_id}.{parsed.label_source}.{f.finding_type}.{i:03d}",
                candidate_id=candidate_id,
                active_moiety_id=active_moiety_id,
                evidence_state=EvidenceState.LABEL_SUPPORTED,
                finding_type=FindingType(f.finding_type),
                finding_text=f.finding_text,
                label_identity=LabelIdentity(
                    label_source=parsed.label_source,
                    setid=parsed.setid,
                    application_number=parsed.application_number,
                    product_identity=parsed.product_identity,
                    label_version=parsed.label_version,
                    effective_date=parsed.effective_date,
                    labeled_section_code=f.labeled_section_code,
                    labeled_section_name=f.labeled_section_name,
                    code_system=f.code_system,
                ),
                provenance=Provenance(
                    source_record_id=source_record_id,
                    access_date=access_date,
                    raw_response_sha256=parsed.raw_sha256,
                    extraction_transform=extraction_transform,
                ),
            )
        )
    return rows


def scenario_matrix(candidate_id: str, records: Iterable[SafetyEvidenceRecord]) -> list[dict[str, Any]]:
    """The five named GBM scenarios x the eight interaction types, kept separate.

    An empty cell is `not_evaluated`, never `no_evidence_found`: nobody looked.
    """
    mine = [r for r in records if r.candidate_id == candidate_id]
    cells: list[dict[str, Any]] = []
    for scenario in GbmScenario:
        for itype in InteractionType:
            hits = [
                r
                for r in mine
                if r.gbm_scenario == scenario and r.interaction_type == itype
            ]
            if hits:
                state = _strongest_state([h.evidence_state.value for h in hits])
            else:
                state = EvidenceState.NOT_EVALUATED.value
            cells.append(
                {
                    "candidate_id": candidate_id,
                    "gbm_scenario": scenario.value,
                    "interaction_type": itype.value,
                    **render_evidence_state(state),
                    "n_evidence_rows": len(hits),
                    "evidence_ids": sorted(h.evidence_id for h in hits),
                }
            )
    return cells


_STATE_ORDER = [
    "label_supported",
    "literature_supported",
    "signal_only",
    "no_evidence_found",
    "not_evaluated",
]


def _strongest_state(states: list[str]) -> str:
    """Report the best-supported state present. This is a display choice over rows that
    all remain individually listed — it is not an aggregation of the evidence itself."""
    for s in _STATE_ORDER:
        if s in states:
            return s
    return EvidenceState.NOT_EVALUATED.value


def assert_no_forbidden_fields(obj: Any, forbidden: Iterable[str], where: str = "artifact") -> None:
    """Fail loudly if any artifact grows a combined clinical verdict."""
    forbidden_set = {f.lower() for f in forbidden}

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if str(k).lower() in forbidden_set:
                    raise ForbiddenFieldError(
                        f"{where}: forbidden field {k!r} at {path}. Stage 4 emits evidence lanes, "
                        "not a combined clinical score or recommendation."
                    )
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(obj, where)
