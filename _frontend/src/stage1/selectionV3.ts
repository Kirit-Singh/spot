// spot.stage01_selection.v3 verifier. JSON-Schema validity is NOT sufficient: this
// INDEPENDENTLY recomputes selection_id / selection_full_sha256 / full_contract_content_sha256
// and re-derives the routing decision from the poles + mode, rejecting any artifact whose
// declared execution_status disagrees. Enforces every mismatch the contract calls out:
// temporal-labeled-ready, estimator/mode mismatch, top-level-vs-canonical mode mismatch,
// pole-identity mismatch, condition-count, effect-unavailable, and an untrue active_gate.

import { canonicalJson, sha256Hex } from './canonical';

export const EXECUTION_STATUS = ['ready', 'refused', 'awaiting_estimator'] as const;
export const ESTIMATOR_STATUS = ['available', 'not_implemented'] as const;
export const ANALYSIS_MODE = ['within_condition', 'temporal_cross_condition'] as const;
export const EFFECT_PROJECTION_STATUS = ['available', 'unavailable'] as const;
export const ESTIMATOR_ID = ['within_condition_v1', 'temporal_cross_condition_v1'] as const;
export const CONDITIONS = ['Rest', 'Stim8hr', 'Stim48hr'] as const;

export type ExecutionStatus = (typeof EXECUTION_STATUS)[number];
export type AnalysisMode = (typeof ANALYSIS_MODE)[number];
export type EffectProjectionStatus = (typeof EFFECT_PROJECTION_STATUS)[number];

export type SelectionErrorCode =
  | 'bad_schema_version'
  | 'malformed'
  | 'bad_enum'
  | 'selection_id_mismatch'
  | 'selection_full_sha_mismatch'
  | 'full_contract_sha_mismatch'
  | 'mode_mismatch'
  | 'estimator_mode_mismatch'
  | 'pole_identity_mismatch'
  | 'invalid_condition_count'
  | 'temporal_labeled_ready'
  | 'execution_status_mismatch'
  | 'active_gate_true';

export class SelectionError extends Error {
  readonly code: SelectionErrorCode;
  constructor(code: SelectionErrorCode, message: string) {
    super(message);
    this.name = 'SelectionError';
    this.code = code;
  }
}
function fail(code: SelectionErrorCode, message: string): never {
  throw new SelectionError(code, message);
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}
function str(v: unknown, path: string): string {
  if (typeof v !== 'string') fail('malformed', `${path} must be a string`);
  return v as string;
}
function enumOf<T extends string>(v: unknown, allowed: readonly T[], path: string): T {
  const s = str(v, path);
  if (!(allowed as readonly string[]).includes(s)) fail('bad_enum', `${path} "${s}" not in ${allowed.join('|')}`);
  return s as T;
}

export interface VerifiedSelectionV3 {
  selection_id: string;
  execution_status: ExecutionStatus;
  analysis_mode: AnalysisMode;
  raw: Record<string, unknown>;
  /** The routing decision the UI re-derived (must equal the declared execution_status). */
  derived_execution_status: ExecutionStatus;
}

/** Pure routing derivation from mode + poles — the UI's own decision, per the contract rules. */
export function deriveExecutionStatus(
  mode: AnalysisMode,
  poleAStatus: EffectProjectionStatus,
  poleBStatus: EffectProjectionStatus,
): ExecutionStatus {
  if (mode === 'temporal_cross_condition') return 'awaiting_estimator';
  // within_condition: refused if either pole's effect projection is unavailable, else ready.
  if (poleAStatus === 'unavailable' || poleBStatus === 'unavailable') return 'refused';
  return 'ready';
}

/**
 * Verify a selection.v3 artifact. Throws {@link SelectionError} on any violation;
 * returns the verified summary on success.
 */
