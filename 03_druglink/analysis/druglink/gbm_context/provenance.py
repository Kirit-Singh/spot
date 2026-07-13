"""Provenance for the GBM disease-context layer.

Records the pinned public sources + licenses (Open Targets Data 26.06 / CC0; DepMap Public
26Q1 / CC BY 4.0), the honest tissue/organ-axis note, a deterministic content hash of the
module source, the runtime env, the rerun command, and an explicit populated-vs-missing
map. Everything a reader needs to reproduce the run, and nothing invented.
"""
from __future__ import annotations

import hashlib
import platform
import sys
from typing import Any

from . import ot_disease as ot
from . import depmap_bridge as db

SOURCES: dict[str, Any] = {
    "open_targets": {
        "name": "Open Targets Platform",
        "data_version": ot.OT_DATA_VERSION_EXPECTED,
        "endpoint": ot.OT_ENDPOINT,
        "license": ot.OT_LICENSE,
        "license_url": ot.OT_LICENSE_URL,
        "verified_on": ot.OT_VERIFIED_ON,
        "glioblastoma_id": ot.GLIOBLASTOMA_ID,
        "glioma_id": ot.GLIOMA_ID,
        "query_field": "Target.associatedDiseases(Bs: [diseaseIds])",
        "note": ("disease ids verified live against the API; EFO_0000519 is null/"
                 "deprecated and was NOT used. Association scores are upstream-reported, "
                 "non-gating."),
    },
    "depmap": {
        "name": db.DEPMAP_RELEASE_NAME,
        "release_id": db.DEPMAP_RELEASE_ID,
        "license": db.DEPMAP_LICENSE,
        "license_url": db.DEPMAP_LICENSE_URL,
        "portal": db.DEPMAP_PORTAL,
        "required_files": list(db.REQUIRED_FILES),
        "cell_line_inclusion_rule": db.CELL_LINE_INCLUSION_RULE,
        "source_module": db.DEPMAP_SOURCE_MODULE,
        "note": ("byte pinning + dependency computation are owned by the Stage-2 DepMap "
                 "lane; consumed here only via a validated per-gene handoff."),
    },
}

# This is a CD4+ T-cell (blood/immune) perturbation assay joined to tumor cell-line
# dependency + a single disease association. There is no tissue/organ axis on the immune
# effect; the tumor + disease contexts are named categories, not organ-expression gradients.
TISSUE_ORGAN_AXIS: dict[str, Any] = {
    "immune_assay_tissue_organ_axis_present": False,
    "immune_assay_rationale": (
        "The immune-cell effect comes from an in-vitro CD4+ T-cell (blood) Perturb-seq "
        "assay with donor x condition x perturbation axes only; there is no tissue/organ "
        "axis and none is inferred."),
    "tumor_context": (
        "Tumor-cell dependency is over named GBM/glioma cell lines (DepMap lineage node); "
        "a discrete cell-line panel, not a tissue-expression gradient."),
    "disease_context": (
        "Disease association is to glioblastoma (MONDO_0018177) and glioma "
        "(MONDO_0021042) as single disease categories, not a tissue axis."),
}


def code_hash(paths: list[str]) -> str:
    """Deterministic, order-independent sha256 over the given source files' bytes."""
    h = hashlib.sha256()
    for p in sorted(paths):
        with open(p, "rb") as fh:
            h.update(hashlib.sha256(fh.read()).digest())
    return h.hexdigest()


def env_fingerprint() -> dict[str, Any]:
    return {"python": sys.version.split()[0], "platform": platform.platform(),
            "implementation": platform.python_implementation()}


def rerun_command(arms_path: str = "<selected_arms.json>",
                  out_path: str = "gbm_context_handoff.json",
                  depmap_handoff: str = "<optional depmap_dependency_handoff.json>") -> str:
    return (f"python -m druglink.gbm_context.run_gbm_context "
            f"--arms {arms_path} --out {out_path} --live-open-targets "
            f"[--depmap-handoff {depmap_handoff}]")


def run_provenance(*, run_timestamp_utc: str, code_sha256: str, n_genes: int,
                   ot_evaluated: bool, depmap_evaluated: bool) -> dict[str, Any]:
    return {
        "run_timestamp_utc": run_timestamp_utc,
        "code_sha256": code_sha256,
        "env": env_fingerprint(),
        "rerun_command": rerun_command(),
        "sources": SOURCES,
        "tissue_organ_axis": TISSUE_ORGAN_AXIS,
        "n_genes": n_genes,
        "populated_vs_missing": {
            "immune_direction_stage2_arm": "populated",
            "disease_association_open_targets": "populated" if ot_evaluated
            else "not_evaluated",
            "tumor_dependency_depmap": "populated" if depmap_evaluated
            else "not_evaluated",
        },
    }
