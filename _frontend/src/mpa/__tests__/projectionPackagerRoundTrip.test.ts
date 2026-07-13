// End-to-end fixture round-trip: the offline packager preserves W3's admitted compact Stage-2
// projection + generator≠verifier receipt, content-addresses the served tree, and the production
// browser loader independently verifies and resolves it for the active v3 selection.

import { describe, expect, it } from 'vitest';
import { loadProductionProjection, resolveRouteArtifact } from '../resolveRouteArtifact';
import type { RouteLoaderDeps } from '../resolveRouteArtifact';
import { STAGE1_SELECTION_SCHEMA_RAW_SHA256, STAGE1_V3_RELEASE_SELF_SHA256 } from '../../stage1/contractBinding';
import type { SelectionV3 } from '../../adapters/selectionV3Adapter';
import { compactProjectionRaw, compactReceiptAdmitted, CONDITIONS, SOURCES } from '../../test/compactStage2';

interface Packager {
  pack: (spec: unknown) => { tree: Record<string, string>; current: unknown };
  deriveCompactProjection: (route: string, native: unknown) => unknown;
  hydrateStage2FileInputs: (spec: any, baseDir: string, readText: (path: string) => string) => any;
}
async function importPack(): Promise<Packager> {
  const modPath: string = '../../../deploy/pack_ui_projections.mjs';
  return import(modPath) as Promise<Packager>;
}

function treeFetch(tree: Record<string, string>) {
  return async (path: string): Promise<string> => {
    const rel = path.startsWith('results/') ? path.slice('results/'.length) : path;
    if (Object.prototype.hasOwnProperty.call(tree, rel)) return tree[rel];
    throw new Error(`404 ${path}`);
  };
}

function receipt(route: string) {
  return {
    release_revision: 'rev-1', raw_sha256: 'a'.repeat(64), canonical_sha256: 'b'.repeat(64),
    method_code_sha256: 'c'.repeat(64), environment: 'conda@env1', last_run_utc: '2026-07-13T00:00:00Z',
    generator_status: 'generated', verifier_status: 'admitted', reproduce_command: `spot repro ${route}`,
    cs_notebook_url: null, artifact_paths: ['results/x.json'], source_artifact_ids: ['s1'],
  };
}

const drugsNative = {
  schema_version: 'spot.stage03_drug_annotation.v2', artifact_class: 'analysis',
  bundle_id: 's3_b1', canonical_content_sha256: 'a'.repeat(64),
  p_q_fdr_permitted: false, candidate_rank_permitted: false, combined_objective_permitted: false,
  headline_arm_permitted: false, stage2_aggregate: { manifest_self_hash: 'b'.repeat(64) },
  candidates: [{ candidate_id: 'cand-1', active_moiety_id: 'AM1', preferred_name: 'Examplib',
    identity_status: 'resolved', molecule_chembl_ids: ['CHEMBL1'], target_ids: ['ENSG1'],
    n_edges_by_origin: { direct_target: 1, temporal_cross_time_measured: 1, endpoint_pathway_context: 0 },
    max_phase_status: 'stated', max_phase_sources: ['4'], observed_perturbation_arm_keys: ['a1'],
    observed_perturbation_support: true, mechanism_match_statuses: ['phenocopies_the_perturbation_that_helped'],
    pathway_hypothesis_arm_keys: [], stage3_evidence_classes: ['measured_perturbation'],
    stage4_assessment_status: 'queued', stage4_assessment_reason: null, source_record_ids: ['s1'] }],
};
const pksafetyNative = {
  schema_id: 'spot.stage04_browser_projection.v1', scorecard_set_id: 's4_1',
  upstream: { candidate_set_id: 's3_b1', namespace: 'production', is_fixture: false },
  store_is_selection_independent: true, is_ranking: false, ordering: { by: 'candidate_id' }, guards: [],
  active_selection_view: null, active_view_candidate_ids: ['cand-1'],
  candidates: [{ candidate_id: 'cand-1', active_moiety: { active_moiety_name: 'Examplib' },
    compound_ids: { chembl_id: 'CID1' }, target: 'T1', mechanism: 'inhibitor', direction_compatibility: 'supported',
    production_eligible: { eligible: true, reason_code: null }, provenance_chain: [], stage3_arm_membership: {},
    in_active_view: true, lanes: { delivery: [], cns_mpo: { status: 'complete' }, transporters: {}, exposure: [],
      nebpi: [], safety: { rows: [] }, potency: { state: 'not_evaluated' }, evidence_availability: {} } }],
};

