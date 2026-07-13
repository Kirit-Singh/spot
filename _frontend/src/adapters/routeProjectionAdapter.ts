// Strict, FAIL-CLOSED adapters for the compact browser ROUTE PROJECTIONS — the same-origin,
// content-addressed `.ui.json` files the loader fetches to render a route's canvas. This is the
// STABLE browser-facing schema (spot.ui_projection.{stage2,drugs,pksafety}.v1) that the offline
// packager emits from the moving native producer artifacts; the browser never parses native fields.
//
// Every projection is rejected unless its schema_version + route match the code-bound route and every
// field has the exact shape below. A fixture/demo-shaped artifact (namespace != production, or an id
// prefixed fixture:/demo:) is refused. Stage-2 arm bundles are delegated to the existing production
// adapters, which already enforce the namespace firewall.

import type { ResolvedBundles } from '../repository/joinResolver';
import type { SelectionV3 } from './selectionV3Adapter';
import type { Stage3Candidate, Stage3UiArtifact } from '../domain/stage3UiArtifact';
import { STAGE3_NATIVE_ARTIFACT_SCHEMA, STAGE3_UI_ARTIFACT_SCHEMA } from '../domain/stage3UiArtifact';
import type { JsonObject, JsonValue, Stage4Candidate, Stage4Lanes, Stage4ProductionEligibility, Stage4UiArtifact } from '../domain/stage4UiArtifact';
import { STAGE4_LANE_KEYS, STAGE4_UI_ARTIFACT_SCHEMA } from '../domain/stage4UiArtifact';
import { parseNativeTemporalArmBundle } from './nativeTemporalArmAdapter';
import { parseDirectArmBundle, parsePathwayArmBundle } from './reusableArmAdapter';
import type { PathwayArmBundle } from '../domain/reusableArm';
import { fail } from './errors';
import { arr, bool, isObject, optBool, optNum, optStr, str } from './guards';

export const UI_PROJECTION_SCHEMA = {
  stage2: 'spot.ui_projection.stage2.v1',
  drugs: 'spot.ui_projection.drugs.v1',
  pksafety: 'spot.ui_projection.pksafety.v1',
} as const;

const PROD: 'production' = 'production';

/** A required string that must NOT be a fixture/demo-namespaced id. */
function prodId(v: unknown, path: string): string {
  const s = str(v, path);
  if (/^(fixture|demo|research_only):/i.test(s)) fail('namespace_mismatch', `${path} "${s}" is a non-production (fixture/demo) id`);
  return s;
}
function strList(v: unknown, path: string): string[] {
  return arr(v, path).map((x, i) => str(x, `${path}[${i}]`));
}
/** A projection must not smuggle a non-production namespace marker. */
function assertProductionEnvelope(raw: Record<string, unknown>): void {
  if ('namespace' in raw && raw.namespace !== PROD) {
    fail('namespace_mismatch', `projection namespace "${String(raw.namespace)}" is not production`);
  }
}

// ── Stage-2 (Targets / Pathways) — the COMPLETE generic release ────────────────
// The projection carries the WHOLE release: one Direct bundle per condition, one temporal bundle per
// ORDERED condition pair, and one pathway bundle per (condition, source). Completeness (every expected
// slot present) is validated up-front; the requested programs/conditions are selected at JOIN time from
// this complete set. Individual bundles are parsed LAZILY (only the selected slot) via resolveStage2Bundles
// — so a missing slot FAILS completeness here and never silently renders empty.
export interface Stage2Projection {
  run_id: string; // the admitted Stage-2 run id (must match results/current.json chain.stage2_run_id)
  // NO top-level analysis_mode: the all-arm release serves BOTH within_condition and temporal selections;
  // the active v3 selection decides the mode at join time (resolveStage2Bundles).
  release_conditions: string[]; // the release's condition axis (e.g. Rest / Stim8hr / Stim48hr)
  pathway_sources: string[]; // the release's pathway sources (e.g. reactome / go_bp)
  pathway_source: string; // the active source for the view (∈ pathway_sources)
  directByCondition: Record<string, unknown>; // raw per-condition Direct bundles (parsed lazily)
  temporalByPair: Record<string, unknown>; // raw per ORDERED "<from>__<to>" temporal bundles
  pathwayByContext: Record<string, unknown>; // raw per "<condition>|<source>" pathway bundles
}

/** Expected slot keys for a complete release, derived from the condition axis + pathway sources. */
export function expectedStage2Slots(conditions: string[], sources: string[]) {
  const pairs: string[] = [];
  for (const from of conditions) for (const to of conditions) if (from !== to) pairs.push(`${from}__${to}`);
  const pathways: string[] = [];
  for (const c of conditions) for (const s of sources) pathways.push(`${c}|${s}`);
  return { direct: [...conditions], temporal: pairs, pathway: pathways };
}

