// The five per-stage island pages. Each is a separate URL with a deterministic DOM,
// all rendered from the one shared design-system bundle. Programs (programs.html) is
// the migrated hand-written Stage-1 page; the other four are React entries.

export type PageKey = 'programs' | 'targets' | 'pathways' | 'drugs' | 'pksafety';

export interface PageDef {
  key: PageKey;
  n: string;
  label: string;
  href: string;
}

// Conceptual stage numbers: Targets AND Pathways are two VIEWS of the same Stage-2
// gene-perturbation stage, so both carry '02'. Drugs is 03, PK & Safety is 04. There is
// no stage 05 in this pipeline. PageKey + href values are stable (routing depends on them).
export const PAGES: PageDef[] = [
  { key: 'programs', n: '01', label: 'Programs', href: 'programs.html' },
  { key: 'targets', n: '02', label: 'Targets', href: 'targets.html' },
  { key: 'pathways', n: '02', label: 'Pathways', href: 'pathways.html' },
  { key: 'drugs', n: '03', label: 'Drugs', href: 'drugs.html' },
  { key: 'pksafety', n: '04', label: 'PK & Safety', href: 'pksafety.html' },
];

/** Carry the current query (the Stage-1 selection thread) across page navigations. */
export function hrefWithSearch(href: string): string {
  const s = typeof window !== 'undefined' ? window.location.search : '';
  return href + s;
}
