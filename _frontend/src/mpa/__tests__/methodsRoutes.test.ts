import { describe, expect, it } from 'vitest';
import { notebookHref, traceHref, stageFromSearch, STAGE_VIEWS } from '../methodsRoutes';

describe('per-stage Methods (notebook) + Provenance (trace) routing', () => {
  it('exposes the four downstream stages', () => {
    expect(STAGE_VIEWS).toEqual(['targets', 'pathways', 'drugs', 'pksafety']);
  });

  it('builds a notebook URL with the stage param', () => {
    expect(notebookHref('targets', '')).toBe('01_notebook.html?stage=targets');
  });

  it('builds a trace URL with the stage param', () => {
    expect(traceHref('drugs', '')).toBe('01_trace.html?stage=drugs');
  });

  it('carries the current selection thread + ?demo across the hop', () => {
    const href = notebookHref('pathways', '?selection_id=SEL_1&demo=1');
    const p = new URLSearchParams(href.split('?')[1]);
    expect(href.startsWith('01_notebook.html?')).toBe(true);
    expect(p.get('stage')).toBe('pathways');
    expect(p.get('selection_id')).toBe('SEL_1');
    expect(p.get('demo')).toBe('1');
  });

  it('resolves the stage from the query, rejecting unknown/absent values', () => {
    expect(stageFromSearch('?stage=pksafety')).toBe('pksafety');
    expect(stageFromSearch('?stage=programs')).toBeNull(); // programs has no notebook/trace view
    expect(stageFromSearch('?stage=bogus')).toBeNull();
    expect(stageFromSearch('')).toBeNull();
  });
});
