import { describe, expect, it } from 'vitest';
import type { SelectionV3 } from '../../adapters/selectionV3Adapter';
import { parseUiResultsCurrent } from '../../adapters/uiResultsCurrentAdapter';
import { STAGE1_SELECTION_SCHEMA_RAW_SHA256, STAGE1_V3_RELEASE_SELF_SHA256 } from '../../stage1/contractBinding';
import { compactMetadata, compactProjectionRaw, compactReceipt, compactReceiptAdmitted, CONDITIONS } from '../../test/compactStage2';
import { canonicalJson, sha256Hex } from '../../stage1/canonical';
import { directArmKey, temporalArmKey } from '../../repository/armKey';
import { loadProductionProjection } from '../resolveRouteArtifact';

const H = '1'.repeat(64);

function selection(mode: SelectionV3['analysis_mode'], conditions: string[]): SelectionV3 {
  return {
    selection_id: 'a'.repeat(16), question_id: 'b'.repeat(16), analysis_mode: mode,
    execution_status: 'ready', estimator_id: mode === 'within_condition' ? 'within_condition_v1' : 'temporal_cross_condition_v1',
    estimator_status: 'available', A: { program_id: 'prog_alpha', direction: 'high' },
    B: { program_id: 'prog_beta', direction: 'low' }, conditions,
    registry_scorer_view_sha256: 'd'.repeat(64), source_h5ad_sha256: 'e'.repeat(64),
    selection_full_sha256: 'f'.repeat(64), full_contract_content_sha256: '0'.repeat(64), raw: {},
  };
}

async function release(
  rawInput?: Awaited<ReturnType<typeof compactProjectionRaw>>,
  receiptInput?: unknown,
) {
  const raw = rawInput ?? await compactProjectionRaw();
  const receipt = receiptInput ?? await compactReceiptAdmitted(raw);
  const meta = await compactMetadata(raw, receipt);
  const current = parseUiResultsCurrent({
    schema: 'spot.ui_results_current.v1',
    stage1_binding: {
      release_method_version: 'stage1-continuous-v3.0.1', registry_scorer_view_sha256: 'd'.repeat(64),
      selection_schema_raw_sha256: STAGE1_SELECTION_SCHEMA_RAW_SHA256,
      release_self_sha256: STAGE1_V3_RELEASE_SELF_SHA256,
    },
    chain: { stage2_run_id: meta.run_id, stage3_bundle_id: null, stage4_scorecard_set_id: null },
    routes: {
      targets: { manifest_path: 'manifests/targets.json', content_hash: H,
        projection_path: 'stage02/display.json', projection_content_hash: meta.projection_canonical_sha256,
        compact_stage2: meta },
      pathways: { manifest_path: 'manifests/pathways.json', content_hash: H,
        projection_path: 'stage02/display.json', projection_content_hash: meta.projection_canonical_sha256,
        compact_stage2: meta },
    },
  });
  const files: Record<string, string> = {
    'results/stage02/display.json': JSON.stringify(raw),
    [`results/${meta.independent_verifier.receipt_path}`]: JSON.stringify(receipt),
  };
  const fetchText = async (path: string) => {
    if (!(path in files)) throw new Error(`404 ${path}`);
    return files[path];
  };
  return { current, files, fetchText, raw, receipt };
}

function stage2View(result: Awaited<ReturnType<typeof loadProductionProjection>>) {
  return result?.kind === 'stage2' && 'schema_version' in result.view ? result.view : null;
}

describe('compact Stage-2 production loader — all dropdown arrangements', () => {
  it.each(CONDITIONS)('loads arbitrary axes for within-condition %s', async (condition) => {
    const rel = await release();
    const result = await loadProductionProjection('targets', rel.current, rel.fetchText,
      selection('within_condition', [condition]));
    const view = stage2View(result);
    expect(view?.geneArmA.arm_key).toBe(directArmKey('prog_alpha', 'decrease', condition));
    expect(view?.geneArmB.arm_key).toBe(directArmKey('prog_beta', 'decrease', condition));
  });

  const pairs = CONDITIONS.flatMap((from) => CONDITIONS.filter((to) => to !== from).map((to) => [from, to] as const));
  it.each(pairs)('loads ordered temporal %s → %s without endpoint inference', async (from, to) => {
    const rel = await release();
    const result = await loadProductionProjection('pathways', rel.current, rel.fetchText,
      selection('temporal_cross_condition', [from, to]));
    const view = stage2View(result);
    expect(view?.geneArmA.arm_key).toBe(temporalArmKey('prog_alpha', 'decrease', from, to));
    expect(view?.geneArmB.arm_key).toBe(temporalArmKey('prog_beta', 'decrease', from, to));
    expect(view?.pathwayArmA.context.condition).toBe(from);
    expect(view?.pathwayArmB.context.condition).toBe(to);
  });
});

