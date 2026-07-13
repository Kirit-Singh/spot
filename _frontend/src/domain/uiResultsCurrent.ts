// results/current.json — the SINGLE mutable downstream pointer (schema spot.ui_results_current.v1).
//
// It is the only file the browser must fetch to discover admitted downstream results; it
// content-addresses every route it names (each route's ui_release manifest by pinned sha256) and
// binds the Stage-1 release the results descend from. It lives OUTSIDE the immutable Stage-1 `data/`
// tree (under `results/`), so binding downstream results never perturbs the pinned Stage-1 digest.
//
// FAIL-CLOSED: an absent, malformed, unknown-schema, or Stage-1-mismatched pointer leaves ALL routes
// unbound. A route simply absent from `routes` is unbound (not an error). No fixture, no fake result.

export const UI_RESULTS_CURRENT_SCHEMA = 'spot.ui_results_current.v1' as const;

export type ResultRouteKey = 'targets' | 'pathways' | 'drugs' | 'pksafety';
export const RESULT_ROUTE_KEYS: readonly ResultRouteKey[] = ['targets', 'pathways', 'drugs', 'pksafety'];

/** A per-route pointer to that route's content-addressed ui_release manifest + native projection. */
export interface RouteReleaseEntry {
  /** Same-origin path to this route's spot.ui_release_manifest.v1 (drawer run-status binding). */
  manifest_path: string;
  /** Pinned sha256 over that manifest's canonical JSON — the shell verifies before trusting it. */
  content_hash: string;
  /** Same-origin path to the route's native/projection bundle index, or null until one is bound. */
  projection_path: string | null;
  /** Pinned sha256 over that projection (verified before any row renders), or null. */
  projection_content_hash: string | null;
}

/** The Stage-1 release/selection identity the downstream results descend from (fail closed on drift). */
export interface Stage1Binding {
  release_method_version: string; // e.g. stage1-continuous-v3.0.1
  registry_scorer_view_sha256: string; // ties to the v3 selection's registry_scorer_view_sha256
  // Release-level identity of the exact Stage-1 v3 contract these results descend from. The loader
  // pins the UI's own build (STAGE1_* in stage1/contractBinding) and refuses a served release whose
  // identity differs — a deployed UI resolves downstream results only for the release it was built on.
  selection_schema_raw_sha256: string; // == release components.selection_schema_v3.raw_sha256
  release_self_sha256: string; // == release self_release_sha256
}

/**
 * The admitted cross-stage chain the results descend from: Stage-1 selection → Stage-2 run → Stage-3
 * bundle → Stage-4 scorecard set. Each route binds only if its projection's upstream ids match this
 * chain EXACTLY — an admitted receipt for run A packaged over data from run B is refused.
 */
export interface ResultChain {
  stage2_run_id: string; // the admitted Stage-2 run id every downstream result descends from
  stage3_bundle_id: string | null; // the admitted Stage-3 bundle id (Drugs), or null until bound
  stage4_scorecard_set_id: string | null; // the admitted Stage-4 scorecard-set id (PK & Safety), or null
}

// results/current.json is SELECTION-INDEPENDENT — it carries only native release ids/hashes so ONE
// admitted release resolves ARBITRARY within/temporal dropdown choices without regeneration. It has NO
// top-level selection or analysis_mode. The active v3 selection is re-derived at runtime
// (selectionIdentity) and used to select release slots + (per W6/W3 contracts) filter Stage-3/4.
export interface UiResultsCurrent {
  schema: typeof UI_RESULTS_CURRENT_SCHEMA;
  stage1_binding: Stage1Binding;
  chain: ResultChain;
  /** A route absent here is UNBOUND (allowed); a present route must carry a complete entry. */
  routes: Partial<Record<ResultRouteKey, RouteReleaseEntry>>;
}

/** Map a downstream page key to its result-route key (Programs has no downstream results). */
export function resultRouteKeyForPage(page: string): ResultRouteKey | null {
  return (RESULT_ROUTE_KEYS as readonly string[]).includes(page) ? (page as ResultRouteKey) : null;
}
