"""Build a REAL science-evidence registry for tests to reference.

The tests do not fake the registry. They write actual records — raw bytes, structured
bytes, provenance — through the writer, and then reference them. A test that stubbed the
resolution step would prove nothing about the thing it exists to check: that a reference
resolves to bytes on disk and those bytes re-hash to what the reference binds.
"""
from __future__ import annotations

from typing import Any, Optional

from druglink import science_registry as sr

SESSION = "cs_sess_20260712T0213Z"
MODEL = "claude-opus-4-8"
METHOD = "claude-science.disease-context-review.v1"


def provenance(**over: Any) -> dict[str, Any]:
    prov = {
        "session_id": SESSION,
        "model_id": MODEL,
        "method_id": METHOD,
        "source_chain": ["pubmed:31234567", "chembl:CHEMBL1201581"],
        "raw_media_type": "text/markdown",
    }
    prov.update(over)
    return prov


def make(registry_root: str,
         specs: Optional[list[tuple[str, str, str]]] = None) -> dict[str, dict[str, str]]:
    """Write a registry and return, per id, the TYPED TRIPLE that references it.

    ``specs`` is ``(science_evidence_id, record_type, raw_text)``.
    """
    if specs is None:
        specs = [
            ("sci_1", "mechanistic_rationale",
             "CTLA4 blockade relieves a co-inhibitory brake on effector CD4 T cells."),
            ("sci_2", "literature_support",
             "Reported in GBM-adjacent settings; not measured in this dataset."),
            ("sci_3", "contradiction",
             "One report finds the opposite direction in a non-CNS context."),
            ("sci_4", "disease_context_review",
             "Disease-context reading of the inverse-direction hypothesis."),
        ]

    records = []
    refs: dict[str, dict[str, str]] = {}
    for evid, rtype, text in specs:
        raw = text.encode("utf-8")
        structured = {"claim": text, "record_type": rtype, "confidence": "suggestive"}
        record = sr.build_record(science_evidence_id=evid, record_type=rtype,
                                 provenance=provenance(), raw=raw, structured=structured)
        records.append((record, raw, structured))
        refs[evid] = {
            "science_evidence_id": evid,
            "science_evidence_sha256": record["record_sha256"],
            "record_type": rtype,
        }

    sr.write(registry_root, records)
    return refs
