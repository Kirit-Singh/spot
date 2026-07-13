// Valid-selection arithmetic for the generic release (frozen — ROUND4_ADDENDUM.md Rule 2 +
// the topology correction). This is the SELECTION space (ordered A→B tuples a user may
// pick), distinct from the 300 reusable ARM slots. A selection is realized as a cheap UI
// join of two reusable arms; it is never a rerun.
//
// With `n` admitted programs there are `n * 2` states per condition (program × pole
// high|low). Ordered selections:
//   · within_condition: 3 conditions × states × (states − 1)   — exclude the identical tuple
//   · temporal:         6 ordered condition pairs × states × states  — same state is a VALID
//                        cross-timepoint comparison, so it is NOT excluded here
// For n=10 this is 1,140 + 2,400 = 3,540 (NOT 5,400 — the naive states² × contexts count).
//
// `n` MUST be derived from the v3 generic release / scorer-view and bound to its hash, never
// from the legacy stage01_program_registry.json (both currently yield 10, but only the
// scorer-view is authoritative).

export const POLES = ['high', 'low'] as const;
export type PoleDirection = (typeof POLES)[number];

export const WITHIN_CONDITIONS = ['Rest', 'Stim8hr', 'Stim48hr'] as const;

/** Ordered condition pairs for temporal (3 × 2 = 6). */
export const N_ORDERED_TEMPORAL_PAIRS = WITHIN_CONDITIONS.length * (WITHIN_CONDITIONS.length - 1);

/** States (program × pole) available per condition. */
export function statesPerCondition(nPrograms: number): number {
  return nPrograms * POLES.length;
}

/** Ordered within-condition selections, excluding the identical (program+pole+condition) tuple. */
export function withinConditionSelectionCount(nPrograms: number): number {
  const s = statesPerCondition(nPrograms);
  return WITHIN_CONDITIONS.length * s * (s - 1);
}

/** Ordered temporal selections; same program+pole across DIFFERENT timepoints is valid. */
export function temporalSelectionCount(nPrograms: number): number {
  const s = statesPerCondition(nPrograms);
  return N_ORDERED_TEMPORAL_PAIRS * s * s;
}

export function totalValidSelections(nPrograms: number): number {
  return withinConditionSelectionCount(nPrograms) + temporalSelectionCount(nPrograms);
}

/** One pole of a selection: a program at a pole in a condition. */
export interface SelectionState {
  program_id: string;
  direction: PoleDirection;
  condition: string;
}

/**
 * The exact-pole refusal (identical selection): refuse ONLY when program AND pole AND
 * condition are all identical. Same program+pole across different conditions is a valid
 * (temporal) comparison, not a refusal.
 */
export function isExactPoleRefusal(a: SelectionState, b: SelectionState): boolean {
  return a.program_id === b.program_id && a.direction === b.direction && a.condition === b.condition;
}
