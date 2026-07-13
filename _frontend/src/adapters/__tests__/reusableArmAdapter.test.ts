// Data-contract tests for the Round-4 REUSABLE-ARM bundle adapters (ROUND4_ADDENDUM.md,
// Rule 2). A bundle is a per-(lane, context) all-arm artifact carrying every
// program × desired_change arm, each addressed by its canonical armKey.ts key. These tests
// prove: NON-Treg per-program arms resolve by key; a mismatched arm_key is rejected; a legacy
// PRE-JOINED pair-shaped arm (away_from_A / joint_status) is rejected; temporal + pathway
// contexts resolve their arms; and the namespace firewall + convergence reference hold.
// Allowlist-and-project: machine columns present in a verified bundle are dropped, never a
// reason to reject, never surfaced. No combined/balanced score is read.

import { describe, expect, it } from 'vitest';
import { AdapterError } from '../errors';
import {
  getDirectArm,
  getPathwayArm,
  getTemporalArm,
  parseDirectArmBundle,
  parsePathwayArmBundle,
  parseTemporalArmBundle,
} from '../reusableArmAdapter';
import {
  convergenceKey,
  directArmKey,
  pathwayArmKey,
  temporalArmKey,
} from '../../repository/armKey';
import { fixtureProvenance, h64 } from '../../fixtures/synthetic';

const clone = <T,>(v: T): T => structuredClone(v);

/** Deep set of every object key in a normalized output — used to prove projection. */
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

// machine / pair fields that appear in the raw bundles but must NEVER surface in the output
const MACHINE_KEYS = ['balanced_skew', 'delta_A', 'machine_batch_id', 'source_hash', 'away_from_A', 'toward_b'];
function expectNoMachineKeys(normalized: unknown) {
  const keys = allKeys(normalized);
  for (const k of MACHINE_KEYS) expect(keys.has(k)).toBe(false);
}

function bundleProv(slug: string, seed: string, schemaVersion: string) {
  return {
    ...fixtureProvenance({
      stage: 'stage02',
      slug,
      seed,
      methodId: 'reusable_arm_bundle.fixture',
      sources: [{ label: 'Reactome', record_id: 'R-FIX-0000', url: null, detail: 'Synthetic (fixture)' }],
      upstream: { stage: 'stage01', slug: 'demo_selection', seed: 'a1b1c1d1' },
    }),
    schema_version: schemaVersion,
  };
}

// ── A NON-Treg program (th17_like) — proves arbitrary per-program arms, not a hardcoded pair ──
const PROGRAM = 'th17_like';

// ───────────────────────────── Direct bundle (Rest) ─────────────────────────────

/** One flat direct-arm row carrying machine columns the adapter must project away. */
function directRow(over: Record<string, unknown>) {
  return {
    // machine columns — present in the verified bundle, must be dropped:
    balanced_skew: 0.9,
    delta_A: -0.61,
    machine_batch_id: 'batch-7',
    ...over,
  };
}

const directBundleRaw = {
  provenance: bundleProv('demo_direct_arm_bundle', 'e1e1e1e1', 'spot.stage02_direct_arm_bundle.v1'),
  bundle_sha256: h64('bd1'),
  condition: 'Rest',
  arms: {
    [directArmKey(PROGRAM, 'increase', 'Rest')]: {
      arm_key: directArmKey(PROGRAM, 'increase', 'Rest'),
      program_id: PROGRAM,
      desired_change: 'increase',
      rows: [
        directRow({ target_ensembl: 'ENSG00000000001', target_symbol: 'GENE_A', effect: 0.42, rank: 1, ontarget_significant: true }),
        directRow({ target_ensembl: 'ENSG00000000002', target_symbol: 'GENE_B', effect: null, rank: null, ontarget_significant: false }),
      ],
    },
    [directArmKey(PROGRAM, 'decrease', 'Rest')]: {
      arm_key: directArmKey(PROGRAM, 'decrease', 'Rest'),
      program_id: PROGRAM,
      desired_change: 'decrease',
      rows: [
        directRow({ target_ensembl: 'ENSG00000000001', target_symbol: 'GENE_A', effect: -0.42, rank: 1, ontarget_significant: true }),
      ],
    },
  },
};

