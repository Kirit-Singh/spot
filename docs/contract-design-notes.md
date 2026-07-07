# Contract design notes (Hit / Evidence)

Prior-art research (2026-07-07) behind the `spot_contracts` schema, plus the
methodology guidance that shapes Lane A confirmation and Lane B modeling.

## Guiding decision
Keep the contract **data-type-agnostic**: single-cell / genetic / bulk specifics
live in *values* (ontology ids, metric names, context axes), never in the
structure. Core fields now; richer fields are documented extension points.

## Prior art
- **Open Targets** (target-disease evidence): flat "source-agnostic core + typed
  nullable extras"; two-level typing (datatype -> datasource); harmonic-sum
  scoring with per-source weights (0-1); score = evidence availability, not
  calibrated truth. Gap: stores only positive evidence -> we add an explicit
  `verdict`. https://platform-docs.opentargets.org/evidence
- **Biolink / ECO** (KG standards): reified edges with `negated`, direction
  qualifiers (increased/decreased), `knowledge_level`, `agent_type`
  (computational_model...), ECO evidence codes, InfoRes primary/aggregator
  provenance. No standard confirmed/contradicted verdict -> our addition;
  keep verdict orthogonal to negated. https://biolink.github.io/biolink-model/
- **scPerturb / scanpy / CELLxGENE Census**: perturbation fields
  (perturbation_type, target, guide_id, nperts); Census obs axes as label +
  `*_ontology_term_id` (CL/MONDO/UBERON/HANCESTRO); effect as a method-tagged
  triple (metric/value/direction/pval_adj), not a bare float.
  https://www.nature.com/articles/s41592-023-02144-y

## Methodology guardrails (Fable consult; standard, public-data methodology)
- Join on **pinned Ensembl gene ids** + **pinned ontology CURIEs**; record
  build versions. Never join on symbols. `mapping_confidence` on every subject.
- Confirm only within a **matched context tuple** across **independent
  donors/accessions**, on **sign + FDR** with units/log-space reconciled.
- Keep **underpowered (inconclusive) separate from contradicted**; stim-only
  effects are **context_specific**, not contradicted.
- Every gate is a structured **Check** {name, passed, value, threshold}.
- **Lane B**: pseudobulk per (donor x context x perturbation); leave-donor-out /
  leave-perturbation-out **blocked CV**; held-out **AUPRC / precision@k** beating
  expression- and hub-baselines; predictions typed `predictive` + `untested`
  with capped weight -> may prioritize, never self-confirm (enforced in code).

## Enforced invariants (in models.py)
- Predictive evidence cannot be `verdict=confirmed` (model_validator).
- `weight` bounded 0-1.
- Closed enums for direction / evidence_type / verdict / agent_type so the two
  lanes cannot drift.
