// Downstream header title = the carried Stage-1 selection, rendered as a contrast,
// e.g. "Naïve-like hi (at rest) → Activated hi (at rest)". The Stage-1 page stores the
// selection artifact in session/localStorage (key spot.stage01_selection.v1) on
// Identify-genes. Falls back to a prompt when nothing is bound.
//
// RECONCILED with the v3 shell adapter: readStage1Selection() resolves the stored
// selection through parseSelection() — the SAME validated `research_only` path the body
// binds to — so the header contrast agrees with the body and a malformed / wrong-namespace
// selection is excluded. The unvalidated raw object is kept as a fallback so we never
// regress "show the carried selection" for a selection the strict adapter would reject.
// The storage key itself is imported (SELECTION_KEY) — one source of truth, not a literal.

import { parseSelection } from '../adapters/selectionAdapter';
import { SELECTION_KEY } from '../repository/source';

interface Pole {
  display_label?: string;
  direction?: string;
}
export interface Stage1Selection {
  program_a?: Pole;
  program_b?: Pole;
  analysis_condition?: string;
}

/**
 * Read the selection the Stage-1 page bridged via storage (session/local hold identical
 * content — the frozen page writes both). PRIMARY: resolve through the shell's validated
 * `research_only` adapter so the header agrees with the body. FALLBACK: the unvalidated
 * raw object, so a selection the strict adapter rejects still renders a contrast rather
 * than silently vanishing from the header.
 */
export function readStage1Selection(): Stage1Selection | null {
  if (typeof window === 'undefined') return null;
  for (const store of [window.sessionStorage, window.localStorage]) {
    let raw: string | null = null;
    try {
      raw = store.getItem(SELECTION_KEY);
    } catch {
      continue; // unreadable store — try the next
    }
    if (!raw) continue;
    let obj: unknown;
    try {
      obj = JSON.parse(raw);
    } catch {
      continue; // malformed JSON — treat as no selection in this store
    }
    try {
      return parseSelection(obj, 'research_only'); // validated adapter path
    } catch {
      return obj as Stage1Selection; // fallback: unvalidated raw object
    }
  }
  return null;
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

/** Remove the bridged selection so the downstream header reverts to the prompt. */
export function clearStage1Selection(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(SELECTION_KEY);
  } catch {
    /* ignore */
  }
  try {
    window.sessionStorage.removeItem(SELECTION_KEY);
  } catch {
    /* ignore */
  }
}
