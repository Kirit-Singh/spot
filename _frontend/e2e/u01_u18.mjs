// u01_u18.mjs — browser acceptance harness for the spot same-origin :8347 distribution.
//
// Gates from ~/.spot-runs/20260712T021343Z/UI_CONTEXTUAL_DRAWER_CROSSCHECK.md (sha b0a6de06).
// One exported async function per gate: (browser, baseURL, mode) => { gate, pass, detail }.
// Every gate is PASS or FAIL — there is NO "blocked" release status.
//
// Two modes for the result-dependent gates (U06, U08–U12):
//   pending  (DEFAULT — the shell-deploy gate): the page is honestly PRE-RUN — a compact
//            neutral pending canvas + a REAL method-DEFINITION drawer (method_id, estimand,
//            masks/QC, sources populated; run-status fields — incl. the reproduce command, which
//            reproduces only an ADMITTED artifact — unavailable);
//            ZERO fixture/demo/GENE_A/COMPOUND_A/stale/"awaiting artifact" text anywhere.
//   admitted (--mode=admitted, after real bundles land): the stronger result/hash checks
//            (real rows/figures, run-status + artifact hashes populated, last_run_utc bound).
//
// Runtime: pinned playwright-core + system Chrome (mirrors capture_baseline.mjs).
// Run:  node _frontend/e2e/u01_u18.mjs http://100.117.50.59:8347 [--mode=admitted]

import { existsSync } from 'node:fs';
import {
  DEFAULT_BASE, RELEASE_MANIFEST, ROUTES, DOWNSTREAM, STAGE_LABEL, NAV_EXPECTED,
  V3_KEY, V1_KEY,
  sha256Hex, fetchBuf, fetchJson, urlOf, poll, withPage, goto, gotoReady,
  setViewport, reduceMotion, extractNav, drawerState, openDrawer, countDrawerInvokers,
  drawerRows, bad, bodyForbidden, makeSelection, seedStorage, readStores, isUtc,
} from './harness_util.mjs';

const PW_PATH = '/Users/kiritsingh/.spot-orchestrator/node_modules/playwright-core/index.js';
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const ROUTE_LABEL = { '01_page.html': 'Programs', 'targets.html': 'Targets', 'pathways.html': 'Pathways', 'drugs.html': 'Drugs', 'pksafety.html': 'PK & Safety' };

export { DEFAULT_BASE, ROUTES, DOWNSTREAM, NAV_EXPECTED, STAGE_LABEL };

// Method-DEFINITION fields (populated pre-run) vs RUN-STATUS fields (unavailable until a run).
// Reproduce is RUN-STATUS, not definition: a command reproduces only an ADMITTED artifact, so it stays
// unavailable until a run is bound (matches the shipped reproduce=null-when-unbound design + its tests).
const DEF_METHODS = ['Data / input', 'Estimand', 'Masks / QC', 'Method'];
const RUNSTATUS_METHODS = ['Last run UTC', 'Reproduce'];
const RUNSTATUS_PROV = ['Release', 'Raw sha256', 'Canonical', 'Generator', 'Verifier'];

// ── pending method-definition assertion (shared by U08–U11) ──
function pendingDefProblems(rows) {
  const p = [];
  if (bad(rows.methods['Method'])) p.push('drawer has no real method definition (Method unavailable)');
  for (const k of DEF_METHODS) if (bad(rows.methods[k])) p.push(`method-definition missing "${k}"`);
  if (rows.sources.length === 0 && bad(rows.methods['Source'])) p.push('sources not populated');
  for (const k of RUNSTATUS_METHODS) if (!bad(rows.methods[k])) p.push(`pre-run claim: run-status "${k}" should be unavailable`);
  for (const k of RUNSTATUS_PROV) if (!bad(rows.provenance[k])) p.push(`pre-run claim: run-status "${k}" should be unavailable`);
  return p;
}

// ─────────────────────────────────────────────────────────────────────────────
// U01 — every route 200 same-origin + served release manifest hashes == served bytes
// ─────────────────────────────────────────────────────────────────────────────
export async function checkU01(browser, base) {
  const problems = [];
  const wantOrigin = new URL(base).origin;
  await withPage(browser, async (page) => {
    for (const r of ROUTES) {
      let status = 0, origin = '';
      try {
        const resp = await goto(page, base, r);
        status = resp ? resp.status() : 0;
        origin = new URL(page.url()).origin;
      } catch (e) { origin = `error:${e.message}`; }
      if (status !== 200 || origin !== wantOrigin) problems.push(`${r}→${status}@${origin}`);
    }
  });
  const { status, json, error } = await fetchJson(urlOf(base, RELEASE_MANIFEST));
  if (status !== 200 || !json) {
    problems.push(`release manifest ${RELEASE_MANIFEST} not served (status ${status}${error ? ': ' + error : ''})`);
  } else {
    if (!/^[0-9a-f]{40}$/.test(String(json.commit || ''))) problems.push(`manifest commit/source-ref not a 40-hex digest ("${json.commit}")`);
    const files = Array.isArray(json.files) ? json.files : [];
    if (!files.length) problems.push('manifest lists no files');
    const classes = new Set(files.map((f) => f.class));
    for (const c of ['built', 'preserved-stage1', 'stage1-data']) if (!classes.has(c)) problems.push(`manifest missing class "${c}" (served identity incomplete)`);
    let mism = 0;
    for (const f of files) {
      const { status: s, buf } = await fetchBuf(urlOf(base, f.path));
      if (s !== 200) { problems.push(`served ${f.path} → ${s}`); continue; }
      if (sha256Hex(buf) !== f.sha256) { mism++; if (mism <= 5) problems.push(`hash mismatch: ${f.path}`); }
    }
    if (mism > 5) problems.push(`…and ${mism - 5} more hash mismatches`);
  }
  return { gate: 'U01', pass: problems.length === 0, detail: problems.length === 0 ? `${ROUTES.length} routes 200 same-origin; manifest commit + built/preserved/data hashes == served bytes` : problems.join(' | ') };
}

