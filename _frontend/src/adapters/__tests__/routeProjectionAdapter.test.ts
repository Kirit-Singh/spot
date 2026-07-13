// Strict, fail-closed parsing of the compact browser route projections. A valid projection parses to
// the typed artifact; an unknown schema, wrong route, fixture/demo-namespaced id, or missing/mis-typed
// field is rejected. (Stage-2 arm bundles are delegated to the production arm adapters, which enforce
// the namespace firewall — a fixture-namespaced bundle is rejected there.)

import { describe, expect, it } from 'vitest';
import { AdapterError } from '../errors';
import { parseDrugsProjection, parsePkSafetyProjection, parseStage2Projection } from '../routeProjectionAdapter';

const H = 'a'.repeat(64);

function drugsRaw() {
  return {
    schema_version: 'spot.ui_projection.drugs.v1',
    route: 'drugs',
    artifact: {
      schema_version: 'spot.stage03_drug_annotation.v1',
      bundle_id: 's3_b1',
      manifest_sha256: H,
      upstream_stage2_run: 'run_1',
      candidates: [
        {
          candidate_id: 'cand-1', active_moiety_id: 'MOI1', preferred_name: 'Examplib', identity_status: 'resolved',
          form_ids: ['F1'], target_ensembls: ['ENSG1'], n_edges: 2, n_direct_gene_edges: 1,
          development_state_aggregate: 'approved', n_potency_rows: 0, potency_state: null,
          observed_perturbation_arms: ['a1'], inverse_direction_support: 'supported', pathway_hypothesis_arms: [],
          stage3_evidence_classes: ['observed_perturbation_target'], disease_context_review_status: 'reviewed',
          disease_context_review_result: 'eligible', stage4_assessment_status: 'queued', source_record_ids: ['s1'],
        },
      ],
    },
  };
}
function pksafetyRaw() {
  return {
    schema_version: 'spot.ui_projection.pksafety.v1',
    route: 'pksafety',
    artifact: {
      schema_version: 'spot.stage04_scorecards.v1', scorecard_set_id: 's4_1', stage4_method_version: 'stage4-evidence-v2',
      upstream_stage3_bundle: 's3_b1',
      candidates: [
        {
          candidate_id: 'cand-1', active_moiety: 'Examplib', compound_ids: ['CID1'], target: 'T1', mechanism: 'inhibitor',
          production_eligible: null, production_eligible_reason: null,
          lanes: { delivery: 'oral', cns_mpo: '4.5', transporters: null, exposure: null, nebpi: 'context_specific', safety: null },
        },
      ],
    },
  };
}
const CONDS = ['Rest', 'Stim8hr', 'Stim48hr'];
const SOURCES = ['reactome', 'go_bp'];
/** Complete placeholder release: all 3 Direct + 6 ordered temporal + 6 pathway slots present. */
function completeMaps() {
  const direct: Record<string, unknown> = {};
  const temporal: Record<string, unknown> = {};
  const pathway: Record<string, unknown> = {};
  for (const c of CONDS) direct[c] = { _slot: c };
  for (const f of CONDS) for (const t of CONDS) if (f !== t) temporal[`${f}__${t}`] = { _slot: `${f}__${t}` };
  for (const c of CONDS) for (const s of SOURCES) pathway[`${c}|${s}`] = { _slot: `${c}|${s}` };
  return { direct, temporal, pathway };
}
function stage2Raw() {
  const m = completeMaps();
  return {
    schema_version: 'spot.ui_projection.stage2.v1', route: 'targets',
    run_id: 'run_1', analysis_mode: 'within_condition',
    release_conditions: CONDS, pathway_sources: SOURCES, pathway_source: 'reactome',
    directByCondition: m.direct, temporalByPair: m.temporal, pathwayByContext: m.pathway,
  };
}