const withinSelection: SelectionV3 = {
  selection_id: 'a'.repeat(16), question_id: 'q'.repeat(16), analysis_mode: 'within_condition', execution_status: 'ready',
  estimator_id: 'within_condition_v1', estimator_status: 'available',
  A: { program_id: 'prog_alpha', direction: 'high' }, B: { program_id: 'prog_beta', direction: 'low' }, conditions: ['Rest'],
  registry_scorer_view_sha256: 'd'.repeat(64), source_h5ad_sha256: 'c'.repeat(64),
  selection_full_sha256: 'f'.repeat(64), full_contract_content_sha256: 'e'.repeat(64), raw: {},
};

async function makeSpec(opts?: { projection?: Awaited<ReturnType<typeof compactProjectionRaw>>; projectionText?: string }) {
  const projection = opts?.projection ?? await compactProjectionRaw();
  // W3 hands the packager EXACT projection bytes; the subject raw hash is over those bytes. The default
  // here simulates a differently-formatted-but-identical-content serialization (pretty-printed) to prove
  // the packager preserves the bytes verbatim rather than re-serializing them.
  const text = opts?.projectionText ?? JSON.stringify(projection, null, 2);
  const display_verifier_receipt = await compactReceiptAdmitted(projection, text);
  const compact_release = {
    display_release_id: 'stage2-display-1', release_conditions: [...CONDITIONS], pathway_sources: [...SOURCES],
    active_pathway_source: 'reactome',
  };
  const stage2 = { projection_text: text, display_verifier_receipt, compact_release };
  return {
    stage2_run_id: 'b'.repeat(64),
    stage1_binding: {
      release_method_version: 'stage1-continuous-v3.0.1', registry_scorer_view_sha256: 'd'.repeat(64),
      selection_schema_raw_sha256: STAGE1_SELECTION_SCHEMA_RAW_SHA256,
      release_self_sha256: STAGE1_V3_RELEASE_SELF_SHA256,
    },
    routes: {
      targets: { ...stage2, receipt: receipt('targets') },
      pathways: { ...stage2, receipt: receipt('pathways') },
      drugs: { native: drugsNative, receipt: receipt('drugs') },
      pksafety: { native: pksafetyNative, receipt: receipt('pksafety') },
    },
  };
}

const deps = (sel: SelectionV3 | null, tree: Record<string, string>): RouteLoaderDeps => ({
  fetchText: treeFetch(tree),
  loadProjection: (p, current, fetchText) => loadProductionProjection(p, current, fetchText, sel),
});

