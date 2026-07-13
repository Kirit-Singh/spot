// harness_util.mjs — shared contract constants + browser/Node helpers for the U01–U18
// acceptance gates. Kept separate so u01_u18.mjs stays focused (≤500 lines each).
//
// Hashing is done in Node (node:crypto over Node `fetch` bytes), never in-browser:
// http://…:8347 is not a secure context, so window.crypto.subtle is unavailable there.

import { createHash } from 'node:crypto';

// ── Contract constants (mirror the app's source of truth) ──
export const DEFAULT_BASE = 'http://100.117.50.59:8347';
export const RELEASE_MANIFEST = 'release_manifest.json';
export const ROUTES = ['01_page.html', 'targets.html', 'pathways.html', 'drugs.html', 'pksafety.html'];
export const DOWNSTREAM = ['targets.html', 'pathways.html', 'drugs.html', 'pksafety.html'];

// U03 — required data-stage-label per downstream route.
export const STAGE_LABEL = {
  'targets.html': 'Targets',
  'pathways.html': 'Pathways',
  'drugs.html': 'Drugs',
  'pksafety.html': 'PK & Safety',
};

// U04 — required nav model on ALL five pages: 01 / 02 / 02 / 03 / 04.
export const NAV_EXPECTED = [
  { n: '01', label: 'Programs' },
  { n: '02', label: 'Targets' },
  { n: '02', label: 'Pathways' },
  { n: '03', label: 'Drugs' },
  { n: '04', label: 'PK & Safety' },
];

export const V3_KEY = 'spot.stage01_selection.v3';
export const V1_KEY = 'spot.stage01_selection.v1';

// Text that must NEVER appear anywhere on a honestly pre-run (or real) page — the firewall.
export const PENDING_FORBIDDEN = [
  'fixture', 'demo', 'gene_a', 'gene_b', 'compound_a', 'compound_b',
  'synthetic', 'lorem', 'awaiting artifact', 'stale',
];

// A drawer row value counts as "unavailable / empty" (never a fabricated placeholder).
export const bad = (v) => v == null || v === '' || /unavailable/i.test(v);

// Read the drawer's Methods + Provenance rows (label→value) and its source-chain list.
export async function drawerRows(page) {
  return page.evaluate(() => {
    const a = document.querySelector('aside[role="dialog"]');
    const rows = (secSel) => {
      const sec = a?.querySelector(secSel);
      const out = {};
      sec?.querySelectorAll('.grid').forEach((g) => {
        const c = g.children;
        if (c.length >= 2) out[(c[0].textContent || '').trim()] = (c[1].textContent || '').trim();
      });
      return out;
    };
    const sources = [...(a?.querySelectorAll('[data-section="provenance"] li') || [])]
      .map((li) => (li.textContent || '').replace(/\s+/g, ' ').trim());
    return { methods: rows('[data-section="methods"]'), provenance: rows('[data-section="provenance"]'), sources };
  });
}

// Forbidden synthetic/stale/pre-run-claim text anywhere in the rendered document body.
export async function bodyForbidden(page) {
  const t = await page.evaluate(() => (document.body?.innerText || '').toLowerCase());
  return PENDING_FORBIDDEN.filter((w) => t.includes(w));
}

// ── Node fetch + hash ──
export function sha256Hex(buf) {
  return createHash('sha256').update(buf).digest('hex');
}
export async function fetchBuf(u, timeoutMs = 60000) {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const r = await fetch(u, { signal: ac.signal });
    return { status: r.status, buf: Buffer.from(await r.arrayBuffer()) };
  } catch (e) {
    return { status: 0, buf: Buffer.alloc(0), error: e.message };
  } finally {
    clearTimeout(t);
  }
}
export async function fetchJson(u, timeoutMs = 20000) {
  const { status, buf, error } = await fetchBuf(u, timeoutMs);
  if (status !== 200) return { status, json: null, error };
  try {
    return { status, json: JSON.parse(buf.toString('utf8')) };
  } catch (e) {
    return { status, json: null, error: e.message };
  }
}

// ── generic ──
export const urlOf = (base, route) => `${base.replace(/\/+$/, '')}/${route}`;
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const isUtc = (s) =>
  typeof s === 'string' &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})$/.test(s) &&
  !Number.isNaN(Date.parse(s));

export async function poll(fn, ms = 4000, step = 100) {
  const t0 = Date.now();
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() - t0 > ms) return v;
    await sleep(step);
  }
}

export async function withPage(browser, fn) {
  const page = await browser.newPage();
  try {
    return await fn(page);
  } finally {
    await page.close().catch(() => {});
  }
}

export async function goto(page, base, route) {
  // waitUntil:'networkidle' matches the proven baseline runner (capture_baseline.mjs).
  return page.goto(urlOf(base, route), { waitUntil: 'networkidle', timeout: 60000 });
}

