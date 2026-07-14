// Stage-4 — safety & brain exposure (UI shape of spot.stage04_scorecard_set.v1).
//
// Separate panels for human safety/regulatory, measured systemic/unbound exposure,
// measured CNS/tumour evidence, CNS-MPO descriptor support, and the NEBPI decision
// tier/rationale. Measured / calculated / label-derived / not-evaluated / missing are
// distinguished; missing is never coerced to zero. CNS-MPO is a property heuristic,
// never equivalent to clinical brain exposure. No fabricated composite ranking.

import type { Field, Provenance } from './common';

/** Human safety & regulatory evidence. */
export interface SafetyEvidence {
  regulatory_status: Field<string>;
  boxed_warning: Field<string>;
  key_risks: Field<string>;
}

/** What delivery is required to reach the CNS target, and the evidence for it. */
export interface DeliveryEvidence {
  /** e.g. "systemic (oral)", "requires intrathecal / local delivery". */
  requirement: Field<string>;
  /** Supporting evidence for the delivery requirement. */
  supporting_evidence: Field<string>;
}

/** Safety specific to the intended treatment context (not generic label safety). */
export interface TreatmentContextSafety {
  /** The treatment setting, e.g. "adjunct to radiotherapy + temozolomide". */
  setting: Field<string>;
  /** Context-specific concerns, e.g. additive myelosuppression / immunosuppression. */
  concerns: Field<string>;
}

/** Measured systemic / unbound exposure. */
export interface ExposureEvidence {
  systemic_cmax: Field<number>;
  unbound_fraction: Field<number>;
  half_life: Field<number>;
}

/** Measured CNS / tumour evidence. */
export interface CnsEvidence {
  kp_uu: Field<number>;
  csf_concentration: Field<number>;
  tumour_concentration: Field<number>;
}

/** CNS-MPO descriptor support — a property heuristic, never clinical brain exposure. */
export interface CnsMpoSupport {
  clogp: Field<number>;
  clogd: Field<number>;
  tpsa: Field<number>;
  mw: Field<number>;
  hbd: Field<number>;
  pka: Field<number>;
  /** Aggregate descriptor score if the adapter supplies one; explicitly a heuristic. */
  descriptor_score: Field<number>;
}

export type NebpiTier =
  | 'sufficiently_permeable'
  | 'insufficiently_permeable'
  | 'impermeable'
  | 'not_evaluated';

export const NEBPI_TIERS: readonly NebpiTier[] = [
  'sufficiently_permeable',
  'insufficiently_permeable',
  'impermeable',
  'not_evaluated',
];

export interface NebpiStep {
  label: string;
  /** Outcome of this decision-path node, verbatim. */
  outcome: string;
}

export interface NebpiDecision {
  /** NEBPI methodology version (Grossman et al., Neuro-Oncology 2026). */
  version: string;
  tier: NebpiTier;
  rationale: string;
  /** The exact ordered decision path taken. */
  decision_path: NebpiStep[];
}

/** Sort keys the adapter may supply (evidence completeness / tier only — never a composite). */
export type SortKey = 'evidence_completeness' | 'nebpi_tier';

export interface Scorecard {
  scorecard_id: string;
  candidate_id: string;
  active_moiety: string;
  /** Administered form the scorecard applies to. */
  form: string;
  /** What delivery is required to reach the target, with evidence. */
  delivery: DeliveryEvidence;
  safety: SafetyEvidence;
  exposure: ExposureEvidence;
  cns: CnsEvidence;
  cns_mpo: CnsMpoSupport;
  nebpi: NebpiDecision;
  /** Safety in the intended treatment context. */
  treatment_context: TreatmentContextSafety;
  provenance: Provenance;
}

export interface Stage4Artifact {
  provenance: Provenance;
  /** Explicit sort capabilities; empty means no ordering is offered. */
  sortable_by: SortKey[];
  scorecards: Scorecard[];
}
