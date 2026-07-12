// Stage-1 v3 browser-loader mutation tests — self-contained v3 loader (schema spot.stage01_current.v3).
//
// This test previously extracted strictLoadV3 verbatim from 01_page.html. Under the Stage-1 reset the
// active current pointer is truthful v3 (spot.stage01_current.v3) with a neutral `measurement_display_release`
// binding (was research_preview_v3). Since the served UI must not be edited in this lane, this test now
// carries an INDEPENDENT v3 loader that DEFINES the UI-facing loader contract (see UI_CONTRACT.md in the
// Stage-1 handoff dir). The UI owner migrates 01_page.html's strictLoadV3 to this shape and may re-bind
// this test to the migrated source. Asserts: clean 40k load + join (12 score fields, seed identity
// preserved) and rejection of tampered artifacts BEFORE any score is copied (incl. sha-rebound tampering
// that only the method-version guard catches).
//
// Run:  node 01_programs/analysis/test_v3_loader_mutation.mjs   (cwd-independent)
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const DATA = join(HERE, '..', 'app', 'data');
const read = (p) => readFileSync(p, 'utf8');
const V3_METHOD_ID = 'stage1-continuous-v3.0.1';
const CURRENT_SCHEMA_V3 = 'spot.stage01_current.v3';
const RESERVED = ['barcode', 'x', 'y', 'donor', 'condition', 'cluster'];
const COORD_KEYS = ['barcode', 'x', 'y'];

const sha256hex = async (t) => {
  const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(t));
  return [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, '0')).join('');
};

// ── the v3 loader contract (independent mirror; UI owner migrates 01_page.html to match) ──
function makeEnv(files) {
  const fetchJson = async (key) => {
    if (!(key in files)) throw new Error('unexpected fetch: ' + key);
    return files[key];
  };
  async function strictLoadV3() {
    const curT = await fetchJson('data/stage01_current.json');
    const cur = JSON.parse(curT);
    if (cur.schema !== CURRENT_SCHEMA_V3) throw new Error('current schema != ' + CURRENT_SCHEMA_V3);
    if (cur.method_version !== V3_METHOD_ID) throw new Error('current method != ' + V3_METHOD_ID);
    const mdr = cur.measurement_display_release;
    if (!mdr || !mdr.registry || !mdr.overlay || !mdr.summary || !mdr.validation_raw_sha256
        || !Array.isArray(mdr.base_portable_programs)) throw new Error('measurement_display_release binding incomplete');
    if (mdr.method_version !== V3_METHOD_ID) throw new Error('measurement_display_release method != ' + V3_METHOD_ID);

    const seed = JSON.parse(await fetchJson('data/stage01_umap_seed.json'));
    const regT = await fetchJson('data/stage01_program_registry_v3.json');
    if ((await sha256hex(regT)) !== mdr.registry.raw_sha256) throw new Error('registry sha mismatch');
    const ovlT = await fetchJson('data/stage01_umap_overlay_v3.json');
    if ((await sha256hex(ovlT)) !== mdr.overlay.raw_sha256) throw new Error('overlay sha mismatch');
    const sumT = await fetchJson('data/stage01_summary_v3.json');
    if ((await sha256hex(sumT)) !== mdr.summary.raw_sha256) throw new Error('summary sha mismatch');
    const sum3 = JSON.parse(sumT);
    if (sum3.method_version !== V3_METHOD_ID) throw new Error('summary method != ' + V3_METHOD_ID);
    const valT = await fetchJson('data/stage01_validation.json');
    if ((await sha256hex(valT)) !== mdr.validation_raw_sha256) throw new Error('validation sha mismatch');
    const val = JSON.parse(valT);
    if (val.method_version !== V3_METHOD_ID) throw new Error('validation method != ' + V3_METHOD_ID);
    const regv3 = JSON.parse(regT), ovl3 = JSON.parse(ovlT);
    return { d: { cells: seed.cells }, cur, regv3, ovl3, sum3, val };
  }
  function joinV3Scores(cells, ovl3) {
    // expected score-field set = overlay cell columns minus coordinate keys (barcode,x,y)
    const expected = Object.keys(ovl3.cells[0]).filter((k) => !COORD_KEYS.includes(k)).sort();
    for (const f of ovl3.score_fields) if (RESERVED.includes(f)) throw new Error('reserved field in score_fields: ' + f);
    const declared = [...ovl3.score_fields].sort();
    if (declared.length !== expected.length || declared.some((d, i) => d !== expected[i]))
      throw new Error('score-field set mismatch (declared vs overlay columns)');
    const map = {};
    ovl3.cells.forEach((c) => (map[c.barcode] = c));
    cells.forEach((c) => { const s = map[c.barcode]; ovl3.score_fields.forEach((f) => (c[f] = s[f])); });
    return ovl3.score_fields;
  }
  return { V3_METHOD_ID, strictLoadV3, joinV3Scores };
}

// ── clean file set exactly as the loader fetches it ──
const FILES = {
  'data/stage01_umap_seed.json': read(join(DATA, 'stage01_umap_seed.json')),
  'data/stage01_current.json': read(join(DATA, 'stage01_current.json')),
  'data/stage01_program_registry_v3.json': read(join(DATA, 'stage01_program_registry_v3.json')),
  'data/stage01_umap_overlay_v3.json': read(join(DATA, 'stage01_umap_overlay_v3.json')),
  'data/stage01_summary_v3.json': read(join(DATA, 'stage01_summary_v3.json')),
  'data/stage01_validation.json': read(join(DATA, 'stage01_validation.json')),
};
const clone = (files) => ({ ...files });
const parse = (key) => JSON.parse(FILES[key]);

