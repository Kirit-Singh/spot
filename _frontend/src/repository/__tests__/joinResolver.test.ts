// Production join resolver + referential identity + desired-direction disposition.
// Freezes the cross-time join end-to-end at the resolver level (audit acceptance 3 & 4):
// within-condition → two Direct gene arms + condition-matched pathway; temporal → two Temporal
// DiD gene arms + endpoint pathway (A@from, B@to). Identity joins by immutable base_key (never
// symbol); conditionUniverse gates the release conditions.

import { describe, expect, it } from 'vitest';
import { resolveJoinedView } from '../joinResolver';
import { joinRowIdentity, desiredDirectionDisposition } from '../armIdentity';
import { directArmKey, temporalArmKey, pathwayArmKey, convergenceKey } from '../armKey';
import { ConditionUniverseError } from '../joinSemantics';
import type { SelectionV3 } from '../../adapters/selectionV3Adapter';
import type { DirectArmBundle, PathwayArmBundle } from '../../domain/reusableArm';
import type { NativeTemporalArmBundle } from '../../domain/nativeTemporalArm';

const prov = { provenance: {} } as unknown as { provenance: unknown };

function sel(mode: SelectionV3['analysis_mode'], A: SelectionV3['A'], B: SelectionV3['B'], conditions: string[]): SelectionV3 {
  return {
    selection_id: 'a'.repeat(16), question_id: 'q'.repeat(16), analysis_mode: mode, execution_status: 'ready',
    estimator_id: mode === 'within_condition' ? 'within_condition_v1' : 'temporal_cross_condition_v1',
    estimator_status: 'available', A, B, conditions,
    registry_scorer_view_sha256: 'b'.repeat(64), source_h5ad_sha256: 'c'.repeat(64),
    selection_full_sha256: 'd'.repeat(64), full_contract_content_sha256: 'e'.repeat(64), raw: {},
  };
}

const A = { program_id: 'th17_like', direction: 'high' as const }; // away_from_A(high)=decrease
const B = { program_id: 'th1_like', direction: 'high' as const }; //  toward_b(high)=increase
const RELEASE = ['Rest', 'Stim8hr', 'Stim48hr'];

function directBundle(condition: string): DirectArmBundle {
  const kA = directArmKey('th17_like', 'decrease', condition);
  const kB = directArmKey('th1_like', 'increase', condition);
  return {
    ...prov, lane: 'direct', condition, bundle_sha256: 'f'.repeat(64),
    base_records: { BK1: { base_key: 'BK1', target_id: 'ENSG1', target_ensembl: 'ENSG1', target_symbol: 'GENE1' } },
    arms: {
      [kA]: { arm_key: kA, program_id: 'th17_like', desired_change: 'decrease', condition, rows: [{ base_key: 'BK1', target_ensembl: 'X', target_symbol: 'X', effect: -0.4, rank: 1, ontarget_significant: true }] },
      [kB]: { arm_key: kB, program_id: 'th1_like', desired_change: 'increase', condition, rows: [] },
    },
  } as unknown as DirectArmBundle;
}
function temporalBundle(from: string, to: string): NativeTemporalArmBundle {
  const kA = temporalArmKey('th17_like', 'decrease', from, to);
  const kB = temporalArmKey('th1_like', 'increase', from, to);
  const emptyArm = (arm_key: string, program_id: string, desired_change: 'increase' | 'decrease') => ({
    arm_key, program_id, desired_change, from_condition: from, to_condition: to,
    n_targets: 0, n_evaluable: 0, n_ranked: 0, records: [],
    ranking: { path: '', raw_sha256: '', canonical_sha256: '' },
  });
  return {
    schema_version: 'spot.stage02_temporal_arm_bundle.v1', lane: 'temporal', analysis_mode: 'temporal_cross_condition',
    from_condition: from, to_condition: to, bundle_id: 'x', base_records: {},
    verification_ref: 'spot.stage02.temporal.arm.independent_verifier.v1', ...prov,
    arms: { [kA]: emptyArm(kA, 'th17_like', 'decrease'), [kB]: emptyArm(kB, 'th1_like', 'increase') },
  } as unknown as NativeTemporalArmBundle;
}
function pathwayBundle(condition: string, source: string): PathwayArmBundle {
  const kA = pathwayArmKey('th17_like', 'decrease', condition, source);
  const kB = pathwayArmKey('th1_like', 'increase', condition, source);
  return {
    ...prov, lane: 'pathway', condition, source, convergence_ref: convergenceKey(condition, source), bundle_sha256: 'f'.repeat(64),
    arms: {
      [kA]: { arm_key: kA, program_id: 'th17_like', desired_change: 'decrease', condition, source, convergence_ref: convergenceKey(condition, source), records: [] },
      [kB]: { arm_key: kB, program_id: 'th1_like', desired_change: 'increase', condition, source, convergence_ref: convergenceKey(condition, source), records: [] },
    },
  } as unknown as PathwayArmBundle;
}

