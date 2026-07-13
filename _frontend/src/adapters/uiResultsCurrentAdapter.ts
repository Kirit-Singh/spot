// Fail-closed adapter for results/current.json (spot.ui_results_current.v1). The browser fetches this
// pointer FIRST and trusts nothing it names until it parses here. A rejection (thrown AdapterError) or
// an absent file leaves every route unbound — never a partial or fabricated binding.
//
// This validates only the pointer's SHAPE + Stage-1 binding + per-route release entries. The route's
// ui_release manifest and native projection are each independently content-verified downstream
// (parseUiReleaseManifest / the projection loader) against the hashes this pointer pins.

import type { CompactStage2ReleaseMetadata } from '../domain/compactStage2Projection';
import { P2S_RELEASE_SCHEMA, type P2sSecondaryReleaseMetadata } from '../p2s/types';
import { COMPACT_STAGE2_VERIFIER } from '../domain/compactStage2Projection';
import type { ResultChain, RouteReleaseEntry, Stage1Binding, UiResultsCurrent, ResultRouteKey } from '../domain/uiResultsCurrent';
import { RESULT_ROUTE_KEYS, UI_RESULTS_CURRENT_SCHEMA } from '../domain/uiResultsCurrent';
import { fail } from './errors';
import { arr, isObject, optStr, str } from './guards';

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

