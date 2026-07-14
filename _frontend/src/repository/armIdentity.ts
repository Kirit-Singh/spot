// Referential target-identity join + desired-direction display disposition for reusable arms.
//
// W5/W11 contract: a bundle keeps immutable target identity ONCE in `base_records`; arm rows
// join to it by `base_key` (or target_id) — NEVER by symbol. This module performs that join
// before any symbol/Ensembl/evidence is rendered. When a bundle carries no `base_records`
// (pre-W5 shape) it falls back to the row's inline identity; it never guesses by symbol.

import type {
  BaseRecord,
  DesiredChange,
  DesiredDirectionDisposition,
} from '../domain/reusableArm';

export interface ResolvedIdentity {
  target_id: string | null;
  target_ensembl: string | null;
  target_symbol: string | null;
}

/** Join a row to its immutable identity by base_key/target_id (never by symbol). */
export function joinRowIdentity(
  bundle: { base_records?: Record<string, BaseRecord> },
  row: { base_key?: string; target_ensembl?: string | null; target_symbol?: string | null },
): ResolvedIdentity {
  const key = row.base_key;
  if (bundle.base_records && key) {
    const rec = bundle.base_records[key];
    if (rec) {
      return { target_id: rec.target_id, target_ensembl: rec.target_ensembl, target_symbol: rec.target_symbol };
    }
    // key present but unresolved in base_records → identity unavailable (do NOT fall back to symbol)
    return { target_id: null, target_ensembl: null, target_symbol: null };
  }
  // pre-W5 inline identity (bundle has no base_records)
  return {
    target_id: null,
    target_ensembl: row.target_ensembl ?? null,
    target_symbol: row.target_symbol ?? null,
  };
}

/**
 * Display disposition of a knockdown effect relative to the desired change. A response in the
 * desired direction reads as `supports_inhibition`; otherwise `opposed`. A null effect is
 * `unavailable`. This NEVER infers pharmacologic reversibility. (`activation_needed` is reserved
 * in the type for the finalized W5/W11 contract.)
 */
export function desiredDirectionDisposition(
  effect: number | null,
  change: DesiredChange,
): DesiredDirectionDisposition {
  if (effect === null) return 'unavailable';
  if (effect === 0) return 'opposed';
  const inDesiredDirection = change === 'decrease' ? effect < 0 : effect > 0;
  return inDesiredDirection ? 'supports_inhibition' : 'opposed';
}
