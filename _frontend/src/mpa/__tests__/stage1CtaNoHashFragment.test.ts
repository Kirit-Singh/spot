// The "ID program skew genes" call to action must not typeset a selection/hash fragment.
//
// The Stage-1 page used to print the selection_id beside the CTA in three places: an 8-hex chip inside
// the button (#idpend), "Contrast ready · <selection_id>", and "Selection ready · <selection_id> →
// Stage 2". A bare hash next to a button reads as a value the reader is meant to act on; it is an
// identifier, and it belongs where it is accountable — the Methods & provenance artifacts.
//
// What must NOT change: the selection_id stays INTERNAL. It still drives curContrastId, it is still
// folded into the v3 contract that Stage-2 verifies, and it still routes. This test pins BOTH halves —
// the fragment is gone from the served bytes, and the internals that depend on it are intact — so a
// future edit cannot "fix" the display by weakening the contract.
//
// Asserted on the SERVED artifact (public/01_page.html — the exact bytes the deploy pins and ships),
// not on a copy, so it cannot pass against source that is never deployed.

import { describe, expect, it } from 'vitest';
import page from '../../../public/01_page.html?raw';

/** Every assignment to the #idpend chip inside the CTA button. */
const PEND_WRITES = [...page.matchAll(/pend\.textContent\s*=\s*([^;]+);/g)].map((m) => m[1].trim());
/** Every assignment to the inline status box beside the CTA. */
const STATUS_WRITES = [...page.matchAll(/st\.textContent\s*=\s*([^;]+);/g)].map((m) => m[1].trim());

describe('Stage-1 CTA — no selection/hash fragment is typeset beside the button', () => {
  it('the #idpend chip is never written a selection_id (it only ever gets the empty string)', () => {
    expect(PEND_WRITES.length).toBeGreaterThan(0); // the writes still exist; they are just never a hash
    for (const write of PEND_WRITES) {
      expect(write).toBe("''");
    }
    // the specific bug: an 8-hex slice of the id, printed on the button
    expect(page).not.toMatch(/selection_id\.slice\(/);
  });

  it('no status line concatenates a selection_id into its text', () => {
    for (const write of STATUS_WRITES) {
      expect(write).not.toMatch(/selection_id/);
    }
    expect(page).not.toMatch(/'Contrast ready · '\s*\+/);
    expect(page).not.toMatch(/'Selection ready · '\s*\+/);
  });

  it('the ready states still say what they mean — without an identifier', () => {
    expect(page).toContain("st.textContent='Contrast ready';");
    expect(page).toContain("st.textContent='Selection ready → Stage 2';");
  });

  it('no bare hex-hash fragment is emitted into ANY visible text node beside the CTA', () => {
    // any string literal assigned to the button chip or status box that carries a >=8-char hex run
    for (const write of [...PEND_WRITES, ...STATUS_WRITES]) {
      expect(write).not.toMatch(/[0-9a-f]{8,}/i);
    }
  });

  // ── the other half: the identifier is REMOVED FROM DISPLAY, not from the contract ──
  it('PRESERVED: the selection_id still drives curContrastId', () => {
    expect(page).toContain('curContrastId=r.selection_id');
  });

  it('PRESERVED: the emitted artifact is still the full v3 contract, stored under the v3 key', () => {
    expect(page).toContain("const SELECTION_LS_KEY='spot.stage01_selection.v3'");
    expect(page).toContain('localStorage.setItem(SELECTION_LS_KEY,JSON.stringify(art))');
    expect(page).toContain('sessionStorage.setItem(SELECTION_LS_KEY,JSON.stringify(art))');
  });

  it('PRESERVED: Identify still routes to Stage 2', () => {
    expect(page).toContain("window.location.assign('targets.html')");
  });

  it('the CTA keeps its label and its chip slot (layout unchanged)', () => {
    expect(page).toContain('<span class="idlbl">ID program skew genes →</span>');
    expect(page).toContain('<span class="pend" id="idpend"></span>');
  });
});