describe('parseDrugsProjection — strict', () => {
  it('parses a valid drugs projection', () => {
    const a = parseDrugsProjection(drugsRaw());
    expect(a.bundle_id).toBe('s3_b1');
    expect(a.candidates[0].candidate_id).toBe('cand-1');
    expect(a.candidates[0].potency_state).toBeNull();
  });
  it('rejects an unknown projection schema', () => {
    expect(() => parseDrugsProjection({ ...drugsRaw(), schema_version: 'spot.ui_projection.drugs.v2' })).toThrow(AdapterError);
  });
  it('rejects a wrong-route envelope', () => {
    expect(() => parseDrugsProjection({ ...drugsRaw(), route: 'targets' })).toThrow(AdapterError);
  });
  it('rejects a fixture-namespaced candidate id', () => {
    const raw = drugsRaw();
    raw.artifact.candidates[0].candidate_id = 'fixture:cand-1';
    expect(() => parseDrugsProjection(raw)).toThrow(/namespace_mismatch|non-production/);
  });
  it('rejects a fixture-namespaced bundle id', () => {
    expect(() => parseDrugsProjection({ ...drugsRaw(), artifact: { ...drugsRaw().artifact, bundle_id: 'demo:b1' } })).toThrow(AdapterError);
  });
  it('rejects a mis-typed candidate field', () => {
    const raw = drugsRaw();
    (raw.artifact.candidates[0] as unknown as Record<string, unknown>).form_ids = 'F1'; // must be string[]
    expect(() => parseDrugsProjection(raw)).toThrow(AdapterError);
  });
  it('rejects a namespace-smuggling envelope', () => {
    expect(() => parseDrugsProjection({ ...drugsRaw(), namespace: 'fixture' })).toThrow(/namespace/);
  });
});

describe('parsePkSafetyProjection — strict', () => {
  it('parses a valid pksafety projection; not-evaluated lanes stay null', () => {
    const a = parsePkSafetyProjection(pksafetyRaw());
    expect(a.scorecard_set_id).toBe('s4_1');
    expect(a.candidates[0].production_eligible).toBeNull();
    expect(a.candidates[0].lanes.safety).toBeNull();
    expect(a.candidates[0].lanes.nebpi).toBe('context_specific');
  });
  it('rejects an unknown schema / wrong route', () => {
    expect(() => parsePkSafetyProjection({ ...pksafetyRaw(), schema_version: 'x' })).toThrow(AdapterError);
    expect(() => parsePkSafetyProjection({ ...pksafetyRaw(), route: 'drugs' })).toThrow(AdapterError);
  });
});

describe('parseStage2Projection — complete generic release', () => {
  it('accepts a complete release (3 Direct + 6 ordered temporal + 6 pathway slots)', () => {
    const p = parseStage2Projection(stage2Raw());
    expect(p.analysis_mode).toBe('within_condition');
    expect(p.pathway_source).toBe('reactome');
    expect(Object.keys(p.directByCondition).sort()).toEqual(['Rest', 'Stim48hr', 'Stim8hr']);
    expect(Object.keys(p.temporalByPair).length).toBe(6);
    expect(Object.keys(p.pathwayByContext).length).toBe(6);
  });
  it('#2 completeness: a missing Direct/temporal/pathway slot FAILS (never renders empty)', () => {
    const m = completeMaps();
    delete m.direct.Stim48hr; // missing a Direct condition bundle
    expect(() => parseStage2Projection({ ...stage2Raw(), directByCondition: m.direct })).toThrow(/incomplete_release|missing/);
    const m2 = completeMaps();
    delete m2.temporal['Rest__Stim8hr']; // missing an ordered temporal pair
    expect(() => parseStage2Projection({ ...stage2Raw(), temporalByPair: m2.temporal })).toThrow(/incomplete_release|missing/);
    const m3 = completeMaps();
    delete m3.pathway['Rest|go_bp']; // missing a (condition, source) pathway bundle
    expect(() => parseStage2Projection({ ...stage2Raw(), pathwayByContext: m3.pathway })).toThrow(/incomplete_release|missing/);
  });
  it('rejects unknown schema / wrong route / invalid mode', () => {
    expect(() => parseStage2Projection({ ...stage2Raw(), schema_version: 'x' })).toThrow(AdapterError);
    expect(() => parseStage2Projection({ ...stage2Raw(), route: 'drugs' })).toThrow(AdapterError);
    expect(() => parseStage2Projection({ ...stage2Raw(), analysis_mode: 'pooled' })).toThrow(AdapterError);
  });
});