function rawMap(v: unknown, path: string): Record<string, unknown> {
  if (!isObject(v)) fail('malformed', `${path} must be an object`);
  return v;
}
function requireSlots(map: Record<string, unknown>, keys: string[], path: string): void {
  for (const k of keys) {
    if (!(k in map) || !isObject(map[k])) fail('incomplete_release', `${path} is missing the "${k}" slot — the release is not complete (never render empty)`);
  }
}

/**
 * Parse + COMPLETENESS-validate the compact Stage-2 projection. Every expected Direct / temporal /
 * pathway slot must be present; a missing slot fails `incomplete_release`. Bundles are stored raw and
 * parsed lazily by resolveStage2Bundles at selection time (namespace-firewalled to production).
 */
export function parseStage2Projection(raw: unknown): Stage2Projection {
  if (!isObject(raw)) fail('malformed', 'stage-2 projection must be an object');
  if (str(raw.schema_version, 'schema_version') !== UI_PROJECTION_SCHEMA.stage2) {
    fail('unknown_schema_version', `expected ${UI_PROJECTION_SCHEMA.stage2}`);
  }
  assertProductionEnvelope(raw);
  const route = str(raw.route, 'route');
  if (route !== 'targets' && route !== 'pathways') fail('malformed', `stage-2 projection route "${route}" must be targets|pathways`);

  const run_id = prodId(raw.run_id, 'run_id');
  const release_conditions = strList(raw.release_conditions, 'release_conditions');
  const pathway_sources = strList(raw.pathway_sources, 'pathway_sources');
  if (release_conditions.length === 0 || pathway_sources.length === 0) fail('malformed', 'release_conditions + pathway_sources required');
  const pathway_source = str(raw.pathway_source, 'pathway_source');
  if (!pathway_sources.includes(pathway_source)) fail('malformed', `pathway_source "${pathway_source}" not in pathway_sources`);

  const directByCondition = rawMap(raw.directByCondition, 'directByCondition');
  const temporalByPair = rawMap(raw.temporalByPair, 'temporalByPair');
  const pathwayByContext = rawMap(raw.pathwayByContext, 'pathwayByContext');

  const slots = expectedStage2Slots(release_conditions, pathway_sources);
  requireSlots(directByCondition, slots.direct, 'directByCondition');
  requireSlots(temporalByPair, slots.temporal, 'temporalByPair');
  requireSlots(pathwayByContext, slots.pathway, 'pathwayByContext');

  return { run_id, release_conditions, pathway_sources, pathway_source, directByCondition, temporalByPair, pathwayByContext };
}

/**
 * Select the requested slice of the complete release for a selection + parse ONLY those bundles
 * (production-firewalled). within_condition → the condition's Direct bundle; temporal → the ordered
 * "<from>__<to>" temporal bundle. Pathway contexts for the selected condition(s) at the active source
 * are parsed too. Returns null if the requested slot is absent (refuse, never render empty).
 */
export function resolveStage2Bundles(proj: Stage2Projection, selection: SelectionV3): ResolvedBundles | null {
  const src = proj.pathway_source;
  const conds = selection.analysis_mode === 'within_condition'
    ? [selection.conditions[0]]
    : [selection.conditions[0], selection.conditions[1]];
  const pathwayByContext: Record<string, PathwayArmBundle> = {};
  for (const c of conds) {
    const rawPw = proj.pathwayByContext[`${c}|${src}`];
    if (rawPw == null) return null;
    pathwayByContext[`${c}|${src}`] = parsePathwayArmBundle(rawPw, PROD);
  }
  if (selection.analysis_mode === 'within_condition') {
    const rawDirect = proj.directByCondition[selection.conditions[0]];
    if (rawDirect == null) return null;
    return { direct: parseDirectArmBundle(rawDirect, PROD), pathwayByContext };
  }
  const rawTemporal = proj.temporalByPair[`${selection.conditions[0]}__${selection.conditions[1]}`];
  if (rawTemporal == null) return null;
  return { temporal: parseNativeTemporalArmBundle(rawTemporal, PROD), pathwayByContext };
}

