import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { SelectionV3 } from '../../adapters/selectionV3Adapter';
import { parseCompactStage2Projection } from '../../adapters/compactStage2ProjectionAdapter';
import { compactMetadata, compactProjectionRaw, compactReceipt } from '../../test/compactStage2';
import { resolveCompactStage2Selection } from '../../repository/compactStage2Resolver';
import { renderRouteReal } from '../renderReal';

afterEach(cleanup);

const selection: SelectionV3 = {
  selection_id: 'a'.repeat(16), question_id: 'b'.repeat(16), analysis_mode: 'within_condition',
  execution_status: 'ready', estimator_id: 'within_condition_v1', estimator_status: 'available',
  A: { program_id: 'prog_alpha', direction: 'high' }, B: { program_id: 'prog_beta', direction: 'low' },
  conditions: ['Stim48hr'], registry_scorer_view_sha256: 'c'.repeat(64), source_h5ad_sha256: 'd'.repeat(64),
  selection_full_sha256: 'e'.repeat(64), full_contract_content_sha256: 'f'.repeat(64), raw: {},
};

async function view() {
  const raw = await compactProjectionRaw();
  const receipt = await compactReceipt(raw.n_arms);
  return resolveCompactStage2Selection(
    await parseCompactStage2Projection(raw, raw.projection_sha256),
    await compactMetadata(raw, receipt),
    selection,
  );
}

