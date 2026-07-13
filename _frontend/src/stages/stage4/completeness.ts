// Evidence-completeness helper for Stage-4 sorting. Counts fields that carry a
// real, present value (measured / calculated / label-derived) — missing and
// not-evaluated do not count and are never treated as zero.

import type { MeasurementState } from '../../domain/common';

export function completenessOf(states: MeasurementState[]): { present: number; total: number } {
  const present = states.filter(
    (s) => s === 'measured' || s === 'calculated' || s === 'label_derived',
  ).length;
  return { present, total: states.length };
}