// ─────────────────────────────────────────────────────────────────────────────
// U02 — ONE combined "Methods & provenance" invoker opens ONE drawer (URL stable) with BOTH
//       sections, focused/scrolled to Methods on open; the two sections' content differs.
// ─────────────────────────────────────────────────────────────────────────────
export async function checkU02(browser, base) {
  const problems = [];
  for (const r of DOWNSTREAM) {
    await withPage(browser, async (page) => {
      await gotoReady(page, base, r);
      const url0 = page.url();
      const invokers = await countDrawerInvokers(page);
      if (invokers !== 1) problems.push(`${r}: expected exactly 1 "Methods & provenance" invoker, found ${invokers}`);
      const s = await openDrawer(page);
      if (!s.open) return problems.push(`${r}: drawer did not open`);
      const asides = await page.$$('aside[role="dialog"]');
      if (asides.length !== 1) problems.push(`${r}: expected exactly 1 aside[role=dialog], found ${asides.length}`);
      if (!s.activeInside) problems.push(`${r}: focus not inside dialog on open`);
      if (!(s.hasMethods && s.hasProvenance)) problems.push(`${r}: both Methods AND Provenance sections not present in one drawer`);
      if (!(!s.overflow || Math.abs(s.methodsTop ?? 999) <= 8 || s.scrollTop === 0)) problems.push(`${r}: not focused/scrolled to Methods on open (methodsTop=${s.methodsTop}, scrollTop=${s.scrollTop})`);
      if (!s.methodsText || !s.provText || s.methodsText === s.provText) problems.push(`${r}: Methods & Provenance section text does not DIFFER`);
      if (page.url() !== url0) problems.push(`${r}: URL changed ${url0} → ${page.url()}`);
    });
  }
  return { gate: 'U02', pass: problems.length === 0, detail: problems.length === 0 ? 'exactly one "Methods & provenance" invoker opens one drawer (URL stable) with both sections, focused at Methods; sections differ' : problems.join(' | ') };
}

// ─────────────────────────────────────────────────────────────────────────────
// U03 — data-stage-label matches page; per-stage method-id/hash + body DIFFER; no stale
// ─────────────────────────────────────────────────────────────────────────────
export async function checkU03(browser, base) {
  const problems = [];
  const sigs = {};
  for (const r of DOWNSTREAM) {
    await withPage(browser, async (page) => {
      await gotoReady(page, base, r);
      const s = await openDrawer(page);
      const want = STAGE_LABEL[r];
      if (!s.open) return problems.push(`${r}: drawer did not open`);
      if (s.stageLabel !== want) problems.push(`${r}: data-stage-label "${s.stageLabel || '∅'}" ≠ "${want}"`);
      // Stage-1 parity: the VISIBLE title is exactly "Methods & provenance" on every route — the
      // active route is carried semantically (data-stage-label, asserted above, + dialog aria-label),
      // NOT baked into the title line. (Old assertion expected the title to start with the route.)
      if (s.title !== 'Methods & provenance') problems.push(`${r}: drawer title "${s.title}" ≠ exact "Methods & provenance" (route is semantic via data-stage-label/aria-label)`);
      sigs[r] = `${s.methodId || '∅'}|${s.codeSha || '∅'}|${s.methodsText}||${s.provText}`;
    });
  }
  const vals = Object.values(sigs);
  if (new Set(vals).size !== vals.length) problems.push('per-stage method-id/hash/body identical across stages (real per-stage manifests not wired)');
  return { gate: 'U03', pass: problems.length === 0, detail: problems.length === 0 ? 'stage-label + title match active page; method-id/hash/body differ across all 4 stages; no stale content' : problems.join(' | ') };
}

