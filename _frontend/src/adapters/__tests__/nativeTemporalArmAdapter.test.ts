// Aligns the temporal consumer to W5's NATIVE spot.stage02_temporal_arm_bundle.v1 shape:
// base_records identity (join by base_key, never symbol), arm records with arm_value +
// temporal_status + native desired_target_modulation + RETAINED rank-null rows, ranking refs,
// and the independent-verifier ref (external admission pending).

import { describe, expect, it } from 'vitest';
import { AdapterError } from '../errors';
import {
  parseNativeTemporalArmBundle,
  getNativeTemporalArm,
  nativeTemporalIdentity,
  nativeTemporalAdmission,
  resolveTemporalAdmission,
} from '../nativeTemporalArmAdapter';
import { fixtureProvenance } from '../../fixtures/synthetic';

const clone = <T,>(v: T): T => structuredClone(v);
function expectCode(fn: () => unknown, code: string) {
  try { fn(); } catch (e) {
    expect(e).toBeInstanceOf(AdapterError);
    expect((e as AdapterError).code).toBe(code);
    return;
  }
  throw new Error(`expected AdapterError(${code})`);
}

const ARM = 'temporal|th17_like|decrease|Rest|Stim48hr';
function native() {
  return {
    schema_version: 'spot.stage02_temporal_arm_bundle.v1',
    lane: 'temporal',
    analysis_mode: 'temporal_cross_condition',
    from_condition: 'Rest',
    to_condition: 'Stim48hr',
    bundle_id: 'abc123def456abcd',
    provenance: {
      ...fixtureProvenance({ stage: 'stage02', slug: 'temporal_arm', seed: 't1t1t1t1', methodId: 'temporal.native.fixture', sources: [] }),
      schema_version: 'spot.stage02_temporal_provenance.v1',
    },
    base_records: {
      'th17_like|ENSG1': { base_key: 'th17_like|ENSG1', program_id: 'th17_like', target_id: 'ENSG1', target_symbol: 'GENE1', target_ensembl: 'ENSG1', target_id_namespace: 'ensembl_gene_id', perturbation_modality: 'CRISPRi_knockdown', from_condition: 'Rest', to_condition: 'Stim48hr', temporal_status: 'evaluable', evaluable: true, base_delta: -0.2 },
      'th17_like|ENSG2': { base_key: 'th17_like|ENSG2', program_id: 'th17_like', target_id: 'ENSG2', target_symbol: null, target_ensembl: 'ENSG2', target_id_namespace: 'ensembl_gene_id', perturbation_modality: 'CRISPRi_knockdown', from_condition: 'Rest', to_condition: 'Stim48hr', temporal_status: 'not_evaluable', evaluable: false, base_delta: null },
    },
    arms: {
      [ARM]: {
        arm_key: ARM, program_id: 'th17_like', desired_change: 'decrease', from_condition: 'Rest', to_condition: 'Stim48hr',
        n_targets: 2, n_evaluable: 1, n_ranked: 1,
        records: [
          { target_id: 'ENSG1', base_key: 'th17_like|ENSG1', arm_value: -0.12, evaluable: true, temporal_status: 'evaluable', desired_target_modulation: 'supports_target_inhibition', rank: 1 },
          { target_id: 'ENSG2', base_key: 'th17_like|ENSG2', arm_value: null, evaluable: false, temporal_status: 'not_evaluable', desired_target_modulation: 'not_evaluable', rank: null },
        ],
        ranking: { path: 'rankings/th17_like__decrease.json', raw_sha256: 'a'.repeat(64), canonical_sha256: 'b'.repeat(64) },
      },
    },
    verification_ref: 'spot.stage02.temporal.arm.independent_verifier.v1',
  };
}

describe('parseNativeTemporalArmBundle — W5 native shape', () => {
  it('parses the native bundle, retains rank-null rows, and resolves an arm by desired_change key', () => {
    const b = parseNativeTemporalArmBundle(native(), 'fixture');
    const arm = getNativeTemporalArm(b, 'th17_like', 'decrease')!;
    expect(arm.arm_key).toBe(ARM);
    expect(arm.records).toHaveLength(2);
    expect(arm.records[1].rank).toBeNull(); // unrankable row RETAINED, not omitted
    expect(arm.records[0].arm_value).toBe(-0.12);
    expect(arm.records[0].desired_target_modulation).toBe('supports_target_inhibition');
  });

  it('joins identity via base_records by base_key (never by symbol)', () => {
    const b = parseNativeTemporalArmBundle(native(), 'fixture');
    const id = nativeTemporalIdentity(b, b.arms[ARM].records[0]);
    expect(id.target_ensembl).toBe('ENSG1');
    expect(id.target_symbol).toBe('GENE1');
  });

  it('marks external (W11) admission pending, matching the independent verifier id', () => {
    const a = nativeTemporalAdmission(parseNativeTemporalArmBundle(native(), 'fixture'));
    expect(a.external_admission).toBe('pending');
    expect(a.matches_independent_id).toBe(true);
  });

  it('rejects a wrong bundle schema version', () => {
    const evil = clone(native());
    evil.schema_version = 'spot.stage02_temporal_arm_bundle.v2';
    expectCode(() => parseNativeTemporalArmBundle(evil, 'fixture'), 'unknown_schema_version');
  });

  it('rejects an arm_key that disagrees with (program, desired_change, from, to)', () => {
    const evil = clone(native());
    evil.arms[ARM].desired_change = 'increase'; // key still says decrease
    expectCode(() => parseNativeTemporalArmBundle(evil, 'fixture'), 'arm_key_mismatch');
  });

  it('rejects an arm record whose base_key has no base_records entry (referential integrity)', () => {
    const evil = clone(native());
    evil.arms[ARM].records[0].base_key = 'th17_like|GHOST';
    expectCode(() => parseNativeTemporalArmBundle(evil, 'fixture'), 'malformed');
  });

  it('rejects an unknown desired_target_modulation value (native vocabulary only)', () => {
    const evil = clone(native());
    evil.arms[ARM].records[0].desired_target_modulation = 'decrease'; // Direct vocab, not native
    expectCode(() => parseNativeTemporalArmBundle(evil, 'fixture'), 'malformed');
  });
});

describe('resolveTemporalAdmission — requires W5 release + W11 ADMIT of that exact release', () => {
  const rel = { release_sha256: 'r'.repeat(64) };
  it('admits only when both bind the same release', () => {
    expect(resolveTemporalAdmission({ w5_release: rel, w11_verification: { verdict: 'ADMIT', admits_release: 'r'.repeat(64) } })).toBe('admitted');
  });
  it('pending when W11 verification is absent (producer preflight is not admitted data)', () => {
    expect(resolveTemporalAdmission({ w5_release: rel, w11_verification: null })).toBe('pending');
  });
  it('pending when W11 does not ADMIT or binds a different release', () => {
    expect(resolveTemporalAdmission({ w5_release: rel, w11_verification: { verdict: 'REJECT', admits_release: 'r'.repeat(64) } })).toBe('pending');
    expect(resolveTemporalAdmission({ w5_release: rel, w11_verification: { verdict: 'ADMIT', admits_release: 'x'.repeat(64) } })).toBe('pending');
  });
});