describe('compact Stage-2 production loader — fail-closed attacks', () => {
  it('rejects changed projection bytes and changed receipt bytes', async () => {
    const rel = await release();
    rel.files['results/stage02/display.json'] += ' ';
    expect(await loadProductionProjection('targets', rel.current, rel.fetchText,
      selection('within_condition', ['Rest']))).toBeNull();

    const rel2 = await release();
    rel2.files['results/stage02/display_projection.verification.json'] += ' ';
    expect(await loadProductionProjection('targets', rel2.current, rel2.fetchText,
      selection('within_condition', ['Rest']))).toBeNull();
  });

  it('rejects nested p/q/combined fields even when surrounding route hashes are internally consistent', async () => {
    for (const key of ['p_value', 'qval', 'fdr', 'combined_score', 'balanced_skew']) {
      const raw = await compactProjectionRaw();
      const first = Object.values(raw.arms)[0] as { rows: Record<string, unknown>[] };
      first.rows[0][key] = 0.01;
      const rel = await release(raw, await compactReceiptAdmitted(raw));
      expect(await loadProductionProjection('targets', rel.current, rel.fetchText,
        selection('within_condition', ['Rest']))).toBeNull();
    }
  });

  it('rejects a receipt that no longer admits, a self-hash mismatch, and a missing requested arm', async () => {
    const raw = await compactProjectionRaw();
    const rejected = { ...(await compactReceiptAdmitted(raw)), verdict: 'reject', n_failed: 1, failures: ['row mismatch'] };
    const badReceipt = await release(raw, rejected);
    expect(await loadProductionProjection('targets', badReceipt.current, badReceipt.fetchText,
      selection('within_condition', ['Rest']))).toBeNull();

    const raw2 = await compactProjectionRaw();
    const admittedSelf = raw2.projection_sha256;
    const rel2 = await release(raw2);
    rel2.current.routes.targets!.compact_stage2!.projection_self_sha256 = '9'.repeat(64);
    expect(rel2.current.routes.targets!.compact_stage2!.projection_self_sha256).not.toBe(admittedSelf);
    expect(await loadProductionProjection('targets', rel2.current, rel2.fetchText,
      selection('within_condition', ['Rest']))).toBeNull();

    const raw3 = await compactProjectionRaw();
    delete raw3.arms[directArmKey('prog_alpha', 'decrease', 'Rest')];
    raw3.n_arms -= 1;
    const missing = await release(raw3, await compactReceiptAdmitted(raw3));
    expect(await loadProductionProjection('targets', missing.current, missing.fetchText,
      selection('within_condition', ['Rest']))).toBeNull();
  });

  it('rejects the pre-W3 n_arms-only receipt (no exact projection-subject binding)', async () => {
    const raw = await compactProjectionRaw();
    const rel = await release(raw, await compactReceipt(raw.n_arms)); // n_arms-only: the exposed weakness
    expect(await loadProductionProjection('targets', rel.current, rel.fetchText,
      selection('within_condition', ['Rest']))).toBeNull();
  });

  it('rejects a same-n_arms projection whose arm_value was mutated but reuses the old admitted receipt', async () => {
    const raw = await compactProjectionRaw();
    const oldReceipt = await compactReceiptAdmitted(raw); // subject admits the ORIGINAL bytes
    const arm = Object.values(raw.arms)[0] as { rows: { arm_value: number }[] };
    arm.rows[0].arm_value = arm.rows[0].arm_value + 0.5; // same shape + n_arms, different bytes
    const body: Record<string, unknown> = { ...raw };
    delete body.projection_sha256;
    raw.projection_sha256 = await sha256Hex(canonicalJson(body)); // reseal so the projection itself parses
    const rel = await release(raw, oldReceipt); // metadata re-points to the mutated bytes; receipt is stale
    expect(await loadProductionProjection('targets', rel.current, rel.fetchText,
      selection('within_condition', ['Rest']))).toBeNull();
  });
});
