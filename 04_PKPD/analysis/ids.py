"""scorecard_set_id derivation.

The id IS the cache key, so it must move whenever anything that could change a number
changes. The audit found four things that could change a result without moving it, and
all four are bound in now:

  * the source CLASS. Relabeling fixture sources as public data left the id identical.
    The registry now hashes the whole provenance class (type, acquisition status, URL,
    record id, release, license, byte count), not just `source_id -> raw_sha256`.
  * the NAMESPACE. A fixture candidate set and a production one hashed alike.
  * potency-context relevance LINKS, which flipped a margin from not_computable to
    computed while the id stood still.
  * the analysis CODE. The scoring implementation could be altered and the id would not
    move, so a scorecard could be served for a number the code no longer produces.

Magnitudes enter identity as exact decimal strings (`quantity.py`), never as floats on a
universal rounding grid — 1e-12 and 4e-11 are different concentrations and hash apart.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .canonical import sha256_bytes, short_id, strict_content_sha256
from .contracts import STAGE4_METHOD_VERSION, Stage3DrugCandidateSet
from .method_config import MethodBundle

ANALYSIS_DIR = os.path.dirname(os.path.abspath(__file__))


def code_tree_sha256(root: str = ANALYSIS_DIR) -> tuple[str, dict[str, str]]:
    """Hash the analysis tree. Alter the scoring code and every id moves."""
    files: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            with open(full, "rb") as fh:
                files[rel] = sha256_bytes(fh.read())
    return strict_content_sha256(dict(sorted(files.items()))), files


def _as_content(rows: list[Any]) -> list[Any]:
    """Evidence rows -> canonical content. Exact decimals; no floats."""
    out = []
    for r in rows:
        d = r.model_dump(mode="json") if hasattr(r, "model_dump") else r
        out.append(_no_floats(d))
    out.sort(key=strict_content_sha256)
    return out


def _no_floats(node: Any) -> Any:
    """Any float that survives into identity content is a bug; make it explicit and exact."""
    if isinstance(node, float):
        from decimal import Decimal

        return format(Decimal(repr(node)).normalize(), "E")
    if isinstance(node, dict):
        return {k: _no_floats(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_no_floats(v) for v in node]
    return node


def evidence_inputs_digest(evidence: dict[str, list[Any]]) -> str:
    """Hash every evidence input record, including its calculator and response hash."""
    return strict_content_sha256(
        {lane: _as_content(evidence[lane]) for lane in sorted(evidence)}
    )


def source_registry_digest(sources: dict[str, Any]) -> str:
    """The whole provenance class, not just the bytes hash.

    Relabeling a synthetic fixture as an acquired public record changes this digest, and
    therefore the scorecard_set_id — which is the only way "is this real data?" can stay
    an answerable question.
    """
    payload = {}
    for sid, rec in sorted(sources.items()):
        if hasattr(rec, "model_dump"):
            d = rec.model_dump(mode="json")
            payload[sid] = {
                "source_type": d.get("source_type"),
                "acquisition_status": d.get("acquisition_status"),
                "url": d.get("url"),
                "record_id": d.get("record_id"),
                "release_version": d.get("release_version"),
                "license": d.get("license"),
                "raw_sha256": d.get("raw_sha256"),
                "raw_bytes": d.get("raw_bytes"),
                "raw_media_type": d.get("raw_media_type"),
            }
        else:
            payload[sid] = dict(rec)
    return strict_content_sha256(payload)


def derive_scorecard_set_id(
    cset: Stage3DrugCandidateSet,
    method: MethodBundle,
    evidence: dict[str, list[Any]],
    sources: dict[str, Any],
    environment_lock_sha256: str,
    config: Optional[dict[str, Any]] = None,
    code_sha256: Optional[str] = None,
) -> tuple[str, dict[str, Any]]:
    """-> (scorecard_set_id, the exact object it was hashed over)."""
    binding = cset.stage3_binding
    key = {
        "stage3": {
            "schema_id": cset.schema_id,
            "stage3_run_id": cset.stage3_run_id,
            "candidate_set_id": cset.candidate_set_id,
            "candidate_rows_sha256": cset.candidate_rows_sha256,
            "namespace": cset.namespace.value,
            "is_fixture": cset.is_fixture,
            "stage3_method_version": cset.stage3_method_version,
            "upstream_contrast_id": cset.upstream_contrast_id,
            "upstream_gene_lever_set_sha256": cset.upstream_gene_lever_set_sha256,
            # The exact upstream Stage-3 artifact, including ITS code and env identity.
            "stage3_binding": binding.model_dump(mode="json") if binding else None,
        },
        "stage4_method_version": STAGE4_METHOD_VERSION,
        "method_file_sha256": dict(sorted(method.method_file_sha256.items())),
        "analysis_code_sha256": code_sha256 or code_tree_sha256()[0],
        "config_sha256": strict_content_sha256(_no_floats(config or {})),
        "evidence_inputs_sha256": evidence_inputs_digest(evidence),
        "source_registry_sha256": source_registry_digest(sources),
        "environment_lock_sha256": environment_lock_sha256,
    }
    return short_id(strict_content_sha256(key)), key
