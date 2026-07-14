// Stage-1 insecure-context SHA-256 fallback proof (live blocker: crypto.subtle is undefined over plain
// HTTP on a non-localhost/Tailscale origin, so the Identify-genes preflight/hash path fails). This proves the
// in-page pure-JS fallback (_sha256js over _sha256utf8) is byte-identical to WebCrypto and reproduces the
// exact v3 selection_id / full_contract hashes with crypto.subtle FORCED OFF — no CDN, no dependency.
//
//   1) standard SHA-256 vectors
//   2) WebCrypto (secure-context) parity over a fuzz battery incl. canonical JSON + Unicode + block boundaries
//   3) the EXACT existing v3 selection fixtures reproduce on the fallback path (same-time + cross-time)
//   4) mutation: a one-byte change flips the digest, and a one-byte contract change breaks fixture parity
import fs from 'node:fs';
import { webcrypto } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const HERE = new URL('.', import.meta.url).pathname;                 // 01_programs/analysis/ (portable; no machine path)
const ROOT = HERE.replace(/\/01_programs\/analysis\/$/, '');
const PAGE = ROOT + '/01_programs/app/programs.html';
const DATA = ROOT + '/01_programs/app/data';
const BRIDGE = ROOT + '/01_programs/analysis/stage2_bridge';
const SELDIR = BRIDGE + '/release/selections';
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
  extract('function _estBinding('), extract('function _desiredChange('), extract('function _armRef('),
  extract('function canonicalContent('), extract('async function computeContrast('),
].join('\n');

const BUNDLE = JSON.parse(fs.readFileSync(DATA + '/stage01_selection_bundle.json', 'utf8'));
const reg = JSON.parse(fs.readFileSync(DATA + '/stage01_program_registry_v3.json', 'utf8'));
const regByField = {};
for (const p of reg.programs) regByField[p.score_field] = { program_id: p.program_id, score_field: p.score_field, role: p.role };

// two page instances: one with a REAL WebCrypto (secure context), one with crypto.subtle ABSENT (the exact
// insecure-HTTP condition — sha256hex must take the pure-JS branch).
function mkPage(cryptoObj) {
  const f = new Function('BUNDLE', 'regByField', 'crypto', 'TextEncoder',
    'let axisA={},axisB={};\n' + src +
    '\nreturn {computeContrast, sha256hex, _sha256js, _sha256utf8, setAxes:(a,b)=>{axisA=a;axisB=b;}};');
  return f(BUNDLE, regByField, cryptoObj, TextEncoder);
}
const secure = mkPage(webcrypto);                                   // crypto.subtle present
const INSECURE_CRYPTO = { getRandomValues: (a) => webcrypto.getRandomValues(a) };  // NO .subtle
const insecure = mkPage(INSECURE_CRYPTO);

function pyContract(a, ad, b, bd, conds) {
  const code = `import json,sys; sys.path.insert(0,'${BRIDGE}'); import emit_selection_contract as sc;` +
    `print(json.dumps(sc.build_contract(${JSON.stringify(a)},${JSON.stringify(ad)},${JSON.stringify(b)},${JSON.stringify(bd)},${JSON.stringify(conds)})))`;
  return JSON.parse(execFileSync('python3', ['-c', code], { encoding: 'utf8' }));
}