export async function verifySelectionV3(input: unknown): Promise<VerifiedSelectionV3> {
  if (!isObject(input)) throw new SelectionError('malformed', 'selection must be an object');
  const raw: Record<string, unknown> = input;
  if (raw.schema_version !== 'spot.stage01_selection.v3') {
    fail('bad_schema_version', `schema_version "${String(raw.schema_version)}" != spot.stage01_selection.v3`);
  }

  const execution_status = enumOf(raw.execution_status, EXECUTION_STATUS, 'execution_status');
  const analysis_mode = enumOf(raw.analysis_mode, ANALYSIS_MODE, 'analysis_mode');
  const estimator_id = enumOf(raw.estimator_id, ESTIMATOR_ID, 'estimator_id');
  const estimator_status = enumOf(raw.estimator_status, ESTIMATOR_STATUS, 'estimator_status');
  const selection_id = str(raw.selection_id, 'selection_id');
  const selection_full = str(raw.selection_full_sha256, 'selection_full_sha256');
  const full_contract = str(raw.full_contract_content_sha256, 'full_contract_content_sha256');

  const cc = raw.canonical_content;
  if (!isObject(cc)) fail('malformed', 'canonical_content must be an object');
  const poles = raw.poles;
  if (!isObject(poles) || !isObject(poles.A) || !isObject(poles.B)) fail('malformed', 'poles.A/B required');
  const pA = poles.A as Record<string, unknown>;
  const pB = poles.B as Record<string, unknown>;

  // ── independent hash recompute (never trust the artifact's own hash fields) ──
  const ccFull = await sha256Hex(canonicalJson(cc));
  if (ccFull !== selection_full) fail('selection_full_sha_mismatch', 'recomputed selection_full_sha256 mismatch');
  if (ccFull.slice(0, 16) !== selection_id) fail('selection_id_mismatch', 'recomputed selection_id mismatch');
  const { full_contract_content_sha256: _omit, ...contractNoHash } = raw;
  void _omit;
  const recomputedContract = await sha256Hex(canonicalJson(contractNoHash));
  if (recomputedContract !== full_contract) fail('full_contract_sha_mismatch', 'recomputed full_contract_content_sha256 mismatch');

  // ── mode / estimator / pole-identity / condition-count consistency ──
  const ccMode = enumOf(cc.analysis_mode, ANALYSIS_MODE, 'canonical_content.analysis_mode');
  if (ccMode !== analysis_mode) fail('mode_mismatch', 'top-level analysis_mode != canonical_content.analysis_mode');

  const expectedEstimator = analysis_mode === 'within_condition' ? 'within_condition_v1' : 'temporal_cross_condition_v1';
  if (estimator_id !== expectedEstimator) fail('estimator_mode_mismatch', `estimator_id ${estimator_id} != ${expectedEstimator}`);
  const expectedEstimatorStatus = analysis_mode === 'within_condition' ? 'available' : 'not_implemented';
  if (estimator_status !== expectedEstimatorStatus) {
    fail('estimator_mode_mismatch', `estimator_status ${estimator_status} != ${expectedEstimatorStatus} for ${analysis_mode}`);
  }

  const ccA = cc.A as Record<string, unknown>;
  const ccB = cc.B as Record<string, unknown>;
  if (str(pA.program_id, 'poles.A.program_id') !== str(ccA?.program_id, 'canonical_content.A.program_id') ||
      str(pA.direction, 'poles.A.direction') !== str(ccA?.direction, 'canonical_content.A.direction')) {
    fail('pole_identity_mismatch', 'poles.A identity != canonical_content.A');
  }
  if (str(pB.program_id, 'poles.B.program_id') !== str(ccB?.program_id, 'canonical_content.B.program_id') ||
      str(pB.direction, 'poles.B.direction') !== str(ccB?.direction, 'canonical_content.B.direction')) {
    fail('pole_identity_mismatch', 'poles.B identity != canonical_content.B');
  }

  const conditions = Array.isArray(cc.conditions) ? cc.conditions : fail('malformed', 'conditions must be an array');
  const wantConditions = analysis_mode === 'within_condition' ? 1 : 2;
  if (conditions.length !== wantConditions) {
    fail('invalid_condition_count', `${analysis_mode} requires ${wantConditions} condition(s), got ${conditions.length}`);
  }

  // ── re-derive routing and enforce it against the declared status ──
  const aStatus = enumOf(pA.effect_projection_status, EFFECT_PROJECTION_STATUS, 'poles.A.effect_projection_status');
  const bStatus = enumOf(pB.effect_projection_status, EFFECT_PROJECTION_STATUS, 'poles.B.effect_projection_status');
  const derived = deriveExecutionStatus(analysis_mode, aStatus, bStatus);

  if (analysis_mode === 'temporal_cross_condition' && execution_status === 'ready') {
    fail('temporal_labeled_ready', 'temporal_cross_condition can never be ready');
  }
  if (execution_status !== derived) {
    fail('execution_status_mismatch', `declared ${execution_status} != re-derived ${derived}`);
  }

  const hvp = raw.historical_validation_provenance;
  if (!isObject(hvp) || hvp.active_gate !== false) {
    fail('active_gate_true', 'historical_validation_provenance.active_gate must be false');
  }

  return { selection_id, execution_status, analysis_mode, raw, derived_execution_status: derived };
}
