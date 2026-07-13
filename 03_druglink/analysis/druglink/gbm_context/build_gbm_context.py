"""Assemble the Stage-3 v2 GBM disease-context handoff from selected Stage-2 arms.

For each gene (joined on its Ensembl id, NEVER a symbol) this builds a record with three
SEPARATE descriptive axes — immune (per arm), tumor-cell dependency (gene-level, DepMap),
disease association (gene-level, Open Targets) — plus a per-immune-direction, SUGGESTIVE
compatibility state. The handoff is descriptive and NON-GATING: it carries no rank, no
score, no p/q, and it never reorders or alters any Stage-2 output. W16 merges it into the
Stage-3 v2 candidates by ``target_ensembl``.
"""
from __future__ import annotations

from typing import Any, Optional

from . import GbmContextError, CLASSIFICATION
from . import states as st
from . import depmap_bridge as db

HANDOFF_ID = "spot.stage03.gbm_context.v1"


def _immune_axis(arm_rows: list[dict[str, Any]]) -> dict[str, Any]:
    arms, directions = [], []
    for r in arm_rows:
        d = st.immune_direction(r.get("desired_change"))
        arms.append({"arm_key": r.get("arm_key"), "program_id": r.get("program_id"),
                     "desired_change": r.get("desired_change"),
                     "desired_perturbation_direction": d})
        if d not in directions:
            directions.append(d)
    return {"source": "stage2_arm", "arms": arms, "directions": directions}


def build_gene_record(ensembl_id: str, symbol: Optional[str],
                      arm_rows: list[dict[str, Any]], *,
                      ot_result: Optional[dict[str, Any]],
                      dep_metrics: Optional[dict[str, Any]]) -> dict[str, Any]:
    """One gene's record: immune (per arm), tumor + disease (gene-level), compatibility
    (per distinct immune direction). Axes never fuse into a single score."""
    immune = _immune_axis(arm_rows)
    tumor = st.tumor_dependency_state(dep_metrics)
    disease = st.disease_association_state(ot_result)
    compatibility = {d: st.compatibility(d, tumor) for d in immune["directions"]}
    return {"target_ensembl": ensembl_id, "target_symbol": symbol,
            "immune_axis": immune, "tumor_axis": tumor,
            "disease_axis": disease, "compatibility": compatibility}


def build_handoff(arm_rows: list[dict[str, Any]], *,
                  ot_by_gene: dict[str, Any],
                  dep_handoff: Optional[dict[str, Any]],
                  sources: Optional[dict[str, Any]] = None,
                  tissue_organ_axis: Optional[dict[str, Any]] = None,
                  raw_response_artifacts: Optional[dict[str, Any]] = None,
                  run_provenance: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Group arm rows by Ensembl id and emit the descriptive, non-gating handoff.

    A row lacking a stable Ensembl id is refused — this layer never joins on a symbol.
    ``ot_by_gene`` maps ``ensembl -> parsed OT result``; ``dep_handoff`` is the optional
    DepMap dependency handoff (validated here)."""
    loaded_dep = db.load_dependency_handoff(dep_handoff)
    by_gene: dict[str, list[dict[str, Any]]] = {}
    symbols: dict[str, Any] = {}
    order: list[str] = []
    for r in arm_rows:
        ens = r.get("target_ensembl")
        if not ens:
            raise GbmContextError(
                f"arm row {r.get('arm_key')!r} has no target_ensembl — this layer joins "
                "on stable gene identity only, never a symbol.")
        if ens not in by_gene:
            by_gene[ens] = []
            order.append(ens)
        by_gene[ens].append(r)
        symbols.setdefault(ens, r.get("target_symbol"))

    genes: dict[str, Any] = {}
    for ens in order:
        genes[ens] = build_gene_record(
            ens, symbols.get(ens), by_gene[ens],
            ot_result=ot_by_gene.get(ens),
            dep_metrics=db.gene_metrics(loaded_dep, ens))

    return {
        "handoff_id": HANDOFF_ID,
        "classification": CLASSIFICATION,
        "never_alters_ranks": True,
        "suggestive_only": True,
        "no_pq_no_overall_rank": True,
        "join_key": "target_ensembl",
        "merge_note": ("W16 merges each gene into the Stage-3 v2 candidates by "
                       "target_ensembl; immune-cell effect and tumor-cell context stay "
                       "separate; missing evidence is not_evaluated."),
        "n_genes": len(genes),
        "sources": sources or {},
        "tissue_organ_axis": tissue_organ_axis or {},
        "depmap_release_provenance": db.release_provenance(loaded_dep),
        "raw_response_artifacts": raw_response_artifacts or {},
        "genes": genes,
        "run_provenance": run_provenance or {}}
