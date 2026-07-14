import { render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SelectionV3 } from '../../adapters/selectionV3Adapter';
import { resolveDevelopmentRealArtifact } from '../devRealAdapter';
import { renderDevelopmentReal } from '../devRealRender';
import pathwaysRest from '../../../public/results/dev-real/pathways.Rest.json?raw';
import pathwaysStim8 from '../../../public/results/dev-real/pathways.Stim8hr.json?raw';
import drugsRest from '../../../public/results/dev-real/drugs.Rest.json?raw';
import drugsStim8 from '../../../public/results/dev-real/drugs.Stim8hr.json?raw';
import pkRest from '../../../public/results/dev-real/pksafety.Rest.json?raw';
import pkStim8 from '../../../public/results/dev-real/pksafety.Stim8hr.json?raw';

const state = vi.hoisted(() => ({ selection: null as SelectionV3 | null }));

vi.mock('../contrastTitle', async (load) => {
  const actual = await load<typeof import('../contrastTitle')>();
  return { ...actual, readStage1SelectionV3: vi.fn(async () => state.selection) };
});

function selection(condition: string, mode: SelectionV3['analysis_mode'] = 'within_condition'): SelectionV3 {
  return {
    selection_id: 's', question_id: 'q', analysis_mode: mode, execution_status: 'ready',
    estimator_id: 'e', estimator_status: 'available',
    A: { program_id: 'treg_like', direction: 'high' },
    B: { program_id: 'th1_like', direction: 'high' },
    conditions: mode === 'within_condition' ? [condition] : [condition, condition === 'Rest' ? 'Stim8hr' : 'Rest'],
    registry_scorer_view_sha256: '', source_h5ad_sha256: '', selection_full_sha256: '',
    full_contract_content_sha256: '', raw: {},
  };
}

const artifacts: Record<string, string> = {
  'pathways.Rest.json': pathwaysRest,
  'pathways.Stim8hr.json': pathwaysStim8,
  'drugs.Rest.json': drugsRest,
  'drugs.Stim8hr.json': drugsStim8,
  'pksafety.Rest.json': pkRest,
  'pksafety.Stim8hr.json': pkStim8,
};

function fixture(name: string): string { return artifacts[name] ?? ''; }

beforeEach(() => {
  state.selection = selection('Rest');
  vi.stubGlobal('fetch', vi.fn(async (path: string) => {
    const name = path.replace('results/dev-real/', '');
    return artifacts[name]
      ? new Response(fixture(name), { status: 200 })
      : new Response('', { status: 404 });
  }));
});

afterEach(() => vi.unstubAllGlobals());

