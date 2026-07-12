import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
  contrastTitle,
  readStage1Selection,
  clearStage1Selection,
  NO_SELECTION_TITLE,
} from '../contrastTitle';
import type { Stage1Selection } from '../contrastTitle';
import { SELECTION_KEY } from '../../repository/source';
import { researchSelectionExampleRaw } from '../../fixtures/researchSelection.example';

const CONTRAST = 'Treg-like lo (at 48 hr) → Th1-like hi (at 48 hr)';

describe('contrastTitle — formatting', () => {
  it('is null when there is no selection', () => {
    expect(contrastTitle(null)).toBeNull();
  });

  it('is null when either pole is missing', () => {
    expect(contrastTitle({ program_a: { display_label: 'A' } })).toBeNull();
    expect(contrastTitle({ program_b: { display_label: 'B' } })).toBeNull();
  });

  it('formats direction (high→hi, low→lo) and a known condition (Stim48hr→48 hr)', () => {
    const sel: Stage1Selection = {
      program_a: { display_label: 'Treg-like', direction: 'low' },
      program_b: { display_label: 'Th1-like', direction: 'high' },
      analysis_condition: 'Stim48hr',
    };
    expect(contrastTitle(sel)).toBe(CONTRAST);
  });

  it('maps Rest→rest and lowercases an unknown condition', () => {
    const poles = {
      program_a: { display_label: 'A', direction: 'high' },
      program_b: { display_label: 'B', direction: 'low' },
    };
    expect(contrastTitle({ ...poles, analysis_condition: 'Rest' })).toBe(
      'A hi (at rest) → B lo (at rest)',
    );
    expect(contrastTitle({ ...poles, analysis_condition: 'CUSTOM_TP' })).toBe(
      'A hi (at custom_tp) → B lo (at custom_tp)',
    );
  });

  it('omits the "(at …)" clause without a condition and passes an unknown direction through', () => {
    expect(
      contrastTitle({
        program_a: { display_label: 'A', direction: 'up' },
        program_b: { display_label: 'B' },
      }),
    ).toBe('A up → B');
  });

  it('exposes the no-selection prompt string', () => {
    expect(NO_SELECTION_TITLE).toBe('Select populations in Programs →');
  });
});

describe('readStage1Selection — adapter-primary, storage-fallback', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it('is null when nothing is stored', () => {
    expect(readStage1Selection()).toBeNull();
  });

  it('PRIMARY: resolves a valid research_only selection through the shell adapter', () => {
    window.localStorage.setItem(SELECTION_KEY, JSON.stringify(researchSelectionExampleRaw));
    const sel = readStage1Selection();
    expect(sel).not.toBeNull();
    // it came back through parseSelection (validated), not a raw pass-through
    expect((sel as { namespace?: string }).namespace).toBe('research_only');
    expect(contrastTitle(sel)).toBe(CONTRAST);
  });

  it('reads sessionStorage as well as localStorage', () => {
    window.sessionStorage.setItem(SELECTION_KEY, JSON.stringify(researchSelectionExampleRaw));
    expect(contrastTitle(readStage1Selection())).toBe(CONTRAST);
  });

  it('FALLBACK: an adapter-rejected (wrong-namespace) selection still yields the raw contrast', () => {
    // namespace 'production' can never bind to the research_only adapter → parseSelection throws;
    // the raw object is returned unvalidated so the header never loses the carried selection.
    const rejected = { ...researchSelectionExampleRaw, namespace: 'production' };
    window.localStorage.setItem(SELECTION_KEY, JSON.stringify(rejected));
    const sel = readStage1Selection();
    expect(sel).not.toBeNull();
    expect((sel as { namespace?: string }).namespace).toBe('production'); // not coerced
    expect(contrastTitle(sel)).toBe(CONTRAST);
  });

  it('treats malformed JSON as no selection', () => {
    window.localStorage.setItem(SELECTION_KEY, '{ not valid json');
    expect(readStage1Selection()).toBeNull();
  });

  it('yields no contrast for valid JSON that is not a selection', () => {
    window.localStorage.setItem(SELECTION_KEY, JSON.stringify({ foo: 'bar' }));
    expect(contrastTitle(readStage1Selection())).toBeNull();
  });
});

describe('clearStage1Selection', () => {
  it('removes the bridged selection from both stores', () => {
    const raw = JSON.stringify(researchSelectionExampleRaw);
    window.localStorage.setItem(SELECTION_KEY, raw);
    window.sessionStorage.setItem(SELECTION_KEY, raw);
    clearStage1Selection();
    expect(window.localStorage.getItem(SELECTION_KEY)).toBeNull();
    expect(window.sessionStorage.getItem(SELECTION_KEY)).toBeNull();
    expect(readStage1Selection()).toBeNull();
  });
});
