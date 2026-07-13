// Data-contract tests for the three Stage-2 real-run adapters. They pin the AUTHORITATIVE
// shapes (flat screen/temporal rows; pathway records[].enrichment.{away_from_A,toward_b}),
// prove allowlist-and-project (machine/batch/combined columns exist in the verified artifact
// but are dropped, never rendered, never a reason to reject), and check a non-Treg pair and a
// different-timepoint pair. `ontarget_significant` is the only eligibility signal carried.

import { describe, expect, it } from 'vitest';
import { AdapterError } from '../errors';
import { parseDirectScreen, parseTemporalDiD, parsePathwayConvergence } from '../stage2RealRunAdapter';
import {
  directScreenFixtureRaw,
  temporalDiDFixtureRaw,
  pathwayConvergenceFixtureRaw,
} from '../../fixtures/stage2RealRun.fixture';

const clone = <T,>(v: T): T => structuredClone(v);

/** Deep set of every object key in the normalized output — used to prove projection. */
function allKeys(v: unknown, acc = new Set<string>()): Set<string> {
  if (Array.isArray(v)) v.forEach((x) => allKeys(x, acc));
  else if (v && typeof v === 'object') {
    for (const k of Object.keys(v)) {
      acc.add(k);
      allKeys((v as Record<string, unknown>)[k], acc);
    }
  }
  return acc;
}

// keys that must NEVER appear in a normalized (UI-facing) artifact
const MACHINE_KEYS = [
  'balanced_skew',
  'balanced_skew_zscore',
  'delta_A',
  'delta_B',
  'away_from_A_zscore',
  'toward_b_zscore',
  'support_state',
  'mask_resolved',
  'batch_partially_confounded',
  'batch_reliability_metric',
  'interaction_std_program',
  'combined_temporal_score',
  'combined_score',
  // NB: `method` is intentionally absent — it is a legitimate provenance.method key. The
  // record-level `source_hash` below still proves per-record machine fields are dropped.
  'source_hash',
];

function expectNoMachineKeys(normalized: unknown) {
  const keys = allKeys(normalized);
  for (const k of MACHINE_KEYS) expect(keys.has(k)).toBe(false);
}

// ───────────────────────────── Direct screen ─────────────────────────────
describe('parseDirectScreen — flat screen.parquet rows, allowlist-and-project', () => {
  it('reads the two independent arm effects straight from the flat columns', () => {
    const a = parseDirectScreen(directScreenFixtureRaw, 'fixture');
    expect(a.condition).toBe('Rest');
    expect(a.rows).toHaveLength(3);
    expect(a.rows[0].away_from_A).toBe(-0.52);
    expect(a.rows[0].toward_b).toBe(0.31);
    expect(a.rows[0].rank).toBe(1);
    expect(a.rows[0].target_ensembl).toBe('ENSG00000000001');
  });

  it('binds a NON-Treg pair (proves arbitrary programs, not a hardcoded Treg contrast)', () => {
    const a = parseDirectScreen(directScreenFixtureRaw, 'fixture');
    expect(a.selection.program_a.display_label).toBe('Th17-like');
    expect(a.selection.program_b.display_label).toBe('Th1-like');
    expect(a.selection.program_a.program_id).not.toMatch(/treg/i);
  });

  it('carries only the upstream ontarget_significant eligibility (never a spot p/q)', () => {
    const a = parseDirectScreen(directScreenFixtureRaw, 'fixture');
    expect(a.rows[0].ontarget_significant).toBe(true);
    expect(a.rows[2].ontarget_significant).toBe(false);
    expect(a.rows[2].eligibility_state).toBe('ineligible_ontarget_not_significant');
  });

  it('keeps a not-evaluated arm null (never coerced to zero)', () => {
    const a = parseDirectScreen(directScreenFixtureRaw, 'fixture');
    expect(a.rows[1].toward_b).toBeNull();
    expect(a.rows[2].away_from_A).toBeNull();
  });

  it('does NOT reject the verified artifact for its machine columns, and never surfaces them', () => {
    // the fixture rows carry delta_*, *_zscore, balanced_skew, support_*, mask_* — all present
    expect(() => parseDirectScreen(directScreenFixtureRaw, 'fixture')).not.toThrow();
    expectNoMachineKeys(parseDirectScreen(directScreenFixtureRaw, 'fixture'));
  });

  it('enforces the namespace firewall (wrong expected namespace → mismatch)', () => {
    try {
      parseDirectScreen(clone(directScreenFixtureRaw), 'production');
      throw new Error('expected rejection');
    } catch (e) {
      expect(e).toBeInstanceOf(AdapterError);
      expect((e as AdapterError).code).toBe('namespace_mismatch');
    }
  });
});

