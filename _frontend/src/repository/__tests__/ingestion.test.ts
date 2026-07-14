// Selection ingestion + fail-closed v3 gate.
//
// The Stage-1 page writes the AUTHORITATIVE `spot.stage01_selection.v3` contract to
// storage. This suite pins how the shell ingests it: demo vs research vs rejected, the
// v3-only fail-closed gate (a v1 object or corrupt v3 is rejected, never a v1/raw/stale
// fallback), and that fixture results are NEVER shown beneath a real selection.

import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { buildRepository, createDemoRepository } from '../repository';
import { mapSource, browserSource, SELECTION_V3_KEY } from '../source';

const j = (o: unknown) => JSON.stringify(o);

/** A minimal, structurally-valid spot.stage01_selection.v3 object (sync gate is shallow). */
const validV3 = {
  schema_version: 'spot.stage01_selection.v3',
  selection_id: 'a1b2c3d4e5f60718',
  question_id: 'q'.repeat(16), // biology-only id; shallow projection shape-checks it present
  analysis_mode: 'within_condition',
  execution_status: 'ready',
  estimator_id: 'within_condition_v1',
  estimator_status: 'available',
  selection_full_sha256: 'f'.repeat(64),
  full_contract_content_sha256: '9'.repeat(64),
  canonical_content: {
    A: { program_id: 'treg_like', score_field: 'treg_like_score', direction: 'low' },
    B: { program_id: 'th1_like', score_field: 'th1_like_score', direction: 'high' },
    conditions: ['Stim48hr'],
    registry_scorer_view_sha256: 'a'.repeat(64),
    source_h5ad_sha256: 'b'.repeat(64),
  },
};

describe('mode selection from storage (v3 key)', () => {
  it('no selection, no demo → empty scaffold (no data rendered)', () => {
    const repo = buildRepository(mapSource({}));
    expect(repo.mode).toBe('empty');
    expect(repo.selection).toBeNull();
    expect(repo.selectionV3).toBeNull();
    expect(repo.getStage2().status).toBe('not_generated');
  });

  it('no selection + explicit demo gate → demo mode with synthetic artifacts', () => {
    const repo = buildRepository(mapSource({}), { demo: true });
    expect(repo.mode).toBe('demo');
    expect(repo.namespace).toBe('fixture');
    expect(repo.selectionV3).toBeNull();
    expect(repo.getStage2().status).toBe('loaded');
  });

  it('valid v3 selection → research mode; the v3 selection resolves', () => {
    const repo = buildRepository(mapSource({ [SELECTION_V3_KEY]: j(validV3) }));
    expect(repo.mode).toBe('research');
    expect(repo.namespace).toBe('research_only');
    expect(repo.selectionRejection).toBeNull();
    // The authoritative v3 is exposed…
    expect(repo.selectionV3?.A).toEqual({ program_id: 'treg_like', direction: 'low' });
    expect(repo.selectionV3?.B).toEqual({ program_id: 'th1_like', direction: 'high' });
    expect(repo.selectionV3?.conditions).toEqual(['Stim48hr']);
    // …while the legacy StageSelection carrier stays null (v3 is the carrier).
    expect(repo.selection).toBeNull();
  });

  it('research selection → not_generated, NEVER fixture results (binding held)', () => {
    const repo = buildRepository(mapSource({ [SELECTION_V3_KEY]: j(validV3) }));
    expect(repo.getStage2().status).toBe('not_generated');
    expect(repo.getStage3().status).toBe('not_generated');
    expect(repo.getStage4().status).toBe('not_generated');
  });
});

describe('fail-closed v3 gate — no v1/raw/stale fallback', () => {
  it('a v1 object in the v3 key → rejected_selection (never research, never fixture)', () => {
    const v1 = {
      schema_version: 'spot.stage01_selection.v1',
      namespace: 'research_only',
      program_a: { program_id: 'treg_like', display_label: 'Treg', direction: 'low' },
      program_b: { program_id: 'th1_like', display_label: 'Th1', direction: 'high' },
      analysis_condition: 'Stim48hr',
    };
    const repo = buildRepository(mapSource({ [SELECTION_V3_KEY]: j(v1) }));
    expect(repo.mode).toBe('rejected_selection');
    expect(repo.selection).toBeNull();
    expect(repo.selectionV3).toBeNull();
    expect(repo.selectionRejection).toBeTruthy();
    expect(repo.getStage2().status).toBe('rejected');
  });

  it('a corrupt v3 (right schema, missing canonical_content) → rejected_selection', () => {
    const repo = buildRepository(
      mapSource({ [SELECTION_V3_KEY]: j({ schema_version: 'spot.stage01_selection.v3' }) }),
    );
    expect(repo.mode).toBe('rejected_selection');
    expect(repo.selectionV3).toBeNull();
  });

  it('a v3 with a broken pole (missing program_id) → rejected_selection', () => {
    const broken = structuredClone(validV3) as Record<string, unknown>;
    (broken.canonical_content as { A: Record<string, unknown> }).A = { direction: 'low' };
    const repo = buildRepository(mapSource({ [SELECTION_V3_KEY]: j(broken) }));
    expect(repo.mode).toBe('rejected_selection');
  });

  it('an unknown schema_version → rejected_selection', () => {
    const repo = buildRepository(mapSource({ [SELECTION_V3_KEY]: j({ schema_version: 'nope.v9' }) }));
    expect(repo.mode).toBe('rejected_selection');
  });

  it('malformed JSON selection → rejected_selection', () => {
    const repo = buildRepository(mapSource({ [SELECTION_V3_KEY]: '{ not json ]' }));
    expect(repo.mode).toBe('rejected_selection');
  });
});

describe('reconciled both-stores read at the repository (gate U18)', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it('session and local hold DIFFERENT valid v3 → binds nothing (no split-brain with the header)', () => {
    window.sessionStorage.setItem(SELECTION_V3_KEY, j({ ...validV3, selection_id: 'aaaaaaaaaaaaaaaa' }));
    window.localStorage.setItem(SELECTION_V3_KEY, j({ ...validV3, selection_id: 'bbbbbbbbbbbbbbbb' }));
    const repo = buildRepository(browserSource());
    expect(repo.selectionV3).toBeNull();
    expect(repo.mode).not.toBe('research');
  });

  it('session == local → research mode binds the reconciled selection', () => {
    const raw = j(validV3);
    window.sessionStorage.setItem(SELECTION_V3_KEY, raw);
    window.localStorage.setItem(SELECTION_V3_KEY, raw);
    const repo = buildRepository(browserSource());
    expect(repo.mode).toBe('research');
    expect(repo.selectionV3?.selection_id).toBe('a1b2c3d4e5f60718');
  });

  it('only one store present → resolves to research mode', () => {
    window.localStorage.setItem(SELECTION_V3_KEY, j(validV3));
    const repo = buildRepository(browserSource());
    expect(repo.mode).toBe('research');
  });
});

describe('demo/fixture repository stays available', () => {
  it('createDemoRepository loads synthetic stage artifacts', () => {
    const repo = createDemoRepository();
    expect(repo.mode).toBe('demo');
    expect(repo.getStage2().status).toBe('loaded');
    expect(repo.getStage3().status).toBe('loaded');
    expect(repo.getStage4().status).toBe('loaded');
  });
});
