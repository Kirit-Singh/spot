// The browser INDEPENDENTLY derives the active selection's identity (mode + selection_id + the two exact
// selected gene arm keys) from the verified v3 selection — results/current.json is selection-INDEPENDENT,
// so ONE admitted release resolves arbitrary within/temporal dropdown choices. A changed A/B/time yields a
// DIFFERENT identity (the loader then selects different release slots / filters Stage-3/4 by these arms),
// never reusing a previous selection's result. The biology-only question_id (539431d) is re-derived +
// verified upstream in parseSelectionV3 and carried through here, DISTINCT from the method/input-bound
// selection_id; identical full endpoints (both poles → the same arm) are refused.

import { describe, expect, it } from 'vitest';
import { selectionIdentity } from '../selectionIdentity';
import type { SelectionV3 } from '../../adapters/selectionV3Adapter';

function sel(over: Partial<SelectionV3>): SelectionV3 {
  return {
    selection_id: 's1', question_id: 'q'.repeat(16), analysis_mode: 'within_condition', execution_status: 'ready',
    estimator_id: 'within_condition_v1', estimator_status: 'available',
    A: { program_id: 'treg_like', direction: 'high' }, B: { program_id: 'th1_like', direction: 'low' }, conditions: ['Rest'],
    registry_scorer_view_sha256: 'd'.repeat(64), source_h5ad_sha256: 'c'.repeat(64),
    selection_full_sha256: 'e'.repeat(64), full_contract_content_sha256: 'f'.repeat(64), raw: {},
    ...over,
  };
}

describe('selectionIdentity — runtime derivation over a selection-independent release', () => {
  it('arbitrary within: mode + two Direct arm keys for the selected programs @ the selected condition', () => {
    const id = selectionIdentity(sel({ analysis_mode: 'within_condition', A: { program_id: 'treg_like', direction: 'high' }, B: { program_id: 'th1_like', direction: 'low' }, conditions: ['Rest'] }));
    expect(id.analysis_mode).toBe('within_condition');
    expect(id.arm_keys.length).toBe(2);
    expect(id.arm_keys.every((k) => k.startsWith('direct|'))).toBe(true);
    expect(id.arm_keys.some((k) => k.includes('treg_like'))).toBe(true);
    expect(id.arm_keys.some((k) => k.includes('th1_like'))).toBe(true);
    expect(id.arm_keys.every((k) => k.endsWith('|Rest'))).toBe(true);
  });

  it('arbitrary temporal: mode + two Temporal arm keys across the ordered conditions', () => {
    const id = selectionIdentity(sel({ analysis_mode: 'temporal_cross_condition', A: { program_id: 'treg_like', direction: 'high' }, B: { program_id: 'th1_like', direction: 'high' }, conditions: ['Rest', 'Stim48hr'] }));
    expect(id.analysis_mode).toBe('temporal_cross_condition');
    expect(id.arm_keys.length).toBe(2);
    expect(id.arm_keys.every((k) => k.startsWith('temporal|'))).toBe(true);
  });

  it('same-program temporal: still two DISTINCT arm keys (A away_from_A vs B toward_b → different change)', () => {
    const id = selectionIdentity(sel({ analysis_mode: 'temporal_cross_condition', A: { program_id: 'treg_like', direction: 'high' }, B: { program_id: 'treg_like', direction: 'high' }, conditions: ['Rest', 'Stim48hr'] }));
    expect(id.arm_keys.length).toBe(2);
    expect(new Set(id.arm_keys).size).toBe(2);
  });

  it('selection change: a different time / B program / id yields a DIFFERENT identity (never reused)', () => {
    const base = selectionIdentity(sel({ conditions: ['Rest'] }));
    expect(selectionIdentity(sel({ conditions: ['Stim48hr'] })).arm_keys).not.toEqual(base.arm_keys); // changed time
    expect(selectionIdentity(sel({ B: { program_id: 'th2_like', direction: 'low' } })).arm_keys).not.toEqual(base.arm_keys); // changed B
    expect(selectionIdentity(sel({ selection_id: 's2' })).selection_id).not.toBe(base.selection_id);
  });

  it('carries the biology-only question_id through (DISTINCT from selection_id)', () => {
    const id = selectionIdentity(sel({ selection_id: 's1', question_id: 'q'.repeat(16) }));
    expect(id.question_id).toBe('q'.repeat(16));
    expect(id.question_id).not.toBe(id.selection_id);
  });

  it('REFUSES identical full endpoints — both poles resolve to the exact same arm', () => {
    // within_condition, same program: away_from_A(high)=decrease and toward_b(low)=decrease → both poles
    // become direct|treg_like|decrease|Rest. That is a degenerate (A==B) question, not a real contrast.
    expect(() =>
      selectionIdentity(sel({ analysis_mode: 'within_condition', A: { program_id: 'treg_like', direction: 'high' }, B: { program_id: 'treg_like', direction: 'low' }, conditions: ['Rest'] })),
    ).toThrow(/identical full endpoints/);
  });
});