// ───────────────────────────── Temporal DiD ─────────────────────────────
describe('parseTemporalDiD — flat temporal.parquet rows, batch projected away', () => {
  it('parses a DIFFERENT-timepoint pair (Rest → Stim48hr) with per-arm DiD + both endpoints', () => {
    const t = parseTemporalDiD(temporalDiDFixtureRaw, 'fixture');
    expect(t.from_condition).toBe('Rest');
    expect(t.to_condition).toBe('Stim48hr');
    expect(t.analysis_mode).toBe('temporal_cross_condition');
    expect(t.rows[0].away_from_A_did).toBe(-0.12);
    expect(t.rows[0].toward_b_did).toBe(0.05);
    expect(t.rows[0].away_from_A_from).toBe(-0.52);
    expect(t.rows[0].away_from_A_to).toBe(-0.64);
  });

  it('emits a union row with the missing endpoint marked absent (never zero)', () => {
    const t = parseTemporalDiD(temporalDiDFixtureRaw, 'fixture');
    const d = t.rows.find((r) => r.target_ensembl === 'ENSG00000000004')!;
    expect(d.present_to).toBe(false);
    expect(d.away_from_A_to).toBeNull();
    expect(d.away_from_A_did).toBeNull();
  });

  it('does NOT reject for the methods-only batch_partially_confounded field, and never surfaces it', () => {
    // fixture carries batch_partially_confounded + reliability + a stray combined_temporal_score
    expect(() => parseTemporalDiD(temporalDiDFixtureRaw, 'fixture')).not.toThrow();
    expectNoMachineKeys(parseTemporalDiD(temporalDiDFixtureRaw, 'fixture'));
  });
});

// ─────────────────────── Pathway convergence (per-arm enrichment) ───────────────────────
describe('parsePathwayConvergence — records[].enrichment.{away_from_A,toward_b}', () => {
  it('reads per-arm enrichment from the real enrichment-by-arm shape', () => {
    const p = parsePathwayConvergence(pathwayConvergenceFixtureRaw, 'fixture');
    expect(p.condition).toBe('Rest');
    expect(p.gene_set_source).toBe('reactome');
    expect(p.records).toHaveLength(2);
    const r1 = p.records[0];
    expect(r1.enrichment.away_from_A.enrichment_value).toBe(2.1);
    expect(r1.enrichment.toward_b.enrichment_value).toBe(1.4);
  });

  it('carries a SEPARATE per-arm headline-rankable flag + disposition (UI can split headline vs descriptive)', () => {
    const r1 = parsePathwayConvergence(pathwayConvergenceFixtureRaw, 'fixture').records[0];
    expect(r1.enrichment.away_from_A.arm_headline_rankable).toBe(true);
    expect(r1.enrichment.away_from_A.arm_coverage_disposition).toBe('rankable');
    expect(r1.enrichment.toward_b.arm_headline_rankable).toBe(false);
    expect(r1.enrichment.toward_b.arm_coverage_disposition).toBe('descriptive_only_thin_arm');
  });

  it('keeps low-coverage / undefined arms non-headline with a null enrichment', () => {
    const r2 = parsePathwayConvergence(pathwayConvergenceFixtureRaw, 'fixture').records[1];
    expect(r2.enrichment.away_from_A.arm_coverage_disposition).toBe('descriptive_only_low_source_coverage');
    expect(r2.enrichment.away_from_A.arm_headline_rankable).toBe(false);
    expect(r2.enrichment.toward_b.arm_coverage_disposition).toBe('undefined');
    expect(r2.enrichment.toward_b.enrichment_value).toBeNull();
  });

  it('does NOT surface record-level machine fields (method / source_hash)', () => {
    expectNoMachineKeys(parsePathwayConvergence(pathwayConvergenceFixtureRaw, 'fixture'));
  });
});
