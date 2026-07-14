// The fixture firewall. These tests are the load-bearing guarantee that a
// research/fixture artifact can never be relabelled into a production pointer,
// and that stale combined scores / illegal ranks / unknown schemas are rejected.

import { describe, expect, it } from 'vitest';
import { AdapterError } from '../errors';
import { parseStage2 } from '../stage2Adapter';
import { parseStage3 } from '../stage3Adapter';
import { parseStage4 } from '../stage4Adapter';
import { parseSelection } from '../selectionAdapter';
import { stage2FixtureRaw } from '../../fixtures/stage2.fixture';
import { stage3FixtureRaw } from '../../fixtures/stage3.fixture';
import { stage4FixtureRaw } from '../../fixtures/stage4.fixture';
import { selectionFixtureRaw } from '../../fixtures/selection.fixture';

const clone = <T,>(v: T): T => structuredClone(v);

function expectCode(fn: () => unknown, code: string) {
  try {
    fn();
  } catch (e) {
    expect(e).toBeInstanceOf(AdapterError);
    expect((e as AdapterError).code).toBe(code);
    return;
  }
  throw new Error(`expected AdapterError(${code}) but none was thrown`);
}

describe('valid fixtures parse under the fixture namespace', () => {
  it('parses stage 2/3/4 + selection', () => {
    expect(parseStage2(stage2FixtureRaw, 'fixture').levers.length).toBeGreaterThan(0);
    expect(parseStage3(stage3FixtureRaw, 'fixture').candidates.length).toBeGreaterThan(0);
    expect(parseStage4(stage4FixtureRaw, 'fixture').scorecards.length).toBeGreaterThan(0);
    expect(parseSelection(selectionFixtureRaw, 'fixture').production_gate_passed).toBe(false);
  });

  it('marks fixtures production_eligible=false', () => {
    expect(parseStage2(stage2FixtureRaw, 'fixture').provenance.production_eligible).toBe(false);
    expect(parseStage3(stage3FixtureRaw, 'fixture').provenance.production_eligible).toBe(false);
    expect(parseStage4(stage4FixtureRaw, 'fixture').provenance.production_eligible).toBe(false);
  });
});

describe('namespace relabelling attacks are rejected', () => {
  it('rejects a fixture whose provenance claims production', () => {
    const evil = clone(stage2FixtureRaw);
    evil.provenance.namespace = 'production';
    expectCode(() => parseStage2(evil, 'fixture'), 'namespace_mismatch');
  });

  it('rejects a fixture parsed under the wrong expected namespace', () => {
    expectCode(() => parseStage2(clone(stage2FixtureRaw), 'production'), 'namespace_mismatch');
  });

  it('rejects a non-production artifact claiming production_eligible=true', () => {
    const evil = clone(stage2FixtureRaw);
    evil.provenance.production_eligible = true;
    expectCode(() => parseStage2(evil, 'fixture'), 'illegal_production_claim');
  });

  it('rejects a selection claiming it passed the production gate', () => {
    const evil = clone(selectionFixtureRaw);
    evil.production_gate_passed = true;
    expectCode(() => parseSelection(evil, 'fixture'), 'illegal_production_claim');
  });
});

describe('fixture-to-production pointer firewall', () => {
  it('rejects an upstream pointer that crosses into production', () => {
    const evil = clone(stage2FixtureRaw);
    evil.provenance.upstream_ref = {
      artifact_id: 'production:stage01:demo@abcdef012345',
      canonical_sha256: 'a'.repeat(64),
    };
    expectCode(() => parseStage2(evil, 'fixture'), 'cross_namespace_pointer');
  });

  it('rejects an artifact-id whose namespace segment disagrees with the declared namespace', () => {
    const evil = clone(stage2FixtureRaw);
    evil.provenance.artifact_id = 'production:stage02:demo@abcdef012345';
    expectCode(() => parseStage2(evil, 'fixture'), 'namespace_mismatch');
  });
});

describe('unknown schema versions are rejected', () => {
  it('rejects an unrecognized stage-2 schema version', () => {
    const evil = clone(stage2FixtureRaw);
    evil.provenance.schema_version = 'spot.stage02_gene_lever_set.v2';
    expectCode(() => parseStage2(evil, 'fixture'), 'unknown_schema_version');
  });

  it('rejects an unrecognized stage-4 schema version', () => {
    const evil = clone(stage4FixtureRaw);
    evil.provenance.schema_version = 'made.up.v9';
    expectCode(() => parseStage4(evil, 'fixture'), 'unknown_schema_version');
  });
});

describe('missing hashes are rejected', () => {
  it('rejects a missing canonical hash', () => {
    const evil = clone(stage2FixtureRaw);
    delete (evil.provenance.hashes as unknown as Record<string, unknown>).canonical_sha256;
    expectCode(() => parseStage2(evil, 'fixture'), 'missing_hash');
  });
});