// Navigate + wait for the shell to be present (React nav / Programs nav / Identify button).
export async function gotoReady(page, base, route) {
  const resp = await goto(page, base, route);
  await poll(async () => page.evaluate(() =>
    !!document.querySelector('nav[aria-label="Pipeline stages"], .nav, #idgenes')), 8000).catch(() => {});
  return resp;
}

// Cross-runtime viewport (playwright: setViewportSize; puppeteer: setViewport).
export async function setViewport(page, width, height) {
  if (typeof page.setViewportSize === 'function') return page.setViewportSize({ width, height });
  if (typeof page.setViewport === 'function') return page.setViewport({ width, height });
}

// Cross-runtime reduced-motion (playwright: emulateMedia; puppeteer: emulateMediaFeatures).
export async function reduceMotion(page) {
  if (typeof page.emulateMedia === 'function') return page.emulateMedia({ reducedMotion: 'reduce' });
  if (typeof page.emulateMediaFeatures === 'function')
    return page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);
}

// ── DOM extractors (run in the browser page) ──
export async function extractNav(page) {
  return page.evaluate(() => {
    const rows = (root, stepSel, numSel) =>
      [...root.querySelectorAll(stepSel)].map((el) => {
        const n = (el.querySelector(numSel)?.textContent || '').trim();
        const full = (el.textContent || '').replace(/\s+/g, ' ').trim();
        const label = n && full.startsWith(n) ? full.slice(n.length).trim() : full;
        const a = el.matches('a[href]') ? el : el.querySelector('a[href]');
        return {
          n,
          label,
          href: a ? a.getAttribute('href') : null,
          active: el.getAttribute('aria-current') === 'page' || !!el.closest('[aria-current="page"]'),
        };
      });
    const react = document.querySelector('nav[aria-label="Pipeline stages"]');
    if (react) return rows(react, '.stage-nav__step', '.font-mono');
    const prog = document.querySelector('.nav');
    if (prog) return rows(prog, '.nstep', '.n');
    return [];
  });
}

// Stage-1 parity: downstream tabs have ONE combined header invoker "Methods & provenance"
// (no separate Methods / Provenance actions). One click opens the active-page drawer focused
// at the Methods section, with BOTH Methods and Provenance sections in one scroll.
const INVOKER_RE = /Methods\s*&\s*provenance/i;
export async function countDrawerInvokers(page) {
  return page.evaluate(() => {
    const re = /Methods\s*&\s*provenance/i;
    return [...document.querySelectorAll('header button')].filter((x) => re.test((x.textContent || '').replace(/\s+/g, ' '))).length;
  });
}
export async function clickDrawer(page) {
  return page.evaluate(() => {
    const re = /Methods\s*&\s*provenance/i;
    const b = [...document.querySelectorAll('header button')].find((x) => re.test((x.textContent || '').replace(/\s+/g, ' ')));
    if (!b) return false;
    b.click();
    return true;
  });
}
export { INVOKER_RE };

// Rich drawer snapshot — open state, sections, focus, per-section text, method id/hash, scroll.
export async function drawerState(page) {
  return page.evaluate(() => {
    const a = document.querySelector('aside[role="dialog"]');
    if (!a) return { present: false };
    const active = document.activeElement;
    const scroller = a.querySelector('.overflow-y-auto') || a;
    const mSec = a.querySelector('[data-section="methods"]');
    const pSec = a.querySelector('[data-section="provenance"]');
    const topOf = (el) => (el ? Math.round(el.getBoundingClientRect().top - scroller.getBoundingClientRect().top) : null);
    const rowVal = (sec, label) => {
      if (!sec) return null;
      const cells = [...sec.querySelectorAll('div')];
      const l = cells.find((d) => (d.textContent || '').trim().toLowerCase() === label.toLowerCase());
      return l && l.nextElementSibling ? (l.nextElementSibling.textContent || '').trim() : null;
    };
    return {
      present: true,
      open: a.getAttribute('aria-hidden') === 'false',
      inert: a.hasAttribute('inert'),
      ariaModal: a.getAttribute('aria-modal'),
      hasMethods: !!mSec,
      hasProvenance: !!pSec,
      stageLabel: (a.querySelector('[data-stage-label]')?.textContent || '').trim(),
      title: (a.querySelector('h2')?.textContent || '').trim(),
      methodsText: (mSec?.textContent || '').replace(/\s+/g, ' ').trim(),
      provText: (pSec?.textContent || '').replace(/\s+/g, ' ').trim(),
      methodId: rowVal(mSec, 'Method'),
      codeSha: rowVal(mSec, 'Code sha256'),
      lastRunUtc: rowVal(mSec, 'Last run UTC'),
      dataInput: rowVal(mSec, 'Data / input'),
      release: rowVal(pSec, 'Release'),
      rawSha: rowVal(pSec, 'Raw sha256'),
      canonicalSha: rowVal(pSec, 'Canonical'),
      scrollTop: Math.round(scroller.scrollTop),
      overflow: scroller.scrollHeight > scroller.clientHeight + 1,
      methodsTop: topOf(mSec),
      provTop: topOf(pSec),
      activeInside: !!(active && a.contains(active)),
      // drawer-only anchors + their hrefs (for U13 frame_ref / external-link checks)
      anchors: [...a.querySelectorAll('a[href]')].map((x) => x.getAttribute('href')),
    };
  });
}

