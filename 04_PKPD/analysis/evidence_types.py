"""`EvidenceType` — what KIND of study a row came from.

Its own module because both `evidence_records` and `nebpi_records` need it, and a shared type
that lives in one of the modules that uses it is a cycle waiting to happen (the same reason
`Provenance` sits in `contracts`).
"""

from __future__ import annotations

from enum import Enum


class EvidenceType(str, Enum):
    IN_VITRO = "in_vitro"
    IN_VIVO_ANIMAL = "in_vivo_animal"
    HUMAN_CLINICAL = "human_clinical"
    IN_SILICO = "in_silico"
    LABEL = "label"
