"""Which evidence contract a bundle, a run and a release are speaking.

There are two, and they are not interchangeable:

  v1  the original contract. FROZEN (`contract_v1_frozen.py`). Every release ever emitted is
      one of these, and every one of them must still verify, byte for byte, forever.
  v2  the acquisition-complete contract. Everything v1 has, plus what an ACQUISITION must be
      able to show: how the bytes were obtained, which assay a potency came from, what kind of
      exposure a concentration is, whether a ratio was reported or worked out.

The version is a property of the EVIDENCE, not of the code. A v1 bundle stays v1 forever — it
does not become acquisition-complete because newer code can read it, and its rows do not
acquire v2 columns full of nulls. A null `relation` is not "no concept of a relation"; it is
"this row has a relation and nobody knows it", which is a different and false claim.

Absent means v1. A release written before this field existed cannot be expected to declare it,
and treating that silence as anything else would make every historical artifact unreadable the
moment a v2 appeared.
"""

from __future__ import annotations

from enum import Enum


class ContractVersion(str, Enum):
    V1 = "v1"
    V2 = "v2"

    @classmethod
    def of(cls, declared: object) -> "ContractVersion":
        """Absent/None -> V1. A release that predates the field IS a v1 release."""
        if declared is None or declared == "":
            return cls.V1
        return cls(declared)


# The bundle schema_id each contract is carried in.
BUNDLE_SCHEMA = {
    ContractVersion.V1: "spot.stage04_evidence_bundle.v1",
    ContractVersion.V2: "spot.stage04_evidence_bundle.v2",
}

SCHEMA_TO_VERSION = {v: k for k, v in BUNDLE_SCHEMA.items()}