describe('packager → browser loader round-trip', () => {
  it('hydrates exact W3 projection/receipt files without embedding or reserializing their bytes', async () => {
    const { pack, hydrateStage2FileInputs } = await importPack();
    const projection = await compactProjectionRaw();
    const projectionText = JSON.stringify(projection, null, 1) + '\n';
    const admitted = await compactReceiptAdmitted(projection, projectionText);
    const spec = await makeSpec({ projection, projectionText });
    for (const route of ['targets', 'pathways'] as const) {
      delete (spec.routes[route] as any).projection_text;
      delete (spec.routes[route] as any).display_verifier_receipt;
      Object.assign(spec.routes[route], {
        projection_file: 'projection.json', display_verifier_receipt_file: 'receipt.json',
      });
    }
    const files: Record<string, string> = {
      '/run/projection.json': projectionText, '/run/receipt.json': JSON.stringify(admitted),
    };
    hydrateStage2FileInputs(spec, '/run', (path) => files[path]);
    const { tree } = pack(spec);
    expect(tree['stage02/stage2_display_projection.json']).toBe(projectionText);
  });

  it('preserves one exact W3 projection for both Stage-2 routes and binds its receipt/hashes', async () => {
    const { pack } = await importPack();
    const { tree, current } = pack(await makeSpec());
    expect(tree['stage02/stage2_display_projection.json']).toBeTruthy();
    expect(tree['stage02/display_projection.verification.json']).toBeTruthy();
    const cur = current as { chain: { stage2_display_release_id: string; stage2_run_id: string | null }; routes: Record<string, { compact_stage2: { release_conditions: string[]; pathway_sources: string[]; projection_self_sha256: string } }> };
    expect(cur.chain.stage2_display_release_id).toBe('stage2-display-1');
    expect(cur.chain.stage2_run_id).toBe('b'.repeat(64));
    expect(cur.routes.targets.compact_stage2.release_conditions).toEqual(CONDITIONS);
    expect(cur.routes.targets.compact_stage2.pathway_sources).toEqual(SOURCES);
    expect(cur.routes.targets.compact_stage2).toEqual(cur.routes.pathways.compact_stage2);

    const targets = await resolveRouteArtifact('targets', deps(withinSelection, tree));
    const pathways = await resolveRouteArtifact('pathways', deps(withinSelection, tree));
    expect(targets?.route).toBe('targets');
    expect(pathways?.route).toBe('pathways');
    expect(targets?.manifest?.methods.reproduce_command).toBe('spot repro targets');
    expect(pathways?.manifest?.provenance.verifier_status).toBe('admitted');
  });

  it('serves W3 projection bytes VERBATIM (formatting differs, content identical) and refuses a stale receipt over another serialization', async () => {
    const { pack } = await importPack();
    const projection = await compactProjectionRaw();
    const pretty = JSON.stringify(projection, null, 2); // W3's exact bytes (sorted-python-like formatting)
    const compactText = JSON.stringify(projection);     // identical CONTENT, different bytes

    // (a) the served projection file is the EXACT input bytes — never re-serialized
    const { tree } = pack(await makeSpec({ projection, projectionText: pretty }));
    expect(tree['stage02/stage2_display_projection.json']).toBe(pretty);
    expect(tree['stage02/stage2_display_projection.json']).not.toBe(compactText);
    // and it still round-trips through the browser loader (raw hash is over the served bytes)
    const resolved = await resolveRouteArtifact('targets', deps(withinSelection, tree));
    expect(resolved?.route).toBe('targets');

    // (b) a receipt whose subject hashed a DIFFERENT serialization than the served bytes is refused
    const stale = await compactReceiptAdmitted(projection, compactText); // subject over compact bytes
    const spec = await makeSpec({ projection, projectionText: pretty });  // but serve the pretty bytes
    spec.routes.targets.display_verifier_receipt = stale;
    spec.routes.pathways.display_verifier_receipt = stale;
    expect(() => pack(spec)).toThrow(/different projection/);
  });

  it('round-trips Stage-3 and Stage-4 while preserving typed missing values', async () => {
    const { pack } = await importPack();
    const { tree } = pack(await makeSpec());
    const drugs = await resolveRouteArtifact('drugs', deps(withinSelection, tree));
    expect(drugs?.route).toBe('drugs');
    expect(drugs && drugs.route === 'drugs' ? drugs.artifact.candidates[0].observed_perturbation_support : false).toBe(true);
    const pk = await resolveRouteArtifact('pksafety', deps(withinSelection, tree));
    const art = pk && pk.route === 'pksafety' ? pk.artifact : null;
    expect(art?.candidates[0].lanes.delivery).toEqual([]);
    expect(art?.candidates[0].lanes.transporters).toEqual({});
    expect(art?.candidates[0].lanes.potency).toEqual({ state: 'not_evaluated' });
  });

  it('refuses retired or fixture Stage-3 native documents before projecting candidates', async () => {
    const { deriveCompactProjection } = await importPack();
    expect(() => deriveCompactProjection('drugs', { ...drugsNative,
      schema_version: 'spot.stage03_drug_annotation.v1' })).toThrow(/schema_version/);
    expect(() => deriveCompactProjection('drugs', { ...drugsNative,
      artifact_class: 'fixture' })).toThrow(/artifact_class|fixture/);
  });

  it('fails closed when projection or independent-receipt bytes change', async () => {
    const { pack } = await importPack();
    const { tree } = pack(await makeSpec());
    const badProjection = { ...tree, 'stage02/stage2_display_projection.json': tree['stage02/stage2_display_projection.json'].replace('prog_alpha', 'tampered') };
    expect(await resolveRouteArtifact('targets', deps(withinSelection, badProjection))).toBeNull();
    const badReceipt = { ...tree, 'stage02/display_projection.verification.json': tree['stage02/display_projection.verification.json'].replace('"admit"', '"reject"') };
    expect(await resolveRouteArtifact('targets', deps(withinSelection, badReceipt))).toBeNull();
  });

  it('refuses a stale Stage-1 scorer binding on every route', async () => {
    const { pack } = await importPack();
    const { tree } = pack(await makeSpec());
    const stale = { ...withinSelection, registry_scorer_view_sha256: '9'.repeat(64) };
    for (const route of ['targets', 'pathways', 'drugs', 'pksafety'] as const) {
      expect(await resolveRouteArtifact(route, deps(stale, tree))).toBeNull();
    }
  });
});

