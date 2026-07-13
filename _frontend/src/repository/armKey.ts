// Canonical reusable-arm identity — frozen topology (ROUND4_ADDENDUM.md, Rule 2,
// sha256 fd59ecb6cc099009965fd552bedb0378cfddbf337a7afabde10f7419cfc96c0e).
//
// A program's perturbation effect is computed ONCE per context; the two logical arms
// (`increase` / `decrease`) are exact sign transforms of that one base effect, not two
// experimental estimates. Reuse keys therefore key on the perturbation's DESIRED_CHANGE,
// NEVER on the arm's role (away_from_A / toward_b) and NEVER on the pole's high|low
// direction. Role and pole stay selection metadata and may not alter a cached arm's values.
//
// A pair is a cheap UI JOIN of two independently-verified reusable arms — away_from_A of
// program A + toward_b of program B — with NO combined / balanced / weighted score. The
// release holds 300 logical arm slots (60 direct + 120 temporal + 120 pathway) over 10
// base-portable programs, materialized by 15 content-addressed all-arm bundles.

import type { DirectObjective } from '../domain/stage2RealRun';

export type DesiredChange = 'increase' | 'decrease';
export type PoleDirection = 'high' | 'low';

/**
 * Frozen role × pole → desired_change mapping (re-derived by the verifier):
 *   away_from_A(high)=decrease  away_from_A(low)=increase
 *   toward_b(high)=increase     toward_b(low)=decrease
 * toward_b follows the pole (high→increase); away_from_A takes the opposite.
 */
export function desiredChange(objective: DirectObjective, pole: PoleDirection): DesiredChange {
  const followsPole: DesiredChange = pole === 'high' ? 'increase' : 'decrease';
  if (objective === 'toward_b') return followsPole;
  return followsPole === 'increase' ? 'decrease' : 'increase';
}

/** Direct reusable arm: `direct|program_id|desired_change|condition`. */
export function directArmKey(program_id: string, change: DesiredChange, condition: string): string {
  return `direct|${program_id}|${change}|${condition}`;
}

/** Pathway reusable arm: `pathway|program_id|desired_change|condition|source`. */
export function pathwayArmKey(
  program_id: string,
  change: DesiredChange,
  condition: string,
  source: string,
): string {
  return `pathway|${program_id}|${change}|${condition}|${source}`;
}

/** Temporal reusable arm: `temporal|program_id|desired_change|from|to` (order = DiD direction). */
export function temporalArmKey(
  program_id: string,
  change: DesiredChange,
  from: string,
  to: string,
): string {
  return `temporal|${program_id}|${change}|${from}|${to}`;
}

/**
 * Shared transcriptional-convergence artifact: `convergence|condition|source`. There are 6
 * (3 conditions × 2 sources); convergence depends only on the masked perturbation signatures
 * for a (condition, source), so it is computed ONCE and referenced by its 20 enrichment arms
 * (10 programs × 2 desired_change) — never duplicated per arm. Enrichment arms are keyed with
 * {@link pathwayArmKey} and both desired-change arms are computed independently (no assumed
 * rank antisymmetry between increase and decrease).
 */
export function convergenceKey(condition: string, source: string): string {
  return `convergence|${condition}|${source}`;
}
