// The route resolution loader is FAIL-CLOSED at every step: results/current.json → the route's
// ui_release manifest (content hash + stage/method firewall + admitted verifier + completeness) →
// mergeAdmittedManifest → a matching native projection. Missing current.json, an absent route, a hash
// mismatch, a cross-route method_id, a non-admitted verifier, a 404 manifest, OR an absent/kind-mismatched
// projection all leave the route UNBOUND (null) — never a partial render. A valid admitted manifest +
// matching projection yields a route-discriminated admitted resolution carrying the merged drawer manifest.

import { describe, expect, it } from 'vitest';
import {
  loadResultsCurrent,
  loadRouteReleaseManifest,
  resolveRouteArtifact,
} from '../resolveRouteArtifact';
import type { RouteProjection } from '../resolveRouteArtifact';
import { parseUiResultsCurrent } from '../../adapters/uiResultsCurrentAdapter';
import { buildStageMethodsManifest } from '../stageMethods';
import { canonicalJson, sha256Hex } from '../../stage1/canonical';
import type { JoinedView, ResolvedBundles } from '../../repository/joinResolver';
import type { Stage3UiArtifact } from '../../domain/stage3UiArtifact';
import type { UiResultsCurrent } from '../../domain/uiResultsCurrent';
import type { PageKey } from '../pages';

const CURRENT_PATH = 'results/current.json';
const stage2Projection: RouteProjection = {
  kind: 'stage2',
  view: {} as unknown as JoinedView,
  bundles: {} as unknown as ResolvedBundles,
};

function stage3Artifact(): Stage3UiArtifact {
  return {
    schema_version: 'spot.stage03_drug_annotation.v1',
    bundle_id: 's3_bundle01',
    manifest_sha256: 'f'.repeat(64),
    upstream_stage2_run: 'stage02_run_777',
    candidates: [],
  };
}

function fakeFetch(files: Record<string, string>) {
  return async (path: string): Promise<string> => {
    if (Object.prototype.hasOwnProperty.call(files, path)) return files[path];
    throw new Error(`404 ${path}`);
  };
}

/** Build a fully admitted ui_release manifest JSON for a route + its pinned content hash. */
async function admittedManifest(page: PageKey, over: Record<string, unknown> = {}) {
  const def = await buildStageMethodsManifest(page);
  const manifest = {
    schema_version: 'spot.ui_release_manifest.v1',
    stage_label: def.stage_label,
    method_id: def.methods.method_id,
    release_revision: 'rev-1',
    raw_sha256: 'a'.repeat(64),
    canonical_sha256: 'b'.repeat(64),
    method_code_sha256: 'c'.repeat(64),
    environment: 'conda@env1',
    last_run_utc: '2026-07-13T00:00:00Z',
    generator_status: 'generated',
    verifier_status: 'admitted',
    reproduce_command: `spot repro ${page}`,
    cs_notebook_url: null,
    artifact_paths: ['results/stage02/release.json'],
    source_artifact_ids: ['stage02:run@abc'],
    ...over,
  };
  const json = JSON.stringify(manifest);
  const hash = await sha256Hex(canonicalJson(manifest));
  return { json, hash };
}

function current(routes: Record<string, unknown>): UiResultsCurrent {
  return parseUiResultsCurrent({
    schema: 'spot.ui_results_current.v1',
    stage1_binding: { release_method_version: 'stage1-continuous-v3.0.1', registry_scorer_view_sha256: 'd'.repeat(64) },
    routes,
  });
}
function entry(manifest_path: string, content_hash: string) {
  return { manifest_path, content_hash, projection_path: null, projection_content_hash: null };
}

describe('loadResultsCurrent — fail-closed pointer fetch', () => {
  it('absent current.json → null', async () => {
    expect(await loadResultsCurrent(fakeFetch({}))).toBeNull();
  });
  it('malformed JSON → null', async () => {
    expect(await loadResultsCurrent(fakeFetch({ [CURRENT_PATH]: '{ not json' }))).toBeNull();
  });
  it('unknown schema → null', async () => {
    expect(await loadResultsCurrent(fakeFetch({ [CURRENT_PATH]: JSON.stringify({ schema: 'x' }) }))).toBeNull();
  });
});

