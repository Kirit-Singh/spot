// The header "Methods & provenance" slide-out is the ONLY primary methods/provenance UI surface.
// No route — 01 Programs, 02 Targets/Pathways, 03 Drugs, 04 PK & Safety — navigates to a standalone
// methods/notebook page; each shows its OWN route-specific methods + provenance inside that one drawer
// (Stage-1 parity). These tests pin exactly that contract:
//   1) exactly one combined "Methods & provenance" header action per route;
//   2) opening it stays on the route and yields the same slide-over geometry;
//   3) 02/03/04 content is route-specific with BOTH a methods and a provenance section;
//   4) no drawer holds an anchor/href to a standalone methods/notebook/trace page (incl. static 01);
//   5) the drawer content is not duplicated as a banner / editorial prose on the canvas.

import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { StageIsland } from '../StageIsland';
import type { PageKey } from '../pages';
// Vite `?raw` import (type-safe under the vite/client tsconfig) — the exact static Programs bytes.
import html01 from '../../../public/01_page.html?raw';

const DOWNSTREAM: [PageKey, string][] = [
  ['targets', 'Targets'],
  ['pathways', 'Pathways'],
  ['drugs', 'Drugs'],
  ['pksafety', 'PK & Safety'],
];

// Geometry tokens shared by the ONE slide-over (Stage-1 parity: 600px/94vw, 16px corner, 340ms curve).
const GEOMETRY = ['w-[600px]', 'max-w-[94vw]', 'rounded-l-2xl', 'duration-[340ms]'];

// A href is a forbidden in-app methods destination if it is NOT an external URL / mailto and points
// at a methods/notebook/trace/provenance page. The only allow-listed non-URL drawer href is the
// same-origin Stage-1 release manifest reference.
function isStandaloneMethodsHref(href: string): boolean {
  if (/^(https?:\/\/|mailto:)/i.test(href)) return false; // external references are allowed in the drawer
  if (href === '/data/stage01_release_manifest.json') return false; // allow-listed release manifest
  return /(notebook|trace|methods|provenance)/i.test(href);
}

function hrefsIn(markup: string): string[] {
  return [...markup.matchAll(/href="([^"]*)"/gi)].map((m) => m[1]);
}

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

function openDrawer() {
  fireEvent.click(screen.getByRole('button', { name: /Methods & provenance/i }));
  return screen.getByRole('dialog');
}

describe('the header drawer is the sole primary methods/provenance surface (all routes)', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  // ── 02/03/04 (React) ───────────────────────────────────────────────────────
  it('1+2+3: one combined action, no route change, same geometry, route-specific with BOTH sections', () => {
    for (const [page, label] of DOWNSTREAM) {
      goto('/02_page.html'); // production, no demo
      const before = window.location.href;
      const { unmount } = renderStage(page, label);

      // (1) exactly one combined action; no separate "Provenance" button
      expect(screen.getAllByRole('button', { name: /Methods & provenance/i })).toHaveLength(1);
      expect(screen.queryByRole('button', { name: /^Provenance$/ })).toBeNull();

      const dialog = openDrawer();

      // (2) staying on the route + identical slide-over geometry
      expect(window.location.href).toBe(before);
      for (const token of GEOMETRY) expect(dialog.className).toContain(token);

      // (3) route-specific identity + BOTH sections present
      expect(dialog.querySelector('[data-stage-label]')?.textContent).toBe(label);
      expect(dialog.getAttribute('aria-label')).toContain(label);
      expect(dialog.querySelector('[data-section="methods"]')).toBeTruthy();
      expect(dialog.querySelector('[data-section="provenance"]')).toBeTruthy();

      unmount();
    }
  });

  it('4: no downstream drawer holds an anchor to a standalone methods/notebook/trace page', () => {
    for (const [page, label] of DOWNSTREAM) {
      goto('/02_page.html');
      const { unmount } = renderStage(page, label);
      const dialog = openDrawer();
      const bad = [...dialog.querySelectorAll('a[href]')]
        .map((a) => a.getAttribute('href') || '')
        .filter(isStandaloneMethodsHref);
      expect(bad).toEqual([]);
      unmount();
    }
  });

  it('5: the drawer content is not mirrored as a banner / editorial prose on the canvas', () => {
    goto('/02_page.html');
    renderStage('targets', 'Targets');
    const main = document.querySelector('main')!;
    // the single header title lives in the drawer, never as a canvas banner
    expect(within(main).queryByText(/Methods & provenance/i)).toBeNull();
    // the route's method definition (drawer content) is not duplicated onto the canvas
    expect(within(main).queryByText(/Direct & temporal effects/i)).toBeNull();
    expect(within(main).queryByText(/CD4 T cells/i)).toBeNull();
    expect(main.querySelector('[role="banner"]')).toBeNull();
  });

  // ── 01 Programs (frozen static HTML) ─────────────────────────────────────────
  it('1: static Programs page exposes exactly one drawer trigger and one provenance modal', () => {
    expect((html01.match(/id="provbtn"/g) || []).length).toBe(1);
    expect((html01.match(/id="provmodal"/g) || []).length).toBe(1);
  });

  it('4: the Programs drawer has NO anchor to a standalone methods/notebook/trace page (link removed)', () => {
    // Scope to the provenance modal onward (the drawer region lives at the tail of the page).
    const modalOnward = html01.slice(html01.indexOf('id="provmodal"'));
    expect(modalOnward.length).toBeGreaterThan(0);
    const bad = hrefsIn(modalOnward).filter(isStandaloneMethodsHref);
    expect(bad).toEqual([]);
    // Whole-page guard: the specific archival pages are never a UI destination anywhere on the page.
    expect(html01).not.toMatch(/href="[^"]*01_notebook\.html"/i);
    expect(html01).not.toMatch(/href="[^"]*01_(trace|methods)\.html"/i);
    // …but the drawer's own reproducibility content is preserved (external script ref + reproduce line).
    expect(modalOnward).toMatch(/reproduce\.sh/);
  });
});