describe('parseDirectArmBundle — per-program all-arm bundle for one condition', () => {
  it('carries a NON-Treg program with BOTH increase & decrease arms, resolvable by key', () => {
    const b = parseDirectArmBundle(directBundleRaw, 'fixture');
    expect(b.lane).toBe('direct');
    expect(b.condition).toBe('Rest');
    expect(Object.keys(b.arms)).toHaveLength(2);

    const inc = getDirectArm(b, PROGRAM, 'increase');
    const dec = getDirectArm(b, PROGRAM, 'decrease');
    expect(inc).not.toBeNull();
    expect(dec).not.toBeNull();
    expect(inc!.arm_key).toBe('direct|th17_like|increase|Rest');
    expect(inc!.program_id).not.toMatch(/treg/i);
    expect(inc!.desired_change).toBe('increase');
    expect(inc!.condition).toBe('Rest');
    // increase / decrease are exact sign transforms — two logical arms, independently addressed
    expect(inc!.rows[0].effect).toBe(0.42);
    expect(dec!.rows[0].effect).toBe(-0.42);
  });

  it('keeps a not-evaluated arm effect null (never coerced to zero) + carries ontarget_significant only', () => {
    const b = parseDirectArmBundle(directBundleRaw, 'fixture');
    const inc = getDirectArm(b, PROGRAM, 'increase')!;
    expect(inc.rows[1].effect).toBeNull();
    expect(inc.rows[1].rank).toBeNull();
    expect(inc.rows[1].ontarget_significant).toBe(false);
  });

  it('returns null for an arm not present in the bundle', () => {
    const b = parseDirectArmBundle(directBundleRaw, 'fixture');
    expect(getDirectArm(b, 'some_other_program', 'increase')).toBeNull();
  });

  it('allowlist-and-project: does NOT reject for machine columns and never surfaces them', () => {
    expect(() => parseDirectArmBundle(directBundleRaw, 'fixture')).not.toThrow();
    expectNoMachineKeys(parseDirectArmBundle(directBundleRaw, 'fixture'));
  });

  it('enforces the namespace firewall (wrong expected namespace → mismatch)', () => {
    try {
      parseDirectArmBundle(clone(directBundleRaw), 'production');
      throw new Error('expected rejection');
    } catch (e) {
      expect(e).toBeInstanceOf(AdapterError);
      expect((e as AdapterError).code).toBe('namespace_mismatch');
    }
  });

  it('rejects a non-hex bundle_sha256 (bundles are content-addressed)', () => {
    const bad = clone(directBundleRaw);
    bad.bundle_sha256 = 'NOT-A-HEX-DIGEST';
    expect(() => parseDirectArmBundle(bad, 'fixture')).toThrow(AdapterError);
  });
});

describe('parseDirectArmBundle — arm-key + pair-shape gates (fail-closed)', () => {
  it('rejects an arm whose arm_key disagrees with (program, change, condition)', () => {
    const bad = clone(directBundleRaw);
    const k = directArmKey(PROGRAM, 'increase', 'Rest');
    bad.arms[k].arm_key = 'direct|th17_like|increase|WrongCondition';
    try {
      parseDirectArmBundle(bad, 'fixture');
      throw new Error('expected rejection');
    } catch (e) {
      expect((e as AdapterError).code).toBe('arm_key_mismatch');
    }
  });

  it('rejects an arm parked under a bundle map key that differs from its arm_key', () => {
    const bad = clone(directBundleRaw);
    const k = directArmKey(PROGRAM, 'increase', 'Rest');
    // move the (valid) arm to a wrong map key
    bad.arms['direct|th17_like|increase|Rest__WRONG_MAP'] = bad.arms[k];
    delete (bad.arms as Record<string, unknown>)[k];
    try {
      parseDirectArmBundle(bad, 'fixture');
      throw new Error('expected rejection');
    } catch (e) {
      expect((e as AdapterError).code).toBe('arm_key_mismatch');
    }
  });

  it('rejects a legacy PRE-JOINED pair-shaped arm (top-level away_from_A present)', () => {
    const bad = clone(directBundleRaw) as unknown as {
      arms: Record<string, Record<string, unknown>>;
    };
    bad.arms[directArmKey(PROGRAM, 'increase', 'Rest')].away_from_A = -0.5;
    try {
      parseDirectArmBundle(bad, 'fixture');
      throw new Error('expected rejection');
    } catch (e) {
      expect((e as AdapterError).code).toBe('legacy_pair_shape');
    }
  });

  it('rejects a legacy arm carrying a stored joint_status (join is display-time only)', () => {
    const bad = clone(directBundleRaw) as unknown as {
      arms: Record<string, Record<string, unknown>>;
    };
    bad.arms[directArmKey(PROGRAM, 'increase', 'Rest')].joint_status = 'concordant';
    try {
      parseDirectArmBundle(bad, 'fixture');
      throw new Error('expected rejection');
    } catch (e) {
      expect((e as AdapterError).code).toBe('legacy_pair_shape');
    }
  });
});

