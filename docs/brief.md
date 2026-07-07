# spot — Project Brief

## Product
A cross-dataset evidence graph: take a hit discovered in one dataset and confirm or refute it in independent public datasets, rendered as an interactive graph connecting datasets across **target · cell type · disease · population · context · modality**. Biology's missing layer is cross-dataset replication — spot carries a finding across datasets and shows it holding up (or not).

Narrative: analyze the CD4+ T cell genome-scale Perturb-seq screen → surface a hit (a perturbation shifting cells toward a T-cell program of interest, immunotherapy lens) → find context-matched public datasets → run an actual confirmation in a distinct dataset (a real query on real statistics) → show it on a graph where each dataset lights up **confirmed / untested / contradicted** and each edge is **typed by evidence kind and weighted by strength**.

## Data (public, MIT)
Primary: Human CD4+ T Cell Perturb-seq (Zhu, Dann, Pritchard, Marson et al., bioRxiv 2025). CRISPRi, genome-scale. 22M cells · 4 donors · 3 contexts (Rest / Stim8hr / Stim48hr) · ~18,129 genes (10,282 in DE) · 33,983 perturbation-condition pairs.
Path (NAS): see `infra.env` → `SPOT_DATASET_DIR`. Treat the precomputed deterministic files as ground truth: `GWCD4i.pseudobulk_merged.h5ad`; `GWCD4i.DE_stats.h5ad` / `.by_guide.h5mu` / `.by_donors.h5mu`; `suppl_tables/*.csv`; `D{1-4}_{Rest,Stim8hr,Stim48hr}.assigned_guide.h5ad` (cell-level, large — QC/volcano only).
Reference only, do NOT copy: `github.com/emdann/GWT_perturbseq_analysis_2025`.

## Architecture — two tiers (Lane A)
- **Tier 1 — harmonized backbone (demo spine):** CZ CELLxGENE Census (ontology-harmonized independent single-cell) + Open Targets (human-genetic / disease support).
- **Tier 2 — agentic long-tail adapter:** given a GEO accession, read metadata, infer format, write a bespoke parser on the fly, harmonize to ontology, run the confirmation, grade it.

## Evidence model
Never invent statistics — every number from deterministic tools (scanpy / pyDESeq2 / decoupler / Census). Type every edge: **replication · consistency · genetic** (· **predictive/model** for Lane B). Weight by strength. Never present consistency as replication. Adversarially try to kill each hit before it earns an edge (donor consistency · context specificity · guide-efficiency confounder · effect vs noise).

## Two lanes
- **Lane A — Evidence Graph** (this brief's core).
- **Lane B — Predictive Modeling:** training loops (DGX Sparks) to identify perturbation hot spots / favorable transcription pathways, with **Claude Science** for reasoning; emits candidate Hits into the shared `contracts/` seam. See spec §12–13.

## Constraints
Public data + MIT only. Reproducible from public sources + this repo. Build one gorgeous vertical thread end-to-end; the architecture is the argument for generality.

## Definition of done (demo)
A user with no bioinformatics points at a hit; spot confirms it in ≥2 independent public datasets with typed + weighted edges; the graph lights up live; every claim is click-through to the real statistic and the code that produced it.
