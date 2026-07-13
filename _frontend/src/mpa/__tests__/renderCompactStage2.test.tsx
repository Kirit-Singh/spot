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
    expect(within(canvas).getAllByText('2 shown')).toHaveLength(2);
    expect(within(canvas).getAllByText('2 ranked')).toHaveLength(2);
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
    const point = within(canvas).getByRole('link', { name: /PROG_ALPHA_INCREASE_1, increase/ });
    fireEvent.focus(point);
    expect(canvas.textContent).toContain('signed shift 0.5');
    expect(canvas.textContent).toContain('rank 1/2');
    expect(canvas.textContent).toContain('rank evidence 0.301');
    const hpa = within(canvas).getAllByRole('link', { name: /HPA/ })[0];
    expect(hpa).toHaveAttribute('href', 'https://www.proteinatlas.org/ENSG10000000111');
    expect(hpa).toHaveAttribute('target', '_blank');
    expect(hpa).toHaveAttribute('rel', expect.stringContaining('noopener'));
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