// ───────────────────────────── Temporal bundle (Rest → Stim48hr) ─────────────────────────────

const temporalBundleRaw = {
  provenance: bundleProv('demo_temporal_arm_bundle', 'e2e2e2e2', 'spot.stage02_temporal_arm_bundle.v1'),
  bundle_sha256: h64('bd2'),
  from: 'Rest',
  to: 'Stim48hr',
  arms: {
    [temporalArmKey(PROGRAM, 'increase', 'Rest', 'Stim48hr')]: {
      arm_key: temporalArmKey(PROGRAM, 'increase', 'Rest', 'Stim48hr'),
      program_id: PROGRAM,
      desired_change: 'increase',
      rows: [
        {
          target_ensembl: 'ENSG00000000001',
          target_symbol: 'GENE_A',
          did: -0.12,
          effect_from: -0.52,
          effect_to: -0.64,
          present_from: true,
          present_to: true,
          machine_batch_id: 'batch-9', // projected away
        },
        {
          target_ensembl: 'ENSG00000000004',
          target_symbol: 'GENE_D',
          did: null,
          effect_from: -0.2,
          effect_to: null,
          present_from: true,
          present_to: false, // union row: absent at the `to` endpoint
        },
      ],
    },
    [temporalArmKey(PROGRAM, 'decrease', 'Rest', 'Stim48hr')]: {
      arm_key: temporalArmKey(PROGRAM, 'decrease', 'Rest', 'Stim48hr'),
      program_id: PROGRAM,
      desired_change: 'decrease',
      rows: [],
    },
  },
};

describe('parseTemporalArmBundle — ordered (from → to) all-arm bundle', () => {
  it('resolves a temporal arm for a DIFFERENT-timepoint pair with per-arm DiD + both endpoints', () => {
    const b = parseTemporalArmBundle(temporalBundleRaw, 'fixture');
    expect(b.lane).toBe('temporal');
    expect(b.from).toBe('Rest');
    expect(b.to).toBe('Stim48hr');

    const inc = getTemporalArm(b, PROGRAM, 'increase');
    expect(inc).not.toBeNull();
    expect(inc!.arm_key).toBe('temporal|th17_like|increase|Rest|Stim48hr');
    expect(inc!.from).toBe('Rest');
    expect(inc!.to).toBe('Stim48hr');
    expect(inc!.rows[0].did).toBe(-0.12);
    expect(inc!.rows[0].effect_from).toBe(-0.52);
    expect(inc!.rows[0].effect_to).toBe(-0.64);
  });

  it('emits a union row with the missing endpoint marked absent (never zero) + projects machine cols', () => {
    const b = parseTemporalArmBundle(temporalBundleRaw, 'fixture');
    const inc = getTemporalArm(b, PROGRAM, 'increase')!;
    const d = inc.rows.find((r) => r.target_ensembl === 'ENSG00000000004')!;
    expect(d.present_to).toBe(false);
    expect(d.effect_to).toBeNull();
    expect(d.did).toBeNull();
    expectNoMachineKeys(b);
  });
});

// ───────────────────────────── Pathway bundle (reactome, Rest) ─────────────────────────────

