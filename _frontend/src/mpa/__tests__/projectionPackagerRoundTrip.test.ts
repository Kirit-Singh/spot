// End-to-end fixture round-trip: the offline packager DERIVES compact route projections from admitted
// NATIVE bundles + receipts, content-addresses them, and emits the served results/ tree; the browser
// loader then fetches that exact tree and re-verifies every content hash before returning a resolution.
// If the packager's canonical hashing or manifest binding diverged from the browser's, this fails.
// Fixture-only — no production results are written.

import { describe, expect, it } from 'vitest';
import { loadProductionProjection, resolveRouteArtifact } from '../resolveRouteArtifact';
import type { RouteLoaderDeps } from '../resolveRouteArtifact';
import { parseStage2Projection } from '../../adapters/routeProjectionAdapter';
import type { SelectionV3 } from '../../adapters/selectionV3Adapter';

const CONDS = ['Rest', 'Stim8hr', 'Stim48hr'];
const SOURCES = ['reactome', 'go_bp'];
/** Complete placeholder Stage-2 release: all 3 Direct + 6 ordered temporal + 6 pathway slots. */
function completeStage2Maps() {
  const directByCondition: Record<string, unknown> = {};
  const temporalByPair: Record<string, unknown> = {};
  const pathwayByContext: Record<string, unknown> = {};
  for (const c of CONDS) directByCondition[c] = { _slot: c };
  for (const f of CONDS) for (const t of CONDS) if (f !== t) temporalByPair[`${f}__${t}`] = { _slot: `${f}__${t}` };
  for (const c of CONDS) for (const s of SOURCES) pathwayByContext[`${c}|${s}`] = { _slot: `${c}|${s}` };
  return { directByCondition, temporalByPair, pathwayByContext };
}

// Untyped Node ESM packager — imported at runtime; `string`-typed specifier keeps tsc from resolving it.
interface Packager {
  pack: (spec: unknown) => { tree: Record<string, string>; current: unknown };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  deriveCompactProjection: (route: string, native: unknown) => any;
}
async function importPack(): Promise<Packager> {
  const modPath: string = '../../../deploy/pack_ui_projections.mjs';
  return import(modPath) as Promise<Packager>;
}

// A same-origin fetch backed by the packager's virtual tree (results-relative keys; loader prefixes results/).
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
  bundle_id: 's3_b1', manifest_sha256: 'a'.repeat(64), upstream_stage2_run: 'run_1',
  candidates: [{ candidate_id: 'cand-1', preferred_name: 'Examplib', identity_status: 'resolved', development_state_aggregate: 'approved', potency_state: null }],
};
const pksafetyNative = {
  scorecard_set_id: 's4_1', stage4_method_version: 'stage4-evidence-v2', upstream_stage3_bundle: 's3_b1',
  candidates: [{ candidate_id: 'cand-1', active_moiety: 'Examplib', target: 'T1', mechanism: 'inhibitor', production_eligible: null, lanes: { delivery: 'oral', safety: null } }],
};
const stage2Native = {
  run_id: 'run_1', analysis_mode: 'within_condition',
  release_conditions: CONDS, pathway_sources: SOURCES, pathway_source: 'reactome',
  ...completeStage2Maps(),
};

const withinSelection: SelectionV3 = {
  selection_id: 'a'.repeat(16), analysis_mode: 'within_condition', execution_status: 'ready',
  estimator_id: 'within_condition_v1', estimator_status: 'available',
  A: { program_id: 'p1', direction: 'high' }, B: { program_id: 'p2', direction: 'high' }, conditions: ['Rest'],
  registry_scorer_view_sha256: 'd'.repeat(64), source_h5ad_sha256: 'c'.repeat(64), // matches spec.stage1_binding
  selection_full_sha256: 'f'.repeat(64), full_contract_content_sha256: 'e'.repeat(64), raw: {},
};
// results/current.json is SELECTION-INDEPENDENT — one release resolves any within/temporal selection.
const spec = {
  stage1_binding: { release_method_version: 'stage1-continuous-v3.0.1', registry_scorer_view_sha256: 'd'.repeat(64) },
  routes: {
    targets: { native: stage2Native, receipt: receipt('targets') },
    drugs: { native: drugsNative, receipt: receipt('drugs') },
    pksafety: { native: pksafetyNative, receipt: receipt('pksafety') },
  },
};

