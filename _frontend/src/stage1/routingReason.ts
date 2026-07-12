// v3 selection routing → a compact TYPED inline reason for the "ID program skew genes"
// control. Mirrors spot.stage01_selection.v3 execution_status/routing so the Programs
// page never silently greys the button: it shows WHY it isn't executable. The Programs
// page (hand-written) mirrors this exact logic inline; this module is the tested source.

export type ExecStatus = 'ready' | 'refused' | 'awaiting_estimator' | 'incomplete';

export interface RoutingInput {
  aProgram: string | null;
  bProgram: string | null;
  aDirection: 'high' | 'low';
  bDirection: 'high' | 'low';
  /** effect_projection_status === 'available' for each pole (within-condition). */
  aAvailable: boolean;
  bAvailable: boolean;
  /** 'Rest' | 'Stim8hr' | 'Stim48hr' | 'All' (All = pooled, display-only). */
  conditionA: string;
  conditionB: string;
}

export interface Routing {
  analysis_mode: 'within_condition' | 'temporal_cross_condition' | null;
  execution_status: ExecStatus;
  executable: boolean;
  /** Compact typed reason; '' when ready. */
  reason: string;
  reason_code?: string;
}

export const TEMPORAL_AWAITING_REASON =
  'Cross-condition (temporal) analysis awaits the temporal estimator — pick the same condition for both programs to run within-condition.';
export const POOLED_ALL_REASON =
  'Pick a concrete timepoint (Rest / Stim8hr / Stim48hr) — pooled “All” is display-only.';
export const IDENTICAL_REASON =
  'From and To are identical — pick distinct programs or opposite directions.';

/** Reason for an effect-unavailable pole (default panel_below; the frozen Th9 case). */
export function poleUnavailableReason(label: string, code = 'panel_below_effect_universe_min'): string {
  return `${label} has no panel genes in the effect universe (${code}).`;
}

export function deriveRouting(s: RoutingInput): Routing {
  if (!s.aProgram || !s.bProgram) {
    return { analysis_mode: null, execution_status: 'incomplete', executable: false, reason: '' };
  }
  // Objective incompatible: same pole (same program + same direction).
  if (s.aProgram === s.bProgram && s.aDirection === s.bDirection) {
    return {
      analysis_mode: null, execution_status: 'refused', executable: false,
      reason: IDENTICAL_REASON, reason_code: 'objective_incompatible_same_pole',
    };
  }
  // Pooled 'All' is display-only — a within-condition run needs one concrete timepoint.
  if (s.conditionA === 'All' || s.conditionB === 'All') {
    return {
      analysis_mode: null, execution_status: 'refused', executable: false,
      reason: POOLED_ALL_REASON, reason_code: 'invalid_condition_count',
    };
  }
  // Cross-condition ⇒ temporal ⇒ awaiting_estimator (never ready).
  if (s.conditionA !== s.conditionB) {
    return {
      analysis_mode: 'temporal_cross_condition', execution_status: 'awaiting_estimator',
      executable: false, reason: TEMPORAL_AWAITING_REASON,
    };
  }
  // Within-condition: an effect-unavailable pole ⇒ refused (typed reason_code).
  if (!s.aAvailable) {
    return {
      analysis_mode: 'within_condition', execution_status: 'refused', executable: false,
      reason: poleUnavailableReason('Program A'), reason_code: 'panel_below_effect_universe_min',
    };
  }
  if (!s.bAvailable) {
    return {
      analysis_mode: 'within_condition', execution_status: 'refused', executable: false,
      reason: poleUnavailableReason('Program B'), reason_code: 'panel_below_effect_universe_min',
    };
  }
  // Within-condition + both poles available ⇒ ready.
  return { analysis_mode: 'within_condition', execution_status: 'ready', executable: true, reason: '' };
}
