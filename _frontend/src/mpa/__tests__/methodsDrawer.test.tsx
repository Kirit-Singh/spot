// The ONE contextual header slide-out drawer, per active downstream tab. Clicking a tab then
// Methods & provenance opens the same drawer geometry with THAT stage's content — no route change.
// Production-only: no demo/fixture route. Unbound routes show ONE terse route status and zero
// "unavailable" filler (the resolved-manifest invariant); ?demo=1 reveals nothing synthetic.

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { StageIsland } from '../StageIsland';
import type { PageKey } from '../pages';
import { ProvenanceDrawer } from '../../shell/ProvenanceDrawer';

function goto(url: string) {
  window.history.pushState({}, '', url);
}

function renderStage(page: PageKey, subtitle: string) {
  return render(
    <StageIsland
      page={page}
      subtitle={subtitle}
      purpose="p"
      regions={[]}
      enqueueTarget="x"
      renderDemo={() => null}
    />,
  );
}

// One combined header action on every route (Stage-1 parity: single "Methods & provenance").
function openDrawer() {
  fireEvent.click(screen.getByRole('button', { name: /Methods & provenance/i }));
  return screen.getByRole('dialog');
}

describe('contextual Methods & Provenance drawer', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it('opens the same header drawer on each downstream tab with stage-specific content, no route change', () => {
    for (const [page, label] of [
      ['targets', 'Targets'],
      ['drugs', 'Drugs'],
      ['pksafety', 'PK & Safety'],
    ] as [PageKey, string][]) {
      goto('/02_page.html'); // production, no demo
      const before = window.location.href;
      const { unmount } = renderStage(page, label);
      const dialog = openDrawer();
      expect(dialog.querySelector('[data-stage-label]')?.textContent).toBe(label); // stage-specific
      expect(dialog.querySelector('[data-section="methods"]')).toBeTruthy();
      expect(dialog.querySelector('[data-section="provenance"]')).toBeTruthy();
      expect(window.location.href).toBe(before); // NO navigation — one shell drawer
      unmount();
    }
  });

  it('renders distinct verified v3 temporal endpoints instead of one shared condition', () => {
    render(
      <ProvenanceDrawer
        open
        onClose={() => {}}
        title="Targets"
        provenance={null}
        selectionV3={{
          selection_id: 'selection-1',
          question_id: 'question-1',
          analysis_mode: 'temporal_cross_condition',
          execution_status: 'ready',
          estimator_id: 'temporal_cross_condition_v1',
          estimator_status: 'available',
          A: { program_id: 'diff_activated', display_label: 'Activated', direction: 'high', condition: 'Stim8hr' },
          B: { program_id: 'diff_activated', display_label: 'Activated', direction: 'high', condition: 'Stim48hr' },
        }}
      />,
    );
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Activated · high · Stim8hr')).toBeInTheDocument();
    expect(within(dialog).getByText('Activated · high · Stim48hr')).toBeInTheDocument();
    expect(within(dialog).getByText('temporal_cross_condition')).toBeInTheDocument();
  });

  it('the ONE combined action opens the single drawer with BOTH sections (no separate provenance action)', () => {
    goto('/02_page.html');
    renderStage('targets', 'Targets');
    // Stage-1 parity: exactly one header action, no separate "Provenance" button.
    expect(screen.queryByRole('button', { name: /^Provenance$/ })).toBeNull();
    expect(screen.getAllByRole('button', { name: /Methods & provenance/i })).toHaveLength(1);
    const d = openDrawer();
    expect(d.querySelector('[data-section="methods"]')).toBeTruthy();
    expect(d.querySelector('[data-section="provenance"]')).toBeTruthy(); // both sections, one drawer
    // (References render only with bound sources — asserted on the resolved manifest elsewhere)
  });

  it('states the source-tissue fact in the drawer (stage-appropriate, not a canvas banner)', () => {
    goto('/02_page.html');
    const { unmount } = renderStage('targets', 'Targets');
    const d1 = openDrawer();
    expect(
      within(d1).getByText(/Primary human CD4 T cells.*no tissue\/organ sampling axis or multi-tissue expression measurements in GWCD4i.*HPA\/GTEx analysis is external/i),
    ).toBeInTheDocument();
    // it lives in the drawer, not as a banner on the canvas
    expect(within(document.querySelector('main')!).queryByText(/CD4 T cells/i)).toBeNull();
    unmount();

    goto('/02_page.html');
    renderStage('pksafety', 'PK & Safety');
    expect(
      within(openDrawer()).getByText(/emitted only from an admitted structured source field.*never inferred from target, mechanism, class, or drug name/i),
    ).toBeInTheDocument();
  });

  it('MINOR 6: Drugs states its upstream CD4 source fact (not "unavailable")', () => {
    goto('/02_page.html');
    renderStage('drugs', 'Drugs');
    expect(
      within(openDrawer()).getByText(/Marson primary-human-CD4 dataset/),
    ).toBeInTheDocument();
  });

  it('Stage-1 header: ONE "Methods & provenance" title; route identity is semantic (data-stage-label + aria-label) + body', () => {
    goto('/02_page.html');
    renderStage('targets', 'Targets');
    const dialog = openDrawer();
    const h2 = within(dialog).getByRole('heading', { level: 2 });
    expect(h2.textContent).toBe('Methods & provenance'); // single title, NO second route line
    expect(h2).not.toHaveAttribute('data-stage-label'); // route is not on the visible title
    // route identity: sr-only stage label + dialog aria-label + route-specific body content
    expect(dialog.querySelector('[data-stage-label]')?.textContent).toBe('Targets');
    expect(dialog.getAttribute('aria-label')).toContain('Targets');
    expect(within(dialog).getByText('Direct & temporal effects')).toBeInTheDocument(); // route-specific
  });

  it('pre-resolution fallback obeys zero-filler: an immediately-opened drawer has zero literal "unavailable"', () => {
    goto('/02_page.html');
    renderStage('targets', 'Targets');
    const dialog = openDrawer(); // opened BEFORE the async manifest resolves (reads the fallback)
    expect(within(dialog).queryAllByText('unavailable')).toHaveLength(0); // References returns null when empty
    expect(within(dialog).getAllByText('No admitted Stage-2 run bundle bound')).toHaveLength(1);
  });

  it('CLEAN unbound: exactly one route status row, never a fixture (strict zero-unavailable is asserted on the resolved manifest)', () => {
    goto('/02_page.html');
    renderStage('targets', 'Targets');
    const dialog = openDrawer();
    expect(within(dialog).getAllByText('No admitted Stage-2 run bundle bound')).toHaveLength(1);
    expect(within(dialog).queryByText(/fixture/i)).toBeNull();
    expect(within(dialog).queryByText(/run_screen --lane fixture/)).toBeNull();
  });

  it('the public ?demo=1 route is RETIRED — the RESOLVED drawer is the honest production manifest (one status, zero filler)', async () => {
    goto('/02_page.html?demo=1');
    renderStage('targets', 'Targets');
    // Await the ASYNC real manifest into the drawer (re-click until method_id shows) — this proves we
    // are NOT asserting on the pre-resolution fallback.
    await waitFor(() => {
      fireEvent.click(screen.getByRole('button', { name: /Methods & provenance/i }));
      expect(within(screen.getByRole('dialog')).getByText(/masked_program_projection/)).toBeInTheDocument();
    });
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).queryByText(/fixture/i)).toBeNull(); // no synthetic fixture even with ?demo=1
    expect(within(dialog).queryByText('target_masked_measured_effect_screen.fixture')).toBeNull();
    expect(within(dialog).getAllByText('No admitted Stage-2 run bundle bound')).toHaveLength(1);
    expect(within(dialog).queryAllByText('unavailable')).toHaveLength(0); // zero filler on the resolved manifest
  });

  it('keyboard/focus/escape: focuses close on open, aria-modal, Escape closes', () => {
    goto('/02_page.html');
    renderStage('drugs', 'Drugs');
    const dialog = openDrawer();
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    const close = within(dialog).getByRole('button', { name: /Close methods and provenance/ });
    expect(document.activeElement).toBe(close);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByRole('dialog', { hidden: true })).toHaveAttribute('aria-hidden', 'true');
  });
});
