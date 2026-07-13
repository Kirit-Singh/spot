import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
  contrastTitle,
  readStage1Selection,
  readStage1SelectionV3,
  clearStage1Selection,
  NO_SELECTION_TITLE,
} from '../contrastTitle';
import type { Stage1Selection } from '../contrastTitle';
import { SELECTION_V3_KEY, SELECTION_KEY } from '../../repository/source';
import { canonicalJson, sha256Hex } from '../../stage1/canonical';
import { deriveExecutionStatus } from '../../stage1/selectionV3';
import { deriveQuestionId } from '../../stage1/questionId';

const CONTRAST = 'Treg-like lo (at 48 hr) → Th1-like hi (at 48 hr)';
// The v3 contract carries program_ids, not display labels, so the shallow header contrast
// shows the ids (treg_like / th1_like) rather than the v1 display labels.
const V3_CONTRAST = 'treg_like lo (at 48 hr) → th1_like hi (at 48 hr)';

/**
 * Build a spot.stage01_selection.v3 contract with REAL recomputed hashes (mirrors the
 * builder used by the adapter suites) so the async fail-closed verifier accepts it.
 */
async function buildV3(over: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
  const cc: Record<string, unknown> = {
    A: { program_id: 'treg_like', score_field: 'treg_like_score', direction: 'low' },
    B: { program_id: 'th1_like', score_field: 'th1_like_score', direction: 'high' },
    analysis_mode: 'within_condition',
    combined_objective: null,
    conditions: ['Stim48hr'],
    dataset_id: 'marson2025_gwcd4_perturbseq',
    donor_scope: 'all',
    effect_universe_id: 'eu',
    poles_separate: true,
    registry_scorer_view_sha256: 'a'.repeat(64),
    source_h5ad_sha256: 'b'.repeat(64),
    source_hf_revision: 'rev1',
    stage1_method_version: 'stage1-continuous-v3.0.1',
  };
  const selFull = await sha256Hex(canonicalJson(cc));
  const contract: Record<string, unknown> = {
    schema_version: 'spot.stage01_selection.v3',
    selection_origin: 'user_selected',
    execution_status: deriveExecutionStatus('within_condition', 'available', 'available', 'available'),
    analysis_mode: 'within_condition',
    estimator_id: 'within_condition_v1',
    estimator_status: 'available',
    selection_id: selFull.slice(0, 16),
    selection_full_sha256: selFull,
    canonical_content: cc,
    poles: {
      A: { program_id: 'treg_like', direction: 'low', effect_projection_status: 'available', n_measured: 5, n_panel_in_effect_universe: 5, n_control_in_effect_universe: 5, reason_codes: [] },
      B: { program_id: 'th1_like', direction: 'high', effect_projection_status: 'available', n_measured: 4, n_panel_in_effect_universe: 4, n_control_in_effect_universe: 4, reason_codes: [] },
    },
    trust_bindings: { validation_raw_sha256: 'c'.repeat(64) },
    provenance_bindings: { primary_registry_v3_raw_sha256: 'd'.repeat(64) },
    historical_validation_provenance: { kind: 'frozen', selectability_v3_raw_sha256: 'e'.repeat(64), active_gate: false },
    // biology-only question_id (539431d), folded into the full-contract hash like the real emitter.
    question_id: await deriveQuestionId({ program_id: 'treg_like', direction: 'low' }, { program_id: 'th1_like', direction: 'high' }, ['Stim48hr'], 'within_condition'),
    ...over,
  };
  contract.full_contract_content_sha256 = await sha256Hex(canonicalJson(contract));
  if (over.full_contract_content_sha256) contract.full_contract_content_sha256 = over.full_contract_content_sha256;
  return contract;
}

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

describe('readStage1Selection — sync, v3-only, shallow-shaped, fail-closed', () => {
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

  it('shallow-shapes a valid v3 contract from localStorage into the header contrast', async () => {
    window.localStorage.setItem(SELECTION_V3_KEY, JSON.stringify(await buildV3()));
    expect(contrastTitle(readStage1Selection())).toBe(V3_CONTRAST);
  });

  it('reads sessionStorage as well as localStorage', async () => {
    window.sessionStorage.setItem(SELECTION_V3_KEY, JSON.stringify(await buildV3()));
    expect(contrastTitle(readStage1Selection())).toBe(V3_CONTRAST);
  });

  it('FAIL CLOSED: a v1 object in the v3 key yields no selection (no v1/raw fallback)', () => {
    const v1 = { schema_version: 'spot.stage01_selection.v1', program_a: { display_label: 'X', direction: 'low' } };
    window.localStorage.setItem(SELECTION_V3_KEY, JSON.stringify(v1));
    expect(readStage1Selection()).toBeNull();
  });

  it('FAIL CLOSED: never reads the legacy v1 key', () => {
    const v1 = { schema_version: 'spot.stage01_selection.v1', program_a: { display_label: 'X', direction: 'low' } };
    window.localStorage.setItem(SELECTION_KEY, JSON.stringify(v1));
    expect(readStage1Selection()).toBeNull();
  });

  it('treats malformed JSON as no selection', () => {
    window.localStorage.setItem(SELECTION_V3_KEY, '{ not valid json');
    expect(readStage1Selection()).toBeNull();
  });

  it('yields no contrast for a v3-schema object lacking canonical_content', () => {
    window.localStorage.setItem(SELECTION_V3_KEY, JSON.stringify({ schema_version: 'spot.stage01_selection.v3' }));
    expect(readStage1Selection()).toBeNull();
    expect(contrastTitle(readStage1Selection())).toBeNull();
  });
});