describe('compact Stage-2 route rendering', () => {
  it('renders two separate effect-rank facets plus the producer target tables', async () => {
    const v = await view();
    render(<div data-testid="canvas">{renderRouteReal({ route: 'targets', view: v, admission: 'admitted' })}</div>);
    const canvas = screen.getByTestId('canvas');
    expect(canvas.querySelector('[data-route="targets"]')).toBeTruthy();
    expect(within(canvas).getAllByText('rank')).toHaveLength(2);
    expect(within(canvas).getAllByText('symbol')).toHaveLength(2);
    expect(within(canvas).getAllByText('ensembl')).toHaveLength(2);
    // the arm's context carries the size of the ranking its rows are drawn from
    expect(within(canvas).getAllByText('Stim48hr (2 ranked)')).toHaveLength(2);
    expect(canvas.querySelectorAll('section[aria-label$="effect-rank facet"]')).toHaveLength(2);
    expect(within(canvas).getAllByText('Signed program shift')).toHaveLength(2);
    expect(within(canvas).getAllByText('Rank evidence −log10(rank/N)')).toHaveLength(2);
    expect(canvas.textContent).toContain('PROG_ALPHA_DECREASE_1');
    expect(canvas.textContent).toContain('PROG_BETA_DECREASE_1');
    expect(canvas.textContent).not.toMatch(/disposition|status|combined|balanced|p[_ -]?value|q[_ -]?value|significance/i);
  });

  it('labels the top signed points and exposes exact hover fields plus an official ENSG HPA link', async () => {
    const v = await view();
    render(<div data-testid="canvas">{renderRouteReal({ route: 'targets', view: v, admission: 'admitted' })}</div>);
    const canvas = screen.getByTestId('canvas');
    const point = within(canvas).getByRole('img', { name: /PROG_ALPHA_INCREASE_1, increase/ });
    fireEvent.focus(point);
    expect(canvas.textContent).toContain('signed shift 0.5');
    expect(canvas.textContent).toContain('rank 1/2');
    expect(canvas.textContent).toContain('rank evidence 0.301');
    const hpa = within(canvas).getAllByRole('link', { name: /HPA/ })[0];
    expect(hpa).toHaveAttribute('href', 'https://www.proteinatlas.org/ENSG10000000111');
    expect(hpa).toHaveAttribute('target', '_blank');
    expect(hpa).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('coordinates facet and table: hovering a point marks its row, clicking pins the gene', async () => {
    const v = await view();
    render(<div data-testid="canvas">{renderRouteReal({ route: 'targets', view: v, admission: 'admitted' })}</div>);
    const canvas = screen.getByTestId('canvas');
    const point = within(canvas).getByRole('img', { name: /PROG_ALPHA_DECREASE_1, decrease/ });
    const rowOf = (symbol: string) =>
      [...canvas.querySelectorAll('tbody tr')].find((tr) => tr.textContent?.includes(symbol));

    const row = rowOf('PROG_ALPHA_DECREASE_1');
    expect(row?.getAttribute('data-active')).toBe('false');
    expect(row?.getAttribute('aria-selected')).toBe('false');

    fireEvent.mouseEnter(point); // hover the plot → the producer row for that gene is emphasised
    expect(rowOf('PROG_ALPHA_DECREASE_1')?.getAttribute('data-active')).toBe('true');
    // and ONLY that row — a coordinated highlight, not a blanket one
    expect(canvas.querySelectorAll('tbody tr[data-active="true"]')).toHaveLength(1);

    fireEvent.mouseLeave(point);
    expect(canvas.querySelectorAll('tbody tr[data-active="true"]')).toHaveLength(0);

    fireEvent.click(point); // click → the gene stays pinned across facets and tables
    expect(rowOf('PROG_ALPHA_DECREASE_1')?.getAttribute('aria-selected')).toBe('true');
    expect(rowOf('PROG_ALPHA_DECREASE_1')?.getAttribute('data-active')).toBe('true');
  });

  it('marks a target carried by BOTH selected arms without merging their ranks or values', async () => {
    const v = await view();
    // the same gene ranked in each arm: down in one program, up in the other
    const shared = { target_id: 'ENSG10000000999', target_symbol: 'SHARED_TARGET', rank: 2, arm_value: 0.4 };
    v.geneArmA.rows = [...v.geneArmA.rows, shared];
    v.geneArmB.rows = [...v.geneArmB.rows, { ...shared, rank: 7, arm_value: 0.9 }];
    render(<div data-testid="canvas">{renderRouteReal({ route: 'targets', view: v, admission: 'admitted' })}</div>);
    const canvas = screen.getByTestId('canvas');

    // flagged in both tables, and counted once on the summary
    const marked = [...canvas.querySelectorAll('tbody tr')].filter((tr) =>
      tr.textContent?.includes('SHARED_TARGET'),
    );
    expect(marked).toHaveLength(2);
    for (const row of marked) expect(row.textContent).toContain('both');
    expect(canvas.textContent).toContain('in both arms · 1');

    // …and each arm still reports ITS OWN rank and value — nothing is combined
    expect(marked[0].textContent).toContain('2');
    expect(marked[1].textContent).toContain('7');
    expect(canvas.textContent).not.toMatch(/combined|balanced|overall|merged score/i);
  });

  it('shows the top ten by default and switches BOTH tables to the both-arms subset on toggle', async () => {
    const v = await view();
    // 12 ranked rows per arm on DISJOINT ids, then exactly one gene deliberately carried by both
    const rows = (prefix: string, label: string) =>
      Array.from({ length: 12 }, (_, i) => ({
        target_id: `ENSG${prefix}${String(i).padStart(4, '0')}`,
        target_symbol: `${label}_${i + 1}`,
        rank: i + 1,
        arm_value: 1 - i * 0.05,
      }));
    const SHARED = 'ENSG99999999999';
    v.geneArmA.rows = rows('3000000', 'A_DEC');
    v.geneArmB.rows = rows('4000000', 'B_INC');
    v.geneArmA.rows[1] = { ...v.geneArmA.rows[1], target_id: SHARED }; // rank 2 in arm A
    v.geneArmB.rows[3] = { ...v.geneArmB.rows[3], target_id: SHARED }; // rank 4 in arm B

    render(<div data-testid="canvas">{renderRouteReal({ route: 'targets', view: v, admission: 'admitted' })}</div>);
    const canvas = screen.getByTestId('canvas');
    const bodyRows = () => canvas.querySelectorAll('tbody tr');
    const bodyText = () => [...bodyRows()].map((tr) => tr.textContent).join(' ');

    // default: the top ten of each arm — the producer's 12 rows are filtered for display only
    expect(bodyRows()).toHaveLength(20);
    expect(bodyText()).not.toContain('A_DEC_11');

    fireEvent.click(within(canvas).getAllByRole('button', { name: /^In both/ })[0]);
    // one control drives both tables, so the columns stay comparable
    expect(bodyRows()).toHaveLength(2);
    for (const row of bodyRows()) expect(row.textContent).toContain('both');

    fireEvent.click(within(canvas).getAllByRole('button', { name: /^All/ })[0]);
    expect(bodyRows()).toHaveLength(24); // every emitted row still reachable

    // columns are laid out fixed, not sized to whichever rows happen to be shown, so switching
    // modes (and gaining a scrollbar) cannot reflow them
    for (const table of canvas.querySelectorAll('table')) {
      expect(table.className).toContain('table-fixed');
      expect(table.querySelector('colgroup')).toBeTruthy();
    }
    for (const scroller of canvas.querySelectorAll('table')) {
      expect(scroller.parentElement?.className).toContain('scrollbar-gutter:stable');
    }
  });

  it('keeps a pinned gene visible in every arm that ranks it, even outside the current filter', async () => {
    const v = await view();
    const rows = (prefix: string, label: string) =>
      Array.from({ length: 30 }, (_, i) => ({
        target_id: `ENSG${prefix}${String(i).padStart(4, '0')}`,
        target_symbol: `${label}_${i + 1}`,
        rank: i + 1,
        arm_value: 1 - i * 0.02,
      }));
    const SHARED = 'ENSG99999999999';
    v.geneArmA.rows = rows('3000000', 'A_DEC');
    v.geneArmB.rows = rows('4000000', 'B_INC');
    v.geneArmA.rows[24] = { ...v.geneArmA.rows[24], target_id: SHARED, target_symbol: 'PINME' }; // rank 25
    v.geneArmB.rows[2] = { ...v.geneArmB.rows[2], target_id: SHARED, target_symbol: 'PINME' }; // rank 3

    render(<div data-testid="canvas">{renderRouteReal({ route: 'targets', view: v, admission: 'admitted' })}</div>);
    const canvas = screen.getByTestId('canvas');
    const pinmeRows = () => [...canvas.querySelectorAll('tbody tr')].filter((tr) => tr.textContent?.includes('PINME'));

    // in the top-ten default it is visible only in the arm that ranks it 3rd
    expect(pinmeRows()).toHaveLength(1);

    fireEvent.click(within(canvas).getAllByRole('img', { name: /^PINME,/ })[0]);

    // pinned: now present in BOTH arms — the arm that ranks it 25th re-admits it at its true rank
    const pinned = pinmeRows();
    expect(pinned).toHaveLength(2);
    for (const row of pinned) expect(row.getAttribute('aria-selected')).toBe('true');
    // arm A re-admits it at rank 25 (outside its top ten); arm B already had it at rank 3
    expect(pinned.map((row) => row.querySelector('td')?.textContent)).toEqual(['25', '3']);
  });

  it('binds every displayed row to its typed Ensembl HPA page and keeps the exact producer value', async () => {
    const v = await view();
    render(<div data-testid="canvas">{renderRouteReal({ route: 'targets', view: v, admission: 'admitted' })}</div>);
    const canvas = screen.getByTestId('canvas');
    const row = [...canvas.querySelectorAll('tbody tr')].find((tr) =>
      tr.textContent?.includes('PROG_ALPHA_DECREASE_1'),
    );
    const link = row?.querySelector('a[href^="https://www.proteinatlas.org/"]');
    expect(link).toHaveAttribute('href', 'https://www.proteinatlas.org/ENSG10000000121');
    expect(link?.getAttribute('rel')).toContain('noopener');
    // the cell shows a legible value, but the producer's exact number stays retrievable
    const valueCell = [...(row?.querySelectorAll('td') ?? [])].find((td) => td.hasAttribute('title'));
    expect(valueCell?.getAttribute('title')).toBe('0.5');
  });

  it('omits the optional arm-value column when the producer supplied no values', async () => {
    const v = await view();
    v.geneArmA.rows = v.geneArmA.rows.map((row) => ({ ...row, arm_value: null }));
    v.geneArmB.rows = v.geneArmB.rows.map((row) => ({ ...row, arm_value: null }));
    render(<div data-testid="canvas">{renderRouteReal({ route: 'targets', view: v, admission: 'admitted' })}</div>);
    expect(within(screen.getByTestId('canvas')).queryByText('arm value')).toBeNull();
  });

  it('renders pathway set_id and only producer-present optional columns, never an invented set name/rank', async () => {
    const v = await view();
    render(<div data-testid="canvas">{renderRouteReal({ route: 'pathways', view: v, admission: 'admitted' })}</div>);
    const canvas = screen.getByTestId('canvas');
    expect(canvas.querySelector('[data-route="pathways"]')).toBeTruthy();
    expect(within(canvas).getAllByText('set')).toHaveLength(2);
    expect(within(canvas).getAllByText('native order')).toHaveLength(2);
    expect(canvas.textContent).toContain('reactome:1');
    expect(canvas.textContent).toContain('50 shown');
    expect(canvas.textContent).toContain('51 sets');
    expect(canvas.textContent).toContain('first 50');
    expect(canvas.textContent).not.toMatch(/set name|pathway rank|combined|balanced|p[_ -]?value|q[_ -]?value/i);
  });

  it('omits every optional pathway column when all producer values are null', async () => {
    const v = await view();
    for (const arm of [v.pathwayArmA, v.pathwayArmB]) {
      if (!arm) throw new Error('fixture pathway arm missing');
      arm.rows = arm.rows.map((row) => ({ ...row, enrichment_value: null, target_source_coverage: null,
        global_coverage_disposition: null, n_leading_edge: null, peak_rank: null }));
    }
    render(<div data-testid="canvas">{renderRouteReal({ route: 'pathways', view: v, admission: 'admitted' })}</div>);
    const canvas = screen.getByTestId('canvas');
    for (const header of ['enrichment', 'source coverage', 'disposition', 'leading edge', 'peak rank']) {
      expect(within(canvas).queryByText(header)).toBeNull();
    }
  });
});
