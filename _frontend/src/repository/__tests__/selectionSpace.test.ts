// Frozen valid-selection arithmetic (ROUND4_ADDENDUM final topology). With 10 admitted
// programs the ordered selection space is 3,540 (1,140 within-condition + 2,400 temporal) —
// NOT the naive 5,400. Same program+pole is a valid cross-timepoint comparison but an
// identical within-condition tuple is refused.

import { describe, expect, it } from 'vitest';
import {
  statesPerCondition,
  withinConditionSelectionCount,
  temporalSelectionCount,
  totalValidSelections,
  isExactPoleRefusal,
  N_ORDERED_TEMPORAL_PAIRS,
} from '../selectionSpace';

describe('valid-selection arithmetic (n = 10 admitted programs)', () => {
  it('has 20 states per condition (program × high|low)', () => {
    expect(statesPerCondition(10)).toBe(20);
  });

  it('has 6 ordered temporal condition pairs', () => {
    expect(N_ORDERED_TEMPORAL_PAIRS).toBe(6);
  });

  it('within-condition = 3 × 20 × 19 = 1,140 (excludes the identical tuple)', () => {
    expect(withinConditionSelectionCount(10)).toBe(1140);
  });

  it('temporal = 6 × 20 × 20 = 2,400 (same state across timepoints is valid)', () => {
    expect(temporalSelectionCount(10)).toBe(2400);
  });

  it('total = 3,540 valid ordered selections — NOT 5,400', () => {
    expect(totalValidSelections(10)).toBe(3540);
    expect(totalValidSelections(10)).not.toBe(5400);
  });
});

describe('exact-pole refusal (identical only when program+pole+condition all identical)', () => {
  const a = { program_id: 'checkpoint_hi', direction: 'high' as const, condition: 'Rest' };

  it('refuses a truly identical within-condition tuple', () => {
    expect(isExactPoleRefusal(a, { ...a })).toBe(true);
  });

  it('does NOT refuse the same program+pole across different timepoints (valid temporal)', () => {
    expect(isExactPoleRefusal(a, { ...a, condition: 'Stim48hr' })).toBe(false);
  });

  it('does NOT refuse a different pole of the same program', () => {
    expect(isExactPoleRefusal(a, { ...a, direction: 'low' })).toBe(false);
  });
});