function relativePath(v: unknown, path: string): string {
  const s = reqStr(v, path);
  if (s.startsWith('/') || s.includes('..') || s.includes('://') || /[?#]/.test(s)) {
    fail('malformed', `${path} must be a same-origin relative path`);
  }
  return s;
}

function exactStrings(v: unknown, expected: readonly string[], path: string): string[] {
  const got = arr(v, path).map((x, i) => str(x, `${path}[${i}]`));
  if (got.length !== expected.length || got.some((x, i) => x !== expected[i])) {
    fail('malformed', `${path} must be exactly [${expected.join(', ')}]`);
  }
  return got;
}

function exactKeys(v: Record<string, unknown>, expected: readonly string[], path: string): void {
  const got = Object.keys(v).sort();
  const want = [...expected].sort();
  if (got.length !== want.length || got.some((key, i) => key !== want[i])) {
    fail('malformed', `${path} fields [${got.join(', ')}] do not equal [${want.join(', ')}]`);
  }
}

function compactStage2Metadata(v: unknown, path: string): CompactStage2ReleaseMetadata {
  if (!isObject(v)) fail('malformed', `${path} must be an object`);
  exactKeys(v, ['active_pathway_source', 'independent_verifier', 'pathway_sources',
    'projection_canonical_sha256', 'projection_raw_sha256', 'projection_self_sha256',
    'release_conditions', 'display_release_id', 'schema_version'], path);
  if (str(v.schema_version, `${path}.schema_version`) !== 'spot.ui_compact_stage2_release.v1') {
    fail('unknown_schema_version', `${path}.schema_version must be spot.ui_compact_stage2_release.v1`);
  }
  const conditions = exactStrings(v.release_conditions, ['Rest', 'Stim8hr', 'Stim48hr'], `${path}.release_conditions`);
  const sources = exactStrings(v.pathway_sources, ['reactome', 'go_bp'], `${path}.pathway_sources`);
  const active = str(v.active_pathway_source, `${path}.active_pathway_source`);
  if (!sources.includes(active)) fail('malformed', `${path}.active_pathway_source is not in pathway_sources`);
  if (!isObject(v.independent_verifier)) fail('malformed', `${path}.independent_verifier must be an object`);
  const verifier = v.independent_verifier;
  exactKeys(verifier, ['receipt_canonical_sha256', 'receipt_path', 'receipt_raw_sha256',
    'verifier_id'], `${path}.independent_verifier`);
  const verifierId = str(verifier.verifier_id, `${path}.independent_verifier.verifier_id`);
  if (verifierId !== COMPACT_STAGE2_VERIFIER) {
    fail('verifier_not_admitted', `${path}.independent_verifier.verifier_id is not the compact-display verifier`);
  }
  return {
    schema_version: 'spot.ui_compact_stage2_release.v1',
    display_release_id: reqStr(v.display_release_id, `${path}.display_release_id`),
    release_conditions: conditions as CompactStage2ReleaseMetadata['release_conditions'],
    pathway_sources: sources as CompactStage2ReleaseMetadata['pathway_sources'],
    active_pathway_source: active as CompactStage2ReleaseMetadata['active_pathway_source'],
    projection_raw_sha256: hex64(v.projection_raw_sha256, `${path}.projection_raw_sha256`),
    projection_canonical_sha256: hex64(v.projection_canonical_sha256, `${path}.projection_canonical_sha256`),
    projection_self_sha256: hex64(v.projection_self_sha256, `${path}.projection_self_sha256`),
    independent_verifier: {
      verifier_id: COMPACT_STAGE2_VERIFIER,
      receipt_path: relativePath(verifier.receipt_path, `${path}.independent_verifier.receipt_path`),
      receipt_raw_sha256: hex64(verifier.receipt_raw_sha256, `${path}.independent_verifier.receipt_raw_sha256`),
      receipt_canonical_sha256: hex64(verifier.receipt_canonical_sha256, `${path}.independent_verifier.receipt_canonical_sha256`),
    },
  };
}

function p2sSecondaryMetadata(v: unknown, path: string): P2sSecondaryReleaseMetadata {
  if (!isObject(v)) fail('malformed', `${path} must be an object`);
  exactKeys(v, ['arm_key', 'p2s_run_sha256', 'projection_canonical_sha256', 'projection_path',
    'projection_raw_sha256', 'projection_rows_sha256', 'receipt_sha256', 'schema_version',
    'sibling_arm_key', 'source_bundle', 'verification_canonical_sha256', 'verification_path',
    'verification_raw_sha256', 'verification_self_sha256'], path);
  if (str(v.schema_version, `${path}.schema_version`) !== P2S_RELEASE_SCHEMA) {
    fail('unknown_schema_version', `${path}.schema_version must be ${P2S_RELEASE_SCHEMA}`);
  }
  const arm = reqStr(v.arm_key, `${path}.arm_key`);
  const sibling = reqStr(v.sibling_arm_key, `${path}.sibling_arm_key`);
  if (!arm.startsWith('direct|') || !sibling.startsWith('direct|') || arm === sibling) {
    fail('malformed', `${path} must bind two distinct Direct arms`);
  }
  return {
    schema_version: P2S_RELEASE_SCHEMA,
    projection_path: relativePath(v.projection_path, `${path}.projection_path`),
    projection_raw_sha256: hex64(v.projection_raw_sha256, `${path}.projection_raw_sha256`),
    projection_canonical_sha256: hex64(v.projection_canonical_sha256, `${path}.projection_canonical_sha256`),
    projection_rows_sha256: hex64(v.projection_rows_sha256, `${path}.projection_rows_sha256`),
    verification_path: relativePath(v.verification_path, `${path}.verification_path`),
    verification_raw_sha256: hex64(v.verification_raw_sha256, `${path}.verification_raw_sha256`),
    verification_canonical_sha256: hex64(v.verification_canonical_sha256, `${path}.verification_canonical_sha256`),
    verification_self_sha256: hex64(v.verification_self_sha256, `${path}.verification_self_sha256`),
    receipt_sha256: hex64(v.receipt_sha256, `${path}.receipt_sha256`),
    p2s_run_sha256: hex64(v.p2s_run_sha256, `${path}.p2s_run_sha256`),
    arm_key: arm,
    sibling_arm_key: sibling,
    source_bundle: reqStr(v.source_bundle, `${path}.source_bundle`),
  };
}

function routeEntry(v: unknown, path: string, route: ResultRouteKey, chain: ResultChain): RouteReleaseEntry {
  if (!isObject(v)) fail('malformed', `${path} must be an object`);
  const projection_path = optStr(v.projection_path, `${path}.projection_path`);
  const projection_content_hash = optHex64(v.projection_content_hash, `${path}.projection_content_hash`);
  // A projection is either fully bound (path + hash) or fully absent — never half-bound.
  if ((projection_path === null) !== (projection_content_hash === null)) {
    fail('malformed', `${path}.projection_path and projection_content_hash must both be present or both absent`);
  }
  const stage2Route = route === 'targets' || route === 'pathways';
  const compact_stage2 = v.compact_stage2 == null ? null : compactStage2Metadata(v.compact_stage2, `${path}.compact_stage2`);
  const p2s_secondary = v.p2s_secondary == null ? null : p2sSecondaryMetadata(v.p2s_secondary, `${path}.p2s_secondary`);
  if (stage2Route && projection_path !== null && compact_stage2 === null) {
    fail('malformed', `${path}.compact_stage2 is required for a bound compact Stage-2 route`);
  }
  if (!stage2Route && compact_stage2 !== null) {
    fail('malformed', `${path}.compact_stage2 is only valid on targets/pathways routes`);
  }
  if (p2s_secondary !== null && route !== 'targets') {
    fail('malformed', `${path}.p2s_secondary is only valid on the targets route`);
  }
  if (p2s_secondary !== null && compact_stage2 === null) {
    fail('malformed', `${path}.p2s_secondary requires the admitted compact Stage-2 release`);
  }
  if (compact_stage2) {
    if (compact_stage2.display_release_id !== chain.stage2_display_release_id) {
      fail('content_hash_mismatch', `${path}.compact_stage2.display_release_id does not match chain.stage2_display_release_id`);
    }
    if (compact_stage2.projection_canonical_sha256 !== projection_content_hash) {
      fail('content_hash_mismatch', `${path}.compact_stage2 projection canonical hash does not match projection_content_hash`);
    }
  }
  return {
    manifest_path: reqStr(v.manifest_path, `${path}.manifest_path`),
    content_hash: hex64(v.content_hash, `${path}.content_hash`),
    projection_path,
    projection_content_hash,
    compact_stage2,
    p2s_secondary,
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
    stage2_display_release_id: reqStr(v.stage2_display_release_id, `${path}.stage2_display_release_id`),
    stage2_run_id: optStr(v.stage2_run_id, `${path}.stage2_run_id`),
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
    const route = key as ResultRouteKey;
    routes[route] = routeEntry(routesRaw[key], `routes.${key}`, route, chain);
  }
  const targetMeta = routes.targets?.compact_stage2;
  const pathwayMeta = routes.pathways?.compact_stage2;
  if (targetMeta && pathwayMeta && JSON.stringify(targetMeta) !== JSON.stringify(pathwayMeta)) {
    fail('content_hash_mismatch', 'targets/pathways compact Stage-2 release metadata disagree');
  }

  return { schema: UI_RESULTS_CURRENT_SCHEMA, stage1_binding, chain, routes };
}
