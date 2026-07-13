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
import type { Stage3Candidate, Stage3UiArtifact } from '../domain/stage3UiArtifact';
import { STAGE3_UI_ARTIFACT_SCHEMA } from '../domain/stage3UiArtifact';
import type { Stage4Candidate, Stage4Lanes, Stage4UiArtifact } from '../domain/stage4UiArtifact';
import { STAGE4_LANE_KEYS, STAGE4_UI_ARTIFACT_SCHEMA } from '../domain/stage4UiArtifact';
import { parseNativeTemporalArmBundle } from './nativeTemporalArmAdapter';
import { parseDirectArmBundle, parsePathwayArmBundle } from './reusableArmAdapter';
import type { PathwayArmBundle } from '../domain/reusableArm';
import { fail } from './errors';
import { arr, isObject, optBool, optNum, optStr, str } from './guards';

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

// ── Stage-2 (Targets / Pathways) ──────────────────────────────────────────────
export interface Stage2Projection {
  run_id: string; // the admitted Stage-2 run id (must match results/current.json chain.stage2_run_id)
  analysis_mode: 'within_condition' | 'temporal_cross_condition';
  pathway_source: string;
  release_conditions: string[];
  bundles: ResolvedBundles;
}

/**
 * Parse the compact Stage-2 projection. Arm bundles are delegated to the production adapters
 * (namespace-firewalled). The loader resolves the JoinedView from these bundles + the stored selection.
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
  const analysis_mode = str(raw.analysis_mode, 'analysis_mode');
  if (analysis_mode !== 'within_condition' && analysis_mode !== 'temporal_cross_condition') {
    fail('malformed', `analysis_mode "${analysis_mode}" invalid`);
  }
  const pathway_source = str(raw.pathway_source, 'pathway_source');
  const release_conditions = strList(raw.release_conditions, 'release_conditions');

  const direct = raw.direct == null ? null : parseDirectArmBundle(raw.direct, PROD);
  const temporal = raw.temporal == null ? null : parseNativeTemporalArmBundle(raw.temporal, PROD);
  const pathwayByContext: Record<string, PathwayArmBundle | null> = {};
  if (raw.pathwayByContext != null) {
    if (!isObject(raw.pathwayByContext)) fail('malformed', 'pathwayByContext must be an object');
    for (const key of Object.keys(raw.pathwayByContext)) {
      const b = raw.pathwayByContext[key];
      pathwayByContext[key] = b == null ? null : parsePathwayArmBundle(b, PROD);
    }
  }
  return { run_id, analysis_mode, pathway_source, release_conditions, bundles: { direct, temporal, pathwayByContext } };
}

// ── Stage-3 (Drugs) ───────────────────────────────────────────────────────────
function parseStage3Candidate(v: unknown, path: string): Stage3Candidate {
  if (!isObject(v)) fail('malformed', `${path} must be an object`);
  return {
    candidate_id: prodId(v.candidate_id, `${path}.candidate_id`),
    active_moiety_id: optStr(v.active_moiety_id, `${path}.active_moiety_id`),
    preferred_name: optStr(v.preferred_name, `${path}.preferred_name`),
    identity_status: optStr(v.identity_status, `${path}.identity_status`),
    form_ids: strList(v.form_ids, `${path}.form_ids`),
    target_ensembls: strList(v.target_ensembls, `${path}.target_ensembls`),
    n_edges: optNum(v.n_edges, `${path}.n_edges`),
    n_direct_gene_edges: optNum(v.n_direct_gene_edges, `${path}.n_direct_gene_edges`),
    development_state_aggregate: optStr(v.development_state_aggregate, `${path}.development_state_aggregate`),
    n_potency_rows: optNum(v.n_potency_rows, `${path}.n_potency_rows`),
    potency_state: optStr(v.potency_state, `${path}.potency_state`),
    observed_perturbation_arms: strList(v.observed_perturbation_arms, `${path}.observed_perturbation_arms`),
    inverse_direction_support: optStr(v.inverse_direction_support, `${path}.inverse_direction_support`),
    pathway_hypothesis_arms: strList(v.pathway_hypothesis_arms, `${path}.pathway_hypothesis_arms`),
    stage3_evidence_classes: strList(v.stage3_evidence_classes, `${path}.stage3_evidence_classes`),
    disease_context_review_status: optStr(v.disease_context_review_status, `${path}.disease_context_review_status`),
    disease_context_review_result: optStr(v.disease_context_review_result, `${path}.disease_context_review_result`),
    stage4_assessment_status: optStr(v.stage4_assessment_status, `${path}.stage4_assessment_status`),
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
    bundle_id: prodId(a.bundle_id, 'artifact.bundle_id'),
    manifest_sha256: str(a.manifest_sha256, 'artifact.manifest_sha256'),
    upstream_stage2_run: prodId(a.upstream_stage2_run, 'artifact.upstream_stage2_run'),
    candidates: arr(a.candidates, 'artifact.candidates').map((c, i) => parseStage3Candidate(c, `artifact.candidates[${i}]`)),
  };
}

// ── Stage-4 (PK & Safety) ──────────────────────────────────────────────────────
function parseStage4Lanes(v: unknown, path: string): Stage4Lanes {
  if (!isObject(v)) fail('malformed', `${path} must be an object`);
  const lanes = {} as Stage4Lanes;
  for (const lane of STAGE4_LANE_KEYS) lanes[lane] = optStr(v[lane], `${path}.${lane}`);
  return lanes;
}
function parseStage4Candidate(v: unknown, path: string): Stage4Candidate {
  if (!isObject(v)) fail('malformed', `${path} must be an object`);
  return {
    candidate_id: prodId(v.candidate_id, `${path}.candidate_id`),
    active_moiety: optStr(v.active_moiety, `${path}.active_moiety`),
    compound_ids: strList(v.compound_ids, `${path}.compound_ids`),
    target: optStr(v.target, `${path}.target`),
    mechanism: optStr(v.mechanism, `${path}.mechanism`),
    production_eligible: optBool(v.production_eligible, `${path}.production_eligible`),
    production_eligible_reason: optStr(v.production_eligible_reason, `${path}.production_eligible_reason`),
    lanes: parseStage4Lanes(v.lanes, `${path}.lanes`),
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
  if (str(a.schema_version, 'artifact.schema_version') !== STAGE4_UI_ARTIFACT_SCHEMA) {
    fail('unknown_schema_version', `artifact.schema_version must be ${STAGE4_UI_ARTIFACT_SCHEMA}`);
  }
  return {
    schema_version: STAGE4_UI_ARTIFACT_SCHEMA,
    scorecard_set_id: prodId(a.scorecard_set_id, 'artifact.scorecard_set_id'),
    stage4_method_version: str(a.stage4_method_version, 'artifact.stage4_method_version'),
    upstream_stage3_bundle: prodId(a.upstream_stage3_bundle, 'artifact.upstream_stage3_bundle'),
    candidates: arr(a.candidates, 'artifact.candidates').map((c, i) => parseStage4Candidate(c, `artifact.candidates[${i}]`)),
  };
}
