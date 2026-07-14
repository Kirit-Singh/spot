// Reconciled Stage-1 v3 read rule (gate U18): SELECTION_V3_KEY is read from BOTH stores
// under one documented rule so the header and the repository can never bind DIFFERENT
// selections. The legacy v1 key is never consulted.

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  readReconciledV3Raw,
  browserSource,
  SELECTION_V3_KEY,
  SELECTION_KEY,
  STAGE2_KEY,
} from '../source';

/** A valid-shaped v3 contract string with a given selection_id (bytes are what matter here). */
const v3 = (id: string) =>
  JSON.stringify({
    schema_version: 'spot.stage01_selection.v3',
    selection_id: id,
    canonical_content: { A: { program_id: 'a', direction: 'low' }, B: { program_id: 'b', direction: 'high' }, conditions: ['Rest'] },
  });

const A = v3('1111111111111111');
const B = v3('2222222222222222');

describe('readReconciledV3Raw — both-stores rule', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it('neither store → null', () => {
    expect(readReconciledV3Raw()).toBeNull();
  });

  it('only local → that value', () => {
    window.localStorage.setItem(SELECTION_V3_KEY, A);
    expect(readReconciledV3Raw()).toBe(A);
  });

  it('only session → that value', () => {
    window.sessionStorage.setItem(SELECTION_V3_KEY, A);
    expect(readReconciledV3Raw()).toBe(A);
  });

  it('both byte-identical → that value', () => {
    window.localStorage.setItem(SELECTION_V3_KEY, A);
    window.sessionStorage.setItem(SELECTION_V3_KEY, A);
    expect(readReconciledV3Raw()).toBe(A);
  });

  it('both present but DIFFERENT → null (FAIL CLOSED, no split-brain)', () => {
    window.localStorage.setItem(SELECTION_V3_KEY, A);
    window.sessionStorage.setItem(SELECTION_V3_KEY, B);
    expect(readReconciledV3Raw()).toBeNull();
  });

  it('a v1 object at the legacy v1 key is never consulted', () => {
    window.localStorage.setItem(SELECTION_KEY, JSON.stringify({ schema_version: 'spot.stage01_selection.v1' }));
    window.sessionStorage.setItem(SELECTION_KEY, JSON.stringify({ schema_version: 'spot.stage01_selection.v1' }));
    expect(readReconciledV3Raw()).toBeNull();
  });
});

describe('browserSource — SELECTION_V3_KEY reads through the reconciled rule', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it('routes the v3 key through reconciliation (mismatch → null)', () => {
    window.localStorage.setItem(SELECTION_V3_KEY, A);
    window.sessionStorage.setItem(SELECTION_V3_KEY, B);
    expect(browserSource().read(SELECTION_V3_KEY)).toBeNull();
  });

  it('agreeing stores → the reconciled value', () => {
    window.localStorage.setItem(SELECTION_V3_KEY, A);
    window.sessionStorage.setItem(SELECTION_V3_KEY, A);
    expect(browserSource().read(SELECTION_V3_KEY)).toBe(A);
  });

  it('non-v3 keys still read localStorage directly (not reconciled)', () => {
    window.localStorage.setItem(STAGE2_KEY, 'X');
    window.sessionStorage.setItem(STAGE2_KEY, 'Y'); // ignored — only the v3 key is reconciled
    expect(browserSource().read(STAGE2_KEY)).toBe('X');
  });
});