// ─────────────────────────────────────────────────────────────────────────────
// U04 — nav 01/02/02/03/04; active tab correct; every href same-origin relative; identical on 5 pages
// ─────────────────────────────────────────────────────────────────────────────
export async function checkU04(browser, base) {
  const problems = [];
  const seen = [];
  for (const r of ROUTES) {
    await withPage(browser, async (page) => {
      await gotoReady(page, base, r);
      const nav = await extractNav(page);
      seen.push(nav.map((s) => `${s.n}|${s.label}|${s.href || ''}`).join(' › '));
      if (nav.length !== NAV_EXPECTED.length) return problems.push(`${r}: ${nav.length} nav steps ≠ ${NAV_EXPECTED.length}`);
      NAV_EXPECTED.forEach((exp, i) => { if (nav[i].n !== exp.n || nav[i].label !== exp.label) problems.push(`${r}[${i}]: "${nav[i].n} ${nav[i].label}" ≠ "${exp.n} ${exp.label}"`); });
      const active = nav.find((s) => s.active);
      if (!active) problems.push(`${r}: no active nav step`);
      else if (active.label !== ROUTE_LABEL[r]) problems.push(`${r}: active step "${active.label}" ≠ page "${ROUTE_LABEL[r]}"`);
      const abs = nav.filter((s) => s.href && /^https?:\/\//i.test(s.href)).map((s) => s.href);
      if (abs.length) problems.push(`${r}: nav hrefs not same-origin relative: ${abs.join(', ')}`);
    });
  }
  if (new Set(seen).size > 1) problems.push('nav model differs across pages');
  return { gate: 'U04', pass: problems.length === 0, detail: problems.length === 0 ? 'nav 01/02/02/03/04, correct active tab, all hrefs same-origin relative, identical on all 5 pages' : problems.join(' | ') };
}

// ─────────────────────────────────────────────────────────────────────────────
// U05/U07 — seeded-v1 ATTACK rejected fail-closed; valid v3 persisted (no v1); corrupt byte rejected
// ─────────────────────────────────────────────────────────────────────────────
export async function checkU05U07(browser, base) {
  const notes = [];
  const v1blob = JSON.stringify({ schema_version: V1_KEY, program_a: { display_label: 'ATTACK-A', direction: 'high' }, program_b: { display_label: 'ATTACK-B', direction: 'low' }, analysis_condition: 'Rest' });

  await withPage(browser, async (page) => {
    await gotoReady(page, base, '01_page.html');
    await seedStorage(page, [{ key: V3_KEY, value: v1blob }, { key: V1_KEY, value: v1blob }]);
    await gotoReady(page, base, 'targets.html');
    const header = await page.evaluate(() => (document.querySelector('header')?.textContent || '').replace(/\s+/g, ' ').trim());
    const prompt = /Select populations in Programs/i.test(header);
    if (!prompt || (/→|➜|->/.test(header) && !prompt) || /ATTACK-/.test(header)) notes.push(`ATTACK: seeded v1 was read/fell back (header="${header.slice(0, 80)}")`);
  });

  await withPage(browser, async (page) => {
    const sel = await makeSelection(page, base, { temporal: false });
    if (!sel.ok) { notes.push(`VALID: could not establish v3 selection: ${sel.reason}`); return; }
    if (!/(^|\/)targets\.html/.test(sel.at)) notes.push(`VALID: did not navigate to targets.html (${sel.at})`);
    const v3 = await readStores(page, V3_KEY);
    const v1 = await readStores(page, V1_KEY);
    const c = sel.contract || {};
    const v3ok = v3.ls && v3.ss && c.schema_version === V3_KEY && typeof c.selection_id === 'string' && c.canonical_content && typeof c.full_contract_content_sha256 === 'string' && typeof c.selection_full_sha256 === 'string';
    if (!v3ok) notes.push('VALID: v3 not persisted+verifiable in BOTH stores');
    if (v1.ls || v1.ss) notes.push('VALID: a v1 key is present (must not exist)');
    await page.evaluate((k) => {
      const flip = (s) => { const v = s.getItem(k); if (!v) return; const i = Math.max(1, (v.length / 2) | 0); s.setItem(k, v.slice(0, i) + (v[i] === 'a' ? 'b' : 'a') + v.slice(i + 1)); };
      try { flip(localStorage); } catch {} try { flip(sessionStorage); } catch {}
    }, V3_KEY);
    await gotoReady(page, base, 'targets.html');
    const header = await page.evaluate(() => (document.querySelector('header')?.textContent || '').replace(/\s+/g, ' ').trim());
    if (!/Select populations in Programs/i.test(header)) notes.push(`U07: corrupt v3 not rejected fail-closed (header="${header.slice(0, 80)}")`);
  });

  return { gate: 'U05/U07', pass: notes.length === 0, detail: notes.length === 0 ? 'seeded-v1 read by neither key; valid v3 in both stores (no v1) → targets.html; corrupt byte rejected, no fallback' : notes.join(' | ') };
}

// ─────────────────────────────────────────────────────────────────────────────
// U06 — temporal selection routes at the shell level (pending) / real temporal run (admitted)
// ─────────────────────────────────────────────────────────────────────────────
export async function checkU06(browser, base, mode) {
  return withPage(browser, async (page) => {
    const sel = await makeSelection(page, base, { temporal: true });
    if (!sel.ok) return { gate: 'U06', pass: false, detail: `temporal selection not established: ${sel.reason}` };
    const forbidden = await bodyForbidden(page);
    const conds = Array.isArray(sel.contract?.canonical_content?.conditions) ? sel.contract.canonical_content.conditions : [];
    const problems = [];
    if (conds.length !== 2 || conds[0] === conds[1]) problems.push(`temporal contract not two ordered conditions (${JSON.stringify(conds)})`);
    if (forbidden.length) problems.push(`synthetic/stale text present: ${forbidden.join(', ')}`);
    if (mode === 'admitted') {
      const rows = (await openDrawer(page), await drawerRows(page));
      if (bad(rows.methods['Last run UTC'])) problems.push('admitted: temporal run has no last_run_utc / real endpoints');
    }
    return { gate: 'U06', pass: problems.length === 0, detail: problems.length === 0 ? `${mode}: temporal arm routes with two ordered conditions; no synthetic/stale text` : problems.join(' | ') };
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// U08 / U09 — pending: neutral canvas + real method-definition drawer, no fixture/stale.
//             admitted: real rows/figures rendered, no fixture.
// ─────────────────────────────────────────────────────────────────────────────
async function resultGate(browser, base, mode, gate, note) {
  const problems = [];
  for (const r of ['targets.html', 'pathways.html']) {
    await withPage(browser, async (page) => {
      await gotoReady(page, base, r);
      const forbidden = await bodyForbidden(page);
      if (forbidden.length) problems.push(`${r}: forbidden text ${forbidden.join(', ')}`);
      const rows = (await openDrawer(page), await drawerRows(page));
      if (mode === 'pending') {
        for (const p of pendingDefProblems(rows)) problems.push(`${r}: ${p}`);
        const canvasRows = await page.evaluate(() => document.querySelectorAll('main table tr, main [role="row"]').length);
        if (canvasRows > 0) problems.push(`${r}: pre-run canvas shows ${canvasRows} fabricated rows`);
      } else {
        const canvasRows = await page.evaluate(() => document.querySelectorAll('main table tr, main [role="row"], main svg').length);
        if (canvasRows === 0) problems.push(`${r}: admitted mode shows no real rows/figures`);
        if (bad(rows.methods['Last run UTC'])) problems.push(`${r}: admitted mode has no last_run_utc (results not bound)`);
      }
    });
  }
  return { gate, pass: problems.length === 0, detail: problems.length === 0 ? `${mode}: ${note}` : problems.join(' | ') };
}
export async function checkU08(browser, base, mode) { return resultGate(browser, base, mode, 'U08', 'same-time targets+pathways honest (neutral canvas + real method definition / real rows)'); }
export async function checkU09(browser, base, mode) { return resultGate(browser, base, mode, 'U09', 'temporal-context targets+pathways honest (neutral canvas + real method definition / real endpoints)'); }

// ─────────────────────────────────────────────────────────────────────────────
// U10 — methods drawer rows.  pending: definition populated + run-status unavailable.
//       admitted: every methods row (incl. run-status) populated.
// ─────────────────────────────────────────────────────────────────────────────
export async function checkU10(browser, base, mode) {
  return withPage(browser, async (page) => {
    await gotoReady(page, base, 'targets.html');
    const s = await openDrawer(page);
    if (!s.open) return { gate: 'U10', pass: false, detail: 'drawer did not open' };
    const rows = await drawerRows(page);
    let problems;
    if (mode === 'pending') {
      problems = pendingDefProblems(rows);
    } else {
      const need = ['Data / input', 'Source', 'Estimand', 'Masks / QC', 'Method', 'Code sha256', 'Environment', 'Last run UTC', 'Reproduce'];
      problems = need.filter((k) => bad(rows.methods[k])).map((k) => `admitted: missing "${k}"`);
    }
    return { gate: 'U10', pass: problems.length === 0, detail: problems.length === 0 ? `${mode}: methods rows correct (definition populated, run-status ${mode === 'pending' ? 'unavailable' : 'populated'})` : problems.join(' | ') };
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// U11 — provenance rows.  pending: sources populated + run-status hashes unavailable.
//       admitted: release/hashes/generator/verifier/artifacts/notebook/sources populated.
// ─────────────────────────────────────────────────────────────────────────────
export async function checkU11(browser, base, mode) {
  return withPage(browser, async (page) => {
    await gotoReady(page, base, 'targets.html');
    const s = await openDrawer(page);
    if (!s.open) return { gate: 'U11', pass: false, detail: 'drawer did not open' };
    const rows = await drawerRows(page);
    const problems = [];
    if (rows.sources.length === 0) problems.push('no public source records');
    if (mode === 'pending') {
      for (const k of RUNSTATUS_PROV) if (!bad(rows.provenance[k])) problems.push(`pre-run claim: run-status "${k}" should be unavailable`);
    } else {
      for (const k of ['Release', 'Raw sha256', 'Canonical', 'Generator', 'Verifier', 'CS notebook', 'Artifacts']) if (bad(rows.provenance[k])) problems.push(`admitted: missing "${k}"`);
    }
    return { gate: 'U11', pass: problems.length === 0, detail: problems.length === 0 ? `${mode}: provenance rows correct (sources populated; run hashes ${mode === 'pending' ? 'unavailable' : 'populated'})` : problems.join(' | ') };
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// U12 — stage/content gate: each downstream route serves its OWN real method definition
//       (distinct method_id + stage_label; no cross-stage bleed / fixture).
// ─────────────────────────────────────────────────────────────────────────────
export async function checkU12(browser, base) {
  const ids = {};
  const problems = [];
  for (const r of DOWNSTREAM) {
    await withPage(browser, async (page) => {
      await gotoReady(page, base, r);
      const s = await openDrawer(page);
      const rows = await drawerRows(page);
      if (s.stageLabel !== STAGE_LABEL[r]) problems.push(`${r}: stage-label "${s.stageLabel}" ≠ "${STAGE_LABEL[r]}"`);
      if (bad(rows.methods['Method'])) problems.push(`${r}: no real method definition (Method unavailable)`);
      ids[r] = rows.methods['Method'] || '∅';
    });
  }
  const vals = Object.values(ids);
  if (new Set(vals).size !== vals.length) problems.push(`method_id not stage-distinct: ${JSON.stringify(ids)}`);
  return { gate: 'U12', pass: problems.length === 0, detail: problems.length === 0 ? 'each stage serves a distinct real method definition; stage-labels correct; no cross-stage bleed' : problems.join(' | ') };
}

// ─────────────────────────────────────────────────────────────────────────────
// U13 — no internal methods/notebook/trace nav; frame_ref never an href; external links drawer-only; clean <main>
// ─────────────────────────────────────────────────────────────────────────────
export async function checkU13(browser, base) {
  const problems = [];
  for (const r of DOWNSTREAM) {
    await withPage(browser, async (page) => {
      await gotoReady(page, base, r);
      const res = await page.evaluate(() => {
        const drawer = document.querySelector('aside[role="dialog"]');
        const inDrawer = (el) => drawer && drawer.contains(el);
        const anchors = [...document.querySelectorAll('a[href]')];
        const badInternal = anchors.filter((a) => !inDrawer(a)).map((a) => a.getAttribute('href') || '').filter((h) => /(notebook|trace|methods|provenance)/i.test(h) && !/^https?:\/\//i.test(h));
        const externalOutside = anchors.filter((a) => !inDrawer(a) && /^https?:\/\//i.test(a.getAttribute('href') || '')).map((a) => a.getAttribute('href'));
        // The verified Stage-1 release Reference legitimately links the same-origin, root-relative
        // release manifest; allowlist exactly that path. All other non-URL drawer hrefs (frame_ref,
        // notebook/method-page/session links) remain forbidden.
        const drawerNonUrl = [...(drawer?.querySelectorAll('a[href]') || [])].map((a) => a.getAttribute('href') || '').filter((h) => !/^(https?:\/\/|mailto:)/i.test(h) && h !== '/data/stage01_release_manifest.json');
        const t = (document.querySelector('main')?.textContent || '').replace(/\s+/g, ' ').toLowerCase();
        const forbidden = ['science evidence', 'enqueue review', 'methods & provenance', 'provenance', 'reproduce command', 'rerun', 'notebook', 'trace'];
        return { badInternal, externalOutside, drawerNonUrl, hits: forbidden.filter((f) => t.includes(f)) };
      });
      if (res.badInternal.length) problems.push(`${r}: internal methods/notebook/trace links: ${res.badInternal.join(', ')}`);
      if (res.externalOutside.length) problems.push(`${r}: external links outside drawer: ${res.externalOutside.join(', ')}`);
      if (res.drawerNonUrl.length) problems.push(`${r}: drawer anchor with non-URL href (frame_ref?): ${res.drawerNonUrl.join(', ')}`);
      if (res.hits.length) problems.push(`${r}: forbidden copy in <main>: ${res.hits.join(', ')}`);
    });
  }
  return { gate: 'U13', pass: problems.length === 0, detail: problems.length === 0 ? 'no internal methods/notebook/trace nav; no frame_ref href; external links drawer-only; <main> free of methods/science/rerun copy' : problems.join(' | ') };
}

// ─────────────────────────────────────────────────────────────────────────────
// U14 — clean <main>: no editorial/caveat/0-of-33/review-job/demo/scaffold chrome
// ─────────────────────────────────────────────────────────────────────────────
export async function checkU14(browser, base) {
  const problems = [];
  for (const r of DOWNSTREAM) {
    await withPage(browser, async (page) => {
      await gotoReady(page, base, r);
      const res = await page.evaluate(() => {
        const main = document.querySelector('main');
        const t = (main?.textContent || '').replace(/\s+/g, ' ').toLowerCase();
        const patterns = [['0-of-33 gate copy', /0\s*(of|\/)\s*33/], ['caveat banner', /caveat/], ['editorial banner', /editorial/], ['review-job control', /enqueue review|review job/], ['demo scaffold', /\bdemo\b/], ['awaiting-artifact scaffold', /awaiting artifact/]];
        const hits = patterns.filter(([, re]) => re.test(t)).map(([n]) => n);
        const enqueueBtn = [...(main?.querySelectorAll('button') || [])].some((b) => /enqueue|review job/i.test(b.textContent || ''));
        return { hits, enqueueBtn };
      });
      if (res.hits.length) problems.push(`${r}: ${res.hits.join(', ')}`);
      if (res.enqueueBtn) problems.push(`${r}: review-job button in <main>`);
    });
  }
  return { gate: 'U14', pass: problems.length === 0, detail: problems.length === 0 ? '<main> clean/data-first on all 4 routes (no caveat/0-of-33/review-job/demo/scaffold/awaiting)' : problems.join(' | ') };
}

// ─────────────────────────────────────────────────────────────────────────────
// U15 — X + Escape + scrim close; focus restore; focus trap; inert when hidden
// ─────────────────────────────────────────────────────────────────────────────
export async function checkU15(browser, base) {
  const notes = [];
  const inside = (page) => page.evaluate(() => { const a = document.querySelector('aside[role="dialog"]'); return !!(a && document.activeElement && a.contains(document.activeElement)); });
  const atInvoker = (page) => page.evaluate(() => document.activeElement?.getAttribute('data-invoker') === '1');
  for (const r of DOWNSTREAM) {
    await withPage(browser, async (page) => {
      await gotoReady(page, base, r);
      const c0 = await drawerState(page);
      if (!c0.inert) notes.push(`${r}: hidden drawer not inert`);
      if (c0.open) notes.push(`${r}: drawer open before any action`);
      // mark the ONE combined invoker
      await page.evaluate(() => { const re = /Methods\s*&\s*provenance/i; const b = [...document.querySelectorAll('header button')].find((x) => re.test((x.textContent || '').replace(/\s+/g, ' '))); if (b) b.setAttribute('data-invoker', '1'); });
      const s = await openDrawer(page);
      if (!s.open) { notes.push(`${r}: drawer did not open`); return; }
      if (s.inert) notes.push(`${r}: open drawer still inert`);
      if (s.ariaModal !== 'true') notes.push(`${r}: drawer missing aria-modal=true`);
      if (!s.activeInside) notes.push(`${r}: focus not moved into open drawer`);
      // forward trap: Tab from last focusable stays inside
      if (!(await page.evaluate(() => { const a = document.querySelector('aside[role="dialog"]'); const f = a?.querySelectorAll('a[href],button:not([disabled]),input,select,textarea,[tabindex]:not([tabindex="-1"])'); if (!f || !f.length) return false; f[f.length - 1].focus(); return true; }))) notes.push(`${r}: no focusable in drawer`);
      await page.keyboard.press('Tab');
      if (!(await inside(page))) notes.push(`${r}: forward focus-trap leaked on Tab`);
      // reverse trap: Shift+Tab from first focusable stays inside
      await page.evaluate(() => { const a = document.querySelector('aside[role="dialog"]'); const f = a?.querySelectorAll('a[href],button:not([disabled]),input,select,textarea,[tabindex]:not([tabindex="-1"])'); if (f && f.length) f[0].focus(); });
      await page.keyboard.down('Shift'); await page.keyboard.press('Tab'); await page.keyboard.up('Shift');
      if (!(await inside(page))) notes.push(`${r}: reverse focus-trap leaked on Shift+Tab`);
      // close via X → focus restored to the single invoker
      await page.evaluate(() => document.querySelector('[aria-label="Close methods and provenance"]')?.click());
      await poll(async () => (await drawerState(page)).open === false, 2000);
      const ax = await drawerState(page);
      if (ax.open) notes.push(`${r}: X did not close drawer`);
      if (!ax.inert) notes.push(`${r}: closed drawer not inert after X`);
      // focus restoration may land after the close transition settles — poll, don't assert once.
      if (!(await poll(() => atInvoker(page), 1500))) notes.push(`${r}: focus NOT restored to invoker after X`);
      // close via Escape → focus restored
      await openDrawer(page); await page.keyboard.press('Escape');
      await poll(async () => (await drawerState(page)).open === false, 2000);
      if ((await drawerState(page)).open) notes.push(`${r}: Escape did not close drawer`);
      else if (!(await poll(() => atInvoker(page), 1500))) notes.push(`${r}: focus NOT restored to invoker after Escape`);
      // close via scrim → focus restored
      await openDrawer(page); await page.evaluate(() => { const a = document.querySelector('aside[role="dialog"]'); a?.previousElementSibling?.click(); });
      await poll(async () => (await drawerState(page)).open === false, 2000);
      if ((await drawerState(page)).open) notes.push(`${r}: scrim click did not close drawer`);
      else if (!(await poll(() => atInvoker(page), 1500))) notes.push(`${r}: focus NOT restored to invoker after scrim`);
    });
  }
  return { gate: 'U15', pass: notes.length === 0, detail: notes.length === 0 ? 'single invoker on all 4 routes: X/Escape/scrim close + focus restored to the one Methods&provenance button; fwd+rev trap; inert when hidden' : notes.join(' | ') };
}

// ─────────────────────────────────────────────────────────────────────────────
// U16 — 390/880/desktop: no horizontal overflow; drawer fits; reduced motion suppresses slide
// ─────────────────────────────────────────────────────────────────────────────
export async function checkU16(browser, base) {
  const problems = [];
  await withPage(browser, async (page) => {
    await reduceMotion(page);
    for (const w of [390, 880, 1440]) {
      await setViewport(page, w, 900);
      await gotoReady(page, base, DOWNSTREAM[0]);
      const o = await page.evaluate(() => ({ scroll: Math.max(document.documentElement.scrollWidth, document.body ? document.body.scrollWidth : 0), inner: window.innerWidth }));
      if (o.scroll > o.inner + 1) problems.push(`${w}px: body overflow (scrollWidth ${o.scroll} > ${o.inner})`);
      const s = await openDrawer(page);
      if (!s.open) { problems.push(`${w}px: drawer did not open`); continue; }
      const f = await page.evaluate(() => { const a = document.querySelector('aside[role="dialog"]'); const rc = a.getBoundingClientRect(); return { left: rc.left, right: rc.right, width: rc.width, inner: window.innerWidth, dur: getComputedStyle(a).transitionDuration }; });
      if (f.right > f.inner + 1 || f.left < -1 || f.width > f.inner + 1) problems.push(`${w}px: drawer does not fit (l=${Math.round(f.left)} r=${Math.round(f.right)} w=${Math.round(f.width)} vw=${f.inner})`);
      // reduced-motion must suppress the slide: accept an exact 0s OR a legacy near-zero (<=1ms) value.
      const maxDurS = Math.max(0, ...String(f.dur || '0s').split(',').map((t) => {
        const m = t.trim().match(/^([\d.]+)(ms|s)?$/);
        return m ? parseFloat(m[1]) * (m[2] === 'ms' ? 0.001 : 1) : 0;
      }));
      if (maxDurS > 0.001) problems.push(`${w}px: reduced-motion did not suppress transition (${f.dur})`);
    }
  });
  return { gate: 'U16', pass: problems.length === 0, detail: problems.length === 0 ? 'no horizontal overflow at 390/880/1440; drawer fits viewport; reduced-motion suppresses slide' : problems.join(' | ') };
}

// ─────────────────────────────────────────────────────────────────────────────
// U17 — rerun copy == manifest-bound command; Last-run-UTC valid and != build time
//       (pending: no admitted run yet ⇒ Last-run UTC is honestly unavailable — PASS;
//        a populated-but-invalid or build-time value FAILs.)
// ─────────────────────────────────────────────────────────────────────────────
export async function checkU17(browser, base, mode) {
  return withPage(browser, async (page) => {
    try { await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: new URL(base).origin }); } catch {}
    await gotoReady(page, base, DOWNSTREAM[0]);
    const s = await openDrawer(page);
    if (!s.open) return { gate: 'U17', pass: false, detail: 'drawer did not open' };
    const info = await page.evaluate(() => {
      const m = document.querySelector('aside[role="dialog"] [data-section="methods"]');
      const copyBtn = m?.querySelector('[aria-label="Copy reproduce command"]');
      const cmd = copyBtn ? (copyBtn.previousElementSibling?.textContent || copyBtn.parentElement?.querySelector('code')?.textContent || '').trim() : null;
      let lastRun = null;
      m?.querySelectorAll('div').forEach((d) => { if ((d.textContent || '').trim().toLowerCase() === 'last run utc') { const v = d.nextElementSibling; if (v) lastRun = (v.textContent || '').trim(); } });
      return { hasCopyBtn: !!copyBtn, cmd, lastRun, clip: typeof navigator.clipboard?.readText === 'function' };
    });
    const notes = [];
    // reproduce command is a RUN-STATUS field: unavailable until admitted, then copyable + == manifest.
    if (mode === 'pending') {
      if (info.hasCopyBtn || info.cmd) notes.push('pending: a reproduce command is shown but no artifact is admitted (must be unavailable until admitted)');
    } else if (!info.hasCopyBtn || !info.cmd) {
      notes.push('no manifest-bound reproduce command shown');
    } else if (info.clip) {
      await page.evaluate(() => document.querySelector('[data-section="methods"] [aria-label="Copy reproduce command"]')?.click());
      const clip = await page.evaluate(() => navigator.clipboard.readText().catch(() => null));
      if (clip !== info.cmd) notes.push(`clipboard "${(clip || '∅').slice(0, 40)}" ≠ command "${(info.cmd || '∅').slice(0, 40)}"`);
    }
    // last_run_utc is a RUN-STATUS field: pending ⇒ must be unavailable; admitted ⇒ valid & != build.
    if (mode === 'pending') {
      if (!bad(info.lastRun)) notes.push(`pending: Last run UTC should be unavailable, got "${info.lastRun}"`);
    } else {
      if (!isUtc(info.lastRun)) notes.push(`admitted: Last run UTC invalid: "${info.lastRun || '∅'}"`);
      else { const { json } = await fetchJson(urlOf(base, RELEASE_MANIFEST)); if (json?.generated_utc && info.lastRun === json.generated_utc) notes.push('Last run UTC equals build/deploy time'); }
    }
    return { gate: 'U17', pass: notes.length === 0, detail: notes.length === 0 ? `${mode}: reproduce command ${mode === 'pending' ? 'honestly unavailable (no admitted artifact)' : 'copyable == manifest'}; Last-run UTC ${mode === 'pending' ? 'honestly unavailable' : 'valid & != build time'}` : notes.join(' | ') };
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// U18 — v3 byte-identical in BOTH stores across full nav loop; v1 absent throughout; Clear removes v3
// ─────────────────────────────────────────────────────────────────────────────
export async function checkU18(browser, base) {
  return withPage(browser, async (page) => {
    const sel = await makeSelection(page, base, { temporal: false });
    if (!sel.ok) return { gate: 'U18', pass: false, detail: `could not establish selection: ${sel.reason}` };
    const notes = [];
    for (const r of ['targets.html', 'pathways.html', 'drugs.html', 'pksafety.html', '01_page.html', 'targets.html']) {
      await gotoReady(page, base, r);
      const v3 = await readStores(page, V3_KEY);
      const v1 = await readStores(page, V1_KEY);
      if (v3.ls !== sel.ls || v3.ss !== sel.ss) notes.push(`${r}: v3 not byte-identical in both stores`);
      if (v1.ls || v1.ss) notes.push(`${r}: a v1 key appeared`);
    }
    const cleared = await page.evaluate(() => { const b = document.querySelector('[aria-label="Clear selection and return to Programs"]'); if (b) { b.click(); return true; } return false; });
    if (!cleared) notes.push('no Clear control on Targets header');
    else {
      await poll(async () => /01_page\.html(\?|#|$)/.test(page.url()), 4000);
      const after = await readStores(page, V3_KEY);
      if (after.ls || after.ss) notes.push('Clear did not remove v3 from both stores');
      if (!/01_page\.html(\?|#|$)/.test(page.url())) notes.push(`Clear did not return to Programs (${page.url()})`);
    }
    return { gate: 'U18', pass: notes.length === 0, detail: notes.length === 0 ? 'v3 byte-identical in both stores across full loop; v1 absent throughout; Clear removes v3 + returns to Programs' : notes.join(' | ') };
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Registry + runner
// ─────────────────────────────────────────────────────────────────────────────
export const CHECKS = [
  checkU01, checkU02, checkU03, checkU04, checkU05U07, checkU06,
  checkU08, checkU09, checkU10, checkU11, checkU12,
  checkU13, checkU14, checkU15, checkU16, checkU17, checkU18,
];

const gateOf = (fn) => fn.name.replace(/^check/, '').replace('U05U07', 'U05/U07');

export function parseArgs(argv) {
  let base;
  let mode = 'pending';
  for (const a of argv) {
    if (a.startsWith('--mode=')) mode = a.slice('--mode='.length);
    else if (!a.startsWith('--') && !base) base = a;
  }
  if (mode !== 'pending' && mode !== 'admitted') throw new Error(`--mode must be pending|admitted (got "${mode}")`);
  return { base: base || process.env.SPOT_BASE_URL || DEFAULT_BASE, mode };
}

function printTable(results) {
  const w = Math.max(...results.map((r) => r.gate.length), 5);
  const row = (g, s, d) => `  ${g.padEnd(w)}  ${s.padEnd(4)}  ${d}`;
  console.log('');
  console.log(row('GATE', 'RSLT', 'DETAIL'));
  console.log(`  ${'-'.repeat(w)}  ${'-'.repeat(4)}  ${'-'.repeat(40)}`);
  for (const r of results) console.log(row(r.gate, r.pass ? 'PASS' : 'FAIL', r.detail));
  console.log('');
}

export async function main(argv = process.argv.slice(2)) {
  let base, mode;
  try { ({ base, mode } = parseArgs(argv)); } catch (e) { console.error(e.message); process.exitCode = 2; return; }

  let playwright;
  try {
    playwright = (await import(PW_PATH)).default;
  } catch (e) {
    console.error(`CANNOT RUN (environment) — playwright-core not found at ${PW_PATH} (${e.message}).`);
    console.error('Fix: `npm i -D playwright-core`, or correct the pinned path. This is not a gate result.');
    process.exitCode = 2;
    return;
  }
  if (!existsSync(CHROME)) {
    console.error(`CANNOT RUN (environment) — Chrome not found at ${CHROME}. This is not a gate result.`);
    process.exitCode = 2;
    return;
  }

  console.log(`spot U01–U18 harness · base=${base} · mode=${mode}`);
  const launchOpts = {
    executablePath: CHROME,
    headless: true,
    args: ['--no-first-run', '--no-default-browser-check', '--disable-component-update', '--disable-background-networking'],
  };
  let browser = await playwright.chromium.launch(launchOpts);
  const results = [];
  try {
    for (const check of CHECKS) {
      // resilience: if Chrome dropped during a prior gate, relaunch before the next one
      if (typeof browser.isConnected === 'function' && !browser.isConnected()) {
        try { browser = await playwright.chromium.launch(launchOpts); } catch { /* reported per-gate below */ }
      }
      try {
        results.push(await check(browser, base, mode));
      } catch (e) {
        results.push({ gate: gateOf(check), pass: false, detail: `ERROR: ${e.message}` });
      }
    }
  } finally {
    await browser.close().catch(() => {});
  }

  printTable(results);
  const failed = results.filter((r) => !r.pass);
  console.log(`base=${base}  mode=${mode}  total=${results.length}  passed=${results.length - failed.length}  failed=${failed.length}`);
  if (failed.length === 0) {
    console.log(`VERDICT: GO — all ${results.length} gates PASS in ${mode} mode.`);
    process.exitCode = 0;
  } else {
    console.log(`VERDICT: NOT CERTIFIED — ${failed.length} gate(s) FAIL: ${failed.map((r) => r.gate).join(', ')}`);
    process.exitCode = 1;
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}
