"""Load the Stage-4 method bundle and hash it.

Method parameters live in 04_PKPD/method/*.json, not in code, so that a change to an
inflection point, a rule or the calculator policy is a *content* change: it moves the
method hash, which moves the scorecard_set_id, which invalidates every cached result.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from .canonical import content_sha256, sha256_bytes
from .contract_version import ContractVersion

STAGE4_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METHOD_DIR = os.path.join(STAGE4_DIR, "method")

METHOD_FILES_V1 = {
    "cns_mpo": "cns_mpo_wager2010_v1.json",
    "nebpi": "nebpi_grossman2026_v1.json",
    "calculator_policy": "calculator_policy_v1.json",
    "delivery_rules": "delivery_rules_v1.json",
    "safety_taxonomy": "safety_taxonomy_v1.json",
    "sources": "sources.json",
    "prose": "stage4_prose_v1.json",
}


@dataclass(frozen=True)
class MethodBundle:
    cns_mpo: dict[str, Any]
    nebpi: dict[str, Any]
    calculator_policy: dict[str, Any]
    delivery_rules: dict[str, Any]
    safety_taxonomy: dict[str, Any]
    sources: dict[str, Any]
    # Every SENTENCE Stage 4 emits, declared as method DATA. A sentence that lives only in
    # the emitter is bound by nothing; declared here it is hashed into method_file_sha256 and
    # therefore into the scorecard_set_id, so it cannot be rewritten without moving identity.
    prose: dict[str, Any]
    method_file_sha256: dict[str, str]  # raw file bytes — any edit at all moves this
    bundle_sha256: str
    # v2 method content, in NEW files. None under v1: the seven v1 files are bound by hash into
    # every release ever emitted, so v2 ADDS rather than edits.
    nebpi_source_framing: Optional[dict[str, Any]] = None
    safety_taxonomy_v2: Optional[dict[str, Any]] = None

    @property
    def forbidden_fields(self) -> list[str]:
        """The v1 list, plus v2's additions when the v2 method is loaded.

        A forbidden-name list that nothing reads is a comment. v2 adds p/q/FDR (which would
        imply a hypothesis test this stage does not run) and the organ-system score names
        (which would recreate the single combined clinical verdict the taxonomy exists to
        prevent). The v1 list is never edited -- it is bound by hash into every release.
        """
        names = list(self.safety_taxonomy["prohibited_outputs"]["forbidden_field_names"])
        v2 = self.safety_taxonomy_v2 or {}
        names += list(
            (v2.get("prohibited_outputs_v2") or {}).get("additional_forbidden_field_names", []))
        return sorted(set(names))


# v2 method content lives in NEW files. The seven v1 files above are bound by hash into every
# release ever emitted, so editing one -- or adding one to that map -- would make all of them
# unverifiable. v2 therefore ADDS.
METHOD_FILES_V2 = {
    **METHOD_FILES_V1,
    "nebpi_source_framing": "nebpi_source_framing_v2.json",
    "safety_taxonomy_v2": "safety_taxonomy_v2.json",
}

METHOD_FILES = {
    ContractVersion.V1: METHOD_FILES_V1,
    ContractVersion.V2: METHOD_FILES_V2,
}


def load_method_bundle(method_dir: str = METHOD_DIR,
                       version: ContractVersion = ContractVersion.V1) -> MethodBundle:
    loaded: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    for key, filename in sorted(METHOD_FILES[version].items()):
        path = os.path.join(method_dir, filename)
        with open(path, "rb") as fh:
            raw = fh.read()
        hashes[key] = sha256_bytes(raw)
        loaded[key] = json.loads(raw.decode("utf-8"))
    # The prose catalog is reachable from the nebpi method dict, because `evaluate_nebpi` is
    # handed that dict and every requirement SENTENCE it emits must come from the catalog
    # rather than from a literal in the code. The raw-file hashes above are taken from the
    # BYTES, so this in-memory convenience cannot affect method_file_sha256.
    loaded["nebpi"]["prose"] = loaded["prose"]

    return MethodBundle(
        cns_mpo=loaded["cns_mpo"],
        nebpi=loaded["nebpi"],
        calculator_policy=loaded["calculator_policy"],
        delivery_rules=loaded["delivery_rules"],
        safety_taxonomy=loaded["safety_taxonomy"],
        sources=loaded["sources"],
        nebpi_source_framing=loaded.get("nebpi_source_framing"),
        safety_taxonomy_v2=loaded.get("safety_taxonomy_v2"),
        prose=loaded["prose"],
        method_file_sha256=hashes,
        bundle_sha256=content_sha256(hashes),
    )
