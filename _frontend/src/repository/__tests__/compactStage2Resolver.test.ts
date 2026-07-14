import { describe, expect, it } from 'vitest';
import type { SelectionV3 } from '../../adapters/selectionV3Adapter';
import { parseCompactStage2Projection } from '../../adapters/compactStage2ProjectionAdapter';
import { resolveCompactStage2Selection } from '../compactStage2Resolver';
import { directArmKey, pathwayArmKey, temporalArmKey } from '../armKey';
import { compactMetadata, compactProjectionRaw, compactReceipt, CONDITIONS } from '../../test/compactStage2';

function selection(
  mode: SelectionV3['analysis_mode'],
  conditions: string[],
  a = 'prog_alpha',
  da: 'high' | 'low' = 'high',
  b = 'prog_beta',
  db: 'high' | 'low' = 'high',
): SelectionV3 {
  return {
    selection_id: 'a'.repeat(16), question_id: 'b'.repeat(16), analysis_mode: mode,
    execution_status: 'ready', estimator_id: mode === 'within_condition' ? 'within_condition_v1' : 'temporal_cross_condition_v1',
    estimator_status: 'available', A: { program_id: a, direction: da }, B: { program_id: b, direction: db },
    conditions, registry_scorer_view_sha256: 'c'.repeat(64), source_h5ad_sha256: 'd'.repeat(64),
    selection_full_sha256: 'e'.repeat(64), full_contract_content_sha256: 'f'.repeat(64), raw: {},
  };
}

async function release() {
  const raw = await compactProjectionRaw();
  const receipt = await compactReceipt(Object.keys(raw.arms).length);
  return { projection: await parseCompactStage2Projection(raw), metadata: await compactMetadata(raw, receipt) };
}

describe('resolveCompactStage2Selection — arbitrary axes and every condition arrangement', () => {
  it.each(CONDITIONS)('binds an arbitrary within-condition pair at %s by exact derived keys', async (condition) => {
    const { projection, metadata } = await release();
    const view = resolveCompactStage2Selection(projection, metadata, selection('within_condition', [condition], 'prog_beta', 'low', 'prog_alpha', 'low'));
    expect(view.geneArmA.arm_key).toBe(directArmKey('prog_beta', 'increase', condition));
    expect(view.geneArmB.arm_key).toBe(directArmKey('prog_alpha', 'decrease', condition));
    expect(view.effectRankFacets[0].program_id).toBe('prog_beta');
    expect(view.effectRankFacets[0].increase.arm_key).toBe(directArmKey('prog_beta', 'increase', condition));
    expect(view.effectRankFacets[0].decrease.arm_key).toBe(directArmKey('prog_beta', 'decrease', condition));
    expect(view.effectRankFacets[1].program_id).toBe('prog_alpha');
    expect(view.pathwayArmA?.arm_key).toBe(pathwayArmKey('prog_beta', 'increase', condition, 'go_bp'));
    expect(view.pathwayArmB?.arm_key).toBe(pathwayArmKey('prog_alpha', 'decrease', condition, 'go_bp'));
    expect(view.pathway_context).toBe('condition_matched');
  });

  const orderedPairs = CONDITIONS.flatMap((from) => CONDITIONS.filter((to) => to !== from).map((to) => [from, to] as const));
  it.each(orderedPairs)('binds temporal target arms %s → %s without borrowing endpoint pathways', async (from, to) => {
    const { projection, metadata } = await release();
    const view = resolveCompactStage2Selection(projection, metadata, selection('temporal_cross_condition', [from, to]));
    expect(view.geneArmA.arm_key).toBe(temporalArmKey('prog_alpha', 'decrease', from, to));
    expect(view.geneArmB.arm_key).toBe(temporalArmKey('prog_beta', 'increase', from, to));
    expect(view.effectRankFacets[0].increase.arm_key).toBe(temporalArmKey('prog_alpha', 'increase', from, to));
    expect(view.effectRankFacets[0].decrease.arm_key).toBe(temporalArmKey('prog_alpha', 'decrease', from, to));
    expect(view.pathwayArmA).toBeNull();
    expect(view.pathwayArmB).toBeNull();
    expect(view.pathway_context).toBe('awaiting_temporal_pathway_bundle');
    expect(() => resolveCompactStage2Selection(
      projection, metadata, selection('temporal_cross_condition', [from, to]), 'pathways',
    )).toThrow(/awaiting_temporal_pathway_bundle/);
  });

  it('resolves targets without requiring pathway arms, while the pathways route still fails closed', async () => {
    const { projection, metadata } = await release();
    for (const [key, arm] of Object.entries(projection.arms)) {
      if (arm.lane === 'pathway') delete projection.arms[key];
    }
    const sel = selection('within_condition', ['Rest']);
    const targetView = resolveCompactStage2Selection(projection, metadata, sel, 'targets');
    expect(targetView.geneArmA.arm_key).toBe(directArmKey('prog_alpha', 'decrease', 'Rest'));
    expect(targetView.pathwayArmA).toBeNull();
    expect(() => resolveCompactStage2Selection(projection, metadata, sel, 'pathways')).toThrow(/pathway arm/);
  });

  it('fails closed when any exact requested arm is absent; it never substitutes another program or condition', async () => {
    const { projection, metadata } = await release();
    delete projection.arms[directArmKey('prog_alpha', 'decrease', 'Rest')];
    expect(() => resolveCompactStage2Selection(projection, metadata, selection('within_condition', ['Rest']))).toThrow(/no requested arm/);
  });

  it('rejects a condition outside the explicit release metadata', async () => {
    const { projection, metadata } = await release();
    expect(() => resolveCompactStage2Selection(projection, metadata, selection('within_condition', ['Unknown']))).toThrow(/outside/);
  });

  it('rejects unrelated projection arms outside the explicit condition/source axes', async () => {
    const first = await release();
    const direct = first.projection.arms[directArmKey('prog_alpha', 'increase', 'Rest')];
    if (direct.lane !== 'direct') throw new Error('test fixture lane mismatch');
    direct.context = { condition: 'Unknown' };
    expect(() => resolveCompactStage2Selection(first.projection, first.metadata,
      selection('within_condition', ['Rest']))).toThrow(/condition axis/);

    const second = await release();
    const path = second.projection.arms[pathwayArmKey('prog_alpha', 'increase', 'Rest', 'go_bp')];
    if (path.lane !== 'pathway') throw new Error('test fixture lane mismatch');
    path.context = { condition: 'Rest', gene_set_source: 'unknown_source' };
    expect(() => resolveCompactStage2Selection(second.projection, second.metadata,
      selection('within_condition', ['Rest']))).toThrow(/pathway-source axis/);
  });
});
