// Stage-4 (PK & Safety) browser projection model — the native scorecards document (handoff §8).
//
// Preserves the six INDEPENDENT evidence lanes (delivery, CNS-MPO, transporters, exposure, NEBPI,
// safety) as typed states rather than flattening them. A missing / not-evaluated value stays
// `null` (typed-missing) — it must NEVER become zero, `safe`, `brain penetrant`, or any inferred
// negative result. NEBPI keeps its context specificity (not collapsed to a drug-wide class). No
// combined / balanced / weighted PK or safety score is introduced.
//
// The scorecard set must descend from the currently admitted Stage-3 bundle by immutable
// `upstream_stage3_bundle` id; a cross-bundle set is refused.

export const STAGE4_UI_ARTIFACT_SCHEMA = 'spot.stage04_scorecards.v1' as const;

/** A native lane evidence state string, or null when the lane was not evaluated (typed-missing). */
export type Stage4LaneState = string | null;

export interface Stage4Lanes {
  delivery: Stage4LaneState;
  cns_mpo: Stage4LaneState;
  transporters: Stage4LaneState;
  exposure: Stage4LaneState;
  nebpi: Stage4LaneState;
  safety: Stage4LaneState;
}

export const STAGE4_LANE_KEYS: readonly (keyof Stage4Lanes)[] = [
  'delivery',
  'cns_mpo',
  'transporters',
  'exposure',
  'nebpi',
  'safety',
];

export interface Stage4Candidate {
  candidate_id: string;
  active_moiety: string | null;
  compound_ids: string[];
  target: string | null;
  mechanism: string | null;
  /** Native production-eligibility verdict; null = not evaluated (never coerced to false). */
  production_eligible: boolean | null;
  production_eligible_reason: string | null;
  lanes: Stage4Lanes;
}

export interface Stage4UiArtifact {
  schema_version: typeof STAGE4_UI_ARTIFACT_SCHEMA;
  scorecard_set_id: string;
  stage4_method_version: string;
  /** Immutable Stage-3 bundle id this scorecard set descends from (cross-bundle → refuse). */
  upstream_stage3_bundle: string;
  candidates: Stage4Candidate[];
}
