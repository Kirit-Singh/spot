// The RESOLVED Methods & provenance drawer, on each downstream tab, must render all SIX numbered
// sections — 1 Data source · 2 estimand · 3 masks/QC · 4 Upstream model · 5 Method · 6 Provenance
// & status — with sections 2–5 carrying REAL bound content, and the drawer bound to the SELECTION
// the page is actually carrying.
//
// This is the regression for the live-deploy drift: a stale bundle rendered a thinner drawer than the
// source does. The fix belongs in the DEPLOY (rebuild), so this test pins what a CLEAN build owes:
// six sections, none of 2–5 hollow, opened in-page (no navigation to a methods page).
//
// "Nonempty" is asserted on the step BODY minus its heading — a step that renders only its <h4> and
// omits every DefRow (a null definition field) is exactly the hollow section this must catch.
// "Selection-bound" is asserted against the verified v3 actually in storage: its selection_id,
// question_id, and BOTH poles with their OWN conditions.

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { StageIsland } from '../StageIsland';
import type { PageKey } from '../pages';
import { SELECTION_V3_KEY } from '../../repository/source';
import { canonicalJson, sha256Hex } from '../../stage1/canonical';
import { deriveExecutionStatus } from '../../stage1/selectionV3';
import { deriveQuestionId } from '../../stage1/questionId';

const PROGRAMS = [
  { program_id: 'prog_alpha', display_label: 'Alpha' },
  { program_id: 'prog_beta', display_label: 'Beta' },
];

const A = { program_id: 'prog_alpha', direction: 'low' as const };
const B = { program_id: 'prog_beta', direction: 'high' as const };
const CONDITIONS = ['Stim8hr', 'Stim48hr']; // temporal, so the per-pole binding is visible

/** A verified spot.stage01_selection.v3 (real recomputed hashes) — the selection the drawer binds. */
async function buildV3(): Promise<Record<string, unknown>> {
  const mode = 'temporal_cross_condition';
  const cc: Record<string, unknown> = {
    A: { program_id: A.program_id, score_field: `${A.program_id}_score`, direction: A.direction },
    B: { program_id: B.program_id, score_field: `${B.program_id}_score`, direction: B.direction },
    analysis_mode: mode,
    combined_objective: null,
    conditions: CONDITIONS,
    dataset_id: 'marson2025_gwcd4_perturbseq',
    donor_scope: 'all',
    effect_universe_id: 'eu',
    poles_separate: true,
    registry_scorer_view_sha256: 'a'.repeat(64),
    source_h5ad_sha256: 'b'.repeat(64),
    source_hf_revision: 'rev1',
    stage1_method_version: 'stage1-continuous-v3.0.1',
  };
  const selFull = await sha256Hex(canonicalJson(cc));
  const contract: Record<string, unknown> = {
    schema_version: 'spot.stage01_selection.v3',
    selection_origin: 'user_selected',
    execution_status: deriveExecutionStatus(mode, 'available', 'available', 'available'),
    analysis_mode: mode,
    estimator_id: 'temporal_cross_condition_v1',
    estimator_status: 'available',
    selection_id: selFull.slice(0, 16),
    selection_full_sha256: selFull,
    canonical_content: cc,
    poles: {
      A: { program_id: A.program_id, direction: A.direction, effect_projection_status: 'available', n_measured: 5, n_panel_in_effect_universe: 5, n_control_in_effect_universe: 5, reason_codes: [] },
      B: { program_id: B.program_id, direction: B.direction, effect_projection_status: 'available', n_measured: 4, n_panel_in_effect_universe: 4, n_control_in_effect_universe: 4, reason_codes: [] },
    },
    trust_bindings: { validation_raw_sha256: 'c'.repeat(64) },
    provenance_bindings: { primary_registry_v3_raw_sha256: 'd'.repeat(64) },
    historical_validation_provenance: { kind: 'frozen', selectability_v3_raw_sha256: 'e'.repeat(64), active_gate: false },
    question_id: await deriveQuestionId(A, B, CONDITIONS, mode),
  };
  contract.full_contract_content_sha256 = await sha256Hex(canonicalJson(contract));
  return contract;
}

const TABS: [PageKey, string][] = [
  ['targets', 'Targets'],
  ['pathways', 'Pathways'],
  ['drugs', 'Drugs'],
  ['pksafety', 'PK & Safety'],
];

/** The six sections a resolved drawer owes, 1–5 under methods and 6 under provenance. */
const METHODS_STEPS = ['1', '2', '3', '4', '5'];
const PROVENANCE_STEP = '6';

/** A step's content with its heading removed — what is left when the <h4> is not counted. */
function stepContent(dialog: HTMLElement, n: string): string {
  const step = dialog.querySelector(`[data-step="${n}"]`);
  expect(step, `step ${n} must render`).toBeTruthy();
  const body = step!.querySelector('[data-step-body]') as HTMLElement;
  const clone = body.cloneNode(true) as HTMLElement;
  clone.querySelector('h4')?.remove();
  return (clone.textContent ?? '').trim();
}

/** Open the drawer only once the ASYNC method-definition manifest has resolved into it (never the
 *  pre-resolution fallback — that would assert on a thinner, unbound drawer). */
async function openResolvedDrawer(): Promise<HTMLElement> {
  await waitFor(() => {
    fireEvent.click(screen.getByRole('button', { name: /Methods & provenance/i }));
    const d = screen.getByRole('dialog');
    // step 5 carries the bound method_id — its presence proves the real manifest resolved
    expect(d.querySelector('[data-step="5"]')).toBeTruthy();
    expect(stepContent(d, '5').length).toBeGreaterThan(0);
  });
  return screen.getByRole('dialog');
}

