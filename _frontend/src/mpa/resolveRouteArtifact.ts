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
import type { CompactStage2SelectionView } from '../domain/compactStage2Projection';
import type { JoinedView, ResolvedBundles } from '../repository/joinResolver';
import type { Stage3UiArtifact } from '../domain/stage3UiArtifact';
import type { Stage4UiArtifact } from '../domain/stage4UiArtifact';
import type { StageMethodsManifest } from '../domain/methodsManifest';
import type { UiResultsCurrent } from '../domain/uiResultsCurrent';
import type { RealRouteResolution } from './renderReal';
import type { SelectionV3 } from '../adapters/selectionV3Adapter';
import { parseUiResultsCurrent } from '../adapters/uiResultsCurrentAdapter';
import { mergeAdmittedManifest, parseUiReleaseManifest } from '../adapters/uiReleaseManifestAdapter';
import { parseDrugsProjection, parsePkSafetyProjection } from '../adapters/routeProjectionAdapter';
import { parseCompactDisplayReceipt, parseCompactStage2Projection } from '../adapters/compactStage2ProjectionAdapter';
import { resultRouteKeyForPage } from '../domain/uiResultsCurrent';
import { resolveCompactStage2Selection } from '../repository/compactStage2Resolver';
import { canonicalJson, sha256Hex } from '../stage1/canonical';
import { STAGE1_SELECTION_SCHEMA_RAW_SHA256, STAGE1_V3_RELEASE_SELF_SHA256 } from '../stage1/contractBinding';
import { readStage1SelectionV3 } from './contrastTitle';
import { buildStageMethodsManifest } from './stageMethods';
import { loadAdmittedP2sSecondary, type AdmittedP2sSecondary } from '../p2s/p2sAdmission';

const RESULTS_ROOT = 'results/';
const RESULTS_CURRENT_PATH = `${RESULTS_ROOT}current.json`;
// current.json manifest_path / projection_path are RESULTS-tree-relative (matching the deploy inventory);
// the browser resolves them under the served results/ root.
const underResults = (relPath: string): string => `${RESULTS_ROOT}${relPath}`;

/** A route's native canvas projection — a Stage-2 join view, or a Stage-3/Stage-4 UI artifact. */
export type RouteProjection =
  | { kind: 'stage2'; view: CompactStage2SelectionView | JoinedView; bundles?: ResolvedBundles;
      p2sPending?: Promise<AdmittedP2sSecondary | undefined> }
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
    manifestText = await fetchText(underResults(entry.manifest_path));
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
    return { route: 'targets', view: projection.view, bundles: projection.bundles,
      p2sPending: projection.p2sPending, admission: 'admitted', manifest };
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
 * The REAL content-verified production projection loader. For the active route it reads the route's
 * `projection_path` + `projection_content_hash` from results/current.json, fetches the same-origin
 * projection, verifies its canonical content hash, and strict-parses the compact route schema into a
 * RouteProjection. FAIL-CLOSED: no projection bound, a 404, malformed JSON, a content-hash mismatch, an
 * unknown/wrong-route/fixture-shaped projection, or (for Stage-2) an absent selection / analysis-mode
 * mismatch all return null → the route stays unbound. Stage-2 resolves the JoinedView from the ADMITTED
 * bundles + the stored, independently-verified v3 selection (never a synthetic view). Never demo/fixture.
 */