describe('readStage1SelectionV3 — async, fully verified, fail-closed', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it('resolves a verified v3 contract into the typed SelectionV3', async () => {
    window.localStorage.setItem(SELECTION_V3_KEY, JSON.stringify(await buildV3()));
    const sel = await readStage1SelectionV3();
    expect(sel).not.toBeNull();
    expect(sel?.A).toEqual({ program_id: 'treg_like', direction: 'low' });
    expect(sel?.B).toEqual({ program_id: 'th1_like', direction: 'high' });
    expect(sel?.execution_status).toBe('ready');
    expect(sel?.conditions).toEqual(['Stim48hr']);
  });

  it('rejects a v1 object at the schema gate → null (no v1 fallback)', async () => {
    window.localStorage.setItem(SELECTION_V3_KEY, JSON.stringify({ schema_version: 'spot.stage01_selection.v1' }));
    expect(await readStage1SelectionV3()).toBeNull();
  });

  it('rejects a forged full_contract_content_sha256 → null', async () => {
    const forged = await buildV3({ full_contract_content_sha256: '0'.repeat(64) });
    window.localStorage.setItem(SELECTION_V3_KEY, JSON.stringify(forged));
    expect(await readStage1SelectionV3()).toBeNull();
  });

  it('is null when nothing is stored', async () => {
    expect(await readStage1SelectionV3()).toBeNull();
  });
});

describe('reconciled both-stores read (gate U18) — no split-brain', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  const minimalV3 = (id: string) =>
    JSON.stringify({
      schema_version: 'spot.stage01_selection.v3',
      selection_id: id,
      canonical_content: {
        A: { program_id: 'treg_like', direction: 'low' },
        B: { program_id: 'th1_like', direction: 'high' },
        conditions: ['Stim48hr'],
      },
    });

  it('session and local DIFFER → sync AND async header reads both resolve to null (fail closed)', async () => {
    window.sessionStorage.setItem(SELECTION_V3_KEY, minimalV3('1111111111111111'));
    window.localStorage.setItem(SELECTION_V3_KEY, minimalV3('2222222222222222'));
    expect(readStage1Selection()).toBeNull();
    expect(await readStage1SelectionV3()).toBeNull();
  });

  it('session == local (byte-identical, verified) → both reads resolve the SAME selection', async () => {
    const raw = JSON.stringify(await buildV3());
    window.sessionStorage.setItem(SELECTION_V3_KEY, raw);
    window.localStorage.setItem(SELECTION_V3_KEY, raw);
    expect(contrastTitle(readStage1Selection())).toBe(V3_CONTRAST);
    const v3 = await readStage1SelectionV3();
    expect(v3?.selection_id).toMatch(/^[0-9a-f]{16}$/);
  });

  it('only session present → resolves', async () => {
    window.sessionStorage.setItem(SELECTION_V3_KEY, JSON.stringify(await buildV3()));
    expect(contrastTitle(readStage1Selection())).toBe(V3_CONTRAST);
    expect(await readStage1SelectionV3()).not.toBeNull();
  });

  it('only local present → resolves', async () => {
    window.localStorage.setItem(SELECTION_V3_KEY, JSON.stringify(await buildV3()));
    expect(contrastTitle(readStage1Selection())).toBe(V3_CONTRAST);
    expect(await readStage1SelectionV3()).not.toBeNull();
  });

  it('a v1 object at the legacy v1 key is ignored by both reads', async () => {
    const v1 = JSON.stringify({ schema_version: 'spot.stage01_selection.v1' });
    window.localStorage.setItem(SELECTION_KEY, v1);
    window.sessionStorage.setItem(SELECTION_KEY, v1);
    expect(readStage1Selection()).toBeNull();
    expect(await readStage1SelectionV3()).toBeNull();
  });
});

describe('clearStage1Selection', () => {
  it('removes the bridged v3 selection from both stores', async () => {
    const raw = JSON.stringify(await buildV3());
    window.localStorage.setItem(SELECTION_V3_KEY, raw);
    window.sessionStorage.setItem(SELECTION_V3_KEY, raw);
    clearStage1Selection();
    expect(window.localStorage.getItem(SELECTION_V3_KEY)).toBeNull();
    expect(window.sessionStorage.getItem(SELECTION_V3_KEY)).toBeNull();
    expect(readStage1Selection()).toBeNull();
  });
});