describe('direct real Rest/Stim8 loader', () => {
  it('loads all three exact Rest artifacts and keeps them development-typed', async () => {
    for (const route of ['pathways', 'drugs', 'pksafety'] as const) {
      const result = await resolveDevelopmentRealArtifact(route);
      expect(result?.route).toBe(route);
      expect(result?.admission).toBe('development');
    }
  });

  it('loads Stim8 and pairs supported temporal endpoints; stale unsupported storage falls back to the visible review context', async () => {
    state.selection = selection('Stim8hr');
    expect((await resolveDevelopmentRealArtifact('pathways'))?.route).toBe('pathways');
    state.selection = selection('Rest', 'temporal_cross_condition');
    const temporal = await resolveDevelopmentRealArtifact('pathways');
    expect(temporal?.route).toBe('pathways');
    expect(temporal?.context).toMatchObject({ conditionA: 'Rest', conditionB: 'Stim8hr', analysisMode: 'endpoint_comparison' });
    if (!temporal || temporal.route !== 'pathways') throw new Error('temporal endpoints did not resolve');
    expect(temporal.artifact.arms.map((arm) => arm.arm_key)).toEqual([
      'pathway|treg_like|decrease|Rest|go_bp',
      'pathway|th1_like|increase|Stim8hr|go_bp',
    ]);
    state.selection = selection('Stim48hr');
    expect((await resolveDevelopmentRealArtifact('drugs'))?.context).toMatchObject({ conditionA: 'Rest', conditionB: 'Stim8hr' });
    state.selection = { ...selection('Rest'), A: { program_id: 'naive_like', direction: 'high' } };
    expect((await resolveDevelopmentRealArtifact('drugs'))?.context).toMatchObject({ conditionA: 'Rest', conditionB: 'Stim8hr' });
  });

  it('shows the Rest to Stim8 endpoint comparison when review storage is empty', async () => {
    state.selection = null;
    const pathways = await resolveDevelopmentRealArtifact('pathways');
    expect(pathways?.context).toMatchObject({ conditionA: 'Rest', conditionB: 'Stim8hr', analysisMode: 'endpoint_comparison' });
    const pk = await resolveDevelopmentRealArtifact('pksafety');
    if (!pk || pk.route !== 'pksafety') throw new Error('PK endpoints did not resolve');
    expect(pk.artifact.candidates.map((candidate) => candidate.moiety_name)).toEqual([
      'IDELALISIB', 'LENIOLISIB', 'VADADUSTAT', 'ISTRADEFYLLINE',
    ]);
  });

  it('renders independent pathway columns with explicit truncation', async () => {
    const result = await resolveDevelopmentRealArtifact('pathways');
    if (!result || result.route !== 'pathways') throw new Error('pathways did not resolve');
    const view = render(renderDevelopmentReal(result, new Map([['treg_like', 'Treg-like'], ['th1_like', 'Th1-like']])));
    expect(view.getAllByText(/GO-BP · 100 of/)).toHaveLength(2);
    expect(view.getByText('Treg-like decrease')).toBeInTheDocument();
    expect(view.getByText('Th1-like increase')).toBeInTheDocument();
    expect(view.container.textContent).not.toMatch(/combined|balanced|weighted/i);
  });

  it('puts CRISPRi-aligned drug links before visibly opposed links', async () => {
    const result = await resolveDevelopmentRealArtifact('drugs');
    if (!result || result.route !== 'drugs') throw new Error('drugs did not resolve');
    const view = render(renderDevelopmentReal(result));
    const body = view.container.textContent ?? '';
    expect(body).toContain('CHEMBL_37');
    expect(body).toContain('CRISPRi-aligned');
    expect(body).toContain('opposed');
    expect(body.indexOf('CRISPRi-aligned')).toBeLessThan(body.indexOf('opposed'));
  });

  it('renders sourced PK properties, explicit CNS-MPO completeness, and acquisition counts', async () => {
    const result = await resolveDevelopmentRealArtifact('pksafety');
    if (!result || result.route !== 'pksafety') throw new Error('PK did not resolve');
    const view = render(renderDevelopmentReal(result));
    expect(view.getAllByText('3/6 · MW, TPSA, HBD').length).toBe(3);
    expect(view.getAllByText('not evaluated').length).toBe(3);
    expect(view.container.textContent).not.toContain('CNS-MPOunknown');
    expect(view.getByText(/^3 acquired$/)).toBeInTheDocument();
    expect(view.container.textContent).not.toMatch(/rank|score/i);
  });

  it('labels cross-condition endpoint comparisons and exposes the shared-molecule filter', async () => {
    state.selection = selection('Rest', 'temporal_cross_condition');
    const result = await resolveDevelopmentRealArtifact('drugs');
    if (!result || result.route !== 'drugs') throw new Error('drugs did not resolve');
    const view = render(renderDevelopmentReal(result));
    expect(view.getByText('Endpoint comparison')).toBeInTheDocument();
    expect(view.getByRole('button', { name: 'In both · 0' })).toBeDisabled();
    expect(view.getByRole('button', { name: 'All' })).toBeEnabled();
  });

  it('serves no machine-local paths or inferential keys', () => {
    for (const route of ['pathways', 'drugs', 'pksafety']) {
      for (const condition of ['Rest', 'Stim8hr']) {
        const raw = fixture(`${route}.${condition}.json`);
        expect(raw).not.toMatch(/\/home\/tcelab|\/Users\/|\/mnt\/|file:\/\//);
        const keys: string[] = [];
        const walk = (value: unknown) => {
          if (Array.isArray(value)) return value.forEach(walk);
          if (value && typeof value === 'object') Object.entries(value).forEach(([key, child]) => { keys.push(key); walk(child); });
        };
        walk(JSON.parse(raw));
        expect(keys.join('\n')).not.toMatch(/(^|_)(p|q)(_?val(?:ue)?|_?value)?($|_)|fdr|signific/i);
      }
    }
  });
});
