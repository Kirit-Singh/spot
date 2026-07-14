"""`organ_system` — W9's optional v2 field, acquired from a source or left `unspecified`.

Coordination note for W9 (v2 owner). Acquisition supplies this field under one rule:

    A value exists only when a public structured source ACTUALLY CARRIES an organ-system field.
    It is then copied VERBATIM, with the exact section/locator and the raw record identity
    (set ID, label version, response SHA-256). Otherwise the value is `unspecified` /
    `not_evaluated` — and the record still says where we looked and at which bytes, so
    "unspecified" can never be confused with "never checked".

What acquisition will NOT do, on any path:

    Classify an organ system from a target, a gene, a mechanism, a pharmacologic class or a drug
    name. "Anti-CTLA-4, therefore immune system" is an inference. In the artifact it would be
    indistinguishable from a sourced value, and tissue specificity that no source asserted is
    exactly the kind of number this project refuses to invent. `refuse_inferred_organ_system`
    exists so that path raises instead of being available.

**State of the world in this pass: `ORGAN_SYSTEM_SPECS` is EMPTY.** No source in the Stage-4
ledger (PubChem, RxNorm, DailyMed, openFDA/Drugs@FDA) carries an organ-system field:

  * SPL/DailyMed has LOINC-coded SECTIONS, not an organ-system attribute. Some labels group
    adverse reactions under MedDRA System Organ Class headings, but recognising a heading AS an
    SOC needs the MedDRA vocabulary, whose licence is not established for this project — and
    matching heading text without it would be a classifier, i.e. the inference above.
  * openFDA carries `pharm_class_*` (EPC/MoA/PE/CS). A pharmacologic class is not an organ system.
  * PubChem and RxNorm carry neither.

So every real extraction returns `unspecified` today. The plumbing is built and tested anyway, so
that when a source-backed field appears it is a reviewed SPEC entry naming the source and the
locator — not a code change buried in an adapter. No new external dataset is required, and none
was added.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .firewall import Rejection

UNSPECIFIED = "unspecified"
EXTRACTION_TRANSFORM = "organ_system.extract_organ_system:v1 (verbatim from a declared source " \
                       "field; never inferred)"

NO_SOURCE_REASON = (
    "no public source in the Stage-4 ledger carries an organ-system field: SPL has LOINC-coded "
    "sections rather than an organ-system attribute, openFDA carries pharmacologic class (not an "
    "organ system), and PubChem/RxNorm carry neither. The value is therefore not_evaluated — it "
    "is not inferred from the target, the mechanism or the drug name."
)


@dataclass(frozen=True)
class OrganSystemSpec:
    """A DECLARED source-backed field. Adding one is a reviewed decision, not an adapter tweak."""

    source_key: str
    field_path: tuple[str, ...]
    section_code: Optional[str]
    code_system: Optional[str]
    note: str
    # Is the source's value a term from a controlled vocabulary, or the source's own free term?
    # W9 needs to know which; acquisition does not normalise one into the other.
    value_kind: str = "source_term"
    subsection_code: Optional[str] = None


# Empty, deliberately. See the module docstring.
ORGAN_SYSTEM_SPECS: tuple[OrganSystemSpec, ...] = ()


@dataclass(frozen=True)
class LabelRef:
    """What the extractor reads: the raw record identity, and whatever structured fields the
    source actually gave us. Callers build one of these rather than passing a parsed label, so
    the extractor can never reach into free text and start pattern-matching."""

    source_record_id: str
    setid: Optional[str]
    label_version: Optional[str]
    raw_response_sha256: Optional[str]
    structured: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OrganSystemEvidence:
    """The field, plus everything a reviewer needs to check it — including when it is absent.

    Field names are W9's, not new ones: `source_record_id`, `raw_response_sha256` and
    `extraction_transform` are exactly the `evidence_records.Provenance` names, so the value binds
    to the response it came from the same way every other Stage-4 number does.
    """

    organ_system: str            # a controlled value, or the source term, VERBATIM
    value_kind: str              # controlled_value | source_term | none
    evidence_state: str          # observed | not_evaluated
    source_key: str
    source_record_id: str        # the acquisition record whose bytes were read
    setid: Optional[str]
    label_version: Optional[str]
    raw_response_sha256: Optional[str]
    section_code: Optional[str] = None
    subsection_code: Optional[str] = None
    code_system: Optional[str] = None
    locator: Optional[str] = None
    extraction_transform: str = EXTRACTION_TRANSFORM
    reason: str = ""


def refuse_inferred_organ_system(hint: str) -> None:
    """Any attempt to derive the field from biology instead of from a source. Always raises."""
    raise Rejection(
        "organ_system_inference_refused",
        f"organ_system cannot be classified from {hint!r}. It is admissible only when a public "
        "structured source carries the field, and is then copied verbatim with its locator. A "
        "target, gene, mechanism, pharmacologic class or drug name is not an observation of "
        "tissue specificity, and a guessed value would be indistinguishable in the artifact from "
        "a sourced one.")


def extract_organ_system(label: Any, *, source_key: str,
                         specs: tuple[OrganSystemSpec, ...] = ORGAN_SYSTEM_SPECS,
                         ) -> OrganSystemEvidence:
    """Take the field from a declared source field, or state its absence. Never guess."""
    source_record_id = getattr(label, "source_record_id", "")
    setid = getattr(label, "setid", None)
    label_version = getattr(label, "label_version", None)
    raw_response_sha256 = getattr(label, "raw_response_sha256", None)

    for spec in specs:
        if spec.source_key != source_key:
            continue
        value = _read_path(getattr(label, "structured", None) or {}, spec.field_path)
        if value is None:
            continue
        return OrganSystemEvidence(
            organ_system=str(value),          # verbatim: not mapped, normalised or re-classified
            value_kind=spec.value_kind,
            evidence_state="observed",
            source_key=source_key,
            source_record_id=source_record_id,
            setid=setid,
            label_version=label_version,
            raw_response_sha256=raw_response_sha256,
            section_code=spec.section_code,
            subsection_code=spec.subsection_code,
            code_system=spec.code_system,
            locator=".".join(spec.field_path),
            reason=f"read verbatim from the {source_key} field {'.'.join(spec.field_path)!r}",
        )

    return OrganSystemEvidence(
        organ_system=UNSPECIFIED,
        value_kind="none",
        evidence_state="not_evaluated",
        source_key=source_key,
        source_record_id=source_record_id,
        setid=setid,
        label_version=label_version,
        raw_response_sha256=raw_response_sha256,
        reason=NO_SOURCE_REASON if not specs else (
            f"the declared {source_key} organ-system field is absent from this record. An absent "
            "field is an absent value, not a value to be inferred."),
    )


def _read_path(node: Any, path: tuple[str, ...]) -> Optional[Any]:
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    if node is None:
        return None
    text = str(node).strip()
    return text or None
