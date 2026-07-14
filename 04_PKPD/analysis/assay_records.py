"""The assay a number was measured in, as structured fields rather than a sentence.

The audit: the potency record had value / binding-state / assay / context, but no structured
activity, assay, target or document id, no relation, no confidence and no validity comment —
and "hiding those in free text would make independent reconstruction weak."

`Relation` is the one that changes conclusions. A curated database records `IC50 > 10000 nM`
about as often as `IC50 = 47 nM`, and the two sentences mean opposite things: the first says
the assay ran OUT OF RANGE — no effect was reached at the highest concentration tested — and
reading its magnitude as a point estimate converts "we could not reach the effect" into "the
effect happens at 10 uM". Only `=` is a point estimate, and only a point estimate can be the
denominator of an exposure margin.

`confidence_score` is the SOURCE's curation score (ChEMBL target confidence, 0-9). It is
carried, never computed, and never combined with anything: spot emits no score of its own.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field

from .contracts import Strict


class Relation(str, Enum):
    """What the source actually said about the magnitude.

    A censored potency (`>`, `<`, `>=`, `<=`) and an approximate one (`~`) are not point
    estimates, and `PotencyRecord.is_point_estimate` is what stops the margin code from
    treating them as one.
    """

    EQ = "="
    LT = "<"
    GT = ">"
    LE = "<="
    GE = ">="
    APPROX = "~"


POINT_ESTIMATE_RELATIONS = (Relation.EQ,)


class AssayBinding(Strict):
    """The activity / assay / target / document a potency or transporter number came from.

    Every id here is the SOURCE's stable id, so an independent reader can pull the same
    record and see the same number. That is the difference between evidence and a citation.
    """

    # The exact source rows. ChEMBL's four-level identity: which measurement, in which assay,
    # against which target, reported in which document.
    activity_id: Optional[str] = None
    assay_id: Optional[str] = None
    target_id: Optional[str] = None
    document_id: Optional[str] = None

    # What KIND of assay: binding (B), functional (F), ADMET (A), physicochemical (P), or a
    # free description when the source does not use a coded vocabulary.
    assay_type: Optional[str] = None
    assay_description: Optional[str] = None
    # The system the measurement was actually made in — a cell-free kinase assay and a
    # patient-derived GBM line are not interchangeable evidence.
    experimental_system: Optional[str] = None

    # Species is load-bearing: a Ki against the mouse orthologue is not a Ki against the human
    # target, and the audit is explicit that species differences matter (P-gp especially).
    target_organism: str = Field(min_length=1)
    target_uniprot_accession: Optional[str] = None

    # The source's own curation confidence (ChEMBL target confidence is 0-9). Carried, never
    # computed, never combined into anything.
    confidence_score: Optional[int] = Field(default=None, ge=0, le=9)
    # The source's own doubt about the number ("Potential author error", "Outside typical
    # range"). A curator's warning travels WITH the number, or it is lost.
    validity_comment: Optional[str] = None
