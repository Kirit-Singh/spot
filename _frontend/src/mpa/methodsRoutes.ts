// Routing pattern for the per-stage Methods (notebook) and Provenance (trace) views.
//
// Each downstream stage links to two dedicated routed pages — `01_notebook.html` (the
// analysis Methods view) and `01_trace.html` (the content-addressed provenance trace) —
// carrying the current selection thread + ?demo across the hop via a `stage` param. These
// are navigation URLs only: no banners, no topology counts, no editorial badges.

import type { PageKey } from './pages';

/** The four downstream stages that expose Methods + Provenance views. */
export type StageView = Exclude<PageKey, 'programs'>;

export const STAGE_VIEWS: readonly StageView[] = ['targets', 'pathways', 'drugs', 'pksafety'];

const NOTEBOOK = '01_notebook.html';
const TRACE = '01_trace.html';

function currentSearch(): string {
  return typeof window !== 'undefined' ? window.location.search : '';
}

/** Merge `stage` into the current query (preserving selection thread + ?demo), stable order. */
function withStage(base: string, stage: StageView, search: string): string {
  const p = new URLSearchParams(search);
  p.set('stage', stage);
  const q = p.toString();
  return q ? `${base}?${q}` : base;
}

/** Methods (notebook) URL for a stage. */
export function notebookHref(stage: StageView, search: string = currentSearch()): string {
  return withStage(NOTEBOOK, stage, search);
}

/** Provenance (trace) URL for a stage. */
export function traceHref(stage: StageView, search: string = currentSearch()): string {
  return withStage(TRACE, stage, search);
}

/** Which stage a notebook/trace page is showing; null when absent/unknown. */
export function stageFromSearch(search: string = currentSearch()): StageView | null {
  const s = new URLSearchParams(search).get('stage');
  return STAGE_VIEWS.includes(s as StageView) ? (s as StageView) : null;
}
