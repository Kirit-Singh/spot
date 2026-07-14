// Contract tests freezing the cross-time join semantics + the release condition-universe gate.
// A cross-time selection must NEVER use same-time Direct gene ranks or borrow same-time endpoint
// pathways. No combined score, no longitudinal pathway statistic.

import { describe, expect, it } from 'vitest';
import {
  joinPlan,
  conditionUniverse,
  ConditionUniverseError,
  CANONICAL_CONDITIONS,
} from '../joinSemantics';

const A = { program_id: 'naive_like', direction: 'high' as const };
const B = { program_id: 'checkpoint_hi', direction: 'low' as const };

describe('condition-universe gate (authority = Stage-1 v3 release.selector.conditions, not --batch-policy)', () => {
  it('accepts the exact canonical condition set', () => {
    expect(conditionUniverse(['Rest', 'Stim8hr', 'Stim48hr'])).toEqual(CANONICAL_CONDITIONS);
  });

  it('rejects a forged condition', () => {
    expect(() => conditionUniverse(['Rest', 'Stim8hr', 'StimForged'])).toThrow(ConditionUniverseError);
  });

  it('rejects a missing condition', () => {
    expect(() => conditionUniverse(['Rest', 'Stim8hr'])).toThrow(ConditionUniverseError);
  });

  it('rejects a reordered condition set', () => {
    expect(() => conditionUniverse(['Stim8hr', 'Rest', 'Stim48hr'])).toThrow(ConditionUniverseError);
  });

  it('rejects a non-list (e.g. a --batch-policy string smuggled in)', () => {
    expect(() => conditionUniverse('Rest,Stim8hr,Stim48hr')).toThrow(ConditionUniverseError);
  });
});

describe('within_condition join — two Direct arms + condition-matched Pathway arms', () => {
  const plan = joinPlan({ mode: 'within_condition', A, B, conditions: ['Rest'], source: 'reactome' });

  it('ranks perturbation genes from the DIRECT lane', () => {
    expect(plan.gene_ranking_lane).toBe('direct');
    expect(plan.gene_arm_keys[0].startsWith('direct|')).toBe(true);
    expect(plan.gene_arm_keys).toEqual([
      'direct|naive_like|decrease|Rest', // away_from_A(high)=decrease
      'direct|checkpoint_hi|decrease|Rest', // toward_b(low)=decrease
    ]);
  });

  it('uses condition-matched Pathway arms (both at the selected condition)', () => {
    expect(plan.pathway_context).toBe('condition_matched');
    expect(plan.pathway_arm_keys).toEqual([
      'pathway|naive_like|decrease|Rest|reactome',
      'pathway|checkpoint_hi|decrease|Rest|reactome',
    ]);
  });
});

describe('temporal_cross_condition join — two Temporal DiD arms; no borrowed endpoint pathways', () => {
  const plan = joinPlan({
    mode: 'temporal_cross_condition',
    A,
    B,
    conditions: ['Rest', 'Stim48hr'],
    source: 'reactome',
  });

  it('ranks perturbation genes from the TEMPORAL lane — never same-time Direct ranks', () => {
    expect(plan.gene_ranking_lane).toBe('temporal');
    expect(plan.gene_arm_keys.every((k) => k.startsWith('temporal|'))).toBe(true);
    expect(plan.gene_arm_keys.some((k) => k.startsWith('direct|'))).toBe(false);
    expect(plan.gene_arm_keys).toEqual([
      'temporal|naive_like|decrease|Rest|Stim48hr',
      'temporal|checkpoint_hi|decrease|Rest|Stim48hr',
    ]);
  });

  it('leaves pathway routing unavailable instead of substituting same-time endpoint arms', () => {
    expect(plan.pathway_context).toBe('awaiting_temporal_pathway_bundle');
    expect(plan.pathway_arm_keys).toBeNull();
  });

  it('Stage-3 drug acquisition consumes the selected temporal gene arms', () => {
    // the gene arms Stage-3 consumes are exactly the temporal DiD arms
    expect(plan.gene_arm_keys.every((k) => k.startsWith('temporal|'))).toBe(true);
  });
});

describe('no combined / longitudinal statistic leaks into a join plan', () => {
  it('a plan is exactly two independent gene arms + two pathway arms — no combined key', () => {
    const plan = joinPlan({ mode: 'within_condition', A, B, conditions: ['Rest'], source: 'go_bp' });
    expect(plan.gene_arm_keys).toHaveLength(2);
    expect(plan.pathway_arm_keys).toHaveLength(2);
    const all = [...plan.gene_arm_keys, ...(plan.pathway_arm_keys ?? [])].join(' ');
    expect(all).not.toMatch(/combined|balanced|weighted|longitudinal/i);
  });
});