const deps = (sel: SelectionV3 | null, tree: Record<string, string>): RouteLoaderDeps => ({
  fetchText: treeFetch(tree),
  loadProjection: (p, current, fetchText) => loadProductionProjection(p, current, fetchText, sel),
});

describe('packager → browser loader round-trip (native fixtures)', () => {
  it('Drugs: derived + content-addressed → loader binds artifact + admitted run', async () => {
    const { pack } = await importPack();
    const { tree } = pack(spec);
    const res = await resolveRouteArtifact('drugs', deps(withinSelection, tree));
    expect(res?.route).toBe('drugs');
    expect(res && res.route === 'drugs' ? res.artifact.bundle_id : null).toBe('s3_b1');
    expect(res && res.route === 'drugs' ? res.artifact.candidates[0].development_state_aggregate : null).toBe('approved');
    expect(res && res.route === 'drugs' ? res.artifact.candidates[0].potency_state : 'x').toBeNull(); // missing stays missing
    expect(res?.manifest?.methods.reproduce_command).toBe('spot repro drugs');
    expect(res?.manifest?.provenance.verifier_status).toBe('admitted');
  });

  it('PK & Safety: derived lanes preserved; not-evaluated stays null', async () => {
    const { pack } = await importPack();
    const { tree } = pack(spec);
    const res = await resolveRouteArtifact('pksafety', deps(withinSelection, tree));
    expect(res?.route).toBe('pksafety');
    const art = res && res.route === 'pksafety' ? res.artifact : null;
    expect(art?.scorecard_set_id).toBe('s4_1');
    expect(art?.candidates[0].lanes.delivery).toBe('oral');
    expect(art?.candidates[0].lanes.safety).toBeNull();
    expect(art?.candidates[0].lanes.transporters).toBeNull(); // absent native lane → typed missing
    expect(art?.candidates[0].production_eligible).toBeNull();
  });

  it('Targets (Stage-2): packager emits the COMPLETE generic release the adapter accepts (all slots)', async () => {
    const { pack, deriveCompactProjection } = await importPack();
    // #2 completeness: the derived projection carries the whole release (3 Direct + 6 temporal + 6 pathway)
    const parsed = parseStage2Projection(deriveCompactProjection('targets', stage2Native));
    expect(parsed.release_conditions).toEqual(CONDS);
    expect(Object.keys(parsed.directByCondition).sort()).toEqual(['Rest', 'Stim48hr', 'Stim8hr']);
    expect(Object.keys(parsed.temporalByPair).length).toBe(6);
    expect(Object.keys(parsed.pathwayByContext).length).toBe(6);
    // and it round-trips through the packager (served projection present + content-addressed)
    const { tree, current } = pack(spec);
    expect(tree['stage02/targets.ui.json']).toBeTruthy();
    expect((current as { chain: { stage2_run_id: string } }).chain.stage2_run_id).toBe('run_1');
  });

  it('a corrupted served projection byte fails the content hash → route unbound', async () => {
    const { pack } = await importPack();
    const { tree } = pack(spec);
    const tampered = { ...tree, 'stage03/drugs.ui.json': tree['stage03/drugs.ui.json'].replace('Examplib', 'Tampered') };
    const res = await resolveRouteArtifact('drugs', deps(withinSelection, tampered));
    expect(res).toBeNull();
  });

  it('a route with no admitted native/receipt is simply absent (unbound), others still bind', async () => {
    const { pack } = await importPack();
    const { tree } = pack(spec); // pksafety present, but request an unlisted route binding
    const res = await resolveRouteArtifact('pathways', deps(withinSelection, tree)); // pathways not in spec
    expect(res).toBeNull();
  });

  it('#1 stale cross-release: a selection whose Stage-1 scorer binding differs is refused on EVERY route', async () => {
    const { pack } = await importPack();
    const { tree } = pack(spec);
    const stale: SelectionV3 = { ...withinSelection, registry_scorer_view_sha256: '9'.repeat(64) }; // a different Stage-1 release
    for (const route of ['drugs', 'pksafety', 'targets'] as const) {
      expect(await resolveRouteArtifact(route, deps(stale, tree))).toBeNull();
    }
    // no selection at all also refuses (cannot validate the release binding)
    expect(await resolveRouteArtifact('drugs', deps(null, tree))).toBeNull();
  });
});

