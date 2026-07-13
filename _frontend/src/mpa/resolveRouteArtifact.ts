// The production real-artifact resolution seam — ROUTE-DISCRIMINATED + FAIL-CLOSED. It loads
// results/current.json, then the active route's ui_release manifest (the drawer run-status binding)
// and its native projection (the canvas rows), verifying content addresses + the route/method
// firewall + the admitted-verifier token at every step. Any missing hash, admission mismatch, unknown
// field, unsupported schema, wrong route, or absent projection leaves the route UNBOUND (returns
// null) — never a partial or fabricated render.
//
// Result bytes are same-origin, content-addressed files, NEVER localStorage/sessionStorage (those
// carry only the Stage-1 selection contract). No fixture, no demo.

import type { PageKey } from './pages';
import type { JoinedView, ResolvedBundles } from '../repository/joinResolver';
import type { Stage3UiArtifact } from '../domain/stage3UiArtifact';
import type { Stage4UiArtifact } from '../domain/stage4UiArtifact';
import type { StageMethodsManifest } from '../domain/methodsManifest';
import type { UiResultsCurrent } from '../domain/uiResultsCurrent';
import type { RealRouteResolution } from './renderReal';
import { parseUiResultsCurrent } from '../adapters/uiResultsCurrentAdapter';
import { mergeAdmittedManifest, parseUiReleaseManifest } from '../adapters/uiReleaseManifestAdapter';
import { resultRouteKeyForPage } from '../domain/uiResultsCurrent';
import { buildStageMethodsManifest } from './stageMethods';

const RESULTS_CURRENT_PATH = 'results/current.json';

/** A route's native canvas projection — a Stage-2 join view, or a Stage-3/Stage-4 UI artifact. */
export type RouteProjection =
  | { kind: 'stage2'; view: JoinedView; bundles: ResolvedBundles }
  | { kind: 'stage3'; artifact: Stage3UiArtifact }
  | { kind: 'stage4'; artifact: Stage4UiArtifact };

/** Injectable IO — production wires same-origin fetch + the native projection loader; tests inject fakes. */
export interface RouteLoaderDeps {
  fetchText: (path: string) => Promise<string>;
  /** Load + content-verify the route's native projection, or null when none is bound (→ route unbound). */
  loadProjection: (
    page: PageKey,
    current: UiResultsCurrent,
    fetchText: (path: string) => Promise<string>,
  ) => Promise<RouteProjection | null>;
}

/** Fetch + parse results/current.json (fail-closed). Returns null if absent/unfetchable/malformed. */
export async function loadResultsCurrent(fetchText: (p: string) => Promise<string>): Promise<UiResultsCurrent | null> {
  let text: string;
  try {
    text = await fetchText(RESULTS_CURRENT_PATH);
  } catch {
    return null; // absent (404) → all routes unbound
  }
  try {
    return parseUiResultsCurrent(JSON.parse(text));
  } catch {
    return null; // malformed / unknown-schema / bad binding → fail closed
  }
}

/**
 * Load + fail-closed-verify the route's ui_release manifest and MERGE it onto the static route method
 * definition. Returns the merged manifest, or null if the route is absent, the manifest is unfetchable,
 * or any gate (content hash / schema / stage+method firewall / admitted verifier / completeness) fails.
 * This is the drawer run-status binding; the canvas projection is loaded separately.
 */
export async function loadRouteReleaseManifest(
  page: PageKey,
  current: UiResultsCurrent,
  fetchText: (p: string) => Promise<string>,
): Promise<StageMethodsManifest | null> {
  const routeKey = resultRouteKeyForPage(page);
  if (!routeKey) return null;
  const entry = current.routes[routeKey];
  if (!entry) return null; // route not bound in current.json → unbound

  const staticDef = await buildStageMethodsManifest(page).catch(() => null);
  if (!staticDef || !staticDef.methods.method_id) return null;

  let manifestText: string;
  try {
    manifestText = await fetchText(entry.manifest_path);
  } catch {
    return null;
  }
  try {
    const admitted = await parseUiReleaseManifest(
      JSON.parse(manifestText),
      entry.content_hash,
      staticDef.stage_label,
      staticDef.methods.method_id,
    );
    return mergeAdmittedManifest(staticDef, admitted);
  } catch {
    return null; // any fail-closed gate → route stays on the static definition
  }
}

/** Assemble the route-discriminated resolution from a merged manifest + a MATCHING native projection. */
function toResolution(page: PageKey, projection: RouteProjection, manifest: StageMethodsManifest): RealRouteResolution | null {
  const routeKey = resultRouteKeyForPage(page);
  if (routeKey === 'targets' && projection.kind === 'stage2') {
    return { route: 'targets', view: projection.view, bundles: projection.bundles, admission: 'admitted', manifest };
  }
  if (routeKey === 'pathways' && projection.kind === 'stage2') {
    return { route: 'pathways', view: projection.view, bundles: projection.bundles, admission: 'admitted', manifest };
  }
  if (routeKey === 'drugs' && projection.kind === 'stage3') {
    return { route: 'drugs', artifact: projection.artifact, admission: 'admitted', manifest };
  }
  if (routeKey === 'pksafety' && projection.kind === 'stage4') {
    return { route: 'pksafety', artifact: projection.artifact, admission: 'admitted', manifest };
  }
  return null; // route/projection kind mismatch → fail closed
}

/**
 * Resolve the admitted real artifact for a route (fail-closed at every step). Returns a
 * route-discriminated resolution ONLY when the ui_release manifest is admitted AND a matching native
 * projection is bound; otherwise null (the route stays on its static definition + one-line status).
 */
export async function resolveRouteArtifact(page: PageKey, deps: RouteLoaderDeps): Promise<RealRouteResolution | null> {
  const current = await loadResultsCurrent(deps.fetchText);
  if (!current) return null;
  const manifest = await loadRouteReleaseManifest(page, current, deps.fetchText);
  if (!manifest) return null;
  const projection = await deps.loadProjection(page, current, deps.fetchText).catch(() => null);
  if (!projection) return null; // no admitted projection → unbound (never partially rendered)
  return toResolution(page, projection, manifest);
}

// ── production wiring ──

async function sameOriginFetchText(path: string): Promise<string> {
  const res = await fetch(path, { cache: 'no-store' });
  if (!res.ok) throw new Error(`fetch ${path} → ${res.status}`);
  return res.text();
}

/**
 * PRE-RUN production loader. No native projection loader is wired yet (W1 supplies the deterministic
 * native→browser projection loaders after the real run), so this resolves to null and the island shows
 * the compact pending state. It NEVER returns demo/fixture data. Once W1 binds results/current.json +
 * the per-route ui_release manifests + native projections, this begins returning admitted resolutions.
 */
const noProjectionYet: RouteLoaderDeps['loadProjection'] = async () => null;

export async function resolveProductionRealArtifact(page: PageKey): Promise<RealRouteResolution | null> {
  try {
    return await resolveRouteArtifact(page, { fetchText: sameOriginFetchText, loadProjection: noProjectionYet });
  } catch {
    return null;
  }
}
