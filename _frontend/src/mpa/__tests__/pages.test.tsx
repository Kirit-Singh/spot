import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PAGES } from '../pages';
import type { PageKey } from '../pages';
import { MpaNav } from '../MpaNav';

const byKey = (k: PageKey) => {
  const p = PAGES.find((x) => x.key === k);
  if (!p) throw new Error(`no page ${k}`);
  return p;
};

describe('PAGES — conceptual stage numbering (gate U04)', () => {
  it('Programs is 01', () => {
    expect(byKey('programs').n).toBe('01');
  });

  it('Targets and Pathways are the SAME Stage 2 (both 02, never 03)', () => {
    expect(byKey('targets').n).toBe('02');
    expect(byKey('pathways').n).toBe('02');
    expect(byKey('targets').n).toBe(byKey('pathways').n);
    expect(byKey('pathways').n).not.toBe('03');
  });

  it('Drugs is 03 and PK & Safety is 04 — there is no stage 05', () => {
    expect(byKey('drugs').n).toBe('03');
    expect(byKey('pksafety').n).toBe('04');
    expect(PAGES.some((p) => p.n === '05')).toBe(false);
  });

  it('keeps stable labels, keys and href basenames', () => {
    expect(PAGES.map((p) => p.label)).toEqual(['Programs', 'Targets', 'Pathways', 'Drugs', 'PK & Safety']);
    expect(PAGES.map((p) => p.key)).toEqual(['programs', 'targets', 'pathways', 'drugs', 'pksafety']);
    expect(PAGES.map((p) => p.href)).toEqual([
      'programs.html',
      'targets.html',
      'pathways.html',
      'drugs.html',
      'pksafety.html',
    ]);
  });

  it('every href is a same-origin relative page (no scheme, host or leading slash)', () => {
    for (const p of PAGES) {
      expect(p.href).toMatch(/^[a-z0-9_]+\.html$/);
      expect(p.href).not.toMatch(/^(?:[a-z]+:)?\/\//i); // no protocol / protocol-relative
      expect(p.href.startsWith('/')).toBe(false);
    }
  });
});

describe('MpaNav — renders the numbering with Targets + Pathways grouped in Stage 2', () => {
  it('shows 02 twice (Targets + Pathways), then 03 and 04, with same-origin links', () => {
    render(<MpaNav active="targets" />);
    const nav = screen.getByRole('navigation', { name: /pipeline stages/i });
    expect(within(nav).getAllByText('02')).toHaveLength(2);
    expect(within(nav).getAllByText('03')).toHaveLength(1);
    expect(within(nav).getAllByText('04')).toHaveLength(1);
    // links carry only relative page hrefs (same-origin)
    for (const link of within(nav).getAllByRole('link')) {
      const href = link.getAttribute('href') ?? '';
      expect(href).toMatch(/^[a-z0-9_]+\.html(?:\?|#|$)/);
    }
    // the active step (Targets) is marked
    expect(within(nav).getByText('Targets').closest('[aria-current="page"]')).not.toBeNull();
  });
});
