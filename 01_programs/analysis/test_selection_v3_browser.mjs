// Browser v3 selection-contract cross-check (external review S1-B2).
// Extracts the REAL page JS (canonicalContent / computeContrast / sha) from programs.html, runs it against
// the served stage01_selection_bundle.json, and asserts the emitted spot.stage01_selection.v3 contract
// byte-matches stage2_bridge/emit_selection_contract.build_contract (same selection_id + full-contract
// hash + execution routing). Proves the live page emits the reviewed v3 contract, not the legacy v1.
import fs from 'node:fs';
import { webcrypto } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const REPO = new URL('.', import.meta.url).pathname.replace(/\/01_programs\/analysis\/$/, '');  // portable; no machine path
const PAGE = REPO + '/01_programs/app/programs.html';
const DATA = REPO + '/01_programs/app/data';
const BRIDGE = REPO + '/01_programs/analysis/stage2_bridge';
// Hard guard: page + emitter MUST be this test's OWN git worktree, never a hardcoded primary checkout — else
// the test silently reads a stale tree and browser/Python agree only because BOTH are the wrong (old) files.
const GIT_TOP = fs.realpathSync(execFileSync('git', ['-C', REPO, 'rev-parse', '--show-toplevel'], { encoding: 'utf8' }).trim());
if (fs.realpathSync(REPO) !== GIT_TOP) throw new Error(`test must run against its own worktree: REPO=${REPO} git_top=${GIT_TOP}`);
if (!fs.existsSync(PAGE)) throw new Error(`resolved PAGE not found under the current worktree: ${PAGE}`);
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
  // generic selector: an ARBITRARY non-Treg pair, within-condition and different-timepoint temporal
  ['within ready (non-Treg pair)', { af: 'th2_like_score', ad: 'high', ac: 'Rest', bf: 'cd4_ctl_like_score', bd: 'low', bc: 'Rest' }, ['Rest']],
  ['temporal ready (non-Treg, different timepoints)', { af: 'th2_like_score', ad: 'high', ac: 'Rest', bf: 'cd4_ctl_like_score', bd: 'low', bc: 'Stim48hr' }, ['Rest', 'Stim48hr']],
  // frozen topology: SAME program + SAME pole at DIFFERENT timepoints — valid (away=decrease vs toward=increase)
  ['temporal ready (same program/pole, cross-time)', { af: 'th1_like_score', ad: 'high', ac: 'Stim8hr', bf: 'th1_like_score', bd: 'high', bc: 'Stim48hr' }, ['Stim8hr', 'Stim48hr']],
];

// frozen (role, pole) -> desired_change (ROUND4_ADDENDUM c4773562) — the browser arms must key on this, not the pole
const DESIRED = { 'away_from_A|high': 'decrease', 'away_from_A|low': 'increase', 'toward_B|high': 'increase', 'toward_B|low': 'decrease' };

let pass = 0, fail = 0;
for (const [name, s, conds] of CASES) {
  page.setAxes({ field: s.af, direction: s.ad, condition: s.ac, donor: 'All' },
              { field: s.bf, direction: s.bd, condition: s.bc, donor: 'All' });
  const bc = await page.computeContrast();
  const browser = bc.contract;
  const py = pyContract(regByField[s.af].program_id, s.ad, regByField[s.bf].program_id, s.bd, conds);
  const checks = {
    selection_id: browser.selection_id === py.selection_id,
    question_id: browser.question_id === py.question_id && /^[0-9a-f]{16}$/.test(browser.question_id)
                 && browser.question_id !== browser.selection_id,   // biology-only id, browser==emitter, distinct
    full_hash: browser.full_contract_content_sha256 === py.full_contract_content_sha256,   // byte-equal incl. arms + question_id
    execution_status: browser.execution_status === py.execution_status,
    schema_v3: browser.schema_version === 'spot.stage01_selection.v3',
    // pair expressed as two independent per-program arm references (away_from_A on A, toward_B on B)
    arms: browser.arms && browser.arms.away_from_A.program_id === browser.canonical_content.A.program_id
          && browser.arms.toward_B.program_id === browser.canonical_content.B.program_id
          && browser.arms.away_from_A.role === 'away_from_A' && browser.arms.toward_B.role === 'toward_B',
    // reusable arms key on desired_change (frozen mapping), NOT pole high|low; pole kept as metadata
    desired_change: browser.arms.away_from_A.desired_change === DESIRED['away_from_A|' + browser.arms.away_from_A.pole_direction]
          && browser.arms.toward_B.desired_change === DESIRED['toward_B|' + browser.arms.toward_B.pole_direction]
          && browser.arms.away_from_A.direct_arm_key === 'direct|' + browser.arms.away_from_A.program_id + '|' + browser.arms.away_from_A.desired_change + '|' + browser.arms.away_from_A.condition,
  };
  const ok = Object.values(checks).every(Boolean);
  ok ? pass++ : fail++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}  exec=${browser.execution_status} selid=${browser.selection_id}`);
  if (!ok) console.log('   ', JSON.stringify(checks), '\n    browser_full=', browser.full_contract_content_sha256, '\n    python_full =', py.full_contract_content_sha256);
}
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
