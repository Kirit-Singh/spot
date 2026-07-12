import { describe, expect, it } from 'vitest';
import { deriveRouting, TEMPORAL_AWAITING_REASON, IDENTICAL_REASON } from '../routingReason';

const base = {
  aProgram: 'treg_like',
  bProgram: 'th1_like',
  aDirection: 'low' as const,
  bDirection: 'high' as const,
  aAvailable: true,
  bAvailable: true,
  conditionA: 'Stim48hr',
  conditionB: 'Stim48hr',
};

describe('selection routing → typed inline reason (button state)', () => {
  it('same-condition, both poles available → ready + button enabled', () => {
    const r = deriveRouting(base);
    expect(r.execution_status).toBe('ready');
    expect(r.executable).toBe(true);
    expect(r.reason).toBe('');
  });

  it('cross-condition → temporal awaiting_estimator + button disabled + temporal reason', () => {
    const r = deriveRouting({ ...base, conditionA: 'Rest', conditionB: 'Stim48hr' });
    expect(r.analysis_mode).toBe('temporal_cross_condition');
    expect(r.execution_status).toBe('awaiting_estimator');
    expect(r.executable).toBe(false);
    expect(r.reason).toBe(TEMPORAL_AWAITING_REASON);
    expect(r.reason).toMatch(/temporal estimator/);
  });

  it('effect-unavailable pole (within-condition) → refused + typed panel reason_code', () => {
    const r = deriveRouting({ ...base, aAvailable: false });
    expect(r.execution_status).toBe('refused');
    expect(r.executable).toBe(false);
    expect(r.reason_code).toBe('panel_below_effect_universe_min');
    expect(r.reason).toMatch(/effect universe/);
  });

  it('same pole + SAME condition → refused + identical (objective_incompatible_same_pole)', () => {
    // same program + same direction + same timepoint = truly identical → unchanged by the fix.
    const r = deriveRouting({
      ...base, bProgram: 'treg_like', bDirection: 'low', conditionA: 'Rest', conditionB: 'Rest',
    });
    expect(r.execution_status).toBe('refused');
    expect(r.executable).toBe(false);
    expect(r.reason_code).toBe('objective_incompatible_same_pole');
    expect(r.reason).toBe(IDENTICAL_REASON);
  });

  it('same program + direction but DIFFERENT condition → temporal cross-condition, not identical (f656d6d)', () => {
    // the bugfix: same program+direction across DIFFERENT timepoints is a temporal comparison,
    // NOT an identical selection — routes to awaiting_estimator (refused → awaiting_estimator).
    const r = deriveRouting({
      ...base, bProgram: 'treg_like', bDirection: 'low', conditionA: 'Rest', conditionB: 'Stim8hr',
    });
    expect(r.reason_code).not.toBe('objective_incompatible_same_pole');
    expect(r.analysis_mode).toBe('temporal_cross_condition');
    expect(r.execution_status).toBe('awaiting_estimator');
    expect(r.executable).toBe(false);
    expect(r.reason).toBe(TEMPORAL_AWAITING_REASON);
  });

  it('pooled All condition → refused (needs a concrete within-condition timepoint)', () => {
    const r = deriveRouting({ ...base, conditionA: 'All', conditionB: 'All' });
    expect(r.execution_status).toBe('refused');
    expect(r.reason_code).toBe('invalid_condition_count');
  });

  it('demo cannot change routing — routing is a pure function of the selection', () => {
    // Identical inputs yield identical routing regardless of any demo flag (there is none here).
    expect(deriveRouting({ ...base, conditionA: 'Rest', conditionB: 'Stim8hr' })).toEqual(
      deriveRouting({ ...base, conditionA: 'Rest', conditionB: 'Stim8hr' }),
    );
  });
});