let pass = 0, fail = 0;
const check = (name, cond, extra) => { cond ? pass++ : fail++; console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${cond ? '' : '  ' + (extra || '')}`); };

// ---- 1) standard SHA-256 vectors (fallback only) ----
const VECTORS = {
  '': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  'abc': 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
  'abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq': '248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1',
};
for (const [s, h] of Object.entries(VECTORS))
  check(`vector[${JSON.stringify(s).slice(0, 18)}]`, insecure._sha256js(insecure._sha256utf8(s)) === h, insecure._sha256js(insecure._sha256utf8(s)));

// ---- 2) WebCrypto parity over a fuzz battery (block boundaries + canonical JSON + Unicode) ----
async function wc(s) { return [...new Uint8Array(await webcrypto.subtle.digest('SHA-256', new TextEncoder().encode(s)))].map(b => b.toString(16).padStart(2, '0')).join(''); }
let parityBad = 0;
const battery = [];
for (const n of [0, 1, 55, 56, 57, 63, 64, 65, 119, 120, 127, 128, 129, 200]) battery.push('a'.repeat(n));
battery.push('{"A":{"program_id":"treg_like"},"conditions":["Rest","Stim48hr"]}', 'µ-café—π≈∑ 日本語 🧬', JSON.stringify(BUNDLE).slice(0, 300));
for (let t = 0; t < 1200; t++) { let s = ''; const len = (t * 5 + 1) % 160; for (let i = 0; i < len; i++) { const r = (t * 97 + i * 13 + 7) % 0x2FFF; s += String.fromCharCode(r < 0xD800 ? r : r + 0x800); } battery.push(s); }
for (const s of battery) if (insecure._sha256js(insecure._sha256utf8(s)) !== await wc(s)) parityBad++;
check(`webcrypto parity (${battery.length} strings incl. boundaries/JSON/Unicode)`, parityBad === 0, `${parityBad} mismatches`);

// ---- 3) EXACT existing v3 selection fixtures reproduce on the fallback path (same-time + cross-time) ----
const CASES = [
  ['within same-time (Treg demo)', { af: 'treg_like_score', ad: 'high', ac: 'Stim48hr', bf: 'th1_like_score', bd: 'high', bc: 'Stim48hr' }, ['Stim48hr']],
  ['temporal cross-time (Treg demo)', { af: 'treg_like_score', ad: 'high', ac: 'Stim8hr', bf: 'th1_like_score', bd: 'high', bc: 'Stim48hr' }, ['Stim8hr', 'Stim48hr']],
  ['within same-time (arbitrary non-Treg)', { af: 'th2_like_score', ad: 'high', ac: 'Rest', bf: 'cd4_ctl_like_score', bd: 'low', bc: 'Rest' }, ['Rest']],
  ['temporal cross-time (arbitrary non-Treg)', { af: 'th2_like_score', ad: 'high', ac: 'Rest', bf: 'cd4_ctl_like_score', bd: 'low', bc: 'Stim48hr' }, ['Rest', 'Stim48hr']],
  ['temporal same program/pole cross-time', { af: 'th1_like_score', ad: 'high', ac: 'Stim8hr', bf: 'th1_like_score', bd: 'high', bc: 'Stim48hr' }, ['Stim8hr', 'Stim48hr']],
];
for (const [name, s, conds] of CASES) {
  secure.setAxes({ field: s.af, direction: s.ad, condition: s.ac, donor: 'All' }, { field: s.bf, direction: s.bd, condition: s.bc, donor: 'All' });
  insecure.setAxes({ field: s.af, direction: s.ad, condition: s.ac, donor: 'All' }, { field: s.bf, direction: s.bd, condition: s.bc, donor: 'All' });
  const sec = (await secure.computeContrast()).contract;
  const ins = (await insecure.computeContrast()).contract;
  const py = pyContract(regByField[s.af].program_id, s.ad, regByField[s.bf].program_id, s.bd, conds);
  const ok = ins.selection_id === sec.selection_id && ins.selection_id === py.selection_id
    && ins.full_contract_content_sha256 === sec.full_contract_content_sha256
    && ins.full_contract_content_sha256 === py.full_contract_content_sha256
    && ins.execution_status === 'ready' && ins.schema_version === 'spot.stage01_selection.v3';
  check(`fixture parity (fallback==WebCrypto==emitter): ${name}`, ok,
    `ins=${ins.full_contract_content_sha256} sec=${sec.full_contract_content_sha256} py=${py.full_contract_content_sha256}`);
}

// on-disk released fixtures reproduce from the fallback path
let fxBad = 0, fxN = 0;
for (const fn of fs.readdirSync(SELDIR).filter(f => f.endsWith('.v3.json'))) {
  const on = JSON.parse(fs.readFileSync(SELDIR + '/' + fn, 'utf8'));
  const A = on.canonical_content.A, B = on.canonical_content.B, conds = on.canonical_content.conditions;
  insecure.setAxes({ field: A.score_field, direction: A.direction, condition: conds[0], donor: 'All' },
                   { field: B.score_field, direction: B.direction, condition: conds[conds.length - 1], donor: 'All' });
  const ins = (await insecure.computeContrast()).contract;
  fxN++;
  if (ins.selection_id !== on.selection_id || ins.full_contract_content_sha256 !== on.full_contract_content_sha256) { fxBad++; if (fxBad <= 3) console.log('   on-disk mismatch', fn); }
}
check(`on-disk released selection fixtures reproduce on fallback (${fxN} files)`, fxBad === 0, `${fxBad} mismatches`);

// ---- 4) mutation: one-byte change flips the digest + breaks fixture parity (fail-closed) ----
const base = '{"A":{"program_id":"treg_like","direction":"high"}}';
const mut = base.replace('treg_like', 'treg_likf');   // one-byte change
check('mutation: one-byte input change flips the fallback digest',
  insecure._sha256js(insecure._sha256utf8(base)) !== insecure._sha256js(insecure._sha256utf8(mut)));
check('mutation: fallback digest of the mutant also matches WebCrypto (still a real SHA-256)',
  insecure._sha256js(insecure._sha256utf8(mut)) === await wc(mut));
// a one-byte change to the canonical content must change selection_id (both paths agree it changed)
secure.setAxes({ field: 'treg_like_score', direction: 'high', condition: 'Stim48hr', donor: 'All' }, { field: 'th1_like_score', direction: 'high', condition: 'Stim48hr', donor: 'All' });
const c1 = (await secure.computeContrast()).contract;
secure.setAxes({ field: 'treg_like_score', direction: 'high', condition: 'Stim8hr', donor: 'All' }, { field: 'th1_like_score', direction: 'high', condition: 'Stim48hr', donor: 'All' });
const c2 = (await secure.computeContrast()).contract;
check('mutation: changing one condition changes selection_id + full_contract', c1.selection_id !== c2.selection_id && c1.full_contract_content_sha256 !== c2.full_contract_content_sha256);

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