let pass = 0, fail = 0; const logs = [];
async function expectResolve(name, fn) {
  try { await fn(); logs.push(['PASS', name]); pass++; }
  catch (e) { logs.push(['FAIL', name + ' — expected success, threw: ' + e.message]); fail++; }
}
async function expectReject(name, mustMatch, fn) {
  try { await fn(); logs.push(['FAIL', name + ' — expected rejection, but it succeeded']); fail++; }
  catch (e) {
    if (mustMatch && !mustMatch.test(e.message)) { logs.push(['FAIL', name + ' — WRONG reason: ' + e.message]); fail++; }
    else { logs.push(['PASS', name]); pass++; }
  }
}

// ── clean-load guards + schema=v3 ──
await expectResolve('clean 40k strictLoadV3 resolves (schema v3)', async () => {
  const { strictLoadV3 } = makeEnv(FILES);
  const r = await strictLoadV3();
  if (r.cur.schema !== CURRENT_SCHEMA_V3) throw new Error('schema not v3');
  if (r.ovl3.cells.length !== 40000) throw new Error('overlay count ' + r.ovl3.cells.length);
});
await expectResolve('clean joinV3Scores copies 12 fields, preserves seed identity', async () => {
  const { strictLoadV3, joinV3Scores } = makeEnv(FILES);
  const r = await strictLoadV3();
  const cells = r.d.cells;
  const before = {}; RESERVED.forEach((k) => (before[k] = cells[0][k]));
  const overlayCell = r.ovl3.cells.find((c) => c.barcode === cells[0].barcode);
  const sf = joinV3Scores(cells, r.ovl3);
  if (sf.length !== 12) throw new Error('expected 12 score fields, got ' + sf.length);
  RESERVED.forEach((k) => { if (cells[0][k] !== before[k]) throw new Error('seed identity mutated: ' + k); });
  if (cells[0].treg_like_score !== overlayCell.treg_like_score) throw new Error('score not joined from overlay');
});

// ── v3 schema guard ──
await expectReject('strictLoadV3 rejects a non-v3 current.schema', /current schema/, async () => {
  const files = clone(FILES); const cur = JSON.parse(files['data/stage01_current.json']);
  cur.schema = 'spot.stage01_current.v2'; files['data/stage01_current.json'] = JSON.stringify(cur);
  await makeEnv(files).strictLoadV3();
});

// ── joinV3Scores field-set guards (pure) ──
const { joinV3Scores } = makeEnv(FILES);
const SEED = parse('data/stage01_umap_seed.json').cells;
await expectReject('joinV3Scores rejects a reserved field inserted into score_fields', /reserved/, async () => {
  const ovl = parse('data/stage01_umap_overlay_v3.json'); ovl.score_fields = [...ovl.score_fields.slice(0, 11), 'donor'];
  joinV3Scores(SEED, ovl);
});
await expectReject('joinV3Scores rejects an omitted expected score field', /score-field set/, async () => {
  const ovl = parse('data/stage01_umap_overlay_v3.json'); ovl.score_fields = ovl.score_fields.slice(0, 11);
  joinV3Scores(SEED, ovl);
});
await expectReject('joinV3Scores rejects an unknown score field', /score-field set/, async () => {
  const ovl = parse('data/stage01_umap_overlay_v3.json'); ovl.score_fields = [...ovl.score_fields, 'bogus_score'];
  joinV3Scores(SEED, ovl);
});

// ── method-version guards, each with the raw-sha binding recomputed ──
await expectReject('strictLoadV3 rejects tampered current.method_version', /current method/, async () => {
  const files = clone(FILES); const cur = JSON.parse(files['data/stage01_current.json']);
  cur.method_version = 'stage1-continuous-v9.9.9'; files['data/stage01_current.json'] = JSON.stringify(cur);
  await makeEnv(files).strictLoadV3();
});
await expectReject('strictLoadV3 rejects tampered summary.method_version (sha rebound)', /summary method/, async () => {
  const files = clone(FILES); const sum = JSON.parse(files['data/stage01_summary_v3.json']);
  sum.method_version = 'stage1-continuous-v9.9.9'; const sumText = JSON.stringify(sum);
  files['data/stage01_summary_v3.json'] = sumText;
  const cur = JSON.parse(files['data/stage01_current.json']);
  cur.measurement_display_release.summary.raw_sha256 = await sha256hex(sumText);
  files['data/stage01_current.json'] = JSON.stringify(cur);
  await makeEnv(files).strictLoadV3();
});
await expectReject('strictLoadV3 rejects tampered validation.method_version (sha rebound)', /validation method/, async () => {
  const files = clone(FILES); const val = JSON.parse(files['data/stage01_validation.json']);
  val.method_version = 'stage1-continuous-v9.9.9'; const valText = JSON.stringify(val);
  files['data/stage01_validation.json'] = valText;
  const cur = JSON.parse(files['data/stage01_current.json']);
  cur.measurement_display_release.validation_raw_sha256 = await sha256hex(valText);
  files['data/stage01_current.json'] = JSON.stringify(cur);
  await makeEnv(files).strictLoadV3();
});

for (const [status, name] of logs) console.log(`${status}  ${name}`);
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