describe('resolveJoinedView — within-condition (Direct gene arms + condition-matched pathway)', () => {
  it('resolves exactly two Direct gene arms + two condition-matched Pathway arms via desired_change', () => {
    const v = resolveJoinedView(
      sel('within_condition', A, B, ['Rest']),
      { direct: directBundle('Rest'), pathwayByContext: { 'Rest|reactome': pathwayBundle('Rest', 'reactome') } },
      'reactome', RELEASE,
    );
    expect(v.plan.gene_ranking_lane).toBe('direct');
    expect(v.geneArmA?.arm_key).toBe('direct|th17_like|decrease|Rest'); // away_from_A(high)=decrease
    expect(v.geneArmB?.arm_key).toBe('direct|th1_like|increase|Rest'); //  toward_b(high)=increase
    expect(v.pathway_context).toBe('condition_matched');
    expect(v.pathwayArmA?.arm_key).toBe('pathway|th17_like|decrease|Rest|reactome');
  });
});

describe('resolveJoinedView — temporal (Temporal DiD arms + ENDPOINT pathway A@from/B@to)', () => {
  const v = resolveJoinedView(
    sel('temporal_cross_condition', A, B, ['Rest', 'Stim48hr']),
    {
      temporal: temporalBundle('Rest', 'Stim48hr'),
      pathwayByContext: { 'Rest|reactome': pathwayBundle('Rest', 'reactome'), 'Stim48hr|reactome': pathwayBundle('Stim48hr', 'reactome') },
    },
    'reactome', RELEASE,
  );
  it('ranks genes from Temporal DiD arms — never same-time Direct', () => {
    expect(v.plan.gene_ranking_lane).toBe('temporal');
    expect(v.geneArmA?.arm_key).toBe('temporal|th17_like|decrease|Rest|Stim48hr');
    expect((v.geneArmA?.arm_key ?? '').startsWith('direct|')).toBe(false);
  });
  it('uses ENDPOINT pathway contexts: A at from_condition, B at to_condition; label never temporal', () => {
    expect(v.pathway_context).toBe('endpoint_pathway_context');
    expect(v.pathwayArmA?.arm_key).toBe('pathway|th17_like|decrease|Rest|reactome'); // A@from
    expect(v.pathwayArmB?.arm_key).toBe('pathway|th1_like|increase|Stim48hr|reactome'); // B@to
  });
});

describe('resolver gates the release condition universe (authority = release, not --batch-policy)', () => {
  it('rejects a forged/reordered release condition set before resolving', () => {
    expect(() =>
      resolveJoinedView(sel('within_condition', A, B, ['Rest']), { direct: directBundle('Rest') }, 'reactome', ['Stim8hr', 'Rest', 'Stim48hr']),
    ).toThrow(ConditionUniverseError);
  });
});

describe('referential identity join (by base_key, never symbol) + desired-direction disposition', () => {
  it('joins a row to bundle.base_records by base_key, never by symbol', () => {
    const b = directBundle('Rest');
    const row = b.arms['direct|th17_like|decrease|Rest'].rows[0];
    const id = joinRowIdentity(b, row);
    expect(id.target_ensembl).toBe('ENSG1'); // from base_records, not the row's inline 'X'
    expect(id.target_symbol).toBe('GENE1');
  });
  it('an unresolved base_key yields unavailable identity (does not guess by symbol)', () => {
    const b = directBundle('Rest');
    expect(joinRowIdentity(b, { base_key: 'MISSING', target_symbol: 'GENE1' }).target_ensembl).toBeNull();
  });
  it('desired-direction disposition: in-direction supports_inhibition, null unavailable, never reversibility', () => {
    expect(desiredDirectionDisposition(-0.4, 'decrease')).toBe('supports_inhibition');
    expect(desiredDirectionDisposition(0.4, 'decrease')).toBe('opposed');
    expect(desiredDirectionDisposition(null, 'decrease')).toBe('unavailable');
  });
});
