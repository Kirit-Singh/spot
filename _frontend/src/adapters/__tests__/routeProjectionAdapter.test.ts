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
      schema_version: 'spot.ui.stage03_candidates.v2',
      native_schema_version: 'spot.stage03_drug_annotation.v2',
      artifact_class: 'analysis',
      bundle_id: 's3_b1',
      canonical_content_sha256: H,
      upstream_stage2_run: 'run_1',
      candidates: [
        {
          candidate_id: 'cand-1', active_moiety_id: 'MOI1', preferred_name: 'Examplib', identity_status: 'resolved',
          molecule_chembl_ids: ['CHEMBL1'], target_ensembls: ['ENSG1'], n_edges: 2, n_direct_gene_edges: 1,
          max_phase_status: 'stated', max_phase_sources: ['4'],
          observed_perturbation_arms: ['a1'], observed_perturbation_support: true,
          mechanism_match_statuses: ['phenocopies_the_perturbation_that_helped'], pathway_hypothesis_arms: [],
          stage3_evidence_classes: ['measured_perturbation'], stage4_assessment_status: 'queued',
          stage4_assessment_reason: null, source_record_ids: ['s1'],
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
      schema_version: 'spot.stage04_browser_projection.v1', schema_id: 'spot.stage04_browser_projection.v1',
      scorecard_set_id: 's4_1', upstream_stage3_bundle: 's3_b1',
      upstream: { candidate_set_id: 's3_b1', namespace: 'production', is_fixture: false },
      store_is_selection_independent: true, is_ranking: false, ordering: { by: 'candidate_id' }, guards: [],
      active_selection_view: null, active_view_candidate_ids: [],
      candidates: [
        {
          candidate_id: 'cand-1', active_moiety: { active_moiety_name: 'Examplib' }, compound_ids: { chembl_id: 'CID1' },
          target: 'T1', mechanism: 'inhibitor', direction_compatibility: 'supported',
          production_eligible: { eligible: true, reason_code: null }, provenance_chain: [], stage3_arm_membership: {},
          in_active_view: true,
          lanes: { delivery: [], cns_mpo: { status: 'complete', total_published: 4.5 }, transporters: {},
            exposure: [], nebpi: [], safety: { rows: [] }, potency: { state: 'not_evaluated' },
            evidence_availability: { brain_exposure: 'not_evaluated' } },
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
    run_id: 'run_1',
    release_conditions: CONDS, pathway_sources: SOURCES, pathway_source: 'reactome',
    directByCondition: m.direct, temporalByPair: m.temporal, pathwayByContext: m.pathway,
  };
}

describe('parseDrugsProjection — strict', () => {
  it('parses a valid drugs projection', () => {
    const a = parseDrugsProjection(drugsRaw());
    expect(a.bundle_id).toBe('s3_b1');
    expect(a.candidates[0].candidate_id).toBe('cand-1');
    expect(a.candidates[0].observed_perturbation_support).toBe(true);
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
  it('rejects a retired native schema or non-analysis artifact class', () => {
    const v1 = drugsRaw();
    v1.artifact.native_schema_version = 'spot.stage03_drug_annotation.v1';
    expect(() => parseDrugsProjection(v1)).toThrow(/native_schema_version/);
    const fixture = drugsRaw();
    fixture.artifact.artifact_class = 'fixture';
    expect(() => parseDrugsProjection(fixture)).toThrow(/artifact_class|analysis/);
  });
  it('rejects a mis-typed candidate field', () => {
    const raw = drugsRaw();
    (raw.artifact.candidates[0] as unknown as Record<string, unknown>).molecule_chembl_ids = 'F1'; // must be string[]
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
    expect(a.candidates[0].production_eligible.eligible).toBe(true);
    expect(a.candidates[0].lanes.safety).toEqual({ rows: [] });
    expect(a.candidates[0].lanes.cns_mpo).toEqual({ status: 'complete', total_published: 4.5 });
  });
  it('rejects an unknown schema / wrong route', () => {
    expect(() => parsePkSafetyProjection({ ...pksafetyRaw(), schema_version: 'x' })).toThrow(AdapterError);
    expect(() => parsePkSafetyProjection({ ...pksafetyRaw(), route: 'drugs' })).toThrow(AdapterError);
  });
  it('rejects a research-only or fixture Stage-4 projection', () => {
    const raw = pksafetyRaw();
    raw.artifact.upstream.namespace = 'research_only';
    expect(() => parsePkSafetyProjection(raw)).toThrow(/production|fixture/);
  });
});

describe('parseStage2Projection — complete generic release', () => {
  it('accepts a complete release (3 Direct + 6 ordered temporal + 6 pathway slots)', () => {
    const p = parseStage2Projection(stage2Raw());
    expect(p.pathway_source).toBe('reactome'); // active source; the release itself is mode-agnostic
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
  it('rejects unknown schema / wrong route / missing run_id; carries NO top-level analysis_mode', () => {
    expect(() => parseStage2Projection({ ...stage2Raw(), schema_version: 'x' })).toThrow(AdapterError);
    expect(() => parseStage2Projection({ ...stage2Raw(), route: 'drugs' })).toThrow(AdapterError);
    expect(() => parseStage2Projection({ ...stage2Raw(), run_id: undefined })).toThrow(AdapterError);
    // the unified all-arm release is mode-agnostic — no analysis_mode is parsed (the selection decides).
    expect(parseStage2Projection(stage2Raw())).not.toHaveProperty('analysis_mode');
  });
});