// ── Stage-3 (Drugs) ───────────────────────────────────────────────────────────
function parseStage3Candidate(v: unknown, path: string): Stage3Candidate {
  if (!isObject(v)) fail('malformed', `${path} must be an object`);
  return {
    candidate_id: prodId(v.candidate_id, `${path}.candidate_id`),
    active_moiety_id: optStr(v.active_moiety_id, `${path}.active_moiety_id`),
    preferred_name: optStr(v.preferred_name, `${path}.preferred_name`),
    identity_status: optStr(v.identity_status, `${path}.identity_status`),
    molecule_chembl_ids: strList(v.molecule_chembl_ids, `${path}.molecule_chembl_ids`),
    target_ensembls: strList(v.target_ensembls, `${path}.target_ensembls`),
    n_edges: optNum(v.n_edges, `${path}.n_edges`),
    n_direct_gene_edges: optNum(v.n_direct_gene_edges, `${path}.n_direct_gene_edges`),
    max_phase_status: optStr(v.max_phase_status, `${path}.max_phase_status`),
    max_phase_sources: strList(v.max_phase_sources, `${path}.max_phase_sources`),
    observed_perturbation_arms: strList(v.observed_perturbation_arms, `${path}.observed_perturbation_arms`),
    observed_perturbation_support: bool(v.observed_perturbation_support, `${path}.observed_perturbation_support`),
    mechanism_match_statuses: strList(v.mechanism_match_statuses, `${path}.mechanism_match_statuses`),
    pathway_hypothesis_arms: strList(v.pathway_hypothesis_arms, `${path}.pathway_hypothesis_arms`),
    stage3_evidence_classes: strList(v.stage3_evidence_classes, `${path}.stage3_evidence_classes`),
    stage4_assessment_status: optStr(v.stage4_assessment_status, `${path}.stage4_assessment_status`),
    stage4_assessment_reason: optStr(v.stage4_assessment_reason, `${path}.stage4_assessment_reason`),
    source_record_ids: strList(v.source_record_ids, `${path}.source_record_ids`),
  };
}

/** Parse the compact Drugs (Stage-3) projection → Stage3UiArtifact. */
export function parseDrugsProjection(raw: unknown): Stage3UiArtifact {
  if (!isObject(raw)) fail('malformed', 'drugs projection must be an object');
  if (str(raw.schema_version, 'schema_version') !== UI_PROJECTION_SCHEMA.drugs) {
    fail('unknown_schema_version', `expected ${UI_PROJECTION_SCHEMA.drugs}`);
  }
  assertProductionEnvelope(raw);
  if (str(raw.route, 'route') !== 'drugs') fail('malformed', 'drugs projection route must be drugs');
  const a = raw.artifact;
  if (!isObject(a)) fail('malformed', 'drugs projection.artifact must be an object');
  if (str(a.schema_version, 'artifact.schema_version') !== STAGE3_UI_ARTIFACT_SCHEMA) {
    fail('unknown_schema_version', `artifact.schema_version must be ${STAGE3_UI_ARTIFACT_SCHEMA}`);
  }
  return {
    schema_version: STAGE3_UI_ARTIFACT_SCHEMA,
    native_schema_version: str(a.native_schema_version, 'artifact.native_schema_version') === STAGE3_NATIVE_ARTIFACT_SCHEMA
      ? STAGE3_NATIVE_ARTIFACT_SCHEMA
      : fail('unknown_schema_version', `artifact.native_schema_version must be ${STAGE3_NATIVE_ARTIFACT_SCHEMA}`),
    artifact_class: str(a.artifact_class, 'artifact.artifact_class') === 'analysis'
      ? 'analysis'
      : fail('namespace_mismatch', 'artifact.artifact_class must be analysis'),
    bundle_id: prodId(a.bundle_id, 'artifact.bundle_id'),
    canonical_content_sha256: str(a.canonical_content_sha256, 'artifact.canonical_content_sha256'),
    upstream_stage2_run: prodId(a.upstream_stage2_run, 'artifact.upstream_stage2_run'),
    candidates: arr(a.candidates, 'artifact.candidates').map((c, i) => parseStage3Candidate(c, `artifact.candidates[${i}]`)),
  };
}