const pathwayBundleRaw = {
  provenance: bundleProv('demo_pathway_arm_bundle', 'e3e3e3e3', 'spot.stage02_pathway_arm_bundle.v1'),
  bundle_sha256: h64('bd3'),
  condition: 'Rest',
  source: 'reactome',
  convergence_ref: convergenceKey('Rest', 'reactome'),
  arms: {
    [pathwayArmKey(PROGRAM, 'increase', 'Rest', 'reactome')]: {
      arm_key: pathwayArmKey(PROGRAM, 'increase', 'Rest', 'reactome'),
      program_id: PROGRAM,
      desired_change: 'increase',
      records: [
        {
          pathway_id: 'R-HSA-FIX01',
          name: 'Synthetic convergent signature 01',
          contributing_targets: ['ENSG00000000001', 'ENSG00000000002'],
          druggable: true,
          source_hash: 'fixturehashpathway01', // record-level machine field, projected away
          enrichment: {
            arm_headline_rankable: true,
            arm_coverage_disposition: 'rankable',
            enrichment_value: 2.1,
            n_hits_in_ranking: 4,
            source_coverage: 0.66,
          },
        },
        {
          pathway_id: 'R-HSA-FIX02',
          name: 'Synthetic convergent signature 02',
          contributing_targets: ['ENSG00000000001'],
          druggable: false,
          enrichment: {
            arm_headline_rankable: false,
            arm_coverage_disposition: 'descriptive_only_low_source_coverage',
            enrichment_value: null,
            n_hits_in_ranking: 1,
            source_coverage: 0.2,
          },
        },
      ],
    },
    [pathwayArmKey(PROGRAM, 'decrease', 'Rest', 'reactome')]: {
      arm_key: pathwayArmKey(PROGRAM, 'decrease', 'Rest', 'reactome'),
      program_id: PROGRAM,
      desired_change: 'decrease',
      records: [],
    },
  },
};

describe('parsePathwayArmBundle — per-(condition, source) all-arm bundle + shared convergence', () => {
  it('resolves a pathway arm with arm-scoped enrichment (headline-rankable + disposition)', () => {
    const b = parsePathwayArmBundle(pathwayBundleRaw, 'fixture');
    expect(b.lane).toBe('pathway');
    expect(b.condition).toBe('Rest');
    expect(b.source).toBe('reactome');
    expect(b.convergence_ref).toBe('convergence|Rest|reactome');

    const inc = getPathwayArm(b, PROGRAM, 'increase');
    expect(inc).not.toBeNull();
    expect(inc!.arm_key).toBe('pathway|th17_like|increase|Rest|reactome');
    expect(inc!.convergence_ref).toBe('convergence|Rest|reactome');

    const r0 = inc!.records[0];
    expect(r0.enrichment.arm_headline_rankable).toBe(true);
    expect(r0.enrichment.arm_coverage_disposition).toBe('rankable');
    expect(r0.enrichment.enrichment_value).toBe(2.1);

    const r1 = inc!.records[1];
    expect(r1.enrichment.arm_headline_rankable).toBe(false);
    expect(r1.enrichment.arm_coverage_disposition).toBe('descriptive_only_low_source_coverage');
    expect(r1.enrichment.enrichment_value).toBeNull();
  });

  it('does NOT surface record-level machine fields (source_hash)', () => {
    expectNoMachineKeys(parsePathwayArmBundle(pathwayBundleRaw, 'fixture'));
  });

  it('rejects a convergence_ref that disagrees with (condition, source)', () => {
    const bad = clone(pathwayBundleRaw);
    bad.convergence_ref = 'convergence|Stim8hr|reactome';
    try {
      parsePathwayArmBundle(bad, 'fixture');
      throw new Error('expected rejection');
    } catch (e) {
      expect((e as AdapterError).code).toBe('convergence_ref_mismatch');
    }
  });

  it('rejects a pathway arm keyed under the wrong source', () => {
    const bad = clone(pathwayBundleRaw);
    const k = pathwayArmKey(PROGRAM, 'increase', 'Rest', 'reactome');
    bad.arms[k].arm_key = pathwayArmKey(PROGRAM, 'increase', 'Rest', 'go_bp');
    try {
      parsePathwayArmBundle(bad, 'fixture');
      throw new Error('expected rejection');
    } catch (e) {
      expect((e as AdapterError).code).toBe('arm_key_mismatch');
    }
  });
});