describe('loadRouteReleaseManifest — fail-closed drawer binding', () => {
  const MP = 'results/manifests/targets.ui_release.json';

  it('binds an admitted manifest → merged run rows onto the STATIC definition', async () => {
    const m = await admittedManifest('targets');
    const merged = await loadRouteReleaseManifest('targets', current({ targets: entry(MP, m.hash) }), fakeFetch({ [MP]: m.json }));
    expect(merged).not.toBeNull();
    expect(merged!.methods.method_code_sha256).toBe('c'.repeat(64));
    expect(merged!.provenance.verifier_status).toBe('admitted');
    expect(merged!.provenance.artifact_paths).toContain('results/stage02/release.json');
    // the static route method_id is preserved (definition prose is never taken from the release manifest)
    const def = await buildStageMethodsManifest('targets');
    expect(merged!.methods.method_id).toBe(def.methods.method_id);
  });

  it('route absent in current.json → null', async () => {
    expect(await loadRouteReleaseManifest('targets', current({}), fakeFetch({}))).toBeNull();
  });

  it('content-hash mismatch → null', async () => {
    const m = await admittedManifest('targets');
    const merged = await loadRouteReleaseManifest('targets', current({ targets: entry(MP, 'e'.repeat(64)) }), fakeFetch({ [MP]: m.json }));
    expect(merged).toBeNull();
  });

  it('cross-route method_id (a pksafety manifest served at the targets path) → null', async () => {
    const wrong = await admittedManifest('pksafety');
    const merged = await loadRouteReleaseManifest('targets', current({ targets: entry(MP, wrong.hash) }), fakeFetch({ [MP]: wrong.json }));
    expect(merged).toBeNull();
  });

  it('non-admitted verifier status → null', async () => {
    const m = await admittedManifest('targets', { verifier_status: 'pending' });
    const merged = await loadRouteReleaseManifest('targets', current({ targets: entry(MP, m.hash) }), fakeFetch({ [MP]: m.json }));
    expect(merged).toBeNull();
  });

  it('manifest path 404 → null', async () => {
    const m = await admittedManifest('targets');
    const merged = await loadRouteReleaseManifest('targets', current({ targets: entry(MP, m.hash) }), fakeFetch({}));
    expect(merged).toBeNull();
  });
});

describe('resolveRouteArtifact — route-discriminated admitted resolution', () => {
  async function filesFor(page: PageKey, manifestPath: string) {
    const m = await admittedManifest(page);
    return {
      [CURRENT_PATH]: JSON.stringify({
        schema: 'spot.ui_results_current.v1',
        stage1_binding: { release_method_version: 'stage1-continuous-v3.0.1', registry_scorer_view_sha256: 'd'.repeat(64) },
        routes: { [page]: entry(manifestPath, m.hash) },
      }),
      [manifestPath]: m.json,
    };
  }

  it('admitted manifest + matching stage2 projection → route:targets, admission admitted, merged manifest', async () => {
    const files = await filesFor('targets', 'results/manifests/targets.ui_release.json');
    const res = await resolveRouteArtifact('targets', { fetchText: fakeFetch(files), loadProjection: async () => stage2Projection });
    expect(res?.route).toBe('targets');
    expect(res?.admission).toBe('admitted');
    expect(res?.manifest?.methods.method_code_sha256).toBe('c'.repeat(64));
  });

  it('admitted manifest but NO projection → null (unbound, never partially rendered)', async () => {
    const files = await filesFor('targets', 'results/manifests/targets.ui_release.json');
    const res = await resolveRouteArtifact('targets', { fetchText: fakeFetch(files), loadProjection: async () => null });
    expect(res).toBeNull();
  });

  it('route/projection KIND mismatch (targets route, stage3 projection) → null', async () => {
    const files = await filesFor('targets', 'results/manifests/targets.ui_release.json');
    const proj: RouteProjection = { kind: 'stage3', artifact: stage3Artifact() };
    const res = await resolveRouteArtifact('targets', { fetchText: fakeFetch(files), loadProjection: async () => proj });
    expect(res).toBeNull();
  });

  it('drugs route + stage3 projection → route:drugs resolution', async () => {
    const files = await filesFor('drugs', 'results/manifests/drugs.ui_release.json');
    const proj: RouteProjection = { kind: 'stage3', artifact: stage3Artifact() };
    const res = await resolveRouteArtifact('drugs', { fetchText: fakeFetch(files), loadProjection: async () => proj });
    expect(res?.route).toBe('drugs');
  });

  it('absent current.json → null (all routes unbound), even with a projection available', async () => {
    const res = await resolveRouteArtifact('targets', { fetchText: fakeFetch({}), loadProjection: async () => stage2Projection });
    expect(res).toBeNull();
  });
});
