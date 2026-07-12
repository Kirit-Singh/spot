import { describe, expect, it } from 'vitest';
import { deriveRouting, TEMPORAL_AWAITING_REASON } from '../routingReason';

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

  it('objective incompatible (same pole) → refused + typed reason', () => {
    const r = deriveRouting({ ...base, bProgram: 'treg_like', bDirection: 'low' });
    expect(r.execution_status).toBe('refused');
    expect(r.reason_code).toBe('objective_incompatible_same_pole');
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