export async function loadProductionProjection(
  page: PageKey,
  current: UiResultsCurrent,
  fetchText: (path: string) => Promise<string>,
  selection: SelectionV3 | null,
): Promise<RouteProjection | null> {
  const routeKey = resultRouteKeyForPage(page);
  if (!routeKey) return null;
  const entry = current.routes[routeKey];
  if (!entry || !entry.projection_path || !entry.projection_content_hash) return null; // no projection → unbound

  // #1 STALE CROSS-RELEASE REFUSAL — the results MUST descend from the ACTIVE selection's Stage-1 scorer
  // binding. Every route (not just Stage-2) requires a verified selection and an exact registry-scorer-view
  // match; a result package from a different Stage-1 release/scorer is refused, never rendered.
  if (!selection) return null;
  if (current.stage1_binding.registry_scorer_view_sha256 !== selection.registry_scorer_view_sha256) return null;

  // 539431d RELEASE PIN — the served release identity MUST equal the exact Stage-1 v3 contract this UI
  // was built against (schema-file raw sha + release self-hash). A UI built on a different Stage-1 release
  // never binds these results, even if the scorer view happened to match. Fail closed on any drift.
  if (current.stage1_binding.selection_schema_raw_sha256 !== STAGE1_SELECTION_SCHEMA_RAW_SHA256) return null;
  if (current.stage1_binding.release_self_sha256 !== STAGE1_V3_RELEASE_SELF_SHA256) return null;

  let raw: unknown;
  let projectionText: string;
  try {
    projectionText = await fetchText(underResults(entry.projection_path));
    raw = JSON.parse(projectionText);
  } catch {
    return null; // 404 / malformed JSON
  }
  // content-address the projection (canonical form — same convention as the ui_release manifest).
  try {
    if ((await sha256Hex(canonicalJson(raw))) !== entry.projection_content_hash) return null;
  } catch {
    return null;
  }

  // #6 CROSS-ROUTE CHAIN — each route's projection must descend from the admitted chain
  // (Stage-2 run → Stage-3 bundle → Stage-4 scorecard set) by EXACT id; an admitted receipt over
  // data from a different run/bundle is refused (the chain ids come from results/current.json).
  const chain = current.chain;
  try {
    if (routeKey === 'drugs') {
      const artifact = parseDrugsProjection(raw);
      if (artifact.upstream_stage2_run !== chain.stage2_run_id) return null;
      if (artifact.bundle_id !== chain.stage3_bundle_id) return null;
      return { kind: 'stage3', artifact };
    }
    if (routeKey === 'pksafety') {
      const artifact = parsePkSafetyProjection(raw);
      if (artifact.upstream_stage3_bundle !== chain.stage3_bundle_id) return null;
      if (artifact.scorecard_set_id !== chain.stage4_scorecard_set_id) return null;
      return { kind: 'stage4', artifact };
    }
    // Stage-2 (targets | pathways): W3's compact all-arm prefix, selected at join time. Release
    // order/source/run identity comes ONLY from the explicit route metadata — never inferred from keys.
    const meta = entry.compact_stage2;
    if (!meta || meta.display_release_id !== chain.stage2_display_release_id) return null;
    if ((await sha256Hex(projectionText)) !== meta.projection_raw_sha256) return null;
    if ((await sha256Hex(canonicalJson(raw))) !== meta.projection_canonical_sha256) return null;
    const proj = await parseCompactStage2Projection(raw, meta.projection_self_sha256);

    const receiptText = await fetchText(underResults(meta.independent_verifier.receipt_path));
    if ((await sha256Hex(receiptText)) !== meta.independent_verifier.receipt_raw_sha256) return null;
    const receiptRaw = JSON.parse(receiptText) as unknown;
    if ((await sha256Hex(canonicalJson(receiptRaw))) !== meta.independent_verifier.receipt_canonical_sha256) return null;
    // Admit the receipt against the EXACT projection identity (not n_arms alone): the receipt subject
    // must bind these projection bytes. A real receipt lacking the W3 subject fails closed here.
    parseCompactDisplayReceipt(receiptRaw, {
      n_arms: proj.n_arms,
      projection_raw_sha256: meta.projection_raw_sha256,
      projection_canonical_sha256: meta.projection_canonical_sha256,
      projection_self_sha256: meta.projection_self_sha256,
    });

    const view = resolveCompactStage2Selection(proj, meta, selection, routeKey);
    // P2S is an optional, secondary/non-gating lane. Its own admission may fail without weakening or
    // hiding the already-admitted Direct result; failure simply leaves this optional field absent.
    let p2sPending: Promise<AdmittedP2sSecondary | undefined> | undefined;
    if (routeKey === 'targets' && entry.p2s_secondary) {
      // Start the optional sidecar in parallel but DO NOT await it: slow, absent, or malformed P2S
      // bytes cannot delay the already-admitted Direct canvas. StageIsland hydrates it later.
      p2sPending = loadAdmittedP2sSecondary(entry.p2s_secondary, fetchText, proj).then((candidate) => {
        const displayedArms = new Set(view.effectRankFacets.flatMap((facet) =>
          [facet.increase.arm_key, facet.decrease.arm_key]));
        return displayedArms.has(candidate.support.armKey) &&
          displayedArms.has(candidate.support.siblingArmKey) ? candidate : undefined;
      }).catch(() => undefined);
    }
    return { kind: 'stage2', view, p2sPending };
  } catch {
    return null; // strict-parse rejection / view-resolution failure → unbound
  }
}

export async function resolveProductionRealArtifact(page: PageKey): Promise<RealRouteResolution | null> {
  try {
    const selection = await readStage1SelectionV3().catch(() => null);
    return await resolveRouteArtifact(page, {
      fetchText: sameOriginFetchText,
      loadProjection: (p, current, fetchText) => loadProductionProjection(p, current, fetchText, selection),
    });
  } catch {
    return null;
  }
}
