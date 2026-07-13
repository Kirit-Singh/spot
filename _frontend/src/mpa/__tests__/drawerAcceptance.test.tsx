// Milestone acceptance: the ONE shared contextual "Methods & provenance" slide-out on every
// semantic page. There is exactly ONE combined header action (matching Stage-1's single
// #provbtn); one click opens the SAME drawer node focused at Methods with BOTH the Methods and
// Provenance sections visible; content is contextual to the active page; focus trap + Escape +
// close + focus restored to the invoker (U15); no navigation to a methods page; no stale
// content after a route change.

import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { StageIsland } from '../StageIsland';
import type { PageKey } from '../pages';

const PAGES: [PageKey, string][] = [
  ['targets', 'Targets'],
  ['pathways', 'Pathways'],
  ['drugs', 'Drugs'],
  ['pksafety', 'PK & Safety'],
];

function goto(url: string) {
  window.history.pushState({}, '', url);
}
function renderPage(page: PageKey, subtitle: string) {
  return render(
    <StageIsland page={page} subtitle={subtitle} purpose="p" regions={[]} enqueueTarget="x" renderDemo={() => null} />,
  );
}
// The ONE combined header invoker, matching Stage-1's single #provbtn "Methods & provenance".
const methodsBtn = () => screen.getByRole('button', { name: /Methods & provenance/i });
const stageLabel = (d: HTMLElement) => d.querySelector('[data-stage-label]')?.textContent;

describe('shared contextual drawer — one combined action, one node, every semantic page', () => {
  beforeEach(() => {
    goto('/targets.html');
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  afterEach(() => cleanup());

  for (const [page, label] of PAGES) {
    it(`${page}: the one Methods & provenance button opens the contextual drawer with both sections, no route change`, () => {
      const before = window.location.href;
      renderPage(page, label);

      // Exactly ONE header invoker; no separate provenance action anywhere.
      expect(screen.queryByRole('button', { name: /^Provenance$/ })).toBeNull();
      expect(screen.getAllByRole('button', { name: /Methods & provenance/i })).toHaveLength(1);

      fireEvent.click(methodsBtn());
      const d = screen.getByRole('dialog');
      expect(stageLabel(d)).toBe(label); // contextual to the active page
      // both sections present in the ONE drawer (Stage-1 numbered-step grammar)
      expect(d.querySelector('[data-section="methods"]')).toBeTruthy();
      expect(d.querySelector('[data-section="provenance"]')).toBeTruthy();
      expect(within(d).getByText('Data source')).toBeInTheDocument(); // methods step-1 heading
      expect(within(d).getByText('Provenance & status')).toBeInTheDocument(); // provenance step heading
      // (References render only with bound sources — asserted on the resolved manifest, not this fallback)
      expect(window.location.href).toBe(before); // no navigation to a methods page
    });
  }

  it('focus trap + focus-on-open + Escape close + focus restored to the invoker (U15)', () => {
    renderPage('targets', 'Targets');
    const invoker = methodsBtn();
    invoker.focus(); // the button is the active element when clicked
    fireEvent.click(invoker);
    const dialog = screen.getByRole('dialog');
    expect(document.activeElement).toBe(within(dialog).getByRole('button', { name: /Close methods/ }));
    // Tab from the last focusable wraps within the drawer (focus never leaves)
    const focusable = dialog.querySelectorAll<HTMLElement>('a[href], button:not([disabled])');
    focusable[focusable.length - 1].focus();
    fireEvent.keyDown(window, { key: 'Tab' });
    expect(dialog.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByRole('dialog', { hidden: true })).toHaveAttribute('aria-hidden', 'true');
    // U15: focus returns to the exact button that opened the drawer
    expect(document.activeElement).toBe(invoker);
  });

  it('no stale content after a route change (fresh page → fresh contextual drawer)', () => {
    renderPage('targets', 'Targets');
    fireEvent.click(methodsBtn());
    expect(stageLabel(screen.getByRole('dialog'))).toBe('Targets');
    cleanup(); // route change away from targets

    renderPage('drugs', 'Drugs');
    fireEvent.click(methodsBtn());
    const d = screen.getByRole('dialog');
    expect(stageLabel(d)).toBe('Drugs'); // contextual to the new page, not stale "Targets"
    expect(within(d).queryByText('Targets')).toBeNull();
  });
});
