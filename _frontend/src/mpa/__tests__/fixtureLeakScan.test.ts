// Unit + mutation coverage for the deploy fixture-leak scanner (deploy/scan_dist_no_fixtures.mjs). The
// scanner is what the :8347 deploy runs over the built bundles to refuse any served bundle in which a
// demo/fixture identifier or value is reachable. Here we pin its token set (curated + data-driven from
// src/fixtures) and its detection/no-false-positive behaviour; the real import-graph bundle proof lives
// in deploy/test_fixture_leak_scan.sh (esbuild-bundles repository.ts → fixtures → refused).

import { describe, expect, it } from 'vitest';

// Untyped Node ESM scanner — imported at runtime; a `string`-typed specifier keeps tsc from resolving it.
async function importScanner(): Promise<{ tokensFor: (dir: string) => string[]; scanText: (text: string, tokens: string[]) => string[] }> {
  const modPath: string = '../../../deploy/scan_dist_no_fixtures.mjs';
  return import(modPath) as Promise<{ tokensFor: (dir: string) => string[]; scanText: (text: string, tokens: string[]) => string[] }>;
}

describe('deploy fixture-leak scanner', () => {
  it('token set is curated + data-driven from src/fixtures', async () => {
    const { tokensFor } = await importScanner();
    const tokens = tokensFor('src/fixtures');
    expect(tokens).toContain('GENE_A'); // curated demo gene
    expect(tokens).toContain('COMPOUND_A'); // curated demo compound
    expect(tokens).toContain('stage2FixtureRaw'); // curated fixture export
    // export names + genes MINED from the actual fixture sources (so the set tracks the fixtures)
    expect(tokens.some((t) => /Fixture/.test(t))).toBe(true);
    expect(tokens.length).toBeGreaterThanOrEqual(15);
  });

  it('catches fixture identifiers (mutation) without false-positives on legitimate firewall code', async () => {
    const { tokensFor, scanText } = await importScanner();
    const tokens = tokensFor('src/fixtures');
    // mutation: fixture identifiers in a served bundle are flagged
    expect(scanText('const a="GENE_A";const b=stage2FixtureRaw;', tokens)).toEqual(
      expect.arrayContaining(['GENE_A', 'stage2FixtureRaw']),
    );
    // NOT flagged: the legit lowercase field + the bare `fixture`/`research_only` firewall words the
    // production bundle legitimately contains (case-sensitive, specific tokens only).
    expect(scanText('gene_ranking_lane;namespace==="fixture";tone==="research_only";', tokens)).toEqual([]);
  });
});
