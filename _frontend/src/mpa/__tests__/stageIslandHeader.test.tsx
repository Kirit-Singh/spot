import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { StageIsland } from '../StageIsland';
// The verified-v3 → contrast (and forged-v3 → prompt) header cases live in
// stageIslandHeaderVerify.test.tsx, which exercises the real async fail-closed path. This file
// covers only the two synchronous header states: no selection, and the ?demo=1 fixture.

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

  it('the public ?demo=1 route is retired → header shows the neutral prompt, never a synthetic contrast', () => {
    goto('/02_page.html?demo=1');
    renderIsland();
    const header = screen.getByRole('banner');
    expect(within(header).getByText(/Select populations in/)).toBeInTheDocument();
    expect(within(header).queryByText(/regulatory-like|inflammatory-like/)).toBeNull();
  });
});
