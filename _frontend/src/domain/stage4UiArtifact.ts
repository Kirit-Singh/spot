// Stage-4 (PK & Safety) browser projection model — the native, nested projection emitted by
// 04_PKPD/analysis/projection.py.  The nested evidence documents are deliberately preserved: a
// null is a typed "not evaluated" value, not zero/negative, and no lane is collapsed into a score.

export const STAGE4_UI_ARTIFACT_SCHEMA = 'spot.stage04_browser_projection.v1' as const;

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };
export interface JsonObject { [key: string]: JsonValue }

export const STAGE4_LANE_KEYS = [
  'delivery',
  'cns_mpo',
  'transporters',
  'exposure',
  'nebpi',
  'safety',
  'potency',
  'evidence_availability',
] as const;
export type Stage4LaneKey = (typeof STAGE4_LANE_KEYS)[number];
export type Stage4Lanes = Record<Stage4LaneKey, JsonValue>;

export interface Stage4ProductionEligibility extends JsonObject {
  eligible: boolean;
  reason_code: string | null;
}

export interface Stage4Candidate {
  candidate_id: string;
  active_moiety: JsonObject | null;
  compound_ids: JsonObject;
  target: string | null;
  mechanism: string | null;
  direction_compatibility: string | null;
  production_eligible: Stage4ProductionEligibility;
  lanes: Stage4Lanes;
  provenance_chain: JsonValue[];
  stage3_arm_membership: JsonObject;
  in_active_view: boolean | null;
}

export interface Stage4UiArtifact {
  schema_version: typeof STAGE4_UI_ARTIFACT_SCHEMA;
  scorecard_set_id: string;
  /** Immutable Stage-3 candidate-set/bundle identity carried by native `upstream.candidate_set_id`. */
  upstream_stage3_bundle: string;
  upstream: JsonObject;
  store_is_selection_independent: true;
  is_ranking: false;
  ordering: JsonValue;
  guards: JsonValue;
  active_selection_view: JsonObject | null;
  active_view_candidate_ids: string[];
  candidates: Stage4Candidate[];
}
