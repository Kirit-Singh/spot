// Main-canvas editorial firewall. Forbidden interpretation/caveat copy is asserted
// ONLY against <main>, so provenance-drawer text (rendered outside <main>) stays
// allowed. Positive, route-specific assertions guard against a test that passes by
// deleting useful state. Covers empty (default), demo, and research modes.

import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import App from '../App';
import { SELECTION_V3_KEY } from '../repository/source';

const ROUTES = ['stage-2', 'stage-3', 'stage-4'] as const;

/** A minimal, structurally-valid spot.stage01_selection.v3 contract (the sync gate is shallow). */
const selectionV3Raw = {
  schema_version: 'spot.stage01_selection.v3',
  selection_id: 'a1b2c3d4e5f60718',
  question_id: 'q'.repeat(16), // biology-only id; shallow projection shape-checks it present
  analysis_mode: 'within_condition',
  execution_status: 'ready',
  estimator_id: 'within_condition_v1',
  estimator_status: 'available',
  selection_full_sha256: 'f'.repeat(64),
  full_contract_content_sha256: '9'.repeat(64),
  canonical_content: {
    A: { program_id: 'treg_like', score_field: 'treg_like_score', direction: 'low' },
    B: { program_id: 'th1_like', score_field: 'th1_like_score', direction: 'high' },
    conditions: ['Stim48hr'],
    registry_scorer_view_sha256: 'a'.repeat(64),
    source_h5ad_sha256: 'b'.repeat(64),
  },
};

const FORBIDDEN_MAIN = [
  /not production-selectable/i,
  /0\s*(?:of|\/)\s*33/i,
  /cleared the frozen/i,
  /exploratory decision-support/i,
  /not causal(?:ly)? confirm/i,
  /does not (?:confirm|demonstrate)/i,
  /\bcaveat\b|\blimitation\b/i,
  /pathway support\s*·\s*descriptive/i,
  /relation\s*&\s*unit unaltered/i,
  /shown, not collapsed/i,
];

function renderRoute(route: string, opts: { demo?: boolean; research?: boolean } = {}) {
  const q = opts.demo ? '?demo=1' : '';
  window.history.pushState({}, '', `/02_page.html${q}#/${route}`);
  if (opts.research) window.localStorage.setItem(SELECTION_V3_KEY, JSON.stringify(selectionV3Raw));
  render(<App />);
  return screen.getByRole('main');
}

function assertNoForbidden(main: HTMLElement) {
  const text = main.textContent ?? '';
  for (const re of FORBIDDEN_MAIN) expect(text).not.toMatch(re);
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.history.pushState({}, '', '/02_page.html');
});

describe('demo mode — no editorial copy on the populated main canvas', () => {
  for (const route of ROUTES) {
    it(`${route}: main carries none of the forbidden interpretation copy`, () => {
      assertNoForbidden(renderRoute(route, { demo: true }));
    });
  }

  it('stage-2: retains typed states, joint views and the convergent-pathways heading', () => {
    const main = renderRoute('stage-2', { demo: true });
    expect(main).toHaveTextContent(/fixture/);
    expect(main).toHaveTextContent(/significance (?:not_calibrated|calibrated)/);
    expect(main).toHaveTextContent(/not evaluated|opposed|both arms/);
    expect(main).toHaveTextContent('Convergent pathways');
  });

  it('stage-3: retains namespace, desired directions and mechanism evidence states', () => {
    const main = renderRoute('stage-3', { demo: true });
    expect(main).toHaveTextContent(/fixture/);
    expect(main).toHaveTextContent(/desired directions/i);
    expect(main).toHaveTextContent(/not evaluated|missing|mixed|conflicting/);
  });

  it('stage-4: retains delivery, missingness and the NEBPI panel', () => {
    const main = renderRoute('stage-4', { demo: true });
    expect(main).toHaveTextContent(/fixture/);
    expect(main).toHaveTextContent(/Delivery requirement/i);
    expect(main).toHaveTextContent(/not evaluated|missing/);
    expect(main).toHaveTextContent(/NEBPI decision path/i);
  });
});

describe('empty mode (default) — honest scaffold, no fake data, no editorial', () => {
  for (const route of ROUTES) {
    it(`${route}: shows the output shape with no data and no editorial`, () => {
      const main = renderRoute(route);
      assertNoForbidden(main);
      expect(main).toHaveTextContent('no artifact');
      expect(main).toHaveTextContent('awaiting artifact');
      // No fake results on the default canvas.
      expect(within(main).queryByText('GENE_A')).toBeNull();
      expect(within(main).queryByText('COMPOUND_A')).toBeNull();
    });
  }
});

describe('v3 research mode — compact not-generated state, no paragraphs', () => {
  for (const route of ROUTES) {
    it(`${route}: compact not-generated state visible with no editorial prose`, () => {
      const main = renderRoute(route, { research: true });
      assertNoForbidden(main);
      expect(main).toHaveTextContent('analysis not generated');
      expect(main.querySelectorAll('p')).toHaveLength(0);
      expect(main).not.toHaveTextContent(/results appear here|selection context above is real/i);
    });
  }
});

describe('provenance drawer — one gate note and a compact role row', () => {
  function openDrawer(route: string) {
    window.history.pushState({}, '', `/02_page.html?demo=1#/${route}`);
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Methods/ }));
    return screen.getByRole('dialog');
  }

  it('stage-3: states the production-gate/promotion point exactly once (0/33 lives here)', () => {
    const dialog = openDrawer('stage-3');
    expect(within(dialog).queryByText('Promotion')).toBeNull();
    expect(within(dialog).getAllByText('Production gate')).toHaveLength(1);
    expect(within(dialog).getAllByText(/0\s*\/\s*33/)).toHaveLength(1);
  });

  it('renders NO generic "Claude Science role — provenance trace" footer row (only real bound records)', () => {
    const dialog = openDrawer('stage-2');
    expect(within(dialog).queryByText('Claude Science role')).toBeNull();
    expect(within(dialog).queryByText('provenance trace')).toBeNull();
    expect(within(dialog).queryByText(/auditability only|is not evidence/i)).toBeNull();
  });

  it('keeps hashes, sources and CS session/frame fields in provenance', () => {
    const dialog = openDrawer('stage-2');
    expect(within(dialog).getByText('Raw sha256')).toBeInTheDocument();
    expect(within(dialog).getByText('Canonical')).toBeInTheDocument();
    expect(within(dialog).getByText('Public source records')).toBeInTheDocument();
    expect(within(dialog).getByText('CS session')).toBeInTheDocument();
    expect(within(dialog).getByText('CS frame')).toBeInTheDocument();
  });
});
