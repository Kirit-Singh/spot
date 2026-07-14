#!/usr/bin/env node
// GO-BP-ONLY RELEASE GATE — refuses a distribution that ships Reactome.
//
// The critical path releases exactly ONE pathway source: go_bp. Reactome is PARKED — it keeps its
// licence/history record in the REPO (DATA_LICENSES), never in the bytes a served page hands a reader.
// A live audit of :8347 found results/current.json declaring ["reactome","go_bp"] with active
// "reactome", and the built bundle advertising the Reactome V97 bundle as a live co-input of the
// Pathways method (data_input prose, coverage percentages, a source record with a CC0 URL + hashes).
//
// This is a ZERO-TOLERANCE scan, deliberately: after the GO-BP-only correction there is no legitimate
// occurrence of the token in a deployable artifact, so any hit is a regression — a stale packer spec,
// a reintroduced source record, or a fixture leak. It is not a prose linter; it refuses SHIPPING it.
//
// Usage:  node deploy/scan_dist_no_reactome.mjs <dist-dir> [results-dir ...]
// Exit 0 = clean. Exit 1 = NO-GO, with every offending file/line printed.

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const TOKEN = /reactome/i;
// Text-bearing served artifacts. Binary/asset types cannot carry a declaration.
const SCAN_EXT = new Set(['.js', '.mjs', '.json', '.html', '.css', '.csv', '.txt', '.svg', '.map']);

/**
 * The GATE, as a pure function: given { path → text } of a deployable tree, return every Reactome hit.
 * Exported so the contract test drives the REAL refusal logic the deploy runs — not a reimplementation
 * of it — without needing a filesystem or a subprocess. The CLI below is a thin fs wrapper over this.
 */
export function findReactomeHits(files) {
  const hits = [];
  for (const [path, text] of Object.entries(files)) {
    if (!TOKEN.test(text)) continue;
    for (const line of text.split('\n')) {
      const re = /reactome/gi;
      let m;
      while ((m = re.exec(line)) !== null) {
        const a = Math.max(0, m.index - 60);
        hits.push({ file: path, context: line.slice(a, m.index + 70).trim() });
        if (hits.length > 40) return hits;
      }
    }
  }
  return hits;
}

function walk(dir) {
  const out = [];
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return out; // an absent tree (e.g. an unbound deploy with no results/) is not a violation
  }
  for (const name of entries) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (SCAN_EXT.has(name.slice(name.lastIndexOf('.')))) out.push(full);
  }
  return out;
}

function main() {
  const roots = process.argv.slice(2);
  if (roots.length === 0) {
    console.error('usage: scan_dist_no_reactome.mjs <dist-dir> [results-dir ...]');
    process.exit(2);
  }

  const files = {};
  for (const root of roots) {
    for (const file of walk(root)) files[relative(process.cwd(), file)] = readFileSync(file, 'utf8');
  }
  const hits = findReactomeHits(files);

  if (hits.length > 0) {
    console.error(`NO-GO: GO-BP-only release rule violated — Reactome is present in ${hits.length} place(s) in the deployable tree.`);
    console.error('The release declares exactly one pathway source (go_bp); Reactome is parked and must not ship.\n');
    for (const h of hits) console.error(`  ${h.file}\n    …${h.context}…`);
    process.exit(1);
  }

  console.log(`OK — GO-BP-only: no Reactome in any deployable artifact (${Object.keys(files).length} text artifact(s) scanned)`);
}

if (import.meta.url === `file://${process.argv[1]}`) main();