describe('packager: derives from native, never invents run metadata', () => {
  it('refuses a missing required receipt field', async () => {
    const { pack } = await importPack();
    const bad = { ...spec, routes: { drugs: { native: drugsNative, receipt: { ...receipt('drugs'), reproduce_command: undefined } } } };
    expect(() => pack(bad)).toThrow(/reproduce_command/);
  });
  it('refuses a non-admitted verifier status', async () => {
    const { pack } = await importPack();
    const bad = { ...spec, routes: { drugs: { native: drugsNative, receipt: { ...receipt('drugs'), verifier_status: 'pending' } } } };
    expect(() => pack(bad)).toThrow(/admitted token/);
  });
  it('refuses hand-authored compact rows (native input required)', async () => {
    const { pack } = await importPack();
    const bad = { ...spec, routes: { drugs: { receipt: receipt('drugs') } } }; // no native
    expect(() => pack(bad)).toThrow(/native input required/);
  });
  it('derives Stage-2 objects from native base_records[]/arms[] arrays (values unchanged)', async () => {
    const { deriveCompactProjection } = await importPack();
    const maps = completeStage2Maps();
    maps.temporalByPair['Rest__Stim8hr'] = { bundle_id: 'b1', base_records: [{ base_key: 'k1', target_symbol: 'SYM1' }], arms: [{ arm_key: 'a1', records: [{ base_key: 'k1', arm_value: -0.1 }] }] };
    const compact = deriveCompactProjection('targets', { run_id: 'run_1', analysis_mode: 'temporal_cross_condition', release_conditions: CONDS, pathway_sources: SOURCES, pathway_source: 'reactome', ...maps });
    const t = compact.temporalByPair['Rest__Stim8hr'];
    expect(t.base_records.k1).toEqual({ base_key: 'k1', target_symbol: 'SYM1' }); // array → object keyed by base_key
    expect(t.arms.a1.arm_key).toBe('a1');
    expect(Array.isArray(t.arms.a1.records)).toBe(true); // arm.records stays a native array
  });

  it('#6 chain: refuses drugs upstream_stage2_run != stage-2 run_id at pack time (receipt A + data B)', async () => {
    const { pack } = await importPack();
    const badDrugs = { ...drugsNative, upstream_stage2_run: 'run_WRONG' };
    const bad = { ...spec, routes: { ...spec.routes, drugs: { native: badDrugs, receipt: receipt('drugs') } } };
    expect(() => pack(bad)).toThrow(/chain.*upstream_stage2_run|upstream_stage2_run.*run_id/);
  });

  it('#6 chain: loader refuses a projection whose upstream id != the current.json chain', async () => {
    const { pack } = await importPack();
    const { tree } = pack(spec);
    // tamper the pointer's chain so the drugs projection.upstream_stage2_run no longer matches
    const cur = JSON.parse(tree['current.json']);
    cur.chain.stage2_run_id = 'run_TAMPERED';
    const tampered = { ...tree, 'current.json': JSON.stringify(cur) };
    expect(await resolveRouteArtifact('drugs', deps(withinSelection, tampered))).toBeNull();
  });

  it('#2 completeness: packager refuses an INCOMPLETE Stage-2 release (missing a temporal pair)', async () => {
    const { pack } = await importPack();
    const maps = completeStage2Maps();
    delete (maps.temporalByPair as Record<string, unknown>)['Stim8hr__Stim48hr'];
    const incomplete = { run_id: 'run_1', analysis_mode: 'within_condition', release_conditions: CONDS, pathway_sources: SOURCES, pathway_source: 'reactome', ...maps };
    const bad = { ...spec, routes: { targets: { native: incomplete, receipt: receipt('targets') } } };
    expect(() => pack(bad)).toThrow(/incomplete|missing (temporal|Direct|pathway)/);
  });
});