describe('packager refuses invented or inconsistent Stage-2 releases', () => {
  it('requires W3 projection + independent receipt, never the retired imagined aggregate', async () => {
    const { pack } = await importPack();
    const base = await makeSpec();
    const retired = { run_id: 'stage2-run-1', directByCondition: {}, temporalByPair: {}, pathwayByContext: {} };
    const bad = { ...base, routes: { targets: { native: retired, receipt: receipt('targets') } } };
    expect(() => pack(bad)).toThrow(/projection|compact_release/);
  });

  it('refuses non-admitted/mismatched display receipts and mutable release ordering', async () => {
    const { pack } = await importPack();
    const base = await makeSpec();
    const target = base.routes.targets;
    expect(() => pack({ ...base, routes: { targets: { ...target, display_verifier_receipt: { ...target.display_verifier_receipt, verdict: 'reject' } } } })).toThrow(/verifier receipt/);
    expect(() => pack({ ...base, routes: { targets: { ...target, compact_release: { ...target.compact_release, release_conditions: ['Stim8hr', 'Rest', 'Stim48hr'] } } } })).toThrow(/exactly/);
    expect(() => pack({ ...base, routes: { targets: { ...target, compact_release: { ...target.compact_release, display_release_id: 'other' } }, pathways: base.routes.pathways } })).toThrow(/display_release_id differs/);
    expect(() => pack({ ...base, routes: { targets: target, pathways: { ...base.routes.pathways,
      compact_release: { ...base.routes.pathways.compact_release, active_pathway_source: 'go_bp' } } } })).toThrow(/metadata disagrees/);
  });

  it('refuses hidden p/q/combined fields before writing the served tree', async () => {
    const { pack } = await importPack();
    for (const key of ['empirical_p_value', 'qval', 'fdr', 'combined_score', 'balanced_skew']) {
      const projection = await compactProjectionRaw();
      const first = Object.values(projection.arms)[0] as { rows: Record<string, unknown>[] };
      first.rows[0][key] = 0.01;
      const base = await makeSpec({ projection, projectionText: JSON.stringify(projection) });
      expect(() => pack(base)).toThrow(/forbidden/);
    }
  });

  it('still refuses missing run provenance and cross-stage chain mismatches', async () => {
    const { pack } = await importPack();
    const base = await makeSpec();
    const badReceipt = { ...base, routes: { drugs: { native: drugsNative, receipt: { ...receipt('drugs'), reproduce_command: undefined } } } };
    expect(() => pack(badReceipt)).toThrow(/reproduce_command/);
    const wrong = { ...drugsNative, stage2_aggregate: { manifest_self_hash: '9'.repeat(64) } };
    expect(() => pack({ ...base, routes: { ...base.routes, drugs: { native: wrong, receipt: receipt('drugs') } } })).toThrow(/upstream_stage2_run/);
  });
});
