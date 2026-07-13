// The ONE contextual header slide-out drawer, per active downstream tab. Clicking a tab then
// Methods & provenance opens the same drawer geometry with THAT stage's content — no route
// change. Production shows "unavailable" (never a fixture); ?demo=1 fills it synthetically.

import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { StageIsland } from '../StageIsland';
import type { PageKey } from '../pages';

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

function openDrawer(action: 'Methods' | 'Provenance' = 'Methods') {
  fireEvent.click(screen.getByRole('button', { name: new RegExp(action) }));
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
      expect(within(dialog).getByText('Methods')).toBeInTheDocument();
      expect(within(dialog).getByText('Provenance')).toBeInTheDocument();
      expect(window.location.href).toBe(before); // NO navigation — one shell drawer
      unmount();
    }
  });

  it('BOTH the Methods and the Provenance header actions open the same one drawer', () => {
    goto('/02_page.html');
    renderStage('targets', 'Targets');
    // Methods action
    const d1 = openDrawer('Methods');
    expect(within(d1).getByText('Methods')).toBeInTheDocument();
    expect(within(d1).getByText('Provenance')).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    // Provenance action opens the same drawer (both sections present)
    const d2 = openDrawer('Provenance');
    expect(within(d2).getByText('Provenance')).toBeInTheDocument();
    expect(within(d2).getByText('Methods')).toBeInTheDocument();
    expect(d2).toBe(d1); // the same single shell drawer node
  });

  it('states the source-tissue fact in the drawer (stage-appropriate, not a canvas banner)', () => {
    goto('/02_page.html');
    const { unmount } = renderStage('targets', 'Targets');
    const d1 = openDrawer();
    expect(
      within(d1).getByText(/Primary human CD4 T cells.*no multi-tissue expression analysis/i),
    ).toBeInTheDocument();
    // it lives in the drawer, not as a banner on the canvas
    expect(within(document.querySelector('main')!).queryByText(/CD4 T cells/i)).toBeNull();
    unmount();

    goto('/02_page.html');
    renderStage('pksafety', 'PK & Safety');
    expect(
      within(openDrawer()).getByText(/label evidence, never inferred from tissue expression/i),
    ).toBeInTheDocument();
  });

  it('MINOR 6: Drug link states its upstream CD4 source fact (not "unavailable")', () => {
    goto('/02_page.html');
    renderStage('drugs', 'Drug link');
    expect(
      within(openDrawer()).getByText(/Marson primary-human-CD4 dataset/),
    ).toBeInTheDocument();
  });

  it('MINOR 7: the Provenance action opens a neutrally-titled drawer (not "— methods")', () => {
    goto('/02_page.html');
    renderStage('targets', 'Targets');
    const dialog = openDrawer('Provenance');
    const title = within(dialog).getByRole('heading', { level: 2 }).textContent ?? '';
    expect(title).toMatch(/— methods & provenance$/); // neutral, not "— methods"
    expect(title.endsWith('— methods')).toBe(false);
  });

  it('production shows "unavailable" values and never a fixture (values never invented)', () => {
    goto('/02_page.html');
    renderStage('targets', 'Targets');
    const dialog = openDrawer();
    expect(within(dialog).getAllByText('unavailable').length).toBeGreaterThan(3);
    expect(within(dialog).queryByText(/fixture/i)).toBeNull();
    expect(within(dialog).queryByText(/run_screen --lane fixture/)).toBeNull();
  });

  it('?demo=1 fills the drawer from the synthetic manifest (explicit gate) incl. a copyable reproduce command', () => {
    goto('/02_page.html?demo=1');
    renderStage('targets', 'Targets');
    const dialog = openDrawer();
    expect(within(dialog).getByText('target_masked_measured_effect_screen.fixture')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /Copy reproduce command/ })).toBeInTheDocument();
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
