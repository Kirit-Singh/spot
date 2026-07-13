#!/usr/bin/env node
// FIXTURE-LEAK guard for the :8347 deploy. Inspects the BUILT served bundles (dist assets + page HTML)
// and REFUSES if any demo/fixture identifier or known fixture value is reachable in a served bundle.
// Fixtures are test-only; they must never enter the production dependency graph. This is
// import-graph aware BY CONSTRUCTION: if a served entry pulls in `repository.ts` (which imports the
// stage2/3/4 fixtures) — or any fixture module — the fixtures' distinctive string values are bundled
// and detected here. The token set is curated PLUS data-driven from src/fixtures (so it tracks whatever
// the fixtures currently contain). The mutation test deploy/test_fixture_leak_scan.sh proves detection.

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

// Curated demo/fixture identifiers that must never reach a served bundle. Deliberately SPECIFIC so they
// never collide with legitimate firewall code (which uses the bare words `fixture` / `demo` /
// `research_only` in the namespace enum + reject regex — those are allowed and NOT listed here).
const CURATED = [
  'GENE_A', 'GENE_B', 'GENE_C', 'GENE_D', 'GENE_E', 'GENE_F',
  'COMPOUND_A', 'COMPOUND_B', 'COMPOUND_C', 'COMPOUND_D',
  'GBM context',
  'stage2FixtureRaw', 'stage3FixtureRaw', 'stage4FixtureRaw', 'selectionFixtureRaw', 'fixtureProvenance',
  'fixture://', 'research_preview_v3',
];

/** Distinctive tokens mined from the fixture sources (stays current if the fixtures change). */
function fixtureTokens(fixturesDir) {
  const toks = new Set();
  let files = [];
  try { files = readdirSync(fixturesDir); } catch { return []; }
  for (const f of files) {
    if (!f.endsWith('.ts')) continue;
    const src = readFileSync(join(fixturesDir, f), 'utf8');
    for (const m of src.matchAll(/\b(GENE_[A-Z0-9]+|COMPOUND_[A-Z0-9]+)\b/g)) toks.add(m[1]);
    for (const m of src.matchAll(/export\s+(?:const|function|let)\s+([A-Za-z0-9_]*[Ff]ixture[A-Za-z0-9_]*)/g)) toks.add(m[1]);
  }
  return [...toks];
}

/** The full forbidden-token set (curated ∪ data-driven). */
export function tokensFor(fixturesDir) {
  return [...new Set([...CURATED, ...(fixturesDir ? fixtureTokens(fixturesDir) : [])])];
}

/** Case-sensitive substring scan of one text blob → the tokens it contains. */
export function scanText(text, tokens) {
  return tokens.filter((t) => text.includes(t));
}

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(js|mjs|cjs|css|html)$/.test(name)) out.push(p);
  }
  return out;
}

/** Scan every served text bundle under `dir`; returns { file: [tokens] } for any hit. */
export function scanDir(dir, tokens) {
  const hits = {};
  for (const file of walk(dir)) {
    const found = scanText(readFileSync(file, 'utf8'), tokens);
    if (found.length) hits[file] = found;
  }
  return hits;
}

// CLI: scan_dist_no_fixtures.mjs <dist_dir> [fixtures_dir]
function main() {
  const [dist, fixturesDir] = process.argv.slice(2);
  if (!dist) {
    console.error('usage: scan_dist_no_fixtures.mjs <dist_dir> [fixtures_dir]');
    process.exit(2);
  }
  const tokens = tokensFor(fixturesDir);
  const hits = scanDir(dist, tokens);
  const files = Object.keys(hits);
  if (files.length) {
    console.error('FIXTURE-LEAK: demo/fixture identifiers reachable in served bundle(s):');
    for (const f of files) console.error(`  ${f}: ${hits[f].join(', ')}`);
    process.exit(1);
  }
  console.log(`OK — ${tokens.length} demo/fixture tokens scanned; served bundles are fixture-free`);
}

if (import.meta.url === `file://${process.argv[1]}`) main();
