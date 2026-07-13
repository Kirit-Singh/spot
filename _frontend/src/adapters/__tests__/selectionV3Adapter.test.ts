import { describe, expect, it } from 'vitest';
import { canonicalJson, sha256Hex } from '../../stage1/canonical';
import { deriveQuestionId } from '../../stage1/questionId';
import { deriveExecutionStatus, SelectionError, type EstimatorStatus } from '../../stage1/selectionV3';
import { parseSelectionV3 } from '../selectionV3Adapter';

interface BuildOpts {
  mode?: 'within_condition' | 'temporal_cross_condition';
  aId?: string;
  aDir?: 'high' | 'low';
  bId?: string;
  bDir?: 'high' | 'low';
  aStatus?: 'available' | 'unavailable';
  bStatus?: 'available' | 'unavailable';
  conditions?: string[];
  estimator_id?: string;
  estimator_status?: 'available' | 'not_implemented';
  execution_status?: string;
  tamperFullContract?: string;
  /** Force a specific question_id (still folded into the full-contract hash, so the value is
   *  internally hash-consistent — exercises a REFORGED-but-consistent question_id). */
  questionId?: string;
  /** Omit question_id from the contract entirely (exercises the null refusal). */
  omitQuestionId?: boolean;
}

/**
 * Build a spot.stage01_selection.v3 contract with REAL recomputed hashes over its content,
 * mirroring the `build()` helper in stage1/__tests__/selectionV3.test.ts so the adapter is
 * exercised against genuinely-verifiable fixtures (not hand-faked digests).
 */
async function build(opts: BuildOpts = {}): Promise<Record<string, unknown>> {
  const mode = opts.mode ?? 'within_condition';
  const aId = opts.aId ?? 'treg_like';
  const aDir = opts.aDir ?? 'low';
  const bId = opts.bId ?? 'th1_like';
  const bDir = opts.bDir ?? 'high';
  const aStatus = opts.aStatus ?? 'available';
  const bStatus = opts.bStatus ?? 'available';
  const conditions =
    opts.conditions ?? (mode === 'within_condition' ? ['Stim48hr'] : ['Rest', 'Stim48hr']);
  const estimator_id =
    opts.estimator_id ?? (mode === 'within_condition' ? 'within_condition_v1' : 'temporal_cross_condition_v1');
  const estimatorStatus = (opts.estimator_status ??
    (mode === 'within_condition' ? 'available' : 'available')) as EstimatorStatus;

  const cc: Record<string, unknown> = {
    A: { program_id: aId, score_field: `${aId}_score`, direction: aDir },
    B: { program_id: bId, score_field: `${bId}_score`, direction: bDir },
    analysis_mode: mode,
    combined_objective: null,
    conditions,
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
    execution_status: opts.execution_status ?? deriveExecutionStatus(mode, aStatus, bStatus, estimatorStatus),
    analysis_mode: mode,
    estimator_id,
    estimator_status: estimatorStatus,
    selection_id: selFull.slice(0, 16),
    selection_full_sha256: selFull,
    canonical_content: cc,
    poles: {
      A: { program_id: aId, direction: aDir, effect_projection_status: aStatus, n_measured: 5, n_panel_in_effect_universe: 5, n_control_in_effect_universe: 5, reason_codes: [] },
      B: { program_id: bId, direction: bDir, effect_projection_status: bStatus, n_measured: 4, n_panel_in_effect_universe: 4, n_control_in_effect_universe: 4, reason_codes: [] },
    },
    trust_bindings: { validation_raw_sha256: 'c'.repeat(64) },
    provenance_bindings: { primary_registry_v3_raw_sha256: 'd'.repeat(64) },
    historical_validation_provenance: { kind: 'frozen', selectability_v3_raw_sha256: 'e'.repeat(64), active_gate: false },
  };
  // question_id (539431d): biology-only top-level field, folded into the full-contract hash (as the
  // real emitter does). Derived from the poles + ordered conditions + mode, so the happy-path fixture
  // matches the adapter's independent re-derivation.
  if (!opts.omitQuestionId) {
    contract.question_id =
      opts.questionId ??
      (await deriveQuestionId({ program_id: aId, direction: aDir }, { program_id: bId, direction: bDir }, conditions, mode));
  }
  contract.full_contract_content_sha256 = await sha256Hex(canonicalJson(contract));
  if (opts.tamperFullContract) contract.full_contract_content_sha256 = opts.tamperFullContract;
  return contract;
}

async function expectCode(fn: () => Promise<unknown>, code: string) {
  try {
    await fn();
  } catch (e) {
    expect(e).toBeInstanceOf(SelectionError);
    expect((e as SelectionError).code).toBe(code);
    return;
  }
  throw new Error(`expected SelectionError(${code}) but none thrown`);
}

