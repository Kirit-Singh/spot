// CONTRACT: the DEPLOY refuses a Reactome-bearing distribution — not merely "a scanner exists".
//
// A standalone scanner nobody calls is not a gate. These tests pin two halves together:
//   1. the gate LOGIC — the REAL findReactomeHits() the deploy runs (imported, not reimplemented) —
//      refuses each way Reactome can re-enter a deployable tree: a current.json that DECLARES it, and
//      a built bundle that ADVERTISES it as a live co-input; and
//   2. deploy_8347.sh actually INVOKES that gate, over the dist AND the results tree, with a hard die.
//
// (2) is the durability half: without it, a future deploy silently reships the state the live audit of
// :8347 found — current.json declaring ["reactome","go_bp"], active "reactome".

import { describe, expect, it } from 'vitest';
import deploySh from '../../../deploy/deploy_8347.sh?raw';

interface Hit {
  file: string;
  context: string;
}
interface Scanner {
  findReactomeHits(files: Record<string, string>): Hit[];
}

async function gate(): Promise<Scanner> {
  const modPath: string = '../../../deploy/scan_dist_no_reactome.mjs';
  return import(modPath) as Promise<Scanner>;
}

/** A results/current.json shaped like the real one, parameterised by its declared pathway topology. */
function currentJson(sources: string[], active: string): string {
  return JSON.stringify(
    {
      schema: 'spot.ui_results_current.v1',
      routes: {
        targets: {
          compact_stage2: {
            schema_version: 'spot.ui_compact_stage2_release.v1',
            release_conditions: ['Rest', 'Stim8hr', 'Stim48hr'],
            pathway_sources: sources,
            active_pathway_source: active,
          },
        },
      },
    },
    null,
    2,
  );
}

describe('GO-BP-only deploy gate — refuses every way Reactome re-enters a release', () => {
  it('PASSES a GO-BP-only dist + results tree', async () => {
    const { findReactomeHits } = await gate();
    expect(
      findReactomeHits({
        'dist/assets/app.js': 'const src=["go_bp"];const active="go_bp";',
        'results/current.json': currentJson(['go_bp'], 'go_bp'),
      }),
    ).toEqual([]);
  });

  it('REFUSES the exact live-audit finding: current.json declaring ["reactome","go_bp"] / active "reactome"', async () => {
    const { findReactomeHits } = await gate();
    const hits = findReactomeHits({ 'results/current.json': currentJson(['reactome', 'go_bp'], 'reactome') });
    expect(hits.length).toBeGreaterThan(0);
    expect(hits.every((h) => h.file === 'results/current.json')).toBe(true);
  });

  it('REFUSES a built bundle that ADVERTISES Reactome as a live co-input (prose, coverage, CC0 URL)', async () => {
    const { findReactomeHits } = await gate();
    const bundle =
      'const m={data_input:`gene-set bundles: Reactome V97 (2,868 sets) and GO-BP`,' +
      'limitations:[`Reactome loses 39.6069% of member slots`],' +
      'url:`https://reactome.org/download/97/ReactomePathways.gmt.zip`};';
    expect(findReactomeHits({ 'dist/assets/app.js': bundle }).length).toBeGreaterThan(0);
  });

  it('REFUSES a lone mention anywhere in a deployable artifact (zero tolerance, any served text type)', async () => {
    const { findReactomeHits } = await gate();
    const trees: Record<string, string>[] = [
      { 'dist/assets/app.js': 'const x=`reactome`;' },
      { 'dist/targets.html': '<!-- Reactome -->' },
      { 'results/manifests/targets.ui_release.json': '{"note":"REACTOME"}' },
    ];
    for (const files of trees) {
      expect(findReactomeHits(files).length).toBeGreaterThan(0);
    }
  });

  it('an EMPTY tree is not a violation (a clean UNBOUND deploy still passes)', async () => {
    const { findReactomeHits } = await gate();
    expect(findReactomeHits({})).toEqual([]);
  });
});

describe('the gate is WIRED INTO the deploy (a scanner beside the path is not a gate)', () => {
  it('deploy_8347.sh invokes scan_dist_no_reactome.mjs', () => {
    expect(deploySh).toMatch(/node "\$SCRIPT_DIR\/scan_dist_no_reactome\.mjs"/);
  });

  it('it scans the dist AND the results tree when one is bound', () => {
    expect(deploySh).toMatch(/GOBP_SCAN=\("\$DIST_DIR"\)/);
    expect(deploySh).toMatch(/GOBP_SCAN\+=\("\$RESULTS_SRC"\)/);
  });

  it('a violation is a HARD NO-GO (die), never a warning the deploy walks past', () => {
    const call = deploySh.slice(deploySh.indexOf('node "$SCRIPT_DIR/scan_dist_no_reactome.mjs"'));
    expect(call.slice(0, call.indexOf('\nsay '))).toMatch(/\|\|\s*die /);
  });

  it('it runs inside the pre-copy hygiene gate — after the fixture scan, BEFORE anything is staged', () => {
    const fixtures = deploySh.indexOf('scan_dist_no_fixtures.mjs');
    const reactome = deploySh.indexOf('scan_dist_no_reactome.mjs');
    const copySet = deploySh.indexOf('[6/10] resolving copy set');
    expect(deploySh).toContain('[5/10] provenance-hygiene scan');
    expect(reactome).toBeGreaterThan(fixtures);
    expect(reactome).toBeLessThan(copySet);
  });
});
