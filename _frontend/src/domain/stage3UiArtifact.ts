// Stage-3 (Drugs) browser projection model derived from spot.stage03_drug_annotation.v2.
//
// This is the BROWSER-SAFE projection the Drugs route renders. It preserves the native workflow-state
// fields (handoff §7) WITHOUT manufacturing the deprecated `gbm_context`, `directness`, or a scalar
// `mechanism_direction`. Every scientific value is carried verbatim from the native artifact; a value
// the native artifact does not supply stays `null` (typed-missing → em-dash in the UI), never inferred.
//
// The Drugs route must bind a candidate bundle to the active Stage-2 run (`upstream_stage2_run`); a
// bundle from another run is refused, not shown as generic drug data.

export const STAGE3_UI_ARTIFACT_SCHEMA = 'spot.ui.stage03_candidates.v2' as const;
export const STAGE3_NATIVE_ARTIFACT_SCHEMA = 'spot.stage03_drug_annotation.v2' as const;

/** One Stage-3 candidate, preserving native workflow states (join optional detail tables by ID). */
export interface Stage3Candidate {
  candidate_id: string;
  active_moiety_id: string | null;
  preferred_name: string | null;
  identity_status: string | null;
  molecule_chembl_ids: string[];
  target_ensembls: string[];
  n_edges: number | null;
  n_direct_gene_edges: number | null;
  max_phase_status: string | null;
  max_phase_sources: string[];
  observed_perturbation_arms: string[];
  observed_perturbation_support: boolean;
  mechanism_match_statuses: string[];
  pathway_hypothesis_arms: string[];
  stage3_evidence_classes: string[];
  stage4_assessment_status: string | null;
  stage4_assessment_reason: string | null;
  source_record_ids: string[];
}

export interface Stage3UiArtifact {
  schema_version: typeof STAGE3_UI_ARTIFACT_SCHEMA;
  native_schema_version: typeof STAGE3_NATIVE_ARTIFACT_SCHEMA;
  artifact_class: 'analysis';
  bundle_id: string;
  canonical_content_sha256: string;
  /** The admitted Stage-2 run this candidate bundle descends from (immutable id; cross-run → refuse). */
  upstream_stage2_run: string;
  candidates: Stage3Candidate[];
}