describe('parseSelectionV3 — projects a verified within_condition contract', () => {
  it('projects A/B program_ids + directions + conditions', async () => {
    const s = await parseSelectionV3(await build({ mode: 'within_condition' }));
    expect(s.analysis_mode).toBe('within_condition');
    expect(s.execution_status).toBe('ready');
    expect(s.estimator_id).toBe('within_condition_v1');
    expect(s.estimator_status).toBe('available');
    expect(s.A).toEqual({ program_id: 'treg_like', direction: 'low' });
    expect(s.B).toEqual({ program_id: 'th1_like', direction: 'high' });
    expect(s.conditions).toEqual(['Stim48hr']);
    expect(s.selection_id).toMatch(/^[0-9a-f]{16}$/);
    expect(s.selection_full_sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(s.full_contract_content_sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(s.registry_scorer_view_sha256).toBe('a'.repeat(64));
    expect(s.source_h5ad_sha256).toBe('b'.repeat(64));
    // question_id: biology-only, independently re-derived, DISTINCT from selection_id.
    expect(s.question_id).toMatch(/^[0-9a-f]{16}$/);
    expect(s.question_id).toBe(
      await deriveQuestionId({ program_id: 'treg_like', direction: 'low' }, { program_id: 'th1_like', direction: 'high' }, ['Stim48hr'], 'within_condition'),
    );
    expect(s.question_id).not.toBe(s.selection_id);
  });

  it('is generic — projects a NON-Treg arbitrary pair (th17_like → th1_like)', async () => {
    const s = await parseSelectionV3(
      await build({ aId: 'th17_like', aDir: 'high', bId: 'th1_like', bDir: 'low' }),
    );
    expect(s.A).toEqual({ program_id: 'th17_like', direction: 'high' });
    expect(s.B).toEqual({ program_id: 'th1_like', direction: 'low' });
    expect(s.execution_status).toBe('ready');
  });
});

describe('parseSelectionV3 — temporal cross-condition', () => {
  it('projects an ordered 2-condition pair; estimator available → execution_status ready', async () => {
    const s = await parseSelectionV3(
      await build({ mode: 'temporal_cross_condition', estimator_status: 'available' }),
    );
    expect(s.analysis_mode).toBe('temporal_cross_condition');
    expect(s.estimator_id).toBe('temporal_cross_condition_v1');
    expect(s.estimator_status).toBe('available');
    expect(s.execution_status).toBe('ready');
    expect(s.conditions).toEqual(['Rest', 'Stim48hr']); // ordered [from, to]
  });
});

describe('parseSelectionV3 — fail-closed rejections', () => {
  it('rejects a v1 selection object at the named schema gate', async () => {
    const v1 = {
      schema_version: 'spot.stage01_selection.v1',
      namespace: 'research',
      production_gate_passed: false,
      selection_id: 'sel-v1',
      contrast_id: 'c1',
      program_a: { program_id: 'treg_like', score_field: 'treg_like_score', display_label: 'Treg', direction: 'low' },
      program_b: { program_id: 'th1_like', score_field: 'th1_like_score', display_label: 'Th1', direction: 'high' },
      analysis_condition: 'Stim48hr',
      dataset_id: 'ds',
      donor_scope: 'all',
      artifact_status: 'ok',
    };
    await expectCode(() => parseSelectionV3(v1), 'bad_schema_version');
  });

  it('rejects a forged full_contract_content_sha256', async () => {
    await expectCode(
      () => build({ tamperFullContract: '0'.repeat(64) }).then(parseSelectionV3),
      'full_contract_sha_mismatch',
    );
  });

  it('rejects a wrong estimator for the mode (temporal estimator on within_condition)', async () => {
    await expectCode(
      () => build({ mode: 'within_condition', estimator_id: 'temporal_cross_condition_v1' }).then(parseSelectionV3),
      'estimator_mode_mismatch',
    );
  });

  it('rejects a contract with NO question_id (null → cannot be re-derived-and-matched)', async () => {
    // full_contract hash is still valid (computed over the question_id-less contract); the adapter
    // refuses because the required biology-only question_id is absent.
    await expectCode(() => build({ omitQuestionId: true }).then(parseSelectionV3), 'malformed');
  });

  it('rejects a REFORGED question_id (hash-consistent but != independently re-derived biology id)', async () => {
    // The forged id is folded into the full-contract hash, so verifySelectionV3 passes; the adapter's
    // independent 539431d re-derivation still catches that it names a different question.
    await expectCode(() => build({ questionId: '0'.repeat(16) }).then(parseSelectionV3), 'malformed');
  });
});
