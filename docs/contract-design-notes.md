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

## Revision 2 (post adversarial review, 2026-07-07)
Hardened after a Fable adversarial review. Blocking fixes: (B1) precise subject
identity (id_type, taxon_id, version-stripped join_key, unmapped=>symbol);
(B2) controlled context axis keys (core enum + x_ extensions); (B3) direction
reconciled to the measurement (single source of truth); (B4) controlled Metric
vocab (+OTHER companion) so incomparable metrics aren't compared; (B5)
corroborating_hit_ids linking replication evidence to what confirmed it. Plus:
p-value provenance, n_type, verdict<->direction_agreement invariants, untested=>
weight 0, dataset_id de-duplicated into provenance, upstream_accession, controlled
CheckName, hit_content_hash. Two deliberate deviations from the review: require
corroborating only for `replication` (consistency's counterpart is a query/stat
in provenance), and no "all-checks-passed => not contradicted" rule (a genuine
opposite-direction effect can pass all QC).

## Revision 3 (executed review by Claude Science + Fable adjudication, 2026-07-07)
Claude Science EXECUTED forbidden-edge construction against the real package and
validated against the real Marson CSV columns (via CLI: suppl_tables in
`.scratch/`; the big h5ad/h5mu are truncated mid-download). It proved holes the
read-throughs missed; Fable then adjudicated the fixes against the contract-vs-Lane-A
boundary. Applied to the contract (all intra-object / intra-aggregate):
- **Firewall by source, not label:** agent_type=computational_model OR
  knowledge_level=prediction (OR evidence_type=predictive) cannot be replication/
  consistency and cannot be verdict=confirmed (closes the relabel bypass).
- **`confirmed` requires passed gate Checks** (metric_match + direction_reconciled;
  + independence for replication) -> a confirmed edge is impossible without the
  gates, without denormalizing the hit. Lane A computes the checks.
- Self-corroboration guard (hit_id not in corroborating_hit_ids); absolute
  predictive weight cap (<= 0.5); `extra="forbid"` everywhere; schema_version
  check; `Evidence.context`; optional `Measurement.significant`; perturbation
  subjects require perturbation_type; `CheckName.OFFTARGET/METRIC_MATCH/
  DIRECTION_RECONCILED`; optional `Provenance.license`.
Pushed to Lane A (documented, NOT contract): cross-hit dataset independence
(needs other hits' datasets), relative predictive-vs-replication weight ordering,
`ontarget_effect_size -> Metric.OTHER` ingestion mapping (real range -58.5..+7.09,
median -6.3 -> NOT log2fc), context_match verdict. Rejected: dataset-independence
on consistency (same-dataset by design; Science was wrong), required FDR check (no
p-value column exists), hit_content_hash-required (redundant if Evidence stays
under the hit aggregate). Full artifact: Claude Science `contract_review.md`.
