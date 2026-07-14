// Focused acceptance for a PARTIAL admitted release: Targets is bound to W3's admitted
// selection-independent Direct+Temporal display projection while Pathways remains intentionally unbound.

import { existsSync } from 'node:fs';
import { makeSelection, poll, gotoReady, openDrawer, drawerRows, urlOf } from './harness_util.mjs';

const PW_PATH = '/Users/kiritsingh/.spot-orchestrator/node_modules/playwright-core/index.js';
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const base = (process.argv[2] || 'http://100.117.50.59:8347').replace(/\/+$/, '');

function assert(ok, message) { if (!ok) throw new Error(message); }

async function checkSelection(browser, temporal) {
  const page = await browser.newPage();
  try {
    const selected = await makeSelection(page, base, { temporal });
    assert(selected.ok, `${temporal ? 'temporal' : 'within'} selection failed: ${selected.reason}`);
    const canvas = await poll(() => page.$('[data-real-canvas][data-route="targets"]'), 15000);
    assert(canvas, `${temporal ? 'temporal' : 'within'} Targets canvas did not bind`);
    const result = await page.evaluate(() => ({
      rows: document.querySelectorAll('main table tbody tr').length,
      facets: document.querySelectorAll('main section[aria-label$="effect-rank facet"]').length,
      hpaLinks: document.querySelectorAll('main a[href^="https://www.proteinatlas.org/ENSG"][target="_blank"][rel~="noopener"]').length,
      axisLabels: [...document.querySelectorAll('main svg text')].map((node) => node.textContent || ''),
      text: document.querySelector('main')?.textContent || '',
      headerTitle: (document.querySelector('header span[title]')?.textContent || '').replace(/\s+/g, ' ').trim(),
    }));
    assert(result.rows > 0, `${temporal ? 'temporal' : 'within'} Targets rendered no rows`);
    assert(result.facets === 2, `${temporal ? 'temporal' : 'within'} Targets did not render exactly two selected-program facets`);
    assert(result.hpaLinks > 0, `${temporal ? 'temporal' : 'within'} Targets rendered no typed Ensembl HPA links`);
    assert(result.axisLabels.includes('Rank evidence −log10(rank/N)'), `${temporal ? 'temporal' : 'within'} rank-evidence axis is missing`);
    assert(!/pending independent admission|not generated|fixture|demo|combined|balanced|p[_ -]?value|q[_ -]?value/i.test(result.text),
      `${temporal ? 'temporal' : 'within'} Targets canvas contains pending/forbidden text`);
    const conditions = selected.contract?.canonical_content?.conditions || [];
    const conditionLabel = (c) => ({ Rest: 'rest', Stim8hr: '8 hr', Stim48hr: '48 hr' }[c] || String(c).toLowerCase());
    const labelA = conditionLabel(conditions[0]);
    const labelB = conditionLabel(conditions[1] ?? conditions[0]);
    assert(result.headerTitle.includes(`(at ${labelA})`), `Targets header lost A endpoint condition ${conditions[0]}`);
    assert(result.headerTitle.includes(`(at ${labelB})`), `Targets header lost B endpoint condition ${conditions[1] ?? conditions[0]}`);
    if (temporal) {
      assert(conditions[0] !== conditions[1], 'temporal acceptance did not select distinct conditions');
      assert(result.headerTitle.indexOf(`(at ${labelA})`) < result.headerTitle.lastIndexOf(`(at ${labelB})`),
        `Targets header collapsed or reversed temporal endpoints: ${result.headerTitle}`);
    }
    await openDrawer(page);
    const rows = await drawerRows(page);
    assert(rows.provenance.Verifier === 'admitted', 'Targets drawer is not bound to admitted verifier status');
    assert(rows.methods['Last run UTC'] === '2026-07-13T20:58:11Z', 'Targets Last run UTC does not match the admitted receipt');
    assert(!/^—$|unavailable/i.test(rows.methods.Reproduce || ''), 'Targets reproduce command is unavailable');
    return result.rows;
  } finally { await page.close(); }
}

async function main() {
  assert(existsSync(CHROME), `Chrome missing at ${CHROME}`);
  const playwright = (await import(PW_PATH)).default;
  const browser = await playwright.chromium.launch({ executablePath: CHROME, headless: true,
    args: ['--no-first-run', '--no-default-browser-check', '--disable-component-update', '--disable-background-networking'] });
  try {
    const withinRows = await checkSelection(browser, false);
    const temporalRows = await checkSelection(browser, true);
    const page = await browser.newPage();
    try {
      await gotoReady(page, base, 'pathways.html');
      assert(!(await page.$('[data-real-canvas][data-route="pathways"]')),
        'Pathways rendered without an admitted pathway lane');
    } finally { await page.close(); }
    const current = await (await fetch(urlOf(base, 'results/current.json'))).json();
    assert(current.chain.stage2_display_release_id === 'stage2-display-e3e06d7ecafdbac9',
      'current.json does not bind the admitted display release');
    assert(current.chain.stage2_run_id === null, 'display projection was mislabeled as a production Stage-2 run');
    console.log(`GO — admitted Targets: within=${withinRows} rows, temporal=${temporalRows} rows; Pathways remains fail-closed.`);
  } finally { await browser.close(); }
}

main().catch((error) => { console.error(`NO-GO — ${error.message}`); process.exitCode = 1; });