// ── Stage-4 (PK & Safety) ──────────────────────────────────────────────────────
// Stage 4's browser projection is already the intended browser-safe document.  Its nested objects
// carry missingness/provenance semantics, so this adapter validates JSON shape and preserves them
// rather than flattening a lane to a string.
function jsonValue(v: unknown, path: string): JsonValue {
  if (v === null || typeof v === 'string' || typeof v === 'boolean') return v;
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) fail('malformed', `${path} must be finite JSON`);
    return v;
  }
  if (Array.isArray(v)) return v.map((x, i) => jsonValue(x, `${path}[${i}]`));
  if (isObject(v)) {
    const out: JsonObject = {};
    for (const [key, child] of Object.entries(v)) out[key] = jsonValue(child, `${path}.${key}`);
    return out;
  }
  fail('malformed', `${path} must be JSON`);
}
function jsonObject(v: unknown, path: string): JsonObject {
  if (!isObject(v)) fail('malformed', `${path} must be an object`);
  return jsonValue(v, path) as JsonObject;
}
function parseStage4Lanes(v: unknown, path: string): Stage4Lanes {
  const raw = jsonObject(v, path);
  const lanes = {} as Stage4Lanes;
  for (const lane of STAGE4_LANE_KEYS) {
    if (!(lane in raw)) fail('malformed', `${path}.${lane} is required`);
    lanes[lane] = raw[lane];
  }
  return lanes;
}
function parseProductionEligibility(v: unknown, path: string): Stage4ProductionEligibility {
  const raw = jsonObject(v, path);
  if (typeof raw.eligible !== 'boolean') fail('malformed', `${path}.eligible must be boolean`);
  if (raw.reason_code !== null && typeof raw.reason_code !== 'string') {
    fail('malformed', `${path}.reason_code must be string or null`);
  }
  return raw as Stage4ProductionEligibility;
}
function parseStage4Candidate(v: unknown, path: string): Stage4Candidate {
  if (!isObject(v)) fail('malformed', `${path} must be an object`);
  const active = v.active_moiety === null ? null : jsonObject(v.active_moiety, `${path}.active_moiety`);
  return {
    candidate_id: prodId(v.candidate_id, `${path}.candidate_id`),
    active_moiety: active,
    compound_ids: jsonObject(v.compound_ids, `${path}.compound_ids`),
    target: optStr(v.target, `${path}.target`),
    mechanism: optStr(v.mechanism, `${path}.mechanism`),
    direction_compatibility: optStr(v.direction_compatibility, `${path}.direction_compatibility`),
    production_eligible: parseProductionEligibility(v.production_eligible, `${path}.production_eligible`),
    lanes: parseStage4Lanes(v.lanes, `${path}.lanes`),
    provenance_chain: arr(v.provenance_chain, `${path}.provenance_chain`).map((x, i) => jsonValue(x, `${path}.provenance_chain[${i}]`)),
    stage3_arm_membership: jsonObject(v.stage3_arm_membership, `${path}.stage3_arm_membership`),
    in_active_view: optBool(v.in_active_view, `${path}.in_active_view`),
  };
}

/** Parse the compact PK & Safety (Stage-4) projection → Stage4UiArtifact. */
export function parsePkSafetyProjection(raw: unknown): Stage4UiArtifact {
  if (!isObject(raw)) fail('malformed', 'pksafety projection must be an object');
  if (str(raw.schema_version, 'schema_version') !== UI_PROJECTION_SCHEMA.pksafety) {
    fail('unknown_schema_version', `expected ${UI_PROJECTION_SCHEMA.pksafety}`);
  }
  assertProductionEnvelope(raw);
  if (str(raw.route, 'route') !== 'pksafety') fail('malformed', 'pksafety projection route must be pksafety');
  const a = raw.artifact;
  if (!isObject(a)) fail('malformed', 'pksafety projection.artifact must be an object');
  if (str(a.schema_version, 'artifact.schema_version') !== STAGE4_UI_ARTIFACT_SCHEMA) fail('unknown_schema_version', `artifact.schema_version must be ${STAGE4_UI_ARTIFACT_SCHEMA}`);
  const upstream = jsonObject(a.upstream, 'artifact.upstream');
  if (upstream.namespace !== 'production' || upstream.is_fixture !== false) {
    fail('namespace_mismatch', 'artifact.upstream must be admitted production and not a fixture');
  }
  const upstreamBundle = prodId(upstream.candidate_set_id, 'artifact.upstream.candidate_set_id');
  if (a.store_is_selection_independent !== true || a.is_ranking !== false) {
    fail('malformed', 'Stage-4 projection must be a selection-independent, non-ranking store');
  }
  const activeSelection = a.active_selection_view === undefined || a.active_selection_view === null
    ? null : jsonObject(a.active_selection_view, 'artifact.active_selection_view');
  return {
    schema_version: STAGE4_UI_ARTIFACT_SCHEMA,
    scorecard_set_id: prodId(a.scorecard_set_id, 'artifact.scorecard_set_id'),
    upstream_stage3_bundle: upstreamBundle,
    upstream,
    store_is_selection_independent: true,
    is_ranking: false,
    ordering: jsonValue(a.ordering, 'artifact.ordering'),
    guards: jsonValue(a.guards, 'artifact.guards'),
    active_selection_view: activeSelection,
    active_view_candidate_ids: a.active_view_candidate_ids === undefined ? [] : strList(a.active_view_candidate_ids, 'artifact.active_view_candidate_ids'),
    candidates: arr(a.candidates, 'artifact.candidates').map((c, i) => parseStage4Candidate(c, `artifact.candidates[${i}]`)),
  };
}
