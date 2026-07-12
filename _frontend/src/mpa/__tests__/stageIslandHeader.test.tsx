import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { StageIsland } from '../StageIsland';
import { SELECTION_KEY } from '../../repository/source';
import { researchSelectionExampleRaw } from '../../fixtures/researchSelection.example';

/** Set the full URL before render — the demo gate reads location.search. */
function goto(url: string) {
  window.history.pushState({}, '', url);
}

/** Minimal StageIsland; the header (banner) is what these tests assert on. */
function renderIsland() {
  return render(
    <StageIsland
      page="targets"
      subtitle="Targets"
      purpose="test purpose"
      regions={[]}
      enqueueTarget="stage02_review"
      renderDemo={() => null}
    />,
  );
}

describe('StageIsland — header selection context', () => {
  beforeEach(() => {
    goto('/02_page.html'); // no demo gate, no hash
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it('no selection → prompt where only "Programs" links back, and no clear control', () => {
    renderIsland();
    const header = screen.getByRole('banner');
    expect(within(header).getByText(/Select populations in/)).toBeInTheDocument();
    expect(within(header).getByRole('link', { name: 'Programs' })).toHaveAttribute(
      'href',
      '01_page.html',
    );
    expect(
      within(header).queryByRole('button', { name: /Clear selection and return to Programs/ }),
    ).toBeNull();
  });

  it('bound research selection → header shows the contrast + a clear (✕) control', () => {
    window.localStorage.setItem(SELECTION_KEY, JSON.stringify(researchSelectionExampleRaw));
    renderIsland();
    const header = screen.getByRole('banner');
    expect(
      within(header).getByText('Treg-like lo (at 48 hr) → Th1-like hi (at 48 hr)'),
    ).toBeInTheDocument();
    expect(
      within(header).getByRole('button', { name: 'Clear selection and return to Programs' }),
    ).toBeInTheDocument();
    // once bound, the no-selection prompt link is gone (nav lives in a separate <nav>)
    expect(within(header).queryByRole('link', { name: 'Programs' })).toBeNull();
  });

  it('demo gate with no real selection → the fixture contrast fills the header', () => {
    goto('/02_page.html?demo=1');
    renderIsland();
    const header = screen.getByRole('banner');
    expect(
      within(header).getByText(/Program A \(regulatory-like\) lo .* Program B \(inflammatory-like\) hi/),
    ).toBeInTheDocument();
  });
});
