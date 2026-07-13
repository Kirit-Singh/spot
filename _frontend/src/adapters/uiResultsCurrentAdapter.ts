// Fail-closed adapter for results/current.json (spot.ui_results_current.v1). The browser fetches this
// pointer FIRST and trusts nothing it names until it parses here. A rejection (thrown AdapterError) or
// an absent file leaves every route unbound — never a partial or fabricated binding.
//
// This validates only the pointer's SHAPE + Stage-1 binding + per-route release entries. The route's
// ui_release manifest and native projection are each independently content-verified downstream
// (parseUiReleaseManifest / the projection loader) against the hashes this pointer pins.

import type { ResultChain, RouteReleaseEntry, Stage1Binding, UiResultsCurrent, ResultRouteKey } from '../domain/uiResultsCurrent';
import { RESULT_ROUTE_KEYS, UI_RESULTS_CURRENT_SCHEMA } from '../domain/uiResultsCurrent';
import { fail } from './errors';
import { isObject, optStr, str } from './guards';

const HEX64 = /^[0-9a-f]{64}$/;

function reqStr(v: unknown, path: string): string {
  const s = str(v, path);
  if (s.trim() === '') fail('malformed', `${path} is empty`);
  return s;
}
function hex64(v: unknown, path: string): string {
  const s = str(v, path);
  if (!HEX64.test(s)) fail('missing_hash', `${path} must be a 64-hex sha256`);
  return s;
}
function optHex64(v: unknown, path: string): string | null {
  if (v === null || v === undefined) return null;
  return hex64(v, path);
}

function routeEntry(v: unknown, path: string): RouteReleaseEntry {
  if (!isObject(v)) fail('malformed', `${path} must be an object`);
  const projection_path = optStr(v.projection_path, `${path}.projection_path`);
  const projection_content_hash = optHex64(v.projection_content_hash, `${path}.projection_content_hash`);
  // A projection is either fully bound (path + hash) or fully absent — never half-bound.
  if ((projection_path === null) !== (projection_content_hash === null)) {
    fail('malformed', `${path}.projection_path and projection_content_hash must both be present or both absent`);
  }
  return {
    manifest_path: reqStr(v.manifest_path, `${path}.manifest_path`),
    content_hash: hex64(v.content_hash, `${path}.content_hash`),
    projection_path,
    projection_content_hash,
  };
}

function stage1Binding(v: unknown, path: string): Stage1Binding {
  if (!isObject(v)) fail('malformed', `${path} must be an object`);
  return {
    release_method_version: reqStr(v.release_method_version, `${path}.release_method_version`),
    registry_scorer_view_sha256: hex64(v.registry_scorer_view_sha256, `${path}.registry_scorer_view_sha256`),
    // Shape only here (both must be 64-hex); the loader enforces they EQUAL the UI's pinned release.
    selection_schema_raw_sha256: hex64(v.selection_schema_raw_sha256, `${path}.selection_schema_raw_sha256`),
    release_self_sha256: hex64(v.release_self_sha256, `${path}.release_self_sha256`),
  };
}

function resultChain(v: unknown, path: string): ResultChain {
  if (!isObject(v)) fail('malformed', `${path} must be an object`);
  return {
    stage2_run_id: reqStr(v.stage2_run_id, `${path}.stage2_run_id`),
    stage3_bundle_id: optStr(v.stage3_bundle_id, `${path}.stage3_bundle_id`),
    stage4_scorecard_set_id: optStr(v.stage4_scorecard_set_id, `${path}.stage4_scorecard_set_id`),
  };
}

/** Parse + fully validate results/current.json, FAIL-CLOSED. Throws AdapterError on any violation. */
export function parseUiResultsCurrent(raw: unknown): UiResultsCurrent {
  if (!isObject(raw)) fail('malformed', 'results/current.json must be an object');

  if (str(raw.schema, 'schema') !== UI_RESULTS_CURRENT_SCHEMA) {
    fail('unknown_schema_version', `expected ${UI_RESULTS_CURRENT_SCHEMA}`);
  }

  const stage1_binding = stage1Binding(raw.stage1_binding, 'stage1_binding');
  const chain = resultChain(raw.chain, 'chain');

  if (!isObject(raw.routes)) fail('malformed', 'routes must be an object');
  const routesRaw = raw.routes;
  const routes: Partial<Record<ResultRouteKey, RouteReleaseEntry>> = {};
  for (const key of Object.keys(routesRaw)) {
    if (!(RESULT_ROUTE_KEYS as readonly string[]).includes(key)) {
      fail('malformed', `routes has an unknown route key "${key}"`);
    }
    routes[key as ResultRouteKey] = routeEntry(routesRaw[key], `routes.${key}`);
  }

  return { schema: UI_RESULTS_CURRENT_SCHEMA, stage1_binding, chain, routes };
}
