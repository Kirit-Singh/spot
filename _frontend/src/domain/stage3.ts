// Stage-3 — direction-compatible drug linkage (UI shape of spot.stage03_drug_candidate_set.v1).
//
// Begins from a selected gene/pathway lever and keeps BOTH desired-arm directions
// visible. No single best-evidence collapse — mixed / conflicting / not-evaluated
// states stay visible. Research-only and fixture candidates can be inspected but
// cannot be promoted (no production pointer).

import type { Provenance } from './common';
import type { Objective } from './stage2';

/** Whether a mechanism direction is compatible with the desired program arm. */
export type DirectionCompat = 'compatible' | 'incompatible' | 'not_evaluated';

/** Whether the drug acts directly on the target entity. */
export type Directness = 'direct' | 'indirect' | 'not_evaluated';

/** Where the candidate came from: a direct Stage-2 target, or a convergent pathway node. */
export type CandidateOrigin = 'direct_target' | 'pathway_node';

export const CANDIDATE_ORIGINS: readonly CandidateOrigin[] = ['direct_target', 'pathway_node'];

/** Direction the mechanism moves the target's activity (verbatim intent, not inferred). */
export type MechanismDirection = 'up' | 'down' | 'not_evaluated';

/** Evidence state for GBM-context activity (kept suggestive, never confirmatory). */
export type EvidenceState = 'measured' | 'conflicting' | 'mixed' | 'not_evaluated' | 'missing';

export interface AdministeredForm {
  form_id: string;
  /** Relation of this form to the active moiety, verbatim (e.g. "salt_of", "prodrug_of"). */
  relation: string;
  route: string | null;
}

export interface TargetEntity {
  entity_id: string;
  /** e.g. "gene", "protein", "complex". */
  entity_type: string;
  label: string;
}

/** A potency record kept with its ORIGINAL relation + unit — never altered/normalized. */
export interface PotencyRecord {
  /** Verbatim relation, e.g. "=", ">", "<". */
  relation: string;
  value: number | null;
  /** Verbatim unit, e.g. "nM"; null only when the source omits it. */
  unit: string | null;
  assay: string;
  source: { label: string; record_id: string; url: string | null };
}

export interface SourceConflict {
  field: string;
  /** Verbatim conflicting values from distinct sources. */
  values: { source: string; value: string }[];
}

export interface DrugCandidate {
  candidate_id: string;
  active_moiety: string;
  forms: AdministeredForm[];
  /** Mechanism action type, e.g. "INHIBITOR", "AGONIST"; verbatim. */
  mechanism_action: string;
  /** Whether the candidate came from a direct Stage-2 target or a convergent pathway node. */
  origin: CandidateOrigin;
  /** The pathway node id when origin === 'pathway_node'; null for direct targets. */
  pathway_node: string | null;
  /** Direction the mechanism moves the target's activity (traced, never inferred). */
  mechanism_direction: MechanismDirection;
  target_entity: TargetEntity;
  /** Gene lever this candidate was linked from. */
  source_lever_gene_id: string;
  /** The EXACT supporting program arm — traced from Stage 2, never inferred from joint ordering. */
  desired_arm: Objective;
  direction_compatibility: DirectionCompat;
  directness: Directness;
  potency_records: PotencyRecord[];
  gbm_context: EvidenceState;
  source_conflicts: SourceConflict[];
  provenance: Provenance;
}

export interface Stage3Artifact {
  provenance: Provenance;
  /** Both desired-arm directions carried from Stage 2. */
  desired_arms: Objective[];
  candidates: DrugCandidate[];
}