export async function openDrawer(page) {
  const found = await clickDrawer(page);
  if (!found) return { present: false, open: false };
  await poll(async () => (await drawerState(page)).open === true, 3000);
  return drawerState(page);
}

// Best-effort: drive the Programs contrast UI to a REAL v3 selection contract. Never injects
// a forged contract — a dependent gate reports honestly if the UI cannot be driven.
export async function makeSelection(page, base, { temporal = false } = {}) {
  await gotoReady(page, base, '01_page.html');
  await poll(async () => (await page.$('#idgenes')) !== null, 8000);
  // Stage-1 loads its selection data (stage01_bins_v3.csv / controls) asynchronously — up to ~12s.
  // WAIT until the program (and, for temporal, condition) <select>s are actually POPULATED before
  // choosing: an empty select is a mid-load state, NOT an app refusal, and picking into it produces
  // no valid contrast so Identify never enables.
  const populated = await poll(async () => page.evaluate((temporal) => {
    const q = (s) => document.querySelector(s);
    const pa = q('.axsel.prog[data-ax="A"]'), pb = q('.axsel.prog[data-ax="B"]');
    const ca = q('.axsel.cond[data-ax="A"]'), cb = q('.axsel.cond[data-ax="B"]');
    const progOk = pa && pb && pa.options.length > 1 && pb.options.length > 1;
    const condOk = !temporal || (ca && cb && ca.options.length > 1 && cb.options.length > 1);
    return !!(progOk && condOk);
  }, temporal), 20000);
  if (!populated) return { ok: false, reason: 'Stage-1 program/condition options never populated (data load exceeded 20s)' };
  await page.evaluate((temporal) => {
    const fire = (el) => el && el.dispatchEvent(new Event('change', { bubbles: true }));
    const pick = (sel, idx) => {
      if (!sel || sel.options.length === 0) return;
      sel.selectedIndex = Math.min(idx, sel.options.length - 1);
      fire(sel);
    };
    const q = (s) => document.querySelector(s);
    pick(q('.axsel.prog[data-ax="A"]'), 0);
    const pb = q('.axsel.prog[data-ax="B"]');
    pick(pb, pb && pb.options.length > 1 ? 1 : 0);
    const ca = q('.axsel.cond[data-ax="A"]');
    const cb = q('.axsel.cond[data-ax="B"]');
    if (temporal) {
      pick(ca, ca && ca.options.length > 1 ? 1 : 0);
      pick(cb, cb && cb.options.length > 2 ? 2 : 0);
    } else {
      const i = ca && ca.options.length > 1 ? 1 : 0;
      pick(ca, i);
      pick(cb, i);
    }
  }, temporal);
  const enabled = await poll(async () => page.evaluate(() => {
    const b = document.getElementById('idgenes');
    return !!b && !b.disabled;
  }), 10000);
  if (!enabled) return { ok: false, reason: 'Identify (#idgenes) never enabled — contrast preflight not satisfied' };
  // Click fires window.location.assign('targets.html'); poll page.url() (runtime-agnostic —
  // avoids waitForNavigation API drift) and let the new document settle before reading storage.
  await page.evaluate(() => document.getElementById('idgenes').click());
  await poll(async () => /(^|\/)targets\.html(\?|#|$)/.test(page.url()), 15000);
  if (typeof page.waitForLoadState === 'function') await page.waitForLoadState('networkidle').catch(() => {});
  const stored = await page.evaluate((k) => {
    const g = (s) => { try { return s.getItem(k); } catch { return null; } };
    return { ls: g(localStorage), ss: g(sessionStorage) };
  }, V3_KEY);
  if (!stored.ls && !stored.ss) return { ok: false, reason: 'no v3 contract written to storage after Identify' };
  let contract = null;
  try {
    contract = JSON.parse(stored.ls || stored.ss);
  } catch {
    return { ok: false, reason: 'stored v3 contract is not valid JSON' };
  }
  return { ok: true, reason: 'selection created', contract, ls: stored.ls, ss: stored.ss, at: page.url() };
}

// Seed identical objects into a set of storage keys across both stores (U05/U07 attack).
export async function seedStorage(page, entries /* [{key, value}] */) {
  await page.evaluate((entries) => {
    for (const { key, value } of entries) {
      try { localStorage.setItem(key, value); } catch {}
      try { sessionStorage.setItem(key, value); } catch {}
    }
  }, entries);
}

export async function readStores(page, key) {
  return page.evaluate((k) => {
    const g = (s) => { try { return s.getItem(k); } catch { return null; } };
    return { ls: g(localStorage), ss: g(sessionStorage) };
  }, key);
}
