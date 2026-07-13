// Downstream header title = the carried Stage-1 selection, rendered as a contrast,
// e.g. "treg_like lo (at 48 hr) → th1_like hi (at 48 hr)". The Stage-1 page stores the
// AUTHORITATIVE v3 selection artifact in session/localStorage (key
// spot.stage01_selection.v3) on Identify-genes. Falls back to a prompt when nothing is bound.
//
// FAIL-CLOSED, v3-only: the selection is read ONLY from SELECTION_V3_KEY and validated as a
// spot.stage01_selection.v3 contract. There is NO v1 read and NO raw-object fallback — a
// corrupt / absent / wrong-schema selection resolves to null so the header reverts to the
// prompt rather than rendering an unverified contrast.
//   - readStage1Selection()   sync, shallow-shapes the v3 key (schema-gated, NO hash check)
//                             so the header renders synchronously today.
//   - readStage1SelectionV3()  async, runs the full fail-closed parseSelectionV3 verifier
//                             (recomputes hashes, re-derives routing) — the trustworthy path.

import { parseSelectionV3 } from '../adapters/selectionV3Adapter';
import type { SelectionV3 } from '../adapters/selectionV3Adapter';
import { SELECTION_V3_KEY, readReconciledV3Raw } from '../repository/source';

interface Pole {
  display_label?: string;
  direction?: string;
}
export interface Stage1Selection {
  program_a?: Pole;
  program_b?: Pole;
  analysis_condition?: string;
}

const V3_SCHEMA = 'spot.stage01_selection.v3';

/**
 * The reconciled v3 bytes (session + local agree, or exactly one present), JSON-parsed —
 * or null when absent / mismatched / malformed. Routing BOTH reads through the SAME
 * {@link readReconciledV3Raw} rule keeps the header and the repository on ONE selection.
 */
function parseReconciledV3(): unknown {
  const raw = readReconciledV3Raw();
  if (raw === null) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null; // malformed JSON — treat as no selection
  }
}

/** True only for a plain object declaring the authoritative v3 schema_version. */
function isV3(obj: unknown): obj is Record<string, unknown> {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    !Array.isArray(obj) &&
    (obj as Record<string, unknown>).schema_version === V3_SCHEMA
  );
}

/**
 * SYNC shallow-shape of a v3 contract into the header's Stage1Selection. No hash recompute
 * (that is {@link readStage1SelectionV3}); it only projects canonical_content for display.
 * Returns null for anything that is not the v3 schema — NEVER a v1 or raw-object fallback.
 */
export function readStage1Selection(): Stage1Selection | null {
  const obj = parseReconciledV3();
  if (!isV3(obj)) return null; // fail closed: absent / mismatched / wrong schema → no fallback
  const cc = obj.canonical_content;
  if (typeof cc !== 'object' || cc === null) return null;
  const ccr = cc as Record<string, unknown>;
  const conditions = Array.isArray(ccr.conditions) ? ccr.conditions : [];
  return {
    program_a: pole1(ccr.A),
    program_b: pole1(ccr.B),
    analysis_condition: typeof conditions[0] === 'string' ? (conditions[0] as string) : undefined,
  };
}

/** Shallow pole projection: program_id doubles as the display label (v3 carries no label). */
function pole1(v: unknown): Pole | undefined {
  if (typeof v !== 'object' || v === null) return undefined;
  const p = v as Record<string, unknown>;
  return {
    display_label: typeof p.program_id === 'string' ? p.program_id : undefined,
    direction: typeof p.direction === 'string' ? p.direction : undefined,
  };
}

/**
 * ASYNC fail-closed read of the verified v3 selection. Runs {@link parseSelectionV3} (named
 * schema gate + independent hash recompute + routing re-derivation). Returns the verified
 * {@link SelectionV3} or null — NEVER a v1 read, NEVER a raw/forged fallback.
 */
export async function readStage1SelectionV3(): Promise<SelectionV3 | null> {
  const obj = parseReconciledV3();
  if (obj === null) return null;
  try {
    return await parseSelectionV3(obj); // throws on non-v3 / forged / mismatch → null
  } catch {
    return null;
  }
}

const DIR: Record<string, string> = { high: 'hi', low: 'lo' };
const COND: Record<string, string> = { Rest: 'rest', Stim8hr: '8 hr', Stim48hr: '48 hr' };

function pole(p: Pole | undefined, cond: string): string {
  const label = p?.display_label ?? '—';
  const dir = p?.direction ? (DIR[p.direction] ?? p.direction) : '';
  return `${label}${dir ? ' ' + dir : ''}${cond ? ` (at ${cond})` : ''}`;
}

/** Format a selection as the contrast title, or null if it lacks two poles. */
export function contrastTitle(sel: Stage1Selection | null): string | null {
  if (!sel || !sel.program_a || !sel.program_b) return null;
  const cond = sel.analysis_condition
    ? (COND[sel.analysis_condition] ?? sel.analysis_condition.toLowerCase())
    : '';
  return `${pole(sel.program_a, cond)} → ${pole(sel.program_b, cond)}`;
}

export const NO_SELECTION_TITLE = 'Select populations in Programs →';

/** Remove the bridged v3 selection so the downstream header reverts to the prompt. */
export function clearStage1Selection(): void {
  if (typeof window === 'undefined') return;
  for (const store of [window.localStorage, window.sessionStorage]) {
    try {
      store.removeItem(SELECTION_V3_KEY);
    } catch {
      /* ignore */
    }
  }
}