describe('stale combined/balanced fields are rejected', () => {
  it('rejects a lever carrying a combined_score', () => {
    const evil = clone(stage2FixtureRaw);
    (evil.levers[0] as unknown as Record<string, unknown>).combined_score = 0.9;
    expectCode(() => parseStage2(evil, 'fixture'), 'stale_combined_field');
  });

  it('rejects a lever carrying a balanced_a_to_b field', () => {
    const evil = clone(stage2FixtureRaw);
    (evil.levers[1] as unknown as Record<string, unknown>).balanced_a_to_b = 1;
    expectCode(() => parseStage2(evil, 'fixture'), 'stale_combined_field');
  });
});

describe('nullable arm ranks', () => {
  it('accepts null ranks on not-evaluated arms', () => {
    const parsed = parseStage2(stage2FixtureRaw, 'fixture');
    const notEval = parsed.levers.find((g) => !g.arms.toward_B.evaluated);
    expect(notEval?.arms.toward_B.rank).toBeNull();
  });

  it('rejects a non-null rank on a not-evaluated arm', () => {
    const evil = clone(stage2FixtureRaw);
    const gene = evil.levers.find((g) => g.gene_id === 'GENE_B');
    if (!gene) throw new Error('fixture missing GENE_B');
    (gene.arms.toward_B as unknown as Record<string, unknown>).rank = 3;
    expectCode(() => parseStage2(evil, 'fixture'), 'illegal_rank_on_ineligible_arm');
  });
});

describe('Stage-2 typed joint ordering (multi-objective, never averaged)', () => {
  it('permits the typed ordering fields joint_status / pareto_tier / joint_ordering_method_id', () => {
    const parsed = parseStage2(stage2FixtureRaw, 'fixture');
    expect(parsed.joint_ordering_method_id).toBeTruthy();
    expect(parsed.levers[0].joint_status).toBe('both_arms');
    expect(parsed.levers[0].pareto_tier).toBe(1);
  });

  it('rejects a non-positive-integer pareto_tier', () => {
    const evil = clone(stage2FixtureRaw);
    (evil.levers[0] as unknown as Record<string, unknown>).pareto_tier = 0;
    expectCode(() => parseStage2(evil, 'fixture'), 'malformed');
  });

  it('still rejects a numeric combined score alongside the typed ordering', () => {
    const evil = clone(stage2FixtureRaw);
    (evil.levers[0] as unknown as Record<string, unknown>).combined_score = 0.9;
    expectCode(() => parseStage2(evil, 'fixture'), 'stale_combined_field');
  });
});

describe('optional v3 Stage-1 bindings', () => {
  it('has null bindings when the bridge supplies none', () => {
    expect(parseSelection(selectionFixtureRaw, 'fixture').stage1_bindings).toBeNull();
  });

  it('validates and preserves v3 bindings when present', () => {
    const withV3 = {
      ...clone(selectionFixtureRaw),
      stage1_method_version: 'stage1-continuous-v3.0.1',
      program_registry_sha256: 'c'.repeat(64),
      source_h5ad_sha256: 'd'.repeat(64),
    };
    const b = parseSelection(withV3, 'fixture').stage1_bindings;
    expect(b?.stage1_method_version).toBe('stage1-continuous-v3.0.1');
    expect(b?.program_registry_sha256).toBe('c'.repeat(64));
    expect(b?.source_h5ad_sha256).toBe('d'.repeat(64));
    // Untouched optional fields stay null.
    expect(b?.validation_raw_sha256).toBeNull();
  });

  it('rejects a malformed (non-hex) v3 digest', () => {
    const evil = { ...clone(selectionFixtureRaw), program_registry_sha256: 'NOT-A-HASH' };
    expectCode(() => parseSelection(evil, 'fixture'), 'malformed');
  });
});

describe('missing-data is preserved, never coerced to zero', () => {
  it('keeps a missing exposure value null with state missing', () => {
    const parsed = parseStage4(stage4FixtureRaw, 'fixture');
    const b = parsed.scorecards.find((s) => s.candidate_id === 'COMPOUND_B');
    expect(b?.exposure.systemic_cmax.value).toBeNull();
    expect(b?.exposure.systemic_cmax.state).toBe('missing');
  });

  it('rejects a field whose present value contradicts a missing state', () => {
    const evil = clone(stage4FixtureRaw);
    const b = evil.scorecards.find((s) => s.candidate_id === 'COMPOUND_B');
    if (!b) throw new Error('fixture missing COMPOUND_B');
    b.exposure.systemic_cmax = { value: 0, state: 'missing', unit: 'uM', source: null };
    expectCode(() => parseStage4(evil, 'fixture'), 'malformed');
  });
});