describe('resolved Methods drawer — six sections, 2–5 nonempty, selection-bound', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/02_page.html'); // production, no demo
    window.localStorage.clear();
    window.sessionStorage.clear();
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string | URL | Request) => {
        if (String(input) === 'data/stage01_program_registry.json') {
          return { ok: true, text: async () => JSON.stringify({ programs: PROGRAMS }) };
        }
        return { ok: false, text: async () => '' };
      }),
    );
  });
  afterEach(() => {
    cleanup();
    window.localStorage.clear();
    window.sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  async function renderTab(page: PageKey, label: string) {
    window.localStorage.setItem(SELECTION_V3_KEY, JSON.stringify(await buildV3()));
    render(
      <StageIsland page={page} subtitle={label} purpose="p" regions={[]} enqueueTarget="x" renderDemo={() => null} />,
    );
  }

  for (const [page, label] of TABS) {
    it(`${label}: renders all SIX numbered sections in the ONE in-page drawer`, async () => {
      const before = window.location.href;
      await renderTab(page, label);
      const dialog = await openResolvedDrawer();

      for (const n of [...METHODS_STEPS, PROVENANCE_STEP]) {
        expect(dialog.querySelector(`[data-step="${n}"]`), `section ${n} on ${label}`).toBeTruthy();
      }
      // 1–5 live under methods, 6 under provenance — one drawer, both sections
      const methods = dialog.querySelector('[data-section="methods"]')!;
      const provenance = dialog.querySelector('[data-section="provenance"]')!;
      for (const n of METHODS_STEPS) expect(methods.querySelector(`[data-step="${n}"]`)).toBeTruthy();
      expect(provenance.querySelector(`[data-step="${PROVENANCE_STEP}"]`)).toBeTruthy();

      // it is a slide-out on THIS page — never a navigation to a separate methods page
      expect(window.location.href).toBe(before);
      expect(dialog.getAttribute('aria-modal')).toBe('true');
      expect(dialog.querySelector('[data-stage-label]')?.textContent).toBe(label);
    });

    it(`${label}: sections 2–5 are NONEMPTY (no hollow heading-only step)`, async () => {
      await renderTab(page, label);
      const dialog = await openResolvedDrawer();

      for (const n of ['2', '3', '4', '5']) {
        const content = stepContent(dialog, n);
        expect(content.length, `section ${n} on ${label} must carry bound content, got ""`).toBeGreaterThan(0);
        expect(content).not.toMatch(/^unavailable$/i); // never filler
      }
    });

    it(`${label}: sections 2–3 are route-specific, not one shared block of prose`, async () => {
      await renderTab(page, label);
      const dialog = await openResolvedDrawer();
      // the estimand + masks headings are derived from THIS stage, so each tab reads as its own method
      const h2 = within(dialog.querySelector('[data-step="2"]') as HTMLElement).getByRole('heading', { level: 4 });
      const h3 = within(dialog.querySelector('[data-step="3"]') as HTMLElement).getByRole('heading', { level: 4 });
      const expected: Record<string, [string, string]> = {
        Targets: ['Direct & temporal effects', 'Target-guide masks & eligibility'],
        Pathways: ['Ranked enrichment & signature convergence', 'Gene-set coverage & namespace'],
        Drugs: ['Direction-aware drug linking', 'Target identity & mechanism evidence'],
        'PK & Safety': ['Brain-exposure framework', 'Label evidence & safety'],
      };
      expect(h2.textContent).toBe(expected[label][0]);
      expect(h3.textContent).toBe(expected[label][1]);
    });

    it(`${label}: the drawer is SELECTION-BOUND — the verified v3, with each pole's own condition`, async () => {
      await renderTab(page, label);
      const dialog = await openResolvedDrawer();
      const sel = dialog.querySelector('[data-selection-v3]') as HTMLElement;
      expect(sel, 'the drawer must bind the verified v3 selection').toBeTruthy();

      const scoped = within(sel);
      // the ordered temporal endpoints, each pole at its OWN condition (never one shared label)
      expect(scoped.getByText('Alpha · low · Stim8hr')).toBeInTheDocument();
      expect(scoped.getByText('Beta · high · Stim48hr')).toBeInTheDocument();
      expect(scoped.getByText('temporal_cross_condition')).toBeInTheDocument();

      // and it is THIS selection: the id/question_id recomputed from the stored contract
      const stored = JSON.parse(window.localStorage.getItem(SELECTION_V3_KEY)!);
      expect(scoped.getByText(String(stored.selection_id))).toBeInTheDocument();
      expect(scoped.getByText(String(stored.question_id))).toBeInTheDocument();
    });
  }

  it('an UNBOUND run still renders all six sections — one terse status, zero "unavailable" filler', async () => {
    await renderTab('targets', 'Targets');
    const dialog = await openResolvedDrawer();
    // no admitted Stage-2 bundle is bound here, so section 6 collapses to the ONE status row …
    expect(within(dialog).getAllByText('No admitted Stage-2 run bundle bound')).toHaveLength(1);
    // … but the METHOD DEFINITION sections 1–5 are still fully rendered, not blanked out
    for (const n of METHODS_STEPS) expect(stepContent(dialog, n).length).toBeGreaterThan(0);
    expect(within(dialog).queryAllByText('unavailable')).toHaveLength(0);
  });
});
