// Frozen cross-time JOIN semantics (ROUND4_ADDENDUM c4773562 + owner integration rules).
// A selection is realized as a cheap join of two INDEPENDENT reusable arms — never a rerun,
// never a combined/balanced/weighted score, never a longitudinal pathway statistic.
//
//   within_condition       → gene ranking from two DIRECT arms; pathway panels are the two
//                            condition-matched Pathway arms.
//   temporal_cross_condition → gene ranking from two TEMPORAL DiD arms (population-level DiD).
//                            Same-time pathway arms are never substituted for a temporal pathway
//                            result. Pathway routing remains unavailable until an independently
//                            admitted temporal-pathway bundle exists.
// Stage-3 drug acquisition consumes the selected gene arms (temporal arms for a cross-time
// selection). The condition universe is derived independently from the authoritative Stage-1
// v3 release.selector.conditions — NOT from any --batch-policy input.

import { desiredChange, directArmKey, temporalArmKey, pathwayArmKey } from './armKey';
import type { PoleDirection } from './armKey';

/** Canonical condition set, in canonical order. */
export const CANONICAL_CONDITIONS = ['Rest', 'Stim8hr', 'Stim48hr'] as const;

export class ConditionUniverseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ConditionUniverseError';
  }
}

/**
 * Independently derive + validate the condition universe from the Stage-1 v3
 * `release.selector.conditions`. Rejects a forged / missing / reordered condition set — the
 * release is the authority, not a --batch-policy flag.
 */
export function conditionUniverse(releaseConditions: unknown): readonly string[] {
  if (!Array.isArray(releaseConditions)) {
    throw new ConditionUniverseError('release.selector.conditions is missing or not a list');
  }
  const got = releaseConditions.map((c) => String(c));
  if (
    got.length !== CANONICAL_CONDITIONS.length ||
    got.some((c, i) => c !== CANONICAL_CONDITIONS[i])
  ) {
    throw new ConditionUniverseError(
      `release conditions [${got.join(', ')}] are forged / missing / reordered vs [${CANONICAL_CONDITIONS.join(', ')}]`,
    );
  }
  return CANONICAL_CONDITIONS;
}

export interface JoinPole {
  program_id: string;
  direction: PoleDirection;
}

export interface JoinSelectionInput {
  mode: 'within_condition' | 'temporal_cross_condition';
  A: JoinPole;
  B: JoinPole;
  /** 1 condition for within; 2 ordered [from, to] for temporal (order = DiD direction). */
  conditions: string[];
  /** Gene-set source for the pathway panels (e.g. reactome / go_bp). */
  source: string;
}

export interface JoinPlan {
  mode: JoinSelectionInput['mode'];
  /** Which lane's arms drive perturbation-gene ranking (+ Stage-3 drug acquisition). */
  gene_ranking_lane: 'direct' | 'temporal';
  /** The two independent gene arms joined (A, B). No combined arm. */
  gene_arm_keys: [string, string];
  /** Pathway context label. Cross-time selections cannot borrow same-time endpoint pathways. */
  pathway_context: 'condition_matched' | 'awaiting_temporal_pathway_bundle';
  pathway_arm_keys: [string, string] | null;
}

/** Freeze the join: same-time uses Direct gene ranks; cross-time uses Temporal DiD arms. */
export function joinPlan(sel: JoinSelectionInput): JoinPlan {
  const dcA = desiredChange('away_from_A', sel.A.direction);
  const dcB = desiredChange('toward_b', sel.B.direction);

  if (sel.mode === 'within_condition') {
    if (sel.conditions.length !== 1) {
      throw new ConditionUniverseError('within_condition requires exactly 1 condition');
    }
    const cond = sel.conditions[0];
    return {
      mode: sel.mode,
      gene_ranking_lane: 'direct',
      gene_arm_keys: [directArmKey(sel.A.program_id, dcA, cond), directArmKey(sel.B.program_id, dcB, cond)],
      pathway_context: 'condition_matched',
      pathway_arm_keys: [
        pathwayArmKey(sel.A.program_id, dcA, cond, sel.source),
        pathwayArmKey(sel.B.program_id, dcB, cond, sel.source),
      ],
    };
  }

  // temporal_cross_condition
  if (sel.conditions.length !== 2) {
    throw new ConditionUniverseError('temporal_cross_condition requires exactly 2 ordered conditions');
  }
  const [from, to] = sel.conditions;
  return {
    mode: sel.mode,
    gene_ranking_lane: 'temporal',
    gene_arm_keys: [
      temporalArmKey(sel.A.program_id, dcA, from, to),
      temporalArmKey(sel.B.program_id, dcB, from, to),
    ],
    pathway_context: 'awaiting_temporal_pathway_bundle',
    pathway_arm_keys: null,
  };
}
