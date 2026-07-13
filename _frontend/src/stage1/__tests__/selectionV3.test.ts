import { describe, expect, it } from 'vitest';
import { canonicalJson, sha256Hex } from '../canonical';
import {
  deriveExecutionStatus,
  SelectionError,
  verifySelectionV3,
  type EstimatorStatus,
} from '../selectionV3';

interface BuildOpts {
  mode?: 'within_condition' | 'temporal_cross_condition';
  aStatus?: 'available' | 'unavailable';
  bStatus?: 'available' | 'unavailable';
  execution_status?: string;
  estimator_id?: string;
  estimator_status?: string;
  ccMode?: string;
  topMode?: string;
  polesAId?: string;
  activeGate?: boolean;
  tamperSelectionId?: string;
  tamperFullContract?: string;
}

/** Build a selection.v3 contract with REAL recomputed hashes over its (possibly mutated) content. */
async function build(opts: BuildOpts = {}) {
  const mode = opts.mode ?? 'within_condition';
  const aStatus = opts.aStatus ?? 'available';
  const bStatus = opts.bStatus ?? 'available';
  const estimatorStatus = (opts.estimator_status ??
    (mode === 'within_condition' ? 'available' : 'not_implemented')) as EstimatorStatus;
  const conditions = mode === 'within_condition' ? ['Stim48hr'] : ['Rest', 'Stim48hr'];
  const cc: Record<string, unknown> = {
    A: { program_id: 'treg_like', score_field: 'treg_like_score', direction: 'low' },
    B: { program_id: 'th1_like', score_field: 'th1_like_score', direction: 'high' },
    analysis_mode: opts.ccMode ?? mode,
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
    analysis_mode: opts.topMode ?? mode,
    estimator_id: opts.estimator_id ?? (mode === 'within_condition' ? 'within_condition_v1' : 'temporal_cross_condition_v1'),
    estimator_status: estimatorStatus,
    selection_id: selFull.slice(0, 16),
    selection_full_sha256: selFull,
    canonical_content: cc,
    poles: {
      A: { program_id: opts.polesAId ?? 'treg_like', direction: 'low', effect_projection_status: aStatus, n_measured: 5, n_panel_in_effect_universe: 5, n_control_in_effect_universe: 5, reason_codes: [] },
      B: { program_id: 'th1_like', direction: 'high', effect_projection_status: bStatus, n_measured: 4, n_panel_in_effect_universe: 4, n_control_in_effect_universe: 4, reason_codes: [] },
    },
    trust_bindings: { validation_raw_sha256: 'c'.repeat(64) },
    provenance_bindings: { primary_registry_v3_raw_sha256: 'd'.repeat(64) },
    historical_validation_provenance: { kind: 'frozen', selectability_v3_raw_sha256: 'e'.repeat(64), active_gate: opts.activeGate ?? false },
  };
  contract.full_contract_content_sha256 = await sha256Hex(canonicalJson(contract));
  if (opts.tamperSelectionId) contract.selection_id = opts.tamperSelectionId;
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

describe('selection.v3 — valid routing resolves', () => {
  it('within_condition, both poles available → ready', async () => {
    const r = await verifySelectionV3(await build({ mode: 'within_condition' }));
    expect(r.execution_status).toBe('ready');
    expect(r.derived_execution_status).toBe('ready');
  });
  it('within_condition, a pole unavailable → refused', async () => {
    const r = await verifySelectionV3(await build({ aStatus: 'unavailable' }));
    expect(r.execution_status).toBe('refused');
  });
  it('temporal_cross_condition with estimator available → ready', async () => {
    const r = await verifySelectionV3(
      await build({ mode: 'temporal_cross_condition', estimator_status: 'available' }),
    );
    expect(r.execution_status).toBe('ready');
    expect(r.derived_execution_status).toBe('ready');
  });
  it('temporal_cross_condition with estimator not_implemented → awaiting_estimator', async () => {
    const r = await verifySelectionV3(
      await build({ mode: 'temporal_cross_condition', estimator_status: 'not_implemented' }),
    );
    expect(r.execution_status).toBe('awaiting_estimator');
    expect(r.derived_execution_status).toBe('awaiting_estimator');
  });
});

describe('selection.v3 — independent hash recompute', () => {
  it('rejects a tampered selection_id', async () => {
    await expectCode(() => build({ tamperSelectionId: '0'.repeat(16) }).then(verifySelectionV3), 'selection_id_mismatch');
  });
  it('rejects a tampered full_contract_content_sha256', async () => {
    await expectCode(() => build({ tamperFullContract: '0'.repeat(64) }).then(verifySelectionV3), 'full_contract_sha_mismatch');
  });
});

describe('selection.v3 — routing semantics enforced, not trusted', () => {
  it('rejects temporal not_implemented labelled ready (status must follow from content)', async () => {
    await expectCode(() => build({ mode: 'temporal_cross_condition', estimator_status: 'not_implemented', execution_status: 'ready' }).then(verifySelectionV3), 'execution_status_mismatch');
  });
  it('rejects temporal available labelled awaiting_estimator (status must follow from content)', async () => {
    await expectCode(() => build({ mode: 'temporal_cross_condition', estimator_status: 'available', execution_status: 'awaiting_estimator' }).then(verifySelectionV3), 'execution_status_mismatch');
  });
  it('rejects effect-unavailable pole labelled ready', async () => {
    await expectCode(() => build({ aStatus: 'unavailable', execution_status: 'ready' }).then(verifySelectionV3), 'execution_status_mismatch');
  });
  it('rejects estimator/mode mismatch (fake temporal estimator on within_condition)', async () => {
    await expectCode(() => build({ mode: 'within_condition', estimator_id: 'temporal_cross_condition_v1' }).then(verifySelectionV3), 'estimator_mode_mismatch');
  });
  it('rejects top-level vs canonical mode mismatch', async () => {
    await expectCode(() => build({ mode: 'within_condition', ccMode: 'temporal_cross_condition' }).then(verifySelectionV3), 'mode_mismatch');
  });
  it('rejects pole identity mismatch', async () => {
    await expectCode(() => build({ polesAId: 'someone_else' }).then(verifySelectionV3), 'pole_identity_mismatch');
  });
  it('rejects an untrue active_gate', async () => {
    await expectCode(() => build({ activeGate: true }).then(verifySelectionV3), 'active_gate_true');
  });
  it('rejects a wrong schema_version', async () => {
    const c = await build();
    c.schema_version = 'spot.stage01_selection.v2';
    await expectCode(() => verifySelectionV3(c), 'bad_schema_version');
  });
});
