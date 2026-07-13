// Browser v3 selection-contract cross-check (external review S1-B2).
// Extracts the REAL page JS (canonicalContent / computeContrast / sha) from 01_page.html, runs it against
// the served stage01_selection_bundle.json, and asserts the emitted spot.stage01_selection.v3 contract
// byte-matches stage2_bridge/emit_selection_contract.build_contract (same selection_id + full-contract
// hash + execution routing). Proves the live page emits the reviewed v3 contract, not the legacy v1.
import fs from 'node:fs';
import { webcrypto } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..');
const PAGE = path.join(REPO, '01_programs', 'app', '01_page.html');
const DATA = path.join(REPO, '01_programs', 'app', 'data');
const BRIDGE = path.join(REPO, '01_programs', 'analysis', 'stage2_bridge');
const html = fs.readFileSync(PAGE, 'utf8');

function extract(sig) {
  const i = html.indexOf(sig);
  if (i < 0) throw new Error('not found: ' + sig);
  let d = 0, started = false;
  for (let j = i; j < html.length; j++) {
    const c = html[j];
    if (c === '{') { d++; started = true; }
    else if (c === '}') { d--; if (started && d === 0) return html.slice(i, j + 1); }
  }
  throw new Error('unbalanced: ' + sig);
}

const src = [
  extract('function _sha256utf8('), extract('function _sha256js('), extract('async function sha256hex('),
  extract('function canonicalJSON('), extract('function _normConds('), extract('function _poleV3('),
  extract('function _estBinding('), extract('function canonicalContent('), extract('async function computeContrast('),
].join('\n');

const BUNDLE = JSON.parse(fs.readFileSync(DATA + '/stage01_selection_bundle.json', 'utf8'));
const reg = JSON.parse(fs.readFileSync(DATA + '/stage01_program_registry_v3.json', 'utf8'));
const regByField = {};
for (const p of reg.programs) regByField[p.score_field] = { program_id: p.program_id, score_field: p.score_field, role: p.role };

const factory = new Function('BUNDLE', 'regByField', 'crypto', 'TextEncoder',
  'let axisA={},axisB={};\n' + src +
  '\nreturn {computeContrast, setAxes:(a,b)=>{axisA=a;axisB=b;}};');
const page = factory(BUNDLE, regByField, webcrypto, TextEncoder);

function pyContract(a, ad, b, bd, conds) {
  const code = `import json,sys; sys.path.insert(0,'${BRIDGE}'); import emit_selection_contract as sc;` +
    `print(json.dumps(sc.build_contract(${JSON.stringify(a)},${JSON.stringify(ad)},${JSON.stringify(b)},${JSON.stringify(bd)},${JSON.stringify(conds)})))`;
  return JSON.parse(execFileSync('python3', ['-c', code], { encoding: 'utf8' }));
}

const CASES = [
  ['within ready',   { af: 'treg_like_score', ad: 'high', ac: 'Stim48hr', bf: 'th1_like_score', bd: 'high', bc: 'Stim48hr' }, ['Stim48hr']],
  ['unavailable pole refused', { af: 'th9_like_score', ad: 'low', ac: 'Rest', bf: 'th1_like_score', bd: 'high', bc: 'Rest' }, ['Rest']],
  ['temporal ready', { af: 'treg_like_score', ad: 'high', ac: 'Stim8hr', bf: 'th1_like_score', bd: 'high', bc: 'Stim48hr' }, ['Stim8hr', 'Stim48hr']],
];

let pass = 0, fail = 0;
for (const [name, s, conds] of CASES) {
  page.setAxes({ field: s.af, direction: s.ad, condition: s.ac, donor: 'All' },
              { field: s.bf, direction: s.bd, condition: s.bc, donor: 'All' });
  const bc = await page.computeContrast();
  const browser = bc.contract;
  const py = pyContract(regByField[s.af].program_id, s.ad, regByField[s.bf].program_id, s.bd, conds);
  const checks = {
    selection_id: browser.selection_id === py.selection_id,
    full_hash: browser.full_contract_content_sha256 === py.full_contract_content_sha256,
    execution_status: browser.execution_status === py.execution_status,
    schema_v3: browser.schema_version === 'spot.stage01_selection.v3',
  };
  const ok = Object.values(checks).every(Boolean);
  ok ? pass++ : fail++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}  exec=${browser.execution_status} selid=${browser.selection_id}`);
  if (!ok) console.log('   ', JSON.stringify(checks), '\n    browser_full=', browser.full_contract_content_sha256, '\n    python_full =', py.full_contract_content_sha256);
}
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
