// Milestone acceptance: the ONE shared contextual Methods & Provenance slide-out on every
// semantic page. Both header actions open the SAME drawer node (the clicked button only picks
// the initial section); content is contextual to the active page; focus trap + Escape + close;
// no navigation to a methods page; no stale content after a route change.

import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { StageIsland } from '../StageIsland';
import type { PageKey } from '../pages';

const PAGES: [PageKey, string][] = [
  ['targets', 'Targets'],
  ['pathways', 'Pathways'],
  ['drugs', 'Drug link'],
  ['pksafety', 'PK / PD · brain'],
];

function goto(url: string) {
  window.history.pushState({}, '', url);
}
function renderPage(page: PageKey, subtitle: string) {
  return render(
    <StageIsland page={page} subtitle={subtitle} purpose="p" regions={[]} enqueueTarget="x" renderDemo={() => null} />,
  );
}
const methodsBtn = () => screen.getByRole('button', { name: /Methods/ }); // accessible name "iMethods"
const provBtn = () => screen.getByRole('button', { name: /^Provenance$/ });
const stageLabel = (d: HTMLElement) => d.querySelector('[data-stage-label]')?.textContent;

describe('shared contextual drawer — both actions, one node, every semantic page', () => {
  beforeEach(() => {
    goto('/targets.html');
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  afterEach(() => cleanup());

  for (const [page, label] of PAGES) {
    it(`${page}: Methods + Provenance open the SAME drawer node with "${label}" content, no route change`, () => {
      const before = window.location.href;
      renderPage(page, label);

      fireEvent.click(methodsBtn());
      const d1 = screen.getByRole('dialog');
      expect(stageLabel(d1)).toBe(label);
      expect(within(d1).getByText('Methods')).toBeInTheDocument();
      expect(within(d1).getByText('Provenance')).toBeInTheDocument();
      fireEvent.keyDown(window, { key: 'Escape' });

      fireEvent.click(provBtn());
      const d2 = screen.getByRole('dialog');
      expect(d2).toBe(d1); // the SAME single shell drawer node
      expect(stageLabel(d2)).toBe(label);
      expect(window.location.href).toBe(before); // no navigation to a methods page
    });
  }

  it('focus trap + focus-on-open + Escape close', () => {
    renderPage('targets', 'Targets');
    fireEvent.click(methodsBtn());
    const dialog = screen.getByRole('dialog');
    expect(document.activeElement).toBe(within(dialog).getByRole('button', { name: /Close methods/ }));
    // Tab from the last focusable wraps within the drawer (focus never leaves)
    const focusable = dialog.querySelectorAll<HTMLElement>('a[href], button:not([disabled])');
    focusable[focusable.length - 1].focus();
    fireEvent.keyDown(window, { key: 'Tab' });
    expect(dialog.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByRole('dialog', { hidden: true })).toHaveAttribute('aria-hidden', 'true');
  });

  it('no stale content after a route change (fresh page → fresh contextual drawer)', () => {
    renderPage('targets', 'Targets');
    fireEvent.click(methodsBtn());
    expect(stageLabel(screen.getByRole('dialog'))).toBe('Targets');
    cleanup(); // route change away from targets

    renderPage('drugs', 'Drug link');
    fireEvent.click(methodsBtn());
    const d = screen.getByRole('dialog');
    expect(stageLabel(d)).toBe('Drug link'); // contextual to the new page, not stale "Targets"
    expect(within(d).queryByText('Targets')).toBeNull();
  });
});
