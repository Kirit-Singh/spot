# 02_geneskew — perturbation targets and pathway context

Stage 2 consumes a generic Stage-1 v3 selection: two ordered continuous programs, their desired
directions, and either one shared condition or two temporal endpoints. It projects each measured
CRISPRi knockdown onto the two program scorers and keeps the resulting arms separate. There is no
combined, balanced or weighted objective.

The direct lane uses the authors' released `GWCD4i.DE_stats` effect estimates with the target,
30-kb neighbouring genes and contributing-guide off-target alignments masked from each projection.
The temporal lane compares perturbation effects between two population-level endpoints; it is not
lineage tracing. GO Biological Process provides pathway context. Reactome is parked in the current
release, and Perturb2State remains deferred rather than presented as a completed primary lane.

**Produces:** ranked, suggestive target hypotheses, temporal endpoint comparisons and GO-BP
context. These are not validated targets or causal mechanisms. Displayed outputs contain no
calibrated p-values, q-values or FDR, and pathway convergence requires support from at least two
in-pathway perturbations.

- `inputs/` — Stage-1 v3 selection contracts plus the public Marson target-level release
- `analysis/` — direct projections, temporal estimators, Pareto status, masks, pathway analysis
  and independent verifiers
- `outputs/` — content-addressed `screen.parquet`, `temporal.parquet`, `pathway.json` and their
  provenance / verification records (generated outputs are not committed wholesale)

Detailed design decisions, historical amendments and schemas remain in `STAGE2_PLAN.md` and the
review documents in this directory.
