// The five per-stage island pages. Each is a separate URL with a deterministic DOM,
// all rendered from the one shared design-system bundle. Programs (01_page.html) is
// the migrated hand-written Stage-1 page; the other four are React entries.

export type PageKey = 'programs' | 'targets' | 'pathways' | 'drugs' | 'pksafety';

export interface PageDef {
  key: PageKey;
  n: string;
  label: string;
  href: string;
}

export const PAGES: PageDef[] = [
  { key: 'programs', n: '01', label: 'Programs', href: '01_page.html' },
  { key: 'targets', n: '02', label: 'Targets', href: 'targets.html' },
  { key: 'pathways', n: '03', label: 'Pathways', href: 'pathways.html' },
  { key: 'drugs', n: '04', label: 'Drugs', href: 'drugs.html' },
  { key: 'pksafety', n: '05', label: 'PK & Safety', href: 'pksafety.html' },
];

/** Carry the current query (selection thread + ?demo) across page navigations. */
export function hrefWithSearch(href: string): string {
  const s = typeof window !== 'undefined' ? window.location.search : '';
  return href + s;
}

/** Explicit demo gate: synthetic data renders only when ?demo=1 is present. */
export function isDemoGate(): boolean {
  if (typeof window === 'undefined') return false;
  return new URLSearchParams(window.location.search).get('demo') === '1';
}
