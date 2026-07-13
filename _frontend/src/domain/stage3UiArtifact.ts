// Stage-3 (Drugs) browser projection model — spot.stage03_drug_annotation.v1 workflow states.
//
// This is the BROWSER-SAFE projection the Drugs route renders. It preserves the native workflow-state
// fields (handoff §7) WITHOUT manufacturing the deprecated `gbm_context`, `directness`, or a scalar
// `mechanism_direction`. Every scientific value is carried verbatim from the native artifact; a value
// the native artifact does not supply stays `null` (typed-missing → em-dash in the UI), never inferred.
//
// The Drugs route must bind a candidate bundle to the active Stage-2 run (`upstream_stage2_run`); a
// bundle from another run is refused, not shown as generic drug data.

export const STAGE3_UI_ARTIFACT_SCHEMA = 'spot.stage03_drug_annotation.v1' as const;

/** One Stage-3 candidate, preserving native workflow states (join optional detail tables by ID). */
export interface Stage3Candidate {
  candidate_id: string;
  active_moiety_id: string | null;
  preferred_name: string | null;
  identity_status: string | null;
  form_ids: string[];
  target_ensembls: string[];
  n_edges: number | null;
  n_direct_gene_edges: number | null;
  development_state_aggregate: string | null;
  n_potency_rows: number | null;
  potency_state: string | null;
  observed_perturbation_arms: string[];
  inverse_direction_support: string | null;
  pathway_hypothesis_arms: string[];
  stage3_evidence_classes: string[];
  disease_context_review_status: string | null;
  disease_context_review_result: string | null;
  stage4_assessment_status: string | null;
  source_record_ids: string[];
}

export interface Stage3UiArtifact {
  schema_version: typeof STAGE3_UI_ARTIFACT_SCHEMA;
  bundle_id: string;
  manifest_sha256: string;
  /** The admitted Stage-2 run this candidate bundle descends from (immutable id; cross-run → refuse). */
  upstream_stage2_run: string;
  candidates: Stage3Candidate[];
}
